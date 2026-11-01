// The player page's entry module: the one once-a-second loop.
import { refreshTimeline, renderAt } from "./page.js";
import { positionMs } from "./timeline.js";

const url = document.getElementById("stream-url");
if (url) url.textContent = new URL("/live.m3u8", location.href).href;

function tick() {
  renderAt(positionMs({ playing: false, playbackMs: null, nowMs: Date.now() }));
  refreshTimeline(false);
}
tick();
setInterval(tick, 1000);
