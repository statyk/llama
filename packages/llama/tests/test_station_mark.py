"""The station mark writer (bulk-apply spec, "The `awaiting_fix` contract";
plan Task 5, Review Focus 1). Station dirs live under tmp_path only."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from llama import catalog, station_mark
from llama.errors import LlamaError
from llama.station_mark import (MARK_KEY, StationRefused, StationUnreadable, clear_mark,
                                destination_voiced, manifest_differences, mark_of, put_back,
                                read_station_manifest, write_mark)

SLUG = "gratefuldead-1973-06-10"
MARK = {"reason": "changed by the held-backlog fixes: titles",
        "marked_at": "2026-10-26T10:00:00.000000Z"}


def _manifest(**over) -> dict:
    m = {"schema_version": 3,
         "show": {"artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
                  "city": "Washington, DC", "context": ""},
         "source": {"performance_id": "GratefulDead/1973-06-10", "identifier": "gd73",
                    "profile": "dead"},
         "tracks": [{"index": 1, "set": "1", "title": "Morning Dew",
                     "filename": "01 - Morning Dew.mp3", "duration_sec": 612.5,
                     "segue": False},
                    {"index": 2, "set": "2", "title": "Café Ü", "filename": "02 - x.mp3",
                     "duration_sec": 300.0, "segue": True}],
         "set_breaks": [{"after_track": 1, "label": "Set 2"}],
         "briefing": {"file": "briefing.md", "json": "briefing.json",
                      "narration": "full", "vetted": True},
         "dj_notes": {"file": "dj-notes.md"},
         "dj_audio": {"dir": "dj-audio", "presenter": "phil", "profile": "dead"},
         "total_duration_sec": 912.5, "set_durations_sec": {"1": 612.5, "2": 300.0}}
    m.update(over)
    return m


def _station(tmp_path: Path, manifest=None, *, raw: bytes | None = None,
             newline: bool = True) -> Path:
    out = tmp_path / "station" / SLUG
    out.mkdir(parents=True)
    if raw is None:
        raw = (json.dumps(manifest if manifest is not None else _manifest(), indent=2,
                          ensure_ascii=False) + ("\n" if newline else "")).encode()
    (out / "manifest.json").write_bytes(raw)
    old = 1_600_000_000
    os.utime(out / "manifest.json", (old, old))
    return out


def _files(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir())


def test_write_mark_adds_only_the_key(tmp_path: Path):
    out = _station(tmp_path)
    mf = out / "manifest.json"
    original_bytes = mf.read_bytes()
    original = json.loads(original_bytes)
    mtime = mf.stat().st_mtime_ns

    before, after = write_mark(out, **MARK)

    assert before == original_bytes
    assert mf.read_bytes() == after
    got = json.loads(after)
    assert got[MARK_KEY] == MARK
    assert {k: v for k, v in got.items() if k != MARK_KEY} == original
    assert list(got)[:-1] == list(original)          # key order kept, mark appended
    assert json.dumps(got["tracks"]) == json.dumps(original["tracks"])
    assert got["dj_audio"] == original["dj_audio"]
    assert got["dj_notes"] == original["dj_notes"]
    assert after.endswith(b"\n")
    assert mf.stat().st_mtime_ns != mtime
    assert mark_of(got) == MARK
    assert _files(out) == ["manifest.json"]          # no temp left

    before2, after2 = clear_mark(out)
    assert before2 == after
    cleared = json.loads(mf.read_bytes())
    assert cleared == original and MARK_KEY not in cleared
    assert list(cleared) == list(original)
    assert mf.read_bytes() == after2 == original_bytes   # round trip, byte for byte
    assert _files(out) == ["manifest.json"]


def test_write_mark_keeps_a_missing_trailing_newline_and_an_existing_key_position(
        tmp_path: Path):
    m = _manifest()
    m = {"awaiting_fix": None, **m}
    out = _station(tmp_path, m, newline=False)
    _, after = write_mark(out, **MARK)
    assert not after.endswith(b"\n")
    got = json.loads(after)
    assert list(got)[0] == MARK_KEY and got[MARK_KEY] == MARK


def test_mark_of():
    assert mark_of({}) is None
    assert mark_of({MARK_KEY: None}) is None
    assert mark_of({MARK_KEY: MARK}) == MARK
    assert mark_of({MARK_KEY: "garbage"}) is not None     # any non-null value is a mark
    assert mark_of({MARK_KEY: {}}) is not None


def test_clear_mark_of_an_unmarked_copy_is_refused_and_untouched(tmp_path: Path):
    out = _station(tmp_path)
    raw = (out / "manifest.json").read_bytes()
    with pytest.raises(StationRefused) as exc:
        clear_mark(out)
    assert str(exc.value) == f"{SLUG}: the station copy is not marked; nothing to clear"
    assert (out / "manifest.json").read_bytes() == raw


@pytest.mark.parametrize("how", ["missing-file", "missing-dir", "invalid-json", "json-list"])
def test_unreadable_or_malformed_manifest_is_refused_and_untouched(tmp_path: Path, how):
    if how == "missing-dir":
        out = tmp_path / "station" / SLUG
        (tmp_path / "station").mkdir()
    elif how == "missing-file":
        out = _station(tmp_path)
        (out / "manifest.json").unlink()
    elif how == "invalid-json":
        out = _station(tmp_path, raw=b"{not json")
    else:
        out = _station(tmp_path, raw=b"[1, 2]\n")
    snapshot = {p.name: p.read_bytes() for p in out.iterdir()} if out.is_dir() else None

    for call in (lambda: read_station_manifest(out), lambda: write_mark(out, **MARK),
                 lambda: clear_mark(out), lambda: destination_voiced(out)):
        with pytest.raises(StationUnreadable) as exc:
            call()
        text = str(exc.value)
        assert text.startswith(f"{SLUG}: station copy unreadable: "), text
        assert "\n" not in text
        assert isinstance(exc.value, StationRefused) and isinstance(exc.value, LlamaError)
        after = {p.name: p.read_bytes() for p in out.iterdir()} if out.is_dir() else None
        assert after == snapshot
    assert not out.exists() or how != "missing-dir"


def test_destination_voiced(tmp_path: Path):
    out = _station(tmp_path)
    assert destination_voiced(out) is True
    (out / "manifest.json").write_text(json.dumps(_manifest(dj_audio=None)))
    assert destination_voiced(out) is False
    nodir = tmp_path / "station" / "nowhere"
    with pytest.raises(StationUnreadable):
        destination_voiced(nodir)


def test_write_mark_detects_a_concurrent_rewrite(tmp_path: Path, monkeypatch):
    """Review Focus 1, before the rename: emcee rewrites `dj_audio` after the
    read and before the rename. The byte re-read catches it: nothing written,
    no temp left, retryable refusal; the file keeps emcee's bytes."""
    out = _station(tmp_path)
    mf = out / "manifest.json"
    theirs = {}
    real = catalog._flush_to_disk

    def flush_then_emcee(path):
        real(path)
        if path.parent == out and path.name != "manifest.json":
            m = json.loads(mf.read_text())
            m["dj_audio"] = {"dir": "dj-audio", "presenter": "kurt"}
            theirs["bytes"] = (json.dumps(m, indent=2) + "\n").encode()
            mf.write_bytes(theirs["bytes"])

    monkeypatch.setattr(catalog, "_flush_to_disk", flush_then_emcee)
    with pytest.raises(StationRefused) as exc:
        write_mark(out, **MARK)
    assert not isinstance(exc.value, StationUnreadable)
    assert str(exc.value).startswith(f"{SLUG}: ")
    assert mf.read_bytes() == theirs["bytes"]
    assert MARK_KEY not in json.loads(mf.read_bytes())
    assert _files(out) == ["manifest.json"]


def test_write_mark_temp_is_removed_when_the_flush_fails(tmp_path: Path, monkeypatch):
    out = _station(tmp_path)
    raw = (out / "manifest.json").read_bytes()

    def boom(path):
        raise OSError("flush refused")

    monkeypatch.setattr(catalog, "_flush_to_disk", boom)
    with pytest.raises(OSError):
        write_mark(out, **MARK)
    assert (out / "manifest.json").read_bytes() == raw
    assert _files(out) == ["manifest.json"]


def test_write_mark_detects_a_rewrite_after_the_rename(tmp_path: Path, monkeypatch):
    """Review Focus 1, after the rename: emcee rewrites `dj_audio` right after
    the rename. The post-write re-read catches it; the file no longer holds this
    call's bytes, so `before` is never written over emcee's content."""
    out = _station(tmp_path)
    mf = out / "manifest.json"
    theirs = {}
    real = os.replace

    def replace_then_emcee(src, dst):
        real(src, dst)
        if Path(dst) == mf and not theirs:
            m = json.loads(mf.read_text())
            m["dj_audio"] = {"dir": "dj-audio", "presenter": "kurt"}
            theirs["bytes"] = (json.dumps(m, indent=2) + "\n").encode()
            mf.write_bytes(theirs["bytes"])

    monkeypatch.setattr(station_mark.os, "replace", replace_then_emcee)
    with pytest.raises(StationRefused) as exc:
        write_mark(out, **MARK)
    assert not isinstance(exc.value, StationUnreadable)
    assert mf.read_bytes() == theirs["bytes"]
    assert _files(out) == ["manifest.json"]


def test_write_mark_puts_back_before_when_the_reread_mismatches_its_own_bytes(
        tmp_path: Path, monkeypatch):
    """A post-write re-read that disagrees while the file still holds this
    call's bytes: `before` goes back, and the call refuses."""
    out = _station(tmp_path)
    mf = out / "manifest.json"
    original = mf.read_bytes()
    real = station_mark._read
    calls = {"n": 0}

    def flaky_read(o):
        calls["n"] += 1
        raw, d = real(o)
        if calls["n"] == 2:          # the post-rename re-read (1: the first read)
            d = dict(d, dj_audio={"dir": "transient"})
        return raw, d

    monkeypatch.setattr(station_mark, "_read", flaky_read)
    with pytest.raises(StationRefused):
        write_mark(out, **MARK)
    assert mf.read_bytes() == original
    assert _files(out) == ["manifest.json"]


def test_put_back_requires_the_expected_sha(tmp_path: Path):
    out = _station(tmp_path)
    mf = out / "manifest.json"
    before, after = write_mark(out, **MARK)

    with pytest.raises(StationRefused):
        put_back(out, expect_sha256=hashlib.sha256(before).hexdigest(), data=b"{}")
    assert mf.read_bytes() == after
    assert _files(out) == ["manifest.json"]

    put_back(out, expect_sha256=hashlib.sha256(after).hexdigest(), data=before)
    assert mf.read_bytes() == before
    assert _files(out) == ["manifest.json"]

    missing = tmp_path / "station" / "nowhere"
    with pytest.raises(StationUnreadable):
        put_back(missing, expect_sha256="0" * 64, data=before)


def test_manifest_differences():
    lib = _manifest(dj_notes=None, dj_audio=None,
                    briefing={"file": "briefing.md", "json": "briefing.json",
                              "narration": "vague", "vetted": False})
    lib.pop("dj_notes")
    station = _manifest(awaiting_fix=MARK)
    assert manifest_differences(lib, station) == []

    moved = json.loads(json.dumps(station))
    moved["tracks"][1]["set"] = "1"
    assert manifest_differences(lib, moved) == ["tracks.set"]

    longer = json.loads(json.dumps(station))
    longer["tracks"][0]["duration_sec"] = 613.0
    assert manifest_differences(lib, longer) == ["tracks.duration_sec"]

    other = json.loads(json.dumps(station))
    other["source"]["identifier"] = "gd73b"
    other["show"]["venue"] = "Elsewhere"
    other["set_breaks"] = []
    other["tracks"][0]["segue"] = True
    other["tracks"][1]["title"] = "Something"
    assert manifest_differences(lib, other) == [
        "source.identifier", "show.venue", "tracks.title", "tracks.segue", "set_breaks"]

    shorter = json.loads(json.dumps(station))
    shorter["tracks"] = shorter["tracks"][:1]
    assert manifest_differences(lib, shorter) == [
        "tracks.filename", "tracks.duration_sec", "tracks.title", "tracks.set",
        "tracks.segue"]
    assert station_mark.COMPARED == (
        "source.identifier", "show.venue", "show.city", "show.date", "tracks.filename",
        "tracks.duration_sec", "tracks.title", "tracks.set", "tracks.segue", "set_breaks")
