"""ADTS framing (ISO/IEC 13818-7): parse headers, split a stream into frames,
build headers (tests and the fMP4 contingency need them). Only 7-byte headers
(protection_absent=1) are built; parsing accepts either."""

from dataclasses import dataclass

from transmitter.errors import AdtsError

STATION_OBJECT_TYPE = 2        # AAC-LC
STATION_SAMPLE_RATE_INDEX = 4  # 44100 Hz
STATION_CHANNELS = 2


@dataclass(frozen=True)
class AdtsHeader:
    object_type: int
    sample_rate_index: int
    channel_config: int
    frame_length: int


def parse_header(buf: bytes, pos: int = 0) -> AdtsHeader:
    if len(buf) - pos < 7:
        raise AdtsError(f"truncated ADTS header at byte {pos}")
    b0, b1, b2, b3, b4, b5 = buf[pos:pos + 6]
    if b0 != 0xFF or (b1 & 0xF6) != 0xF0:
        raise AdtsError(f"lost ADTS sync at byte {pos}")
    length = ((b3 & 0x03) << 11) | (b4 << 3) | (b5 >> 5)
    if length < 7:
        raise AdtsError(f"ADTS frame length {length} at byte {pos} is shorter than its header")
    return AdtsHeader(
        object_type=((b2 >> 6) & 0x3) + 1,
        sample_rate_index=(b2 >> 2) & 0xF,
        channel_config=((b2 & 0x1) << 2) | (b3 >> 6),
        frame_length=length,
    )


def frame_offsets(buf: bytes) -> list[int]:
    """Byte offset of every frame, plus a final entry == len(buf)."""
    offsets = [0]
    pos = 0
    while pos < len(buf):
        length = parse_header(buf, pos).frame_length
        if pos + length > len(buf):
            raise AdtsError(f"truncated ADTS frame at byte {pos} ({length} bytes declared)")
        pos += length
        offsets.append(pos)
    return offsets


def split_frames(buf: bytes) -> list[bytes]:
    offsets = frame_offsets(buf)
    return [buf[a:b] for a, b in zip(offsets, offsets[1:])]


def build_frame(payload: bytes, *, object_type: int = STATION_OBJECT_TYPE,
                sample_rate_index: int = STATION_SAMPLE_RATE_INDEX,
                channel_config: int = STATION_CHANNELS) -> bytes:
    length = 7 + len(payload)
    if length >= 1 << 13:
        raise ValueError(f"ADTS frame too long: {length}")
    header = bytes([
        0xFF,
        0xF1,  # MPEG-4, layer 0, protection absent
        (((object_type - 1) & 0x3) << 6) | ((sample_rate_index & 0xF) << 2) | ((channel_config >> 2) & 0x1),
        ((channel_config & 0x3) << 6) | ((length >> 11) & 0x3),
        (length >> 3) & 0xFF,
        ((length & 0x7) << 5) | 0x1F,  # buffer fullness 0x7FF (VBR), high bits
        0xFC,                          # buffer fullness low bits; one raw data block
    ])
    return header + payload


def require_station_format(h: AdtsHeader) -> None:
    got = (h.object_type, h.sample_rate_index, h.channel_config)
    want = (STATION_OBJECT_TYPE, STATION_SAMPLE_RATE_INDEX, STATION_CHANNELS)
    if got != want:
        raise AdtsError(f"ADTS stream is (object type, rate index, channels) {got}, need {want}")
