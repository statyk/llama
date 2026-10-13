import io
import json
import wave

import httpx
import pytest

from emcee.config import EmceeConfig
from emcee.tts import speech_provider_for
from emcee.tts.elevenlabs import ElevenLabsProvider
from emcee.tts.fake import SILENT_MP3, SILENT_WAV, FakeSpeechProvider
from emcee.tts.provider import SpeechError, SpeechProvider


def test_fake_returns_silent_mp3_and_records_calls():
    fake = FakeSpeechProvider()
    assert isinstance(fake, SpeechProvider)
    assert fake.synthesize("Good evening.") == SILENT_MP3
    assert SILENT_MP3.startswith(b"\xff\xfb")  # a real MPEG frame header
    assert fake.calls == ["Good evening."]
    assert (fake.voice, fake.model) == ("fake-voice", "fake-model")


def test_fake_wav_fmt_returns_valid_16bit_wav():
    fake = FakeSpeechProvider()
    data = fake.synthesize("Good evening.", fmt="wav")
    assert data != SILENT_MP3
    assert data == SILENT_WAV
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getsampwidth() == 2
        assert w.getnchannels() == 1
        assert w.getnframes() > 0
    assert fake.calls == ["Good evening."]


def test_fake_armed_to_fail():
    fake = FakeSpeechProvider(fail=True)
    with pytest.raises(SpeechError):
        fake.synthesize("x")
    assert fake.calls == ["x"]  # the attempt is still recorded


def make_provider(handler, api_key="k1"):
    return ElevenLabsProvider(voice="v-abc", model="eleven_multilingual_v2",
                              api_key=api_key, transport=httpx.MockTransport(handler))


def test_elevenlabs_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["xi-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"mp3bytes")

    assert make_provider(handler).synthesize("Tonight, the Grateful Dead.") == b"mp3bytes"
    assert seen["url"].endswith("/v1/text-to-speech/v-abc")
    assert seen["key"] == "k1"
    assert seen["body"] == {"text": "Tonight, the Grateful Dead.",
                            "model_id": "eleven_multilingual_v2"}


def test_elevenlabs_includes_context_in_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"x")

    make_provider(handler).synthesize(
        "The middle sentence.", previous_text="What came before.",
        next_text="What comes after.")
    assert seen["body"] == {
        "text": "The middle sentence.",
        "model_id": "eleven_multilingual_v2",
        "previous_text": "What came before.",
        "next_text": "What comes after.",
    }


def test_elevenlabs_sends_only_the_context_side_provided():
    # A first/last chunk has a neighbor on only one side; the absent side must
    # be omitted, not sent as null (ElevenLabs treats present-but-null oddly).
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"x")

    make_provider(handler).synthesize("Final chunk.", previous_text="Prior chunk.")
    assert seen["body"] == {"text": "Final chunk.", "model_id": "eleven_multilingual_v2",
                            "previous_text": "Prior chunk."}
    assert "next_text" not in seen["body"]


def test_elevenlabs_env_key_wins_over_config_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k-env")
    p = ElevenLabsProvider(voice="v", model="m", api_key="k-config")
    assert p.api_key == "k-env"


def test_elevenlabs_missing_key_raises():
    # conftest guarantees no ambient ELEVENLABS_API_KEY
    with pytest.raises(SpeechError):
        ElevenLabsProvider(voice="v", model="m")


def test_elevenlabs_error_status_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    with pytest.raises(SpeechError):
        make_provider(handler).synthesize("x")


def test_elevenlabs_close_closes_underlying_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"mp3bytes")

    provider = make_provider(handler)
    assert provider._client.is_closed is False
    provider.close()
    assert provider._client.is_closed is True


def test_elevenlabs_context_manager_closes_on_exit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"mp3bytes")

    with make_provider(handler) as provider:
        assert provider._client.is_closed is False
    assert provider._client.is_closed is True


def test_fake_speech_provider_close_is_a_noop():
    fake = FakeSpeechProvider()
    fake.close()  # must not raise; no hasattr guard needed by callers


def test_elevenlabs_model_defaults_when_none():
    from emcee.tts.elevenlabs import DEFAULT_MODEL
    p = ElevenLabsProvider(voice="v", model=None, api_key="k")
    assert p.model == DEFAULT_MODEL == "eleven_multilingual_v2"


# --- speech_provider_for factory: resolution-driven -------------------------

from emcee.presenters import Presenter
from emcee.tts.resolve import resolve_tts
from emcee.tts.voxtral import VoxtralProvider


def _make(cfg, *, voice=None, clone_ref=None, clone_text=None, presenter=None):
    return speech_provider_for(cfg, resolve_tts(cfg, presenter), voice=voice,
                               clone_ref=clone_ref, clone_text=clone_text)


def test_factory_arguments_are_required_keywords():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "fake"}})
    res = resolve_tts(cfg, None)
    with pytest.raises(TypeError):
        speech_provider_for(cfg, res)  # an unmigrated call site fails loudly
    with pytest.raises(TypeError):
        speech_provider_for(cfg, "voice-string", None)


def test_factory_fake_backend():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "fake"}})
    assert isinstance(_make(cfg, voice="ignored"), FakeSpeechProvider)


def test_factory_elevenlabs_uses_voice_and_model(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = EmceeConfig.model_validate({"tts": {"backend": "elevenlabs", "model": "eleven_turbo_v2_5"}})
    p = _make(cfg, voice="v-abc")
    assert isinstance(p, ElevenLabsProvider)
    assert (p.voice, p.model) == ("v-abc", "eleven_turbo_v2_5")


def test_factory_voxtral_is_default_preset(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    p = _make(EmceeConfig.model_validate({"tts": {"voice": "british-dj"}}), voice="british-dj")
    assert isinstance(p, VoxtralProvider)
    assert p.voice == "british-dj"


def test_factory_voxtral_clone_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    p = _make(EmceeConfig(), clone_ref=str(ref))
    assert isinstance(p, VoxtralProvider)
    assert p.voice.startswith("clone:")


def test_factory_ignores_config_clone_without_clone_ref(monkeypatch, tmp_path):
    # Callers own clone resolution (a presenter must fully own its voice):
    # the factory itself never falls back to [tts] voice_clone.
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    cfg = EmceeConfig.model_validate({"tts": {"voice_clone": str(ref)}})
    with pytest.raises(SpeechError, match="no Voxtral voice configured"):
        _make(cfg)


def test_factory_voxtral_model_and_key_from_the_resolution(monkeypatch):
    cfg = EmceeConfig.model_validate({"tts": {"voxtral": {"api_key": "k-sub", "model": "m-sub"}}})
    p = _make(cfg, voice="v")
    assert (p.model, p.api_key) == ("m-sub", "k-sub")


def test_factory_env_key_wins_over_the_resolved_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")
    cfg = EmceeConfig.model_validate({"tts": {"voxtral": {"api_key": "k-sub"}}})
    assert _make(cfg, voice="v").api_key == "k-env"


def test_factory_missing_house_key_names_env_and_both_locations():
    with pytest.raises(SpeechError) as exc:
        _make(EmceeConfig(), voice="v")
    assert str(exc.value) == ("Mistral API key missing: set MISTRAL_API_KEY or "
                              "[tts.voxtral] api_key or [tts] api_key")


def test_factory_missing_pinned_key_names_only_the_subtable():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "elevenlabs", "api_key": "el"}})
    pinned = Presenter(id="p", name="P", sex="male", voice="v", character="x", tts="voxtral")
    with pytest.raises(SpeechError) as exc:
        _make(cfg, voice="v", presenter=pinned)
    assert str(exc.value) == "Mistral API key missing: set MISTRAL_API_KEY or [tts.voxtral] api_key"


def test_factory_elevenlabs_rejects_an_inherited_clone(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = EmceeConfig.model_validate({"tts": {"backend": "elevenlabs"}})
    unpinned = Presenter(id="p", name="P", sex="male", voice_clone="/refs/x.wav", character="x")
    with pytest.raises(SpeechError, match="voice cloning is not available on elevenlabs"):
        _make(cfg, clone_ref="/refs/x.wav", presenter=unpinned)


def test_factory_elevenlabs_rejects_a_pinned_clone(monkeypatch):
    # Presenter validation already refuses tts="elevenlabs" + voice_clone; the
    # factory still refuses any clone that reaches elevenlabs.
    from emcee.tts.resolve import TTSResolution
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    res = TTSResolution("elevenlabs", "eleven_multilingual_v2", None,
                        ("[tts.elevenlabs] api_key",), "p", True)
    with pytest.raises(SpeechError, match="voice cloning is not available on elevenlabs"):
        speech_provider_for(EmceeConfig(), res, voice=None, clone_ref="/refs/x.wav",
                            clone_text=None)


def test_factory_voxtral_no_voice_no_clone_raises(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(SpeechError):
        _make(EmceeConfig())


def test_factory_no_voice_raises(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    with pytest.raises(SpeechError):
        _make(EmceeConfig.model_validate({"tts": {"backend": "elevenlabs"}}))


def test_factory_unknown_backend_raises():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "kokoro"}})
    with pytest.raises(SpeechError, match="unknown TTS backend"):
        _make(cfg, voice="v")


from emcee.tts.provider import SpeechBlocked


def test_fake_blocks_text_containing_the_armed_phrase():
    fake = FakeSpeechProvider(block="climax")
    assert fake.synthesize("A clean sentence here.") == SILENT_MP3
    with pytest.raises(SpeechBlocked) as ei:
        fake.synthesize("The climax comes early.", fmt="wav")
    assert ei.value.text == "The climax comes early."
    assert ei.value.categories == ["sexual"]
    assert fake.calls == ["A clean sentence here.", "The climax comes early."]
