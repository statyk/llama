import { describe, expect, it } from "vitest";
import { evaluateSpend, overThreshold, PRICES, priceUsage, type Reading } from "../src/pricing";

const DAY = 86_400_000;
const PERIOD = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const zero = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0 };

describe("priceUsage", () => {
  it("is the $5 base while every meter is inside its allowance", () => {
    expect(priceUsage({ workersRequests: 9_999_999, r2ClassA: 1_000_000, r2ClassB: 10_000_000, r2StorageGbMonth: 10 }).totalUsd)
      .toBe(5);
  });

  it("prices only the usage beyond each allowance", () => {
    const r = priceUsage({ workersRequests: 12_000_000, r2ClassA: 3_000_000, r2ClassB: 20_000_000, r2StorageGbMonth: 30 });
    expect(r.perMeterUsd.workersRequests).toBeCloseTo(0.6, 10);
    expect(r.perMeterUsd.r2ClassA).toBeCloseTo(9.0, 10);
    expect(r.perMeterUsd.r2ClassB).toBeCloseTo(3.6, 10);
    expect(r.perMeterUsd.r2StorageGbMonth).toBeCloseTo(0.3, 10);
    expect(r.totalUsd).toBeCloseTo(5 + 0.6 + 9 + 3.6 + 0.3, 10);
  });

  it("carries the published prices", () => {
    expect(PRICES.baseUsd).toBe(5);
    expect(PRICES.meters.r2ClassA).toEqual({ included: 1_000_000, usdPerUnit: 4.5e-6 });
  });
});

describe("evaluateSpend", () => {
  it("projects each meter from the recent rate through the allowances, not a dollar average", () => {
    const now = PERIOD.startMs + 10 * DAY; // 21 days left
    const r: Reading = {
      periodToDate: { workersRequests: 100_000, r2ClassA: 500_000, r2ClassB: 0 },
      recent: { workersRequests: 0, r2ClassA: 30_000, r2ClassB: 0 }, // 10k Class A per hour
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.actualUsd).toBe(5); // 0.5M Class A is inside the 1M allowance
    // 500k + 10k/h * 504 h = 5.54M Class A: 4.54M billable * $4.50/M
    expect(e.projected.r2ClassA).toBeCloseTo(5_540_000, 3);
    expect(e.projectedUsd).toBeCloseTo(5 + 4.54 * 4.5, 6);
  });

  it("projects every op meter from its own recent rate", () => {
    const now = PERIOD.startMs + 10 * DAY; // 504 h left
    const r: Reading = {
      periodToDate: { workersRequests: 100_000, r2ClassA: 500_000, r2ClassB: 0 },
      // distinct per-hour rates: Workers 400k, Class A 10k, Class B 200k
      recent: { workersRequests: 1_200_000, r2ClassA: 30_000, r2ClassB: 600_000 },
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.projected.workersRequests).toBeCloseTo(100_000 + 400_000 * 504, 3); // 201.7M
    expect(e.projected.r2ClassA).toBeCloseTo(500_000 + 10_000 * 504, 3); // 5.54M
    expect(e.projected.r2ClassB).toBeCloseTo(200_000 * 504, 3); // 100.8M
    // every meter past its allowance, so the total depends on each projection
    expect(e.projectedUsd).toBeCloseTo(5 + 191.7 * 0.3 + 4.54 * 4.5 + 90.8 * 0.36, 6);
  });

  it("never projects below period-to-date once the period is over", () => {
    const r: Reading = {
      periodToDate: { workersRequests: 11_000_000, r2ClassA: 2_000_000, r2ClassB: 0 },
      recent: { workersRequests: 1_000_000, r2ClassA: 1_000_000, r2ClassB: 0 },
      recentMs: 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, PERIOD.endMs + DAY, 15);
    expect(e.projected.workersRequests).toBe(11_000_000);
    expect(e.projected.r2ClassA).toBe(2_000_000);
    expect(e.projectedUsd).toBeCloseTo(e.actualUsd, 10);
    expect(e.projectedUsd).toBeCloseTo(5 + 0.3 + 4.5, 10);
  });

  it("holds the peak storage over the elapsed and the whole period", () => {
    const now = PERIOD.startMs + 15 * DAY;
    const e = evaluateSpend({ periodToDate: zero, recent: zero, recentMs: 3_600_000, storageBytes: 60e9,
                              unknownActionTypes: [] }, PERIOD, now, 15);
    expect(e.periodToDate.r2StorageGbMonth).toBeCloseTo(30, 10); // 60 GB * 15/30
    expect(e.projected.r2StorageGbMonth).toBeCloseTo(62, 10); // 60 GB * 31/30
  });

  it("has nothing left to project at the period's end", () => {
    const e = evaluateSpend({ periodToDate: zero, recent: { ...zero, r2ClassA: 1e9 }, recentMs: 1, storageBytes: 0,
                              unknownActionTypes: [] }, PERIOD, PERIOD.endMs, 15);
    expect(e.projectedUsd).toBe(5);
  });
});

describe("overThreshold", () => {
  it("trips at actual >= 90% or projected >= 100%", () => {
    expect(overThreshold({ actualUsd: 13.49, projectedUsd: 14.99, budgetUsd: 15 })).toBe(false);
    expect(overThreshold({ actualUsd: 13.5, projectedUsd: 13.5, budgetUsd: 15 })).toBe(true);
    expect(overThreshold({ actualUsd: 5, projectedUsd: 15, budgetUsd: 15 })).toBe(true);
  });

  it("fails closed: any NaN trips", () => {
    expect(overThreshold({ actualUsd: 5, projectedUsd: 5, budgetUsd: Number.NaN })).toBe(true);
    expect(overThreshold({ actualUsd: 5, projectedUsd: Number.NaN, budgetUsd: 15 })).toBe(true);
    expect(overThreshold({ actualUsd: Number.NaN, projectedUsd: 5, budgetUsd: 15 })).toBe(true);
  });
});
