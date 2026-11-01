// The early iPhone test (spec "Unverified"): plain <audio>, native HLS, iPhone only.
// Throwaway. Everything the operator learns comes from the log, so a test that isn't
// answered by a log line isn't answered: the tick lines below carry all the state.
"use strict";

const STREAM = "/live.m3u8";
const TICK_MS = 5000;
const RETRY_MS = 30000;
const LATE_GAP_S = 7.5; // a tick this late means the timer did not run on time
const STALL_LOSS_S = 2; // played this far less than the wall clock moved: a stall
const LOG_KEY = "probe-log";
const MAX_LINES = 6000; // over 3 hours of two tick lines per 5 s, under 1 MB
const SHOWN_LINES = 200;

const $ = (id) => document.getElementById(id);
const audio = $("audio");

// --- The log. Saved on every line: the page may be killed at any moment.

const lines = (() => {
  try {
    const saved = localStorage.getItem(LOG_KEY);
    return saved ? saved.split("\n") : [];
  } catch {
    return [];
  }
})();
let saveFailed = false;

function clock() {
  const now = new Date();
  return `${now.toTimeString().slice(0, 8)}.${String(now.getMilliseconds()).padStart(3, "0")}`;
}

function log(text) {
  lines.push(`${clock()} ${text}`);
  if (lines.length > MAX_LINES) lines.splice(0, lines.length - MAX_LINES);
  try {
    localStorage.setItem(LOG_KEY, lines.join("\n"));
  } catch (err) {
    if (!saveFailed) lines.push(`${clock()} LOG NOT SAVED: ${err.name}: ${err.message}`);
    saveFailed = true;
  }
  $("log").textContent = lines.slice(-SHOWN_LINES).reverse().join("\n"); // newest first
}

// --- State that goes on every line.

let wanted = false; // the page means to be playing, whatever the element says
let movedCt = 0; // highest currentTime since the last restart
let movedAt = Date.now(); // when it last went up

function bufferAhead() {
  const { buffered, currentTime } = audio;
  return buffered.length ? (buffered.end(buffered.length - 1) - currentTime).toFixed(1) : "none";
}

function state() {
  return `ct=${audio.currentTime.toFixed(2)} buf=${bufferAhead()} paused=${audio.paused} `
    + `rs=${audio.readyState} ns=${audio.networkState} `
    + `net=${navigator.onLine ? "on" : "off"} vis=${document.visibilityState}`;
}

// How long currentTime has stood still while the page wants audio. Survives the
// retry loop's restarts, so it reads the whole dropout.
function stuckSeconds(now) {
  if (audio.currentTime > movedCt) {
    movedCt = audio.currentTime;
    movedAt = now;
  }
  return wanted ? Math.round((now - movedAt) / 1000) : 0;
}

// --- Media Session. The title shows what last updated it and when, so the lock
// screen and the car answer "which source is still running" by eye.

let metaCount = 0;

function setMeta(source) {
  const title = `#${++metaCount} ${source} ${new Date().toTimeString().slice(0, 8)}`;
  if ("mediaSession" in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title,
      artist: "artist field",
      album: "album field",
    });
  }
  return title;
}

// One line per tick of one source, with the gap since its last tick. Flags come
// first, to be seen on a phone: LATE, the timer slept; STALL, audio didn't advance.
function makeTick(source) {
  let count = 0;
  let lastAt = null;
  let lastCt = 0;
  let lastWanted = false;
  return () => {
    const now = Date.now();
    const ct = audio.currentTime;
    const stuck = stuckSeconds(now);
    const gap = lastAt === null ? 0 : (now - lastAt) / 1000;
    const played = ct - lastCt;
    const late = gap > LATE_GAP_S ? " LATE" : "";
    const stall = wanted && lastWanted && played >= 0 && played < gap - STALL_LOSS_S ? " STALL" : "";
    lastAt = now;
    lastCt = ct;
    lastWanted = wanted;
    // Not while stopped or paused: a real player wouldn't, and tests 5 and 6 ask
    // what survives that state.
    const title = wanted ? setMeta(source) : "(not updated)";
    log(`tick ${source} n=${++count}${late}${stall} gap=${gap.toFixed(2)}s `
      + `played=${played.toFixed(2)}s stuck=${stuck}s ${state()} title="${title}"`);
  };
}

setInterval(makeTick("interval"), TICK_MS);

const timeupdateTick = makeTick("timeupdate");
let lastTimeupdate = 0;
audio.addEventListener("timeupdate", () => {
  if (Date.now() - lastTimeupdate < TICK_MS) return;
  lastTimeupdate = Date.now();
  timeupdateTick();
});

// --- Playback.

function begin(label) {
  if (!wanted) movedAt = Date.now();
  wanted = true;
  movedCt = 0;
  audio.src = STREAM;
  const result = audio.play();
  log(`${label}: play() called`);
  result.then(
    () => log(`${label}: play() resolved ${state()}`),
    (err) => log(`${label}: play() REJECTED ${err.name}: ${err.message} ${state()}`),
  );
}

// As player.js does.
function teardown() {
  log("teardown");
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}

function restart(label) {
  teardown();
  begin(label);
}

let retryTimer = null;
let retryCount = 0;
let lastRetryAt = 0;

function retryOnce() {
  const now = Date.now();
  const gap = lastRetryAt ? ` gap=${((now - lastRetryAt) / 1000).toFixed(1)}s` : "";
  lastRetryAt = now;
  const label = `retry ${++retryCount}`;
  log(`${label}:${gap} ${state()}`);
  restart(label);
}

function stopRetry() {
  clearInterval(retryTimer);
  retryTimer = null;
  lastRetryAt = 0;
  $("retry").textContent = "Retry loop: off";
  log("retry loop off");
}

// --- Events.

for (const name of ["play", "playing", "pause", "waiting", "stalled", "error", "ended", "suspend", "abort"]) {
  audio.addEventListener(name, () => {
    const detail = name === "error" && audio.error ? ` code=${audio.error.code} ${audio.error.message}` : "";
    log(`event ${name}${detail} ${state()}`);
  });
}
audio.addEventListener("play", () => log(`meta "${setMeta("play")}"`));

document.addEventListener("visibilitychange", () => log(`visibilitychange ${state()}`));
for (const name of ["pagehide", "pageshow"]) {
  window.addEventListener(name, (event) => log(`${name} persisted=${event.persisted} ${state()}`));
}
for (const name of ["online", "offline", "popstate"]) {
  window.addEventListener(name, () => log(`${name} ${state()} url=${location.pathname}${location.hash}`));
}

// "pause" and "stop" log and do nothing else, so an element pause that follows
// was iOS's own doing, not this page's.
if ("mediaSession" in navigator) {
  for (const action of ["play", "pause", "stop"]) {
    try {
      navigator.mediaSession.setActionHandler(action, () => {
        log(`media session action ${action} ${state()}`);
        if (action === "play") restart("media session play");
      });
    } catch (err) {
      log(`media session action ${action} refused: ${err.name}: ${err.message}`);
    }
  }
} else {
  log("no navigator.mediaSession");
}

// --- Buttons.

$("start").addEventListener("click", () => {
  log("button Start");
  begin("Start");
});

$("stop").addEventListener("click", () => {
  log("button Stop");
  if (retryTimer !== null) stopRetry();
  wanted = false;
  teardown();
});

$("pause").addEventListener("click", () => {
  log("button Pause only");
  wanted = false;
  audio.pause();
});

$("retry").addEventListener("click", () => {
  if (retryTimer !== null) {
    stopRetry();
    return;
  }
  log("button Retry loop on");
  $("retry").textContent = "Retry loop: ON (press to end)";
  retryTimer = setInterval(retryOnce, RETRY_MS);
  retryOnce();
});

let pushCount = 0;
$("push").addEventListener("click", () => {
  history.pushState({ push: ++pushCount }, "", `#pushed-${pushCount}`);
  log(`button pushState url=${location.pathname}${location.hash} history.length=${history.length}`);
});

$("archive").addEventListener("click", () => log(`link archive.org ${state()}`));

// The box is filled and selected first, inside the tap: iOS allows the fallback's
// copy, and a selection the operator can copy by hand, only from a user gesture.
$("copy").addEventListener("click", () => {
  const text = lines.join("\n");
  const box = $("copybox");
  const status = $("status");
  box.value = text;
  box.hidden = false;
  box.select();
  box.setSelectionRange(0, text.length);
  const copied = () => {
    box.hidden = true;
    status.textContent = `Copied ${text.split("\n").length} lines`;
  };
  const fallback = () => {
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      // handled as not copied
    }
    if (ok) copied();
    else status.textContent = "Not copied: select all in the box below, then Copy";
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(copied, fallback);
  } else {
    fallback();
  }
});

// --- Page start.

const round = location.pathname.match(/\/assets\/preview\/([^/]+)\//);
if (round) {
  const link = document.createElement("link");
  link.rel = "manifest";
  link.href = `/assets/preview/${round[1]}/probe.webmanifest`;
  document.head.append(link);
}

log(`--- page load ${new Date().toString()}`);
log(`standalone=${navigator.standalone} display-standalone=${matchMedia("(display-mode: standalone)").matches} `
  + `manifest=${round ? round[1] : "none"} url=${location.href}`);
log(`ua ${navigator.userAgent}`);
