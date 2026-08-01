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

# Non-song tracks (tuning, repairs, announcements, crowd noise) that no
# canonical setlist contains; they must not count against alignment coverage.
_FILLER = re.compile(
    r"tun(?:ing|e\s*-?\s*up)|repairs?|announ?ce|applause|crowd|banter"
    r"|soundcheck|equipment",
    re.I,
)


def is_filler(title: str) -> bool:
    return bool(_FILLER.search(title))

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def norm_title(title: str) -> str:
    return normalize_song(_STRUCTURE_PREFIX.sub("", title))


# Interior segue separators. A merged track ("China Cat Sunflower > I Know You
# Rider") is several songs on one file; the song it *closes* on is the last
# component, which is what a jerrybase set closer has to be compared against.
_SEGUE_SEP = re.compile(r"\s*(?:->|>|→)\s*")


def fuzzy_norm_title(title: str) -> str:
    """`norm_title` with "&" folded to "and" first.

    `normalize_song`'s punctuation strip turns "&" into whitespace, so
    "Me & My Uncle" and "Me and My Uncle" normalize differently today. Folding
    beforehand collapses them. Deliberately kept out of `normalize_song`
    itself: folding there would shift `align()`'s coverage on every show at
    once, which is a later phase's decision, not this one's.
    """
    return norm_title(title.replace("&", " and "))


def title_components(title: str) -> list[str]:
    """Normalized components of a possibly-merged track title, in order.

    A trailing separator yields no empty component, so a dangling ">" stays a
    segue marker rather than becoming a phantom song.
    """
    parts = [p.strip() for p in _SEGUE_SEP.split(title) if p.strip()]
    return [fuzzy_norm_title(p) for p in parts] or [fuzzy_norm_title(title)]


def _is_subphrase(short: str, long: str) -> bool:
    ws, wl = short.split(), long.split()
    if len(ws) < 2 or len(ws) >= len(wl):
        return False
    return any(wl[i:i + len(ws)] == ws for i in range(len(wl) - len(ws) + 1))


def fuzzy_title_eq(a: str, b: str) -> bool:
    """Equality for already-normalized titles, tolerating the subtitles and
    parentheticals tapers drop ("Mississippi Half Step" vs the canonical
    "... Uptown Toodeloo").

    The two-word floor on the shorter side is deliberate: single-word shorthand
    ("Scarlet", "Help", "Estimated") is a hardcoded alias table's job, not a
    general rule's — a one-word floor would match "Dew" to "Morning Dew" and to
    everything else containing the word.
    """
    return a == b or _is_subphrase(a, b) or _is_subphrase(b, a)


# --- Venue equivalence (jerrybase venue-mismatch tripwire) -------------------
# Conservative, deterministic, offline. Only high-confidence equivalences
# auto-pass; when uncertain, callers still flag. No fuzzy scoring, no aliases.

# Connective/positional tokens dropped before comparison.
_PLACE_STOPWORDS = {"the", "at", "of", "and"}

# Token-wise abbreviation expansions applied before matching. Each token maps to
# the set of full forms it may stand for; two tokens are equal when their
# expansion sets intersect ("st" is ambiguous, so any matching expansion counts).
_PLACE_ABBREV = {
    "aud": {"auditorium"},
    "theatre": {"theater"},
    "theater": {"theater"},
    "univ": {"university"},
    "coll": {"college"},
    "mem": {"memorial"},
    "ctr": {"center"},
    "cntr": {"center"},
    "gym": {"gymnasium"},
    "st": {"street", "state"},
}


def _place_tokens(s: str) -> list[str]:
    """Shared venue tokenizer: lowercase, alphanumerics only, stopwords dropped.
    (Replaces gather's old _norm_place; that folded to a joined string, this
    keeps tokens for subset/initialism comparison.)"""
    norm = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return [t for t in norm.split() if t not in _PLACE_STOPWORDS]


def _tokens_equal(a: str, b: str) -> bool:
    return a == b or bool(_PLACE_ABBREV.get(a, {a}) & _PLACE_ABBREV.get(b, {b}))


def _token_subset(sub: list[str], sup: list[str]) -> bool:
    return bool(sub) and all(any(_tokens_equal(x, y) for y in sup) for x in sub)


def _acronym_match(short: list[str], long: list[str]) -> bool:
    """True if `short`'s tokens match `long`'s in order, where a short token may
    be an initialism (>=2 letters) spelling a contiguous run of long tokens:
    [rfk, stadium] matches [robert, f, kennedy, stadium]."""
    i = j = 0
    while i < len(short) and j < len(long):
        s = short[i]
        if _tokens_equal(s, long[j]):
            i += 1
            j += 1
            continue
        if len(s) >= 2 and s.isalpha():
            run = 0
            k = j
            while k < len(long) and run < len(s) and long[k][0] == s[run]:
                run += 1
                k += 1
            if run == len(s):
                i += 1
                j = k
                continue
        return False
    return i == len(short) and j == len(long)


def venues_equivalent(a: str, b: str) -> bool:
    """Conservative venue-name equivalence for the jerrybase tripwire. Equivalent
    iff (after tokenizing and dropping stopwords) one token set is a subset of
    the other, or one side's initialism spells the other (RFK <-> Robert F.
    Kennedy). Abbreviations (aud/auditorium, theatre/theater, ...) are folded in
    token-wise. Anything less certain returns False so the caller still flags."""
    ta, tb = _place_tokens(a), _place_tokens(b)
    if not ta and not tb:
        return True
    if not ta or not tb:
        return False
    if _token_subset(ta, tb) or _token_subset(tb, ta):
        return True
    return _acronym_match(ta, tb) or _acronym_match(tb, ta)


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
    coverage = _songish_coverage(tracks, matched)
    conflicts = [it.title for k, it in enumerate(items) if k not in matched_idx]
    return AlignResult(sets=sets, segues=segues, matched=matched,
                       coverage=coverage, conflicts=conflicts)


def _songish_coverage(tracks: list["Track"], matched: list[bool]) -> float:
    """Matched fraction over song-like tracks only: filler (tuning, repairs,
    crowd) can never match a canonical setlist and must not drag coverage."""
    songish = [m for t, m in zip(tracks, matched) if not is_filler(t.title)]
    return (sum(songish) / len(songish)) if songish else 0.0


def structure_guard(tracks: list[Track], set_breaks: list[int],
                    evidence_sets: set[str] | None = None,
                    min_minutes: int = 150,
                    expected_set_count: int | None = None) -> str | None:
    """Flag suspicious structure. When expected_set_count is given (jerrybase
    evidence), the aligned distinct-set count — counting numbered sets only, an
    "encore" is a coda not a set — that differs is flagged even when breaks
    exist (the caller's expected_set_count likewise excludes any encore).
    Otherwise: flag single-set
    structure only on real evidence of a problem - the setlist sources showed
    multiple sets that alignment lost, or the show runs implausibly long for one
    uninterrupted set (single sets past 2.5 hours are rare; two-set shows
    usually exceed it). Track count alone is not a signal - plenty of artists
    play 20+ short songs in one set."""
    if not tracks:
        return None
    if expected_set_count is not None:
        actual = len({t.set for t in tracks if t.set != "encore"})
        if actual != expected_set_count:
            return f"structure has {actual} sets but jerrybase shows {expected_set_count}"
    if set_breaks:
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
    coverage = _songish_coverage(tracks, matched)
    return AlignResult(sets=[a.set for a in ordered], segues=[a.segue for a in ordered],
                       matched=matched, coverage=coverage)
