"""Recognizing a usage-window exhaustion in a backend failure.

The 5-hour signature was captured from a live run on 2026-09-04:

    claude exited 1: You've hit your session limit - resets 11:10am (America/New_York)

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

_SIGNATURES: tuple[tuple[re.Pattern, str | None], ...] = (
    # Measured 2026-09-04. Do not loosen without a new capture.
    (re.compile(r"hit your session limit", re.I), "five_hour"),
    # Unverified: the 7-day variant's wording has not been observed. The
    # scope is still useful when it matches, and a miss just falls through
    # to scope=None, which pauses without naming a window.
    (re.compile(r"(weekly|7-day|seven[ -]day) limit", re.I), "seven_day"),
    (re.compile(r"usage limit reached", re.I), None),
)

_RESET_RE = re.compile(
    r"resets\s+(\d{1,2}):(\d{2})\s*([ap]m)\s*\(([A-Za-z_]+/[A-Za-z_+-]+)\)", re.I)


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


def parse_reset(text: str, now: datetime | None = None) -> datetime | None:
    """The UTC instant named by a `resets 11:10am (America/New_York)` clause.

    Resolved to the next future occurrence of that wall-clock time in the
    zone the message names - which is not necessarily the caller's zone.
    Returns None when absent, unparseable, or further out than
    MAX_RESET_AHEAD_S.
    """
    m = _RESET_RE.search(text)
    if not m:
        return None
    hour12, minute, meridiem, zone_name = m.groups()
    try:
        tz = ZoneInfo(zone_name)
    except Exception:
        return None
    hour = int(hour12) % 12 + (12 if meridiem.lower() == "pm" else 0)
    if not 0 <= int(minute) <= 59:
        return None
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    target = datetime.combine(local.date(), time(hour, int(minute)), tzinfo=tz)
    if target <= local:
        target = datetime.combine(local.date() + timedelta(days=1),
                                  time(hour, int(minute)), tzinfo=tz)
    out = target.astimezone(timezone.utc)
    if (out - now.astimezone(timezone.utc)).total_seconds() > MAX_RESET_AHEAD_S:
        return None
    return out


def classify(text: str, now: datetime | None = None) -> RateLimited | None:
    """A RateLimited when the failure text names an exhausted window, else None."""
    for pattern, scope in _SIGNATURES:
        if pattern.search(text):
            return RateLimited(text.strip()[:500], scope=scope,
                               resets_at=parse_reset(text, now))
    return None
