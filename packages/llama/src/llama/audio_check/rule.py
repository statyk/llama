"""Window measure and verdict rule. Constants are fixed in code, never config.

numpy is imported lazily inside windows()/measure() so that importing this
module (for VERSION) loads no numpy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from llama.audio_check import model

if TYPE_CHECKING:
    import numpy as np

VERSION = "yamnet-onnx-1/rule-0.55-120-0.60"

MUSIC_MIN = 0.55
DRUM_MIN = 0.3
SPEECH_MAX = 0.3
RUN_MIN_SEC = 120
FRAC_MIN = 0.60
WINDOW_SEC = 10

_DRUM_LABELS = ("Drum kit", "Drum", "Percussion", "Snare drum", "Bass drum", "Drum roll")


@dataclass(frozen=True)
class Measure:
    run_sec: int
    frac: float


def windows(frame_scores: "np.ndarray", duration_sec: float) -> "np.ndarray":
    """Average F frame-score rows into n = max(1, floor(duration/10)) bins; (n, 521)."""
    import numpy as np

    frames = np.asarray(frame_scores, dtype=float)
    f = frames.shape[0]
    n = max(1, int(duration_sec // WINDOW_SEC))
    out = np.zeros((n, frames.shape[1]), dtype=float)
    if f == 0:
        return out
    for k in range(n):
        lo = (k * f) // n
        hi = ((k + 1) * f) // n
        if hi <= lo:  # more bins than frames: reuse the nearest frame
            hi = min(lo + 1, f)
            lo = min(lo, f - 1)
        out[k] = frames[lo:hi].mean(axis=0)
    return out


def measure(frame_scores: "np.ndarray", duration_sec: float) -> Measure:
    import numpy as np

    frames = np.asarray(frame_scores)
    if frames.shape[0] == 0:
        return Measure(run_sec=0, frac=0.0)
    w = windows(frames, duration_sec)
    names = model.CLASS_NAMES
    music = w[:, names.index("Music")]
    speech = w[:, names.index("Speech")]
    drum = w[:, [names.index(d) for d in _DRUM_LABELS]].max(axis=1)
    musical = ((music > MUSIC_MIN) | (drum > DRUM_MIN)) & (speech < SPEECH_MAX)
    best = cur = 0
    for flag in musical.tolist():
        cur = cur + 1 if flag else 0
        best = max(best, cur)
    return Measure(run_sec=int(best * WINDOW_SEC), frac=float(int(musical.sum()) / len(musical)))


def verdict(m: Measure) -> Literal["music", "junk"]:
    return "music" if m.run_sec >= RUN_MIN_SEC and m.frac >= FRAC_MIN else "junk"
