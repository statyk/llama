from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from herder.limits import RateLimited, classify, parse_reset

# The measured signature, captured verbatim from a live run on 2026-09-04.
# Note the U+00B7 middle dot: it is part of the real string and must not be
# normalized away.
SESSION_LIMIT = (
    "claude exited 1: You've hit your session limit · "
    "resets 11:10am (America/New_York)"
)
# The dropped-connection failure this must NOT match; it is what stands
# between a network blip and a multi-hour idle.
CLOSED_MID = ("claude exited 1: API Error: Connection closed mid-response. "
              "The response above may be incomplete.")

NY = ZoneInfo("America/New_York")


def test_classifies_the_measured_session_limit():
    err = classify(SESSION_LIMIT, now=datetime(2026, 9, 4, 14, 0, tzinfo=NY))
    assert isinstance(err, RateLimited)
    assert err.scope == "five_hour"
    assert "session limit" in str(err)


def test_dropped_connection_is_not_a_rate_limit():
    assert classify(CLOSED_MID) is None


def test_ordinary_failures_are_not_rate_limits():
    assert classify("claude exited 1: boom") is None
    assert classify("claude output was not JSON: <html>") is None


def test_reset_resolves_to_the_next_future_occurrence():
    now = datetime(2026, 9, 4, 8, 30, tzinfo=NY)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got == datetime(2026, 9, 4, 11, 10, tzinfo=NY).astimezone(timezone.utc)


def test_reset_past_today_rolls_to_tomorrow_only_within_the_bound():
    # 11:10am already gone: tomorrow's 11:10am is >5.5h out, so it is refused
    # rather than becoming a day-long sleep.
    now = datetime(2026, 9, 4, 12, 0, tzinfo=NY)
    assert parse_reset(SESSION_LIMIT, now=now) is None


def test_reset_within_the_bound_is_accepted():
    now = datetime(2026, 9, 4, 7, 0, tzinfo=NY)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got is not None
    assert timedelta(0) < got - now.astimezone(timezone.utc) <= timedelta(hours=5.5)


def test_reset_is_read_in_the_zone_the_message_names_not_the_callers():
    # Caller in UTC; message says America/New_York. 11:10am EDT == 15:10 UTC.
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got == datetime(2026, 9, 4, 15, 10, tzinfo=timezone.utc)


def test_reset_survives_a_dst_boundary():
    # 2026-11-01 02:00 EDT -> EST. 11:10am the morning after the switch is EST.
    text = "You've hit your session limit · resets 11:10am (America/New_York)"
    now = datetime(2026, 11, 1, 7, 30, tzinfo=NY)
    got = parse_reset(text, now=now)
    assert got == datetime(2026, 11, 1, 11, 10, tzinfo=NY).astimezone(timezone.utc)


def test_unknown_zone_or_unparseable_time_yields_no_reset():
    assert parse_reset("hit your session limit, resets soon") is None
    assert parse_reset("resets 11:10am (Mars/Olympus)") is None


def test_classified_error_without_a_parseable_reset_still_classifies():
    err = classify("You've hit your session limit")
    assert isinstance(err, RateLimited)
    assert err.resets_at is None
