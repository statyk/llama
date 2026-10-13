### Task 4: The latch — guard.json, blind rule, budget raises

**Model hint:** opus (spend path)

**Files:**
- Create: `antenna/src/latch.ts`, `antenna/test/latch.test.ts`

**Interfaces:**
- Consumes: `Period` (Task 1); `Evaluation`, `overThreshold`, `PRICES`, `Usage` (Task 2).
- Produces:
  - `GUARD_KEY = "state/guard.json"`, `BUDGET_KEY = "state/budget.json"`, `OFFAIR_KEY = "state/offair.json"`, `MAX_BUDGET_USD = 100`.
  - `type TripReason = "spend" | "blind"`, `interface StoredEvaluation`, and `interface GuardDoc`, which is the `state/guard.json` schema transmitter reads (Task 12). Its fields:
    - `schema: 1`, `tripped`, `reason`, `tripped_at`;
    - `tripped_period_start`, `tripped_budget_usd`, `since`, `last_success`;
    - `evaluated_at`, `last_error`, `period: {start, end}`, `evaluation`, `waf: {enabled, error}`.
  - `freshGuardDoc(nowMs)`, `parseGuardDoc(raw) -> GuardDoc | null`, `corruptGuardDoc(nowMs, period | null, budgetUsd)`.
  - `type Attempt = { ok: true; evaluation; period; baseBudgetUsd } | { ok: false; atMs; error }`, `applyAttempt(prev, attempt) -> GuardDoc`, `applyBlindRule(doc, nowMs, blindAfterMs) -> GuardDoc`, `shouldEvaluate(doc, nowMs, intervalMs, budgetWrittenAtMs | null) -> boolean`.
  - `interface EffectiveBudget { budgetUsd; raisedUntil; writtenAtMs; invalid }`, `effectiveBudget(baseUsd, raw, nowMs, periodEndMs)` (a raise that expires after `periodEndMs` is ignored and described in `invalid`; a `written_at` ahead of `nowMs` is clamped to it), `validBaseBudget(v)`.

The latch rules (spec "Blocking", rulings R1 and R3) are in the module docstring below. The tests are the authority. Each rule:
- **set spend:** an evaluation over a threshold always leaves or sets reason `spend`;
- **set blind:** no successful reading for `blind_after`;
- **clear blind:** the first successful reading under the thresholds;
- **clear spend:** a successful reading under the thresholds in a new period, or with a budget above the one it last tripped at;
- **failed reading:** never sets or clears the latch;
- **blind vs spend:** blind never downgrades spend.

- [ ] **Step 1: Write the failing test**

`antenna/test/latch.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { type Attempt, applyAttempt, applyBlindRule, corruptGuardDoc, effectiveBudget, freshGuardDoc, type GuardDoc,
         MAX_BUDGET_USD, parseGuardDoc, shouldEvaluate, validBaseBudget } from "../src/latch";
import type { Evaluation } from "../src/pricing";

const H = 3_600_000;
const T0 = Date.parse("2026-10-20T00:00:00Z");
const P1 = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const P2 = { startMs: P1.endMs, endMs: Date.parse("2026-12-11T00:00:00Z") };
const usage = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0 };

function ok(atMs: number, actualUsd: number, projectedUsd: number, budgetUsd = 15, period = P1): Attempt {
  const evaluation: Evaluation = { atMs, actualUsd, projectedUsd, budgetUsd, periodToDate: usage, projected: usage,
                                   unknownActionTypes: [] };
  return { ok: true, evaluation, period, baseBudgetUsd: 15 };
}
const fail = (atMs: number): Attempt => ({ ok: false, atMs, error: "boom" });
const UNDER = [5.2, 6] as const;
const OVER = [5.2, 15] as const;

describe("the tripped latch", () => {
  it("sets reason spend on a reading over a threshold and records the period and budget", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_period_start: "2026-10-11T00:00:00.000Z",
                              tripped_budget_usd: 15, last_success: new Date(T0).toISOString() });
    expect(d.evaluation).toMatchObject({ actual_usd: 5.2, projected_usd: 15, budget_usd: 15, base_budget_usd: 15 });
  });

  it("does not clear spend on a later reading under the thresholds in the same period at the same budget", () => {
    let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    d = applyAttempt(d, ok(T0 + H, ...UNDER));
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_at: new Date(T0).toISOString() });
  });

  it("clears spend in a new period, only when that period's reading is under the thresholds", () => {
    let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(applyAttempt(d, ok(P2.startMs + H, 5, 15, 15, P2)).tripped).toBe(true); // over again: stays
    d = applyAttempt(d, ok(P2.startMs + H, 5, 6, 15, P2));
    expect(d).toMatchObject({ tripped: false, reason: null, tripped_at: null, tripped_budget_usd: null });
  });

  it("clears spend after a raise, only if that evaluation is under; an over evaluation consumes the raise", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(applyAttempt(d, ok(T0 + H, 5.2, 19, 20)).tripped).toBe(false);
    const stillOver = applyAttempt(d, ok(T0 + H, 5.2, 21, 20));
    expect(stillOver).toMatchObject({ tripped: true, reason: "spend", tripped_budget_usd: 20 });
    expect(applyAttempt(stillOver, ok(T0 + 2 * H, 5.2, 6, 20)).tripped).toBe(true); // needs a further raise
  });

  it("a failed reading never clears or sets the latch; it records the attempt", () => {
    const tripped = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    const d = applyAttempt(tripped, fail(T0 + H));
    expect(d).toMatchObject({ tripped: true, reason: "spend", last_error: "boom", evaluated_at: new Date(T0 + H).toISOString(),
                              last_success: new Date(T0).toISOString() });
    expect(applyAttempt(freshGuardDoc(T0), fail(T0)).tripped).toBe(false);
  });

  it("trips blind after blind_after without a success, and only the first success under clears it", () => {
    const six = 6 * H;
    let d = freshGuardDoc(T0);
    d = applyBlindRule(applyAttempt(d, fail(T0 + six - 1)), T0 + six - 1, six);
    expect(d.tripped).toBe(false);
    d = applyBlindRule(d, T0 + six, six);
    expect(d).toMatchObject({ tripped: true, reason: "blind" });
    expect(applyAttempt(d, ok(T0 + six + 1, ...UNDER)).tripped).toBe(false);
    expect(applyAttempt(d, ok(T0 + six + 1, ...OVER))).toMatchObject({ tripped: true, reason: "spend" });
  });

  it("measures blindness from the last success, and never turns spend into blind", () => {
    const six = 6 * H;
    const d = applyAttempt(freshGuardDoc(T0), ok(T0 + H, ...UNDER));
    expect(applyBlindRule(d, T0 + H + six - 1, six).tripped).toBe(false);
    expect(applyBlindRule(d, T0 + H + six, six).reason).toBe("blind");
    const spend = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(applyBlindRule(spend, T0 + 10 * six, six).reason).toBe("spend");
  });
});

describe("parseGuardDoc and corruptGuardDoc", () => {
  it("round-trips what this code writes and rejects anything else", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(parseGuardDoc(JSON.parse(JSON.stringify(d)))).toEqual(d);
    for (const bad of [null, 7, {}, { ...d, schema: 2 }, { ...d, tripped: "yes" }, { ...d, reason: "bored" },
                       { ...d, tripped: false }, { ...d, since: "never" }, { ...d, waf: null }]) {
      expect(parseGuardDoc(bad)).toBeNull();
    }
  });

  it("a corrupt document becomes a spend trip that only a raise or a new period clears", () => {
    const d: GuardDoc = corruptGuardDoc(T0, P1, 15);
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_budget_usd: 15 });
    expect(applyAttempt(d, ok(T0 + H, ...UNDER)).tripped).toBe(true);
    expect(applyAttempt(d, ok(T0 + H, 5.2, 6, 16)).tripped).toBe(false);
  });
});

describe("shouldEvaluate", () => {
  const at = (ms: number) => ({ ...freshGuardDoc(T0), evaluated_at: new Date(ms).toISOString() });
  it("evaluates when never evaluated, >= 15 min old, after a clock step back, or after a newer raise", () => {
    const m15 = 15 * 60_000;
    expect(shouldEvaluate(freshGuardDoc(T0), T0, m15, null)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 + m15 - 1, m15, null)).toBe(false);
    expect(shouldEvaluate(at(T0), T0 + m15, m15, null)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 - 1, m15, null)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 + 60_000, m15, T0 + 30_000)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 + 60_000, m15, T0 - 30_000)).toBe(false);
  });
});

describe("effectiveBudget", () => {
  const raise = (budget_usd: unknown, expires: string, written_at = "2026-10-20T00:00:00.000Z") =>
    ({ budget_usd, expires, written_at });
  it("honours an unexpired raise above the base, capped at the maximum", () => {
    expect(effectiveBudget(15, raise(25, "2026-11-11T00:00:00Z"), T0, P1.endMs)).toEqual(
      { budgetUsd: 25, raisedUntil: "2026-11-11T00:00:00.000Z", writtenAtMs: T0, invalid: null });
    expect(effectiveBudget(15, raise(5000, "2026-11-11T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(MAX_BUDGET_USD);
  });
  it("ignores an expired, lowering, malformed or absent raise", () => {
    expect(effectiveBudget(15, raise(25, "2026-10-19T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, raise(10, "2026-11-11T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, raise("25", "2026-11-11T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, raise(25, "soon"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, null, T0, P1.endMs)).toEqual({ budgetUsd: 15, raisedUntil: null, writtenAtMs: null,
                                                              invalid: null });
  });
  it("ignores and reports a raise that outlives the billing period", () => {
    const r = effectiveBudget(15, raise(25, "2026-12-11T00:00:00Z"), T0, P1.endMs);
    expect(r).toMatchObject({ budgetUsd: 15, raisedUntil: null });
    expect(r.invalid).toMatch(/after this billing period ends/);
  });
  it("clamps a written_at ahead of the Worker's clock to now", () => {
    expect(effectiveBudget(15, raise(25, "2026-11-11T00:00:00Z", "2026-10-20T00:05:00.000Z"), T0, P1.endMs).writtenAtMs)
      .toBe(T0);
  });
  it("validates the configured base", () => {
    expect([15, 5.01, 100].map(validBaseBudget)).toEqual([true, true, true]);
    expect([5, 4, 100.01, Number.NaN].map(validBaseBudget)).toEqual([false, false, false, false]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/latch.test.ts`
Expected: FAIL. `../src/latch` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/latch.ts`:

```ts
/** state/guard.json and the `tripped` latch (spec "Cost guard"). Pure: no IO.
 *
 * Set: a successful evaluation over a threshold (reason "spend"; a successful
 * reading over a threshold always leaves or sets reason "spend"), or no
 * successful reading for blind_after (reason "blind").
 * Cleared, only: "blind" by the first successful reading under the thresholds;
 * "spend" by a successful reading under the thresholds in a new billing period
 * or with a budget raised above the one it last tripped at. Nothing else. */

import type { Period } from "./period";
import { type Evaluation, overThreshold, PRICES, type Usage } from "./pricing";

export const GUARD_KEY = "state/guard.json";
export const BUDGET_KEY = "state/budget.json";
export const OFFAIR_KEY = "state/offair.json";
/** No raise (state/budget.json) or configured budget is honoured above this. */
export const MAX_BUDGET_USD = 100;

export type TripReason = "spend" | "blind";

export interface StoredEvaluation {
  at: string;
  actual_usd: number;
  projected_usd: number;
  budget_usd: number;
  base_budget_usd: number;
  period_to_date: Usage;
  projected: Usage;
  unknown_action_types: string[];
}

export interface GuardDoc {
  schema: 1;
  tripped: boolean;
  reason: TripReason | null;
  tripped_at: string | null;
  /** For "spend": the period and effective budget of the last over-threshold evaluation. */
  tripped_period_start: string | null;
  tripped_budget_usd: number | null;
  /** When this document was first written: the blind clock's baseline. */
  since: string;
  last_success: string | null;
  /** The last evaluation attempt, successful or not (drives the 15-minute cadence). */
  evaluated_at: string | null;
  last_error: string | null;
  period: { start: string; end: string } | null;
  evaluation: StoredEvaluation | null;
  /** The kill switch as last observed by reconciliation. */
  waf: { enabled: boolean | null; error: string | null };
}

const iso = (ms: number) => new Date(ms).toISOString();

export function freshGuardDoc(nowMs: number): GuardDoc {
  return {
    schema: 1, tripped: false, reason: null, tripped_at: null, tripped_period_start: null, tripped_budget_usd: null,
    since: iso(nowMs), last_success: null, evaluated_at: null, last_error: null, period: null, evaluation: null,
    waf: { enabled: null, error: null },
  };
}

const isStr = (v: unknown) => typeof v === "string";
const isStrOrNull = (v: unknown) => v === null || typeof v === "string";
const isNumOrNull = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v));

/** The document, or null when its shape is not one this code wrote. */
export function parseGuardDoc(raw: unknown): GuardDoc | null {
  const d = raw as Partial<GuardDoc> | null;
  if (!d || typeof d !== "object" || d.schema !== 1) return null;
  if (typeof d.tripped !== "boolean") return null;
  if (!(d.reason === null || d.reason === "spend" || d.reason === "blind")) return null;
  if (d.tripped !== (d.reason !== null)) return null;
  if (!isStr(d.since) || Number.isNaN(Date.parse(d.since!))) return null;
  for (const k of ["tripped_at", "tripped_period_start", "last_success", "evaluated_at", "last_error"] as const) {
    if (!isStrOrNull(d[k])) return null;
  }
  if (!isNumOrNull(d.tripped_budget_usd)) return null;
  if (!d.waf || typeof d.waf !== "object") return null;
  return d as GuardDoc;
}

/** What an unreadable state/guard.json becomes: tripped for spend, so only a
 * raise or a new period (with an evaluation under the thresholds) clears it. */
export function corruptGuardDoc(nowMs: number, period: Period | null, budgetUsd: number): GuardDoc {
  return {
    ...freshGuardDoc(nowMs),
    tripped: true, reason: "spend", tripped_at: iso(nowMs),
    tripped_period_start: period ? iso(period.startMs) : null, tripped_budget_usd: budgetUsd,
  };
}

export type Attempt =
  | { ok: true; evaluation: Evaluation; period: Period; baseBudgetUsd: number }
  | { ok: false; atMs: number; error: string };

function stored(e: Evaluation, baseBudgetUsd: number): StoredEvaluation {
  const r4 = (x: number) => Math.round(x * 10_000) / 10_000;
  const usage = (u: Usage): Usage => ({ workersRequests: Math.round(u.workersRequests), r2ClassA: Math.round(u.r2ClassA),
                                        r2ClassB: Math.round(u.r2ClassB), r2StorageGbMonth: r4(u.r2StorageGbMonth) });
  return { at: iso(e.atMs), actual_usd: r4(e.actualUsd), projected_usd: r4(e.projectedUsd), budget_usd: e.budgetUsd,
           base_budget_usd: baseBudgetUsd, period_to_date: usage(e.periodToDate), projected: usage(e.projected),
           unknown_action_types: e.unknownActionTypes };
}

export function applyAttempt(prev: GuardDoc, a: Attempt): GuardDoc {
  if (!a.ok) return { ...prev, evaluated_at: iso(a.atMs), last_error: a.error };
  const e = a.evaluation;
  const at = iso(e.atMs);
  const periodStart = iso(a.period.startMs);
  const base: GuardDoc = { ...prev, last_success: at, evaluated_at: at, last_error: null,
                           period: { start: periodStart, end: iso(a.period.endMs) }, evaluation: stored(e, a.baseBudgetUsd) };
  if (overThreshold(e)) {
    return { ...base, tripped: true, reason: "spend",
             tripped_at: prev.tripped && prev.reason === "spend" ? prev.tripped_at : at,
             tripped_period_start: periodStart, tripped_budget_usd: e.budgetUsd };
  }
  const cleared: GuardDoc = { ...base, tripped: false, reason: null, tripped_at: null, tripped_period_start: null,
                              tripped_budget_usd: null };
  if (!prev.tripped || prev.reason === "blind") return cleared;
  const newPeriod = prev.tripped_period_start !== periodStart;
  const raised = prev.tripped_budget_usd !== null && e.budgetUsd > prev.tripped_budget_usd;
  return newPeriod || raised ? cleared : { ...base, tripped: true, reason: "spend", tripped_at: prev.tripped_at,
                                           tripped_period_start: prev.tripped_period_start,
                                           tripped_budget_usd: prev.tripped_budget_usd };
}

/** Trip "blind" when no reading has succeeded for blindAfterMs (since the
 * document was first written, if none ever has). Never downgrades "spend". */
export function applyBlindRule(doc: GuardDoc, nowMs: number, blindAfterMs: number): GuardDoc {
  if (doc.tripped) return doc;
  const baseline = Date.parse(doc.last_success ?? doc.since);
  if (Number.isFinite(baseline) && nowMs - baseline < blindAfterMs) return doc;
  return { ...doc, tripped: true, reason: "blind", tripped_at: iso(nowMs), tripped_period_start: null,
           tripped_budget_usd: null };
}

/** Evaluate when the last attempt is intervalMs old (a negative age -- a clock
 * step back -- counts as old), or when a budget raise was written after it. */
export function shouldEvaluate(doc: GuardDoc, nowMs: number, intervalMs: number, budgetWrittenAtMs: number | null): boolean {
  if (doc.evaluated_at === null) return true;
  const last = Date.parse(doc.evaluated_at);
  const age = nowMs - last;
  if (!Number.isFinite(age) || age < 0 || age >= intervalMs) return true;
  return budgetWrittenAtMs !== null && budgetWrittenAtMs > last;
}

export interface EffectiveBudget {
  budgetUsd: number;
  raisedUntil: string | null;
  writtenAtMs: number | null;
  /** Why a raise in state/budget.json is ignored as invalid (the guard alerts), or null. */
  invalid: string | null;
}

/** The configured budget, or a raise from state/budget.json ({budget_usd,
 * expires, written_at}, written by `transmitter budget --raise-to`) while it is
 * unexpired. A raise only ever raises, and never past MAX_BUDGET_USD. A raise
 * lasts until the end of the period it was made in (R3), so one expiring after
 * the current period ends (`periodEndMs`; null when the period is unknown) is
 * ignored and reported. A written_at ahead of the Worker's clock (a skewed
 * writer) is clamped to now. */
export function effectiveBudget(baseUsd: number, raw: unknown, nowMs: number,
                                periodEndMs: number | null): EffectiveBudget {
  const none = { budgetUsd: baseUsd, raisedUntil: null, writtenAtMs: null, invalid: null };
  const d = raw as { budget_usd?: unknown; expires?: unknown; written_at?: unknown } | null;
  if (!d || typeof d !== "object") return none;
  const usd = d.budget_usd;
  const expires = typeof d.expires === "string" ? Date.parse(d.expires) : Number.NaN;
  const written = typeof d.written_at === "string" ? Date.parse(d.written_at) : Number.NaN;
  const writtenAtMs = Number.isFinite(written) ? Math.min(written, nowMs) : null;
  if (typeof usd !== "number" || !Number.isFinite(usd) || !(expires > nowMs) || usd <= baseUsd) {
    return { ...none, writtenAtMs };
  }
  if (periodEndMs !== null && expires > periodEndMs) {
    return { ...none, writtenAtMs, invalid: `state/budget.json raises the budget to $${usd} until ${iso(expires)}, ` +
                                            `after this billing period ends (${iso(periodEndMs)}); it is ignored` };
  }
  return { budgetUsd: Math.min(usd, MAX_BUDGET_USD), raisedUntil: iso(expires), writtenAtMs, invalid: null };
}

/** MONTHLY_BUDGET_USD: above the $5 base (else nothing is left to spend) and at most MAX_BUDGET_USD. */
export function validBaseBudget(v: number): boolean {
  return Number.isFinite(v) && v > PRICES.baseUsd && v <= MAX_BUDGET_USD;
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run test/latch.test.ts && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/latch.ts antenna/test/latch.test.ts
git commit -m "feat(antenna): the tripped latch (spend/blind), state/guard.json schema, budget raises"
```

---

