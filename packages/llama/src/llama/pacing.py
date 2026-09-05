"""Waiting out a usage window.

Phase 1 is the reactive half only: llama learns the reset time from the
backend's own refusal (herder.limits) and either sleeps through it or
checkpoints. The proactive half - reading Claude Code's usage cache,
projecting per-show cost, pausing BEFORE a window is exhausted - is
phase 2 and deliberately absent here.
"""
import re
import time
from datetime import datetime, timezone

_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_sleep = time.sleep                                  # indirection for tests
def _now() -> datetime:                              # noqa: E302 - paired with _sleep
    return datetime.now(timezone.utc)


def parse_duration(text: str) -> float:
    """Seconds from `6h`, `90m`, `5h30m`, `45s`. Raises ValueError otherwise."""
    m = _DURATION_RE.match((text or "").strip())
    if not m or not any(m.groups()):
        raise ValueError(f"not a duration: {text!r} (use forms like 6h, 90m, 5h30m)")
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_delta(seconds: float) -> str:
    """`4h 12m` / `12m` / `1m` - never bare seconds, which read as noise."""
    total = max(int(seconds), 60)
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def sleep_until(when: datetime, echo, chunk_s: float = 900) -> None:
    """Sleep until `when`, reporting what is left after each nap.

    Chunked so a multi-hour wait is not a dead prompt, and so a
    KeyboardInterrupt lands promptly. The caller handles that interrupt.

    `when` must be timezone-aware. A naive value is ambiguous (local time or
    UTC?) and this function refuses to guess: silently treating it as UTC
    would risk a multi-hour wake-time error that no one would notice until
    the run was hours late or hours early. Raise, don't coerce.
    """
    if when.tzinfo is None:
        raise ValueError(f"sleep_until requires a timezone-aware datetime, got naive {when!r}")
    while True:
        remaining = (when - _now()).total_seconds()
        if remaining <= 0:
            return
        _sleep(min(remaining, chunk_s))
        left = (when - _now()).total_seconds()
        if left > 0:
            echo(f"  … waiting, {format_delta(left)} left")
