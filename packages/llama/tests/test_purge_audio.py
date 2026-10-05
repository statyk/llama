"""`catalog.purge_package_audio` -- deleting a delivered show's library audio
once the station copy is verified, and refusing to delete anything otherwise."""
import os
import shutil
from pathlib import Path

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


def test_partially_purged_library_finishes_when_destination_is_whole(tmp_path: Path):
    """A purge interrupted partway leaves some library tracks gone; the next
    attempt verifies against the destination and deletes the rest."""
    ws, out = _delivered(tmp_path)
    (ws.package_dir / "audio" / "02 - Other.mp3").write_bytes(b"yy")
    shutil.copy(ws.package_dir / "audio" / "02 - Other.mp3", out / "audio")
    (ws.package_dir / "audio" / AUDIO).unlink()
    r = purge_package_audio(ws, out)
    assert r.skipped is None and r.freed == 2
    assert list((ws.package_dir / "audio").iterdir()) == []


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
