// The player: the audio element, hls.js, dropout recovery and the Media
// Session. Decisions come from recovery.js; station text comes from page.js;
// iPhone measurements: docs/superpowers/2026-11-01-player-probe.md.
import { ARTWORK, sessionText } from "./media.js";
import { currentTimeline, refreshTimeline, setState } from "./page.js";
import { classifyProbe, immediateOffair, pauseMeansStop, playBlockedNotice, prefersNativeHls,
         Recovery } from "./recovery.js";
import { STATION_NAME, findShow, positionMs } from "./timeline.js";

const STREAM = "/live.m3u8";
const PROBE_LIMIT_MS = 8000;
// Long enough for a pause queued by a teardown to arrive, if load() didn't
// cancel it; a teardown's pause must never read as the phone's Stop.
const TEARDOWN_SETTLE_MS = 500;

const audio = document.getElementById("audio");
const hubs = document.getElementById("hubs");
const native = prefersNativeHls(navigator, audio.canPlayType("application/vnd.apple.mpegurl") !== "");
const recovery = new Recovery({ native });

let hls = null;
let wanted = false; // the listener wants audio: from start until a stop of any kind
let state = "stopped";
let session = 0; // bumped by every rejoin and stop: a fetch from before it is dropped
let asking = null; // the session whose Play is waiting on its fetch
let selfTeardown = false;
let settleTimer = null;
let shownText = null; // the Media Session text last set, as JSON

function show(name) {
  state = name;
  setState(name);
}

/** Leaves the element empty. With audio wanted, only after an HTTP answer (a
 * `restart` result, or Play's question): a teardown while unreachable ends the
 * audio session and iOS freezes the page. A stop may always call it. */
function tearDown() {
  selfTeardown = true;
  clearTimeout(settleTimer);
  if (hls) {
    hls.destroy();
    hls = null;
  }
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  settleTimer = setTimeout(() => { selfTeardown = false; }, TEARDOWN_SETTLE_MS);
}

/** Ends the session in `name`, a state with no audio. */
function halt(name) {
  wanted = false;
  session += 1;
  tearDown();
  hubs.classList.remove("turning");
  show(name);
  syncMedia(Date.now());
}

/** Radio semantics: every attach joins the live edge. False when the browser
 * can't play the stream. */
function attach() {
  if (native) {
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
      if (data.details && data.details.live === false) halt("offair");
    });
    // Any other fatal error waits for Recovery: buffered audio may still be playing.
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      if (immediateOffair(data)) halt("offair");
    });
    hls.loadSource(STREAM);
    hls.attachMedia(audio);
  } else {
    return false;
  }
  const started = session;
  audio.play().catch((err) => {
    if (playBlockedNotice(err, wanted && started === session)) halt("refused");
    // any other rejection is left to the stall path
  });
  return true;
}

function rejoin() {
  wanted = true;
  session += 1;
  recovery.begin(Date.now());
  tearDown();
  hubs.classList.remove("turning");
  show("playing");
  if (attach()) syncMedia(Date.now());
  else halt("unsupported");
}

/** Play. During a session it waits for an HTTP answer, off-air included: with
 * none, the element is left alone and audio or recovery carry on. */
async function start() {
  if (!wanted) {
    rejoin();
    return;
  }
  if (asking === session) return;
  const asked = session;
  asking = asked;
  const answer = await ask();
  if (asked !== session) return;
  asking = null;
  if (answer !== "unreachable") rejoin();
}

function stop() {
  if (wanted) halt("stopped"); // otherwise a notice stays up
}

/** A question to live.m3u8: "offair", "reachable" or "unreachable". A cache
 * hit, or the kill switch's 403: never billed per request. */
async function ask() {
  const controller = new AbortController();
  const limit = setTimeout(() => controller.abort(), PROBE_LIMIT_MS);
  let answer;
  try {
    const res = await fetch(STREAM, { cache: "no-store", signal: controller.signal });
    const body = res.ok ? await res.text() : "";
    answer = classifyProbe(res.status, body) === "offair" ? "offair" : "reachable";
  } catch {
    answer = "unreachable";
  }
  clearTimeout(limit);
  return answer;
}

/** The stalled stream's question. Every outcome gets an answer, so a probe
 * failing just after the network returns only waits for the next one. */
async function probe() {
  const asked = session;
  const answer = await ask();
  if (asked !== session) return;
  if (recovery.verdict(answer)) halt("offair");
  else step(Date.now()); // a restart must follow a fresh answer
}

function restart(nowMs) {
  if (!recovery.mayPlay(nowMs)) {
    halt("gaveup");
    return;
  }
  tearDown();
  attach();
  recovery.restarted(nowMs);
}

/** One recovery decision, acted on. Only while `wanted`: never after a stop. */
function step(nowMs) {
  const result = recovery.tick(audio.currentTime, nowMs);
  if (result === "giveup") {
    halt("gaveup");
    return;
  }
  if (result === "probe" || result === "restart") {
    if (state !== "reconnecting") show("reconnecting");
    if (result === "probe") probe();
    else restart(nowMs);
  }
  if (!wanted) return;
  if (recovery.advancing && state !== "playing") show("playing");
  hubs.classList.toggle("turning", recovery.advancing);
}

function playbackMs() {
  let ms = NaN;
  if (hls && hls.playingDate) ms = hls.playingDate.getTime();
  else if (typeof audio.getStartDate === "function") ms = audio.getStartDate().getTime() + audio.currentTime * 1000;
  return Number.isFinite(ms) ? ms : null;
}

function syncMedia(nowMs) {
  if (!("mediaSession" in navigator)) return;
  const audible = player.audible;
  const atMs = positionMs({ playing: audible, playbackMs: playbackMs(), nowMs });
  const text = sessionText({ np: findShow(currentTimeline(), atMs), stationName: STATION_NAME, audible });
  const json = JSON.stringify(text);
  if (json !== shownText) {
    shownText = json;
    navigator.mediaSession.metadata = new MediaMetadata({ ...text, artwork: ARTWORK });
  }
  navigator.mediaSession.playbackState = wanted ? "playing" : "paused";
}

export const player = {
  start,
  stop,
  tick(nowMs) {
    if (wanted) step(nowMs);
    syncMedia(nowMs);
  },
  get audible() {
    return wanted && recovery.advancing;
  },
  playbackMs,
};

audio.addEventListener("error", () => {
  if (wanted) recovery.failed(Date.now());
});
audio.addEventListener("ended", () => {
  if (wanted) halt("offair");
});
audio.addEventListener("waiting", () => {
  if (wanted) recovery.noteWaiting();
});
// `stalled` is deliberately not handled: a healthy iPhone fires it every 11 s.
audio.addEventListener("pause", () => {
  if (wanted && pauseMeansStop({ selfTeardown, stalled: recovery.stalled, ended: audio.ended })) stop();
});

if ("mediaSession" in navigator) {
  const handlers = {
    // start first: refreshTimeline stays gated while stopped and hidden.
    play() {
      start();
      refreshTimeline(true);
    },
    pause: stop, // from a car this is a normal Stop
    stop,
  };
  for (const [action, handler] of Object.entries(handlers)) {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch {
      // an older WebKit without this action
    }
  }
}
