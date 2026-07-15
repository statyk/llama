"""Performance-level set structure: convert, rank, blend, align, guard.

Pure logic - no I/O. Set boundaries, song order, and segues are properties
of the performance, not of any one recording, so they are recovered from
the best source across all recordings (and setlist.fm) and aligned onto
the chosen recording's tracks.
"""
import re

from llama.models import AlignedStructure, AlignResult, ParsedSetlist, SetlistItem, SourcedParse, Track
from llama.songs import normalize_song

# "E: Baby Blue" / "Encore: Casey Jones" - structure markers embedded in a title.
_STRUCTURE_PREFIX = re.compile(r"^\s*(?:e|encore)\s*:\s*", re.I)

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def norm_title(title: str) -> str:
    return normalize_song(_STRUCTURE_PREFIX.sub("", title))


def from_setlistfm(raw: dict) -> ParsedSetlist | None:
    sets = (raw.get("sets") or {}).get("set") or []
    items: list[SetlistItem] = []
    set_no = 0
    for s in sets:
        if s.get("encore"):
            label = "encore"
        else:
            set_no += 1
            label = str(set_no)
        for song in s.get("song", []):
            name = (song.get("name") or "").strip()
            if not name or song.get("tape"):
                continue
            items.append(SetlistItem(title=name, normalized=normalize_song(name),
                                     set=label, segue=False))
    if len(items) < 5:
        return None  # a stub entry must not out-rank a rich LMA parse
    return ParsedSetlist(items=items, confidence="high")


def rank_parses(parses: list[SourcedParse], target_count: int) -> SourcedParse | None:
    candidates = [p for p in parses if p.parsed.items]
    if not candidates:
        return None

    def key(p: SourcedParse):
        multi_set = len({i.set for i in p.parsed.items}) > 1
        return (
            p.source == "setlist.fm",
            _CONF_RANK.get(p.parsed.confidence, 0),
            multi_set,
            -abs(len(p.parsed.items) - target_count),
        )

    # max() keeps the first maximal element, so callers list the chosen
    # recording first to win ties among copy-paste descriptions.
    return max(candidates, key=key)


def blend_segues(winner: ParsedSetlist, lma: ParsedSetlist | None) -> ParsedSetlist:
    """Overlay LMA segue notation onto the winning parse (taper descriptions
    carry segues; setlist.fm generally does not)."""
    if lma is None or lma is winner or not any(i.segue for i in lma.items):
        return winner
    pools: dict[str, list[SetlistItem]] = {}
    for it in lma.items:
        pools.setdefault(it.normalized, []).append(it)
    items = []
    for it in winner.items:
        pool = pools.get(it.normalized)
        src = pool.pop(0) if pool else None
        items.append(it.model_copy(update={"segue": src.segue}) if src else it)
    return ParsedSetlist(items=items, confidence=winner.confidence)


def align(tracks: list["Track"], canonical: ParsedSetlist, lookahead: int = 3) -> "AlignResult":
    """Map canonical set/segue structure onto tracks, in recording order.

    Two-pointer with lookahead: a track matches the next canonical item with
    the same normalized title within `lookahead` positions, so repeated songs
    pair with the right occurrence and merged/split tracks skip over the gap.
    """
    items = canonical.items
    sets: list[str] = []
    segues: list[bool] = []
    matched: list[bool] = []
    matched_idx: set[int] = set()
    j = 0
    for t in tracks:
        norm = norm_title(t.title)
        hit = next(
            (k for k in range(j, min(j + 1 + lookahead, len(items)))
             if items[k].normalized == norm),
            None,
        )
        if hit is None:
            sets.append(sets[-1] if sets else "1")
            segues.append(False)
            matched.append(False)
        else:
            sets.append(items[hit].set)
            segues.append(items[hit].segue)
            matched.append(True)
            matched_idx.add(hit)
            j = hit + 1
    coverage = (sum(matched) / len(tracks)) if tracks else 0.0
    conflicts = [it.title for k, it in enumerate(items) if k not in matched_idx]
    return AlignResult(sets=sets, segues=segues, matched=matched,
                       coverage=coverage, conflicts=conflicts)


def structure_guard(tracks: list[Track], set_breaks: list[int],
                    evidence_sets: set[str] | None = None,
                    min_minutes: int = 150) -> str | None:
    """Flag single-set structure only on real evidence of a problem: the
    setlist sources showed multiple sets that alignment lost, or the show
    runs implausibly long for one uninterrupted set (single sets past 2.5
    hours are rare; two-set shows usually exceed it). Track count alone is
    not a signal - plenty of artists play 20+ short songs in one set."""
    if set_breaks or not tracks:
        return None
    if evidence_sets and len(evidence_sets) > 1:
        return "setlist evidence shows multiple sets but alignment found none"
    total = sum(t.duration_sec for t in tracks if t.duration_sec)
    if total >= min_minutes * 60:
        return f"single-set structure for a long show ({total / 60:.0f} min)"
    return None


_VALID_SETS = {"1", "2", "3", "encore"}


def apply_llm_alignment(tracks: list[Track], resp: AlignedStructure) -> AlignResult | None:
    """Convert an align_structure LLM response to an AlignResult, or None if
    the response does not cover exactly the track indices with valid sets."""
    by_idx = {a.index: a for a in resp.tracks}
    if set(by_idx) != set(range(1, len(tracks) + 1)) or len(by_idx) != len(resp.tracks):
        return None
    ordered = [by_idx[i] for i in range(1, len(tracks) + 1)]
    if any(a.set not in _VALID_SETS for a in ordered):
        return None
    matched = [bool(a.matched_title) for a in ordered]
    coverage = (sum(matched) / len(tracks)) if tracks else 0.0
    return AlignResult(sets=[a.set for a in ordered], segues=[a.segue for a in ordered],
                       matched=matched, coverage=coverage)
