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
  const code = data && data.response && data.response.code;
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

export function nowPlayingText(np, timelineLoaded) {
  if (!np) return timelineLoaded ? "We'll be back shortly." : "Tuning in…";
  const s = np.show;
  const where = [s.venue, s.city].filter(Boolean).join(", ");
  const head = [s.artist, [s.date, where].filter(Boolean).join(", ")].filter(Boolean).join(" — ");
  return np.file ? `${head} · ${np.file.title}` : head;
}
