import { describe, expect, it } from "vitest";
import { guardConditions, READING_WARN_MS } from "../src/conditions";
import { freshGuardDoc, type GuardDoc, type StoredEvaluation } from "../src/latch";

const T0 = Date.parse("2026-10-20T12:00:00Z");
const usage = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0, doRequests: 0, doDurationGbS: 0,
                doRowsWritten: 0 };
function withEvaluation(e: Partial<StoredEvaluation>): GuardDoc {
  return { ...freshGuardDoc(T0), last_success: new Date(T0).toISOString(),
           period: { start: "2026-10-11T00:00:00.000Z", end: "2026-11-11T00:00:00.000Z" },
           evaluation: { at: new Date(T0).toISOString(), actual_usd: 6, projected_usd: 7, budget_usd: 15, base_budget_usd: 15,
                         period_to_date: usage, projected: usage, unknown_action_types: [], ...e } };
}
const keys = (d: GuardDoc, now = T0) => guardConditions(d, now, 21_600_000).map((c) => c.key);

describe("guardConditions", () => {
  it("raises each budget level once per period and budget", () => {
    expect(keys(withEvaluation({}))).toEqual([]);
    expect(keys(withEvaluation({ projected_usd: 8 }))).toEqual(["budget-50:2026-10-11:15"]);
    expect(keys(withEvaluation({ actual_usd: 12.5 }))).toEqual(["budget-50:2026-10-11:15", "budget-80:2026-10-11:15"]);
  });

  it("an unknown (null) amount or budget alerts every level rather than going quiet, and does not crash", () => {
    for (const e of [{ actual_usd: null }, { projected_usd: null }, { budget_usd: null }, { budget_usd: 0 }]) {
      const c = guardConditions(withEvaluation(e), T0, 21_600_000);
      expect(c.map((x) => x.key.split(":")[0])).toEqual(["budget-50", "budget-80"]);
    }
    const spend = { ...withEvaluation({ actual_usd: null, budget_usd: null }), tripped: true, reason: "spend" as const,
                    tripped_at: new Date(T0).toISOString() };
    expect(guardConditions(spend, T0, 21_600_000).find((x) => x.key === "tripped-spend")!.message)
      .toMatch(/actual an unknown amount, projected \$7\.00 of an unknown amount/);
  });

  it("warns that readings are failing after an hour, and not while tripped", () => {
    const failing = { ...freshGuardDoc(T0), last_error: "HTTP 503" };
    expect(keys(failing, T0 + READING_WARN_MS - 1)).toEqual([]);
    expect(keys(failing, T0 + READING_WARN_MS)).toEqual(["guard-reading-failing"]);
    const blind = { ...failing, tripped: true, reason: "blind" as const, tripped_at: new Date(T0).toISOString() };
    expect(keys(blind, T0 + READING_WARN_MS)).toEqual(["tripped-blind"]);
  });
});
