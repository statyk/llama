"""`emcee run --keep-script --presenter ID`: the batch form of
`emcee voice --keep-script`. It clears `dj_audio` on shows that may be
airing, so a failing batch stops."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
import emcee.process as process_mod
from emcee.cli import app
from emcee.presenters import Presenter, save_presenter
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.provider import SpeechError

from tests.helpers import (build_package, forbid_spend, mark_awaiting_fix, set_dj_audio,
                           station_home)

runner = CliRunner()
_ASSIGN = ('[assign.profiles.southern]\npresenter = "gregg"\n\n'
           '[assign.profiles.other]\npresenter = "waldo"\n')
FAKE_TTS = {"backend": "fake", "model": None, "voice": "fake-voice"}


class Speech(FakeSpeechProvider):
    def __init__(self, *, fail: bool = False):
        super().__init__()
        self.fail = fail

    def synthesize(self, text, fmt="mp3", **kw):
        if self.fail:
            self.calls.append(text)
            raise SpeechError("armed to fail")
        return super().synthesize(text, fmt=fmt, **kw)


def _use_speech(monkeypatch, speech) -> None:
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text: speech)


def _forbid_llm(monkeypatch) -> list[str]:
    asked: list[str] = []

    def no_llm(settings, task):
        asked.append(task)
        raise AssertionError(f"LLM provider built: {task}")

    monkeypatch.setattr(process_mod, "provider_for", no_llm)
    return asked


def _tty(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)


def _manifest(pkg: Path) -> dict:
    return json.loads((pkg / "manifest.json").read_text())


def _write(pkg: Path, manifest: dict) -> None:
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _voiced(station: Path, slug: str, *, profile="southern", presenter="gregg", tts=FAKE_TTS):
    pkg = build_package(station, slug=slug, voiced=True, profile=profile)
    fields = {"presenter": presenter, "profile": profile, "profile_source": "llama"}
    if tts is not None:
        fields["tts"] = tts
    set_dj_audio(pkg, **fields)
    return pkg


def _home(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_ASSIGN)
    for pid in ("gregg", "waldo"):
        save_presenter(home, Presenter(id=pid, name=pid.title(), sex="male",
                                       voice=f"{pid}-v", character="c"))
    return home, station


def _station(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    _voiced(station, "ready")
    pending = _voiced(station, "pending")
    (pending / "broadcast.m3u").unlink()
    attempt = _voiced(station, "attempt")
    m = _manifest(attempt)
    m["dj_audio"] = None
    _write(attempt, m)
    build_package(station, slug="nonotes", profile="southern")
    _voiced(station, "elsewhere", profile="other", presenter="waldo")
    _voiced(station, "mismatch", presenter="phil")
    mark_awaiting_fix(_voiced(station, "held"))
    holes = _voiced(station, "holes")
    sorted((holes / "audio").iterdir())[0].unlink()
    return station


def _would(text: str) -> list[str]:
    return sorted(line.split()[2] for line in text.splitlines() if line.startswith("would voice:"))


# --- usage -------------------------------------------------------------------


@pytest.mark.parametrize("args", [
    ["--keep-script"],
    ["--presenter", "gregg"],
    ["--drifted"],
    ["--drifted", "--presenter", "gregg"],
])
def test_flag_combinations_without_their_partner_are_usage_errors(tmp_path, monkeypatch, args):
    _home(tmp_path, monkeypatch)
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--yes", *args])

    assert result.exit_code == 2
    assert "error:" in result.stderr and "--keep-script" in result.stderr
    assert attempts == []


# --- selection ---------------------------------------------------------------


def test_selection_covers_ready_pending_and_failed_attempt_only(tmp_path, monkeypatch):
    station = _station(tmp_path, monkeypatch)
    _use_speech(monkeypatch, Speech())
    before = {d.name: (d / "manifest.json").read_bytes() for d in station.iterdir()}

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert _would(result.stdout) == ["attempt", "pending", "ready"]
    assert "skip mismatch: script was written for phil" in result.stdout
    assert "skip held: awaiting fix from llama" in result.stdout
    assert "skip holes: 1 audio file(s) missing; re-deliver from llama" in result.stdout
    for quiet in ("nonotes", "elsewhere"):
        assert quiet not in result.stdout + result.stderr
    assert "kept script awaiting retry" not in result.stdout     # the plain-run skip is not used here
    assert before == {d.name: (d / "manifest.json").read_bytes() for d in station.iterdir()}


def test_the_id_compares_case_insensitively(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "GrEgG", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert _would(result.stdout) == ["attempt", "pending", "ready"]


def test_an_empty_selection_prints_the_note(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "nobody", "--yes"])

    assert result.exit_code == 0, result.output
    assert "note: no package resolves to presenter nobody" in result.stdout + result.stderr
    assert attempts == []


def test_a_presenter_whose_packages_have_no_script_prints_the_note(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="nonotes", profile="southern")
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--yes"])

    assert result.exit_code == 0, result.output
    assert "note: no package resolves to presenter gregg" in result.stdout + result.stderr
    assert attempts == []


# --- --drifted ---------------------------------------------------------------


def test_drifted_keeps_a_changed_tts_a_missing_record_and_a_null_block(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    _voiced(station, "same")
    _voiced(station, "moved", tts={"backend": "voxtral", "model": "m", "voice": "v"})
    _voiced(station, "norecord", tts=None)
    attempt = _voiced(station, "attempt")
    m = _manifest(attempt)
    m["dj_audio"] = None
    _write(attempt, m)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg",
                                 "--drifted", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert _would(result.stdout) == ["attempt", "moved", "norecord"]


def test_drifted_that_selects_nothing_is_not_the_no_presenter_note(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    _voiced(station, "same")
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg",
                                 "--drifted", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "no package resolves" not in result.stdout + result.stderr
    assert _would(result.stdout) == []


# --- the plan ----------------------------------------------------------------


def test_the_plan_is_one_kept_script_group_with_an_exact_clip_count(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    _voiced(station, "a")
    _voiced(station, "b")
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())
    # a first pass renders every clip, so the keys on disk are today's
    first = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--yes"])
    assert first.exit_code == 0, first.output

    plan = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--dry-run"])
    assert "0 of 6 clips will re-render" in plan.stderr
    assert "  kept script" in plan.stderr and "  repair " not in plan.stderr
    assert "no scriptwriting LLM cost" in plan.stderr

    (station / "a" / "dj-audio" / "99-outro.mp3").unlink()
    (station / "b" / "dj-audio" / "segments.json").write_text(
        json.dumps({"set1-intro.mp3": "old", "set2-intro.mp3": "old", "99-outro.mp3": "old"}))
    plan = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--dry-run"])
    assert "4 of 6 clips will re-render" in plan.stderr

    plan = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--force",
                               "--dry-run"])
    assert "6 of 6 clips will re-render" in plan.stderr


# --- running -----------------------------------------------------------------


def test_the_batch_reaches_tts_from_the_kept_scripts_with_no_llm(tmp_path, monkeypatch):
    station = _station(tmp_path, monkeypatch)
    asked = _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)
    scripts = {s: _manifest(station / s)["dj_notes"] for s in ("ready", "pending", "attempt")}

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--yes"])

    assert result.exit_code == 0, result.output
    assert asked == []
    assert "3 package(s) voiced" in result.stdout
    for slug, script in scripts.items():
        m = _manifest(station / slug)
        assert m["dj_notes"] == script and m["dj_audio"] is not None
    assert _manifest(station / "mismatch")["dj_audio"]["presenter"] == "phil"


def test_the_batch_stops_after_three_consecutive_failures(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    for slug in ("a", "b", "c", "d", "e"):
        _voiced(station, slug)
    _forbid_llm(monkeypatch)
    speech = Speech(fail=True)
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--yes"])

    assert result.exit_code == 1
    assert result.stderr.count("error: ") >= 3
    assert "error: a:" in result.stderr and "error: c:" in result.stderr
    assert "error: d:" not in result.stderr and "error: e:" not in result.stderr
    assert "stopping after 3 consecutive failures" in result.stderr
    assert "not attempted: d, e" in result.stderr
    for slug in ("d", "e"):         # untouched, still airing
        assert _manifest(station / slug)["dj_audio"] is not None
    for slug in ("a", "b", "c"):    # script kept, retry named
        m = _manifest(station / slug)
        assert m["dj_audio"] is None and m["dj_notes"] is not None


def test_a_success_resets_the_consecutive_failure_count(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    for slug in ("a", "b", "c", "d", "e"):
        _voiced(station, slug)
    _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)
    real = cli_mod._process_one

    def flaky(config, moves, pkg, force, **kw):
        if pkg.dir.name in ("a", "b", "d", "e"):
            raise RuntimeError("boom")
        return real(config, moves, pkg, force, **kw)

    monkeypatch.setattr(cli_mod, "_process_one", flaky)

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg", "--yes"])

    assert result.exit_code == 1
    assert "stopping after" not in result.stderr
    assert "1 package(s) voiced" in result.stdout


def test_other_selections_keep_going_after_failures(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    for slug in ("a", "b", "c", "d"):
        build_package(station, slug=slug, profile="southern")
    monkeypatch.setattr(cli_mod, "_process_one",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 1
    assert result.stderr.count("error: ") == 4
    assert "stopping" not in result.stderr


def test_no_tty_and_no_yes_refuses_before_any_spend(tmp_path, monkeypatch):
    station = _station(tmp_path, monkeypatch)
    _use_speech(monkeypatch, Speech())
    before = {d.name: (d / "manifest.json").read_bytes() for d in station.iterdir()}
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: False)

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg"])

    assert result.exit_code == 1
    assert "refusing to voice without confirmation; pass --yes" in result.stderr
    assert "kept script" in result.stderr       # the plan was printed first
    assert before == {d.name: (d / "manifest.json").read_bytes() for d in station.iterdir()}


def test_a_declined_question_voices_nothing(tmp_path, monkeypatch):
    station = _station(tmp_path, monkeypatch)
    _use_speech(monkeypatch, Speech())
    _tty(monkeypatch)
    before = {d.name: (d / "manifest.json").read_bytes() for d in station.iterdir()}

    result = runner.invoke(app, ["run", "--keep-script", "--presenter", "gregg"], input="n\n")

    assert "nothing voiced" in result.stdout
    assert before == {d.name: (d / "manifest.json").read_bytes() for d in station.iterdir()}
