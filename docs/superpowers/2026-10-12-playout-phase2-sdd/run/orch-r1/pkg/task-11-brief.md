### Task 11: Player — kill switch detected mid-play

**Model hint:** sonnet

**Files:**
- Modify: `antenna/public/nowplaying.js`, `antenna/public/player.js` (replace both whole files), `antenna/test/nowplaying.test.ts` (import line + appended tests)

**Interfaces:**
- Consumes: the phase-1 player.
- Produces:
  - `nowplaying.js`: `hlsErrorNotice` also reads `data.networkDetails.status`;
  - `classifyProbe(status, body) -> "offair" | "unknown"`;
  - `class StallWatch({ stallMs = 15000, probeEveryMs = 10000, verdictsNeeded = 2 })` with `reset(nowMs)`, `tick(positionS, nowMs) -> boolean` (probe now?), `verdict(v) -> boolean` (go off-air?) and `stalled(nowMs)`.

Amendment A2. The probe is `fetch("live.m3u8", { cache: "no-store" })`. It is answered at the edge: a cache hit (the `Cache-Control: no-cache` that `no-store` adds does not bypass the edge cache, measured 2026-10-12; the edge refetches `live.m3u8` from R2 at most every 5 s, whoever asks), or the WAF's 403 while blocked. It is never billed per request, and at most one runs per 10 s per stalled listener. `index.html` is unchanged, so `src/pages.ts` stays fresh.

- [ ] **Step 1: Write the failing tests**

In `antenna/test/nowplaying.test.ts`, change the import to:

```ts
import { classifyProbe, findNowPlaying, hlsErrorNotice, playBlockedNotice, nowPlayingText, prefersNativeHls,
         StallWatch } from "../public/nowplaying.js";
```

and append:

```ts
describe("hlsErrorNotice: the 403 can arrive on networkDetails", () => {
  it("treats networkDetails.status 403 as off-air", () => {
    expect(hlsErrorNotice({ fatal: false, networkDetails: { status: 403 } })).toBe("The station is off the air.");
  });
});

describe("classifyProbe", () => {
  it("only a 403 or an ENDLIST playlist is off-air", () => {
    expect(classifyProbe(403, "")).toBe("offair");
    expect(classifyProbe(200, "#EXTM3U\n#EXT-X-ENDLIST\n")).toBe("offair");
    for (const [s, b] of [[0, ""], [200, "#EXTM3U\nseg/e1/1.aac\n"], [503, ""], [429, ""], [404, ""]] as const) {
      expect(classifyProbe(s, b)).toBe("unknown");
    }
  });
});

describe("StallWatch", () => {
  const playFor = (w: StallWatch, fromS: number, fromMs: number, seconds: number) => {
    for (let i = 0; i <= seconds; i++) expect(w.tick(fromS + i, fromMs + i * 1000)).toBe(false);
  };

  it("never probes while playback advances", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 120);
  });

  it("probes after 15 s without progress, at most every 10 s, one at a time", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10); // position 10 at t=10 s
    const probes: number[] = [];
    for (let t = 11_000; t <= 60_000; t += 1000) {
      if (w.tick(10, t)) {
        probes.push(t);
        expect(w.tick(10, t + 500)).toBe(false); // still probing
        w.verdict("unknown");
      }
    }
    expect(probes).toEqual([25_000, 35_000, 45_000, 55_000]);
  });

  it("goes off-air on two consecutive off-air verdicts (the kill switch mid-play)", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10);
    expect(w.tick(10, 25_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false);
    expect(w.tick(10, 35_000)).toBe(true);
    expect(w.verdict("offair")).toBe(true);
  });

  it("a blip: network errors while stalled, then progress resumes -- never off-air", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10);
    expect(w.tick(10, 25_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false); // one stray 403 is not enough...
    expect(w.tick(10, 35_000)).toBe(true);
    expect(w.verdict("unknown")).toBe(false); // ...and a non-verdict resets the count
    expect(w.tick(10, 45_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false);
    expect(w.tick(11, 46_000)).toBe(false); // playing again
    expect(w.stalled(47_000)).toBe(false);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/nowplaying.test.ts`
Expected: FAIL. `classifyProbe`/`StallWatch` are not exported.

- [ ] **Step 3: Implement**

Replace `antenna/public/nowplaying.js` with:

```js
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
  const code = (data && data.response && data.response.code) || (data && data.networkDetails && data.networkDetails.status);
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
```

Replace `antenna/public/player.js` with:

```js
import { classifyProbe, findNowPlaying, hlsErrorNotice, nowPlayingText, playBlockedNotice, prefersNativeHls,
         StallWatch } from "./nowplaying.js";

const STREAM = "live.m3u8";
const TIMELINE = "timeline.json";
const TIMELINE_REFRESH_MS = 3 * 60 * 1000;

const audio = document.getElementById("audio");
const playButton = document.getElementById("play");
const nowPlaying = document.getElementById("now-playing");
const notice = document.getElementById("notice");
const noticeText = document.getElementById("notice-text");
const retryButton = document.getElementById("retry");
document.getElementById("stream-url").textContent = new URL(STREAM, location.href).href;

let hls = null;
let playing = false;
let timeline = null;
let timelineFetchedAt = 0;
const watch = new StallWatch();

const useNative = () => prefersNativeHls(navigator, audio.canPlayType("application/vnd.apple.mpegurl") !== "");

function showNotice(text) {
  noticeText.textContent = text;
  notice.hidden = false;
}

function stop() {
  playing = false;
  if (hls) {
    hls.destroy();
    hls = null;
  }
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  playButton.textContent = "Play";
}

// Off-air (ENDLIST) or blocked (403): stop, show the notice, never auto-reconnect.
function offAir(text) {
  stop();
  showNotice(text);
  nowPlaying.textContent = "";
}

// Radio semantics: every start joins the live edge (pause = stop).
function start() {
  stop();
  notice.hidden = true;
  playing = true;
  watch.reset(Date.now());
  playButton.textContent = "Stop";
  if (useNative()) {
    audio.src = STREAM;
  } else if (window.Hls && window.Hls.isSupported()) {
    hls = new window.Hls({ liveSyncDurationCount: 3 });
    hls.on(window.Hls.Events.LEVEL_LOADED, (_event, data) => {
      if (data.details && data.details.live === false) offAir("The station is off the air.");
    });
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      const text = hlsErrorNotice(data);
      if (text) offAir(text);
    });
    hls.loadSource(STREAM);
    hls.attachMedia(audio);
  } else {
    offAir("This browser cannot play the stream here; open the stream URL in VLC.");
    return;
  }
  audio.play().catch((err) => {
    const text = playBlockedNotice(err, playing);
    if (text) offAir(text);
  });
  refreshTimeline(true);
}

audio.addEventListener("ended", () => offAir("The station is off the air."));
audio.addEventListener("error", () => {
  if (playing) offAir("The stream is unavailable right now.");
});
// Pause from OS/lock-screen controls: treat as stop (stop() sets playing=false
// before its own pause, so this cannot recurse).
// A natural end fires pause then ended with audio.ended already true; stop()'s
// load() would cancel that pending ended event and swallow the off-air notice.
audio.addEventListener("pause", () => {
  if (playing && !audio.ended) stop();
});
playButton.addEventListener("click", () => (playing ? stop() : start()));
retryButton.addEventListener("click", start);

function playbackDateMs() {
  if (hls && hls.playingDate) return hls.playingDate.getTime();
  if (typeof audio.getStartDate === "function") {
    const startMs = audio.getStartDate().getTime();
    if (Number.isFinite(startMs)) return startMs + audio.currentTime * 1000;
  }
  return null;
}

// Fetched only while playing, at most every few minutes, never while hidden.
async function refreshTimeline(force) {
  if (!playing || document.hidden) return;
  if (!force && Date.now() - timelineFetchedAt < TIMELINE_REFRESH_MS) return;
  timelineFetchedAt = Date.now();
  try {
    const res = await fetch(TIMELINE);
    if (res.ok) timeline = await res.json();
  } catch {
    // keep the last timeline
  }
}

// Stalled playback: ask live.m3u8 directly whether the station is off the air.
// The answer is a cache hit (the edge refetches live.m3u8 from R2 at most every
// 5 s, whoever asks) or the kill switch's 403: never billed per request.
async function probe() {
  let status = 0;
  let body = "";
  try {
    const res = await fetch(STREAM, { cache: "no-store" });
    status = res.status;
    if (res.ok) body = await res.text();
  } catch {
    // a network error is not a verdict
  }
  if (!playing) return;
  if (watch.verdict(classifyProbe(status, body))) offAir("The station is off the air.");
}

// All timeline-derived text goes to the DOM via textContent only.
setInterval(() => {
  if (!playing) return;
  const now = Date.now();
  if (watch.tick(audio.currentTime, now)) probe();
  refreshTimeline(false);
  if (watch.stalled(now)) {
    nowPlaying.textContent = "Reconnecting…";
    return;
  }
  const at = playbackDateMs();
  if (at !== null) nowPlaying.textContent = nowPlayingText(findNowPlaying(timeline, at), timeline !== null);
}, 1000);
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/public/nowplaying.js antenna/public/player.js antenna/test/nowplaying.test.ts
git commit -m "feat(antenna): an already-playing page notices the kill switch (stall watch + probe), ignoring blips"
```

---
