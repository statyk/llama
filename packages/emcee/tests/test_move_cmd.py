"""`emcee move`: record, clear and list one-off profile moves (spec section 3)."""

import fcntl
import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.moves as moves_mod
from emcee.cli import app
from emcee.errors import EmceeError

from tests.helpers import build_package, forbid_spend, set_dj_audio, station_home, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = _SOUTHERN + '\n[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n'


@pytest.fixture(autouse=True)
def _no_spend(monkeypatch):
    forbid_spend(monkeypatch)              # emcee move makes no LLM or TTS call


def _moves(home: Path) -> dict:
    return json.loads((home / "moves.json").read_text())


# --- record ------------------------------------------------------------------------


def test_record_a_move_of_a_voiced_package(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    result = runner.invoke(app, ["move", "ttb", "southern"])

    assert result.exit_code == 0, result.output
    assert "moved: ttb  funk -> southern (pending; voiced on the next emcee run)" in result.stdout
    entry = _moves(home)["GratefulDead/ttb"]
    assert (entry["profile"], entry["package"]) == ("southern", "ttb")
    assert entry["moved_at"].endswith("Z") and len(entry["moved_at"]) == 20


def test_the_identical_move_again_is_unchanged(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    runner.invoke(app, ["move", "ttb", "southern"])
    before = (home / "moves.json").read_bytes()

    result = runner.invoke(app, ["move", "ttb", "southern"])

    assert result.exit_code == 0
    assert result.stdout.startswith("unchanged: ttb")
    assert (home / "moves.json").read_bytes() == before


def test_an_unvoiced_package_says_when_it_will_be_voiced(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", profile="funk")

    result = runner.invoke(app, ["move", "ttb", "southern"])

    assert ("moved: ttb  funk -> southern (unvoiced; voiced as southern on the next emcee run)"
            in result.stdout)


def test_an_exemption_from_a_rule_needs_no_assign_entry_and_reads_ready(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_RULE)  # no [assign.profiles.funk]
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    result = runner.invoke(app, ["move", "ttb", "--delivered"])

    assert result.exit_code == 0, result.output
    assert "moved: ttb  southern -> funk (ready; already voiced as funk)" in result.stdout
    assert _moves(home)["GratefulDead/ttb"]["profile"] == "funk"


def test_the_state_is_the_profile_checks_not_full_readiness(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    pkg_dir = build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    (pkg_dir / "broadcast.m3u").unlink()                          # a repair, not a re-voice

    result = runner.invoke(app, ["move", "ttb", "--delivered"])

    assert "moved: ttb  southern -> funk (ready; already voiced as funk)" in result.stdout


@pytest.mark.parametrize("args, assign, voiced, expected", [
    (["move", "ttb", "southern"], _SOUTHERN, True,
     "funk -> southern (pending; 1 audio file(s) missing — re-deliver from llama)"),
    (["move", "ttb", "--delivered"], _RULE, True,
     "southern -> funk (ready; already voiced as funk; 1 audio file(s) missing — re-deliver from llama)"),
    (["move", "ttb", "southern"], _SOUTHERN, False,
     "funk -> southern (unvoiced; 1 audio file(s) missing — re-deliver from llama)"),
], ids=["pending", "ready", "unvoiced"])
def test_missing_track_audio_says_re_deliver_instead_of_voiced(tmp_path, monkeypatch, args, assign,
                                                               voiced, expected):
    _, station = station_home(tmp_path, monkeypatch, assign=assign)
    pkg_dir = build_package(station, slug="ttb", voiced=voiced, profile="funk", artist=TTB)
    sorted((pkg_dir / "audio").iterdir())[0].unlink()

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert f"moved: ttb  {expected}" in result.stdout
    assert "next emcee run" not in result.stdout


def test_a_move_naming_the_delivered_profile_needs_no_assign_entry(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    assert runner.invoke(app, ["move", "ttb", "funk"]).exit_code == 0
    assert _moves(home)["GratefulDead/ttb"]["profile"] == "funk"


def test_delivered_records_null_for_a_package_with_no_profile(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    build_package(station, slug="ttb", voiced=True, profile=None, artist=TTB)

    assert runner.invoke(app, ["move", "ttb", "--delivered"]).exit_code == 0
    assert _moves(home)["GratefulDead/ttb"]["profile"] is None


def test_other_entries_unknown_keys_survive(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    (home / "moves.json").write_text(json.dumps(
        {"Other/1": {"profile": "southern", "package": "other", "note": "keep"}}))
    build_package(station, slug="ttb", profile="funk")

    assert runner.invoke(app, ["move", "ttb", "southern"]).exit_code == 0
    assert _moves(home)["Other/1"] == {"profile": "southern", "package": "other", "note": "keep"}


def test_the_lock_is_held_around_load_modify_write(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", profile="funk")
    seen: list = []

    def held() -> bool:
        fd = os.open(home / "moves.json.lock", os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            return False
        finally:
            os.close(fd)

    real_read, real_write = moves_mod.read_moves_data, moves_mod.write_moves
    monkeypatch.setattr(moves_mod, "read_moves_data",
                        lambda root: (seen.append(("read", held())), real_read(root))[1])
    monkeypatch.setattr(moves_mod, "write_moves",
                        lambda root, data: (seen.append(("write", held())), real_write(root, data))[1])

    assert runner.invoke(app, ["move", "ttb", "southern"]).exit_code == 0
    assert seen == [("read", True), ("write", True)]


# --- refusals leave moves.json byte-for-byte unchanged ------------------------------


def _refusal_station(tmp_path, monkeypatch, existing: bool):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", profile="funk")
    nopid = build_package(station, slug="nopid", profile="funk")
    m = json.loads((nopid / "manifest.json").read_text())
    del m["source"]["performance_id"]
    (nopid / "manifest.json").write_text(json.dumps(m))
    old = station / "old"
    old.mkdir()
    (old / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    junk = station / "junk"
    junk.mkdir()
    (junk / "manifest.json").write_text("{not json")
    if existing:
        (home / "moves.json").write_text(json.dumps(
            {"Other/1": {"profile": "southern", "package": "other"}}))
    return home


@pytest.mark.parametrize("existing", [True, False], ids=["file-present", "file-absent"])
@pytest.mark.parametrize("args, why", [
    (["move", "ttb", "bluegrass"], "[assign.profiles.bluegrass]"),
    (["move", "nopid", "southern"], "performance_id"),
    (["move", "old", "southern"], "unsupported"),
    (["move", "junk", "southern"], "not valid JSON"),
    (["move", "ttb", ""], "[assign.profiles.] entry"),
])
def test_each_refusal_exits_1_and_leaves_the_file_alone(tmp_path, monkeypatch, existing, args, why):
    home = _refusal_station(tmp_path, monkeypatch, existing)
    before = (home / "moves.json").read_bytes() if existing else None

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert why in str(result.exception)
    if existing:
        assert (home / "moves.json").read_bytes() == before
    else:
        assert not (home / "moves.json").exists()


@pytest.mark.parametrize("args", [["move"], ["move", "ttb"], ["move", "ttb", "southern", "--clear"],
                                  ["move", "ttb", "--delivered", "--clear"], ["move", "--list", "ttb"]])
def test_usage_errors_exit_2(tmp_path, monkeypatch, args):
    station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    assert runner.invoke(app, args).exit_code == 2


# --- the missing-file guard ------------------------------------------------------------


@pytest.mark.parametrize("args", [["move", "fresh", "southern"], ["move", "--list"],
                                  ["move", "moved", "--clear"]])
def test_a_missing_file_with_a_move_voiced_package_refuses_and_writes_nothing(tmp_path, monkeypatch,
                                                                              args):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    build_package(station, slug="fresh", profile="funk")

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert str(home / "moves.json") in str(result.exception)
    assert "1 package(s)" in str(result.exception)
    details = "\n".join(result.exception.details)
    assert "rebuild" in details and "{}" in details               # both ways out are named
    assert not (home / "moves.json").exists()


# --- a bad moves.json stops every form before any work ------------------------------------


@pytest.mark.parametrize("args", [["move", "ttb", "southern"], ["move", "ttb", "--clear"],
                                  ["move", "--list"]])
@pytest.mark.parametrize("content", ['{"GratefulDead/ttb": {"profile": "sou', '["not", "an", "object"]'],
                         ids=["truncated", "wrong-shape"])
def test_a_bad_moves_file_refuses_and_is_left_alone(tmp_path, monkeypatch, args, content):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    (home / "moves.json").write_text(content)
    before = (home / "moves.json").read_bytes()

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert str(home / "moves.json") in str(result.exception)
    assert (home / "moves.json").read_bytes() == before


# --- --clear -----------------------------------------------------------------------------


def test_clear_prints_the_id_and_leaves_an_empty_object(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", profile="funk")
    write_moves_file(home, {"GratefulDead/ttb": "southern"})

    result = runner.invoke(app, ["move", "ttb", "--clear"])

    assert result.exit_code == 0, result.output
    assert "cleared: GratefulDead/ttb" in result.stdout
    assert _moves(home) == {}


def test_a_stale_move_is_cleared_by_id_or_by_its_recorded_package_name(tmp_path, monkeypatch):
    home, _ = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    write_moves_file(home, {"Gone/gone-1999": "southern", "Gone/gone-2000": "southern"})

    first = runner.invoke(app, ["move", "Gone/gone-1999", "--clear"])
    second = runner.invoke(app, ["move", "gone-2000", "--clear"])   # no live package has this name

    assert "cleared: Gone/gone-1999" in first.stdout
    assert "cleared: Gone/gone-2000" in second.stdout
    assert _moves(home) == {}


def test_recorded_entries_are_matched_before_live_packages(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="abc", profile="funk")              # live, pid GratefulDead/abc
    write_moves_file(home, {"Old/abc": "southern"})                # stale, recorded package "abc"

    result = runner.invoke(app, ["move", "abc", "--clear"])

    assert "cleared: Old/abc" in result.stdout


def test_ambiguous_recorded_matches_are_refused_with_their_ids(tmp_path, monkeypatch):
    home, _ = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    write_moves_file(home, {"Old/abc": "southern", "Older/abc": "southern"})
    before = (home / "moves.json").read_bytes()

    result = runner.invoke(app, ["move", "abc", "--clear"])

    assert result.exit_code == 1
    assert result.exception.details == ["Old/abc", "Older/abc"]
    assert (home / "moves.json").read_bytes() == before


# --- --list ------------------------------------------------------------------------------


def test_list_shows_target_delivered_missing_and_no_assign_entry(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    build_package(station, slug="gd", voiced=True, profile="dead")
    write_moves_file(home, {"GratefulDead/ttb": "southern", "GratefulDead/gd": "jazz",
                            "Gone/gone-1999": "southern"})

    out = runner.invoke(app, ["move", "--list"]).stdout.splitlines()

    assert out == [
        "gone-1999  Gone/gone-1999  southern (from ?)  missing",
        "gd  GratefulDead/gd  jazz (from dead)  [no assign entry]",
        "ttb  GratefulDead/ttb  southern (from funk)",
    ]


def test_list_with_no_moves(tmp_path, monkeypatch):
    station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    assert runner.invoke(app, ["move", "--list"]).stdout.strip() == "no moves recorded"


# --- a move survives llama's --replace-voiced -----------------------------------------------


def test_a_move_survives_a_replace_voiced_redelivery(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    assert runner.invoke(app, ["move", "ttb", "southern"]).exit_code == 0

    shutil.rmtree(station / "ttb")                                  # llama replaces the dir wholesale
    build_package(station, slug="ttb", voiced=False, profile="funk")  # same performance_id

    rows = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).stdout)}
    assert (rows["ttb"]["profile"], rows["ttb"]["state"]) == ("southern", "pending")
    dry = runner.invoke(app, ["run", "--dry-run"])
    assert "would voice: ttb  southern  gregg" in dry.stdout
