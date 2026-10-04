"""Loudness normalization for synthesized speech.

Voxtral returns each call at its own level: the sentence chunks of one DJ clip
can differ by several dB (measured 2026-10-03 -- worst on presenters whose
reference clip is dynamic, but present in every voice as per-call randomness).
`normalize_speech` gains one stretch of voice PCM to a fixed speech-active level
before it is concatenated or mixed under a bed. Pure numpy, no I/O. See
docs/superpowers/specs/2026-10-04-tts-loudness-normalization-design.md.
"""
import numpy as np

TARGET_DB = -20.0    # speech-active RMS target, dBFS: today's on-air voice level
                     # (measured 2026-10-04 over 16 delivered clips, bed excluded)
CEILING_DB = -1.0    # output sample peak never exceeds this, dBFS
MAX_GAIN_DB = 10.0   # gain is clamped to +/- this
FRAME_S = 0.05       # measurement frame length, seconds
GATE_DB = 30.0       # frames more than this below the loudest frame are not "active"
SILENCE_DB = -60.0   # input whose loudest frame is below this is returned unchanged
LOUDNESS_VERSION = "v1"  # in the DJ-clip cache key; bump when anything above changes

_FULL_SCALE = 32768.0
_INT16_MIN, _INT16_MAX = -32768, 32767


def _frame_mean_squares(x: np.ndarray, framerate: int) -> np.ndarray:
    """Mean-square per FRAME_S frame; a trailing partial frame is its own frame."""
    n = max(1, round(framerate * FRAME_S))
    starts = np.arange(0, x.size, n)
    sums = np.add.reduceat(x * x, starts)
    counts = np.diff(np.append(starts, x.size))
    return sums / counts


def active_level_db(pcm: bytes, framerate: int) -> float | None:
    """Speech-active RMS level of int16 mono PCM, in dBFS: the power mean of the
    frames within GATE_DB of the loudest frame. None for empty input or input
    whose loudest frame is below SILENCE_DB."""
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / _FULL_SCALE
    if x.size == 0:
        return None
    ms = _frame_mean_squares(x, framerate)
    loudest = float(ms.max())
    if loudest <= 0.0 or 10.0 * np.log10(loudest) < SILENCE_DB:
        return None
    active = ms[ms >= loudest * 10.0 ** (-GATE_DB / 10.0)]
    return float(10.0 * np.log10(active.mean()))


def normalize_speech(pcm: bytes, framerate: int) -> bytes:
    """Gain one stretch of int16 mono speech PCM to TARGET_DB speech-active level.

    The gain is clamped to +/-MAX_GAIN_DB, then lowered further if needed so the
    output peak stays at or under CEILING_DB -- so a quiet chunk with a sharp
    transient can land short of target (preferred over a limiter, which would
    change the voice). Silent or empty input comes back unchanged. Assumes 16-bit
    mono: callers run it after their sample-width checks.
    """
    level = active_level_db(pcm, framerate)
    if level is None:
        return pcm
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    gain_db = min(max(TARGET_DB - level, -MAX_GAIN_DB), MAX_GAIN_DB)
    peak_db = 20.0 * np.log10(np.abs(x).max() / _FULL_SCALE)
    gain_db = min(gain_db, CEILING_DB - peak_db)
    y = np.rint(x * 10.0 ** (gain_db / 20.0))
    np.clip(y, _INT16_MIN, _INT16_MAX, out=y)
    return y.astype("<i2").tobytes()
