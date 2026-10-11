import time

import numpy as np
import pytest

from tests_transmitter.helpers import (build_package, decode_adts, make_root, requires_ffmpeg,
                                       stereo_sine, write_mp3)
from transmitter import aacenc, adts, analysis, render, station
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.config import RenderConfig
from transmitter.errors import AdtsError, FrameCountDrift, RenderError, TransmitterError


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
    assert t1.samples + t2.samples == 6 * 44_100                  # gapless decode: the segue loses nothing
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


@requires_ffmpeg
def test_unverifiable_encode_is_removed(tmp_path, monkeypatch):
    """close() has already renamed the encode into place when the frame count
    is read; an unreadable output must not survive there, or FrameStore would
    treat an unverified encode as rendered."""
    show, _ = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    out = tmp_path / "x.aac"

    def broken(buf):
        raise AdtsError("malformed output")

    monkeypatch.setattr(adts, "frame_offsets", broken)
    with pytest.raises(AdtsError) as info:
        render.render_show(show, a, out, settings=render.RenderSettings("ffmpeg", -16, -16, 0),
                           extra=aacenc.extra_frames())
    assert isinstance(info.value, TransmitterError)
    assert not out.exists() and not any(out.parent.glob(".x.aac.*"))


@requires_ffmpeg
def test_a_decode_mismatch_drops_the_cached_analysis(tmp_path):
    # The cache is keyed by the package's file set, not the decoder: a decoder
    # whose trimmed sample counts differ from the cached ones would otherwise
    # fail this show on every tick until someone deleted cache/.
    from transmitter.config import TransmitterConfig
    from transmitter.pipeline import FfmpegEngine
    from transmitter.workspace import Workspace, read_json, write_json

    show, _ = _segue_package(tmp_path)
    ws = Workspace(tmp_path / "tx")
    engine = FfmpegEngine(ws, TransmitterConfig(root=ws.root))
    good = engine.analyze(show)                                   # writes cache/<key>.json
    cached = ws.cache_dir / f"{show.key}.json"
    data = read_json(cached)
    data["files"][1]["samples"] += 1                              # as analysed by another decoder
    write_json(cached, data)
    stale = engine.analyze(show)
    assert stale.files[1].samples == good.files[1].samples + 1
    out = ws.shows_dir / f"{show.key}.aac"
    with pytest.raises(RenderError, match="decoded to"):
        engine.encode_show(show, stale, out)
    assert not cached.exists() and not out.exists()
    assert engine.analyze(show) == good                           # the next tick re-analyses
    assert engine.encode_show(show, good, out) == render.planned_frames(
        good, engine.settings.clip_pause_samples, engine.extra_frames())
