"""Tests for `emcee status`: a table (or --json list) of every package in
the station -- slug, state, reasons -- with the same `[station] root`
resolution and the same broad per-package error handling as `run`.

Task 9.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from emcee.cli import app
from emcee.errors import EmceeError

from tests.helpers import build_package

runner = CliRunner()


def _write_config(root: Path, station_root: Path | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ['[tts]', 'backend = "fake"', 'voice = "test-voice"', '']
    if station_root is not None:
        lines = ['[station]', f'root = "{station_root}"', ''] + lines
    (root / "config.toml").write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# [station] root resolution
# ---------------------------------------------------------------------------


def test_status_missing_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_status_nonexistent_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=tmp_path / "does-not-exist")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


# ---------------------------------------------------------------------------
# All three states, table + --json
# ---------------------------------------------------------------------------


def _setup_three_states(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    build_package(station, slug="ready-show", voiced=True)
    build_package(station, slug="pending-show", voiced=False)
    v2_dir = station / "unsupported-show"
    v2_dir.mkdir(parents=True)
    (v2_dir / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    return station


def test_status_table_renders_all_three_states_with_reasons(tmp_path, monkeypatch):
    _setup_three_states(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "ready-show" in out and "ready" in out
    assert "pending-show" in out and "pending" in out
    assert "unsupported-show" in out and "unsupported" in out
    # pending's reasons are surfaced (at least one leg named)
    assert "no DJ audio" in out or "no DJ script" in out or "broadcast.m3u" in out
    assert "re-deliver from llama" in out


def test_status_json_shape(tmp_path, monkeypatch):
    _setup_three_states(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    by_slug = {row["slug"]: row for row in payload}
    assert set(by_slug) == {"ready-show", "pending-show", "unsupported-show"}
    assert by_slug["ready-show"]["state"] == "ready"
    assert by_slug["ready-show"]["reasons"] == []
    assert by_slug["pending-show"]["state"] == "pending"
    assert by_slug["pending-show"]["reasons"]
    assert by_slug["unsupported-show"]["state"] == "unsupported"
    assert "re-deliver from llama" in by_slug["unsupported-show"]["reasons"][0]


def test_status_empty_station_reports_no_packages(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "no packages" in result.output.lower()


# ---------------------------------------------------------------------------
# Broad per-package error handling: a malformed-but-valid-JSON manifest must
# render as an error row, not crash the table.
# ---------------------------------------------------------------------------


def test_status_malformed_manifest_renders_as_error_row_and_table_continues(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)

    build_package(station, slug="okshow", voiced=True)

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

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert "okshow" in result.output and "ready" in result.output
    assert "badshow" in result.output
    assert "error" in result.output.lower()

    # same, via --json
    result_json = runner.invoke(app, ["status", "--json"])
    assert result_json.exit_code == 0, result_json.output
    payload = json.loads(result_json.output)
    by_slug = {row["slug"]: row for row in payload}
    assert by_slug["badshow"]["state"] == "error"
    assert "filename" in by_slug["badshow"]["reasons"][0]
