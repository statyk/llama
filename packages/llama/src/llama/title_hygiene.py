"""Title hygiene (piece 3): definitions, comparators, the checks and the D decision.

Pure: no IO, no gather wiring. Check 1 (`judge`) calls `structure.hygienic_title` with
`require_real=False` and never re-composes its clauses; the class a note names for a
`hygienic_title` failure is derived afterwards, for the note only.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from llama.desc_list import (
    Cleaned,
    DescList,
    clean_entries,
    clean_one,
    is_header_shape,
    written_seconds,
)
from llama.placeholders import is_junk_tag, is_placeholder, is_residue, is_timestamp, looks_like_filename
from llama.models import ParsedSetlist, Track
from llama.setlist import MAX_TITLE_LEN
from llama.siblings import MIN_ANCHORS, DonorTape, SiblingRow
from llama.structure import (
    fuzzy_norm_title,
    fuzzy_title_eq,
    hygienic_title,
    is_filler,
    loosely_same_title,
)
from llama.titles import is_placeholder_text, is_real_title, shipped_short_tag, tag_core

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
# Checkpoint A ruling P2: one leading set/encore prefix, stripped for the ?-only test only.
_SET_PREFIX = re.compile(r"^\s*(?:set\s*)?(?:\d{1,2}|[ivx]{1,4}|e|enc|encore)\s*:\s*", re.I)
_UNKNOWN = re.compile(r"^\s*(?:unknown|unk|\(unknown\))\s*$", re.I)
_BARE_NUMBER = re.compile(r"^\d+[.\-)]?$")
_ANNOTATION = re.compile(r"^\s*w/\s|\bopened\b", re.I)
_LEAD_TIME = re.compile(r"^\s*\(?\s*\d{1,3}:\d{2}(?::\d{2})?\s*(?:[)\]]|\s-\s)")
# Final review M-1, Checkpoint B ruling 5: a lone `Encore` (optional `:`), `Set Break`,
# `Setbreak` or `Intermission`, as the whole entry, is a header shape in check 1. An
# addition beside the fixed grammar (`desc_list.is_header_shape`); `taper._SET_HEADERS` is
# not edited.
_LONE_MARKER = re.compile(r"^\s*(?:encore\s*:?|set ?break|intermission)\s*$", re.I)


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
    if (_QUESTION_ONLY.match(text) or _QUESTION_ONLY.match(_SET_PREFIX.sub("", text, count=1))
            or is_placeholder(text) or _UNKNOWN.match(text)):
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
    if is_header_shape(text) or _LONE_MARKER.match(text):
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
    if _QUESTION_ONLY.match(c.text):
        return "neutral"  # Checkpoint A ruling P1: a `?` slot placeholder is no evidence
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


def _agreement(dl: DescList, canonical: ParsedSetlist,
               aliases: dict[str, str]) -> tuple[float, int | None] | None:
    """`agreement_share`'s computation: (share, 0-based position of the first song-like
    entry no canonical item matches, or None)."""
    if not canonical.items:
        return None
    songs = [i for i, c in enumerate(dl.cleaned) if not c.filler_marked and not is_filler(c.text)]
    if not songs:
        return None
    misses = [i for i in songs
              if not any(agrees(dl.cleaned[i].text, it.title, aliases) for it in canonical.items)]
    return (len(songs) - len(misses)) / len(songs), (misses[0] if misses else None)


def agreement_share(dl: DescList, canonical: ParsedSetlist,
                    aliases: dict[str, str]) -> float | None:
    """Share of the list's song-like entries that some canonical item matches (order-free,
    whole list). The ONE place `GD_SHORTHAND` is expanded: the caller passes it for a
    family artist, `{}` otherwise."""
    got = _agreement(dl, canonical, aliases)
    return None if got is None else got[0]


def wholly_untagged(tag_titles: list[str], demoted: frozenset[int]) -> bool:
    """Fewer than `MIN_ANCHORS` song-like real tag titles (0-based positions in `demoted`
    are 2b-demoted and do not count)."""
    real = sum(1 for i, t in enumerate(tag_titles)
               if i not in demoted and not is_filler(t) and is_real_title(t))
    return real < MIN_ANCHORS


# ---- Slice 2: the untagged checks and the D decision -------------------------------------

# Every show-level check name not starting `hygiene:`: a decline on one of these is a shift
# signature, and S (deferred) declines with D.
SHIFT_CHECKS = frozenset({"adjacent duplicate", "tape agreement", "written durations",
                          "block size", "sibling durations", "agreement"})

# Filename stem (basename minus extension), last match wins. The token must sit directly
# before a track token, after a non-letter, so `sbd`, `dsbd` and words stay out.
_DISC_INDEX = re.compile(
    r"(?<![a-z])(?:cd|disc|disk|d)[\s_\-]*0?(\d{1,2})[\s_\-.]*(?:t|tr|trk|track)[\s_\-]*\d{1,3}",
    re.I)
_SET_INDEX = re.compile(
    r"(?<![a-z])(?:set|s)[\s_\-]*0?(\d{1,2})[\s_\-.]*(?:t|tr|trk|track)[\s_\-]*\d{1,3}",
    re.I)


def _stem(filename: str) -> str:
    return os.path.splitext(os.path.basename(filename))[0]


def _index(rx: re.Pattern, filename: str) -> int | None:
    found = list(rx.finditer(_stem(filename)))
    return int(found[-1].group(1)) if found else None


def _detail(pos: int, text: str) -> str:
    """The note's `(track <n> '<text>')` payload; `pos` is 0-based."""
    return f"track {pos + 1} '{text}'"


def block_size_mismatch(filenames: list[str], dl: DescList, *,
                        fold_encore: bool = True) -> str | None:
    """Untagged check (a). Each block's entry count must equal its disc's (or set's) file
    count; returns the first mismatched block's first entry as a note detail, or None
    (passed or inert). Inert unless the list has 2+ blocks after folding, every filename
    yields the index, the index takes exactly as many values as there are blocks, and the
    files are grouped by index in play order. `fold_encore=False` is the probe's
    alternative (row R10); gather never passes it."""
    # Fold: block b starts at boundary b-1; an `encore` block joins the one before it.
    fid = [0]
    kept: list[str] = []
    for b in dl.boundaries:
        if fold_encore and b == "encore":
            fid.append(fid[-1])
        else:
            fid.append(fid[-1] + 1)
            kept.append(b)
    blocks = [fid[b] for b in dl.blocks]
    n_blocks = len(kept) + 1
    if n_blocks < 2 or not filenames:
        return None
    sets = [_index(_SET_INDEX, f) for f in filenames]
    if all(b == "set" for b in kept) and all(s is not None for s in sets):
        idx = sets
    else:
        idx = [_index(_DISC_INDEX, f) for f in filenames]
        if any(i is None for i in idx):
            return None
    groups: list[int] = []  # file counts per index value, in play order
    seen: list[int] = []
    for i in idx:
        if seen and seen[-1] == i:
            groups[-1] += 1
            continue
        if i in seen:
            return None  # not grouped by index in play order
        seen.append(i)
        groups.append(1)
    if len(groups) != n_blocks:
        return None
    sizes = [blocks.count(k) for k in range(n_blocks)]
    for k in range(n_blocks):
        if sizes[k] != groups[k]:
            first = blocks.index(k) if sizes[k] else sum(sizes[:k])
            if first >= len(dl.cleaned):
                return _detail(len(dl.cleaned) - 1, dl.cleaned[-1].text)
            return _detail(first, dl.cleaned[first].text)
    return None


def sibling_disagreement(cands: dict[int, str],
                         donor: tuple[DonorTape, list[SiblingRow]] | None
                         ) -> tuple[int, str, str] | None:
    """Untagged check (b). `cands` keys are 0-BASED positions; `SiblingRow.track` is 1-BASED.
    A pair is a row whose `donor_span` has length 1 and is shared by no other row, whose
    donor title passes `is_real_title`, and whose position has a candidate; a pair with filler
    on either side counts toward `MIN_ANCHORS` but is neutral (never disagrees). Check 3's
    comparator, no aliases. Fewer than
    `MIN_ANCHORS` pairs is inert. Returns the first disagreement (pos, candidate, donor
    title)."""
    if donor is None:
        return None
    tape, rows = donor
    spans = [r.donor_span for r in rows if r.donor_span is not None]
    pairs: list[tuple[int, str, str]] = []
    for r in sorted(rows, key=lambda r: r.track):
        span = r.donor_span
        if span is None or span[1] - span[0] != 1 or spans.count(span) != 1:
            continue
        pos = r.track - 1
        if pos not in cands or not 0 <= span[0] < len(tape.titles):
            continue
        title = tape.titles[span[0]].strip()
        if not title or not is_real_title(title):
            continue
        pairs.append((pos, cands[pos], title))
    if len(pairs) < MIN_ANCHORS:
        return None
    for pos, cand, title in pairs:
        if is_filler(title) or is_filler(cand):
            continue  # neutral: counted as a pair, never a disagreement
        if not agrees(cand, title):
            return pos, cand, title
    return None


@dataclass(frozen=True)
class DDecision:
    fills: dict[int, str]                    # 0-based -> shipped text; empty on a show decline
    failed: tuple[tuple[str, str], ...]      # every show-level failure (check, detail), in order
    track_declines: dict[int, str]           # 0-based -> per-track check

    @property
    def shift(self) -> bool:
        return any(check in SHIFT_CHECKS for check, _ in self.failed)


def decide_d(tracks: list[Track], dl: DescList, *, tag_titles: list[str],
             canonical: ParsedSetlist, metadata_norms: set[str], aliases: dict[str, str],
             wholly_untagged: bool,
             donor: Callable[[], tuple[DonorTape, list[SiblingRow]] | None]
             ) -> DDecision | None:
    """The D rung's decision over a count-matched admissible list. None when the entry count
    differs from the track count or no track is `unresolved`. Every show-level check runs
    and is recorded in `failed`, in check order; any one declines every fill."""
    if len(dl.raws) != len(tracks) or len(dl.cleaned) != len(tracks):
        return None
    open_ = [i for i, t in enumerate(tracks) if t.title_source == "unresolved"]
    if not open_:
        return None

    failed: list[tuple[str, str]] = []
    track_declines: dict[int, str] = {}
    cands: dict[int, str] = {}
    # Check 1, over the candidates (the entries at unresolved positions).
    for i in open_:
        c = dl.cleaned[i]
        tag = tag_titles[i] if i < len(tag_titles) else ""
        h = judge(c, track_no=i + 1, first=i == 0, stem=_stem(tracks[i].filename),
                  own_core=tag_core(tag or ""), metadata_norms=metadata_norms)
        if h.scope == "track":
            track_declines[i] = h.check
            continue
        if h.scope == "show":
            failed.append((h.check, _detail(i, c.text)))
        cands[i] = c.text
    # Check 2.
    dup = adjacent_duplicate(cands, tracks)
    if dup is not None:
        failed.append(("adjacent duplicate", _detail(dup[0], dup[1])))
    # Check 3.
    dis = tape_disagreement(tracks, dl)
    if dis is not None:
        failed.append(("tape agreement", _detail(dis[0], dis[2])))
    # Written durations.
    wd = written_duration_mismatch(tracks, dl)
    if wd is not None:
        failed.append(("written durations", _detail(wd[0], dl.cleaned[wd[0]].text)))
    # The untagged checks.
    if wholly_untagged:
        bs = block_size_mismatch([t.filename for t in tracks], dl)
        if bs is not None:
            failed.append(("block size", bs))
        if cands:
            sib = sibling_disagreement(cands, donor())
            if sib is not None:
                failed.append(("sibling durations", _detail(sib[0], sib[1])))
    # The agreement check (the only place `aliases` reaches).
    ag = _agreement(dl, canonical, aliases)
    if ag is not None and ag[0] < AGREEMENT_FLOOR and ag[1] is not None:
        failed.append(("agreement", _detail(ag[1], dl.cleaned[ag[1]].text)))

    fills = {} if failed else dict(cands)
    return DDecision(fills, tuple(failed), track_declines)


def apply_d(tracks: list[Track], d: DDecision) -> list[Track]:
    """D's fills, stamped `desc-position`, on still-`unresolved` positions only."""
    out = list(tracks)
    for pos, text in d.fills.items():
        if 0 <= pos < len(out) and out[pos].title_source == "unresolved":
            out[pos] = out[pos].model_copy(update={"title": text,
                                                   "title_source": DESC_POSITION})
    return out


def d_notes(d: DDecision, dl: DescList) -> list[str]:
    """ONE note for a show-level decline, naming `failed[0]`; one per per-track decline."""
    notes: list[str] = []
    if d.failed:
        check, detail = d.failed[0]
        notes.append(f"positional fill declined: {DESC_POSITION} {check} ({detail})")
    for pos in sorted(d.track_declines):
        notes.append(f"positional fill declined: {DESC_POSITION} track {pos + 1} "
                     f"{d.track_declines[pos]} '{dl.cleaned[pos].text}'")
    return notes


def is_self_filled(tracks: list[Track], d: DDecision | None) -> bool:
    """Slice 2, "Self-filled tapes": D passed every check and every song-like track is
    `desc-position` (and there is at least one). Any `unresolved` track blocks it: its title
    is its filename, which `is_filler` may read as filler (`d1t01 Tuning.flac`)."""
    if d is None or d.failed:
        return False
    if any(t.title_source == "unresolved" for t in tracks):
        return False
    songs = [t for t in tracks if not is_filler(t.title)]
    return bool(songs) and all(t.title_source == DESC_POSITION for t in songs)


# ---- Slice 1: the S plan and the deferred S fill -----------------------------------------

SETLIST = "setlist"
_Q1_NOTE = "positional fill declined: setlist wholly untagged tape"
_Q1_CHOSEN_NOTE = ("positional fill declined: setlist wholly untagged tape "
                   "(chosen canonical, no admissible taper list)")


def _s_check(raw: dict[int, str], judge_at: list[int], neighbours: list[Track], *,
             tag_titles: list[str], metadata_norms: set[str]
             ) -> tuple[dict[int, str], list[tuple[str, str]], dict[int, tuple[str, str]]]:
    """Checks 1 and 2 over the S candidates at `judge_at` (0-based). `raw` holds EVERY S
    candidate (today's item text), in whose position order the cleaning's leader vote is
    taken; the checks run on the cleaned form, the fills ship the raw item text. Check 2
    compares against `neighbours` and the other candidates. Today's `is_placeholder_text`
    refusal stays, silent and per track, after check 1. Returns (fills, show-level failures
    in check order, per-track declines as pos -> (check, cleaned text))."""
    order = sorted(raw)
    cleaned = dict(zip(order, clean_entries([raw[p] for p in order])))
    failed: list[tuple[str, str]] = []
    track_declines: dict[int, tuple[str, str]] = {}
    cands: dict[int, str] = {}
    for p in sorted(judge_at):
        c = cleaned[p]
        h = judge(c, track_no=p + 1, first=p == 0,
                  stem=_stem(neighbours[p].filename) if p < len(neighbours) else "",
                  own_core=tag_core(tag_titles[p] if p < len(tag_titles) else ""),
                  metadata_norms=metadata_norms)
        if h.scope == "track":
            track_declines[p] = (h.check, c.text)
            continue
        if h.scope == "show":
            failed.append((h.check, _detail(p, c.text)))
        elif is_placeholder_text(raw[p]):
            continue  # today's refusal: unresolved, no note, not declined
        cands[p] = c.text
    dup = adjacent_duplicate(cands, neighbours)
    if dup is not None:
        failed.append(("adjacent duplicate", _detail(dup[0], dup[1])))
    fills = {} if failed else {p: raw[p] for p in cands}
    return fills, failed, track_declines


def _s_notes(failed: list[tuple[str, str]],
             track_declines: dict[int, tuple[str, str]]) -> list[str]:
    """ONE note for a show-level decline, naming the first failed check; then one per
    per-track decline."""
    notes: list[str] = []
    if failed:
        check, detail = failed[0]
        notes.append(f"positional fill declined: {SETLIST} {check} ({detail})")
    for p in sorted(track_declines):
        check, text = track_declines[p]
        notes.append(f"positional fill declined: {SETLIST} track {p + 1} {check} '{text}'")
    return notes


@dataclass(frozen=True)
class SetlistPlan:
    mode: str                     # "none" | "today" | "untagged" | "chosen" | "deferred" | "gated"
    fills: dict[int, str]         # made inside resolve_titles (today's item text)
    deferred: dict[int, str]      # held for after D ("deferred" mode)
    declined: frozenset[int]      # passed to adopt_gap_titles
    notes: tuple[str, ...]


def _plan(mode: str, fills: dict[int, str] | None = None, deferred: dict[int, str] | None = None,
          declined=frozenset(), notes=()) -> SetlistPlan:
    return SetlistPlan(mode, fills or {}, deferred or {}, frozenset(declined), tuple(notes))


def plan_setlist_rung(*, canonical: ParsedSetlist, canonical_source: str | None,
                      s_positions: list[int], tag_titles: list[str], tag_real: list[bool],
                      filenames: list[str], metadata_norms: set[str], desc_used: bool,
                      wholly_untagged: bool, slice1: bool, slice2: bool) -> SetlistPlan:
    """Where the S rung fires (slice 1, "The S rung splits by canonical source").

    `s_positions` (0-based) reach today's S branch (not 2b-demoted, tag fails
    `is_real_title`) and are not `overrides.titles` positions; `tag_real[i]` is True when
    position i resolves from its tag. Modes, first match wins:
    - `none`: no count-matched canonical with confidence not `low`;
    - `today`: slice 1 off, exactly today's rung (every S position whose item is not
      `is_placeholder_text`);
    - `chosen`: the canonical is the selected description and D (slice 2) has its
      count-matched list, so D makes these fills; S does nothing;
    - `untagged`: operator ruling Q1, no fills, every S position declined, one note (none
      when there is no S position);
    - `deferred`: a count-matched admissible list beside any other canonical; S holds its
      items for after D (`apply_deferred_setlist`) and declines them to setlist-gap;
    - `gated`: today's place, under checks 1 and 2 (check 2 against the real tags and the
      other candidates). A show-level failure fills nothing and declines every S position.
    """
    items = canonical.items
    if canonical.confidence == "low" or len(items) != len(filenames):
        return _plan("none")
    raw = {p: items[p].title for p in s_positions}
    if not slice1:
        return _plan("today", fills={p: t for p, t in raw.items()
                                     if not is_placeholder_text(t)})
    chosen = canonical_source == "chosen"
    if chosen and desc_used and slice2:
        return _plan("chosen")
    if wholly_untagged:
        note = _Q1_CHOSEN_NOTE if chosen else _Q1_NOTE
        return _plan("untagged", declined=s_positions, notes=(note,) if s_positions else ())
    if desc_used and slice2:
        return _plan("deferred", deferred=raw, declined=s_positions)
    neighbours = [
        Track(index=i + 1, set="1", filename=f,
              title=tag_titles[i] if tag_real[i] else "",
              title_source="tags" if tag_real[i] else "unresolved")
        for i, f in enumerate(filenames)
    ]
    fills, failed, track_declines = _s_check(raw, list(raw), neighbours,
                                             tag_titles=tag_titles,
                                             metadata_norms=metadata_norms)
    declined = s_positions if failed else track_declines
    return _plan("gated", fills=fills, declined=declined,
                 notes=_s_notes(failed, track_declines))


def apply_deferred_setlist(tracks: list[Track], plan: SetlistPlan, d: DDecision | None, *,
                           tag_titles: list[str], metadata_norms: set[str]
                           ) -> tuple[list[Track], list[str]]:
    """The deferred S fill, after D and before `align()`. Fills only still-`unresolved`
    positions, never one D declined as a `filler entry`, and nothing when D failed on a
    shift signature (S declines with D: one note naming D's first shift check). Checks 1
    and 2 re-run against the current tracks. Source `setlist`, today's item text."""
    if plan.mode != "deferred" or not plan.deferred:
        return tracks, []
    if d is not None and d.shift:
        check, detail = next((c, x) for c, x in d.failed if c in SHIFT_CHECKS)
        return tracks, [f"positional fill declined: {SETLIST} {check} ({detail})"]
    filler = {p for p, c in (d.track_declines.items() if d else ()) if c == "filler entry"}
    open_ = [p for p in plan.deferred
             if 0 <= p < len(tracks) and tracks[p].title_source == "unresolved"
             and p not in filler]
    if not open_:
        return tracks, []
    fills, failed, track_declines = _s_check(plan.deferred, open_, tracks,
                                             tag_titles=tag_titles,
                                             metadata_norms=metadata_norms)
    out = list(tracks)
    for p, text in fills.items():
        out[p] = out[p].model_copy(update={"title": text, "title_source": SETLIST})
    return out, _s_notes(failed, track_declines)


def confirm_short_tags(tracks: list[Track], tag_titles: list[str], tag_sources: list[str], *,
                       desc: DescList | None, demoted: frozenset[int], metadata_norms: set[str]
                       ) -> tuple[list[Track], list[str], list[int], dict[int, str]]:
    """Slice 4: a short real tag that fails `is_real_title` is accepted when the taper's own
    count-matched list confirms it at the same position. Returns (tracks, notes, accepted
    0-based positions, declined 0-based position -> first failed rule).

    A candidate is a still-`unresolved`, not-demoted position with a non-empty tag failing
    `is_real_title`. Rules, in order: `entry` (the tag's core equals the WHOLE cleaned entry
    by `fuzzy_norm_title`); `no neighbour` / `neighbour disagrees` (among independent
    titles within `SHORT_TAG_WINDOW`, at least one agrees with its entry and none
    disagrees, by `position_agreement`, no aliases); `stem` (the core, at least
    `STEM_SUBSTRING_MIN` characters, is a case-insensitive substring of the filename stem);
    `veto` (no alphanumeric core, `is_junk_tag`, or a `metadata_norms` hit, as 2a).
    Neighbours are judged on the tracks as passed in, so one slice-4 accept never
    confirms another. Ships `shipped_short_tag(tag)` with the per-track tag source."""
    out = list(tracks)
    notes: list[str] = []
    accepted: list[int] = []
    declined: dict[int, str] = {}
    if desc is None or len(desc.raws) != len(tracks) or len(tag_titles) != len(tracks):
        return out, notes, accepted, declined
    for i, t in enumerate(tracks):
        if t.title_source != "unresolved" or i in demoted:
            continue
        tag = tag_titles[i]
        if not tag.strip() or is_real_title(tag):
            continue
        core = tag_core(tag)
        title = shipped_short_tag(tag)
        entry = fuzzy_norm_title(desc.cleaned[i].text)
        if entry not in (fuzzy_norm_title(core), fuzzy_norm_title(title)):
            declined[i] = "entry"
            continue
        verdicts = [position_agreement(tracks[j], desc.cleaned[j])
                    for j in range(max(0, i - SHORT_TAG_WINDOW),
                                   min(len(tracks), i + SHORT_TAG_WINDOW + 1)) if j != i]
        if "disagree" in verdicts:
            declined[i] = "neighbour disagrees"
            continue
        if "agree" not in verdicts:
            declined[i] = "no neighbour"
            continue
        if len(core) >= STEM_SUBSTRING_MIN and core.lower() in _stem(t.filename).lower():
            declined[i] = "stem"
            continue
        if (not any(ch.isalnum() for ch in core) or is_junk_tag(core)
                or fuzzy_norm_title(core) in metadata_norms):
            declined[i] = "veto"
            continue
        out[i] = t.model_copy(update={"title": title, "title_source": tag_sources[i]})
        accepted.append(i)
        notes.append(f"short tag title confirmed by the taper's list: track {t.index} '{title}'")
    return out, notes, accepted, declined
