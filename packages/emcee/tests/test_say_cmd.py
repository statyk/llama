"""Tests for `emcee say`: ad-hoc narration of a text file, apart from the
llama-package pipeline.

`say` shares the station's voice/bed configuration and the `render_speech_mp3`
renderer with `emcee voice`, but touches no package, no manifest and no LLM.
Voice/bed RESOLUTION is unit-tested in `test_process.py`
(`ad_hoc_speech`/`ad_hoc_bed`); what follows is the command's own wiring:
which options reach the resolvers, text normalization, chunking, and where
the MP3 lands.
"""

import wave
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
from emcee.cli import app
from emcee.presenters import Presenter, save_presenter
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.provider import SpeechError

runner = CliRunner()


def _write_config(root: Path, **tts) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ["[tts]", 'backend = "fake"', 'voice = "test-voice"']
    for key, value in tts.items():
        lines.append(f'{key} = {value!r}' if isinstance(value, str) else f"{key} = {value}")
    (root / "config.toml").write_text("\n".join(lines) + "\n")


def _arm_speech(monkeypatch):
    """Hand the command a FakeSpeechProvider we keep a handle on, and record
    the voice-source kwargs it resolved with. `ad_hoc_speech` itself is
    tested for real in test_process.py; this seam is about what `say` passes
    to it."""
    speech = FakeSpeechProvider()
    seen: dict = {}

    def fake_ad_hoc_speech(config, **kwargs):
        seen.update(kwargs)
        return speech

    monkeypatch.setattr(cli_mod, "ad_hoc_speech", fake_ad_hoc_speech)
    return speech, seen


def _text_file(tmp_path: Path, text: str = "A short read.") -> Path:
    p = tmp_path / "notes.txt"
    p.write_text(text)
    return p


def _bed_file(tmp_path: Path, seconds: float = 1.0, rate: int = 24000,
              channels: int = 1) -> Path:
    p = tmp_path / f"bed{rate}x{channels}.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(np.full(int(seconds * rate) * channels, 500, dtype="<i2").tobytes())
    return p


def _run(args, tmp_path, monkeypatch, **config_tts):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, **config_tts)
    return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_say_writes_an_mp3_beside_the_text_file_by_default(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    src = _text_file(tmp_path)

    result = _run(["say", str(src)], tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    assert (tmp_path / "notes.mp3").exists()


def test_say_honors_an_explicit_output_path(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    src = _text_file(tmp_path)
    dest = tmp_path / "out" / "spoken.mp3"

    result = _run(["say", str(src), "-o", str(dest)], tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    assert dest.exists()
    assert not (tmp_path / "notes.mp3").exists()


def test_say_rejects_an_empty_text_file(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    src = _text_file(tmp_path, "   \n\n")

    result = _run(["say", str(src)], tmp_path, monkeypatch)

    assert result.exit_code != 0
    assert "empty" in str(result.exception)


# ---------------------------------------------------------------------------
# Text handling
# ---------------------------------------------------------------------------


def test_say_normalizes_speech_symbols_by_default(tmp_path, monkeypatch):
    speech, _ = _arm_speech(monkeypatch)
    src = _text_file(tmp_path, "Scarlet > Fire, the whole way.")

    _run(["say", str(src), "--no-chunk"], tmp_path, monkeypatch)

    assert speech.calls == ["Scarlet into Fire, the whole way."]


def test_say_raw_skips_normalization(tmp_path, monkeypatch):
    speech, _ = _arm_speech(monkeypatch)
    src = _text_file(tmp_path, "Scarlet > Fire, the whole way.")

    _run(["say", str(src), "--no-chunk", "--raw"], tmp_path, monkeypatch)

    assert speech.calls == ["Scarlet > Fire, the whole way."]


def test_say_chunks_by_sentence_by_default(tmp_path, monkeypatch):
    speech, _ = _arm_speech(monkeypatch)
    src = _text_file(tmp_path, "First sentence here. Second sentence here.")

    _run(["say", str(src)], tmp_path, monkeypatch)

    # Chunking defaults ON for `say`: an arbitrary text file routinely
    # exceeds Voxtral's per-request cap, which a whole-passage call cannot.
    assert speech.calls == ["First sentence here.", "Second sentence here."]


def test_say_no_chunk_sends_the_whole_passage_in_one_call(tmp_path, monkeypatch):
    speech, _ = _arm_speech(monkeypatch)
    src = _text_file(tmp_path, "First sentence here. Second sentence here.")

    _run(["say", str(src), "--no-chunk"], tmp_path, monkeypatch)

    assert speech.calls == ["First sentence here. Second sentence here."]


# ---------------------------------------------------------------------------
# Voice sources reach the resolver
# ---------------------------------------------------------------------------


def test_say_forwards_a_clone_reference(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    src = _text_file(tmp_path)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")

    _run(["say", str(src), "--clone", str(ref)], tmp_path, monkeypatch)

    assert seen == {"clone_ref": str(ref), "clone_text": None, "voice": None, "presenter": None}


def test_say_forwards_a_preset_voice(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    src = _text_file(tmp_path)

    _run(["say", str(src), "--voice", "other-preset"], tmp_path, monkeypatch)

    assert seen["voice"] == "other-preset"


def test_say_forwards_a_loaded_presenter(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    save_presenter(home, Presenter(id="waldo", name="Waldo", sex="male",
                                   voice="waldo-preset", character="Laid-back."))
    src = _text_file(tmp_path)

    _run(["say", str(src), "--presenter", "waldo"], tmp_path, monkeypatch)

    assert seen["presenter"].id == "waldo"


# ---------------------------------------------------------------------------
# Bed
# ---------------------------------------------------------------------------


def test_say_mixes_the_configured_station_bed(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    src = _text_file(tmp_path)
    bed = _bed_file(tmp_path)
    dry = tmp_path / "dry.mp3"
    wet = tmp_path / "wet.mp3"

    _run(["say", str(src), "-o", str(dry), "--no-bed"], tmp_path, monkeypatch,
         bed=str(bed))
    _run(["say", str(src), "-o", str(wet)], tmp_path, monkeypatch, bed=str(bed))

    # mix_bed wraps the ~0.3s clip in 1.5s of pre-roll and 2s of tail.
    assert wet.stat().st_size > dry.stat().st_size * 4


def test_say_bed_option_overrides_the_configured_bed(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    src = _text_file(tmp_path)
    out = tmp_path / "out.mp3"

    result = _run(["say", str(src), "-o", str(out),
                   "--bed", str(_bed_file(tmp_path, seconds=2.0))],
                  tmp_path, monkeypatch, bed="/nonexistent/station-bed.wav")

    assert result.exit_code == 0, result.output
    assert out.exists()


def test_say_rejects_a_bed_in_the_wrong_format(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    src = _text_file(tmp_path)

    result = _run(["say", str(src), "--bed",
                   str(_bed_file(tmp_path, rate=44100, channels=2))],
                  tmp_path, monkeypatch)

    assert result.exit_code != 0
    assert isinstance(result.exception, SpeechError)
    assert "24kHz mono 16-bit" in str(result.exception)


from emcee.tts.provider import SpeechBlocked


def test_say_names_the_blocked_sentence(tmp_path, monkeypatch):
    speech, _ = _arm_speech(monkeypatch)
    speech.block = "climax"
    src = _text_file(tmp_path, "First sentence here, fine. The climax comes too early here.")

    result = _run(["say", str(src), "--no-chunk"], tmp_path, monkeypatch)

    assert result.exit_code != 0
    assert isinstance(result.exception, SpeechBlocked)
    assert result.exception.details == ['blocked: "The climax comes too early here."']


# ---------------------------------------------------------------------------
# --clone-text and the mlx_audio house (spec section 4)
# ---------------------------------------------------------------------------

from tests.mlx_helpers import TEST_MODEL, MlxServer, calibrate_test_model, install_mlx, wav_bytes

HOUSE_TEXT = "House words, spoken for the record."


def _mlx_house(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    clip = home / "house.wav"
    clip.write_bytes(wav_bytes(1.0))
    (home / "config.toml").write_text(
        f'[tts]\nbackend = "mlx_audio"\nvoice_clone = "{clip}"\n'
        f'voice_clone_text = "{HOUSE_TEXT}"\n\n[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\n')
    return clip


def test_say_clone_text_without_clone_is_a_usage_error(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    result = _run(["say", str(_text_file(tmp_path)), "--clone-text", "words"], tmp_path, monkeypatch)
    assert result.exit_code == 2 and "--clone-text needs --clone" in result.output


def test_say_ignores_clone_text_under_a_hosted_house(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")
    _run(["say", str(_text_file(tmp_path)), "--clone", str(ref), "--clone-text", "words"],
         tmp_path, monkeypatch)
    assert seen["clone_text"] is None


def test_say_forwards_clone_text_under_an_mlx_house(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    _mlx_house(tmp_path, monkeypatch)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")
    result = runner.invoke(app, ["say", str(_text_file(tmp_path)), "--clone", str(ref),
                                 "--clone-text", "Their words."])
    assert result.exit_code == 0, result.output
    assert (seen["clone_ref"], seen["clone_text"]) == (str(ref), "Their words.")


@pytest.mark.parametrize("args, message", [
    (["--clone", "REF"], "--clone needs --clone-text (the clip's transcript) when the house backend is mlx_audio"),
    (["--clone", "REF", "--clone-text", "   "], "--clone needs --clone-text"),
    (["--voice", "preset"], "--voice is a preset, but the house backend is mlx_audio, which is clone-only"),
])
def test_say_usage_errors_under_an_mlx_house(tmp_path, monkeypatch, args, message):
    _arm_speech(monkeypatch)
    _mlx_house(tmp_path, monkeypatch)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")
    args = [str(ref) if a == "REF" else a for a in args]
    result = runner.invoke(app, ["say", str(_text_file(tmp_path)), *args])
    assert result.exit_code == 2 and message in result.output


def test_say_with_no_voice_flags_sends_the_house_transcript(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    _mlx_house(tmp_path, monkeypatch)
    server = MlxServer()
    install_mlx(monkeypatch, server)
    result = runner.invoke(app, ["say", str(_text_file(tmp_path, "Good evening to all of you out there."))])
    assert result.exit_code == 0, result.output
    assert server.speech_bodies and all(b["ref_text"] == HOUSE_TEXT for b in server.speech_bodies)
