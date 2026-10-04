import math

import numpy as np

from emcee.tts.loudness import (
    CEILING_DB, LOUDNESS_VERSION, MAX_GAIN_DB, TARGET_DB,
    active_level_db, normalize_speech,
)

RATE = 24000
FS = 32768.0


def _sine(rms_db: float, seconds: float = 0.5, freq: float = 220.0) -> np.ndarray:
    """Float sine in int16 units whose RMS is `rms_db` dBFS (peak = RMS + 3.01 dB)."""
    amp = 10 ** (rms_db / 20) * math.sqrt(2) * FS
    t = np.arange(int(seconds * RATE)) / RATE
    return amp * np.sin(2 * math.pi * freq * t)


def _pcm(x: np.ndarray) -> bytes:
    return np.clip(np.rint(x), -32768, 32767).astype("<i2").tobytes()


def _samples(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float64)


def _rms_db(x: np.ndarray) -> float:
    return 20 * math.log10(math.sqrt(np.mean((x / FS) ** 2)))


def _peak_db(x: np.ndarray) -> float:
    return 20 * math.log10(np.abs(x).max() / FS)


def test_constants_match_the_spec():
    assert (TARGET_DB, CEILING_DB, MAX_GAIN_DB) == (-20.0, -1.0, 10.0)
    assert LOUDNESS_VERSION == "v1"


def test_quiet_tone_is_raised_to_target():
    out = _samples(normalize_speech(_pcm(_sine(-26.0)), RATE))
    assert abs(_rms_db(out) - TARGET_DB) < 0.1


def test_hot_tone_is_lowered_to_target():
    out = _samples(normalize_speech(_pcm(_sine(-14.0)), RATE))
    assert abs(_rms_db(out) - TARGET_DB) < 0.1


def test_output_length_equals_input_length():
    pcm = _pcm(_sine(-26.0, seconds=0.537))
    assert len(normalize_speech(pcm, RATE)) == len(pcm)


def test_boost_is_clamped():
    # -40 wants +20 dB; the clamp allows +10, so it lands at -30.
    out = _samples(normalize_speech(_pcm(_sine(-40.0)), RATE))
    assert abs(_rms_db(out) - (-40.0 + MAX_GAIN_DB)) < 0.1


def test_cut_is_clamped():
    # -8 wants -12 dB; the clamp allows -10, so it lands at -18 (peak -15, so
    # the ceiling does not bind).
    out = _samples(normalize_speech(_pcm(_sine(-8.0)), RATE))
    assert abs(_rms_db(out) - (-8.0 - MAX_GAIN_DB)) < 0.1


def test_active_level_is_power_averaged_not_db_averaged():
    # 0.25 s at -20 then 0.25 s at -30 (both inside the gate): power mean is
    # 10*log10((0.01 + 0.001) / 2) = -22.6; a dB average would give -25.
    x = np.concatenate([_sine(-20.0, seconds=0.25), _sine(-30.0, seconds=0.25)])
    assert abs(active_level_db(_pcm(x), RATE) - (-22.596)) < 0.1


def test_ceiling_binds_on_a_click():
    # A -30 dBFS tone with one near-full-scale click: reaching -20 would put the
    # click far above the ceiling, so the gain stops at the ceiling instead.
    x = _sine(-30.0)
    x[len(x) // 2] = 10 ** (-0.5 / 20) * FS
    out = _samples(normalize_speech(_pcm(x), RATE))
    assert np.abs(out).max() <= 10 ** (CEILING_DB / 20) * FS + 1  # +1 LSB rounding
    assert _rms_db(out) < TARGET_DB - 5  # landed well short of target


def test_ceiling_attenuates_a_chunk_already_at_target_with_a_hot_peak():
    x = _sine(-20.0)
    x[100] = 10 ** (-0.2 / 20) * FS
    out = _samples(normalize_speech(_pcm(x), RATE))
    assert _peak_db(out) <= CEILING_DB + 0.01


def test_digital_silence_is_returned_unchanged():
    pcm = bytes(RATE)  # 0.5 s of zeros
    assert normalize_speech(pcm, RATE) == pcm


def test_below_silence_floor_is_returned_unchanged():
    pcm = _pcm(_sine(-66.0))  # loudest frame well below SILENCE_DB
    assert normalize_speech(pcm, RATE) == pcm


def test_empty_input_is_returned_unchanged():
    assert normalize_speech(b"", RATE) == b""


def test_input_shorter_than_one_frame_is_normalized():
    pcm = _pcm(_sine(-26.0, seconds=0.02))  # 480 samples < one 1200-sample frame
    out = normalize_speech(pcm, RATE)
    assert len(out) == len(pcm)
    assert abs(_rms_db(_samples(out)) - TARGET_DB) < 0.2


def test_gate_ignores_leading_and_trailing_silence():
    # 1 s of digital silence either side must not drag the measurement down.
    pad = np.zeros(RATE)
    x = np.concatenate([pad, _sine(-26.0), pad])
    out = _samples(normalize_speech(_pcm(x), RATE))
    voiced = out[RATE:RATE + int(0.5 * RATE)]
    assert abs(_rms_db(voiced) - TARGET_DB) < 0.1
    assert not out[:RATE].any() and not out[-RATE:].any()


def test_gate_ignores_low_noise_more_than_30_db_down():
    # Room noise 40 dB under the speech sits outside the gate.
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 10 ** (-66 / 20) * FS, RATE)
    x = np.concatenate([noise, _sine(-26.0), noise])
    out = _samples(normalize_speech(_pcm(x), RATE))
    voiced = out[RATE:RATE + int(0.5 * RATE)]
    assert abs(_rms_db(voiced) - TARGET_DB) < 0.15


def test_active_level_db_measures_a_tone_and_none_for_silence():
    assert abs(active_level_db(_pcm(_sine(-26.0)), RATE) - (-26.0)) < 0.1
    assert active_level_db(bytes(RATE), RATE) is None
    assert active_level_db(b"", RATE) is None
