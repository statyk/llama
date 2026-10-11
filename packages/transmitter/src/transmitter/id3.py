"""The RFC 8216 §3.4 packed-audio timestamp: an ID3v2.4 tag holding one PRIV
frame owned by `com.apple.streaming.transportStreamTimestamp`, whose payload is
the segment's first-sample PTS as a 33-bit value in an 8-byte big-endian field."""

PRIV_OWNER = b"com.apple.streaming.transportStreamTimestamp"
_TS_LIMIT = 1 << 33


def _syncsafe(n: int) -> bytes:
    if not 0 <= n < 1 << 28:
        raise ValueError(f"syncsafe integer out of range: {n}")
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _unsyncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def timestamp_tag(ts: int) -> bytes:
    if not 0 <= ts < _TS_LIMIT:
        raise ValueError(f"timestamp must be a 33-bit value, got {ts}")
    body = PRIV_OWNER + b"\x00" + ts.to_bytes(8, "big")
    frame = b"PRIV" + _syncsafe(len(body)) + b"\x00\x00" + body
    return b"ID3" + bytes([4, 0, 0]) + _syncsafe(len(frame)) + frame


def parse_timestamp_tag(data: bytes) -> tuple[int, int]:
    """(timestamp, tag_length) of the ID3 tag at the start of `data`."""
    if data[:3] != b"ID3" or len(data) < 10:
        raise ValueError("data does not start with an ID3 tag")
    end = 10 + _unsyncsafe(data[6:10])
    pos = 10
    while pos + 10 <= end:
        frame_id = data[pos:pos + 4]
        size = _unsyncsafe(data[pos + 4:pos + 8])
        body = data[pos + 10:pos + 10 + size]
        if frame_id == b"PRIV" and body.startswith(PRIV_OWNER + b"\x00"):
            raw = body[len(PRIV_OWNER) + 1:]
            if len(raw) != 8:
                raise ValueError("transportStreamTimestamp payload is not 8 bytes")
            return int.from_bytes(raw, "big"), end
        pos += 10 + size
    raise ValueError("ID3 tag has no transportStreamTimestamp PRIV frame")
