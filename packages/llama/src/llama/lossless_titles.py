"""Per-track lossless titles (title hygiene, piece 3, slice 3: C).

Spec `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`, "Slice 3". Sits BESIDE
`gather._recover_format_titles` (wholesale, gated at 0.5/0.9; both constants untouched):
C runs only where recovery's first gate excluded the item (`in_scope`, computed by the
caller: `format_titles is None` and the delivered layer's `title_fraction >=
_RECOVER_BELOW`), on the same `recovery_basis` and the same filename-stem bijection
(`titles.sibling_format_titles`) with a lossless format of the SAME item.

This is the one rung that REPLACES a tag (C2), so it is strict:
- **C1, fill.** The delivered tag is blank, a placeholder, or fails `is_real_title`, and is
  not the 2a shape; the lossless tag is a real tag, hygienic, and not vetoed. Adoption is
  the plan's reading: a target agreeing with (a) the count-matched list's entry at its
  position or (b) the count-matched canonical's item there is adopted; one agreeing with
  neither is adopted only when (c) holds for the show (at least `siblings.MIN_ANCHORS`
  comparison stems agree and none disagrees); if ANY target fails all three, C1 fills
  nothing on the show.
- **C2, replace.** Both tags real (or the delivered one in 2a shape), `fuzzy_norm_title`
  differs, the lossless tag agrees with the ONE reference ((a) when there is a list, else
  (b)) and the delivered one does not. No reference, no C2.
- **Vetoes** on the lossless tag: wholly `[...]`; ending `:`; the delivered title plus
  only trailing `@ ^ * #`.
- **Show-level skip:** two or more lossless tags each agreeing with the reference at
  position +/-1 but not at their own (builttospill-1997-10-13).

"Agree" is `title_hygiene.agrees` with no aliases: cleaned copies, `loosely_same_title`
unmodified, short cores by `fuzzy_norm_title` equality.

Pure: no IO. A re-admitted file (in `kept`, not in `recovery_basis`) has no lossless
title: it is never changed and never votes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from llama.desc_list import _TRAIL_MARKERS, DescList
from llama.junk import LOSSLESS_TITLE_FORMATS, filter_files
from llama.models import ParsedSetlist
from llama.placeholders import is_junk_tag
from llama.siblings import MIN_ANCHORS
from llama.structure import fuzzy_norm_title, hygienic_title
from llama.title_hygiene import agrees
from llama.titles import (
    is_placeholder_text,
    is_real_title,
    sibling_format_titles,
    tag_core,
    title_fraction,
)

SIBLING_FORMAT = "sibling-format"
OUT_OF_SCOPE = "out of scope"
NO_LOSSLESS = "no lossless format"
OFF_BY_ONE = "off by one"
C1_UNCONFIRMED = "C1 unconfirmed"

_BRACKETED = re.compile(r"\s*\[.*\]\s*")
_SYMBOL_TAIL = re.compile(r"(?:\s*[@^*#])+\s*$")


@dataclass(frozen=True)
class LosslessResult:
    titles: list[str]               # tag layer after C, parallel to kept
    sources: list[str]              # per track: the incoming source, or "sibling-format" where C acted
    changed: dict[int, str]         # 0-based -> "C1" | "C2"
    declined: str | None            # show-level reason, or None
    notes: tuple[str, ...]
    c1_verdicts: dict[int, tuple[bool | None, bool | None]]
    # per C1 target (0-based): agrees with (a), with (b); None when that reference is absent
    c_holds: bool | None            # (c) for the show; None when no target needed it


def _real(tag: str) -> bool:
    """Spec Definitions, "Real tag"."""
    return is_real_title(tag) and not is_placeholder_text(tag)


def _shape_2a(tag: str) -> bool:
    """Spec Definitions, "2a shape" (`J`, `42`, `M80`): the core has an alphanumeric
    character (as `accept_short_tags` tests it), passes 2a's junk veto, and the tag is
    not a placeholder."""
    core = tag_core(tag)
    return (any(ch.isalnum() for ch in core) and not is_junk_tag(core)
            and not is_placeholder_text(tag))


def _vetoed(lossless: str, delivered: str) -> bool:
    """Never take a lossless tag that is wholly bracketed, ends in `:` (`(m:ss):`
    included), or is the delivered title plus only trailing `@ ^ * #`."""
    t = lossless.strip()
    if _BRACKETED.fullmatch(t) or t.endswith(":"):
        return True
    d = delivered.strip()
    bare = _SYMBOL_TAIL.sub("", t)
    return bool(d) and bare != t and bare == d


def _lossless_map(files: list[dict], ordering: dict,
                  recovery_basis: list[dict]) -> dict[str, str] | None:
    """The first format in `LOSSLESS_TITLE_FORMATS` order, skipping the delivered one, whose
    bijection with `recovery_basis` exists and carries any real title."""
    for fmt in LOSSLESS_TITLE_FORMATS:
        if fmt == ordering.get("format"):
            continue
        other, _, _ = filter_files(files, want_format=fmt)
        mapped = sibling_format_titles(recovery_basis, other)
        if mapped and title_fraction(list(mapped.values())) > 0:
            return mapped
    return None


def apply_lossless(kept: list[dict], tag_titles: list[str], tag_source: str, *, in_scope: bool,
                   files: list[dict], ordering: dict, recovery_basis: list[dict],
                   desc: DescList | None, canonical: ParsedSetlist,
                   metadata_norms: set[str]) -> LosslessResult:
    n = len(kept)
    titles = list(tag_titles)
    sources = [tag_source] * n

    def result(changed=None, declined=None, notes=(), verdicts=None, c_holds=None):
        return LosslessResult(titles, sources, changed or {}, declined, tuple(notes),
                              verdicts or {}, c_holds)

    if not in_scope:
        return result(declined=OUT_OF_SCOPE)
    mapped = _lossless_map(files, ordering, recovery_basis)
    if mapped is None:
        return result(declined=NO_LOSSLESS)
    lossless: list[str | None] = [mapped.get(f["name"]) for f in kept]

    # References: (a) the count-matched list's cleaned entry, (b) the count-matched
    # canonical item. C2 and the show-level skip use ONE: (a) when there is a list.
    ref_a = ([c.text for c in desc.cleaned]
             if desc is not None and len(desc.cleaned) == n else None)
    ref_b = ([it.title for it in canonical.items]
             if len(canonical.items) == n else None)
    ref, ref_name = (ref_a, "the taper's list") if ref_a is not None else (ref_b, "the canonical")

    # Show-level skip: 2+ lossless tags agreeing with the reference at +/-1, not at their own.
    if ref is not None:
        shifted = [i for i, lt in enumerate(lossless)
                   if lt and lt.strip() and not agrees(lt, ref[i])
                   and any(0 <= j < n and agrees(lt, ref[j]) for j in (i - 1, i + 1))]
        if len(shifted) >= 2:
            tracks = ", ".join(str(i + 1) for i in shifted)
            return result(declined=OFF_BY_ONE, notes=(
                f"lossless titles declined: {OFF_BY_ONE} against {ref_name} (tracks {tracks})",))

    def eligible(i: int) -> bool:
        lt = lossless[i]
        return (lt is not None and _real(lt) and hygienic_title(lt, metadata_norms)
                and not _vetoed(lt, tag_titles[i]))

    targets: list[int] = []
    c2_cands: list[int] = []
    agree_stems = disagree_stems = 0
    for i in range(n):
        lt, dt = lossless[i], tag_titles[i]
        if lt is None:
            continue  # re-admitted: no lossless title, no vote
        if _real(dt) and _real(lt):
            if agrees(dt, lt):
                agree_stems += 1
            else:
                disagree_stems += 1
        if not eligible(i):
            continue
        if _real(dt) or (dt.strip() and not is_real_title(dt) and _shape_2a(dt)):
            c2_cands.append(i)
        else:
            targets.append(i)

    # C1: per target (a)/(b); (c) for the show only when some target needs it.
    verdicts: dict[int, tuple[bool | None, bool | None]] = {}
    unconfirmed: list[int] = []
    for i in targets:
        va = agrees(lossless[i], ref_a[i]) if ref_a is not None else None
        vb = agrees(lossless[i], ref_b[i]) if ref_b is not None else None
        verdicts[i] = (va, vb)
        if not (va or vb):
            unconfirmed.append(i)
    c_holds = (agree_stems >= MIN_ANCHORS and disagree_stems == 0) if unconfirmed else None

    changed: dict[int, str] = {}
    notes: list[str] = []
    declined = None
    if unconfirmed and not c_holds:
        first = unconfirmed[0]
        declined = C1_UNCONFIRMED
        c1_notes = [f"lossless titles declined: {C1_UNCONFIRMED} "
                    f"(track {first + 1} '{lossless[first]}')"]
    else:
        c1_notes = []
        for i in targets:
            changed[i] = "C1"

    # C2: one reference; the lossless tag agrees with it and the delivered one does not.
    if ref is not None:
        for i in c2_cands:
            lt, dt = lossless[i], tag_titles[i]
            if (fuzzy_norm_title(lt) != fuzzy_norm_title(dt)
                    and agrees(lt, ref[i]) and not agrees(dt, ref[i])):
                changed[i] = "C2"

    for i in sorted(changed):
        # Checkpoint A ruling (h): ship the title without its taper segue/footnote marker,
        # after the adoption decision; an all-marker title ships as it is.
        new = _TRAIL_MARKERS.sub("", lossless[i]).strip() or lossless[i]
        notes.append(f"lossless title: track {i + 1} '{tag_titles[i]}' -> "
                     f"'{new}' ({changed[i]})")
        titles[i] = new
        sources[i] = SIBLING_FORMAT
    return result(changed, declined, c1_notes + notes, verdicts, c_holds)
