"""Transcript verification (spec section 3): the comparison, the STT
client, the layer's use of it, and preflight's end-to-end STT check."""
from pathlib import Path

import json

import httpx
import pytest
from herder import FakeProvider
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.audio import _synthesize_dj_audio
from emcee.cli import _process_one, app
from emcee.config import EmceeConfig, load_config
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.process import ad_hoc_speech, process_package
from emcee.tts import speech_provider_for
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.mlx_audio import PREFLIGHT_TEXT
from emcee.tts.provider import SpeechDefect, SpeechError
from emcee.tts.quality import QualitySpeech
from emcee.tts.resolve import resolve_tts
from emcee.tts.verify import (SttClient, Verifier, comparable_words, preflight_clip_wav,
                              transcript_problem)

from tests.helpers import build_package
from tests.mlx_helpers import (TEST_MODEL, MlxServer, calibrate_test_model, install_mlx,
                               plausible_seconds, wav_bytes)

runner = CliRunner()
STT = "stt/test-model"
WAV = wav_bytes(1.0)
LINE = "Tonight we open the vault to the Grateful Dead in Rotterdam."


# --- the comparison -------------------------------------------------------------


def test_comparable_words_normalize_and_drop_numbers():
    assert comparable_words("It's May Eleventh, 1972 -- the 15th show!") == ["its", "may", "the", "show"]
    assert comparable_words("Seventy-two, twenty-one hundred.") == []


def test_exact_and_case_punctuation_differences_pass():
    assert transcript_problem(LINE, "tonight, we open the vault to the grateful dead in rotterdam") is None


def test_a_wrong_word_or_two_passes():
    assert transcript_problem("Here is Morning Dew.", "Here is morning due.") is None
    assert transcript_problem(
        "It was really the great hall of De Doelen, in Rotterdam.",
        "It was really the great hall of Dedoulin in Rotterdam.") is None


def test_number_formatting_is_ignored():
    assert transcript_problem("On May eleventh, 1972, the band played.",
                              "On May 11th, nineteen seventy-two, the band played.") is None


def test_all_number_sentence_passes():
    assert transcript_problem("1972.", "Nineteen seventy-two.") is None
    assert transcript_problem("Seventy-two.", "72") is None


def test_too_few_script_words_heard_fails():
    problem = transcript_problem(LINE, "tonight we")
    assert problem is not None and "words were heard" in problem


def test_a_transcript_far_longer_than_the_script_fails():
    loop = " ".join(["here is morning dew"] * 6)
    problem = transcript_problem("Here is Morning Dew.", loop)
    assert problem is not None and "words for a" in problem


def test_an_empty_transcript_fails_a_real_sentence():
    assert transcript_problem(LINE, "") is not None


# --- the STT client ---------------------------------------------------------------


def stt(server, url="http://127.0.0.1:8000"):
    return SttClient(url=url, model=STT, transport=server.transport())


def test_transcription_request_shape():
    server = MlxServer(transcript=lambda last: "  Hello there.  ")
    assert stt(server).transcribe(WAV) == "Hello there."
    req = server.transcriptions[0]
    assert req.url.path == "/v1/audio/transcriptions"
    body = req.content
    assert b'filename="clip.wav"' in body
    assert b'name="model"\r\n\r\nstt/test-model\r\n' in body
    assert b'name="language"\r\n\r\nen\r\n' in body
    assert b'name="response_format"\r\n\r\njson\r\n' in body


def test_failed_transcription_requests_are_speech_errors():
    with pytest.raises(SpeechError, match="not reachable at http://127.0.0.1:8000 for transcription"):
        stt(MlxServer(stt_down=True)).transcribe(WAV)
    with pytest.raises(SpeechError, match="mlx-audio transcription returned 500"):
        stt(MlxServer(stt_status=500)).transcribe(WAV)

    def no_text(request):
        return httpx.Response(200, json={"segments": []})

    client = SttClient(url="http://x", model=STT, transport=httpx.MockTransport(no_text))
    with pytest.raises(SpeechError, match="no text"):
        client.transcribe(WAV)


def test_unload_deletes_the_model():
    server = MlxServer()
    stt(server).unload()
    assert server.deletes == [{"model_name": STT}]


def test_the_bundled_clip_loader_fails_closed_when_missing(monkeypatch):
    monkeypatch.setattr("emcee.tts.verify.PREFLIGHT_CLIP", "no-such-clip.wav")
    with pytest.raises(SpeechError, match="emcee/data/no-such-clip.wav"):
        preflight_clip_wav()


# --- the layer with a verifier ----------------------------------------------------


class Scripted:
    voice = "inner-voice"
    model = "inner-model"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []
        self.preflights = 0

    def synthesize(self, text, fmt="mp3", *, previous_text=None, next_text=None):
        self.calls.append((text, fmt))
        return self.outcomes.pop(0)

    def preflight(self):
        self.preflights += 1

    def close(self):
        pass


def verified(inner, server, backend="voxtral"):
    return QualitySpeech(inner, backend=backend, verifier=Verifier(stt(server)))


def test_verification_requests_wav_and_encodes_mp3_locally(monkeypatch):
    monkeypatch.setattr("emcee.audio._encode_mp3", lambda pcm, rate, ch: b"MP3!")
    inner = Scripted(WAV)
    server = MlxServer(transcript=lambda last: LINE)
    assert verified(inner, server).synthesize(LINE, "mp3") == b"MP3!"
    assert inner.calls == [(LINE, "wav")]
    assert len(server.transcriptions) == 1


def test_verification_pass_returns_the_wav():
    assert verified(Scripted(WAV), MlxServer(transcript=lambda last: LINE)).synthesize(LINE, "wav") == WAV


def test_verification_fail_then_pass():
    heard = iter(["completely unrelated words about the weather today", LINE])
    inner = Scripted(WAV, WAV)
    assert verified(inner, MlxServer(transcript=lambda last: next(heard))).synthesize(LINE, "wav") == WAV
    assert len(inner.calls) == 2


def test_verification_double_fail_names_both_texts():
    garbage = "completely unrelated words about the weather today"
    with pytest.raises(SpeechDefect) as exc:
        verified(Scripted(WAV, WAV), MlxServer(transcript=lambda last: garbage)).synthesize(LINE, "wav")
    assert exc.value.details == [f'text: "{LINE}"', f'transcript: "{garbage}"']
    assert "transcript mismatch" in exc.value.reason and "(failed twice)" in exc.value.reason


def test_a_failed_transcription_request_is_an_error_never_a_pass():
    inner = Scripted(WAV, WAV)
    with pytest.raises(SpeechError) as exc:
        verified(inner, MlxServer(stt_status=500)).synthesize(LINE, "wav")
    assert not isinstance(exc.value, SpeechDefect)
    assert len(inner.calls) == 1


def test_cache_hits_are_not_re_verified(tmp_path):
    checks: list[str] = []

    class CountingVerifier:
        def check(self, wav, text, *, backend):
            checks.append(text)

        def close(self):
            pass

    pkg = build_package(tmp_path / "station", voiced=False)
    notes = ScriptNotes(set_intros={"1": "Set one opens.", "2": "Set two follows."}, outro="Thanks.")
    speech = QualitySpeech(FakeSpeechProvider(), backend="voxtral", verifier=CountingVerifier())
    _synthesize_dj_audio(pkg, notes, speech, False)
    first = len(checks)
    _synthesize_dj_audio(pkg, notes, speech, False)
    assert first == 3 and len(checks) == first  # every clip came from the cache


# --- which providers are verified ---------------------------------------------------


def _verify_cfg(backends, **tts):
    return EmceeConfig.model_validate({"tts": {
        "mlx_audio": {"model": TEST_MODEL, "stt_model": STT},
        "verify": {"backends": backends}, **tts}})


def test_voxtral_is_verified_only_when_listed(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    off = _verify_cfg(["mlx_audio"])
    on = _verify_cfg(["voxtral"])
    plain = speech_provider_for(off, resolve_tts(off, None), voice="v", clone_ref=None, clone_text=None)
    wrapped = speech_provider_for(on, resolve_tts(on, None), voice="v", clone_ref=None, clone_text=None)
    assert not isinstance(plain, QualitySpeech)
    assert isinstance(wrapped, QualitySpeech) and wrapped.verifier is not None
    assert wrapped.voice == wrapped.inner.voice  # enabling verification keeps the cache key


@pytest.mark.parametrize("backends, verified_", [([], False), (["mlx_audio"], True)])
def test_mlx_gets_a_verifier_only_when_listed(tmp_path, monkeypatch, backends, verified_):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(backends)
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    p = speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None, clone_ref=str(clip),
                            clone_text="Hi there.")
    assert isinstance(p, QualitySpeech) and (p.verifier is not None) is verified_


def test_say_paths_are_wrapped_when_the_backend_is_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(["voxtral"], voice="house-preset")
    host = Presenter(id="roy", name="R", sex="male", voice="roy-preset", character="x")
    for speech in (ad_hoc_speech(cfg), ad_hoc_speech(cfg, clone_ref=str(clip)),
                   ad_hoc_speech(cfg, presenter=host)):
        assert isinstance(speech, QualitySpeech) and speech.verifier is not None


# --- never silently skipped: preflight checks the STT path ---------------------------


def _station(tmp_path, monkeypatch, tts_toml: str, assign_toml: str = "") -> tuple[Path, Path]:
    home, station = tmp_path / "home", tmp_path / "station"
    home.mkdir()
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n\n{tts_toml}\n{assign_toml}\n')
    return home, station


def _forbid_scriptwrite(monkeypatch) -> list[str]:
    tasks: list[str] = []

    def no_llm(settings, task):
        tasks.append(task)
        raise AssertionError("LLM called before preflight passed")

    monkeypatch.setattr(process_mod, "provider_for", no_llm)
    return tasks


_MLX_VERIFIED = (f'[tts]\nbackend = "fake"\nvoice = "house"\n\n'
                 f'[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\nstt_model = "{STT}"\n\n'
                 '[tts.verify]\nbackends = ["mlx_audio"]\n')
_VOXTRAL_VERIFIED = (f'[tts]\nvoice = "house-preset"\n\n'
                     f'[tts.mlx_audio]\nstt_model = "{STT}"\n\n'
                     '[tts.verify]\nbackends = ["voxtral"]\n')


def _mlx_presenter(home: Path) -> None:
    clip = home / "phil_ex.wav"
    clip.write_bytes(WAV)
    save_presenter(home, Presenter(id="phil", name="Phil", sex="male", voice_clone=str(clip),
                                   voice_clone_text="It's the chemistry.", tts="mlx_audio",
                                   character="x"))


@pytest.mark.parametrize("server_kwargs, error", [
    ({"stt_down": True}, "for transcription"),
    ({"transcript": lambda last: "nothing at all like the words that were sent"}, "transcript mismatch"),
])
def test_mlx_preflight_fails_the_package_on_a_broken_stt_path(tmp_path, monkeypatch,
                                                              server_kwargs, error):
    calibrate_test_model(monkeypatch)
    home, station = _station(tmp_path, monkeypatch, _MLX_VERIFIED,
                             '[assign.profiles.dead]\npresenter = "phil"\n')
    _mlx_presenter(home)
    pkg_dir = build_package(station, slug="showA", profile="dead", voiced=True)
    before = (pkg_dir / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(**server_kwargs))
    tasks = _forbid_scriptwrite(monkeypatch)

    with pytest.raises(SpeechError, match=error):
        _process_one(load_config(), Package(pkg_dir), False)

    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("server_kwargs, error", [
    ({"stt_down": True}, "for transcription"),
    ({"transcript": lambda last: "nothing at all like the check sentence"}, "verification preflight failed"),
])
def test_hosted_preflight_checks_the_bundled_clip(tmp_path, monkeypatch, server_kwargs, error):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    home, station = _station(tmp_path, monkeypatch, _VOXTRAL_VERIFIED)
    pkg_dir = build_package(station, slug="showA", voiced=True)  # no profile: the house voice
    before = (pkg_dir / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(**server_kwargs))
    monkeypatch.setattr("emcee.tts.verify.preflight_clip_wav", lambda: wav_bytes(2.0))
    tasks = _forbid_scriptwrite(monkeypatch)

    with pytest.raises(SpeechError, match=error):
        _process_one(load_config(), Package(pkg_dir), False)

    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_hosted_preflight_passes_on_a_good_transcription(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    _station(tmp_path, monkeypatch, _VOXTRAL_VERIFIED)
    server = MlxServer(transcript=lambda last: PREFLIGHT_TEXT)
    install_mlx(monkeypatch, server)
    monkeypatch.setattr("emcee.tts.verify.preflight_clip_wav", lambda: wav_bytes(2.0))
    cfg = load_config()
    speech = speech_provider_for(cfg, resolve_tts(cfg, None), voice="house-preset",
                                 clone_ref=None, clone_text=None)
    speech.preflight()
    assert len(server.transcriptions) == 1 and server.speech_bodies == []  # no hosted spend


def _verified_mlx_speech(tmp_path, monkeypatch, server):
    """A verified, unchunked mlx provider routed through `server`, and its config."""
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(["mlx_audio"], chunk=False).model_copy(update={"root": tmp_path / "home"})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    install_mlx(monkeypatch, server)
    return cfg, speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None,
                                    clone_ref=str(clip), clone_text="Hi there.")


def test_verified_mlx_preflight_transcribes_its_one_take(tmp_path, monkeypatch):
    server = MlxServer(transcript=lambda last: PREFLIGHT_TEXT)
    _, speech = _verified_mlx_speech(tmp_path, monkeypatch, server)
    speech.preflight()
    assert [(b["input"], b["max_tokens"]) for b in server.speech_bodies] == [(PREFLIGHT_TEXT, 200)]
    assert len(server.transcriptions) == 1
    assert wav_bytes(plausible_seconds(PREFLIGHT_TEXT)) in server.transcriptions[0].content


def test_verified_mlx_preflight_retries_once_on_a_mismatch(tmp_path, monkeypatch):
    heard = iter(["nothing like it, the weather today", PREFLIGHT_TEXT])
    server = MlxServer(transcript=lambda last: next(heard))
    _, speech = _verified_mlx_speech(tmp_path, monkeypatch, server)
    speech.preflight()
    assert [(b["input"], b["max_tokens"]) for b in server.speech_bodies] == [(PREFLIGHT_TEXT, 200)] * 2
    assert len(server.transcriptions) == 2


def test_a_verified_package_whose_segment_fails_twice_is_not_voiced(tmp_path, monkeypatch):
    garbage = "completely unrelated words about the weather today"
    cfg, speech = _verified_mlx_speech(tmp_path, monkeypatch,
                                       MlxServer(transcript=lambda last: garbage))
    notes = {"context": "Spring '73 tour",
             "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                            "2": "China Cat Sunflower leads set two."},
             "outro": "I Know You Rider sends us off. Thanks for listening.",
             "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[json.dumps(notes)]))
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    before = pkg.manifest_path.read_bytes()

    with pytest.raises(SpeechDefect) as exc:
        process_package(cfg, pkg, speech)

    assert exc.value.segment == "set1-intro"
    assert "in set1-intro" in str(exc.value) and "(failed twice)" in str(exc.value)
    assert pkg.manifest_path.read_bytes() == before
    assert not (pkg.dir / "dj-audio" / "set1-intro.mp3").exists()


def test_say_verifies_without_preflight(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, _ = _station(tmp_path, monkeypatch, _MLX_VERIFIED)
    _mlx_presenter(home)
    server = MlxServer(stt_down=True)
    install_mlx(monkeypatch, server)
    text = tmp_path / "say.txt"
    text.write_text("Good evening, everybody, and welcome back to the archive.")

    result = runner.invoke(app, ["say", str(text), "--presenter", "phil"])

    assert result.exit_code == 1
    assert "for transcription" in str(result.exception)
    assert server.speech_bodies and server.speech_bodies[0]["input"] != PREFLIGHT_TEXT
