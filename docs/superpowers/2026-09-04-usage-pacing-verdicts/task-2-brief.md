### Task 2: RateLimited classification and reset parsing

Pure functions only — no wiring into the provider yet, so a reviewer can judge the classifier on its own.

**Files:**
- Create: `packages/herder/src/herder/limits.py`
- Create: `packages/herder/tests/test_limits.py`
- Modify: `packages/herder/src/herder/__init__.py`

**Interfaces:**
- Consumes: `HerderError` from `herder.provider`.
- Produces: `RateLimited(HerderError)` with attributes `scope: str | None` and `resets_at: datetime | None`; `classify(text: str, now: datetime | None = None) -> RateLimited | None`; `parse_reset(text: str, now: datetime | None = None) -> datetime | None`. Tasks 3, 4 and 7 all import `RateLimited`.

- [ ] **Step 1: Write the failing test**

Create `packages/herder/tests/test_limits.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'herder.limits'`

- [ ] **Step 3: Write minimal implementation**

Create `packages/herder/src/herder/limits.py`:

```python
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
```

- [ ] **Step 4: Export it**

In `packages/herder/src/herder/__init__.py`, add after the `from herder.fake import FakeProvider` line:

```python
from herder.limits import RateLimited, classify, parse_reset
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q`
Expected: 10 passed

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: all green, no change in count except the 10 new tests.

- [ ] **Step 7: Commit**

```bash
git add packages/herder/src/herder/limits.py packages/herder/src/herder/__init__.py packages/herder/tests/test_limits.py
git commit -m "feat(herder): classify usage-window exhaustion as RateLimited"
```

---

