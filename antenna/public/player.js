import { findNowPlaying, nowPlayingText, playBlockedNotice, prefersNativeHls } from "./nowplaying.js";

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
  playButton.textContent = "Stop";
  if (useNative()) {
    audio.src = STREAM;
  } else if (window.Hls && window.Hls.isSupported()) {
    hls = new window.Hls({ liveSyncDurationCount: 3 });
    hls.on(window.Hls.Events.LEVEL_LOADED, (_event, data) => {
      if (data.details && data.details.live === false) offAir("The station is off the air.");
    });
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      const code = data.response && data.response.code;
      if (code === 403) offAir("The station is off the air.");
      else if (data.fatal) offAir("The stream is unavailable right now.");
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
audio.addEventListener("pause", () => {
  if (playing) stop();
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

// All timeline-derived text goes to the DOM via textContent only.
setInterval(() => {
  if (!playing) return;
  refreshTimeline(false);
  const at = playbackDateMs();
  if (at !== null) nowPlaying.textContent = nowPlayingText(findNowPlaying(timeline, at), timeline !== null);
}, 1000);
