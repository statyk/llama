### Task 8: Show render — joins, gain, encode, frame check

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/render.py`
- Create: `packages/transmitter/tests_transmitter/test_render.py`

**Interfaces:**
- Consumes: `aacenc.AacFileEncoder/frames_for/pad_to_frame/extra_frames`, `adts.frame_offsets`, `analysis.ShowAnalysis/FileAnalysis/gain_db`, `audio.iter_decode`, `config.RenderConfig`, `station.Show`, `errors.RenderError/FrameCountDrift`.
- Produces:
  - `FileSpan(path, kind, title, start_sample, samples)`; `ShowLayout(spans: tuple[FileSpan, ...], content_samples, padded_samples)`.
  - `show_layout(analysis, pause_samples) -> ShowLayout` — clip↔track and clip↔clip joins get `pause_samples`, track→track gets 0; padded to whole frames.
  - `planned_frames(analysis, pause_samples, extra) -> int`.
  - `RenderSettings(ffmpeg, music_target_lufs, speech_target_lufs, clip_pause_samples)` with `RenderSettings.from_config(cfg: RenderConfig)`.
  - `file_gain(file, analysis, settings) -> float` (linear).
  - `render_show(show, analysis, out_path, *, settings, extra) -> int` (frames written; raises `RenderError` on a changed package, `FrameCountDrift` on a frame-count mismatch).

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_render.py`:

```python
import time

import numpy as np
import pytest

from tests_transmitter.helpers import (build_package, decode_adts, make_root, requires_ffmpeg,
                                       stereo_sine, write_mp3)
from transmitter import aacenc, analysis, render, station
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.config import RenderConfig
from transmitter.errors import FrameCountDrift, RenderError


def _a(*files):
    return ShowAnalysis(key="k", slug="s", files=tuple(FileAnalysis(p, k, p, n) for p, k, n in files),
                        tracks_i_lufs=-20.0, tracks_tp_dbfs=-6.0, meta={})


def test_layout_joins():
    a = _a(("i", "clip", 100), ("t1", "track", 1000), ("t2", "track", 1000), ("o", "clip", 50))
    lay = render.show_layout(a, pause_samples=7)
    assert [s.start_sample for s in lay.spans] == [0, 107, 1107, 2114]
    assert lay.content_samples == 2164
    assert lay.padded_samples == 3072


def test_layout_clip_to_clip_also_pauses():
    lay = render.show_layout(_a(("a", "clip", 10), ("b", "clip", 10)), pause_samples=5)
    assert [s.start_sample for s in lay.spans] == [0, 15]


def test_planned_frames():
    a = _a(("t", "track", 2048))
    assert render.planned_frames(a, 0, extra=1) == 3


def test_file_gain_uses_the_track_set_for_tracks_and_the_clip_for_clips():
    s = render.RenderSettings("ffmpeg", -16.0, -18.0, 0)
    a = ShowAnalysis("k", "s", (FileAnalysis("t", "track", "t", 1), FileAnalysis("c", "clip", "c", 1, -24.0, -12.0)),
                     tracks_i_lufs=-20.0, tracks_tp_dbfs=-6.0, meta={})
    assert render.file_gain(a.files[0], a, s) == pytest.approx(10 ** (4.0 / 20))
    assert render.file_gain(a.files[1], a, s) == pytest.approx(10 ** (6.0 / 20))


def _segue_package(tmp_path):
    """Two tracks cut from one phase-continuous sine (a segue) between DJ clips."""
    music = stereo_sine(6.0, 440.0, 0.1)
    split = 130_001

    def writer(path, i):
        if i == 1:
            write_mp3(path, music[:split])
        elif i == 2:
            write_mp3(path, music[split:])
        else:
            write_mp3(path, stereo_sine(1.0, 300.0, 0.05, rate=24_000)[:, 0], rate=24_000)

    pkg = build_package(make_root(tmp_path), tracks=2, audio=writer)
    return station.evaluate(pkg, now_s=time.time(), quiet_s=0), split


@requires_ffmpeg
def test_render_show_frame_count_gain_and_gapless_segue(tmp_path):
    show, split = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    settings = render.RenderSettings.from_config(RenderConfig())     # -16/-16 LUFS, 0.75 s pause
    extra = aacenc.extra_frames()
    out = tmp_path / "shows" / f"{show.key}.aac"
    frames = render.render_show(show, a, out, settings=settings, extra=extra)
    assert frames == render.planned_frames(a, settings.clip_pause_samples, extra)

    pcm = decode_adts(out.read_bytes())[aacenc.ENCODER_PRIMING_SAMPLES:]
    lay = render.show_layout(a, settings.clip_pause_samples)
    t1, t2 = lay.spans[1], lay.spans[2]
    assert t2.start_sample == t1.start_sample + t1.samples        # no inserted silence
    join = t2.start_sample
    rms = float(np.sqrt(np.mean(pcm[join - 2048:join + 2048, 0] ** 2)))
    expected_amp = 0.1 * render.file_gain(a.files[1], a, settings)     # file_gain is linear
    assert rms == pytest.approx(expected_amp / np.sqrt(2), rel=0.15)   # no dip at the segue

    pause_mid = lay.spans[1].start_sample - settings.clip_pause_samples // 2
    assert float(np.max(np.abs(pcm[pause_mid - 500:pause_mid + 500]))) < 0.01   # clip->track pause


@requires_ffmpeg
def test_render_refuses_a_package_that_changed_after_analysis(tmp_path):
    show, _ = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    files = list(a.files)
    files[1] = FileAnalysis(files[1].path, "track", files[1].title, files[1].samples + 1)
    stale = ShowAnalysis(a.key, a.slug, tuple(files), a.tracks_i_lufs, a.tracks_tp_dbfs, a.meta)
    out = tmp_path / "x.aac"
    with pytest.raises(RenderError, match="the package changed"):
        render.render_show(show, stale, out, settings=render.RenderSettings("ffmpeg", -16, -16, 0),
                           extra=aacenc.extra_frames())
    assert not out.exists() and not any(out.parent.glob(".x.aac.*"))


@requires_ffmpeg
def test_frame_count_drift_is_fatal(tmp_path):
    show, _ = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    out = tmp_path / "x.aac"
    with pytest.raises(FrameCountDrift):
        render.render_show(show, a, out, settings=render.RenderSettings("ffmpeg", -16, -16, 0),
                           extra=aacenc.extra_frames() + 1)
    assert not out.exists()


def test_render_refuses_a_mismatched_analysis(tmp_path):
    show = station.Show("s", tmp_path, (station.Entry("audio/a.mp3", "track", "A"),), "k", {})
    with pytest.raises(RenderError, match="does not match"):
        render.render_show(show, _a(("audio/b.mp3", "track", 10)), tmp_path / "x.aac",
                           settings=render.RenderSettings("ffmpeg", -16, -16, 0), extra=1)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.render'`.

- [ ] **Step 3: Implement `render.py`**

```python
"""Per-show encode (spec "Per-show encode, frame-count segmentation", "Joins",
"Loudness").

A show's whole broadcast.m3u is decoded gaplessly, gained (tracks by the
show's track-set gain, each DJ clip by its own speech gain), joined (no
silence track->track; `clip_pause` around clips), padded to a whole frame and
encoded once. The encoder's output -- priming and flush frames included -- is
the show's frame count; it must equal `planned_frames`, which the planner used
to place the next show."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts
from transmitter.analysis import FileAnalysis, ShowAnalysis, gain_db
from transmitter.audio import iter_decode
from transmitter.config import RenderConfig
from transmitter.errors import FrameCountDrift, RenderError
from transmitter.grid import samples_for_seconds
from transmitter.station import Show


@dataclass(frozen=True)
class FileSpan:
    path: str
    kind: str
    title: str
    start_sample: int     # within the show, before encoder priming
    samples: int


@dataclass(frozen=True)
class ShowLayout:
    spans: tuple[FileSpan, ...]
    content_samples: int
    padded_samples: int


def show_layout(analysis: ShowAnalysis, pause_samples: int) -> ShowLayout:
    spans: list[FileSpan] = []
    pos = 0
    prev: str | None = None
    for f in analysis.files:
        if prev is not None and "clip" in (prev, f.kind):
            pos += pause_samples
        spans.append(FileSpan(f.path, f.kind, f.title, pos, f.samples))
        pos += f.samples
        prev = f.kind
    return ShowLayout(tuple(spans), pos, aacenc.pad_to_frame(pos))


def planned_frames(analysis: ShowAnalysis, pause_samples: int, extra: int) -> int:
    return aacenc.frames_for(show_layout(analysis, pause_samples).padded_samples, extra)


@dataclass(frozen=True)
class RenderSettings:
    ffmpeg: str
    music_target_lufs: float
    speech_target_lufs: float
    clip_pause_samples: int

    @classmethod
    def from_config(cls, cfg: RenderConfig) -> "RenderSettings":
        return cls(cfg.ffmpeg, cfg.music_target_lufs, cfg.speech_target_lufs,
                   samples_for_seconds(cfg.clip_pause_seconds))


def file_gain(f: FileAnalysis, analysis: ShowAnalysis, settings: RenderSettings) -> float:
    if f.kind == "clip":
        db = gain_db(settings.speech_target_lufs, f.i_lufs, f.tp_dbfs)
    else:
        db = gain_db(settings.music_target_lufs, analysis.tracks_i_lufs, analysis.tracks_tp_dbfs)
    return 10.0 ** (db / 20.0)


def render_show(show: Show, analysis: ShowAnalysis, out_path: Path, *,
                settings: RenderSettings, extra: int) -> int:
    if analysis.key != show.key or [f.path for f in analysis.files] != [e.path for e in show.entries]:
        raise RenderError(f"{show.slug}: analysis does not match the package's current file set")
    layout = show_layout(analysis, settings.clip_pause_samples)
    expected = aacenc.frames_for(layout.padded_samples, extra)
    enc = aacenc.AacFileEncoder(out_path, settings.ffmpeg)
    try:
        pos = 0
        for span, f in zip(layout.spans, analysis.files):
            enc.write_silence(span.start_sample - pos)
            gain = file_gain(f, analysis, settings)
            n = 0
            for pcm in iter_decode(show.dir / span.path, settings.ffmpeg):
                # The gain rule already bounds true peak at -1 dBTP; the clamp is
                # the safety limiter the spec calls for, and normally never acts.
                enc.write(np.clip(pcm * gain, -1.0, 1.0))
                n += len(pcm)
            if n != span.samples:
                raise RenderError(f"{show.slug}: {span.path} decoded to {n} samples but was "
                                  f"analysed at {span.samples} -- the package changed")
            pos = span.start_sample + n
        enc.write_silence(layout.padded_samples - pos)
        enc.close()
    except BaseException:
        enc.abort()
        raise
    frames = len(adts.frame_offsets(Path(out_path).read_bytes())) - 1
    if frames != expected:
        Path(out_path).unlink(missing_ok=True)
        raise FrameCountDrift(f"{show.slug}: encoder produced {frames} frames, expected {expected} "
                              f"({layout.padded_samples} padded samples + {extra}); the frame-count "
                              "model does not hold on this ffmpeg")
    return frames
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_render.py -q`
Expected: PASS.

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS on ffmpeg 5.1.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): per-show render with gapless joins, loudness gain and frame-count check"
```

---

