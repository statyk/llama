### Task 2: Spike B — AAC encoder, spike tool, HUMAN CHECKPOINT

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/aacenc.py`, `packages/transmitter/src/transmitter/spike.py`
- Create: `packages/transmitter/scripts/test-in-debian12.sh`
- Create: `packages/transmitter/tests_transmitter/test_aacenc.py`, `test_spike.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (add `decode_adts`)
- Modify: `.gitignore` (add `*.aac`)

**Interfaces:**
- Consumes: Task 1's `grid`, `adts`, `segment`, `errors.EncodeError`.
- Produces:
  - `transmitter.aacenc`: `ENCODER_PRIMING_SAMPLES = 1024`; `BITRATE = "128k"`; `encode_cmd(ffmpeg) -> list[str]`; `as_station_pcm(pcm) -> np.ndarray` (float32, shape `(n, 2)`); `encode_pcm(pcm, ffmpeg="ffmpeg") -> bytes` (ADTS); `class AacFileEncoder(out_path, ffmpeg="ffmpeg")` with `.write(pcm)`, `.write_silence(samples)`, `.close() -> Path`, `.abort()`, `.samples_written`, context-manager use; `extra_frames(ffmpeg="ffmpeg") -> int` (memoized); `frames_for(padded_samples, extra) -> int`; `pad_to_frame(samples) -> int`; `silent_frame(ffmpeg="ffmpeg") -> bytes` (memoized).
  - `transmitter.spike`: `WRAP_N = 9321`; `show_a(seconds) -> tuple[np.ndarray, dict]`; `show_b(seconds) -> np.ndarray`; `build(out_dir, minutes=12.0, ffmpeg="ffmpeg") -> dict`; `vod_playlist(meta, epoch_us) -> str`; `live_playlist(meta, epoch_us, now_us, window=6) -> str | None`; `serve(out_dir, port=8000, host="0.0.0.0")`; `main(argv=None)`.
  - `tests_transmitter.helpers.decode_adts(data: bytes) -> np.ndarray` (ffmpeg decode to float32 `(n, 2)`).

- [ ] **Step 1: Write the failing encoder tests**

Append to `tests_transmitter/helpers.py`:

```python
import subprocess

import numpy as np


def decode_adts(data: bytes) -> np.ndarray:
    """Decode an ADTS byte stream to float32 (n, 2) with ffmpeg. The decoder
    does NOT trim encoder priming from raw ADTS, so sample 0 of the result is
    the first sample of the priming frame."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "aac", "-i", "pipe:0",
         "-f", "f32le", "-ac", "2", "-ar", "44100", "pipe:1"],
        input=data, capture_output=True, check=True,
    ).stdout
    return np.frombuffer(out, dtype="<f4").reshape(-1, 2)
```

`tests_transmitter/test_aacenc.py`:

```python
import numpy as np
import pytest

from tests_transmitter.helpers import decode_adts, requires_ffmpeg
from transmitter import aacenc, adts
from transmitter.errors import EncodeError
from transmitter.grid import FRAME_SAMPLES


def _zeros(n):
    return np.zeros((n, 2), np.float32)


def test_frames_for_and_pad_to_frame():
    assert aacenc.pad_to_frame(0) == 0
    assert aacenc.pad_to_frame(1) == 1024
    assert aacenc.pad_to_frame(2048) == 2048
    assert aacenc.frames_for(4096, 1) == 5
    with pytest.raises(ValueError):
        aacenc.frames_for(4097, 1)


def test_as_station_pcm_rejects_mono():
    with pytest.raises(ValueError):
        aacenc.as_station_pcm(np.zeros(10, np.float32))


@requires_ffmpeg
def test_encode_pcm_yields_station_format_frames():
    frames = adts.split_frames(aacenc.encode_pcm(_zeros(4 * FRAME_SAMPLES)))
    for f in frames:
        adts.require_station_format(adts.parse_header(f))


@requires_ffmpeg
@pytest.mark.parametrize("frames", [3, 441, 1000])
def test_extra_frames_is_the_same_for_every_padded_length(frames):
    extra = aacenc.extra_frames()
    got = len(adts.split_frames(aacenc.encode_pcm(_zeros(frames * FRAME_SAMPLES))))
    assert got == aacenc.frames_for(frames * FRAME_SAMPLES, extra)


@requires_ffmpeg
def test_priming_matches_the_declared_constant():
    pcm = _zeros(44_100)
    pcm[5000:5003] = 0.8
    decoded = decode_adts(aacenc.encode_pcm(pcm))
    peak = int(np.argmax(np.abs(decoded[:, 0])))
    assert abs((peak - 5001) - aacenc.ENCODER_PRIMING_SAMPLES) <= 3


@requires_ffmpeg
def test_file_encoder_streams_and_renames_atomically(tmp_path):
    out = tmp_path / "shows" / "k.aac"
    enc = aacenc.AacFileEncoder(out)
    enc.write(_zeros(3000))
    enc.write_silence(5000)
    assert enc.samples_written == 8000
    assert enc.close() == out
    assert len(adts.split_frames(out.read_bytes())) == aacenc.frames_for(aacenc.pad_to_frame(8000), aacenc.extra_frames())
    assert [p.name for p in out.parent.iterdir()] == ["k.aac"]


@requires_ffmpeg
def test_file_encoder_abort_leaves_nothing(tmp_path):
    out = tmp_path / "k.aac"
    with pytest.raises(RuntimeError):
        with aacenc.AacFileEncoder(out) as enc:
            enc.write(_zeros(2048))
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_silent_frame_is_station_format_and_decodes_to_silence():
    frame = aacenc.silent_frame()
    adts.require_station_format(adts.parse_header(frame))
    decoded = decode_adts(frame * 20)
    assert float(np.max(np.abs(decoded))) < 1e-4


def test_missing_ffmpeg_is_an_encode_error():
    with pytest.raises(EncodeError):
        aacenc.encode_pcm(_zeros(1024), ffmpeg="/nonexistent/ffmpeg")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_aacenc.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.aacenc'`.

- [ ] **Step 3: Implement `aacenc.py`**

```python
"""AAC-LC encoding with ffmpeg's native `aac` encoder (present in ffmpeg 5.1;
no libfdk). 128 kbps target, 44.1 kHz stereo, ADTS output.

The native encoder has no strict CBR mode: `-b:a 128k` targets 128 kbps and
digital silence encodes to tiny frames. Frame counts are what matter here:
for input padded to whole frames the encoder emits `padded/1024 + extra`
frames, with `extra` measured by `extra_frames()` rather than assumed (1 on
ffmpeg 8.1; the Debian 12 run checks 5.1)."""

import functools
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from transmitter import adts
from transmitter.errors import EncodeError
from transmitter.grid import CHANNELS, FRAME_SAMPLES, SAMPLE_RATE

ENCODER_PRIMING_SAMPLES = 1024   # ffmpeg aac's declared initial_padding
BITRATE = "128k"


def encode_cmd(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-v", "error",
            "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-c:a", "aac", "-b:a", BITRATE, "-f", "adts", "pipe:1"]


def as_station_pcm(pcm: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(pcm, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != CHANNELS:
        raise ValueError(f"station PCM is float32 shaped (n, {CHANNELS}); got {arr.shape}")
    return arr


def encode_pcm(pcm: np.ndarray, ffmpeg: str = "ffmpeg") -> bytes:
    """Encode a whole (small) PCM buffer in one ffmpeg call."""
    try:
        proc = subprocess.run(encode_cmd(ffmpeg), input=as_station_pcm(pcm).tobytes(),
                              capture_output=True)
    except OSError as exc:
        raise EncodeError(f"cannot run {ffmpeg}: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip()[-500:]
        raise EncodeError(f"ffmpeg aac encode failed (exit {proc.returncode}): {tail}")
    return proc.stdout


class AacFileEncoder:
    """Streams PCM into one ffmpeg encode whose ADTS output appears at
    `out_path` atomically on close(). stdout goes straight to a unique temp
    file and stderr to an anonymous temp file, so no pipe can fill up and
    deadlock the writer."""

    def __init__(self, out_path: Path, ffmpeg: str = "ffmpeg"):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.out_path.parent, prefix=f".{self.out_path.name}.",
                                   suffix=".tmp")
        self._tmp = Path(tmp)
        self._out = os.fdopen(fd, "wb")
        self._err = tempfile.TemporaryFile()
        try:
            self._proc = subprocess.Popen(encode_cmd(ffmpeg), stdin=subprocess.PIPE,
                                          stdout=self._out, stderr=self._err)
        except OSError as exc:
            self._out.close()
            self._cleanup()
            raise EncodeError(f"cannot run {ffmpeg}: {exc}") from exc
        self.samples_written = 0
        self._closed = False

    def __enter__(self) -> "AacFileEncoder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()

    def write(self, pcm: np.ndarray) -> None:
        arr = as_station_pcm(pcm)
        try:
            self._proc.stdin.write(arr.tobytes())
        except BrokenPipeError as exc:
            raise EncodeError(f"ffmpeg aac encoder exited early: {self._stderr_tail()}") from exc
        self.samples_written += len(arr)

    def write_silence(self, samples: int, chunk: int = 1 << 16) -> None:
        while samples > 0:
            n = min(samples, chunk)
            self.write(np.zeros((n, CHANNELS), np.float32))
            samples -= n

    def close(self) -> Path:
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self._proc.wait()
        self._out.close()
        self._closed = True
        if rc != 0:
            tail = self._stderr_tail()
            self._cleanup()
            raise EncodeError(f"ffmpeg aac encode failed (exit {rc}): {tail}")
        self._err.close()
        os.replace(self._tmp, self.out_path)
        return self.out_path

    def abort(self) -> None:
        if self._closed:
            return
        self._proc.kill()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        self._out.close()
        self._closed = True
        self._cleanup()

    def _cleanup(self) -> None:
        self._err.close()
        self._tmp.unlink(missing_ok=True)

    def _stderr_tail(self) -> str:
        self._err.seek(0)
        return self._err.read().decode(errors="replace").strip()[-500:]


def pad_to_frame(samples: int) -> int:
    return -(-samples // FRAME_SAMPLES) * FRAME_SAMPLES


def frames_for(padded_samples: int, extra: int) -> int:
    if padded_samples % FRAME_SAMPLES:
        raise ValueError("pad the input to a whole number of frames first")
    return padded_samples // FRAME_SAMPLES + extra


@functools.cache
def extra_frames(ffmpeg: str = "ffmpeg") -> int:
    """Frames the encoder emits beyond padded_samples/1024 (priming + flush)."""
    probe = 8
    got = len(adts.split_frames(encode_pcm(np.zeros((probe * FRAME_SAMPLES, CHANNELS), np.float32), ffmpeg)))
    extra = got - probe
    if extra < 0:
        raise EncodeError(f"{ffmpeg} emitted {got} frames for {probe} frames of input")
    return extra


@functools.cache
def silent_frame(ffmpeg: str = "ffmpeg") -> bytes:
    """One steady-state encoded frame of digital silence, repeated to fill
    gaps between shows (spec: "pre-encoded silent frames fill the gap")."""
    frames = adts.split_frames(encode_pcm(np.zeros((16 * FRAME_SAMPLES, CHANNELS), np.float32), ffmpeg))
    frame = frames[len(frames) // 2]
    adts.require_station_format(adts.parse_header(frame))
    return frame
```

- [ ] **Step 4: Run the encoder tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_aacenc.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing spike tests**

`tests_transmitter/test_spike.py`:

```python
import json

import numpy as np

from tests_transmitter.helpers import requires_ffmpeg
from transmitter import grid, segment, spike


def test_wrap_n_is_the_first_wrapped_segment():
    assert grid.segment_timestamp(spike.WRAP_N) < grid.segment_timestamp(spike.WRAP_N - 1)


def test_show_a_segue_is_phase_continuous():
    pcm, info = spike.show_a(36.0)
    mono = pcm[:, 0].astype(np.float64)
    at = int(info["segue_at_s"] * grid.SAMPLE_RATE)
    window = mono[at - 2000:at + 2000]
    # a phase-continuous 0.25-amplitude sine below 600 Hz never moves more than
    # 2*pi*600/44100*0.25 = 0.0214 between samples; a click would.
    assert float(np.max(np.abs(np.diff(window)))) < 0.0214


def test_live_playlist_window_and_endlist():
    meta = {"n0": 100, "count": 10}
    e = 0
    at = lambda n: grid.segment_start_us(e, n) + 1   # noqa: E731
    assert spike.live_playlist(meta, e, at(99)) is None
    body = spike.live_playlist(meta, e, at(107))
    assert "#EXT-X-MEDIA-SEQUENCE:102\n" in body
    assert body.count("#EXTINF:10.240,") == 6
    assert "seg/107.aac" in body and "#EXT-X-ENDLIST" not in body
    done = spike.live_playlist(meta, e, at(115))
    assert done.rstrip().endswith("#EXT-X-ENDLIST") and "seg/109.aac" in done


@requires_ffmpeg
def test_build_produces_grid_segments_with_the_wrap_in_show_b(tmp_path):
    meta = spike.build(tmp_path, minutes=1.5)
    n0, count = meta["n0"], meta["count"]
    assert n0 < spike.WRAP_N <= n0 + count - 1
    assert meta["wrap_at_s"] > meta["show_b_at_s"]
    for n in range(n0, n0 + count):
        ts, frames = segment.parse((tmp_path / "seg" / f"{n}.aac").read_bytes())
        assert ts == grid.segment_timestamp(n)
        assert len(frames) == grid.SEGMENT_FRAMES
    vod = (tmp_path / "vod.m3u8").read_text()
    assert vod.count("#EXTINF:10.240,") == count
    assert vod.rstrip().endswith("#EXT-X-ENDLIST")
    assert json.loads((tmp_path / "meta.json").read_text()) == meta
    assert "hls.js" in (tmp_path / "index.html").read_text()
```

- [ ] **Step 6: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_spike.py -q`
Expected: FAIL — `ImportError: cannot import name 'spike'`.

- [ ] **Step 7: Implement `spike.py`**

```python
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
```

- [ ] **Step 8: Run the spike tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_spike.py -q`
Expected: PASS.

- [ ] **Step 9: Add the Debian 12 runner and check hugo's ffmpeg**

`packages/transmitter/scripts/test-in-debian12.sh` (then `chmod +x`):

```sh
#!/bin/sh
# Run transmitter's tests on hugo's versions: Debian 12 = Python 3.11 + ffmpeg 5.1.
# Usage: packages/transmitter/scripts/test-in-debian12.sh [extra pytest args]
set -eu
repo=$(cd "$(dirname "$0")/../../.." && pwd)
exec docker run --rm -v "$repo:/src:ro" debian:12 sh -euc '
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv ffmpeg >/dev/null
  ffmpeg -version | head -1
  python3 --version
  mkdir /work
  tar -C /src --exclude=./.venv --exclude=./.git --exclude=./.claude \
      --exclude="*/node_modules" --exclude="*/__pycache__" -cf - . | tar -C /work -xf -
  python3 -m venv /venv
  /venv/bin/pip install -q -e "/work/packages/transmitter[dev]"
  cd /work
  /venv/bin/python -m pytest -q -p no:cacheprovider packages/transmitter/tests_transmitter "$@"
' sh "$@"
```

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: prints `ffmpeg version 5.1.x` and `Python 3.11.x`, then PASS. If `test_priming_matches_the_declared_constant` or `test_extra_frames_is_the_same_for_every_padded_length` fails on 5.1, STOP and report BLOCKED with the measured values: the frame-count model must hold on hugo.

Add to `.gitignore`:

```
*.aac
```

- [ ] **Step 10: Commit**

```bash
git add .gitignore packages/transmitter
git commit -m "feat(transmitter): native-aac encoder wrapper and the phase-1 container spike"
```

- [ ] **Step 11: HUMAN CHECKPOINT — the operator listens (orchestrator: stop and escalate)**

The orchestrator reports to the operator and waits for a recorded PASS before starting Task 4 (Tasks 3, 5 and 7 may proceed meanwhile). Procedure for the operator:

```bash
SPIKE="$HOME/spike-out"            # anywhere outside the repo
./.venv/bin/python -m transmitter.spike build "$SPIKE"
./.venv/bin/python -m transmitter.spike serve "$SPIKE"     # note the printed segue/gap/wrap offsets
```

1. **Chrome (hls.js):** open `http://localhost:8000/`, press *Play live.m3u8*, listen ≥ 3 minutes (≥ 15 segment boundaries) in show B's steady tone. Then *Play vod.m3u8* and seek to just before the printed segue, show-gap and wrap offsets in turn.
2. **Safari (macOS):** same as 1 (native HLS).
3. **iPhone/iPad on the same LAN:** `http://<mac-lan-ip>:8000/`, *Play live.m3u8*, lock the screen, let it play ≥ 10 minutes; then AirPlay to a receiver.
4. **VLC:** *Open Network Stream* `http://localhost:8000/live.m3u8`, then `…/vod.m3u8`.
5. **ENDLIST:** let a live session run to its end (the live playlist appends `#EXT-X-ENDLIST` after the last segment): every player stops cleanly, with no error loop.

**PASS requires all of:** (a) no click, dropout or stutter at segment boundaries in the continuous tones, in every player; the segue is a clean pitch step with no click; the show gap is ~2 s of clean silence with clean onsets either side; (b) playback continues through the timestamp wrap with no stall, skip or error (hls.js log: no FATAL; program-date-time keeps advancing smoothly); (c) all four players accept the packed-audio container; (d) iOS lock-screen playback runs 10 minutes uninterrupted and AirPlay works.

Record per player, per criterion, in the run's SDD ledger.

**If it FAILS:**
- (b) or (c) in any player, or (a) at *every* segment boundary → the container is the problem: switch to fMP4. Stop the run and escalate to the operator with Appendix A; it is planned and reviewed as an amendment to Task 4 (the segment writer), then this spike is re-run in fMP4 mode before Task 4 proceeds.
- (a) only at the show gap → silent-frame splicing problem, not the container: escalate (candidate fix: take the trailing frames of the preceding show's own encode as the gap filler instead of a repeated standalone silent frame).
- (d) only → a player-page issue, not the container: note it for the phase-4 player and continue.

---

