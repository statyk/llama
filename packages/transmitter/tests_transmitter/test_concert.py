import hashlib
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from transmitter import concert
from transmitter.clock import BlockConfig, ClockConfig

NY = ZoneInfo("America/New_York")


def _us(local: str) -> int:
    """A naive America/New_York wall time 'YYYY-MM-DD HH:MM[:SS]' -> epoch microseconds."""
    fmt = "%Y-%m-%d %H:%M:%S" if local.count(":") == 2 else "%Y-%m-%d %H:%M"
    dt = datetime.strptime(local, fmt).replace(tzinfo=NY)
    return int(dt.astimezone(timezone.utc).timestamp()) * 1_000_000


E = _us("2026-11-02 00:00")


def _clock(tz="America/New_York", *blocks):
    return ClockConfig(timezone=tz, block=[BlockConfig(**b) for b in blocks])


def _three():
    return _clock("America/New_York",
                  dict(name="a", title="a", start="12:00"),
                  dict(name="b", title="b", start="02:00"),
                  dict(name="c", start="18:00"))


@pytest.mark.parametrize("local,text", [
    ("2026-11-25 23:00", "at 11 Eastern."), ("2026-11-25 23:02", "at 11 Eastern."),
    ("2026-11-25 23:03", "just after 11 Eastern."), ("2026-11-25 23:10", "just after 11 Eastern."),
    ("2026-11-25 23:11", "around quarter past 11 Eastern."), ("2026-11-25 23:19", "around quarter past 11 Eastern."),
    ("2026-11-25 23:20", "around half past 11 Eastern."), ("2026-11-25 23:40", "around half past 11 Eastern."),
    ("2026-11-25 23:41", "around quarter to midnight Eastern."), ("2026-11-25 23:49", "around quarter to midnight Eastern."),
    ("2026-11-25 23:50", "a few minutes before midnight Eastern."), ("2026-11-25 23:57", "a few minutes before midnight Eastern."),
    ("2026-11-25 23:58", "at midnight Eastern."), ("2026-11-25 11:59", "at noon Eastern."),
    ("2026-11-26 00:05", "just after midnight Eastern."), ("2026-11-26 12:30", "around half past noon Eastern."),
    ("2026-11-26 00:59:59", "at 1 Eastern."),
])
def test_time_phrase_buckets(local, text):
    assert concert.time_phrase(_us(local)) == text


def test_seventy_eight_time_phrases():
    assert len(concert.ALL_TIME_PHRASES) == 78 == len(set(concert.ALL_TIME_PHRASES))
    assert all(t.endswith(" Eastern.") for t in concert.ALL_TIME_PHRASES)


def test_every_bucket_output_is_in_the_inventory():
    start = _us("2026-11-25 00:00")
    got = {concert.time_phrase(start + m * 60_000_000) for m in range(24 * 60)}
    assert got == set(concert.ALL_TIME_PHRASES)


def test_then_time_and_text():
    assert concert.then_time(_us("2026-11-26 02:00")) == "2"
    assert concert.then_time(_us("2026-11-26 02:30")) == "2:30"
    assert concert.then_time(_us("2026-11-26 00:00")) == "midnight"
    assert concert.then_time(_us("2026-11-26 12:00")) == "noon"
    assert concert.then_time(_us("2026-11-26 00:30")) == "12:30"
    assert concert.then_time(_us("2026-11-26 12:30")) == "12:30"
    assert concert.then_text("The Music Never Stopped", _us("2026-11-26 02:00")) == \
        "Then, at 2 Eastern, The Music Never Stopped"


def test_fixed_texts():
    assert concert.next_text("Overnight Variety") == "Coming up next, Overnight Variety"
    assert concert.next_end_text("Overnight Variety") == "Coming up next, Overnight Variety."
    assert concert.continues_text("Overnight Variety") == "Overnight Variety continues"
    assert concert.continues_end_text("Overnight Variety") == "Overnight Variety continues."
    assert (concert.with_comma("Cracker"), concert.with_period("Cracker"), concert.followed_by("Ryan Adams")) == \
        ("with Cracker,", "with Cracker.", "followed by Ryan Adams,")
    assert concert.with_period("moe.") == "with moe."
    assert concert.piece_id("with Cracker,") == hashlib.sha256(b"with Cracker,").hexdigest()[:12]


def test_eastern_whatever_the_clock_timezone_and_across_dst():
    # the repeated 01:xx hour on 2026-11-01 (both passes) is spoken as the Eastern wall hour
    first = int(datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).timestamp()) * 1_000_000
    second = int(datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp()) * 1_000_000
    assert concert.time_phrase(first) == concert.time_phrase(second) == "around half past 1 Eastern."
    # a Europe/London clock: a 02:00 London block is 9 PM Eastern, then 10 PM once the US
    # springs forward on 2027-03-14 (before London does) -> no exception, Eastern wall hours
    london = _clock("Europe/London", dict(name="x", title="X", start="02:00"))
    start = int(datetime(2027, 3, 10, tzinfo=timezone.utc).timestamp()) * 1_000_000
    texts = {p.text for p in concert.needed_pieces(london, [], "ID.", from_us=start) if p.kind == "then"}
    assert texts == {"Then, at 9 Eastern, X", "Then, at 10 Eastern, X"}
    # a New York 02:00 block on the spring-forward day resolves to 3, never a nonexistent 2
    ny = _clock("America/New_York", dict(name="y", title="Y", start="02:00"))
    start = _us("2027-03-13 12:00")
    texts = {p.text for p in concert.needed_pieces(ny, [], "ID.", from_us=start, days=3) if p.kind == "then"}
    assert texts == {"Then, at 2 Eastern, Y", "Then, at 3 Eastern, Y"}


def test_inventory_counts_and_kinds():
    got = concert.needed_pieces(_three(), ["Cracker", "Ryan Adams"], "ID.", from_us=E)
    by_kind = Counter(p.kind for p in got)
    assert by_kind == {"id": 1, "next": 2, "next_end": 2, "continues": 2, "continues_end": 2,
                       "then": 2, "with_comma": 2, "with_period": 2, "followed": 2, "time": 78}
    assert set(by_kind) <= set(concert.PIECE_KINDS)
    assert all(p.id == concert.piece_id(p.text) for p in got) and got == sorted(got, key=lambda p: p.id)


def test_artist_texts_are_single_line_and_deduped():
    got = concert.needed_pieces(_three(), ["Grateful Dead", "Grateful  Dead ", "moe.", "a\nb", "", None, 7],
                                "ID.", from_us=E)
    arts = {p.text for p in got if p.kind == "with_comma"}
    assert arts == {"with Grateful Dead,", "with moe.,", "with a b,"}
    assert {p.text for p in got if p.kind == "with_period"} == {"with Grateful Dead.", "with moe.", "with a b."}
    assert concert.clean("  x \n y ") == "x y" and concert.clean("") is None and concert.clean(7) is None
