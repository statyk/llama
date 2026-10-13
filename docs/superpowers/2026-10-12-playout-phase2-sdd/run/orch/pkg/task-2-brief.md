### Task 2: Price table, spend evaluation, thresholds

**Model hint:** opus (spend path)

**Files:**
- Create: `antenna/src/pricing.ts`, `antenna/test/pricing.test.ts`

**Interfaces:**
- Consumes: `Period` (Task 1).
- Produces:
  - `type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth"`, `METERS`, `interface PriceTable`, `PRICES` ($5 base; 10M Workers requests then $0.30/M; R2 Class A 1M then $4.50/M; Class B 10M then $0.36/M; storage 10 GB-month then $0.015/GB-month).
  - `type Usage = Record<Meter, number>`, `priceUsage(u, p?) -> { totalUsd, perMeterUsd }`.
  - `interface OpCounts { workersRequests; r2ClassA; r2ClassB }`, `interface Reading { periodToDate: OpCounts; recent: OpCounts; recentMs; storageBytes; unknownActionTypes: string[] }`.
  - `interface Evaluation { atMs; actualUsd; projectedUsd; budgetUsd; periodToDate: Usage; projected: Usage; unknownActionTypes }`, `evaluateSpend(reading, period, nowMs, budgetUsd, p?) -> Evaluation`.
  - `TRIP_ACTUAL = 0.9`, `TRIP_PROJECTED = 1.0`, `ALERT_LEVELS = [0.5, 0.8]`, `overThreshold({actualUsd, projectedUsd, budgetUsd}) -> boolean`.

- [ ] **Step 1: Write the failing test**

`antenna/test/pricing.test.ts`:

```ts
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
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/pricing.test.ts`
Expected: FAIL. `../src/pricing` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/pricing.ts`:

```ts
/** The guard's price table and spend arithmetic (spec "Cost guard"). Prices
 * and allowances are Cloudflare's published ones (Workers Paid, R2 Standard),
 * checked 2026-10-11; the $5 Workers Paid base is part of every total, so
 * monthly_budget_usd includes it. Workers CPU time is not metered: the dataset
 * exposes it only as percentiles and the clock's CPU is bounded by design. */

import type { Period } from "./period";

export type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth";
export const METERS: Meter[] = ["workersRequests", "r2ClassA", "r2ClassB", "r2StorageGbMonth"];

export interface PriceTable {
  baseUsd: number;
  meters: Record<Meter, { included: number; usdPerUnit: number }>;
}

export const PRICES: PriceTable = {
  baseUsd: 5,
  meters: {
    workersRequests: { included: 10_000_000, usdPerUnit: 0.3 / 1_000_000 },
    r2ClassA: { included: 1_000_000, usdPerUnit: 4.5 / 1_000_000 },
    r2ClassB: { included: 10_000_000, usdPerUnit: 0.36 / 1_000_000 },
    r2StorageGbMonth: { included: 10, usdPerUnit: 0.015 },
  },
};

export type Usage = Record<Meter, number>;

export function priceUsage(u: Usage, p: PriceTable = PRICES): { totalUsd: number; perMeterUsd: Usage } {
  const perMeterUsd = {} as Usage;
  let totalUsd = p.baseUsd;
  for (const m of METERS) {
    const { included, usdPerUnit } = p.meters[m];
    perMeterUsd[m] = Math.max(0, u[m] - included) * usdPerUnit;
    totalUsd += perMeterUsd[m];
  }
  return { totalUsd, perMeterUsd };
}

/** Request counts from the analytics read (storage is reported separately). */
export interface OpCounts {
  workersRequests: number;
  r2ClassA: number;
  r2ClassB: number;
}

export interface Reading {
  periodToDate: OpCounts; // period start .. now
  recent: OpCounts; // the last recentMs (ending a few minutes ago: analytics lag)
  recentMs: number;
  storageBytes: number; // peak bytes stored in the period, summed over buckets
  unknownActionTypes: string[];
}

export interface Evaluation {
  atMs: number;
  actualUsd: number;
  projectedUsd: number;
  budgetUsd: number;
  periodToDate: Usage;
  projected: Usage;
  unknownActionTypes: string[];
}

/** R2 bills storage as the average of daily peaks over 30 days. */
const STORAGE_MONTH_MS = 30 * 86_400_000;
/** Conservative: decimal GB (more GB than GiB for the same bytes). */
const BYTES_PER_GB = 1e9;

export const TRIP_ACTUAL = 0.9;
export const TRIP_PROJECTED = 1.0;
export const ALERT_LEVELS = [0.5, 0.8] as const;

/**
 * Actual = period-to-date usage priced through the allowances. Projected =
 * per meter, period-to-date plus the recent rate times the time left, then
 * priced through the allowances (never a linear month-to-date dollar average).
 * Storage is the period's peak held for the elapsed (actual) or whole
 * (projected) period: an upper bound of R2's average-of-daily-peaks.
 */
export function evaluateSpend(r: Reading, period: Period, nowMs: number, budgetUsd: number,
                              p: PriceTable = PRICES): Evaluation {
  const elapsedMs = Math.max(0, Math.min(nowMs, period.endMs) - period.startMs);
  const remainingMs = Math.max(0, period.endMs - nowMs);
  const gb = r.storageBytes / BYTES_PER_GB;
  const rate = (m: keyof OpCounts) => (r.recentMs > 0 ? r.recent[m] / r.recentMs : 0);
  const periodToDate: Usage = {
    workersRequests: r.periodToDate.workersRequests,
    r2ClassA: r.periodToDate.r2ClassA,
    r2ClassB: r.periodToDate.r2ClassB,
    r2StorageGbMonth: (gb * elapsedMs) / STORAGE_MONTH_MS,
  };
  const projected: Usage = {
    workersRequests: periodToDate.workersRequests + rate("workersRequests") * remainingMs,
    r2ClassA: periodToDate.r2ClassA + rate("r2ClassA") * remainingMs,
    r2ClassB: periodToDate.r2ClassB + rate("r2ClassB") * remainingMs,
    r2StorageGbMonth: (gb * (period.endMs - period.startMs)) / STORAGE_MONTH_MS,
  };
  return {
    atMs: nowMs,
    actualUsd: priceUsage(periodToDate, p).totalUsd,
    projectedUsd: priceUsage(projected, p).totalUsd,
    budgetUsd,
    periodToDate,
    projected,
    unknownActionTypes: r.unknownActionTypes,
  };
}

/** Trip when actual >= 90% or projected >= 100% of the budget. */
export function overThreshold(e: Pick<Evaluation, "actualUsd" | "projectedUsd" | "budgetUsd">): boolean {
  return e.actualUsd >= TRIP_ACTUAL * e.budgetUsd || e.projectedUsd >= TRIP_PROJECTED * e.budgetUsd;
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run test/pricing.test.ts && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/pricing.ts antenna/test/pricing.test.ts
git commit -m "feat(antenna): guard price table and per-meter spend projection through the allowances"
```

---
