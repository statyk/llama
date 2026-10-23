"""Entry cleaning for the taper's description list (title hygiene, piece 3, task 1).

Pure: no IO, no gather wiring. `clean_one`/`clean_entries` produce the ONE cleaned form
check 1 tests and D ships; `written_seconds` reads the single written duration;
`is_header_shape` says whether an entry is a set/disc header rather than a title.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass

from llama import taper
from llama.titles import _ENUMERATED_MIN_COVERAGE, _ENUMERATED_MIN_FILES

_T = r"\d{1,3}(?::\d{2}){1,2}"  # m:ss or h:mm:ss (minutes may be 3 digits)
_BRACKETED = re.compile(rf"\s*[\[(]\s*({_T})\s*[\])]")
_LEAD_DASH = re.compile(rf"^\s*({_T})\s+[-–—]\s+(?=\S)")
_TAB_TIME = re.compile(rf"(?<=\S)\t+\s*({_T})\s*$")
_TRAIL_DOT = re.compile(r"(?<=\S)(?:\t+|\s{2,})(\d{1,3}\.\d{2})\s*$")
_TRAIL_TIME = re.compile(rf"(?<=\S)\s+({_T})\s*$")
_WHOLE_TIME = re.compile(rf"^\s*{_T}\s*$")

_ENTRY_LEADER = re.compile(r"^(?:\.\d{1,3}|\d{1,3}[-.)])\s*(?=[^\d\s])")
_FILLER_MARK = re.compile(r"^\s*filler\s*:\s*", re.I)
_FOOTNOTE = re.compile(r"\s*\(\s*(?:\d{1,2}|[*#^+~@$%]+)\s*\)")
_TRAIL_MARKERS = re.compile(r"(?:\s*(?:=>|->|>|\*+|@+))+\s*$")
_ENCORE_MARK = re.compile(r"^\s*(?:e|en|enc|encore)\s*:\s*", re.I)
_DISC_TRACK_HEADER = re.compile(
    r"^\s*(?:disc|disk|cd)\s*\d{1,2}\s*[,:]\s*track\s*\d{1,3}\s*$", re.I
)


@dataclass(frozen=True)
class Cleaned:
    text: str
    durations: tuple[float, ...]
    filler_marked: bool
    leader_stripped: bool
    trailing_time_stripped: bool


def _secs(t: str) -> float:
    if ":" in t:
        parts = [int(p) for p in t.split(":")]
        total = 0
        for p in parts:
            total = total * 60 + p
        return float(total)
    m, s = t.split(".")
    return float(int(m) * 60 + int(s))


def _strip_durations(s: str) -> tuple[str, list[float], bool]:
    """Step 1. A whole entry that is only a time (`2:22`), or that would be emptied, stays."""
    if _WHOLE_TIME.match(s):
        return s, [], False
    durs: list[float] = []
    trailing = False
    out = s

    def take(m: re.Match) -> str:
        durs.append(_secs(m.group(1)))
        return ""

    out = _BRACKETED.sub(take, out)
    out = _LEAD_DASH.sub(take, out)
    for rx in (_TAB_TIME, _TRAIL_DOT):
        out = rx.sub(take, out)
    before = len(durs)
    out = _TRAIL_TIME.sub(take, out)
    trailing = len(durs) > before
    out = out.strip()
    if not out:
        return s, [], False
    return out, durs, trailing


def _finish(text: str) -> tuple[str, bool]:
    filler = bool(_FILLER_MARK.match(text))
    text = _FILLER_MARK.sub("", text, count=1)
    text = _FOOTNOTE.sub("", text)
    text = _TRAIL_MARKERS.sub("", text)
    text = _ENCORE_MARK.sub("", text, count=1)
    t = text.strip()
    if len(t) >= 2 and (
        (t[0] == '"' and t[-1] == '"') or (t[0] == "“" and t[-1] == "”")
    ):
        t = t[1:-1]
    return t.strip(), filler


def _build(step1: str, durs: list[float], trailing: bool, strip_leader: bool) -> Cleaned:
    text = step1
    stripped = False
    if strip_leader:
        new = _ENTRY_LEADER.sub("", text, count=1)
        stripped = new != text
        text = new
    text, filler = _finish(text)
    return Cleaned(text, tuple(durs), filler, stripped, trailing)


def clean_one(raw: str, *, strip_leader: bool = False) -> Cleaned:
    s, durs, trailing = _strip_durations(html.unescape(raw))
    return _build(s, durs, trailing, strip_leader)


def clean_entries(raws: Sequence[str]) -> list[Cleaned]:
    """Clean a whole list; the leader is stripped only under the enumerated vote taken over
    the entries after the duration step."""
    steps = [_strip_durations(html.unescape(r)) for r in raws]
    numbered = sum(1 for s, _, _ in steps if _ENTRY_LEADER.match(s))
    vote = numbered >= _ENUMERATED_MIN_FILES and numbered >= _ENUMERATED_MIN_COVERAGE * len(steps)
    return [_build(s, d, t, vote) for s, d, t in steps]


def written_seconds(c: Cleaned) -> float | None:
    return c.durations[0] if len(c.durations) == 1 else None


def is_header_shape(text: str) -> bool:
    if _DISC_TRACK_HEADER.match(text) or taper._DISC_LABEL.match(text):
        return True
    for rx in taper._SET_HEADERS:
        m = rx.match(text)
        if m and not (m.groupdict().get("rest") or "").strip():
            return True
    return False


# --- Reader (i): the taper's own numbered lines -------------------------------------------

# The census `NUMLINE` with named groups, otherwise identical.
_NUMLINE = re.compile(
    r"^\s*(?:(?:d|cd|disc)\s*(?P<disc>\d+)\s*)?(?:t(?:rack)?\s*)?(?P<num>\d{1,3})"
    r"\s*[.):\-]?\s+(?P<text>\S.*)$",
    re.I,
)
_TIMESTAMP_LINE = re.compile(r"^\s*\d{1,2}[:/]\d")
# A numbered line with no text. A bare `N` or `N:` is a disc label in measured descriptions
# and is NOT an empty entry.
_EMPTY_NUMBERED = re.compile(
    r"^\s*(?:(?:d|cd|disc)\s*\d+\s*)?(?:t(?:rack)?\s*)?\d{1,3}\s*[.)\-]\s*$", re.I
)


@dataclass(frozen=True)
class DescList:
    reader: str  # "numbered" | "parse"
    raws: tuple[str, ...]  # entry text after the taper's own number
    cleaned: tuple[Cleaned, ...]  # clean_entries(raws)
    blocks: tuple[int, ...]  # 0-based block per entry
    boundaries: tuple[str, ...]  # per block boundary: "set" | "disc" | "restart" | "encore"


def _lines(desc: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", desc or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return html.unescape(text).splitlines()


def _header_kind(line: str, encore_header: bool) -> str | None:
    for rx in taper._SET_HEADERS:
        if rx.match(line):
            return "set"
    if taper._DISC_LABEL.match(line) or _DISC_TRACK_HEADER.match(line):
        return "disc"
    if encore_header and taper._ENCORE_HEADER.match(line):
        return "encore"
    return None


def read_numbered(desc: str, *, encore_header: bool = False) -> DescList | str:
    """The taper's numbered lines as one list with blocks, or a reason string."""
    # (kind of header seen since the previous entry, disc, num, text)
    items: list[tuple[str | None, int | None, int, str]] = []
    pending: str | None = None
    for line in _lines(desc):
        if _TIMESTAMP_LINE.match(line):
            continue
        if _EMPTY_NUMBERED.match(line):
            return "empty entry"
        m = _NUMLINE.match(line)
        if m:
            disc = m.group("disc")
            items.append((pending, int(disc) if disc else None, int(m.group("num")),
                          m.group("text").strip()))
            pending = None
            continue
        kind = _header_kind(line, encore_header)
        if kind and pending is None:
            pending = kind
    if not items:
        return "no numbered lines"

    three = all(len(str(n)) == 3 and d is None for _, d, n, _ in items)
    raws: list[str] = []
    blocks: list[int] = []
    boundaries: list[str] = []
    block = 0
    prev_disc: int | None = None
    prev_track = 0
    for idx, (hdr, disc, num, text) in enumerate(items):
        track = num
        if three:
            disc, track = num // 100, num % 100
        boundary = hdr if idx else None
        if idx and boundary is None and disc is not None and prev_disc is not None \
                and disc != prev_disc:
            boundary = "disc"
        if idx == 0:
            ok = track == 1
        elif boundary:
            ok = track in (1, prev_track + 1)
        else:
            ok = track == prev_track + 1
        if not ok:
            return f"non-contiguous at {num}"
        if boundary:
            block += 1
            boundaries.append(boundary)
        raws.append(text)
        blocks.append(block)
        prev_disc = disc if disc is not None else prev_disc
        prev_track = track
    return DescList("numbered", tuple(raws), tuple(clean_entries(raws)), tuple(blocks),
                    tuple(boundaries))
