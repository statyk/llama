"""Readiness's fifth leg (the profile check) and the scan threading config
and moves (spec sections 1, 3, 4; strict surfaces 2 and 3)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
from emcee.cli import app
from emcee.config import EmceeConfig
from emcee.errors import EmceeError
from emcee.package_io import Package
from emcee.station import readiness, scan

from tests.helpers import (build_package, forbid_spend, moves_of, no_moves, set_dj_audio,
                           station_home, write_moves_file)

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = _SOUTHERN + '\n[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n'


def _rule_config() -> EmceeConfig:
    return EmceeConfig(assign={"profiles": {"southern": {"presenter": "gregg"}},
                               "artists": {TTB: "southern"}})


def _edit(pkg_dir: Path, mutate) -> None:
    path = pkg_dir / "manifest.json"
    manifest = json.loads(path.read_text())
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


# --- strict surface 3: nothing ready today goes pending ----------------------


@pytest.mark.parametrize("moves", [no_moves(), moves_of({})], ids=["no-file", "empty-file"])
@pytest.mark.parametrize("source", ["dead", "", None, "missing"])
def test_a_legacy_voiced_package_stays_ready_with_no_rules_or_moves(tmp_path, source, moves):
    pkg_dir = build_package(tmp_path, slug="legacy", voiced=True, profile="dead")

    def mutate(m):
        assert "profile" not in m["dj_audio"]       # the fixture is a legacy block
        if source == "missing":
            del m["source"]
        else:
            m["source"]["profile"] = source
    _edit(pkg_dir, mutate)

    assert readiness(Package(pkg_dir), EmceeConfig(), moves) == (True, [])
    [status] = scan(tmp_path, EmceeConfig(), moves)
    assert (status.state, status.reasons) == ("ready", [])


# --- the four reason texts -------------------------------------------------------


def test_the_same_legacy_package_under_a_matching_rule_goes_pending(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    assert readiness(Package(pkg_dir), _rule_config(), no_moves()) == (
        False, ['voiced as funk, now southern (artist rule "Tedeschi Trucks Band")'])


def test_a_move_makes_it_pending_with_the_move_reason(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    assert readiness(Package(pkg_dir), EmceeConfig(),
                     moves_of({"GratefulDead/ttb": "southern"})) == (
        False, ["voiced as funk, now southern (move)"])


def test_a_move_no_longer_recorded(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    set_dj_audio(pkg_dir, profile="southern", profile_source="move")
    assert readiness(Package(pkg_dir), EmceeConfig(), no_moves()) == (
        False, ["voiced as southern, now funk (move no longer recorded)"])


def test_back_to_the_delivered_profile_when_no_rule_or_move_applies(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    set_dj_audio(pkg_dir, profile="southern", profile_source="artist")
    assert readiness(Package(pkg_dir), EmceeConfig(), no_moves()) == (
        False, ["voiced as southern, now funk (delivered profile; no rule or move applies)"])


def test_a_none_profile_renders_as_none(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile=None, artist=TTB)
    ok, reasons = readiness(Package(pkg_dir), _rule_config(), no_moves())
    assert reasons == ['voiced as (none), now southern (artist rule "Tedeschi Trucks Band")']


# --- what does NOT make a package pending ----------------------------------------


def test_voiced_as_the_effective_profile_stays_ready(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    set_dj_audio(pkg_dir, profile="southern", profile_source="artist", presenter="gregg")
    assert readiness(Package(pkg_dir), _rule_config(), no_moves()) == (True, [])


def test_a_missing_tts_or_a_different_presenter_never_makes_it_pending(tmp_path):
    pkg_dir = build_package(tmp_path, slug="gd", voiced=True, profile="dead")
    set_dj_audio(pkg_dir, profile="dead", profile_source="llama", presenter="someone-else")
    cfg = EmceeConfig(assign={"profiles": {"dead": {"presenter": "phil"}}})
    assert readiness(Package(pkg_dir), cfg, no_moves()) == (True, [])


# --- scan fields ---------------------------------------------------------------------


def test_scan_reports_effective_and_delivered_profiles(tmp_path):
    build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    build_package(tmp_path, slug="gd", voiced=False, profile="dead")

    by = {s.path.name: s for s in scan(tmp_path, _rule_config(), no_moves())}

    ttb, gd = by["ttb"], by["gd"]
    assert (ttb.profile, ttb.delivered_profile, ttb.profile_source) == ("southern", "funk", "artist")
    assert ttb.state == "pending" and ttb.voiced is True
    assert ttb.profile_reason == 'voiced as funk, now southern (artist rule "Tedeschi Trucks Band")'
    assert (ttb.performance_id, ttb.clips, ttb.missing_tracks) == ("GratefulDead/ttb", 3, 0)
    assert (gd.profile, gd.delivered_profile, gd.profile_source) == ("dead", "dead", "llama")
    assert gd.voiced is False and gd.profile_reason is None and gd.tts is None


def test_scan_counts_missing_tracks_and_flags_an_invalid_move(tmp_path):
    pkg_dir = build_package(tmp_path, slug="gd", voiced=False, profile="dead")
    sorted((pkg_dir / "audio").iterdir())[0].unlink()

    [status] = scan(tmp_path, EmceeConfig(), moves_of({"GratefulDead/gd": "gone"}))

    assert status.missing_tracks == 1
    assert status.move_problem == 'move target "gone" has no [assign.profiles] entry'


def test_scan_keeps_unsupported_rows_on_llamas_profile(tmp_path):
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "manifest.json").write_text(json.dumps(
        {"schema_version": 2, "source": {"profile": "old", "performance_id": "X/1"}}))
    [status] = scan(tmp_path, _rule_config(), no_moves())
    assert (status.state, status.profile, status.delivered_profile, status.performance_id) == (
        "unsupported", "old", "old", "X/1")


# --- CLI: moves are loaded first, and loudly -------------------------------------------


def _malformed(station: Path) -> None:
    """A valid-JSON v3 manifest whose track has no filename: `scan` raises on
    it, so the command falls back to the per-entry `_scan_broad` walk."""
    bad = station / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"profile": "dead"}, "tracks": [{}]}))


@pytest.mark.parametrize("command", [["run"], ["run", "--dry-run"], ["status"], ["status", "--json"]])
@pytest.mark.parametrize("content", ['{"GratefulDead/a": {"profile": "sou', '["not", "an", "object"]'],
                         ids=["truncated", "wrong-shape"])
def test_a_bad_moves_file_fails_loudly_before_any_work(tmp_path, monkeypatch, command, content):
    home, station = station_home(tmp_path, monkeypatch)
    build_package(station, slug="a", profile="dead")
    (home / "moves.json").write_text(content)
    forbid_spend(monkeypatch)

    result = runner.invoke(app, command)

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert str(home / "moves.json") in str(result.exception)
    assert "voiced:" not in result.output and "would voice" not in result.output
    assert json.loads((station / "a" / "manifest.json").read_text())["dj_audio"] is None


@pytest.mark.parametrize("command, broken", [
    (["run"], False), (["run", "--dry-run"], False), (["status"], False),
    (["status"], True), (["run"], True),
], ids=["run", "run-dry-run", "status", "status-scan-broad", "run-scan-broad"])
def test_a_missing_moves_file_with_move_voiced_packages_fails(tmp_path, monkeypatch, command,
                                                              broken):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    for slug in ("m1", "m2"):
        pkg_dir = build_package(station, slug=slug, voiced=True, profile="funk")
        set_dj_audio(pkg_dir, profile="southern", profile_source="move", presenter="gregg")
    build_package(station, slug="fresh", profile="dead")
    if broken:
        _malformed(station)
    broad: list[int] = []
    real_broad = cli_mod._scan_broad
    monkeypatch.setattr(cli_mod, "_scan_broad",
                        lambda *a, **k: (broad.append(1), real_broad(*a, **k))[1])
    forbid_spend(monkeypatch)

    result = runner.invoke(app, command)

    assert broad == ([1] if broken else [])      # the guard ran on the path under test
    assert result.exit_code == 1
    exc = result.exception
    assert isinstance(exc, EmceeError)
    details = "\n".join(exc.details)
    assert str(home / "moves.json") in str(exc) and "2 package(s)" in str(exc)
    assert "m1: performance_id GratefulDead/m1, voiced as southern" in details
    assert "rebuild" in details and "write {}" in details
    assert "voiced:" not in result.output and "would voice" not in result.output
    assert not (home / "moves.json").exists()


def test_a_missing_moves_file_with_no_move_voiced_package_is_no_moves(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch)
    build_package(station, slug="a", voiced=True, profile="dead")

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["state"] == "ready"
    assert not (home / "moves.json").exists()


def test_run_filters_select_by_the_effective_profile(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="ttb", profile="funk", artist=TTB)
    build_package(station, slug="lettuce", profile="funk", artist="Lettuce")

    south = runner.invoke(app, ["run", "--profile", "southern", "--dry-run"])
    assert "would voice: ttb  southern  gregg" in south.output
    assert "would voice: lettuce" not in south.output

    funk = runner.invoke(app, ["run", "--profile", "funk", "--dry-run"])
    assert "would voice: lettuce  funk" in funk.output
    assert "would voice: ttb" not in funk.output

    assigned = runner.invoke(app, ["run", "--assigned", "--dry-run"])
    assert "would voice: ttb" in assigned.output
    assert "would voice: lettuce" not in assigned.output


def test_a_malformed_manifest_does_not_unmove_a_moved_ready_package(tmp_path, monkeypatch):
    """One malformed manifest sends status down the per-entry `_scan_broad`
    path; that path must thread config and moves too."""
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    _malformed(station)

    result = runner.invoke(app, ["status", "--json"])

    by = {row["slug"]: row for row in json.loads(result.stdout)}
    assert by["bad"]["state"] == "error"
    assert by["moved"]["state"] == "ready"
    assert by["moved"]["profile"] == "southern"
