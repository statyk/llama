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
  /** Bypasses the 3-consecutive alert gate (alerts.ts GATED_KEYS): sent at its
   * first presence, and its repeats are not held. It still advances the key's
   * streak. Set at exactly two raise sites: metronome-down from the stall
   * trigger (clock.ts renew, metronome-core fallbackCause, already debounced by
   * STALLS_FALLBACK), and guard-unknown from the post-unblock re-check in
   * guard.ts (one minute forced to ENDLIST, which can never last 3 minutes). */
  immediate?: boolean;
}

/** A stored amount is null when it was not finite (latch.ts StoredEvaluation). */
const usd = (x: number | null) => (x === null ? "an unknown amount" : `$${x.toFixed(2)}`);
/** A reading failing this long raises an early warning before the blind trip. */
export const READING_WARN_MS = 3_600_000;

/** Peak spend as a fraction of the budget. Any unknown (null) amount or a
 * budget that is not positive counts as over every level: fail toward alerting. */
function peakFraction(actual: number | null, projected: number | null, budget: number | null): number {
  if (actual === null || projected === null || budget === null || !(budget > 0)) return Number.POSITIVE_INFINITY;
  const f = Math.max(actual, projected) / budget;
  return Number.isNaN(f) ? Number.POSITIVE_INFINITY : f;
}

/** Conditions that follow from the guard's own state. */
export function guardConditions(doc: GuardDoc, nowMs: number, blindAfterMs: number): AlertCondition[] {
  const out: AlertCondition[] = [];
  const e = doc.evaluation;
  if (e) {
    // Once per level per billing period (and budget: a raise starts the levels afresh).
    const period = (doc.period?.start ?? e.at).slice(0, 10);
    const peak = peakFraction(e.actual_usd, e.projected_usd, e.budget_usd);
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
