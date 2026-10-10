import time

import numpy as np
import pytest

from tests_transmitter.helpers import build_package, make_root, requires_ffmpeg, stereo_sine, write_mp3
from transmitter import analysis, station
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
