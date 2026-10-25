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


def test_validate_rows_accepts_abutting_and_cut_then_aligned():
    validate_rows([row(0, "a", 0, 100), row(1, "b", 100, 50)])
    validate_rows([row(0, "a", 0, 1000, cut_frame=441), row(1, "b", 441, 10, run_start=True)])


def test_validate_rows_rejects_empty_row_and_cut_outside_show():
    with pytest.raises(LayoutError, match="no frames"):
        validate_rows([row(0, "a", 0, 0)])
    with pytest.raises(LayoutError, match="cut outside"):
        validate_rows([row(0, "a", 10, 100, cut_frame=10)])
    with pytest.raises(LayoutError, match="cut outside"):
        validate_rows([row(0, "a", 10, 100, cut_frame=111)])


def test_build_segment_plan_end_boundary(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 441)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    _, frames = segment.parse(store.build_segment(0, [row(0, "a", 0, 441)]))
    assert len(frames) == F
    write_fake_show(tmp_path / "b.aac", "b", 440)
    with pytest.raises(LayoutError, match="past the end of the plan"):
        store.build_segment(0, [row(0, "b", 0, 440)])


def test_silent_frame_must_be_exactly_one_frame(tmp_path):
    with pytest.raises(LayoutError, match="silent frame"):
        FrameStore(tmp_path, fake_frame("s", 0) * 2)
    with pytest.raises(LayoutError, match="silent frame"):
        FrameStore(tmp_path, b"")


def test_unreadable_encode_is_a_layout_error(tmp_path):
    (tmp_path / "d.aac").mkdir()
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="d.aac"):
        store.frame_count("d")


def test_phase1_row_loads_with_defaults():
    r = PlanRow.from_json({"seq": 0, "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                           "frames": 10, "run_start": True, "cut_frame": None})
    assert r.kind == "show" and r.block is None and r.bends == () and dict(r.extra) == {}


def test_unknown_keys_survive_a_round_trip():
    data = {"seq": 1, "slug": "a", "dir": "a", "key": "k", "start_frame": 0, "frames": 10,
            "run_start": False, "cut_frame": None, "future_field": {"x": 1}}
    r = PlanRow.from_json(data)
    assert r.extra["future_field"] == {"x": 1}
    assert PlanRow.from_json(r.to_json()).to_json() == r.to_json()
    assert r.to_json()["future_field"] == {"x": 1}


def test_scheduler_fields_round_trip_as_tuples():
    import json
    r = PlanRow(seq=2, slug="ann-abc", dir="interstitials", key="k2", start_frame=5, frames=3,
                kind="interstitial", role="next", block="dead-evening",
                nominal_start="2096-10-02T23:00:00Z", names=(("dead-evening", "2096-10-02T23:00:00Z"),),
                bends=("era",))
    back = PlanRow.from_json(json.loads(json.dumps(r.to_json())))
    assert back == r and back.names == (("dead-evening", "2096-10-02T23:00:00Z"),)
    assert back.bends == ("era",)
