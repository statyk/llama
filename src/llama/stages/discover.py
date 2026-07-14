import logging
import re

from llama.llm.tasks import run_json_task
from llama.models import Criteria, ProposedArtists
from llama.workspace import RunWorkspace, read_json, should_run, write_artifact

log = logging.getLogger("llama")

COLLECTIONS_QUERY = "collection:etree AND mediatype:collection"

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def _norm(name: str) -> str:
    s = _PUNCT.sub(" ", name.lower().replace("'", ""))
    return _WS.sub(" ", s).strip()


def match_artists(proposed: list[str], collections: list[dict], max_artists: int = 10) -> list[dict]:
    """One best collection per proposed name: normalized equality beats containment,
    first-listed collection wins ties; LLM order preserved; deduped; capped.

    Containment is word-set based (every word of the shorter name appears in the
    longer one), not literal substring — e.g. "Doc Watson" must match "Doc and
    Merle Watson" even though "and Merle" splits the words apart.
    """
    normed = [(c, _norm(str(c.get("title") or ""))) for c in collections if c.get("identifier")]
    out: list[dict] = []
    seen: set[str] = set()
    for name in proposed:
        n = _norm(name)
        if not n:
            continue
        n_words = set(n.split())
        best = None
        for c, ct in normed:
            if not ct:
                continue
            if ct == n:
                best = c
                break
            if best is None:
                ct_words = set(ct.split())
                if n_words <= ct_words or ct_words <= n_words:
                    best = c
        if best and best["identifier"] not in seen:
            seen.add(best["identifier"])
            out.append({"identifier": best["identifier"], "title": str(best.get("title") or "")})
        if len(out) >= max_artists:
            break
    return out


def run_discover(
    ws: RunWorkspace,
    provider,
    ia,
    criteria: Criteria,
    *,
    max_artists: int = 10,
    force: bool = False,
) -> list[dict]:
    if not should_run(ws.artists, force):
        return read_json(ws.artists)
    collections = ia.search(COLLECTIONS_QUERY, ["identifier", "title"], rows=10000)
    result = run_json_task(
        provider, "propose_artists", ProposedArtists,
        query=criteria.query,
        soft_preferences=criteria.soft_preferences or "(none)",
        date_from=criteria.date_from or "any",
        date_to=criteria.date_to or "any",
    )
    matched = match_artists(result.artists, collections, max_artists=max_artists)
    log.info("discover: %d proposed -> %d found on LMA", len(result.artists), len(matched))
    write_artifact(ws.artists, matched)
    return matched
