import type { BucketLike } from "./bucket";
import type { AlertCondition } from "./conditions";
import { describeError } from "./errors";
import { GRID_D, type Grid, type Horizon, gridOf, indexAt, startMs } from "./grid";
import type { GuardOutcome } from "./guard";
import { reconcileIndex } from "./indexpage";
import { type LiveSource, offairWithoutFallback, putLive, renderLive } from "./live";
import { fallbackReason, holdLease, type Lease, type MetronomeClient, type MetronomeStatus,
         playLease } from "./metronome-core";
import type { FallbackIndex, PlaylistConfig } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";
export { LIVE_KEY } from "./live";

export interface ClockConfig extends PlaylistConfig {
  loopMs: number;
  liveMaxAge: number;
  /** Alert when the published lead (end of horizon.last - now) is below this. */
  leadFloorMs: number;
}

export interface ClockEnv {
  PLAYLIST_WINDOW?: string;
  PLAYLIST_LOOKAHEAD?: string;
  PLAYLIST_HOLD_BACK?: string;
  GRACE_SEGMENTS?: string;
  OFFAIR_AFTER_SECONDS?: string;
  LOOP_SECONDS?: string;
  LIVE_MAX_AGE?: string;
  LEAD_FLOOR_HOURS?: string;
  /** The metronome's rollback switch: only the exact string "on" enables it; anything else is off. */
  METRONOME?: string;
}

function num(v: string | undefined, fallback: number): number {
  const x = v === undefined ? Number.NaN : Number(v);
  return Number.isFinite(x) && x >= 0 ? x : fallback;
}

/** The lookahead never exceeds this (amendment A4, amended 2026-10-12). */
export const MAX_LOOKAHEAD = 16;

export function configFromEnv(env: ClockEnv): ClockConfig {
  const windowSegments = Math.max(1, Math.floor(num(env.PLAYLIST_WINDOW, 6)));
  return {
    window: windowSegments,
    lookahead: Math.min(MAX_LOOKAHEAD, Math.floor(num(env.PLAYLIST_LOOKAHEAD, 0))),
    // The start offset must lie inside the listed window.
    holdBack: Math.min(windowSegments - 1, Math.floor(num(env.PLAYLIST_HOLD_BACK, 0))),
    grace: Math.floor(num(env.GRACE_SEGMENTS, 3)),
    offairAfterMs: num(env.OFFAIR_AFTER_SECONDS, 86_400) * 1000,
    loopMs: num(env.LOOP_SECONDS, 75) * 1000,
    liveMaxAge: Math.max(1, Math.floor(num(env.LIVE_MAX_AGE, 5))),
    leadFloorMs: num(env.LEAD_FLOOR_HOURS, 16) * 3_600_000,
  };
}

export interface ClockDeps {
  bucket: BucketLike;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  scheduledTime: number;
  config: ClockConfig;
  /** The cost guard step (guard.ts), run first; it decides blocked. */
  guard: () => Promise<GuardOutcome>;
  /** Where this invocation's alert conditions go (alerts.ts); default: logged.
   * Called exactly once per invocation, after the last playlist write or at an
   * early return or throw. See AlertBatch for what `complete` obliges. */
  alerts?: (conditions: AlertCondition[], nowMs: number, batch: AlertBatch) => Promise<void>;
  /** The metronome (metronome spec), given only when METRONOME is exactly "on".
   * It is renewed every invocation, on every path, with the lease the lease
   * table names; cron's own loop then runs only as the fallback, and only with
   * a known verdict and an accepted horizon. Absent: cron's loop exactly as
   * before. */
  metronome?: MetronomeClient;
}

/** The scope of one invocation's condition set.
 *
 * `complete` is true only when runClock reached the end of its normal path, so
 * every condition was computed and a key absent from the batch has genuinely
 * cleared. It is false on an unknown guard outcome, a guard crash, the
 * horizon-missing / horizon-refused early returns and any throw: the batch is
 * then partial (the conditions it carries are real, but the ones that were
 * never computed are simply missing). A sink MUST NOT resolve -- announce as
 * cleared, or start any cooldown for -- a key that is absent from an
 * incomplete batch; it may still send and repeat the conditions present.
 * Otherwise one transient R2 failure while tripped would announce
 * "resolved: Station blocked: spend".
 *
 * `guardComplete` is true whenever the guard returned a known outcome (not
 * unknown, not crashed): every guard-family condition (guard.ts,
 * conditions.ts) was then computed, so a sink may resolve an absent
 * guard-family key even when `complete` is false. Clock-family keys (and any
 * key it does not recognise) still resolve only on a complete batch. */
export interface AlertBatch {
  complete: boolean;
  guardComplete: boolean;
}

/** What runClock throws: the original failure's message, with the partial
 * result so far (guardMs, blocked, puts ...) for the per-invocation clock line. */
export class ClockError extends Error {
  constructor(readonly cause: unknown, readonly partial: ClockResult) {
    super(describeError(cause));
    this.name = "ClockError";
  }
}

export interface ClockResult {
  puts: number;
  skipped: number;
  /** Set when off-air was in force but no usable fallback/notice exists, so
   * the ENDLIST-only playlist (no notice) was written instead (also logged
   * once per invocation as a structured console.error). */
  offairWithoutFallback: string | null;
  /** Set when the horizon was refused (d is not the grid constant); nothing written. */
  refused: string | null;
  /** The guard's verdict: null = unknown, nothing written this invocation. */
  blocked: boolean | null;
  /** How long the guard step took. Logged on the clock line: amendment A4's
   * trigger adds it to the cron lag. */
  guardMs: number | null;
  index: "written" | "unchanged" | "failed" | "skipped";
  /** Keys of the alert conditions raised this invocation. */
  alerts: string[];
  /** The renew this invocation made (the clock line's `metronome`), or null
   * when the metronome is off. */
  metronome: MetronomeLine | null;
}

/** One invocation's renew, for the clock line. */
export interface MetronomeLine {
  /** What cron passed: a play lease (blocked or not), a hold, or null (a health check). */
  sent: "play" | "blocked" | "hold" | null;
  /** The DO's answer; null when renew threw or timed out. */
  status: MetronomeStatus | null;
  error: string | null;
  /** Why cron fell back (metronome-core fallbackReason), or null. */
  fallback: string | null;
}

// Spend is the strict surface (Cloudflare has no spending cap), so the PUT
// bound is absolute and never derived from inputs alone: d comes from
// state/horizon.json and loopMs from a wrangler var, and either could
// otherwise turn the cap into thousands of Class-A writes per invocation.
export { GRID_D };
/** The spec's run length: write until scheduledTime + 75 s, never longer. */
export const MAX_LOOP_MS = 75_000;
/** ceil(75 / 10.24) + 2: the per-invocation PUT ceiling, whatever the inputs. */
export const MAX_PUTS = 10;
const BOUNDARY_SLACK_MS = 25;

export interface ClockInputs {
  horizon: Horizon | null;
  fallback: FallbackIndex | null;
  /** Blocked (tripped OR offair), from the guard: the off-air playlist. */
  offair: boolean;
}

async function readJson<T>(bucket: BucketLike, key: string): Promise<T | null> {
  const obj = await bucket.get(key);
  if (obj === null) return null;
  try {
    return JSON.parse(await obj.text()) as T;
  } catch {
    return null;
  }
}

/** The horizon and its fallback, read once per invocation via the binding
 * (never through the cache). The blocked state comes from the guard. */
export async function readInputs(bucket: BucketLike, blocked: boolean): Promise<ClockInputs> {
  const horizon = await readJson<Horizon>(bucket, "state/horizon.json");
  const fallback = horizon?.fallback_version
    ? await readJson<FallbackIndex>(bucket, `fallback/${horizon.fallback_version}/index.json`)
    : null;
  return { horizon, fallback, offair: blocked };
}

/** Default alert sink when none is given: one structured line each, carrying
 * the batch's scope (AlertBatch). */
export async function logAlerts(conditions: AlertCondition[], _nowMs: number, batch: AlertBatch): Promise<void> {
  for (const c of conditions) {
    console.error(JSON.stringify({ event: "alert", key: c.key, title: c.title, message: c.message,
                                   complete: batch.complete, guardComplete: batch.guardComplete }));
  }
}

export function putCap(cfg: ClockConfig, dMs: number): number {
  return Math.min(MAX_PUTS, Math.ceil(cfg.loopMs / dMs) + 2);
}

/**
 * One cron invocation. First the cost guard (guard.ts): it decides blocked =
 * tripped OR offair and reconciles the kill switch; when it cannot tell, the
 * invocation writes nothing at all. Then index.html follows the blocked state,
 * and the playlist is written immediately and at every grid boundary
 * E + N*d until scheduledTime + loopMs (the off-air playlist while blocked).
 * Alerts go out after the last playlist write, so a slow channel never delays
 * a boundary write. Only CPU time is billed, so the waiting is free.
 * Overlapping invocations are harmless: the playlist is a pure function of the
 * clock and the inputs. With the metronome on (deps.metronome), the playlist
 * is the Durable Object's: cron renews its lease on every path (metronome
 * spec, lease table) and runs that loop only as the fallback.
 *
 * Epoch change: inputs are read once per invocation, so an epoch never changes
 * inside one. When state/horizon.json's epoch_id changes between invocations,
 * segment numbering restarts (N from 0 at the new epoch E) and
 * EXT-X-MEDIA-SEQUENCE drops. That is deliberate, not a defect: a new epoch is
 * an operator re-render event (transmitter re-renders and republishes under
 * seg/<new epoch_id>/), and players must reload the stream to follow it.
 */
export async function runClock(deps: ClockDeps): Promise<ClockResult> {
  const { bucket } = deps;
  const config: ClockConfig = {
    ...deps.config,
    loopMs: Math.min(deps.config.loopMs, MAX_LOOP_MS),
    liveMaxAge: Math.max(1, Math.floor(deps.config.liveMaxAge)),
  };
  if (config.loopMs !== deps.config.loopMs) {
    console.error(JSON.stringify({ event: "loop-clamped", configuredMs: deps.config.loopMs, usedMs: config.loopMs,
                                   scheduled: deps.scheduledTime }));
  }
  const result: ClockResult = { puts: 0, skipped: 0, offairWithoutFallback: null, refused: null, blocked: null,
                                guardMs: null, index: "skipped", alerts: [], metronome: null };
  const conditions: AlertCondition[] = [];
  let flushed = false;
  let complete = false; // set only at the end of the normal path (AlertBatch)
  let guardComplete = false; // set once the guard returned a known outcome (AlertBatch)
  let failureNamed = false; // a condition naming this path's failure was pushed (no clock-failed then)
  const flush = async () => {
    if (flushed) return;
    flushed = true;
    result.alerts = conditions.map((c) => c.key);
    try {
      await (deps.alerts ?? logAlerts)(conditions, deps.now(), { complete, guardComplete });
    } catch (e) {
      console.error(JSON.stringify({ event: "alert-dispatch-failed", error: describeError(e) }));
    }
  };
  /** Renew the metronome (a no-op when it is off) and say whether cron must
   * fall back. Never throws: a failed or timed-out renew is trigger (a). Every
   * return path below calls it first, with the lease the lease table names. */
  const renew = async (lease: Lease | null): Promise<string | null> => {
    if (!deps.metronome) return null;
    const sent = lease === null ? null : lease.kind === "hold" ? "hold" : lease.blocked ? "blocked" : "play";
    let r: { status: MetronomeStatus } | { error: string };
    try {
      const status: unknown = await deps.metronome.renew(lease);
      // Data from another isolate (a skewed or broken DO): fallbackReason reads its fields.
      r = typeof status === "object" && status !== null ? { status: status as MetronomeStatus }
                                                        : { error: "renew returned a non-object" };
    } catch (e) {
      r = { error: describeError(e) };
    }
    const fallback = fallbackReason(lease, r);
    result.metronome = { sent, status: "status" in r ? r.status : null, error: "error" in r ? r.error : null, fallback };
    if (fallback !== null) {
      console.error(JSON.stringify({ event: "metronome-down", reason: fallback, scheduled: deps.scheduledTime }));
      conditions.push({ key: "metronome-down", priority: "high", resolvable: true, title: "Metronome down",
                        message: `The metronome looks dead (${fallback}). The clock's own loop writes live.m3u8 ` +
                                 "this minute when the verdict is known and the horizon accepted." });
    }
    return fallback;
  };
  try {
    // 1. The guard, first: it decides blocked and reconciles the kill switch.
    const startedMs = deps.now(); // the lease's verdictAt: when this guard step's state reads began
    let outcome: GuardOutcome;
    try {
      outcome = await deps.guard();
    } catch (e) {
      outcome = { blocked: null, tripped: null, offair: null, doc: null, conditions: [{
        key: "guard-crashed", priority: "urgent", resolvable: true, title: "Cost guard crashed",
        message: `The guard step threw (${describeError(e)}); the clock wrote nothing.` }] };
    }
    result.guardMs = deps.now() - startedMs;
    conditions.push(...outcome.conditions);
    result.blocked = outcome.blocked;
    if (outcome.blocked === null) {
      // Unknown: change nothing (players stall on a stale playlist, toward zero
      // cost). The metronome keeps its current lease, to its expiry.
      console.error(JSON.stringify({ event: "guard-unknown", scheduled: deps.scheduledTime }));
      await renew(null);
      return result;
    }
    guardComplete = true;
    const blocked = outcome.blocked;
    // 2. index.html follows the blocked state.
    try {
      result.index = await reconcileIndex(bucket, blocked);
    } catch (e) {
      result.index = "failed";
      conditions.push({ key: "index-write", priority: "high", resolvable: true, title: "index.html not reconciled",
                        message: `Writing index.html (${blocked ? "off-air" : "player"} page) failed: ${describeError(e)}` });
    }
    // 3. The playlist. Lease table (metronome spec): unusable inputs pass on a
    // known blocked verdict as a hold, and an unblocked one as no lease at all.
    const unusable = () => (blocked ? holdLease(startedMs, deps.now()) : null);
    const failedInputs = (e: unknown) => {
      failureNamed = true;
      conditions.push({ key: "clock-inputs", priority: "urgent", resolvable: true, title: "Clock cannot read its inputs",
                        message: `Reading state/horizon.json or its fallback, or deriving the grid from it, failed ` +
                                 `(${describeError(e)}); live.m3u8 was not written this minute.` });
      return e;
    };
    let inputs: ClockInputs;
    try {
      inputs = await readInputs(bucket, blocked);
    } catch (e) {
      await renew(unusable());
      throw failedInputs(e);
    }
    const horizon = inputs.horizon;
    if (horizon === null) {
      conditions.push({ key: "horizon-missing", priority: "default", resolvable: true, title: "No horizon published",
                        message: "state/horizon.json is absent, or unreadable (not JSON): live.m3u8 was not written. " +
                                 "Either nothing is on air yet (transmitter has not published) or the object is corrupt." });
      await renew(unusable());
      return result;
    }
    if (horizon.d !== GRID_D) {
      result.refused = `state/horizon.json d is ${JSON.stringify(horizon.d)}, not the grid constant ${GRID_D}: live.m3u8 not written`;
      console.error(JSON.stringify({ event: "horizon-refused", reason: result.refused, d: horizon.d,
                                     epoch_id: horizon.epoch_id, scheduled: deps.scheduledTime }));
      conditions.push({ key: "horizon-refused", priority: "urgent", resolvable: true, title: "Horizon refused",
                        message: result.refused });
      await renew(holdLease(startedMs, deps.now())); // a spend refusal, not a transient: the DO stops at once
      return result;
    }
    let g: Grid;
    try {
      g = gridOf(horizon);
    } catch (e) {
      await renew(unusable());
      throw failedInputs(e);
    }
    const leadMs = startMs(g, horizon.last + 1) - deps.now();
    // While tripped, transmitter stops publishing by design: the lead drains then.
    if (!outcome.tripped && leadMs < config.leadFloorMs) {
      conditions.push({ key: "lead-low", priority: "high", resolvable: true, title: "Published lead below floor",
                        message: `The published lead is ${(leadMs / 3_600_000).toFixed(1)} h (floor ` +
                                 `${(config.leadFloorMs / 3_600_000).toFixed(1)} h): is transmitter on hugo publishing?` });
    }
    const src: LiveSource = { horizon, fallback: inputs.fallback, offair: inputs.offair };
    // Ruling: off-air without a usable fallback writes the ENDLIST-only
    // playlist (cap and identical-bytes skip apply), but stays loud: the notice
    // is missing. Raised by cron from its own inputs, once per invocation:
    // before the lease is issued, and again by the loop if it starts later on.
    const noteOffairWithoutFallback = (reason: string | null) => {
      if (result.offairWithoutFallback !== null || reason === null) return;
      result.offairWithoutFallback = reason;
      console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                     fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
      conditions.push({ key: "offair-without-fallback", priority: "high", resolvable: true,
                        title: "Off-air without a notice", message: reason });
    };
    noteOffairWithoutFallback(offairWithoutFallback(src, deps.now(), config));
    // 4. The lease: a known verdict and an accepted horizon. A healthy DO writes
    // the playlist from here on; cron's loop runs only when it looks dead.
    if (deps.metronome && (await renew(playLease(startedMs, deps.now(), blocked, horizon, inputs.fallback))) === null) {
      complete = true;
      return result;
    }
    const cap = putCap(config, g.dMs);
    let lastBody: string | null = null;
    const write = async (force: boolean) => {
      const nowMs = deps.now();
      // The off-air number comes from max(scheduledTime + loopMs, nowMs) plus
      // lookahead + 1 (playlist.offairSequence): constant within an on-time
      // invocation, and above every live segment listed so far even when this
      // invocation runs later than its own loop.
      const { body, offairWithoutFallback: reason } = renderLive(src, nowMs, deps.scheduledTime + config.loopMs, config);
      noteOffairWithoutFallback(reason);
      if (body === null) return;
      if (!force && body === lastBody) {
        result.skipped++;
        return;
      }
      if (result.puts >= cap) return;
      await putLive(bucket, body, config.liveMaxAge);
      result.puts++;
      lastBody = body;
    };
    await write(true);
    const deadline = deps.scheduledTime + config.loopMs;
    while (result.puts < cap) {
      const now = deps.now();
      const next = startMs(g, indexAt(g, now) + 1);
      if (next > deadline) break;
      await deps.sleep(next - now + BOUNDARY_SLACK_MS);
      await write(false);
    }
    complete = true;
    return result;
  } catch (e) {
    if (!failureNamed) {
      // Catch-all, so no failure goes unalerted (a failed playlist PUT, say).
      conditions.push({ key: "clock-failed", priority: "urgent", resolvable: true, title: "Clock invocation failed",
                        message: `The clock invocation threw (${describeError(e)}); ` +
                                 "live.m3u8 may not have been written this minute." });
    }
    throw new ClockError(e, result);
  } finally {
    await flush(); // after the last playlist write (or an early return), never before the guard
  }
}
