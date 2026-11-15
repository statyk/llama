"""Classify one audio file: decode, run the model, apply the rule.

numpy and miniaudio are imported only inside the functions that need them.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from llama.audio_check import decode, model, rule

_MODEL: "model.Model | None" = None
_FAILURE: "model.ClassifierUnavailable | None" = None


@dataclass(frozen=True)
class Result:
    verdict: str
    run_sec: int
    frac: float


def reset_model_cache() -> None:
    """Forget the cached model / load failure (tests)."""
    global _MODEL, _FAILURE
    _MODEL = None
    _FAILURE = None


def get_model() -> "model.Model":
    """The per-process model. A failed load prints one stderr line, then re-raises quietly."""
    global _MODEL, _FAILURE
    if _MODEL is not None:
        return _MODEL
    if _FAILURE is not None:
        raise _FAILURE
    try:
        _MODEL = model.load()
    except model.ClassifierUnavailable as exc:
        _FAILURE = exc
        print(
            f"llama: audio check unavailable ({exc}); junk-title drops are recorded unchecked",
            file=sys.stderr,
        )
        raise
    return _MODEL


def classify_file(path: Path) -> Result:
    """Raises ClassifierUnavailable (no model, or the model run failed) / DecodeError."""
    mdl = get_model()
    wave, seconds = decode.to_16k_mono(Path(path))
    try:
        scores = mdl.frame_scores(wave)
    except Exception as exc:
        raise model.ClassifierUnavailable(f"the audio classifier failed while running: {exc}") from exc
    m = rule.measure(scores, seconds)
    return Result(verdict=rule.verdict(m), run_sec=m.run_sec, frac=m.frac)
