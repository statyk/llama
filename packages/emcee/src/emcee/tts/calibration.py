"""Per-model calibration for the mlx_audio runaway guard.

The guard (spec section 3) caps each request's max_tokens in proportion to
the text's length and checks the returned audio's duration against that
length. Tokens become seconds through the model's codec frame rate, so every
constant is per model: emcee carries a table of calibrated mlx models, and
resolving to a model outside it is a configuration error
("mlx_audio model not calibrated for the runaway guard").

Lengths are measured in characters of whitespace-collapsed text (see
`text_units`, added with the guard math).
"""
import math
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class ModelCalibration:
    frame_rate_hz: float   # codec frames (= generated tokens) per second of audio
    cap_floor_s: float     # max_tokens covers cap_floor_s + cap_s_per_char * chars
    cap_s_per_char: float
    max_floor_s: float     # longer than max_floor_s + max_s_per_char * chars: implausibly long
    max_s_per_char: float
    min_s_per_char: float  # shorter than min_s_per_char * chars - min_slack_s: implausibly short
    min_slack_s: float
    cap_margin_s: float    # within cap_margin_s of the cap's duration: a capped runaway

    def __post_init__(self):
        if self.frame_rate_hz <= 0:
            raise ValueError("frame_rate_hz must be positive")
        for f in fields(self):
            if getattr(self, f.name) < 0:
                raise ValueError(f"{f.name} must not be negative")
        # The cap must sit above every plausible clip, or the cap-margin check
        # would fire on legitimate long sentences.
        if self.cap_s_per_char < self.max_s_per_char:
            raise ValueError("cap_s_per_char must be >= max_s_per_char")
        if self.cap_floor_s - self.cap_margin_s <= self.max_floor_s:
            raise ValueError("cap_floor_s - cap_margin_s must exceed max_floor_s")


# Model id -> calibration. EMPTY until the calibration run (implementation
# plan Task 12) measures the first entry: nothing voices on mlx_audio with
# guessed constants. Tests register a test-only entry (tests/mlx_helpers.py).
CALIBRATED_MODELS: dict[str, ModelCalibration] = {}


def text_units(text: str) -> int:
    """The length the guard scales with: characters of whitespace-collapsed text."""
    return len(" ".join(text.split()))


def max_tokens_for(cal: ModelCalibration, text: str) -> int:
    """The request's max_tokens: the cap's duration in codec frames. Always
    sent -- the server's default of 1200 (~96 s) silently truncates long
    unchunked segments."""
    return math.ceil((cal.cap_floor_s + cal.cap_s_per_char * text_units(text)) * cal.frame_rate_hz)


def cap_seconds(cal: ModelCalibration, max_tokens: int) -> float:
    return max_tokens / cal.frame_rate_hz


def guard_problem(cal: ModelCalibration, text: str, seconds: float,
                  max_tokens: int) -> str | None:
    """Why `seconds` of audio is implausible for `text`, or None. The cap
    check comes first: a runaway that ran into max_tokens would otherwise
    read as merely long (or, with a cap close to the limit, pass). An empty
    clip is checked before everything: a short text's lower bound floors at
    0 s, so the short check alone would accept it."""
    if seconds <= 0:
        return f"clip is empty ({seconds:.1f}s of audio)"
    n = text_units(text)
    cap = cap_seconds(cal, max_tokens)
    if seconds >= cap - cal.cap_margin_s:
        return f"clip is {seconds:.1f}s, at the {cap:.1f}s token cap (a capped runaway)"
    longest = cal.max_floor_s + cal.max_s_per_char * n
    if seconds > longest:
        return f"clip is {seconds:.1f}s, implausibly long for {n} characters (limit {longest:.1f}s)"
    shortest = max(0.0, cal.min_s_per_char * n - cal.min_slack_s)
    if seconds < shortest:
        return (f"clip is {seconds:.1f}s, implausibly short for {n} characters "
                f"(minimum {shortest:.1f}s)")
    return None
