import logging

from llama.grouping import group_candidates
from llama.models import Candidate, Criteria
from llama.workspace import RunWorkspace, read_model_list, should_run, write_artifact

log = logging.getLogger("llama")

SEARCH_FIELDS = [
    "identifier", "title", "date", "venue", "coverage",
    "avg_rating", "num_reviews", "description",
]


def build_query(criteria: Criteria) -> str:
    """Hard filters only — the wide net. Quality thresholds are enforced in winnow."""
    parts = ["mediatype:etree"]
    if criteria.collection:
        parts.append(f"collection:{criteria.collection}")
    elif criteria.artist:
        parts.append(f'creator:"{criteria.artist}"')
    if criteria.date_from or criteria.date_to:
        lo = criteria.date_from or "1900-01-01"
        hi = criteria.date_to or "2100-01-01"
        parts.append(f"date:[{lo} TO {hi}]")
    return " AND ".join(parts)


def run_search(
    ws: RunWorkspace, ia, criteria: Criteria,
    artists: list[dict] | None = None,
    rows: int = 500, force: bool = False,
) -> list[Candidate]:
    if not should_run(ws.candidates, force):
        return read_model_list(ws.candidates, Candidate)
    if artists:
        candidates: list[Candidate] = []
        for i, artist in enumerate(artists, 1):
            log.info("search: %s (%d/%d)", artist.get("title") or artist["identifier"],
                     i, len(artists))
            fanned = criteria.model_copy(update={"collection": artist["identifier"]})
            docs = ia.search(build_query(fanned), SEARCH_FIELDS, rows=rows)
            candidates.extend(group_candidates(artist["identifier"], docs))
        candidates.sort(key=lambda c: (c.date, c.performance_id))
    else:
        docs = ia.search(build_query(criteria), SEARCH_FIELDS, rows=rows)
        label = criteria.collection or criteria.artist or "unknown"
        candidates = group_candidates(label, docs)
    write_artifact(ws.candidates, candidates)
    return candidates
