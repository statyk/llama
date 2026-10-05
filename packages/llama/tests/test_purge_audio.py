"""`catalog.purge_package_audio` -- deleting a delivered show's library audio
once the station copy is verified, and refusing to delete anything otherwise."""
import json
import os
import shutil
from pathlib import Path

import llama.catalog as catalog
from llama.catalog import purge_package_audio

from helpers import build_ready

AUDIO = "01 - Morning Dew.mp3"


def _delivered(tmp_path: Path, slug: str = "gd-1973-06-10"):
    ws = build_ready(tmp_path, slug)
    out = tmp_path / "inbox" / slug
    shutil.copytree(ws.package_dir, out)
    return ws, out


def test_verified_destination_purges_library_audio(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    r = purge_package_audio(ws, out)
    assert r.skipped is None and r.warning is None
    assert r.freed == 1
    assert list((ws.package_dir / "audio").iterdir()) == []
    assert (ws.package_dir / "manifest.json").exists()
    assert (out / "audio" / AUDIO).exists()


def test_stale_non_manifest_audio_goes_too(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    (ws.package_dir / "audio" / "01 - Old Title.mp3").write_bytes(b"stale")
    r = purge_package_audio(ws, out)
    assert r.skipped is None
    assert r.freed == 6
    assert list((ws.package_dir / "audio").iterdir()) == []


def test_dry_run_deletes_nothing_but_reports_size(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    r = purge_package_audio(ws, out, dry_run=True)
    assert r.skipped is None and r.freed == 1
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_track_missing_at_destination_deletes_nothing(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    (out / "audio" / AUDIO).unlink()
    r = purge_package_audio(ws, out)
    assert r.skipped == f"{AUDIO} missing at destination"
    assert r.freed == 0
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_size_mismatch_deletes_nothing(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    (out / "audio" / AUDIO).write_bytes(b"truncated?")
    r = purge_package_audio(ws, out)
    assert r.skipped == f"{AUDIO} differs in size at destination"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_destination_that_is_the_library_deletes_nothing(tmp_path: Path):
    ws = build_ready(tmp_path, "gd-1973-06-10")
    r = purge_package_audio(ws, ws.package_dir)
    assert r.skipped == f"{AUDIO} at destination is the library copy itself"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_hardlinked_destination_deletes_nothing(tmp_path: Path):
    ws = build_ready(tmp_path, "gd-1973-06-10")
    out = tmp_path / "inbox" / "gd-1973-06-10"
    (out / "audio").mkdir(parents=True)
    shutil.copy(ws.package_dir / "manifest.json", out)
    os.link(ws.package_dir / "audio" / AUDIO, out / "audio" / AUDIO)
    r = purge_package_audio(ws, out)
    assert r.skipped == f"{AUDIO} at destination is the library copy itself"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_already_purged_is_reported(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    assert purge_package_audio(ws, out).skipped is None
    r = purge_package_audio(ws, out)
    assert r.skipped == "already purged" and r.freed == 0


def test_no_audio_dir_is_already_purged(tmp_path: Path):
    ws = build_ready(tmp_path, "gd-1973-06-10", drop_audio=True)
    r = purge_package_audio(ws, tmp_path / "inbox" / "gd-1973-06-10")
    assert r.skipped == "already purged"


TWO = "02 - Other.mp3"


def _delivered_two(tmp_path: Path):
    """A two-track show, delivered: the failed-check cases below hit the
    SECOND track, so a verify-and-delete-as-you-go loop cannot pass them."""
    ws = build_ready(tmp_path, "gd-1973-06-10")
    m = json.loads((ws.package_dir / "manifest.json").read_text())
    m["tracks"].append({"index": 2, "set": "1", "title": "Other", "filename": TWO})
    (ws.package_dir / "manifest.json").write_text(json.dumps(m))
    (ws.package_dir / "audio" / TWO).write_bytes(b"yy")
    out = tmp_path / "inbox" / "gd-1973-06-10"
    shutil.copytree(ws.package_dir, out)
    return ws, out


def test_second_track_missing_at_destination_deletes_nothing(tmp_path: Path):
    ws, out = _delivered_two(tmp_path)
    (out / "audio" / TWO).unlink()
    r = purge_package_audio(ws, out)
    assert r.skipped == f"{TWO} missing at destination"
    assert (ws.package_dir / "audio" / AUDIO).exists()
    assert (ws.package_dir / "audio" / TWO).exists()


def test_second_track_size_mismatch_deletes_nothing(tmp_path: Path):
    ws, out = _delivered_two(tmp_path)
    (out / "audio" / TWO).write_bytes(b"y")
    r = purge_package_audio(ws, out)
    assert r.skipped == f"{TWO} differs in size at destination"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_partially_purged_library_finishes_when_destination_is_whole(tmp_path: Path):
    """A purge interrupted partway leaves some library tracks gone; the next
    attempt verifies against the destination and deletes the rest."""
    ws, out = _delivered_two(tmp_path)
    (ws.package_dir / "audio" / AUDIO).unlink()
    r = purge_package_audio(ws, out)
    assert r.skipped is None and r.freed == 2
    assert list((ws.package_dir / "audio").iterdir()) == []


def test_station_manifest_listing_other_tracks_deletes_nothing(tmp_path: Path):
    """Same sizes are not the same package: a retag (e.g. after `fix
    --set-title`) usually keeps every file's size, so a stale station copy
    could otherwise verify against a newer library package."""
    ws, out = _delivered(tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    m["tracks"][0]["title"] = "Morning Dew (old)"
    (out / "manifest.json").write_text(json.dumps(m))
    r = purge_package_audio(ws, out)
    assert r.skipped == "station copy is a different package version"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_voiced_station_manifest_still_verifies(tmp_path: Path):
    """emcee rewrites only dj_notes/dj_audio; the tracks still match."""
    ws, out = _delivered(tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    m["dj_audio"] = {"dir": "dj-audio"}
    (out / "manifest.json").write_text(json.dumps(m))
    assert purge_package_audio(ws, out).skipped is None


def test_no_station_copy_deletes_nothing(tmp_path: Path):
    ws = build_ready(tmp_path, "gd-1973-06-10")
    r = purge_package_audio(ws, tmp_path / "inbox" / "gd-1973-06-10")
    assert r.skipped == "no station copy"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_missing_station_manifest_deletes_nothing(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    (out / "manifest.json").unlink()
    r = purge_package_audio(ws, out)
    assert r.skipped == "station manifest unreadable"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_oserror_while_verifying_is_a_skip_not_a_raise(tmp_path: Path, monkeypatch):
    ws, out = _delivered(tmp_path)

    def boom(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(os.path, "samefile", boom)
    r = purge_package_audio(ws, out)
    monkeypatch.undo()
    assert r.skipped == "could not verify: denied"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_station_copy_is_flushed_before_anything_is_deleted(tmp_path: Path, monkeypatch):
    ws, out = _delivered_two(tmp_path)
    events = []
    monkeypatch.setattr(catalog, "_flush_to_disk",
                        lambda p: events.append(("flush", p.name)))
    real_unlink = Path.unlink

    def unlink(self, *a, **k):
        events.append(("unlink", self.name))
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert purge_package_audio(ws, out).skipped is None
    monkeypatch.undo()
    assert [e for e in events if e[0] == "flush"] == [("flush", AUDIO), ("flush", TWO)]
    assert events.index(("flush", TWO)) < min(
        i for i, e in enumerate(events) if e[0] == "unlink")


def test_flush_failure_deletes_nothing(tmp_path: Path, monkeypatch):
    ws, out = _delivered(tmp_path)

    def boom(p):
        raise OSError("io error")

    monkeypatch.setattr(catalog, "_flush_to_disk", boom)
    r = purge_package_audio(ws, out)
    assert r.skipped == "could not flush station copy: io error"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_dry_run_does_not_flush(tmp_path: Path, monkeypatch):
    ws, out = _delivered(tmp_path)
    monkeypatch.setattr(catalog, "_flush_to_disk",
                        lambda p: (_ for _ in ()).throw(AssertionError("flushed")))
    assert purge_package_audio(ws, out, dry_run=True).skipped is None


def test_flush_to_disk_really_runs(tmp_path: Path):
    f = tmp_path / "f"
    f.write_bytes(b"z")
    catalog._flush_to_disk(f)


def test_unpackaged_show_deletes_nothing(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    (ws.package_dir / "manifest.json").unlink()
    r = purge_package_audio(ws, out)
    assert r.skipped == "not packaged"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_unreadable_manifest_deletes_nothing(tmp_path: Path):
    ws, out = _delivered(tmp_path)
    (ws.package_dir / "manifest.json").write_text("{not json")
    r = purge_package_audio(ws, out)
    assert r.skipped == "manifest unreadable"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_manifest_with_no_tracks_deletes_nothing(tmp_path: Path):
    """Nothing to verify against is not the same as verified."""
    ws, out = _delivered(tmp_path)
    (ws.package_dir / "manifest.json").write_text('{"tracks": []}')
    r = purge_package_audio(ws, out)
    assert r.skipped == "manifest lists no tracks"
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_delete_failure_is_a_warning_not_a_raise(tmp_path: Path, monkeypatch):
    ws, out = _delivered(tmp_path)

    def boom(self, *a, **k):
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "unlink", boom)
    r = purge_package_audio(ws, out)
    monkeypatch.undo()
    assert r.skipped is None
    assert r.freed == 0
    assert r.warning == f"could not delete {AUDIO}: read-only"
