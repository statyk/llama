/** Cloud alerts (spec "Alerts and operations"): conditions computed each
 * invocation are deduped per key in state/alerts.json and sent to ntfy (HTTP
 * POST) and email (Email Routing's send_email binding, to the ALERT_EMAIL_TO
 * secret). Sent when a condition appears, repeated every ALERT_REPEAT_HOURS
 * while it lasts, "resolved" when a resolvable one clears; a `once` condition
 * is sent when it first appears and never again. A condition must stay absent
 * for COOLDOWN_MS before it counts as cleared (and "resolved" goes out): until
 * then its entry stays active with `clearing_since` set, and a return is
 * continuing (no new message, the repeat clock unchanged), so a flapping API
 * neither pages every minute nor leaves "resolved" as the last word while it
 * is back. An alert no channel ever delivered gets no "resolved" when it clears.
 *
 * A key absent from the batch has cleared only when the batch says so
 * (AlertBatch in clock.ts): an incomplete batch resolves nothing, except that
 * guard-family keys resolve whenever the guard itself returned a known outcome.
 *
 * Off-account text (ntfy, email) never carries an account, zone, ruleset or
 * rule ID: every channel passes title and message through `redact`. The
 * structured log lines keep the detail. */

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
    if (c.once) {
      // Sent once; its entry stays (active or not) so it is never sent again.
      next[c.key] = e ? { ...e, active: true, cleared_at: null }
                      : { active: true, resolvable: false, once: true, title: c.title, first_at: iso(nowMs),
                          last_sent_at: iso(nowMs), cleared_at: null };
      if (!e) send.push({ ...out, kind: "alert" });
    } else if (!e || !e.active || (e.clearing_since != null && age(nowMs, e.clearing_since) >= COOLDOWN_MS)) {
      // New, or back after it cleared (an inactive entry was absent for
      // COOLDOWN_MS; so was one clearing that long with no batch between).
      next[c.key] = { active: true, resolvable: c.resolvable, title: c.title, first_at: iso(nowMs),
                      last_sent_at: iso(nowMs), cleared_at: null, delivered: true }; // dispatch corrects a failure
      send.push({ ...out, kind: "alert" });
    } else if (age(nowMs, e.last_sent_at) >= repeatMs) {
      next[c.key] = { ...notClearing(e), active: true, resolvable: c.resolvable, title: c.title, last_sent_at: iso(nowMs),
                      cleared_at: null, delivered: true }; // dispatch restores it on a failure
      send.push({ ...out, kind: "repeat" });
    } else {
      // Continuing (a return inside the clearing window included): the repeat clock runs on.
      next[c.key] = { ...notClearing(e), active: true, resolvable: c.resolvable, title: c.title, cleared_at: null };
    }
  }
  const keep = (key: string, e: AlertEntry) => {
    if (age(nowMs, e.cleared_at) < (e.once ? ONCE_KEEP_MS : KEEP_INACTIVE_MS)) next[key] = e;
  };
  for (const [key, e] of Object.entries(prev)) {
    if (seen.has(key)) continue;
    if (!e.active) {
      keep(key, e);
    } else if (!clearedIn(key, batch)) {
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

const NTFY_PRIORITY: Record<Priority, string> = { urgent: "5", high: "4", default: "3" };
const NTFY_TAGS: Record<Priority, string> = { urgent: "rotating_light", high: "warning", default: "information_source" };

/** `secrets`: configured account details to redact on top of the patterns. */
export function ntfyChannel(fetchFn: typeof fetch, url: string, token: string | undefined, station: string,
                            secrets: readonly string[] = []): Channel {
  return {
    name: "ntfy",
    async send(o) {
      const headers: Record<string, string> = {
        Title: redact(`${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`, secrets),
        Priority: o.kind === "resolved" ? "3" : NTFY_PRIORITY[o.priority],
        Tags: o.kind === "resolved" ? "white_check_mark" : NTFY_TAGS[o.priority],
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetchFn(url, { method: "POST", headers, body: redact(o.message, secrets),
                                       signal: AbortSignal.timeout(TIMEOUT_MS) });
      if (!res.ok) throw new Error(`ntfy: HTTP ${res.status}`);
    },
  };
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

export interface EmailBinding {
  send(message: EmailMessage): Promise<unknown>;
}

/** `timeoutMs` bounds the binding's send like ntfy's fetch: a hung binding
 * cannot hold the invocation open, and a timeout is a channel failure. */
export function emailChannel(binding: EmailBinding, from: string, to: string, station: string, now: () => number,
                             Message: typeof EmailMessage = EmailMessage, secrets: readonly string[] = [],
                             timeoutMs = TIMEOUT_MS): Channel {
  return {
    name: "email",
    async send(o) {
      const subject = redact(`${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`, secrets);
      const text = `${redact(o.message, secrets)}\n\n-- antenna clock, ${iso(now())}\n`;
      const message = new Message(from, to, rawEmail(from, to, subject, text, now(), crypto.randomUUID()));
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([
          binding.send(message),
          new Promise<never>((_, reject) => {
            timer = setTimeout(() => reject(new Error(`email: send timed out after ${timeoutMs} ms`)), timeoutMs);
          }),
        ]);
      } finally {
        if (timer !== undefined) clearTimeout(timer);
      }
    },
  };
}

export interface AlertEnv {
  NTFY_URL?: string;
  NTFY_TOKEN?: string;
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

export function channelsFromEnv(env: AlertEnv, fetchFn: typeof fetch, now: () => number,
                                Message: typeof EmailMessage = EmailMessage): Channel[] {
  const station = env.STATION_NAME?.trim() || "llama radio";
  const secrets = [env.CF_ACCOUNT_ID, env.CF_ZONE_ID, env.CF_ANALYTICS_TOKEN, env.CF_WAF_TOKEN]
    .filter((v): v is string => typeof v === "string");
  const out: Channel[] = [];
  if (env.NTFY_URL?.trim()) {
    out.push(ntfyChannel(fetchFn, env.NTFY_URL.trim(), env.NTFY_TOKEN?.trim() || undefined, station, secrets));
  }
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

/** Plan, send, persist. Every message is also logged. A message no channel
 * accepted is not recorded as sent, so the next invocation retries it. */
export async function dispatchAlerts(bucket: BucketLike, channels: Channel[], conditions: AlertCondition[],
                                     nowMs: number, repeatMs: number,
                                     batch: AlertBatch = COMPLETE): Promise<{ sent: number; failed: number }> {
  const read = await readJsonDoc<unknown>(bucket, ALERTS_KEY);
  const prev = validState(read.kind === "ok" ? read.value : null);
  const { next, send } = planAlerts(prev, conditions, nowMs, repeatMs, batch);
  let sent = 0;
  let failed = 0;
  for (const o of send) {
    console.error(JSON.stringify({ event: "alert", kind: o.kind, key: o.key, title: o.title, message: o.message }));
    let delivered = channels.length === 0; // with no channel configured the log line is all there is
    for (const ch of channels) {
      try {
        await ch.send(o);
        delivered = true;
      } catch (e) {
        console.error(JSON.stringify({ event: "alert-channel-failed", channel: ch.name, key: o.key,
                                       error: describeError(e) }));
      }
    }
    if (delivered) sent++;
    else {
      failed++;
      if (o.kind === "resolved") next[o.key] = prev[o.key]; // still active: the next invocation resolves it again
      else if (next[o.key]?.once) delete next[o.key]; // never sent: the next invocation sends it as new
      else if (next[o.key]) {
        // Due again at once. A failed alert over no episode, or over a cleared
        // one, opens an undelivered episode; otherwise -- a failed repeat, or a
        // failed alert over a still-active episode (clearing for COOLDOWN_MS
        // after a failed "resolved", or across incomplete batches) -- the entry
        // keeps what the episode already had, so a delivered episode's
        // "resolved" is never dropped.
        next[o.key] = { ...next[o.key], last_sent_at: null,
                        delivered: o.kind === "alert" && !prev[o.key]?.active ? false : wasDelivered(prev[o.key]) };
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
export function alertSink(bucket: BucketLike, env: AlertEnv, fetchFn: typeof fetch, now: () => number) {
  const channels = channelsFromEnv(env, fetchFn, now);
  const repeatMs = repeatMsFromEnv(env);
  return async (conditions: AlertCondition[], nowMs: number, batch: AlertBatch): Promise<void> => {
    await dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs, batch);
  };
}
