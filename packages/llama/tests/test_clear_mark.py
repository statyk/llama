"""`llama clear-mark` (bulk-apply spec, "Clearing without re-delivery is only for
voiced destinations, one named show at a time"; plan Task 6). A strict surface:
it writes station manifests and purges library audio. Station dirs live under
tmp_path only."""
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.cli as cli
from llama import campaign, station_mark
from llama.models import Show
from llama.workspace import read_model, write_artifact

from helpers import build_ready, tree_bytes

runner = CliRunner()

SLUG = "gratefuldead-1973-06-10"
LONG_AGO = "2026-01-01T00:00:00.000000Z"
REASON = "changed by the held-backlog fixes: titles"
AUDIO = "01 - Morning Dew.mp3"


@pytest.fixture(autouse=True)
def _no_emcee(monkeypatch):
    """The real check reads `ps`: any emcee process on this machine (another
    session's emcee tests included) would refuse every clear. Tests opt in."""
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\ndelivery_path = "{tmp_path / "inbox"}"\n')
    return str(tmp_path / "config.toml")


def _clear(tmp_path: Path, *extra, name=SLUG):
    return runner.invoke(cli.app, ["--config", _cfg(tmp_path), "clear-mark", name, *extra])


def _voice(out: Path) -> None:
    """What emcee leaves behind in a delivered package (emcee's own encoding)."""
    m = json.loads((out / "manifest.json").read_text())
    m["dj_notes"] = {"file": "dj-notes.md"}
    m["dj_audio"] = {"dir": "dj-audio", "presenter": "phil", "profile": "dead"}
    (out / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    (out / "dj-notes.md").write_text("script")
    (out / "dj-audio").mkdir()
    (out / "dj-audio" / "intro.mp3").write_bytes(b"voice")
    (out / "broadcast.m3u").write_text("#EXTM3U\n")


def _setup(tmp_path: Path, *, voiced=True, marked=True, record=True, processed=True):
    """A delivered show, voiced by emcee, its station copy marked and the library
    re-processed (audio back in `package/audio/`, the record processed)."""
    ws = build_ready(tmp_path, SLUG)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", SLUG])
    assert r.exit_code == 0, r.output
    out = tmp_path / "inbox" / SLUG
    if voiced:
        _voice(out)
    if marked:
        station_mark.write_mark(out, reason=REASON, marked_at=LONG_AGO)
    if record:
        campaign.add_mark(ws, reason=REASON, start_stage="gather", batch="b1", at=LONG_AGO)
    (ws.package_dir / "audio" / AUDIO).write_text("x")      # re-processing re-fetched it
    if record and processed:
        assert campaign.mark_processed(ws, held=False)
    return ws, out


def _record_bytes(ws) -> bytes | None:
    return ws.campaign.read_bytes() if ws.campaign.exists() else None


def _refused(tmp_path: Path, ws, out: Path, expected: str, *extra):
    station = tree_bytes(out)
    rec = _record_bytes(ws)
    library = tree_bytes(ws.dir)
    r = _clear(tmp_path, *extra)
    assert r.exit_code == 1, r.output
    assert expected in r.output, r.output
    assert "mark cleared" not in r.output
    assert tree_bytes(out) == station
    assert _record_bytes(ws) == rec
    assert tree_bytes(ws.dir) == library
    return r


def _edit_library_manifest(ws, edit) -> None:
    mf = ws.package_dir / "manifest.json"
    m = json.loads(mf.read_text())
    edit(m)
    write_artifact(mf, m)


# --- the refusals, in order -----------------------------------------------------

@pytest.mark.parametrize("how", ["bad-json", "no-manifest"])
def test_unreadable_station_copy_refuses(tmp_path: Path, how):
    ws, out = _setup(tmp_path)
    if how == "bad-json":
        (out / "manifest.json").write_text("{not json")
    else:
        (out / "manifest.json").unlink()
    _refused(tmp_path, ws, out, f"{SLUG}: station copy unreadable:")


def test_missing_station_dir_refuses(tmp_path: Path):
    import shutil
    ws, out = _setup(tmp_path)
    shutil.rmtree(out)
    rec = _record_bytes(ws)
    r = _clear(tmp_path)
    assert r.exit_code == 1
    assert f"{SLUG}: station copy unreadable: no directory {out}" in " ".join(
        r.output.split())
    assert not out.exists()
    assert _record_bytes(ws) == rec


def test_no_delivery_path_refuses(tmp_path: Path):
    build_ready(tmp_path, SLUG)
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                "clear-mark", SLUG])
    assert r.exit_code == 1
    assert "no delivery_path in config" in r.output


def test_not_marked_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path, marked=False)
    _refused(tmp_path, ws, out, f"{SLUG}: the station copy is not marked; nothing to clear")


def test_null_mark_counts_as_not_marked(tmp_path: Path):
    ws, out = _setup(tmp_path, marked=False)
    m = json.loads((out / "manifest.json").read_text())
    m["awaiting_fix"] = None
    (out / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    _refused(tmp_path, ws, out, f"{SLUG}: the station copy is not marked; nothing to clear")


def test_unvoiced_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path, voiced=False)
    _refused(tmp_path, ws, out,
             f"{SLUG}: unvoiced destination; re-deliver it instead: llama deliver {SLUG}")


def test_not_processed_since_the_last_mark_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path)
    campaign.add_mark(ws, reason=REASON, start_stage="gather", batch="b2",
                      at="2099-01-01T00:00:00.000000Z")
    _refused(tmp_path, ws, out, f"{SLUG}: awaiting fix; re-process it first")


def test_never_processed_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path, processed=False)
    _refused(tmp_path, ws, out, f"{SLUG}: awaiting fix; re-process it first")


def test_no_campaign_record_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path, record=False)
    _refused(tmp_path, ws, out, f"{SLUG}: awaiting fix; re-process it first")


def test_station_mark_newer_than_the_processing_refuses(tmp_path: Path):
    """Spec: processed after `marked_at` (the station's), not only after the
    record's last mark."""
    ws, out = _setup(tmp_path, marked=False)
    station_mark.write_mark(out, reason=REASON, marked_at="2099-01-01T00:00:00.000000Z")
    _refused(tmp_path, ws, out, f"{SLUG}: awaiting fix; re-process it first")


def test_unreadable_campaign_record_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path)
    ws.campaign.write_text("{not json")
    _refused(tmp_path, ws, out, f"{SLUG}: cannot read campaign.json (")


def test_held_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path)
    show = read_model(ws.show, Show)
    write_artifact(ws.show, show.model_copy(update={"needs_review": True,
                                                    "review_flags": ["x"]}))
    _refused(tmp_path, ws, out, f"{SLUG}: held for review")


def test_awaiting_is_checked_before_held(tmp_path: Path):
    ws, out = _setup(tmp_path, processed=False)
    show = read_model(ws.show, Show)
    write_artifact(ws.show, show.model_copy(update={"needs_review": True}))
    r = _refused(tmp_path, ws, out, f"{SLUG}: awaiting fix; re-process it first")
    assert "held for review" not in r.output


def test_library_changed_since_processing_refuses(tmp_path: Path):
    ws, out = _setup(tmp_path)
    _edit_library_manifest(ws, lambda m: m["briefing"].update(vetted=True))
    _refused(tmp_path, ws, out,
             f"{SLUG}: the library package changed since it was processed; re-process it")


def test_held_processing_has_no_sha_and_refuses(tmp_path: Path):
    """A record processed while held stores no manifest sha: never "equal"."""
    ws, out = _setup(tmp_path, processed=False)
    assert campaign.mark_processed(ws, held=True)
    _refused(tmp_path, ws, out,
             f"{SLUG}: the library package changed since it was processed; re-process it")


def test_differences_refuse_without_accept_change(tmp_path: Path):
    ws, out = _setup(tmp_path, processed=False)
    _edit_library_manifest(ws, lambda m: (m["tracks"][0].update(title="Morning Dew (jam)"),
                                          m["show"].update(venue="Elsewhere")))
    assert campaign.mark_processed(ws, held=False)
    _refused(tmp_path, ws, out,
             f"{SLUG}: the station copy differs: show.venue, tracks.title; "
             "pass --accept-change if the change is cosmetic")


def test_emcee_running_refuses_last(tmp_path: Path, monkeypatch):
    ws, out = _setup(tmp_path)
    monkeypatch.setattr(station_mark, "emcee_running", lambda: ["123 emcee run --yes"])
    _refused(tmp_path, ws, out, "refusing: emcee is running")


def test_emcee_check_comes_after_the_other_refusals(tmp_path: Path, monkeypatch):
    ws, out = _setup(tmp_path, voiced=False)
    monkeypatch.setattr(station_mark, "emcee_running", lambda: ["123 emcee run --yes"])
    r = _refused(tmp_path, ws, out, f"{SLUG}: unvoiced destination")
    assert "emcee is running" not in r.output


def test_failed_station_write_exits_cleanly_and_records_nothing(tmp_path: Path, monkeypatch):
    """A dropped mount mid-write: a clean exit 1 with an error line, no
    traceback, the station untouched, no clear recorded, the library audio kept."""
    ws, out = _setup(tmp_path)

    def boom(*a, **k):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(station_mark, "_swap_in", boom)
    r = _refused(tmp_path, ws, out, f"{SLUG}: could not clear the station mark: ")
    assert "Input/output error" in r.output
    assert isinstance(r.exception, SystemExit)
    assert "Traceback" not in r.output
    assert campaign.read_record(ws).clears == []
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_station_refusal_from_the_writer_exits_cleanly(tmp_path: Path, monkeypatch):
    ws, out = _setup(tmp_path)

    def changed(*a, **k):
        raise station_mark.StationRefused(f"{SLUG}: the station copy changed while llama "
                                          "was rewriting it; nothing written (retry)")

    monkeypatch.setattr(station_mark, "_swap_in", changed)
    r = _refused(tmp_path, ws, out, "nothing written (retry)")
    assert isinstance(r.exception, SystemExit)
    assert campaign.read_record(ws).clears == []


def test_failed_record_write_puts_the_station_mark_back(tmp_path: Path, monkeypatch):
    ws, out = _setup(tmp_path)
    station = tree_bytes(out)

    def boom(ws_, outcome):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(campaign, "add_clear", boom)
    r = _clear(tmp_path)
    assert r.exit_code == 1
    assert isinstance(r.exception, SystemExit)
    text = " ".join(r.output.split())
    assert f"{SLUG}: could not record the clear (" in text
    assert "the station mark was put back" in text
    assert "mark cleared" not in r.output
    assert tree_bytes(out) == station
    assert (ws.package_dir / "audio" / AUDIO).exists()


# --- success ----------------------------------------------------------------------

def test_equal_clears_and_purges(tmp_path: Path):
    ws, out = _setup(tmp_path)
    before = json.loads((out / "manifest.json").read_text())
    voiced_files = {k: v for k, v in tree_bytes(out).items() if k != "manifest.json"}

    r = _clear(tmp_path)

    assert r.exit_code == 0, r.output
    assert "mark cleared; the voicing is kept" in r.output
    assert "change accepted" not in r.output
    after = json.loads((out / "manifest.json").read_text())
    assert "awaiting_fix" not in after
    assert after == {k: v for k, v in before.items() if k != "awaiting_fix"}
    assert after["dj_audio"] == {"dir": "dj-audio", "presenter": "phil", "profile": "dead"}
    assert {k: v for k, v in tree_bytes(out).items() if k != "manifest.json"} == voiced_files
    assert list((ws.package_dir / "audio").iterdir()) == []
    assert "library audio purged (1 B freed)" in r.output
    rec = campaign.read_record(ws)
    assert rec.clears[-1].outcome == "equal"
    assert [p.name for p in out.parent.iterdir()] == [SLUG]


def test_equal_with_accept_change_records_equal(tmp_path: Path):
    ws, out = _setup(tmp_path)
    r = _clear(tmp_path, "--accept-change")
    assert r.exit_code == 0, r.output
    assert "change accepted" not in r.output
    assert campaign.read_record(ws).clears[-1].outcome == "equal"


def test_equal_purge_skip_warns(tmp_path: Path, monkeypatch):
    import llama.catalog as catalog
    ws, out = _setup(tmp_path)
    monkeypatch.setattr(catalog, "purge_package_audio",
                        lambda ws, out: catalog.PurgeResult(skipped="nope"))
    r = _clear(tmp_path)
    assert r.exit_code == 0, r.output
    assert f"warning: kept library audio for {SLUG}: nope" in r.output
    assert (ws.package_dir / "audio" / AUDIO).exists()


def test_equal_purge_partial_warns(tmp_path: Path, monkeypatch):
    import llama.catalog as catalog
    ws, out = _setup(tmp_path)
    monkeypatch.setattr(catalog, "purge_package_audio",
                        lambda ws, out: catalog.PurgeResult(freed=5, warning="could not delete z"))
    r = _clear(tmp_path)
    assert r.exit_code == 0, r.output
    assert f"warning: library audio for {SLUG} partly purged: could not delete z" in r.output


def test_accept_change_clears_and_keeps_library_audio(tmp_path: Path):
    ws, out = _setup(tmp_path, processed=False)
    _edit_library_manifest(ws, lambda m: m["tracks"][0].update(title="Morning Dew (jam)"))
    assert campaign.mark_processed(ws, held=False)
    station_before = json.loads((out / "manifest.json").read_text())

    r = _clear(tmp_path, "--accept-change")

    assert r.exit_code == 0, r.output
    assert "mark cleared; the voicing is kept" in r.output
    assert "change accepted: tracks.title" in r.output
    assert "library audio kept (track lists differ)" in r.output
    after = json.loads((out / "manifest.json").read_text())
    assert after == {k: v for k, v in station_before.items() if k != "awaiting_fix"}
    assert after["tracks"][0]["title"] == "Morning Dew"        # the station copy airs as is
    assert (ws.package_dir / "audio" / AUDIO).read_text() == "x"
    assert campaign.read_record(ws).clears[-1].outcome == "change accepted"


def test_accept_change_with_equal_tracks_still_purges(tmp_path: Path):
    """A venue-only change: the track lists agree, so the purge verifies and runs."""
    ws, out = _setup(tmp_path, processed=False)
    _edit_library_manifest(ws, lambda m: m["show"].update(venue="Elsewhere"))
    assert campaign.mark_processed(ws, held=False)
    r = _clear(tmp_path, "--accept-change")
    assert r.exit_code == 0, r.output
    assert "change accepted: show.venue" in r.output
    assert "library audio purged (1 B freed)" in r.output
    assert "track lists differ" not in r.output
    assert list((ws.package_dir / "audio").iterdir()) == []


def test_processed_then_overruled_still_clears(tmp_path: Path):
    """Task 3's sha refresh: a package build after processing (an overrule's
    `redo --from package`) refreshes the record's sha, so the show still qualifies."""
    ws, out = _setup(tmp_path)
    _edit_library_manifest(ws, lambda m: m["briefing"].update(vetted=True))
    campaign.after_package(ws)        # the last step of every package build

    r = _clear(tmp_path)

    assert r.exit_code == 0, r.output
    assert "mark cleared; the voicing is kept" in r.output
    assert "awaiting_fix" not in json.loads((out / "manifest.json").read_text())
    assert campaign.read_record(ws).clears[-1].outcome == "equal"


def test_clear_mark_takes_the_show_lock(tmp_path: Path, monkeypatch):
    from llama.locks import Locked, file_lock
    ws, out = _setup(tmp_path)
    seen = []
    real = station_mark.clear_mark

    def spy(o):
        with pytest.raises(Locked):
            with file_lock(ws.lock, blocking=False):
                pass
        seen.append(o)
        return real(o)

    monkeypatch.setattr(station_mark, "clear_mark", spy)
    r = _clear(tmp_path)
    assert r.exit_code == 0, r.output
    assert seen == [out]
