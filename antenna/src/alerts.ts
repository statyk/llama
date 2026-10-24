/** Cloud alerts (spec "Alerts and operations"): conditions computed each
 * invocation are deduped per key in state/alerts.json and sent by email (Email
 * Routing's send_email binding, to the ALERT_EMAIL_TO secret), the only
 * channel. Every invocation that sends anything also appends its messages, in
 * one write after the emails, to state/alert-relay.json, which hugo relays to
 * its ntfy (the Worker sends no ntfy: ntfy.sh limits a tierless account per IP,
 * and Workers share egress IPs). A message is delivered when its email was
 * accepted OR the relay write landed. Sent when a condition appears, repeated
 * every ALERT_REPEAT_HOURS while it lasts, "resolved" when a resolvable one
 * clears; a `once` condition is sent when it first appears and never again. A
 * condition must stay absent for COOLDOWN_MS before it counts as cleared (and
 * "resolved" goes out): until then its entry stays active with `clearing_since`
 * set, and a return is continuing (no new message, the repeat clock unchanged),
 * so a flapping API neither pages every minute nor leaves "resolved" as the
 * last word while it is back. An alert never delivered gets no "resolved" when
 * it clears.
 *
 * A key absent from the batch has cleared only when the batch says so
 * (AlertBatch in clock.ts): an incomplete batch resolves nothing, except that
 * guard-family keys resolve whenever the guard itself returned a known outcome.
 *
 * The 3-consecutive gate (operator rule: a check that runs about every minute
 * alerts only after 3 consecutive failures). A key in GATED_KEYS keeps a
 * `streak` of consecutive presences in its entry (capped at GATE): a presence
 * advances it, an absence on a batch that could clear the key resets it, and an
 * absence on one that could not leaves it alone. Every send of a gated key,
 * first alert or repeat, needs a streak of GATE ("resolved" is never gated), so
 * a single blip inside an active episode sends no repeat. There are two
 * exceptions: an immediate condition (below), and an episode whose first
 * message was never delivered, which is resent at once and never re-gated
 * (`first_undelivered` marks one that a failed alert opened over a still-active
 * episode, whose `delivered` it keeps). Below GATE, where a new episode would
 * start, nothing is sent: a key with no stored history gets a `pending` entry
 * (inactive, never sent, dropped when its streak resets), a kept inactive
 * entry keeps its history, and a still-active entry whose clearing window
 * elapsed stays as it is (it may still resolve) until the new episode replaces
 * it at GATE. A gated episode's first message says it followed GATE failing
 * minutes.
 * Two raise sites bypass the gate with a condition's `immediate` flag
 * (conditions.ts): the metronome stall trigger and the guard's post-unblock
 * re-check. Every other key (the spend and off-air latches, `once` keys, the
 * already-debounced ones) is sent at its first presence and stores no streak.
 *
 * Off-account text (email, and the relay, which leaves the account via hugo)
 * never carries an account, zone, ruleset or rule ID: both pass title and
 * message through `redact`. The structured log lines keep the detail. */

import { EmailMessage } from "cloudflare:email";
import { type BucketLike, createJson, putJson, readJsonDoc } from "./bucket";
import type { AlertBatch } from "./clock";
import type { AlertCondition, Priority } from "./conditions";
import { describeError } from "./errors";

export const ALERTS_KEY = "state/alerts.json";
export const COOLDOWN_MS = 15 * 60_000;
const KEEP_INACTIVE_MS = 7 * 86_400_000;
/** A `once` entry is kept this long after it clears: longer than a billing period. */
const ONCE_KEEP_MS = 35 * 86_400_000;
const TIMEOUT_MS = 10_000;
const COMPLETE: AlertBatch = { complete: true, guardComplete: true };

/** Keys the clock itself raises (clock.ts). They clear only on a complete batch. */
export const CLOCK_KEYS: ReadonlySet<string> = new Set([
  "guard-crashed", "index-write", "horizon-missing", "horizon-refused", "lead-low", "offair-without-fallback",
  "clock-inputs", "clock-failed", "metronome-down",
]);
/** Keys the guard raises (guard.ts, conditions.ts), plus the spend levels below.
 * They are all computed whenever the guard returns a known outcome. */
const GUARD_KEYS: ReadonlySet<string> = new Set([
  "tripped-spend", "tripped-blind", "guard-reading-failing", "guard-unknown", "offair-corrupt", "guard-state-corrupt",
  "waf-api", "waf-corrected", "budget-file-invalid", "guard-write", "budget-unreadable",
]);
const SPEND_LEVEL_KEY = /^budget-\d+:/;

/** Consecutive failing invocations a gated key needs before it is sent. */
export const GATE = 3;
/** The every-minute checks gated at GATE (operator-approved list, spec Part 1).
 * Every key not listed here is sent at its first presence. */
export const GATED_KEYS: ReadonlySet<string> = new Set([
  "waf-api", "guard-unknown", "guard-write", "budget-unreadable", "index-write", "clock-inputs", "clock-failed",
  "guard-crashed", "horizon-missing", "metronome-down",
]);
const gated = (c: AlertCondition): boolean => GATED_KEYS.has(c.key) && !c.once;

/** Which part of an invocation computes a key. A key in neither known family
 * counts as clock-family: resolved only on a complete batch (the conservative side). */
export function keyFamily(key: string): "guard" | "clock" {
  if (CLOCK_KEYS.has(key)) return "clock";
  return GUARD_KEYS.has(key) || SPEND_LEVEL_KEY.test(key) ? "guard" : "clock";
}

/** Whether a key absent from this batch has genuinely cleared. */
function clearedIn(key: string, batch: AlertBatch): boolean {
  return batch.complete || (batch.guardComplete && keyFamily(key) === "guard");
}

/** Extra wording on a "resolved" notice whose title alone would overstate what cleared. */
const RESOLVED_NOTE: Record<string, string> = {
  "guard-state-corrupt": "state/guard.json reads cleanly again; any spend trip it caused stays until a raise or a new " +
                         "billing period.",
};

export interface AlertEntry {
  active: boolean;
  resolvable: boolean;
  title: string;
  first_at: string;
  last_sent_at: string | null;
  /** A channel accepted a message of this episode (alert or repeat). Missing
   * (older entries): true when last_sent_at is set -- see wasDelivered. */
  delivered?: boolean;
  cleared_at: string | null;
  /** Absent since then (on batches allowed to resolve it), still active: it
   * clears once absent for COOLDOWN_MS. Missing or null: not clearing. */
  clearing_since?: string | null;
  once?: boolean;
  /** Gated keys only (GATED_KEYS): consecutive presences, capped at GATE.
   * Missing: 0 (an entry written before the gate, or reset by a clean batch). */
  streak?: number;
  /** A gated key with no stored history whose streak is below GATE: `active`
   * false, never sent; dropped (not kept) when its streak resets. */
  pending?: boolean;
  /** This episode's first message reached no channel and no relay, although
   * `delivered` is true: a failed alert that replaced a still-active episode
   * keeps that episode's `delivered`, so its "resolved" is not lost. Read by
   * firstUndelivered; the next send drops it. */
  first_undelivered?: boolean;
}
export type AlertState = Record<string, AlertEntry>;

export interface Outgoing {
  key: string;
  kind: "alert" | "repeat" | "resolved";
  priority: Priority;
  title: string;
  message: string;
}

const iso = (ms: number) => new Date(ms).toISOString();
const age = (nowMs: number, at: string | null) => (at === null ? Number.POSITIVE_INFINITY : nowMs - Date.parse(at));
/** Missing `delivered` counts as delivered when a send was recorded: the
 * conservative side, so a "resolved" may be sent but is never lost. */
const wasDelivered = (e: AlertEntry | undefined): boolean => (e ? e.delivered ?? e.last_sent_at !== null : false);
const notClearing = (e: AlertEntry): AlertEntry => {
  const { clearing_since: _, ...rest } = e;
  return rest;
};
/** The entry with `streak` set (always last, so an unchanged state serializes
 * identically), or without one when `streak` is undefined. */
const withStreak = (e: AlertEntry, streak: number | undefined): AlertEntry => {
  const { streak: _, ...rest } = e;
  return streak === undefined ? rest : { ...rest, streak };
};
/** A stored streak, read defensively (a hand edit must not wedge the gate). */
const storedStreak = (e: AlertEntry | undefined): number => {
  const n = e?.streak;
  return typeof n === "number" && Number.isInteger(n) && n > 0 ? Math.min(n, GATE) : 0;
};
/** The episode's first message has not reached any channel yet. */
const firstUndelivered = (e: AlertEntry): boolean =>
  e.last_sent_at === null && (!wasDelivered(e) || e.first_undelivered === true);
const withoutFirstMark = (e: AlertEntry): AlertEntry => {
  const { first_undelivered: _, ...rest } = e;
  return rest;
};

export function planAlerts(prev: AlertState, conditions: AlertCondition[], nowMs: number, repeatMs: number,
                           batch: AlertBatch = COMPLETE): { next: AlertState; send: Outgoing[] } {
  const next: AlertState = {};
  const send: Outgoing[] = [];
  const seen = new Set<string>();
  for (const c of conditions) {
    if (seen.has(c.key)) continue;
    seen.add(c.key);
    const e = prev[c.key];
    const out = { key: c.key, priority: c.priority, title: c.title, message: c.message };
    // The gate: an immediate condition advances the streak but is never held.
    const streak = gated(c) ? Math.min(GATE, storedStreak(e) + 1) : undefined;
    const held = streak !== undefined && !c.immediate && streak < GATE;
    // Rule 7: a message of a gated episode with no successful send yet says it
    // followed GATE failing minutes (only when this send itself passed the gate).
    const noted = streak !== undefined && !c.immediate && !held
      ? `${c.message} (Alerted after ${GATE} consecutive failing minutes.)` : c.message;
    if (c.once) {
      // Sent once; its entry stays (active or not) so it is never sent again.
      next[c.key] = e ? { ...e, active: true, cleared_at: null }
                      : { active: true, resolvable: false, once: true, title: c.title, first_at: iso(nowMs),
                          last_sent_at: iso(nowMs), cleared_at: null };
      if (!e) send.push({ ...out, kind: "alert" });
    } else if (!e || !e.active || (e.clearing_since != null && age(nowMs, e.clearing_since) >= COOLDOWN_MS)) {
      // New, or back after it cleared (an inactive entry was absent for
      // COOLDOWN_MS; so was one clearing that long with no batch between).
      if (held) {
        // Pending: nothing sent, nothing activated. A kept inactive entry keeps
        // its history; a still-active one (clearing elapsed) stays as it is and
        // may still resolve, until the new episode replaces it at GATE.
        next[c.key] = e ? withStreak(e, streak)
                        : { active: false, pending: true, resolvable: c.resolvable, title: c.title, first_at: iso(nowMs),
                            last_sent_at: null, cleared_at: null, streak };
      } else {
        next[c.key] = withStreak({ active: true, resolvable: c.resolvable, title: c.title, first_at: iso(nowMs),
                                   last_sent_at: iso(nowMs), cleared_at: null, delivered: true }, // dispatch corrects a failure
                                 streak);
        send.push({ ...out, message: noted, kind: "alert" });
      }
    } else if (age(nowMs, e.last_sent_at) >= repeatMs && (!held || firstUndelivered(e))) {
      // A due repeat waits for the gate, except an undelivered first message:
      // that is resent at once, never re-gated (operator ruling 2026-10-24).
      next[c.key] = withStreak({ ...notClearing(withoutFirstMark(e)), active: true, resolvable: c.resolvable,
                                 title: c.title, last_sent_at: iso(nowMs), cleared_at: null,
                                 delivered: true }, // restored on a failure, with the first-message mark
                               streak);
      send.push({ ...out, message: firstUndelivered(e) ? noted : c.message, kind: "repeat" });
    } else {
      // Continuing (a return inside the clearing window included, and a due
      // repeat the gate holds): the repeat clock runs on.
      next[c.key] = withStreak({ ...notClearing(e), active: true, resolvable: c.resolvable, title: c.title,
                                 cleared_at: null }, streak);
    }
  }
  const keep = (key: string, e: AlertEntry) => {
    if (age(nowMs, e.cleared_at) < (e.once ? ONCE_KEEP_MS : KEEP_INACTIVE_MS)) next[key] = e;
  };
  for (const [key, stored] of Object.entries(prev)) {
    if (seen.has(key)) continue;
    const cleared = clearedIn(key, batch);
    if (stored.pending) {
      // A pending-only entry: a batch that could clear it resets its streak
      // (dropped, it has no history); one that could not leaves it unchanged.
      if (!cleared) next[key] = stored;
      continue;
    }
    // Rule 2: an absence that could have been a presence resets the streak.
    const e = cleared ? withStreak(stored, undefined) : stored;
    if (!e.active) {
      keep(key, e);
    } else if (!cleared) {
      // Not computed this invocation, so not known to be absent: unchanged
      // (no "resolved"; an incomplete batch neither starts nor resets the
      // clearing window -- its elapsed time is wall-clock from the first
      // allowed absence, so it may complete on the next allowed batch).
      next[key] = e;
    } else if (e.once) {
      next[key] = { ...e, active: false, cleared_at: iso(nowMs) };
    } else if (e.clearing_since == null) {
      next[key] = { ...e, clearing_since: iso(nowMs) };
    } else if (age(nowMs, e.clearing_since) < COOLDOWN_MS) {
      next[key] = e;
    } else if (!wasDelivered(e)) {
      // Cleared before any channel ever delivered it: no "resolved" for an
      // alert the operator never got; forget it.
    } else {
      // Absent for COOLDOWN_MS: cleared, as of when it was first absent.
      keep(key, { ...notClearing(e), active: false, cleared_at: e.clearing_since });
      if (e.resolvable) {
        const note = RESOLVED_NOTE[key];
        send.push({ key, kind: "resolved", priority: "default", title: e.title,
                    message: `Resolved: ${e.title} (active since ${e.first_at}).${note ? ` ${note}` : ""}` });
      }
    }
  }
  return { next, send };
}

/** Strip account details from text that leaves the account: Cloudflare API
 * path IDs (/zones/<id>, /accounts/<id>, /rulesets/<id>, /rules/<id>), bare
 * 32-hex IDs (the shape of every Cloudflare account, zone, ruleset and rule
 * ID), and the configured values themselves (8 characters or more). */
export function redact(text: string, values: readonly string[] = []): string {
  let out = text;
  for (const v of values) {
    const t = v.trim();
    if (t.length >= 8) out = out.split(t).join("<id>");
  }
  return out
    .replace(/\/(zones|accounts)\/[^/\s"'?:;,)]+/g, "/$1/<id>")
    .replace(/\/rulesets\/(?!phases\/)[^/\s"'?:;,)]+/g, "/rulesets/<id>")
    .replace(/\/rules\/[^/\s"'?:;,)]+/g, "/rules/<id>")
    .replace(/\b[0-9a-f]{32}\b/gi, "<id>");
}

export interface Channel {
  name: string;
  send(o: Outgoing): Promise<void>;
}

function b64(text: string): string {
  let bin = "";
  for (const byte of new TextEncoder().encode(text)) bin += String.fromCharCode(byte);
  return btoa(bin);
}

/** A minimal RFC 5322 text/plain message (base64 body, RFC 2047 subject). */
export function rawEmail(from: string, to: string, subject: string, text: string, nowMs: number, id: string): string {
  const subj = /^[\x20-\x7e]*$/.test(subject) ? subject : `=?UTF-8?B?${b64(subject)}?=`;
  const domain = from.includes("@") ? from.slice(from.lastIndexOf("@") + 1) : "localhost";
  const body = (b64(text).match(/.{1,76}/g) ?? []).join("\r\n");
  return [`From: ${from}`, `To: ${to}`, `Subject: ${subj}`, `Date: ${new Date(nowMs).toUTCString()}`,
          `Message-ID: <${id}@${domain}>`, "MIME-Version: 1.0", "Content-Type: text/plain; charset=utf-8",
          "Content-Transfer-Encoding: base64", "", body, ""].join("\r\n");
}

/** `p`, or a rejection once `ms` have passed (R2 and send_email binding calls
 * have no timeout of their own). The timer is cleared either way. */
async function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      p,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms} ms`)), ms);
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export interface EmailBinding {
  send(message: EmailMessage): Promise<unknown>;
}

/** `timeoutMs` bounds the binding's send: a hung binding cannot hold the
 * invocation open, and a timeout is a channel failure. */
export function emailChannel(binding: EmailBinding, from: string, to: string, station: string, now: () => number,
                             Message: typeof EmailMessage = EmailMessage, secrets: readonly string[] = [],
                             timeoutMs = TIMEOUT_MS): Channel {
  return {
    name: "email",
    async send(o) {
      const subject = redact(`${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`, secrets);
      const text = `${redact(o.message, secrets)}\n\n-- antenna clock, ${iso(now())}\n`;
      const message = new Message(from, to, rawEmail(from, to, subject, text, now(), crypto.randomUUID()));
      await withTimeout(binding.send(message), timeoutMs, "email: send");
    },
  };
}

export interface AlertEnv {
  ALERT_EMAIL?: EmailBinding;
  ALERT_EMAIL_FROM?: string;
  ALERT_EMAIL_TO?: string;
  ALERT_REPEAT_HOURS?: string;
  STATION_NAME?: string;
  // The guard's secrets, read here only to redact them from off-account text.
  CF_ACCOUNT_ID?: string;
  CF_ZONE_ID?: string;
  CF_ANALYTICS_TOKEN?: string;
  CF_WAF_TOKEN?: string;
}

/** The configured account details redacted from every off-account text, on
 * top of redact's patterns. */
export function secretsFromEnv(env: AlertEnv): string[] {
  return [env.CF_ACCOUNT_ID, env.CF_ZONE_ID, env.CF_ANALYTICS_TOKEN, env.CF_WAF_TOKEN]
    .filter((v): v is string => typeof v === "string");
}

/** Email only: the Worker sends no ntfy (ntfy.sh limits a tierless account per
 * IP, and Workers share egress IPs); its alerts reach ntfy through the relay. */
export function channelsFromEnv(env: AlertEnv, now: () => number,
                                Message: typeof EmailMessage = EmailMessage): Channel[] {
  const station = env.STATION_NAME?.trim() || "llama radio";
  const secrets = secretsFromEnv(env);
  const out: Channel[] = [];
  if (env.ALERT_EMAIL && env.ALERT_EMAIL_FROM?.trim() && env.ALERT_EMAIL_TO?.trim()) {
    out.push(emailChannel(env.ALERT_EMAIL, env.ALERT_EMAIL_FROM.trim(), env.ALERT_EMAIL_TO.trim(), station, now,
                          Message, secrets));
  }
  return out;
}

export function repeatMsFromEnv(env: AlertEnv): number {
  const h = Number(env.ALERT_REPEAT_HOURS);
  return (Number.isFinite(h) && h >= 1 ? h : 6) * 3_600_000;
}

/** The stored state, keeping only object entries: a hand edit such as
 * `{"stale": null}` (or a non-object document) must not wedge every alert. */
function validState(value: unknown): AlertState {
  const out: AlertState = {};
  if (value === null || typeof value !== "object" || Array.isArray(value)) return out;
  for (const [k, v] of Object.entries(value)) {
    if (v !== null && typeof v === "object" && !Array.isArray(v)) out[k] = v as AlertEntry;
  }
  return out;
}

/** The first write is create-only (If-None-Match: *), as the guard's is. A
 * store that refuses the precondition outright gets an unconditional write
 * rather than never creating the document (every alert would then resend). */
async function createAlerts(bucket: BucketLike, state: AlertState): Promise<boolean> {
  try {
    return await createJson(bucket, ALERTS_KEY, state);
  } catch {
    return putJson(bucket, ALERTS_KEY, state);
  }
}

/** The relay to hugo (spec Part 2): every sending invocation appends its
 * messages to this object in one write; hugo reads it each minute and sends
 * each message once to its own ntfy, keeping a (stream, seq) cursor. The
 * document's shape is a contract with transmitter (its relay reader). */
export const RELAY_KEY = "state/alert-relay.json";
/** The ring keeps the last RELAY_RING messages. */
export const RELAY_RING = 50;
/** Bounds the relay write (both attempts): it must never hold a spend email. */
export const RELAY_TIMEOUT_MS = 10_000;

/** One relayed message. `at` is the sending invocation's time; `seq` is an
 * integer, strictly increasing within a stream, starting at 1. Title and
 * message are already redacted. */
export interface RelayMessage {
  seq: number;
  at: string;
  key: string;
  kind: "alert" | "repeat" | "resolved";
  priority: Priority;
  title: string;
  message: string;
}
/** `stream` is random, new whenever the Worker creates or recreates the
 * object; `ring` holds the last RELAY_RING messages, ascending seq. */
export interface RelayDoc {
  stream: string;
  ring: RelayMessage[];
}

/** Why a stored relay document is unusable, or null when it is usable: not an
 * object, `stream` not a string, `ring` not an array, or a ring entry that is
 * not a JSON object with an integer (never boolean) `seq`. */
export function relayDocProblem(value: unknown): string | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return "not an object";
  const doc = value as { stream?: unknown; ring?: unknown };
  if (typeof doc.stream !== "string") return "stream is not a string";
  if (!Array.isArray(doc.ring)) return "ring is not an array";
  for (const [i, m] of doc.ring.entries()) {
    if (m === null || typeof m !== "object" || Array.isArray(m)) return `ring[${i}] is not an object`;
    const seq = (m as { seq?: unknown }).seq;
    if (typeof seq !== "number" || !Number.isInteger(seq)) return `ring[${i}].seq is not an integer`;
  }
  return null;
}

/** Appends an invocation's messages; true when the write landed. Never throws. */
export type RelaySink = (messages: Outgoing[], nowMs: number) => Promise<boolean>;

/** Create-only first, as createAlerts: a store that refuses the precondition
 * outright gets an unconditional write. */
async function createRelay(bucket: BucketLike, doc: RelayDoc): Promise<boolean> {
  try {
    return await createJson(bucket, RELAY_KEY, doc);
  } catch {
    return putJson(bucket, RELAY_KEY, doc);
  }
}

/** At most two attempts, so at most 2 PUTs: a lost race re-reads and retries once. */
async function writeRelay(bucket: BucketLike, messages: Outgoing[], nowMs: number, secrets: readonly string[],
                          newStream: () => string): Promise<boolean> {
  const at = iso(nowMs);
  const msgs = (start: number): RelayMessage[] =>
    messages.map((o, i) => ({ seq: start + i, at, key: o.key, kind: o.kind, priority: o.priority,
                              title: redact(o.title, secrets), message: redact(o.message, secrets) }))
      .slice(-RELAY_RING);
  for (let attempt = 0; attempt < 2; attempt++) {
    const read = await readJsonDoc<unknown>(bucket, RELAY_KEY);
    let ok: boolean;
    if (read.kind === "absent") {
      ok = await createRelay(bucket, { stream: newStream(), ring: msgs(1) });
    } else if (read.kind === "ok" && relayDocProblem(read.value) === null) {
      const doc = read.value as RelayDoc;
      // After the highest stored seq, so a seq never repeats within the stream.
      const last = doc.ring.reduce((n, m) => Math.max(n, m.seq), 0);
      const ring = [...doc.ring, ...msgs(last + 1)].slice(-RELAY_RING);
      ok = await putJson(bucket, RELAY_KEY, { stream: doc.stream, ring }, read.etag);
    } else {
      // Corrupt: overwritten over the corrupt object's own etag, with a fresh stream.
      const error = read.kind === "corrupt" ? read.error : relayDocProblem(read.value);
      console.error(JSON.stringify({ event: "alert-relay-corrupt", error }));
      ok = await putJson(bucket, RELAY_KEY, { stream: newStream(), ring: msgs(1) }, read.etag);
    }
    if (ok) return true;
  }
  console.error(JSON.stringify({ event: "alert-relay-failed", error: "lost the write race twice" }));
  return false;
}

/** The relay write, bounded by `timeoutMs`. False on a failure, a timeout or a
 * second lost race, each logged; never throws. `secrets` as for email. */
export function relaySink(bucket: BucketLike, secrets: readonly string[],
                          newStream: () => string = () => crypto.randomUUID(),
                          timeoutMs = RELAY_TIMEOUT_MS): RelaySink {
  return async (messages, nowMs) => {
    try {
      return await withTimeout(writeRelay(bucket, messages, nowMs, secrets, newStream), timeoutMs, "relay: write");
    } catch (e) {
      console.error(JSON.stringify({ event: "alert-relay-failed", error: describeError(e) }));
      return false;
    }
  };
}

/** Plan, send, persist. Every message is logged, then emailed; then all of the
 * invocation's messages go to the relay in one write. A message is delivered
 * when a channel accepted it or the relay write landed; one neither did is not
 * recorded as sent, so the next invocation retries it. */
export async function dispatchAlerts(bucket: BucketLike, channels: Channel[], conditions: AlertCondition[],
                                     nowMs: number, repeatMs: number, batch: AlertBatch = COMPLETE,
                                     relay?: RelaySink): Promise<{ sent: number; failed: number }> {
  const read = await readJsonDoc<unknown>(bucket, ALERTS_KEY);
  const prev = validState(read.kind === "ok" ? read.value : null);
  const { next, send } = planAlerts(prev, conditions, nowMs, repeatMs, batch);
  let sent = 0;
  let failed = 0;
  const emailed: boolean[] = [];
  for (const o of send) {
    console.error(JSON.stringify({ event: "alert", kind: o.kind, key: o.key, title: o.title, message: o.message }));
    let ok = false;
    for (const ch of channels) {
      try {
        await ch.send(o);
        ok = true;
      } catch (e) {
        console.error(JSON.stringify({ event: "alert-channel-failed", channel: ch.name, key: o.key,
                                       error: describeError(e) }));
      }
    }
    emailed.push(ok);
  }
  // After every email, so the relay never delays one.
  const relayed = send.length > 0 && relay !== undefined ? await relay(send, nowMs) : false;
  for (const [i, o] of send.entries()) {
    // With neither a channel nor the relay configured, the log line is all there is.
    const delivered = (channels.length === 0 && relay === undefined) || emailed[i] || relayed;
    if (delivered) sent++;
    else {
      failed++;
      // Still active: the next invocation resolves it again. Without its streak:
      // this batch was clean, so the reset holds.
      if (o.kind === "resolved") next[o.key] = withStreak(prev[o.key], undefined);
      else if (next[o.key]?.once) delete next[o.key]; // never sent: the next invocation sends it as new
      else if (next[o.key]) {
        // Due again at once. A failed alert over no episode, or over a cleared
        // one, opens an undelivered episode; otherwise -- a failed repeat, or a
        // failed alert over a still-active episode (clearing for COOLDOWN_MS
        // after a failed "resolved", or across incomplete batches) -- the entry
        // keeps what the episode already had, so a delivered episode's
        // "resolved" is never dropped. A failed alert that keeps an earlier
        // episode's `delivered` marks the new episode's first message as
        // undelivered all the same, so it is resent at once, never re-gated; a
        // failed repeat keeps the mark the episode had.
        const p = prev[o.key];
        const delivered = o.kind === "alert" && !p?.active ? false : wasDelivered(p);
        const first = o.kind === "alert" ? delivered : p?.first_undelivered === true;
        next[o.key] = withStreak({ ...next[o.key], last_sent_at: null, delivered,
                                   ...(first ? { first_undelivered: true } : {}) }, next[o.key].streak);
      }
    }
  }
  if (JSON.stringify(next) !== JSON.stringify(prev)) {
    // A lost race (false) means an overlapping invocation wrote meanwhile: its
    // state stands and our sends are re-planned from it -- a duplicate, never a loss.
    if (read.kind === "absent") await createAlerts(bucket, next);
    else await putJson(bucket, ALERTS_KEY, next, read.etag);
  }
  return { sent, failed };
}

/** The clock's alert sink (ClockDeps.alerts): the batch's scope is passed through. */
export function alertSink(bucket: BucketLike, env: AlertEnv, now: () => number) {
  const channels = channelsFromEnv(env, now);
  const relay = relaySink(bucket, secretsFromEnv(env));
  const repeatMs = repeatMsFromEnv(env);
  return async (conditions: AlertCondition[], nowMs: number, batch: AlertBatch): Promise<void> => {
    await dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs, batch, relay);
  };
}
