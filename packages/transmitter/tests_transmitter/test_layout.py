import pytest

from tests_transmitter.helpers import fake_frame, payloads, write_fake_show
from transmitter import grid, segment
from transmitter.errors import LayoutError
from transmitter.layout import FrameStore, Piece, PlanRow, pieces, rows_overlapping, segment_pieces, validate_rows

F = grid.SEGMENT_FRAMES


def row(seq, key, start, frames, **kw):
    return PlanRow(seq=seq, slug=f"s{seq}", dir=f"s{seq}", key=key, start_frame=start, frames=frames, **kw)


def test_pieces_show_gap_show():
    rows = [row(0, "a", 0, 100), row(1, "b", 187, 50)]
    assert pieces(rows, 90, 200) == [Piece("a", 90, 10), Piece(None, 0, 87), Piece("b", 0, 13)]


def test_pieces_before_the_first_row_and_after_the_last_are_silence():
    rows = [row(0, "a", 10, 5)]
    assert pieces(rows, 0, 20) == [Piece(None, 0, 10), Piece("a", 0, 5), Piece(None, 0, 5)]


def test_pieces_respect_a_cut_row():
    rows = [row(0, "a", 0, 1000, cut_frame=441), row(1, "b", 882, 441, run_start=True)]
    assert rows[0].end_frame == 441
    assert segment_pieces(rows, 1) == [Piece(None, 0, 441)]
    assert segment_pieces(rows, 2) == [Piece("b", 0, 441)]


def test_validate_rows_rejects_overlap_and_unaligned_run_start():
    with pytest.raises(LayoutError, match="overlap"):
        validate_rows([row(0, "a", 0, 100), row(1, "b", 50, 10)])
    with pytest.raises(LayoutError, match="segment-aligned"):
        validate_rows([row(0, "a", 5, 100, run_start=True)])


def test_rows_overlapping():
    rows = [row(0, "a", 0, 100), row(1, "b", 187, 50)]
    assert rows_overlapping(rows, 100, 187) == []
    assert rows_overlapping(rows, 99, 188) == rows


def test_plan_row_json_round_trip():
    r = row(3, "k", 882, 1234, run_start=True, cut_frame=1000)
    assert PlanRow.from_json(r.to_json()) == r


def test_build_segment_spans_show_end_gap_and_next_show(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 600)
    write_fake_show(tmp_path / "b.aac", "b", 900)
    rows = [row(0, "a", 0, 600), row(1, "b", 687, 900)]
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    ts, frames = segment.parse(store.build_segment(1, rows))
    assert ts == grid.segment_timestamp(1)
    got = payloads(frames)
    assert got[:159] == [f"a:{i}" for i in range(441, 600)]
    assert got[159:246] == ["silence:0"] * 87
    assert got[246:] == [f"b:{i}" for i in range(0, 195)]


def test_build_segment_refuses_past_the_plan(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 500)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="past the end of the plan"):
        store.build_segment(1, [row(0, "a", 0, 500)])


def test_build_segment_checks_the_encode_matches_the_plan(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 400)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="400 frames"):
        store.build_segment(0, [row(0, "a", 0, 900)])


def test_missing_encode_is_a_layout_error(tmp_path):
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="missing"):
        store.build_segment(0, [row(0, "zz", 0, 900)])
