import time

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
    # DJ clips: mono 24 kHz, like emcee's -- and LOUD, measuring ~-7.3 LUFS
    # against the tracks' ~-14.8. Quiet clips would fall under ebur128's
    # relative gate, so clip PCM leaking into the tracks meter would move the
    # tracks reading by only ~0.3 dB; loud ones move it ~4.5 dB (to ~-10.3).
    if i in (0, 99):
        write_mp3(path, stereo_sine(1.5, 300.0, 0.7, rate=24_000)[:, 0], rate=24_000)
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
    assert len(clips) == 2
    assert all(f.i_lufs is not None and f.i_lufs > a.tracks_i_lufs + 5 for f in clips)
    # A stereo 550/660 Hz sine at amplitude 0.2 (-14.0 dBFS peak) measures
    # -14.8 LUFS on ffmpeg 5.1 and 8.1 (BS.1770's -0.691 offset plus K-weighting
    # below 1 kHz). Clip PCM in the tracks meter would read ~-10.3.
    assert a.tracks_i_lufs == pytest.approx(-14.8, abs=0.5)
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


@requires_ffmpeg
@pytest.mark.parametrize("bad", [
    lambda key: "",                                    # zero-length (power loss mid-write)
    lambda key: "[]",                                  # valid JSON, not an object
    lambda key: "[1]",                                 # ... and not falsy either
    lambda key: '{"version": 1, "key": "%s", "slug": "s", "files": [{"bogus": 1}], '
                '"tracks_i_lufs": null, "tracks_tp_dbfs": null, "meta": {}}' % key,
], ids=["empty", "empty-list", "list", "wrong-shape"])
def test_a_corrupt_cache_file_is_a_miss_and_is_rewritten(tmp_path, monkeypatch, bad):
    pkg = build_package(make_root(tmp_path), tracks=1, audio=_tone_writer)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f"{show.key}.json").write_text(bad(show.key))
    assert analysis.load_cached(cache, show.key) is None

    decoded = []
    real = analysis.iter_decode

    def counting(path, ffmpeg="ffmpeg"):
        decoded.append(path)
        return real(path, ffmpeg)

    monkeypatch.setattr(analysis, "iter_decode", counting)
    result = analysis.load_or_analyze(cache, show)
    assert len(decoded) == len(show.entries)
    assert analysis.load_cached(cache, show.key) == result
