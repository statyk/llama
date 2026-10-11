import numpy as np
import pytest

from tests_transmitter.helpers import decode_adts, requires_ffmpeg
from transmitter import aacenc, adts
from transmitter.errors import EncodeError
from transmitter.grid import FRAME_SAMPLES


def _zeros(n):
    return np.zeros((n, 2), np.float32)


def test_frames_for_and_pad_to_frame():
    assert aacenc.pad_to_frame(0) == 0
    assert aacenc.pad_to_frame(1) == 1024
    assert aacenc.pad_to_frame(2048) == 2048
    assert aacenc.frames_for(4096, 1) == 5
    with pytest.raises(ValueError):
        aacenc.frames_for(4097, 1)


def test_as_station_pcm_rejects_mono():
    with pytest.raises(ValueError):
        aacenc.as_station_pcm(np.zeros(10, np.float32))


@requires_ffmpeg
def test_encode_pcm_yields_station_format_frames():
    frames = adts.split_frames(aacenc.encode_pcm(_zeros(4 * FRAME_SAMPLES)))
    assert frames
    for f in frames:
        adts.require_station_format(adts.parse_header(f))


@requires_ffmpeg
@pytest.mark.parametrize("frames", [3, 441, 1000])
def test_extra_frames_is_the_same_for_every_padded_length(frames):
    extra = aacenc.extra_frames()
    got = len(adts.split_frames(aacenc.encode_pcm(_zeros(frames * FRAME_SAMPLES))))
    assert got == aacenc.frames_for(frames * FRAME_SAMPLES, extra)


@requires_ffmpeg
def test_priming_matches_the_declared_constant():
    pcm = _zeros(44_100)
    pcm[5000:5003] = 0.8
    decoded = decode_adts(aacenc.encode_pcm(pcm))
    peak = int(np.argmax(np.abs(decoded[:, 0])))
    assert abs((peak - 5001) - aacenc.ENCODER_PRIMING_SAMPLES) <= 3


@requires_ffmpeg
def test_file_encoder_streams_and_renames_atomically(tmp_path):
    out = tmp_path / "shows" / "k.aac"
    enc = aacenc.AacFileEncoder(out)
    enc.write(_zeros(3000))
    enc.write_silence(5000)
    assert enc.samples_written == 8000
    assert enc.close() == out
    assert len(adts.split_frames(out.read_bytes())) == aacenc.frames_for(aacenc.pad_to_frame(8000), aacenc.extra_frames())
    assert [p.name for p in out.parent.iterdir()] == ["k.aac"]


@requires_ffmpeg
def test_file_encoder_abort_leaves_nothing(tmp_path):
    out = tmp_path / "k.aac"
    with pytest.raises(RuntimeError):
        with aacenc.AacFileEncoder(out) as enc:
            enc.write(_zeros(2048))
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_silent_frame_is_station_format_and_decodes_to_silence():
    frame = aacenc.silent_frame()
    adts.require_station_format(adts.parse_header(frame))
    decoded = decode_adts(frame * 20)
    assert float(np.max(np.abs(decoded))) < 1e-4


def test_missing_ffmpeg_is_an_encode_error():
    with pytest.raises(EncodeError):
        aacenc.encode_pcm(_zeros(1024), ffmpeg="/nonexistent/ffmpeg")
