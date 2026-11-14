"""Task 9 of the junk-tag-drop plan: the optional manifest list `dropped_tracks`
(schema stays v3). The manifest is the only contract between llama, emcee and
transmitter, so the no-drop bytes and the station readers are pinned here."""
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.cli as cli
from llama import audio_reuse, campaign, station_mark
from llama.junk_titles import REASON
from llama.manifest import build_manifest
from llama.models import DroppedTrack, Manifest, ManifestBriefing
from llama.stages.package import run_package
from llama.workspace import write_artifact

from helpers import build_ready, tree_bytes
from test_stage_package import StubIA, make_show, setup

runner = CliRunner()

SLUG = "gratefuldead-1973-06-10"
LONG_AGO = "2026-01-01T00:00:00.000000Z"
MARK_REASON = "changed by the held-backlog fixes: titles"
GOLDEN = Path(__file__).parent / "data_manifest_no_drop_golden.json"

DROP_ROW = {"filename": "gd79-12-05d1t01.mp3", "reasons": [REASON], "duration_sec": 280.0,
            "title": "Tuning", "set": "1", "after_track": 0}
DROP_JSON = {"title": "Tuning", "duration_sec": 280.0, "set": "1", "after_track": 0,
             "source_file": "gd79-12-05d1t01.mp3", "reason": "junk title"}


def _manifest(pkg: Path) -> dict:
    return json.loads((pkg / "manifest.json").read_text())


def test_package_writes_dropped_tracks(tmp_path: Path):
    sws, show = setup(tmp_path)
    show = show.model_copy(update={"excluded_files": [
        {"filename": "x.mp3", "reasons": ["too short"], "duration_sec": 5.0},
        DROP_ROW]})
    write_artifact(sws.show, show)
    pkg = run_package(sws, StubIA(), show, profile="prime-dead")
    m = _manifest(pkg)
    assert m["dropped_tracks"] == [DROP_JSON]
    assert m["schema_version"] == 3
    # Only the dropped_tracks key is new; every other field is as for a no-drop show.
    assert [k for k in m if k != "dropped_tracks"] == list(json.loads(GOLDEN.read_text()))


def test_package_without_drops_omits_key(tmp_path: Path):
    sws, show = setup(tmp_path)
    show = show.model_copy(update={"excluded_files": [
        {"filename": "x.mp3", "reasons": ["too short"], "duration_sec": 5.0}]})
    write_artifact(sws.show, show)
    pkg = run_package(sws, StubIA(), show, profile="prime-dead")
    assert "dropped_tracks" not in _manifest(pkg)
    # Bytes captured from the pre-change code path (HEAD def2cf61) for this fixture.
    assert (pkg / "manifest.json").read_bytes() == GOLDEN.read_bytes()


def test_manifest_reads_absent_null_empty_and_list():
    base = json.loads(GOLDEN.read_text())
    assert Manifest.model_validate(base).dropped_tracks is None
    assert Manifest.model_validate({**base, "dropped_tracks": None}).dropped_tracks is None
    assert Manifest.model_validate({**base, "dropped_tracks": []}).dropped_tracks == []
    got = Manifest.model_validate({**base, "dropped_tracks": [DROP_JSON]}).dropped_tracks
    assert got == [DroppedTrack(**DROP_JSON)]


def test_dropped_track_duration_none(tmp_path: Path):
    sws, show = setup(tmp_path)
    row = {**DROP_ROW, "duration_sec": None}
    show = show.model_copy(update={"excluded_files": [row]})
    write_artifact(sws.show, show)
    pkg = run_package(sws, StubIA(), show)
    assert _manifest(pkg)["dropped_tracks"][0]["duration_sec"] is None
    assert DroppedTrack.model_validate({k: v for k, v in DROP_JSON.items()
                                        if k != "duration_sec"}).duration_sec is None


def test_build_manifest_parameter_defaults_to_none():
    m = build_manifest(make_show(), [], briefing=ManifestBriefing())
    assert m.dropped_tracks is None


# --- station readers read raw JSON and must not care about the key -----------------

DAMAGED = ["a string", {"title": "x"}, [{"title": "ok", "set": "1", "after_track": 0},
                                        "not an object", 7, None],
          None, []]


@pytest.mark.parametrize("damaged", DAMAGED)
def test_station_readers_tolerate_damaged_dropped_tracks(tmp_path: Path, damaged):
    ws = build_ready(tmp_path, SLUG)
    lib = json.loads((ws.package_dir / "manifest.json").read_text())
    station = {**lib, "dropped_tracks": damaged}
    assert station_mark.manifest_differences(lib, station) == []
    assert station_mark.manifest_differences(station, lib) == []

    # audio_reuse reads the station manifest raw: same plan with or without the key.
    out = tmp_path / "station" / SLUG
    shutil.copytree(ws.package_dir, out)
    clean = audio_reuse.plan_reuse(ws, out)
    (out / "manifest.json").write_text(json.dumps(station))
    assert audio_reuse.plan_reuse(ws, out) == clean
    assert audio_reuse.plan_reuse(ws, out, strict=True).station_problem is None

    # deliver's voiced-destination check behaves as for a station manifest without it.
    dest = tmp_path / "inbox"
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "deliver", SLUG, "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    m = json.loads((dest / SLUG / "manifest.json").read_text())
    m.update(dj_notes={"file": "dj-notes.md"}, dj_audio={"dir": "dj-audio"},
             dropped_tracks=damaged)
    (dest / SLUG / "manifest.json").write_text(json.dumps(m))
    (ws.package_dir / "audio").mkdir(parents=True, exist_ok=True)
    (ws.package_dir / "audio" / "01 - Morning Dew.mp3").write_text("x")
    before = tree_bytes(dest)
    r = runner.invoke(cli.app, ["--config", cfg, "deliver", SLUG, "--dest", str(dest)])
    assert r.exit_code == 1
    assert "voiced" in r.output
    assert tree_bytes(dest) == before


def test_compared_is_unchanged():
    assert station_mark.COMPARED == (
        "source.identifier", "show.venue", "show.city", "show.date", "tracks.filename",
        "tracks.duration_sec", "tracks.title", "tracks.set", "tracks.segue", "set_breaks")
    assert not any("dropped_tracks" in name for name in station_mark.COMPARED)


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\ndelivery_path = "{tmp_path / "inbox"}"\n')
    return str(tmp_path / "config.toml")


def _voice(out: Path) -> None:
    m = json.loads((out / "manifest.json").read_text())
    m["dj_notes"] = {"file": "dj-notes.md"}
    m["dj_audio"] = {"dir": "dj-audio", "presenter": "phil", "profile": "dead"}
    (out / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    (out / "dj-notes.md").write_text("script")
    (out / "dj-audio").mkdir()
    (out / "dj-audio" / "intro.mp3").write_bytes(b"voice")
    (out / "broadcast.m3u").write_text("#EXTM3U\n")


def _add_drop(ws) -> None:
    mf = ws.package_dir / "manifest.json"
    m = json.loads(mf.read_text())
    m["dropped_tracks"] = [DROP_JSON]
    write_artifact(mf, m)


def test_clear_mark_ignores_dropped_tracks(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])
    ws = build_ready(tmp_path, SLUG)
    cfg = _cfg(tmp_path)
    assert runner.invoke(cli.app, ["--config", cfg, "deliver", SLUG]).exit_code == 0
    out = tmp_path / "inbox" / SLUG
    _voice(out)
    station_mark.write_mark(out, reason=MARK_REASON, marked_at=LONG_AGO)
    campaign.add_mark(ws, reason=MARK_REASON, start_stage="gather", batch="b1", at=LONG_AGO)
    (ws.package_dir / "audio" / "01 - Morning Dew.mp3").write_text("x")
    _add_drop(ws)                    # the library differs from the station ONLY here
    assert campaign.mark_processed(ws, held=False)

    r = runner.invoke(cli.app, ["--config", cfg, "clear-mark", SLUG])

    assert r.exit_code == 0, r.output
    assert "mark cleared" in r.output
    assert "awaiting_fix" not in json.loads((out / "manifest.json").read_text())
    assert "dropped_tracks" not in json.loads((out / "manifest.json").read_text())


def test_replace_voiced_equal_test_ignores_dropped_tracks(tmp_path: Path):
    ws = build_ready(tmp_path, SLUG)
    cfg = _cfg(tmp_path)
    dest = tmp_path / "inbox"
    base = ["--config", cfg, "deliver", SLUG, "--dest", str(dest)]
    assert runner.invoke(cli.app, base).exit_code == 0
    out = dest / SLUG
    _voice(out)
    station_mark.write_mark(out, reason=MARK_REASON, marked_at=LONG_AGO)
    (ws.package_dir / "audio" / "01 - Morning Dew.mp3").write_text("x")
    _add_drop(ws)
    before = tree_bytes(dest)

    r = runner.invoke(cli.app, [*base, "--replace-voiced"])

    assert r.exit_code == 1
    assert (f"refusing to replace {SLUG}: the re-processed show equals the voiced "
            f"station copy; keep the voicing with: llama clear-mark {SLUG}"
            ) in " ".join(r.output.split())
    assert tree_bytes(dest) == before
