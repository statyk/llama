from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from herder.limits import RateLimited, classify, parse_reset
from herder.provider import HerderError

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


# --- Fix round 1: pinning tests below. Every test above uses 11:10am, where
# the `% 12` am/pm conversion agrees with the naive `+ 12` formula and the
# 5.5h bound is never exercised near its edges - so those constraints, and
# two of the three _SIGNATURES entries, had no test at all. See
# task-2-quality-verdict.md I1/I2/I4.


def test_reset_12am_resolves_to_midnight_not_noon():
    # 12:00am is hour 0. A naive `int(hour12) + 12` (dropping the `% 12`)
    # would give 12, i.e. noon - this pins the correct conversion.
    now = datetime(2026, 9, 4, 22, 0, tzinfo=NY)
    got = parse_reset("resets 12:00am (America/New_York)", now=now)
    assert got == datetime(2026, 9, 5, 0, 0, tzinfo=NY).astimezone(timezone.utc)


def test_reset_12pm_resolves_to_noon_not_midnight():
    # 12:00pm is hour 12. The naive `int(hour12) + 12` formula would give
    # 24, which is not a valid hour - this pins the correct conversion.
    now = datetime(2026, 9, 4, 8, 0, tzinfo=NY)
    got = parse_reset("resets 12:00pm (America/New_York)", now=now)
    assert got == datetime(2026, 9, 4, 12, 0, tzinfo=NY).astimezone(timezone.utc)


def test_reset_just_over_the_bound_is_refused():
    # 11:10am is 6h10m out: refused, one edge of MAX_RESET_AHEAD_S.
    now = datetime(2026, 9, 4, 5, 0, tzinfo=NY)
    assert parse_reset(SESSION_LIMIT, now=now) is None


def test_reset_just_under_the_bound_is_accepted():
    # 11:10am is 5h10m out: accepted, the other edge of MAX_RESET_AHEAD_S.
    now = datetime(2026, 9, 4, 6, 0, tzinfo=NY)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got == datetime(2026, 9, 4, 11, 10, tzinfo=NY).astimezone(timezone.utc)


def test_reset_out_of_range_minute_yields_no_reset():
    assert parse_reset("resets 11:75am (America/New_York)") is None


def test_reset_exactly_now_rolls_to_tomorrow():
    # now equal to the named wall-clock instant rolls forward (pins `<=`
    # rather than `<`), and tomorrow's occurrence is then outside the
    # 5.5h bound, so the net result is refused rather than returning `now`.
    now = datetime(2026, 9, 4, 11, 10, tzinfo=NY)
    assert parse_reset(SESSION_LIMIT, now=now) is None


def test_classifies_usage_limit_reached():
    err = classify("usage limit reached")
    assert isinstance(err, RateLimited)
    assert err.scope is None


def test_classifies_seven_day_variant():
    err = classify("You've hit your weekly limit")
    assert isinstance(err, RateLimited)
    assert err.scope == "seven_day"


def test_specific_pattern_wins_when_generic_also_matches():
    # Matches both "hit your session limit" and "usage limit reached";
    # the specific signature must win because it is listed first in
    # _SIGNATURES - pins the ordering as load-bearing.
    text = "You hit your session limit; usage limit reached."
    err = classify(text)
    assert isinstance(err, RateLimited)
    assert err.scope == "five_hour"


def test_reset_zone_utc_is_recognized():
    # UTC has no "/" - the likeliest zone on an unattended headless host.
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    got = parse_reset("resets 11:10am (UTC)", now=now)
    assert got == datetime(2026, 9, 4, 11, 10, tzinfo=timezone.utc)


def test_reset_zone_multi_segment_is_recognized():
    # America/Indiana/Indianapolis has two "/"s.
    tz = ZoneInfo("America/Indiana/Indianapolis")
    now = datetime(2026, 9, 4, 8, 0, tzinfo=tz)
    got = parse_reset("resets 11:10am (America/Indiana/Indianapolis)", now=now)
    assert got == datetime(2026, 9, 4, 11, 10, tzinfo=tz).astimezone(timezone.utc)


def test_rate_limited_is_a_herder_error():
    # Load-bearing: cli.py's `except (LlamaError, HerderError)` boundary, and
    # its per-show `except RateLimited` (checked first because RateLimited
    # subclasses HerderError), both rely on this subclassing. If it silently
    # broke, a rate limit would surface as an unhandled traceback instead of
    # a clean pause/exit - nothing else in the suite pins it.
    assert issubclass(RateLimited, HerderError)
    assert isinstance(RateLimited("boom"), HerderError)
