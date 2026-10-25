from datetime import date

import pytest

from tests_transmitter.helpers import show_piece
from transmitter import planner, rules
from transmitter.clock import BlockConfig, ClockConfig, Occurrence, Prefer, RotationConfig
from transmitter.grid import iso_to_us
from transmitter.history import Recency

TZ = "America/New_York"
DAY = 86_400_000_000
HOUR = 3_600_000_000
SLOT = iso_to_us("2026-11-03T01:00:00Z")          # 20:00 on 2026-11-02 in New York


def clock(**rotation):
    return ClockConfig(timezone=TZ, rotation=RotationConfig(**rotation),
                       block=[BlockConfig(name="b", start="20:00")])


def occ(prefer=()):
    b = BlockConfig(name="b", start="20:00", profiles=["dead"], prefer=list(prefer))
    return Occurrence(b, SLOT, SLOT - 15 * 60_000_000, SLOT + 15 * 60_000_000, SLOT + 4 * HOUR,
                      date(2026, 11, 2))


def aired(rec, piece, us, day):
    return rec.with_piece(piece, us, day)


def test_never_aired_outranks_recently_aired():
    a = show_piece("a", artist="A", date="1980-01-05")
    b = show_piece("b", artist="B", date="1980-01-06")
    rec = aired(Recency(), a, SLOT - DAY, date(2026, 11, 1))
    ck = clock()
    assert rules.score(b, occ(), rec, ck, SLOT) == 1.0
    assert rules.score(a, occ(), rec, ck, SLOT) == pytest.approx(0.9 / 45)
    # past the gap the term saturates at 0.9: never aired still ranks first
    rec_old = aired(Recency(), a, SLOT - 90 * DAY, date(2026, 8, 4))
    assert rules.score(a, occ(), rec_old, ck, SLOT) == pytest.approx(0.9)


def test_gap_zero_disables_the_gap_rule_without_dividing():
    a = show_piece("a", artist="A", date="1980-01-05")
    rec = aired(Recency(), a, SLOT - HOUR, date(2026, 11, 2))
    ck = clock(concert_gap_days=0)
    assert rules.score(a, occ(), rec, ck, SLOT) == 0.9
    assert rules.score(show_piece("n", date="1980-01-06"), occ(), rec, ck, SLOT) == 1.0
    assert rules.violations([a, a], None, occ(), rec, ck, [SLOT, SLOT + HOUR])[1] == 0


def test_huge_gap_loads_and_scores_without_overflow():
    a = show_piece("a", artist="A", date="1980-01-05")
    rec = aired(Recency(), a, SLOT - 400 * DAY, date(2025, 9, 28))
    ck = clock(concert_gap_days=1e300)
    assert 0.0 <= rules.score(a, occ(), rec, ck, SLOT) < 1e-290
    assert rules.violations([a], None, occ(), rec, ck, [SLOT])[1] == 1


def test_on_this_day_boost_uses_the_slot_local_date():
    ck = clock()
    local = show_piece("l", date="1977-11-02")      # local month-day at SLOT
    utc = show_piece("u", date="1977-11-03")        # the UTC date at SLOT: no boost
    assert rules.score(local, occ(), Recency(), ck, SLOT) == 1.0 + 3.0
    assert rules.score(utc, occ(), Recency(), ck, SLOT) == 1.0
    # the block's own on_this_day overrides the rotation default
    o = occ([Prefer(on_this_day=5.0)])
    assert rules.score(local, o, Recency(), ck, SLOT) == 1.0 + 5.0
    assert rules.score(local, occ(), Recency(), clock(on_this_day_weight=0.5), SLOT) == 1.5


def test_years_preference_adds_its_weight():
    ck = clock()
    o = occ([Prefer(years="1972-1977", weight=1.5), Prefer(years="1977", weight=0.25)])
    assert rules.score(show_piece("a", date="1977-05-08"), o, Recency(), ck, SLOT) == 1.0 + 1.5 + 0.25
    assert rules.score(show_piece("b", date="1972-01-01"), o, Recency(), ck, SLOT) == 1.0 + 1.5
    assert rules.score(show_piece("c", date="1978-05-08"), o, Recency(), ck, SLOT) == 1.0
    assert rules.score(show_piece("d", date=None), o, Recency(), ck, SLOT) == 1.0


def test_huge_weights_score_infinite_not_nan():
    o = occ([Prefer(years="1977", weight=1e308), Prefer(years="1970-1980", weight=1e308)])
    s = rules.score(show_piece("a", date="1977-05-08"), o, Recency(), clock(), SLOT)
    assert s == float("inf")


def test_violations_count_each_rule():
    ck = clock()
    today = date(2026, 11, 2)
    earlier = show_piece("e", artist="Day", date="1977-05-08")
    gapped = show_piece("g", artist="Gap", date="1990-01-01")
    rec = aired(aired(Recency(), earlier, SLOT - 2 * HOUR, today), gapped, SLOT - 3 * DAY, date(2026, 10, 30))
    o = occ()
    # adjacency: same artist as prev_artist, then as the show before it
    adj = [show_piece("a1", artist="Prev", date="1980-01-01"), show_piece("a2", artist="Prev", date="1981-01-01")]
    assert rules.violations(adj, "Prev", o, rec, ck, [SLOT, SLOT + HOUR]) == (2, 0, 1, 0)
    # gap: aired 3 days ago, and twice in the sequence
    assert rules.violations([gapped], None, o, rec, ck, [SLOT]) == (0, 1, 0, 0)
    x = show_piece("x", artist="X", date="1980-02-02")
    y = show_piece("y", artist="Y", date="1980-02-03")
    assert rules.violations([x, y, x], None, o, rec, ck, [SLOT, SLOT + HOUR, SLOT + 2 * HOUR]) == (0, 1, 1, 1)
    # artist_day: the artist already aired today; era: same artist and year today
    other_year = show_piece("d1", artist="Day", date="1980-01-01")
    same_year = show_piece("d2", artist="Day", date="1977-12-31")
    assert rules.violations([other_year], None, o, rec, ck, [SLOT]) == (0, 0, 1, 0)
    assert rules.violations([same_year], None, o, rec, ck, [SLOT]) == (0, 0, 1, 1)
    # the next local day is clean (SLOT + 5 h is past local midnight)
    assert rules.violations([same_year], None, o, rec, ck, [SLOT + 5 * HOUR]) == (0, 0, 0, 0)


def test_violations_ignore_unknown_artists_and_years():
    ck = clock()
    a = show_piece("a", artist=None, date=None)
    b = show_piece("b", artist=None, date=None)
    assert rules.violations([a, b], None, occ(), Recency(), ck, [SLOT, SLOT + HOUR]) == (0, 0, 0, 0)


def test_rules_are_hardest_first():
    assert rules.RULES == ("adjacency", "gap", "artist_day", "era")


def test_tie_rank_is_the_planner_shuffle_rank():
    assert rules.tie_rank(7, "alpha") == planner.shuffle_rank(7, "alpha")
    assert rules.tie_rank(7, "alpha") != rules.tie_rank(8, "alpha")
    assert planner.shuffle_rank is rules.tie_rank
