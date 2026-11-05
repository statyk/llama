"""`emcee run --sample N [--seed S]`: voice a random N of what `run` would
voice. The sample is drawn last, after every filter and skip, so it only
picks packages a run would actually voice; a seed reproduces it, and a change
to the station moves only the packages that change touches."""

import json
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from herder import FakeProvider

import emcee.process as process_mod
from emcee.cli import app
from emcee.presenters import Presenter, save_presenter

from tests.helpers import (build_package, forbid_spend, mark_awaiting_fix, notes_json,
                           set_dj_audio, station_home)

runner = CliRunner()
SLUGS = [f"show{i}" for i in range(8)]


def _station(tmp_path, monkeypatch) -> Path:
    _, station = station_home(tmp_path, monkeypatch)
    for slug in SLUGS:
        build_package(station, slug=slug, profile="dead")
    build_package(station, slug="done", voiced=True, profile="dead")
    holes = build_package(station, slug="holes", profile="dead")
    sorted((holes / "audio").iterdir())[0].unlink()
    mark_awaiting_fix(build_package(station, slug="held", profile="dead"))
    attempt = build_package(station, slug="attempt", voiced=True, profile="dead")
    m = json.loads((attempt / "manifest.json").read_text())
    m["dj_audio"] = None                                  # a failed --keep-script attempt
    (attempt / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    build_package(station, slug="elsewhere", profile="funk")
    return station


def _would(text: str) -> list[str]:
    return [line.split()[2] for line in text.splitlines() if line.startswith("would voice:")]


def _dry(*args: str):
    result = runner.invoke(app, ["run", "--dry-run", *args])
    assert result.exit_code == 0, result.output
    return result


def test_the_sample_is_n_of_the_voiceable_packages_and_the_plan_covers_only_them(
        tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    spent = forbid_spend(monkeypatch)

    result = _dry("--profile", "dead", "--sample", "3", "--seed", "7")

    picked = _would(result.stdout)
    assert len(picked) == 3 and set(picked) <= set(SLUGS)
    assert picked == sorted(picked)                       # voiced in station order
    assert "sampled 3 of 8 to voice (seed 7)" in result.stderr       # none of the skipped
    assert "skip held: awaiting fix from llama" in result.stdout
    assert "skip attempt: kept script awaiting retry" in result.stdout
    assert "to voice: 3 packages" in result.stderr
    assert "skip holes: 1 audio file(s) missing" in result.stdout
    assert "3 package(s) would be voiced" in result.stdout
    assert spent == []


def test_the_same_seed_picks_the_same_packages(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    forbid_spend(monkeypatch)

    assert _would(_dry("--sample", "3", "--seed", "7").stdout) == \
        _would(_dry("--sample", "3", "--seed", "7").stdout)


def test_without_a_seed_one_is_printed_and_reproduces_the_sample(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    forbid_spend(monkeypatch)

    first = _dry("--sample", "3")
    seed = re.search(r"sampled 3 of 9 to voice \(seed (\d+)\)", first.stderr).group(1)

    assert _would(_dry("--sample", "3", "--seed", seed).stdout) == _would(first.stdout)


def test_a_station_change_moves_only_the_packages_it_touches(tmp_path, monkeypatch):
    station = _station(tmp_path, monkeypatch)
    forbid_spend(monkeypatch)
    before = _would(_dry("--sample", "3", "--seed", "7").stdout)

    shutil.rmtree(station / next(s for s in SLUGS if s not in before))     # an unsampled one goes
    removed = _dry("--sample", "3", "--seed", "7")
    assert "sampled 3 of 8" in removed.stderr
    assert _would(removed.stdout) == before

    build_package(station, slug="zz-new", profile="dead")                  # a new one arrives
    added = _would(_dry("--sample", "3", "--seed", "7").stdout)
    assert set(added) <= set(before) | {"zz-new"}
    assert len(set(added) & set(before)) >= 2


def test_a_sample_larger_than_the_queue_voices_all_of_it(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    forbid_spend(monkeypatch)

    result = _dry("--sample", "50", "--seed", "1")

    assert sorted(_would(result.stdout)) == sorted(SLUGS + ["elsewhere"])
    assert "sampled 9 of 9 to voice (seed 1)" in result.stderr


def test_yes_voices_exactly_the_sample_the_dry_run_showed(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    planned = _would(_dry("--sample", "2", "--seed", "11").stdout)
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[notes_json()]))

    result = runner.invoke(app, ["run", "--sample", "2", "--seed", "11", "--yes"])

    assert result.exit_code == 0, result.output
    voiced = [line.split(": ", 1)[1] for line in result.stdout.splitlines()
              if line.startswith("voiced: ")]
    assert voiced == planned
    assert "2 package(s) voiced" in result.stdout


def test_nothing_to_voice_prints_no_sample_line(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    build_package(station, slug="done", voiced=True, profile="dead")
    forbid_spend(monkeypatch)

    result = _dry("--sample", "3")

    assert "sampled" not in result.output
    assert "0 package(s) would be voiced" in result.stdout


def test_the_sample_combines_with_keep_script(tmp_path, monkeypatch):
    home, station = station_home(
        tmp_path, monkeypatch, assign='[assign.profiles.southern]\npresenter = "gregg"\n')
    save_presenter(home, Presenter(id="gregg", name="Gregg", sex="male", voice="g-v",
                                   character="c"))
    cur = build_package(station, slug="cur", voiced=True, profile="southern")
    set_dj_audio(cur, presenter="gregg", profile="southern", profile_source="llama")
    monkeypatch.setattr(process_mod, "provider_for",          # no LLM; the fake TTS only counts
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM")))
    first = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--yes"])
    assert first.exit_code == 0, first.output             # cur's clips now carry today's keys
    for slug in SLUGS[:5]:
        pkg = build_package(station, slug=slug, voiced=True, profile="southern")
        set_dj_audio(pkg, presenter="gregg", profile="southern", profile_source="llama")
        (pkg / "broadcast.m3u").unlink()                  # pending: never "already current"
    monkeypatch.setattr(process_mod, "provider_for",          # no LLM; the fake TTS only counts
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM")))

    result = _dry("--keep-script", "--presenter", "gregg", "--sample", "2", "--seed", "3")

    assert len(_would(result.stdout)) == 2 and "cur" not in _would(result.stdout)
    assert "skip cur: every clip is already current" in result.stdout
    assert "sampled 2 of 5 to voice (seed 3)" in result.stderr
    assert "2 package(s) would be voiced" in result.stdout


@pytest.mark.parametrize("args", [["--sample", "0"], ["--seed", "4"]])
def test_bad_sample_flags_are_usage_errors(tmp_path, monkeypatch, args):
    _station(tmp_path, monkeypatch)
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run", *args])

    assert result.exit_code == 2, result.output
