r"""The taper's own set/encore markers, read for STRUCTURE ONLY (held-backlog piece 2).

Spec: `docs/superpowers/specs/2026-10-22-taper-set-markers-design.md`, sections 1 and 2.

`parse_setlist` is deliberately untouched: its output (the canonical setlist, the title
rungs, `--suggest-titles`) must stay byte-identical. This module is a second, separate
reader of the chosen recording's description (or its `notes`), used only to derive the
set structure the taper wrote. It reuses `setlist.py`'s line handling (`_INLINE_MARKER`,
`_TRACK_PREFIX`, the enumerated `_NUM_PREFIX`, `_NOISE`, `_split_songs`, `is_junk_title`)
without changing their behaviour, and adds its own regexes for everything new. It never
truncates.

Recognised forms are EXACTLY the spec's section 1 list, and nothing else:

- numbered sets: `Set` + 1-3 / one-three / I-III (word-bounded, so `Set Intro` and
  `Set IV` are not set 1), `First`/`Second`/`Third Set`, `1st`/`2nd`/`3rd Set`; decoration
  (dashes, asterisks, tildes, brackets, parentheses, `=`) may surround the header, which
  stands alone on its line or is followed by `:`/`-` and songs. `Disc N (Set M)`,
  `Disc N - Set M` and `Disc N / Set M` read as set M.
- the encore: a line starting (after decoration and track-prefix stripping) `Encore`,
  `Encores`, `ENC`, `E`, `E1`, `E2` ..., followed by `:` (or `- `) and songs or alone on the
  line; `Encore 1:`, `Encore #1:`, `1st Encore:`; plus the mid-line `Set II:`/`E:`/
  `Encore:` that `setlist._INLINE_MARKER` already splits.
- `Set 4` or higher anywhere in the text, for VOIDING only.

Everything else (bare digits `1:`/`[1]`, bare roman numerals, `S1`, `E.`, `(E)`, a trailing
`enc`, parenthetical `(set II)` mid-line, `Early`/`Late`/`Acoustic Set`, `Early Show`, act
headers) is not a marker.

Encore-like text sets `TaperText.encore_like`, the input to section 2's veto (when there is
no recognised encore marker, the taper owns nothing). It never starts an encore. It is
matched on song lines and on the song text after a marker, never on the marker itself:

- `\bencores?\b` or `\benc\b` anywhere (`encore break`, `Ripple (Encore)`, prose);
- a song line starting `E.`, `E)`, `E` plus a digit or `(E)`, after the track-prefix strip
  and also after an unconditional leading `\d{1,3}\s+` strip, so `14 E. Playin' Reprise`
  counts on a text that is not enumerated (ruling R4 (d));
- a split song item that is exactly `E`, `E<digit>` or `ENC` once decoration is stripped
  (`... Day Tripper, E`, an own-line `[E]` or `(E)`; ruling R4 (a), (c));
- a song line ending ` E`, ` (E)`, ` [E]` or `, E` (`Traffic Jam E`, `US Blues (E)`; ruling
  R4 (b)). Accepted collateral: a title such as `D to E` also counts. It only makes the
  taper own less;
- a header naming both a set and the encore (`Set 2 + Encore`), which names an encore it
  does not start.

Beyond section 2's void rules (decreasing, restarting or skipping set numbers, set 4 or
higher, a numbered marker after the encore, an empty set), three own-less voids are this
module's own reading:

- a continuation header (`Set 2 cont.`) whose set never started under its own header;
- an empty set at the END of the text (`... Encore:` with nothing after it), not only one
  followed directly by another header;
- a set holding only filler (`Set 1:` then `Tuning`) counts as empty.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from llama.setlist import (
    _INLINE_MARKER,
    _NOISE,
    _NUM_PREFIX,
    _TRACK_PREFIX,
    MAX_TITLE_LEN,
    _enumerated_prefix,
    _split_songs,
    is_junk_title,
    parse_setlist,
)
from llama.structure import is_filler


@dataclass(frozen=True)
class TaperItem:
    title: str  # song text after _emit_items-style cleaning
    set: str  # "1" | "2" | "3" | "encore"


@dataclass(frozen=True)
class TaperText:
    items: tuple[TaperItem, ...]  # ordered song items (non-filler), every item labelled
    asserts: bool  # True only for a valid 2-3 numbered-set structure
    has_encore: bool  # a recognised encore marker started the encore
    encore_like: bool  # encore-like text outside a recognised marker (veto input)
    reason: str | None  # why asserts is False: "no markers", "one set",
    # "void: <rule>", "cross-check: <label>", None when asserts


# --- Marker regexes (spec section 1). All are matched against a line AFTER the inline
# split and AFTER stripping a leading track prefix (`_TRACK_PREFIX`, plus `_NUM_PREFIX`
# when the text is enumerated), and must match the WHOLE line.

# Header decoration: dashes, asterisks, tildes, brackets, parentheses, `=` (and spaces).
_DECOR = r"[-–—*~=\[\]()\s]*"
# A header standing alone on its line, closing decoration allowed (`-Set I-`, `[Set One]`).
_TAIL_ALONE = rf"{_DECOR}$"
# A header followed by `:` or a dash run and then songs. The dash must be followed by
# whitespace or the line end, as `_ENCORE_LINE`'s `-\s` is, so `E-Bow the Letter` is not
# an encore line.
_TAIL_SONGS = r"[\])~*=\s]*(?::|[-–—]+(?=\s|$))\s*(?P<rest>.*)$"

# The numbered-set token. `(?!\w)` is the word boundary: `Set Intro`, `Set IV`, `Set 12`
# and `Set 1st` are not set 1.
_SET_TOKEN = (
    r"(?:set\s*(?P<tok>one|two|three|iii|ii|i|[123])(?!\w)"
    r"|(?P<ord>first|second|third)\s+set(?!\w)"
    r"|(?P<ordn>1st|2nd|3rd)\s+set(?!\w))"
)
# A repeated set number written as a continuation: `Set 2 cont.`, `Set II (cont.)`,
# `Set 2, cont.`, `Set 2 cont'd`, `Set 2 continued`, `Set2cont`.
_CONT = r"(?P<cont>\s*,?\s*\(?\s*cont(?:inued|'d|’d|d)?\.?\s*\)?)?"
# A header naming both a set and the encore: `Set 2 + Encore`, `Set One & Encore`.
_AND_ENCORE = r"(?P<andenc>\s*(?:\+|&|/|,|\band\b)\s*encores?(?!\w))?"
_SET_CORE = _SET_TOKEN + _CONT + _AND_ENCORE

_SET_HEADER = re.compile(rf"^{_DECOR}{_SET_CORE}(?:{_TAIL_ALONE}|{_TAIL_SONGS})", re.I)
# `Disc N (Set M)`, `Disc N - Set M`, `Disc N / Set M`. Tested BEFORE `_NOISE`, which drops
# every disc line (and is not changed: only this reader gives such a line meaning).
_DISC_SET_HEADER = re.compile(
    rf"^{_DECOR}disc\s*#?\s*(?:\d{{1,2}}|one|two|three|four|five|six|iv|i{{1,3}})(?!\w)\s*"
    # `(Set M)` in parentheses, or `- Set M` / `/ Set M`: one copy of the core, the
    # closing parenthesis required exactly when the opening one is there.
    rf"(?P<open>\()?(?(open)\s*|[-–—/]\s*){_SET_CORE}(?(open)\s*\))"
    rf"(?:{_TAIL_ALONE}|{_TAIL_SONGS})",
    re.I,
)
# Worded encore headers: `Encore`, `Encores`, `==encores==`, `Encore ======`, `(encore)`,
# `Encore 1:`, `Encore #1:`, `1st Encore:`.
_ENCORE_HEADER = re.compile(
    rf"^{_DECOR}(?:(?:1st|2nd|3rd|first|second|third)\s+encore"
    rf"|encores?(?:\s*#?\s*\d)?)(?!\w)(?:{_TAIL_ALONE}|{_TAIL_SONGS})",
    re.I,
)
# The short encore forms `ENC`, `E`, `E1`, `E2` (`_ENCORE_LINE`'s `e\d?`). No bracket or
# parenthesis decoration on either side: `(E)`, `[E]` and `E)` are spec-listed non-markers.
_E_DECOR = r"[-–—*~=\s]*"
_E_HEADER = re.compile(
    rf"^{_E_DECOR}(?:enc|e\d?)(?!\w)"
    rf"(?:{_E_DECOR}$|[~*=\s]*(?::|[-–—]+(?=\s|$))\s*(?P<rest>.*)$)",
    re.I,
)

_TOKEN_NUM = {"one": 1, "two": 2, "three": 3, "i": 1, "ii": 2, "iii": 3,
              "first": 1, "second": 2, "third": 3, "1st": 1, "2nd": 2, "3rd": 3}

# Any mention of a set numbered 4 or higher, anywhere in the text, voids the structure.
_SET_FOUR_PLUS = re.compile(
    r"\bset\s*(?:0*[4-9]|[1-9]\d+|four|five|six|seven|eight|nine|ten"
    r"|iv|v|vi{1,3}|ix|x)(?!\w)"
    r"|\b(?:[4-9]|[1-9]\d)th\s+set\b"
    r"|\b(?:fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+set\b",
    re.I,
)

# --- Song-line cleaning beyond `_emit_items` (spec section 3's first paragraph).
# A line that is only a number (DSO's `1:`/`2:`/`3:` disc lines, the `18.` stub the inline
# split leaves of `18. E: ...`) is neither a marker nor a song item.
_BARE_NUMBER = re.compile(r"^\d{1,3}[.:)]?$")
_TIMESTAMP = r"[-–—\[({]?\s*\d{1,3}:\d{2}(?::\d{2})?(?:\.\d+)?\s*[-–—\])}]?"
# A leading duration or timestamp before the title: `-04:41.50- Right in Tune`.
_LEAD_TIMESTAMP = re.compile(rf"^{_TIMESTAMP}\s+(?=\S)")
# An item that is only a timestamp: `(2:33:33)` after a set header, `1:08:07`.
_TIMESTAMP_ONLY = re.compile(rf"^{_TIMESTAMP}$")

# --- Encore-like text (section 2's veto input), matched only OUTSIDE recognised markers.
_ENCORE_WORDS = re.compile(r"\bencores?\b|\benc\b", re.I)
# A song line (after track-prefix stripping) starting `E.`, `E)`, `E` plus a digit, `(E)`.
_ENCORE_LIKE_START = re.compile(r"^(?:e[.)]|e\d|\(e\))", re.I)
# The same test is also made after this unconditional bare-number strip (ruling R4 (d)).
_LEADING_NUMBER = re.compile(r"^\d{1,3}\s+")
# A song line ending ` E`, ` (E)`, ` [E]` or `, E` (ruling R4 (b)).
_ENCORE_LIKE_END = re.compile(r"\s(?:e|\(e\)|\[e\])$|,\s*e$", re.I)
# A split song item that is only `E`, `E<digit>` or `ENC` (ruling R4 (a), (c)).
_ENCORE_LIKE_ITEM = re.compile(r"^(?:e\d?|enc)$", re.I)
_ITEM_DECOR = "-–—*~=[]() \t"


def _preprocess(text: str) -> list[str]:
    """`parse_setlist`'s own preprocessing (no truncation), then `_emit_items`'s inline
    split, as stripped lines."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    raw = [ln.strip() for ln in text.splitlines()]
    return [ln.strip() for ln in _INLINE_MARKER.sub("\n", "\n".join(raw)).splitlines()]


def _classify(core: str) -> tuple[str, int | None, bool, bool, str]:
    """(kind, set number, continuation, set-and-encore, rest) for one prefix-stripped line.
    kind is "set" | "encore" | "song"."""
    for rx in (_SET_HEADER, _DISC_SET_HEADER):
        m = rx.match(core)
        if m:
            token = (m.group("tok") or m.group("ord") or m.group("ordn")).lower()
            return ("set", _TOKEN_NUM.get(token) or int(token), bool(m.group("cont")),
                    bool(m.group("andenc")), m.group("rest") or "")
    for rx in (_ENCORE_HEADER, _E_HEADER):
        m = rx.match(core)
        if m:
            return "encore", None, False, False, m.group("rest") or ""
    return "song", None, False, False, core


@dataclass
class _Scan:
    """The reader's working state; `read_taper_structure` turns it into a `TaperText`."""
    entries: list[tuple[str, str | None]] = field(default_factory=list)  # (title, label)
    saw_marker: bool = False
    has_encore: bool = False
    encore_like: bool = False
    set_four_plus: bool = False
    void: str | None = None
    current: int | None = None  # the numbered set in progress; None before the first
    in_encore: bool = False
    songs: dict[str, int] = field(default_factory=dict)  # song items per label

    def label(self) -> str | None:
        if self.in_encore:
            return "encore"
        return str(self.current) if self.current is not None else None

    def set_void(self, rule: str) -> None:
        if self.void is None:
            self.void = rule

    def leading_songs(self) -> int:
        return sum(1 for _, lab in self.entries if lab is None)

    def started_set_is_empty(self) -> bool:
        """The set in progress (numbered or the encore) has no song item."""
        lab = self.label()
        if lab is None:
            return False
        return self.songs.get(lab, 0) == 0


def _encore_like(song_text: str) -> bool:
    """Section 2's encore-like rules (plus ruling R4) on one piece of song text: a song
    line after its track-prefix strip, or the song text after a marker."""
    text = song_text.strip()
    if _ENCORE_WORDS.search(text) or _ENCORE_LIKE_END.search(text):
        return True
    if _ENCORE_LIKE_START.match(text) or _ENCORE_LIKE_START.match(_LEADING_NUMBER.sub("", text)):
        return True
    return any(_ENCORE_LIKE_ITEM.match(title.strip(_ITEM_DECOR)) for title, _ in _split_songs(text))


def _song_titles(rest: str, enumerated: bool) -> list[str]:
    """Song items from the text after a marker, or from a whole (unstripped) song line.
    The track prefix is stripped exactly ONCE here, as `_emit_items` strips it: stripping
    it twice would turn `02 100 Years` into `Years` on an enumerated text."""
    rest = _TRACK_PREFIX.sub("", rest)
    if enumerated:
        rest = _NUM_PREFIX.sub("", rest)
    if _BARE_NUMBER.match(rest.strip()):
        return []
    rest = _LEAD_TIMESTAMP.sub("", rest.strip())
    titles = []
    for title, _segue in _split_songs(rest):
        if len(title) > MAX_TITLE_LEN or is_junk_title(title) or _TIMESTAMP_ONLY.match(title):
            continue
        if is_filler(title):
            continue
        titles.append(title)
    return titles


def _scan(text: str) -> _Scan:
    s = _Scan()
    lines = _preprocess(text)
    s.set_four_plus = any(_SET_FOUR_PLUS.search(ln) for ln in lines)
    enumerated = _enumerated_prefix(lines)
    for line in lines:
        if not line:
            continue
        core = _TRACK_PREFIX.sub("", line)
        if enumerated:
            core = _NUM_PREFIX.sub("", core)
        kind, number, cont, and_encore, rest = _classify(core)
        if kind == "song":
            if _ENCORE_WORDS.search(line) or _encore_like(core):
                s.encore_like = True
            if _NOISE.search(line):
                continue
            # The whole line, unstripped: `_song_titles` does the one prefix strip.
            rest = line
        else:
            s.saw_marker = True
            # The rest of a marker line is song text, so encore-like text there counts.
            if _encore_like(rest):
                s.encore_like = True
        if kind == "set":
            _numbered(s, number, cont, and_encore)
        elif kind == "encore":
            if not s.in_encore:
                if s.current is not None and s.started_set_is_empty():
                    s.set_void("empty set")
                s.in_encore = True
                s.has_encore = True
            # Every encore line after the first continues the encore.
        for title in _song_titles(rest, enumerated):
            lab = s.label()
            s.entries.append((title, lab))
            if lab is not None:
                s.songs[lab] = s.songs.get(lab, 0) + 1
    if s.started_set_is_empty():
        s.set_void("empty set")
    return s


def _numbered(s: _Scan, number: int, cont: bool, and_encore: bool) -> None:
    """One numbered header (spec section 2's sequence rules)."""
    if s.in_encore:
        s.set_void("numbered marker after the encore")
        return
    if and_encore:
        # Names both a set and the encore: asserts nothing, changes no label. The encore
        # it names has no recognised start, so it is encore-like (the veto's input).
        s.encore_like = True
        return
    if s.current is None:
        if cont:
            s.set_void("continuation without its set's header")
        elif number == 2 and s.leading_songs() > 0:
            # A leading unlabelled block is set 1 only when the first marker is set 2.
            s.songs["1"] = s.leading_songs()
            s.entries[:] = [(t, "1") for t, _ in s.entries]
        elif number == 1:
            # Lines before an explicit `Set 1` are header text: they yield no items.
            s.entries.clear()
        else:
            s.set_void("skipped set number")
        s.current = number
        return
    if number == s.current:
        return  # a repeated set number is a continuation
    if cont:
        s.set_void("continuation without its set's header")
    elif number < s.current:
        s.set_void("decreasing set number")
    elif number > s.current + 1:
        s.set_void("skipped set number")
    elif s.started_set_is_empty():
        s.set_void("empty set")
    s.current = number


def read_taper_structure(text: str) -> TaperText:
    """Read the taper's set/encore markers from one text (a description or notes).

    `asserts` is True only for a valid numbered structure of two or three sets,
    consecutive from set 1, with or without an encore (spec section 2), that also has
    every label `parse_setlist` reads from the same text (the cross-check: the reader
    never sees less than the parser does)."""
    s = _scan(text)
    items = tuple(TaperItem(title, lab or "1") for title, lab in s.entries)
    numbered = s.current or 0
    if s.set_four_plus:
        reason: str | None = "void: set 4 or higher"
    elif s.void:
        reason = f"void: {s.void}"
    elif not s.saw_marker:
        reason = "no markers"
    elif numbered < 2:
        reason = "one set"
    else:
        own = {str(n) for n in range(1, numbered + 1)}
        if s.has_encore:
            own.add("encore")
        missing = sorted({i.set for i in parse_setlist(text).items} - own)
        reason = f"cross-check: {', '.join(missing)}" if missing else None
    return TaperText(items=items, asserts=reason is None, has_encore=s.has_encore,
                     encore_like=s.encore_like, reason=reason)


def _field_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value)


def _has_marker(text: str) -> bool:
    s = _scan(text)
    return s.saw_marker or s.set_four_plus


def taper_text_for(meta: dict) -> tuple[str, str]:
    """(text, source) with source "description" | "notes" | "none": the description when it
    has any recognised marker, else the notes (string or list) when they have one, else
    "none" (with empty text)."""
    desc = _field_text(meta.get("description"))
    if desc and _has_marker(desc):
        return desc, "description"
    notes = _field_text(meta.get("notes"))
    if notes and _has_marker(notes):
        return notes, "notes"
    return "", "none"
