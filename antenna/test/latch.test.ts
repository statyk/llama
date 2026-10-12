import { describe, expect, it } from "vitest";
import { type Attempt, applyAttempt, applyBlindRule, BLIND_FUTURE_TOLERANCE_MS, corruptGuardDoc, effectiveBudget,
         freshGuardDoc, type GuardDoc, MAX_BUDGET_USD, parseGuardDoc, shouldEvaluate, validBaseBudget } from "../src/latch";
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

describe("non-finite budgets fail closed", () => {
  it("a NaN budget trips spend and records no tripped budget; only a raise above the base or a new period clears it", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...UNDER, Number.NaN));
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_budget_usd: null });
    expect(applyAttempt(d, ok(T0 + H, ...UNDER)).tripped).toBe(true); // budget 15 = base: no raise
    expect(applyAttempt(d, ok(T0 + H, 5.2, 6, 50)).tripped).toBe(false); // an honoured raise (fix round 1, ruling 3)
    expect(applyAttempt(d, ok(P2.startMs + H, 5, 6, 15, P2)).tripped).toBe(false); // a new period still clears
  });

  it("a corrupt document under a non-finite budget records none, and an unraised reading leaves it tripped", () => {
    for (const b of [Number.NaN, Number.POSITIVE_INFINITY]) {
      const d = corruptGuardDoc(T0, P1, b);
      expect(d.tripped_budget_usd).toBeNull();
      expect(applyAttempt(d, ok(T0 + H, ...UNDER)).tripped).toBe(true);
    }
  });

  it("effectiveBudget never honours a non-finite raise", () => {
    for (const usd of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
      expect(effectiveBudget(15, { budget_usd: usd, expires: "2026-11-11T00:00:00Z" }, T0, P1.endMs).budgetUsd).toBe(15);
    }
  });
});

describe("parseGuardDoc rejects nested shapes this code never writes", () => {
  it("checks waf, period and evaluation", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    for (const bad of [{ ...d, waf: {} }, { ...d, waf: { enabled: "on", error: null } },
                       { ...d, waf: { enabled: true, error: 3 } }, { ...d, period: "P1" },
                       { ...d, period: { start: "2026-10-11T00:00:00.000Z" } }, { ...d, evaluation: 5 },
                       { ...d, evaluation: { ...d.evaluation, budget_usd: "15" } },
                       { ...d, evaluation: { ...d.evaluation, at: undefined } },
                       { ...d, evaluation: { ...d.evaluation, at: 5 } }]) {
      expect(parseGuardDoc(bad)).toBeNull();
    }
    expect(parseGuardDoc({ ...d, evaluation: null, period: null })).not.toBeNull();
    expect(parseGuardDoc(JSON.parse(JSON.stringify(freshGuardDoc(T0))))).toEqual(freshGuardDoc(T0));
  });
});

describe("fix round 1: re-trips, null latch fields, cadence and clock faults", () => {
  const P2_START = new Date(P2.startMs).toISOString();

  it("re-anchors a spend trip to the new period when that period reads over too, so its under readings stay tripped", () => {
    let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    d = applyAttempt(d, ok(P2.startMs + H, 5, 15, 15, P2));
    expect(d.tripped_period_start).toBe(P2_START);
    expect(applyAttempt(d, ok(P2.startMs + 2 * H, 5, 6, 15, P2)).tripped).toBe(true);
  });

  it("keeps the first tripped_at across consecutive over readings", () => {
    let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    d = applyAttempt(d, ok(T0 + H, ...OVER));
    expect(d.tripped_at).toBe(new Date(T0).toISOString());
  });

  it("a spend trip with no recorded period adopts the current one and stays tripped", () => {
    const d = corruptGuardDoc(T0, null, 15);
    const next = applyAttempt(d, ok(T0 + H, ...UNDER));
    expect(next).toMatchObject({ tripped: true, reason: "spend", tripped_period_start: "2026-10-11T00:00:00.000Z" });
    expect(applyAttempt(next, ok(T0 + 2 * H, ...UNDER)).tripped).toBe(true); // same period: still tripped
    expect(applyAttempt(next, ok(P2.startMs + H, 5, 6, 15, P2)).tripped).toBe(false); // a later period clears
  });

  it("a spend trip with no recorded budget clears only with an honoured raise above the base", () => {
    const d = corruptGuardDoc(T0, P1, Number.NaN);
    expect(d.tripped_budget_usd).toBeNull();
    expect(applyAttempt(d, ok(T0 + H, ...UNDER)).tripped).toBe(true); // budget 15 = base: no raise
    expect(applyAttempt(d, ok(T0 + H, 5.2, 6, 20)).tripped).toBe(false); // raised to 20 over base 15
    expect(applyAttempt(d, ok(T0 + H, 5.2, 21, 20))).toMatchObject({ tripped: true, tripped_budget_usd: 20 });
    const badBase: Attempt = { ...(ok(T0 + H, 5.2, 6, 20) as Extract<Attempt, { ok: true }>), baseBudgetUsd: Number.NaN };
    expect(applyAttempt(d, badBase).tripped).toBe(true); // no valid base: nothing to be raised above
  });

  it("a written_at clamped to now never forces an evaluation inside the interval; a past raise still does", () => {
    const m15 = 15 * 60_000;
    let d = at(T0);
    for (let i = 1; i < 15; i++) {
      const now = T0 + i * 60_000;
      // effectiveBudget clamps a future written_at to now
      const written = effectiveBudget(15, { budget_usd: 25, expires: "2026-11-11T00:00:00Z",
                                            written_at: "2027-01-01T00:00:00Z" }, now, P1.endMs).writtenAtMs;
      expect(written).toBe(now);
      expect(shouldEvaluate(d, now, m15, written)).toBe(false);
      d = at(T0); // nothing evaluated, so evaluated_at stays
    }
    expect(shouldEvaluate(at(T0), T0 + 60_000, m15, T0 + 59_999)).toBe(true);
  });

  it("trips blind when the blindness baseline is more than the tolerance ahead of the clock, not a few seconds", () => {
    const six = 6 * H;
    const ahead = (ms: number) => ({ ...freshGuardDoc(T0), last_success: new Date(T0 + ms).toISOString() });
    expect(applyBlindRule(ahead(5_000), T0, six).tripped).toBe(false);
    expect(applyBlindRule(ahead(BLIND_FUTURE_TOLERANCE_MS), T0, six).tripped).toBe(false);
    expect(applyBlindRule(ahead(BLIND_FUTURE_TOLERANCE_MS + 1), T0, six)).toMatchObject({ tripped: true, reason: "blind" });
    const since = { ...freshGuardDoc(T0 + BLIND_FUTURE_TOLERANCE_MS + 1) };
    expect(applyBlindRule(since, T0, six).reason).toBe("blind");
  });

  function at(ms: number): GuardDoc {
    return { ...freshGuardDoc(T0), evaluated_at: new Date(ms).toISOString() };
  }
});
