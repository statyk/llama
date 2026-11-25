import io
import wave

import numpy as np
import pytest

from emcee.piece_audio import (
    finish_take,
    onset_problem,
    pcm_to_wav,
    read_wav,
    trim_edges,
)
from emcee.tts.loudness import TARGET_DB, active_level_db
from emcee.tts.provider import SpeechError

RATE = 24000


def silence(s: float) -> bytes:
    return bytes(2 * round(RATE * s))


def tone(s: float, dbfs: float) -> bytes:
    """A 220 Hz sine whose RMS is `dbfs` dBFS."""
    n = round(RATE * s)
    amp = 10 ** (dbfs / 20) * np.sqrt(2) * 32768
    x = amp * np.sin(2 * np.pi * 220 * np.arange(n) / RATE)
    return np.rint(x).astype("<i2").tobytes()


def test_onset_rejects_a_take_that_starts_at_speech_level():
    assert "onset" in onset_problem(tone(1.0, -20), RATE)


def test_onset_accepts_a_short_quiet_lead():
    assert onset_problem(silence(0.03) + tone(1.0, -20), RATE) is None


def test_trim_keeps_exactly_80ms_lead_and_120ms_tail():
    out = trim_edges(silence(0.5) + tone(1.0, -20) + silence(0.7), RATE)
    assert len(out) // 2 == round(RATE * (0.08 + 1.0 + 0.12))


def test_trim_pads_with_digital_silence_when_the_lead_is_short():
    out = trim_edges(silence(0.02) + tone(1.0, -20), RATE)
    assert len(out) // 2 == round(RATE * (0.08 + 1.0 + 0.12))
    assert out[: 2 * 1440] == bytes(2 * 1440)


def test_trim_of_silence_is_no_speech():
    with pytest.raises(ValueError, match="no speech"):
        trim_edges(silence(1.0), RATE)


def test_finish_take_reaches_the_speech_target():
    # -28 dBFS needs +8 dB; normalize_speech clamps gain to +/-10 dB, so -32 could not reach it
    out = finish_take(silence(0.2) + tone(1.0, -28), RATE)
    assert abs(active_level_db(out, RATE) - TARGET_DB) < 0.5


def _wav(channels: int, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(RATE)
        w.writeframes(bytes(width * channels * 100))
    return buf.getvalue()


def test_read_wav_refuses_stereo():
    with pytest.raises(SpeechError):
        read_wav(_wav(2))


def test_read_wav_refuses_non_16_bit_and_garbage():
    with pytest.raises(SpeechError):
        read_wav(_wav(1, 1))
    with pytest.raises(SpeechError):
        read_wav(b"not a wav")


def test_wav_round_trip():
    pcm = tone(0.1, -20)
    assert read_wav(pcm_to_wav(pcm, RATE)) == (pcm, RATE)
