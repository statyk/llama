"""The projection (`scheduler.project`): occurrences in sequence, station IDs
and truthful announcements at the boundaries, exact gap layout."""

import dataclasses
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tests_transmitter.helpers import library_pieces, show_piece
from tests_transmitter.test_scheduler_block import _synthetic
from transmitter import announce, scheduler
from transmitter.announce import ann_id, text_for
from transmitter.clock import IMPLICIT_CLOCK, BlockConfig, ClockConfig, OpenConfig, RotationConfig, occurrences
from transmitter.errors import PlanError
from transmitter.grid import frame_to_us, iso_to_us
from transmitter.history import Recency
from transmitter.layout import PlanRow
from transmitter.pieces import Piece
from transmitter.scheduler import PlannedPiece, SchedulerInput, project, to_row
from transmitter.station import Entry, Show

TZ = "America/New_York"
E = iso_to_us("2026-11-02T05:00:00Z")           # frame 0 = 00:00 local, Monday 2026-11-02
MIN = 60_000_000
DAY = 86_400_000_000
GAP = 87                                         # 2 s of frames


def fr(minutes: float) -> int:
    return round(minutes * 60 * 44_100 / 1024)


def at(frame: int) -> int:
    return E + frame_to_us(frame)


def ld(us: int) -> date:
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=us)).astimezone(ZoneInfo(TZ)).date()


def sp(slug, minutes, artist=None, *, profile="p", date="1980-01-01"):
    return show_piece(slug, artist=artist or slug.upper(), date=date, profile=profile, frames=fr(minutes))


def clip(slug, seconds, role="id", aid=None) -> Piece:
    show = Show(slug, Path("interstitials"), (Entry(f"{slug}.mp3", "clip", "Station ID"),), f"k-{slug}",
                {"role": role, "ann_id": aid, "sizes": {}})
    return Piece("interstitial", show, "interstitials", fr(seconds / 60), True)


def ann(form, x, y, clock, seconds=6.0) -> Piece:
    i = ann_id(text_for(form, x, y, clock.announce))
    return clip(f"ann-{i}", seconds, "ann", i)


def all_anns(clock, seconds=6.0) -> list[Piece]:
    return [clip(f"ann-{n.id}", seconds, "ann", n.id) for n in announce.needed(clock, E - DAY, days=6)]


IDS = [clip("id-a", 8), clip("id-b", 11), clip("id-c", 15)]


def clk(*blocks, exclude=(), wiggle=15, gap_days=45) -> ClockConfig:
    return ClockConfig(timezone=TZ, wiggle_minutes=wiggle, open=OpenConfig(exclude_profiles=list(exclude)),
                       rotation=RotationConfig(concert_gap_days=gap_days),
                       block=[BlockConfig(**b) for b in blocks])


def occ(clock, name, day=0):
    for o in occurrences(clock, E - DAY, E + 10 * DAY):
        if o.block.name == name and o.local_date == date(2026, 11, 2) + timedelta(days=day):
            return o
    raise LookupError(name)


def mk(pool, clock, *, rows=(), start=0, run_start=True, rec=None, seed=7, now_us=None, gap=GAP):
    return SchedulerInput(rows=tuple(rows), start_frame=start, run_start=run_start, pool=list(pool), clock=clock,
                          rec=rec if rec is not None else Recency(), epoch_us=E, gap_frames=gap, seed=seed,
                          now_us=now_us)


def shows_of(pieces, o=None):
    """Show pieces, of one occurrence when `o` is given."""
    return [p for p in pieces if p.role == "show" and (o is None or (p.block, p.nominal_start) == o.key)]


def roles_in(pieces, o):
    return [p.role for p in pieces if (p.block, p.nominal_start) == o.key]


def live(inp: SchedulerInput, until_frame: int) -> list[PlanRow]:
    """The live planner: append project(...)[0] one piece at a time, the history
    growing with each appended piece (as Task 11 rebuilds it from the rows)."""
    rows: list[PlanRow] = list(inp.rows)
    rec, start, rs = inp.rec, inp.start_frame, inp.run_start
    while not rows or rows[-1].end_frame < until_frame:
        pp = project(dataclasses.replace(inp, rows=tuple(rows), rec=rec, start_frame=start, run_start=rs))[0]
        rows.append(to_row(pp, len(rows)))
        rec = rec.with_piece(pp.piece, at(pp.start_frame), ld(at(pp.start_frame)))
        start, rs = pp.end_frame + inp.gap_frames, False
    return rows


# a day of three blocks: two titled profile blocks and a titled open night
DAYCLOCK = clk({"name": "a", "title": "Alpha", "start": "12:00", "profiles": ["p"], "max_shows": 2},
               {"name": "b", "title": "Beta", "start": "18:00", "profiles": ["q"], "max_shows": 2},
               {"name": "c", "title": "Gamma", "start": "23:00"})


def daypool():
    p = [sp(f"p{i}", 178 + i * 0.25, f"P act {i}") for i in range(4)]
    q = [sp(f"q{i}", 148 + i * 0.25, f"Q act {i}", profile="q") for i in range(4)]
    o = [sp(f"o{i}", 128 + i * 0.5, f"O act {i}", profile="o") for i in range(10)]
    return p + q + o


# --- purity and continuation -----------------------------------------------

def test_project_is_pure_and_deterministic():
    pool = daypool() + IDS + all_anns(DAYCLOCK)
    inp = mk(pool, DAYCLOCK, start=fr(12 * 60))
    snapshot = list(inp.pool)
    one, two = project(inp), project(inp)
    assert one == two and one
    assert list(inp.pool) == snapshot and inp.rows == ()
    assert all(isinstance(p, PlannedPiece) for p in one)


def test_first_piece_continues_a_partly_filled_block():
    # b holds one persisted show; with max_shows 2 it may add only one more, though two
    # 75-min shows would land the next block on time: the persisted row counts
    clock = clk({"name": "b", "start": "18:00", "profiles": ["p"], "max_shows": 2},
                {"name": "n", "start": "23:00"})
    x = sp("x150", 150, "X")
    pool = [x] + [sp(f"s{i}", 75, f"S{i}") for i in range(3)] + [clip("id-a", 10)]
    b = occ(clock, "b")
    row = PlanRow(seq=0, slug="x150", dir="x150", key=x.key, start_frame=fr(18 * 60), frames=x.frames,
                  run_start=True, block="b", nominal_start=b.nominal_iso, role="show", miss=False, package="x150")
    rec = Recency().with_piece(x, at(row.start_frame), ld(at(row.start_frame)))
    pieces = project(mk(pool, clock, rows=[row], start=row.end_frame + GAP, run_start=False, rec=rec))
    assert pieces[0].role == "id" and pieces[0].block == "b" and pieces[0].start_frame == row.end_frame + GAP
    added = shows_of(pieces, occ(clock, "b"))
    assert len(added) == 1 and added[0].miss is None and pieces[1] is added[0]
    n_first = shows_of(pieces, occ(clock, "n"))[0]
    assert n_first.miss is True                     # one 75-min show lands n early


def test_a_next_row_last_continues_its_named_occurrence():
    # the last row is b's `next`, laid out so b's first show starts at 17:30, before b's
    # window (early 0): the row names b, so b continues (placed=()) and its start is a miss,
    # although the start lies inside the 12:00 block
    clock = clk({"name": "a", "start": "12:00", "profiles": ["p"]},
                {"name": "b", "title": "Bee", "start": "18:00", "profiles": ["q"], "early_minutes": 0,
                 "late_minutes": 15},
                {"name": "n", "start": "23:00"})
    b = occ(clock, "b")
    nx = ann("next_one", b, None, clock)
    row = PlanRow(seq=0, slug=nx.slug, dir=nx.dir, key=nx.key, start_frame=fr(17 * 60 + 30), frames=nx.frames,
                  run_start=True, kind="interstitial", block="b", nominal_start=b.nominal_iso, role="next",
                  names=(b.key,))
    pool = [sp(f"q{i}", 150, f"Q{i}", profile="q") for i in range(3)] + [sp("p0", 100)] + [nx]
    pieces = project(mk(pool, clock, rows=[row], start=row.end_frame + GAP, run_start=False))
    first = pieces[0]
    assert first.role == "show" and first.block == "b" and first.nominal_start == b.nominal_iso
    assert first.start_frame == row.end_frame + GAP and first.miss is True
    assert len(shows_of(pieces, occ(clock, "b"))) == 2


def test_phase1_prefix_is_extended_mid_block():
    clock = clk({"name": "b", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "n", "start": "18:00"})
    old = sp("old", 60, "Old Band")
    pool = [old, sp("s1", 118, "S1"), sp("s2", 118, "S2"), sp("s3", 60, "S3"), clip("id-a", 10)]
    row = PlanRow(seq=0, slug="old", dir="old", key=old.key, start_frame=fr(13 * 60), frames=old.frames)
    rec = Recency().with_piece(old, at(row.start_frame), ld(at(row.start_frame)))
    pieces = project(mk(pool, clock, rows=[row], start=row.end_frame + GAP, run_start=False, rec=rec))
    b = occ(clock, "b")
    assert pieces[0].role == "id" and (pieces[0].block, pieces[0].nominal_start) == b.key
    bshows = shows_of(pieces, occ(clock, "b"))
    assert sorted(p.piece.slug for p in bshows) == ["s1", "s2"]          # "old" is persisted and unaired
    assert bshows[0].miss is True                                       # 14:00 is outside 12:00's window
    assert shows_of(pieces, occ(clock, "n"))[0].miss is False


def test_a_fresh_start_inside_the_next_window_starts_that_block():
    # 11:50 lies in a's 12:00 window (and in the 00:00 block): a starts now, on time
    clock = clk({"name": "z", "start": "00:00"},
                {"name": "a", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "n", "start": "18:00"})
    pool = daypool() + IDS
    first = project(mk(pool, clock, start=fr(11 * 60 + 50)))[0]
    assert (first.block, first.nominal_start) == occ(clock, "a").key and first.miss is False
    inside = project(mk(pool, clock, start=fr(11 * 60 + 40)))[0]          # before a's window: z
    assert (inside.block, inside.nominal_start) == occ(clock, "z").key


def test_a_run_start_after_an_outage_enters_the_occurrence_in_progress():
    # the last row names yesterday's b; the run restarts today at 14:00 (a run start): the
    # occurrence in progress is today's b, with nothing placed and no boundary piece
    clock = clk({"name": "b", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "n", "start": "18:00"})
    y = occ(clock, "b", -1)
    old = sp("old", 60, "Old Band")
    row = PlanRow(seq=0, slug="old", dir="old", key=old.key, start_frame=fr(-11 * 60), frames=old.frames,
                  run_start=True, block="b", nominal_start=y.nominal_iso, role="show", miss=False)
    pool = [old, sp("s1", 118, "S1"), sp("s2", 118, "S2"), sp("s3", 120, "S3")] + IDS
    pieces = project(mk(pool, clock, rows=[row], start=fr(14 * 60), run_start=True))
    first = pieces[0]
    assert first.role == "show" and first.run_start and first.start_frame == fr(14 * 60)
    assert (first.block, first.nominal_start) == occ(clock, "b").key
    assert len(shows_of(pieces, occ(clock, "b"))) == 2          # placed=(): yesterday's show does not count


def test_gap_layout_for_every_projected_piece():
    pool = daypool() + IDS + all_anns(DAYCLOCK)
    for start, rs in ((fr(12 * 60), True), (fr(12 * 60) + 5, False)):
        pieces = project(mk(pool, DAYCLOCK, start=start, run_start=rs))
        assert pieces[0].start_frame == start and pieces[0].run_start is rs
        assert not any(p.run_start for p in pieces[1:])
        for prev, cur in zip(pieces, pieces[1:]):
            assert cur.start_frame == prev.end_frame + GAP
        assert {p.role for p in pieces} >= {"show", "id", "next", "later"}


REPRO_CLOCK = clk({"name": "dead", "title": "Dead Hour", "start": "12:00", "profiles": ["dead"], "max_shows": 2},
                  {"name": "grass", "title": "Bluegrass", "start": "17:00", "profiles": ["bluegrass"],
                   "max_shows": 2, "wiggle_minutes": 20},
                  {"name": "night", "start": "21:30"})


def test_appending_first_pieces_reproduces_one_projection():
    # exact lengths; ID clips of three different lengths, so the boundary estimate is
    # wrong at most boundaries and the blocks are re-planned from exact starts
    pool = library_pieces() + IDS + all_anns(REPRO_CLOCK, seconds=9)
    rec = Recency()
    for i, p in enumerate(pool[:120:3]):
        when = E - (i + 1) * DAY // 3
        rec = rec.with_piece(p, when, ld(when))
    inp = mk(pool, REPRO_CLOCK, start=fr(12 * 60), rec=rec)
    until = fr(12 * 60) + fr(36 * 60)
    one = project(inp, until_frame=until)
    rows = live(inp, until)
    assert [to_row(pp, i) for i, pp in enumerate(one[:len(rows)])] == rows
    assert {r.role for r in rows} >= {"show", "id", "next", "later"}
    assert len({(r.block, r.nominal_start) for r in rows}) >= 5


# --- station IDs ---------------------------------------------------------------

OPEN = clk({"name": "o", "start": "00:00", "wiggle_minutes": 60})


def test_station_id_between_shows_rotates_least_recent_first():
    pool = [sp(f"s{i}", 120, f"Act {i}") for i in range(14)] + IDS
    rec = Recency().with_piece(IDS[0], E - MIN * 60, ld(E - MIN * 60))        # id-a: an hour ago
    rec = rec.with_piece(IDS[1], E - MIN * 600, ld(E - MIN * 600))            # id-b: ten hours ago
    pieces = project(mk(pool, OPEN, rec=rec))
    ids = [p.piece.slug for p in pieces if p.role == "id"]
    assert ids[:6] == ["id-c", "id-b", "id-a", "id-c", "id-b", "id-a"]
    assert all(p.role in ("show", "id") for p in pieces)
    for prev, cur in zip(pieces, pieces[1:]):
        assert (prev.role == "show") != (cur.role == "show")                  # show, ID, show, ...


def test_boundary_estimate_is_two_gaps_and_the_median_id(monkeypatch):
    seen = []
    orig = scheduler._BlockRun.__init__

    def spy(self, *a, **kw):
        seen.append((kw["boundary_frames"], kw["final_boundary_frames"]))
        orig(self, *a, **kw)

    monkeypatch.setattr(scheduler._BlockRun, "__init__", spy)
    project(mk([sp(f"s{i}", 120, f"Act {i}") for i in range(14)] + IDS, OPEN))
    assert seen and set(seen) == {(2 * GAP + IDS[1].frames,) * 2}


def test_empty_id_pool_boundary_is_one_gap(monkeypatch):
    seen = []
    orig = scheduler._BlockRun.__init__

    def spy(self, *a, **kw):
        seen.append((kw["boundary_frames"], kw["final_boundary_frames"]))
        orig(self, *a, **kw)

    monkeypatch.setattr(scheduler._BlockRun, "__init__", spy)
    pool = daypool() + all_anns(DAYCLOCK)          # announcements but no station ID
    pieces = project(mk(pool, DAYCLOCK, start=fr(12 * 60)))
    assert seen and set(seen) == {(GAP, GAP)}
    assert "next" in {p.role for p in pieces} and "id" not in {p.role for p in pieces}


def test_no_id_clips_means_plain_gaps():
    pool = [sp(f"s{i}", 120, f"Act {i}") for i in range(14)]
    pieces = project(mk(pool, OPEN))
    assert pieces and all(p.role == "show" for p in pieces)
    for prev, cur in zip(pieces, pieces[1:]):
        assert cur.start_frame == prev.end_frame + GAP


# --- announcements -------------------------------------------------------------

def _boundary_into(pieces, o):
    """The interstitial right before occurrence o's first show."""
    i = next(n for n, p in enumerate(pieces) if p.role == "show" and (p.block, p.nominal_start) == o.key)
    return pieces[i - 1]


def test_next_announcement_at_block_start_names_x_and_y():
    b, c, a1 = occ(DAYCLOCK, "b"), occ(DAYCLOCK, "c"), occ(DAYCLOCK, "a", 1)
    # a voiced two-block clip for c (naming tomorrow's a, 13 h on) is never used (R12)
    pool = daypool() + IDS + all_anns(DAYCLOCK) + [ann("next", c, a1, DAYCLOCK)]
    pieces = project(mk(pool, DAYCLOCK, start=fr(12 * 60)))
    into_b = _boundary_into(pieces, b)
    assert into_b.role == "next" and (into_b.block, into_b.nominal_start) == b.key
    assert into_b.names == (b.key, c.key)
    assert into_b.piece.slug == "ann-" + ann_id(text_for("next", b, c, DAYCLOCK.announce))
    # c is followed by a the next day 13 h later: the one-block form (R12)
    into_c = _boundary_into(pieces, c)
    assert into_c.role == "next" and into_c.names == (c.key,)
    assert into_c.piece.slug == "ann-" + ann_id(text_for("next_one", c, None, DAYCLOCK.announce))


def test_later_on_the_last_internal_boundary_only():
    clock = clk({"name": "o", "start": "12:00"},
                {"name": "x", "title": "Ex", "start": "18:00", "profiles": ["p"], "max_shows": 2},
                {"name": "y", "title": "Why", "start": "22:00", "profiles": ["q"], "max_shows": 2})
    pool = ([sp(f"p{i}", 119 + i * 0.1, f"P{i}") for i in range(4)]
            + [sp(f"q{i}", 119 + i * 0.1, f"Q{i}", profile="q") for i in range(4)]
            + [sp(f"r{i}", 119 + i * 0.1, f"R{i}", profile="r") for i in range(4)] + IDS + all_anns(clock))
    pieces = project(mk(pool, clock, start=fr(12 * 60)))
    o, x, y = occ(clock, "o"), occ(clock, "x"), occ(clock, "y")
    assert roles_in(pieces, o) == ["show", "id", "show", "later", "show"]       # three-show open block
    later = next(p for p in pieces if p.role == "later")
    assert later.names == (x.key, y.key) and later.block == "o"
    assert later.piece.slug == "ann-" + ann_id(text_for("later", x, y, clock.announce))
    assert roles_in(pieces, x)[0] == "next"


def _three_show_open_block(x_block, y_block, extra=()):
    clock = clk({"name": "o", "start": "12:00"}, x_block, y_block)
    pool = ([sp(f"p{i}", 119 + i * 0.1, f"P{i}") for i in range(4)]
            + [sp(f"q{i}", 119 + i * 0.1, f"Q{i}", profile="q") for i in range(4)]
            + [sp(f"r{i}", 119 + i * 0.1, f"R{i}", profile="r") for i in range(4)]
            + list(extra) + IDS + all_anns(clock))
    return clock, project(mk(pool, clock, start=fr(12 * 60)))


def test_later_is_only_at_the_last_internal_boundary_even_when_x_is_reachable_earlier():
    # x's 3 h window would accept a start one show early: still an ID at the first boundary
    clock, pieces = _three_show_open_block(
        {"name": "x", "title": "Ex", "start": "18:00", "profiles": ["p"], "max_shows": 2, "wiggle_minutes": 180},
        {"name": "y", "start": "22:00", "profiles": ["q"], "max_shows": 2})
    assert roles_in(pieces, occ(clock, "o")) == ["show", "id", "show", "later", "show"]


def test_later_falls_back_to_one_block_when_y_would_miss():
    # x's only show runs 4 h, so y (2 h after x) starts late: `later_one` names x alone
    clock, pieces = _three_show_open_block(
        {"name": "x", "title": "Ex", "start": "18:00", "profiles": ["qq"], "max_shows": 1},
        {"name": "y", "title": "Why", "start": "20:00", "profiles": ["q"], "max_shows": 2},
        [sp("q240", 240, "Q long", profile="qq")])
    x = occ(clock, "x")
    later = next(p for p in pieces if p.role == "later")
    assert later.block == "o" and later.names == (x.key,)
    assert later.piece.slug == "ann-" + ann_id(text_for("later_one", x, None, clock.announce))
    assert shows_of(pieces, occ(clock, "y"))[0].miss is True


def test_untitled_x_gets_an_id_not_an_announcement():
    clock = clk({"name": "a", "title": "Alpha", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "u", "start": "18:00", "profiles": ["q"], "max_shows": 2},
                {"name": "w", "title": "Dub", "start": "23:00"})
    pieces = project(mk(daypool() + IDS + all_anns(clock), clock, start=fr(12 * 60)))
    a, u = occ(clock, "a"), occ(clock, "u")
    assert roles_in(pieces, a) == ["show", "id", "show"]       # its `later` would name u
    assert _boundary_into(pieces, u).role == "id"


def test_titled_open_block_is_announced():
    clock = clk({"name": "a", "title": "Alpha", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "o", "title": "Open House", "start": "18:00"})
    o = occ(clock, "o")
    extra = [ann("next", o, occ(clock, "a", 1), clock)]          # voiced, but a is 18 h on
    pieces = project(mk(daypool() + IDS + all_anns(clock) + extra, clock, start=fr(12 * 60)))
    nx = _boundary_into(pieces, o)
    assert nx.role == "next" and nx.names == (o.key,)            # a follows 18 h later: one-block


def test_degraded_y_uses_the_one_block_form():
    clock = clk({"name": "a", "title": "Alpha", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "b", "title": "Beta", "start": "18:00", "profiles": ["q"], "max_shows": 2},
                {"name": "c", "title": "Gamma", "start": "23:00", "profiles": ["nobody"]})
    pieces = project(mk(daypool() + IDS + all_anns(clock), clock, start=fr(12 * 60)))
    b, c = occ(clock, "b"), occ(clock, "c")
    nx = _boundary_into(pieces, b)
    assert nx.role == "next" and nx.names == (b.key,)
    assert nx.piece.slug == "ann-" + ann_id(text_for("next_one", b, None, clock.announce))
    assert _boundary_into(pieces, c).role == "id"                 # c itself is degraded: never announced
    assert all(p.degraded for p in shows_of(pieces, occ(clock, "c")))


def test_y_outside_its_window_uses_the_one_block_form():
    clock = clk({"name": "a", "title": "Alpha", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "b", "title": "Beta", "start": "18:00", "profiles": ["q"], "max_shows": 1},
                {"name": "c", "title": "Gamma", "start": "20:00"})
    pool = ([sp(f"p{i}", 178 + i * 0.25, f"P{i}") for i in range(4)]
            + [sp(f"q{i}", 240, f"Q{i}", profile="q") for i in range(2)]
            + [sp(f"o{i}", 120, f"O{i}", profile="o") for i in range(8)] + IDS + all_anns(clock))
    pieces = project(mk(pool, clock, start=fr(12 * 60)))
    b, c = occ(clock, "b"), occ(clock, "c")
    nx = _boundary_into(pieces, b)
    assert nx.role == "next" and nx.names == (b.key,)
    assert shows_of(pieces, occ(clock, "c"))[0].miss is True                  # b's only show runs 4 h


@pytest.mark.parametrize("have", ["one", "none"])
def test_two_block_clip_missing_falls_back_to_one_block_then_id(have):
    b, c = occ(DAYCLOCK, "b"), occ(DAYCLOCK, "c")
    two = ann("next", b, c, DAYCLOCK)
    one = ann("next_one", b, None, DAYCLOCK)
    anns = [p for p in all_anns(DAYCLOCK) if p.slug != two.slug and (have == "one" or p.slug != one.slug)]
    pieces = project(mk(daypool() + IDS + anns, DAYCLOCK, start=fr(12 * 60)))
    into_b = _boundary_into(pieces, b)
    if have == "one":
        assert into_b.role == "next" and into_b.piece.slug == one.slug and into_b.names == (b.key,)
    else:
        assert into_b.role == "id" and into_b.names == ()


def test_announcement_dropped_when_x_would_start_outside_its_window():
    clock = clk({"name": "a", "title": "Alpha", "start": "12:00", "profiles": ["p"], "max_shows": 1},
                {"name": "b", "title": "Beta", "start": "14:00", "profiles": ["q"], "max_shows": 2},
                {"name": "c", "title": "Gamma", "start": "20:00"})
    pool = ([sp("p0", 240, "P0")] + [sp(f"q{i}", 148, f"Q{i}", profile="q") for i in range(4)]
            + [sp(f"o{i}", 120, f"O{i}", profile="o") for i in range(8)] + IDS + all_anns(clock))
    pieces = project(mk(pool, clock, start=fr(12 * 60)))
    b = occ(clock, "b")
    assert _boundary_into(pieces, b).role == "id"
    assert shows_of(pieces, occ(clock, "b"))[0].miss is True


def test_overlapping_windows_resolve_as_a_late_start_and_a_miss():
    clock = clk({"name": "a", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "b", "start": "12:30", "profiles": ["q"], "max_shows": 2},
                {"name": "c", "start": "18:00"})
    pool = [sp("p0", 120, "P0"), sp("q0", 150, "Q0", profile="q"), sp("q1", 150, "Q1", profile="q")]
    pool += [sp(f"o{i}", 100, f"O{i}", profile="o") for i in range(6)] + IDS
    pieces = project(mk(pool, clock, start=fr(12 * 60)))
    a_shows, b_shows = shows_of(pieces, occ(clock, "a")), shows_of(pieces, occ(clock, "b"))
    assert [p.piece.slug for p in a_shows] == ["p0"] and a_shows[0].miss is False
    assert a_shows[0].end_frame == a_shows[0].start_frame + fr(120)        # never cut
    assert b_shows[0].miss is True and b_shows[0].start_frame > a_shows[0].end_frame


# --- pools ---------------------------------------------------------------------

def test_exclude_profiles_bends_when_the_open_pool_is_empty():
    clock = clk({"name": "o", "start": "00:00", "wiggle_minutes": 60}, exclude=["dead"])
    dead = [sp(f"d{i}", 120, f"Dead {i}", profile="dead") for i in range(14)]
    pieces = project(mk(dead + IDS, clock))
    for o_key in {(p.block, p.nominal_start) for p in pieces}:
        rows = [p for p in pieces if p.role == "show" and (p.block, p.nominal_start) == o_key]
        assert [("exclude_profiles" in p.bends) for p in rows] == [True] + [False] * (len(rows) - 1)
    kept = project(mk(dead + [sp("x", 120, "X", profile="funk")] + IDS, clock))
    assert not any("exclude_profiles" in p.bends for p in kept)


def test_plan_error_only_when_no_show_is_eligible():
    with pytest.raises(PlanError, match="no eligible packages to plan"):
        project(mk(IDS, OPEN))
    clock = clk({"name": "b", "start": "00:00", "profiles": ["nobody"]})
    pieces = project(mk([sp("s", 120, "S")] + IDS, clock))
    assert pieces and all(p.degraded for p in shows_of(pieces))


def test_used_holds_persisted_shows_until_they_air():
    # gap 0 (no gap rule) and a 1977 preference: only `used` keeps yesterday's persisted,
    # unaired favourite out of today's block; once its row has aired it returns
    clock = clk({"name": "o", "start": "00:00", "wiggle_minutes": 60,
                 "prefer": [{"years": "1977", "weight": 2.0}]}, gap_days=0)
    fav = sp("fav", 120, "Fav", date="1977-05-08")
    pool = [fav] + [sp(f"s{i}", 120, f"Act {i}") for i in range(14)]
    row = PlanRow(seq=0, slug="fav", dir="fav", key=fav.key, start_frame=-fr(180), frames=fav.frames,
                  run_start=True, block="o", nominal_start=occ(clock, "o", -1).nominal_iso, role="show",
                  miss=False, package="fav")
    rec = Recency().with_piece(fav, at(row.start_frame), ld(at(row.start_frame)))
    base = dict(rows=[row], start=row.end_frame + GAP, run_start=False, rec=rec)

    def today(now_us):
        return {p.piece.slug for p in shows_of(project(mk(pool, clock, now_us=now_us, **base)), occ(clock, "o"))}

    assert "fav" not in today(None)
    assert "fav" not in today(at(row.end_frame) - 1)
    assert "fav" in today(at(row.end_frame))


def test_implicit_clock_never_records_a_miss():
    pieces = project(mk(library_pieces(), IMPLICIT_CLOCK), until_frame=fr(7 * 24 * 60))
    shows = shows_of(pieces)
    assert not any(p.miss for p in shows)
    assert sum(p.miss is False for p in shows) >= 7


# --- horizon -------------------------------------------------------------------

def test_default_horizon_is_the_continuing_occurrence_plus_two():
    pieces = project(mk(daypool() + IDS + all_anns(DAYCLOCK), DAYCLOCK, start=fr(12 * 60)))
    keys = [occ(DAYCLOCK, "a").key, occ(DAYCLOCK, "b").key, occ(DAYCLOCK, "c").key]
    assert list(dict.fromkeys((p.block, p.nominal_start) for p in pieces)) == keys


def test_until_frame_extends_the_horizon():
    pool = daypool() + IDS + all_anns(DAYCLOCK)
    pieces = project(mk(pool, DAYCLOCK, start=fr(12 * 60)), until_frame=fr(24 * 60 + 19 * 60))
    seen = list(dict.fromkeys((p.block, p.nominal_start) for p in pieces))
    # until_frame lies in day 1's b: a, b, c, a', b' and two more
    want = [occ(DAYCLOCK, n, d).key for d, n in ((0, "a"), (0, "b"), (0, "c"), (1, "a"), (1, "b"),
                                                  (1, "c"), (2, "a"))]
    assert seen == want
    assert project(mk(pool, DAYCLOCK, start=fr(12 * 60)), until_frame=fr(13 * 60)) == \
        project(mk(pool, DAYCLOCK, start=fr(12 * 60)))
    assert len(project(mk(pool, DAYCLOCK, start=fr(12 * 60)), ahead=0)) < len(pieces)


# --- rows ----------------------------------------------------------------------

def test_to_row_carries_every_scheduler_field():
    pool = daypool() + IDS + all_anns(DAYCLOCK)
    pieces = project(mk(pool, DAYCLOCK, start=fr(12 * 60)))
    for i, pp in enumerate(pieces):
        r = to_row(pp, 40 + i)
        assert (r.seq, r.slug, r.dir, r.key, r.start_frame, r.frames, r.run_start) == (
            40 + i, pp.piece.slug, pp.piece.dir, pp.piece.key, pp.start_frame, pp.piece.frames, pp.run_start)
        assert (r.kind, r.block, r.nominal_start, r.role, r.miss, r.degraded, r.fill, r.bends, r.names) == (
            pp.piece.kind, pp.block, pp.nominal_start, pp.role, pp.miss, pp.degraded, pp.fill, pp.bends,
            pp.names)
        assert r.package == pp.piece.package and r.end_frame == pp.end_frame
        assert PlanRow.from_json(r.to_json()) == r


def test_fill_rows_carry_the_cause_from_the_block_plan():
    clock = clk({"name": "b", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "n", "start": "18:00"})
    own = [sp(f"s{i}", 60, f"Act {i}") for i in range(5)]
    funk = [sp("f1", 120, "Funk A", profile="funk"), sp("f2", 118, "Funk B", profile="funk"),
            sp("f3", 125, "Funk C", profile="funk"), sp("f4", 60, "Funk D", profile="funk")]
    pieces = project(mk(own + funk, clock, start=fr(12 * 60)))
    rows = shows_of(pieces, occ(clock, "b"))
    assert [p.fill for p in rows][:2] == [None, None]
    assert rows[2:] and all(p.fill == "structural" for p in rows[2:])


def test_block_bends_are_written_once_across_its_rows():
    # a single-artist pool forced twice a day into two Dead blocks: rules bend, and each
    # block's rows carry each rule at most once; their union is the block plan's bends
    clock = clk({"name": "d1", "start": "12:00", "profiles": ["dead"], "max_shows": 2},
                {"name": "d2", "start": "18:00", "profiles": ["dead"], "max_shows": 2},
                {"name": "n", "start": "23:00"})
    pool = [sp(f"gd{i}", 178 + i * 0.1, "Grateful Dead", profile="dead", date=f"1977-0{1 + i % 9}-0{1 + i % 9}")
            for i in range(6)]
    pool += [sp("jg0", 178.5, "Jerry Garcia Band", profile="dead"), sp("o1", 120, "O", profile="o")] + IDS
    pieces = project(mk(pool, clock, start=fr(12 * 60)), until_frame=fr(36 * 60))
    total = []
    for key in dict.fromkeys((p.block, p.nominal_start) for p in pieces):
        bends = [b for p in pieces if p.role == "show" and (p.block, p.nominal_start) == key for b in p.bends]
        assert len(bends) == len(set(bends)), (key, bends)
        total += bends
    assert total                                    # the scenario does bend rules


# --- speed -----------------------------------------------------------------------

def test_project_over_a_3000_piece_pool_is_fast():
    clock = clk({"name": "dead", "title": "Dead", "start": "12:00", "profiles": ["dead"], "max_shows": 2},
                {"name": "funk", "title": "Funk", "start": "17:00", "profiles": ["funk"], "max_shows": 2},
                {"name": "jam", "title": "Jam Night", "start": "21:30"})
    pool = _synthetic(3000) + IDS + all_anns(clock)
    t0 = time.perf_counter()
    pieces = project(mk(pool, clock, start=fr(12 * 60)))
    elapsed = time.perf_counter() - t0
    assert len({(p.block, p.nominal_start) for p in pieces}) == 3
    assert elapsed < 2.0, elapsed


def test_block_bends_match_the_block_plan_and_sit_on_the_show_that_bent_them():
    # A1 aired 10 days ago (a gap violation); B1, B2 share an artist (adjacency, which
    # outranks the gap). The block plays A1 and a B show and bends "gap", once, on A1's row.
    clock = clk({"name": "b", "start": "12:00", "profiles": ["p"], "max_shows": 2},
                {"name": "n", "start": "16:00"})
    a1, b1, b2 = sp("a1", 119, "A"), sp("b1", 119.5, "B"), sp("b2", 119.7, "B")
    pool = [a1, b1, b2] + [sp(f"o{i}", 100, f"O{i}", profile="o") for i in range(6)]
    rec = Recency().with_piece(a1, E - 10 * DAY, ld(E - 10 * DAY))
    pieces = project(mk(pool, clock, start=fr(12 * 60), rec=rec))
    b, n = occ(clock, "b"), occ(clock, "n")
    plan = scheduler.fill_block(b, n, start_frame=fr(12 * 60), placed=(), own_pool=[a1, b1, b2], open_pool=pool,
                                boundary_frames=GAP, final_boundary_frames=GAP, prev_artist=None, rec=rec,
                                clock=clock, epoch_us=E, seed=7, used=frozenset())
    assert plan.bends == ("gap",)
    rows = shows_of(pieces, b)
    assert [p.piece for p in rows] == list(plan.shows)
    assert [p.bends for p in rows] == [("gap",) if p.piece.slug == "a1" else () for p in rows]
