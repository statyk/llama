import pytest

from transmitter import adts
from transmitter.errors import AdtsError


def test_build_frame_matches_ffmpeg_header():
    # ffmpeg 8.1 `-c:a aac -f adts`, 44.1 kHz stereo, first frame: fff1508003dffc (30 bytes)
    frame = adts.build_frame(bytes(23))
    assert frame[:7].hex() == "fff1508003dffc"
    assert len(frame) == 30


def test_parse_header_fields():
    h = adts.parse_header(adts.build_frame(b"x" * 100))
    assert (h.object_type, h.sample_rate_index, h.channel_config, h.frame_length) == (2, 4, 2, 107)


def test_split_frames_round_trip():
    frames = [adts.build_frame(bytes([i]) * (i + 1)) for i in range(5)]
    data = b"".join(frames)
    assert adts.split_frames(data) == frames
    assert adts.frame_offsets(data) == [0, 8, 17, 27, 38, 50]


def test_split_rejects_lost_sync():
    with pytest.raises(AdtsError, match="sync"):
        adts.split_frames(adts.build_frame(b"ab") + b"\x00\x00junkjunk")


def test_split_rejects_truncated_frame():
    with pytest.raises(AdtsError):
        adts.split_frames(adts.build_frame(b"abcdef")[:-1])


def test_require_station_format():
    adts.require_station_format(adts.parse_header(adts.build_frame(b"z")))
    with pytest.raises(AdtsError):
        adts.require_station_format(adts.parse_header(adts.build_frame(b"z", channel_config=1)))
