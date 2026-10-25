import random
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from tests_transmitter.helpers import library_pieces, show_piece
from transmitter import rules, scheduler
from transmitter.clock import BlockConfig, ClockConfig, Occurrence, Prefer, RotationConfig
from transmitter.errors import PlanError
from transmitter.grid import frame_to_us, iso_to_us
from transmitter.history import Recency
from transmitter.scheduler import BlockPlan, fill_block

TZ = "America/New_York"
E = iso_to_us("2026-11-02T23:00:00Z")          # 18:00 local on 2026-11-02
MIN = 60_000_000
DAY = 86_400_000_000
GAP = 87                                        # 2 s of frames
CLOCK = ClockConfig(timezone=TZ, block=[BlockConfig(name="b", start="18:00")])


def fr(minutes: float) -> int:
    return round(minutes * 60 * 44_100 / 1024)


def at(frame: int) -> int:
    return E + frame_to_us(frame)


def local_date(us: int) -> date:
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=us)).astimezone(ZoneInfo(TZ)).date()


def make_occ(name="b", *, at_min=0.0, profiles=("p",), max_shows=None, early=15.0, late=15.0, prefer=()):
    nominal = E + round(at_min * MIN)
    b = BlockConfig(name=name, start="18:00", profiles=list(profiles), max_shows=max_shows,
                    early_minutes=early, late_minutes=late, prefer=list(prefer))
    return Occurrence(b, nominal, nominal - round(early * MIN), nominal + round(late * MIN),
                      nominal + 6 * 60 * MIN, local_date(nominal))


def nxt(at_min, early=15.0, late=15.0):
    return make_occ("next", at_min=at_min, early=early, late=late)


def sp(slug, minutes, artist=None, *, profile="p", date="1980-01-01"):
    return show_piece(slug, artist=artist or slug.upper(), date=date, profile=profile, frames=fr(minutes))


def fill(occ, next_occ, own, open_pool=(), *, start_frame=0, placed=(), prev_artist=None, rec=None,
         clock=CLOCK, seed=7, used=frozenset(), gap=GAP) -> BlockPlan:
    return fill_block(occ, next_occ, start_frame=start_frame, placed=tuple(placed), own_pool=list(own),
                      open_pool=list(open_pool), boundary_frames=gap, final_boundary_frames=gap,
                      prev_artist=prev_artist, rec=rec if rec is not None else Recency(), clock=clock,
                      epoch_us=E, seed=seed, used=used)


def in_window(plan, next_occ):
    return next_occ.lo_us <= at(plan.landing_frame) <= next_occ.hi_us


def slugs(plan):
    return [p.slug for p in plan.shows]


# --- tier 0 ---------------------------------------------------------------

def test_single_show_landing_in_window_is_tier0():
    own = [sp("s60", 60), sp("s118", 118), sp("s200", 200)]
    n = nxt(120)
    plan = fill(make_occ(), n, own)
    assert slugs(plan) == ["s118"]
    assert plan.tier == 0 and plan.fill_from is None and plan.fill_cause is None and not plan.degraded
    assert plan.landing_frame == fr(118) + GAP and in_window(plan, n)


def test_pair_fills_a_long_block_from_its_own_profile():
    # 4 h jam block, own pool only 2 h and 1.9 h shows -> both chosen, tier 0
    own = [sp("j120", 120, "Moe"), sp("j114", 114, "Panic")]
    n = nxt(240)
    plan = fill(make_occ(), n, own, [sp("f120", 120, "Funk", profile="funk")] + own)
    assert sorted(slugs(plan)) == ["j114", "j120"]
    assert plan.tier == 0 and plan.fill_from is None and in_window(plan, n)
    assert plan.landing_frame == fr(120) + fr(114) + 2 * GAP


def test_own_profile_pair_beats_fill_even_when_pairing_breaks_adjacency():
    # single-artist Dead pool, block needs two shows: tier 0 pair chosen; "adjacency" not in bends
    own = [sp("d1", 120, "Grateful Dead", profile="dead"), sp("d2", 115, "Grateful Dead", profile="dead",
                                                                date="1977-05-08")]
    funk = [sp("f1", 115, "Funk A", profile="funk"), sp("f2", 120, "Funk B", profile="funk")]
    n = nxt(240)
    plan = fill(make_occ(profiles=("dead",)), n, own, own + funk)
    assert sorted(slugs(plan)) == ["d1", "d2"]
    assert plan.tier == 0 and plan.fill_from is None
    assert "adjacency" not in plan.bends and "artist_day" not in plan.bends


def test_open_block_takes_as_many_shows_as_land_it():
    pool = [sp(f"o{i}", 120, f"Band {i}", profile=f"x{i}") for i in range(6)]
    n = nxt(360)
    plan = fill(make_occ(profiles=()), n, pool, pool)
    assert len(plan.shows) == 3 and plan.tier == 0 and in_window(plan, n)


def test_greedy_extension_keeps_the_rules_when_it_can():
    # three shows needed; the best-scoring show shares the previous block's artist
    o = make_occ(profiles=(), prefer=[Prefer(years="1977", weight=2.0)])
    pool = [sp("x1", 120, "X", date="1977-05-08"), sp("a", 120, "A"), sp("b", 121, "B"), sp("c", 119, "C")]
    plan = fill(o, nxt(360), pool, pool, prev_artist="X")
    artists = [p.artist for p in plan.shows]
    assert len(artists) == 3 and "X" in artists and artists[0] != "X" and plan.tier == 0


def test_used_pieces_are_skipped_unless_nothing_else_is_left():
    own = [sp("a", 118, "A"), sp("b", 119, "B")]
    n = nxt(120)
    first = fill(make_occ(), n, own)
    other = fill(make_occ(), n, own, used=frozenset({first.shows[0].slug}))
    assert other.shows[0].slug != first.shows[0].slug
    only = fill(make_occ(), n, own[:1], used=frozenset({"a"}))
    assert slugs(only) == ["a"]


def test_a_block_never_plays_one_piece_twice():
    # one 2 h show and a 4 h block: no (a, a) pair; it plays once and the next block starts early
    own = [sp("a", 120, "A")]
    plan = fill(make_occ(), nxt(240), own)
    assert slugs(plan) == ["a"] and plan.tier == 2


# --- tier 1: fill ---------------------------------------------------------

def test_fill_when_the_own_pool_cannot_reach_the_window():
    # own shows all short (fewer than max_shows of them); tier 1 with fill_cause "pool-short"
    own = [sp("bg1", 60, "Grass A", profile="bluegrass"), sp("bg2", 60, "Grass B", profile="bluegrass")]
    funk = [sp("f1", 110, "Funk A", profile="funk"), sp("f2", 116, "Funk B", profile="funk"),
            sp("f3", 30, "Funk C", profile="funk")]
    n = nxt(240)
    plan = fill(make_occ(profiles=("bluegrass",), max_shows=3), n, own, own + funk)
    assert plan.tier == 1 and plan.fill_cause == "pool-short"
    assert plan.fill_from == 2 and sorted(slugs(plan)[:2]) == ["bg1", "bg2"]
    assert all(p.profile == "funk" for p in plan.shows[2:]) and in_window(plan, n)


def test_fill_with_long_own_shows_that_cannot_combine_is_pool_short():
    own = [sp("o1", 150, "A"), sp("o2", 140, "B")]       # singles land early, the pair overruns
    funk = [sp("f1", 90, "Funk", profile="funk")]
    n = nxt(240)
    plan = fill(make_occ(), n, own, own + funk)
    assert plan.tier == 1 and plan.fill_cause == "pool-short" and plan.fill_from == 1
    assert slugs(plan)[0] in {"o1", "o2"} and in_window(plan, n)


def test_structural_fill_when_block_is_longer_than_max_shows_can_cover():
    own = [sp(f"s{i}", 60, f"Act {i}") for i in range(5)]
    funk = [sp("f1", 120, "Funk A", profile="funk"), sp("f2", 118, "Funk B", profile="funk"),
            sp("f3", 125, "Funk C", profile="funk"), sp("f4", 60, "Funk D", profile="funk")]
    n = nxt(360)
    plan = fill(make_occ(), n, own, own + funk)
    assert plan.tier == 1 and plan.fill_cause == "structural" and plan.fill_from == 2
    assert all(p.profile == "p" for p in plan.shows[:2]) and in_window(plan, n)
    assert len(plan.shows) - plan.fill_from <= 3


def test_fill_keeps_at_least_one_own_show():
    # a 4 h fill show alone would land on the nominal time; the block still opens with its own show
    own = [sp("o1", 60, "Own")]
    funk = [sp("f240", 240, "Long", profile="funk"), sp("f180", 178, "Mid", profile="funk")]
    n = nxt(240)
    plan = fill(make_occ(), n, own, own + funk)
    assert plan.tier == 1 and slugs(plan) == ["o1", "f180"] and plan.fill_from == 1


def test_no_own_show_follows_fill():
    # the block is already into its fill (a placed show from another profile): fill goes at the end
    a, f = sp("a", 60, "A"), sp("f", 60, "F", profile="funk")
    own = [a, sp("b", 60, "B")]
    funk = [f, sp("g", 58, "G", profile="funk")]
    start = 2 * fr(60) + 2 * GAP
    plan = fill(make_occ(max_shows=3), nxt(180), own, own + funk, start_frame=start, placed=(a, f))
    assert slugs(plan) == ["g"] and plan.fill_from == 0 and plan.tier == 1
    done = fill(make_occ(max_shows=3), nxt(120), own, own + funk, start_frame=start, placed=(a, f))
    assert done.shows == () and done.tier == 1 and done.fill_from is None


def test_open_blocks_have_no_fill_tier():
    pool = [sp("a", 60, "A"), sp("b", 61, "B")]
    plan = fill(make_occ(profiles=()), nxt(240), pool, pool + [sp("f", 120, "F", profile="funk")])
    assert plan.tier == 2 and plan.fill_from is None
    assert set(slugs(plan)) <= {"a", "b"}


# --- tier 2: miss ---------------------------------------------------------

def test_miss_keeps_the_blocks_own_profile():
    # every own show overruns: tier 2, one own show, landing late, no fill
    own = [sp("o190", 190, "A"), sp("o180", 180, "B")]
    funk = [sp("f110", 110, "Funk", profile="funk")]
    n = nxt(120)
    plan = fill(make_occ(), n, own, own + funk)
    assert plan.tier == 2 and slugs(plan) == ["o180"] and plan.fill_from is None
    assert at(plan.landing_frame) > n.hi_us


def test_overlapping_window_plays_late_with_a_miss():
    # the next block's window has already passed at start_frame: one own show still chosen, tier 2, landing late
    own = [sp("a", 100, "A"), sp("b", 90, "B"), sp("c", 95, "C")]
    n = nxt(-60)
    plan = fill(make_occ(), n, own)
    assert plan.tier == 2 and slugs(plan) == ["b"] and at(plan.landing_frame) > n.hi_us


def test_placed_prefix_at_max_shows_has_an_option():
    # placed == max_shows: a BlockPlan with no added own show, no exception
    placed = (sp("p1", 60, "A"), sp("p2", 60, "B"))
    start = fr(60) * 2 + 2 * GAP
    plan = fill(make_occ(), nxt(240), [sp("x", 60, "X")] + list(placed), start_frame=start, placed=placed)
    assert plan.shows == () and plan.tier == 2 and plan.landing_frame == start
    funk = [sp("f", 118, "F", profile="funk")]
    filled = fill(make_occ(), nxt(240), list(placed), list(placed) + funk, start_frame=start, placed=placed)
    assert slugs(filled) == ["f"] and filled.tier == 1 and filled.fill_from == 0


def test_early_landing_block_gets_no_extra_show():
    # placed prefix already lands in window: k = 0 chosen
    placed = (sp("p1", 118, "A"),)
    start = fr(118) + GAP
    n = nxt(120)
    plan = fill(make_occ(), n, [sp("x", 60, "X"), placed[0]], start_frame=start, placed=placed)
    assert plan.shows == () and plan.tier == 0 and plan.landing_frame == start and in_window(plan, n)


def test_placed_shows_supply_the_previous_artist():
    placed = (sp("p1", 60, "Same"),)
    own = [sp("same", 58, "Same"), sp("diff", 58, "Diff")]
    start = fr(60) + GAP
    plan = fill(make_occ(), nxt(120), own, start_frame=start, placed=placed, prev_artist="Other")
    assert slugs(plan) == ["diff"]


# --- degraded and scarce pools ----------------------------------------------

def test_empty_pool_block_degrades_to_open_time():
    open_pool = [sp(f"o{i}", 120, f"Band {i}", profile="funk") for i in range(4)]
    n = nxt(360)
    plan = fill(make_occ(profiles=("bluegrass",)), n, [], open_pool)
    assert plan.degraded and plan.tier == 0 and len(plan.shows) == 3     # unbounded, as an open block
    assert plan.fill_from is None and in_window(plan, n)


def test_no_show_anywhere_raises_plan_error():
    with pytest.raises(PlanError):
        fill(make_occ(profiles=("bluegrass",)), nxt(120), [], [])


def test_scarce_pool_repeats_rather_than_degrading():
    # own pool of 2 shows both aired yesterday: still own profile, "gap" not a bend (no option kept it)
    own = [sp("c1", 120, "Hank", profile="country"), sp("c2", 118, "Wayne", profile="country")]
    rec = Recency()
    for p in own:
        rec = rec.with_piece(p, E - DAY, local_date(E - DAY))
    funk = [sp("f", 238, "Funk", profile="funk")]
    plan = fill(make_occ(profiles=("country",)), nxt(240), own, own + funk, rec=rec)
    assert not plan.degraded and plan.tier == 0 and sorted(slugs(plan)) == ["c1", "c2"]
    assert "gap" not in plan.bends


# --- rules within a tier ------------------------------------------------------

def _rule_pool():
    today = local_date(E)
    day_show = sp("dayshow", 60, "Day", date="1977-05-08")
    gapper = sp("gap", 119, "Gap", date="1990-01-01")
    rec = Recency().with_piece(day_show, E - 120 * MIN, today).with_piece(gapper, E - DAY, local_date(E - DAY))
    opts = {
        "adj": sp("adj", 118, "Prev", date="1985-01-01"),     # adjacency only
        "gap": gapper,                                       # gap only
        "dayera": sp("dayera", 121, "Day", date="1977-01-01"),  # artist_day + era
        "day": sp("day", 122, "Day", date="1980-01-01"),     # artist_day only
    }
    return opts, rec


def test_bend_counted_only_when_a_keeping_option_existed():
    opts, rec = _rule_pool()
    plan = fill(make_occ(), nxt(120), [opts["adj"], opts["gap"]], rec=rec, prev_artist="Prev")
    assert slugs(plan) == ["gap"] and plan.bends == ("gap",)
    alone = fill(make_occ(), nxt(120), [opts["gap"]], rec=rec, prev_artist="Prev")
    assert slugs(alone) == ["gap"] and alone.bends == ()


def test_softest_rule_bends_first():
    # era bends before artist_day, which bends before gap, which bends before adjacency.
    # era implies artist_day (same artist, same day), so its option breaks both.
    opts, rec = _rule_pool()
    order = []
    left = dict(opts)
    while left:
        plan = fill(make_occ(), nxt(120), list(left.values()), rec=rec, prev_artist="Prev")
        assert len(plan.shows) == 1 and plan.tier == 0
        order.append(plan.shows[0].slug)
        del left[plan.shows[0].slug]
    assert order == ["day", "dayera", "gap", "adj"]


def test_deterministic_with_seed_tiebreak():
    pool = [sp(f"t{i}", 118, f"Band {i}") for i in range(6)]
    for seed in (1, 2, 3):
        want = min(pool, key=lambda p: rules.tie_rank(seed, p.slug)).slug
        shuffled = pool[:]
        random.Random(seed).shuffle(shuffled)
        a = fill(make_occ(), nxt(120), pool, seed=seed)
        b = fill(make_occ(), nxt(120), shuffled, seed=seed)
        assert slugs(a) == slugs(b) == [want]


def test_infinite_scores_order_by_tie_rank():
    o = make_occ(prefer=[Prefer(years="1980", weight=1e308), Prefer(years="1979-1981", weight=1e308)])
    pool = [sp(f"t{i}", 118, f"Band {i}") for i in range(4)]
    want = min(pool, key=lambda p: rules.tie_rank(7, p.slug)).slug
    plan = fill(o, nxt(120), pool)
    assert slugs(plan) == [want] and plan.tier == 0


def test_gap_zero_never_counts_a_gap_bend():
    own = [sp("a", 118, "A"), sp("b", 119, "B")]
    rec = Recency().with_piece(own[0], E - DAY, local_date(E - DAY))
    ck = ClockConfig(timezone=TZ, rotation=RotationConfig(concert_gap_days=0),
                     block=[BlockConfig(name="b", start="18:00")])
    plan = fill(make_occ(), nxt(120), own, rec=rec, clock=ck)
    assert plan.bends == () and plan.tier == 0


# --- consistency and the fixture --------------------------------------------

def _start_us_of(plan_shows, start_frame, gap=GAP):
    out, f = [], start_frame
    for p in plan_shows:
        out.append(f)
        f += p.frames + gap
    return out


def _continue_matches(occ, n, own, open_pool, rec=None):
    """Appending the chosen shows one at a time (as the live planner does) and
    re-filling the block reproduces the rest of the first choice."""
    rec = rec if rec is not None else Recency()
    first = fill(occ, n, own, open_pool, rec=rec)
    starts = _start_us_of(first.shows, 0)
    for i in range(1, len(first.shows)):
        placed = first.shows[:i]
        r = rec
        for p, f in zip(placed, starts):
            r = r.with_piece(p, at(f), local_date(at(f)))
        again = fill(occ, n, own, open_pool, rec=r, placed=placed,
                     start_frame=starts[i], used=frozenset())
        assert again.shows == first.shows[i:], (i, slugs(first), slugs(again))
        assert again.landing_frame == first.landing_frame
    return first


def _aired_history(pieces, seed=3):
    """Half the library aired in the last 60 days: recency terms differ."""
    rng = random.Random(seed)
    rec = Recency()
    for p in pieces:
        if rng.random() < 0.5:
            when = E - rng.randrange(1, 60 * 24) * 60 * MIN
            rec = rec.with_piece(p, when, local_date(when))
    return rec


PREFS = [Prefer(years="1972-1977", weight=0.6), Prefer(years="2010-2019", weight=0.3)]


@pytest.mark.parametrize("history", [False, True])
def test_continuing_a_block_reproduces_the_first_choice(history):
    pieces = library_pieces()
    rec = _aired_history(pieces) if history else None
    dead = [p for p in pieces if p.profile == "dead"]
    plan = _continue_matches(make_occ(profiles=("dead",), early=20, late=20, prefer=PREFS),
                             nxt(335, 20, 20), dead, pieces, rec)
    assert len(plan.shows) == 2 and plan.tier == 0
    jam = [p for p in pieces if p.profile == "jam"]
    _continue_matches(make_occ(profiles=("jam",), max_shows=3, prefer=PREFS), nxt(9 * 60), jam, pieces, rec)


@pytest.mark.parametrize("history", [False, True])
def test_continuing_an_open_block_reproduces_the_first_choice(history):
    pieces = library_pieces()
    rec = _aired_history(pieces) if history else None
    for hours, wiggle in ((12, 30), (24, 720)):
        plan = _continue_matches(make_occ(profiles=(), early=wiggle, late=wiggle, prefer=PREFS),
                                 nxt(hours * 60, wiggle, wiggle), pieces, pieces, rec)
        assert len(plan.shows) >= 4 and plan.tier == 0


def test_every_fixture_profile_block_lands_or_compromises():
    pieces = library_pieces()
    profiles = sorted({p.profile for p in pieces})
    for prof in profiles:
        own = [p for p in pieces if p.profile == prof]
        for hours in (2, 3, 4, 5):
            n = nxt(hours * 60)
            plan = fill(make_occ(profiles=(prof,)), n, own, pieces)
            assert plan.shows or plan.tier == 2
            if plan.tier < 2:
                assert in_window(plan, n)
            own_shows = plan.shows if plan.fill_from is None else plan.shows[:plan.fill_from]
            assert own_shows and all(p.profile == prof for p in own_shows)


def test_violation_counts_agree_with_rules():
    pieces = library_pieces()
    rng = random.Random(5)
    rec = Recency()
    for p in rng.sample(pieces, 60):
        when = E - rng.randrange(0, 60) * DAY // 2
        rec = rec.with_piece(p, when, local_date(when))
    for trial in range(200):
        seq = [rng.choice(pieces) for _ in range(rng.randint(1, 5))]
        prev = rng.choice([None, "Grateful Dead", seq[0].artist])
        start = rng.randrange(0, fr(20 * 60))
        got = scheduler._sequence_violations(make_occ(), rec, CLOCK, E, seq, prev, start, GAP)
        starts = [at(f) for f in _start_us_of(seq, start)]
        assert got == rules.violations(seq, prev, make_occ(), rec, CLOCK, starts), trial


# --- speed -------------------------------------------------------------------

def _synthetic(n, seed=11):
    rng = random.Random(seed)
    profs = ["dead", "funk", "jam", "bluegrass", "indie", "americana"]
    out = []
    for i in range(n):
        prof = profs[i % len(profs)]
        artist = "Grateful Dead" if prof == "dead" else f"{prof} act {rng.randrange(40)}"
        out.append(sp(f"syn{i:04d}", rng.uniform(60, 220), artist, profile=prof,
                      date=f"{rng.randint(1966, 2019)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"))
    return out


def test_fill_block_is_fast_on_a_3000_piece_pool():
    pool = _synthetic(3000)
    dead = [p for p in pool if p.profile == "dead"]
    long_dead = [p for p in dead if fr(140) <= p.frames <= fr(165)]      # singles early, pairs late
    t0 = time.perf_counter()
    assert fill(make_occ(profiles=("dead",)), nxt(330), dead, pool).tier == 0
    assert fill(make_occ(profiles=("dead",)), nxt(240), long_dead, pool).tier == 1
    assert fill(make_occ(profiles=()), nxt(12 * 60, 60, 60), pool, pool).tier == 0
    assert fill(make_occ(profiles=()), nxt(24 * 60, 720, 720), pool, pool).tier == 0   # the implicit clock
    assert time.perf_counter() - t0 < 2.0
