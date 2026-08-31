"""Blind-the-tags measurement of `structure.adopt_gap_titles` (evidence M1).

Manual, read-only diagnostic (never run by the pipeline). It hides the
embedded tag titles of short runs of tracks -- one run at a time -- re-runs
the REAL `structure.adopt_gap_titles` over the resulting gap, and scores each
adopted title against the tag it could not see. The hidden tag is the ground
truth; the adoption is the guess.

What this harness does NOT do, deliberately: it never reimplements the thing
it measures. `adopt_gap_titles`, `resolve_titles`, `filter_files`,
`parse_setlist`, `rank_parses`, `blend_segues`, `_strip_head_banner`,
`_drop_artist_items`, `_show_metadata_norms`, `_collect_parses`,
`_sibling_titles` and `_recover_format_titles` are all imported and called.
The only logic written here is the driver (which is `run_gather`'s prefix
minus the workspace I/O, since `run_gather` writes to the library) and the
scorer.

Anchor kinds are recorded by SPYING on the real `structure._merge_run`: the
harness wraps it for the duration of one `adopt_gap_titles` call and records
which calls returned a hit. A track that carries more than one title
component and whose `_merge_run` call succeeded was bound as a MERGED anchor
(component-fuzzy, `_is_subphrase` fallback -- the documented weak point);
every other anchor was bound by exact normalized equality. This is exact, not
inferred: the calls come from the function under test.

Usage:
  ./.venv/bin/python scripts/blind_tag_gapfill.py > gapfill.tsv
  ./.venv/bin/python scripts/blind_tag_gapfill.py --selftest

  --cache DIR      archive.org metadata cache (default ~/.llama/cache).
                   READ-ONLY: only ever opened for reading.
  --format mp3|flac  delivery format to measure (default mp3, production's).
  --limit N        stop after N cached items (smoke runs).
  --progress N     emit a progress line to stderr every N items.
  --selftest       run the can-this-return-non-empty demonstration instead:
                   three hand-built cases through the real
                   `adopt_gap_titles`, one of which MUST score WRONG.

TSV columns are printed as a `#`-comment header. The summary block is printed
both to stderr and as trailing `#` lines on stdout, unconditionally and
whether or not anything went wrong -- a harness that silently adopts nothing
and a harness that correctly finds no errors otherwise look identical.

Offline standing caveat: this runs with `setlistfm=None`, so every canonical
setlist here is LMA-only. Real canonicals for some of these shows are
setlist.fm-won. The numbers are therefore BOUNDS, not truths.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections import Counter
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from llama import jerrybase, structure
from llama.grouping import group_candidates
from llama.ia_client import IAError
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Candidate, ParsedSetlist, SetlistItem, Track
from llama.songs import GD_SHORTHAND
from llama.stages.gather import (_collect_parses, _description, _creator,
                                 _drop_artist_items, _recover_format_titles,
                                 _show_metadata_norms, _sibling_titles,
                                 _strip_head_banner)
from llama.structure import (adopt_gap_titles, blend_segues, fuzzy_norm_title,
                             rank_parses, title_components)
from llama.titles import resolve_titles

DEFAULT_CACHE = Path.home() / ".llama" / "cache"

# The rungs whose titles came off the tape's own tags -- the only ones that
# can serve as hidden ground truth. `setlist`/`setlist-gap` are the canonical
# setlist's own text (circular), `sibling` is another tape's tags (a different
# claim), `override` is an operator's hand.
TAG_SOURCES = ("tags", "sibling-format")

# Longest run of tags blinded in one trial. The spec's mechanism fills short
# gaps between anchors; blinding more than three at once measures a shape
# production does not produce from a well-tagged tape.
MAX_RUN = 3

# Collections that identify an archive.org section rather than an artist.
_GENERIC_COLLECTIONS = {
    "etree", "stream_only", "audio", "audio_music", "opensource_audio",
    "community", "additional_collections",
}


# --- cache-backed stand-in for llama.ia_client.IAClient ---------------------

class CacheIA:
    """`.metadata(identifier)` served from the on-disk archive.org cache.

    Read-only by construction: it opens files and never writes. An identifier
    with no cached metadata raises `IAError`, which is exactly what
    `_collect_parses` already handles (it records a note and skips the
    sibling), so an incompletely cached performance degrades the same way a
    network failure would rather than crashing the sweep.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self._by_identifier: dict[str, Path] = {}
        self._memo: dict[str, dict] = {}
        for path in sorted(cache_dir.glob("md_*.json")):
            self._by_identifier[path.name[len("md_"):-len(".json")]] = path

    def identifiers(self) -> list[str]:
        return sorted(self._by_identifier)

    def metadata(self, identifier: str) -> dict:
        if identifier in self._memo:
            return self._memo[identifier]
        path = self._by_identifier.get(identifier)
        if path is None:
            raise IAError(f"not cached: {identifier}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            raise IAError(f"unreadable cache entry {identifier}: {err}") from err
        if not isinstance(data, dict):
            raise IAError(f"malformed cache entry {identifier}")
        self._memo[identifier] = data
        return data


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _collection_of(meta: dict) -> str:
    """The artist-ish collection an item belongs to, mirroring what a search
    would have been run under. Generic archive.org sections are skipped so
    `jerrybase.lookup` gets something it can key on."""
    colls = meta.get("collection")
    colls = colls if isinstance(colls, list) else [colls] if colls else []
    for c in colls:
        if isinstance(c, str) and c.lower() not in _GENERIC_COLLECTIONS:
            return c
    creator = _creator(meta)
    return str(creator or (colls[0] if colls else "") or "unknown")


def _doc_of(meta: dict) -> dict:
    """The archive.org search-result shape `grouping._summary` consumes,
    reconstructed from cached item metadata."""
    return {
        "identifier": meta.get("identifier", ""),
        "title": meta.get("title", ""),
        "date": str(_first(meta.get("date")) or "")[:10],
        "venue": meta.get("venue"),
        "coverage": meta.get("coverage"),
        "description": _description(meta),
    }


def build_candidates(ia: CacheIA) -> list[tuple[Candidate, str]]:
    """Every (candidate, chosen identifier) pair the cache can support.

    Grouping is the real `grouping.group_candidates`, so early/late splits,
    `/spans` and `/unassigned` come out exactly as production would produce
    them. Every recording of a performance is measured in turn as the CHOSEN
    one, because the chosen recording is the one whose tags are on trial.
    """
    by_collection: dict[str, list[dict]] = {}
    for identifier in ia.identifiers():
        try:
            meta = ia.metadata(identifier).get("metadata", {})
        except IAError:
            continue
        if not meta.get("identifier") or not _first(meta.get("date")):
            continue
        by_collection.setdefault(_collection_of(meta), []).append(_doc_of(meta))

    out: list[tuple[Candidate, str]] = []
    for collection, docs in sorted(by_collection.items()):
        for cand in group_candidates(collection, docs, jerrybase_enabled=True):
            for rec in cand.recordings:
                out.append((cand, rec.identifier))
    return out


# --- gather's prefix, without the workspace --------------------------------

@dataclass
class Prepared:
    """Everything `adopt_gap_titles` is called with in production, for one
    chosen recording -- built by the real functions, in `run_gather`'s order."""
    identifier: str
    artist: str
    kept: list[dict]
    canonical: ParsedSetlist
    metadata_norms: set
    aliases: dict
    sibling_titles: list[str] | None
    tracks: list[Track]


def prepare(ia: CacheIA, candidate: Candidate, identifier: str,
            audio_format: str = "mp3") -> Prepared | None:
    """Reproduce `stages/gather.run_gather` up to the `adopt_gap_titles` call.

    Line-for-line the same call sequence (gather.py:508-635) minus the
    workspace read/write, the `overrides` layer (there are none for a cached
    item that was never gathered) and the setlist.fm lookup (offline: see the
    module docstring's standing caveat). Returns None when the item has no
    usable audio at all.
    """
    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    artist = str(_creator(meta) or candidate.collection)
    want = FORMAT_BY_AUDIO[audio_format]
    kept, _excluded, ordering = filter_files(md.get("files", []), want_format=want)
    if not kept:
        return None
    format_titles = _recover_format_titles(md.get("files", []), kept, ordering)

    parses, _notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    best = rank_parses(parses, target_count=len(kept))
    canonical = best.parsed if best else ParsedSetlist()
    # The `best.source == "setlist.fm"` branch of gather cannot fire offline;
    # `blend_segues` is called anyway, with the same LMA winner on both sides,
    # so the call sequence stays the production one and stays a no-op.
    if best is not None:
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)

    events = jerrybase.lookup(artist, candidate.date)
    metadata_norms = _show_metadata_norms(artist, candidate, meta, events)
    canonical = _strip_head_banner(canonical, metadata_norms)
    canonical = _drop_artist_items(canonical, artist)

    siblings = None
    from llama.titles import clean_tag_titles, title_fraction
    if kept and title_fraction(clean_tag_titles(kept)) < 1.0 and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
        siblings = _sibling_titles(ia, candidate, identifier, want, len(kept))
    tracks = resolve_titles(kept, canonical, sibling_titles=siblings,
                            format_titles=format_titles)
    aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}
    return Prepared(identifier=identifier, artist=artist, kept=kept,
                    canonical=canonical, metadata_norms=metadata_norms,
                    aliases=aliases, sibling_titles=siblings, tracks=tracks)


# --- blinding --------------------------------------------------------------

def blindable_runs(tracks: list[Track]) -> list[tuple[int, int]]:
    """Inclusive [lo, hi] windows of 1..MAX_RUN tag-titled tracks whose
    flanking tracks are themselves titled (or which touch a tape edge).

    A window whose neighbour is ALREADY unresolved is skipped: blinding it
    would merge with a pre-existing run, and only part of the resulting gap
    would have ground truth behind it.
    """
    n = len(tracks)
    out = []
    for lo in range(n):
        for hi in range(lo, min(lo + MAX_RUN, n)):
            if any(tracks[k].title_source not in TAG_SOURCES for k in range(lo, hi + 1)):
                continue
            if lo > 0 and tracks[lo - 1].title_source == "unresolved":
                continue
            if hi + 1 < n and tracks[hi + 1].title_source == "unresolved":
                continue
            out.append((lo, hi))
    return out


def blind(prep: Prepared, lo: int, hi: int) -> list[Track]:
    """`prep.tracks` with [lo, hi]'s tag titles hidden.

    The replacement rung is `titles.resolve_titles`' own fallback ladder
    (titles.py:150-160) for a track whose tag is unusable: the whole-tape
    setlist rung if it is live for this recording, else the sibling rung, else
    unresolved. Blanking the file dicts and re-running `resolve_titles`
    outright would have been circular in the other direction -- removing three
    titles perturbs `clean_tag_titles`' enumerated-tape gate and can change
    the OTHER tracks' titles, i.e. the anchors -- so the ladder is applied
    here, to the three tracks under test only, and nothing else moves.
    """
    n = len(prep.tracks)
    items = prep.canonical.items
    aligned = items if (prep.canonical.confidence != "low" and len(items) == n) else None
    sibs = prep.sibling_titles if (prep.sibling_titles
                                   and len(prep.sibling_titles) == n) else None
    out = list(prep.tracks)
    for pos in range(lo, hi + 1):
        if aligned:
            title, source = aligned[pos].title, "setlist"
        elif sibs:
            title, source = sibs[pos], "sibling"
        else:
            title, source = prep.kept[pos]["name"], "unresolved"
        out[pos] = out[pos].model_copy(update={"title": title, "title_source": source})
    return out


@contextlib.contextmanager
def merge_run_spy():
    """Record every `structure._merge_run` call the code under test makes.

    Yields a list that receives one bool per call, in call order: True when
    the call bound a merged run. `adopt_gap_titles` calls `_merge_run` exactly
    once per titled multi-component track, walking tracks in order, so the
    Nth recorded call belongs to the Nth such track.
    """
    calls: list[bool] = []
    real = structure._merge_run

    def spy(norms, lo, hi, comps):
        got = real(norms, lo, hi, comps)
        calls.append(got is not None)
        return got

    structure._merge_run = spy
    try:
        yield calls
    finally:
        structure._merge_run = real


def anchor_kinds(tracks: list[Track], calls: list[bool],
                 aliases: dict) -> dict[int, str]:
    """Track position -> "merged" for every position `_merge_run` bound.

    Replays the spy's call log against the same walk order
    `adopt_gap_titles` used. Positions absent from the map were either not
    anchors at all or were bound by exact normalized equality.
    """
    out: dict[int, str] = {}
    i = 0
    for pos, t in enumerate(tracks):
        if t.title_source == "unresolved":
            continue
        if len(title_components(t.title, aliases)) > 1:
            if i < len(calls) and calls[i]:
                out[pos] = "merged"
            i += 1
    return out


def merged_attribution(kinds: dict[int, str], lo: int, hi: int, n: int) -> str:
    """How a merged anchor could have reached this gap: "adjacent", "upstream"
    or "none".

    The distinction is the whole point, and getting it wrong was the Critical
    finding of this task's review. A merged anchor can corrupt a gap two ways:
    by binding its OWN flank wrongly (adjacent), or by mis-advancing `j` so
    that every gap AFTER it is shifted (upstream). `adopt_gap_titles`'
    docstring states the risk in the second form; labelling gaps only by their
    adjacent anchor answers the first question and is blind to the second.

    "upstream" means: no flanking anchor was merged, but some merged anchor was
    bound at a track position before this run -- so the pointer this gap's span
    was computed from passed through a merged bind.
    """
    if kinds.get(lo - 1) == "merged" or kinds.get(hi + 1) == "merged":
        return "adjacent"
    return "upstream" if any(pos < lo for pos in kinds) else "none"


# --- scoring ---------------------------------------------------------------

COLUMNS = ("identifier", "artist", "n_tracks", "n_items", "run_lo", "run_hi",
           "track", "edge", "anchor_kind", "merged_attr", "verdict",
           "adopted", "hidden")


@dataclass
class Totals:
    items_seen: int = 0
    items_prepared: int = 0
    items_with_runs: int = 0
    trials: int = 0
    trials_preempted: Counter = field(default_factory=Counter)
    firings: int = 0            # trials in which >= 1 track was adopted
    adoptions: int = 0          # scored adoptions (inside the blinded run)
    unverifiable: int = 0       # adoptions outside the blinded run
    ok: Counter = field(default_factory=Counter)
    wrong: Counter = field(default_factory=Counter)


def _clean(s: str) -> str:
    return " ".join(str(s).split()).replace("\t", " ")


def measure_item(prep: Prepared, totals: Totals, rows: list[str]) -> None:
    runs = blindable_runs(prep.tracks)
    if runs:
        totals.items_with_runs += 1
    n = len(prep.tracks)
    for lo, hi in runs:
        totals.trials += 1
        blinded = blind(prep, lo, hi)
        totals.trials_preempted[blinded[lo].title_source] += 1
        if blinded[lo].title_source != "unresolved":
            continue          # a higher rung answered first; the gap never forms
        with merge_run_spy() as calls:
            out = adopt_gap_titles(blinded, prep.canonical,
                                   metadata_norms=prep.metadata_norms,
                                   aliases=prep.aliases)
        kinds = anchor_kinds(blinded, calls, prep.aliases)
        fired = False
        for pos in range(n):
            if out[pos].title_source != "setlist-gap":
                continue
            if not (lo <= pos <= hi):
                totals.unverifiable += 1
                continue
            fired = True
            adopted = out[pos].title
            hidden = prep.tracks[pos].title
            verdict = ("ok" if fuzzy_norm_title(adopted) == fuzzy_norm_title(hidden)
                       else "wrong")
            edge = int(lo == 0 or hi == n - 1)
            attr = merged_attribution(kinds, lo, hi, n)
            kind = "merged" if attr == "adjacent" else "single"
            totals.adoptions += 1
            (totals.ok if verdict == "ok" else totals.wrong)[kind] += 1
            rows.append("\t".join(str(v) for v in (
                prep.identifier, _clean(prep.artist), n, len(prep.canonical.items),
                lo + 1, hi + 1, pos + 1, edge, kind, attr, verdict,
                _clean(adopted), _clean(hidden))))
        if fired:
            totals.firings += 1


def _rate(bad: int, all_: int) -> str:
    return f"{100.0 * bad / all_:.2f}%" if all_ else "n/a"


def distinct_lines(rows: list[str]) -> list[str]:
    """De-duplicated view of the same adoptions.

    Trials overlap by construction -- blinding [3,3], [3,4] and [3,5] all put
    track 3 in a gap -- so the per-trial counts above weight a track by how
    many windows contain it. This view collapses every row that makes the
    same claim about the same track (same identifier, track, adopted title,
    hidden tag, anchor kind), which is the population the hand triage works
    over.
    """
    seen: set[tuple] = set()
    ok: Counter = Counter()
    wrong: Counter = Counter()
    attr_ok: Counter = Counter()
    attr_wrong: Counter = Counter()
    edges: dict[tuple, set[str]] = {}
    for row in rows:
        f = row.split("\t")
        key = (f[0], f[6], f[8], f[9], f[10], f[11], f[12])
        edges.setdefault(key, set()).add(f[7])
        if key in seen:
            continue
        seen.add(key)
        (ok if f[10] == "ok" else wrong)[f[8]] += 1
        (attr_ok if f[10] == "ok" else attr_wrong)[f[9]] += 1
    ok_s, wr_s, ok_m, wr_m = ok["single"], wrong["single"], ok["merged"], wrong["merged"]
    out = [
        f"distinct adoptions            : {len(seen)}",
        f"  pooled  ok={ok_s + ok_m} wrong={wr_s + wr_m} "
        f"rate={_rate(wr_s + wr_m, ok_s + ok_m + wr_s + wr_m)}",
        f"  [adjacency view, NARROWER THAN THE MECHANISM -- see merged_attr]",
        f"  single  ok={ok_s} wrong={wr_s} rate={_rate(wr_s, ok_s + wr_s)}",
        f"  merged  ok={ok_m} wrong={wr_m} rate={_rate(wr_m, ok_m + wr_m)}",
        f"  [merged attribution: adjacent | upstream-only | none]",
    ]
    for a in ("adjacent", "upstream", "none"):
        o, w = attr_ok[a], attr_wrong[a]
        out.append(f"  {a:<9} ok={o} wrong={w} rate={_rate(w, o + w)}")
    # `edge` is a property of the TRIAL (did the blinded window touch a tape
    # end), not of the adoption: the same adoption is reached by several
    # windows and can carry both values. Collapsing it therefore needs a
    # stated rule, and the answer moves with the rule -- so all three are
    # printed rather than one being passed off as the number.
    both = sum(1 for v in edges.values() if len(v) > 1)
    firstwins: dict[tuple, str] = {}
    for row in rows:
        f = row.split("\t")
        key = (f[0], f[6], f[8], f[9], f[10], f[11], f[12])
        firstwins.setdefault(key, f[7])
    out += [
        f"edge is a TRIAL property; {both} of {len(seen)} distinct adoptions "
        f"carry both values",
        f"  edge population, first-window-wins : "
        f"{sum(1 for v in firstwins.values() if v == '1')}",
        f"  edge population, any-edge-wins     : "
        f"{sum(1 for v in edges.values() if '1' in v)}",
        f"  edge population, any-interior-wins : "
        f"{sum(1 for v in edges.values() if v == {'1'})}",
    ]
    return out


def summary_lines(totals: Totals, audio_format: str) -> list[str]:
    rate = _rate
    ok_s, wr_s = totals.ok["single"], totals.wrong["single"]
    ok_m, wr_m = totals.ok["merged"], totals.wrong["merged"]
    lines = [
        f"format={audio_format}",
        f"cached items scanned          : {totals.items_seen}",
        f"items with usable audio       : {totals.items_prepared}",
        f"items offering >=1 blind run  : {totals.items_with_runs}",
        f"blinding trials run           : {totals.trials}",
        f"  trials pre-empted by a higher rung: "
        + ", ".join(f"{k}={v}" for k, v in sorted(totals.trials_preempted.items())
                    if k != "unresolved"),
        f"trials in which gap-fill FIRED: {totals.firings}",
        f"scored adoptions              : {totals.adoptions}",
        f"unverifiable adoptions        : {totals.unverifiable}",
        f"  pooled  ok={ok_s + ok_m} wrong={wr_s + wr_m} "
        f"rate={rate(wr_s + wr_m, ok_s + ok_m + wr_s + wr_m)}",
        f"  single  ok={ok_s} wrong={wr_s} rate={rate(wr_s, ok_s + wr_s)}",
        f"  merged  ok={ok_m} wrong={wr_m} rate={rate(wr_m, ok_m + wr_m)}",
    ]
    return lines


# --- the can-this-return-non-empty demonstration ---------------------------

def _fake_tracks(titles: list[tuple[str, str]]) -> list[Track]:
    return [Track(index=i + 1, set="1", title=t, filename=f"t{i + 1:02d}.mp3",
                  title_source=src)
            for i, (t, src) in enumerate(titles)]


def _fake_canonical(titles: list[str]) -> ParsedSetlist:
    return ParsedSetlist(
        items=[SetlistItem(title=t, normalized=structure.norm_title(t), set="1")
               for t in titles],
        confidence="high")


def selftest() -> int:
    """Demonstrate that the harness's scorer can emit WRONG at all.

    Three hand-built cases go through the REAL `adopt_gap_titles`, the REAL
    spy and the REAL verdict comparison. Case B is constructed so a correct
    implementation MUST adopt a title that differs from the hidden tag: the
    canonical setlist genuinely disagrees with the tape at that one position.
    If the harness cannot print `wrong` here, no clean corpus result from it
    means anything.
    """
    cases = [
        ("A single-anchor gap that is right",
         ["Bertha", "Jack Straw", "Deal", "Loser"],
         [("Bertha", "tags"), ("Jack Straw", "tags"), ("Deal", "tags"),
          ("Loser", "tags")], 2, 2),
        ("B single-anchor gap that is WRONG (canonical disagrees with the tape)",
         ["Bertha", "Jack Straw", "Sugaree", "Loser"],
         [("Bertha", "tags"), ("Jack Straw", "tags"), ("Deal", "tags"),
          ("Loser", "tags")], 2, 2),
        ("C merged-anchor gap (left anchor consumes two items)",
         ["Scarlet Begonias", "Fire On The Mountain", "Estimated Prophet",
          "Eyes Of The World"],
         [("Scarlet Begonias > Fire On The Mountain", "tags"),
          ("Estimated Prophet", "tags"), ("Eyes Of The World", "tags")], 1, 1),
    ]
    saw_wrong = False
    n_adoptions = 0
    print("# selftest: real adopt_gap_titles, real spy, real scorer")
    for label, canon_titles, tagged, lo, hi in cases:
        canonical = _fake_canonical(canon_titles)
        tracks = _fake_tracks(tagged)
        blinded = list(tracks)
        for pos in range(lo, hi + 1):
            blinded[pos] = blinded[pos].model_copy(
                update={"title": f"t{pos + 1:02d}.mp3", "title_source": "unresolved"})
        with merge_run_spy() as calls:
            out = adopt_gap_titles(blinded, canonical, metadata_norms=set())
        kinds = anchor_kinds(blinded, calls, {})
        kind = merged_attribution(kinds, lo, hi, len(blinded))
        for pos in range(lo, hi + 1):
            adopted = out[pos].title
            if out[pos].title_source != "setlist-gap":
                print(f"  {label}: track {pos + 1} NOT adopted "
                      f"(source={out[pos].title_source})")
                continue
            hidden = tracks[pos].title
            verdict = ("ok" if fuzzy_norm_title(adopted) == fuzzy_norm_title(hidden)
                       else "wrong")
            saw_wrong = saw_wrong or verdict == "wrong"
            n_adoptions += 1
            print(f"  {label}: track {pos + 1} merged={kind} verdict={verdict} "
                  f"adopted={adopted!r} hidden={hidden!r}")
    print(f"# selftest adoptions={n_adoptions} saw_wrong={saw_wrong}")
    if n_adoptions == 0 or not saw_wrong:
        print("# SELFTEST FAILED: the harness cannot demonstrate a wrong adoption",
              file=sys.stderr)
        return 1
    print("# SELFTEST PASSED: the harness adopts, and it can score an adoption wrong")
    return 0


# --- triage roll-up --------------------------------------------------------

def read_triage(path: Path) -> dict[tuple[str, str], str]:
    """(adopted, hidden) -> hand-assigned class, from the companion TSV.

    The classification is data, not a heuristic: one row per distinct pair,
    assigned by hand, shipped beside the evidence doc so every published class
    count is regenerable rather than reconstructible.
    """
    out: dict[tuple[str, str], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cls, adopted, hidden = line.split("\t")
        out[(adopted, hidden)] = cls
    return out


def triage(class_path: Path, rows_path) -> int:
    """Roll the hand classification up over a sweep TSV."""
    src = sys.stdin if rows_path is None else open(rows_path, encoding="utf-8")
    try:
        raw = [l.rstrip("\n").split("\t") for l in src if not l.startswith("#") and l.strip()]
    finally:
        if src is not sys.stdin:
            src.close()
    classes = read_triage(class_path)
    i = {name: n for n, name in enumerate(COLUMNS)}
    seen: set[tuple] = set()
    distinct = []
    for f in raw:
        key = (f[i["identifier"]], f[i["track"]], f[i["anchor_kind"]],
               f[i["merged_attr"]], f[i["verdict"]], f[i["adopted"]], f[i["hidden"]])
        if key in seen:
            continue
        seen.add(key)
        distinct.append(f)
    total = len(distinct)
    cls: Counter = Counter()
    by_attr: dict[str, Counter] = defaultdict(Counter)
    unknown = 0
    for f in distinct:
        if f[i["verdict"]] == "ok":
            cls["ok"] += 1
            by_attr[f[i["merged_attr"]]]["ok"] += 1
            continue
        c = classes.get((f[i["adopted"]], f[i["hidden"]]))
        if c is None:
            unknown += 1
            continue
        cls[c] += 1
        by_attr[f[i["merged_attr"]]][c] += 1
    gw, gwf = cls["genuinely-wrong"], cls["genuinely-wrong/filler-segment"]
    print(f"distinct adoptions            : {total}")
    print(f"unclassified wrong adoptions  : {unknown}   "
          f"(must be 0; a nonzero value means the sweep and the "
          f"classification have drifted apart)")
    for c in ("ok", "scorer-artifact", "tag-typo-adoption-superior",
              "genuinely-wrong", "genuinely-wrong/filler-segment"):
        print(f"  {c:<32} {cls[c]:>5}  {_rate(cls[c], total)}")
    print(f"  HEADLINE RANGE: genuinely-wrong {_rate(gw, total)} "
          f"-- incl. filler-segment {_rate(gw + gwf, total)}")
    print("  by merged attribution (genuinely-wrong, strict / incl. filler):")
    for a in ("adjacent", "upstream", "none"):
        n = sum(by_attr[a].values())
        g, gf = by_attr[a]["genuinely-wrong"], by_attr[a]["genuinely-wrong/filler-segment"]
        print(f"    {a:<9} n={n:>5} strict={g:>4} ({_rate(g, n)})"
              f"  incl-filler={g + gf:>4} ({_rate(g + gf, n)})")
    return 1 if unknown else 0


# --- exposure: what the rung does to the cache as it actually stands --------

def natural(ia: CacheIA, pairs, args) -> int:
    """Blind nothing. Count the tracks `adopt_gap_titles` fills on tapes whose
    tags are already missing -- the population the rung changes in production,
    as opposed to the synthetic gaps the blind test manufactures."""
    items = unresolved = adopted = touched = 0
    print("# identifier\ttrack\tadopted\twas")
    for i, (candidate, identifier) in enumerate(pairs, 1):
        try:
            prep = prepare(ia, candidate, identifier, args.audio_format)
        except (IAError, KeyError, ValueError):
            continue
        if prep is None:
            continue
        items += 1
        n_un = sum(1 for t in prep.tracks if t.title_source == "unresolved")
        unresolved += n_un
        if not n_un:
            continue
        out = adopt_gap_titles(prep.tracks, prep.canonical,
                               metadata_norms=prep.metadata_norms,
                               aliases=prep.aliases)
        hits = [k for k in range(len(out)) if out[k].title_source == "setlist-gap"]
        if hits:
            touched += 1
            adopted += len(hits)
            for k in hits:
                print(f"{identifier}\t{k + 1}\t{_clean(out[k].title)}\t"
                      f"{_clean(prep.tracks[k].filename)}")
        if args.progress and i % args.progress == 0:
            print(f"... {i}/{len(pairs)} items, {unresolved} unresolved, "
                  f"{adopted} adopted", file=sys.stderr, flush=True)
    for line in (f"items measured                : {items}",
                 f"naturally unresolved tracks   : {unresolved}",
                 f"items the rung changes at all : {touched}",
                 f"tracks the rung fills         : {adopted}"):
        print("# " + line)
        print(line, file=sys.stderr)
    return 0


# --- entry point -----------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--format", dest="audio_format", default="mp3",
                    choices=sorted(FORMAT_BY_AUDIO))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--progress", type=int, default=50)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--triage", type=Path, default=None,
                    help="roll a hand-classification TSV up over a sweep TSV")
    ap.add_argument("--rows", type=Path, default=None,
                    help="sweep TSV for --triage (default: stdin)")
    ap.add_argument("--natural", action="store_true",
                    help="blind nothing; report how many genuinely-unresolved "
                         "tracks the rung fills as the cache stands")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.triage is not None:
        return triage(args.triage, args.rows)

    ia = CacheIA(args.cache.expanduser())
    pairs = build_candidates(ia)
    if args.limit:
        pairs = pairs[:args.limit]

    if args.natural:
        return natural(ia, pairs, args)

    totals = Totals()
    rows: list[str] = []
    print("# " + "\t".join(COLUMNS))
    for i, (candidate, identifier) in enumerate(pairs, 1):
        totals.items_seen += 1
        try:
            prep = prepare(ia, candidate, identifier, args.audio_format)
        except (IAError, KeyError, ValueError) as err:
            print(f"skip {identifier}: {err}", file=sys.stderr)
            continue
        if prep is None:
            continue
        totals.items_prepared += 1
        measure_item(prep, totals, rows)
        if args.progress and i % args.progress == 0:
            print(f"... {i}/{len(pairs)} items, {totals.trials} trials, "
                  f"{totals.firings} firings, {totals.adoptions} adoptions",
                  file=sys.stderr, flush=True)

    for row in rows:
        print(row)
    for line in summary_lines(totals, args.audio_format) + distinct_lines(rows):
        print("# " + line)
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
