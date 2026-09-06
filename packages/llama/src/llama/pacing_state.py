"""What a show costs, learned from the meter across show boundaries.

A reading taken AFTER a show minus the one taken before it is exactly that
show's cost. Both readings are taken in `cli._execute`'s show loop: the
`reading_before` bound just above the show lock, and the second `_meter`
call passed straight into `record` once `_process` has returned. That is a
cleaner attribution than any rate estimate over time, and it is available
for free because the meter read costs nothing.

Before/after, not before-N/before-N+1: the gate's own meter read and this
module's `record` write both happen BETWEEN shows, so a boundary measured
from one show's start to the next show's start would fold them into every
sample -- a constant that has nothing to do with the show it is attributed
to. Two reads per show buys that precision, and a read is not an inference
call (see herder.usage).

Known bias, accepted: the meter is account-wide, so a run paced while the
operator works attributes their burn to llama and over-estimates. That
pauses EARLY, which is the safe direction. Do not try to correct it by
subtracting llama's own dollar spend - no dollars-to-percent conversion
exists (see the phase 2 spec's "Measured signals").
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from llama.locks import file_lock
from llama.workspace import write_artifact

STATE_NAME = "pacing-state.json"

# Weighted toward recent shows without letting one outlier swing the gate.
EWMA_ALPHA = 0.4


@dataclass(frozen=True)
class PacingState:
    per_show_delta: float | None = None
    samples: int = 0


def _five(reading):
    return getattr(reading, "five_hour", None) if reading is not None else None


def observe(before, after, state: PacingState) -> PacingState:
    """Fold one show boundary into the estimate, or decline to.

    A boundary contributes ONLY when both readings succeeded and `resets_at`
    is unchanged between them. A window rollover makes the delta negative or
    nonsensical; folding it in would drag the estimate toward zero, and an
    under-estimate is precisely what lets a run walk into the wall.
    """
    b, a = _five(before), _five(after)
    if b is None or a is None or b.resets_at != a.resets_at:
        return state
    delta = float(a.percent - b.percent)
    if delta < 0:
        return state
    if state.per_show_delta is None:
        return PacingState(delta, 1)
    smoothed = state.per_show_delta + EWMA_ALPHA * (delta - state.per_show_delta)
    return PacingState(smoothed, state.samples + 1)


def _valid_persisted_delta(value) -> bool:
    """True when `value` is a JSON-decoded `per_show_delta` we can trust.

    `None` is the valid "no estimate yet" sentinel and is accepted here; the
    caller distinguishes it. Everything else must be a real, finite,
    non-negative number. `bool` is deliberately rejected even though it is a
    Python subclass of `int` - a JSON `true`/`false` is not a percentage
    delta, and `decide()`'s precondition is about numeric sign, not
    truthiness, so letting `True` through as `1.0` would be accepting a type
    the producer (`observe`) can never emit.
    """
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value >= 0


def read_state(root: Path) -> PacingState:
    """The persisted estimate, or an empty one. Never raises.

    A negative, non-numeric, or non-finite `per_show_delta` is corruption -
    `observe` (the sole computed-path producer) never writes one - so rather
    than clamp or coerce it, an untrustworthy value degrades to no estimate
    at all, exactly like an unreadable file. `decide()` relies on this: its
    non-negative precondition holds for every `PacingState` this function
    can return.
    """
    try:
        data = json.loads((root / STATE_NAME).read_text())
        delta = data.get("per_show_delta")
        if not _valid_persisted_delta(delta):
            return PacingState(None, 0)
        samples = int(data.get("samples", 0))
        return PacingState(float(delta) if delta is not None else None, samples)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return PacingState(None, 0)


def record(root: Path, before, after) -> PacingState:
    """Observe one boundary and persist the result.

    Read-modify-write on a workspace that is explicitly parallel-safe, so it
    takes the same advisory lock discipline as the ledger. What the lock
    prevents is a LOST UPDATE: unlocked, two concurrent runs read the same
    state, and the later write wins with the earlier run's boundary folded
    into nothing -- one sample silently discarded from an estimate whose
    whole value is how many boundaries it has seen.

    Not the same thing as the account-wide meter bias in the module
    docstring: each run does see the other's burn in its own readings, but
    that is a property of the meter and no lock can fix it.
    """
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / (STATE_NAME + ".lock")):
        state = observe(before, after, read_state(root))
        write_artifact(root / STATE_NAME, json.dumps(
            {"per_show_delta": state.per_show_delta, "samples": state.samples},
            indent=2))
        return state
