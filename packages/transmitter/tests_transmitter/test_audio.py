import numpy as np
import pytest

from tests_transmitter.helpers import requires_ffmpeg, stereo_sine, write_mp3
from transmitter import audio
from transmitter.errors import AnalysisError, DecodeError

SUMMARY = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -18.4 LUFS
    Threshold: -28.5 LUFS

  Loudness range:
    LRA:         6.1 LU

  True peak:
    Peak:       -0.7 dBFS
"""


def test_parse_summary():
    assert audio.parse_ebur128_summary("noise\n" + SUMMARY) == audio.Loudness(-18.4, -0.7)


def test_parse_summary_handles_silence():
    text = SUMMARY.replace("-18.4 LUFS", "-70.0 LUFS").replace("-0.7 dBFS", "-inf dBFS")
    assert audio.parse_ebur128_summary(text) == audio.Loudness(None, None)


def test_parse_summary_uses_the_last_summary():
    text = SUMMARY.replace("-18.4", "-30.0") + SUMMARY
    assert audio.parse_ebur128_summary(text).i_lufs == -18.4


def test_parse_summary_without_summary_is_an_error():
    with pytest.raises(AnalysisError):
        audio.parse_ebur128_summary("no summary here")


@requires_ffmpeg
def test_decode_honours_lame_delay_and_padding(tmp_path):
    """Two halves of one sine, split at a sample that is not an MP3 frame
    boundary, decode back to exactly their own lengths: a segue stays gapless."""
    pcm = stereo_sine(6.0, 440.0, 0.3)
    split = 123_457
    write_mp3(tmp_path / "a.mp3", pcm[:split])
    write_mp3(tmp_path / "b.mp3", pcm[split:])
    a = np.concatenate(list(audio.iter_decode(tmp_path / "a.mp3")))
    b = np.concatenate(list(audio.iter_decode(tmp_path / "b.mp3")))
    assert len(a) == split and len(b) == len(pcm) - split
    assert a.dtype == np.float32 and a.shape[1] == 2


@requires_ffmpeg
def test_decode_resamples_a_mono_24k_clip_to_stereo_44k1(tmp_path):
    mono = stereo_sine(2.0, 300.0, 0.3, rate=24_000)[:, 0]
    write_mp3(tmp_path / "clip.mp3", mono, rate=24_000)
    out = np.concatenate(list(audio.iter_decode(tmp_path / "clip.mp3")))
    assert out.shape[1] == 2
    assert abs(len(out) - 88_200) <= 64


@requires_ffmpeg
def test_decode_failure_is_a_decode_error(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(DecodeError):
        list(audio.iter_decode(bad))


@requires_ffmpeg
def test_meter_measures_a_known_sine():
    meter = audio.LoudnessMeter()
    pcm = stereo_sine(8.0, 1000.0, 0.1)            # -20 dBFS peak in both channels
    for i in range(0, len(pcm), 50_000):
        meter.write(pcm[i:i + 50_000])
    loud = meter.finish()
    assert loud.i_lufs == pytest.approx(-20.0, abs=0.5)
    assert loud.tp_dbfs == pytest.approx(-20.0, abs=0.5)


@requires_ffmpeg
def test_meter_on_silence_and_on_nothing():
    meter = audio.LoudnessMeter()
    meter.write(np.zeros((44_100 * 3, 2), np.float32))
    assert meter.finish() == audio.Loudness(None, None)
    assert audio.LoudnessMeter().finish() == audio.Loudness(None, None)
