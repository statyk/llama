/** The guard's price table and spend arithmetic (spec "Cost guard"). Prices
 * and allowances are Cloudflare's published ones (Workers Paid, R2 Standard),
 * checked 2026-10-11; the Durable Objects meters (Workers Paid) were checked
 * 2026-10-14 on developers.cloudflare.com/durable-objects/platform/pricing/
 * (metronome spec, "Cost guard: Durable Object meters"). The $5 Workers Paid
 * base is part of every total, so monthly_budget_usd includes it. Not metered,
 * each bounded by design instead: Workers CPU time (the dataset exposes it only
 * as percentiles), DO rows read and DO stored bytes (the metronome's fixed key
 * set and capped invocations; `durableObjectsStorageGroups` returns no rows for
 * this account). */

import type { Period } from "./period";

export type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth" | "doRequests" | "doDurationGbS" |
  "doRowsWritten";
export const METERS: Meter[] = ["workersRequests", "r2ClassA", "r2ClassB", "r2StorageGbMonth", "doRequests",
                                "doDurationGbS", "doRowsWritten"];

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
    // Durable Objects (requests include RPC sessions and alarm invocations).
    doRequests: { included: 1_000_000, usdPerUnit: 0.15 / 1_000_000 },
    doDurationGbS: { included: 400_000, usdPerUnit: 12.5 / 1_000_000 },
    doRowsWritten: { included: 50_000_000, usdPerUnit: 1.0 / 1_000_000 },
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

/** Counts from the analytics read (R2 storage is reported separately). */
export interface OpCounts {
  workersRequests: number;
  r2ClassA: number;
  r2ClassB: number;
  doRequests: number;
  /** GB-s (the dataset's `duration`: activeTime x 0.128 GB, measured 2026-10-14). */
  doDurationGbS: number;
  doRowsWritten: number;
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
    doRequests: r.periodToDate.doRequests,
    doDurationGbS: r.periodToDate.doDurationGbS,
    doRowsWritten: r.periodToDate.doRowsWritten,
  };
  const projected: Usage = {
    workersRequests: periodToDate.workersRequests + rate("workersRequests") * remainingMs,
    r2ClassA: periodToDate.r2ClassA + rate("r2ClassA") * remainingMs,
    r2ClassB: periodToDate.r2ClassB + rate("r2ClassB") * remainingMs,
    r2StorageGbMonth: (gb * (period.endMs - period.startMs)) / STORAGE_MONTH_MS,
    doRequests: periodToDate.doRequests + rate("doRequests") * remainingMs,
    doDurationGbS: periodToDate.doDurationGbS + rate("doDurationGbS") * remainingMs,
    doRowsWritten: periodToDate.doRowsWritten + rate("doRowsWritten") * remainingMs,
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

/** Trip when actual >= 90% or projected >= 100% of the budget. Written
 * negated ("not safely under both") so a NaN anywhere trips: every comparison
 * with NaN is false, and the plain `>=` form would fail open. */
export function overThreshold(e: Pick<Evaluation, "actualUsd" | "projectedUsd" | "budgetUsd">): boolean {
  return !(e.actualUsd < TRIP_ACTUAL * e.budgetUsd && e.projectedUsd < TRIP_PROJECTED * e.budgetUsd);
}
