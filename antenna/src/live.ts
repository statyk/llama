/** The one implementation of a live.m3u8 write, shared by the cron loop
 * (clock.ts) and the metronome (metronome-engine.ts): build the body, detect
 * off-air without a usable fallback, and PUT it with its headers. What each
 * writer adds around it (its PUT cap, its identical-bytes memory, its timing)
 * stays with that writer. */

import type { BucketLike } from "./bucket";
import type { Horizon } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export const LIVE_KEY = "live.m3u8";

/** What a playlist is built from: the horizon, its fallback index, and the
 * blocked verdict (true = the off-air playlist). */
export interface LiveSource {
  horizon: Horizon;
  fallback: FallbackIndex | null;
  offair: boolean;
}

/** Why off-air is in force at nowMs and no usable fallback exists, or null. */
export function offairWithoutFallback(src: LiveSource, nowMs: number, cfg: PlaylistConfig): string | null {
  const inp = { nowMs, horizon: src.horizon, fallback: src.fallback, offair: src.offair };
  if (!isOffair(inp, cfg) || usableFallback(inp) !== null) return null;
  const h = src.horizon;
  const cause = src.offair
    ? "the station is blocked (tripped or state/offair.json)"
    : `horizon is stale (now is more than ${cfg.offairAfterMs / 1000} s past the end of segment ${h.last})`;
  const missing =
    h.fallback_version === null || h.fallback_version === ""
      ? "horizon.fallback_version is null"
      : src.fallback === null
        ? `fallback/${h.fallback_version}/index.json is missing or unreadable`
        : `fallback/${h.fallback_version}/index.json has len < 1`;
  return `off-air (${cause}) but no usable fallback (${missing}): live.m3u8 written as an ENDLIST-only playlist (no notice), so players stop`;
}

/** The body to write at nowMs (null = write nothing: before the epoch, or no
 * usable fallback for a loop entry), with the off-air-without-fallback reason
 * when that applies. offairSeqMs numbers the off-air notice
 * (playlist.offairSequence). */
export function renderLive(src: LiveSource, nowMs: number, offairSeqMs: number,
                           cfg: PlaylistConfig): { body: string | null; offairWithoutFallback: string | null } {
  return {
    body: buildPlaylist({ nowMs, horizon: src.horizon, fallback: src.fallback, offair: src.offair, offairSeqMs }, cfg),
    offairWithoutFallback: offairWithoutFallback(src, nowMs, cfg),
  };
}

/** PUT live.m3u8 with its content type and max-age (at least 1 s). */
export async function putLive(bucket: BucketLike, body: string, liveMaxAge: number): Promise<void> {
  await bucket.put(LIVE_KEY, body, {
    httpMetadata: { contentType: "application/vnd.apple.mpegurl",
                    cacheControl: `public, max-age=${Math.max(1, Math.floor(liveMaxAge))}` },
  });
}
