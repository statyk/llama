import { afterEach, describe, expect, it, vi } from "vitest";
import { ALERTS_KEY, type AlertState, alertSink, CLOCK_KEYS, channelsFromEnv, COOLDOWN_MS, dispatchAlerts, emailChannel,
         keyFamily, ntfyChannel, type Outgoing, planAlerts, rawEmail, redact } from "../src/alerts";
import type { AlertBatch } from "../src/clock";
import type { AlertCondition } from "../src/conditions";
import { guardConfigFromEnv, type GuardEnv, guardStep } from "../src/guard";
import { GRAPHQL_URL } from "../src/meter";
import { API } from "../src/waf";
import { type FetchCall, fakeFetch, json, MemoryBucket, usageResponse } from "./support";

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

describe("planAlerts on an incomplete batch (AlertBatch)", () => {
  const INCOMPLETE: AlertBatch = { complete: false, guardComplete: false };
  const GUARD_ONLY: AlertBatch = { complete: false, guardComplete: true };

  it("resolves nothing that is absent, and starts no cooldown for it, while still sending what is present", () => {
    let s = planAlerts({}, [cond("tripped-spend"), cond("lead-low")], T0, REPEAT).next;
    // One transient R2 failure while tripped: only guard-unknown is computed.
    const r = planAlerts(s, [cond("guard-unknown")], T0 + 60_000, REPEAT, INCOMPLETE);
    expect(r.send.map((o) => [o.kind, o.key])).toEqual([["alert", "guard-unknown"]]);
    expect(r.next["tripped-spend"]).toEqual(s["tripped-spend"]);
    expect(r.next["lead-low"]).toEqual(s["lead-low"]);
    s = r.next;
    // Back to normal 20 minutes later (past the cooldown): continuing, not new;
    // and guard-unknown clears aloud on the complete batch.
    const back = planAlerts(s, [cond("tripped-spend"), cond("lead-low")], T0 + 21 * 60_000, REPEAT);
    expect(back.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "guard-unknown"]]);
  });

  it("still repeats a present condition on an incomplete batch", () => {
    const s = planAlerts({}, [cond("tripped-spend")], T0, REPEAT).next;
    expect(planAlerts(s, [cond("tripped-spend")], T0 + REPEAT, REPEAT, INCOMPLETE).send.map((o) => o.kind))
      .toEqual(["repeat"]);
  });

  it("guardComplete: guard-family keys resolve, clock-family keys do not", () => {
    const s = planAlerts({}, [cond("waf-api"), cond("lead-low"), cond("guard-crashed"), cond("budget-unreadable")],
                         T0, REPEAT).next;
    const r = planAlerts(s, [cond("horizon-missing")], T0 + 60_000, REPEAT, GUARD_ONLY);
    expect(r.send.map((o) => [o.kind, o.key]).sort())
      .toEqual([["alert", "horizon-missing"], ["resolved", "budget-unreadable"], ["resolved", "waf-api"]]);
    expect(r.next["lead-low"]).toEqual(s["lead-low"]);
    expect(r.next["guard-crashed"]).toEqual(s["guard-crashed"]);
  });

  it("a key in neither family is treated as clock-family: resolved only on a complete batch", () => {
    const s = planAlerts({}, [cond("something-new")], T0, REPEAT).next;
    expect(planAlerts(s, [], T0 + 60_000, REPEAT, GUARD_ONLY).send).toEqual([]);
    expect(planAlerts(s, [], T0 + 60_000, REPEAT).send.map((o) => o.kind)).toEqual(["resolved"]);
  });

  it("classifies every key the guard and the clock raise", () => {
    for (const k of ["tripped-spend", "tripped-blind", "budget-50:2026-10-11:15", "budget-80:2026-10-11:40",
                     "guard-reading-failing", "guard-unknown", "offair-corrupt", "guard-state-corrupt", "waf-api",
                     "waf-corrected", "budget-file-invalid", "guard-write", "budget-unreadable"]) {
      expect([k, keyFamily(k)]).toEqual([k, "guard"]);
    }
    const clock = ["guard-crashed", "index-write", "horizon-missing", "horizon-refused", "lead-low",
                   "offair-without-fallback", "clock-inputs", "clock-failed"];
    expect([...CLOCK_KEYS].sort()).toEqual([...clock].sort());
    for (const k of clock) expect([k, keyFamily(k)]).toEqual([k, "clock"]);
    expect(keyFamily("budget-x")).toBe("clock");
  });
});

describe("resolved wording", () => {
  it("guard-state-corrupt's resolution does not imply the spend trip it caused has cleared", () => {
    const c: AlertCondition = { key: "guard-state-corrupt", priority: "urgent", resolvable: true,
                                title: "state/guard.json unreadable", message: "m" };
    const s = planAlerts({}, [c], T0, REPEAT).next;
    const [o] = planAlerts(s, [], T0 + 60_000, REPEAT).send;
    expect(o.kind).toBe("resolved");
    expect(o.message).toMatch(/reads cleanly again/);
    expect(o.message).toMatch(/spend trip it caused stays until a raise or a new (billing )?period/);
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

describe("redaction of account details from off-account text", () => {
  const decodeEmail = (raw: string) => {
    const [head, body] = raw.split("\r\n\r\n");
    const b = body.replace(/\r\n/g, "");
    return head + "\n" + new TextDecoder().decode(Uint8Array.from(atob(b), (c) => c.charCodeAt(0)));
  };

  it("redact: Rulesets/accounts paths, bare 32-hex ids and the configured values", () => {
    const hex = "0123456789abcdef0123456789abcdef";
    expect(redact(`GET /zones/zz9/rulesets/phases/http_request_firewall_custom/entrypoint: HTTP 403`))
      .toBe("GET /zones/<id>/rulesets/phases/http_request_firewall_custom/entrypoint: HTTP 403");
    expect(redact(`PATCH /zones/zz9/rulesets/rs7/rules/r3: HTTP 500`)).toBe("PATCH /zones/<id>/rulesets/<id>/rules/<id>: HTTP 500");
    expect(redact(`/accounts/a1b2/x and zone ${hex}.`)).toBe("/accounts/<id>/x and zone <id>.");
    expect(redact("account acct-secret-77 is wrong", ["acct-secret-77"])).toBe("account <id> is wrong");
    expect(redact("short ids are left alone: ab", ["ab"])).toBe("short ids are left alone: ab");
  });

  it("a WafError carrying the zone, ruleset and rule ids reaches neither ntfy nor email", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const ZONE = "zone-7f3a9c41";
    const RS = "ruleset-4b2e81d0";
    const RULE = "rule-91c0ffee";
    const HEXZ = "fedcba9876543210fedcba9876543210";
    const env: GuardEnv = { MONTHLY_BUDGET_USD: "15", BILLING_ANNIVERSARY_DAY: "11", CF_ACCOUNT_ID: "acct-5e1d",
                            CF_ZONE_ID: ZONE, CF_ANALYTICS_TOKEN: "an-tok", CF_WAF_TOKEN: "waf-tok" };
    const cloud = fakeFetch({
      [`POST ${GRAPHQL_URL}`]: () => json(usageResponse()),
      [`GET ${API}/zones/${ZONE}/rulesets/phases/`]: () =>
        json({ success: true, result: { id: RS, rules: [{ id: RULE, action: "block", description: "station: kill switch",
                                                          expression: "x", enabled: true }] } }),
      [`PATCH ${API}/zones/${ZONE}/rulesets/${RS}/rules/${RULE}`]: (_c: FetchCall) =>
        json({ success: false, errors: [{ code: 10000, message: `zone ${HEXZ}: not authorized` }] }, 403),
    });
    const bucket = new MemoryBucket();
    const out = await guardStep({ bucket, now: () => T0, fetch: cloud.fetch, config: guardConfigFromEnv(env) });
    const waf = out.conditions.find((c) => c.key === "waf-api")!;
    expect(waf.message).toContain(RS); // the guard's own text (and the console) keep the detail

    const ntfy = fakeFetch({ "POST https://ntfy.example/t": () => new Response("{}") });
    const raws: string[] = [];
    const binding = { send: async (m: unknown) => { raws.push((m as { raw: string }).raw); } };
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const channels = channelsFromEnv({ ...env, NTFY_URL: "https://ntfy.example/t", ALERT_EMAIL: binding,
                                       ALERT_EMAIL_FROM: "alerts@lma-radio.com", ALERT_EMAIL_TO: "ops@example.net" },
                                     ntfy.fetch, () => T0, FakeMessage as never);
    expect(await dispatchAlerts(bucket, channels, [waf], T0, REPEAT)).toEqual({ sent: 1, failed: 0 });
    const ntfyText = JSON.stringify(ntfy.calls[0].headers) + ntfy.calls[0].body;
    const emailText = decodeEmail(raws[0]);
    expect(ntfyText).toMatch(/Kill switch not reconciled/);
    expect(emailText).toMatch(/Kill switch not reconciled/);
    for (const text of [ntfyText, emailText]) {
      for (const id of [ZONE, RS, RULE, HEXZ, "acct-5e1d"]) expect([id, text.includes(id)]).toEqual([id, false]);
    }
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

  it("a failed alert for a condition back after the cooldown is retried the next minute, not a repeat period later", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    await dispatchAlerts(bucket, [ok], [cond("waf-api")], T0, REPEAT);
    await dispatchAlerts(bucket, [ok], [], T0 + H, REPEAT); // resolved
    const back = T0 + H + 2 * COOLDOWN_MS;
    expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], back, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [cond("waf-api")], back + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toHaveLength(3);
    expect(got[2]).toMatch(/:waf-api$/);
  });

  it("a resolved notice no channel accepted is retried the next minute", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    await dispatchAlerts(bucket, [ok], [cond("waf-api")], T0, REPEAT);
    expect(await dispatchAlerts(bucket, [broken], [], T0 + H, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [], T0 + H + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["alert:waf-api", "resolved:waf-api"]);
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

  it("alertSink passes the batch through: an incomplete batch resolves nothing", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const ntfy = fakeFetch({ "POST https://n/t": () => new Response("{}") });
    const sink = alertSink(bucket, { NTFY_URL: "https://n/t" }, ntfy.fetch, () => T0);
    await sink([cond("tripped-spend"), cond("lead-low")], T0, { complete: true, guardComplete: true });
    await sink([cond("guard-unknown")], T0 + 60_000, { complete: false, guardComplete: false });
    expect(ntfy.calls.map((c) => c.headers.title)).toEqual(
      ["llama radio: tripped-spend title", "llama radio: lead-low title", "llama radio: guard-unknown title"]);
    await sink([cond("tripped-spend")], T0 + 120_000, { complete: false, guardComplete: true });
    expect(ntfy.calls.map((c) => c.headers.title).slice(3)).toEqual(["llama radio: resolved: guard-unknown title"]);
    expect(bucket.json(ALERTS_KEY)["lead-low"].active).toBe(true);
  });
});
