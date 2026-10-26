"""The plan file and the two drop paths (`replan_from`, `cut_for_recovery`).
The phase-1 shuffle planner is retired: rows are laid out here by hand; the
scheduler's own choice is tested in test_scheduler*.py and test_pipeline.py."""

import pytest

from transmitter import planner
from transmitter.errors import PlanError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.layout import PlanRow, validate_rows

SLUGS = ("alpha", "bravo", "charlie", "delta")


def ext(rows, *, frames=1000, gap_frames=87, until_frame=10_000, start_frame=0, run_start=True):
    """Lay 1000-frame rows back to back with the gap from `start_frame` until
    `until_frame` is covered."""
    out = list(rows)
    start, mark = start_frame, run_start
    while not out or out[-1].end_frame < until_frame:
        slug = SLUGS[len(out) % len(SLUGS)]
        row = PlanRow(seq=len(out), slug=slug, dir=slug, key=f"key-{slug}", start_frame=start,
                      frames=frames, run_start=mark)
        out.append(row)
        start, mark = row.end_frame + gap_frames, False
    validate_rows(out)
    return out


def test_next_start_is_the_gap_after_the_last_row():
    rows = ext([], until_frame=2_000)
    assert planner.next_start(rows, 87) == rows[-1].end_frame + 87


def test_replan_from_keeps_the_boundary():
    rows = ext([], until_frame=5_000)
    kept, start, run_start = planner.replan_from(rows, 2)
    assert kept == rows[:2] and start == rows[2].start_frame and run_start is False
    assert planner.replan_from(rows, 0)[2] is True


def _rows_at(start_n):
    return ext([], start_frame=start_n * F, until_frame=start_n * F + 5_000)


def test_cut_for_recovery_cuts_the_spanning_show_and_drops_the_rest():
    rows = _rows_at(10)                               # 1000-frame shows from frame 4410
    last = 12                                         # published through segment 12
    kept = planner.cut_for_recovery(rows, last)
    boundary = 13 * F                                 # 5733, inside row 1 (5497..6497)
    assert kept[0] == rows[0]
    assert kept[1].cut_frame == boundary and kept[1].end_frame == boundary
    assert len(kept) == 2


def test_cut_for_recovery_with_nothing_published_drops_everything():
    assert planner.cut_for_recovery(_rows_at(10), None) == []


def test_publish_next():
    rows = _rows_at(10)
    assert planner.current_run_start(rows) == 10
    assert planner.publish_next([], None) is None
    assert planner.publish_next(rows, None) == 10
    assert planner.publish_next(rows, 14) == 15
    assert planner.publish_next(rows, 3) == 10        # last belongs to an older run


def test_plan_file_round_trip(tmp_path):
    rows = _rows_at(10)
    planner.write_plan(tmp_path / "plan.jsonl", rows)
    assert planner.read_plan(tmp_path / "plan.jsonl") == rows
    assert planner.read_plan(tmp_path / "missing.jsonl") == []
    assert [p.name for p in tmp_path.iterdir()] == ["plan.jsonl"]


def test_cut_for_recovery_drops_a_row_starting_exactly_at_the_boundary():
    # gap chosen so row 1 starts on segment 13's first frame (5733 = 5410 + 323)
    rows = ext([], start_frame=10 * F, gap_frames=13 * F - (10 * F + 1000), until_frame=10 * F + 5_000)
    assert rows[1].start_frame == 13 * F
    kept = planner.cut_for_recovery(rows, 12)
    assert kept == rows[:1]
    validate_rows(kept)


@pytest.mark.parametrize("bad", [
    "{not json",                                                   # invalid JSON
    "[1, 2]",                                                      # valid JSON, wrong shape
    '{"seq": 1, "slug": "x"}',                                     # missing fields
    '{"seq": 1, "slug": "x", "dir": "x", "key": "k", "start_frame": 5000, "frames": "9"}',  # wrong type
])
def test_a_corrupt_plan_is_a_plan_error_naming_the_file_and_line(tmp_path, bad):
    path = tmp_path / "plan.jsonl"
    planner.write_plan(path, _rows_at(10)[:1])
    path.write_text(path.read_text() + bad + "\n")
    with pytest.raises(PlanError, match=rf"plan\.jsonl: line 2: "):
        planner.read_plan(path)


def test_read_plan_keeps_unknown_keys_through_write(tmp_path):
    import json
    p = tmp_path / "plan.jsonl"
    p.write_text(json.dumps({"seq": 0, "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                             "frames": 441, "run_start": True, "cut_frame": None, "zz": 7}) + "\n")
    rows = planner.read_plan(p)
    planner.write_plan(p, rows)
    assert json.loads(p.read_text())["zz"] == 7


def test_read_plan_still_type_checks_known_fields(tmp_path):
    import json
    p = tmp_path / "plan.jsonl"
    p.write_text(json.dumps({"seq": "0", "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                             "frames": 441, "run_start": True, "cut_frame": None}) + "\n")
    with pytest.raises(PlanError):
        planner.read_plan(p)
