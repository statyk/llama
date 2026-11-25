"""Audio checks and edits for one voiced announcement piece (a short phrase).

A take is 16-bit mono PCM. `onset_problem` rejects a take whose first 50 ms is
already at speech level (the engine clipped the start of the word); `trim_edges`
cuts the take to ~80 ms before and ~120 ms after the speech, padding with digital
silence when less exists; `finish_take` trims and then gains to the speech target.
Pure numpy plus the stdlib wave module.
"""
import io
import wave

import numpy as np

from emcee.tts.loudness import active_level_db, normalize_speech
from emcee.tts.provider import SpeechError

ONSET_WINDOW_S = 0.05
FRAME_S = 0.01
ONSET_MARGIN_DB = 20.0
TRIM_THRESHOLD_DB = -60.0
LEAD_S = 0.08
TAIL_S = 0.12

_FULL_SCALE = 32768.0


def read_wav(wav: bytes) -> tuple[bytes, int]:
    """16-bit mono PCM and its sample rate from WAV bytes; SpeechError otherwise."""
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            if channels != 1 or width != 2:
                raise SpeechError(
                    f"expected 16-bit mono WAV, got {width * 8}-bit, {channels} channel(s)"
                )
            return w.readframes(w.getnframes()), rate
    except (wave.Error, EOFError) as e:
        raise SpeechError(f"unreadable WAV from the speech engine: {e}") from e


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _frame_db(pcm: bytes, rate: int) -> tuple[np.ndarray, int]:
    """RMS dBFS per FRAME_S frame (-inf for digital silence) and the frame length."""
    n = max(1, round(rate * FRAME_S))
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / _FULL_SCALE
    if x.size == 0:
        return np.empty(0), n
    starts = np.arange(0, x.size, n)
    ms = np.add.reduceat(x * x, starts) / np.diff(np.append(starts, x.size))
    with np.errstate(divide="ignore"):
        return 10.0 * np.log10(ms), n


def onset_problem(pcm: bytes, rate: int) -> str | None:
    """A reason string when every frame of the first ONSET_WINDOW_S is within
    ONSET_MARGIN_DB of the take's speech-active level (no lead-in), else None."""
    level = active_level_db(pcm, rate)
    if level is None:
        return None
    db, n = _frame_db(pcm, rate)
    window = db[: max(1, round(ONSET_WINDOW_S / FRAME_S))]
    if window.size and bool(np.all(window >= level - ONSET_MARGIN_DB)):
        return (
            f"onset: the first {ONSET_WINDOW_S * 1000:.0f} ms is already at speech "
            "level (the start of the take is clipped)"
        )
    return None


def trim_edges(pcm: bytes, rate: int) -> bytes:
    """Keep LEAD_S before the first and TAIL_S after the last frame at or above
    TRIM_THRESHOLD_DB, padding with digital silence to exactly that much."""
    db, n = _frame_db(pcm, rate)
    loud = np.flatnonzero(db >= TRIM_THRESHOLD_DB)
    if loud.size == 0:
        raise ValueError("no speech")
    total = len(pcm) // 2
    first = int(loud[0]) * n
    last = min((int(loud[-1]) + 1) * n, total)
    lead, tail = round(rate * LEAD_S), round(rate * TAIL_S)
    start, end = max(0, first - lead), min(total, last + tail)
    body = pcm[2 * start : 2 * end]
    pad_lead = lead - (first - start)
    pad_tail = tail - (end - last)
    return bytes(2 * pad_lead) + body + bytes(2 * pad_tail)


def finish_take(pcm: bytes, rate: int) -> bytes:
    return normalize_speech(trim_edges(pcm, rate), rate)
