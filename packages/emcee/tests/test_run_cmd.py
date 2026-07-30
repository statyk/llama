"""Tests for `emcee run`: scan the station, process every "pending" package,
skip "ready"/"unsupported" ones, and survive per-package failures -- including
a structurally malformed (but valid-JSON) v3 manifest that would otherwise
escape the EmceeError taxonomy as a bare KeyError/AttributeError/TypeError.

Task 9. Uses `backend = "fake"` for TTS (llama's test convention) and
monkeypatches `emcee.process.provider_for` for the LLM, the established
injection seam (see test_process.py).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import app
from emcee.errors import EmceeError

from herder import FakeProvider

from tests.helpers import build_package

runner = CliRunner()


def _write_config(root: Path, station_root: Path | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ['[tts]', 'backend = "fake"', 'voice = "test-voice"', '']
    if station_root is not None:
        lines = ['[station]', f'root = "{station_root}"', ''] + lines
    (root / "config.toml").write_text("\n".join(lines))


def _good_notes_json(**overrides) -> str:
    # Matches build_package's default fixture (sets=("1", "2"), encore=True):
    # tracks are Morning Dew/Sugaree (set 1), Jack Straw/China Cat Sunflower
    # (set 2), I Know You Rider (encore) -- all valid mentioned_songs.
    d = {
        "context": "Spring '73 tour",
        "set_intros": {
            "1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
            "2": "China Cat Sunflower leads set two.",
        },
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    }
    d.update(overrides)
    return json.dumps(d)


def _arm_fake_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        process_mod, "provider_for",
        lambda settings, task: FakeProvider(completes=[_good_notes_json()]),
    )


# ---------------------------------------------------------------------------
# [station] root resolution
# ---------------------------------------------------------------------------


def test_run_missing_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_run_nonexistent_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=tmp_path / "does-not-exist")

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_run_station_root_flag_overrides_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)

    result = runner.invoke(app, ["run", "--station-root", str(station)])

    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# run: process pending, skip ready, skip (and never touch) unsupported
# ---------------------------------------------------------------------------


def test_run_processes_exactly_the_unvoiced_package(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    unvoiced_dir = build_package(station, slug="unvoiced-show", voiced=False)
    voiced_dir = build_package(station, slug="voiced-show", voiced=True)
    v2_dir = station / "v2-show"
    v2_dir.mkdir(parents=True)
    (v2_dir / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    before_v2 = (v2_dir / "manifest.json").read_text()
    before_voiced = (voiced_dir / "manifest.json").read_text()
    before_notes = (voiced_dir / "dj-notes.md").read_text()

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    # the unvoiced package got fully processed
    assert (unvoiced_dir / "dj-notes.md").exists()
    assert (unvoiced_dir / "dj-audio" / "set1-intro.mp3").exists()
    assert (unvoiced_dir / "dj-audio" / "99-outro.mp3").exists()
    assert (unvoiced_dir / "broadcast.m3u").exists()
    manifest = json.loads((unvoiced_dir / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["dj_audio"] is not None
    assert f"voiced: {unvoiced_dir.name}" in result.output

    # the already-voiced package was left completely alone
    assert (voiced_dir / "manifest.json").read_text() == before_voiced
    assert (voiced_dir / "dj-notes.md").read_text() == before_notes

    # the v2 package was reported and never modified
    assert (v2_dir / "manifest.json").read_text() == before_v2
    assert "v2-show" in result.output
    assert "unsupported" in result.output


def test_run_skips_all_ready_and_reports_zero_processed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)
    build_package(station, slug="already-ready", voiced=True)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert "voiced:" not in result.output


# ---------------------------------------------------------------------------
# Batch resilience: one failure must not stop the others.
# ---------------------------------------------------------------------------


def test_run_batch_continues_after_one_package_fails(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    ok_dir = build_package(station, slug="okshow", voiced=False)
    fail_dir = build_package(station, slug="failshow", voiced=False)

    real_process_package = process_mod.process_package

    def flaky_process_package(config, pkg, speech, force=False):
        if pkg.dir.name == "failshow":
            raise RuntimeError("synthetic TTS blowup")
        return real_process_package(config, pkg, speech, force)

    import emcee.cli as cli_mod
    monkeypatch.setattr(cli_mod, "process_package", flaky_process_package)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "error: failshow: synthetic TTS blowup" in result.output
    # the other (good) package was still processed
    assert (ok_dir / "broadcast.m3u").exists()
    assert f"voiced: {ok_dir.name}" in result.output
    # the failed package was left without a broadcast.m3u (never completed)
    assert not (fail_dir / "broadcast.m3u").exists()


def test_run_malformed_but_valid_json_manifest_reported_and_batch_continues(tmp_path, monkeypatch):
    """A v3 manifest that is valid JSON but structurally wrong (a track dict
    missing "filename") makes `readiness()` raise a bare KeyError -- this
    must be caught broadly, reported as an `error: <slug>: ...` line, and
    must NOT abort processing of the other, well-formed package."""
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    ok_dir = build_package(station, slug="okshow", voiced=False)

    bad_dir = station / "badshow"
    bad_dir.mkdir(parents=True)
    (bad_dir / "manifest.json").write_text(json.dumps({
        "schema_version": 3,
        "briefing": {"file": "briefing.md", "json": "briefing.json",
                     "narration": "full", "vetted": False},
        "show": {"artist": "X", "date": "1970-01-01", "venue": "V",
                 "city": None, "context": ""},
        "source": {"performance_id": "X/1970-01-01"},
        "tracks": [{"index": 1, "set": "1", "title": "Song"}],  # missing "filename"
        "set_breaks": [],
        "total_duration_sec": 0,
        "set_durations_sec": {},
    }))

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert result.exception is None or not isinstance(result.exception, KeyError)
    assert "error: badshow" in result.output
    # the good package still got processed -- proof the batch continued
    assert (ok_dir / "broadcast.m3u").exists()
    assert f"voiced: {ok_dir.name}" in result.output
