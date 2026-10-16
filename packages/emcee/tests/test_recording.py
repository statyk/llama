"""What emcee records in dj_audio, and one resolution per package (spec
section 4; use-time move validation and the missing-file guard for
`emcee voice`, spec section 3)."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from herder import FakeProvider

import emcee.process as process_mod
from emcee.cli import _process_one, app
from emcee.config import load_config
from emcee.errors import EmceeError
from emcee.models import DJAudioBlock, DJClips
from emcee.moves import load_moves
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.station import readiness
from emcee.tts.voxtral import DEFAULT_MODEL as VOX_DEFAULT

from tests.helpers import (build_package, forbid_spend, no_moves, notes_json, set_dj_audio,
                           station_home, write_moves_file)

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = ('[assign.profiles.southern]\npresenter = "gregg"\ntitle = "Southern Hour"\n\n'
         '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')


def _arm_llm(monkeypatch) -> None:
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[notes_json()]))


def _gregg(home: Path, **kw) -> None:
    save_presenter(home, Presenter(id="gregg", name="Mr. LeNoir", sex="male",
                                   voice="gregg-preset", character="Smoky.", **kw))


def _dj_audio(pkg_dir: Path) -> dict:
    return json.loads((pkg_dir / "manifest.json").read_text())["dj_audio"]


def _fake_synth(record: list | None = None):
    def synth(pkg_dir, notes, speech, force, chunk=False, lexicon=None, bed=None, rendered=None):
        if record is not None:
            record.append((speech.voice, bed.path.name if bed is not None else None))
        return DJClips(set_intros={k: f"dj-audio/set{k}-intro.mp3" for k in notes.set_intros},
                       outro="dj-audio/99-outro.mp3")
    return synth


def test_a_voiced_package_records_its_profile_source_and_tts(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="showA", profile=None)

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 0, result.output
    dj = _dj_audio(pkg_dir)
    assert dj["presenter"] is None
    assert "profile" in dj and dj["profile"] is None          # null serialized, not omitted
    assert dj["profile_source"] == "llama"
    assert dj["tts"] == {"backend": "fake", "model": "fake-model", "voice": "fake-voice"}


def test_voice_persona_title_bed_and_record_all_follow_the_effective_profile(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch,
                                 assign=_RULE + '\n[assign.profiles.funk]\npresenter = "fred"\n',
                                 tts='[tts]\nbackend = "fake"\nvoice = "house-voice"\n'
                                     'bed = "/beds/house.wav"\n')
    _gregg(home, bed="/beds/gregg.wav")
    save_presenter(home, Presenter(id="fred", name="Fred", sex="male", voice="fred-preset",
                                   character="x", bed="/beds/fred.wav"))
    _arm_llm(monkeypatch)
    scripted: dict = {}
    real_write = process_mod.write_script

    def spy_write(pkg, provider, presenter, title):
        scripted.update(presenter=presenter.id if presenter else None, title=title)
        return real_write(pkg, provider, presenter, title)

    class Tagged:
        def __init__(self, voice):
            self.voice, self.model = voice, "tagged-model"

        def synthesize(self, *a, **k):
            raise AssertionError("_synthesize_dj_audio is faked")

        def preflight(self):
            pass

        def close(self):
            pass

    synth_calls: list = []
    monkeypatch.setattr(process_mod, "write_script", spy_write)
    monkeypatch.setattr(process_mod, "_synthesize_dj_audio", _fake_synth(synth_calls))
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text: Tagged(voice))
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 0, result.output
    assert scripted == {"presenter": "gregg", "title": "Southern Hour"}
    assert synth_calls == [("gregg-preset", "gregg.wav")]
    dj = _dj_audio(pkg_dir)
    assert (dj["presenter"], dj["profile"], dj["profile_source"]) == ("gregg", "southern", "artist")
    assert dj["tts"] == {"backend": "fake", "model": "tagged-model", "voice": "gregg-preset"}


def test_an_artist_rule_voicing_leaves_the_package_ready(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    _gregg(home)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)

    assert runner.invoke(app, ["voice", "ttb"]).exit_code == 0

    assert readiness(Package(pkg_dir), load_config(), no_moves()) == (True, [])


def test_process_one_resolves_the_assignment_exactly_once(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_RULE)
    _gregg(home)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)
    seen: list = []
    real = process_mod.resolve_assignment

    def counting(config, profile):
        seen.append(profile)
        return real(config, profile)

    monkeypatch.setattr(process_mod, "resolve_assignment", counting)

    _process_one(load_config(), no_moves(), Package(pkg_dir), False)

    assert seen == ["southern"]


def test_a_clone_presenters_tts_voice_is_the_clone_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k-test")
    home, station = station_home(tmp_path, monkeypatch,
                                 assign='[assign.profiles.dead]\npresenter = "phil"\n')
    clip = home / "phil.wav"
    clip.write_bytes(b"RIFF-phil-clip")
    save_presenter(home, Presenter(id="phil", name="Phil", sex="male", voice_clone=str(clip),
                                   tts="voxtral", character="x"))
    _arm_llm(monkeypatch)
    monkeypatch.setattr(process_mod, "_synthesize_dj_audio", _fake_synth())
    pkg_dir = build_package(station, slug="gd", profile="dead")

    result = runner.invoke(app, ["voice", "gd"])

    assert result.exit_code == 0, result.output
    assert _dj_audio(pkg_dir)["tts"] == {
        "backend": "voxtral", "model": VOX_DEFAULT,
        "voice": "clone:" + hashlib.sha256(b"RIFF-phil-clip").hexdigest()[:16]}


def test_a_legacy_block_cannot_round_trip_through_the_model():
    with pytest.raises(ValidationError):
        DJAudioBlock.model_validate({"set_intros": {"1": "a"}, "outro": "o", "presenter": "phil"})


def test_voice_under_a_recorded_move_records_the_move(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    _gregg(home)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)
    write_moves_file(home, {"GratefulDead/ttb": "southern"})

    assert runner.invoke(app, ["voice", "ttb"]).exit_code == 0

    dj = _dj_audio(pkg_dir)
    assert (dj["profile"], dj["profile_source"], dj["presenter"]) == ("southern", "move", "gregg")
    assert readiness(Package(pkg_dir), load_config(), load_moves(home)) == (True, [])


def test_voice_refuses_a_move_whose_target_lost_its_assign_entry(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch)
    pkg_dir = build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    write_moves_file(home, {"GratefulDead/ttb": "southern"})
    before = (pkg_dir / "manifest.json").read_bytes()
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 1
    assert 'error: ttb: move target "southern" has no [assign.profiles] entry' in result.stderr
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_voice_refuses_a_missing_moves_file_for_a_move_voiced_package(tmp_path, monkeypatch):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    pkg_dir = build_package(station, slug="ttb", voiced=True, profile="funk")
    set_dj_audio(pkg_dir, profile="southern", profile_source="move", presenter="gregg")
    before = (pkg_dir / "manifest.json").read_bytes()
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 1
    exc = result.exception
    assert isinstance(exc, EmceeError)
    assert str(home / "moves.json") in str(exc) and "1 package(s)" in str(exc)
    assert "rebuild" in "\n".join(exc.details) and "write {}" in "\n".join(exc.details)
    assert (pkg_dir / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("content", ['{"GratefulDead/ttb": {"profile": "sou', '["not", "an", "object"]'],
                         ids=["truncated", "wrong-shape"])
def test_voice_refuses_a_bad_moves_file_before_any_work(tmp_path, monkeypatch, content):
    home, station = station_home(tmp_path, monkeypatch, assign=_SOUTHERN)
    pkg_dir = build_package(station, slug="ttb", voiced=True, profile="funk")
    (home / "moves.json").write_text(content)
    before = (pkg_dir / "manifest.json").read_bytes()
    forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert str(home / "moves.json") in str(result.exception)
    assert (pkg_dir / "manifest.json").read_bytes() == before
