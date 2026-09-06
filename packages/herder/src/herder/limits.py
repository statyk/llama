"""Recognizing a usage-window exhaustion in a backend failure.

The 5-hour signature was captured from a live run on 2026-09-04:

    claude exited 1: You've hit your session limit · resets 11:10am (America/New_York)

Three things follow. Exit code 1, so it arrives through claude_cli's
returncode branch. "session limit" names the window, matching the usage
API's own vocabulary (`kind: "session"` for the 5-hour bucket,
`kind: "weekly_all"` for the 7-day one). And the reset instant is IN the
message, so nothing here needs to read Claude Code's internal state files.

A false positive is worse than a false negative: mistaking a transient
error for a window exhaustion idles a run for hours. So the patterns are
narrow, and the dropped-connection message is pinned as a negative test.
"""
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from herder.provider import HerderError

# A 5-hour window's reset is always within 5 hours. Anything further out
# means the parse or the clock is wrong; parsing must never be able to
# manufacture a day-long sleep.
MAX_RESET_AHEAD_S = 5.5 * 3600

# Most specific first: classify() returns on the first match, so ordering
# is load-bearing whenever a text could match more than one pattern (see
# test_specific_pattern_wins_when_generic_also_matches).
_SIGNATURES: tuple[tuple[re.Pattern, str | None], ...] = (
    # Measured 2026-09-04. Do not loosen without a new capture.
    (re.compile(r"hit your session limit", re.I), "five_hour"),
    # Unverified: the 7-day variant's wording has not been observed. The
    # scope is still useful when it matches, and a miss just falls through
    # to scope=None, which pauses without naming a window.
    (re.compile(r"(weekly|7-day|seven[ -]day) limit", re.I), "seven_day"),
    # Unverified: wording not observed either. Deliberately the loosest of
    # the three - the fallback for a limit whose window we cannot name.
    (re.compile(r"usage limit reached", re.I), None),
)

# Only the measured message shape is handled on purpose: "resets at ...",
# "resets 11am" with no minutes, and a missing zone all correctly fail to
# match and yield None rather than guessing. The zone group allows any
# number of "/segment" pieces (`UTC`, `America/New_York`,
# `America/Indiana/Indianapolis`) and digits within a segment (`Etc/GMT+5`).
_RESET_RE = re.compile(
    r"resets\s+(\d{1,2}):(\d{2})\s*([ap]m)\s*"
    r"\(([A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*)\)", re.I)

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

# The /usage form: a date, an optional minute ("7am" is what the weekly line
# actually renders), then the same meridiem-and-zone tail as the refusal form.
# Tried FIRST because it is the more specific of the two; the time-only
# pattern cannot match it anyway, since "Sep" is not a digit.
_RESET_DATED_RE = re.compile(
    r"resets\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})\s+at\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*"
    r"\(([A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*)\)", re.I)


def _hour24(hour12: str, meridiem: str) -> int:
    return int(hour12) % 12 + (12 if meridiem.lower() == "pm" else 0)


def _dated_target(m: re.Match, now: datetime) -> datetime | None:
    """The instant named by a dated clause, resolved to the next future year.

    The year is absent from the text, so it is inferred: this year if that
    lands in the future, else next. A date that has already passed therefore
    resolves a full year out, which no caller's bound admits - so a stale or
    clock-skewed date degrades to None rather than to a long sleep.
    """
    month_s, day_s, hour_s, minute_s, meridiem, zone_name = m.groups()
    month = _MONTHS.get(month_s[:3].lower())
    if month is None:
        return None
    try:
        tz = ZoneInfo(zone_name)
    except Exception:  # noqa: BLE001 - unknown zone must not crash the caller
        return None
    minute = int(minute_s) if minute_s else 0
    if not 0 <= minute <= 59:
        return None
    local = now.astimezone(tz)
    for year in (local.year, local.year + 1):
        try:
            target = datetime(year, month, int(day_s),
                              _hour24(hour_s, meridiem), minute, tzinfo=tz)
        except ValueError:      # e.g. Feb 29 in a non-leap year
            continue
        if target > local:
            return target
    return None


class RateLimited(HerderError):
    """The backend refused because a usage window is exhausted.

    Distinct from every other HerderError in exactly two ways that matter:
    retrying it is pointless (see tasks._with_transport_retry) and it names
    a time after which retrying is not pointless.
    """

    def __init__(self, message: str, scope: str | None = None,
                 resets_at: datetime | None = None):
        super().__init__(message)
        self.scope = scope
        self.resets_at = resets_at


def parse_reset(text: str, now: datetime | None = None,
                max_ahead_s: float = MAX_RESET_AHEAD_S) -> datetime | None:
    """The UTC instant named by a `resets ...` clause, in either shape.

    Two forms are accepted: the refusal message's time-only
    `resets 11:10am (America/New_York)`, and /usage's dated
    `resets Sep 5 at 5:20pm (America/New_York)` (whose minutes are
    optional - the weekly line renders as `7am`). Both resolve to the next
    future occurrence in the zone the message names, which is not
    necessarily the caller's.

    `max_ahead_s` is per-call because the bound is a property of the WINDOW,
    not of the parser: a 5-hour reset is always within ~5 hours, a weekly one
    is legitimately up to seven days out. A single shared constant would
    either reject every valid weekly reading or let a mis-parsed session
    reset manufacture a week-long sleep.
    """
    now = now or datetime.now(timezone.utc)
    dated = _RESET_DATED_RE.search(text)
    if dated is not None:
        target = _dated_target(dated, now)
        if target is None:
            return None
    else:
        m = _RESET_RE.search(text)
        if not m:
            return None
        hour12, minute, meridiem, zone_name = m.groups()
        try:
            tz = ZoneInfo(zone_name)
        except Exception:  # noqa: BLE001 - see _dated_target
            return None
        if not 0 <= int(minute) <= 59:
            return None
        local = now.astimezone(tz)
        target = datetime.combine(local.date(),
                                  time(_hour24(hour12, meridiem), int(minute)),
                                  tzinfo=tz)
        if target <= local:
            target = datetime.combine(local.date() + timedelta(days=1),
                                      time(_hour24(hour12, meridiem), int(minute)),
                                      tzinfo=tz)
    out = target.astimezone(timezone.utc)
    if (out - now.astimezone(timezone.utc)).total_seconds() > max_ahead_s:
        return None
    return out


def classify(text: str, now: datetime | None = None) -> RateLimited | None:
    """A RateLimited when the failure text names an exhausted window, else None."""
    for pattern, scope in _SIGNATURES:
        if pattern.search(text):
            return RateLimited(text.strip()[:500], scope=scope,
                               resets_at=parse_reset(text, now))
    return None
