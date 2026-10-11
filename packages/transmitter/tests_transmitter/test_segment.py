import pytest

from transmitter import adts, grid, segment


def test_assemble_prefixes_the_grid_timestamp():
    frames = [adts.build_frame(i.to_bytes(4, "big")) for i in range(441)]
    data = segment.assemble(9321, frames)
    ts, parsed = segment.parse(data)
    assert ts == grid.segment_timestamp(9321) == 299_008
    assert parsed == frames


def test_assemble_requires_exactly_441_frames():
    with pytest.raises(ValueError):
        segment.assemble(0, [adts.build_frame(b"x")] * 440)


def test_segment_key():
    assert segment.segment_key("e20261010T120000Z", 42) == "seg/e20261010T120000Z/42.aac"
