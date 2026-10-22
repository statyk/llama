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
- Operator ruling 2026-10-22 (Checkpoint A, (c)): the disc-and-set shapes cpa-decl listed,
  each carrying `Set` or an ordinal set, read as set M: set first `Set 1 Disc 1`,
  `Set I Disc 1: 74:16`, `set 1 - disc 1`, `Set 1/Disc 1:`, `set 2 / disc 2`; disc first
  `Disc I 1st Set`, `Disk 1: Set 1`, `DISC 1 SET ONE`, `DISC 01:SET I :`, `disc 01 [Set I]`,
  `CD1 Set 1`, `Disc/Set1`, `Disc N: Set M`. Never `Set 1/2`, `(Start Set N)` or
  `(start of Set II)`. (llama-db reading of operator ruling (c), 2026-10-22: `Disc`/`Disk`/
  `CD` are interchangeable in these shapes and in `Disc N (Set M)`/`- Set M`/`/ Set M`, and
  the `,` and unspaced-dash joins, `Disc 1, Set 1` and `Set 1-Disk 1`, are admitted.)
- the encore: a line starting (after decoration and track-prefix stripping) `Encore`,
  `Encores`, `ENC`, `E`, `E1`, `E2` ..., followed by `:` (or `- `) and songs or alone on the
  line; `Encore 1:`, `Encore #1:`, `1st Encore:`; plus the mid-line `Set II:`/`E:`/
  `Encore:` that `setlist._INLINE_MARKER` already splits.
- Operator ruling 2026-10-22 (Checkpoint A, (b)): a recognised header followed by a
  trailing `(duration|time)` annotation is that header (`SET ONE (50:28)`,
  `Set One (9:30PM - 10:46PM):`). The annotation must directly follow the header token: a
  word (`Set 1 (Acoustic)`), anything in between, and a trailing `...` are not admitted.
  (My call: a time range may also be joined by `~`, and a time may end in `?`,
  `12:14AM?`; both are still a parenthesised time.)
- `Set 4` or higher anywhere in the text, for VOIDING only.

A header naming both a set and the encore (`Set II & Encore:`, `Set 3 / Encore:`,
`Disc 3 - Set II + Encore:`) asserts nothing, colon or not. It is recognised on the raw line,
BEFORE `_INLINE_MARKER`'s split, which would otherwise cut it before `Encore:` and start the
encore there (Checkpoint A).

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
- the Checkpoint A veto gap: the `Encor:` typo (`\bencor\b`), an `E` glued to the track
  number (`9E.Wayfaring Stranger`), a song line `E <Title>` (`E Ripple`, `24. E Ripple`;
  case-sensitive), and a decorated `E~` or `-e-` anywhere (`Tap In, E~ Twilight`,
  `-e- Freq.1>2`). Accepted collateral: a title such as `E Street Shuffle` counts too;
- a header naming both a set and the encore (`Set 2 + Encore`), which names an encore it
  does not start.

Set-like text sets `TaperText.set_like`, the input to the own-less set-like veto (llama-db
ruling, Checkpoint A2, 2026-10-22): an item of a numbered set (`1`/`2`/`3`; the encore's
items, its songs and any notes after them, are skipped) holding a word-bounded numbered-set
token, any spelling `_SET_TOKEN` reads (`Set 1.5:`, `- end of set one`, `Cardinals Set 1 CD 2`,
`set one-(1:05:59)`), means the taper owns nothing: `decide_taper` declines with
`veto: set-like text`. So does an item that is exactly `Set` once decoration is stripped: the
inline split cuts an ordinal header before a numbered line (`Third Set` then `1- Truckin`)
into the items `Third` and `Set` (orchestrator ruling R10, Checkpoint A3, 2026-10-22).
A continuation of the item's own set (`Set 2 con't` inside set 2) is not set-like
(orchestrator ruling R9, 2026-10-22, confirmed by llama-db, 2026-10-22). Recognised markers are
not items, so they never count, and nothing here makes a marker. Like the encore-like veto,
it only makes the taper own less.

Song items get reader-local cleaning `parse_setlist` does not do (Checkpoint A, R-ITEM; see
`_song_titles`): at most ONE leading prefix is stripped from a title (`_TRACK_PREFIX`, a
`s2t01:` token or an `08:` colon number, else the enumerated `_NUM_PREFIX`), so
`04. 44 Blues` keeps its `44`; items with no letter or digit (`=====`) are dropped, and so,
in a header line's rest, are a lone parenthetical (`(Electric)`) or disc label (`Disc 2:`);
and a numbered line on an enumerated text keeps a comma that is followed by a word
(`9. Quantico, VA`).

An encore whose rest (or first song item) is `none`, `no encore` or `n/a`, after
decoration (`Encore: none`, `E: None Filler: ...`), voids the structure: `void: encore none`
(Checkpoint A). Accepted collateral: a title starting with the word `None` voids too.

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
from llama.models import Track
from llama.structure import (
    _ENCORE_MARKER,
    TAUTOLOGICAL_TITLE_SOURCES,
    fuzzy_norm_title,
    fuzzy_title_eq,
    is_filler,
    title_components,
)


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
    set_like: bool = False  # a numbered set's item names a set (veto input)


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
# `Set 2, cont.`, `Set 2 cont'd`, `Set 2 continued`. A `cont` glued to the token
# (`Set2cont`, `Set 2cont:`, `Set IIcont`) is NOT one: the token's `(?!\w)` stops it, so
# such a line reads as a song title.
_CONT = r"(?P<cont>\s*,?\s*\(?\s*cont(?:inued|'d|’d|d)?\.?\s*\)?)?"
# A header naming both a set and the encore: `Set 2 + Encore`, `Set One & Encore`.
_AND_ENCORE = r"(?P<andenc>\s*(?:\+|&|/|,|\band\b)\s*encores?(?!\w))?"
_SET_CORE = _SET_TOKEN + _CONT + _AND_ENCORE

# Operator ruling 2026-10-22 (Checkpoint A, (b)): a trailing `(duration|time)` annotation
# directly after the header token: `SET ONE (50:28)`, `Set One (9:30PM - 10:46PM):`. Only a
# time in parentheses, never a word (`Set 1 (Acoustic)`) and never `...` (fix round 1).
# (My call: the `~` range join and a trailing `?` after a time.)
_TIME = r"\d{1,3}:\d{2}(?::\d{2})?(?:\.\d+)?\s*(?:[ap]\.?m\.?)?\??"
_ANNOT = rf"(?:\s*\(\s*{_TIME}(?:\s*[-–—~]\s*{_TIME})?\s*\))?"

_SET_HEADER = re.compile(rf"^{_DECOR}{_SET_CORE}{_ANNOT}(?:{_TAIL_ALONE}|{_TAIL_SONGS})", re.I)
# `Disc N (Set M)`, `Disc N - Set M`, `Disc N / Set M`. Tested BEFORE `_NOISE`, which drops
# every disc line (and is not changed: only this reader gives such a line meaning).
# A disc label: `Disc`, `Disk` or `CD` and its number (`Disc 1`, `Disk II`, `CD1`, `DISC 01`).
_DISC_WORD = r"(?:disc|disk|cd)"
_DISC_NUM = r"(?:\d{1,2}|one|two|three|four|five|six|iv|i{1,3})(?!\w)"
_DISC = rf"{_DISC_WORD}\s*#?\s*{_DISC_NUM}"
# Disc first, then the set. Spec section 1's `Disc N (Set M)`, `Disc N - Set M` and
# `Disc N / Set M`, and (operator ruling 2026-10-22, Checkpoint A, (c)) `Disc N: Set M`,
# `Disc N Set M` (`DISC 1 SET ONE`, `CD1 Set 1`, `Disc I 1st Set`), `disc 01 [Set I]`,
# `DISC 01:SET I :` and `Disc/Set1`. (llama-db reading of operator ruling (c): `Disc`/`Disk`/
# `CD` interchangeable everywhere here, and the `,` join, `Disc 1, Set 1`.) Tested BEFORE `_NOISE`, which drops
# every disc line (and is not changed: only this reader gives such a line meaning). One copy
# of the core; the closing bracket is required exactly when an opening one is there.
_DISC_SET_HEADER = re.compile(
    rf"^{_DECOR}(?:{_DISC}\s*(?:(?P<open>[(\[])\s*|[-–—/:,]\s*|(?<=\s))|{_DISC_WORD}\s*/\s*)"
    rf"{_SET_CORE}{_ANNOT}(?(open)\s*[)\]]){_ANNOT}"
    rf"(?:{_TAIL_ALONE}|{_TAIL_SONGS})",
    re.I,
)
# The set first, then the disc (Checkpoint A, (c)): `Set 1 Disc 1`, `Set I Disc 1: 74:16`,
# `set 1 - disc 1`, `Set 1/Disc 1:`, `set 2 / disc 2`. (llama-db reading of operator ruling
# (c): the unspaced dash join, `Set 1-Disk 1`.)
_SET_DISC_HEADER = re.compile(
    rf"^{_DECOR}{_SET_CORE}\s*(?:[-–—/]\s*)?{_DISC}{_ANNOT}(?:{_TAIL_ALONE}|{_TAIL_SONGS})",
    re.I,
)
_SET_HEADERS = (_SET_HEADER, _DISC_SET_HEADER, _SET_DISC_HEADER)
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

# An encore whose rest says there was none (`Encore: none`, `E: None Filler: ...`,
# `Encore: N/A`, `Encore: no encore`): the taper owns nothing (Checkpoint A). Tested on the
# marker's rest after decoration, and on the encore's first song item.
_ENCORE_NONE = re.compile(r"^[-–—*~=\[\]()\s]*(?:none|no\s+encores?|n/a)(?![\w/])", re.I)

# --- Reader-local item cleaning (Checkpoint A, R-ITEM). `parse_setlist` keeps all of these.
# A filename-style set/track token: `s2t01: Ripple`, `S1T02 Bertha`.
_SXT_PREFIX = re.compile(r"^\s*s\d{1,2}t\d{1,3}(?:\s*[:.\-]\s*|\s+)", re.I)
# A colon track number: `08: Ripple` (a following space required, so `1:08:07` is untouched).
_COLON_PREFIX = re.compile(r"^\s*\d{1,3}:\s+(?=\S)")
# An item that is only decoration, with no letter or digit: `=====`, `-`, `~~~ ***`, a
# footnote mark (`%`, `&`). A lone `?` (an unknown song) is kept.
_DECOR_ONLY = re.compile(r"^[^\w?]+$")
# In a header line's rest: an item that is only a parenthetical, `(Electric)`, `[Acoustic]`,
_PAREN_ONLY = re.compile(r"^\([^()]*\)$|^\[[^\[\]]*\]$")
# ... or only a disc label, `Disc 2:`, `-Disk 2`, `CD 2`.
_DISC_LABEL = re.compile(
    r"^[-–—*~=\s\[(]*(?:disc|disk|cd)\s*#?\s*(?:\d{1,2}|one|two|three|four|five|six|iv|i{1,3})"
    r"(?!\w)[-–—\])\s:.]*$",
    re.I,
)
# Stands in for a comma that must not split (a numbered title on an enumerated text).
_COMMA = "\x00"
_TITLE_COMMA = re.compile(r",(?=\s*[^\W\d_])")

# --- Encore-like text (section 2's veto input), matched only OUTSIDE recognised markers.
# `\bencor\b` is the `Encor:` typo (Checkpoint A, the veto gap).
_ENCORE_WORDS = re.compile(r"\bencores?\b|\benc\b|\bencor\b", re.I)
# A song line (after track-prefix stripping) starting `E.`, `E)`, `E` plus a digit, `(E)`.
_ENCORE_LIKE_START = re.compile(r"^(?:e[.)]|e\d|\(e\))", re.I)
# The same test is also made after this unconditional bare-number strip (ruling R4 (d)).
_LEADING_NUMBER = re.compile(r"^\d{1,3}\s+")
# A song line ending ` E`, ` (E)`, ` [E]` or `, E` (ruling R4 (b)).
_ENCORE_LIKE_END = re.compile(r"\s(?:e|\(e\)|\[e\])$|,\s*e$", re.I)
# A split song item that is only `E`, `E<digit>` or `ENC` (ruling R4 (a), (c)).
_ENCORE_LIKE_ITEM = re.compile(r"^(?:e\d?|enc)$", re.I)
# Checkpoint A, the veto gap (only raises `encore_like`; nothing here starts an encore):
# an `E` glued to the track number (`9E.Wayfaring Stranger`);
_ENCORE_GLUED = re.compile(r"^\d{1,3}e[.):]", re.I)
# a song line `E <Title>` (`E Ripple`, `24. E Ripple`), case-sensitive;
_ENCORE_E_SPACE = re.compile(r"^(?:\d+\.?\s+)?E\s+[A-Z]")
# a decorated `E~` or `-e-` anywhere (`Tap In, E~ Twilight`, `Orbital  E~ Water Song`,
# `Just thanks,-e- Freq.1>2`).
_ENCORE_DECORATED_E = re.compile(r"(?<![a-z0-9])e~|-e-", re.I)
_ITEM_DECOR = "-–—*~=[]() \t"

# --- Set-like text (llama-db ruling, Checkpoint A2, 2026-10-22), the own-less veto's input:
# `_SET_TOKEN` (any spelling the reader reads as a numbered set), word-bounded on the left
# too, found INSIDE an item of a numbered set (`Set 1.5:`, `- end of set one`,
# `Cardinals Set 1 CD 2`). It never makes a marker.
_SET_LIKE = re.compile(rf"\b{_SET_TOKEN}", re.I)
# A continuation of the item's own set (`Set 2 con't` inside set 2): not set-like
# (orchestrator ruling R9, 2026-10-22, confirmed by llama-db, 2026-10-22). Used with `.match`
# on the text right after the token, so it anchors there; no `^`, so that a `.search` would
# not be an equivalent mutant (fix round 1, finding 2).
_CONT_AFTER = re.compile(r"\s*[,(]?\s*con(?:'|’)?t", re.I)


_HELD = re.compile(r"^\x00\d+\x00$")


def _set_header_match(core: str) -> re.Match | None:
    """The numbered-set header regex matching one prefix-stripped line, if any."""
    for rx in _SET_HEADERS:
        m = rx.match(core)
        if m:
            return m
    return None


def _split_set_and_encore(line: str) -> tuple[str, str] | None:
    """(header, rest) when the RAW line is a header naming both a set and the encore
    (`Set II & Encore:`, `Set 3 / Encore: ...`, `Disc 3 - Set II + Encore:`), else None.
    Tested before `_INLINE_MARKER`'s split, which would otherwise cut the line before its
    `Encore:` and start the encore there. Any prefix is stripped only to test the shape."""
    core = _TRACK_PREFIX.sub("", line)
    core = _NUM_PREFIX.sub("", core)
    m = _set_header_match(core)
    if not m or not m.group("andenc"):
        return None
    cut = len(line) - len(core) + (m.start("rest") if m.group("rest") is not None else len(core))
    return line[:cut].strip(), line[cut:].strip()


def _preprocess(text: str) -> list[str]:
    """`parse_setlist`'s own preprocessing (no truncation), then `_emit_items`'s inline
    split, as stripped lines. A set-and-encore header is kept whole (`_split_set_and_encore`);
    only the songs after it are split."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    # The split runs over the JOINED lines, exactly as `_emit_items` runs it (its `\s+` may
    # span a line break). A set-and-encore header is swapped for a placeholder the split
    # cannot match, and restored after.
    held: list[str] = []
    raw: list[str] = []
    for ln in text.splitlines():
        ln = ln.strip()
        both = _split_set_and_encore(ln)
        if both:
            raw.append(f"\x00{len(held)}\x00")
            held.append(both[0])
            ln = both[1]
        raw.append(ln)
    lines = [ln.strip() for ln in _INLINE_MARKER.sub("\n", "\n".join(raw)).splitlines()]
    return [held[int(ln[1:-1])] if _HELD.match(ln) else ln for ln in lines]


def _classify(core: str) -> tuple[str, int | None, bool, bool, str]:
    """(kind, set number, continuation, set-and-encore, rest) for one prefix-stripped line.
    kind is "set" | "encore" | "song"."""
    m = _set_header_match(core)
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
    if (_ENCORE_WORDS.search(text) or _ENCORE_LIKE_END.search(text)
            or _ENCORE_DECORATED_E.search(text)):
        return True
    if _ENCORE_LIKE_START.match(text) or _ENCORE_LIKE_START.match(_LEADING_NUMBER.sub("", text)):
        return True
    if _ENCORE_GLUED.match(text) or _ENCORE_E_SPACE.match(text):
        return True
    return any(_ENCORE_LIKE_ITEM.match(title.strip(_ITEM_DECOR)) for title, _ in _split_songs(text))


def _strip_title_prefix(text: str, enumerated: bool) -> tuple[str, bool]:
    """(text, numbered): AT MOST ONE leading prefix stripped, the first of `_TRACK_PREFIX`,
    `_SXT_PREFIX`, `_COLON_PREFIX` that strips anything, else (enumerated text only)
    `_NUM_PREFIX`. Unlike `_emit_items`, which strips `_TRACK_PREFIX` and then `_NUM_PREFIX`,
    a second number is the title's own: `04. 44 Blues` is `44 Blues`, not `Blues`."""
    rxs = (_TRACK_PREFIX, _SXT_PREFIX, _COLON_PREFIX) + ((_NUM_PREFIX,) if enumerated else ())
    for rx in rxs:
        out = rx.sub("", text)
        if out != text:
            return out, True
    return text, False


def _song_titles(rest: str, enumerated: bool, *, header_rest: bool = False) -> list[str]:
    """Song items from the text after a marker (`header_rest`), or from a whole (unstripped)
    song line. The prefix is stripped here once (`_strip_title_prefix`), never also by the
    caller. Reader-local cleaning (Checkpoint A), none of it in `parse_setlist`: items that
    are only decoration are dropped; in a header line's rest, so are items that are only a
    parenthetical (`Set 2: (Electric)`) or only a disc label (`Set 2: Disc 2:`); and on an
    enumerated text a numbered line is one title, not split on its commas
    (`9. Quantico, VA`)."""
    rest, numbered = _strip_title_prefix(rest, enumerated)
    if _BARE_NUMBER.match(rest.strip()):
        return []
    rest = _LEAD_TIMESTAMP.sub("", rest.strip())
    if enumerated and numbered:
        # One title per numbered line: a comma followed by a word stays in the title
        # (`Quantico, VA`). A comma before a footnote mark, a duration or the line end
        # (`Casualty,*`, `Intro,  [1:03]`) still splits, so those stay apart.
        rest = _TITLE_COMMA.sub(_COMMA, rest)
    titles = []
    for title, _segue in _split_songs(rest):
        title = title.replace(_COMMA, ",")
        if len(title) > MAX_TITLE_LEN or is_junk_title(title) or _TIMESTAMP_ONLY.match(title):
            continue
        if _DECOR_ONLY.match(title):
            continue
        if header_rest and (_PAREN_ONLY.match(title) or _DISC_LABEL.match(title)):
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
            if _ENCORE_NONE.match(rest):
                s.set_void("encore none")
        for title in _song_titles(rest, enumerated, header_rest=kind != "song"):
            lab = s.label()
            if lab == "encore" and s.songs.get("encore", 0) == 0 and _ENCORE_NONE.match(title):
                s.set_void("encore none")
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


def _set_like(items: tuple[TaperItem, ...]) -> bool:
    """An item of a numbered set holds a set token (`_SET_LIKE`) that is not a continuation
    of that same set, or is exactly `Set` once decoration is stripped (the second half of an
    ordinal header the inline split cut: `Third` / `Set`). Every token in an item is checked.
    The encore's items (its songs and any notes after them, `Trey Anastasio plays entire 2nd
    set and encore`) are skipped."""
    for item in items:
        if item.set == "encore":
            continue
        if item.title.strip(_ITEM_DECOR).lower() == "set":
            return True
        for m in _SET_LIKE.finditer(item.title):
            token = (m.group("tok") or m.group("ord") or m.group("ordn")).lower()
            number = _TOKEN_NUM.get(token) or int(token)
            if str(number) == item.set and _CONT_AFTER.match(item.title[m.end():]):
                continue
            return True
    return False


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
                     encore_like=s.encore_like, reason=reason, set_like=_set_like(items))


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


# --- Exact placement and the ownership decision (spec sections 2 and 3). ---


@dataclass(frozen=True)
class TaperPlacement:
    sets: tuple[str, ...]  # per-track labels, parallel to tracks
    boundaries: tuple[int, ...]  # 1-based track index after which each boundary falls


@dataclass(frozen=True)
class TaperDecision:
    placement: TaperPlacement | None  # None when not owned
    taper: TaperText
    source: str  # "description" | "notes" | "none"
    reason: str | None  # why not owned (the reader's reason, "veto: track title",
    # "veto: encore-like text", "veto: set-like text", a placement decline,
    # "veto: step-1 break before set 1", "veto: today's encore", or
    # "veto: no encore on today's LLM path")


def _counts(track: Track) -> bool:
    return track.title_source != "unresolved" and track.title_source not in TAUTOLOGICAL_TITLE_SOURCES


def _comma_parts(title: str) -> list[str]:
    """The comma parts of an item the comma rule kept whole, else []. Only a comma outside
    brackets separates parts: one inside a credit, `(SM, NA)`, splits no song."""
    parts, depth, cur = [], 0, ""
    for ch in title:
        depth += ch in "([" and 1 or ch in ")]" and -1 or 0
        if ch == "," and depth <= 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else []


def _hit(track: Track, target: str, aliases: dict[str, str]) -> bool:
    """Section 3's matching: the track counts (`_counts`) and its title, or a title
    component of a merged track, is `fuzzy_title_eq` to `target` (already normalized)."""
    if not _counts(track):
        return False
    if fuzzy_title_eq(fuzzy_norm_title(track.title, aliases), target):
        return True
    return any(fuzzy_title_eq(c, target) for c in title_components(track.title, aliases))


def _place_boundary(tracks: list[Track], left: list[TaperItem], right: list[TaperItem],
                    aliases: dict[str, str], today_sets: list[str]
                    ) -> tuple[int, int, int] | str:
    """(boundary position, a position, b position), 0-based, or the decline reason."""
    def norm(title: str) -> str:
        return fuzzy_norm_title(title, aliases)

    a_norm, b_norm = norm(left[-1].title), norm(right[0].title)
    # A comma in an item is one the comma rule kept (`_song_titles`); `_split_songs` splits
    # every other. The item may still be two songs (`Native End, Open E`), so its comma
    # parts count as songs of that side too (fix round 1).
    left_norms = [norm(t) for i in left for t in (i.title, *_comma_parts(i.title))]
    right_norms = [norm(t) for i in right for t in (i.title, *_comma_parts(i.title))]

    def hit(track: Track, target: str) -> bool:
        return _hit(track, target, aliases)

    a_hits = [i for i, t in enumerate(tracks) if hit(t, a_norm)]
    b_hits = [i for i, t in enumerate(tracks) if hit(t, b_norm)]
    if len(a_hits) != 1:
        return f"last song {left[-1].title!r} matches {len(a_hits)} tracks"
    if len(b_hits) != 1:
        return f"first song {right[0].title!r} matches {len(b_hits)} tracks"
    a, b = a_hits[0], b_hits[0]
    if a >= b:
        return "songs out of order"
    # A boundary item's later comma part naming a song on the tape (another track, or a
    # component of its own merged track) means the item may be two songs, and which one
    # sits at the boundary is unknown: decline rather than guess.
    for item, pos in ((left[-1], a), (right[0], b)):
        for part in _comma_parts(item.title)[1:]:
            p_norm = norm(part)
            comps = title_components(tracks[pos].title, aliases)
            if (any(hit(t, p_norm) for k, t in enumerate(tracks) if k != pos)
                    or (len(comps) > 1 and any(fuzzy_title_eq(c, p_norm) for c in comps))):
                return f"comma-joined {item.title!r} names a second song on the tape"
    a_all = [a_norm, *(norm(t) for t in _comma_parts(left[-1].title))]
    b_all = [b_norm, *(norm(t) for t in _comma_parts(right[0].title))]
    if any(fuzzy_title_eq(x, n) for x in a_all for n in right_norms):
        return f"{left[-1].title!r} also occurs on the other side"
    if any(fuzzy_title_eq(x, n) for x in b_all for n in left_norms):
        return f"{right[0].title!r} also occurs on the other side"
    for pos in (a, b):
        comps = title_components(tracks[pos].title, aliases)
        if len(comps) > 1:
            on_left = any(fuzzy_title_eq(c, n) for c in comps for n in left_norms)
            on_right = any(fuzzy_title_eq(c, n) for c in comps for n in right_norms)
            if on_left and on_right:
                return "a merged track spans the boundary"
    for t in tracks[a + 1:b]:
        if not is_filler(t.title) or not _counts(t):
            return f"non-filler track {t.title!r} between the songs"
    splits = [k for k in range(a, b) if k + 1 < len(today_sets) and today_sets[k] != today_sets[k + 1]]
    if b - a > 1 and splits:
        if len(splits) > 1:
            return "today's structure splits the filler run more than once"
        return splits[0], a, b
    return a, a, b


def place_taper_structure(tracks: list[Track], taper: TaperText, *,
                          aliases: dict[str, str], today_sets: list[str]
                          ) -> TaperPlacement | str:
    """The placement, or a decline reason ("unplaced: <A>|<B> <why>")."""
    groups: list[tuple[str, list[TaperItem]]] = []
    for item in taper.items:
        if groups and groups[-1][0] == item.set:
            groups[-1][1].append(item)
        else:
            groups.append((item.set, [item]))
    if len(groups) < 2:
        return "unplaced: fewer than two sets"
    flat = [i for _, g in groups for i in g]
    bounds: list[int] = []  # 0-based positions after which a boundary falls
    prev_b = -1
    offset = 0
    for (la, ga), (lb, gb) in zip(groups, groups[1:]):
        offset += len(ga)
        left, right = flat[:offset], flat[offset:]
        # `left`/`right` are every item on each side; the boundary's own songs are the
        # last of A and the first of B.
        res = _place_boundary(tracks, left, right, aliases, today_sets)
        if isinstance(res, str):
            return f"unplaced: {la}|{lb} {res}"
        pos, a, b = res
        if a < prev_b or pos <= (bounds[-1] if bounds else -1):
            return f"unplaced: {la}|{lb} boundaries out of order"
        bounds.append(pos)
        prev_b = b
    labels: list[str] = []
    cur = 0
    for i in range(len(tracks)):
        labels.append(groups[cur][0])
        if cur < len(bounds) and i == bounds[cur]:
            cur += 1
    return TaperPlacement(sets=tuple(labels), boundaries=tuple(p + 1 for p in bounds))


B4_BREAK = "veto: step-1 break before set 1"


def _step1_break_before_set_1(tracks: list[Track], taper: TaperText, placed: TaperPlacement,
                              aliases: dict[str, str], today_sets: list[str]) -> str | None:
    """B4's decline reason, or None. Step 1 has a NUMBERED break (a label change between
    two numbered sets, never an encore boundary) before the hit of the taper's set-1 first
    song: a change between tracks k and k+1 with k < h, h the 0-based hit. A break AT the
    hit (between h and h+1) does not count. The hit is searched among the tracks at or
    before set 1's placed boundary. When set 1's first song item matches no such track, the
    next set-1 item stands in (my call: placement guarantees set 1's last song has one).
    When the item matches several such tracks, the hit is the LATEST of them, the own-less
    reading: a step-1 break the earliest hit would hide still declines (llama-db ruling,
    2026-10-22, narrowed the same day; the stand-in item is treated the same way)."""
    last = placed.boundaries[0] - 1  # 0-based: no set-1 song sits past set 1's boundary
    h = None
    for item in (i for i in taper.items if i.set == "1"):
        target = fuzzy_norm_title(item.title, aliases)
        hits = [k for k, t in enumerate(tracks[:last + 1]) if _hit(t, target, aliases)]
        if hits:
            h = hits[-1]
            break
    if h is None:
        return None
    if any(today_sets[k] != today_sets[k + 1]
           and today_sets[k] != "encore" and today_sets[k + 1] != "encore"
           for k in range(min(h, len(today_sets) - 1))):
        return B4_BREAK
    return None


def decide_taper(tracks: list[Track], meta: dict, *, aliases: dict[str, str],
                 today_sets: list[str], today_reaches_llm: bool) -> TaperDecision:
    """The one ownership decision (spec sections 2-4). `today_sets` is step 1's per-track
    labels; `today_reaches_llm` is gather's own "today's path would reach the LLM branch"
    predicate (canonical items, no jerrybase anchoring, step-1 coverage under
    `align_coverage_threshold`), computed once in `compute_gather` and passed in.
    Required, not defaulted, so no caller can forget it: a default would make the G1 veto
    fail open (llama-db, 2026-10-22). Callers with no gather pass a stand-in explicitly
    (the probe's stored proxy)."""
    text, source = taper_text_for(meta)
    taper = read_taper_structure(text)
    if not taper.asserts:
        return TaperDecision(None, taper, source, taper.reason)
    if not taper.has_encore:
        if any(_ENCORE_MARKER.search(t.title) for t in tracks):
            return TaperDecision(None, taper, source, "veto: track title")
        if taper.encore_like:
            return TaperDecision(None, taper, source, "veto: encore-like text")
    if taper.set_like:
        # llama-db ruling, Checkpoint A2, 2026-10-22: set-like text the reader does not
        # recognise (a set token inside an item of a numbered set) means the taper owns
        # nothing, as the encore-like veto does for an unrecognised encore.
        return TaperDecision(None, taper, source, "veto: set-like text")
    placed = place_taper_structure(tracks, taper, aliases=aliases, today_sets=today_sets)
    if isinstance(placed, str):
        return TaperDecision(None, taper, source, placed)
    b4 = _step1_break_before_set_1(tracks, taper, placed, aliases, today_sets)
    if b4 is not None:
        # (llama-db reading of operator ruling (d), 2026-10-22; acceptance defect B4,
        # stevekimockband-2000-03-31): the taper owns nothing when step 1 has a numbered
        # break before the hit of the taper's set-1 first song. Lines before an explicit
        # `Set 1` are header text to the reader (section 2), so an unrecognised leading set
        # (`Happy Hour Set:`) would otherwise fold into set 1 and erase today's break there.
        # With several hits for set 1's first song, the break is checked against the LATEST
        # (llama-db ruling, 2026-10-22, narrowed the same day).
        return TaperDecision(None, taper, source, b4)
    if not taper.has_encore and "encore" in today_sets[placed.boundaries[-1]:]:
        # Operator ruling 2026-10-22 (Checkpoint A, (d)), keep today's encore: the taper
        # marks no encore, and today's step-1 structure has an encore boundary after the
        # taper's last placed numbered break. The show is computed as today; this only
        # turns ownership off, never a merge. (llama-db reading of operator ruling (d): an
        # `encore` label on any track after that break, `today_sets[boundaries[-1]:]`.)
        return TaperDecision(None, taper, source, "veto: today's encore")
    if not taper.has_encore and today_reaches_llm:
        # (llama-db reading of operator ruling (d), 2026-10-22; acceptance defect G): ruling
        # (d)'s "keep the encore" read as "what today ships". When today's path would reach
        # the LLM branch, step 1 is not what today ships, so its lack of an encore is
        # evidence of nothing and today's encore is unknowable offline: with no recognised
        # taper encore marker the taper owns nothing (johnkadlecik-2013-06-22,
        # newridersofthepurplesage-2006-04-08, radiators-2010-06-05, jackiegreene-2011-02-12).
        return TaperDecision(None, taper, source, "veto: no encore on today's LLM path")
    return TaperDecision(placed, taper, source, None)
