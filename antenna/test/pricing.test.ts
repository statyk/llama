import { describe, expect, it } from "vitest";
import { applyAttempt, freshGuardDoc } from "../src/latch";
import { evaluateSpend, METERS, type OpCounts, overThreshold, PRICES, priceUsage, type Reading,
         type Usage } from "../src/pricing";

const DAY = 86_400_000;
const PERIOD = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const NO_DO = { doRequests: 0, doDurationGbS: 0, doRowsWritten: 0 };
const zero: OpCounts = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, ...NO_DO };
const usage = (u: Partial<Usage>): Usage =>
  ({ workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0, ...NO_DO, ...u });

describe("priceUsage", () => {
  it("is the $5 base while every meter is inside its allowance", () => {
    expect(priceUsage(usage({ workersRequests: 9_999_999, r2ClassA: 1_000_000, r2ClassB: 10_000_000, r2StorageGbMonth: 10,
                              doRequests: 1_000_000, doDurationGbS: 400_000, doRowsWritten: 50_000_000 })).totalUsd)
      .toBe(5);
  });

  it("prices only the usage beyond each allowance", () => {
    const r = priceUsage(usage({ workersRequests: 12_000_000, r2ClassA: 3_000_000, r2ClassB: 20_000_000, r2StorageGbMonth: 30 }));
    expect(r.perMeterUsd.workersRequests).toBeCloseTo(0.6, 10);
    expect(r.perMeterUsd.r2ClassA).toBeCloseTo(9.0, 10);
    expect(r.perMeterUsd.r2ClassB).toBeCloseTo(3.6, 10);
    expect(r.perMeterUsd.r2StorageGbMonth).toBeCloseTo(0.3, 10);
    expect(r.totalUsd).toBeCloseTo(5 + 0.6 + 9 + 3.6 + 0.3, 10);
  });

  it("prices each Durable Object meter through its allowance", () => {
    const r = priceUsage(usage({ doRequests: 3_000_000, doDurationGbS: 600_000, doRowsWritten: 60_000_000 }));
    expect(r.perMeterUsd.doRequests).toBeCloseTo(2 * 0.15, 10); // 2M over at $0.15/M
    expect(r.perMeterUsd.doDurationGbS).toBeCloseTo(0.2 * 12.5, 10); // 200k GB-s over at $12.50/M
    expect(r.perMeterUsd.doRowsWritten).toBeCloseTo(10 * 1.0, 10); // 10M over at $1.00/M
    expect(r.totalUsd).toBeCloseTo(5 + 0.3 + 2.5 + 10, 10);
  });

  it("carries the published prices", () => {
    expect(PRICES.baseUsd).toBe(5);
    expect(PRICES.meters.r2ClassA).toEqual({ included: 1_000_000, usdPerUnit: 4.5e-6 });
    // Durable Objects, Workers Paid (checked 2026-10-14).
    expect(PRICES.meters.doRequests).toEqual({ included: 1_000_000, usdPerUnit: 0.15e-6 });
    expect(PRICES.meters.doDurationGbS).toEqual({ included: 400_000, usdPerUnit: 12.5e-6 });
    expect(PRICES.meters.doRowsWritten).toEqual({ included: 50_000_000, usdPerUnit: 1e-6 });
  });

  it("prices every meter: a positive, finite price and a finite allowance (no meter is free by omission)", () => {
    expect(METERS).toHaveLength(7);
    expect(new Set(METERS).size).toBe(7);
    expect(Object.keys(PRICES.meters).sort()).toEqual([...METERS].sort());
    for (const m of METERS) {
      const { included, usdPerUnit } = PRICES.meters[m];
      expect([m, Number.isFinite(usdPerUnit) && usdPerUnit > 0]).toEqual([m, true]);
      expect([m, Number.isFinite(included) && included >= 0]).toEqual([m, true]);
      // One unit past the allowance costs money, on its own.
      expect([m, priceUsage(usage({ [m]: included + 1_000_000 })).totalUsd > 5]).toEqual([m, true]);
    }
  });
});

describe("evaluateSpend", () => {
  it("projects each meter from the recent rate through the allowances, not a dollar average", () => {
    const now = PERIOD.startMs + 10 * DAY; // 21 days left
    const r: Reading = {
      periodToDate: { ...zero, workersRequests: 100_000, r2ClassA: 500_000 },
      recent: { ...zero, r2ClassA: 30_000 }, // 10k Class A per hour
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
      periodToDate: { ...zero, workersRequests: 100_000, r2ClassA: 500_000 },
      // distinct per-hour rates: Workers 400k, Class A 10k, Class B 200k
      recent: { ...zero, workersRequests: 1_200_000, r2ClassA: 30_000, r2ClassB: 600_000 },
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.projected.workersRequests).toBeCloseTo(100_000 + 400_000 * 504, 3); // 201.7M
    expect(e.projected.r2ClassA).toBeCloseTo(500_000 + 10_000 * 504, 3); // 5.54M
    expect(e.projected.r2ClassB).toBeCloseTo(200_000 * 504, 3); // 100.8M
    // every meter past its allowance, so the total depends on each projection
    expect(e.projectedUsd).toBeCloseTo(5 + 191.7 * 0.3 + 4.54 * 4.5 + 90.8 * 0.36, 6);
  });

  it("projects each Durable Object meter from its own recent rate", () => {
    const now = PERIOD.startMs + 10 * DAY; // 504 h left
    const r: Reading = {
      periodToDate: { ...zero, doRequests: 100_000, doDurationGbS: 1_000, doRowsWritten: 200_000 },
      // per hour: 3k requests, 20 GB-s, 5k rows
      recent: { ...zero, doRequests: 9_000, doDurationGbS: 60, doRowsWritten: 15_000 },
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.periodToDate).toMatchObject({ doRequests: 100_000, doDurationGbS: 1_000, doRowsWritten: 200_000 });
    expect(e.projected.doRequests).toBeCloseTo(100_000 + 3_000 * 504, 3);
    expect(e.projected.doDurationGbS).toBeCloseTo(1_000 + 20 * 504, 3);
    expect(e.projected.doRowsWritten).toBeCloseTo(200_000 + 5_000 * 504, 3);
    expect(e.projectedUsd).toBeCloseTo(5 + 0.612 * 0.15, 6); // only requests pass their allowance: 1.612M
  });

  it("never projects below period-to-date once the period is over", () => {
    const r: Reading = {
      periodToDate: { ...zero, workersRequests: 11_000_000, r2ClassA: 2_000_000 },
      recent: { ...zero, workersRequests: 1_000_000, r2ClassA: 1_000_000 },
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

  it("every meter is finite in periodToDate, projected and the stored guard.json evaluation", () => {
    const now = PERIOD.startMs + 10 * DAY;
    const r: Reading = { periodToDate: { workersRequests: 1, r2ClassA: 2, r2ClassB: 3, doRequests: 4, doDurationGbS: 5.5,
                                         doRowsWritten: 6 },
                         recent: { workersRequests: 1, r2ClassA: 1, r2ClassB: 1, doRequests: 1, doDurationGbS: 0.25,
                                   doRowsWritten: 1 },
                         recentMs: 3_600_000, storageBytes: 1e9, unknownActionTypes: [] };
    const e = evaluateSpend(r, PERIOD, now, 15);
    const doc = applyAttempt(freshGuardDoc(now), { ok: true, evaluation: e, period: PERIOD, baseBudgetUsd: 15 });
    for (const m of METERS) {
      expect([m, Number.isFinite(e.periodToDate[m])]).toEqual([m, true]);
      expect([m, Number.isFinite(e.projected[m])]).toEqual([m, true]);
      expect([m, Number.isFinite(doc.evaluation!.period_to_date[m])]).toEqual([m, true]);
      expect([m, Number.isFinite(doc.evaluation!.projected[m])]).toEqual([m, true]);
    }
    expect(Object.keys(doc.evaluation!.period_to_date).sort()).toEqual([...METERS].sort());
    expect(doc.evaluation!.period_to_date.doDurationGbS).toBe(5.5); // fractional, not rounded away
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

  it("fails closed on a NaN or missing Durable Object reading", () => {
    const now = PERIOD.startMs + 10 * DAY;
    for (const bad of [Number.NaN, undefined]) {
      const r = { periodToDate: { ...zero, doDurationGbS: bad }, recent: zero, recentMs: 3_600_000, storageBytes: 0,
                  unknownActionTypes: [] } as unknown as Reading;
      expect(overThreshold(evaluateSpend(r, PERIOD, now, 15))).toBe(true);
    }
  });
});
