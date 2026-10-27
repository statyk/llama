"""Per-batch library snapshots and the guarded restore (bulk-apply spec "Undo",
strict surface 4; plan Task 11)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from llama import batch_snapshot
from llama.errors import LlamaError

A = "gd1977-05-08"
B = "gd1972-08-27"

METADATA = {
    "selection.json": b'{"identifier": "x"}\n',
    "show.json": b'{"title": "before"}\n',
    "overrides.json": b'{"titles": {}}\n',
    "campaign.json": b'{"clears": []}\n',
    "reuse-anchor.json": b'{"tracks": []}\n',
    "briefing.md": b"# before\n",
    "package/manifest.json": b'{"tracks": ["01.mp3"]}\n',
    "package/briefing.md": b"# before\n",
}


def _make_show(root: Path, slug: str) -> Path:
    d = root / "shows" / slug
    for rel, data in METADATA.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (d / "package" / "audio").mkdir(parents=True)
    (d / "package" / "audio" / "01.mp3").write_bytes(b"AUDIO" * 100)
    (d / ".lock").write_bytes(b"")
    (d / ".txn" / "files").mkdir(parents=True)
    (d / ".txn" / "files" / "show.json").write_bytes(b"stale txn")
    (d / ".audio-aside").mkdir()
    (d / ".audio-aside" / "02.mp3").write_bytes(b"aside")
    return d


def _make_station(station: Path, slug: str, data: bytes = b'{"tracks": ["01.mp3"]}\n') -> Path:
    out = station / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_bytes(data)
    return out


def _tree(d: Path) -> dict[str, tuple[bytes, int]]:
    """Every file under `d` (dot dirs included) -> (bytes, mtime_ns)."""
    out = {}
    if not d.exists():
        return out
    for p in sorted(d.rglob("*")):
        if p.is_file():
            out[p.relative_to(d).as_posix()] = (p.read_bytes(), p.stat().st_mtime_ns)
    return out


def _metadata(d: Path) -> dict[str, bytes]:
    """The files a snapshot covers, by relpath -> bytes."""
    return {rel: data for rel, (data, _) in _tree(d).items()
            if not (rel.startswith("package/audio/") or rel.startswith(".txn/")
                    or rel.startswith(".audio-aside/") or rel == ".lock")}


def _batch_write(d: Path) -> None:
    """A reapply-style rewrite: show.json, the package manifest and briefing change,
    notes.json and a new package file are created."""
    (d / "show.json").write_bytes(b'{"title": "after"}\n')
    (d / "package" / "manifest.json").write_bytes(b'{"tracks": ["01.mp3", "02.mp3"]}\n')
    (d / "package" / "briefing.md").write_bytes(b"# after\n")
    (d / "notes.json").write_bytes(b'{"gather": []}\n')
    (d / "package" / "extra.m3u").write_bytes(b"#EXTM3U\n")
    (d / "package" / "audio" / "02.mp3").write_bytes(b"NEW" * 50)


@pytest.fixture
def lib(tmp_path: Path):
    root = tmp_path / "llama"
    station = tmp_path / "station"
    station.mkdir()
    a, b = _make_show(root, A), _make_show(root, B)
    _make_station(station, A)                    # B has no station copy
    snap = tmp_path / "batch" / "snapshot"
    return root, station, snap, a, b


def test_take_copies_metadata_only_and_verifies(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A, B], station_root=station)

    m = json.loads((snap / "manifest.json").read_bytes())
    assert m["slugs"] == [A, B]
    assert set(m) >= {"created_at", "slugs", "files", "station"}
    want = {f"{slug}/{rel}": hashlib.sha256(data).hexdigest()
            for slug in (A, B) for rel, data in METADATA.items()}
    assert m["files"] == want                       # audio, .txn, .audio-aside, .lock excluded
    assert f"{A}/campaign.json" in m["files"] and f"{A}/reuse-anchor.json" in m["files"]
    for key in want:
        assert (snap / "shows" / key).read_bytes() == METADATA[key.split("/", 1)[1]]
    assert not (snap / "shows" / A / "package" / "audio").exists()
    assert not (snap / "shows" / A / ".txn").exists()
    assert not (snap / "shows" / A / ".audio-aside").exists()
    assert not (snap / "shows" / A / ".lock").exists()
    assert m["station"] == {
        A: hashlib.sha256((station / A / "manifest.json").read_bytes()).hexdigest(),
        B: None}
    assert batch_snapshot.verify(snap) == []

    (snap / "shows" / A / "show.json").write_bytes(b"tampered")
    problems = batch_snapshot.verify(snap)
    assert problems and any(f"{A}/show.json" in p for p in problems)


def test_partial_snapshot_is_removed_on_failure(lib, monkeypatch):
    root, station, snap, a, b = lib
    real = batch_snapshot._write_copy
    calls = []

    def flaky(dst: Path, data: bytes) -> None:
        calls.append(dst)
        if len(calls) == 5:
            raise OSError("disk full")
        real(dst, data)

    monkeypatch.setattr(batch_snapshot, "_write_copy", flaky)
    with pytest.raises(LlamaError, match="disk full"):
        batch_snapshot.take(snap, root, [A, B], station_root=station)
    assert not snap.exists()

    # A copy that does not read back as its source fails too, and is removed.
    def corrupting(dst: Path, data: bytes) -> None:
        real(dst, data + b"x" if dst.name == "overrides.json" else data)

    monkeypatch.setattr(batch_snapshot, "_write_copy", corrupting)
    with pytest.raises(LlamaError, match="overrides.json"):
        batch_snapshot.take(snap, root, [A, B], station_root=station)
    assert not snap.exists()

    # A missing show fails the whole snapshot.
    monkeypatch.setattr(batch_snapshot, "_write_copy", real)
    with pytest.raises(LlamaError, match="gd1999-01-01"):
        batch_snapshot.take(snap, root, [A, "gd1999-01-01"], station_root=station)
    assert not snap.exists()
    assert not (root / "shows" / "gd1999-01-01").exists()

    # An existing directory is never taken over, nor removed.
    snap.mkdir(parents=True)
    (snap / "keep").write_bytes(b"k")
    with pytest.raises(LlamaError, match="exists"):
        batch_snapshot.take(snap, root, [A], station_root=station)
    assert (snap / "keep").read_bytes() == b"k"


def test_restore_rewinds_a_batch_write(lib):
    root, station, snap, a, b = lib
    before = _metadata(a)
    station_before = _tree(station)
    batch_snapshot.take(snap, root, [A, B], station_root=station)

    _batch_write(a)
    batch_snapshot.record_after(snap, A, root, station_root=station)

    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 slugs={A}, echo=lambda s: None)
    assert out == [(A, "restored; package/audio emptied")]
    assert _metadata(a) == before                   # byte-identical, created files gone
    assert not (a / "notes.json").exists()
    assert not (a / "package" / "extra.m3u").exists()
    assert list((a / "package" / "audio").iterdir()) == []
    assert _tree(station) == station_before         # the station is never written
    assert (a / ".audio-aside" / "02.mp3").exists()  # outside the snapshot: not touched

    again = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                   slugs={A}, echo=lambda s: None)
    assert again == [(A, "already restored")]


def test_restore_keeps_audio_when_the_package_manifest_is_unchanged(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A], station_root=station)
    (a / "overrides.json").write_bytes(b'{"titles": {}, "overrules": []}\n')
    batch_snapshot.record_after(snap, A, root, station_root=station)

    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 echo=lambda s: None)
    assert out == [(A, "restored")]
    assert (a / "overrides.json").read_bytes() == METADATA["overrides.json"]
    assert (a / "package" / "audio" / "01.mp3").exists()


def test_restore_refuses_a_later_library_change(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A], station_root=station)
    _batch_write(a)
    batch_snapshot.record_after(snap, A, root, station_root=station)
    (a / "overrides.json").write_bytes(b'{"titles": {"01.mp3": "Bertha"}}\n')
    after = _tree(a)

    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 echo=lambda s: None)
    assert out == [(A, "refused: library files changed after the batch: overrides.json")]
    assert _tree(a) == after


def test_restore_refuses_a_changed_station_manifest(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A], station_root=station)
    _batch_write(a)
    batch_snapshot.record_after(snap, A, root, station_root=station)
    (station / A / "manifest.json").write_bytes(b'{"tracks": ["01.mp3"], "dj_audio": {}}\n')
    after, station_after = _tree(a), _tree(station)

    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 echo=lambda s: None)
    assert out == [(A, "refused: station manifest changed after the batch "
                       "(re-delivered or re-voiced): roll forward instead")]
    assert _tree(a) == after
    assert _tree(station) == station_after


def test_restore_dry_run_writes_nothing(lib, tmp_path):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A, B], station_root=station)
    _batch_write(a)
    batch_snapshot.record_after(snap, A, root, station_root=station)
    everything = _tree(tmp_path)
    lines = []

    out = batch_snapshot.restore(snap, root, station_root=station, apply=False,
                                 echo=lines.append)
    assert out == [(A, "would restore; would empty package/audio"), (B, "untouched")]
    assert lines == [f"{A}: would restore; would empty package/audio", f"{B}: untouched"]
    assert _tree(tmp_path) == everything


def test_untouched_show_is_left_alone(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A, B], station_root=station)
    _batch_write(a)
    batch_snapshot.record_after(snap, A, root, station_root=station)
    b_before = _tree(b)

    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 echo=lambda s: None)
    assert out == [(A, "restored; package/audio emptied"), (B, "untouched")]
    assert _tree(b) == b_before

    # A show the batch recorded no write for, changed anyway: refused, left as it is.
    (b / "show.json").write_bytes(b'{"title": "someone else"}\n')
    b_changed = _tree(b)
    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 slugs={B}, echo=lambda s: None)
    assert out == [(B, "refused: changed, and this batch recorded no write for it")]
    assert _tree(b) == b_changed

    # Library files back as they were, but a station copy appeared since: refused too.
    (b / "show.json").write_bytes(METADATA["show.json"])
    _make_station(station, B)
    b_changed, station_now = _tree(b), _tree(station)
    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 slugs={B}, echo=lambda s: None)
    assert out == [(B, "refused: changed, and this batch recorded no write for it")]
    assert _tree(station) == station_now
    assert _tree(b) == b_changed


def test_seal_records_every_show_and_record_after_needs_a_snapshot_slug(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A, B], station_root=station)
    _batch_write(a)
    batch_snapshot.seal(snap, root, station_root=station)

    rows = [json.loads(line) for line in (snap / "after.jsonl").read_text().splitlines()]
    assert [r["slug"] for r in rows] == [A, B]
    assert set(rows[0]) == {"slug", "files", "station", "at"}
    assert rows[0]["files"]["notes.json"] == hashlib.sha256(b'{"gather": []}\n').hexdigest()
    assert rows[1]["station"] is None
    out = batch_snapshot.restore(snap, root, station_root=station, apply=True,
                                 echo=lambda s: None)
    assert out == [(A, "restored; package/audio emptied"), (B, "untouched")]  # sealed unchanged

    with pytest.raises(LlamaError, match="not in"):
        batch_snapshot.record_after(snap, "gd1999-01-01", root, station_root=station)


def test_restore_refuses_a_snapshot_that_does_not_verify(lib):
    root, station, snap, a, b = lib
    batch_snapshot.take(snap, root, [A], station_root=station)
    _batch_write(a)
    batch_snapshot.record_after(snap, A, root, station_root=station)
    (snap / "shows" / A / "show.json").write_bytes(b"tampered")
    after = _tree(a)
    with pytest.raises(LlamaError, match="does not verify"):
        batch_snapshot.restore(snap, root, station_root=station, apply=True,
                               echo=lambda s: None)
    assert _tree(a) == after
