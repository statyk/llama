import json
import logging

from llama.ledger import Ledger
from llama.llm.tasks import run_json_task, run_research_task
from llama.models import Candidate, Criteria, QualityBatch, ShortlistEntry
from llama.setlist import parse_setlist
from llama.songs import matches_sequence
from llama.workspace import RunWorkspace, read_model_list, should_run, write_artifact

log = logging.getLogger("llama")


def _best_recording(c: Candidate):
    return max(c.recordings, key=lambda r: (r.num_reviews, r.avg_rating or 0.0))


def _passes_mechanical(c: Candidate, criteria: Criteria) -> bool:
    best_rating = max((r.avg_rating or 0.0) for r in c.recordings)
    total_reviews = sum(r.num_reviews for r in c.recordings)
    if best_rating < criteria.min_avg_rating or total_reviews < criteria.min_reviews:
        return False
    if criteria.setlist_constraints:
        desc = max((r.description or "" for r in c.recordings), key=len)
        parsed = parse_setlist(desc)
        if parsed.confidence == "low":
            return False
        titles = [i.title for i in parsed.items]
        if not all(matches_sequence(titles, sc.sequence) for sc in criteria.setlist_constraints):
            return False
    return True


def run_winnow(
    ws: RunWorkspace,
    score_provider,
    research_provider,
    ia,
    criteria: Criteria,
    ledger: Ledger,
    *,
    shortlist_size: int = 12,
    batch_size: int = 5,
    max_metadata_fetch: int = 40,
    force: bool = False,
) -> list[ShortlistEntry]:
    if not should_run(ws.shortlist, force):
        return read_model_list(ws.shortlist, ShortlistEntry)

    candidates = read_model_list(ws.candidates, Candidate)
    seen = ledger.played_ids() | ledger.rejected_ids()
    pool = [c for c in candidates if c.performance_id not in seen]
    survivors = [c for c in pool if _passes_mechanical(c, criteria)]
    log.info("winnow: %d candidates -> %d after ledger -> %d after mechanical",
             len(candidates), len(pool), len(survivors))
    if len(survivors) > max_metadata_fetch:
        log.warning("winnow: truncating %d survivors to %d for review fetch (raise max_metadata_fetch to widen)",
                    len(survivors), max_metadata_fetch)
        survivors = survivors[:max_metadata_fetch]

    payload = []
    reviewed: dict[str, str] = {}
    for c in survivors:
        best = _best_recording(c)
        md = ia.metadata(best.identifier)
        reviewed[c.performance_id] = best.identifier
        payload.append({
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
        })

    assessments = {}
    for i in range(0, len(payload), batch_size):
        batch = payload[i : i + batch_size]
        result = run_json_task(score_provider, "score_reviews", QualityBatch,
                               candidates_json=json.dumps(batch, indent=2))
        for a in result.assessments:
            a.reviewed_identifier = reviewed.get(a.performance_id, "")
            assessments[a.performance_id] = a

    scored = [(c, assessments[c.performance_id]) for c in survivors
              if c.performance_id in assessments]
    scored.sort(key=lambda pair: pair[1].quality_score, reverse=True)
    top = scored[:shortlist_size]

    entries: list[ShortlistEntry] = []
    for rank, (c, a) in enumerate(top, 1):
        rep = run_research_task(
            research_provider, "light_research",
            artist=criteria.artist or criteria.collection or c.collection,
            date=c.date, venue=c.venue or "unknown venue",
        )
        entries.append(ShortlistEntry(candidate=c, assessment=a,
                                      external_reputation=rep, rank=rank))
    write_artifact(ws.shortlist, entries)
    return entries
