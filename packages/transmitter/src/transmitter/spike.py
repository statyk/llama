"""Phase-1 container spike (spec "Phase-1 spike").

Builds ~12 minutes of frame-count ADTS segments from synthetic audio -- a
phase-continuous segue inside show A, DJ-style pauses around a beep "clip",
a 2 s show gap, and a 2^33 timestamp wrap inside show B -- plus a test page,
a VOD playlist and a wall-clock live playlist served by a tiny local server:

    python -m transmitter.spike build OUT_DIR [--minutes 12]
    python -m transmitter.spike serve OUT_DIR [--port 8000]

It uses the production grid/id3/adts/segment/aacenc modules, so a pass here is
evidence about the code that will air. Keep OUT_DIR outside the repo.
"""

import argparse
import json
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts, grid, segment
from transmitter.grid import D_US, SAMPLE_RATE, SEGMENT_FRAMES, TS_PER_SEGMENT, TS_WRAP

WRAP_N = -(-TS_WRAP // TS_PER_SEGMENT)   # 9321: first segment whose timestamp has wrapped
WINDOW = 6
FADE_S = 0.01


def _tone(freq: float, n: int, phase: float, amp: float) -> tuple[np.ndarray, float]:
    t = np.arange(n, dtype=np.float64)
    out = amp * np.sin(phase + 2 * np.pi * freq * t / SAMPLE_RATE)
    return out, (phase + 2 * np.pi * freq * n / SAMPLE_RATE) % (2 * np.pi)


def _fade(x: np.ndarray) -> np.ndarray:
    n = min(int(FADE_S * SAMPLE_RATE), len(x) // 2)
    if n == 0:
        return x
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, n))
    x = x.copy()
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def _stereo(mono: np.ndarray) -> np.ndarray:
    return np.repeat(mono.astype(np.float32)[:, None], 2, axis=1)


def show_a(seconds: float) -> tuple[np.ndarray, dict]:
    """440 Hz, then a phase-continuous segue to 554.37 Hz at a sample that is
    not frame-aligned, 0.75 s pause, 3 s of beeps (the "DJ clip"), 0.75 s
    pause, 440 Hz to the end. Only outer edges are faded: the segue must be
    click-free on its own."""
    n = grid.samples_for_seconds(seconds)
    pause = grid.samples_for_seconds(0.75)
    clip = grid.samples_for_seconds(3.0)
    segue_at = int(n * 0.30) + 337
    music1_end = int(n * 0.55)
    tail = n - music1_end - 2 * pause - clip
    if tail <= 0:
        raise ValueError("show A is too short")
    a1, phase = _tone(440.0, segue_at, 0.0, 0.25)
    a2, _ = _tone(554.37, music1_end - segue_at, phase, 0.25)
    beeps = np.zeros(clip)
    on = grid.samples_for_seconds(0.2)
    period = grid.samples_for_seconds(0.5)
    for start in range(0, clip - on, period):
        beep, _ = _tone(1000.0, on, 0.0, 0.2)
        beeps[start:start + on] = _fade(beep)
    a3, _ = _tone(440.0, tail, 0.0, 0.25)
    pcm = np.concatenate([_fade(np.concatenate([a1, a2])), np.zeros(pause), beeps,
                          np.zeros(pause), _fade(a3)])
    return _stereo(pcm), {"segue_at_s": segue_at / SAMPLE_RATE}


def show_b(seconds: float) -> np.ndarray:
    """660 Hz under a slow 0.25 Hz swell: continuous, so a glitch at any
    segment boundary or at the timestamp wrap is audible."""
    n = grid.samples_for_seconds(seconds)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    amp = 0.15 + 0.1 * (0.5 - 0.5 * np.cos(2 * np.pi * 0.25 * t))
    return _stereo(_fade(amp * np.sin(2 * np.pi * 660.0 * t)))


def _pad(pcm: np.ndarray) -> np.ndarray:
    missing = aacenc.pad_to_frame(len(pcm)) - len(pcm)
    return np.concatenate([pcm, np.zeros((missing, 2), np.float32)])


def _header(first: int) -> list[str]:
    return ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:11",
            f"#EXT-X-MEDIA-SEQUENCE:{first}"]


def _entry(n: int, epoch_us: int) -> list[str]:
    return [f"#EXT-X-PROGRAM-DATE-TIME:{grid.us_to_iso(grid.segment_start_us(epoch_us, n))}",
            "#EXTINF:10.240,", f"seg/{n}.aac"]


def vod_playlist(meta: dict, epoch_us: int) -> str:
    lines = _header(meta["n0"]) + ["#EXT-X-PLAYLIST-TYPE:VOD"]
    for n in range(meta["n0"], meta["n0"] + meta["count"]):
        lines += _entry(n, epoch_us)
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def live_playlist(meta: dict, epoch_us: int, now_us: int, window: int = WINDOW) -> str | None:
    first, last = meta["n0"], meta["n0"] + meta["count"] - 1
    cur = grid.segment_index_at(epoch_us, now_us)
    if cur < first:
        return None
    end = min(cur, last)
    start = max(first, end - window + 1)
    lines = _header(start)
    for n in range(start, end + 1):
        lines += _entry(n, epoch_us)
    if cur > last:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def build(out_dir: Path, minutes: float = 12.0, ffmpeg: str = "ffmpeg") -> dict:
    out = Path(out_dir)
    (out / "seg").mkdir(parents=True, exist_ok=True)
    total_s = minutes * 60.0
    a_s = min(300.0, total_s * 0.4)
    gap_s = 2.0
    pcm_a, a_info = show_a(a_s)
    frames_a = adts.split_frames(aacenc.encode_pcm(_pad(pcm_a), ffmpeg))
    frames_b = adts.split_frames(aacenc.encode_pcm(_pad(show_b(total_s - a_s - gap_s)), ffmpeg))
    silent = aacenc.silent_frame(ffmpeg)
    gap = grid.gap_frames(gap_s)
    stream = frames_a + [silent] * gap + frames_b
    count = -(-len(stream) // SEGMENT_FRAMES)
    stream += [silent] * (count * SEGMENT_FRAMES - len(stream))
    b_start = len(frames_a) + gap
    n0 = WRAP_N - int(count * 0.6)
    if (WRAP_N - n0) * SEGMENT_FRAMES <= b_start:
        raise ValueError("too few minutes for the timestamp wrap to land inside show B")
    for i in range(count):
        n = n0 + i
        frames = stream[i * SEGMENT_FRAMES:(i + 1) * SEGMENT_FRAMES]
        (out / "seg" / f"{n}.aac").write_bytes(segment.assemble(n, frames))
    meta = {
        "n0": n0, "count": count, "wrap_between": [WRAP_N - 1, WRAP_N],
        "segue_at_s": a_info["segue_at_s"],
        "show_gap_at_s": len(frames_a) * grid.FRAME_SAMPLES / SAMPLE_RATE,
        "show_b_at_s": b_start * grid.FRAME_SAMPLES / SAMPLE_RATE,
        "wrap_at_s": (WRAP_N - n0) * D_US / 1_000_000,
    }
    nominal_epoch_us = int(time.time()) * 1_000_000 - n0 * D_US
    (out / "vod.m3u8").write_text(vod_playlist(meta, nominal_epoch_us))
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    (out / "index.html").write_text(PAGE)
    return meta


def serve(out_dir: Path, port: int = 8000, host: str = "0.0.0.0") -> None:
    out = Path(out_dir)
    meta = json.loads((out / "meta.json").read_text())
    # choose E so the live window is full the moment the server starts
    epoch_us = time.time_ns() // 1000 - (meta["n0"] + WINDOW - 1) * D_US

    class Handler(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                          ".m3u8": "application/vnd.apple.mpegurl", ".aac": "audio/aac"}

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path.split("?")[0] == "/live.m3u8":
                body = live_playlist(meta, epoch_us, time.time_ns() // 1000)
                if body is None:
                    self.send_error(404)
                    return
                data = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

    httpd = ThreadingHTTPServer((host, port), partial(Handler, directory=str(out)))
    print(f"serving {out} at http://{host}:{port}/  (segue at {meta['segue_at_s']:.1f}s, "
          f"show gap at {meta['show_gap_at_s']:.1f}s, wrap at {meta['wrap_at_s']:.1f}s "
          f"of the VOD; the live playlist starts at the beginning and ends with ENDLIST)")
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m transmitter.spike")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out_dir", type=Path)
    b.add_argument("--minutes", type=float, default=12.0)
    s = sub.add_parser("serve")
    s.add_argument("out_dir", type=Path)
    s.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.cmd == "build":
        print(json.dumps(build(args.out_dir, args.minutes), indent=2))
    else:
        serve(args.out_dir, args.port)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>transmitter container spike</title>
<!-- local spike page only: the production player self-hosts hls.js (Task 17) -->
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.7.3/dist/hls.min.js"></script>
<style>body{font:16px system-ui;margin:2em;max-width:42em}button{font-size:1.1em;margin:.3em}
pre{background:#eee;padding:.5em;white-space:pre-wrap;max-height:20em;overflow:auto}</style>
</head><body>
<h1>transmitter container spike</h1>
<p><button id="live">Play live.m3u8</button><button id="vod">Play vod.m3u8</button>
<button id="stop">Stop</button></p>
<audio id="audio" controls></audio>
<p id="mode"></p><p id="pos"></p>
<pre id="log"></pre>
<script>
const audio = document.getElementById("audio"), log = document.getElementById("log");
const native = (navigator.vendor || "").startsWith("Apple") &&
  audio.canPlayType("application/vnd.apple.mpegurl") !== "";
document.getElementById("mode").textContent = native
  ? "player: native HLS (Apple WebKit)" : "player: hls.js " + (window.Hls ? Hls.version : "(not loaded)");
let hls = null;
function say(m) { log.textContent += new Date().toISOString() + "  " + m + "\n"; }
function stop() { if (hls) { hls.destroy(); hls = null; } audio.removeAttribute("src"); audio.load(); }
function play(url) {
  stop(); say("loading " + url);
  if (native) { audio.src = url; }
  else {
    hls = new Hls({ liveSyncDurationCount: 3 });
    hls.on(Hls.Events.ERROR, (e, d) => say("hls.js " + (d.fatal ? "FATAL " : "") + d.type + " " + d.details));
    hls.on(Hls.Events.LEVEL_LOADED, (e, d) => { if (!d.details.live) say("playlist has ENDLIST"); });
    hls.loadSource(url); hls.attachMedia(audio);
  }
  audio.play().catch(err => say("play() rejected: " + err));
}
audio.addEventListener("ended", () => say("ended (ENDLIST reached)"));
audio.addEventListener("error", () => say("media error " + (audio.error && audio.error.code)));
audio.addEventListener("waiting", () => say("waiting (stall?) at " + audio.currentTime.toFixed(2)));
document.getElementById("live").onclick = () => play("live.m3u8");
document.getElementById("vod").onclick = () => play("vod.m3u8");
document.getElementById("stop").onclick = stop;
setInterval(() => {
  let d = null;
  if (hls && hls.playingDate) d = hls.playingDate;
  else if (native && audio.getStartDate) {
    const s = audio.getStartDate().getTime();
    if (!isNaN(s)) d = new Date(s + audio.currentTime * 1000);
  }
  document.getElementById("pos").textContent =
    "t=" + audio.currentTime.toFixed(2) + "s  program-date-time=" + (d ? d.toISOString() : "n/a");
}, 500);
</script></body></html>
"""

if __name__ == "__main__":
    main()
