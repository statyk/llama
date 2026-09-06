"""Waiting out a usage window.

Phase 1 is the reactive half only: llama learns the reset time from the
backend's own refusal (herder.limits) and either sleeps through it or
checkpoints. The proactive half - reading Claude Code's usage cache,
projecting per-show cost, pausing BEFORE a window is exhausted - is
phase 2 and deliberately absent here.
"""
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_sleep = time.sleep                                  # indirection for tests
def _now() -> datetime:                              # noqa: E302 - paired with _sleep
    return datetime.now(timezone.utc)


def parse_duration(text: str) -> float:
    """Seconds from `6h`, `90m`, `5h30m`, `45s`. Raises ValueError otherwise.

    Internal whitespace is ignored, so `6h 0m` parses: that is the shape
    `format_delta` emits, and the pause messages print such a value one line
    above a command the operator is meant to paste. Humans type the space
    too. Whitespace is removed BEFORE matching, so the `$` anchor is
    untouched and every rejection still rejects - `6h banana` becomes
    `6hbanana`, which the anchor refuses, and a whitespace-only string
    becomes empty, which the `any(m.groups())` guard refuses.
    """
    m = _DURATION_RE.match(re.sub(r"\s+", "", text or ""))
    if not m or not any(m.groups()):
        raise ValueError(f"not a duration: {text!r} (use forms like 6h, 90m, 5h30m)")
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_delta(seconds: float) -> str:
    """`4h 12m` / `12m` / `1m` - never bare seconds, which read as noise."""
    total = max(int(seconds), 60)
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def duration_arg(seconds: float) -> str:
    """A duration rendered so it can be handed straight back as `--max-wait`.

    `format_delta` is for prose and emits `2h 0m`, which parse_duration
    rejects on the space - so the copy-pasteable hint a checkpoint prints
    would not run. This one has no space and rounds UP to the minute: a
    floored value can be shorter than the wait it was printed for, so
    re-running with it would checkpoint again for the same reason.
    """
    minutes = max(1, math.ceil(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes}m"
    return f"{hours}h{minutes}m" if minutes else f"{hours}h"


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


@dataclass(frozen=True)
class PaceOptions:
    """The pacing decisions a run is made with, resolved once at its start.

    Frozen because a run must not change its own mind mid-loop: `_execute`
    consults these on every pause, and a value that drifted would make the
    pause after a sleep behave differently from the first one for reasons
    nothing recorded.
    """

    enabled: bool          # False restores the pre-pacing behaviour: a limit fails the show
    wait: bool             # sleep through a reset, rather than checkpoint and exit
    max_wait_s: float      # never sleep longer than this; a longer wait checkpoints
    unknown_reset_wait_s: float   # how long to wait when the refusal named no reset
    reset_skew_s: float    # padding past the named reset, so we do not race its clock
    five_hour_ceiling: float      # pause when the 5h meter + next show crosses this
    seven_day_ceiling: float      # same for the weekly meter; checked first


def pace_options(config, wait: bool | None = None,
                 max_wait: str | None = None,
                 no_pacing: bool = False) -> PaceOptions:
    """Config defaults with the CLI flags layered on top.

    `None` means "the flag was not given", so a `--no-wait` can turn off a
    config `wait = true` and vice versa. Raises ValueError on a malformed
    `--max-wait`, which callers surface before the run starts rather than
    four shows in.
    """
    cfg = config.pacing
    return PaceOptions(
        enabled=cfg.enabled and not no_pacing,
        wait=cfg.wait if wait is None else wait,
        max_wait_s=parse_duration(max_wait or cfg.max_wait),
        unknown_reset_wait_s=parse_duration(cfg.unknown_reset_wait),
        reset_skew_s=parse_duration(cfg.reset_skew),
        five_hour_ceiling=cfg.five_hour_ceiling,
        seven_day_ceiling=cfg.seven_day_ceiling,
    )


def resume_at(err, pace: PaceOptions) -> datetime:
    """When to come back after a refusal: the reset it named, else a default.

    The skew keeps us from racing the window's own clock.

    A naive `resets_at` is treated as no reset at all rather than coerced to
    a zone. It cannot come from `herder.limits.parse_reset`, which always
    resolves to UTC, so it would mean some other producer guessed - and
    guessing again here (UTC? local?) risks waking hours early or hours
    late. The default wait is a known-safe answer; `sleep_until` refuses the
    naive value outright, which would crash the pause instead of pausing.
    """
    when = getattr(err, "resets_at", None)
    if when is None or when.tzinfo is None:
        return _now() + timedelta(seconds=pace.unknown_reset_wait_s)
    return when + timedelta(seconds=pace.reset_skew_s)


@dataclass(frozen=True)
class Proceed:
    """Nothing in the way; run the next unit of work."""


@dataclass(frozen=True)
class PauseUntil:
    when: datetime
    scope: str
    reason: str


@dataclass(frozen=True)
class Progress:
    """Everything the policy knows about the run, as counters only.

    No clock, no IO - so the whole policy is a table test.
    """
    per_show_delta: float | None = None      # learned EWMA; None until observed


def _pause(meter, ceiling, scope, projected, now, opts):
    """A PauseUntil when this meter's projection crosses its ceiling, else None."""
    if meter is None or meter.percent + projected <= ceiling:
        return None
    when = (meter.resets_at + timedelta(seconds=opts.reset_skew_s)
            if meter.resets_at is not None
            else now + timedelta(seconds=opts.unknown_reset_wait_s))
    reason = (f"{'weekly' if scope == 'seven_day' else '5h'} window at "
              f"{meter.percent}%"
              + (f", est {projected:.1f}%/show" if projected else ""))
    return PauseUntil(when, scope, reason)


def decide(now: datetime, reading, progress: Progress,
           opts: PaceOptions) -> Proceed | PauseUntil:
    """Whether to start the next unit of work, or wait for a window to reset.

    Rules in priority order, first match wins:

    1. Weekly ceiling. Checked FIRST because a weekly exhaustion cannot be
       slept off at the 5-hour reset - resuming there would land in a window
       that is still empty.
    2. Session gate, on the PROJECTION rather than the bare percentage: that
       is what stops a run starting a show it cannot finish.
    3. Proceed.

    A missing reading proceeds rather than guessing. The reactive path
    (herder.limits.RateLimited, caught by the caller) remains the backstop,
    so a blind boundary costs one refused show, not a wrong multi-hour idle.
    """
    if not opts.enabled or reading is None:
        return Proceed()
    projected = progress.per_show_delta or 0.0
    return (_pause(reading.seven_day, opts.seven_day_ceiling, "seven_day",
                   projected, now, opts)
            or _pause(reading.five_hour, opts.five_hour_ceiling, "five_hour",
                      projected, now, opts)
            or Proceed())
