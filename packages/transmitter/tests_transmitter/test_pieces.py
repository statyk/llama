import json
from pathlib import Path

import pytest

from transmitter import aacenc, station
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.errors import RenderError
from transmitter.pieces import (LengthCache, Piece, build_pool, estimate_frames,
                                scan_delivered)
from transmitter.render import planned_frames
from transmitter.station import Entry, Show
from tests_transmitter.helpers import build_package, make_root


def _show(tmp_path, kinds, total=100.0):
    entries = tuple(Entry(f"f{i}", k, f"t{i}") for i, k in enumerate(kinds))
    meta = {"total_duration_sec": total, "sizes": {e.path: 1000 + i for i, e in enumerate(entries)}}
    if total is None:
        meta.pop("total_duration_sec")
    return Show("s", tmp_path, entries, "k", meta)


def _expect(samples, extra=1):
    return aacenc.frames_for(aacenc.pad_to_frame(samples), extra)


def test_estimate_frames_counts_tracks_clips_and_pauses(tmp_path):
    show = _show(tmp_path, ["clip", "track", "track", "clip"])
    got = estimate_frames(show, pause_samples=33075, extra=1, clip_seconds=lambda p, size: 5.0)
    assert got == _expect(round(110 * 44100) + 2 * 33075)


def test_estimate_frames_passes_the_scanned_size(tmp_path):
    show = _show(tmp_path, ["clip", "track"])
    seen = []
    estimate_frames(show, pause_samples=0, extra=1, clip_seconds=lambda p, size: seen.append((p, size)) or 1.0)
    assert seen == [(Path(tmp_path) / "f0", 1000)]


def test_unreadable_clip_uses_the_fallback(tmp_path):
    show = _show(tmp_path, ["track", "clip"])
    got = estimate_frames(show, pause_samples=0, extra=1, clip_seconds=lambda p, size: None)
    assert got == _expect(round(220 * 44100))


def test_missing_total_duration_counts_zero(tmp_path):
    show = _show(tmp_path, ["clip"], total=None)
    got = estimate_frames(show, pause_samples=0, extra=1, clip_seconds=lambda p, size: 2.0)
    assert got == _expect(round(2 * 44100))


PAUSE = 33075


def _write_cache(cache, show, samples=44100 * 10):
    cache.mkdir(parents=True, exist_ok=True)
    an = ShowAnalysis(key=show.key, slug=show.slug,
                      files=tuple(FileAnalysis(e.path, e.kind, e.title, samples) for e in show.entries),
                      tracks_i_lufs=-20.0, tracks_tp_dbfs=-3.0, meta={})
    (cache / f"{show.key}.json").write_text(json.dumps(an.to_json()))
    return an


def _clip(tmp_path, name="id-a.mp3", key="ck", meta=None):
    (tmp_path / name).write_bytes(b"x" * 10)
    m = {"role": "id", "ann_id": None, "sizes": {name: 10}}
    m.update(meta or {})
    return Show(Path(name).stem, tmp_path, (Entry(name, "clip", "Station ID"),), key, m)


def test_cached_analysis_gives_an_exact_length(tmp_path):
    show = _show(tmp_path, ["track", "track"])
    an = _write_cache(tmp_path / "cache", show)
    lc = LengthCache(tmp_path / "cache", PAUSE, 1)
    assert lc.length(show) == (planned_frames(an, PAUSE, 1), True)


def test_uncached_show_is_estimated_and_marked(tmp_path):
    show = _show(tmp_path, ["track", "track"])
    lc = LengthCache(tmp_path / "cache", PAUSE, 1)
    assert lc.length(show) == (estimate_frames(show, pause_samples=PAUSE, extra=1), False)


def test_no_cache_dir_never_looks_at_the_cache(tmp_path):
    show = _show(tmp_path, ["track"])
    _write_cache(tmp_path / "cache", show)
    assert LengthCache(None, PAUSE, 1).length(show)[1] is False


def test_mark_exact_overrides_the_estimate(tmp_path):
    show = _show(tmp_path, ["track"])
    lc = LengthCache(tmp_path / "cache", PAUSE, 1)
    assert lc.length(show)[1] is False
    lc.mark_exact(show.key, 1234)
    assert lc.length(show) == (1234, True)


def test_vanished_clip_counts_the_fallback(tmp_path):
    show = _show(tmp_path, ["track", "clip"])    # f1 does not exist on disk
    lc = LengthCache(None, 0, 1)
    got, exact = lc.length(show)
    assert not exact
    assert got == _expect(round(220 * 44100))


def test_build_pool_analyses_every_clip(tmp_path):
    show = _show(tmp_path / "pkg", ["track"])
    clips = [_clip(tmp_path, "id-a.mp3", "k1"), _clip(tmp_path, "id-b.mp3", "k2")]
    seen = []
    pieces, dropped = build_pool([show], clips, lengths=LengthCache(tmp_path / "c", PAUSE, 1),
                                 clip_dir="interstitials",
                                 analyze_clip=lambda c: seen.append(c.key) or 77)
    assert seen == ["k1", "k2"] and dropped == []
    assert [p.kind for p in pieces] == ["show", "interstitial", "interstitial"]
    assert [(p.frames, p.exact, p.dir) for p in pieces[1:]] == [(77, True, "interstitials")] * 2
    assert pieces[0].dir == "pkg" and pieces[0].exact is False


def test_build_pool_skips_analysis_of_known_clips(tmp_path):
    clip = _clip(tmp_path)
    lc = LengthCache(None, PAUSE, 1)
    lc.mark_exact(clip.key, 5)
    pieces, _ = build_pool([], [clip], lengths=lc, clip_dir="i", analyze_clip=lambda c: 1 / 0)
    assert pieces[0].frames == 5 and pieces[0].exact


def test_build_pool_returns_the_clips_it_dropped(tmp_path):
    good, bad = _clip(tmp_path, "id-a.mp3", "k1"), _clip(tmp_path, "id-b.mp3", "k2")
    err = RenderError("boom")

    def analyze(c):
        if c is bad:
            raise err
        return 9

    pieces, dropped = build_pool([], [good, bad], lengths=LengthCache(None, PAUSE, 1),
                                 clip_dir="i", analyze_clip=analyze)
    assert [p.key for p in pieces] == ["k1"]
    assert dropped == [(bad, err)]


def test_build_pool_read_only_never_analyses(tmp_path):
    clip = _clip(tmp_path)
    cache = tmp_path / "cache"
    pieces, dropped = build_pool([], [clip], lengths=LengthCache(cache, PAUSE, 1), clip_dir="i",
                                 analyze_clip=lambda c: 1 / 0, read_only=True)
    assert dropped == [] and pieces[0].exact is False
    assert not cache.exists()


def test_build_pool_needs_analyze_clip_unless_read_only(tmp_path):
    with pytest.raises(ValueError):
        build_pool([], [], lengths=LengthCache(None, 0, 1), clip_dir="i")


def test_piece_properties_from_meta(tmp_path):
    meta = {"artist": "Band", "date": "2005-11-01", "voiced_profile": "indie", "total_duration_sec": 1.0}
    show = Show("band-2005-11-01", tmp_path, (), "k", meta)
    p = Piece("show", show, "band-2005-11-01", 10, False)
    assert (p.slug, p.key, p.package, p.artist, p.date, p.year, p.month_day, p.profile, p.role, p.ann_id) == \
        ("band-2005-11-01", "k", "band-2005-11-01", "Band", "2005-11-01", 2005, "11-01", "indie", "show", None)
    c = Piece("interstitial", _clip(tmp_path, meta={"role": "ann", "ann_id": "x"}), "i", 1, True)
    assert (c.package, c.role, c.ann_id, c.date, c.year, c.month_day) == (None, "ann", "x", None, None, None)


def test_scan_delivered_includes_unvoiced_with_allowance(tmp_path):
    root = make_root(tmp_path)
    pkg = build_package(root, voiced=False)
    m = json.loads((pkg / "manifest.json").read_text())
    m["total_duration_sec"] = 3600
    (pkg / "manifest.json").write_text(json.dumps(m))
    (pieces,) = scan_delivered(root, now_s=1e12, quiet_s=0, pause_samples=PAUSE, extra=1)
    assert pieces.kind == "show" and pieces.exact is False and pieces.dir == pkg.name
    assert pieces.key.startswith("m-") and len(pieces.key) == 22
    assert pieces.frames == _expect(round(3840 * 44100))
    assert pieces.artist == "Band" and pieces.year == 2005


def test_scan_delivered_uses_the_file_set_key_of_an_eligible_package(tmp_path):
    root = make_root(tmp_path)
    pkg = build_package(root, "band-2005-11-02")
    build_package(root, "old-1990-01-01", voiced=False)
    (root / ".hidden").mkdir()
    (root / "junk").mkdir()
    (root / "junk" / "manifest.json").write_text('{"schema_version": 2}')
    pieces = scan_delivered(root, now_s=4e9, quiet_s=0, pause_samples=PAUSE, extra=1)
    assert sorted(p.slug for p in pieces) == ["band-2005-11-02", "old-1990-01-01"]
    got = next(p for p in pieces if p.slug == "band-2005-11-02")
    show = station.evaluate(pkg, now_s=4e9, quiet_s=0)
    assert got.key == show.key and not got.key.startswith("m-")
    assert got.frames == estimate_frames(show, pause_samples=PAUSE, extra=1) and got.exact is False
