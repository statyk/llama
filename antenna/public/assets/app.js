// The player page's entry module: the keys and the one once-a-second loop.
import { refreshTimeline, renderAt, ticketLinks } from "./page.js";
import { openPanel } from "./panel.js";
import { player } from "./player.js";
import { positionMs } from "./timeline.js";

const url = document.getElementById("stream-url");
if (url) url.textContent = new URL("/live.m3u8", location.href).href;

document.getElementById("play").addEventListener("click", player.start);
document.getElementById("retry").addEventListener("click", player.start);
document.getElementById("stop").addEventListener("click", player.stop);
ticketLinks(document, openPanel);

function tick() {
  const nowMs = Date.now();
  // A render error must never stop recovery: player.tick always runs.
  try {
    renderAt(positionMs({ playing: player.audible, playbackMs: player.playbackMs(), nowMs }));
  } catch {
    // The next tick tries again.
  }
  player.tick(nowMs);
  refreshTimeline(false);
}
setInterval(tick, 1000);
tick();
