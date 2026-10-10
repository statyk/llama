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
