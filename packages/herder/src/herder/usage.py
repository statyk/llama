"""Reading the account's live usage meters.

Deliberately separate from herder.limits. `limits` is about REFUSALS -
something has already gone wrong and the message is the evidence. This
module is about HEADROOM - nothing has gone wrong yet and the reading is a
measurement. Different lifetimes, different failure modes, different callers.

The source is `claude -p "/usage"`, a live GET /api/oauth/usage: measured
2026-09-05 on CLI 2.1.252 at num_turns 0, total_cost_usd 0, every token
count 0, ~0.5-3 s. It is NOT an inference call, so it may be taken at every
show boundary.

Deliberately NOT read: ~/.claude.json's cachedUsageUtilization. It is
write-throttled to five minutes, does not refresh when /usage runs, and was
measured on 2026-09-05 serving an ALREADY-EXPIRED window (23% against a
rolled-over window while the live read said 10%). It looks correct exactly
when someone is watching it and goes wrong during the unattended run pacing
exists for.
"""
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

from herder.limits import parse_reset

# Per-window bounds on how far ahead a reset may legitimately sit. See
# limits.parse_reset's max_ahead_s for why this is not one constant.
FIVE_HOUR_MAX_AHEAD_S = 5.5 * 3600
SEVEN_DAY_MAX_AHEAD_S = 7.5 * 86400

# When the fetch fails, /usage still exits 0 and prints cached numbers with
# this banner. An exit-code check alone would accept them.
STALE_MARKER = "Showing last-known usage"

_SESSION_RE = re.compile(r"^Current session:\s*(\d+)%\s*used(.*)$", re.M)
_WEEK_ALL_RE = re.compile(r"^Current week \(all models\):\s*(\d+)%\s*used(.*)$", re.M)
# The lookahead is load-bearing: without it this also matches the all-models
# line and reports a sub-meter named "all models" that does not exist.
_WEEK_MODEL_RE = re.compile(
    r"^Current week \((?!all models\))([^)]+)\):\s*(\d+)%\s*used(.*)$", re.M)


@dataclass(frozen=True)
class Meter:
    percent: int
    resets_at: datetime | None


@dataclass(frozen=True)
class UsageReading:
    five_hour: Meter | None
    seven_day: Meter | None
    per_model: dict[str, Meter] = field(default_factory=dict)
    fetched_at: datetime | None = None


def parse_usage_text(text: str, now: datetime | None = None) -> UsageReading | None:
    """A reading from /usage's prose, or None when it cannot be trusted.

    Never raises. Returns None on a stale banner, a missing session line, or
    anything else unrecognizable - a caller must not have to distinguish
    "no signal" from "bad signal", because it treats them identically.
    """
    now = now or datetime.now(timezone.utc)
    if not text or STALE_MARKER in text:
        return None
    m = _SESSION_RE.search(text)
    if not m:
        return None
    five = Meter(int(m.group(1)),
                 parse_reset(m.group(2), now=now, max_ahead_s=FIVE_HOUR_MAX_AHEAD_S))
    seven = None
    mw = _WEEK_ALL_RE.search(text)
    if mw:
        seven = Meter(int(mw.group(1)),
                      parse_reset(mw.group(2), now=now,
                                  max_ahead_s=SEVEN_DAY_MAX_AHEAD_S))
    per_model = {
        mm.group(1).strip(): Meter(int(mm.group(2)),
                                   parse_reset(mm.group(3), now=now,
                                               max_ahead_s=SEVEN_DAY_MAX_AHEAD_S))
        for mm in _WEEK_MODEL_RE.finditer(text)
    }
    return UsageReading(five_hour=five, seven_day=seven, per_model=per_model,
                        fetched_at=now)
