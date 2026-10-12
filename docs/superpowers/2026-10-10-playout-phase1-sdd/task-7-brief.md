### Task 7: Gapless decode, loudness meter, analysis cache

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/audio.py`, `packages/transmitter/src/transmitter/analysis.py`
- Create: `packages/transmitter/tests_transmitter/test_audio.py`, `test_analysis.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (MP3 fixture writer)

**Interfaces:**
- Consumes: `aacenc.as_station_pcm`, `grid`, `station.Show/Entry`, `workspace.read_json/write_json`, `errors.DecodeError/AnalysisError`.
- Produces:
  - `transmitter.audio`: `decode_cmd(ffmpeg, path) -> list[str]`; `iter_decode(path, ffmpeg="ffmpeg") -> Iterator[np.ndarray]` (float32 `(n, 2)` at 44.1 kHz, LAME delay/padding honoured); `Loudness(i_lufs: float | None, tp_dbfs: float | None)`; `METER_FILTER`; `LoudnessMeter(ffmpeg="ffmpeg")` with `.write(pcm)`, `.finish() -> Loudness`, `.abort()`; `parse_ebur128_summary(text) -> Loudness`.
  - `transmitter.analysis`: `ANALYSIS_VERSION = 1`; `TRUE_PEAK_CEILING_DB = -1.0`; `FileAnalysis(path, kind, title, samples, i_lufs=None, tp_dbfs=None)`; `ShowAnalysis(key, slug, files: tuple[FileAnalysis, ...], tracks_i_lufs, tracks_tp_dbfs, meta: dict)` with `.to_json()`/`ShowAnalysis.from_json(d)`; `analyze_show(show, ffmpeg="ffmpeg") -> ShowAnalysis`; `load_cached(cache_dir, key) -> ShowAnalysis | None`; `load_or_analyze(cache_dir, show, ffmpeg="ffmpeg") -> ShowAnalysis`; `gain_db(target, i_lufs, tp_dbfs, ceiling=TRUE_PEAK_CEILING_DB) -> float`.
  - helpers: `stereo_sine(seconds, freq, amp, phase=0.0, rate=44100) -> np.ndarray`, `write_mp3(path, pcm, rate=44100)` (libmp3lame, LAME tag included).

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
def stereo_sine(seconds: float, freq: float, amp: float, phase: float = 0.0,
                rate: int = 44_100) -> np.ndarray:
    n = round(seconds * rate)
    t = np.arange(n, dtype=np.float64)
    mono = amp * np.sin(phase + 2 * np.pi * freq * t / rate)
    return np.repeat(mono.astype(np.float32)[:, None], 2, axis=1)


def write_mp3(path: Path, pcm: np.ndarray, rate: int = 44_100) -> None:
    """Encode float32 PCM (n, channels) to MP3 with libmp3lame, which writes
    the Xing/LAME header carrying encoder delay and padding (the gapless info
    archive.org derivatives carry)."""
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", str(rate),
         "-ac", str(channels), "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "192k", str(path)],
        input=np.ascontiguousarray(pcm, dtype=np.float32).tobytes(), check=True,
    )
```

`tests_transmitter/test_audio.py`:

```python
import numpy as np
import pytest

from tests_transmitter.helpers import requires_ffmpeg, stereo_sine, write_mp3
from transmitter import audio
from transmitter.errors import AnalysisError, DecodeError

SUMMARY = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -18.4 LUFS
    Threshold: -28.5 LUFS

  Loudness range:
    LRA:         6.1 LU

  True peak:
    Peak:       -0.7 dBFS
"""


def test_parse_summary():
    assert audio.parse_ebur128_summary("noise\n" + SUMMARY) == audio.Loudness(-18.4, -0.7)


def test_parse_summary_handles_silence():
    text = SUMMARY.replace("-18.4 LUFS", "-70.0 LUFS").replace("-0.7 dBFS", "-inf dBFS")
    assert audio.parse_ebur128_summary(text) == audio.Loudness(None, None)


def test_parse_summary_uses_the_last_summary():
    text = SUMMARY.replace("-18.4", "-30.0") + SUMMARY
    assert audio.parse_ebur128_summary(text).i_lufs == -18.4


def test_parse_summary_without_summary_is_an_error():
    with pytest.raises(AnalysisError):
        audio.parse_ebur128_summary("no summary here")


@requires_ffmpeg
def test_decode_honours_lame_delay_and_padding(tmp_path):
    """Two halves of one sine, split at a sample that is not an MP3 frame
    boundary, decode back to exactly their own lengths: a segue stays gapless."""
    pcm = stereo_sine(6.0, 440.0, 0.3)
    split = 123_457
    write_mp3(tmp_path / "a.mp3", pcm[:split])
    write_mp3(tmp_path / "b.mp3", pcm[split:])
    a = np.concatenate(list(audio.iter_decode(tmp_path / "a.mp3")))
    b = np.concatenate(list(audio.iter_decode(tmp_path / "b.mp3")))
    assert len(a) == split and len(b) == len(pcm) - split
    assert a.dtype == np.float32 and a.shape[1] == 2


@requires_ffmpeg
def test_decode_resamples_a_mono_24k_clip_to_stereo_44k1(tmp_path):
    mono = stereo_sine(2.0, 300.0, 0.3, rate=24_000)[:, 0]
    write_mp3(tmp_path / "clip.mp3", mono, rate=24_000)
    out = np.concatenate(list(audio.iter_decode(tmp_path / "clip.mp3")))
    assert out.shape[1] == 2
    assert abs(len(out) - 88_200) <= 64


@requires_ffmpeg
def test_decode_failure_is_a_decode_error(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(DecodeError):
        list(audio.iter_decode(bad))


@requires_ffmpeg
def test_meter_measures_a_known_sine():
    meter = audio.LoudnessMeter()
    pcm = stereo_sine(8.0, 1000.0, 0.1)            # -20 dBFS peak in both channels
    for i in range(0, len(pcm), 50_000):
        meter.write(pcm[i:i + 50_000])
    loud = meter.finish()
    assert loud.i_lufs == pytest.approx(-20.0, abs=0.5)
    assert loud.tp_dbfs == pytest.approx(-20.0, abs=0.5)


@requires_ffmpeg
def test_meter_on_silence_and_on_nothing():
    meter = audio.LoudnessMeter()
    meter.write(np.zeros((44_100 * 3, 2), np.float32))
    assert meter.finish() == audio.Loudness(None, None)
    assert audio.LoudnessMeter().finish() == audio.Loudness(None, None)
```

`tests_transmitter/test_analysis.py`:

```python
import time

import numpy as np
import pytest

from tests_transmitter.helpers import build_package, make_root, requires_ffmpeg, stereo_sine, write_mp3
from transmitter import analysis, audio, station
from transmitter.analysis import FileAnalysis, ShowAnalysis, gain_db


def test_gain_db_loudness_bound():
    assert gain_db(-16.0, -20.0, -10.0) == pytest.approx(4.0)


def test_gain_db_true_peak_bound():
    assert gain_db(-16.0, -20.0, -2.0) == pytest.approx(1.0)       # -1 - (-2)


def test_gain_db_turns_down_a_hot_tape():
    assert gain_db(-16.0, -10.0, -0.1) == pytest.approx(-6.0)


def test_gain_db_unmeasurable_is_unity():
    assert gain_db(-16.0, None, None) == 0.0
    assert gain_db(-16.0, None, -3.0) == 0.0


def test_gain_db_without_a_peak_reading_uses_loudness_alone():
    assert gain_db(-16.0, -20.0, None) == pytest.approx(4.0)


def test_show_analysis_json_round_trip():
    a = ShowAnalysis(key="k", slug="s", files=(FileAnalysis("audio/a.mp3", "track", "A", 10),
                                               FileAnalysis("dj-audio/x.mp3", "clip", "DJ", 5, -18.0, -3.0)),
                     tracks_i_lufs=-17.0, tracks_tp_dbfs=-1.5, meta={"artist": "Band"})
    assert ShowAnalysis.from_json(a.to_json()) == a


def _tone_writer(path, i):
    if i in (0, 99):          # DJ clips: mono 24 kHz, like emcee's
        write_mp3(path, stereo_sine(1.5, 300.0, 0.05, rate=24_000)[:, 0], rate=24_000)
    else:
        write_mp3(path, stereo_sine(2.0, 440.0 + 110 * i, 0.2))


@requires_ffmpeg
def test_analyze_show_counts_samples_and_measures_tracks_apart_from_clips(tmp_path):
    pkg = build_package(make_root(tmp_path), tracks=2, audio=_tone_writer)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    a = analysis.analyze_show(show)
    assert [f.path for f in a.files] == [e.path for e in show.entries]
    assert [f.samples for f in a.files if f.kind == "track"] == [88_200, 88_200]
    clips = [f for f in a.files if f.kind == "clip"]
    assert all(f.i_lufs is not None and f.i_lufs < -25 for f in clips)
    assert a.tracks_i_lufs == pytest.approx(20 * np.log10(0.2), abs=1.0)
    assert a.meta["artist"] == "Band"


@requires_ffmpeg
def test_load_or_analyze_caches_by_key(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path), tracks=1, audio=_tone_writer)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    first = analysis.load_or_analyze(tmp_path / "cache", show)
    assert (tmp_path / "cache" / f"{show.key}.json").exists()

    def boom(*a, **k):
        raise AssertionError("decoded again despite a cache hit")

    monkeypatch.setattr(analysis, "iter_decode", boom)
    assert analysis.load_or_analyze(tmp_path / "cache", show) == first
    assert analysis.load_cached(tmp_path / "cache", show.key) == first
    assert analysis.load_cached(tmp_path / "cache", "nope") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_audio.py packages/transmitter/tests_transmitter/test_analysis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.audio'`.

- [ ] **Step 3: Implement `audio.py`**

```python
"""Gapless decode and loudness measurement (spec "Renderer", "Loudness").

Decoding is ffmpeg to float32 44.1 kHz stereo PCM. ffmpeg's MP3 demuxer reads
the Xing/LAME header and trims encoder delay and padding, so consecutive tracks
of a segue concatenate with no inserted silence. Loudness is ffmpeg's
`ebur128` filter (BS.1770 integrated loudness + true peak), fed the same PCM
through a pipe. Every subprocess writes stderr to an anonymous temp file, so
no pipe can fill and deadlock the reader/writer.
"""

import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from transmitter.aacenc import as_station_pcm
from transmitter.errors import AnalysisError, DecodeError
from transmitter.grid import CHANNELS, SAMPLE_RATE

CHUNK_FRAMES = 1 << 16
_BYTES_PER_FRAME = 4 * CHANNELS
METER_FILTER = "ebur128=peak=true:framelog=verbose"
SILENCE_LUFS = -70.0   # ebur128's absolute gate: nothing measurable


def decode_cmd(ffmpeg: str, path: Path) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(path),
            "-map", "0:a:0", "-f", "f32le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "pipe:1"]


def iter_decode(path: Path, ffmpeg: str = "ffmpeg") -> Iterator[np.ndarray]:
    err = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(decode_cmd(ffmpeg, path), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=err)
    except OSError as exc:
        err.close()
        raise DecodeError(f"cannot run {ffmpeg}: {exc}") from exc
    finished = False
    try:
        pending = b""
        while True:
            chunk = proc.stdout.read(CHUNK_FRAMES * _BYTES_PER_FRAME)
            if not chunk:
                break
            data = pending + chunk
            usable = len(data) - len(data) % _BYTES_PER_FRAME
            pending = data[usable:]
            if usable:
                yield np.frombuffer(data[:usable], dtype="<f4").reshape(-1, CHANNELS)
        rc = proc.wait()
        if rc != 0 or pending:
            err.seek(0)
            tail = err.read().decode(errors="replace").strip()[-500:]
            raise DecodeError(f"{path}: ffmpeg decode failed (exit {rc}): {tail}")
        finished = True
    finally:
        if not finished and proc.poll() is None:
            proc.kill()
        proc.stdout.close()
        proc.wait()
        err.close()


@dataclass(frozen=True)
class Loudness:
    i_lufs: float | None     # None = nothing above the gate (silence)
    tp_dbfs: float | None    # None = -inf (digital silence)


_I_RE = re.compile(r"Integrated loudness:\s*\n\s*I:\s*(\S+)\s+LUFS")
_TP_RE = re.compile(r"True peak:\s*\n\s*Peak:\s*(\S+)\s+dBFS")


def _finite(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_ebur128_summary(text: str) -> Loudness:
    at = text.rfind("Summary:")
    if at < 0:
        raise AnalysisError("ffmpeg ebur128 printed no summary")
    tail = text[at:]
    m_i = _I_RE.search(tail)
    if m_i is None:
        raise AnalysisError("ffmpeg ebur128 summary has no integrated loudness")
    m_tp = _TP_RE.search(tail)
    i = _finite(m_i.group(1))
    if i is not None and i <= SILENCE_LUFS:
        i = None
    return Loudness(i, _finite(m_tp.group(1)) if m_tp else None)


class LoudnessMeter:
    """Feeds PCM into `ffmpeg -af ebur128` and parses its summary. The process
    starts lazily, so a meter that never receives samples reports (None, None)."""

    def __init__(self, ffmpeg: str = "ffmpeg"):
        self._ffmpeg = ffmpeg
        self._proc: subprocess.Popen | None = None
        self._err = None
        self.samples = 0

    def _start(self) -> None:
        self._err = tempfile.TemporaryFile()
        cmd = [self._ffmpeg, "-nostdin", "-hide_banner", "-nostats",
               "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
               "-af", METER_FILTER, "-f", "null", "-"]
        try:
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=self._err)
        except OSError as exc:
            self._err.close()
            raise AnalysisError(f"cannot run {self._ffmpeg}: {exc}") from exc

    def write(self, pcm: np.ndarray) -> None:
        if len(pcm) == 0:
            return
        if self._proc is None:
            self._start()
        try:
            self._proc.stdin.write(as_station_pcm(pcm).tobytes())
        except BrokenPipeError as exc:
            raise AnalysisError(f"ffmpeg ebur128 exited early: {self._stderr()[-500:]}") from exc
        self.samples += len(pcm)

    def finish(self) -> Loudness:
        if self._proc is None:
            return Loudness(None, None)
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self._proc.wait()
        text = self._stderr()
        self._err.close()
        self._proc = None
        if rc != 0:
            raise AnalysisError(f"ffmpeg ebur128 failed (exit {rc}): {text.strip()[-500:]}")
        return parse_ebur128_summary(text)

    def abort(self) -> None:
        if self._proc is None:
            return
        self._proc.kill()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        self._err.close()
        self._proc = None

    def _stderr(self) -> str:
        self._err.seek(0)
        return self._err.read().decode(errors="replace")
```

- [ ] **Step 4: Implement `analysis.py`**

```python
"""Per-show analysis (spec: "Durations and loudness come from one decode pass
per show ... cached keyed by the show's file set"): decoded sample counts per
file, integrated loudness + true peak over the tracks only, and per-clip
loudness for DJ clips (their own speech target). Rendering decodes again with
the same decoder and must reproduce these sample counts exactly."""

from dataclasses import asdict, dataclass
from pathlib import Path

from transmitter.audio import LoudnessMeter, iter_decode
from transmitter.errors import AnalysisError
from transmitter.station import Show
from transmitter.workspace import read_json, write_json

ANALYSIS_VERSION = 1
TRUE_PEAK_CEILING_DB = -1.0


@dataclass(frozen=True)
class FileAnalysis:
    path: str
    kind: str
    title: str
    samples: int
    i_lufs: float | None = None      # clips only
    tp_dbfs: float | None = None     # clips only


@dataclass(frozen=True)
class ShowAnalysis:
    key: str
    slug: str
    files: tuple[FileAnalysis, ...]
    tracks_i_lufs: float | None
    tracks_tp_dbfs: float | None
    meta: dict

    def to_json(self) -> dict:
        data = asdict(self)
        data["files"] = [asdict(f) for f in self.files]
        data["version"] = ANALYSIS_VERSION
        return data

    @classmethod
    def from_json(cls, data: dict) -> "ShowAnalysis":
        return cls(key=data["key"], slug=data["slug"],
                   files=tuple(FileAnalysis(**f) for f in data["files"]),
                   tracks_i_lufs=data["tracks_i_lufs"], tracks_tp_dbfs=data["tracks_tp_dbfs"],
                   meta=dict(data["meta"]))


def gain_db(target: float, i_lufs: float | None, tp_dbfs: float | None,
            ceiling: float = TRUE_PEAK_CEILING_DB) -> float:
    """min(target - I, ceiling - TP). The target is a ceiling, so quiet,
    dynamic tapes are not pushed into a limiter; unmeasurable audio (I below
    the gate) is left at unity gain."""
    if i_lufs is None:
        return 0.0
    gain = target - i_lufs
    if tp_dbfs is not None:
        gain = min(gain, ceiling - tp_dbfs)
    return gain


def analyze_show(show: Show, ffmpeg: str = "ffmpeg") -> ShowAnalysis:
    tracks = LoudnessMeter(ffmpeg)
    files: list[FileAnalysis] = []
    try:
        for entry in show.entries:
            clip_meter = LoudnessMeter(ffmpeg) if entry.kind == "clip" else None
            meter = clip_meter or tracks
            n = 0
            try:
                for pcm in iter_decode(show.dir / entry.path, ffmpeg):
                    meter.write(pcm)
                    n += len(pcm)
            except BaseException:
                if clip_meter is not None:
                    clip_meter.abort()
                raise
            if n == 0:
                raise AnalysisError(f"{show.slug}: {entry.path} decoded to no audio")
            loud = clip_meter.finish() if clip_meter is not None else None
            files.append(FileAnalysis(entry.path, entry.kind, entry.title, n,
                                      loud.i_lufs if loud else None, loud.tp_dbfs if loud else None))
        t = tracks.finish()
    except BaseException:
        tracks.abort()
        raise
    return ShowAnalysis(key=show.key, slug=show.slug, files=tuple(files),
                        tracks_i_lufs=t.i_lufs, tracks_tp_dbfs=t.tp_dbfs, meta=dict(show.meta))


def load_cached(cache_dir: Path, key: str) -> ShowAnalysis | None:
    data = read_json(Path(cache_dir) / f"{key}.json")
    if not data or data.get("version") != ANALYSIS_VERSION or data.get("key") != key:
        return None
    return ShowAnalysis.from_json(data)


def load_or_analyze(cache_dir: Path, show: Show, ffmpeg: str = "ffmpeg") -> ShowAnalysis:
    cached = load_cached(cache_dir, show.key)
    if cached is not None:
        return cached
    result = analyze_show(show, ffmpeg)
    write_json(Path(cache_dir) / f"{show.key}.json", result.to_json())
    return result
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_audio.py packages/transmitter/tests_transmitter/test_analysis.py -q`
Expected: PASS.

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS on ffmpeg 5.1 (this is where `framelog=verbose`, `-map 0:a:0` and LAME gapless decode are confirmed on hugo's ffmpeg; if `framelog` is rejected there, drop `:framelog=verbose` from `METER_FILTER` — stderr goes to a temp file, so per-frame lines are only wasted bytes — and re-run).

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): gapless decode, ebur128 loudness and the per-show analysis cache"
```

---

