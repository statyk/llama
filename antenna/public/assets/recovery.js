// Pure dropout decisions for the player (unit-tested, no DOM). Shares nothing
// with the frozen root files: prefersNativeHls and classifyProbe are copies of
// nowplaying.js's. Measurements behind the rules:
// docs/superpowers/2026-11-01-player-probe.md.

/** Native HLS on Apple WebKit (Safari and every iOS browser -- all WebKit);
 * hls.js everywhere else, including Chrome whose native HLS is buggy. Detected
 * by vendor, not canPlayType alone (also true on Chrome). */
export function prefersNativeHls(nav, canPlayNative) {
  const vendor = typeof nav.vendor === "string" ? nav.vendor : "";
  return Boolean(canPlayNative) && vendor.startsWith("Apple");
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

/** Notice text for a rejected audio.play(), or null to ignore it. Only a
 * NotAllowedError while still playing is a real "blocked"; an AbortError is
 * play() being interrupted by our own stop()/offAir() and must not overwrite
 * the off-air notice. */
export function playBlockedNotice(err, stillPlaying) {
  if (!stillPlaying || !err || err.name !== "NotAllowedError") return null;
  return "Playback was blocked.";
}

/** True for an hls.js ERROR event that is off-air on its own: a 403 is the
 * kill switch; levelEmptyError is the clock's ENDLIST-only playlist. */
export function immediateOffair(data) {
  const code = (data && data.response && data.response.code) ||
    (data && data.networkDetails && data.networkDetails.status);
  return code === 403 || Boolean(data && data.details === "levelEmptyError");
}

/** A `pause` is the phone's Stop only with no stall under way (a Bluetooth
 * disconnect is a plain pause; a dropout never pauses) and not our own doing. */
export function pauseMeansStop({ selfTeardown, stalled, ended }) {
  return !selfTeardown && !stalled && !ended;
}

/** Decides what to do about a stream that stopped moving. Fed the position
 * about once a second; only an advancing position counts as audio, never
 * `playing` or a resolved play(), which an iPhone gave with the position
 * frozen. The element is left alone until a probe gets an HTTP response: a
 * teardown while offline ends the audio session and iOS freezes the page.
 *
 * A failure starts the delay. When it runs out, tick asks for a probe, and
 * again every probeEveryMs until a `reachable` answer allows the restart. An
 * `unreachable` answer changes nothing but when the next probe goes, so after
 * a long outage the delay has long run out and the first reachable answer
 * restarts at once. */
export class Recovery {
  constructor({ native, stallMs = 15000, nativeStallMs = 30000, joinMs = 25000, minDelayMs = 5000,
                maxDelayMs = 30000, resetAfterMs = 60000, giveUpMs = 600000, probeEveryMs = 15000,
                verdictFreshMs = 10000, advanceSlackS = 2, verdictsNeeded = 2, random = Math.random }) {
    this.failAfterMs = native ? nativeStallMs : stallMs;
    this.joinMs = joinMs;
    this.minDelayMs = minDelayMs;
    this.maxDelayMs = maxDelayMs;
    this.resetAfterMs = resetAfterMs;
    this.giveUpMs = giveUpMs;
    this.probeEveryMs = probeEveryMs;
    this.verdictFreshMs = verdictFreshMs;
    this.advanceSlackS = advanceSlackS;
    this.verdictsNeeded = verdictsNeeded;
    this.random = random;
    this.begin(0);
  }

  /** The listener pressed Play. */
  begin(nowMs) {
    this.nowMs = nowMs; // latest time seen; a verdict arrives without one
    this.lastAudioMs = nowMs;
    this.restarts = 0;
    this.offairCount = 0;
    this.probing = false;
    this.lastProbeMs = null;
    this.clearAttempt();
    this.clearSamples();
  }

  /** One position sample. Samples first, so an advance after a frozen gap is
   * audio, then the give-up check, which beats anything pending. */
  tick(positionS, nowMs) {
    this.nowMs = nowMs;
    this.sample(positionS, nowMs);
    if (!this.mayPlay(nowMs)) return "giveup";
    if (this.restartAsked) return "none";
    if (this.retryAtMs === null && this.positionFailed(nowMs)) this.fail(nowMs);
    if (this.retryAtMs === null || nowMs < this.retryAtMs) return "none";
    if (this.reachableMs !== null && nowMs - this.reachableMs < this.verdictFreshMs) {
      this.restartAsked = true;
      return "restart";
    }
    if (this.probing) return "none";
    if (this.lastProbeMs !== null && nowMs - this.lastProbeMs < this.probeEveryMs) return "none";
    this.probing = true;
    this.lastProbeMs = nowMs;
    return "probe";
  }

  /** A native `error` event: the failure counts at once. The position rose
   * up to the error, so the next sample is a baseline, or that rise would read
   * as an advance and cancel the failure. An element still playing gets
   * cancelled by the sample after it. */
  failed(nowMs) {
    this.nowMs = nowMs;
    if (this.retryAtMs !== null || (this.joinUntilMs !== null && nowMs < this.joinUntilMs)) return;
    this.lastPos = null;
    this.fail(nowMs);
  }

  /** A `waiting` event. Never `stalled`: a healthy iPhone fires it every 11 s. */
  noteWaiting() {
    this.waiting = true;
  }

  /** "offair", or "reachable" for an HTTP response that isn't off-air, or
   * "unreachable" for a rejected or timed-out fetch. True means go off-air. A
   * verdict's age counts from the latest tick, so it can only read older than
   * it is. */
  verdict(v) {
    this.probing = false;
    if (v === "reachable") this.reachableMs = this.nowMs;
    if (v !== "offair") return false;
    this.offairCount += 1;
    return this.offairCount >= this.verdictsNeeded;
  }

  /** A restart was just performed. The first position after it, higher or
   * lower, is a baseline. The delay and the verdict count carry on. */
  restarted(nowMs) {
    this.nowMs = nowMs;
    this.restarts += 1;
    this.clearAttempt();
    this.clearSamples();
    this.joinUntilMs = nowMs + this.joinMs;
  }

  /** The wall-clock check before any play(). */
  mayPlay(nowMs) {
    return nowMs - this.lastAudioMs < this.giveUpMs;
  }

  /** The last sample didn't advance, or a `waiting` came since the last advance. */
  get stalled() {
    return this.frozen || this.waiting;
  }

  /** The last sample was a real advance. */
  get advancing() {
    return this.advanced;
  }

  clearAttempt() {
    this.retryAtMs = null;
    this.reachableMs = null;
    this.joinUntilMs = null;
    this.restartAsked = false;
  }

  clearSamples() {
    this.lastPos = null;
    this.lastSampleMs = null;
    this.advanced = false;
    this.frozen = false;
    this.waiting = false;
    this.runStartMs = null;
  }

  sample(positionS, nowMs) {
    const baseline = this.lastPos === null;
    const rise = baseline ? 0 : positionS - this.lastPos;
    const jump = rise > (nowMs - this.lastSampleMs) / 1000 + this.advanceSlackS;
    this.lastPos = positionS;
    this.lastSampleMs = nowMs;
    if (baseline || jump) {
      this.advanced = false;
      this.frozen = false;
      this.runStartMs = null;
    } else if (rise > 0) {
      this.advance(nowMs);
    } else {
      this.advanced = false;
      this.frozen = true;
      this.runStartMs = null;
    }
  }

  advance(nowMs) {
    this.advanced = true;
    this.frozen = false;
    this.waiting = false;
    this.lastAudioMs = nowMs;
    this.offairCount = 0;
    this.clearAttempt();
    if (this.runStartMs === null) this.runStartMs = nowMs;
    if (nowMs - this.runStartMs >= this.resetAfterMs) this.restarts = 0;
  }

  positionFailed(nowMs) {
    if (this.joinUntilMs !== null) return nowMs >= this.joinUntilMs;
    return nowMs - this.lastAudioMs >= this.failAfterMs;
  }

  fail(nowMs) {
    const delayMs = Math.min(this.minDelayMs * 2 ** this.restarts, this.maxDelayMs);
    this.retryAtMs = nowMs + delayMs * (0.8 + 0.4 * this.random());
  }
}
