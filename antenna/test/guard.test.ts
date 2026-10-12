import { describe, expect, it } from "vitest";
import { guardConfigFromEnv, type GuardEnv, guardStep, mergeLostRace } from "../src/guard";
import { BUDGET_KEY, freshGuardDoc, GUARD_KEY, OFFAIR_KEY } from "../src/latch";
import { GRAPHQL_URL } from "../src/meter";
import { API } from "../src/waf";
import { type FetchCall, fakeFetch, json, MemoryBucket, usageResponse } from "./support";

const T0 = Date.parse("2026-10-20T12:00:00Z");
const M = 60_000;
const ENV: GuardEnv = { MONTHLY_BUDGET_USD: "15", BILLING_ANNIVERSARY_DAY: "11", CF_ACCOUNT_ID: "acct",
                        CF_ZONE_ID: "zone1", CF_ANALYTICS_TOKEN: "an-tok", CF_WAF_TOKEN: "waf-tok" };
const ENTRY = `GET ${API}/zones/zone1/rulesets/phases/http_request_firewall_custom/entrypoint`;
const PATCH = `PATCH ${API}/zones/zone1/rulesets/rs1/rules/`;
/** 3M Class A to date and 30k/h recently: actual $14 (> 90% of 15). */
const OVER = usageResponse({ ops: { PutObject: 3_000_000 }, opsRecent: { PutObject: 90_000 } });
const UNDER = usageResponse();
/** 3M Class A to date and none recently: actual = projected = $14 (over at 15, under at 40). */
const FLAT14 = usageResponse({ ops: { PutObject: 3_000_000 }, opsRecent: {} });

function cloud(o: { usage?: object | (() => Response); killEnabled?: boolean } = {}) {
  const state = { enabled: o.killEnabled ?? false };
  const rule = () => ({ id: "r2", action: "block", description: "station: kill switch", expression: "x", enabled: state.enabled });
  const usage = o.usage ?? UNDER;
  const f = fakeFetch({
    [`POST ${GRAPHQL_URL}`]: () => (typeof usage === "function" ? (usage as () => Response)() : json(usage)),
    [ENTRY]: () => json({ success: true, result: { id: "rs1", rules: [rule()] } }),
    [PATCH]: (c: FetchCall) => {
      state.enabled = JSON.parse(c.body!).enabled;
      return json({ success: true, result: { id: "rs1", rules: [rule()] } });
    },
  });
  return { ...f, state, graphqlCalls: () => f.calls.filter((c) => c.url === GRAPHQL_URL).length };
}

function step(bucket: MemoryBucket, c: ReturnType<typeof cloud>, nowMs = T0, env: GuardEnv = ENV) {
  return guardStep({ bucket, now: () => nowMs, fetch: c.fetch, config: guardConfigFromEnv(env) });
}

describe("guardStep", () => {
  it("first run: evaluates, writes guard.json, leaves the kill switch off, not blocked", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: false, tripped: false, offair: false });
    expect(c.graphqlCalls()).toBe(1);
    const doc = bucket.json(GUARD_KEY);
    expect(doc).toMatchObject({ tripped: false, evaluated_at: new Date(T0).toISOString(), waf: { enabled: false, error: null },
                                period: { start: "2026-10-11T00:00:00.000Z", end: "2026-11-11T00:00:00.000Z" } });
    expect(doc.evaluation.budget_usd).toBe(15);
    expect(bucket.objects.get(GUARD_KEY)!.cacheControl).toBe("no-store");
  });

  it("an evaluation over a threshold trips spend and enables the kill switch in the same run", async () => {
    const bucket = new MemoryBucket();
    const c = cloud({ usage: OVER });
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(c.state.enabled).toBe(true);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend", waf: { enabled: true } });
    expect(out.conditions.map((x) => x.key))
      .toEqual(expect.arrayContaining(["budget-50:2026-10-11:15", "budget-80:2026-10-11:15", "tripped-spend"]));
  });

  it("does not re-evaluate within 15 minutes but reconciles the kill switch every run", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    c.state.enabled = true; // someone turned it on by hand
    const out = await step(bucket, c, T0 + 14 * M);
    expect(c.graphqlCalls()).toBe(1);
    expect(out.blocked).toBe(false);
    expect(c.state.enabled).toBe(false);
    await step(bucket, c, T0 + 15 * M);
    expect(c.graphqlCalls()).toBe(2);
  });

  it("alerts waf-corrected when it undoes a hand toggle, not when it carries out its own decision", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    c.state.enabled = true; // turned on by hand in the dashboard
    const out = await step(bucket, c, T0 + M);
    expect(c.state.enabled).toBe(false);
    expect(out.conditions.find((x) => x.key === "waf-corrected")!.message).toMatch(/was on, set to off to match blocked=false/);
    bucket.seed(OFFAIR_KEY, { offair: true }); // the guard's own change: no alert
    const own = await step(bucket, c, T0 + 2 * M);
    expect(c.state.enabled).toBe(true);
    expect(own.conditions.map((x) => x.key)).not.toContain("waf-corrected");
  });

  it("offair blocks fully without touching the latch, and the guard never writes offair.json", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(OFFAIR_KEY, { offair: true, reason: "objection", since: "2026-10-20T00:00:00Z", until: null });
    const c = cloud();
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: true, tripped: false, offair: true });
    expect(c.state.enabled).toBe(true);
    expect(bucket.puts(OFFAIR_KEY)).toBe(0);
    bucket.seed(OFFAIR_KEY, { offair: false, reason: "back", since: "2026-10-20T01:00:00Z", until: null });
    expect((await step(bucket, c, T0 + M)).blocked).toBe(false);
    expect(c.state.enabled).toBe(false);
  });

  it("an unreadable offair.json fails closed: blocked, with an alert", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(OFFAIR_KEY, "{not json");
    const out = await step(bucket, cloud());
    expect(out).toMatchObject({ blocked: true, offair: true });
    expect(out.conditions.map((x) => x.key)).toContain("offair-corrupt");
  });

  it("when state cannot be read the outcome is unknown: no evaluation, no WAF change, no write", async () => {
    const bucket = new MemoryBucket();
    bucket.failGets.add(GUARD_KEY);
    const c = cloud({ killEnabled: true });
    const out = await step(bucket, c);
    expect(out.blocked).toBeNull();
    expect(out.conditions.map((x) => x.key)).toEqual(["guard-unknown"]);
    expect(c.calls).toHaveLength(0);
    expect(bucket.puts()).toBe(0);
  });

  it("a corrupt guard.json becomes a spend trip that an evaluation under the same budget does not clear", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, "garbage");
    const c = cloud();
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(out.conditions.map((x) => x.key)).toContain("guard-state-corrupt");
    expect(bucket.json(GUARD_KEY).reason).toBe("spend");
  });

  it("a failing reading is recorded; after blind_after without success the station blocks (blind)", async () => {
    const bucket = new MemoryBucket();
    const failing = cloud({ usage: () => new Response("upstream", { status: 503 }) });
    let out = await step(bucket, failing);
    expect(out.blocked).toBe(false);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/HTTP 503/);
    out = await step(bucket, failing, T0 + 61 * M);
    expect(out.conditions.map((x) => x.key)).toContain("guard-reading-failing");
    out = await step(bucket, failing, T0 + 6 * 60 * M);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.json(GUARD_KEY).reason).toBe("blind");
    expect(failing.state.enabled).toBe(true);
    // The first successful reading under the thresholds clears blind.
    const healthy = cloud({ killEnabled: true });
    out = await step(bucket, healthy, T0 + 6 * 60 * M + 15 * M);
    expect(out).toMatchObject({ blocked: false, tripped: false });
    expect(healthy.state.enabled).toBe(false);
  });

  it("a thrown fetch (network error) is a failed reading, not a crash", async () => {
    const bucket = new MemoryBucket();
    const f = fakeFetch({ [ENTRY]: () => json({ success: true, result: { id: "rs1", rules: [
      { id: "r2", action: "block", description: "station: kill switch", expression: "x", enabled: false }] } }) });
    const out = await guardStep({ bucket, now: () => T0, fetch: f.fetch, config: guardConfigFromEnv(ENV) });
    expect(out.blocked).toBe(false);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/unexpected fetch: POST/);
  });

  it("missing secrets fail every evaluation and the WAF reconcile, loudly", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    const out = await step(bucket, c, T0, { MONTHLY_BUDGET_USD: "15" });
    expect(c.calls).toHaveLength(0);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/CF_ACCOUNT_ID/);
    expect(out.conditions.map((x) => x.key)).toContain("waf-api");
    expect(bucket.json(GUARD_KEY).waf.error).toMatch(/CF_ZONE_ID/);
  });

  it("a WAF failure while blocked alerts and leaves the decision blocked (cooperative block)", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(OFFAIR_KEY, { offair: true });
    const f = fakeFetch({ [`POST ${GRAPHQL_URL}`]: () => json(UNDER),
                          [ENTRY]: () => json({ success: false, errors: [{ code: 10000, message: "Authentication error" }] }, 403) });
    const out = await guardStep({ bucket, now: () => T0, fetch: f.fetch, config: guardConfigFromEnv(ENV) });
    expect(out.blocked).toBe(true);
    const waf = out.conditions.find((x) => x.key === "waf-api")!;
    expect(waf.message).toMatch(/cooperative-only/);
  });

  it("a raise newer than the last evaluation is evaluated at once and clears spend when under", async () => {
    const bucket = new MemoryBucket();
    await step(bucket, cloud({ usage: FLAT14 }));
    expect(bucket.json(GUARD_KEY).tripped).toBe(true);
    bucket.seed(BUDGET_KEY, { budget_usd: 40, expires: "2026-11-11T00:00:00.000Z", written_at: new Date(T0 + M).toISOString() });
    const c = cloud({ usage: FLAT14, killEnabled: true });
    const out = await step(bucket, c, T0 + 2 * M);
    expect(c.graphqlCalls()).toBe(1);
    expect(out).toMatchObject({ blocked: false, tripped: false });
    expect(bucket.json(GUARD_KEY).evaluation.budget_usd).toBe(40);
  });

  it("ignores and alerts a raise that outlives the billing period", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(BUDGET_KEY, { budget_usd: 40, expires: "2026-12-11T00:00:00.000Z", written_at: new Date(T0 - M).toISOString() });
    const out = await step(bucket, cloud({ usage: FLAT14 }));
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.json(GUARD_KEY).evaluation.budget_usd).toBe(15);
    expect(out.conditions.map((x) => x.key)).toContain("budget-file-invalid");
  });

  it("a bad BILLING_ANNIVERSARY_DAY fails every evaluation, loudly, without reading usage", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c, T0, { ...ENV, BILLING_ANNIVERSARY_DAY: "32" });
    expect(c.graphqlCalls()).toBe(0);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/1\.\.31/);
  });

  it("never loses a trip to an overlapping invocation's write", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, { ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0 - 20 * M).toISOString() });
    const c = cloud({ usage: OVER });
    // Another invocation rewrites guard.json (untripped) between our read and our write.
    const realPut = bucket.put.bind(bucket);
    let raced = false;
    bucket.put = async (key, value, options) => {
      if (key === GUARD_KEY && !raced) {
        raced = true;
        await realPut(key, JSON.stringify({ ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0).toISOString() }),
                      { httpMetadata: { contentType: "application/json", cacheControl: "no-store" } });
      }
      return realPut(key, value, options);
    };
    const out = await step(bucket, c);
    expect(out.blocked).toBe(true);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
  });

  it("writes guard.json only when something changed", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    const before = bucket.puts(GUARD_KEY);
    await step(bucket, c, T0 + M);
    expect(bucket.puts(GUARD_KEY)).toBe(before);
  });
});

describe("mergeLostRace", () => {
  const iso = (ms: number) => new Date(ms).toISOString();
  const lastOk = T0 - 7 * 60 * M;
  const blind = { ...freshGuardDoc(lastOk), last_success: iso(lastOk), tripped: true, reason: "blind" as const,
                  tripped_at: iso(T0) };
  it("carries our trip onto theirs, and drops anything else", () => {
    const theirs = { ...freshGuardDoc(lastOk), last_success: iso(lastOk), evaluated_at: iso(T0) };
    expect(mergeLostRace(blind, theirs)).toMatchObject({ tripped: true, reason: "blind", evaluated_at: iso(T0) });
    expect(mergeLostRace(theirs, blind)).toBeNull();
  });
  it("drops a blind trip when theirs has a newer successful reading", () => {
    expect(mergeLostRace(blind, { ...freshGuardDoc(lastOk), last_success: iso(T0) })).toBeNull();
    const spend = { ...blind, reason: "spend" as const };
    expect(mergeLostRace(spend, { ...freshGuardDoc(lastOk), last_success: iso(T0) })).toMatchObject({ reason: "spend" });
  });
});

describe("guardConfigFromEnv", () => {
  it("bounds the cadence and blind window so a typo cannot weaken the guard", () => {
    expect(guardConfigFromEnv(ENV)).toMatchObject({ evalIntervalMs: 900_000, blindAfterMs: 21_600_000,
      killSwitchDescription: "station: kill switch", baseBudgetUsd: 15, anniversaryDay: 11, meterProblems: [], wafProblems: [] });
    const c = guardConfigFromEnv({ ...ENV, GUARD_EVAL_SECONDS: "86400", BLIND_AFTER_SECONDS: "1e9" });
    expect(c.evalIntervalMs).toBe(900_000);
    expect(c.blindAfterMs).toBe(21_600_000);
    expect(guardConfigFromEnv({ ...ENV, GUARD_EVAL_SECONDS: "1", BLIND_AFTER_SECONDS: "1" }))
      .toMatchObject({ evalIntervalMs: 60_000, blindAfterMs: 900_000 });
  });
  it("reports a bad budget as a problem, not a default", () => {
    expect(guardConfigFromEnv({ ...ENV, MONTHLY_BUDGET_USD: "5" }).meterProblems.join()).toMatch(/MONTHLY_BUDGET_USD/);
  });
});

describe("guardStep: races and failure paths beyond the plan's", () => {
  const racerPut = (bucket: MemoryBucket, racer: () => Promise<unknown>) => {
    const realPut = bucket.put.bind(bucket);
    let raced = false;
    bucket.put = async (key, value, options) => {
      if (key === GUARD_KEY && !raced) {
        raced = true;
        await racer();
      }
      return realPut(key, value, options);
    };
  };
  const writeRaw = (bucket: MemoryBucket, doc: unknown) =>
    bucket.put(GUARD_KEY, typeof doc === "string" ? doc : JSON.stringify(doc),
               { httpMetadata: { contentType: "application/json", cacheControl: "no-store" } });

  it("first creation is create-only: an untripped first run never overwrites a racer's trip, and reports it", async () => {
    const bucket = new MemoryBucket();
    const theirs = { ...freshGuardDoc(T0), tripped: true, reason: "spend", tripped_at: new Date(T0).toISOString(),
                     tripped_period_start: "2026-10-11T00:00:00.000Z", tripped_budget_usd: 15,
                     evaluated_at: new Date(T0).toISOString(), last_success: new Date(T0).toISOString() };
    racerPut(bucket, () => writeRaw(bucket, theirs));
    const out = await step(bucket, cloud());
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(out.conditions.map((x) => x.key)).toContain("tripped-spend");
  });

  it("first creation: a tripped first run that loses the create merges its trip onto the racer's document", async () => {
    const bucket = new MemoryBucket();
    racerPut(bucket, () => writeRaw(bucket, { ...freshGuardDoc(T0), evaluated_at: new Date(T0).toISOString() }));
    const out = await step(bucket, cloud({ usage: OVER }));
    expect(out.blocked).toBe(true);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
  });

  it("a create-only put the store refuses outright falls back to an unconditional write", async () => {
    const bucket = new MemoryBucket();
    const realPut = bucket.put.bind(bucket);
    bucket.put = async (key, value, options) => {
      if (options.onlyIf && "etagDoesNotMatch" in options.onlyIf) throw new Error("unsupported precondition");
      return realPut(key, value, options);
    };
    const out = await step(bucket, cloud());
    expect(out.conditions.map((x) => x.key)).not.toContain("guard-write");
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: false, evaluated_at: new Date(T0).toISOString() });
  });

  it("a document deleted between read and write is rewritten, not dropped", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, { ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0 - 20 * M).toISOString() });
    racerPut(bucket, async () => { bucket.objects.delete(GUARD_KEY); });
    const out = await step(bucket, cloud({ usage: OVER }));
    expect(out.blocked).toBe(true);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
  });

  it("a winner that wrote unreadable bytes is left for the next reader, and this run reports tripped", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, { ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0 - 20 * M).toISOString() });
    racerPut(bucket, () => writeRaw(bucket, "garbage"));
    const out = await step(bucket, cloud());
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.objects.get(GUARD_KEY)!.body).toBe("garbage");
  });

  it("losing every retry is a guard-write alert, and our trip still decides this run", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, { ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0 - 20 * M).toISOString() });
    const realPut = bucket.put.bind(bucket);
    let n = 0;
    const writeRaw2 = () => realPut(GUARD_KEY, JSON.stringify({ ...freshGuardDoc(T0 - 60 * M),
      evaluated_at: new Date(T0 - n++).toISOString() }), { httpMetadata: { contentType: "application/json", cacheControl: "no-store" } });
    bucket.put = async (key, value, options) => {
      if (key === GUARD_KEY) await writeRaw2(); // someone always writes first
      return realPut(key, value, options);
    };
    const out = await step(bucket, cloud({ usage: OVER }));
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(out.conditions.find((x) => x.key === "guard-write")!.message).toMatch(/lost the write race 3 times/);
  });

  it("a network failure or timeout from the Rulesets API is waf-api and leaves the decision blocked", async () => {
    for (const err of [new TypeError("network connection lost"), new DOMException("timed out", "TimeoutError")]) {
      const bucket = new MemoryBucket();
      bucket.seed(OFFAIR_KEY, { offair: true });
      const f = fakeFetch({ [`POST ${GRAPHQL_URL}`]: () => json(UNDER), [ENTRY]: () => { throw err; } });
      const out = await guardStep({ bucket, now: () => T0, fetch: f.fetch, config: guardConfigFromEnv(ENV) });
      expect(out.blocked).toBe(true);
      expect(out.conditions.find((x) => x.key === "waf-api")!.message).toMatch(/cooperative-only/);
      expect(bucket.json(GUARD_KEY).waf.error).toBe(err.message);
    }
  });

  it("a document deleted between read and write is re-created create-only: a racer that creates it first stands", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, { ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0 - 20 * M).toISOString() });
    const theirs = { ...freshGuardDoc(T0), tripped: true, reason: "spend", tripped_at: new Date(T0).toISOString(),
                     tripped_period_start: "2026-10-11T00:00:00.000Z", tripped_budget_usd: 15,
                     evaluated_at: new Date(T0).toISOString(), last_success: new Date(T0).toISOString() };
    const realPut = bucket.put.bind(bucket);
    let n = 0;
    bucket.put = async (key, value, options) => {
      if (key === GUARD_KEY && n === 0) bucket.objects.delete(GUARD_KEY); // deleted before our etag write
      if (key === GUARD_KEY && n === 1) { // re-created (tripped) before our retry
        await realPut(GUARD_KEY, JSON.stringify(theirs), { httpMetadata: { contentType: "application/json", cacheControl: "no-store" } });
      }
      if (key === GUARD_KEY) n++;
      return realPut(key, value, options);
    };
    const out = await step(bucket, cloud());
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
    expect(out).toMatchObject({ blocked: true, tripped: true });
  });

  it("only a refused create-only write on a still-absent key falls back to an unconditional write", async () => {
    const bucket = new MemoryBucket();
    const realPut = bucket.put.bind(bucket);
    bucket.put = async (key, value, options) =>
      options.onlyIf && "etagDoesNotMatch" in options.onlyIf ? null : realPut(key, value, options); // a store refusing "*"
    const out = await step(bucket, cloud());
    expect(out.conditions.map((x) => x.key)).not.toContain("guard-write");
    expect(bucket.json(GUARD_KEY)).toMatchObject({ evaluated_at: new Date(T0).toISOString() });
  });

  it("a non-evaluating run that turns the kill switch off folds in a racer's newer trip (blocked this minute)", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c); // evaluated at T0, untripped, switch off
    c.state.enabled = true; // a racer has enabled it...
    const racer = { ...bucket.json(GUARD_KEY), tripped: true, reason: "spend", tripped_at: new Date(T0 + M).toISOString(),
                    tripped_period_start: "2026-10-11T00:00:00.000Z", tripped_budget_usd: 15, waf: { enabled: true, error: null } };
    // ...and writes its tripped guard.json between our read and our reconcile.
    const realGet = bucket.get.bind(bucket);
    let reads = 0;
    bucket.get = async (key) => {
      const r = await realGet(key);
      if (key === GUARD_KEY && reads++ === 0) await writeRaw(bucket, racer);
      return r;
    };
    const out = await step(bucket, c, T0 + 2 * M);
    expect(c.graphqlCalls()).toBe(1); // no evaluation this run
    expect(c.state.enabled).toBe(false); // our reconcile acted on the older state...
    expect(out).toMatchObject({ blocked: true, tripped: true }); // ...but the outcome holds the racer's trip
    expect(out.conditions.map((x) => x.key)).toContain("tripped-spend");
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
    // The next run re-enables it; the correction notice allows for an overlapping invocation.
    bucket.get = realGet;
    const next = await step(bucket, c, T0 + 3 * M);
    expect(c.state.enabled).toBe(true);
    expect(next.conditions.find((x) => x.key === "waf-corrected")!.message).toMatch(/by hand or by an overlapping invocation/);
  });

  it("an unblocking run with nothing newer in state does not fold anything in", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    c.state.enabled = true; // a genuine hand toggle
    const out = await step(bucket, c, T0 + M);
    expect(out).toMatchObject({ blocked: false, tripped: false });
    expect(bucket.log.filter((l) => l === `head ${GUARD_KEY}`)).toHaveLength(1);
  });

  it("a throwing offair.json get is unknown: no fetch, no write", async () => {
    const bucket = new MemoryBucket();
    bucket.failGets.add(OFFAIR_KEY);
    const c = cloud({ killEnabled: true });
    const out = await step(bucket, c);
    expect(out.blocked).toBeNull();
    expect(out.conditions.map((x) => x.key)).toEqual(["guard-unknown"]);
    expect(c.calls).toHaveLength(0);
    expect(bucket.puts()).toBe(0);
  });

  it("a budget.json read that throws skips the evaluation and alerts; the next minute evaluates against the raise", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(BUDGET_KEY, { budget_usd: 40, expires: "2026-11-11T00:00:00.000Z", written_at: new Date(T0 - 60 * M).toISOString() });
    bucket.failGets.add(BUDGET_KEY);
    const c = cloud({ usage: FLAT14 }); // over the $15 base, under the $40 raise
    const out = await step(bucket, c);
    expect(c.graphqlCalls()).toBe(0);
    expect(out).toMatchObject({ blocked: false, tripped: false });
    expect(out.conditions.find((x) => x.key === "budget-unreadable")).toMatchObject({ resolvable: true, priority: "high" });
    expect(bucket.json(GUARD_KEY)).toMatchObject({ evaluated_at: null, tripped: false });
    bucket.failGets.delete(BUDGET_KEY);
    const next = await step(bucket, c, T0 + M);
    expect(c.graphqlCalls()).toBe(1);
    expect(next).toMatchObject({ blocked: false, tripped: false });
    expect(next.conditions.map((x) => x.key)).not.toContain("budget-unreadable");
    expect(bucket.json(GUARD_KEY).evaluation.budget_usd).toBe(40);
  });

  it("a corrupt budget.json evaluates against the base budget and alerts", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(BUDGET_KEY, "{not json");
    const out = await step(bucket, cloud({ usage: FLAT14 }));
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.json(GUARD_KEY).evaluation.budget_usd).toBe(15);
    expect(out.conditions.map((x) => x.key)).toContain("budget-unreadable");
  });

  it("a hand-edited guard.json the alert conditions cannot read is corrupt (a spend trip), not a throw", async () => {
    const bucket = new MemoryBucket();
    const first = cloud();
    await step(bucket, first);
    const edited = bucket.json(GUARD_KEY);
    delete edited.evaluation.at;
    bucket.seed(GUARD_KEY, { ...edited, period: null });
    const out = await step(bucket, cloud(), T0 + M);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(out.conditions.map((x) => x.key)).toContain("guard-state-corrupt");
    expect(bucket.json(GUARD_KEY).reason).toBe("spend");
  });

  it("blank secrets count as missing: no network call at all", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c, T0, { ...ENV, CF_ACCOUNT_ID: " ", CF_ANALYTICS_TOKEN: "", CF_ZONE_ID: "\t", CF_WAF_TOKEN: " " });
    expect(c.calls).toHaveLength(0);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/CF_ACCOUNT_ID.*CF_ANALYTICS_TOKEN/);
    expect(bucket.json(GUARD_KEY).waf.error).toMatch(/CF_ZONE_ID.*CF_WAF_TOKEN/);
  });

  it("an invalid MONTHLY_BUDGET_USD fails the evaluation before any usage read", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c, T0, { ...ENV, MONTHLY_BUDGET_USD: "abc" });
    expect(c.graphqlCalls()).toBe(0);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: false, last_success: null });
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/MONTHLY_BUDGET_USD/);
  });

  it("blind still trips 6 h after the last success while state/budget.json gets keep throwing", async () => {
    const bucket = new MemoryBucket();
    bucket.failGets.add(BUDGET_KEY);
    const c = cloud();
    const first = await step(bucket, c);
    expect(first.conditions.map((x) => x.key)).toContain("budget-unreadable");
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: false, evaluated_at: null });
    const later = await step(bucket, c, T0 + 6 * 60 * M + M);
    expect(later).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "blind" });
  });
});

describe("mergeLostRace: spend over blind", () => {
  it("a spend trip replaces a winner's blind trip; a blind trip never replaces a winner's spend trip", () => {
    const iso = (ms: number) => new Date(ms).toISOString();
    const spend = { ...freshGuardDoc(T0), tripped: true, reason: "spend" as const, tripped_at: iso(T0),
                    tripped_period_start: "2026-10-11T00:00:00.000Z", tripped_budget_usd: 15, last_success: iso(T0) };
    const blind = { ...freshGuardDoc(T0 - 7 * 60 * M), tripped: true, reason: "blind" as const, tripped_at: iso(T0) };
    expect(mergeLostRace(spend, blind)).toMatchObject({ tripped: true, reason: "spend", tripped_budget_usd: 15 });
    expect(mergeLostRace(blind, spend)).toBeNull();
    expect(mergeLostRace(spend, spend)).toBeNull();
  });
});
