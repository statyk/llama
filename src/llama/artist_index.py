"""Local index of LMA artist collections with stats, built from the scrape API.

Two passes: one request for all ~9.3k artist collections (identifier, title,
downloads), then ~30 cursor pages over all ~292k items aggregated into
per-artist recording counts and year coverage. The aggregated JSON file is
the cache; raw pages are never persisted.
"""

import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("llama")

COLLECTIONS_QUERY = "collection:etree AND mediatype:collection"
ITEMS_QUERY = "collection:etree AND mediatype:etree"

_YEAR = re.compile(r"(\d{4})")


def _parse_year(val) -> int | None:
    if isinstance(val, list):
        val = val[0] if val else None
    if val is None:
        return None
    m = _YEAR.match(str(val).strip())
    if not m:
        return None
    year = int(m.group(1))
    return year if 1900 <= year <= 2100 else None


def build_index(ia) -> dict:
    log.info("building artist index: ~30 requests, about a minute")
    stats: dict[str, dict] = {}
    for c in ia.scrape(COLLECTIONS_QUERY, ["identifier", "title", "downloads"]):
        ident = c.get("identifier")
        if not ident:
            continue
        stats[ident] = {
            "identifier": ident,
            "title": str(c.get("title") or ident),
            "downloads": int(c.get("downloads") or 0),
            "recordings": 0,
            "year_min": None,
            "year_max": None,
        }
    for item in ia.scrape(ITEMS_QUERY, ["identifier", "collection", "year"]):
        cols = item.get("collection") or []
        if isinstance(cols, str):
            cols = [cols]
        year = _parse_year(item.get("year"))
        for col in cols:
            s = stats.get(col)
            if s is None:
                continue  # etree, stream_only, and other non-artist parents
            s["recordings"] += 1
            if year is not None:
                s["year_min"] = year if s["year_min"] is None else min(s["year_min"], year)
                s["year_max"] = year if s["year_max"] is None else max(s["year_max"], year)
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "artists": sorted(stats.values(), key=lambda s: s["identifier"]),
    }
