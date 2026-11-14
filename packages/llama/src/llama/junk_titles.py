"""Junk-title drop rule: pure planning of which gathered tracks to drop on
their title alone (tuning / crowd noise / silence anywhere; intro words at a
show or set start; outro words at the show end).

Authority: docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md, "The
rule". The last track of the list a rule is judged on, if its title starts with an
arrow, is never dropped under any rule (A, B or C). No I/O; imports only
llama.junk, llama.titles and the stdlib."""
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median as _median

from llama import junk
from llama.titles import clean_tag_title

REASON = "junk title"
HOLD_PREFIX = "junk-title drop held for review: "

# Breaker constants: operator-set, do not retune. A drop holds when at least
# BREAKER_NEEDED of the three strict '>' tests pass.
BREAKER_MIN_SEC = 360.0
BREAKER_SHOW_FRACTION = 0.05
BREAKER_MEDIAN_MULTIPLE = 1.0
BREAKER_NEEDED = 2

# Operator's vocabulary; never widen.
_W = r"(?:tuning(?:\s*up)?|tune\s*up|crowd(?:\s+noise)?|silence)"
_INTRO = r"(?:intro(?:duction)?s?)"
_OUTRO = r"(?:outros?)"
_A = re.compile(_W, re.I)
_B = re.compile(rf"{_W}|{_INTRO}", re.I)
_C = re.compile(rf"{_W}|{_OUTRO}", re.I)


@dataclass(frozen=True)
class DropInput:
    filename: str
    title: str
    set: str
    duration_sec: float | None
    raw_arrow: bool = False


@dataclass(frozen=True)
class Drop:
    position: int   # 0-based, pre-drop
    rule: str       # "A" | "B" | "C"


@dataclass(frozen=True)
class JunkDrop:
    filename: str
    title: str
    set: str
    duration_sec: float | None
    rule: str
    position: int
    after_track: int
    held: bool


def is_a_title(title: str) -> bool:
    ps = junk.parts(clean_tag_title(title))
    return bool(ps) and all(_A.fullmatch(p) for p in ps)


def is_intro_title(title: str) -> bool:
    ps = junk.parts(clean_tag_title(title))
    return bool(ps) and all(_B.fullmatch(p) for p in ps)


def is_outro_title(title: str) -> bool:
    ps = junk.parts(clean_tag_title(title))
    return bool(ps) and all(_C.fullmatch(p) for p in ps)


def trailing_arrow(title: str, *, raw_arrow: bool = False) -> bool:
    return raw_arrow or bool(junk.TRAILING_ARROW.search(junk.TIME_PAREN.sub("", title)))


def leading_arrow(title: str) -> bool:
    return bool(junk.LEADING_ARROW.search(junk.TIME_PAREN.sub("", title)))


def plan_drops(tracks: Sequence[DropInput], *,
               include: frozenset[str] = frozenset()) -> list[Drop]:
    n = len(tracks)
    drops: dict[int, str] = {}
    for i, t in enumerate(tracks):
        if t.filename in include or trailing_arrow(t.title, raw_arrow=t.raw_arrow):
            continue
        if i == n - 1 and leading_arrow(t.title):
            continue
        if is_a_title(t.title):
            drops[i] = "A"
    rest = [i for i in range(n) if i not in drops]
    for k, i in enumerate(rest):
        t = tracks[i]
        first = k == 0 or tracks[rest[k - 1]].set != t.set
        if (first and t.filename not in include
                and not (k == len(rest) - 1 and leading_arrow(t.title))
                and not trailing_arrow(t.title, raw_arrow=t.raw_arrow)
                and is_intro_title(t.title)):
            drops[i] = "B"
    if rest:
        i = rest[-1]
        t = tracks[i]
        if (i not in drops and t.filename not in include
                and not trailing_arrow(t.title, raw_arrow=t.raw_arrow)
                and not leading_arrow(t.title) and is_outro_title(t.title)):
            drops[i] = "C"
    return [Drop(p, drops[p]) for p in sorted(drops)]


def show_stats(durations: Sequence[float | None]) -> tuple[float, float]:
    vals = [float(d or 0) for d in durations]
    if not vals:
        return (0.0, 0.0)
    return (sum(vals), float(_median(vals)))


def held(duration: float | None, *, total: float, median: float) -> bool:
    d = float(duration or 0)
    hits = (d > BREAKER_MIN_SEC) + (d > BREAKER_SHOW_FRACTION * total) \
        + (d > BREAKER_MEDIAN_MULTIPLE * median)
    return hits >= BREAKER_NEEDED


def hold_flag(drop: JunkDrop, *, total: float, median: float) -> str:
    d = float(drop.duration_sec or 0)
    s = int(round(d))
    pct = f"{100 * d / total:.1f}" if total else "0.0"
    x = f"{d / median:.2f}" if median else "0.00"
    return (f"{HOLD_PREFIX}'{drop.title}' ({s // 60}:{s % 60:02d}, {pct}% of show, "
            f"{x}x median) file {drop.filename}")


_REF = re.compile(
    r"\btracks?(?:\(s\))?\s+(\d+-\d+(?!\d|:\d)|\d+(?:\s*,\s*\d+)*(?!\d))")


def renumber_text(text: str, numbers: Mapping[int, int | None]) -> str:
    def sub(m: re.Match) -> str:
        body = m.group(1)
        word = m.group(0).split()[0]  # track / tracks / track(s)
        if "-" in body:
            a, b = (int(x) for x in re.split(r"\s*-\s*", body))
            members = list(range(a, b + 1))
            if not any(k in numbers for k in members):
                return m.group(0)
            kept = [numbers.get(k, k) for k in members if numbers.get(k, k) is not None]
            if not kept:
                return "dropped tracks"
            if len(kept) == 1 or kept[0] == kept[-1]:
                return f"track {kept[0]}"
            return f"{word} {kept[0]}-{kept[-1]}"
        nums = [int(x) for x in re.split(r"\s*,\s*", body)]
        if all(numbers.get(k, k) == k for k in nums):
            return m.group(0)
        mapped = [numbers.get(k, k) for k in nums]
        kept = [k for k in mapped if k is not None]
        if len(nums) == 1:
            return f"{word} {kept[0]}" if kept else "dropped track"
        if not kept:
            return "dropped tracks"
        return f"{word} " + ", ".join(str(k) for k in kept)

    return _REF.sub(sub, text)
