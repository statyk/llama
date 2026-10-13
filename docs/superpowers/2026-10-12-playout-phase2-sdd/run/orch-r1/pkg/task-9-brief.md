### Task 9: Cloud alerts — dedupe, ntfy, email

**Model hint:** sonnet

**Files:**
- Create: `antenna/src/alerts.ts`, `antenna/test/alerts.test.ts`
- Modify: `antenna/src/env.ts`, `antenna/src/index.ts`, `antenna/wrangler.jsonc`

**Interfaces:**
- Consumes: `AlertCondition`, `Priority` (Task 6); the bucket seam (Task 1); `ClockDeps.alerts` (Task 8).
- Produces:
  - `ALERTS_KEY = "state/alerts.json"`, `COOLDOWN_MS` (15 min), `interface AlertEntry`, `type AlertState`, `interface Outgoing { key; kind: "alert" | "repeat" | "resolved"; priority; title; message }`.
  - `planAlerts(prev, conditions, nowMs, repeatMs) -> { next, send }`.
  - `interface Channel { name; send(o) }`, `ntfyChannel(fetchFn, url, token, station)`, `rawEmail(from, to, subject, text, nowMs, id)`, `interface EmailBinding`, `emailChannel(binding, from, to, station, now, Message?)`.
  - `interface AlertEnv`: secrets `NTFY_URL`, `NTFY_TOKEN`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO`; the binding `ALERT_EMAIL` (committed in Task 10; until then the email channel is off); vars `ALERT_REPEAT_HOURS` and `STATION_NAME`.
  - `channelsFromEnv(env, fetchFn, now)`, `repeatMsFromEnv(env)`, `dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs) -> { sent, failed }`, `alertSink(bucket, env, fetchFn, now)`.

Rules (ruling R13). Conditions are recomputed every invocation, so a condition that is not computed has cleared.

- **Send:** when a condition first appears.
- **Repeat:** every `ALERT_REPEAT_HOURS` (6) while it lasts.
- **Resolved:** a notice when a resolvable condition clears.
- **Cooldown:** a condition that returns within 15 minutes counts as continuing (no new message).
- **Once:** a `once` condition (the spend levels, keyed by billing period and budget; `budget-file-invalid`) is sent when it first appears and never again: no repeat, no "resolved", not even when it returns. Its entry is kept 35 days after it clears, longer than a billing period.
- **Failure:** a message no channel accepted is not recorded as sent, so the next invocation retries it (a `once` alert included).
- **No channel configured:** the structured log line is the only output.
- **Overlap:** `alerts.json` is written with an etag-conditional PUT; overlapping invocations may duplicate a message, never lose one.

- [ ] **Step 1: Write the failing test**

`antenna/test/alerts.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ALERTS_KEY, type AlertState, channelsFromEnv, COOLDOWN_MS, dispatchAlerts, emailChannel, ntfyChannel,
         type Outgoing, planAlerts, rawEmail } from "../src/alerts";
import type { AlertCondition } from "../src/conditions";
import { fakeFetch, MemoryBucket } from "./support";

const T0 = Date.parse("2026-10-20T12:00:00Z");
const H = 3_600_000;
const REPEAT = 6 * H;
const cond = (key: string, resolvable = true): AlertCondition =>
  ({ key, priority: "high", resolvable, title: `${key} title`, message: `${key} message` });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("planAlerts", () => {
  it("sends a new condition once, repeats it every REPEAT, and resolves it when it clears", () => {
    let s: AlertState = {};
    let r = planAlerts(s, [cond("waf-api")], T0, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    s = r.next;
    r = planAlerts(s, [cond("waf-api")], T0 + H, REPEAT);
    expect(r.send).toEqual([]);
    s = r.next;
    r = planAlerts(s, [cond("waf-api")], T0 + REPEAT, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
    s = r.next;
    r = planAlerts(s, [], T0 + REPEAT + H, REPEAT);
    expect(r.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "waf-api"]]);
    expect(r.next["waf-api"].active).toBe(false);
  });

  it("does not resolve a non-resolvable condition aloud", () => {
    const s = planAlerts({}, [cond("budget-50", false)], T0, REPEAT).next;
    expect(planAlerts(s, [], T0 + H, REPEAT).send).toEqual([]);
  });

  it("a condition that returns within the cooldown is continuing, not new", () => {
    let s = planAlerts({}, [cond("waf-api")], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + 60_000, REPEAT).next;
    const back = planAlerts(s, [cond("waf-api")], T0 + 120_000, REPEAT);
    expect(back.send).toEqual([]);
    expect(back.next["waf-api"].active).toBe(true);
    s = planAlerts(back.next, [], T0 + 180_000, REPEAT).next;
    expect(planAlerts(s, [cond("waf-api")], T0 + 180_000 + COOLDOWN_MS, REPEAT).send.map((o) => o.kind)).toEqual(["alert"]);
  });

  it("sends a once condition when it first appears, never repeats it, and not again when it returns", () => {
    const once = (key: string): AlertCondition => ({ ...cond(key, false), once: true });
    let r = planAlerts({}, [once("budget-50:2026-10-11:15")], T0, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    r = planAlerts(r.next, [once("budget-50:2026-10-11:15")], T0 + REPEAT, REPEAT);
    expect(r.send).toEqual([]);
    r = planAlerts(r.next, [], T0 + REPEAT + H, REPEAT); // the projection dipped under 50%
    expect(r.send).toEqual([]);
    r = planAlerts(r.next, [once("budget-50:2026-10-11:15")], T0 + 2 * REPEAT, REPEAT);
    expect(r.send).toEqual([]);
    // The next billing period is a new key.
    r = planAlerts(r.next, [once("budget-50:2026-11-11:15")], T0 + 3 * REPEAT, REPEAT);
    expect(r.send.map((o) => o.key)).toEqual(["budget-50:2026-11-11:15"]);
  });

  it("forgets inactive entries after a week", () => {
    let s = planAlerts({}, [cond("x")], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + H, REPEAT).next;
    expect(planAlerts(s, [], T0 + 8 * 24 * H, REPEAT).next).toEqual({});
  });
});

describe("channels", () => {
  const o: Outgoing = { key: "tripped-spend", kind: "alert", priority: "urgent", title: "Station blocked: spend", message: "m" };

  it("ntfy: POST with title, priority, tags and the bearer token", async () => {
    const f = fakeFetch({ "POST https://ntfy.example/topic": () => new Response("{}") });
    await ntfyChannel(f.fetch, "https://ntfy.example/topic", "tk_1", "llama radio").send(o);
    expect(f.calls[0].headers).toMatchObject({ title: "llama radio: Station blocked: spend", priority: "5",
                                               tags: "rotating_light", authorization: "Bearer tk_1" });
    expect(f.calls[0].body).toBe("m");
    const bad = fakeFetch({ "POST ": () => new Response("no", { status: 429 }) });
    await expect(ntfyChannel(bad.fetch, "https://ntfy.example/topic", undefined, "s").send(o)).rejects.toThrow(/429/);
  });

  it("email: a send_email message from the configured sender to the configured recipient", async () => {
    const sent: { from: string; to: string; raw: string }[] = [];
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const ch = emailChannel({ send: async (m) => { sent.push(m as unknown as FakeMessage); } }, "radio@example.org",
                            "ops@example.net", "llama radio", () => T0, FakeMessage as never);
    await ch.send(o);
    expect(sent[0]).toMatchObject({ from: "radio@example.org", to: "ops@example.net" });
    expect(sent[0].raw).toContain("Subject: llama radio: Station blocked: spend\r\n");
  });

  it("rawEmail: headers, an encoded non-ASCII subject, a base64 body", () => {
    const raw = rawEmail("a@example.org", "b@example.net", "Spend — 80%", "héllo", T0, "id1");
    expect(raw).toContain("From: a@example.org\r\nTo: b@example.net\r\n");
    expect(raw).toMatch(/Subject: =\?UTF-8\?B\?[A-Za-z0-9+/=]+\?=\r\n/);
    expect(raw).toContain("Message-ID: <id1@example.org>\r\n");
    expect(raw).toContain("Content-Transfer-Encoding: base64\r\n\r\n");
    const body = raw.split("\r\n\r\n")[1].replace(/\r\n/g, "");
    expect(new TextDecoder().decode(Uint8Array.from(atob(body), (c) => c.charCodeAt(0)))).toBe("héllo");
  });

  it("channelsFromEnv: only what is fully configured", () => {
    const f = fakeFetch({});
    expect(channelsFromEnv({}, f.fetch, () => T0)).toEqual([]);
    expect(channelsFromEnv({ NTFY_URL: "https://n/t" }, f.fetch, () => T0).map((c) => c.name)).toEqual(["ntfy"]);
    const binding = { send: async () => undefined };
    expect(channelsFromEnv({ ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "a@x" }, f.fetch, () => T0)).toEqual([]);
    expect(channelsFromEnv({ ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "a@x", ALERT_EMAIL_TO: "b@y" }, f.fetch, () => T0)
      .map((c) => c.name)).toEqual(["email"]);
  });
});

describe("dispatchAlerts", () => {
  it("sends to every channel, records the send, and does not resend the next minute", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const got: string[] = [];
    const ch = (name: string) => ({ name, send: async (o: Outgoing) => { got.push(`${name}:${o.key}`); } });
    expect(await dispatchAlerts(bucket, [ch("a"), ch("b")], [cond("lead-low")], T0, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["a:lead-low", "b:lead-low"]);
    expect(bucket.json(ALERTS_KEY)["lead-low"].active).toBe(true);
    await dispatchAlerts(bucket, [ch("a")], [cond("lead-low")], T0 + 60_000, REPEAT);
    expect(got).toHaveLength(2);
  });

  it("one working channel is enough; when every channel fails the next invocation retries", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [broken, ok], [cond("waf-api")], T0 + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["waf-api"]);
  });

  it("a once alert no channel accepted is sent at the next invocation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    const c: AlertCondition = { ...cond("budget-80:2026-10-11:15", false), once: true };
    expect(await dispatchAlerts(bucket, [broken], [c], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [c], T0 + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["budget-80:2026-10-11:15"]);
  });

  it("writes alerts.json only when the state changed", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    await dispatchAlerts(bucket, [], [], T0, REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(0);
    await dispatchAlerts(bucket, [], [cond("x")], T0, REPEAT);
    await dispatchAlerts(bucket, [], [cond("x")], T0 + 60_000, REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(1);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/alerts.test.ts`
Expected: FAIL. `../src/alerts` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/alerts.ts` (`cloudflare:email` is a workerd built-in, available in the vitest pool too):

```ts
/** Cloud alerts (spec "Alerts and operations"): conditions computed each
 * invocation are deduped per key in state/alerts.json and sent to ntfy (HTTP
 * POST) and email (Email Routing's send_email binding, to the ALERT_EMAIL_TO
 * secret). Sent when a condition appears, repeated every ALERT_REPEAT_HOURS
 * while it lasts, "resolved" when a resolvable one clears; a `once` condition
 * is sent when it first appears and never again. A condition that clears and
 * returns within COOLDOWN_MS is treated as continuing (no new message), so a
 * flapping API does not page every minute. */

import { EmailMessage } from "cloudflare:email";
import { type BucketLike, putJson, readJsonDoc } from "./bucket";
import type { AlertCondition, Priority } from "./conditions";

export const ALERTS_KEY = "state/alerts.json";
export const COOLDOWN_MS = 15 * 60_000;
const KEEP_INACTIVE_MS = 7 * 86_400_000;
/** A `once` entry is kept this long after it clears: longer than a billing period. */
const ONCE_KEEP_MS = 35 * 86_400_000;
const TIMEOUT_MS = 10_000;

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

export function planAlerts(prev: AlertState, conditions: AlertCondition[], nowMs: number,
                           repeatMs: number): { next: AlertState; send: Outgoing[] } {
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
    if (e.active) {
      next[key] = { ...e, active: false, cleared_at: iso(nowMs) };
      if (e.resolvable) send.push({ key, kind: "resolved", priority: "default", title: e.title,
                                    message: `Resolved: ${e.title} (active since ${e.first_at}).` });
    } else if (age(nowMs, e.cleared_at) < (e.once ? ONCE_KEEP_MS : KEEP_INACTIVE_MS)) {
      next[key] = e;
    }
  }
  return { next, send };
}

export interface Channel {
  name: string;
  send(o: Outgoing): Promise<void>;
}

const NTFY_PRIORITY: Record<Priority, string> = { urgent: "5", high: "4", default: "3" };
const NTFY_TAGS: Record<Priority, string> = { urgent: "rotating_light", high: "warning", default: "information_source" };

export function ntfyChannel(fetchFn: typeof fetch, url: string, token: string | undefined, station: string): Channel {
  return {
    name: "ntfy",
    async send(o) {
      const headers: Record<string, string> = {
        Title: `${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`,
        Priority: o.kind === "resolved" ? "3" : NTFY_PRIORITY[o.priority],
        Tags: o.kind === "resolved" ? "white_check_mark" : NTFY_TAGS[o.priority],
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetchFn(url, { method: "POST", headers, body: o.message, signal: AbortSignal.timeout(TIMEOUT_MS) });
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
                             Message: typeof EmailMessage = EmailMessage): Channel {
  return {
    name: "email",
    async send(o) {
      const subject = `${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`;
      const text = `${o.message}\n\n-- antenna clock, ${iso(now())}\n`;
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
}

export function channelsFromEnv(env: AlertEnv, fetchFn: typeof fetch, now: () => number): Channel[] {
  const station = env.STATION_NAME?.trim() || "llama radio";
  const out: Channel[] = [];
  if (env.NTFY_URL?.trim()) out.push(ntfyChannel(fetchFn, env.NTFY_URL.trim(), env.NTFY_TOKEN?.trim() || undefined, station));
  if (env.ALERT_EMAIL && env.ALERT_EMAIL_FROM?.trim() && env.ALERT_EMAIL_TO?.trim()) {
    out.push(emailChannel(env.ALERT_EMAIL, env.ALERT_EMAIL_FROM.trim(), env.ALERT_EMAIL_TO.trim(), station, now));
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
                                     nowMs: number, repeatMs: number): Promise<{ sent: number; failed: number }> {
  const read = await readJsonDoc<AlertState>(bucket, ALERTS_KEY);
  const prev: AlertState = read.kind === "ok" && read.value && typeof read.value === "object" ? read.value : {};
  const { next, send } = planAlerts(prev, conditions, nowMs, repeatMs);
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
      if (next[o.key]?.once) delete next[o.key]; // never sent: the next invocation sends it as new
      else if (o.kind !== "resolved" && next[o.key]) {
        next[o.key] = { ...next[o.key], last_sent_at: prev[o.key]?.last_sent_at ?? null };
      }
    }
  }
  if (JSON.stringify(next) !== JSON.stringify(prev)) {
    // A lost race means an overlapping invocation recorded the same sends.
    await putJson(bucket, ALERTS_KEY, next, read.kind === "absent" ? undefined : read.etag);
  }
  return { sent, failed };
}

export function alertSink(bucket: BucketLike, env: AlertEnv, fetchFn: typeof fetch, now: () => number) {
  const channels = channelsFromEnv(env, fetchFn, now);
  const repeatMs = repeatMsFromEnv(env);
  return async (conditions: AlertCondition[], nowMs: number) => {
    await dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs);
  };
}
```

Replace `antenna/src/env.ts` with:

```ts
import type { AlertEnv } from "./alerts";
import type { ClockEnv } from "./clock";
import type { GuardEnv } from "./guard";

/** Everything the Worker reads from its environment: wrangler vars, Worker
 * secrets (account details and tokens, never in the repo) and bindings. */
export interface AntennaEnv extends ClockEnv, GuardEnv, AlertEnv {
  BUCKET: R2Bucket;
}
```

Replace `antenna/src/index.ts` with:

```ts
import { alertSink } from "./alerts";
import { r2Bucket } from "./bucket";
import { type ClockResult, configFromEnv, runClock } from "./clock";
import type { AntennaEnv } from "./env";
import { guardConfigFromEnv, guardStep } from "./guard";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const bucket = r2Bucket(env.BUCKET);
    const now = () => Date.now();
    const fetchFn: typeof fetch = (input, init) => fetch(input, init);
    let result: ClockResult | undefined;
    let error: string | undefined;
    try {
      result = await runClock({
        bucket,
        now,
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        scheduledTime: controller.scheduledTime,
        config: configFromEnv(env),
        guard: () => guardStep({ bucket, now, fetch: fetchFn, config: guardConfigFromEnv(env) }),
        alerts: alertSink(bucket, env, fetchFn, now),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      throw e; // still a failed invocation in observability
    } finally {
      // One line per invocation, ALWAYS (including when runClock throws); the
      // phase-1 verification compares scheduled vs actual fire times (lagMs).
      console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                   lagMs: started - controller.scheduledTime, ...result, ...(error ? { error } : {}) }));
    }
  },
} satisfies ExportedHandler<AntennaEnv>;
```

In `antenna/wrangler.jsonc`, replace the line `    "KILL_SWITCH_DESCRIPTION": "station: kill switch"` with:

```jsonc
    "KILL_SWITCH_DESCRIPTION": "station: kill switch",
    // Cloud alerts: ntfy (secrets NTFY_URL, optional NTFY_TOKEN) and email
    // through the ALERT_EMAIL send_email binding, from ALERT_EMAIL_FROM to
    // ALERT_EMAIL_TO (secrets). Never put an address in this file.
    "ALERT_REPEAT_HOURS": "6",
    "STATION_NAME": "llama radio"
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS (the `scheduled handler` test now also writes `state/alerts.json`); no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/alerts.ts antenna/test/alerts.test.ts antenna/src/env.ts antenna/src/index.ts antenna/wrangler.jsonc
git commit -m "feat(antenna): cloud alerts deduped in state/alerts.json, sent to ntfy and Email Routing"
```

---

