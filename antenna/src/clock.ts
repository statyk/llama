import type { BucketLike } from "./bucket";
import type { AlertCondition } from "./conditions";
import { type Grid, type Horizon, gridOf, indexAt, startMs } from "./grid";
import type { GuardOutcome } from "./guard";
import { reconcileIndex } from "./indexpage";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";

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
}

function num(v: string | undefined, fallback: number): number {
  const x = v === undefined ? Number.NaN : Number(v);
  return Number.isFinite(x) && x >= 0 ? x : fallback;
}

/** The lookahead never exceeds this (amendment A4, amended 2026-10-12). */
export const MAX_LOOKAHEAD = 16;

export function configFromEnv(env: ClockEnv): ClockConfig {
  const window = Math.max(1, Math.floor(num(env.PLAYLIST_WINDOW, 6)));
  return {
    window,
    lookahead: Math.min(MAX_LOOKAHEAD, Math.floor(num(env.PLAYLIST_LOOKAHEAD, 0))),
    // The start offset must lie inside the listed window.
    holdBack: Math.min(window - 1, Math.floor(num(env.PLAYLIST_HOLD_BACK, 0))),
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
    super(cause instanceof Error ? cause.message : String(cause));
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
}

export const LIVE_KEY = "live.m3u8";

// Spend is the strict surface (Cloudflare has no spending cap), so the PUT
// bound is absolute and never derived from inputs alone: d comes from
// state/horizon.json and loopMs from a wrangler var, and either could
// otherwise turn the cap into thousands of Class-A writes per invocation.
/** The grid constant transmitter always writes: 441 * 1024 / 44100 s. */
export const GRID_D = 10.24;
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

/** Why off-air is in force at nowMs and no usable fallback exists, or null. */
function offairWithoutFallback(inputs: ClockInputs, horizon: Horizon, nowMs: number, cfg: ClockConfig): string | null {
  const inp = { nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair };
  if (!isOffair(inp, cfg) || usableFallback(inp) !== null) return null;
  const cause = inputs.offair
    ? "the station is blocked (tripped or state/offair.json)"
    : `horizon is stale (now is more than ${cfg.offairAfterMs / 1000} s past the end of segment ${horizon.last})`;
  const missing =
    horizon.fallback_version === null || horizon.fallback_version === ""
      ? "horizon.fallback_version is null"
      : inputs.fallback === null
        ? `fallback/${horizon.fallback_version}/index.json is missing or unreadable`
        : `fallback/${horizon.fallback_version}/index.json has len < 1`;
  return `off-air (${cause}) but no usable fallback (${missing}): live.m3u8 written as an ENDLIST-only playlist (no notice), so players stop`;
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
 * clock and the inputs.
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
                                guardMs: null, index: "skipped", alerts: [] };
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
      console.error(JSON.stringify({ event: "alert-dispatch-failed", error: e instanceof Error ? e.message : String(e) }));
    }
  };
  try {
    // 1. The guard, first: it decides blocked and reconciles the kill switch.
    const startedMs = deps.now();
    let outcome: GuardOutcome;
    try {
      outcome = await deps.guard();
    } catch (e) {
      outcome = { blocked: null, tripped: null, offair: null, doc: null, conditions: [{
        key: "guard-crashed", priority: "urgent", resolvable: true, title: "Cost guard crashed",
        message: `The guard step threw (${e instanceof Error ? e.message : String(e)}); the clock wrote nothing.` }] };
    }
    result.guardMs = deps.now() - startedMs;
    conditions.push(...outcome.conditions);
    result.blocked = outcome.blocked;
    if (outcome.blocked === null) {
      // Unknown: change nothing (players stall on a stale playlist, toward zero cost).
      console.error(JSON.stringify({ event: "guard-unknown", scheduled: deps.scheduledTime }));
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
                        message: `Writing index.html (${blocked ? "off-air" : "player"} page) failed: ${e instanceof Error ? e.message : String(e)}` });
    }
    // 3. The playlist.
    const failedInputs = (e: unknown) => {
      failureNamed = true;
      conditions.push({ key: "clock-inputs", priority: "urgent", resolvable: true, title: "Clock cannot read its inputs",
                        message: `Reading state/horizon.json or its fallback, or deriving the grid from it, failed ` +
                                 `(${e instanceof Error ? e.message : String(e)}); live.m3u8 was not written this minute.` });
      return e;
    };
    let inputs: ClockInputs;
    try {
      inputs = await readInputs(bucket, blocked);
    } catch (e) {
      throw failedInputs(e);
    }
    const horizon = inputs.horizon;
    if (horizon === null) {
      conditions.push({ key: "horizon-missing", priority: "default", resolvable: true, title: "No horizon published",
                        message: "state/horizon.json is absent, or unreadable (not JSON): live.m3u8 was not written. " +
                                 "Either nothing is on air yet (transmitter has not published) or the object is corrupt." });
      return result;
    }
    if (horizon.d !== GRID_D) {
      result.refused = `state/horizon.json d is ${JSON.stringify(horizon.d)}, not the grid constant ${GRID_D}: live.m3u8 not written`;
      console.error(JSON.stringify({ event: "horizon-refused", reason: result.refused, d: horizon.d,
                                     epoch_id: horizon.epoch_id, scheduled: deps.scheduledTime }));
      conditions.push({ key: "horizon-refused", priority: "urgent", resolvable: true, title: "Horizon refused",
                        message: result.refused });
      return result;
    }
    let g: Grid;
    try {
      g = gridOf(horizon);
    } catch (e) {
      throw failedInputs(e);
    }
    const leadMs = startMs(g, horizon.last + 1) - deps.now();
    // While tripped, transmitter stops publishing by design: the lead drains then.
    if (!outcome.tripped && leadMs < config.leadFloorMs) {
      conditions.push({ key: "lead-low", priority: "high", resolvable: true, title: "Published lead below floor",
                        message: `The published lead is ${(leadMs / 3_600_000).toFixed(1)} h (floor ` +
                                 `${(config.leadFloorMs / 3_600_000).toFixed(1)} h): is transmitter on hugo publishing?` });
    }
    const cap = putCap(config, g.dMs);
    let lastBody: string | null = null;
    const write = async (force: boolean) => {
      const nowMs = deps.now();
      // The off-air number comes from max(scheduledTime + loopMs, nowMs) plus
      // lookahead + 1 (playlist.offairSequence): constant within an on-time
      // invocation, and above every live segment listed so far even when this
      // invocation runs later than its own loop.
      const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair,
                                   offairSeqMs: deps.scheduledTime + config.loopMs }, config);
      // Ruling: off-air without a usable fallback writes the ENDLIST-only
      // playlist through the normal path below (cap and identical-bytes skip
      // apply), but stays loud: the notice is missing. Once per invocation.
      if (result.offairWithoutFallback === null) {
        const reason = offairWithoutFallback(inputs, horizon, nowMs, config);
        if (reason !== null) {
          result.offairWithoutFallback = reason;
          console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                         fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
          conditions.push({ key: "offair-without-fallback", priority: "high", resolvable: true,
                            title: "Off-air without a notice", message: reason });
        }
      }
      if (body === null) return;
      if (!force && body === lastBody) {
        result.skipped++;
        return;
      }
      if (result.puts >= cap) return;
      await bucket.put(LIVE_KEY, body, {
        httpMetadata: { contentType: "application/vnd.apple.mpegurl", cacheControl: `public, max-age=${config.liveMaxAge}` },
      });
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
                        message: `The clock invocation threw (${e instanceof Error ? e.message : String(e)}); ` +
                                 "live.m3u8 may not have been written this minute." });
    }
    throw new ClockError(e, result);
  } finally {
    await flush(); // after the last playlist write (or an early return), never before the guard
  }
}
