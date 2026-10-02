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


def test_status_station_root_pointing_at_a_file_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    a_file = tmp_path / "not-a-directory.txt"
    a_file.write_text("hi")
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=a_file)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_status_station_root_flag_overrides_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)  # no [station] root in config at all

    result = runner.invoke(app, ["status", "--station-root", str(station)])

    assert result.exit_code == 0, result.output
    assert "no packages" in result.output.lower()


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

    result = runner.invoke(app, ["status", "--list"])

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

    result = runner.invoke(app, ["status", "--list"])

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


# ---------------------------------------------------------------------------
# Profile-aware views: summary (default), --list/--profile/--state, --json
# ---------------------------------------------------------------------------


def _write_assign_config(home: Path, station: Path, assign: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "fake"\nvoice = "v"\n\n{assign}\n')


def _set_voiced_by(pkg_dir: Path, **kw) -> None:
    """Rewrite a voiced fixture's dj_audio block: `presenter=<x>` sets the
    key; `legacy=True` drops it."""
    path = pkg_dir / "manifest.json"
    m = json.loads(path.read_text())
    if kw.get("legacy"):
        m["dj_audio"].pop("presenter", None)
    else:
        m["dj_audio"]["presenter"] = kw["presenter"]
    path.write_text(json.dumps(m))


def _mixed_station(tmp_path, monkeypatch, assign=""):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_assign_config(home, station, assign)
    build_package(station, slug="b1", voiced=True, profile="beta")
    build_package(station, slug="b2", voiced=False, profile="beta")
    build_package(station, slug="a1", voiced=True, profile="alpha")
    build_package(station, slug="n1", voiced=False)
    v2 = station / "u1"
    v2.mkdir(parents=True)
    (v2 / "manifest.json").write_text("{\"schema_version\": 2}")
    return station


def test_status_summary_rows_counts_labels_and_order(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch, '[assign]\ndefault = "dflt"\n\n'
                   '[assign.profiles.beta]\npresenter = "bob"\ntitle = "T"\n')

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    lines = [ln.split() for ln in result.output.splitlines()]
    assert lines[0] == ["profile", "presenter", "ready", "pending", "other"]
    assert lines[1] == ["alpha", "dflt", "(default)", "1", "0", "0"]
    assert lines[2] == ["beta", "bob", "1", "1", "0"]
    assert lines[3] == ["(none)", "dflt", "(default)", "0", "1", "0"]
    assert lines[4] == ["(unknown)", "0", "0", "1"]  # blank presenter
    assert lines[5] == ["total", "2", "2", "1"]
    assert len(lines) == 6
    assert "slug" not in result.output


def test_status_summary_omits_empty_none_and_unknown_rows(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_assign_config(home, station, "")
    build_package(station, slug="a1", voiced=True, profile="alpha")

    out = runner.invoke(app, ["status"]).output

    assert "(none)" not in out and "(unknown)" not in out
    assert "house" in out  # no assignment configured


def test_status_summary_empty_station(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_assign_config(home, station, "")

    assert "no packages found" in runner.invoke(app, ["status"]).output


def test_status_list_flag_and_short_flag_show_per_show_table(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    for flag in ("--list", "-l"):
        out = runner.invoke(app, ["status", flag]).output
        rows = {ln.split()[0]: ln for ln in out.splitlines()}
        assert set(rows) == {"a1", "b1", "b2", "n1", "u1"}
        assert "alpha" in rows["a1"] and "ready" in rows["a1"]
        assert "(none)" in rows["n1"]
        assert "re-deliver from llama" in rows["u1"]


def test_status_profile_filter_implies_list_and_is_repeatable(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    out = runner.invoke(app, ["status", "--profile", "beta"]).output
    assert {ln.split()[0] for ln in out.splitlines()} == {"b1", "b2"}

    out = runner.invoke(app, ["status", "--profile", "beta", "--profile", "alpha"]).output
    assert {ln.split()[0] for ln in out.splitlines()} == {"a1", "b1", "b2"}


def test_status_state_filter_implies_list_and_combines_with_profile(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    out = runner.invoke(app, ["status", "--state", "pending"]).output
    assert {ln.split()[0] for ln in out.splitlines()} == {"b2", "n1"}

    out = runner.invoke(app, ["status", "--state", "pending", "--profile", "beta"]).output
    assert {ln.split()[0] for ln in out.splitlines()} == {"b2"}

    out = runner.invoke(app, ["status", "--state", "ready", "--state", "unsupported"]).output
    assert {ln.split()[0] for ln in out.splitlines()} == {"a1", "b1", "u1"}


def test_status_unknown_state_is_a_usage_error(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--state", "bogus"])

    assert result.exit_code == 2


def test_status_filter_matching_nothing_reports_no_packages(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    assert "no packages found" in runner.invoke(app, ["status", "--profile", "zzz"]).output


def test_status_voiced_by_states_and_drift_annotation(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch,
                             '[assign.profiles.alpha]\npresenter = "BillyG"\n'
                             '[assign.profiles.beta]\npresenter = "bob"\n')
    # b1: voiced by someone else now -> drift; a1: same id, different case -> none
    _set_voiced_by(station / "b1", presenter="carol")
    _set_voiced_by(station / "a1", presenter="billyg")
    build_package(station, slug="legacy", voiced=True, profile="alpha")  # no presenter key
    build_package(station, slug="hse", voiced=True, profile="alpha")
    _set_voiced_by(station / "hse", presenter=None)
    build_package(station, slug="hse2", voiced=True, profile="gamma")  # gamma -> house now
    _set_voiced_by(station / "hse2", presenter=None)
    build_package(station, slug="gone", voiced=True, profile="gamma")
    _set_voiced_by(station / "gone", presenter="dave")

    out = runner.invoke(app, ["status", "--list"]).output
    rows = {ln.split()[0]: ln for ln in out.splitlines()}

    assert "(now: bob)" in rows["b1"] and "carol" in rows["b1"]
    assert "billyg" in rows["a1"] and "(now:" not in rows["a1"]
    assert "(now:" not in rows["legacy"] and rows["legacy"].split()[3] == "?"
    assert "(now: BillyG)" in rows["hse"] and "house" in rows["hse"]
    assert "house" in rows["hse2"] and "(now:" not in rows["hse2"]
    assert "dave (now: house)" in rows["gone"]
    assert "(now:" not in rows["b2"]  # unvoiced: "-"


def test_status_json_adds_profile_voiced_by_and_assignment(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch,
                             '[assign]\ndefault = "dflt"\n\n'
                             '[assign.profiles.beta]\npresenter = "bob"\n')
    _set_voiced_by(station / "b1", presenter="bob")

    payload = json.loads(runner.invoke(app, ["status", "--json"]).output)
    by = {r["slug"]: r for r in payload}

    assert by["b1"]["profile"] == "beta" and by["b1"]["voiced_by"] == "bob"
    assert by["b1"]["assigned_presenter"] == "bob"
    assert by["b1"]["assignment_source"] == "profile"
    assert by["b2"]["voiced_by"] is None
    assert by["a1"]["voiced_by"] == "?"  # legacy
    assert by["a1"]["assigned_presenter"] == "dflt"
    assert by["a1"]["assignment_source"] == "default"
    assert by["n1"]["profile"] is None
    assert by["u1"]["state"] == "unsupported"

    # filters apply to --json, which stays per-show
    only = json.loads(runner.invoke(app, ["status", "--json", "--profile", "beta"]).output)
    assert {r["slug"] for r in only} == {"b1", "b2"}


def test_status_json_house_voiced_and_house_assignment(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch)
    _set_voiced_by(station / "a1", presenter=None)

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    assert by["a1"]["voiced_by"] == "house"
    assert by["a1"]["assigned_presenter"] is None
    assert by["a1"]["assignment_source"] == "house"


def test_status_broad_scan_skips_dot_prefixed_dirs(tmp_path, monkeypatch):
    station = _setup_three_states(tmp_path, monkeypatch)
    build_package(station, slug=".ready-show.deliver-abc123", voiced=False)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    assert {r["slug"] for r in json.loads(result.output)} == {
        "ready-show", "pending-show", "unsupported-show"}
