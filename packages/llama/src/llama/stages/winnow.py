import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from herder import run_json_task, run_research_task
from llama import jerrybase
from llama.artist_index import load_ts_index, ts_items
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.models import Candidate, Criteria, QualityBatch, ShortlistEntry
from llama.prompts import load_prompt
from llama.songs import GD_SHORTHAND
from llama.status import detail, step
from llama.structure import contains_sequence
from llama.taperssection import Allowlist, is_synthetic
from llama.ts_measure import catalogue_rates, percentile, show_rate
from llama.util import cap_across_artists
from llama.workspace import RunWorkspace, read_model_list, should_run, write_artifact

log = logging.getLogger("llama")

# Without download evidence (every recording under ts_measure's 75-day lag) a
# Taper's Section show starts below the default min_quality_score (6.0), so it
# waits for its counters to catch up rather than ship on a zero count.
TS_NO_EVIDENCE_BASELINE = 4
TS_DESCRIPTION_CHARS = 600

# Rendered into score_reviews.md's {{ts_block}} for a Taper's Section batch
# only; an LMA batch renders "" there, so its prompt is byte-identical to the
# pre-taperssection template (golden: tests/fixtures/golden/score_reviews_pre_ts.txt).
TS_PROMPT_BLOCK = f"""

These shows come from archive.org's Taper's Section, not the Live Music Archive,
and most have few or no listener reviews. Each carries "download_percentile": where
the show's age-adjusted download rate (its best recording's downloads per day since
upload) ranks within this artist's whole Taper's Section catalogue, 0-100. Most
downloaders were not at the show, so treat it as non-attendee evidence. With no
reviews, the baseline quality_score is download_percentile / 10 (85 -> 8.5). When
"download_percentile" is null the show has no download evidence yet (its recordings
are too new for archive.org's counter): the baseline is {TS_NO_EVIDENCE_BASELINE}. Reviews, where
present, adjust the baseline up or down, judged as above.

Each show also lists its "recordings" (uploader's creator, title and the start of
the description). Uploader details cannot be trusted. Reading every recording,
decide whether the show really is the named artist, or a tribute act, a cover band,
another performer or otherwise mislabelled. If any recording looks like a different
act, the show is suspect. Add two fields to each assessment:
   "attribution": "ok" or "suspect",
   "attribution_reason": "<one line naming why it is suspect, or null when ok>"
""".rstrip()


def _best_recording(c: Candidate):
    return max(c.recordings, key=lambda r: (r.num_reviews, r.avg_rating or 0.0))


def _evidence(c: Candidate):
    return (sum(r.num_reviews for r in c.recordings),
            max((r.avg_rating or 0.0) for r in c.recordings))


def _is_ts(c: Candidate) -> bool:
    """A Taper's Section candidate (synthetic `ts-` collection key)."""
    return is_synthetic(c.collection)


def _ts_evidence(c: Candidate, rates: dict[str, float | None]) -> tuple:
    """Sort key for a ts candidate: reviews where present, then its show rate
    (-1 when it has no download evidence)."""
    r = rates.get(c.performance_id)
    return (sum(rec.num_reviews for rec in c.recordings), -1 if r is None else r)


def split_sample(lma: list, ts: list, budget: int) -> tuple[list, list]:
    """Split a fetch budget between the (pre-sorted) LMA and ts survivors in
    proportion to their counts; at least one each when both are non-empty and
    the budget is at least 2."""
    total = len(lma) + len(ts)
    if total <= budget:
        return list(lma), list(ts)
    n_ts = round(budget * len(ts) / total)
    if lma and ts and budget >= 2:
        n_ts = min(max(n_ts, 1), budget - 1)
    n_ts = min(n_ts, len(ts))
    n_lma = min(budget - n_ts, len(lma))
    return list(lma[:n_lma]), list(ts[:n_ts])


def _ts_rates(ia, cache_dir: Path | None, allowlist: Allowlist | None,
              ts_cands: list[Candidate], today: date) -> tuple[dict, dict]:
    """(show rate, download percentile) per ts performance_id, against each
    artist's whole taperssection catalogue from the index store. A failed store
    build raises LlamaError naming the cause: ts shows are never scored without
    rates, and never silently dropped (orchestrator ruling R20)."""
    if cache_dir is None:
        raise LlamaError("winnow: taperssection candidates need a cache_dir for the "
                         "taperssection index")
    try:
        index = load_ts_index(ia, cache_dir, allowlist)
    except LlamaError as exc:  # IAError included (it subclasses LlamaError)
        raise LlamaError(f"winnow: cannot score taperssection shows: {exc}") from exc
    rates: dict[str, float | None] = {}
    pct: dict[str, float | None] = {}
    populations: dict[str, list[float]] = {}
    for c in ts_cands:
        store = ts_items(index, c.collection)
        if c.collection not in populations:
            populations[c.collection] = catalogue_rates(store, today)
        items = store.get(c.date) or [
            {"downloads": r.downloads, "addeddate": r.addeddate} for r in c.recordings]
        r = show_rate(items, today)
        rates[c.performance_id] = r
        pct[c.performance_id] = (None if r is None
                                 else percentile(r, populations[c.collection]))
    return rates, pct


def _has_songs(c: Candidate, criteria: Criteria, *, allowlist: Allowlist | None = None) -> bool:
    """Whether this performance satisfies every setlist constraint.

    Matched against EVERY recording's description, not just the longest: the
    constraint is a property of the performance, and any taper who names the
    song is evidence it was played. On the 1984 GD corpus that is the difference
    between 26 and 27 of the 27 shows that actually played "My Brother Esau".

    Deliberately no parse and no confidence gate. The old implementation parsed
    the description and compared parsed items for equality, which found 0 of
    those 27 — descriptions run songs together with no separator, so the parser
    drops the merged blob while still reporting `confidence="high"`. See
    `structure.contains_sequence`.
    """
    family = jerrybase.is_family_artist(
        jerrybase.jerrybase_artist(c.collection, c.collection, allowlist))
    aliases = GD_SHORTHAND if family else {}
    descs = [r.description or "" for r in c.recordings]
    return all(
        any(contains_sequence(d, sc.sequence, aliases) for d in descs)
        for sc in criteria.setlist_constraints
    )


def build_payload_entry(c: Candidate, best, md: dict,
                        ts_pct: dict[str, float | None]) -> dict:
    """One show's scorer payload entry (reviews from `md`, the best recording's
    metadata). A ts show also carries its download percentile and recordings."""
    entry = {
        "performance_id": c.performance_id,
        "date": c.date,
        "venue": c.venue,
        "avg_rating": best.avg_rating,
        "num_reviews": best.num_reviews,
        "reviews": [
            {"title": r.get("reviewtitle"), "stars": r.get("stars"),
             "body": str(r.get("reviewbody") or "")[:1500]}
            for r in md.get("reviews", [])[:10]
        ],
    }
    if _is_ts(c):
        entry["download_percentile"] = ts_pct.get(c.performance_id)
        entry["recordings"] = [
            {"identifier": r.identifier, "creator": r.creator, "title": r.title,
             "description": (r.description or "")[:TS_DESCRIPTION_CHARS]}
            for r in c.recordings
        ]
    return entry


def score_batch(score_provider, batch: list[dict], ts_block: str,
                soft_preferences: str | None) -> QualityBatch:
    """One scorer call over a payload batch (`ts_block` is TS_PROMPT_BLOCK for a
    Taper's Section batch, "" for an LMA batch)."""
    return run_json_task(score_provider, "score_reviews", QualityBatch,
                         template=load_prompt("score_reviews"),
                         candidates_json=json.dumps(batch, indent=2),
                         soft_preferences=soft_preferences or "(none)",
                         ts_block=ts_block)


def _passes_mechanical(c: Candidate, criteria: Criteria, *,
                       allowlist: Allowlist | None = None) -> bool:
    if not _is_ts(c):  # Taper's Section shows skip the review/rating floor
        best_rating = max((r.avg_rating or 0.0) for r in c.recordings)
        total_reviews = sum(r.num_reviews for r in c.recordings)
        if best_rating < criteria.min_avg_rating or total_reviews < criteria.min_reviews:
            return False
    return _has_songs(c, criteria, allowlist=allowlist)


def run_winnow(
    ws: RunWorkspace,
    score_provider,
    research_provider,
    ia,
    criteria: Criteria,
    ledger: Ledger,
    *,
    library_ids: set[str] | None = None,
    shortlist_size: int = 12,
    batch_size: int = 5,
    max_metadata_fetch: int = 40,
    force: bool = False,
    cache_dir: Path | None = None,
    allowlist: Allowlist | None = None,
    today: date | None = None,
) -> list[ShortlistEntry]:
    if not should_run(ws.shortlist, force):
        return read_model_list(ws.shortlist, ShortlistEntry)

    candidates = read_model_list(ws.candidates, Candidate)
    seen = (library_ids or set()) | ledger.played_ids() | ledger.rejected_ids()
    pool = [c for c in candidates if c.performance_id not in seen]
    # Fail closed: every ts candidate needs its allowlist entry.
    entries_by_key = {c.collection: Allowlist.for_candidate(allowlist, c.collection)
                      for c in pool if _is_ts(c)}
    survivors = [c for c in pool if _passes_mechanical(c, criteria, allowlist=allowlist)]
    ts_survivors = [c for c in survivors if _is_ts(c)]
    today = today or datetime.now(timezone.utc).date()
    ts_rate: dict[str, float | None] = {}
    ts_pct: dict[str, float | None] = {}
    if ts_survivors:  # R20: an LMA-only run never touches the ts index
        ts_rate, ts_pct = _ts_rates(ia, cache_dir, allowlist, ts_survivors, today)
    log.info("winnow: %d candidates -> %d after library+ledger -> %d after mechanical",
             len(candidates), len(pool), len(survivors))
    if len(survivors) > max_metadata_fetch:
        log.warning("winnow: sampling %d of %d survivors for review fetch - "
                    "best evidence first, bounded by artist_cap/year_cap "
                    "(raise [winnow] max_metadata_fetch to widen)",
                    max_metadata_fetch, len(survivors))
        lma_pref = sorted([c for c in survivors if not _is_ts(c)], key=_evidence,
                          reverse=True)
        ts_pref = sorted(ts_survivors, key=lambda c: _ts_evidence(c, ts_rate),
                         reverse=True)
        lma_share, ts_share = split_sample(lma_pref, ts_pref, max_metadata_fetch)
        keep = set()
        for prefer, n in ((lma_pref, len(lma_share)), (ts_pref, len(ts_share))):
            if n:
                keep |= {c.performance_id
                         for c in cap_across_artists(prefer, lambda c: c.collection,
                                                     lambda c: c.date, n,
                                                     criteria.artist_cap, criteria.year_cap)}
        survivors = [c for c in survivors if c.performance_id in keep]

    payload = []
    ts_payload = []
    reviewed: dict[str, str] = {}
    with step(f"winnow: fetching reviews ({len(survivors)} shows)"):
        for i, c in enumerate(survivors, 1):
            best = _best_recording(c)
            detail(f"{i}/{len(survivors)}: {best.identifier}")
            md = ia.metadata(best.identifier)
            reviewed[c.performance_id] = best.identifier
            entry = build_payload_entry(c, best, md, ts_pct)
            if _is_ts(c):
                ts_payload.append(entry)
            else:
                payload.append(entry)

    assessments = {}
    # LMA payloads batch exactly as before; Taper's Section payloads batch on
    # their own, so an LMA batch's prompt and payload never change.
    batches = ([(payload[i : i + batch_size], "")
                for i in range(0, len(payload), batch_size)]
               + [(ts_payload[i : i + batch_size], TS_PROMPT_BLOCK)
                  for i in range(0, len(ts_payload), batch_size)])
    n_batches = len(batches)
    with step(f"winnow: scoring reviews ({n_batches} batches)"):
        for bi, (batch, ts_block) in enumerate(batches, 1):
            detail(f"batch {bi}/{n_batches}")
            result = score_batch(score_provider, batch, ts_block,
                                 criteria.soft_preferences)
            for a in result.assessments:
                a.reviewed_identifier = reviewed.get(a.performance_id, "")
                if a.performance_id not in ts_pct:
                    # attribution is a ts-only verdict; never recorded on LMA shows
                    a.attribution = None
                    a.attribution_reason = None
                assessments[a.performance_id] = a

    scored = [(c, assessments[c.performance_id]) for c in survivors
              if c.performance_id in assessments]
    # A query naming one date has already chosen the show: for ts shows only,
    # min_quality_score is not applied (the scorer still ran, for attribution).
    single_date = criteria.date_from is not None and criteria.date_from == criteria.date_to
    floored = [p for p in scored
               if p[1].quality_score >= criteria.min_quality_score
               or (single_date and _is_ts(p[0]))]
    if len(floored) < len(scored):
        log.warning("winnow: %d of %d scored shows fell below the quality floor "
                    "(%.1f) and were dropped - the pool may be thinning; adjust "
                    "min_quality_score or broaden the criteria",
                    len(scored) - len(floored), len(scored), criteria.min_quality_score)
    scored = floored
    scored.sort(key=lambda pair: (pair[1].quality_score, *_evidence(pair[0])),
                reverse=True)
    # Neither a hot year nor one deep catalog may monopolize the shortlist:
    # best score first, dominance bounded by the profile's artist_cap/year_cap.
    top = cap_across_artists(scored, lambda pair: pair[0].collection,
                             lambda pair: pair[0].date, shortlist_size,
                             criteria.artist_cap, criteria.year_cap)
    top.sort(key=lambda pair: (pair[1].quality_score, *_evidence(pair[0])),
             reverse=True)

    entries: list[ShortlistEntry] = []
    with step(f"winnow: researching shortlist ({len(top)} shows)"):
        for rank, (c, a) in enumerate(top, 1):
            detail(f"{c.performance_id} ({rank}/{len(top)})")
            ts_entry = entries_by_key.get(c.collection)
            rep = run_research_task(
                research_provider, "light_research", template=load_prompt("light_research"),
                artist=(ts_entry.name if ts_entry is not None
                        else criteria.artist or criteria.collection or c.collection),
                date=c.date, venue=c.venue or "unknown venue",
            )
            entries.append(ShortlistEntry(candidate=c, assessment=a,
                                          external_reputation=rep, rank=rank))
    write_artifact(ws.shortlist, entries)
    return entries
