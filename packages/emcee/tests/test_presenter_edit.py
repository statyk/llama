"""`emcee presenter edit` (spec section 4)."""
from functools import partial
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emcee.cli import app
from emcee.presenters import Presenter, PresenterError, load_presenter, save_presenter
from emcee.tts.provider import SpeechError
from emcee.tts.verify import SttClient

from tests.mlx_helpers import MlxServer, wav_bytes

runner = CliRunner()
DRAFT = "It's the chemistry, basically."
STT_CONFIG = '[tts.mlx_audio]\nstt_model = "stt/test-model"\n'
STT_VERIFY_CONFIG = STT_CONFIG + '\n[tts.verify]\nbackends = ["mlx_audio"]\n'


def _home(tmp_path, monkeypatch, config: str = "") -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(config)
    return home


def _clip(tmp_path, name: str = "phil_ex.wav") -> Path:
    p = tmp_path / name
    p.write_bytes(wav_bytes(1.0))
    return p


def _save(home, **overrides) -> Presenter:
    d = dict(id="phil", name="Phil", sex="male", voice="phil-preset", character="Professorial.")
    d.update(overrides)
    p = Presenter(**d)
    save_presenter(home, p)
    return p


def _clone(home, tmp_path, **overrides) -> Presenter:
    return _save(home, voice=None, voice_clone=str(_clip(tmp_path, "old.wav")),
                 voice_clone_text="Old words.", **overrides)


def _edit(*args, input=None):
    return runner.invoke(app, ["presenter", "edit", "phil", *args], input=input)


def _file(home) -> Path:
    return home / "presenters" / "phil.toml"


def _stt(monkeypatch, server: MlxServer) -> None:
    monkeypatch.setattr("emcee.cli.SttClient", partial(SttClient, transport=server.transport()))


# --- plain fields ---------------------------------------------------------------


def test_edit_changes_only_the_given_fields(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home, bed="/beds/b.wav")
    r = _edit("--name", "Professor Chapman", "--sex", "nonbinary")
    assert r.exit_code == 0, r.output
    p = load_presenter(home, "phil")
    assert (p.name, p.sex) == ("Professor Chapman", "nonbinary")
    assert (p.voice, p.bed, p.character) == ("phil-preset", "/beds/b.wav", "Professorial.")
    assert "saved:" in r.output


def test_edit_character_and_character_file(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    assert _edit("--character", "Cosmic.").exit_code == 0
    assert load_presenter(home, "phil").character == "Cosmic."
    cf = tmp_path / "c.txt"
    cf.write_text("  From a file.\n")
    assert _edit("--character-file", str(cf)).exit_code == 0
    assert load_presenter(home, "phil").character == "From a file."


def test_edit_bed_set_and_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    assert _edit("--bed", "/beds/new.wav").exit_code == 0
    assert load_presenter(home, "phil").bed == "/beds/new.wav"
    assert _edit("--clear-bed").exit_code == 0
    assert load_presenter(home, "phil").bed is None


def test_edit_pins_and_unpins_tts(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    assert _edit("--tts", "voxtral").exit_code == 0
    assert load_presenter(home, "phil").tts == "voxtral"
    assert _edit("--clear-tts").exit_code == 0
    assert load_presenter(home, "phil").tts is None


def test_edit_tts_model_set_and_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path, tts="mlx_audio")
    assert _edit("--tts-model", "m/x").exit_code == 0
    assert load_presenter(home, "phil").tts_model == "m/x"
    assert _edit("--clear-tts-model").exit_code == 0
    assert load_presenter(home, "phil").tts_model is None


def test_edit_voice_clone_text_set_and_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    assert _edit("--voice-clone-text", "New words.").exit_code == 0
    assert load_presenter(home, "phil").voice_clone_text == "New words."
    assert _edit("--clear-voice-clone-text").exit_code == 0
    assert load_presenter(home, "phil").voice_clone_text is None


# --- usage errors -----------------------------------------------------------------


@pytest.mark.parametrize("args, message", [
    (["--tts", "voxtral", "--clear-tts"], "--tts and --clear-tts are mutually exclusive"),
    (["--tts-model", "m", "--clear-tts-model"], "--tts-model and --clear-tts-model are mutually exclusive"),
    (["--bed", "/b.wav", "--clear-bed"], "--bed and --clear-bed are mutually exclusive"),
    (["--voice-clone-text", "x", "--clear-voice-clone-text"],
     "--voice-clone-text and --clear-voice-clone-text are mutually exclusive"),
    (["--voice", "a", "--voice-clone", "/b.wav"], "--voice and --voice-clone are mutually exclusive"),
    (["--character", "a", "--character-file", "/c.txt"], "give at most one of --character / --character-file"),
    (["--transcribe", "--voice-clone-text", "x"], "--transcribe and --voice-clone-text are mutually exclusive"),
    (["--transcribe", "--clear-voice-clone-text"],
     "--transcribe and --clear-voice-clone-text are mutually exclusive"),
    ([], "nothing to edit: give at least one field option"),
])
def test_usage_errors_exit_2_and_touch_nothing(tmp_path, monkeypatch, args, message):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    r = _edit(*args)
    assert r.exit_code == 2
    assert message in r.output
    assert _file(home).read_bytes() == before


# --- voice / clip / transcript coupling --------------------------------------------


def test_voice_clears_the_clip_and_its_transcript(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    assert _edit("--voice", "new-preset").exit_code == 0
    p = load_presenter(home, "phil")
    assert (p.voice, p.voice_clone, p.voice_clone_text) == ("new-preset", None, None)


def test_a_changed_clip_clears_the_transcript_unless_a_new_one_is_given(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    new = _clip(tmp_path, "new.wav")
    assert _edit("--voice-clone", str(new)).exit_code == 0
    p = load_presenter(home, "phil")
    assert (p.voice_clone, p.voice_clone_text) == (str(new.resolve()), None)
    assert _edit("--voice-clone", str(new), "--voice-clone-text", "New words.").exit_code == 0
    assert load_presenter(home, "phil").voice_clone_text == "New words."


def test_a_changed_clip_on_an_mlx_pin_forces_a_fresh_transcript(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path, tts="mlx_audio")
    before = _file(home).read_bytes()
    r = _edit("--voice-clone", str(_clip(tmp_path, "new.wav")))
    assert r.exit_code == 1
    assert "invalid presenter" in r.output and "needs voice_clone_text" in r.output
    assert _file(home).read_bytes() == before


def test_moving_phil_with_the_runbook_command(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    clip = _clip(tmp_path)
    r = _edit("--tts", "mlx_audio", "--voice-clone", str(clip), "--voice-clone-text", DRAFT + "\n")
    assert r.exit_code == 0, r.output
    p = load_presenter(home, "phil")
    assert (p.tts, p.voice, p.voice_clone) == ("mlx_audio", None, str(clip.resolve()))
    assert p.voice_clone_text.strip() == DRAFT


def test_edit_stores_voice_clone_as_an_absolute_path(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    (tmp_path / "samples").mkdir()
    clip = _clip(tmp_path / "samples")
    monkeypatch.chdir(tmp_path)
    assert _edit("--voice-clone", "samples/phil_ex.wav").exit_code == 0
    assert load_presenter(home, "phil").voice_clone == str(clip.resolve())
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _edit("--voice-clone", "~/samples/phil_ex.wav").exit_code == 0
    assert load_presenter(home, "phil").voice_clone == str(clip.resolve())


def test_an_invalid_merged_edit_leaves_the_file_untouched(tmp_path, monkeypatch):
    # The merge is model_validate'd whole (model_copy would skip validators).
    home = _home(tmp_path, monkeypatch)
    _save(home)
    before = _file(home).read_bytes()
    r = _edit("--tts", "mlx_audio")
    assert r.exit_code == 1 and "clone-only" in r.output
    r = _edit("--tts-model", "m/x")
    assert r.exit_code == 1 and 'tts_model is allowed only with tts = "mlx_audio"' in r.output
    assert _file(home).read_bytes() == before


def test_editing_a_missing_presenter_errors(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    r = _edit("--name", "X")
    assert r.exit_code == 1 and isinstance(r.exception, PresenterError)


# --- --transcribe ------------------------------------------------------------------


def test_transcribe_confirmed_writes_the_draft_and_unloads_when_verification_is_off(
        tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 0, r.output
    assert "transcript draft:" in r.output and DRAFT in r.output
    assert load_presenter(home, "phil").voice_clone_text == DRAFT
    assert b'name="response_format"\r\n\r\njson\r\n' in server.transcriptions[0].content
    assert server.deletes == [{"model_name": "stt/test-model"}]


def test_transcribe_declined_leaves_the_file_untouched(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    r = _edit("--transcribe", input="n\n")
    assert server.deletes == [{"model_name": "stt/test-model"}]  # unloaded before the prompt
    assert r.exit_code == 1
    assert "transcript not written; presenter unchanged" in r.output
    assert _file(home).read_bytes() == before


def test_transcribe_keeps_the_stt_model_loaded_when_verification_is_on(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_VERIFY_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    assert _edit("--transcribe", input="y\n").exit_code == 0
    assert server.deletes == []


def test_transcribe_transcribes_the_new_clip(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    new = tmp_path / "new.wav"
    new.write_bytes(wav_bytes(1.7))
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    assert _edit("--voice-clone", str(new), "--transcribe", input="y\n").exit_code == 0
    assert new.read_bytes() in server.transcriptions[0].content
    p = load_presenter(home, "phil")
    assert (p.voice_clone, p.voice_clone_text) == (str(new.resolve()), DRAFT)


def test_transcribe_needs_an_stt_model(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    r = _edit("--transcribe")
    assert r.exit_code == 2
    assert "--transcribe needs [tts.mlx_audio] stt_model" in r.output


def test_transcribe_needs_a_clone(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _save(home)
    r = _edit("--transcribe")
    assert r.exit_code == 2 and "--transcribe needs a voice clone" in r.output


def test_transcribe_on_an_unreachable_server_leaves_the_file_untouched(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    _stt(monkeypatch, MlxServer(stt_down=True))
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 1 and isinstance(r.exception, SpeechError)
    assert _file(home).read_bytes() == before


def test_an_invalid_edit_fails_before_transcribing(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    r = _edit("--tts", "elevenlabs", "--transcribe", input="y\n")  # elevenlabs cannot clone
    assert r.exit_code == 1 and "invalid presenter" in r.output
    assert server.transcriptions == []


def test_transcribe_failure_with_verification_off_still_unloads_the_stt_model(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    server = MlxServer(stt_status=500)
    _stt(monkeypatch, server)
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 1 and isinstance(r.exception, SpeechError)
    assert server.deletes == [{"model_name": "stt/test-model"}]
    assert _file(home).read_bytes() == before


def test_transcribe_failure_with_verification_on_does_not_unload(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_VERIFY_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(stt_status=500)
    _stt(monkeypatch, server)
    assert _edit("--transcribe", input="y\n").exit_code == 1
    assert server.deletes == []


def test_transcribe_empty_transcription_is_an_error_and_writes_nothing(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    _stt(monkeypatch, MlxServer(transcript=lambda last: "  "))
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 1
    assert "the transcription came back empty; give --voice-clone-text by hand" in str(r.exception)
    assert "use this transcript?" not in r.output
    assert _file(home).read_bytes() == before


def test_transcribe_prints_a_note_when_the_unload_fails_but_still_proceeds(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)

    def boom(self):
        raise SpeechError("could not unload 'stt/test-model' from mlx-audio: boom")

    monkeypatch.setattr(SttClient, "unload", boom)
    _stt(monkeypatch, MlxServer(transcript=lambda last: DRAFT))
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 0, r.output
    assert "note: could not unload 'stt/test-model' from mlx-audio: boom" in r.output
    assert load_presenter(home, "phil").voice_clone_text == DRAFT


def test_draft_transcript_expands_a_tilde_clip_path(tmp_path, monkeypatch):
    from emcee.cli import _draft_transcript
    from emcee.config import load_config
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    (fake_home / "clip.wav").write_bytes(wav_bytes(1.0))
    monkeypatch.setenv("HOME", str(fake_home))
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    config = load_config()
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    assert _draft_transcript(config, "~/clip.wav") == DRAFT
