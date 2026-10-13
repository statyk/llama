### Task 6: guardStep — guard first, try/finally, persistence

**Model hint:** opus (spend + blocking path)

**Files:**
- Create: `antenna/src/conditions.ts`, `antenna/src/guard.ts`, `antenna/test/guard.test.ts`

**Interfaces:**
- Consumes: Tasks 1–5 (`readJsonDoc`, `putJson`, `JsonRead`, `billingPeriod`, `evaluateSpend`, `ALERT_LEVELS`, `readUsage`, the latch functions and keys, `reconcileKillSwitch`).
- Produces:
  - `conditions.ts`: `type Priority = "urgent" | "high" | "default"`, `interface AlertCondition { key; priority; title; message; resolvable; once? }`, `READING_WARN_MS` (1 h), `guardConditions(doc, nowMs, blindAfterMs) -> AlertCondition[]`. Its keys are `budget-50:<period start date>:<budget>` and `budget-80:…` (both `once`: sent once per billing period and budget, R13), `tripped-spend`, `tripped-blind` and `guard-reading-failing`.
  - `guard.ts`:
    - `interface GuardEnv`, with vars `MONTHLY_BUDGET_USD`, `BILLING_ANNIVERSARY_DAY`, `GUARD_EVAL_SECONDS`, `BLIND_AFTER_SECONDS` and `KILL_SWITCH_DESCRIPTION`, and secrets `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN` and `CF_WAF_TOKEN`.
    - `interface GuardConfig` (incl. `meterProblems`, `wafProblems`), `DEFAULT_BLIND_AFTER_S = 21600`, `guardConfigFromEnv(env)`.
    - `interface GuardDeps { bucket; now; fetch; config }`, `interface GuardOutcome { blocked: boolean | null; tripped; offair; doc; conditions }`, `guardStep(deps): Promise<GuardOutcome>`, `mergeLostRace(ours, theirs) -> GuardDoc | null`.
    - Further condition keys: `guard-unknown`, `offair-corrupt`, `guard-state-corrupt`, `waf-api`, `waf-corrected`, `budget-file-invalid` (`once`), `guard-write`.

The order inside `guardStep` is the spec's:
1. **Read state.** If the read fails, the outcome is unknown (`blocked: null`): no evaluation, no WAF call, no write. A raise in `budget.json` that expires after the current billing period ends is ignored and alerted (`budget-file-invalid`).
2. **Evaluate.** In a `try`, when `shouldEvaluate` says so. Any exception there, including a missing secret, counts as a failed reading.
3. **Finally.** In the `finally`:
   1. the blind rule;
   2. `blocked = tripped || offair`;
   3. the kill switch is reconciled to `blocked`; a change that undoes a hand toggle (the rule was the opposite of what the guard last set or saw, `prev.waf.enabled`) alerts `waf-corrected`;
   4. `guard.json` is persisted if it changed, with an etag-conditional PUT. On a lost race a trip is merged onto the winner's document (`mergeLostRace`), so a trip is never lost; only a blind trip yields, and only to a winner holding a newer successful reading, which would have cleared it.

- [ ] **Step 1: Write the failing test**

`antenna/test/guard.test.ts`:

```ts
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/guard.test.ts`
Expected: FAIL. `../src/guard` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/conditions.ts`:

```ts
/** Alert conditions: what is wrong right now, recomputed every invocation from
 * state, so a condition that stops being computed has cleared. Dispatch and
 * dedupe live in alerts.ts. */

import type { GuardDoc } from "./latch";
import { ALERT_LEVELS } from "./pricing";

export type Priority = "urgent" | "high" | "default";

export interface AlertCondition {
  key: string; // dedupe key, stable for the condition
  priority: Priority;
  title: string;
  message: string;
  /** Send a "resolved" notice when it clears (latches and outages). */
  resolvable: boolean;
  /** Send it when it first appears and never again -- no repeat, no "resolved",
   * not even if it clears and returns. The key carries what makes a new one
   * (the budget levels: the billing period and the budget). */
  once?: boolean;
}

const usd = (x: number) => `$${x.toFixed(2)}`;
/** A reading failing this long raises an early warning before the blind trip. */
export const READING_WARN_MS = 3_600_000;

/** Conditions that follow from the guard's own state. */
export function guardConditions(doc: GuardDoc, nowMs: number, blindAfterMs: number): AlertCondition[] {
  const out: AlertCondition[] = [];
  const e = doc.evaluation;
  if (e) {
    // Once per level per billing period (and budget: a raise starts the levels afresh).
    const period = (doc.period?.start ?? e.at).slice(0, 10);
    const peak = Math.max(e.actual_usd, e.projected_usd) / e.budget_usd;
    for (const level of ALERT_LEVELS) {
      if (peak >= level) {
        out.push({ key: `budget-${Math.round(level * 100)}:${period}:${e.budget_usd}`,
                   priority: level >= 0.8 ? "high" : "default", resolvable: false, once: true,
                   title: `Station spend at ${Math.round(level * 100)}% of budget`,
                   message: `Actual ${usd(e.actual_usd)}, projected ${usd(e.projected_usd)} of ${usd(e.budget_usd)} ` +
                            `this billing period (evaluated ${e.at}).` });
      }
    }
  }
  if (doc.tripped && doc.reason === "spend") {
    out.push({ key: "tripped-spend", priority: "urgent", resolvable: true, title: "Station blocked: spend",
               message: `The cost guard tripped at ${doc.tripped_at}: ` +
                        (e ? `actual ${usd(e.actual_usd)}, projected ${usd(e.projected_usd)} of ${usd(e.budget_usd)}. ` : "") +
                        "The station is off the air (ENDLIST, off-air page, kill switch). It clears only in a new " +
                        "billing period or after `transmitter budget --raise-to <usd>`, at an evaluation under the thresholds." });
  }
  if (doc.tripped && doc.reason === "blind") {
    out.push({ key: "tripped-blind", priority: "urgent", resolvable: true, title: "Station blocked: guard blind",
               message: `No usage reading has succeeded since ${doc.last_success ?? doc.since}; the guard fails closed. ` +
                        `Last error: ${doc.last_error ?? "none"}. It clears at the first successful reading under the thresholds.` });
  }
  const lastOk = Date.parse(doc.last_success ?? doc.since);
  if (!doc.tripped && doc.last_error !== null && nowMs - lastOk >= READING_WARN_MS) {
    const hoursLeft = Math.max(0, (lastOk + blindAfterMs - nowMs) / 3_600_000);
    out.push({ key: "guard-reading-failing", priority: "high", resolvable: true, title: "Cost guard cannot read usage",
               message: `Usage readings have failed since ${doc.last_success ?? doc.since}: ${doc.last_error}. ` +
                        `The station blocks itself (blind) in ${hoursLeft.toFixed(1)} h unless a reading succeeds.` });
  }
  return out;
}
```

`antenna/src/guard.ts`:

```ts
/** The cost guard step: first in every clock invocation (spec "Cost guard").
 *
 * 1. Read state/guard.json, state/offair.json and state/budget.json. If R2
 *    cannot be read the blocked state is unknown: the outcome is
 *    `blocked: null` and the clock writes nothing this invocation (players
 *    stall on a stale playlist -- toward zero cost -- and nothing is unblocked).
 * 2. try: evaluate (read usage, price it, apply the latch) when the last
 *    attempt is >= 15 min old or a raise is newer; any exception there is a
 *    failed reading.
 * 3. finally: the blind rule, then reconciliation of the kill switch to
 *    blocked = tripped OR offair, then persist guard.json if it changed.
 * The clock does the playlist and index.html work after this returns.
 */

import { type BucketLike, type JsonRead, putJson, readJsonDoc } from "./bucket";
import { type AlertCondition, guardConditions } from "./conditions";
import { applyAttempt, applyBlindRule, BUDGET_KEY, corruptGuardDoc, effectiveBudget, freshGuardDoc, GUARD_KEY,
         type GuardDoc, OFFAIR_KEY, parseGuardDoc, shouldEvaluate, validBaseBudget } from "./latch";
import { readUsage } from "./meter";
import { billingPeriod, type Period } from "./period";
import { evaluateSpend } from "./pricing";
import { reconcileKillSwitch } from "./waf";

export interface GuardEnv {
  MONTHLY_BUDGET_USD?: string;
  /** The day of the month the billing period starts, 00:00 UTC (R12). */
  BILLING_ANNIVERSARY_DAY?: string;
  GUARD_EVAL_SECONDS?: string;
  BLIND_AFTER_SECONDS?: string;
  KILL_SWITCH_DESCRIPTION?: string;
  // Worker secrets (account details never live in the repo):
  CF_ACCOUNT_ID?: string;
  CF_ZONE_ID?: string;
  CF_ANALYTICS_TOKEN?: string;
  CF_WAF_TOKEN?: string;
}

export interface GuardConfig {
  baseBudgetUsd: number;
  anniversaryDay: number;
  evalIntervalMs: number;
  blindAfterMs: number;
  killSwitchDescription: string;
  accountId: string;
  zoneId: string;
  analyticsToken: string;
  wafToken: string;
  /** Why an evaluation cannot run (each attempt fails with these). */
  meterProblems: string[];
  /** Why the kill switch cannot be reconciled. */
  wafProblems: string[];
}

export const DEFAULT_BLIND_AFTER_S = 21_600;
const clampedSeconds = (v: string | undefined, dflt: number, min: number, max: number) => {
  const x = v === undefined || v.trim() === "" ? Number.NaN : Number(v);
  return (Number.isFinite(x) ? Math.min(max, Math.max(min, x)) : dflt) * 1000;
};

/** Bounds keep a typo from weakening the guard: evaluation at least every
 * 15 min (900 s; lower only for verification, floor 60 s), blind after at most
 * 6 h (floor 15 min). A missing or invalid budget or secret is a problem that
 * fails every evaluation -- and so trips blind -- rather than a silent default;
 * so does an invalid BILLING_ANNIVERSARY_DAY, through billingPeriod's refusal. */
export function guardConfigFromEnv(env: GuardEnv): GuardConfig {
  const meterProblems: string[] = [];
  const wafProblems: string[] = [];
  const budget = Number(env.MONTHLY_BUDGET_USD);
  if (!validBaseBudget(budget)) meterProblems.push(`MONTHLY_BUDGET_USD must be a number above 5 and at most 100, not ${JSON.stringify(env.MONTHLY_BUDGET_USD)}`);
  const day = Number(env.BILLING_ANNIVERSARY_DAY);
  const need = (name: keyof GuardEnv, list: string[]) => {
    const v = env[name];
    if (typeof v !== "string" || v.trim() === "") list.push(`secret ${name} is not set`);
    return (v ?? "").trim();
  };
  const accountId = need("CF_ACCOUNT_ID", meterProblems);
  const analyticsToken = need("CF_ANALYTICS_TOKEN", meterProblems);
  const zoneId = need("CF_ZONE_ID", wafProblems);
  const wafToken = need("CF_WAF_TOKEN", wafProblems);
  return {
    baseBudgetUsd: budget, anniversaryDay: day,
    evalIntervalMs: clampedSeconds(env.GUARD_EVAL_SECONDS, 900, 60, 900),
    blindAfterMs: clampedSeconds(env.BLIND_AFTER_SECONDS, DEFAULT_BLIND_AFTER_S, 900, DEFAULT_BLIND_AFTER_S),
    killSwitchDescription: env.KILL_SWITCH_DESCRIPTION?.trim() || "station: kill switch",
    accountId, zoneId, analyticsToken, wafToken, meterProblems, wafProblems,
  };
}

export interface GuardDeps {
  bucket: BucketLike;
  now: () => number;
  fetch: typeof fetch;
  config: GuardConfig;
}

export interface GuardOutcome {
  /** tripped OR offair; null = unknown (state could not be read): write nothing. */
  blocked: boolean | null;
  tripped: boolean | null;
  offair: boolean | null;
  doc: GuardDoc | null;
  conditions: AlertCondition[];
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

function periodOrNull(nowMs: number, cfg: GuardConfig): Period | null {
  try {
    return billingPeriod(nowMs, cfg.anniversaryDay);
  } catch {
    return null;
  }
}

/** After losing the etag race to `theirs`: the document to write so our trip
 * is not lost, or null when theirs stands (a clear or an evaluation that loses
 * the race is dropped: theirs is as recent). A blind trip carries over only if
 * theirs has no newer successful reading -- a newer success would clear it. */
export function mergeLostRace(ours: GuardDoc, theirs: GuardDoc): GuardDoc | null {
  if (!ours.tripped || theirs.tripped) return null;
  if (ours.reason === "blind" && theirs.last_success !== null &&
      (ours.last_success === null || Date.parse(theirs.last_success) > Date.parse(ours.last_success))) {
    return null;
  }
  return { ...theirs, tripped: true, reason: ours.reason, tripped_at: ours.tripped_at,
           tripped_period_start: ours.tripped_period_start, tripped_budget_usd: ours.tripped_budget_usd };
}

/** Persist with the etag read; if another invocation wrote meanwhile, never
 * let our trip be lost (mergeLostRace). */
async function persist(bucket: BucketLike, doc: GuardDoc, etag: string | undefined): Promise<void> {
  if (await putJson(bucket, GUARD_KEY, doc, etag)) return;
  const latest = await readJsonDoc(bucket, GUARD_KEY);
  if (latest.kind !== "ok") return;
  const theirs = parseGuardDoc(latest.value);
  const merged = theirs ? mergeLostRace(doc, theirs) : null;
  if (merged) await putJson(bucket, GUARD_KEY, merged, latest.etag);
}

export async function guardStep(deps: GuardDeps): Promise<GuardOutcome> {
  const { bucket, config: cfg } = deps;
  const nowMs = deps.now();
  const conditions: AlertCondition[] = [];
  let guardRead: JsonRead<unknown>;
  let offairRead: JsonRead<{ offair?: unknown }>;
  try {
    guardRead = await readJsonDoc(bucket, GUARD_KEY);
    offairRead = await readJsonDoc<{ offair?: unknown }>(bucket, OFFAIR_KEY);
  } catch (e) {
    conditions.push({ key: "guard-unknown", priority: "high", resolvable: true, title: "Cost guard cannot read its state",
                      message: `Reading state/ failed (${msg(e)}); the clock wrote nothing this minute and changed nothing.` });
    return { blocked: null, tripped: null, offair: null, doc: null, conditions };
  }
  let budgetRaw: unknown = null;
  try {
    const b = await readJsonDoc(bucket, BUDGET_KEY);
    budgetRaw = b.kind === "ok" ? b.value : null;
  } catch {
    budgetRaw = null; // unreadable raise: the configured budget (stricter) applies
  }

  // The operator's flag. Unreadable bytes fail closed: off the air.
  let offair = false;
  if (offairRead.kind === "ok" && typeof offairRead.value?.offair === "boolean") {
    offair = offairRead.value.offair;
  } else if (offairRead.kind !== "absent") {
    offair = true;
    conditions.push({ key: "offair-corrupt", priority: "high", resolvable: true, title: "state/offair.json unreadable",
                      message: "state/offair.json is not a valid flag; treating the station as off the air. " +
                               "Rewrite it with `transmitter offair on|off`." });
  }

  const budget = effectiveBudget(cfg.baseBudgetUsd, budgetRaw, nowMs, periodOrNull(nowMs, cfg)?.endMs ?? null);
  if (budget.invalid !== null) {
    conditions.push({ key: "budget-file-invalid", priority: "high", resolvable: false, once: true,
                      title: "Budget raise ignored",
                      message: `${budget.invalid}. A raise lasts until the end of the billing period it was made ` +
                               "in: write it with `transmitter budget --raise-to <usd>`." });
  }
  let prev: GuardDoc;
  const parsed = guardRead.kind === "ok" ? parseGuardDoc(guardRead.value) : null;
  if (guardRead.kind === "absent") prev = freshGuardDoc(nowMs);
  else if (parsed) prev = parsed;
  else {
    prev = corruptGuardDoc(nowMs, periodOrNull(nowMs, cfg), budget.budgetUsd);
    conditions.push({ key: "guard-state-corrupt", priority: "urgent", resolvable: true, title: "state/guard.json unreadable",
                      message: "state/guard.json could not be read as guard state; the guard treats the station as " +
                               "tripped for spend. Clear it with `transmitter budget --raise-to <usd>` or wait for the " +
                               "next billing period." });
  }

  const etag = guardRead.kind === "absent" ? undefined : guardRead.etag;
  let doc = prev;
  let blocked = true;
  try {
    if (shouldEvaluate(prev, nowMs, cfg.evalIntervalMs, budget.writtenAtMs)) {
      try {
        if (cfg.meterProblems.length > 0) throw new Error(cfg.meterProblems.join("; "));
        const period = billingPeriod(nowMs, cfg.anniversaryDay);
        const reading = await readUsage(deps.fetch, { accountId: cfg.accountId, token: cfg.analyticsToken }, period, nowMs);
        const evaluation = evaluateSpend(reading, period, nowMs, budget.budgetUsd);
        doc = applyAttempt(doc, { ok: true, evaluation, period, baseBudgetUsd: cfg.baseBudgetUsd });
      } catch (e) {
        doc = applyAttempt(doc, { ok: false, atMs: nowMs, error: msg(e) });
      }
    }
  } finally {
    doc = applyBlindRule(doc, nowMs, cfg.blindAfterMs);
    blocked = doc.tripped || offair;
    try {
      if (cfg.wafProblems.length > 0) throw new Error(cfg.wafProblems.join("; "));
      const r = await reconcileKillSwitch(deps.fetch, { zoneId: cfg.zoneId, token: cfg.wafToken,
                                                        description: cfg.killSwitchDescription }, blocked);
      if (r.changed && prev.waf.enabled === r.enabled) {
        // It was the opposite of what the guard last set or saw: a hand toggle, undone.
        conditions.push({ key: "waf-corrected", priority: "high", resolvable: false, title: "Kill switch toggled by hand",
                          message: `The kill switch was ${r.enabled ? "off" : "on"}, set to ${r.enabled ? "on" : "off"} ` +
                                   `to match blocked=${blocked}. The guard reconciles it every minute: use ` +
                                   "`transmitter offair on|off` instead of the dashboard." });
      }
      doc = { ...doc, waf: { enabled: r.enabled, error: null } };
    } catch (e) {
      doc = { ...doc, waf: { enabled: prev.waf.enabled, error: msg(e) } };
      conditions.push({ key: "waf-api", priority: "high", resolvable: true, title: "Kill switch not reconciled",
                        message: `The WAF kill switch could not be set to ${blocked ? "enabled" : "disabled"}: ${msg(e)}. ` +
                                 (blocked ? "The block is cooperative-only (ENDLIST + off-air page) until a later run succeeds."
                                          : "Retrying every minute.") });
    }
    if (guardRead.kind !== "ok" || JSON.stringify(doc) !== JSON.stringify(prev)) {
      try {
        await persist(bucket, doc, etag);
      } catch (e) {
        conditions.push({ key: "guard-write", priority: "high", resolvable: true, title: "Cost guard cannot save its state",
                          message: `Writing state/guard.json failed: ${msg(e)}.` });
      }
    }
  }
  conditions.push(...guardConditions(doc, nowMs, cfg.blindAfterMs));
  return { blocked, tripped: doc.tripped, offair, doc, conditions };
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/conditions.ts antenna/src/guard.ts antenna/test/guard.test.ts
git commit -m "feat(antenna): guardStep -- evaluate, blind rule and kill-switch reconciliation in its finally"
```

---
