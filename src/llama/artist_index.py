"""Local index of LMA artist collections with stats, built from the scrape API.

Two passes: one request for all ~9.3k artist collections (identifier, title,
downloads), then ~30 cursor pages over all ~292k items aggregated into
per-artist recording counts and year coverage. The aggregated JSON file is
the cache; raw pages are never persisted.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llama.ia_client import IAError
from llama.llm.tasks import run_json_task
from llama.models import ArtistMatches
from llama.workspace import write_artifact

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


INDEX_FILENAME = "artist_index.json"


def load_or_build(
    ia,
    cache_dir: Path,
    *,
    ttl_days: int = 30,
    refresh: bool = False,
    now: datetime | None = None,
) -> list[dict]:
    """The artists list from the cached index, rebuilding when missing or
    older than ttl_days. A failed rebuild falls back to a stale file (with a
    warning) rather than dying; with no file at all, the IAError propagates."""
    path = cache_dir / INDEX_FILENAME
    now = now or datetime.now(timezone.utc)
    if path.exists() and not refresh:
        data = json.loads(path.read_text())
        if now - datetime.fromisoformat(data["built_at"]) < timedelta(days=ttl_days):
            return data["artists"]
    try:
        data = build_index(ia)
    except IAError as exc:
        if path.exists():
            data = json.loads(path.read_text())
            log.warning("artist index rebuild failed (%s); using stale index from %s",
                        exc, data["built_at"])
            return data["artists"]
        raise
    write_artifact(path, json.dumps(data, indent=2))
    return data["artists"]


def filter_artists(artists: list[dict], min_recordings: int, min_downloads: int) -> list[dict]:
    """The backyard-band gate: enough recordings OR enough downloads."""
    return [a for a in artists
            if a["recordings"] >= min_recordings or a["downloads"] >= min_downloads]


def fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def render_artist_table(artists: list[dict]) -> str:
    lines = []
    for a in artists:
        years = (f"{a['year_min']}-{a['year_max']}"
                 if a.get("year_min") is not None else "?")
        lines.append(f"{a['identifier']} | {a['title']} | {a['recordings']} recordings"
                     f" | {years} | {fmt_count(a['downloads'])} downloads")
    return "\n".join(lines)


def find_matching_artists(provider, artists: list[dict], query: str, max_results: int) -> list[dict]:
    """One inventory-in-context LLM call; identifiers joined back against the
    filtered index, so a hallucinated identifier can never reach the caller."""
    result = run_json_task(
        provider, "find_artists", ArtistMatches,
        query=query, max_results=max_results,
        artist_table=render_artist_table(artists),
    )
    by_id = {a["identifier"]: a for a in artists}
    out: list[dict] = []
    for m in result.matches:
        a = by_id.get(m.identifier)
        if a is None:
            log.warning("find_artists: dropping unknown identifier %r", m.identifier)
            continue
        out.append({**a, "reason": m.reason})
        if len(out) >= max_results:
            break
    return out
