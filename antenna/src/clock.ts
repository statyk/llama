import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export interface StoredObject {
  text(): Promise<string>;
}

export interface BucketLike {
  get(key: string): Promise<StoredObject | null>;
  put(key: string, value: string, options: { httpMetadata: { contentType: string; cacheControl: string } }): Promise<unknown>;
}

export function r2Bucket(b: R2Bucket): BucketLike {
  return {
    get: (key) => b.get(key),
    put: (key, value, options) => b.put(key, value, options),
  };
}

export interface ClockConfig extends PlaylistConfig {
  loopMs: number;
  liveMaxAge: number;
}

export interface ClockEnv {
  PLAYLIST_WINDOW?: string;
  GRACE_SEGMENTS?: string;
  OFFAIR_AFTER_SECONDS?: string;
  LOOP_SECONDS?: string;
  LIVE_MAX_AGE?: string;
}

function num(v: string | undefined, fallback: number): number {
  const x = v === undefined ? Number.NaN : Number(v);
  return Number.isFinite(x) && x >= 0 ? x : fallback;
}

export function configFromEnv(env: ClockEnv): ClockConfig {
  return {
    window: Math.max(1, Math.floor(num(env.PLAYLIST_WINDOW, 6))),
    grace: Math.floor(num(env.GRACE_SEGMENTS, 3)),
    offairAfterMs: num(env.OFFAIR_AFTER_SECONDS, 86_400) * 1000,
    loopMs: num(env.LOOP_SECONDS, 75) * 1000,
    liveMaxAge: Math.max(1, Math.floor(num(env.LIVE_MAX_AGE, 5))),
  };
}

export interface ClockDeps {
  bucket: BucketLike;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  scheduledTime: number;
  config: ClockConfig;
  guard?: (deps: ClockDeps) => Promise<void>;
}

export interface ClockResult {
  puts: number;
  skipped: number;
  /** Set when off-air was in force but no usable fallback/notice exists, so
   * nothing was written and the off-air lever did nothing (also logged once
   * per invocation as a structured console.error). */
  offairWithoutFallback: string | null;
  /** Set when the horizon was refused (d is not the grid constant); nothing written. */
  refused: string | null;
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

/**
 * Phase-2 seam. The cost guard runs here, first in every invocation and in
 * its own try/finally: it evaluates usage when state/guard.json is >= 15 min
 * old, applies the blind rule, and reconciles the blocked state (tripped OR
 * offair: ENDLIST playlist, off-air index.html, WAF kill switch) before any
 * playlist work. Phase 1 honours only a hand-written state/offair.json, which
 * readInputs reads; this is deliberately a no-op.
 */
export async function guardStep(_deps: ClockDeps): Promise<void> {}

export interface ClockInputs {
  horizon: Horizon | null;
  fallback: FallbackIndex | null;
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

/** state/ is read once per invocation, via the binding (never through the cache). */
export async function readInputs(bucket: BucketLike): Promise<ClockInputs> {
  const horizon = await readJson<Horizon>(bucket, "state/horizon.json");
  const offairDoc = await readJson<{ offair?: unknown }>(bucket, "state/offair.json");
  const fallback = horizon?.fallback_version
    ? await readJson<FallbackIndex>(bucket, `fallback/${horizon.fallback_version}/index.json`)
    : null;
  return { horizon, fallback, offair: offairDoc?.offair === true };
}

export function putCap(cfg: ClockConfig, dMs: number): number {
  return Math.min(MAX_PUTS, Math.ceil(cfg.loopMs / dMs) + 2);
}

/** Why off-air is in force at nowMs and no usable fallback exists, or null. */
function offairWithoutFallback(inputs: ClockInputs, horizon: Horizon, nowMs: number, cfg: ClockConfig): string | null {
  const inp = { nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair };
  if (!isOffair(inp, cfg) || usableFallback(inp) !== null) return null;
  const cause = inputs.offair
    ? "state/offair.json has offair: true"
    : `horizon is stale (now is more than ${cfg.offairAfterMs / 1000} s past the end of segment ${horizon.last})`;
  const missing =
    horizon.fallback_version === null || horizon.fallback_version === ""
      ? "horizon.fallback_version is null"
      : inputs.fallback === null
        ? `fallback/${horizon.fallback_version}/index.json is missing or unreadable`
        : `fallback/${horizon.fallback_version}/index.json has len < 1`;
  return `off-air (${cause}) but no usable fallback (${missing}): live.m3u8 not written, so players keep the last playlist`;
}

/**
 * One cron invocation: write the current playlist immediately, then rewrite it
 * at every grid boundary E + N*d until scheduledTime + loopMs. Only CPU time is
 * billed, so the waiting is free. Overlapping invocations are harmless: the
 * playlist is a pure function of the clock and the inputs.
 *
 * Epoch change: inputs are read once per invocation, so an epoch never changes
 * inside one. When state/horizon.json's epoch_id changes between invocations,
 * segment numbering restarts (N from 0 at the new epoch E) and
 * EXT-X-MEDIA-SEQUENCE drops. That is deliberate, not a defect: a new epoch is
 * an operator re-render event (transmitter re-renders and republishes under
 * seg/<new epoch_id>/), and players must reload the stream to follow it.
 */
export async function runClock(deps: ClockDeps): Promise<ClockResult> {
  await (deps.guard ?? guardStep)(deps);
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
  const inputs = await readInputs(bucket);
  const result: ClockResult = { puts: 0, skipped: 0, offairWithoutFallback: null, refused: null };
  const horizon = inputs.horizon;
  if (horizon === null) return result;
  if (horizon.d !== GRID_D) {
    result.refused = `state/horizon.json d is ${JSON.stringify(horizon.d)}, not the grid constant ${GRID_D}: live.m3u8 not written`;
    console.error(JSON.stringify({ event: "horizon-refused", reason: result.refused, d: horizon.d,
                                   epoch_id: horizon.epoch_id, scheduled: deps.scheduledTime }));
    return result;
  }
  const g = gridOf(horizon);
  const cap = putCap(config, g.dMs);
  let lastBody: string | null = null;
  const write = async (force: boolean) => {
    const nowMs = deps.now();
    const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair,
                                 offairSeqMs: deps.scheduledTime + config.loopMs }, config);
    if (body === null) {
      // Ruling: the off-air lever silently doing nothing must be loud. Once
      // per invocation, not per attempt.
      if (result.offairWithoutFallback === null) {
        const reason = offairWithoutFallback(inputs, horizon, nowMs, config);
        if (reason !== null) {
          result.offairWithoutFallback = reason;
          console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                         fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
        }
      }
      return;
    }
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
  return result;
}
