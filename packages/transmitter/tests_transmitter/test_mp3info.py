import struct

import pytest

from tests_transmitter.helpers import requires_ffmpeg, stereo_sine, write_mp3
from transmitter.mp3info import mp3_seconds

HDR = bytes([0xFF, 0xFB, 0x90, 0x00])      # MPEG-1 L3, 128 kbps, 44.1 kHz


def _id3_file(path):
    tag = b"ID3\x03\x00\x00" + bytes([0, 0, 0, 100]) + b"\0" * 100
    path.write_bytes(tag + HDR + b"\0" * 16_000)
    return path


@requires_ffmpeg
def test_mp3_seconds_from_frame_header(tmp_path):
    p = tmp_path / "c.mp3"
    write_mp3(p, stereo_sine(10.0, 440, 0.1))
    assert mp3_seconds(p) == pytest.approx(10.0, abs=0.2)


def test_mp3_seconds_skips_id3v2(tmp_path):
    p = _id3_file(tmp_path / "a.mp3")
    assert p.stat().st_size == 16_114
    assert mp3_seconds(p) == pytest.approx((16_114 - 110) * 8 / 128_000, abs=1e-6)


def test_mp3_seconds_uses_the_given_size(tmp_path):
    p = _id3_file(tmp_path / "a.mp3")
    assert mp3_seconds(p, 32_114) == pytest.approx((32_114 - 110) * 8 / 128_000, abs=1e-6)


def test_mp3_seconds_none_without_a_frame(tmp_path):
    (tmp_path / "x.mp3").write_bytes(b"\0" * 1000)
    assert mp3_seconds(tmp_path / "x.mp3") is None


def test_mpeg2_layer3_bitrate(tmp_path):
    p = tmp_path / "m.mp3"
    p.write_bytes(bytes([0xFF, 0xF3, 0x80, 0x00]) + b"\0" * 996)   # MPEG-2 L3, 64 kbps
    assert mp3_seconds(p) == pytest.approx(1000 * 8 / 64_000)


def test_reserved_headers_are_skipped(tmp_path):
    p = tmp_path / "r.mp3"       # layer II header, then a valid one at offset 4
    p.write_bytes(bytes([0xFF, 0xFD, 0x90, 0x00]) + HDR + b"\0" * 100)
    assert mp3_seconds(p) == pytest.approx(104 * 8 / 128_000)
