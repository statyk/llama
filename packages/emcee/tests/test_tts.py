import io
import json
import wave

import httpx
import pytest

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
