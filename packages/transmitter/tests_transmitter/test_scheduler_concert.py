"""Concert breaks in the projection (`SchedulerInput.concert`): the scheduler
proposes an assembled "coming up next" break naming X[, Y][, Z] at each
boundary, or falls to today's logic (the last rung)."""

import dataclasses
import json
from pathlib import Path

import pytest

from tests_transmitter.helpers import library_pieces, show_piece
from tests_transmitter.test_scheduler import (
    DAY, DAYCLOCK, E, GAP, IDS, REPRO_CLOCK, all_anns, at, clip, clk, daypool, fr, ld, live, mk, occ, shows_of)
from transmitter import concert, promises, scheduler
from transmitter.clock import occurrences
from transmitter.concert import piece_id
from transmitter.history import Recency
from transmitter.layout import CONCERT_ROLE, PlanRow
from transmitter.scheduler import project, to_row

GOLDEN = Path(__file__).parent / "fixtures" / "concert_off_golden.jsonl"
ID_TEXT = "You are listening to LMA Radio."
TYP = fr(18 / 60)                                 # the typical assembled clip: 18 s


def tclock(*, ov_title="Overnight Variety", tm_title="The Music Never Stopped", ov_profiles=("p",),
           tm_profiles=("d",)):
    """pre (untitled, 19:00) -> Overnight Variety (22:00, two shows) -> The Music
    Never Stopped (02:00, one show) -> day (untitled open, 06:00)."""
    return clk({"name": "pre", "start": "19:00", "profiles": ["e"], "max_shows": 1},
               {"name": "ov", "title": ov_title, "start": "22:00", "profiles": list(ov_profiles), "max_shows": 2},
               {"name": "tmns", "title": tm_title, "start": "02:00", "profiles": list(tm_profiles),
                "max_shows": 1},
               {"name": "day", "start": "06:00"})


TCLOCK = tclock()


def tpool(*, x_artist="Cracker", y_artist="Ryan Adams", x_min=115, y_min=116, with_d=True):
    pool = [sp_("pre", 178, "Pre Act", "e"), sp_("cracker", x_min, x_artist, "p"),
            sp_("ryanadams", y_min, y_artist, "p")]
    if with_d:
        pool.append(sp_("dso", 235, "Dark Star Orchestra", "d"))
    return pool + IDS


def sp_(slug, minutes, artist, profile):
    return show_piece(slug, artist=artist, date="1980-01-01", profile=profile, frames=fr(minutes))


def present_all(clock, pool):
    return frozenset(n.id for n in concert.needed_pieces(
        clock, [p.artist for p in pool if p.kind == "show"], ID_TEXT, E - DAY, days=10))


def cin(clock, pool, *, drop=(), **kw):
    present = present_all(clock, pool) - {piece_id(t) for t in drop}
    return concert.ConcertInput(present=present, id_text=ID_TEXT, typical_frames=TYP, **kw)


def mkc(pool, clock, ci, *, seed=1, **kw):
    # seed 1: the tie rank plays cracker before ryanadams in Overnight Variety
    return dataclasses.replace(mk(pool, clock, seed=seed, **kw), concert=ci)


def start_inp(pool=None, clock=TCLOCK, **ckw):
    pool = tpool() if pool is None else pool
    return mkc(pool, clock, cin(clock, pool, **ckw), start=fr(19 * 60))


def after_first(inp):
    """`inp` continued after its first projected piece (persisted)."""
    pp = project(inp)[0]
    return dataclasses.replace(inp, rows=(to_row(pp, 0),), start_frame=pp.end_frame + inp.gap_frames,
                               run_start=False,
                               rec=inp.rec.with_piece(pp.piece, at(pp.start_frame), ld(at(pp.start_frame))))


def breaks(pieces):
    return [p for p in pieces if p.role == CONCERT_ROLE]


def texts(pp):
    return [t for _, t in pp.concert.pieces]


def show_named(pieces, slug):
    return next(p for p in pieces if p.role == "show" and p.piece.slug == slug)


THEN = "Then, at 2 Eastern, The Music Never Stopped"


# --- feature off -----------------------------------------------------------------

def test_concert_off_is_today():
    inp = mk(daypool() + IDS + all_anns(DAYCLOCK), DAYCLOCK, start=fr(12 * 60))
    pieces = project(inp, until_frame=fr(3 * 24 * 60))
    got = [json.dumps(to_row(pp, i).to_json(), sort_keys=True) for i, pp in enumerate(pieces)]
    assert got == GOLDEN.read_text().splitlines()


# --- the full break and its phrases --------------------------------------------------

def test_full_break_names_x_y_z_with_the_spec_wording():
    pieces = project(start_inp())
    assert [p.piece.slug for p in shows_of(pieces)] == ["pre", "cracker", "ryanadams", "dso"]
    b = breaks(pieces)[0]
    y = show_named(pieces, "ryanadams")
    tm = occ(TCLOCK, "tmns", 1)
    want = [ID_TEXT, "Coming up next, Overnight Variety", "with Cracker,", "followed by Ryan Adams,",
            concert.time_phrase(at(y.start_frame)), THEN, "with Dark Star Orchestra."]
    assert texts(b) == want
    assert [i for i, _ in b.concert.pieces] == [piece_id(t) for t in want]
    assert b.concert.named == ("cracker", "ryanadams", "dso")
    assert b.concert.entries == (("cracker", occ(TCLOCK, "ov").key), ("ryanadams", occ(TCLOCK, "ov").key),
                                 ("dso", tm.key))
    assert b.concert.names == (tm.key,) and b.names == (tm.key,)
    assert b.concert.phrases == ("id", "next", "x", "followed", "then")
    assert b.concert.y_time_id == piece_id(concert.time_phrase(at(y.start_frame)))
    assert b.role == "concert" and (b.block, b.nominal_start) == occ(TCLOCK, "ov").key
    assert b.piece.slug == scheduler.PLACEHOLDER_SLUG and b.piece.kind == "interstitial"
    assert b.piece.role == "concert" and b.piece.frames == TYP and not b.piece.exact
    x = show_named(pieces, "cracker")
    assert pieces[pieces.index(b) + 1] is x and x.start_frame == b.end_frame + GAP


def test_continuing_x_uses_the_continues_piece():
    pieces = project(start_inp())
    b = breaks(pieces)[1]
    assert pieces[pieces.index(b) + 1].piece.slug == "ryanadams"
    assert texts(b) == [ID_TEXT, "Overnight Variety continues", "with Ryan Adams.", THEN,
                        "with Dark Star Orchestra."]
    assert b.concert.named == ("ryanadams", "dso")
    assert (b.block, b.nominal_start) == occ(TCLOCK, "ov").key


def test_same_artist_after_cleaning_suppresses_followed():
    pieces = project(start_inp(tpool(x_artist="Grateful Dead", y_artist="Grateful  Dead ")))
    b = breaks(pieces)[0]
    assert texts(b) == [ID_TEXT, "Coming up next, Overnight Variety", "with Grateful Dead.", THEN,
                        "with Dark Star Orchestra."]
    assert b.concert.named == ("cracker", "ryanadams", "dso")
    assert b.concert.phrases == ("id", "next", "x", "then") and b.concert.y_time_id is None


@pytest.mark.parametrize("drop", [("followed by Ryan Adams,",), ("with Cracker,",), concert.ALL_TIME_PHRASES])
def test_followed_dropped_for_a_missing_piece_unnames_y_and_blocks_then(drop):
    pieces = project(start_inp(drop=drop))
    b = breaks(pieces)[0]
    assert texts(b) == [ID_TEXT, "Coming up next, Overnight Variety", "with Cracker."]
    assert b.concert.named == ("cracker",) and b.concert.names == () and b.names == ()
    assert b.concert.phrases == ("id", "next", "x") and b.concert.y_time_id is None


def test_followed_needs_a_y_artist():
    pieces = project(start_inp(tpool(y_artist="  ")))
    b = breaks(pieces)[0]
    assert texts(b) == [ID_TEXT, "Coming up next, Overnight Variety", "with Cracker."]
    assert b.concert.named == ("cracker",)


def _single_open_block():
    clock = clk({"name": "ov", "title": "Overnight Variety", "start": "22:00"})
    pool = [sp_(f"s{i}", 120 + i, f"Act {i}", "o") for i in range(14)] + IDS
    return clock, pool, fr(22 * 60)


THEN_FAILS = {
    "same-block": _single_open_block,
    "untitled": lambda: (tclock(tm_title=None), tpool(), fr(19 * 60)),
    "blank-title": lambda: (tclock(tm_title="   "), tpool(), fr(19 * 60)),
    "degraded": lambda: (TCLOCK, tpool(with_d=False), fr(19 * 60)),
    "outside-window": lambda: (TCLOCK, tpool(x_min=150, y_min=150), fr(19 * 60)),
    "then-piece-missing": lambda: (TCLOCK, tpool(), fr(19 * 60)),
}


@pytest.mark.parametrize("case", sorted(THEN_FAILS))
def test_then_needs_a_different_titled_undegraded_block_in_its_window(case):
    clock, pool, start = THEN_FAILS[case]()
    drop = (THEN,) if case == "then-piece-missing" else ()
    pieces = project(mkc(pool, clock, cin(clock, pool, drop=drop), start=start))
    bs = breaks(pieces)
    assert bs
    for b in bs:
        assert "then" not in b.concert.phrases and b.concert.names == () and b.names == ()
    # non-vacuous: some break's last named show is the last show of its occurrence
    shows = shows_of(pieces)

    def last_of_occ(slug):
        i = next(j for j, p in enumerate(shows) if p.piece.slug == slug)
        return i + 1 < len(shows) and (shows[i + 1].block, shows[i + 1].nominal_start) != (
            shows[i].block, shows[i].nominal_start)
    assert any(last_of_occ(b.concert.named[-1]) for b in bs if b.concert.named[-1] != "dso")


@pytest.mark.parametrize("variant", ["pieces-missing", "no-artist", "end-piece-missing"])
def test_missing_x_artist_ends_after_the_block_piece(variant):
    pool = tpool(x_artist=None if variant == "no-artist" else "Cracker")
    drop = ("with Cracker,", "with Cracker.")
    if variant == "end-piece-missing":
        drop += ("Coming up next, Overnight Variety.",)
    pieces = project(start_inp(pool, drop=drop))
    b = breaks(pieces)[0]
    end = "Coming up next, Overnight Variety" + ("" if variant == "end-piece-missing" else ".")
    assert texts(b) == [ID_TEXT, end]
    assert b.concert.named == ("cracker",) and b.concert.names == ()
    assert b.concert.phrases == ("id", "next")


def test_missing_id_piece_is_left_out():
    pieces = project(start_inp(drop=(ID_TEXT,)))
    b = breaks(pieces)[0]
    assert texts(b)[0] == "Coming up next, Overnight Variety"
    assert b.concert.phrases == ("next", "x", "followed", "then")


@pytest.mark.parametrize("case", ["untitled", "blank-title", "degraded"])
def test_untitled_or_degraded_x_is_todays_logic(case):
    clock = {"untitled": tclock(ov_title=None), "blank-title": tclock(ov_title="  "),
             "degraded": tclock(ov_profiles=("nobody",))}[case]
    pool = tpool()
    pieces = project(mkc(pool, clock, cin(clock, pool), start=fr(19 * 60)))
    ov = occ(clock, "ov")
    assert not [b for b in breaks(pieces) if (b.block, b.nominal_start) == ov.key]
    into_ov = pieces[1]
    assert into_ov.role == "id" and (into_ov.block, into_ov.nominal_start) == ov.key


def test_missing_block_piece_is_todays_logic():
    pieces = project(start_inp(drop=("Coming up next, Overnight Variety",)))
    assert pieces[1].role == "id" and pieces[2].piece.slug == "cracker"
    b = breaks(pieces)[0]                                   # the continuing break is still assembled
    assert texts(b)[1] == "Overnight Variety continues"


def test_no_assembly_at_the_start_is_todays_logic():
    inp = after_first(start_inp())
    s = inp.start_frame
    inp = dataclasses.replace(inp, concert=dataclasses.replace(inp.concert, no_assembly_at=frozenset({s})))
    pieces = project(inp)
    assert pieces[0].role == "id" and pieces[0].start_frame == s
    assert breaks(pieces) and breaks(pieces)[0].start_frame > s


@pytest.mark.parametrize("x_min", [100, 107, 115])
def test_y_time_phrase_comes_from_ys_predicted_start(x_min):
    pieces = project(start_inp(tpool(x_min=x_min)))
    b = breaks(pieces)[0]
    y = show_named(pieces, "ryanadams")
    phrase = concert.time_phrase(at(y.start_frame))
    assert phrase in texts(b) and b.concert.y_time_id == piece_id(phrase)


def test_y_time_phrases_differ_across_x_lengths():
    got = {concert.time_phrase(at(show_named(project(start_inp(tpool(x_min=m))), "ryanadams").start_frame))
           for m in (100, 115)}
    assert len(got) == 2


# --- entering vs continuing, judged with the concert clip's own length ------------

ENTER_CLOCK = clk({"name": "a", "title": "Alpha", "start": "00:00", "wiggle_minutes": 5},
                 {"name": "b", "title": "Beta", "start": "06:00", "wiggle_minutes": 5})


def prefix_inp(inp, pieces, i):
    """`inp` with `pieces[:i]` persisted, so piece [0] is decided at `pieces[i].start_frame`."""
    rec = inp.rec
    for p in pieces[:i]:
        rec = rec.with_piece(p.piece, at(p.start_frame), ld(at(p.start_frame)))
    return dataclasses.replace(inp, rows=tuple(to_row(p, j) for j, p in enumerate(pieces[:i])),
                               start_frame=pieces[i].start_frame, run_start=False, rec=rec)


def first_divergence(inp, today_ci):
    """The first concert break of `project(inp)` at which today's logic, deciding at the
    same frame with the same rows, names another occurrence: (today's piece, the break).
    Both are decided with the earlier breaks' promises taken away, so that the clip
    length alone decides (a live promise would fix X for both)."""
    pieces = project(inp)
    for i, b in enumerate(pieces):
        if b.role != CONCERT_ROLE:
            continue
        base = strip(prefix_inp(inp, pieces, i))
        b0 = project(base)[0]
        t0 = project(dataclasses.replace(base, concert=today_ci))[0]
        if b0.role == CONCERT_ROLE and (t0.block, t0.nominal_start) != (b0.block, b0.nominal_start):
            return pieces, t0, b0
    return pieces, None, None


# Found by scanning the start frame (fourteen 30-min shows, block "b" at 06:00 +-5 min):
# where ending block "a" now (early) and one more show (late) miss "b" by about the
# same distance, the clip length decides. With a 1 s station ID today's logic plays one
# more show in "a"; the 18 s concert clip makes X open "b" ("enters"). With a 60 s ID
# the reverse (today enters "b", the concert break continues "a").
ENTER_CASES = {                                   # case -> (ID seconds, start segments after 04:00)
    "concert-enters": (1, 81),
    "concert-continues": (60, 77),
}


@pytest.mark.parametrize("case", sorted(ENTER_CASES))
def test_concert_length_decides_entering_and_the_row_carries_xs_occurrence(case):
    id_seconds, n = ENTER_CASES[case]
    pool = [sp_(f"s{i}", 30, f"Act {i}", "o") for i in range(14)] + [clip("id-x", id_seconds)]
    inp = mkc(pool, ENTER_CLOCK, cin(ENTER_CLOCK, pool), start=fr(4 * 60) + 441 * n)
    pieces, t0, b = first_divergence(inp, cin(ENTER_CLOCK, pool, drop=_block_pieces(ENTER_CLOCK)))
    assert b is not None and t0.role == "id" and t0.start_frame == b.start_frame
    entering = b.concert.pieces[1][1].startswith("Coming up next")
    assert entering == (case == "concert-enters")
    assert (t0.block, b.block) == (("a", "b") if entering else ("b", "a"))
    for c in breaks(pieces):                     # every break: its X follows in its occurrence
        x = pieces[pieces.index(c) + 1]
        assert x.role == "show" and x.piece.slug == c.concert.named[0]
        assert (x.block, x.nominal_start) == (c.block, c.nominal_start) == c.concert.entries[0][1]


def _block_pieces(clock):
    out = []
    for blk in clock.block:
        title = concert.title_of(blk)
        if title:
            out += [concert.next_text(title), concert.next_end_text(title), concert.continues_text(title),
                    concert.continues_end_text(title)]
    return tuple(out)


def test_a_concert_target_past_the_horizon_stops_the_projection():
    # from Monday's "b" (23:00) the horizon with ahead=1 is Tuesday's "a"; at its tipped last
    # boundary (found by scanning the show length) today's logic stays in "a", the concert
    # clip would open Tuesday's "b": one occurrence past the horizon, so the projection stops
    pool = [sp_(f"s{i}", 29 + 105 / 60, f"Act {i}", "o") for i in range(14)] + [clip("id-x", 1)]
    inp = mkc(pool, ENTER_CLOCK, cin(ENTER_CLOCK, pool), start=fr(23 * 60))
    _, t0, b = first_divergence(inp, cin(ENTER_CLOCK, pool, drop=_block_pieces(ENTER_CLOCK)))
    assert b is not None and (t0.block, b.block) == ("a", "b") and b.start_frame > fr(24 * 60)
    pieces = project(inp, ahead=1)
    assert pieces[-1].role == "show" and pieces[-1].block == "a"
    assert pieces[-1].end_frame + GAP == b.start_frame
    assert not [p for p in pieces if p.block == "b" and p.start_frame > fr(24 * 60)]


@pytest.mark.parametrize("ahead", [1, 2, 3])
def test_no_piece_past_the_horizon(ahead):
    for inp in (start_inp(), after_first(start_inp())):
        pieces = project(inp, ahead=ahead)
        first = (pieces[0].block, pieces[0].nominal_start)
        seq = [o.key for o in sorted(occurrences(TCLOCK, at(inp.start_frame) - DAY, at(inp.start_frame) + 5 * DAY),
                                     key=lambda o: o.nominal_us)]
        lo = seq.index(first)
        assert all(seq.index((p.block, p.nominal_start)) <= lo + ahead for p in pieces)


# --- Then never repeats a named show -------------------------------------------------

def test_then_never_names_a_show_already_named():
    clock = clk({"name": "ov", "title": "Overnight Variety", "start": "22:00", "profiles": ["p"], "max_shows": 1},
                {"name": "tm", "title": "The Music Never Stopped", "start": "02:00", "max_shows": 1},
                {"name": "pre", "start": "06:00"})
    for extra in ([], [sp_("other", 230, "Other Act", "o")]):
        pool = [sp_("cracker", 235, "Cracker", "p")] + extra + IDS
        pieces = project(mkc(pool, clock, cin(clock, pool), start=fr(22 * 60) - fr(240)), ahead=3)
        bs = breaks(pieces)
        assert bs
        for b in bs:
            assert len(set(b.concert.named)) == len(b.concert.named)
        if extra:
            assert any("then" in b.concert.phrases for b in bs)


# --- the clip length, the boundary estimate, rows ----------------------------------------

def test_first_break_sets_the_length_of_piece_zero_only():
    inp = after_first(start_inp())
    fb = clip("concert-abc", 25, role="concert")
    inp = dataclasses.replace(inp, concert=dataclasses.replace(inp.concert, first_break=fb))
    pieces = project(inp)
    assert pieces[0].piece is fb and pieces[0].role == CONCERT_ROLE
    assert pieces[1].start_frame == inp.start_frame + fb.frames + GAP
    later = breaks(pieces)[1:]
    assert later and all(b.piece.slug == scheduler.PLACEHOLDER_SLUG and b.piece.frames == TYP for b in later)


def test_first_break_is_ignored_when_piece_zero_is_a_show():
    inp = start_inp()
    fb = clip("concert-abc", 25, role="concert")
    pieces = project(dataclasses.replace(inp, concert=dataclasses.replace(inp.concert, first_break=fb)))
    assert pieces[0].role == "show"
    assert all(b.piece.slug == scheduler.PLACEHOLDER_SLUG for b in breaks(pieces))


def test_boundary_estimate_uses_the_typical_assembled_length(monkeypatch):
    seen = []
    orig = scheduler._BlockRun.__init__

    def spy(self, *a, **kw):
        seen.append((kw["boundary_frames"], kw["final_boundary_frames"]))
        orig(self, *a, **kw)

    monkeypatch.setattr(scheduler._BlockRun, "__init__", spy)
    project(start_inp())
    assert seen and set(seen) == {(2 * GAP + TYP,) * 2}
    seen.clear()
    pool = [p for p in tpool() if p.kind == "show"]                 # no ID pool at all
    project(mkc(pool, TCLOCK, cin(TCLOCK, pool), start=fr(19 * 60)))
    assert seen and set(seen) == {(2 * GAP + TYP,) * 2}


def test_same_shape_ignores_a_y_bucket_only_difference():
    t1, t2 = piece_id("around quarter past 11 Eastern."), piece_id("around half past 11 Eastern.")
    ov = ("ov", "2026-11-03T03:00:00.000Z")
    tm = ("tmns", "2026-11-03T07:00:00.000Z")
    a = concert.BreakContent(
        pieces=(("i", ID_TEXT), ("n", "Coming up next, Overnight Variety"), ("w", "with Cracker,"),
                ("f", "followed by Ryan Adams,"), (t1, "around quarter past 11 Eastern."), ("t", THEN),
                ("z", "with Dark Star Orchestra.")),
        entries=(("cracker", ov), ("ryanadams", ov), ("dso", tm)), names=(tm,),
        phrases=("id", "next", "x", "followed", "then"), y_time_id=t1)
    b = dataclasses.replace(a, pieces=a.pieces[:4] + ((t2, "around half past 11 Eastern."),) + a.pieces[5:],
                            y_time_id=t2)
    assert a.same_shape(b) and a != b
    assert not a.same_shape(dataclasses.replace(a, entries=a.entries[:2]))
    assert not a.same_shape(dataclasses.replace(a, names=()))
    assert not a.same_shape(dataclasses.replace(a, phrases=a.phrases[1:]))
    assert a.named == ("cracker", "ryanadams", "dso")


def test_to_row_writes_the_concert_fields():
    pieces = project(start_inp())
    for i, b in enumerate(breaks(pieces)):
        r = to_row(b, 30 + i)
        assert (r.kind, r.role, r.slug, r.frames) == ("interstitial", CONCERT_ROLE, b.piece.slug, b.piece.frames)
        assert r.named_shows == b.concert.named
        assert r.piece_ids == tuple(pid for pid, _ in b.concert.pieces)
        assert r.names == b.concert.names
        assert (r.block, r.nominal_start) == (b.block, b.nominal_start)
        assert PlanRow.from_json(r.to_json()) == r
        assert promises.entries_of(r) == b.concert.entries       # well formed for Task 10's promises
    rows = [to_row(p, i) for i, p in enumerate(pieces) if p.role != CONCERT_ROLE]
    assert all(r.named_shows == () and r.piece_ids == () for r in rows)


def test_concert_rows_are_well_formed_over_a_day_clock():
    pool = daypool() + IDS
    pieces = project(mkc(pool, DAYCLOCK, cin(DAYCLOCK, pool), start=fr(12 * 60)), until_frame=fr(3 * 24 * 60))
    bs = breaks(pieces)
    assert bs and any("then" in b.concert.phrases for b in bs) and any("followed" in b.concert.phrases for b in bs)
    for b in bs:
        r = to_row(b, 0)
        assert promises.entries_of(r) == b.concert.entries
        assert not r.names or len(r.named_shows) >= 2
        nxt = pieces[pieces.index(b) + 1]
        assert nxt.role == "show" and nxt.piece.slug == b.concert.named[0]


def test_piece_zero_does_not_depend_on_ahead():
    inp = after_first(start_inp())
    assert project(inp, ahead=1)[0] == project(inp, ahead=3)[0]
    assert project(inp, ahead=1)[0].role == CONCERT_ROLE


# --- strict surface with the feature on: append-only and fallback purity ----------------

def _repro_pool_and_rec():
    pool = library_pieces() + IDS + all_anns(REPRO_CLOCK, seconds=9)
    rec = Recency()
    for i, p in enumerate(pool[:120:3]):
        when = E - (i + 1) * DAY // 3
        rec = rec.with_piece(p, when, ld(when))
    return pool, rec


@pytest.mark.parametrize("ahead", [1, 2])
def test_appending_first_pieces_reproduces_one_projection_with_concert_breaks(ahead):
    # test_scheduler.py's closure test with concert input: appending piece [0] one at a
    # time (concert rows included, so every live step keeps the persisted breaks' promises
    # while the projection keeps its projected ones) reproduces one projection row for row
    pool, rec = _repro_pool_and_rec()
    inp = mkc(pool, REPRO_CLOCK, cin(REPRO_CLOCK, pool), start=fr(12 * 60), rec=rec)
    until = fr(12 * 60) + fr(36 * 60)
    one = project(inp, until_frame=until)
    rows = live(inp, until, ahead)
    assert [to_row(pp, i) for i, pp in enumerate(one[:len(rows)])] == rows
    concert_rows = [r for r in rows if r.role == CONCERT_ROLE]
    assert len(concert_rows) >= 3 and any(len(r.named_shows) == 3 for r in concert_rows)
    # every break's promise is kept: its named shows are the show rows that follow it
    shows = [(i, r) for i, r in enumerate(rows) if r.kind == "show"]
    for i, r in enumerate(rows):
        after = [s.slug for j, s in shows if j > i][:len(r.named_shows)]
        if r.role == CONCERT_ROLE and len(after) == len(r.named_shows):
            assert tuple(after) == r.named_shows


ID_TYP = clip("id-t", 18)                         # one station ID of exactly the typical length


@pytest.mark.parametrize("present", ["empty", "no-block-pieces"])
@pytest.mark.parametrize("world", ["day", "repro"])
def test_falling_back_at_every_boundary_is_todays_rows(world, present):
    # with the boundary estimate equal both ways (one ID of TYP frames), concert input
    # that falls to the last rung at every boundary leaves today's projection unchanged
    assert ID_TYP.frames == TYP
    if world == "day":
        clock, pool = DAYCLOCK, daypool() + [ID_TYP] + all_anns(DAYCLOCK)
    else:
        clock, pool = REPRO_CLOCK, library_pieces() + [ID_TYP] + all_anns(REPRO_CLOCK, seconds=9)
    ci = (concert.ConcertInput(frozenset(), ID_TEXT, TYP) if present == "empty"
          else cin(clock, pool, drop=_block_pieces(clock)))
    off = project(mk(pool, clock, start=fr(12 * 60)), until_frame=fr(2 * 24 * 60))
    on = project(mkc(pool, clock, ci, seed=7, start=fr(12 * 60)), until_frame=fr(2 * 24 * 60))
    assert {p.role for p in off} >= {"next", "later", "id"}
    assert [to_row(p, i) for i, p in enumerate(on)] == [to_row(p, i) for i, p in enumerate(off)]


def test_messy_block_titles_are_spoken_cleaned():
    # X's and Z's pieces exist only under the cleaned title (the inventory's `title_of`)
    clock = tclock(ov_title="Overnight  Variety ", tm_title=" The Music  Never Stopped")
    pool = tpool()
    pieces = project(mkc(pool, clock, cin(clock, pool), start=fr(19 * 60)))
    b = breaks(pieces)[0]
    assert texts(b)[1] == "Coming up next, Overnight Variety"
    assert texts(b)[5:] == [THEN, "with Dark Star Orchestra."]
    assert texts(breaks(pieces)[1])[1] == "Overnight Variety continues"


@pytest.mark.parametrize("drop", ["block-pieces", "untitled"])
def test_a_falling_back_concert_attempt_leaves_the_projection_state_alone(drop):
    # the fallback contract `boundary()` relies on: no `_enter`, the active run and its
    # index restored (the output cannot show a lost restore: `_run_at` re-plans a
    # mismatching run, so this pins the state directly)
    clock = tclock(ov_title=None) if drop == "untitled" else TCLOCK
    pool = tpool()
    inp = after_first(mkc(pool, clock, cin(clock, pool, drop=_block_pieces(clock)), start=fr(19 * 60)))
    for k in range(3):                       # the boundary into Overnight Variety, then inside it
        p = scheduler._Projection(inp)
        before = (p.run, p.run_k, p.occ, p.start, list(p.placed), p.rec, p.after_show, list(p.promise))
        assert p._try_concert(inp.concert, inp.start_frame, 5) is None
        assert (p.run, p.run_k, p.occ, p.start, list(p.placed), p.rec, p.after_show, list(p.promise)) == before
        assert p.run is before[0]
        if k == 2:
            break
        pieces = project(inp)
        nxt = next(i for i, q in enumerate(pieces) if i > 0 and pieces[i - 1].role == "show")
        inp = prefix_inp(inp, pieces, nxt)


# --- live promises (spec "Promises": the shows a break names are the shows then placed) ----

XYZ = ["cracker", "ryanadams", "dso"]


def cpool(*, x_min=115, y_min=116, y_profile="p", with_y=True, alt_min=100, z_min=235, anns=False):
    """tpool's shows with lengths changed after the first break was persisted, plus an
    alternative own show (alt) and Z alternative (dso2), so a fresh run picks otherwise."""
    pool = [sp_("pre", 178, "Pre Act", "e"), sp_("cracker", x_min, "Cracker", "p")]
    if with_y:
        pool.append(sp_("ryanadams", y_min, "Ryan Adams", y_profile))
    pool += [sp_("alt", alt_min, "Alt Act", "p"), sp_("dso", z_min, "Dark Star Orchestra", "d"),
             sp_("dso2", 200, "DSO Two", "d")]
    return pool + IDS + (all_anns(TCLOCK) if anns else [])


def promised(through=2, *, concert_on=True, clock=TCLOCK, **pkw):
    """`start_inp()`'s first `through` pieces persisted ([pre, concert(cracker, ryanadams,
    dso)] for 2; then cracker, the break before ryanadams, ...), then the pool changed."""
    inp = start_inp()
    base = prefix_inp(inp, project(inp), through)
    pool = cpool(**pkw)
    return dataclasses.replace(base, pool=pool, clock=clock, concert=cin(clock, pool) if concert_on else None)


def strip(inp):
    """`inp` with every concert row's promise taken away (no named shows, no names)."""
    return dataclasses.replace(inp, rows=tuple(
        dataclasses.replace(r, named_shows=(), names=()) if r.role == CONCERT_ROLE else r for r in inp.rows))


def slugs(pieces):
    return [p.piece.slug for p in shows_of(pieces)]


def rows_of(pieces, seq=0):
    return [to_row(p, seq + i) for i, p in enumerate(pieces)]


def closure(inp):
    """(one projection's rows, the rows a live planner appends), compared row for row."""
    rows = live(inp, UNTIL)[len(inp.rows):]
    one = rows_of(project(inp, until_frame=UNTIL), len(inp.rows))[:len(rows)]
    return one, rows


UNTIL = fr(32 * 60)


def test_live_promise_places_the_named_shows_after_lengths_change():
    inp = promised(x_min=135, alt_min=100)
    assert slugs(project(strip(inp)))[:3] != XYZ          # a fresh run now picks otherwise
    pieces = project(inp)
    assert slugs(pieces)[:3] == XYZ
    assert pieces[0].piece.slug == "cracker" and pieces[1].role == CONCERT_ROLE
    assert pieces[1].concert.named == ("ryanadams", "dso")


@pytest.mark.parametrize("concert_on", [True, False])
def test_promise_places_z_even_outside_its_window(concert_on):
    # X now 200 min: the run would end Overnight Variety after X (an announcement or ID
    # into The Music Never Stopped); the promise still places Y here, then Z, late
    inp = promised(x_min=200, concert_on=concert_on)
    pieces = project(inp)
    assert slugs(pieces)[:3] == XYZ
    z = show_named(pieces, "dso")
    assert (z.block, z.nominal_start) == occ(TCLOCK, "tmns", 1).key
    assert z.miss is True and to_row(z, 0).miss is True


def test_new_break_between_x_and_y_names_y_and_z_or_fewer():
    for y_min in (116, 200):                                # 200: Z now lands outside its window
        inp = promised(3, y_min=y_min, alt_min=100)
        pieces = project(inp)
        b = pieces[0]
        assert b.role == CONCERT_ROLE and b.concert.named[0] == "ryanadams"
        assert list(b.concert.named) == ["ryanadams", "dso"][:len(b.concert.named)]
        assert slugs(pieces)[:2] == ["ryanadams", "dso"]
        if y_min == 200:
            assert b.concert.named == ("ryanadams",) and b.names == ()   # fewer: Then is not true now


def test_a_new_break_names_the_promised_z_not_a_fresh_pick():
    # rows [pre, R1(X, Y, Z), X], Z now 150 min: a fresh Then would pick dso2; the break
    # before Y names the promised Z
    inp = promised(3, alt_min=60, z_min=150)
    b = project(inp)[0]
    assert b.role == CONCERT_ROLE and b.concert.named == ("ryanadams", "dso") and "then" in b.concert.phrases
    assert slugs(project(inp))[:2] == ["ryanadams", "dso"]


def test_a_new_break_naming_fewer_keeps_the_older_promise_and_projection_equals_live():
    # R2 (projected) names only Y; merged with R1's remainder [Y, Z], Z is still placed, in
    # the projection and in a live continuation alike
    inp = promised(3, y_min=200, alt_min=100)
    assert slugs(project(strip(inp)))[:2] != ["ryanadams", "dso"]
    one, rows = closure(inp)
    assert one == rows
    assert rows[0].role == CONCERT_ROLE and rows[0].named_shows == ("ryanadams",)
    assert [r.slug for r in rows if r.kind == "show"][:2] == ["ryanadams", "dso"]


def _far_names(inp):
    far = occ(TCLOCK, "tmns", 8).key                       # yielded by the clock, but a week on
    return dataclasses.replace(inp, rows=tuple(
        dataclasses.replace(r, names=(far,)) if r.role == CONCERT_ROLE else r for r in inp.rows))


GONE_CLOCK = clk({"name": "pre", "start": "19:00", "profiles": ["e"], "max_shows": 1},
                 {"name": "ov", "title": "Overnight Variety", "start": "22:00", "profiles": ["p"], "max_shows": 2},
                 {"name": "tm2", "title": "The Music Never Stopped", "start": "02:00", "profiles": ["d"],
                  "max_shows": 1},
                 {"name": "day", "start": "06:00"})

VOID_CASES = {
    "y-left-the-pool": lambda: promised(x_min=135, with_y=False),
    "occurrence-gone": lambda: promised(x_min=135, clock=GONE_CLOCK),
    "run-start": lambda: dataclasses.replace(promised(x_min=135), run_start=True),
}


@pytest.mark.parametrize("case", sorted(VOID_CASES))
def test_void_promise_plans_normally_and_never_raises(case):
    inp = VOID_CASES[case]()
    assert rows_of(project(inp)) == rows_of(project(strip(inp)))


def test_a_promise_voided_mid_projection_plans_on():
    # Z's occurrence is still yielded, but is not the one after Y's: X and Y are placed,
    # then the promise is void and planning continues normally
    for concert_on in (True, False):
        inp = _far_names(promised(x_min=135, concert_on=concert_on))
        pieces = project(inp, until_frame=UNTIL)
        assert slugs(pieces)[:2] == ["cracker", "ryanadams"] and pieces[-1].end_frame >= UNTIL


MALFORMED = {
    "non-str-slug": dict(named_shows=(1, None)),
    "empty-slug": dict(named_shows=("",)),
    "too-many": dict(named_shows=("cracker", "ryanadams", "dso", "alt")),
    "a-string": dict(named_shows="cracker"),
    "bad-names": dict(names=(("tmns",),)),
    "names-not-str": dict(names=(("tmns", 5),)),
    "two-names": dict(names=(("a", "b"), ("c", "d"))),
    "not-in-pool": dict(named_shows=("nope", "dso")),
    "no-block": dict(block=None),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_malformed_concert_row_never_raises(case):
    inp = promised(x_min=135)
    bad = dataclasses.replace(inp, rows=tuple(
        dataclasses.replace(r, **MALFORMED[case]) if r.role == CONCERT_ROLE else r for r in inp.rows))
    pieces = project(bad)
    assert pieces and rows_of(pieces) == rows_of(project(strip(bad)))


def test_promises_false_plans_as_if_no_promise():
    inp = promised(x_min=135)
    off = dataclasses.replace(inp, promises=False)
    assert rows_of(project(off)) == rows_of(project(strip(inp))) != rows_of(project(inp))


def test_a_prefix_promise_places_y_then_z():
    # rows [R1(X, Y, Z), X, R2(Y)]: R2's promise is a prefix of R1's remainder, so they agree
    inp = promised(4, y_min=160, alt_min=100)
    assert inp.rows[-1].role == CONCERT_ROLE
    inp = dataclasses.replace(inp, rows=inp.rows[:-1] + (
        dataclasses.replace(inp.rows[-1], named_shows=("ryanadams",), names=()),))
    assert slugs(project(strip(inp)))[:2] != ["ryanadams", "dso"]
    assert slugs(project(inp))[:2] == ["ryanadams", "dso"]
    rows = live(inp, UNTIL)
    assert rows_of(project(inp, until_frame=UNTIL), len(inp.rows))[:len(rows) - len(inp.rows)] == rows[len(inp.rows):]
    for i in range(len(inp.rows), len(rows)):
        assert not promises.first_mismatch(rows[:i], rows[i])
    assert [r.slug for r in rows if r.kind == "show"][2:4] == ["ryanadams", "dso"]


def test_promises_hold_with_announcements_off():
    inp = promised(x_min=135, concert_on=False)
    assert inp.concert is None
    assert slugs(project(strip(inp)))[:3] != XYZ
    pieces = project(inp)
    assert slugs(pieces)[:3] == XYZ and not breaks(pieces)


def test_projection_equals_live_for_promises():
    for concert_on in (True, False):
        inp = promised(3, y_min=160, alt_min=100, concert_on=concert_on)
        assert slugs(project(strip(inp)))[:2] != ["ryanadams", "dso"]
        one, rows = closure(inp)
        assert one == rows
        assert [r.slug for r in rows if r.kind == "show"][:2] == ["ryanadams", "dso"]


def test_projection_equals_live_when_the_promised_show_is_a_fill_show():
    # Y moved to a profile Overnight Variety does not play: placed by the promise, it is a
    # fill show, its fill derived from the pool, so a live continuation rebuilds `extra_own`
    # (from the rows' fill) exactly as the projection had it
    for concert_on in (True, False):
        inp = promised(x_min=135, y_profile="q", concert_on=concert_on)
        one, rows = closure(inp)
        assert one == rows
        y = next(r for r in rows if r.slug == "ryanadams")
        assert y.fill is not None and y.block == "ov"
        assert [r.slug for r in rows if r.kind == "show"][:3] == XYZ
        rows = list(inp.rows) + rows
        i = rows.index(y)
        cont = dataclasses.replace(inp, rows=tuple(rows[:i + 1]), start_frame=y.end_frame + GAP, run_start=False)
        p = scheduler._Projection(cont)
        assert [q.slug for q in p.extra_own] == ["cracker"] and p.promise == [("dso", occ(TCLOCK, "tmns", 1).key)]


def test_a_later_under_a_promise_is_judged_with_the_promised_show():
    # announcements off, Y now 200 min: a fresh run would play alt (120) and land The Music
    # Never Stopped in its window, so today's logic voices a `later` for it; under the
    # promise Y plays, Z cannot start in its window, and no `later` is voiced
    inp = promised(y_min=200, alt_min=120, concert_on=False, anns=True)
    today = project(strip(inp))
    assert [p.role for p in today][:3] == ["show", "later", "show"] and slugs(today)[1] == "alt"
    pieces = project(inp)
    assert slugs(pieces)[:3] == XYZ
    assert pieces[1].role != "later"


def test_a_falling_back_concert_attempt_under_a_live_promise_leaves_the_state_alone():
    # rows [pre, R1(X, Y, Z), X], the continues piece now missing: the attempt before Y
    # falls back with the promise [Y, Z] (and the rest of the state) as it found them
    inp = promised(3, y_min=160)
    inp = dataclasses.replace(inp, concert=cin(TCLOCK, inp.pool, drop=_block_pieces(TCLOCK)))
    p = scheduler._Projection(inp)
    assert p.promise == [("ryanadams", occ(TCLOCK, "ov").key), ("dso", occ(TCLOCK, "tmns", 1).key)]
    before = (p.run, p.run_k, p.occ, p.start, list(p.placed), p.rec, p.after_show, list(p.promise))
    assert p._try_concert(inp.concert, inp.start_frame, 5) is None
    assert (p.run, p.run_k, p.occ, p.start, list(p.placed), p.rec, p.after_show, list(p.promise)) == before
    assert p.run is before[0]
    assert slugs(project(inp))[:2] == ["ryanadams", "dso"]


# a titled open block ("ins") between Overnight Variety and Z's block
INS_CLOCK = clk({"name": "pre", "start": "19:00", "profiles": ["e"], "max_shows": 1},
                {"name": "ov", "title": "Overnight Variety", "start": "22:00", "profiles": ["p"], "max_shows": 2},
                {"name": "ins", "title": "Inserted", "start": "01:00"},
                {"name": "tmns", "title": "The Music Never Stopped", "start": "02:00", "profiles": ["d"],
                 "max_shows": 1},
                {"name": "day", "start": "06:00"})


@pytest.mark.parametrize("concert_on", [True, False])
@pytest.mark.parametrize("through", [2, 3])
def test_a_promise_past_an_inserted_block_is_void_alike_in_preview_and_live(through, concert_on):
    # Z's occurrence is two on from Overnight Variety once a block is inserted: the promise
    # is void at the boundary after Y (the next occurrence is "ins"), and a live step
    # entering "ins" with nothing placed decides the same, so "ins" gets its show
    inp = promised(through, x_min=60, y_min=60, concert_on=concert_on, clock=INS_CLOCK)
    one, rows = closure(inp)
    assert one == rows
    assert any(r.block == "ins" and r.kind == "show" for r in rows)


def test_then_names_only_the_occurrence_after_xs():
    # under the promise [Y, Z in tmns] the break before Y has no Then: the occurrence
    # after Overnight Variety is now "ins", not Z's
    inp = promised(3, x_min=60, y_min=60, clock=INS_CLOCK)
    b = project(inp)[0]
    assert b.role == CONCERT_ROLE and b.concert.named == ("ryanadams",) and b.names == ()
    assert "then" not in b.concert.phrases


def test_a_promised_show_in_a_degraded_block_writes_no_fill():
    # Overnight Variety's profile is gone from the pool: the block is degraded; the
    # promised cracker is not the run's pick, and its row reads as a degraded run's would
    deg = tclock(ov_profiles=("nobody",))
    inp = promised(x_min=60, concert_on=False, clock=deg)
    assert slugs(project(strip(inp)))[0] != "cracker"
    pieces = project(inp)
    assert slugs(pieces)[:2] == ["cracker", "ryanadams"]
    for p in shows_of(pieces)[:2]:
        assert p.block == "ov" and p.degraded and p.fill is None
