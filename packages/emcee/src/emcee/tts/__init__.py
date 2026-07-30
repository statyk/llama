from emcee.config import EmceeConfig
from emcee.tts.elevenlabs import ElevenLabsProvider
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.provider import SpeechError, SpeechProvider
from emcee.tts.voxtral import VoxtralProvider


def speech_provider_for(config: EmceeConfig, voice: str | None,
                        clone_ref: str | None = None) -> SpeechProvider:
    """Construct the speech backend for a run's resolved voice.

    Mirrors herder.provider_for: maps config.tts.backend to a class. No tiers,
    no ladder — one provider, one voice, one model per run. clone_ref is the
    reference-clip path for clone mode; callers resolve it (a presenter's
    voice_clone, or [tts] voice_clone for the house voice) — the factory
    itself never reads config.tts.voice_clone, so a presenter fully owns
    its voice.
    """
    backend = config.tts.backend
    if backend == "fake":
        return FakeSpeechProvider()
    if backend == "voxtral":
        if not (voice or clone_ref):
            raise SpeechError("no Voxtral voice configured: set [tts] voice "
                              "(preset) or [tts] voice_clone (reference clip)")
        return VoxtralProvider(voice=voice, clone_ref=clone_ref,
                               model=config.tts.model, api_key=config.tts.api_key)
    if backend == "elevenlabs":
        if clone_ref:
            raise SpeechError("voice cloning is Voxtral-only: a voice_clone is "
                              "set but [tts] backend is elevenlabs")
        if not voice:
            raise SpeechError("no TTS voice configured: "
                              "set [tts] voice or give the profile a presenter")
        return ElevenLabsProvider(voice=voice, model=config.tts.model,
                                  api_key=config.tts.api_key)
    raise SpeechError(f"unknown TTS backend {backend!r}")
