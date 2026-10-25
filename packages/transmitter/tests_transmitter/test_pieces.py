from pathlib import Path

from transmitter import aacenc
from transmitter.pieces import estimate_frames
from transmitter.station import Entry, Show


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
