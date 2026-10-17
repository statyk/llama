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

import { type BucketLike, createJson, type JsonRead, putJson, readJsonDoc } from "./bucket";
import type { ClockEnv } from "./clock";
import { type AlertCondition, guardConditions } from "./conditions";
import { describeError } from "./errors";
import { applyAttempt, applyBlindRule, BUDGET_KEY, corruptGuardDoc, effectiveBudget, freshGuardDoc, GUARD_KEY,
         type GuardDoc, OFFAIR_KEY, parseGuardDoc, shouldEvaluate, validBaseBudget } from "./latch";
import { assertMetronomeMetered, readUsage } from "./meter";
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
  /** METRONOME is exactly "on": an empty Durable Object reading is a failed one. */
  metronomeOn: boolean;
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
 * so does an invalid BILLING_ANNIVERSARY_DAY, through billingPeriod's refusal.
 * No network call is ever made with an empty account, zone or token: the
 * problems are thrown before the call. */
export function guardConfigFromEnv(env: GuardEnv & Pick<ClockEnv, "METRONOME">): GuardConfig {
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
    metronomeOn: env.METRONOME === "on",
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

const msg = describeError;

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
 * theirs has no newer successful reading -- a newer success would clear it.
 * A spend trip also replaces a blind one: spend is the stickier latch (only a
 * raise or a new period clears it), so letting blind stand would lose it.
 * A loser that merely carried prev's spend trip forward can re-impose it over a
 * winner that cleared it with a raise: fail-closed, and it self-heals at the
 * merged document's next evaluation (within 15 minutes). */
export function mergeLostRace(ours: GuardDoc, theirs: GuardDoc): GuardDoc | null {
  if (!ours.tripped) return null;
  if (theirs.tripped && !(ours.reason === "spend" && theirs.reason === "blind")) return null;
  if (ours.reason === "blind" && theirs.last_success !== null &&
      (ours.last_success === null || Date.parse(theirs.last_success) > Date.parse(ours.last_success))) {
    return null;
  }
  return { ...theirs, tripped: true, reason: ours.reason, tripped_at: ours.tripped_at,
           tripped_period_start: ours.tripped_period_start, tripped_budget_usd: ours.tripped_budget_usd };
}

/** How a write of guard.json is conditioned: over the etag read, create-only
 * (the key was absent), or unconditional (no etag to go on). */
type Precondition = { etag: string } | "absent" | null;

/** Losing more races than this in one invocation fails the write (`guard-write`). */
const PERSIST_ATTEMPTS = 3;

async function writeGuard(bucket: BucketLike, doc: GuardDoc, pre: Precondition): Promise<boolean> {
  if (pre === null) return putJson(bucket, GUARD_KEY, doc);
  if (pre !== "absent") return putJson(bucket, GUARD_KEY, doc, pre.etag);
  try {
    return await createJson(bucket, GUARD_KEY, doc);
  } catch {
    // A create-only put the store refused outright (not a failed precondition,
    // which is null): write unconditionally rather than never create the
    // document -- without it every invocation starts afresh and blind never trips.
    return putJson(bucket, GUARD_KEY, doc);
  }
}

/** What stands in guard.json after persisting: a document, or bytes that do
 * not parse (the next reader treats them as a spend trip). */
type Stored = { kind: "doc"; doc: GuardDoc } | { kind: "corrupt" };

/** Persist conditionally; if another invocation wrote meanwhile, never let our
 * trip be lost (mergeLostRace), retrying the merge if we lose again.
 *
 * Exhausting PERSIST_ATTEMPTS throws (alerted as `guard-write`) and leaves the
 * last winner's document standing: a trip of ours is then absent from storage
 * until the next invocation re-derives it -- a blind trip the next minute, a
 * spend trip at the next evaluation (up to 15 min). This run still reports it
 * (the caller's outcome keeps our decision), so this minute stays blocked. */
async function persist(bucket: BucketLike, doc: GuardDoc, pre: Precondition): Promise<Stored> {
  let ours = doc;
  for (let i = 0; ; i++) {
    if (await writeGuard(bucket, ours, pre)) return { kind: "doc", doc: ours };
    if (i + 1 >= PERSIST_ATTEMPTS) break; // no re-read we would not use
    const latest = await readJsonDoc(bucket, GUARD_KEY);
    if (latest.kind === "absent") {
      // Deleted between our read and our write: create-only, so a racer that
      // creates it meanwhile is merged with, not clobbered. Only when a
      // create-only write was itself refused and the key is still absent (a
      // store that mishandles the precondition) is the write unconditional.
      pre = pre === "absent" ? null : "absent";
      continue;
    }
    const theirs = latest.kind === "ok" ? parseGuardDoc(latest.value) : null;
    if (theirs === null) return { kind: "corrupt" };
    const merged = mergeLostRace(ours, theirs);
    if (merged === null) return { kind: "doc", doc: theirs };
    ours = merged;
    pre = latest.etag ? { etag: latest.etag } : null;
  }
  throw new Error(`lost the write race ${PERSIST_ATTEMPTS} times in one invocation`);
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
  // A raise that cannot be read is never silent. A read that throws skips this
  // minute's evaluation (evaluated_at is not advanced, so the next minute
  // retries, and blind keeps counting from the last success): evaluating
  // against the base instead would trip spend on a raise the guard merely
  // failed to read, and hold the station off the air until the next
  // evaluation. Unparseable bytes are a lasting state, not a blip: evaluate
  // against the configured budget (stricter) and say so.
  let budgetRaw: unknown = null;
  let budgetReadFailed = false;
  const budgetUnreadable = (detail: string): AlertCondition =>
    ({ key: "budget-unreadable", priority: "high", resolvable: true, title: "state/budget.json unreadable",
       message: `${detail} Rewrite it with \`transmitter budget --raise-to <usd>\`, or remove it to use the configured budget.` });
  try {
    const b = await readJsonDoc(bucket, BUDGET_KEY);
    if (b.kind === "ok") budgetRaw = b.value;
    else if (b.kind === "corrupt") {
      conditions.push(budgetUnreadable(`state/budget.json is not JSON (${b.error}); evaluating against the ` +
                                       `configured budget ($${cfg.baseBudgetUsd}).`));
    }
  } catch (e) {
    budgetReadFailed = true;
    conditions.push(budgetUnreadable(`Reading state/budget.json failed (${msg(e)}); the spend evaluation is ` +
                                     "skipped until it can be read (the blind rule keeps counting)."));
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

  const period = periodOrNull(nowMs, cfg);
  const budget = effectiveBudget(cfg.baseBudgetUsd, budgetRaw, nowMs, period?.endMs ?? null);
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
    prev = corruptGuardDoc(nowMs, period, budget.budgetUsd);
    conditions.push({ key: "guard-state-corrupt", priority: "urgent", resolvable: true, title: "state/guard.json unreadable",
                      message: "state/guard.json could not be read as guard state; the guard treats the station as " +
                               "tripped for spend. Clear it with `transmitter budget --raise-to <usd>` or wait for the " +
                               "next billing period." });
  }

  // A corrupt document is overwritten over its own etag (readJsonDoc keeps it).
  const pre: Precondition = guardRead.kind === "absent" ? "absent" : guardRead.etag ? { etag: guardRead.etag } : null;
  let doc = prev;
  let blocked = true;
  let stored: GuardDoc | null = null; // what stands in guard.json after this run, when it differs from doc
  let turnedOff = false; // the reconcile disabled the kill switch this run
  let raceUnknown = false; // the post-unblock re-check could not read state
  try {
    if (!budgetReadFailed && shouldEvaluate(prev, nowMs, cfg.evalIntervalMs, budget.writtenAtMs)) {
      try {
        // Ahead of everything else: no network call with an empty account or
        // token, and an invalid base budget never reaches a successful attempt.
        if (cfg.meterProblems.length > 0) throw new Error(cfg.meterProblems.join("; "));
        const p = billingPeriod(nowMs, cfg.anniversaryDay);
        const reading = await readUsage(deps.fetch, { accountId: cfg.accountId, token: cfg.analyticsToken }, p, nowMs);
        if (cfg.metronomeOn) assertMetronomeMetered(reading);
        const evaluation = evaluateSpend(reading, p, nowMs, budget.budgetUsd);
        doc = applyAttempt(doc, { ok: true, evaluation, period: p, baseBudgetUsd: cfg.baseBudgetUsd });
      } catch (e) {
        doc = applyAttempt(doc, { ok: false, atMs: nowMs, error: msg(e) });
      }
    }
  } finally {
    doc = applyBlindRule(doc, nowMs, cfg.blindAfterMs);
    blocked = doc.tripped || offair;
    try {
      // No network call with an empty zone or token. Any throw -- WafError, a
      // timeout's DOMException, a network TypeError -- leaves the decision
      // standing and is alerted: a block stays cooperative (ENDLIST + off-air page).
      if (cfg.wafProblems.length > 0) throw new Error(cfg.wafProblems.join("; "));
      const r = await reconcileKillSwitch(deps.fetch, { zoneId: cfg.zoneId, token: cfg.wafToken,
                                                        description: cfg.killSwitchDescription }, blocked);
      turnedOff = r.changed && !r.enabled;
      if (r.changed && prev.waf.enabled === r.enabled) {
        // It was the opposite of what the guard last set or saw: a hand toggle,
        // or an overlapping invocation acting on newer state, undone.
        conditions.push({ key: "waf-corrected", priority: "high", resolvable: false, title: "Kill switch corrected",
                          message: `The kill switch was ${r.enabled ? "off" : "on"}, set to ${r.enabled ? "on" : "off"} ` +
                                   `to match blocked=${blocked}. It was changed by hand or by an overlapping ` +
                                   "invocation since the guard last saw it. The guard reconciles it every minute: use " +
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
        const s = await persist(bucket, doc, pre);
        // A winner's document that stands (or unreadable bytes, which the next
        // reader turns into a spend trip) is what the next invocation acts on.
        stored = s.kind === "doc" ? s.doc : corruptGuardDoc(nowMs, period, budget.budgetUsd);
      } catch (e) {
        conditions.push({ key: "guard-write", priority: "high", resolvable: true, title: "Cost guard cannot save its state",
                          message: `Writing state/guard.json failed: ${msg(e)}.` });
      }
    }
  }
  if (turnedOff && stored === null) {
    // We unblocked without writing guard.json, so a race was never checked: an
    // overlapping invocation may have tripped (and enabled the switch we just
    // disabled) since our read. One HEAD finds out; on a newer document, fold
    // its trip into this outcome so this minute stays blocked (the next run
    // re-enables the switch).
    try {
      const head = await bucket.head(GUARD_KEY);
      const readEtag = guardRead.kind === "absent" ? undefined : guardRead.etag;
      if (head !== null && head.etag !== readEtag) {
        const latest = await readJsonDoc(bucket, GUARD_KEY);
        const theirs = latest.kind === "ok" ? parseGuardDoc(latest.value) : null;
        if (latest.kind !== "absent" && (theirs === null || theirs.tripped)) {
          stored = theirs ?? corruptGuardDoc(nowMs, period, budget.budgetUsd);
        }
      }
    } catch (e) {
      // Cannot tell whether a racer tripped: fail toward blocked for this minute.
      raceUnknown = true;
      conditions.push({ key: "guard-unknown", priority: "high", resolvable: true, title: "Cost guard cannot read its state",
                        message: `Re-checking state/guard.json after turning the kill switch off failed (${msg(e)}); ` +
                                 "this minute is treated as blocked." });
    }
  }
  // Never report less blocked than what was decided, or than what now stands in
  // state (another invocation's trip that won the race): the clock then writes
  // ENDLIST this minute, and the next run reconciles the kill switch to it.
  const final = stored ?? doc;
  const tripped = doc.tripped || final.tripped;
  conditions.push(...guardConditions(final, nowMs, cfg.blindAfterMs));
  return { blocked: blocked || tripped || raceUnknown, tripped, offair, doc: final, conditions };
}
