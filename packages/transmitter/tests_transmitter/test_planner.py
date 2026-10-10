from pathlib import Path

import pytest

from transmitter import planner
from transmitter.errors import PlanError, RenderError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.station import Show


def show(slug):
    return Show(slug, Path("/station") / slug, (), f"key-{slug}", {})


SHOWS = [show(s) for s in ("alpha", "bravo", "charlie", "delta")]


def ext(rows, eligible=SHOWS, **kw):
    args = dict(frames_of=lambda s: 1000, seed=7, gap_frames=87, until_frame=10_000,
                start_frame=0, run_start=True)
    args.update(kw)
    return planner.extend(rows, eligible, **args)


def test_shuffle_rank_is_stable_and_seeded():
    assert planner.shuffle_rank(7, "alpha") == planner.shuffle_rank(7, "alpha")
    assert planner.shuffle_rank(7, "alpha") != planner.shuffle_rank(8, "alpha")


def test_order_is_the_seeded_shuffle_and_independent_of_the_set():
    order = [r.slug for r in ext([], until_frame=4 * 1087 - 87)]       # exactly four 1000-frame shows
    expected = sorted(["alpha", "bravo", "charlie", "delta"], key=lambda s: planner.shuffle_rank(7, s))
    assert order == expected
    # adding a package does not reorder the others
    more = [r.slug for r in ext([], SHOWS + [show("echo")], until_frame=5 * 1087 - 87)]
    assert [s for s in more if s != "echo"] == expected


def test_rows_are_back_to_back_with_the_gap_and_cover_until():
    rows = ext([], until_frame=5_000)
    assert rows[0].start_frame == 0 and rows[0].run_start
    for a, b in zip(rows, rows[1:]):
        assert b.start_frame == a.end_frame + 87 and not b.run_start
    assert rows[-1].end_frame >= 5_000 and rows[-2].end_frame < 5_000
    assert [r.seq for r in rows] == list(range(len(rows)))


def test_least_recently_planned_first_so_a_new_show_airs_once_then_falls_in_line():
    rows = ext([], until_frame=8 * 1087 - 87)            # exactly two cycles of four
    rows = ext(rows, SHOWS + [show("echo")], until_frame=rows[-1].end_frame + 3 * 1087,
               start_frame=planner.next_start(rows, 87), run_start=False)
    tail = [r.slug for r in rows[8:]]
    assert tail[0] == "echo" and tail.count("echo") == 1


def test_no_immediate_repeat_unless_alone():
    rows = ext([], [show("solo")], until_frame=3_000)
    assert [r.slug for r in rows] == ["solo", "solo", "solo"]
    two = ext([], SHOWS[:2], until_frame=6_000)
    assert all(a.slug != b.slug for a, b in zip(two, two[1:]))


def test_max_new_limits_growth():
    assert len(ext([], until_frame=100_000, max_new=1)) == 1


def test_a_show_that_cannot_be_measured_is_skipped():
    skipped = []

    def frames_of(s):
        if s.slug == "bravo":
            raise RenderError("bad mp3")
        return 1000

    rows = ext([], frames_of=frames_of, until_frame=6_000, on_skip=lambda s, e: skipped.append(s.slug))
    assert "bravo" not in {r.slug for r in rows} and skipped == ["bravo"]


def test_nothing_eligible_is_a_plan_error_only_when_planning_is_needed():
    with pytest.raises(PlanError):
        ext([], [])
    covered = ext([], until_frame=500)
    assert ext(covered, [], until_frame=500, start_frame=planner.next_start(covered, 87),
               run_start=False) == covered


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
