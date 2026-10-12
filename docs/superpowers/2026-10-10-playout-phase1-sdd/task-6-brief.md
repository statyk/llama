### Task 6: Trivial planner

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/planner.py`
- Create: `packages/transmitter/tests_transmitter/test_planner.py`

**Interfaces:**
- Consumes: `layout.PlanRow`, `layout.validate_rows`, `station.Show`, `workspace.atomic_write_text`, `errors.PlanError/TransmitterError`, `grid.SEGMENT_FRAMES`.
- Produces:
  - `shuffle_rank(seed, slug) -> str`.
  - `choose_next(eligible, last_seq: Mapping[str, int], seed, previous: str | None) -> Show` — least-recently planned first (never planned before all), ties by the seeded rank; never the same show twice in a row when an alternative exists.
  - `extend(rows, eligible, *, frames_of: Callable[[Show], int], seed, gap_frames, until_frame, start_frame, run_start, max_new=None, on_skip=lambda show, exc: None) -> list[PlanRow]` — returns `rows` plus appended rows; the first appended row starts at `start_frame` (flagged `run_start` if asked), each later one at `prev.end_frame + gap_frames`; stops once the last row ends at/after `until_frame` or after `max_new` rows; a show whose `frames_of` raises `TransmitterError` is skipped (reported through `on_skip`).
  - `next_start(rows, gap_frames) -> int`; `replan_from(rows, index) -> tuple[list[PlanRow], int, bool]` (`(kept, start_frame, run_start)`); `cut_for_recovery(rows, published_last) -> list[PlanRow]`; `current_run_start(rows) -> int | None` (segment index); `publish_next(rows, last) -> int | None`.
  - `read_plan(path) -> list[PlanRow]`; `write_plan(path, rows)`.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_planner.py`:

```python
from pathlib import Path

import pytest

from transmitter import planner
from transmitter.errors import PlanError, RenderError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.layout import PlanRow
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_planner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.planner'`.

- [ ] **Step 3: Implement `planner.py`**

```python
"""Phase-1 trivial planner (spec "Scheduler": "Phase 1 replaces all of this
with a trivial planner: eligible packages in a fixed shuffled order, back to
back with the inter-show gap").

The order is a seeded hash rank, so adding or removing a package never
reshuffles the others; selection is least-recently-planned first, which walks
that order as a cycle and lets a newly eligible show air once soon and then
fall in line. Phase 3's scheduler replaces `choose_next`/`extend`; the plan
file, recovery cut and re-plan rules stay.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from transmitter.errors import PlanError, TransmitterError
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import PlanRow, validate_rows
from transmitter.station import Show
from transmitter.workspace import atomic_write_text


def shuffle_rank(seed: int, slug: str) -> str:
    return hashlib.sha256(f"{seed}:{slug}".encode()).hexdigest()


def choose_next(eligible: Sequence[Show], last_seq: Mapping[str, int], seed: int,
                previous: str | None) -> Show:
    if not eligible:
        raise PlanError("no eligible packages to plan")
    ordered = sorted(eligible, key=lambda s: (last_seq.get(s.slug, -1), shuffle_rank(seed, s.slug)))
    if ordered[0].slug == previous and len(ordered) > 1:
        return ordered[1]
    return ordered[0]


def extend(rows: Sequence[PlanRow], eligible: Sequence[Show], *, frames_of: Callable[[Show], int],
           seed: int, gap_frames: int, until_frame: int, start_frame: int, run_start: bool,
           max_new: int | None = None,
           on_skip: Callable[[Show, Exception], None] = lambda show, exc: None) -> list[PlanRow]:
    out = list(rows)
    last_seq = {r.slug: r.seq for r in out}
    next_seq = max((r.seq for r in out), default=-1) + 1
    pool = list(eligible)
    previous = out[-1].slug if out else None
    start, mark, added = start_frame, run_start, 0
    while (not out or out[-1].end_frame < until_frame) and (max_new is None or added < max_new):
        chosen = choose_next(pool, last_seq, seed, previous)
        try:
            frames = frames_of(chosen)
        except TransmitterError as exc:
            on_skip(chosen, exc)
            pool = [s for s in pool if s.slug != chosen.slug]
            continue
        row = PlanRow(seq=next_seq, slug=chosen.slug, dir=chosen.dir.name, key=chosen.key,
                      start_frame=start, frames=frames, run_start=mark)
        out.append(row)
        last_seq[chosen.slug] = next_seq
        next_seq += 1
        added += 1
        previous = chosen.slug
        start, mark = row.end_frame + gap_frames, False
    validate_rows(out)
    return out


def next_start(rows: Sequence[PlanRow], gap_frames: int) -> int:
    return rows[-1].end_frame + gap_frames


def replan_from(rows: Sequence[PlanRow], index: int) -> tuple[list[PlanRow], int, bool]:
    """Skip rows[index] at its boundary: keep everything before it and re-plan
    from its start frame (spec "Frozen means rendered")."""
    return list(rows[:index]), rows[index].start_frame, rows[index].run_start


def cut_for_recovery(rows: Sequence[PlanRow], published_last: int | None) -> list[PlanRow]:
    """After an outage longer than the lead: keep the rows that began before
    the first unpublished segment, cut the one spanning it there, drop the rest."""
    if published_last is None:
        return []
    boundary = (published_last + 1) * SEGMENT_FRAMES
    kept: list[PlanRow] = []
    for r in rows:
        if r.start_frame >= boundary:
            break
        if r.end_frame > boundary:
            r = replace(r, cut_frame=boundary)
        kept.append(r)
    return kept


def current_run_start(rows: Sequence[PlanRow]) -> int | None:
    for r in reversed(rows):
        if r.run_start:
            return r.start_frame // SEGMENT_FRAMES
    return None


def publish_next(rows: Sequence[PlanRow], last: int | None) -> int | None:
    """The next segment to render/publish: continue the current run, or start
    the run if what was published belongs to an older one."""
    rs = current_run_start(rows)
    if rs is None:
        return None
    if last is not None and last + 1 >= rs:
        return last + 1
    return rs


def read_plan(path: Path) -> list[PlanRow]:
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return []
    rows = [PlanRow.from_json(json.loads(line)) for line in text.splitlines() if line.strip()]
    validate_rows(rows)
    return rows


def write_plan(path: Path, rows: Sequence[PlanRow]) -> None:
    validate_rows(rows)
    atomic_write_text(path, "".join(json.dumps(r.to_json(), sort_keys=True) + "\n" for r in rows))
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_planner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): trivial planner with recovery cut and re-plan"
```

---

