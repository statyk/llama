/** Cloud alerts (spec "Alerts and operations"): conditions computed each
 * invocation are deduped per key in state/alerts.json and sent to ntfy (HTTP
 * POST) and email (Email Routing's send_email binding, to the ALERT_EMAIL_TO
 * secret). Sent when a condition appears, repeated every ALERT_REPEAT_HOURS
 * while it lasts, "resolved" when a resolvable one clears; a `once` condition
 * is sent when it first appears and never again. A condition that clears and
 * returns within COOLDOWN_MS is treated as continuing (no new message), so a
 * flapping API does not page every minute.
 *
 * A key absent from the batch has cleared only when the batch says so
 * (AlertBatch in clock.ts): an incomplete batch resolves nothing, except that
 * guard-family keys resolve whenever the guard itself returned a known outcome.
 *
 * Off-account text (ntfy, email) never carries an account, zone, ruleset or
 * rule ID: every channel passes title and message through `redact`. The
 * structured log lines keep the detail. */

import { EmailMessage } from "cloudflare:email";
import { type BucketLike, putJson, readJsonDoc } from "./bucket";
import type { AlertBatch } from "./clock";
import type { AlertCondition, Priority } from "./conditions";

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
  "clock-inputs", "clock-failed",
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
  cleared_at: string | null;
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
    } else if (!e || (!e.active && age(nowMs, e.cleared_at) >= COOLDOWN_MS)) {
      next[c.key] = { active: true, resolvable: c.resolvable, title: c.title, first_at: iso(nowMs),
                      last_sent_at: iso(nowMs), cleared_at: null };
      send.push({ ...out, kind: "alert" });
    } else if (age(nowMs, e.last_sent_at) >= repeatMs) {
      next[c.key] = { ...e, active: true, resolvable: c.resolvable, title: c.title, last_sent_at: iso(nowMs), cleared_at: null };
      send.push({ ...out, kind: "repeat" });
    } else {
      next[c.key] = { ...e, active: true, resolvable: c.resolvable, title: c.title, cleared_at: null };
    }
  }
  for (const [key, e] of Object.entries(prev)) {
    if (seen.has(key)) continue;
    if (e.active && !clearedIn(key, batch)) {
      // Not computed this invocation, so not known to have cleared: unchanged
      // (no "resolved", no cleared_at, so no cooldown starts).
      next[key] = e;
    } else if (e.active) {
      next[key] = { ...e, active: false, cleared_at: iso(nowMs) };
      if (e.resolvable) {
        const note = RESOLVED_NOTE[key];
        send.push({ key, kind: "resolved", priority: "default", title: e.title,
                    message: `Resolved: ${e.title} (active since ${e.first_at}).${note ? ` ${note}` : ""}` });
      }
    } else if (age(nowMs, e.cleared_at) < (e.once ? ONCE_KEEP_MS : KEEP_INACTIVE_MS)) {
      next[key] = e;
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

export function emailChannel(binding: EmailBinding, from: string, to: string, station: string, now: () => number,
                             Message: typeof EmailMessage = EmailMessage, secrets: readonly string[] = []): Channel {
  return {
    name: "email",
    async send(o) {
      const subject = redact(`${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`, secrets);
      const text = `${redact(o.message, secrets)}\n\n-- antenna clock, ${iso(now())}\n`;
      await binding.send(new Message(from, to, rawEmail(from, to, subject, text, now(), crypto.randomUUID())));
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

/** Plan, send, persist. Every message is also logged. A message no channel
 * accepted is not recorded as sent, so the next invocation retries it. */
export async function dispatchAlerts(bucket: BucketLike, channels: Channel[], conditions: AlertCondition[],
                                     nowMs: number, repeatMs: number,
                                     batch: AlertBatch = COMPLETE): Promise<{ sent: number; failed: number }> {
  const read = await readJsonDoc<AlertState>(bucket, ALERTS_KEY);
  const prev: AlertState = read.kind === "ok" && read.value && typeof read.value === "object" ? read.value : {};
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
                                       error: e instanceof Error ? e.message : String(e) }));
      }
    }
    if (delivered) sent++;
    else {
      failed++;
      if (o.kind === "resolved") next[o.key] = prev[o.key]; // still active: the next invocation resolves it again
      else if (next[o.key]?.once) delete next[o.key]; // never sent: the next invocation sends it as new
      else if (next[o.key]) next[o.key] = { ...next[o.key], last_sent_at: null }; // due again at once
    }
  }
  if (JSON.stringify(next) !== JSON.stringify(prev)) {
    // A lost race means an overlapping invocation recorded the same sends.
    await putJson(bucket, ALERTS_KEY, next, read.kind === "absent" ? undefined : read.etag);
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
