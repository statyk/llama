"""`emcee status` on effective profiles (spec sections 1, 3, 4)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from emcee.cli import app

from tests.helpers import build_package, set_dj_audio, station_home, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = _SOUTHERN + '\n[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n'


def _rows(result) -> dict[str, str]:
    return {line.split()[0]: line for line in result.stdout.splitlines()}


def _json(args=("status", "--json")) -> dict[str, dict]:
    return {r["slug"]: r for r in json.loads(runner.invoke(app, list(args)).stdout)}


def test_list_marks_a_profile_that_differs_from_the_delivered_one(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    build_package(station, slug="gd", voiced=True, profile="dead")

    rows = _rows(runner.invoke(app, ["status", "--list"]))

    assert "southern (from funk)" in rows["ttb"]
    assert "pending" in rows["ttb"]
    assert "(from" not in rows["gd"]


def test_summary_groups_by_the_effective_profile(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    lines = [line.split() for line in runner.invoke(app, ["status"]).stdout.splitlines()]

    assert [line[0] for line in lines[1:-1]] == ["southern"]


def test_profile_filter_follows_a_move(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="moved", voiced=True, profile="funk")
    write_moves_file(home, {"GratefulDead/moved": "southern"})

    south = runner.invoke(app, ["status", "--profile", "southern"])
    funk = runner.invoke(app, ["status", "--profile", "funk"])

    assert "moved" in _rows(south)
    assert "no packages match" in funk.stdout
    assert "note: no package has profile 'funk'" in funk.stderr


def test_json_carries_delivered_profile_source_tts_and_move_problem(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    build_package(station, slug="legacy", voiced=True, profile="dead")
    rec = build_package(station, slug="rec", voiced=True, profile="dead")
    tts = {"backend": "voxtral", "model": "voxtral-mini-tts-2603", "voice": "clone:0123abcd"}
    set_dj_audio(rec, presenter=None, profile="dead", profile_source="llama", tts=tts)

    by = _json()

    assert (by["ttb"]["profile"], by["ttb"]["delivered_profile"], by["ttb"]["profile_source"]) == (
        "southern", "funk", "artist")
    assert by["legacy"]["tts"] is None
    assert by["rec"]["tts"] == tts
    assert by["ttb"]["move_problem"] is None


def test_a_move_without_an_assign_entry_is_marked(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch)
    build_package(station, slug="moved", voiced=True, profile="funk")
    write_moves_file(home, {"GratefulDead/moved": "southern"})

    rows = _rows(runner.invoke(app, ["status", "--list"]))
    by = _json()

    assert "southern (from funk) [no assign entry]" in rows["moved"]
    assert by["moved"]["move_problem"] == 'move target "southern" has no [assign.profiles] entry'


def test_status_notes_stale_moves_on_stderr(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="gd", voiced=True, profile="dead")
    write_moves_file(home, {"Gone/gone-1999": "southern"})
    note = "note: 1 recorded move(s) match no package (emcee move --list)"

    plain = runner.invoke(app, ["status"])
    as_json = runner.invoke(app, ["status", "--json"])

    assert note in plain.stderr
    assert note in as_json.stderr
    assert json.loads(as_json.stdout)[0]["slug"] == "gd"       # stdout stays pure JSON


def test_two_packages_sharing_a_performance_id_both_follow_one_move(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)  # Review Focus 5
    build_package(station, slug="a", voiced=True, profile="funk")
    b = build_package(station, slug="b", voiced=True, profile="funk")
    m = json.loads((b / "manifest.json").read_text())
    m["source"]["performance_id"] = "GratefulDead/a"
    (b / "manifest.json").write_text(json.dumps(m))
    write_moves_file(home, {"GratefulDead/a": "southern"})

    result = runner.invoke(app, ["status", "--json"])
    by = {r["slug"]: r for r in json.loads(result.stdout)}
    listed = runner.invoke(app, ["move", "--list"]).stdout

    assert by["a"]["profile"] == by["b"]["profile"] == "southern"
    assert by["a"]["profile_source"] == by["b"]["profile_source"] == "move"
    assert "match no package" not in result.stderr
    assert "missing" not in listed
