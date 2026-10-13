from emcee.config import EmceeConfig
from emcee.tts.calibration import CALIBRATED_MODELS
from emcee.tts.elevenlabs import ElevenLabsProvider
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.provider import SpeechError, SpeechProvider
from emcee.tts.quality import QualitySpeech
from emcee.tts.resolve import TTSResolution
from emcee.tts.voxtral import VoxtralProvider


def _who(resolution: TTSResolution) -> str:
    return (f"presenter {resolution.presenter!r}" if resolution.presenter is not None
            else "the house voice")


def _mlx_provider(config: EmceeConfig, resolution: TTSResolution, *, voice: str | None,
                  clone_ref: str | None, clone_text: str | None) -> MlxAudioProvider:
    """mlx_audio is clone-only and needs the clip's transcript. A presenter
    pin is already validated (Presenter); the house voice is checked here,
    naming its [tts] keys."""
    house = resolution.presenter is None
    who = _who(resolution)
    if voice:
        raise SpeechError(
            "mlx_audio is clone-only: [tts] voice is a preset, but the house voice resolves "
            "to mlx_audio; set [tts] voice_clone and [tts] voice_clone_text instead"
            if house else f"{who}: mlx_audio is clone-only (a preset voice cannot be voiced on it)")
    if not clone_ref:
        raise SpeechError(
            "mlx_audio needs a reference clip: set [tts] voice_clone (the house voice "
            "resolves to mlx_audio)" if house else f"{who}: mlx_audio needs voice_clone")
    if not (clone_text or "").strip():
        raise SpeechError(
            "mlx_audio needs the reference clip's transcript: set [tts] voice_clone_text "
            "(the house voice resolves to mlx_audio)"
            if house else f"{who}: mlx_audio needs voice_clone_text, the transcript of voice_clone")
    mlx = config.tts.mlx_audio
    return MlxAudioProvider(url=mlx.url, model=resolution.model, clone_ref=clone_ref,
                            clone_text=clone_text,
                            calibration=CALIBRATED_MODELS[resolution.model],
                            timeout_s=mlx.timeout_s)


def speech_provider_for(config: EmceeConfig, resolution: TTSResolution, *,
                        voice: str | None, clone_ref: str | None,
                        clone_text: str | None) -> SpeechProvider:
    """Construct exactly the speech backend `resolution` names.

    Every argument is required and has no default: an unmigrated call site
    fails loudly instead of falling back to [tts] backend or dropping the
    transcript. `resolution` comes from `emcee.tts.resolve.resolve_tts`;
    `voice`/`clone_ref`/`clone_text` are the voice source the caller resolved
    (a presenter's own fields, the house [tts] fields, or `emcee say`'s
    flags) -- the factory never reads [tts] voice/voice_clone itself, so a
    presenter fully owns its voice. The render cache keys on the provider's
    `.voice`/`.model`, so a re-pinned presenter never reuses another
    backend's clips.
    """
    backend = resolution.backend
    key_hint = " or ".join(resolution.key_sources) or "[tts] api_key"
    if backend == "fake":
        return FakeSpeechProvider()
    if backend == "voxtral":
        if not (voice or clone_ref):
            raise SpeechError("no Voxtral voice configured: set [tts] voice "
                              "(preset) or [tts] voice_clone (reference clip)")
        return VoxtralProvider(voice=voice, clone_ref=clone_ref, model=resolution.model,
                               api_key=resolution.api_key, key_hint=key_hint)
    if backend == "elevenlabs":
        if clone_ref:
            raise SpeechError(f"{_who(resolution)}: voice cloning is not available on "
                              "elevenlabs: a voice_clone resolves to the elevenlabs backend "
                              "(clone on voxtral or mlx_audio, or use a preset voice)")
        if not voice:
            raise SpeechError("no TTS voice configured: "
                              "set [tts] voice or give the profile a presenter")
        return ElevenLabsProvider(voice=voice, model=resolution.model,
                                  api_key=resolution.api_key, key_hint=key_hint)
    if backend == "mlx_audio":
        return QualitySpeech(_mlx_provider(config, resolution, voice=voice, clone_ref=clone_ref,
                                           clone_text=clone_text),
                             backend="mlx_audio", verifier=None)
    raise SpeechError(f"unknown TTS backend {backend!r}")
