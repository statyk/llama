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
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
/** A budget is recorded only when it is a finite number: a non-finite one (an
 * invalid MONTHLY_BUDGET_USD) is recorded as null, which no raise can clear. */
const finiteOrNull = (v: number) => (Number.isFinite(v) ? v : null);

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
  if (!isObj(d.waf) || !(d.waf.enabled === null || typeof d.waf.enabled === "boolean") || !isStrOrNull(d.waf.error)) {
    return null;
  }
  if (!(d.period === null || (isObj(d.period) && isStr(d.period.start) && isStr(d.period.end)))) return null;
  const ev = d.evaluation as unknown;
  if (!(ev === null || (isObj(ev) && isNumOrNull(ev.actual_usd) && isNumOrNull(ev.projected_usd) &&
                        isNumOrNull(ev.budget_usd)))) {
    return null;
  }
  return d as GuardDoc;
}

/** What an unreadable state/guard.json becomes: tripped for spend, so only a
 * raise or a new period (with an evaluation under the thresholds) clears it. */
export function corruptGuardDoc(nowMs: number, period: Period | null, budgetUsd: number): GuardDoc {
  return {
    ...freshGuardDoc(nowMs),
    tripped: true, reason: "spend", tripped_at: iso(nowMs),
    tripped_period_start: period ? iso(period.startMs) : null, tripped_budget_usd: finiteOrNull(budgetUsd),
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
             tripped_period_start: periodStart, tripped_budget_usd: finiteOrNull(e.budgetUsd) };
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
