"""`emcee voice --keep-script`: re-voice a package from its existing script.

The failure path is a strict surface: nothing here may ever lose a script.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
import emcee.process as process_mod
from emcee.audio import _synthesize_dj_audio, adopt_clips
from emcee.cli import app
from emcee.models import ScriptNotes
from emcee.presenters import Presenter
from emcee.process import script_writer_mismatch
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.provider import SpeechError

from herder import FakeProvider

from tests.helpers import HOUSE_TTS, build_package, forbid_spend, notes_json, station_home

runner = CliRunner()


def _notes(**overrides) -> ScriptNotes:
    fields = {"context": "Spring '73 tour",
              "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                             "2": "China Cat Sunflower leads set two."},
              "outro": "I Know You Rider sends us off. Thanks for listening.",
              "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    return ScriptNotes(**{**fields, **overrides})


def _clips(pkg: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in (pkg / "dj-audio").glob("*.mp3")}


# --- adopt_clips -----------------------------------------------------------


def _stale_clips(pkg: Path) -> None:
    audio = pkg / "dj-audio"
    audio.mkdir()
    for name in ("set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"):
        (audio / name).write_bytes(f"take of {name}".encode())
    (audio / "segments.json").write_text(json.dumps({
        "set1-intro.mp3": "old", "set2-intro.mp3": "old", "99-outro.mp3": "old"}))


def test_adopted_clips_render_nothing_and_stay_out_of_rendered(tmp_path):
    _stale_clips(tmp_path)
    before = _clips(tmp_path)

    adopt_clips(tmp_path, _notes(), FakeSpeechProvider(), chunking=None)

    assert _clips(tmp_path) == before
    speech = FakeSpeechProvider()
    rendered: set[str] = set()
    _synthesize_dj_audio(tmp_path, _notes(), speech, False, chunking=None, rendered=rendered)
    assert speech.calls == []
    assert rendered == set()      # an adopted clip is not a real render
    assert _clips(tmp_path) == before


def test_a_skipped_stem_keeps_its_old_key(tmp_path):
    _stale_clips(tmp_path)

    adopt_clips(tmp_path, _notes(), FakeSpeechProvider(), chunking=None, skip={"set1-intro"})

    keys = json.loads((tmp_path / "dj-audio" / "segments.json").read_text())
    assert keys["set1-intro.mp3"] == "old"
    assert keys["set2-intro.mp3"] != "old" and keys["99-outro.mp3"] != "old"


def test_a_missing_clip_is_not_adopted(tmp_path):
    _stale_clips(tmp_path)
    (tmp_path / "dj-audio" / "99-outro.mp3").unlink()

    adopt_clips(tmp_path, _notes(), FakeSpeechProvider(), chunking=None)

    speech = FakeSpeechProvider()
    _synthesize_dj_audio(tmp_path, _notes(), speech, False, chunking=None)
    assert speech.calls == [_notes().outro]


# --- emcee voice --keep-script ---------------------------------------------

CLEAN_S1 = "China Cat Sunflower leads set two."
BLOCKED_S2 = "The climax comes a little early tonight."
SEG2 = f"{CLEAN_S1} {BLOCKED_S2}"
REVISED = f"{CLEAN_S1} The peak arrives a little early tonight."
RETRY = "--keep-script` to retry"


class Speech(FakeSpeechProvider):
    """A fake that also refuses (SpeechError) any text holding `fail_on`."""

    def __init__(self, *, fail_on: str | None = None, **kw):
        super().__init__(**kw)
        self.fail_on = fail_on

    def synthesize(self, text, fmt="mp3", **kw):
        if self.fail_on is not None and self.fail_on in text:
            self.calls.append(text)
            raise SpeechError("armed to fail on this text")
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


def _arm_rephrase(monkeypatch, *replies) -> list[str]:
    """Only the rephrase task may be built; scriptwrite fails the test."""
    asked: list[str] = []
    provider = FakeProvider(completes=[json.dumps({"text": t}) for t in replies])

    def only_rephrase(settings, task):
        asked.append(task)
        assert task == "rephrase"
        return provider

    monkeypatch.setattr(process_mod, "provider_for", only_rephrase)
    return asked


def _voiced(tmp_path, monkeypatch, *, assign: str = "", tts: str = HOUSE_TTS) -> Path:
    """A really voiced package whose clips hold identifiable bytes."""
    _, station = station_home(tmp_path, monkeypatch, assign=assign, tts=tts)
    pkg_dir = build_package(station, slug="showA")
    _clear_voicing(pkg_dir)
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[notes_json()]))
    result = runner.invoke(app, ["voice", str(pkg_dir)])
    assert result.exit_code == 0, result.output
    for name in _clips(pkg_dir):
        (pkg_dir / "dj-audio" / name).write_bytes(f"take of {name}".encode())
    return pkg_dir


def _clear_voicing(pkg_dir: Path) -> None:
    manifest = _manifest(pkg_dir)
    manifest["dj_notes"] = manifest["dj_audio"] = None
    _write_manifest(pkg_dir, manifest)


def _manifest(pkg_dir: Path) -> dict:
    return json.loads((pkg_dir / "manifest.json").read_text())


def _write_manifest(pkg_dir: Path, manifest: dict) -> None:
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _set_script(pkg_dir: Path, **fields) -> None:
    manifest = _manifest(pkg_dir)
    manifest["dj_notes"].update(fields)
    _write_manifest(pkg_dir, manifest)


def _stale_keys(pkg_dir: Path) -> None:
    """Every clip's key as a package voiced under an older formula has it."""
    sidecar = pkg_dir / "dj-audio" / "segments.json"
    sidecar.write_text(json.dumps({name: "older-formula" for name in _clips(pkg_dir)}))


def _tree(pkg_dir: Path) -> dict[str, bytes]:
    return {str(p.relative_to(pkg_dir)): p.read_bytes()
            for p in sorted(pkg_dir.rglob("*")) if p.is_file()}


def test_a_kept_script_reaches_tts_unchanged_with_no_llm(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    script = _manifest(pkg_dir)["dj_notes"]
    (pkg_dir / "dj-notes.md").write_text("the operator's notes file\n")
    asked = _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--force"])

    assert result.exit_code == 0, result.output
    assert asked == []
    assert sorted(speech.calls) == sorted([*script["set_intros"].values(), script["outro"]])
    manifest = _manifest(pkg_dir)
    assert manifest["dj_notes"] == script
    assert manifest["dj_audio"] is not None
    assert (pkg_dir / "dj-notes.md").read_text() == "the operator's notes file\n"


def test_keep_script_writes_a_missing_notes_file(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    (pkg_dir / "dj-notes.md").unlink()
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output
    assert "Thanks for listening" in (pkg_dir / "dj-notes.md").read_text()


def test_keep_script_alone_compares_keys_as_usual(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _stale_keys(pkg_dir)
    _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output
    assert len(speech.calls) == 3


def test_a_tts_failure_keeps_the_script_and_a_retry_succeeds(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    script = _manifest(pkg_dir)["dj_notes"]
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech(fail=True))

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--force"])

    assert result.exit_code == 1
    assert f"`emcee voice {pkg_dir} {RETRY}" in result.stderr
    manifest = _manifest(pkg_dir)
    assert manifest["dj_notes"] == script
    assert manifest["dj_audio"] is None

    _use_speech(monkeypatch, Speech())
    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--force"])

    assert result.exit_code == 0, result.output
    manifest = _manifest(pkg_dir)
    assert manifest["dj_notes"] == script
    assert manifest["dj_audio"] is not None


def test_a_failure_with_no_exception_details_still_prints_the_retry(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    def blowup(*args, **kwargs):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(cli_mod, "process_package", blowup)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 1
    assert "RuntimeError: synthetic" in result.stderr
    assert RETRY in result.stderr


def test_plain_voice_still_clears_both_blocks_on_failure(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[notes_json()]))
    _use_speech(monkeypatch, Speech(fail=True))

    result = runner.invoke(app, ["voice", str(pkg_dir), "--force"])

    assert result.exit_code == 1
    assert RETRY not in result.stderr
    manifest = _manifest(pkg_dir)
    assert manifest["dj_notes"] is None and manifest["dj_audio"] is None


@pytest.mark.parametrize("recorded, shown", [("phil", "phil"), ("absent", "?")])
def test_a_presenter_mismatch_refuses_with_nothing_written(tmp_path, monkeypatch, recorded, shown):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    if recorded == "absent":
        del manifest["dj_audio"]["presenter"]
    else:
        manifest["dj_audio"]["presenter"] = recorded
    _write_manifest(pkg_dir, manifest)
    before = _tree(pkg_dir)
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "99-outro"])

    assert result.exit_code == 1
    assert f"script was written for {shown}; re-voice without --keep-script" in result.stderr
    assert RETRY not in result.stderr
    assert attempts == []
    assert _tree(pkg_dir) == before


def test_a_recorded_null_presenter_is_the_house_voice(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    assert _manifest(pkg_dir)["dj_audio"]["presenter"] is None
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output


def test_the_presenter_check_reads_case_insensitively_and_passes_a_null_block():
    presenter = Presenter(id="BillyG", name="Billy", sex="male", voice="v", character="c")
    voiced_by = lambda value: {"dj_audio": {"presenter": value}}  # noqa: E731

    assert script_writer_mismatch(voiced_by("billyg"), presenter) is None
    assert script_writer_mismatch(voiced_by("waldo"), presenter) == "waldo"
    assert script_writer_mismatch(voiced_by(None), presenter) == "house"
    assert script_writer_mismatch(voiced_by("BillyG"), None) == "BillyG"
    assert script_writer_mismatch({"dj_audio": {}}, None) == "?"
    assert script_writer_mismatch({"dj_audio": None}, presenter) is None


@pytest.mark.parametrize("script", [None, {"outro": "no intros"}, "not a block"])
def test_no_usable_script_refuses_before_anything_is_touched(tmp_path, monkeypatch, script):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_notes"] = script
    _write_manifest(pkg_dir, manifest)
    before = _tree(pkg_dir)
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "99-outro"])

    assert result.exit_code == 1
    assert ("error: showA: no script to keep; run emcee voice without --keep-script"
            in result.stderr)
    assert RETRY not in result.stderr
    assert attempts == []
    assert _tree(pkg_dir) == before


def test_force_fresh_and_keep_script_together_are_a_usage_error(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    before = _tree(pkg_dir)
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--force",
                                 "--fresh", "99-outro"])

    assert result.exit_code == 2
    assert "--fresh" in result.stderr and "--force" in result.stderr
    assert attempts == []
    assert _tree(pkg_dir) == before


def test_force_with_fresh_stays_legal_without_keep_script(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[notes_json()]))
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--force", "--fresh", "99-outro"])

    assert result.exit_code == 0, result.output


# --- --fresh with --keep-script: adoption ------------------------------------


def test_fresh_keep_script_renders_exactly_the_named_clip(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    script = _manifest(pkg_dir)["dj_notes"]
    _stale_keys(pkg_dir)
    before = _clips(pkg_dir)
    _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "set2-intro"])

    assert result.exit_code == 0, result.output
    assert speech.calls == [script["set_intros"]["2"]]
    after = _clips(pkg_dir)
    assert after["set2-intro.mp3"] != before["set2-intro.mp3"]
    assert after["set1-intro.mp3"] == before["set1-intro.mp3"]
    assert after["99-outro.mp3"] == before["99-outro.mp3"]


def test_a_missing_non_named_clip_renders_as_usual(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    script = _manifest(pkg_dir)["dj_notes"]
    _stale_keys(pkg_dir)
    (pkg_dir / "dj-audio" / "99-outro.mp3").unlink()
    _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "set2-intro"])

    assert result.exit_code == 0, result.output
    assert sorted(speech.calls) == sorted([script["set_intros"]["2"], script["outro"]])


def test_a_failed_fresh_retried_with_keep_script_alone_renders_only_that_clip(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    script = _manifest(pkg_dir)["dj_notes"]
    _stale_keys(pkg_dir)
    before = _clips(pkg_dir)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech(fail=True))

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "set2-intro"])

    assert result.exit_code == 1
    assert _manifest(pkg_dir)["dj_audio"] is None
    speech = Speech()
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output
    assert speech.calls == [script["set_intros"]["2"]]
    after = _clips(pkg_dir)
    assert after["set1-intro.mp3"] == before["set1-intro.mp3"]
    assert after["99-outro.mp3"] == before["99-outro.mp3"]


def test_a_bed_failure_during_adoption_discards_nothing(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    home = tmp_path / "home"
    config = (home / "config.toml").read_text().replace(
        'voice = "house-voice"', f'voice = "house-voice"\nbed = "{tmp_path / "no-such-bed.wav"}"')
    (home / "config.toml").write_text(config)
    before = _tree(pkg_dir)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "set2-intro"])

    assert result.exit_code == 1
    assert _tree(pkg_dir) == before


def test_a_failed_preflight_changes_nothing_and_prints_no_retry(tmp_path, monkeypatch):
    """A `--keep-script` retry here would drop --fresh and re-render every
    clip of a package nothing has happened to; the same command is the retry."""
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _stale_keys(pkg_dir)
    before = _tree(pkg_dir)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech(preflight_fail=True))

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "set2-intro"])

    assert result.exit_code == 1
    assert RETRY not in result.stderr
    assert _tree(pkg_dir) == before


WARNING = "re-rolled clips will sound different from the kept ones"


def test_a_tts_change_warns_once_when_re_rolling(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"]["tts"]["model"] = "last-years-model"
    _write_manifest(pkg_dir, manifest)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "99-outro"])

    assert result.exit_code == 0, result.output
    assert result.stderr.count(WARNING) == 1


def test_a_backend_change_warns_too(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"]["tts"]["backend"] = "voxtral"
    _write_manifest(pkg_dir, manifest)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "99-outro"])

    assert result.stderr.count(WARNING) == 1


def test_the_same_tts_does_not_warn(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "99-outro"])

    assert result.exit_code == 0, result.output
    assert WARNING not in result.output


def test_no_tts_record_does_not_warn(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    del manifest["dj_audio"]["tts"]
    _write_manifest(pkg_dir, manifest)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "99-outro"])

    assert result.exit_code == 0, result.output
    assert WARNING not in result.output


# --- content-filter repair under --keep-script -------------------------------


def test_repair_persists_the_reworded_segment(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _set_script(pkg_dir, set_intros={"1": _notes().set_intros["1"], "2": SEG2})
    asked = _arm_rephrase(monkeypatch, REVISED)
    speech = Speech(block="climax")
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output
    assert asked == ["rephrase"]
    assert _manifest(pkg_dir)["dj_notes"]["set_intros"]["2"] == REVISED
    assert "The peak arrives" in (pkg_dir / "dj-notes.md").read_text()
    assert speech.calls[-1] == REVISED


def test_a_failure_after_a_repair_keeps_the_reworded_text(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _set_script(pkg_dir, set_intros={"1": _notes().set_intros["1"], "2": SEG2})
    (pkg_dir / "dj-audio" / "99-outro.mp3").unlink()
    _arm_rephrase(monkeypatch, REVISED)
    _use_speech(monkeypatch, Speech(block="climax", fail_on="Thanks for listening"))

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 1
    manifest = _manifest(pkg_dir)
    assert manifest["dj_notes"]["set_intros"]["2"] == REVISED
    assert manifest["dj_audio"] is None
    assert "The peak arrives" in (pkg_dir / "dj-notes.md").read_text()

    # The retry voices the reworded text and pays for the outro alone.
    _forbid_llm(monkeypatch)
    speech = Speech()
    _use_speech(monkeypatch, speech)
    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output
    assert speech.calls == [_notes().outro]
    assert _manifest(pkg_dir)["dj_notes"]["set_intros"]["2"] == REVISED


def test_a_failed_repair_names_the_keep_script_retry_once(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _set_script(pkg_dir, set_intros={"1": _notes().set_intros["1"], "2": SEG2})
    script = _manifest(pkg_dir)["dj_notes"]
    _arm_rephrase(monkeypatch, SEG2, SEG2)    # unchanged twice: both attempts fail
    _use_speech(monkeypatch, Speech(block="climax"))

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 1
    assert result.stderr.count(RETRY) == 1
    assert "for a fresh script" not in result.stderr
    assert _manifest(pkg_dir)["dj_notes"] == script


def test_adopted_clips_hold_across_a_repair_round(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    _set_script(pkg_dir, set_intros={"1": _notes().set_intros["1"], "2": SEG2})
    _stale_keys(pkg_dir)
    before = _clips(pkg_dir)
    _arm_rephrase(monkeypatch, REVISED)
    speech = Speech(block="climax")
    _use_speech(monkeypatch, speech)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script", "--fresh", "set2-intro"])

    assert result.exit_code == 0, result.output
    assert _notes().set_intros["1"] not in speech.calls
    assert _notes().outro not in speech.calls
    after = _clips(pkg_dir)
    assert after["set1-intro.mp3"] == before["set1-intro.mp3"]
    assert after["99-outro.mp3"] == before["99-outro.mp3"]


def test_voice_help_describes_keep_script(monkeypatch, tmp_path):
    result = runner.invoke(app, ["voice", "--help"], env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})

    assert "--keep-script" in result.output
    assert "there is no way around this" not in result.output


# --- the failed-attempt state (dj_notes present, dj_audio null) ---------------


def _failed_attempt(tmp_path, monkeypatch) -> Path:
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"] = None
    _write_manifest(pkg_dir, manifest)
    return pkg_dir


def test_status_reads_kept_script(tmp_path, monkeypatch):
    _failed_attempt(tmp_path, monkeypatch)

    table = runner.invoke(app, ["status", "--list"])
    rows = json.loads(runner.invoke(app, ["status", "--json"]).output)

    assert table.exit_code == 0, table.output
    assert rows[0]["state"] == "pending"
    assert rows[0]["reasons"] == ["kept script"]
    assert "kept script" in table.output and "unvoiced" not in table.output


def test_a_never_voiced_package_still_reads_unvoiced(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    build_package(station, slug="showA")

    rows = json.loads(runner.invoke(app, ["status", "--json"]).output)

    assert "no DJ audio (unvoiced)" in rows[0]["reasons"]
    assert "kept script" not in rows[0]["reasons"]


@pytest.mark.parametrize("args", [["--yes"], ["--dry-run"]])
def test_plain_run_skips_the_failed_attempt_state(tmp_path, monkeypatch, args):
    pkg_dir = _failed_attempt(tmp_path, monkeypatch)
    before = _tree(pkg_dir)
    attempts = forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", *args])

    assert result.exit_code == 0, result.output
    assert ("skip showA: kept script awaiting retry (emcee voice showA --keep-script)"
            in result.output)
    assert "would voice" not in result.output
    assert "to voice:" not in result.output
    assert "0 package(s)" in result.output
    assert attempts == []
    assert _tree(pkg_dir) == before


def test_missing_track_audio_wins_over_the_kept_script_skip(tmp_path, monkeypatch):
    pkg_dir = _failed_attempt(tmp_path, monkeypatch)
    next((pkg_dir / "audio").iterdir()).unlink()

    result = runner.invoke(app, ["run", "--yes"])

    assert "re-deliver from llama" in result.output
    assert "kept script" not in result.output


def test_plain_voice_on_the_failed_attempt_state_writes_a_fresh_script(tmp_path, monkeypatch):
    pkg_dir = _failed_attempt(tmp_path, monkeypatch)
    fresh = json.loads(notes_json())
    fresh["outro"] = "A brand new outro for I Know You Rider. Thanks for listening."
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[json.dumps(fresh)]))

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 0, result.output
    assert _manifest(pkg_dir)["dj_notes"]["outro"] == fresh["outro"]


def test_keep_script_retries_the_failed_attempt_state(tmp_path, monkeypatch):
    pkg_dir = _failed_attempt(tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)
    _use_speech(monkeypatch, Speech())

    result = runner.invoke(app, ["voice", str(pkg_dir), "--keep-script"])

    assert result.exit_code == 0, result.output
    assert json.loads(runner.invoke(app, ["status", "--json"]).output)[0]["state"] == "ready"


def test_move_does_not_promise_a_run_for_the_failed_attempt_state(tmp_path, monkeypatch):
    _failed_attempt(tmp_path, monkeypatch)
    config = tmp_path / "home" / "config.toml"
    config.write_text(config.read_text() + '\n[assign.profiles.funk]\npresenter = "kurt"\n')

    result = runner.invoke(app, ["move", "showA", "funk"])

    assert result.exit_code == 0, result.output
    assert "kept script awaiting retry" in result.output
    assert "on the next emcee run" not in result.output
