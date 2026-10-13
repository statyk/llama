"""Which TTS backend, model and key voice a presenter or the house voice.

Pure (no I/O): called before any LLM/TTS spend and before a package's
manifest blocks are cleared, so a configuration error never takes a
broadcast-ready package off air. See spec section 1 "Resolution".

- House voice: [tts] backend.
- Presenter: `presenter.tts` (a pin), else [tts] backend -- except that an
  unpinned presenter never inherits mlx_audio, so changing the house voice
  never moves a presenter.
- mlx_audio model: presenter.tts_model, else [tts.mlx_audio] model, else an
  error; a model outside the runaway guard's calibration table is an error.
- Hosted model/key: the backend's [tts.<backend>] table, else (only when it
  is the house backend) legacy [tts] model/api_key, else the provider's
  default model / no key (the provider's env var may still supply one).
"""
from dataclasses import dataclass

from emcee.config import HOSTED_BACKENDS, EmceeConfig
from emcee.errors import EmceeError
from emcee.presenters import Presenter
from emcee.tts.calibration import CALIBRATED_MODELS
from emcee.tts.elevenlabs import DEFAULT_MODEL as ELEVENLABS_DEFAULT_MODEL
from emcee.tts.voxtral import DEFAULT_MODEL as VOXTRAL_DEFAULT_MODEL

DEFAULT_MODELS = {"voxtral": VOXTRAL_DEFAULT_MODEL, "elevenlabs": ELEVENLABS_DEFAULT_MODEL}


class TTSResolutionError(EmceeError):
    """A presenter or the house voice cannot be resolved to a usable backend."""


@dataclass(frozen=True)
class TTSResolution:
    backend: str                  # "voxtral" | "elevenlabs" | "mlx_audio" | "fake" | (unknown)
    model: str | None             # concrete model id; None only for fake/unknown backends
    api_key: str | None           # config-supplied key (hosted only); env still wins
    key_sources: tuple[str, ...]  # config locations a missing-key error should name
    presenter: str | None         # presenter id; None = the house voice
    pinned: bool                  # True when the presenter's own `tts` chose the backend


def resolve_tts(config: EmceeConfig, presenter: Presenter | None) -> TTSResolution:
    house = config.tts.backend
    pid = presenter.id if presenter is not None else None
    who = f"presenter {pid!r}" if presenter is not None else "the house voice"
    if presenter is not None and presenter.tts is not None:
        backend, pinned = presenter.tts, True
    else:
        backend, pinned = house, False
        if presenter is not None and house == "mlx_audio":
            raise TTSResolutionError(
                f"presenter {pid!r}: pin tts explicitly: the house backend is mlx_audio "
                f"(e.g. `emcee presenter edit {pid} --tts voxtral`)")
    if backend == "mlx_audio":
        model = (presenter.tts_model if presenter is not None else None) \
            or config.tts.mlx_audio.model
        if not model:
            where = "the presenter's tts_model or " if presenter is not None else ""
            raise TTSResolutionError(f"{who}: no mlx_audio model: set {where}[tts.mlx_audio] model")
        if model not in CALIBRATED_MODELS:
            known = ", ".join(sorted(CALIBRATED_MODELS)) or "none yet"
            raise TTSResolutionError(
                f"{who}: mlx_audio model not calibrated for the runaway guard: {model!r} "
                f"(calibrated: {known})")
        return TTSResolution("mlx_audio", model, None, (), pid, pinned)
    if backend in HOSTED_BACKENDS:
        sub = getattr(config.tts, backend)
        is_house = backend == house
        model = sub.model or (config.tts.model if is_house else None) or DEFAULT_MODELS[backend]
        api_key = sub.api_key or (config.tts.api_key if is_house else None)
        sources = (f"[tts.{backend}] api_key",) + (("[tts] api_key",) if is_house else ())
        return TTSResolution(backend, model, api_key, sources, pid, pinned)
    return TTSResolution(backend, None, None, (), pid, pinned)
