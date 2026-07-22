from llama.config import Config
from llama.tts.elevenlabs import ElevenLabsProvider
from llama.tts.fake import FakeSpeechProvider
from llama.tts.provider import SpeechError, SpeechProvider
from llama.tts.voxtral import VoxtralProvider


def speech_provider_for(config: Config, voice: str | None) -> SpeechProvider:
    """Construct the speech backend for a run's resolved voice.

    Mirrors llm.provider_for: maps config.tts.backend to a class. No tiers,
    no ladder — one provider, one voice, one model per run.
    """
    backend = config.tts.backend
    if backend == "fake":
        return FakeSpeechProvider()
    if backend == "voxtral":
        if not (voice or config.tts.voice_clone):
            raise SpeechError("no Voxtral voice configured: set [tts] voice "
                              "(preset) or [tts] voice_clone (reference clip)")
        return VoxtralProvider(voice=voice, clone_ref=config.tts.voice_clone,
                               model=config.tts.model, api_key=config.tts.api_key)
    if backend == "elevenlabs":
        if not voice:
            raise SpeechError("no TTS voice configured: "
                              "set [tts] voice or give the profile a voice")
        return ElevenLabsProvider(voice=voice, model=config.tts.model,
                                  api_key=config.tts.api_key)
    raise SpeechError(f"unknown TTS backend {backend!r}")
