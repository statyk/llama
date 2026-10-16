"""`emcee run`'s pause: the plan, the question and --yes (spec section 5;
strict surface 1: no LLM or TTS call before the plan is printed and
confirmed)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from herder import FakeProvider

import emcee.cli as cli_mod
import emcee.process as process_mod
from emcee.cli import app
from emcee.presenters import Presenter, save_presenter

from tests.helpers import (build_package, forbid_spend, notes_json, set_dj_audio, station_home,
                           write_moves_file)

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_ASSIGN = ('[assign.profiles.southern]\npresenter = "gregg"\n\n'
           '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')


def _gregg(home: Path) -> None:
    save_presenter(home, Presenter(id="gregg", name="Mr. LeNoir", sex="male",
                                   voice="gregg-preset", character="Smoky."))


def _spend(monkeypatch) -> list[str]:
    """Voicing works (fake LLM + fake TTS); records every LLM task asked for."""
    tasks: list[str] = []

    def fake(settings, task):
        tasks.append(task)
        return FakeProvider(completes=[notes_json()])

    monkeypatch.setattr(process_mod, "provider_for", fake)
    return tasks


def _tty(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)


def _lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines()]


def _station(tmp_path, monkeypatch):
    """fresh: unvoiced (new); ttb1/ttb2: voiced as funk, now southern by rule
    (re-voice); emerson: voiced, broadcast.m3u gone (repair); holes: unvoiced
    with one track's audio missing (skip)."""
    home, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)
    _gregg(home)
    build_package(station, slug="fresh", profile="dead")
    build_package(station, slug="ttb1", voiced=True, profile="funk", artist=TTB)
    build_package(station, slug="ttb2", voiced=True, profile="funk", artist=TTB)
    emerson = build_package(station, slug="emerson", voiced=True, profile="dead")
    (emerson / "broadcast.m3u").unlink()
    holes = build_package(station, slug="holes", profile="dead")
    sorted((holes / "audio").iterdir())[0].unlink()
    return home, station


def _manifests(station: Path) -> dict[str, bytes]:
    return {d.name: (d / "manifest.json").read_bytes() for d in sorted(station.iterdir())}


# --- the plan ---------------------------------------------------------------------------


def test_the_plan_names_every_category_and_counts_clips_exactly(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    err = _lines(result.stderr)
    assert "to voice: 4 packages, 12 clips" in err
    assert "new 1" in err and "fresh" not in err                  # new: counted, not listed
    assert "re-voice 2" in err
    assert 'voiced as funk, now southern (artist rule "Tedeschi Trucks Band"): 2' in err
    assert "ttb1" in err and "ttb2" in err
    assert "repair 1" in err and "emerson" in err
    assert "TTS:" in err
    assert "gregg (Mr. LeNoir) fake - 2 packages" in err
    assert "house fake - 2 packages" in err
    assert "skip holes: 1 audio file(s) missing; re-deliver from llama" in result.stdout
    assert "would voice: holes" not in result.stdout
    assert "4 package(s) would be voiced" in result.stdout
    assert "Proceed?" not in result.output


def test_yes_voices_exactly_the_planned_packages(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    holes_before = (station / "holes" / "manifest.json").read_bytes()
    tasks = _spend(monkeypatch)

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 0, result.output
    assert "to voice: 4 packages, 12 clips" in result.stderr
    assert "Proceed?" not in result.output
    voiced = {line.split(": ", 1)[1] for line in result.stdout.splitlines()
              if line.startswith("voiced: ")}
    assert voiced == {"fresh", "ttb1", "ttb2", "emerson"}
    assert tasks.count("scriptwrite") == 4
    assert (station / "holes" / "manifest.json").read_bytes() == holes_before
    dj = json.loads((station / "ttb1" / "manifest.json").read_text())["dj_audio"]
    assert (dj["presenter"], dj["profile"], dj["profile_source"]) == ("gregg", "southern", "artist")
    states = {r["slug"]: r["state"]
              for r in json.loads(runner.invoke(app, ["status", "--json"]).stdout)}
    assert states == {"fresh": "ready", "ttb1": "ready", "ttb2": "ready", "emerson": "ready",
                      "holes": "pending"}


def test_run_voices_from_the_one_scan_it_planned_from(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    _spend(monkeypatch)
    scans: list[int] = []
    real = cli_mod._station_statuses
    monkeypatch.setattr(cli_mod, "_station_statuses",
                        lambda *a, **k: (scans.append(1), real(*a, **k))[1])

    assert runner.invoke(app, ["run", "--yes"]).exit_code == 0
    assert scans == [1]


def test_the_plan_is_printed_before_the_first_llm_or_tts_provider(tmp_path, monkeypatch):
    """Strict surface 1, ordering: with --yes nothing asks, so only the order
    of calls shows the plan came first. A provider built before the plan
    raises inside `_process_one`, which `run` reports as an error row (exit 1)."""
    _station(tmp_path, monkeypatch)
    planned: list[bool] = []
    real_plan = cli_mod._echo_plan
    monkeypatch.setattr(cli_mod, "_echo_plan",
                        lambda *a, **k: (planned.append(True), real_plan(*a, **k))[1])
    built: list[str] = []
    real_speech = process_mod.speech_provider_for

    def llm(settings, task):
        assert planned, "LLM provider built before the plan was printed"
        built.append(task)
        return FakeProvider(completes=[notes_json()])

    def speech(*a, **k):
        assert planned, "TTS provider built before the plan was printed"
        built.append("tts")
        return real_speech(*a, **k)

    monkeypatch.setattr(process_mod, "provider_for", llm)
    monkeypatch.setattr(process_mod, "speech_provider_for", speech)

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 0, result.output
    assert planned == [True]
    assert built.count("scriptwrite") == 4 and "tts" in built


# --- the question -------------------------------------------------------------------------


def test_a_yes_at_the_prompt_voices(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    tasks = _spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "Proceed? [y/N]" in result.stderr
    assert result.stderr.index("to voice:") < result.stderr.index("Proceed?")
    assert tasks.count("scriptwrite") == 4


def test_a_declined_prompt_voices_nothing_and_exits_0(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "to voice: 4 packages" in result.stderr and "Proceed? [y/N]" in result.stderr
    assert "nothing voiced" in result.stdout
    assert "voiced:" not in result.stdout
    assert _manifests(station) == before


def test_eof_at_the_prompt_spends_nothing(tmp_path, monkeypatch):     # Review Focus 3
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"], input="")

    assert result.exit_code != 0
    assert _manifests(station) == before


def test_no_tty_and_no_yes_refuses_after_the_plan_and_spends_nothing(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "to voice: 4 packages, 12 clips" in result.stderr
    assert "error: refusing to voice without confirmation; pass --yes" in result.stderr
    assert "Proceed?" not in result.output
    assert _manifests(station) == before


def test_dry_run_prints_the_plan_and_never_asks(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    forbid_spend(monkeypatch)
    _tty(monkeypatch)

    plain = runner.invoke(app, ["run", "--dry-run"])
    both = runner.invoke(app, ["run", "--yes", "--dry-run"])

    for result in (plain, both):
        assert result.exit_code == 0, result.output
        assert "to voice: 4 packages" in result.stderr
        assert "Proceed?" not in result.output
        assert "voiced:" not in result.stdout
    assert _manifests(station) == before


def test_nothing_to_voice_means_no_plan_and_no_prompt(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)
    build_package(station, slug="done", voiced=True, profile="dead")
    forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert "to voice:" not in result.output and "Proceed?" not in result.output
    assert "0 package(s) voiced" in result.stdout


# --- exit codes ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["declined", "nothing", "proceeded"])
def test_any_error_row_exits_1(tmp_path, monkeypatch, mode):
    _, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)
    bad = station / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"profile": "dead"}, "tracks": [{}]}))
    if mode != "nothing":
        build_package(station, slug="fresh", profile="dead")
    if mode == "proceeded":
        _spend(monkeypatch)
        result = runner.invoke(app, ["run", "--yes"])
    else:
        forbid_spend(monkeypatch)
        _tty(monkeypatch)
        result = runner.invoke(app, ["run"], input="n\n")

    assert result.exit_code == 1
    assert "error: bad:" in result.stderr
    if mode == "proceeded":
        assert "voiced: fresh" in result.stdout


def test_a_move_whose_target_lost_its_entry_is_an_error_row_and_others_still_voice(tmp_path,
                                                                                    monkeypatch):
    home, station = station_home(tmp_path, monkeypatch)  # no [assign.profiles.southern]
    build_package(station, slug="moved", voiced=True, profile="funk")
    build_package(station, slug="fresh", profile="dead")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    _spend(monkeypatch)

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 1
    assert 'error: moved: move target "southern" has no [assign.profiles] entry' in result.stderr
    assert "to voice: 1 package, 3 clips" in result.stderr
    assert "voiced: fresh" in result.stdout and "voiced: moved" not in result.stdout


@pytest.mark.parametrize("args", [["run", "--dry-run"], ["run"]])
def test_a_ready_package_whose_move_lost_its_entry_is_still_an_error_row(tmp_path, monkeypatch,
                                                                         args):
    """Use-time validation runs before the ready check: a package already
    voiced as its move's target still reports the move, and run exits 1."""
    home, station = station_home(tmp_path, monkeypatch)  # no [assign.profiles.southern]
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    before = (moved / "manifest.json").read_bytes()
    forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert 'error: moved: move target "southern" has no [assign.profiles] entry' in result.stderr
    assert "to voice:" not in result.stderr and "Proceed?" not in result.output
    assert "would voice: moved" not in result.stdout
    assert (moved / "manifest.json").read_bytes() == before


# --- notes, markers, and the malformed-manifest path ---------------------------------------


def test_a_stale_move_is_noted_with_or_without_a_plan(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)
    write_moves_file(home, {"Gone/gone-1999": "southern"})
    build_package(station, slug="fresh", profile="dead")
    forbid_spend(monkeypatch)
    note = "note: 1 recorded move(s) match no package (emcee move --list)"

    assert note in runner.invoke(app, ["run", "--dry-run"]).stderr

    shutil.rmtree(station / "fresh")
    build_package(station, slug="done", voiced=True, profile="dead")
    nothing = runner.invoke(app, ["run"])
    assert nothing.exit_code == 0
    assert note in nothing.stderr


def test_the_plan_marks_a_presenter_that_cannot_be_loaded(tmp_path, monkeypatch):   # Review Focus 4
    _, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)  # no presenters/gregg.toml
    build_package(station, slug="ttb", profile="funk", artist=TTB)
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert "gregg [missing presenters/gregg.toml] 1 package" in _lines(result.stderr)


def test_a_malformed_manifest_does_not_put_a_moved_ready_package_in_the_plan(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    bad = station / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"profile": "dead"}, "tracks": [{}]}))
    build_package(station, slug="fresh", profile="dead")
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert "to voice: 1 package, 3 clips" in result.stderr
    assert "moved" not in _lines(result.stderr)
    assert "would voice: moved" not in result.stdout
