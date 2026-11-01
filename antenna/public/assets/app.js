// The player page's entry module: the keys and the one once-a-second loop.
import { refreshTimeline, renderAt } from "./page.js";
import { player } from "./player.js";
import { positionMs } from "./timeline.js";

const url = document.getElementById("stream-url");
if (url) url.textContent = new URL("/live.m3u8", location.href).href;

document.getElementById("play").addEventListener("click", player.start);
document.getElementById("retry").addEventListener("click", player.start);
document.getElementById("stop").addEventListener("click", player.stop);

function tick() {
  const nowMs = Date.now();
  renderAt(positionMs({ playing: player.audible, playbackMs: player.playbackMs(), nowMs }));
  player.tick(nowMs);
  refreshTimeline(false);
}
tick();
setInterval(tick, 1000);
