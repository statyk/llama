# Interactive Artist Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `llama artists "<natural-language query>"` returns ranked LMA artists with stats (recordings, years, downloads) from a locally cached index, and the `discover` stage is rewired onto the same inventory-in-context mechanism.

**Architecture:** A new `artist_index` module builds a ~1 MB JSON index from two archive.org scrape-API passes (collections + all items, aggregated locally), auto-refreshed after 30 days. One `find_artists` LLM `complete` call sees the junk-filtered inventory (default: ≥25 recordings OR ≥50k downloads) and picks from it; results join back deterministically. The blind propose-then-match machinery (`propose_artists` prompt, `ProposedArtists`, `match_artists`) is deleted.

**Tech Stack:** Python 3.11+, typer, pydantic v2, httpx (with `httpx.MockTransport` in tests), pytest.

**Spec:** `docs/superpowers/specs/2026-07-15-artist-search-design.md`

## Global Constraints

- Work in the worktree at `.claude/worktrees/artist-search` (branch `worktree-artist-search`); run everything from that directory with `.venv/bin/pytest` / `.venv/bin/python`.
- All tests offline and deterministic except the one `@pytest.mark.live` test (Task 7).
- Filter defaults exactly: `min_recordings = 25`, `min_downloads = 50000`; gate is OR, not AND.
- Index TTL exactly 30 days; index file is `<config.root>/cache/artist_index.json`.
- LLM calls only through `run_json_task`; new task key `find_artists`, default tier `medium`.
- Stage discipline for `artists.json`: skip-if-exists unless force, atomic `write_artifact`.
- Never commit audio; nothing in this plan downloads audio.
- Commit after every task with the exact message given (append the standard Claude trailer lines used in this repo).

---

### Task 1: `IAClient.scrape` — cursor-paginated bulk listing

**Files:**
- Modify: `src/llama/ia_client.py`
- Test: `tests/test_ia_client.py`

**Interfaces:**
- Consumes: existing `IAClient._get` (retry/throttle) and `IAError`.
- Produces: `IAClient.scrape(query: str, fields: list[str], count: int = 10000) -> list[dict]` — returns every doc for the query by following the scrape API's `cursor` until absent. NOT disk-cached (callers cache aggregates). Later tasks call `ia.scrape(...)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ia_client.py`:

```python
def test_scrape_follows_cursor(tmp_path: Path):
    pages = [
        {"items": [{"identifier": "A"}, {"identifier": "B"}], "count": 2,
         "cursor": "next-1", "total": 3},
        {"items": [{"identifier": "C"}], "count": 1, "total": 3},
    ]
    seen = {"params": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"].append(dict(request.url.params))
        return httpx.Response(200, json=pages[len(seen["params"]) - 1])

    ia = make_client(tmp_path, handler)
    docs = ia.scrape("collection:etree AND mediatype:collection",
                     ["identifier", "title", "downloads"], count=2)
    assert [d["identifier"] for d in docs] == ["A", "B", "C"]
    assert seen["params"][0]["fields"] == "identifier,title,downloads"
    assert seen["params"][0]["count"] == "2"
    assert "cursor" not in seen["params"][0]
    assert seen["params"][1]["cursor"] == "next-1"


def test_scrape_is_not_disk_cached(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [{"identifier": "A"}], "count": 1, "total": 1})

    ia = make_client(tmp_path, handler)
    ia.scrape("q", ["identifier"])
    ia.scrape("q", ["identifier"])
    assert calls["n"] == 2


def test_scrape_client_error_raises(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad"})

    ia = make_client(tmp_path, handler)
    with pytest.raises(IAError):
        ia.scrape("q", ["identifier"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ia_client.py -q`
Expected: 3 new tests FAIL with `AttributeError: 'IAClient' object has no attribute 'scrape'`; existing tests pass.

- [ ] **Step 3: Implement `scrape`**

In `src/llama/ia_client.py`, add below the other URL constants (after line 11):

```python
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
```

Add this method to `IAClient` after `search` (after line 82):

```python
    def scrape(self, query: str, fields: list[str], count: int = 10000) -> list[dict]:
        """Cursor-paginated bulk listing via the scrape API. Not disk-cached:
        callers persist aggregates (e.g. the artist index), not raw pages."""
        out: list[dict] = []
        cursor: str | None = None
        while True:
            params: dict = {"q": query, "fields": ",".join(fields), "count": count}
            if cursor:
                params["cursor"] = cursor
            data = self._get(SCRAPE_URL, params).json()
            out.extend(data.get("items", []))
            cursor = data.get("cursor")
            if not cursor:
                return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ia_client.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/ia_client.py tests/test_ia_client.py
git commit -m "feat: IAClient.scrape cursor-paginated bulk listing"
```

---

### Task 2: Artist index build — scrape aggregation

**Files:**
- Create: `src/llama/artist_index.py`
- Test: `tests/test_artist_index.py`

**Interfaces:**
- Consumes: `ia.scrape(query, fields)` from Task 1 (tests use a stub, not the real client).
- Produces:
  - `COLLECTIONS_QUERY = "collection:etree AND mediatype:collection"`, `ITEMS_QUERY = "collection:etree AND mediatype:etree"`.
  - `build_index(ia) -> dict` — `{"built_at": <ISO-8601 UTC>, "artists": [ {"identifier", "title", "downloads", "recordings", "year_min", "year_max"}, ... ]}` sorted by identifier; `year_min`/`year_max` are `int | None`.
  - Task 3 adds `load_or_build`/`filter_artists`/`fmt_count` to this same module; Task 4 adds `render_artist_table`/`find_matching_artists`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_artist_index.py`:

```python
from pathlib import Path

from llama.artist_index import build_index

COLLECTIONS = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "RobynHitchcock", "title": "Robyn Hitchcock", "downloads": 1311958},
    {"identifier": "BackyardBand", "title": "Backyard Band"},  # no downloads field
]

ITEMS = [
    # normal item: attributed to GratefulDead; etree/stream_only ignored
    {"identifier": "gd73-06-10.sbd", "collection": ["GratefulDead", "etree", "stream_only"],
     "year": "1973"},
    {"identifier": "gd77-05-08.sbd", "collection": ["GratefulDead", "etree"], "year": 1977},
    # collection as bare string, not list
    {"identifier": "rh96", "collection": "RobynHitchcock", "year": "1996"},
    # missing year and garbage year: counted, years skipped
    {"identifier": "rh-noyear", "collection": ["RobynHitchcock"]},
    {"identifier": "rh-badyear", "collection": ["RobynHitchcock"], "year": "n/a"},
    # year as list (archive.org quirk)
    {"identifier": "rh14", "collection": ["RobynHitchcock"], "year": ["2014"]},
    # item pointing at an unknown collection: ignored entirely
    {"identifier": "stray", "collection": ["NotAnArtist"], "year": "1999"},
]


class ScrapeStubIA:
    def __init__(self, collections=COLLECTIONS, items=ITEMS):
        self._collections = collections
        self._items = items
        self.queries = []

    def scrape(self, query, fields, count=10000):
        self.queries.append((query, tuple(fields)))
        if "mediatype:collection" in query:
            return self._collections
        return self._items


def by_id(index):
    return {a["identifier"]: a for a in index["artists"]}


def test_build_index_aggregates_recordings_years_downloads():
    index = build_index(ScrapeStubIA())
    artists = by_id(index)
    gd = artists["GratefulDead"]
    assert gd["recordings"] == 2
    assert (gd["year_min"], gd["year_max"]) == (1973, 1977)
    assert gd["downloads"] == 226766373
    rh = artists["RobynHitchcock"]
    assert rh["recordings"] == 4  # string collection, no-year, bad-year, list-year all count
    assert (rh["year_min"], rh["year_max"]) == (1996, 2014)


def test_build_index_zero_item_artist_and_missing_downloads():
    artists = by_id(build_index(ScrapeStubIA()))
    bb = artists["BackyardBand"]
    assert bb["recordings"] == 0
    assert bb["downloads"] == 0
    assert bb["year_min"] is None and bb["year_max"] is None
    assert "NotAnArtist" not in artists


def test_build_index_queries_and_timestamp():
    ia = ScrapeStubIA()
    index = build_index(ia)
    assert ia.queries[0][0] == "collection:etree AND mediatype:collection"
    assert ia.queries[1][0] == "collection:etree AND mediatype:etree"
    assert index["built_at"].startswith("20")
    ids = [a["identifier"] for a in index["artists"]]
    assert ids == sorted(ids)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_artist_index.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'llama.artist_index'`.

- [ ] **Step 3: Implement `build_index`**

Create `src/llama/artist_index.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_artist_index.py -q`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/artist_index.py tests/test_artist_index.py
git commit -m "feat: artist index build from scrape-API aggregation"
```

---

### Task 3: Index lifecycle (TTL, stale fallback), junk filter, `[artists]` config

**Files:**
- Modify: `src/llama/artist_index.py`
- Modify: `src/llama/config.py`
- Test: `tests/test_artist_index.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `build_index` (Task 2), `write_artifact` from `llama.workspace`, `IAError` from `llama.ia_client`.
- Produces:
  - `load_or_build(ia, cache_dir: Path, *, ttl_days: int = 30, refresh: bool = False, now: datetime | None = None) -> list[dict]` — returns the artists list; file `cache_dir / "artist_index.json"`; rebuild on missing/stale/refresh; on `IAError` during rebuild keep a stale file with a warning, raise if none.
  - `filter_artists(artists: list[dict], min_recordings: int, min_downloads: int) -> list[dict]` — keep when `recordings >= min_recordings OR downloads >= min_downloads`.
  - `fmt_count(n: int) -> str` — `226766373 -> "226.8M"`, `54321 -> "54.3k"`, `950 -> "950"`.
  - `config.artists.min_recordings` (default 25), `config.artists.min_downloads` (default 50000) via new `ArtistsConfig`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_artist_index.py`:

```python
import json
from datetime import datetime, timedelta, timezone

import pytest

from llama.artist_index import filter_artists, fmt_count, load_or_build
from llama.ia_client import IAError


class FailingIA:
    def scrape(self, query, fields, count=10000):
        raise IAError("boom")


def test_load_or_build_builds_and_reuses(tmp_path: Path):
    ia = ScrapeStubIA()
    artists = load_or_build(ia, tmp_path)
    assert {a["identifier"] for a in artists} == {"GratefulDead", "RobynHitchcock", "BackyardBand"}
    assert (tmp_path / "artist_index.json").exists()
    again = load_or_build(FailingIA(), tmp_path)  # fresh file: no scrape happens
    assert again == artists


def test_load_or_build_rebuilds_when_stale(tmp_path: Path):
    load_or_build(ScrapeStubIA(), tmp_path)
    future = datetime.now(timezone.utc) + timedelta(days=31)
    ia = ScrapeStubIA(collections=[{"identifier": "New", "title": "New", "downloads": 1}], items=[])
    artists = load_or_build(ia, tmp_path, now=future)
    assert [a["identifier"] for a in artists] == ["New"]


def test_load_or_build_refresh_forces(tmp_path: Path):
    load_or_build(ScrapeStubIA(), tmp_path)
    ia = ScrapeStubIA(collections=[{"identifier": "New", "title": "New", "downloads": 1}], items=[])
    artists = load_or_build(ia, tmp_path, refresh=True)
    assert [a["identifier"] for a in artists] == ["New"]


def test_load_or_build_keeps_stale_on_failure(tmp_path: Path):
    load_or_build(ScrapeStubIA(), tmp_path)
    future = datetime.now(timezone.utc) + timedelta(days=31)
    artists = load_or_build(FailingIA(), tmp_path, now=future)  # rebuild fails -> stale kept
    assert {a["identifier"] for a in artists} == {"GratefulDead", "RobynHitchcock", "BackyardBand"}


def test_load_or_build_raises_without_any_index(tmp_path: Path):
    with pytest.raises(IAError):
        load_or_build(FailingIA(), tmp_path)


def test_filter_artists_or_semantics():
    artists = [
        {"identifier": "Deep", "recordings": 100, "downloads": 0},
        {"identifier": "Popular", "recordings": 3, "downloads": 90000},
        {"identifier": "Backyard", "recordings": 3, "downloads": 20},
        {"identifier": "EdgeRec", "recordings": 25, "downloads": 0},
        {"identifier": "EdgeDl", "recordings": 0, "downloads": 50000},
    ]
    kept = {a["identifier"] for a in filter_artists(artists, 25, 50000)}
    assert kept == {"Deep", "Popular", "EdgeRec", "EdgeDl"}


def test_fmt_count():
    assert fmt_count(226766373) == "226.8M"
    assert fmt_count(54321) == "54.3k"
    assert fmt_count(950) == "950"
```

Append to `tests/test_config.py`:

```python
def test_artists_config_defaults_and_override(tmp_path):
    from llama.config import load_config

    assert load_config(tmp_path / "missing.toml").artists.min_recordings == 25
    assert load_config(tmp_path / "missing.toml").artists.min_downloads == 50000
    p = tmp_path / "config.toml"
    p.write_text("[artists]\nmin_recordings = 5\nmin_downloads = 1000\n")
    cfg = load_config(p)
    assert cfg.artists.min_recordings == 5
    assert cfg.artists.min_downloads == 1000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_artist_index.py tests/test_config.py -q`
Expected: new tests FAIL with `ImportError` (`filter_artists`) / `AttributeError` (`artists` on Config).

- [ ] **Step 3: Implement lifecycle, filter, config**

In `src/llama/artist_index.py`, extend the imports:

```python
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llama.ia_client import IAError
from llama.workspace import write_artifact
```

Append after `build_index`:

```python
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
```

In `src/llama/config.py`, add after `StructureConfig` (line 26):

```python
class ArtistsConfig(BaseModel):
    min_recordings: int = 25
    min_downloads: int = 50000
```

and add this field to `Config` after the `structure` field (line 34):

```python
    artists: ArtistsConfig = Field(default_factory=ArtistsConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_artist_index.py tests/test_config.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/artist_index.py src/llama/config.py tests/test_artist_index.py tests/test_config.py
git commit -m "feat: artist index lifecycle, junk filter, [artists] config"
```

---

### Task 4: `find_artists` LLM touchpoint

**Files:**
- Create: `src/llama/prompts/find_artists.md`
- Modify: `src/llama/models.py`, `src/llama/artist_index.py`, `src/llama/llm/__init__.py`, `src/llama/pipeline.py`
- Test: `tests/test_artist_index.py`, `tests/test_prompts.py`, `tests/test_model_tiers.py`

**Interfaces:**
- Consumes: `run_json_task(provider, task, schema, **inputs)` from `llama.llm.tasks`; `FakeProvider` from `llama.llm.fake` in tests.
- Produces:
  - Models: `ArtistMatch(identifier: str, reason: str = "")`, `ArtistMatches(matches: list[ArtistMatch])` in `models.py`.
  - `render_artist_table(artists: list[dict]) -> str` — one line per artist: `identifier | title | N recordings | YYYY-YYYY | downloads`.
  - `find_matching_artists(provider, artists: list[dict], query: str, max_results: int) -> list[dict]` — each result is the index entry dict plus a `"reason"` key; unknown identifiers dropped with a warning; capped at `max_results`.
  - Task keys: `find_artists` added to `DEFAULT_TIERS` (tier `medium`) and `pipeline.TASK_KEYS`. (`propose_artists` stays until Task 7.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_artist_index.py`:

```python
from llama.artist_index import find_matching_artists, render_artist_table
from llama.llm.fake import FakeProvider

POOL = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "recordings": 18271,
     "downloads": 226766373, "year_min": 1965, "year_max": 1995},
    {"identifier": "RobynHitchcock", "title": "Robyn Hitchcock", "recordings": 985,
     "downloads": 1311958, "year_min": 1996, "year_max": 2014},
]


def matches_json(*pairs):
    return json.dumps({"matches": [{"identifier": i, "reason": r} for i, r in pairs]})


def test_render_artist_table_line_format():
    table = render_artist_table(POOL)
    lines = table.splitlines()
    assert lines[0] == "GratefulDead | Grateful Dead | 18271 recordings | 1965-1995 | 226.8M downloads"
    assert lines[1].startswith("RobynHitchcock | Robyn Hitchcock | 985 recordings | 1996-2014")


def test_render_artist_table_unknown_years():
    row = {"identifier": "X", "title": "X", "recordings": 0, "downloads": 5,
           "year_min": None, "year_max": None}
    assert "| ? |" in render_artist_table([row])


def test_find_matching_artists_joins_stats_and_reason():
    fake = FakeProvider(completes=[matches_json(("RobynHitchcock", "jangly songwriter"))])
    got = find_matching_artists(fake, POOL, "jangly college rock", max_results=5)
    assert len(got) == 1
    assert got[0]["identifier"] == "RobynHitchcock"
    assert got[0]["recordings"] == 985
    assert got[0]["reason"] == "jangly songwriter"
    prompt = fake.calls[0][1]
    assert "jangly college rock" in prompt
    assert "GratefulDead | Grateful Dead" in prompt


def test_find_matching_artists_drops_hallucinated_identifiers():
    fake = FakeProvider(completes=[matches_json(("NickDrake", "x"), ("GratefulDead", "y"))])
    got = find_matching_artists(fake, POOL, "q", max_results=5)
    assert [a["identifier"] for a in got] == ["GratefulDead"]


def test_find_matching_artists_caps_at_max_results():
    fake = FakeProvider(completes=[matches_json(("GratefulDead", "a"), ("RobynHitchcock", "b"))])
    got = find_matching_artists(fake, POOL, "q", max_results=1)
    assert len(got) == 1
```

In `tests/test_prompts.py`, add to the `EXPECTED` dict (keep `propose_artists` for now):

```python
    "find_artists": {"query", "max_results", "artist_table"},
```

In `tests/test_model_tiers.py` (line 57 area), the expected-tiers table gains:

```python
        "find_artists": "medium",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_artist_index.py tests/test_prompts.py tests/test_model_tiers.py -q`
Expected: FAIL — `ImportError: cannot import name 'find_matching_artists'`, prompt table FAIL (`find_artists` missing), tiers FAIL.

- [ ] **Step 3: Implement models, prompt, helpers, registrations**

In `src/llama/models.py`, add after `ProposedArtists` (line ~194):

```python
class ArtistMatch(BaseModel):
    identifier: str
    reason: str = ""


class ArtistMatches(BaseModel):
    matches: list[ArtistMatch] = Field(default_factory=list)
```

Create `src/llama/prompts/find_artists.md` (placeholders exactly `query`, `max_results`, `artist_table`):

```markdown
You are picking artists for a radio programmer from archive.org's Live
Music Archive (LMA). Below is the actual LMA inventory you may choose
from — one artist per line:

identifier | display title | recordings | years covered | downloads

Request: {{query}}

Pick up to {{max_results}} artists from the inventory that best fit the
request, best fit first. Weigh:
- style/genre and mood fit with the request
- era overlap between the request and the years covered
- catalog depth (more recordings = deeper LMA coverage to draw from)

Only use identifiers that appear in the inventory. Never invent one.
If nothing fits, return an empty list.

Respond with ONLY JSON, no commentary, no markdown fences:
{"matches": [{"identifier": "<identifier from the inventory>",
              "reason": "<one line on why it fits>"}]}

Inventory:
{{artist_table}}
```

In `src/llama/artist_index.py`, add to the imports:

```python
from llama.llm.tasks import run_json_task
from llama.models import ArtistMatches
```

Append after `fmt_count`:

```python
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
```

In `src/llama/llm/__init__.py`, add to `DEFAULT_TIERS` (after `"propose_artists": "medium",`):

```python
    "find_artists": "medium",
```

In `src/llama/pipeline.py`, add `"find_artists"` to `TASK_KEYS`:

```python
TASK_KEYS = ["interpret", "score_reviews", "light_research",
             "extract_setlist", "deep_research", "synthesize", "propose_artists",
             "find_artists", "align_structure", "vet_research"]
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all PASS (235 pre-existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/llama/models.py src/llama/prompts/find_artists.md src/llama/artist_index.py src/llama/llm/__init__.py src/llama/pipeline.py tests/test_artist_index.py tests/test_prompts.py tests/test_model_tiers.py
git commit -m "feat: find_artists inventory-in-context LLM touchpoint"
```

---

### Task 5: `llama artists` CLI command

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_artists_cmd.py` (create)

**Interfaces:**
- Consumes: `load_or_build`, `filter_artists`, `find_matching_artists`, `fmt_count` (Tasks 3–4); `provider_ladder` from `llama.llm`; `config.artists` (Task 3); existing `_setup`.
- Produces: `llama artists [QUERY] [--limit 20] [--min-recordings N] [--min-downloads N] [--all] [--refresh] [--config PATH]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_artists_cmd.py`:

```python
import json

from typer.testing import CliRunner

import llama.cli as cli
from llama.llm.fake import FakeProvider

runner = CliRunner()

COLLECTIONS = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "RobynHitchcock", "title": "Robyn Hitchcock", "downloads": 1311958},
    {"identifier": "BackyardBand", "title": "Backyard Band", "downloads": 20},
]

ITEMS = (
    [{"identifier": f"gd{i}", "collection": ["GratefulDead"], "year": "1973"} for i in range(30)]
    + [{"identifier": f"rh{i}", "collection": ["RobynHitchcock"], "year": "1996"} for i in range(30)]
    + [{"identifier": "bb1", "collection": ["BackyardBand"], "year": "2019"}]
)


class ScrapeFakeIA:
    def __init__(self, *args, **kwargs):
        pass

    def scrape(self, query, fields, count=10000):
        if "mediatype:collection" in query:
            return COLLECTIONS
        return ITEMS


def matches_json(*pairs):
    return json.dumps({"matches": [{"identifier": i, "reason": r} for i, r in pairs]})


def setup(tmp_path, monkeypatch, provider):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: ScrapeFakeIA())
    monkeypatch.setattr(cli, "provider_ladder", lambda config, task: provider)
    return ["--config", str(tmp_path / "config.toml")]


def test_artists_query_prints_ranked_table(tmp_path, monkeypatch):
    provider = FakeProvider(completes=[matches_json(("RobynHitchcock", "jangly icon"))])
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, ["artists", "jangly college rock", *cfg])
    assert result.exit_code == 0, result.output
    assert "Robyn Hitchcock" in result.output
    assert "30" in result.output           # recordings
    assert "1996" in result.output         # years
    assert "1.3M" in result.output         # downloads humanized
    assert "jangly icon" in result.output  # reason
    assert "Backyard Band" not in result.output


def test_artists_filter_excludes_backyard_from_llm_table(tmp_path, monkeypatch):
    provider = FakeProvider(completes=[matches_json(("GratefulDead", "x"))])
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, ["artists", "anything", *cfg])
    assert result.exit_code == 0, result.output
    prompt = provider.calls[0][1]
    assert "GratefulDead" in prompt and "RobynHitchcock" in prompt
    assert "BackyardBand" not in prompt  # 1 recording, 20 downloads: filtered


def test_artists_no_query_lists_by_recordings_without_llm(tmp_path, monkeypatch):
    provider = FakeProvider()  # any complete() call would raise
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, ["artists", *cfg])
    assert result.exit_code == 0, result.output
    assert "Grateful Dead" in result.output and "Robyn Hitchcock" in result.output
    assert "Backyard Band" not in result.output
    assert provider.calls == []


def test_artists_all_includes_backyard(tmp_path, monkeypatch):
    provider = FakeProvider()
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, ["artists", "--all", *cfg])
    assert result.exit_code == 0, result.output
    assert "Backyard Band" in result.output


def test_artists_zero_matches_message(tmp_path, monkeypatch):
    provider = FakeProvider(completes=[matches_json(("NickDrake", "not on LMA"))])
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, ["artists", "obscure query", *cfg])
    assert result.exit_code == 0, result.output
    assert "no matching artists" in result.output


def test_artists_impossible_thresholds_message(tmp_path, monkeypatch):
    provider = FakeProvider()
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, ["artists", "anything",
                                     "--min-recordings", "999999",
                                     "--min-downloads", "999999999999", *cfg])
    assert result.exit_code == 0, result.output
    assert "no artists pass" in result.output
    assert provider.calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_artists_cmd.py -q`
Expected: FAIL — typer exits 2 (`No such command 'artists'`) and `AttributeError: ... has no attribute 'provider_ladder'`.

- [ ] **Step 3: Implement the command**

In `src/llama/cli.py`, extend the `llama.llm` import (line 7):

```python
from llama.llm import provider_ladder
```

and add:

```python
from llama.artist_index import filter_artists, find_matching_artists, fmt_count, load_or_build
```

Add the command after `find` (after line ~173):

```python
@app.command()
def artists(
    query: str = typer.Argument(None, help="Natural-language artist query (omit to list by catalog size)"),
    limit: int = typer.Option(20, "--limit", help="Max artists to show"),
    min_recordings: int = typer.Option(None, "--min-recordings",
                                       help="Junk filter floor (default from [artists] config)"),
    min_downloads: int = typer.Option(None, "--min-downloads",
                                      help="Junk filter floor (default from [artists] config)"),
    all_artists: bool = typer.Option(False, "--all", help="Skip the junk filter entirely"),
    refresh: bool = typer.Option(False, "--refresh", help="Force an artist index rebuild"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Search LMA artists with a natural-language query, or list the deepest catalogs."""
    config, ia, _ = _setup(config_path)
    try:
        index = load_or_build(ia, config.root / "cache", refresh=refresh)
    except IAError as exc:
        typer.echo(f"artist index build failed: {exc}", err=True)
        raise typer.Exit(1)
    mr = min_recordings if min_recordings is not None else config.artists.min_recordings
    md = min_downloads if min_downloads is not None else config.artists.min_downloads
    pool = index if all_artists else filter_artists(index, mr, md)
    if not pool:
        typer.echo("no artists pass the current thresholds - "
                   "lower --min-recordings/--min-downloads or use --all")
        return
    if query is None:
        _print_artists(sorted(pool, key=lambda a: -a["recordings"])[:limit])
        return
    matches = find_matching_artists(provider_ladder(config, "find_artists"),
                                    pool, query, max_results=limit)
    if not matches:
        typer.echo("no matching artists - try a broader query, "
                   "lower thresholds, or --all")
        return
    _print_artists(matches)
```

Add the printer next to `_print_shortlist`:

```python
def _print_artists(rows: list[dict]) -> None:
    for i, a in enumerate(rows, 1):
        years = (f"{a['year_min']}-{a['year_max']}"
                 if a.get("year_min") is not None else "?")
        typer.echo(f"{i:2d}. {a['title']:<40.40s} {a['recordings']:>6d} rec  "
                   f"{years:>9s}  {fmt_count(a['downloads']):>7s} dl")
        if a.get("reason"):
            typer.echo(f"      {a['reason']}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_artists_cmd.py -q` then `.venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_artists_cmd.py
git commit -m "feat: llama artists command - NL artist search with stats"
```

---

### Task 6: Rewire the discover stage onto the artist index

**Files:**
- Modify: `src/llama/stages/discover.py` (near-total rewrite), `src/llama/cli.py:81-88`
- Test: `tests/test_stage_discover.py` (rewrite), `tests/test_cli_commands.py:130-215`

**Interfaces:**
- Consumes: `load_or_build`, `filter_artists`, `find_matching_artists` (Tasks 3–4); `config.artists`.
- Produces: `run_discover(ws, provider, ia, criteria, *, cache_dir: Path, min_recordings: int = 25, min_downloads: int = 50000, max_artists: int = 10, force: bool = False) -> list[dict]` — same trigger, same `artists.json` artifact (`[{"identifier", "title"}]`), same skip-if-exists. `match_artists` and the `COLLECTIONS_QUERY` constant disappear from this module.

- [ ] **Step 1: Rewrite the stage tests**

Replace the entire contents of `tests/test_stage_discover.py` with:

```python
import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Criteria
from llama.stages.discover import run_discover
from llama.workspace import RunWorkspace

COLLECTIONS = [
    {"identifier": "DocWatson", "title": "Doc and Merle Watson", "downloads": 800000},
    {"identifier": "JoanBaez", "title": "Joan Baez", "downloads": 900000},
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "TinyBand", "title": "Tiny Band", "downloads": 20},
]

ITEMS = [{"identifier": f"jb{i}", "collection": ["JoanBaez"], "year": "1965"} for i in range(3)]


class StubIA:
    def __init__(self, collections=COLLECTIONS, items=ITEMS):
        self._collections = collections
        self._items = items
        self.queries = []

    def scrape(self, query, fields, count=10000):
        self.queries.append(query)
        if "mediatype:collection" in query:
            return self._collections
        return self._items


def crit() -> Criteria:
    return Criteria(query="well-known folk/acoustic performer 60s-70s",
                    soft_preferences="folk/acoustic, well known",
                    date_from="1960-01-01", date_to="1979-12-31")


def matches(*pairs):
    return json.dumps({"matches": [{"identifier": i, "reason": r} for i, r in pairs]})


def test_discover_matches_orders_and_writes(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches(("JoanBaez", "60s folk icon"),
                                           ("DocWatson", "flatpicking legend"))])
    got = run_discover(ws, fake, StubIA(), crit(), cache_dir=tmp_path / "cache")
    assert got == [
        {"identifier": "JoanBaez", "title": "Joan Baez"},
        {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    ]  # LLM ranking kept; reasons not persisted in the artifact
    assert json.loads(ws.artists.read_text()) == got
    prompt = fake.calls[0][1]
    assert "folk/acoustic, well known" in prompt      # soft prefs reach the LLM
    assert "1960-01-01" in prompt                     # era reaches the LLM
    assert "TinyBand" not in prompt                   # junk-filtered out of the table


def test_discover_caps_at_max_artists(tmp_path: Path):
    cols = [{"identifier": f"A{i}", "title": f"Artist {i}", "downloads": 60000}
            for i in range(15)]
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches(*((f"A{i}", "fits") for i in range(15)))])
    got = run_discover(ws, fake, StubIA(collections=cols, items=[]), crit(),
                       cache_dir=tmp_path / "cache")
    assert len(got) == 10


def test_zero_matches_writes_empty(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches()])
    assert run_discover(ws, fake, StubIA(), crit(), cache_dir=tmp_path / "cache") == []
    assert json.loads(ws.artists.read_text()) == []


def test_skip_if_exists(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    run_discover(ws, FakeProvider(completes=[matches(("JoanBaez", "x"))]),
                 StubIA(), crit(), cache_dir=tmp_path / "cache")
    again = run_discover(ws, FakeProvider(), StubIA(), crit(),
                         cache_dir=tmp_path / "cache")
    assert again[0]["identifier"] == "JoanBaez"
```

- [ ] **Step 2: Update the CLI fuzzy-query tests**

In `tests/test_cli_commands.py` (lines 130–215):

Replace `FuzzyFakeIA` and `fuzzy_providers` with:

```python
ARTIST_COLLECTIONS = [
    {"identifier": "JoanBaez", "title": "Joan Baez", "downloads": 900000},
    {"identifier": "DocWatson", "title": "Doc and Merle Watson", "downloads": 800000},
    {"identifier": "TownesVanZandt", "title": "Townes Van Zandt", "downloads": 700000},
]


class FuzzyFakeIA:
    def __init__(self, *args, **kwargs):
        self.etree_queries = []

    def scrape(self, query, fields, count=10000):
        if "mediatype:collection" in query:
            return ARTIST_COLLECTIONS
        return []  # no items: downloads alone pass the filter

    def search(self, query, fields, rows=500):
        self.etree_queries.append(query)
        return []  # no shows: pipeline ends at "No shows survived winnowing."


def fuzzy_matches():
    return json.dumps({"matches": [
        {"identifier": "JoanBaez", "reason": "folk icon"},
        {"identifier": "DocWatson", "reason": "flatpicking"},
        {"identifier": "TownesVanZandt", "reason": "songwriter"},
    ]})


def fuzzy_providers(config):
    from llama.llm.fake import FakeProvider
    return {
        "interpret": FakeProvider(completes=[FUZZY_CRITERIA]),
        "find_artists": FakeProvider(completes=[fuzzy_matches()]),
        "score_reviews": FakeProvider(),
        "light_research": FakeProvider(),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(),
        "synthesize": FakeProvider(),
    }
```

In `test_fuzzy_query_zero_matches_exits_cleanly`, replace the `make_providers` monkeypatch with:

```python
    monkeypatch.setattr(cli, "make_providers", lambda config: {
        **fuzzy_providers(config),
        "find_artists": __import__("llama.llm.fake", fromlist=["FakeProvider"]).FakeProvider(
            completes=[json.dumps({"matches": [{"identifier": "NickDrake", "reason": "x"}]})]),
    })
```

and update its message assertion to:

```python
    assert "no matching artists" in result.output
```

Leave the other three fuzzy tests' bodies as they are — same prune input, same assertions on `artists.json` and `collection:DocWatson`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stage_discover.py tests/test_cli_commands.py -q`
Expected: FAIL — `run_discover` rejects `cache_dir` kwarg; fuzzy tests fail on `find_artists` key / scrape.

- [ ] **Step 4: Rewrite the stage and the CLI call site**

Replace the entire contents of `src/llama/stages/discover.py` with:

```python
import logging
from pathlib import Path

from llama.artist_index import filter_artists, find_matching_artists, load_or_build
from llama.models import Criteria
from llama.workspace import RunWorkspace, read_json, should_run, write_artifact

log = logging.getLogger("llama")


def _compose_query(criteria: Criteria) -> str:
    parts = [criteria.query]
    if criteria.soft_preferences:
        parts.append(f"Style/mood: {criteria.soft_preferences}")
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
```

In `src/llama/cli.py` `_execute` (lines 81–88), replace the discover block with:

```python
    if criteria.collection is None and criteria.artist is None and criteria.soft_preferences:
        artists = run_discover(ws, providers["find_artists"], ia, criteria,
                               cache_dir=config.root / "cache",
                               min_recordings=config.artists.min_recordings,
                               min_downloads=config.artists.min_downloads,
                               force=force)
        if not artists:
            typer.echo("no matching artists found on the LMA - "
                       "try naming an artist or broadening the style", err=True)
            return
```

(The interactive prune prompt below it is unchanged.)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/stages/discover.py src/llama/cli.py tests/test_stage_discover.py tests/test_cli_commands.py
git commit -m "feat: discover stage rides the artist index (inventory-in-context)"
```

---

### Task 7: Delete propose-then-match machinery; live test; docs

**Files:**
- Delete: `src/llama/prompts/propose_artists.md`
- Modify: `src/llama/models.py` (drop `ProposedArtists`), `src/llama/pipeline.py` (drop `"propose_artists"` from `TASK_KEYS`), `src/llama/llm/__init__.py` (drop `"propose_artists"` from `DEFAULT_TIERS`), `tests/test_prompts.py` (drop its row), `tests/test_model_tiers.py` (drop its row), `README.md`, `CLAUDE.md`
- Test: `tests/test_live_smoke.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6 already in place; nothing imports the deleted names after Task 6 (verify).
- Produces: a repo with exactly nine named touchpoints again; `-m live` coverage of the real scrape API.

- [ ] **Step 1: Verify nothing still references the old machinery**

Run: `grep -rn "propose_artists\|ProposedArtists\|match_artists" src tests --include="*.py"`
Expected: hits ONLY in `src/llama/models.py`, `src/llama/pipeline.py`, `src/llama/llm/__init__.py`, `tests/test_prompts.py`, `tests/test_model_tiers.py` (the registration/table rows being removed in this task). Any other hit means Task 6 missed a call site — fix that first.

- [ ] **Step 2: Delete the machinery**

```bash
git rm src/llama/prompts/propose_artists.md
```

- In `src/llama/models.py`: delete the `ProposedArtists` class (and its `Field` usage if now unused elsewhere — `Field` is used by other models, keep the import).
- In `src/llama/pipeline.py`: remove `"propose_artists",` from `TASK_KEYS`.
- In `src/llama/llm/__init__.py`: remove `"propose_artists": "medium",` from `DEFAULT_TIERS`.
- In `tests/test_prompts.py`: remove the `"propose_artists"` row from `EXPECTED`.
- In `tests/test_model_tiers.py`: remove the `"propose_artists"` row from the expected table.

- [ ] **Step 3: Add the live scrape-shape test**

Append to `tests/test_live_smoke.py`, following its existing `@pytest.mark.live` style (open the file and match its fixture/client construction pattern; if it builds a real `IAClient` in a helper, reuse that helper):

```python
@pytest.mark.live
def test_scrape_api_shape(tmp_path):
    """One real scrape request: the collections pass returns thousands of
    artist docs with the fields the index build depends on."""
    from llama.artist_index import COLLECTIONS_QUERY
    from llama.ia_client import IAClient

    ia = IAClient(cache_dir=tmp_path / "cache")
    docs = ia.scrape(COLLECTIONS_QUERY, ["identifier", "title", "downloads"])
    assert len(docs) > 5000
    sample = docs[0]
    assert "identifier" in sample
```

- [ ] **Step 4: Run the offline suite**

Run: `.venv/bin/pytest -q`
Expected: all PASS, none deselected other than live.
Then run: `grep -rn "propose_artists\|ProposedArtists\|match_artists" src tests --include="*.py"`
Expected: no output.

- [ ] **Step 5: Update docs**

In `README.md`, after the `find` usage (near the "artist-less queries propose artists first" comment at line ~47 — update that comment to "artist-less queries match artists against the index first"), add:

```markdown
### Explore artists

    llama artists "jangly 80s college rock"     # NL search, ranked with stats
    llama artists                               # deepest catalogs, no LLM call
    llama artists --all "obscure tape scene"    # include the long tail
    llama artists --refresh                     # force an index rebuild

The first call builds a local artist index (one collections request plus
~30 scrape pages over all LMA items, about a minute); it auto-refreshes
after 30 days. Small collections are hidden unless they clear the
`[artists]` thresholds in config (defaults: 25 recordings or 50k
downloads); `--min-recordings` / `--min-downloads` / `--all` override
per invocation.
```

In `CLAUDE.md`: in the Commands section add `llama artists "..."` to the Run line; the "Nine named touchpoints" sentence stays true (propose_artists is replaced by find_artists) — update the touchpoint example wording only if it names propose_artists explicitly.

- [ ] **Step 6: Final verification and commit**

Run: `.venv/bin/pytest -q`
Expected: all PASS.

```bash
git add -A
git commit -m "refactor: retire propose-then-match; live scrape test; artist-search docs"
```
