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
let session = 0; // bumped per start(): a probe from an earlier Play must not feed this one
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
  ++session;
  watch.reset(Date.now());
  playButton.textContent = "Stop";
  if (useNative()) {
    audio.src = STREAM;
  } else if (window.Hls && window.Hls.isSupported()) {
    // Amendment A4 (amended 2026-10-12); option semantics checked against the
    // vendored hls.js 1.7.3. hls.js joins at the playlist's #EXT-X-START
    // (12 segments before the listed end, at the wall clock). No liveSyncDuration:
    // hls.js 1.7.3 takes its target latency from the playlist's own
    // #EXT-X-SERVER-CONTROL HOLD-BACK (without the tag it falls back to the
    // default count of 3), so the playlist is the one source of truth.
    // maxBufferLength must exceed the hold-back (PLAYLIST_HOLD_BACK * 10.24 s
    // = 122.88 s) so the whole runway can fill (default 30 s;
    // maxMaxBufferLength, default 600, caps it). A finite
    // backBufferLength (default Infinity) keeps a long listen from filling the
    // SourceBuffer, whose quota error makes hls.js shrink its buffer target.
    hls = new window.Hls({ maxBufferLength: 130, backBufferLength: 30 });
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
  const gen = session;
  let status = 0;
  let body = "";
  try {
    // AbortSignal.timeout is missing on older WebKit (iOS 15): without it the probe still runs, unbounded
    const signal = typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
      ? AbortSignal.timeout(8000) : undefined;
    const res = await fetch(STREAM, { cache: "no-store", ...(signal ? { signal } : {}) });
    status = res.status;
    if (gen !== session) return;
    if (res.ok) body = await res.text();
  } catch {
    // a network error or timeout is not a verdict
  }
  if (!playing || gen !== session) return;
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
  if (at !== null) nowPlaying.textContent = nowPlayingText(findNowPlaying(timeline, at), timeline !== null, document.title);
}, 1000);
