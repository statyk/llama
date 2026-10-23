"""Entry cleaning for the taper's description list (title hygiene, piece 3, task 1).

Pure: no IO, no gather wiring. `clean_one`/`clean_entries` produce the ONE cleaned form
check 1 tests and D ships; `written_seconds` reads the single written duration;
`is_header_shape` says whether an entry is a set/disc header rather than a title.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from llama import jerrybase, taper
from llama.models import ParsedSetlist
from llama.setlist import (
    _ENCORE_LINE,
    _LABELED_SET_LINE,
    _NOISE,
    _RECOVER_FLOOR,
    _SET_LINE,
    _emit_items,
    _may_start_a_show,
    parse_setlist,
)
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


# --- Reader (ii): parse_setlist's own items, judged per raw line ---------------------------

Cleaner = Callable[[ParsedSetlist], tuple[ParsedSetlist, frozenset[int]]]
"""(cleaned parse, removed_indices): indices into the INPUT items that the cleaner removed
(banner strip, artist drop inside the banner span). A rewrite such as a footnote-marker
strip is never a removal. The cleaned items are the input items minus the removed ones,
in order."""


def drop_leading_artist_items(parsed: ParsedSetlist, artist: str) -> ParsedSetlist:
    """Drop the LEADING run of items that are just the performing artist's name.

    Unlike gather's `_drop_artist_items`, which drops them anywhere, a self-titled song
    further down the list (railroadearth-2004-04-09's `Railroad Earth`) stays."""
    key = jerrybase.artist_key(artist)
    if not key:
        return parsed
    n = 0
    while n < len(parsed.items) and jerrybase.artist_key(parsed.items[n].title) == key:
        n += 1
    if not n:
        return parsed
    return parsed.model_copy(update={"items": parsed.items[n:]})


def _parsed_lines(desc: str) -> list[str]:
    """The lines `parse_setlist` itself parses: its preprocessing, then its header
    truncation (mirrored from `parse_setlist`, which is not changed)."""
    text = re.sub(r"<br\s*/?>", "\n", desc, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    raw_lines = [ln.strip() for ln in html.unescape(text).splitlines()]
    first_marker = next(
        (i for i, ln in enumerate(raw_lines)
         if _SET_LINE.match(ln) or _LABELED_SET_LINE.match(ln) or _ENCORE_LINE.match(ln)),
        None,
    )
    if first_marker is not None and not _may_start_a_show(raw_lines[first_marker]):
        above = [ln for ln in raw_lines[:first_marker] if ln]
        if len(_emit_items(above)[0]) >= _RECOVER_FLOOR:
            first_marker = None
    if first_marker is not None:
        raw_lines = raw_lines[first_marker:]
    return raw_lines


def _is_marker(line: str) -> bool:
    return bool(_SET_LINE.match(line) or _LABELED_SET_LINE.match(line)
                or _ENCORE_LINE.match(line))


def _blocks(sets: Sequence[str]) -> tuple[tuple[int, ...], tuple[str, ...]]:
    blocks: list[int] = []
    boundaries: list[str] = []
    for i, s in enumerate(sets):
        if i and s != sets[i - 1]:
            boundaries.append("encore" if s == "encore" else "set")
        blocks.append(len(boundaries))
    return tuple(blocks), tuple(boundaries)


def read_parse(desc: str, *, artist: str, clean: Cleaner) -> DescList | str:
    """`parse_setlist`'s items for the selected description as one list, or a reason.

    Each raw line `parse_setlist` parses is judged ON ITS OWN (`_emit_items([line])`, so no
    document-level number strip): it must yield exactly one item unless it is exempt --
    a header-only marker line, a `_NOISE` line, or the line of an item the cleaner (or the
    leading-artist drop) removed. Lines above the first marker that header truncation
    removes never reach the parse and are exempt by construction. The per-line counts
    must sum to `parse_setlist`'s own item count, which is what ties each item to its
    line."""
    if any(_EMPTY_NUMBERED.match(ln) for ln in _lines(desc)):
        return "empty entry"
    parsed = parse_setlist(desc or "")
    lines = [ln for ln in _parsed_lines(desc or "") if ln]
    counts = [len(_emit_items([ln])[0]) for ln in lines]
    if sum(counts) != len(parsed.items):
        return "per-line count disagrees"
    if not parsed.items:
        return "no items"
    line_of = [k for k, c in enumerate(counts) for _ in range(c)]

    cleaned, removed = clean(parsed)
    removed = set(removed)
    kept = [i for i in range(len(parsed.items)) if i not in removed]
    consistent = len(kept) == len(cleaned.items)
    if consistent:
        dropped = drop_leading_artist_items(cleaned, artist)
        removed |= set(kept[: len(cleaned.items) - len(dropped.items)])
        cleaned = dropped

    exempt = {line_of[i] for i in removed if 0 <= i < len(line_of)}
    for k, (ln, c) in enumerate(zip(lines, counts)):
        if c == 1 or k in exempt:
            continue
        if c == 0 and (_is_marker(ln) or _NOISE.search(ln)):
            continue
        return f"line yields {c} items: {ln}"
    if not consistent:
        return "cleaner count disagrees"
    if not cleaned.items:
        return "no items"

    raws = tuple(it.title for it in cleaned.items)
    blocks, boundaries = _blocks([it.set for it in cleaned.items])
    return DescList("parse", raws, tuple(clean_entries(raws)), blocks, boundaries)


@dataclass(frozen=True)
class DescRead:
    used: DescList | None  # the count-matched admissible list, (i) preferred
    numbered: DescList | str
    parsed: DescList | str


def read_desc_list(desc: str, n_tracks: int, *, artist: str, clean: Cleaner) -> DescRead:
    """Both readers over the selected description; `used` is the first of (i), (ii) that
    is admissible and has exactly `n_tracks` entries."""
    numbered = read_numbered(desc)
    parsed = read_parse(desc, artist=artist, clean=clean)
    used = next((d for d in (numbered, parsed)
                 if isinstance(d, DescList) and len(d.raws) == n_tracks), None)
    return DescRead(used, numbered, parsed)
