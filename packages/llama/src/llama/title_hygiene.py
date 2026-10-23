"""Title hygiene (piece 3): definitions, comparators and check 1.

Pure: no IO, no gather wiring. Check 1 (`judge`) calls `structure.hygienic_title` with
`require_real=False` and never re-composes its clauses; the class a note names for a
`hygienic_title` failure is derived afterwards, for the note only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from llama.desc_list import Cleaned, DescList, clean_one, is_header_shape, written_seconds
from llama.placeholders import is_placeholder, is_residue, is_timestamp, looks_like_filename
from llama.models import ParsedSetlist, Track
from llama.setlist import MAX_TITLE_LEN
from llama.siblings import MIN_ANCHORS
from llama.structure import (
    fuzzy_norm_title,
    fuzzy_title_eq,
    hygienic_title,
    is_filler,
    loosely_same_title,
)
from llama.titles import is_real_title

# Independent titles (spec, Definitions). NOT `siblings.INDEPENDENT_TITLE_SOURCES`.
INDEPENDENT_SOURCES = frozenset({"tags", "sibling-format", "override", "sibling-align"})
DESC_POSITION = "desc-position"
ALL_SLICES = frozenset({"slice1", "slice2", "slice3", "slice4", "slice5"})
ENABLED_SLICES = ALL_SLICES

AGREEMENT_FLOOR = 0.5
WRITTEN_DURATION_MIN_SHARE = 0.5
WRITTEN_DURATION_TOL_SEC = 15.0
WRITTEN_DURATION_TOL_FRAC = 0.10
SHORT_CORE_LETTERS = 3
SHORT_TAG_WINDOW = 2
STEM_SUBSTRING_MIN = 2

_QUESTION_ONLY = re.compile(r"^[?\s,;.]*\?[?\s,;.]*$")
_UNKNOWN = re.compile(r"^\s*(?:unknown|unk|\(unknown\))\s*$", re.I)
_BARE_NUMBER = re.compile(r"^\d+[.\-)]?$")
_ANNOTATION = re.compile(r"^\s*w/\s|\bopened\b", re.I)
_LEAD_TIME = re.compile(r"^\s*\(?\s*\d{1,3}:\d{2}(?::\d{2})?\s*(?:[)\]]|\s-\s)")


def _short_core(norm: str) -> bool:
    return sum(1 for ch in norm if ch.isascii() and ch.isalpha()) < SHORT_CORE_LETTERS


def agrees(a: str, b: str, aliases: dict[str, str] | None = None) -> bool:
    """Do two titles agree, on cleaned copies. A short core compares by
    `fuzzy_norm_title` equality only; otherwise `loosely_same_title`, unmodified.
    `aliases` is passed only by `agreement_share`."""
    na = fuzzy_norm_title(clean_one(a).text, aliases)
    nb = fuzzy_norm_title(clean_one(b).text, aliases)
    if not na or not nb:
        return False
    if _short_core(na) or _short_core(nb):
        return na == nb
    return loosely_same_title(na, nb)


def duplicate(a: str, b: str) -> bool:
    """Check 2's comparator: filler on either side never matches."""
    if is_filler(a) or is_filler(b):
        return False
    na, nb = fuzzy_norm_title(a), fuzzy_norm_title(b)
    if not na or not nb:
        return False
    return na == nb or fuzzy_title_eq(na, nb)


@dataclass(frozen=True)
class Hygiene:
    ok: bool
    scope: str | None  # "show" | "track" | None
    check: str | None


_OK = Hygiene(True, None, None)


def _track(check: str) -> Hygiene:
    return Hygiene(False, "track", check)


def _show(check: str) -> Hygiene:
    return Hygiene(False, "show", check)


def judge(c: Cleaned, *, track_no: int, first: bool, stem: str, own_core: str,
          metadata_norms: set[str]) -> Hygiene:
    """Check 1 on one cleaned entry. `track_no` is 1-BASED."""
    text = c.text
    if c.filler_marked:
        return _track("filler entry")
    # Per-track: slot placeholders keep the list 1:1.
    if _QUESTION_ONLY.match(text) or is_placeholder(text) or _UNKNOWN.match(text):
        return _track("slot placeholder")
    if _BARE_NUMBER.match(text):
        digits = re.sub(r"\D", "", text)
        if digits != own_core.strip() and (
            digits.startswith("0") or int(digits) == track_no
        ):
            return _track("slot placeholder")
    norm = fuzzy_norm_title(text)
    meta_hit = bool(norm) and norm in metadata_norms
    if meta_hit and not first:
        return _track("metadata")
    # Show-level: such an entry takes a slot, so the list is not 1:1 with the files.
    if meta_hit and first:
        return _show("hygiene:banner")
    if is_header_shape(text):
        return _show("hygiene:header")
    if _ANNOTATION.search(text):
        return _show("hygiene:annotation")
    if is_timestamp(text) or (
        _LEAD_TIME.match(text) and not re.search(r"[^\W\d_]", _LEAD_TIME.sub("", text, count=1))
    ):
        return _show("hygiene:timestamp")
    if (looks_like_filename(text) or text.lower() == stem.strip().lower()
            or (is_real_title(text) and is_residue(text))):
        return _show("hygiene:filename residue")
    if not any(ch.isalnum() for ch in text):
        return _show("hygiene:no alnum")
    if not hygienic_title(text, metadata_norms, require_real=False):
        # Named for the note only; never decides.
        t = text.strip()
        if t.endswith(":"):
            return _show("hygiene:trailing colon")
        if len(t) > MAX_TITLE_LEN:
            return _show("hygiene:over length")
        return _show("hygiene:junk title")
    return _OK


def _has_title(t: Track) -> bool:
    return t.title_source != "unresolved" and bool(t.title.strip())


def adjacent_duplicate(cands: dict[int, str], tracks: list[Track]) -> tuple[int, str, str] | None:
    """Check 2. `cands` maps a 0-BASED position to its candidate; a neighbour is its own
    candidate if it has one, else its current title when not unresolved. First hit."""
    for pos in sorted(cands):
        for nb in (pos - 1, pos + 1):
            if nb < 0 or nb >= len(tracks):
                continue
            if nb in cands:
                other = cands[nb]
            elif _has_title(tracks[nb]):
                other = tracks[nb].title
            else:
                continue
            if duplicate(cands[pos], other):
                return pos, cands[pos], other
    return None


def position_agreement(track: Track, c: Cleaned) -> str:
    """Check 3's judgement of one position, on the entry's cleaned text (a `Filler:`
    marker is already stripped; `filler_marked` plays no part). No aliases."""
    if track.title_source not in INDEPENDENT_SOURCES:
        return "skip"
    tf, ef = is_filler(track.title), is_filler(c.text)
    if tf and ef:
        return "neutral"
    if tf != ef:
        return "disagree"
    return "agree" if agrees(track.title, c.text) else "disagree"


def tape_disagreement(tracks: list[Track], dl: DescList) -> tuple[int, str, str] | None:
    """Check 3: the first position (0-based) whose independent title disagrees with the
    list entry there, as (pos, title, entry text)."""
    for pos in range(min(len(tracks), len(dl.cleaned))):
        if position_agreement(tracks[pos], dl.cleaned[pos]) == "disagree":
            return pos, tracks[pos].title, dl.cleaned[pos].text
    return None


def written_duration_mismatch(tracks: list[Track], dl: DescList) -> tuple[int, float, float] | None:
    """Written durations: with at least `WRITTEN_DURATION_MIN_SHARE` of the entries carrying
    one, the first position (0-based) whose file length is off by more than
    max(TOL_SEC, TOL_FRAC * written), as (pos, file, written). A track with no length is
    skipped."""
    n = len(dl.cleaned)
    if not n:
        return None
    written = [written_seconds(c) for c in dl.cleaned]
    if sum(1 for w in written if w is not None) < WRITTEN_DURATION_MIN_SHARE * n:
        return None
    for pos in range(min(len(tracks), n)):
        w, f = written[pos], tracks[pos].duration_sec
        if w is None or f is None:
            continue
        if abs(f - w) > max(WRITTEN_DURATION_TOL_SEC, WRITTEN_DURATION_TOL_FRAC * w):
            return pos, f, w
    return None


def agreement_share(dl: DescList, canonical: ParsedSetlist,
                    aliases: dict[str, str]) -> float | None:
    """Share of the list's song-like entries that some canonical item matches (order-free,
    whole list). The ONE place `GD_SHORTHAND` is expanded: the caller passes it for a
    family artist, `{}` otherwise."""
    if not canonical.items:
        return None
    songs = [c.text for c in dl.cleaned if not c.filler_marked and not is_filler(c.text)]
    if not songs:
        return None
    hit = sum(1 for e in songs if any(agrees(e, it.title, aliases) for it in canonical.items))
    return hit / len(songs)


def wholly_untagged(tag_titles: list[str], demoted: frozenset[int]) -> bool:
    """Fewer than `MIN_ANCHORS` song-like real tag titles (0-based positions in `demoted`
    are 2b-demoted and do not count)."""
    real = sum(1 for i, t in enumerate(tag_titles)
               if i not in demoted and not is_filler(t) and is_real_title(t))
    return real < MIN_ANCHORS
