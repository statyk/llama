"""Blind-the-tags measurement of the SIBLING TITLE TRANSFER rung (Phase C).

Manual, read-only diagnostic (never run by the pipeline). It takes tapes that
are already ≥95% tagged, HIDES a labelled subset of those tags, re-runs the
REAL shipped guard stack over the resulting unresolved runs, and scores every
automatically adopted title against the tag it could not see. The hidden tag
is the ground truth; the adoption is the guess.

WHAT IS SHIPPED CODE AND WHAT IS WRITTEN HERE, stated up front because the
whole value of this harness is that it measures the thing that ships:

  imported and CALLED     `junk.filter_files`, `titles.clean_tag_titles`,
                          `titles.title_fraction`, `util.length_seconds`,
                          `grouping.group_candidates`, `jerrybase.lookup`,
                          `gather.show_metadata_norms`, `gather._creator`,
                          `gather._description`, `gather.load_donor_tapes`,
                          `gather.best_donor`, `gather._donor_key`,
                          `siblings.propose_rows`, `siblings.rate_alignment`,
                          `siblings.cplus_filter`,
                          `structure.loosely_same_title`
  written here            the driver (cache enumeration + the mask), the
                          scorer, and the three-line donor sort that
                          `best_donor` performs inline (pinned equal to it by
                          `--reconcile`, which calls `best_donor` itself).

THE ALIGNMENT DOES NOT DEPEND ON THE MASK. `propose_rows` sees only the two
tapes' DURATIONS; masking a tag changes nothing it reads. So the DP is
computed ONCE per (target, donor) pair and cached to disk; every stratum,
mask and rep then re-runs only the guards, which are cheap. `--reconcile`
proves the cached path agrees with a live `gather.best_donor` call.

Modes
  --build-cache FILE   compute every (target, donor) alignment once (slow:
                       ~11k pairs, tens of minutes) and write JSONL.
  --score FILE         run the masked arm over a built cache.
  --slide-scan         the REAL (unmasked) donor-span-slide census; needs no
                       cache and no mask -- a ≥95%-tagged tape IS its own
                       ground truth.
  --reconcile FILE     agreement + adopted titles from the cached path vs a
                       live `gather.best_donor` / `rate_alignment` call.
  --selftest FILE      planted positive controls through the committed
                       scorer (see `_selftest`).

Offline standing caveat: cache-only, `setlistfm=None`, so canonical setlists
here are LMA-only. Ground truth is the target taper's own tags, measured 24%
wrong at anchor disagreements (spec), so EVERY error rate here is an UPPER
BOUND.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from llama import jerrybase
from llama.grouping import group_candidates
from llama.ia_client import IAError
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Track
from llama.siblings import (AUTO, DonorTape, SiblingRow, cplus_filter,
                            propose_rows, rate_alignment)
from llama.stages.gather import (_creator, _description, _donor_key,
                                 best_donor, load_donor_tapes,
                                 show_metadata_norms)
from llama.structure import loosely_same_title
from llama.titles import clean_tag_titles, title_fraction
from llama.util import length_seconds

DEFAULT_CACHE = Path.home() / ".llama" / "cache"

# A target must be at least this well tagged to serve as its own ground
# truth. The spec's population caveat: 702 of 757 cached recordings sit here.
WELL_TAGGED = 0.95

# Visible-tag fraction each stratum masks down to (the spec's three bands,
# taken at their midpoints).
STRATA = {"20-50": 0.35, "50-80": 0.65, "80-95": 0.875}
REPS = 5                      # random mask only; the prefix mask is deterministic

# Below this a mask cannot leave both a visible and a hidden track in every
# stratum, so the tape says nothing about any band.
MIN_TRACKS = 6

# A pair is a WHOLESALE FAILURE when it adopts at least this many titles on
# hidden tracks and at least this fraction of them are loose-wrong. The
# probe's four named wholesale failures were whole-tape garbage at agreement
# 0.00; this is that shape, sized so a single variant miss cannot qualify.
WHOLESALE_MIN_ADOPTED = 2
WHOLESALE_WRONG_FRACTION = 0.8

_GENERIC_COLLECTIONS = {
    "etree", "stream_only", "audio", "audio_music", "opensource_audio",
    "community", "additional_collections",
}


# --- cache-backed stand-in for llama.ia_client.IAClient ---------------------

class CacheIA:
    """`.metadata(identifier)` served from the on-disk archive.org cache.
    Read-only by construction; an uncached identifier raises `IAError`, which
    is what `load_donor_tapes` already handles."""

    def __init__(self, cache_dir: Path):
        self._paths = {p.name[len("md_"):-len(".json")]: p
                       for p in sorted(cache_dir.glob("md_*.json"))}
        self._memo: dict[str, dict] = {}

    def identifiers(self) -> list[str]:
        return sorted(self._paths)

    def metadata(self, identifier: str) -> dict:
        if identifier in self._memo:
            return self._memo[identifier]
        path = self._paths.get(identifier)
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
    colls = meta.get("collection")
    colls = colls if isinstance(colls, list) else [colls] if colls else []
    for c in colls:
        if isinstance(c, str) and c.lower() not in _GENERIC_COLLECTIONS:
            return c
    creator = _creator(meta)
    return str(creator or (colls[0] if colls else "") or "unknown")


def _doc_of(meta: dict) -> dict:
    return {"identifier": meta.get("identifier", ""),
            "title": meta.get("title", ""),
            "date": str(_first(meta.get("date")) or "")[:10],
            "venue": meta.get("venue"), "coverage": meta.get("coverage"),
            "description": _description(meta)}


def build_candidates(ia: CacheIA):
    """Every candidate the cache supports, via the real `group_candidates`,
    so early/late splits and `/spans` come out as production produces them."""
    by_collection: dict[str, list[dict]] = {}
    for identifier in ia.identifiers():
        try:
            meta = ia.metadata(identifier).get("metadata", {})
        except IAError:
            continue
        if not meta.get("identifier") or not _first(meta.get("date")):
            continue
        by_collection.setdefault(_collection_of(meta), []).append(_doc_of(meta))
    out = []
    for collection, docs in sorted(by_collection.items()):
        out.extend(group_candidates(collection, docs, jerrybase_enabled=True))
    return out


# --- the target tape -------------------------------------------------------

def load_target(ia: CacheIA, candidate, identifier: str, want):
    """`(names, durations, tag_titles, metadata_norms)` for one recording, or
    None when it cannot serve as a blind target (no audio, a missing
    duration, or under `WELL_TAGGED`). Built by the shipped filter and the
    shipped tag cleaner, so the tape this measures is production's tape."""
    try:
        md = ia.metadata(identifier)
    except IAError:
        return None
    kept, _excluded, _ordering = filter_files(md.get("files", []), want_format=want)
    if len(kept) < MIN_TRACKS:
        return None
    durations = [length_seconds(f.get("length")) for f in kept]
    if any(d is None or d <= 0 for d in durations):
        return None
    titles = clean_tag_titles(kept)
    if title_fraction(titles) < WELL_TAGGED:
        return None
    meta = md.get("metadata", {})
    artist = str(_creator(meta) or candidate.collection)
    events = jerrybase.lookup(artist, candidate.date)
    norms = show_metadata_norms(artist, candidate, meta, events)
    return ([f["name"] for f in kept], durations, titles, norms)


def make_tracks(names, durations, titles, hidden: set[int]) -> list[Track]:
    """The `Track` list the guards see. A hidden position loses its title AND
    its source, exactly as an untagged file reaches `_sibling_transfer`."""
    out = []
    for i, (name, dur, title) in enumerate(zip(names, durations, titles)):
        blind = i in hidden or not title.strip()
        out.append(Track(index=i + 1, set="1", title="" if blind else title,
                         filename=name, duration_sec=dur,
                         title_source="unresolved" if blind else "tags"))
    return out


# --- pass 1: the alignment cache -------------------------------------------

def _row_json(r: SiblingRow) -> list:
    return [r.track, r.proposed, list(r.donor_span) if r.donor_span else None,
            r.residual_sec, r.penalty_sec, r.verdict, r.reason]


def _row_of(j: list) -> SiblingRow:
    return SiblingRow(j[0], j[1], tuple(j[2]) if j[2] else None,
                      j[3], j[4], j[5], j[6])


def build_cache(ia: CacheIA, out_path: Path, audio_format: str,
                limit: int | None, progress: int) -> int:
    want = FORMAT_BY_AUDIO[audio_format]
    n_targets = n_pairs = 0
    t0 = time.time()
    with out_path.open("w", encoding="utf-8") as fh:
        for cand in build_candidates(ia):
            if len(cand.recordings) < 2:
                continue
            for rec in cand.recordings:
                loaded = load_target(ia, cand, rec.identifier, want)
                if loaded is None:
                    continue
                names, durations, titles, norms = loaded
                donors, _notes = load_donor_tapes(ia, cand, rec.identifier, want)
                if not donors:
                    continue
                pairs = []
                for donor in donors:
                    rows, diag = propose_rows(durations, donor, metadata_norms=norms)
                    if rows is None:
                        continue
                    pairs.append({"donor": donor.identifier, "cost": diag["cost"],
                                  "rows": [_row_json(r) for r in rows]})
                if not pairs:
                    continue
                n_targets += 1
                n_pairs += len(pairs)
                fh.write(json.dumps({
                    "target": rec.identifier, "names": names,
                    "durations": durations, "titles": titles,
                    "norms": sorted(norms), "pairs": pairs}) + "\n")
                if progress and n_targets % progress == 0:
                    print(f"  ... {n_targets} targets, {n_pairs} pairs, "
                          f"{time.time() - t0:.0f}s", file=sys.stderr, flush=True)
                if limit and n_targets >= limit:
                    print(f"cache: {n_targets} targets, {n_pairs} pairs, "
                          f"{time.time() - t0:.0f}s", file=sys.stderr)
                    return 0
    print(f"cache: {n_targets} targets, {n_pairs} pairs, "
          f"{time.time() - t0:.0f}s", file=sys.stderr)
    return 0


def read_cache(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


# --- the masks -------------------------------------------------------------

def random_hidden(n: int, keep_fraction: float, seed: int) -> set[int]:
    keep = max(1, min(n - 1, round(keep_fraction * n)))
    rng = random.Random(seed)
    return set(rng.sample(range(n), n - keep))


def prefix_hidden(n: int, keep_fraction: float) -> set[int]:
    """A taper who tagged from the top and stopped: the first `keep` tracks
    keep their tags, everything after is blind."""
    keep = max(1, min(n - 1, round(keep_fraction * n)))
    return set(range(keep, n))


# --- pass 2: the guards, per mask ------------------------------------------

def pick_donor(entry, tracks):
    """`gather.best_donor`'s selection, over cached rows instead of a live
    fetch: rate every donor and take `_donor_key`'s winner. The three-line
    sort is the only piece of `best_donor` reproduced here; `--reconcile`
    pins it equal to the real call."""
    scored = []
    for pair in entry["pairs"]:
        rows = [_row_of(j) for j in pair["rows"]]
        res = rate_alignment(rows, tracks)
        scored.append((_donor_key(res.agreement, pair["cost"], pair["donor"]),
                       pair["donor"], rows, res))
    if not scored:
        return None, [], None
    scored.sort(key=lambda c: c[0])
    _, donor, rows, res = scored[0]
    return donor, rows, res


def score_one(entry, hidden: set[int]):
    """One (target, mask) trial through the shipped guards.

    Returns a dict of counters plus the per-row detail the triage needs. The
    C+ arm is measured by running the SAME rows twice: once as `propose_rows`
    left them (the bare ratio band, which is what the spec's "bare ratio"
    column means) and once through `cplus_filter`."""
    titles = entry["titles"]
    tracks = make_tracks(entry["names"], entry["durations"], titles, hidden)
    donor, rows, res = pick_donor(entry, tracks)
    out = {"target": entry["target"], "donor": donor, "n": len(titles),
           "hidden": sorted(hidden), "band": res.band if res else None,
           "agreement": res.agreement if res else None,
           "n_anchors": res.n_anchors if res else 0,
           "adopted": [], "cplus_blocked": [], "bare_adopted": []}
    if donor is None or res is None or res.band != AUTO_BAND:
        return out
    filtered = cplus_filter(rows, tracks)
    by_track = {r.track: r for r in filtered}
    for row in rows:
        pos = row.track - 1
        if pos not in hidden or not titles[pos].strip():
            continue          # not a blind track, or no ground truth to score
        truth = titles[pos]
        if row.verdict != "adopt":
            continue
        rec = {"track": row.track, "truth": truth, "proposed": row.proposed,
               "correct": bool(loosely_same_title(truth, row.proposed)),
               "residual": row.residual_sec, "penalty": row.penalty_sec}
        out["bare_adopted"].append(rec)
        if by_track[row.track].verdict == "adopt":
            out["adopted"].append(rec)
        else:
            out["cplus_blocked"].append({**rec,
                                         "reason": by_track[row.track].reason})
    return out


AUTO_BAND = "auto"


def is_wholesale(trial) -> bool:
    ad = trial["adopted"]
    if len(ad) < WHOLESALE_MIN_ADOPTED:
        return False
    wrong = sum(1 for a in ad if not a["correct"])
    return wrong / len(ad) >= WHOLESALE_WRONG_FRACTION


def run_score(path: Path, dump: Path | None, progress: int) -> int:
    entries = list(read_cache(path))
    print(f"# scoring {len(entries)} cached targets", file=sys.stderr)
    cells: dict[tuple, dict] = defaultdict(
        lambda: {"trials": 0, "auto": 0, "adopted": 0, "wrong": 0,
                 "wholesale_titles": 0, "wholesale_pairs": 0,
                 "cplus_blocked": 0, "cplus_blocked_wrong": 0,
                 "cplus_blocked_right": 0, "bare_adopted": 0, "bare_wrong": 0})
    detail = []
    t0 = time.time()
    for k, entry in enumerate(entries):
        n = len(entry["titles"])
        for stratum, keep in STRATA.items():
            for mask in ("random", "prefix"):
                reps = REPS if mask == "random" else 1
                for rep in range(reps):
                    hidden = (random_hidden(n, keep, seed=1000 * rep + k)
                              if mask == "random" else prefix_hidden(n, keep))
                    trial = score_one(entry, hidden)
                    cell = cells[(mask, stratum)]
                    cell["trials"] += 1
                    if trial["band"] != AUTO_BAND:
                        continue
                    cell["auto"] += 1
                    cell["adopted"] += len(trial["adopted"])
                    cell["wrong"] += sum(1 for a in trial["adopted"]
                                         if not a["correct"])
                    cell["bare_adopted"] += len(trial["bare_adopted"])
                    cell["bare_wrong"] += sum(1 for a in trial["bare_adopted"]
                                              if not a["correct"])
                    cell["cplus_blocked"] += len(trial["cplus_blocked"])
                    cell["cplus_blocked_wrong"] += sum(
                        1 for a in trial["cplus_blocked"] if not a["correct"])
                    cell["cplus_blocked_right"] += sum(
                        1 for a in trial["cplus_blocked"] if a["correct"])
                    if is_wholesale(trial):
                        cell["wholesale_pairs"] += 1
                        cell["wholesale_titles"] += len(trial["adopted"])
                    if dump is not None and (trial["adopted"] or
                                             trial["cplus_blocked"]):
                        detail.append({"mask": mask, "stratum": stratum,
                                       "rep": rep, **trial})
        if progress and (k + 1) % progress == 0:
            print(f"  ... {k + 1}/{len(entries)} targets, "
                  f"{time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    if dump is not None:
        dump.write_text(json.dumps(detail), encoding="utf-8")
    print(json.dumps({f"{m}/{s}": v for (m, s), v in sorted(cells.items())},
                     indent=2))
    return 0


# --- Step 9: the REAL donor-span-slide census (no mask) --------------------

def slide_scan(ia: CacheIA, audio_format: str, progress: int) -> int:
    """Does a LOCALISED donor-span slide with high anchor agreement occur in
    the REAL corpus? No mask: a ≥95%-tagged tape is its own ground truth, so
    every paired track is an anchor and a slide is directly visible.

    A pair is counted when its agreement is >= AUTO (the band that ships
    automatically) yet some run of >= 2 consecutive disagreeing anchors has,
    for every member, a proposal that loosely matches the tape's OWN title at
    a CONSTANT non-zero offset -- i.e. the alignment is displaced there while
    the flanks are right. That is the class C+ exists for, stated as an
    observable rather than as a mechanism."""
    want = FORMAT_BY_AUDIO[audio_format]
    n_pairs = n_auto = 0
    slides = []
    t0 = time.time()
    for k, cand in enumerate(build_candidates(ia)):
        if len(cand.recordings) < 2:
            continue
        for rec in cand.recordings:
            loaded = load_target(ia, cand, rec.identifier, want)
            if loaded is None:
                continue
            names, durations, titles, norms = loaded
            tracks = make_tracks(names, durations, titles, hidden=set())
            donors, _ = load_donor_tapes(ia, cand, rec.identifier, want)
            for donor in donors:
                rows, diag = propose_rows(durations, donor, metadata_norms=norms)
                if rows is None:
                    continue
                res = rate_alignment(rows, tracks)
                n_pairs += 1
                if res.agreement is None or res.agreement < AUTO:
                    continue
                n_auto += 1
                found = _localised_slide(rows, titles, res)
                if found:
                    slides.append({"target": rec.identifier,
                                   "donor": donor.identifier,
                                   "agreement": res.agreement,
                                   "n_anchors": res.n_anchors, "runs": found})
        if progress and (k + 1) % progress == 0:
            print(f"  ... {k + 1} candidates, {n_pairs} pairs, "
                  f"{time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    print(json.dumps({"pairs": n_pairs, "auto_band_pairs": n_auto,
                      "localised_slides": len(slides), "detail": slides},
                     indent=2))
    return 0


def _localised_slide(rows, titles, res):
    """Runs of >= 2 consecutive disagreeing anchors whose proposals all match
    the tape's own title at one constant non-zero offset."""
    bad = sorted(d.track for d in res.disagreements)
    by_track = {r.track: r for r in rows}
    runs, cur = [], []
    for t in bad:
        if cur and t == cur[-1] + 1:
            cur.append(t)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [t]
    if len(cur) >= 2:
        runs.append(cur)
    out = []
    for run in runs:
        for off in (-2, -1, 1, 2):
            ok = True
            for t in run:
                j = t - 1 + off
                prop = by_track[t].proposed
                if not (0 <= j < len(titles)) or not prop or \
                        not loosely_same_title(titles[j], prop):
                    ok = False
                    break
            if ok:
                out.append({"tracks": run, "offset": off})
                break
    return out


# --- reconciliation: the cached path vs a live best_donor ------------------

def _plant_rows(entry: dict) -> dict:
    """`--reconcile --plant`: rotate every cached pair's proposed titles by
    one row. The live path is untouched, so a working reconciliation MUST
    now report mismatches.

    Without this, `--reconcile`'s headline is a zero with no demonstration
    that it can ever be non-zero -- the same defect as `--arm numeric`'s
    legality rule, one instrument over.
    """
    pairs = []
    for pair in entry["pairs"]:
        rows = [list(j) for j in pair["rows"]]
        props = [r[1] for r in rows]
        for r, prop in zip(rows, props[1:] + props[:1]):
            r[1] = prop
        pairs.append({**pair, "rows": rows})
    return {**entry, "pairs": pairs}


def reconcile(ia: CacheIA, path: Path, audio_format: str, n: int,
              plant: bool = False) -> int:
    """For `n` cached targets, re-run the LIVE shipped path
    (`gather.best_donor` -> `siblings.rate_alignment` -> `cplus_filter`) and
    require identical donor, agreement, band and adopted title strings.

    This is Step 8's acceptance: the scorer's agreement figure must equal the
    shipped guard's, obtained by CALLING `rate_alignment`, not by
    reimplementing it."""
    want = FORMAT_BY_AUDIO[audio_format]
    by_target = {c.recordings[i].identifier: c
                 for c in build_candidates(ia)
                 for i in range(len(c.recordings))}
    checked = mismatched = 0
    bands: Counter = Counter()
    n_title_sets = n_titles = 0
    for entry in read_cache(path):
        if checked >= n:
            break
        cand = by_target.get(entry["target"])
        if cand is None:
            continue
        if plant:
            entry = _plant_rows(entry)
        titles = entry["titles"]
        hidden = random_hidden(len(titles), 0.65, seed=7)
        tracks = make_tracks(entry["names"], entry["durations"], titles, hidden)
        norms = set(entry["norms"])
        live_donor, live_rows, live_res, _ = best_donor(
            ia, cand, entry["target"], want, tracks, norms)
        c_donor, c_rows, c_res = pick_donor(entry, tracks)
        checked += 1
        same = (getattr(live_donor, "identifier", None) == c_donor
                and (live_res.agreement if live_res else None)
                == (c_res.agreement if c_res else None)
                and (live_res.band if live_res else None)
                == (c_res.band if c_res else None))
        bands[live_res.band if live_res else "no-donor"] += 1
        if same and live_res and live_res.band == AUTO_BAND:
            lf = {r.track: r.proposed for r in cplus_filter(live_rows, tracks)
                  if r.verdict == "adopt"}
            cf = {r.track: r.proposed for r in cplus_filter(c_rows, tracks)
                  if r.verdict == "adopt"}
            same = lf == cf
            # DEGENERACY GUARD: "0 mismatched" over 40 EMPTY title sets would
            # be a pass that compared nothing. Report how many sets were
            # non-empty and how many title strings they held.
            if lf:
                n_title_sets += 1
                n_titles += len(lf)
        if not same:
            mismatched += 1
            print(f"  MISMATCH {entry['target']}: live="
                  f"{getattr(live_donor, 'identifier', None)}/"
                  f"{live_res.agreement if live_res else None}/"
                  f"{live_res.band if live_res else None} cached="
                  f"{c_donor}/{c_res.agreement if c_res else None}/"
                  f"{c_res.band if c_res else None}")
    print(f"\nRECONCILE{' (PLANTED)' if plant else ''}: {checked} targets, "
          f"{mismatched} mismatched")
    print(f"  bands: {dict(bands)}")
    print(f"  non-empty adopted-title sets compared: {n_title_sets} "
          f"({n_titles} title strings)")
    if plant:
        ok = bool(checked and mismatched)
        print(f"  PLANT expects mismatches -> {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    ok = bool(checked and not mismatched and n_titles)
    print(f"  -> {'PASS' if ok else 'FAIL'}"
          f"{'' if n_titles else '  (DEGENERATE: nothing was compared)'}")
    return 0 if ok else 1


# --- selftest: planted positive controls through the committed scorer ------

def _plant_titles(titles: list[str], hidden: set[int]) -> tuple[list[str], list[int]]:
    """The POISON plant's donor titles: every hidden track gets a title from
    THIS tape that is verifiably NOT `loosely_same_title` to its own truth.

    A plain rotation is not good enough and the failure is not hypothetical.
    On `gd1968-10-12.sbd.gans.miller.owen.9385.shnf` a rotation put `Jam \\`
    on track 15 whose truth is `Jam >` -- the tape has two Jam tracks, the
    two strings loosely match, and the scorer CORRECTLY scored the adoption
    right. The plant had failed to corrupt; the scorer had not failed to see.
    Accepting 246/247 there would have blunted the control permanently, so
    the plant is made to corrupt instead.

    Returns `(titles, unplantable)`. `unplantable` lists hidden indices for
    which NO title anywhere on the tape is loosely different from the truth
    (a tape of nine `Tuning`s); those tracks keep their own title and are
    excluded from the plant's denominator, and the count is printed rather
    than absorbed.
    """
    out = list(titles)
    unplantable: list[int] = []
    order = sorted(hidden)
    for i in order:
        truth = titles[i]
        pick = None
        # deterministic: the tape's own titles, starting just after `i`,
        # hidden ones first so the plant stays a permutation where it can.
        for j in ([k for k in order if k != i] + [k for k in range(len(titles))
                                                 if k not in hidden]):
            cand = titles[j]
            if cand.strip() and not loosely_same_title(truth, cand):
                pick = cand
                break
        if pick is None:
            unplantable.append(i)
        else:
            out[i] = pick
    return out, unplantable


def _selftest(path: Path, limit: int | None) -> int:
    """Two plants, run through the code above exactly as committed, over the
    WHOLE cache by default -- the same population every table in the evidence
    doc is taken over. `--limit` narrows it for a smoke run and the printed
    line always names how many targets were actually used, because a plant
    proven on 12 targets says nothing about a measurement made on 716.

    1. TRUTH -- the donor IS the target (identical durations and titles).
       Every adoption must score CORRECT, and at least one must occur, which
       is what a scorer stubbed to `False` cannot produce.
    2. POISON -- the donor is the target with every HIDDEN track's title
       replaced by a title from the same tape that is verifiably loosely
       DIFFERENT from its own truth (`_plant_titles`). The visible tracks
       still agree, so the pair still reaches the automatic band and still
       adopts; every one of those adoptions must score WRONG. Rotating the
       WHOLE donor (the obvious plant, and Step 1's rotation control) is
       useless as a scorer control precisely because the guard then declines
       the pair and the scorer is never asked a question -- 0 adoptions, 0
       errors, indistinguishable from a scorer that cannot see failure.
    3. DEGENERACY -- assert the two plants disagree. A measurement whose
       expected value is 0 cannot distinguish `computed correctly` from
       `never computed`, so the control that matters is the PAIR: one plant
       whose expected answer is all-correct and one whose expected answer is
       all-wrong, through the same code path.
    """
    entries = list(read_cache(path))
    if limit:
        entries = entries[:limit]
    rot_wrong = rot_adopted = true_correct = true_adopted = 0
    used = n_unplantable = 0
    for entry in entries:
        n = len(entry["titles"])
        hidden = random_hidden(n, 0.65, seed=11)
        clone = DonorTape(identifier="SELFTEST-TRUTH", names=entry["names"],
                          durations=list(entry["durations"]),
                          titles=list(entry["titles"]))
        poisoned, unplantable = _plant_titles(entry["titles"], hidden)
        n_unplantable += len(unplantable)
        rot = DonorTape(identifier="SELFTEST-POISON", names=entry["names"],
                        durations=list(entry["durations"]), titles=poisoned)
        norms = set(entry["norms"])
        for donor, bucket in ((clone, "truth"), (rot, "rot")):
            rows, diag = propose_rows(entry["durations"], donor,
                                      metadata_norms=norms)
            if rows is None:
                continue
            plant = {**entry, "pairs": [{"donor": donor.identifier,
                                         "cost": diag["cost"],
                                         "rows": [_row_json(r) for r in rows]}]}
            trial = score_one(plant, hidden)
            for a in trial["adopted"]:
                if bucket == "truth":
                    true_adopted += 1
                    true_correct += bool(a["correct"])
                elif a["track"] - 1 not in unplantable:
                    rot_adopted += 1
                    rot_wrong += (not a["correct"])
        used += 1
    ok_truth = true_adopted > 0 and true_correct == true_adopted
    ok_rot = rot_adopted > 0 and rot_wrong == rot_adopted
    print(f"population  : {used} targets from {path.name}")
    print(f"TRUTH plant : {true_correct}/{true_adopted} correct  "
          f"-> {'PASS' if ok_truth else 'FAIL'}")
    print(f"POISON plant: {rot_wrong}/{rot_adopted} wrong      "
          f"-> {'PASS' if ok_rot else 'FAIL'}"
          f"  ({n_unplantable} track(s) had no loosely-different title on "
          f"their own tape and are excluded)")
    print(f"DEGENERACY  : the two plants differ -> "
          f"{'PASS' if ok_truth and ok_rot else 'FAIL'}")
    return 0 if (ok_truth and ok_rot) else 1


# --- triage of wrong adoptions (Step 2) and the row census (Step 7) -------

_NON_SONG = ("tuning", "banter", "crowd", "intro", "outro", "applause",
             "drums", "space", "jam", "tune", "encore", "announce", "talk",
             "chatter", "noise", "silence", "cut", "filler")


def _aggressive(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum())


def classify(truth: str, proposed: str, shifted: set[str]) -> str:
    """Triage class for one wrong adoption. Order matters and is stated:
    a shift is the dangerous class, so it is tested FIRST and only then are
    the benign explanations offered."""
    if proposed in shifted:
        return "shift"
    a, b = _aggressive(truth), _aggressive(proposed)
    if a and b and (a in b or b in a):
        return "variant/comparator"
    if any(w in truth.lower() for w in _NON_SONG) or \
            any(w in proposed.lower() for w in _NON_SONG):
        return "non-song boundary"
    return "genuine"


def run_triage(dump: Path, cache: Path, sample: int) -> int:
    """Classify every wrong adoption, in BOTH units.

    UNIT MATTERS HERE. One (target, donor, track) error is re-drawn by every
    stratum and rep whose mask happens to hide that track, so the entry count
    is several times the count of distinct errors. Both are reported; a rate
    quoted in one unit against a denominator in the other is exactly the
    defect the count-unit rule exists to prevent.

    Shift detection uses the target's FULL hidden truth vector (read back
    from the alignment cache), not just the tracks that happened to be
    adopted in this trial -- a shift whose neighbour was visible in this rep
    is still a shift."""
    truths = {e["target"]: e["titles"] for e in read_cache(cache)}
    detail = json.loads(dump.read_text())
    classes: Counter = Counter()
    distinct: dict[str, set] = defaultdict(set)
    per_class: dict[str, list] = defaultdict(list)
    for trial in detail:
        if trial["mask"] != "random":
            continue
        vec = truths.get(trial["target"], [])
        for a in trial["adopted"]:
            if a["correct"]:
                continue
            neighbours = {t for k, t in enumerate(vec)
                          if t and k != a["track"] - 1}
            cls = classify(a["truth"], a["proposed"], neighbours)
            classes[cls] += 1
            distinct[cls].add((trial["target"], trial["donor"], a["track"]))
            per_class[cls].append({"stratum": trial["stratum"],
                                   "target": trial["target"],
                                   "donor": trial["donor"], **a})
    print("# WRONG ADOPTIONS, random mask (SYNTH)")
    print("# entries = adopted title instances; distinct = (target, donor, track)")
    total = sum(classes.values())
    tot_d = len(set().union(*distinct.values())) if distinct else 0
    for cls, n in classes.most_common():
        print(f"  {cls:20s} entries {n:5d} ({n / total:5.1%})   "
              f"distinct {len(distinct[cls]):4d}")
    print(f"  {'TOTAL':20s} entries {total:5d}            distinct {tot_d:4d}")
    rng = random.Random(99)
    print(f"\n# hand-check sample ({sample} DISTINCT per class, seed 99)")
    for cls, rows in sorted(per_class.items()):
        seen, uniq = set(), []
        for r in rows:
            key = (r["target"], r["donor"], r["track"])
            if key not in seen:
                seen.add(key)
                uniq.append(r)
        print(f"\n## {cls}  ({len(uniq)} distinct)")
        for r in rng.sample(uniq, min(sample, len(uniq))):
            print(f"  {r['target']} <- {r['donor']} t{r['track']}"
                  f"\n      truth={r['truth']!r}\n      prop ={r['proposed']!r}"
                  f"  resid={r['residual']:.0f}s pen={r['penalty']:.0f}s")
    return 0


def row_census(path: Path) -> int:
    """Step 7: how often does a TARGET-SIDE SKIP arise, and what does the
    absorption alternative cost? Counted over every cached (target, donor)
    alignment -- unit: rows (one target track in one pair) and pairs."""
    n_pairs = n_rows = 0
    skip_rows = skip_pairs = split_rows = split_pairs = 0
    merge_rows = merge_pairs = 0
    skip_hist: Counter = Counter()
    for entry in read_cache(path):
        for pair in entry["pairs"]:
            n_pairs += 1
            rows = [_row_of(j) for j in pair["rows"]]
            n_rows += len(rows)
            sk = sum(1 for r in rows if r.reason == "no sibling track")
            sp = sum(1 for r in rows
                     if r.reason == "sibling song split across target files")
            mg = sum(1 for r in rows if r.donor_span
                     and r.donor_span[1] - r.donor_span[0] > 1)
            skip_rows += sk
            split_rows += sp
            merge_rows += mg
            skip_pairs += bool(sk)
            split_pairs += bool(sp)
            merge_pairs += bool(mg)
            skip_hist[min(sk, 5)] += 1
    print(json.dumps({
        "pairs": n_pairs, "rows": n_rows,
        "target_side_skip_rows": skip_rows, "pairs_with_a_skip": skip_pairs,
        "split_declined_rows": split_rows, "pairs_with_a_split": split_pairs,
        "merged_rows": merge_rows, "pairs_with_a_merge": merge_pairs,
        "skips_per_pair_histogram(5=5+)": dict(sorted(skip_hist.items())),
    }, indent=2))
    return 0


# --- instrument proofs: schema, and an independent population oracle ------

def check_schema(cache_path: Path, dump: Path | None) -> int:
    """Proof 1 of 3 for this instrument: the artefacts have the shape the
    scorer assumes. Types, parallel-length invariants, 1-based track numbers
    covering every target track exactly once, half-open donor spans inside
    the donor, and (for the detail dump) that `adopted` and `cplus_blocked`
    are disjoint and both subsets of `bare_adopted`."""
    bad: list[str] = []
    n_entries = n_pairs = n_rows = 0
    for e in read_cache(cache_path):
        n_entries += 1
        n = len(e["names"])
        if not (len(e["durations"]) == len(e["titles"]) == n):
            bad.append(f"{e['target']}: names/durations/titles disagree")
        if any(not isinstance(d, (int, float)) or d <= 0 for d in e["durations"]):
            bad.append(f"{e['target']}: a non-positive duration")
        for pair in e["pairs"]:
            n_pairs += 1
            rows = [_row_of(j) for j in pair["rows"]]
            n_rows += len(rows)
            if sorted(r.track for r in rows) != list(range(1, n + 1)):
                bad.append(f"{e['target']}/{pair['donor']}: rows do not cover "
                           f"1..{n} exactly once")
            for r in rows:
                if r.donor_span and not (0 <= r.donor_span[0] < r.donor_span[1]):
                    bad.append(f"{e['target']}/{pair['donor']} t{r.track}: "
                               f"bad span {r.donor_span}")
                if r.verdict == "adopt" and not r.proposed:
                    bad.append(f"{e['target']}/{pair['donor']} t{r.track}: "
                               "adopt with no title")
    print(f"cache: {n_entries} targets, {n_pairs} pairs, {n_rows} rows")
    if dump is not None:
        detail = json.loads(dump.read_text())
        for t in detail:
            ad = {a["track"] for a in t["adopted"]}
            bl = {a["track"] for a in t["cplus_blocked"]}
            ba = {a["track"] for a in t["bare_adopted"]}
            if ad & bl:
                bad.append(f"{t['target']}: adopted and blocked overlap")
            if not (ad | bl) <= ba:
                bad.append(f"{t['target']}: adopted|blocked not within bare")
            if t["band"] != AUTO_BAND and (ad or bl):
                bad.append(f"{t['target']}: rows outside the automatic band")
        # UNIT: a detail record is written only when a trial adopted or
        # blocked at least one row, so this is BELOW the trial count
        # (716 targets x 3 strata x (5 random reps + 1 prefix) = 12,888).
        print(f"detail: {len(detail)} records (of "
              f"{n_entries * len(STRATA) * (REPS + 1)} trials)")
    for line in bad[:20]:
        print(f"  BAD {line}")
    print(f"SCHEMA: {len(bad)} violations -> "
          f"{'PASS' if not bad else 'FAIL'}")
    return 0 if not bad else 1


def population_oracle(ia: CacheIA, cache_path: Path, audio_format: str) -> int:
    """Proof 3 of 3: an INDEPENDENT recount of the measured population.

    INDEPENDENT MEANS: it shares no *domain judgment* with the instrument.
    It calls neither `build_candidates` nor `load_target` nor
    `gather.load_donor_tapes` -- the three functions `build_cache` uses to
    decide what belongs in the population, any one of which could carry a
    bug that moves both sides of a check that shared it. (That is exactly
    the failure the three-instrument bar was written to prevent: Task 2's
    census oracle caught a first-non-empty-format bug BECAUSE it shared no
    assumptions.) No grouping decision, tag-fraction test, duration test or
    donor-qualification test is reused from this file -- its collection
    key, its search-document shape, its target test and its donor test are
    all written out below, re-derived from scratch.

    It DOES still call two in-file names, both judgment-free: `read_cache`
    (a plain JSONL reader, used only to compare the oracle's recount
    against what the sweep measured) and `CacheIA.identifiers`/`.metadata`
    (the `ia` argument's own cache-file access -- read bytes off disk, no
    decision). Neither encodes any opinion about what belongs in the
    population.

    What it also shares, unavoidably and by design, is the SHIPPED llama
    functions the population is defined in terms of -- `group_candidates`,
    `filter_files`, `clean_tag_titles`, `title_fraction`, `length_seconds`.
    Those are the system under measurement, not the instrument; an oracle
    that re-implemented `filter_files` would be measuring a different
    population and its agreement would mean nothing.

    The whole difference against the sweep's cache must be targets under
    `MIN_TRACKS`, which is the one filter the oracle deliberately omits.
    """
    want = FORMAT_BY_AUDIO[audio_format]

    # -- the oracle's OWN search documents, grouped its OWN way -------------
    docs_by_key: dict[str, list[dict]] = {}
    metas: dict[str, dict] = {}
    for identifier in ia.identifiers():
        try:
            md = ia.metadata(identifier)
        except IAError:
            continue
        meta = md.get("metadata", {})
        ident = meta.get("identifier")
        raw_date = meta.get("date")
        raw_date = raw_date[0] if isinstance(raw_date, list) and raw_date else raw_date
        if not ident or not raw_date:
            continue
        metas[identifier] = meta
        colls = meta.get("collection")
        colls = colls if isinstance(colls, list) else [colls] if colls else []
        key = ""
        for c in colls:
            if isinstance(c, str) and c.lower() not in _GENERIC_COLLECTIONS:
                key = c
                break
        if not key:
            creator = meta.get("creator")
            creator = (creator[0] if isinstance(creator, list) and creator
                       else creator)
            key = str(creator or (colls[0] if colls else "") or "unknown")
        desc = meta.get("description", "")
        desc = " ".join(desc) if isinstance(desc, list) else str(desc or "")
        docs_by_key.setdefault(key, []).append({
            "identifier": ident, "title": meta.get("title", ""),
            "date": str(raw_date)[:10], "venue": meta.get("venue"),
            "coverage": meta.get("coverage"), "description": desc})

    # -- the oracle's OWN target and donor tests ---------------------------
    def usable(identifier: str):
        """(kept_count, all_durations_present, tag_fraction) or None."""
        try:
            files = ia.metadata(identifier).get("files", [])
        except IAError:
            return None
        kept, _e, _o = filter_files(files, want_format=want)
        if not kept:
            return None
        durs = [length_seconds(f.get("length")) for f in kept]
        ok = all(isinstance(d, (int, float)) and d > 0 for d in durs)
        return len(kept), ok, title_fraction(clean_tag_titles(kept))

    oracle, short = set(), set()
    for key in sorted(docs_by_key):
        for cand in group_candidates(key, docs_by_key[key],
                                     jerrybase_enabled=True):
            idents = [r.identifier for r in cand.recordings]
            if len(idents) < 2:
                continue
            info = {i: usable(i) for i in idents}
            for me in idents:
                mine = info[me]
                if mine is None or not mine[1] or mine[2] < WELL_TAGGED:
                    continue
                donors = [o for o in idents if o != me
                          and info[o] is not None and info[o][1]]
                if not donors:
                    continue
                (short if mine[0] < MIN_TRACKS else oracle).add(me)

    measured = {e["target"] for e in read_cache(cache_path)}
    missing = oracle - measured
    extra = measured - oracle
    print(f"oracle targets (>= {MIN_TRACKS} tracks): {len(oracle)}; "
          f"oracle targets under {MIN_TRACKS} tracks: {len(short)}; "
          f"measured: {len(measured)}")
    print(f"  in oracle, not measured: {len(missing)} {sorted(missing)[:5]}")
    print(f"  measured, not in oracle: {len(extra)} {sorted(extra)[:5]}")
    ok = not missing and not extra
    print(f"ORACLE: -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def slide_rank(cache_path: Path) -> int:
    """Step 9's 135-outranked / 1-survivor split, computed by the COMMITTED
    script instead of an ad-hoc one, from the alignment cache.

    For every localised-slide pair (`_localised_slide` over the fully-tagged
    tracks -- no mask), ask whether that donor is the one `gather.best_donor`
    would pick for its target: rate every donor of that target with the
    shipped `rate_alignment` and rank with the shipped `_donor_key`.

    THE FRAMING, corrected after review: "the tie-break eliminated 135" and
    "135 of the slide pairs are multi-donor" are THE SAME OBSERVATION. The
    tie-break does not filter a failure class; it selects among donors, and
    where a better donor exists the slide pair simply is not the one used.
    A single-donor target has no tie-break at all.
    """
    slides, wins, loses = [], [], []
    per_show: Counter = Counter()
    n_pairs = n_auto = 0
    for e in read_cache(cache_path):
        tracks = make_tracks(e["names"], e["durations"], e["titles"], hidden=set())
        rated = []
        for pair in e["pairs"]:
            rows = [_row_of(j) for j in pair["rows"]]
            res = rate_alignment(rows, tracks)
            rated.append((pair, rows, res))
            n_pairs += 1
            if res.agreement is not None and res.agreement >= AUTO:
                n_auto += 1
        if not rated:
            continue
        best = min(rated, key=lambda c: _donor_key(
            c[2].agreement, c[0]["cost"], c[0]["donor"]))[0]["donor"]
        n_donors = len(rated)
        for pair, rows, res in rated:
            if res.agreement is None or res.agreement < AUTO:
                continue
            runs = _localised_slide(rows, e["titles"], res)
            if not runs:
                continue
            rec = {"target": e["target"], "donor": pair["donor"],
                   "agreement": res.agreement, "runs": runs,
                   "donors_for_target": n_donors,
                   "is_winner": pair["donor"] == best}
            slides.append(rec)
            per_show[_show_key(e["target"])] += 1
            (wins if rec["is_winner"] else loses).append(rec)
    print(json.dumps({
        "pairs": n_pairs, "auto_band_pairs": n_auto,
        "localised_slides": len(slides),
        "distinct_targets": len({s["target"] for s in slides}),
        "slide_donor_is_the_agreement_winner": len(wins),
        "outranked_by_a_cleaner_donor": len(loses),
        "winners_with_exactly_one_donor": sum(
            1 for s in wins if s["donors_for_target"] == 1),
        "slide_pairs_by_performance(date key)": dict(per_show.most_common()),
        "winners": wins,
    }, indent=2))
    return 0


_DATE4 = __import__("re").compile(r"((?:19|20)\d{2})-?(\d{2})-?(\d{2})")
_DATE2 = __import__("re").compile(r"(?<![0-9])(\d{2})-(\d{2})-(\d{2})(?![0-9])")


def _show_key(identifier: str) -> str:
    """A performance key for grouping the slide census.

    Presentational only -- it groups a table and never enters a rate. It has
    to cope with BOTH archive.org date conventions on one corpus
    (`gd1973-02-15...` and `gd73-02-15...` are the same night), because
    keying them apart is what made an earlier draft's per-show counts
    reconcile under no grouping at all.
    """
    mo = _DATE4.search(identifier)
    if mo:
        y, m, d = mo.group(1), mo.group(2), mo.group(3)
    else:
        mo = _DATE2.search(identifier)
        if not mo:
            return identifier
        y, m, d = "19" + mo.group(1), mo.group(2), mo.group(3)
    return f"{identifier[:mo.start()].lower().rstrip('.-')}{y}-{m}-{d}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--format", default="mp3", choices=sorted(FORMAT_BY_AUDIO))
    ap.add_argument("--build-cache", type=Path)
    ap.add_argument("--score", type=Path)
    ap.add_argument("--dump", type=Path)
    ap.add_argument("--slide-scan", action="store_true")
    ap.add_argument("--reconcile", type=Path)
    ap.add_argument("--reconcile-n", type=int, default=25)
    ap.add_argument("--plant", action="store_true",
                    help="--reconcile only: corrupt the cached rows, "
                         "so a working check MUST report mismatches")
    ap.add_argument("--selftest", type=Path)
    ap.add_argument("--triage", type=Path)
    ap.add_argument("--triage-sample", type=int, default=8)
    ap.add_argument("--truths", type=Path,
                    help="alignment cache, for --triage's full truth vectors")
    ap.add_argument("--row-census", type=Path)
    ap.add_argument("--schema", type=Path)
    ap.add_argument("--oracle", type=Path)
    ap.add_argument("--slide-rank", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--progress", type=int, default=25)
    args = ap.parse_args()
    ia = CacheIA(args.cache)
    if args.build_cache:
        return build_cache(ia, args.build_cache, args.format, args.limit,
                           args.progress)
    if args.score:
        return run_score(args.score, args.dump, args.progress)
    if args.slide_scan:
        return slide_scan(ia, args.format, args.progress)
    if args.reconcile:
        return reconcile(ia, args.reconcile, args.format,
                         args.reconcile_n, plant=args.plant)
    if args.selftest:
        return _selftest(args.selftest, args.limit)
    if args.triage:
        if not args.truths:
            ap.error("--triage needs --truths <alignment cache>")
        return run_triage(args.triage, args.truths, args.triage_sample)
    if args.row_census:
        return row_census(args.row_census)
    if args.schema:
        return check_schema(args.schema, args.dump)
    if args.oracle:
        return population_oracle(ia, args.oracle, args.format)
    if args.slide_rank:
        return slide_rank(args.slide_rank)
    ap.error("pick a mode")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
