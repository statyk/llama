import base64
import hashlib
import json

import httpx
import pytest

from llama.tts.provider import SpeechError, SpeechProvider
from llama.tts.voxtral import DEFAULT_MODEL, VoxtralProvider


def _ok_audio(payload=b"mp3bytes"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"audio_data": base64.b64encode(payload).decode()})
    return handler


def make_preset(handler, *, voice="british-narrator", model=None, api_key="k1"):
    return VoxtralProvider(voice=voice, model=model, api_key=api_key,
                           transport=httpx.MockTransport(handler))


def test_is_a_speech_provider():
    assert isinstance(make_preset(_ok_audio()), SpeechProvider)


def test_preset_request_shape_and_base64_decode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"audio_data": base64.b64encode(b"MP3!").decode()})

    assert make_preset(handler).synthesize("Tonight, the Dead.") == b"MP3!"
    assert seen["url"] == "https://api.mistral.ai/v1/audio/speech"
    assert seen["auth"] == "Bearer k1"
    assert seen["body"] == {"model": DEFAULT_MODEL, "input": "Tonight, the Dead.",
                            "response_format": "mp3", "voice_id": "british-narrator"}
    assert "ref_audio" not in seen["body"]


def test_preset_voice_and_model_attributes():
    p = make_preset(_ok_audio(), voice="american-dj", model="voxtral-mini-tts-2603")
    assert (p.voice, p.model) == ("american-dj", "voxtral-mini-tts-2603")


def test_model_defaults_when_none():
    assert make_preset(_ok_audio(), model=None).model == DEFAULT_MODEL


def test_env_key_wins_over_config_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")
    p = VoxtralProvider(voice="v", api_key="k-config", transport=httpx.MockTransport(_ok_audio()))
    assert p.api_key == "k-env"


def test_missing_key_raises():
    # conftest guarantees no ambient MISTRAL_API_KEY
    with pytest.raises(SpeechError):
        VoxtralProvider(voice="v")


def test_no_voice_and_no_clone_raises():
    with pytest.raises(SpeechError):
        VoxtralProvider(api_key="k")


def test_error_status_raises():
    def handler(request):
        return httpx.Response(429, text="rate limited")
    with pytest.raises(SpeechError):
        make_preset(handler).synthesize("x")


def test_empty_audio_data_raises():
    def handler(request):
        return httpx.Response(200, json={"audio_data": ""})
    with pytest.raises(SpeechError):
        make_preset(handler).synthesize("x")


def test_missing_audio_data_raises():
    def handler(request):
        return httpx.Response(200, json={"nope": 1})
    with pytest.raises(SpeechError):
        make_preset(handler).synthesize("x")


def test_close_and_context_manager():
    p = make_preset(_ok_audio())
    assert p._client.is_closed is False
    p.close()
    assert p._client.is_closed is True
    with make_preset(_ok_audio()) as q:
        assert q._client.is_closed is False
    assert q._client.is_closed is True


def make_clone(handler, ref_path, *, api_key="k1"):
    return VoxtralProvider(clone_ref=str(ref_path), api_key=api_key,
                           transport=httpx.MockTransport(handler))


def test_clone_request_uses_ref_audio_not_voice_id(tmp_path):
    ref = tmp_path / "dj.wav"
    ref.write_bytes(b"REFERENCE-AUDIO-BYTES")
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"audio_data": base64.b64encode(b"x").decode()})

    make_clone(handler, ref).synthesize("hi")
    assert seen["body"]["ref_audio"] == base64.b64encode(b"REFERENCE-AUDIO-BYTES").decode()
    assert "voice_id" not in seen["body"]


def test_clone_voice_identity_is_clip_hash(tmp_path):
    ref = tmp_path / "dj.wav"
    ref.write_bytes(b"REFERENCE-AUDIO-BYTES")
    p = make_clone(_ok_audio(), ref)
    expected = "clone:" + hashlib.sha256(b"REFERENCE-AUDIO-BYTES").hexdigest()[:16]
    assert p.voice == expected


def test_clone_identity_changes_when_clip_changes(tmp_path):
    a = tmp_path / "a.wav"; a.write_bytes(b"AAAA")
    b = tmp_path / "b.wav"; b.write_bytes(b"BBBB")
    assert make_clone(_ok_audio(), a).voice != make_clone(_ok_audio(), b).voice


def test_clone_missing_file_raises(tmp_path):
    with pytest.raises(SpeechError):
        make_clone(_ok_audio(), tmp_path / "nope.wav")


def test_clone_empty_file_raises(tmp_path):
    ref = tmp_path / "empty.wav"; ref.write_bytes(b"")
    with pytest.raises(SpeechError):
        make_clone(_ok_audio(), ref)


def test_over_long_segment_raises():
    from llama.tts.voxtral import MAX_INPUT_CHARS
    with pytest.raises(SpeechError):
        make_preset(_ok_audio()).synthesize("x" * (MAX_INPUT_CHARS + 1))
