"""`emcee run` and `emcee voice` take the station lock per package.

The lock (`emcee.station_lock`) is held from `_process_one`'s manifest
re-read through its last write, and released before the next package, so
llama is shut out for one package's voicing at most. No lock is held while
`run` asks `Proceed?`. A held lock stops `run` at that package (`not
attempted: ...`, exit 1) and refuses `voice`. `--dry-run`, `status`, `move`
and `say` never take it. Fake LLM and TTS throughout, as in test_run_cmd.py.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
import emcee.process as process_mod
import emcee.station_lock as sl
from emcee.cli import app
from emcee.presenters import Presenter, save_presenter
from emcee.station_lock import LOCK_NAME, token_of
from emcee.tts.fake import FakeSpeechProvider

from herder import FakeProvider

from tests.helpers import (build_package, forbid_spend, notes_json, set_dj_audio,
                           station_home)

runner = CliRunner()
FOREIGN = (b"lma-station-lock 1 " + b"b" * 32 + b"\ntool: llama\ncommand: deliver gd73\n"
           b"host: mac\npid: 999\nstarted: 2026-11-04T09:00:00-08:00\n")


@pytest.fixture(autouse=True)
def _no_held_lock():
    sl._held = None
    yield
    sl._held = None


def _arm_fake_llm(monkeypatch) -> list[str]:
    asked: list[str] = []

    def provider(settings, task):
        asked.append(task)
        return FakeProvider(completes=[notes_json()])

    monkeypatch.setattr(process_mod, "provider_for", provider)
    return asked


def _record_process_one(monkeypatch, lock_dirs, *, call_real=True) -> list:
    """Wrap `cli._process_one`: on entry record, per directory in
    `lock_dirs`, (slug, dir, lock exists, token or None); then run it."""
    seen: list = []
    real = cli_mod._process_one

    def wrapped(config, moves, pkg, force, *args, **kwargs):
        for d in lock_dirs:
            path = Path(d) / LOCK_NAME
            raw = path.read_bytes() if path.exists() else None
            seen.append((pkg.dir.absolute().name, Path(d), raw is not None,
                         None if raw is None else token_of(raw)))
        if call_real:
            return real(config, moves, pkg, force, *args, **kwargs)

    monkeypatch.setattr(cli_mod, "_process_one", wrapped)
    return seen


def _bytes(pkg: Path) -> bytes:
    return (pkg / "manifest.json").read_bytes()


# --- run ---------------------------------------------------------------------------


def test_run_holds_the_lock_for_each_package_and_releases_between(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_fake_llm(monkeypatch)
    pkgs = [build_package(station, slug=s) for s in ("pkg1", "pkg2", "pkg3")]
    seen = _record_process_one(monkeypatch, [station])

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 0, result.output
    assert [s[0] for s in seen] == ["pkg1", "pkg2", "pkg3"]
    assert all(exists for _, _, exists, _ in seen)
    tokens = [token for *_, token in seen]
    assert None not in tokens and len(set(tokens)) == 3
    assert not (station / LOCK_NAME).exists()
    for pkg in pkgs:
        assert json.loads(_bytes(pkg))["dj_audio"] is not None
        assert not (pkg / LOCK_NAME).exists()


def test_run_takes_no_lock_while_asking_proceed(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_fake_llm(monkeypatch)
    build_package(station, slug="pkg1")
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    asked: list[bool] = []

    def confirm(*args, **kwargs):
        asked.append(True)
        assert not (station / LOCK_NAME).exists()
        assert sl._held is None
        return True

    monkeypatch.setattr(cli_mod.typer, "confirm", confirm)
    seen = _record_process_one(monkeypatch, [station])

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert asked == [True]
    assert [s[2] for s in seen] == [True]
    assert not (station / LOCK_NAME).exists()


def test_run_dry_run_takes_no_lock(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    spend = forbid_spend(monkeypatch)
    pkg = build_package(station, slug="pkg1")
    (station / LOCK_NAME).write_bytes(FOREIGN)
    before = _bytes(pkg)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "1 package(s) would be voiced" in result.stdout
    assert (station / LOCK_NAME).read_bytes() == FOREIGN
    assert _bytes(pkg) == before
    assert spend == []


def test_run_stops_at_a_held_lock_and_lists_what_it_did_not_attempt(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_fake_llm(monkeypatch)
    pkg1, pkg2, pkg3 = (build_package(station, slug=s) for s in ("pkg1", "pkg2", "pkg3"))
    before = {p: _bytes(p) for p in (pkg2, pkg3)}
    real_release = sl.release
    releases: list[int] = []

    def release_then_llama_takes_it(held):
        real_release(held)
        releases.append(1)
        if len(releases) == 1:          # llama grabs the lock between pkg1 and pkg2
            (station / LOCK_NAME).write_bytes(FOREIGN)

    monkeypatch.setattr(sl, "release", release_then_llama_takes_it)

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 1
    assert "voiced: pkg1" in result.stdout
    assert json.loads(_bytes(pkg1))["dj_audio"] is not None
    assert "error: pkg2: the station is locked by another writer" in result.stderr
    assert "  tool: llama" in result.stderr
    assert "  command: deliver gd73" in result.stderr
    assert "emcee lock show" in result.stderr and "emcee lock clear" in result.stderr
    assert "not attempted: pkg2, pkg3" in result.stderr
    assert result.stderr.count("not attempted") == 1 and "error: pkg3" not in result.stderr
    assert "voiced: pkg2" not in result.stdout and "voiced: pkg3" not in result.stdout
    for p, raw in before.items():
        assert _bytes(p) == raw
    assert (station / LOCK_NAME).read_bytes() == FOREIGN    # never broken
    assert releases == [1]                                    # the refused acquire held nothing


def test_run_keep_script_also_takes_the_lock(tmp_path, monkeypatch):
    home, station = station_home(
        tmp_path, monkeypatch, assign='[assign.profiles.southern]\npresenter = "gregg"\n')
    save_presenter(home, Presenter(id="gregg", name="Gregg", sex="male",
                                   voice="gregg-v", character="c"))
    pkg = build_package(station, slug="pkg1", voiced=True, profile="southern")
    set_dj_audio(pkg, presenter="gregg", profile="southern", profile_source="llama",
                 tts={"backend": "fake", "model": None, "voice": "gregg-v"})
    m = json.loads(_bytes(pkg))
    m["dj_notes"] = json.loads(notes_json())
    (pkg / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    asked = _arm_fake_llm(monkeypatch)
    seen = _record_process_one(monkeypatch, [station])

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg",
                                 "--force", "--yes"])

    assert result.exit_code == 0, result.output
    assert "voiced: pkg1" in result.stdout
    assert [(s[0], s[2]) for s in seen] == [("pkg1", True)]
    assert asked == []
    assert not (station / LOCK_NAME).exists()


def test_lock_released_when_process_one_raises(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_fake_llm(monkeypatch)
    build_package(station, slug="pkg1")
    pkg2 = build_package(station, slug="pkg2")
    real = process_mod.process_package

    def flaky(config, pkg, speech, force=False, **kwargs):
        if pkg.dir.name == "pkg1":
            raise RuntimeError("synthetic TTS blowup")
        return real(config, pkg, speech, force, **kwargs)

    monkeypatch.setattr(cli_mod, "process_package", flaky)
    seen = _record_process_one(monkeypatch, [station])

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 1
    assert "error: pkg1: RuntimeError: synthetic TTS blowup" in result.stderr
    assert "not attempted" not in result.stderr
    assert "voiced: pkg2" in result.stdout
    assert json.loads(_bytes(pkg2))["dj_audio"] is not None
    assert [(s[0], s[2]) for s in seen] == [("pkg1", True), ("pkg2", True)]
    assert not (station / LOCK_NAME).exists()


# --- voice -------------------------------------------------------------------------


def test_voice_takes_the_lock_at_the_package_parent(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_fake_llm(monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    pkg = build_package(elsewhere, slug="pkg1")
    seen = _record_process_one(monkeypatch, [elsewhere, station, pkg])

    result = runner.invoke(app, ["voice", str(pkg)])

    assert result.exit_code == 0, result.output
    assert [(s[1], s[2]) for s in seen] == [(elsewhere, True), (station, False), (pkg, False)]
    assert not (elsewhere / LOCK_NAME).exists()


def test_voice_dot_from_inside_the_package_locks_the_delivered_folder(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_fake_llm(monkeypatch)
    pkg = build_package(station, slug="pkg1")
    monkeypatch.chdir(pkg)
    seen = _record_process_one(monkeypatch, [station, pkg])

    result = runner.invoke(app, ["voice", "."])

    assert result.exit_code == 0, result.output
    assert [(s[1], s[2]) for s in seen] == [(station, True), (pkg, False)]
    assert not (station / LOCK_NAME).exists() and not (pkg / LOCK_NAME).exists()


def test_voice_refuses_a_held_lock(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    spend = forbid_spend(monkeypatch)
    pkg = build_package(station, slug="pkg1", voiced=True)
    (station / LOCK_NAME).write_bytes(FOREIGN)
    before = _bytes(pkg)

    result = runner.invoke(app, ["voice", "pkg1"])

    assert result.exit_code == 1
    assert "error: pkg1: the station is locked by another writer" in result.stderr
    assert "  pid: 999" in result.stderr
    assert "emcee lock clear" in result.stderr
    assert _bytes(pkg) == before
    assert spend == []
    assert (station / LOCK_NAME).read_bytes() == FOREIGN


# --- commands that take no lock ----------------------------------------------------


def test_status_move_and_say_take_no_lock(tmp_path, monkeypatch):
    home, station = station_home(
        tmp_path, monkeypatch, assign='[assign.profiles.southern]\npresenter = "gregg"\n')
    forbid_spend(monkeypatch)
    build_package(station, slug="pkg1", voiced=True, profile="funk")
    (station / LOCK_NAME).write_bytes(FOREIGN)
    monkeypatch.setattr(cli_mod, "ad_hoc_speech", lambda config, **kw: FakeSpeechProvider())
    text = tmp_path / "say.txt"
    text.write_text("A short read.")

    for args in (["status"], ["status", "--list"], ["move", "pkg1", "southern"],
                 ["say", str(text), "--no-bed"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (args, result.output)
        assert (station / LOCK_NAME).read_bytes() == FOREIGN, args
    assert (tmp_path / "say.mp3").exists()
    assert json.loads((home / "moves.json").read_text())
