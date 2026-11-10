"""Local index of LMA artist collections with stats, built from the scrape API.

Two passes: one request for all ~9.3k artist collections (identifier, title,
downloads), then ~30 cursor pages over all ~292k items aggregated into
per-artist recording counts and year coverage. The aggregated JSON file is
the cache; raw pages are never persisted.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from herder import run_json_task
from llama.errors import ArtistResolutionError, LlamaError
from llama.ia_client import IAError
from llama.models import ArtistMatches
from llama.prompts import load_prompt
from llama.status import step
from llama.taperssection import KEY_PREFIX, Allowlist, norm_creator
from llama.util import slugify
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
    allowlist: Allowlist | None = None,
) -> list[dict]:
    """The artists list from the cached index, rebuilding when missing or
    older than ttl_days. A failed rebuild falls back to a stale file (with a
    warning) rather than dying; with no file at all, the IAError propagates.

    With a non-empty allowlist the Taper's Section rows (load_ts_index) are
    appended after the LMA rows, once no LMA identifier slugifies onto the
    synthetic key prefix. An empty or absent allowlist adds nothing and does
    no taperssection IO."""
    artists = _load_or_build_lma(ia, cache_dir, ttl_days=ttl_days, refresh=refresh, now=now)
    if not allowlist:
        return artists
    clashes = [a["identifier"] for a in artists
               if slugify(a["identifier"]).startswith(KEY_PREFIX)]
    if clashes:
        raise LlamaError(
            f"LMA collection(s) {', '.join(clashes)} slugify to the taperssection key "
            f"prefix {KEY_PREFIX!r}; taperssection keys could collide with them")
    try:
        ts = load_ts_index(ia, cache_dir, allowlist, refresh=refresh, now=now)
    except (LlamaError, IAError) as exc:
        # The LMA paths (discovery, `llama artists`, pinning an LMA artist) must
        # not die with the taperssection index: return the LMA rows alone and
        # say so loudly. load_ts_index itself stays fail-closed for its other callers.
        log.warning("taperssection index could not be built (%s); continuing with "
                    "LMA artists only, no Taper's Section artists this run", exc)
        return artists
    return artists + ts["artists"]


def _load_or_build_lma(
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
        try:
            data = json.loads(path.read_text())
            if now - datetime.fromisoformat(data["built_at"]) < timedelta(days=ttl_days):
                return data["artists"]
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # corrupt index: fall through to rebuild
    try:
        with step("building artist index (~30 requests, a minute or two)"):
            data = build_index(ia)
    except IAError as exc:
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, KeyError, ValueError):
                raise exc from None
            log.warning("artist index rebuild failed (%s); using stale index from %s",
                        exc, data["built_at"])
            return data["artists"]
        raise
    write_artifact(path, json.dumps(data, indent=2))
    return data["artists"]


# ---- Taper's Section (allowlisted artists) -----------------------------------

TS_INDEX_FILENAME = "taperssection_index.json"
TS_INDEX_TTL_DAYS = 7
TS_FIELDS = ["identifier", "creator", "date", "year", "downloads", "addeddate"]
# The scrape endpoint was measured (premises.md, 2026-11-09) answering
# {"total": 0} for valid queries and once serving another query's page, and
# IAClient.scrape returns [] silently on such a page. A response is accepted
# only when it is non-empty and at least TS_PAGE_MATCH_SHARE of its docs carry
# a creator containing one of the entry's spellings (the probe's check); a
# suspect response is retried TS_SCRAPE_ATTEMPTS times in all, TS_SCRAPE_RETRY_S
# apart, then the build raises rather than caching a catalogue missing an entry.
# IAClient.scrape's page size, passed explicitly: a result that is an exact
# multiple of it is a cursor walk a bad later page may have cut short
# (scrape drops `total`), so it is treated as suspect and retried.
TS_SCRAPE_PAGE = 10000
TS_SCRAPE_ATTEMPTS = 4
TS_SCRAPE_RETRY_S = 10.0
TS_PAGE_MATCH_SHARE = 0.8
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _creators(doc: dict) -> list[str]:
    c = doc.get("creator")
    vals = c if isinstance(c, list) else [c]
    return [v for v in vals if isinstance(v, str)]


def _ts_query(entry) -> str:
    spelled = " OR ".join('"' + c.replace('"', "") + '"' for c in entry.creators)
    return f"collection:taperssection AND mediatype:audio AND creator:({spelled})"


def _plausible(docs: list[dict], entry) -> bool:
    """Does this response look like an answer to this entry's query?"""
    if not docs:
        return False
    mine = [norm_creator(c) for c in entry.creators]
    hits = sum(1 for d in docs
               if any(m and m in norm_creator(v) for v in _creators(d) for m in mine))
    return hits >= TS_PAGE_MATCH_SHARE * len(docs)


def _scrape_entry(ia, allowlist: Allowlist, entry) -> list[dict]:
    """The exact-creator docs for one entry, from a validated response."""
    query = _ts_query(entry)
    for attempt in range(TS_SCRAPE_ATTEMPTS):
        if attempt:
            _sleep(TS_SCRAPE_RETRY_S)
        docs = ia.scrape(query, TS_FIELDS, count=TS_SCRAPE_PAGE)
        if docs and len(docs) % TS_SCRAPE_PAGE == 0:
            log.warning("taperssection scrape for %r stopped at exactly %d docs, a page "
                        "multiple (possibly truncated); retrying", entry.name, len(docs))
            continue
        if not _plausible(docs, entry):
            log.warning("taperssection scrape for %r looked wrong (%d docs); retrying",
                        entry.name, len(docs))
            continue
        exact = [d for d in docs if allowlist.match_creator(d.get("creator"), entry)]
        if exact:
            return exact
        log.warning("taperssection scrape for %r kept no exact-creator item; retrying",
                    entry.name)
    raise LlamaError(
        f"taperssection index: no usable archive.org answer for {entry.name!r} "
        f"(creators {entry.creators}) after {TS_SCRAPE_ATTEMPTS} attempts; the scrape "
        "endpoint may be flaky, or no taperssection item carries those creators exactly")


def build_ts_index(ia, allowlist: Allowlist) -> dict:
    """One row per allowlisted entry, shaped like an LMA row plus
    "allowlisted": True, and the raw per-item download store keyed by key and
    show date. Raises LlamaError naming the first entry no validated scrape
    answered, so a flaky endpoint never caches an index missing an entry."""
    artists: list[dict] = []
    items: dict[str, dict[str, list[dict]]] = {}
    for entry in allowlist.entries:
        key = allowlist.key(entry)
        seen: set[str] = set()
        row = {"identifier": key, "title": entry.name, "recordings": 0,
               "year_min": None, "year_max": None, "downloads": 0, "allowlisted": True}
        by_date: dict[str, list[dict]] = {}
        for d in _scrape_entry(ia, allowlist, entry):
            ident = d.get("identifier")
            if not ident or ident in seen:
                continue
            seen.add(ident)
            try:
                downloads = int(d.get("downloads") or 0)
            except (TypeError, ValueError):
                downloads = 0
            m = _DATE.match(str(d.get("date") or "").strip())
            date = m.group(1) if m else None
            year = _parse_year(d.get("year")) or (_parse_year(date) if date else None)
            row["recordings"] += 1
            row["downloads"] += downloads
            if year is not None:
                row["year_min"] = year if row["year_min"] is None else min(row["year_min"], year)
                row["year_max"] = year if row["year_max"] is None else max(row["year_max"], year)
            if date:
                by_date.setdefault(date, []).append(
                    {"identifier": ident, "downloads": downloads,
                     "addeddate": d.get("addeddate")})
        for recs in by_date.values():
            recs.sort(key=lambda r: r["identifier"])
        artists.append(row)
        items[key] = dict(sorted(by_date.items()))
    return {
        "allowlist": allowlist.fingerprint(),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "artists": sorted(artists, key=lambda a: a["identifier"]),
        "items": items,
    }


def load_ts_index(ia, cache_dir: Path, allowlist: Allowlist | None, *,
                  refresh: bool = False, now: datetime | None = None) -> dict:
    """The cached taperssection index, rebuilt when missing, corrupt, built
    for a different allowlist fingerprint, older than TS_INDEX_TTL_DAYS, or on
    refresh. An empty allowlist returns an empty index with no IO.

    A failed rebuild (LlamaError or IAError) falls back to the cached index
    only when it was built for this same allowlist (merely past its TTL), with
    a warning; otherwise it raises, and nothing is written."""
    if not allowlist:
        return {"artists": [], "items": {}}
    path = cache_dir / TS_INDEX_FILENAME
    now = now or datetime.now(timezone.utc)
    fp = allowlist.fingerprint()
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text())
            datetime.fromisoformat(cached["built_at"])
            cached["artists"], cached["items"]  # noqa: B018 - shape check
            if cached.get("allowlist") != fp:
                cached = None
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            cached = None
    if cached is not None and not refresh:
        if now - datetime.fromisoformat(cached["built_at"]) < timedelta(days=TS_INDEX_TTL_DAYS):
            return cached
    try:
        with step("building taperssection index (one request per allowlisted artist)"):
            data = build_ts_index(ia, allowlist)
    except (LlamaError, IAError) as exc:
        if cached is None:
            raise
        log.warning("taperssection index rebuild failed (%s); using stale index from %s",
                    exc, cached["built_at"])
        return cached
    write_artifact(path, json.dumps(data, indent=2))
    return data


def ts_items(ts_index: dict, key: str) -> dict[str, list[dict]]:
    """The per-date item store ({date: [{identifier, downloads, addeddate}]})
    for one ts- key, read from a load_ts_index result; {} when absent."""
    return (ts_index.get("items") or {}).get(key, {})


def filter_artists(artists: list[dict], min_recordings: int, min_downloads: int) -> list[dict]:
    """The backyard-band gate: enough recordings OR enough downloads.
    Allowlisted (Taper's Section) rows bypass it: the list is the curation."""
    return [a for a in artists
            if a.get("allowlisted")
            or a["recordings"] >= min_recordings or a["downloads"] >= min_downloads]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_artists(index: list[dict], names: list[str],
                    allowlist: Allowlist | None = None) -> list[dict]:
    """Resolve human-typed artist names to index entries, order preserved.

    An exact allowlist name or creator match comes first and wins, resolving
    to that entry's ts- index row. Then an exact normalized match on
    identifier or title, then a UNIQUE normalized-substring match over LMA
    rows only (allowlisted rows never join that rung, so no LMA substring pin
    changes); anything else raises ArtistResolutionError so a typo in a
    pinned roster fails at profile-add time, not silently at run time."""
    resolved: list[dict] = []
    for name in names:
        want = _norm(name)
        if not want:
            raise ArtistResolutionError(f"cannot pin artist: empty name in {names!r}")
        entry = allowlist.resolve_name(name) if allowlist else None
        if entry is not None:
            key = allowlist.key(entry)
            row = next((a for a in index if a["identifier"] == key), None)
            if row is None:
                raise ArtistResolutionError(
                    f"cannot pin artist: {name!r} is allowlisted as {key!r} but the "
                    "artist index has no row for it (the taperssection index could not "
                    "be built; see the warning)")
            resolved.append(row)
            continue
        exact = [a for a in index
                 if _norm(a["identifier"]) == want or _norm(a["title"]) == want]
        if exact:
            resolved.append(exact[0])
            continue
        partial = [a for a in index
                   if not a.get("allowlisted")
                   and (want in _norm(a["identifier"]) or want in _norm(a["title"]))]
        if len(partial) == 1:
            resolved.append(partial[0])
        elif not partial:
            raise ArtistResolutionError(f"cannot pin artist: no LMA match for {name!r}")
        else:
            options = ", ".join(a["identifier"] for a in partial[:8])
            raise ArtistResolutionError(
                f"cannot pin artist: {name!r} is ambiguous on the LMA: {options}")
    return resolved


def fmt_count(n: int) -> str:
    if n >= 999_950:
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


# Rendered into find_artists only when an allowlisted row is in the inventory;
# with none, the placeholder renders empty and the prompt is today's text.
TS_INVENTORY_NOTE = (
    "\n\nThe inventory also includes Taper's Section artists (identifiers starting "
    "\"ts-\"): fan recordings on archive.org with no LMA collection. They are "
    "eligible picks, weighed like any other artist.")


def find_matching_artists(provider, artists: list[dict], query: str, max_results: int) -> list[dict]:
    """One inventory-in-context LLM call; identifiers joined back against the
    filtered index, so a hallucinated identifier can never reach the caller."""
    has_ts = any(a.get("allowlisted") for a in artists)
    with step("matching artists against the "
              + ("artist" if has_ts else "LMA") + " inventory (LLM)"):
        result = run_json_task(
            provider, "find_artists", ArtistMatches,
            template=load_prompt("find_artists"),
            query=query, max_results=max_results,
            artist_table=render_artist_table(artists),
            ts_note=TS_INVENTORY_NOTE if has_ts else "",
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
