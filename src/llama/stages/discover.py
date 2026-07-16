import logging
from pathlib import Path

from llama.artist_index import filter_artists, find_matching_artists, load_or_build
from llama.models import Criteria
from llama.workspace import RunWorkspace, read_json, should_run, write_artifact

log = logging.getLogger("llama")


def _compose_query(criteria: Criteria) -> str:
    # criteria.query is always the verbatim request; appending interpret's
    # soft_preferences paraphrase of the same request added nothing and
    # diluted exclusions ("not blues-rock" doesn't survive paraphrase).
    # Only the era bounds are structured signal worth adding.
    parts = [criteria.query]
    if criteria.date_from or criteria.date_to:
        parts.append(f"Era: {criteria.date_from or 'any'} to {criteria.date_to or 'any'}")
    return "\n".join(parts)


def run_discover(
    ws: RunWorkspace,
    provider,
    ia,
    criteria: Criteria,
    *,
    cache_dir: Path,
    min_recordings: int = 25,
    min_downloads: int = 50000,
    max_artists: int = 10,
    force: bool = False,
) -> list[dict]:
    if not should_run(ws.artists, force):
        return read_json(ws.artists)
    pool = filter_artists(load_or_build(ia, cache_dir), min_recordings, min_downloads)
    matched = find_matching_artists(provider, pool, _compose_query(criteria),
                                    max_results=max_artists)
    result = [{"identifier": a["identifier"], "title": a["title"]} for a in matched]
    log.info("discover: %d artists matched on the LMA", len(result))
    write_artifact(ws.artists, result)
    return result
