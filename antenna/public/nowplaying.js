// Pure helpers for the player (unit-tested). The player computes now-playing
// client-side: program-date-time of the playback position, looked up in
// timeline.json -- no request stream bills per listener.

/** Native HLS on Apple WebKit (Safari and every iOS browser -- all WebKit);
 * hls.js everywhere else, including Chrome whose native HLS is buggy. Detected
 * by vendor, not canPlayType alone (also true on Chrome). */
export function prefersNativeHls(nav, canPlayNative) {
  const vendor = typeof nav.vendor === "string" ? nav.vendor : "";
  return Boolean(canPlayNative) && vendor.startsWith("Apple");
}

/** Notice text for a rejected audio.play(), or null to ignore it. Only a
 * NotAllowedError while still playing is a real "blocked"; an AbortError is
 * play() being interrupted by our own stop()/offAir() and must not overwrite
 * the off-air notice. */
export function playBlockedNotice(err, stillPlaying) {
  if (!stillPlaying || !err || err.name !== "NotAllowedError") return null;
  return "Playback was blocked; press Try again.";
}

/** Notice text for an hls.js ERROR event, or null to let hls.js recover. A
 * 403 is the kill switch; levelEmptyError is the clock's ENDLIST-only
 * playlist (off-air with no notice), which hls.js reports as a non-fatal
 * error rather than a LEVEL_LOADED it would otherwise keep reloading. */
export function hlsErrorNotice(data) {
  const code = (data && data.response && data.response.code) ||
    (data && data.networkDetails && data.networkDetails.status);
  if (code === 403 || (data && data.details === "levelEmptyError")) return "The station is off the air.";
  if (data && data.fatal) return "The stream is unavailable right now.";
  return null;
}

/** Timeline contract: shows[].files[] are sorted by start (the writer emits
 * them in play order); the early `break` below relies on it. */
export function findNowPlaying(timeline, atMs) {
  if (!timeline || !Array.isArray(timeline.shows)) return null;
  for (const show of timeline.shows) {
    if (atMs >= Date.parse(show.start) && atMs < Date.parse(show.end)) {
      let file = null;
      for (const f of show.files || []) {
        if (Date.parse(f.start) <= atMs) file = f;
        else break;
      }
      return { show, file };
    }
  }
  return null;
}

export function nowPlayingText(np, timelineLoaded, stationName = "llama radio") {
  if (!np) return timelineLoaded ? stationName : "Tuning in…";
  const s = np.show;
  const where = [s.venue, s.city].filter(Boolean).join(", ");
  const head = [s.artist, [s.date, where].filter(Boolean).join(", ")].filter(Boolean).join(" — ");
  return np.file ? `${head} · ${np.file.title}` : head;
}

/** A probe of live.m3u8 made while playback is stalled. "offair" is
 * definitive: the WAF kill switch answers 403, and the clock's off-air
 * playlist ends with #EXT-X-ENDLIST. Anything else -- a network error
 * (status 0), a 5xx, a 429, a live playlist -- is not a reason to stop. */
export function classifyProbe(status, body) {
  if (status === 403) return "offair";
  if (status === 200 && typeof body === "string" && body.includes("#EXT-X-ENDLIST")) return "offair";
  return "unknown";
}

/** Notices playback that stopped advancing without trusting the player's
 * error events (an already-playing page went silent on the kill switch:
 * phase-1 verification, 2026-10-11). Fed the playback position about once a
 * second while playing. After stallMs without progress it asks for a probe
 * (at most one every probeEveryMs, one at a time); `verdictsNeeded`
 * consecutive "offair" verdicts stop the player. Any progress resets it, so a
 * network blip that recovers never shows the off-air notice. */
export class StallWatch {
  constructor({ stallMs = 15000, probeEveryMs = 10000, verdictsNeeded = 2 } = {}) {
    this.stallMs = stallMs;
    this.probeEveryMs = probeEveryMs;
    this.verdictsNeeded = verdictsNeeded;
    this.reset(0);
  }

  reset(nowMs) {
    this.lastPos = null;
    this.lastProgressMs = nowMs;
    this.lastProbeMs = null;
    this.probing = false;
    this.offairCount = 0;
  }

  /** True when the caller should probe now. */
  tick(positionS, nowMs) {
    if (this.lastPos === null || positionS > this.lastPos + 0.05) {
      this.lastPos = positionS;
      this.lastProgressMs = nowMs;
      this.offairCount = 0;
      return false;
    }
    if (!this.stalled(nowMs) || this.probing) return false;
    if (this.lastProbeMs !== null && nowMs - this.lastProbeMs < this.probeEveryMs) return false;
    this.lastProbeMs = nowMs;
    this.probing = true;
    return true;
  }

  /** Feed a classifyProbe verdict; true when the player should go off-air. */
  verdict(v) {
    this.probing = false;
    this.offairCount = v === "offair" ? this.offairCount + 1 : 0;
    return this.offairCount >= this.verdictsNeeded;
  }

  stalled(nowMs) {
    return nowMs - this.lastProgressMs >= this.stallMs;
  }
}
