import wave
from pathlib import Path

import numpy as np
import pytest

from emcee.tts.bed import BED_RATE, Bed, load_bed_pcm, mix_bed
from emcee.tts.provider import SpeechError


def _write_wav(path: Path, samples: np.ndarray, rate: int = BED_RATE,
               channels: int = 1, sampwidth: int = 2) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(samples.astype("<i2").tobytes())


def _pcm(samples) -> bytes:
    return np.asarray(samples, dtype="<i2").tobytes()


def test_bed_is_frozen_value():
    b = Bed(path=Path("/x.wav"), gain_db=-20.0)
    assert b.path == Path("/x.wav") and b.gain_db == -20.0
    with pytest.raises(Exception):
        b.gain_db = 0.0  # frozen


def test_load_bed_pcm_accepts_24k_mono_16bit(tmp_path: Path):
    p = tmp_path / "bed.wav"
    _write_wav(p, np.full(BED_RATE, 1000, dtype="<i2"))
    pcm, rate, ch, sw = load_bed_pcm(p)
    assert (rate, ch, sw) == (BED_RATE, 1, 2)
    assert len(pcm) == BED_RATE * 2


@pytest.mark.parametrize("rate,ch,sw", [(48000, 1, 2), (BED_RATE, 2, 2), (BED_RATE, 1, 1)])
def test_load_bed_pcm_rejects_wrong_format(tmp_path: Path, rate, ch, sw):
    p = tmp_path / "bad.wav"
    # width-1 needs uint8 frames; just write zeros of the right byte count.
    frames = np.zeros(rate * ch, dtype="<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(ch); w.setsampwidth(sw); w.setframerate(rate)
        w.writeframes(frames.tobytes()[: rate * ch * sw])
    with pytest.raises(SpeechError, match="24kHz mono 16-bit"):
        load_bed_pcm(p)


def test_load_bed_pcm_missing_file_raises(tmp_path: Path):
    with pytest.raises(SpeechError, match="cannot read"):
        load_bed_pcm(tmp_path / "nope.wav")


def test_mix_bed_length_is_preroll_plus_voice_plus_tail():
    rate = BED_RATE
    voice = _pcm(np.full(rate, 100))          # 1.0s of voice
    bed = _pcm(np.full(rate, 500))            # 1.0s of bed
    out = mix_bed(voice, bed, rate, gain_db=0.0, pre_roll_s=1.5, tail_s=2.0, fade_s=0.0)
    n = len(out) // 2
    assert n == int(round(1.5 * rate)) + rate + int(round(2.0 * rate))


def test_mix_bed_attenuates_bed_in_flat_region():
    rate = BED_RATE
    voice = _pcm(np.zeros(rate))
    bed = _pcm(np.full(rate, 1000))
    # fade_s=0 so the pre-roll is flat; sample the middle of the pre-roll (no voice there).
    out = np.frombuffer(mix_bed(voice, bed, rate, gain_db=-20.0, pre_roll_s=1.0, tail_s=0.0, fade_s=0.0), dtype="<i2")
    mid = out[rate // 2]
    assert abs(int(mid) - round(1000 * 10 ** (-20 / 20))) <= 1  # ~100


def test_mix_bed_loops_short_bed():
    rate = BED_RATE
    voice = _pcm(np.zeros(rate * 3))         # 3s voice -> needs > the 1s bed tiled
    bed = _pcm(np.full(rate, 800))
    out = np.frombuffer(mix_bed(voice, bed, rate, gain_db=0.0, pre_roll_s=0.0, tail_s=0.0, fade_s=0.0), dtype="<i2")
    assert out.size == rate * 3
    assert np.all(out == 800)                 # bed tiled across the whole clip


def test_mix_bed_fades_to_silence_at_ends():
    rate = BED_RATE
    voice = _pcm(np.zeros(rate))
    bed = _pcm(np.full(rate, 1000))
    out = np.frombuffer(mix_bed(voice, bed, rate, gain_db=0.0, pre_roll_s=0.5, tail_s=0.5, fade_s=0.5), dtype="<i2")
    assert out[0] == 0 and out[-1] == 0


def test_mix_bed_clips_to_int16_range():
    rate = 100  # small clip; framerate only scales lengths
    voice = _pcm(np.full(rate, 32767))
    bed = _pcm(np.full(rate, 32767))
    out = np.frombuffer(mix_bed(voice, bed, rate, gain_db=0.0, pre_roll_s=0.0, tail_s=0.0, fade_s=0.0), dtype="<i2")
    assert out.max() <= 32767 and out.min() >= -32768
    assert out.max() == 32767  # voice+bed summed past full scale, hard-clipped
