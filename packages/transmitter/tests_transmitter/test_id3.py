import pytest

from transmitter import id3


def test_timestamp_tag_layout():
    tag = id3.timestamp_tag(0x1_2345_6789)
    assert len(tag) == 73
    assert tag[:10] == b"ID3\x04\x00\x00\x00\x00\x00\x3f"          # v2.4, size 63 (syncsafe)
    assert tag[10:20] == b"PRIV\x00\x00\x00\x35\x00\x00"           # frame body 53 bytes
    assert tag[20:64] == b"com.apple.streaming.transportStreamTimestamp"
    assert tag[64:65] == b"\x00"
    assert tag[65:] == (0x1_2345_6789).to_bytes(8, "big")


@pytest.mark.parametrize("ts", [0, 1, 921_600, (1 << 33) - 1])
def test_round_trip(ts):
    assert id3.parse_timestamp_tag(id3.timestamp_tag(ts) + b"rest") == (ts, 73)


@pytest.mark.parametrize("ts", [-1, 1 << 33])
def test_rejects_out_of_range(ts):
    with pytest.raises(ValueError):
        id3.timestamp_tag(ts)


def test_parse_rejects_non_id3():
    with pytest.raises(ValueError):
        id3.parse_timestamp_tag(b"\xff\xf1\x50\x80\x03\xdf\xfc")
