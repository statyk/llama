import logging
from collections import Counter

from llama import ts_rules
from llama.config import TaperssectionArtist
from llama.grouping import _first, _summary, group_candidates
from llama.models import Candidate, Criteria
from llama.status import detail, step
from llama.taperssection import Allowlist, is_synthetic
from llama.ts_measure import parse_title_venue
from llama.workspace import RunWorkspace, read_model_list, should_run, write_artifact

log = logging.getLogger("llama")

SEARCH_FIELDS = [
    "identifier", "title", "date", "venue", "coverage",
    "avg_rating", "num_reviews", "downloads", "description",
]
# Extra scrape fields for Taper's Section (synthetic `ts-` keys) only. Task 0
# measured `lineage` as served for ~0% of items; it is requested anyway so a
# doc that carries it fills `RecordingSummary.lineage` (no per-item metadata
# fetch). `description` is already in SEARCH_FIELDS.
TS_EXTRA_FIELDS = ["creator", "addeddate", "source", "lineage"]


def _date_clause(criteria: Criteria) -> str | None:
    if criteria.date_from or criteria.date_to:
        lo = criteria.date_from or "1900-01-01"
        hi = criteria.date_to or "2100-01-01"
        return f"date:[{lo} TO {hi}]"
    return None


def _ts_query(entry: TaperssectionArtist, criteria: Criteria) -> str:
    creators = " OR ".join(f'"{c}"' for c in entry.creators)
    parts = ["collection:taperssection", "mediatype:audio", f"creator:({creators})"]
    clause = _date_clause(criteria)
    if clause:
        parts.append(clause)
    return " AND ".join(parts)


def build_query(criteria: Criteria, allowlist: Allowlist | None = None) -> str:
    """Hard filters only — the wide net. Quality thresholds are enforced in winnow.

    A synthetic `ts-` collection queries Taper's Section by the entry's
    creators (a prefilter only: `ts_filter_docs` keeps exact creators); it
    raises `LlamaError` without an allowlist or for an unknown key. Every other
    input returns today's string exactly."""
    if criteria.collection:
        entry = Allowlist.for_candidate(allowlist, criteria.collection)
        if entry is not None:
            return _ts_query(entry, criteria)
    parts = ["mediatype:etree"]
    if criteria.collection:
        parts.append(f"collection:{criteria.collection}")
    elif criteria.artist:
        parts.append(f'creator:"{criteria.artist}"')
    clause = _date_clause(criteria)
    if clause:
        parts.append(clause)
    return " AND ".join(parts)


def ts_filter_docs(docs: list[dict], entry: TaperssectionArtist, *, rule) -> list[dict]:
    """The Taper's Section policy pre-filter, before grouping.

    Keeps a doc only when its creator is exactly one of the entry's creators
    (normalized), its date is in the entry's active window, the date it claims
    in identifier/title agrees with `date` (a doc with no date that claims one
    is dropped), it is not `excluded`, and its lineage is not forbidden. Each
    test reads the same `RecordingSummary` grouping stores, so a later
    `classify` of the stored candidate gives the filter-time answer."""
    matcher = Allowlist([entry])
    kept: list[dict] = []
    for doc in docs:
        if not matcher.match_creator(doc.get("creator"), entry):
            continue
        date = str(_first(doc.get("date")) or "")[:10]
        if date and not ts_rules.in_active_window(date, entry):
            continue
        rec = _summary(doc, date)
        if ts_rules.date_disagrees(rec):
            claimed = sorted(ts_rules.dates_claimed(rec.identifier, rec.title))
            log.info("search: %s dropped: date %s disagrees with %s in identifier/title",
                     rec.identifier, date or "(none)", ", ".join(claimed))
            continue
        if not date:
            continue  # grouping would drop it too
        if ts_rules.excluded(rec, entry):
            continue
        if ts_rules.allowed(rec, entry, rule=rule) == "forbidden":
            continue
        kept.append(doc)
    return kept


def _search_one(ia, collection: str, criteria: Criteria, allowlist: Allowlist | None,
                jerrybase_enabled: bool) -> list[Candidate]:
    """One collection's candidates. A `ts-` key scrapes Taper's Section with
    the extra fields and the policy filter; an LMA key runs exactly as before."""
    entry = Allowlist.for_candidate(allowlist, collection)
    scoped = criteria.model_copy(update={"collection": collection})
    if entry is None:
        docs = ia.scrape(build_query(scoped), SEARCH_FIELDS)
        return group_candidates(collection, docs, jerrybase_enabled=jerrybase_enabled)
    docs = ia.scrape(build_query(scoped, allowlist), SEARCH_FIELDS + TS_EXTRA_FIELDS)
    docs = ts_filter_docs(docs, entry, rule=ts_rules.RULE)
    # Filtering precedes grouping, so a date whose every recording was dropped
    # never becomes a candidate.
    return [c.model_copy(update={"ts_title_venue": title_venue(c)})
            for c in group_candidates(collection, docs, jerrybase_enabled=jerrybase_enabled,
                                      allowlist=allowlist)
            if c.recordings]


def title_venue(candidate: Candidate) -> tuple[str | None, str | None] | None:
    """The most common (venue, city) parsed from a ts candidate's recording titles
    (`parse_title_venue`), or None when no title names a venue. Ties go to the
    parse met first, in recording order. Gather's last-resort venue only: it is never
    written into a recording's `venue`/`coverage`."""
    parses = [p for r in candidate.recordings
              if (p := parse_title_venue(r.title))[0]]
    if not parses:
        return None
    return Counter(parses).most_common(1)[0][0]


def run_search(
    ws: RunWorkspace, ia, criteria: Criteria,
    artists: list[dict] | None = None,
    force: bool = False,
    jerrybase_enabled: bool = True,
    allowlist: Allowlist | None = None,
) -> list[Candidate]:
    """Wide net means ALL matching recordings: the cursor-paginated scrape API,
    not a single capped page - every recording of a performance feeds structure
    recovery and recording selection downstream."""
    if not should_run(ws.candidates, force):
        return read_model_list(ws.candidates, Candidate)
    if artists:
        # Fail closed before any scrape: every ts- key must resolve.
        for artist in artists:
            Allowlist.for_candidate(allowlist, artist["identifier"])
        candidates: list[Candidate] = []
        with step(f"searching the LMA ({len(artists)} artists)"):
            for i, artist in enumerate(artists, 1):
                detail(f"{artist.get('title') or artist['identifier']} ({i}/{len(artists)})")
                candidates.extend(_search_one(ia, artist["identifier"], criteria, allowlist,
                                              jerrybase_enabled))
        candidates.sort(key=lambda c: (c.date, c.performance_id))
    elif criteria.collection and is_synthetic(criteria.collection):
        Allowlist.for_candidate(allowlist, criteria.collection)
        with step("searching Taper's Section"):
            candidates = _search_one(ia, criteria.collection, criteria, allowlist,
                                     jerrybase_enabled)
    else:
        with step("searching the LMA"):
            docs = ia.scrape(build_query(criteria), SEARCH_FIELDS)
        label = criteria.collection or criteria.artist or "unknown"
        candidates = group_candidates(label, docs, jerrybase_enabled=jerrybase_enabled)
    write_artifact(ws.candidates, candidates)
    return candidates
