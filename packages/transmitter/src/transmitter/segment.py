"""A packed-audio segment: the ID3 timestamp tag + exactly 441 ADTS frames.
`ts_index` is the grid index N for station segments and the loop index k for
fallback segments (spec: fallback segment timestamps are k·d)."""

from typing import Sequence

from transmitter import adts, grid, id3


def assemble(ts_index: int, frames: Sequence[bytes]) -> bytes:
    if len(frames) != grid.SEGMENT_FRAMES:
        raise ValueError(f"a segment is {grid.SEGMENT_FRAMES} frames, got {len(frames)}")
    return id3.timestamp_tag(grid.segment_timestamp(ts_index)) + b"".join(frames)


def parse(data: bytes) -> tuple[int, list[bytes]]:
    ts, tag_len = id3.parse_timestamp_tag(data)
    return ts, adts.split_frames(data[tag_len:])


def segment_key(epoch_id: str, n: int) -> str:
    return f"seg/{epoch_id}/{n}.aac"
