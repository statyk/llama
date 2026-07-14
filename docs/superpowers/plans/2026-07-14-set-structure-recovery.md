# Set-Structure Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical performance-level setlist from all recordings of a show (plus optional setlist.fm), align it onto the chosen recording's tracks, and flag long shows that still come out single-set.

**Architecture:** Two new modules — `setlistfm.py` (HTTP client mirroring `IAClient`: throttle, retry, disk cache, never raises past itself) and `structure.py` (pure logic: convert/rank/blend/align/guard) — orchestrated by the existing gather stage. One new LLM touchpoint (`align_structure`, the 8th) recovers messy alignments. A `StructureInfo` provenance block on `Show` records which source won and how alignment went.

**Tech Stack:** Python 3.11+, pydantic v2, httpx, typer, pytest. Spec: `docs/superpowers/specs/2026-07-14-set-structure-recovery-design.md`.

## Global Constraints

- All tests offline and deterministic; LLM calls only via `FakeProvider`; HTTP only via `httpx.MockTransport`.
- Never commit audio files (`*.mp3`, `*.flac`, `*.shn`).
- setlist.fm is best-effort everywhere: no API key / no match / any error ⇒ `None`, never an exception out of the client, never a gather failure.
- Config defaults (spec §Config): `guard_min_minutes = 100`, `guard_min_tracks = 16`, `align_coverage_threshold = 0.8`.
- `SETLISTFM_API_KEY` env var overrides `[setlistfm] api_key` in config.
- Run the full suite (`pytest -q`) before every commit; every task ends green.
- Work on branch `set-structure-recovery`.

**Repo orientation (read before Task 1):** source in `src/llama/`, stages in `src/llama/stages/`, prompt templates in `src/llama/prompts/*.md`, pydantic models in `src/llama/models.py`, tests in `tests/`, fixtures in `tests/fixtures/`. `pytest -q` from the repo root with the venv active (`source .venv/bin/activate`).

---

### Task 1: Config — `[setlistfm]` and `[structure]` sections

**Files:**
- Modify: `src/llama/config.py`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.setlistfm: SetlistFMConfig` (field `api_key: str | None`), `Config.structure: StructureConfig` (fields `guard_min_minutes: int = 100`, `guard_min_tracks: int = 16`, `align_coverage_threshold: float = 0.8`). Later tasks read `config.setlistfm.api_key` and pass `config.structure` into gather.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_setlistfm_and_structure_defaults():
    cfg = Config()
    assert cfg.setlistfm.api_key is None
    assert cfg.structure.guard_min_minutes == 100
    assert cfg.structure.guard_min_tracks == 16
    assert cfg.structure.align_coverage_threshold == 0.8


def test_setlistfm_and_structure_from_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[setlistfm]\napi_key = "k123"\n\n'
        "[structure]\nguard_min_minutes = 90\nguard_min_tracks = 12\n"
        "align_coverage_threshold = 0.5\n"
    )
    cfg = load_config(p)
    assert cfg.setlistfm.api_key == "k123"
    assert cfg.structure.guard_min_minutes == 90
    assert cfg.structure.guard_min_tracks == 12
    assert cfg.structure.align_coverage_threshold == 0.5
```

(`Config` and `load_config` are already imported at the top of `tests/test_config.py`; if not, add `from llama.config import Config, load_config`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'setlistfm'`

- [ ] **Step 3: Implement**

In `src/llama/config.py`, after `LLMTaskConfig` add:

```python
class SetlistFMConfig(BaseModel):
    api_key: str | None = None


class StructureConfig(BaseModel):
    guard_min_minutes: int = 100
    guard_min_tracks: int = 16
    align_coverage_threshold: float = 0.8
```

and add two fields to `Config`:

```python
    setlistfm: SetlistFMConfig = Field(default_factory=SetlistFMConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/config.py tests/test_config.py
git commit -m "feat: add setlistfm and structure config sections"
```

---

### Task 2: setlist.fm client

**Files:**
- Create: `src/llama/setlistfm.py`
- Test: `tests/test_setlistfm.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `normalize_song` from `llama.songs`.
- Produces:
  - `SetlistFMClient(cache_dir: Path, api_key: str, client: httpx.Client | None = None, max_retries: int = 3, backoff_s: float = 1.0, rate_limit_s: float = 1.0)`
  - `SetlistFMClient.setlist(artist: str, date: str, venue: str | None = None, city: str | None = None) -> dict | None` — `date` is `YYYY-MM-DD`; returns one raw setlist.fm setlist object or `None`. Never raises.
  - `make_client(config: Config) -> SetlistFMClient | None` — `None` when no key (env `SETLISTFM_API_KEY`, then `config.setlistfm.api_key`).

API notes for the implementer: `GET https://api.setlist.fm/rest/1.0/search/setlists?artistName=<name>&date=<DD-MM-YYYY>` with headers `x-api-key` and `accept: application/json`. A 200 body is `{"setlist": [ ... ]}`; **404 means "no setlists found"** (a normal outcome, not an error); 429/5xx are transient.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setlistfm.py`:

```python
import json
from pathlib import Path

import httpx

from llama.config import Config
from llama.setlistfm import SetlistFMClient, make_client

WINTERLAND = {
    "id": "abc123",
    "eventDate": "24-02-1974",
    "venue": {"name": "Winterland", "city": {"name": "San Francisco", "stateCode": "CA"}},
    "sets": {"set": [{"song": [{"name": "U.S. Blues"}]}]},
}
OAKLAND = {
    "id": "zzz999",
    "eventDate": "24-02-1974",
    "venue": {"name": "Oakland Coliseum", "city": {"name": "Oakland", "stateCode": "CA"}},
    "sets": {"set": [{"song": [{"name": "Other Song"}]}]},
}


def make(tmp_path: Path, handler) -> SetlistFMClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, headers={"x-api-key": "k"})
    return SetlistFMClient(cache_dir=tmp_path / "cache", api_key="k",
                           client=http, backoff_s=0, rate_limit_s=0)


def test_picks_venue_match_and_caches(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.params["date"] == "24-02-1974"
        return httpx.Response(200, json={"setlist": [OAKLAND, WINTERLAND]})

    c = make(tmp_path, handler)
    got = c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena", city="San Francisco, CA")
    assert got["id"] == "abc123"
    again = c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena", city="San Francisco, CA")
    assert again["id"] == "abc123"
    assert calls["n"] == 1  # second call served from disk cache


def test_no_venue_match_returns_none(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"setlist": [OAKLAND]})

    c = make(tmp_path, handler)
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena", city="San Francisco, CA") is None


def test_no_venue_given_accepts_sole_result_rejects_multiple(tmp_path: Path):
    def one(request):
        return httpx.Response(200, json={"setlist": [WINTERLAND]})

    def two(request):
        return httpx.Response(200, json={"setlist": [WINTERLAND, OAKLAND]})

    assert make(tmp_path / "a", one).setlist("Grateful Dead", "1974-02-24")["id"] == "abc123"
    assert make(tmp_path / "b", two).setlist("Grateful Dead", "1974-02-24") is None


def test_404_is_no_result_and_cached(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    c = make(tmp_path, handler)
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena") is None
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena") is None
    assert calls["n"] == 1  # no-result is a normal outcome: cached


def test_server_error_returns_none_and_is_not_cached(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    c = make(tmp_path, handler)
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena") is None
    assert calls["n"] == 3  # retried
    assert not list((tmp_path / "cache").glob("slfm_*.json"))  # errors not cached


def test_make_client_requires_key(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    assert make_client(Config()) is None
    cfg = Config.model_validate({"setlistfm": {"api_key": "fromtoml"}})
    assert make_client(cfg).api_key == "fromtoml"
    monkeypatch.setenv("SETLISTFM_API_KEY", "fromenv")
    assert make_client(cfg).api_key == "fromenv"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_setlistfm.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'llama.setlistfm'`

- [ ] **Step 3: Implement**

Create `src/llama/setlistfm.py`:

```python
"""Best-effort setlist.fm lookup. Every failure degrades to None; nothing raises."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx

from llama.config import Config
from llama.songs import normalize_song

SEARCH_URL = "https://api.setlist.fm/rest/1.0/search/setlists"

log = logging.getLogger("llama")


def _name_match(a: str, b: str) -> bool:
    na, nb = normalize_song(a), normalize_song(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _pick(setlists: list[dict], venue: str | None, city: str | None) -> dict | None:
    if not setlists:
        return None
    if venue is None:
        # Without a venue to verify against, only a sole result is safe.
        return setlists[0] if len(setlists) == 1 else None
    for s in setlists:
        v = s.get("venue") or {}
        if _name_match(venue, v.get("name") or ""):
            return s
        if city and _name_match(city, (v.get("city") or {}).get("name") or ""):
            return s
    return None


class SetlistFMClient:
    def __init__(
        self,
        cache_dir: Path,
        api_key: str,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        rate_limit_s: float = 1.0,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.client = client or httpx.Client(
            timeout=30,
            headers={"x-api-key": api_key, "accept": "application/json",
                     "user-agent": "llama-radio/0.1"},
        )
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.rate_limit_s = rate_limit_s
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.rate_limit_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def setlist(self, artist: str, date: str,
                venue: str | None = None, city: str | None = None) -> dict | None:
        """The setlist.fm setlist for (artist, date) matching venue/city, or None."""
        key = "slfm_" + hashlib.sha1(f"{artist}|{date}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = self._search(artist, date)
            if data is None:
                return None  # transient failure: try again next run
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(path)
        return _pick(data.get("setlist", []), venue, city)

    def _search(self, artist: str, date: str) -> dict | None:
        y, m, d = date.split("-")
        params = {"artistName": artist, "date": f"{d}-{m}-{y}"}
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.client.get(SEARCH_URL, params=params)
            except httpx.TransportError as err:
                log.warning("setlist.fm request failed: %s", err)
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
                continue
            if resp.status_code == 404:
                return {"setlist": []}  # documented "no setlists found"
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("setlist.fm returned %s", resp.status_code)
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
                continue
            if resp.status_code >= 400:
                log.warning("setlist.fm returned %s for %s", resp.status_code, params)
                return None
            return resp.json()
        return None


def make_client(config: Config) -> SetlistFMClient | None:
    key = os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key
    if not key:
        return None
    return SetlistFMClient(config.root / "cache", key)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/setlistfm.py tests/test_setlistfm.py
git commit -m "feat: best-effort setlist.fm client with venue matching and disk cache"
```

---

### Task 3: `structure.py` — title normalizer, setlist.fm converter, ranked pick-best

**Files:**
- Create: `src/llama/structure.py`
- Modify: `src/llama/models.py` (add `SourcedParse`)
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: `ParsedSetlist`, `SetlistItem` from `llama.models`; `normalize_song` from `llama.songs`.
- Produces:
  - model `SourcedParse(BaseModel)`: `source: str` (`"setlist.fm" | "chosen" | "lma:<identifier>" | "llm"`), `parsed: ParsedSetlist`
  - `norm_title(title: str) -> str` — strips a leading `E:`/`Encore:` marker, then `normalize_song` (which already erases trailing `>` segue arrows as punctuation)
  - `from_setlistfm(raw: dict) -> ParsedSetlist | None` — `None` for stubs (< 5 songs); skips `tape: true` songs; encore sets labeled `"encore"`, others `"1"`, `"2"`, … in order; all `segue=False`; `confidence="high"`
  - `rank_parses(parses: list[SourcedParse], target_count: int) -> SourcedParse | None` — pick-best; parses with zero items are unrankable; ties go to the earliest element (callers put the chosen recording first)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_structure.py`:

```python
from llama.models import ParsedSetlist, SetlistItem, SourcedParse
from llama.structure import from_setlistfm, norm_title, rank_parses


def sp(source, sets_titles, confidence="high"):
    """Helper: build a SourcedParse from (set, title) pairs."""
    items = [SetlistItem(title=t, normalized=norm_title(t), set=s, segue=False)
             for s, t in sets_titles]
    return SourcedParse(source=source, parsed=ParsedSetlist(items=items, confidence=confidence))


def test_norm_title_strips_encore_prefix_and_segue_arrow():
    assert norm_title("E: It's All Over Now, Baby Blue") == "its all over now baby blue"
    assert norm_title("Encore: Casey Jones") == "casey jones"
    assert norm_title("China Cat Sunflower >") == "china cat sunflower"
    assert norm_title("Morning Dew") == "morning dew"


def test_from_setlistfm_converts_sets_and_encore():
    raw = {"sets": {"set": [
        {"song": [{"name": "US Blues"}, {"name": "Mexicali Blues"}, {"name": "Loser"}]},
        {"song": [{"name": "Big River"}, {"name": "Dark Star"},
                  {"name": "Intro Tape", "tape": True}]},
        {"encore": 1, "song": [{"name": "Casey Jones"}]},
    ]}}
    p = from_setlistfm(raw)
    assert p.confidence == "high"
    assert [(i.set, i.title) for i in p.items] == [
        ("1", "US Blues"), ("1", "Mexicali Blues"), ("1", "Loser"),
        ("2", "Big River"), ("2", "Dark Star"), ("encore", "Casey Jones"),
    ]
    assert all(i.segue is False for i in p.items)


def test_from_setlistfm_rejects_stubs():
    raw = {"sets": {"set": [{"song": [{"name": "One"}, {"name": "Two"}]}]}}
    assert from_setlistfm(raw) is None
    assert from_setlistfm({}) is None


FIVE = [("1", "A"), ("1", "B"), ("2", "C"), ("2", "D"), ("encore", "E")]
FLAT = [("1", "A"), ("1", "B"), ("1", "C"), ("1", "D"), ("1", "E")]


def test_rank_setlistfm_beats_lma_high():
    best = rank_parses([sp("chosen", FIVE, "high"), sp("setlist.fm", FIVE, "high")], 5)
    assert best.source == "setlist.fm"


def test_rank_confidence_then_multiset_then_count():
    assert rank_parses([sp("lma:a", FIVE, "medium"), sp("lma:b", FIVE, "high")], 5).source == "lma:b"
    assert rank_parses([sp("lma:flat", FLAT, "high"), sp("lma:sets", FIVE, "high")], 5).source == "lma:sets"
    close = sp("lma:close", FIVE, "high")
    far = sp("lma:far", FIVE + [("encore", "F"), ("encore", "G")], "high")
    assert rank_parses([far, close], 5).source == "lma:close"


def test_rank_ties_go_to_first_listed_and_empty_is_unrankable():
    a, b = sp("chosen", FIVE, "high"), sp("lma:copy", FIVE, "high")
    assert rank_parses([a, b], 5).source == "chosen"
    assert rank_parses([SourcedParse(source="chosen", parsed=ParsedSetlist())], 5) is None
    assert rank_parses([], 5) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_structure.py -q`
Expected: FAIL with `ImportError` (no `SourcedParse` / no `llama.structure`)

- [ ] **Step 3: Implement**

In `src/llama/models.py`, directly after `ParsedSetlist`:

```python
class SourcedParse(BaseModel):
    source: str  # "setlist.fm" | "chosen" | "lma:<identifier>" | "llm"
    parsed: ParsedSetlist
```

Create `src/llama/structure.py`:

```python
"""Performance-level set structure: convert, rank, blend, align, guard.

Pure logic - no I/O. Set boundaries, song order, and segues are properties
of the performance, not of any one recording, so they are recovered from
the best source across all recordings (and setlist.fm) and aligned onto
the chosen recording's tracks.
"""
import re

from llama.models import ParsedSetlist, SetlistItem, SourcedParse
from llama.songs import normalize_song

# "E: Baby Blue" / "Encore: Casey Jones" - structure markers embedded in a title.
_STRUCTURE_PREFIX = re.compile(r"^\s*(?:e|encore)\s*:\s*", re.I)

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def norm_title(title: str) -> str:
    return normalize_song(_STRUCTURE_PREFIX.sub("", title))


def from_setlistfm(raw: dict) -> ParsedSetlist | None:
    sets = (raw.get("sets") or {}).get("set") or []
    items: list[SetlistItem] = []
    set_no = 0
    for s in sets:
        if s.get("encore"):
            label = "encore"
        else:
            set_no += 1
            label = str(set_no)
        for song in s.get("song", []):
            name = (song.get("name") or "").strip()
            if not name or song.get("tape"):
                continue
            items.append(SetlistItem(title=name, normalized=normalize_song(name),
                                     set=label, segue=False))
    if len(items) < 5:
        return None  # a stub entry must not out-rank a rich LMA parse
    return ParsedSetlist(items=items, confidence="high")


def rank_parses(parses: list[SourcedParse], target_count: int) -> SourcedParse | None:
    candidates = [p for p in parses if p.parsed.items]
    if not candidates:
        return None

    def key(p: SourcedParse):
        multi_set = len({i.set for i in p.parsed.items}) > 1
        return (
            p.source == "setlist.fm",
            _CONF_RANK.get(p.parsed.confidence, 0),
            multi_set,
            -abs(len(p.parsed.items) - target_count),
        )

    # max() keeps the first maximal element, so callers list the chosen
    # recording first to win ties among copy-paste descriptions.
    return max(candidates, key=key)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/structure.py src/llama/models.py tests/test_structure.py
git commit -m "feat: setlist.fm conversion and ranked pick-best for structure sources"
```

---

### Task 4: `structure.py` — segue blending

**Files:**
- Modify: `src/llama/structure.py`
- Test: `tests/test_structure.py` (append)

**Interfaces:**
- Consumes: `ParsedSetlist`, `SetlistItem`.
- Produces: `blend_segues(winner: ParsedSetlist, lma: ParsedSetlist | None) -> ParsedSetlist` — returns `winner` with segue flags overlaid from `lma` by in-order normalized-title occurrence matching (repeated songs pair with the right occurrence). No-op when `lma` is `None`, the same object, or has no segues.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_structure.py`:

```python
from llama.structure import blend_segues


def pl(*titles_segues, confidence="high"):
    items = [SetlistItem(title=t, normalized=norm_title(t), set="1", segue=g)
             for t, g in titles_segues]
    return ParsedSetlist(items=items, confidence=confidence)


def test_blend_overlays_lma_segues_onto_winner():
    winner = pl(("China Cat Sunflower", False), ("I Know You Rider", False), ("Loser", False))
    lma = pl(("China Cat Sunflower", True), ("I Know You Rider", False), ("Loser", False))
    out = blend_segues(winner, lma)
    assert [i.segue for i in out.items] == [True, False, False]
    assert out.confidence == winner.confidence


def test_blend_matches_repeated_songs_in_order():
    winner = pl(("Not Fade Away", False), ("GDTRFB", False), ("Not Fade Away", False))
    lma = pl(("Not Fade Away", True), ("GDTRFB", True), ("Not Fade Away", False))
    out = blend_segues(winner, lma)
    assert [i.segue for i in out.items] == [True, True, False]


def test_blend_noop_when_lma_missing_same_or_segue_free():
    winner = pl(("A", False), ("B", False))
    assert blend_segues(winner, None) is winner
    assert blend_segues(winner, winner) is winner
    assert blend_segues(winner, pl(("A", False), ("B", False))) is winner
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_structure.py -q`
Expected: FAIL with `ImportError: cannot import name 'blend_segues'`

- [ ] **Step 3: Implement**

Append to `src/llama/structure.py`:

```python
def blend_segues(winner: ParsedSetlist, lma: ParsedSetlist | None) -> ParsedSetlist:
    """Overlay LMA segue notation onto the winning parse (taper descriptions
    carry segues; setlist.fm generally does not)."""
    if lma is None or lma is winner or not any(i.segue for i in lma.items):
        return winner
    pools: dict[str, list[SetlistItem]] = {}
    for it in lma.items:
        pools.setdefault(it.normalized, []).append(it)
    items = []
    for it in winner.items:
        pool = pools.get(it.normalized)
        src = pool.pop(0) if pool else None
        items.append(it.model_copy(update={"segue": src.segue}) if src else it)
    return ParsedSetlist(items=items, confidence=winner.confidence)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/structure.py tests/test_structure.py
git commit -m "feat: blend LMA segue notation onto the winning structure source"
```

---

### Task 5: `structure.py` — ordered track alignment

**Files:**
- Modify: `src/llama/structure.py`, `src/llama/models.py` (add `AlignResult`), `src/llama/songs.py` (one alias)
- Test: `tests/test_structure.py` (append), `tests/test_songs.py` (append)

**Interfaces:**
- Consumes: `Track`, `ParsedSetlist` from `llama.models`; `norm_title` (Task 3).
- Produces:
  - model `AlignResult(BaseModel)`: `sets: list[str]`, `segues: list[bool]`, `matched: list[bool]` (all parallel to the track list), `coverage: float`, `conflicts: list[str]` (canonical titles never matched)
  - `align(tracks: list[Track], canonical: ParsedSetlist, lookahead: int = 3) -> AlignResult` — in-order two-pointer with lookahead: each track matches the next canonical item with the same `norm_title` within `lookahead` items (tolerates split/merged tracks and repeated songs); unmatched tracks inherit the previous track's set (first defaults `"1"`) with `segue=False`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_songs.py`:

```python
def test_gdtrfb_going_feelin_variant_normalizes():
    assert normalize_song("Going Down The Road Feelin' Bad") == "goin down the road feeling bad"
```

Append to `tests/test_structure.py`:

```python
from llama.models import Track
from llama.structure import align


def tr(idx, title):
    return Track(index=idx, set="1", title=title, filename=f"t{idx:02d}.mp3",
                 duration_sec=300.0, segue=False, title_source="tags")


def canon(*rows):
    """rows: (set, title, segue)"""
    items = [SetlistItem(title=t, normalized=norm_title(t), set=s, segue=g)
             for s, t, g in rows]
    return ParsedSetlist(items=items, confidence="high")


def test_align_exact_match():
    c = canon(("1", "A", True), ("1", "B", False), ("2", "C", False))
    r = align([tr(1, "A"), tr(2, "B"), tr(3, "C")], c)
    assert r.sets == ["1", "1", "2"]
    assert r.segues == [True, False, False]
    assert r.coverage == 1.0
    assert r.conflicts == []


def test_align_repeated_songs_map_in_order():
    c = canon(("2", "Not Fade Away", True), ("2", "GDTRFB", True), ("2", "Not Fade Away", False),
              ("encore", "Baby Blue", False))
    r = align([tr(1, "Not Fade Away >"), tr(2, "GDTRFB >"), tr(3, "Not Fade Away"),
               tr(4, "E: Baby Blue")], c)
    assert r.sets == ["2", "2", "2", "encore"]
    assert r.segues == [True, True, False, False]
    assert r.coverage == 1.0


def test_align_skips_merged_canonical_item_via_lookahead():
    # Recording merges "WRS Part 1" into the Prelude file: canonical has 3 items,
    # the recording 2 files. "Let It Grow" is found 2 items ahead.
    c = canon(("2", "Weather Report Suite Prelude", True),
              ("2", "Weather Report Suite Part 1", True),
              ("2", "Let It Grow", True),
              ("2", "Row Jimmy", False),
              ("2", "Ship of Fools", False))
    r = align([tr(1, "Weather Report Suite Prelude >"), tr(2, "Let It Grow >"),
               tr(3, "Row Jimmy"), tr(4, "Ship of Fools")], c)
    assert r.sets == ["2", "2", "2", "2"]
    assert r.coverage == 1.0
    assert r.conflicts == ["Weather Report Suite Part 1"]


def test_align_unmatched_tracks_inherit_previous_set():
    c = canon(("1", "A", False), ("2", "B", False))
    r = align([tr(1, "A"), tr(2, "Tuning"), tr(3, "B"), tr(4, "Crowd")], c)
    assert r.sets == ["1", "1", "2", "2"]
    assert r.matched == [True, False, True, False]
    assert r.coverage == 0.5
    assert r.segues[1] is False


def test_align_first_track_unmatched_defaults_to_set_1():
    c = canon(("1", "B", False))
    r = align([tr(1, "Intro"), tr(2, "B")], c)
    assert r.sets == ["1", "1"]


def test_align_empty_inputs():
    r = align([], canon(("1", "A", False)))
    assert r.sets == [] and r.coverage == 0.0
    r = align([tr(1, "A")], ParsedSetlist())
    assert r.sets == ["1"] and r.coverage == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_structure.py tests/test_songs.py -q`
Expected: FAIL (`ImportError: cannot import name 'align'`; alias test fails with `'going down the road feelin bad'`)

- [ ] **Step 3: Implement**

In `src/llama/songs.py`, add to `DEFAULT_ALIASES` (next to the other GDTRFB aliases):

```python
    "going down the road feelin bad": "goin down the road feeling bad",
```

In `src/llama/models.py`, after `SourcedParse`:

```python
class AlignResult(BaseModel):
    sets: list[str]
    segues: list[bool]
    matched: list[bool]
    coverage: float
    conflicts: list[str] = Field(default_factory=list)
```

Append to `src/llama/structure.py` (extend the models import to include `AlignResult` and `Track`):

```python
def align(tracks: list["Track"], canonical: ParsedSetlist, lookahead: int = 3) -> "AlignResult":
    """Map canonical set/segue structure onto tracks, in recording order.

    Two-pointer with lookahead: a track matches the next canonical item with
    the same normalized title within `lookahead` positions, so repeated songs
    pair with the right occurrence and merged/split tracks skip over the gap.
    """
    items = canonical.items
    sets: list[str] = []
    segues: list[bool] = []
    matched: list[bool] = []
    matched_idx: set[int] = set()
    j = 0
    for t in tracks:
        norm = norm_title(t.title)
        hit = next(
            (k for k in range(j, min(j + 1 + lookahead, len(items)))
             if items[k].normalized == norm),
            None,
        )
        if hit is None:
            sets.append(sets[-1] if sets else "1")
            segues.append(False)
            matched.append(False)
        else:
            sets.append(items[hit].set)
            segues.append(items[hit].segue)
            matched.append(True)
            matched_idx.add(hit)
            j = hit + 1
    coverage = (sum(matched) / len(tracks)) if tracks else 0.0
    conflicts = [it.title for k, it in enumerate(items) if k not in matched_idx]
    return AlignResult(sets=sets, segues=segues, matched=matched,
                       coverage=coverage, conflicts=conflicts)
```

(Import both from `llama.models` at the top: `from llama.models import AlignResult, ParsedSetlist, SetlistItem, SourcedParse, Track`.)

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/structure.py src/llama/models.py src/llama/songs.py tests/test_structure.py tests/test_songs.py
git commit -m "feat: ordered position-aware alignment of canonical structure onto tracks"
```

---

### Task 6: `structure.py` — long-flat-show guard

**Files:**
- Modify: `src/llama/structure.py`
- Test: `tests/test_structure.py` (append)

**Interfaces:**
- Consumes: `Track`.
- Produces: `structure_guard(tracks: list[Track], set_breaks: list[int], min_minutes: int = 100, min_tracks: int = 16) -> str | None` — returns the flag string `"single-set structure for a long show"` or `None`. Duration arm uses the sum of known `duration_sec` (missing durations blind only that arm).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_structure.py`:

```python
from llama.structure import structure_guard


def _tracks(n, dur=300.0):
    return [Track(index=i + 1, set="1", title=f"S{i}", filename=f"t{i}.mp3",
                  duration_sec=dur, segue=False, title_source="tags") for i in range(n)]


def test_guard_fires_on_long_duration_no_breaks():
    assert structure_guard(_tracks(10, dur=700.0), []) == "single-set structure for a long show"


def test_guard_fires_on_track_count_even_without_durations():
    assert structure_guard(_tracks(20, dur=None), []) == "single-set structure for a long show"


def test_guard_silent_on_short_single_set_and_any_multiset():
    assert structure_guard(_tracks(8, dur=300.0), []) is None          # 40 min, 8 tracks
    assert structure_guard(_tracks(30, dur=700.0), [11]) is None       # has a break


def test_guard_respects_thresholds():
    assert structure_guard(_tracks(10, dur=700.0), [], min_minutes=200) is None
    assert structure_guard(_tracks(10, dur=None), [], min_tracks=10) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_structure.py -q`
Expected: FAIL with `ImportError: cannot import name 'structure_guard'`

- [ ] **Step 3: Implement**

Append to `src/llama/structure.py`:

```python
def structure_guard(tracks: list[Track], set_breaks: list[int],
                    min_minutes: int = 100, min_tracks: int = 16) -> str | None:
    """A long show with zero set breaks is implausible - flag for review."""
    if set_breaks or not tracks:
        return None
    total = sum(t.duration_sec for t in tracks if t.duration_sec)
    long_by_time = total >= min_minutes * 60
    long_by_count = len(tracks) >= min_tracks
    if long_by_time or long_by_count:
        return "single-set structure for a long show"
    return None
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/structure.py tests/test_structure.py
git commit -m "feat: needs-review guard for long shows with no set breaks"
```

---

### Task 7: `align_structure` LLM touchpoint (prompt, schema, tier, applier)

**Files:**
- Create: `src/llama/prompts/align_structure.md`
- Modify: `src/llama/models.py` (add `AlignedTrack`, `AlignedStructure`), `src/llama/llm/__init__.py` (tier), `src/llama/structure.py` (applier)
- Test: `tests/test_prompts.py`, `tests/test_model_tiers.py`, `tests/test_structure.py` (append)

**Interfaces:**
- Consumes: `AlignResult` (Task 5).
- Produces:
  - models `AlignedTrack(BaseModel)` (`index: int`, `set: str`, `segue: bool = False`, `matched_title: str = ""`) and `AlignedStructure(BaseModel)` (`tracks: list[AlignedTrack]`)
  - prompt `align_structure.md` with placeholders `{{tracks}}` and `{{setlist}}`
  - `DEFAULT_TIERS["align_structure"] = "medium"`
  - `apply_llm_alignment(tracks: list[Track], resp: AlignedStructure) -> AlignResult | None` — `None` unless the response covers exactly indices 1..N with sets in `{"1","2","3","encore"}`; coverage = fraction of tracks with non-empty `matched_title`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_prompts.py`, add to `EXPECTED`:

```python
    "align_structure": {"tracks", "setlist"},
```

In `tests/test_model_tiers.py::test_tables_match_spec`, add to the expected `DEFAULT_TIERS` dict:

```python
        "align_structure": "medium",
```

Append to `tests/test_structure.py`:

```python
from llama.models import AlignedStructure, AlignedTrack
from llama.structure import apply_llm_alignment


def test_apply_llm_alignment_builds_result():
    tracks = _tracks(3)
    resp = AlignedStructure(tracks=[
        AlignedTrack(index=1, set="1", segue=True, matched_title="A"),
        AlignedTrack(index=3, set="encore", segue=False, matched_title=""),
        AlignedTrack(index=2, set="2", segue=False, matched_title="B"),
    ])
    r = apply_llm_alignment(tracks, resp)
    assert r.sets == ["1", "2", "encore"]      # reordered by index
    assert r.segues == [True, False, False]
    assert r.matched == [True, True, False]
    assert abs(r.coverage - 2 / 3) < 1e-9


def test_apply_llm_alignment_rejects_bad_indices_or_sets():
    tracks = _tracks(2)
    missing = AlignedStructure(tracks=[AlignedTrack(index=1, set="1")])
    assert apply_llm_alignment(tracks, missing) is None
    bad_set = AlignedStructure(tracks=[AlignedTrack(index=1, set="1"),
                                       AlignedTrack(index=2, set="afterparty")])
    assert apply_llm_alignment(tracks, bad_set) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py tests/test_model_tiers.py tests/test_structure.py -q`
Expected: FAIL (prompt file missing, tier dict mismatch, `ImportError` on `AlignedStructure`)

- [ ] **Step 3: Implement**

Create `src/llama/prompts/align_structure.md`:

```markdown
You are aligning concert audio files to a known setlist for radio broadcast.

Audio tracks, in play order (index | filename | title | duration seconds):
{{tracks}}

Canonical setlist for this performance (authoritative set boundaries; ">" means
the song segues into the next):
{{setlist}}

Assign EVERY track to a set from the canonical setlist and say whether it
segues directly into the following track.

Respond with ONLY JSON in this shape:
{"tracks": [{"index": 1, "set": "1" | "2" | "3" | "encore",
             "segue": true | false,
             "matched_title": "<canonical song title, or \"\" if this track is not in the setlist>"}]}

Rules:
- Exactly one entry per track index, covering 1..N.
- Keep the canonical set boundaries; never invent a set that is not in the canonical setlist.
- Tracks that are not songs from the setlist (tuning, crowd, banter, soundcheck)
  get matched_title "" and the set of the surrounding tracks.
- Track titles may differ from canonical titles in spelling, abbreviation, or
  punctuation - match by the song, not the exact string.
Raw JSON only.
```

In `src/llama/models.py`, after `AlignResult`:

```python
class AlignedTrack(BaseModel):
    index: int
    set: str
    segue: bool = False
    matched_title: str = ""


class AlignedStructure(BaseModel):
    tracks: list[AlignedTrack]
```

In `src/llama/llm/__init__.py`, add to `DEFAULT_TIERS`:

```python
    "align_structure": "medium",
```

Append to `src/llama/structure.py` (extend the models import with `AlignedStructure`):

```python
_VALID_SETS = {"1", "2", "3", "encore"}


def apply_llm_alignment(tracks: list[Track], resp: AlignedStructure) -> AlignResult | None:
    """Convert an align_structure LLM response to an AlignResult, or None if
    the response does not cover exactly the track indices with valid sets."""
    by_idx = {a.index: a for a in resp.tracks}
    if set(by_idx) != set(range(1, len(tracks) + 1)) or len(by_idx) != len(resp.tracks):
        return None
    ordered = [by_idx[i] for i in range(1, len(tracks) + 1)]
    if any(a.set not in _VALID_SETS for a in ordered):
        return None
    matched = [bool(a.matched_title) for a in ordered]
    coverage = (sum(matched) / len(tracks)) if tracks else 0.0
    return AlignResult(sets=[a.set for a in ordered], segues=[a.segue for a in ordered],
                       matched=matched, coverage=coverage)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/prompts/align_structure.md src/llama/models.py src/llama/llm/__init__.py src/llama/structure.py tests/test_prompts.py tests/test_model_tiers.py tests/test_structure.py
git commit -m "feat: align_structure LLM touchpoint (prompt, schema, tier, applier)"
```

---

### Task 8: Fixtures — gd74-02-24 pair and setlist.fm responses; capture-script flag

**Files:**
- Modify: `scripts/capture_fixture.py`
- Create: `tests/fixtures/gd74_windsor_metadata.json`, `tests/fixtures/gd74_miller_metadata.json`, `tests/fixtures/slfm_gd_1974_02_24.json`

**Interfaces:**
- Produces: the three fixture files Task 9's tests load. Windsor = the structureless chosen recording (27 VBR MP3 files, tag titles like `China Cat Sunflower >` and `E: It's All Over Now, Baby Blue`, description with no set markers). Miller = the sibling whose description parses at high confidence into sets 1/2/encore (28 items). The slfm file is a setlist.fm **search response** (`{"setlist": [...]}`).

- [ ] **Step 1: Extend the capture script**

Replace `scripts/capture_fixture.py` with:

```python
"""Capture real API responses as test fixtures.

Usage:
  python scripts/capture_fixture.py <identifier> [out.json]
      archive.org metadata, slimmed to the fields tests use.
  python scripts/capture_fixture.py --setlistfm "<artist>" <YYYY-MM-DD> [out.json]
      setlist.fm search response (requires SETLISTFM_API_KEY).
"""
import json
import os
import sys
from pathlib import Path

import httpx


def capture_ia(identifier: str, out: Path | None) -> None:
    out = out or Path(f"tests/fixtures/{identifier}.json")
    data = httpx.get(f"https://archive.org/metadata/{identifier}", timeout=60).json()
    slim = {
        "metadata": data.get("metadata", {}),
        "files": [
            {k: f[k] for k in ("name", "source", "original", "format", "length", "md5", "title") if k in f}
            for f in data.get("files", [])
        ],
        "reviews": data.get("reviews", []),
    }
    out.write_text(json.dumps(slim, indent=2))
    print(f"wrote {out}")


def capture_setlistfm(artist: str, date: str, out: Path | None) -> None:
    key = os.environ["SETLISTFM_API_KEY"]
    y, m, d = date.split("-")
    out = out or Path(f"tests/fixtures/slfm_{artist.lower().replace(' ', '_')}_{date.replace('-', '_')}.json")
    resp = httpx.get(
        "https://api.setlist.fm/rest/1.0/search/setlists",
        params={"artistName": artist, "date": f"{d}-{m}-{y}"},
        headers={"x-api-key": key, "accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    out.write_text(json.dumps(resp.json(), indent=2))
    print(f"wrote {out}")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--setlistfm":
        capture_setlistfm(args[1], args[2], Path(args[3]) if len(args) > 3 else None)
    else:
        capture_ia(args[0], Path(args[1]) if len(args) > 1 else None)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Capture the two archive.org fixtures**

```bash
python scripts/capture_fixture.py gd74-02-24.sbd.windsor.199.sbefail.shnf tests/fixtures/gd74_windsor_metadata.json
python scripts/capture_fixture.py gd1974-02-24.sbd.miller.116902.flac16 tests/fixtures/gd74_miller_metadata.json
```

(Network required. If offline: both items' full metadata responses already sit in `~/.llama/cache/` as `md_gd74-02-24.sbd.windsor.199.sbefail.shnf.json` and `md_gd1974-02-24.sbd.miller.116902.flac16.json`; slim them with the same field list as `capture_ia` in a short Python snippet instead.)

- [ ] **Step 3: Verify the captured fixtures have the shapes Task 9 relies on**

```bash
python - <<'EOF'
import json
from llama.junk import filter_files
from llama.setlist import parse_setlist

w = json.load(open("tests/fixtures/gd74_windsor_metadata.json"))
kept, _ = filter_files(w["files"], want_format="VBR MP3")
assert len(kept) == 27, len(kept)
assert kept[-1]["title"] == "E: It's All Over Now, Baby Blue"
assert parse_setlist(w["metadata"]["description"]).confidence == "medium"
assert {i.set for i in parse_setlist(w["metadata"]["description"]).items} == {"1"}

m = json.load(open("tests/fixtures/gd74_miller_metadata.json"))
p = parse_setlist(m["metadata"]["description"])
assert p.confidence == "high" and {i.set for i in p.items} == {"1", "2", "encore"}
assert len(p.items) == 28
print("fixtures OK")
EOF
```

Expected: `fixtures OK`

- [ ] **Step 4: Create the setlist.fm fixture**

If `SETLISTFM_API_KEY` is available, capture the real thing:

```bash
python scripts/capture_fixture.py --setlistfm "Grateful Dead" 1974-02-24 tests/fixtures/slfm_gd_1974_02_24.json
```

Otherwise create `tests/fixtures/slfm_gd_1974_02_24.json` by hand with this content (correct per the setlist.fm response schema and this show's setlist; re-capture over it whenever a key is available):

```json
{
  "type": "setlists",
  "itemsPerPage": 20,
  "page": 1,
  "total": 1,
  "setlist": [
    {
      "id": "73d1f9bd",
      "eventDate": "24-02-1974",
      "artist": {"mbid": "6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6", "name": "Grateful Dead"},
      "venue": {
        "id": "23d63b83",
        "name": "Winterland",
        "city": {"name": "San Francisco", "state": "California", "stateCode": "CA",
                 "country": {"code": "US", "name": "United States"}}
      },
      "sets": {
        "set": [
          {"song": [
            {"name": "U.S. Blues"}, {"name": "Mexicali Blues"}, {"name": "Brown-Eyed Women"},
            {"name": "Beat It on Down the Line"}, {"name": "Candyman"}, {"name": "Jack Straw"},
            {"name": "China Cat Sunflower"}, {"name": "I Know You Rider"}, {"name": "El Paso"},
            {"name": "Loser"}, {"name": "Playing in the Band"}
          ]},
          {"song": [
            {"name": "Cumberland Blues"}, {"name": "It Must Have Been the Roses"},
            {"name": "Big River"}, {"name": "Bertha"}, {"name": "Weather Report Suite"},
            {"name": "Row Jimmy"}, {"name": "Ship of Fools"}, {"name": "The Promised Land"},
            {"name": "Dark Star"}, {"name": "Morning Dew"}, {"name": "Sugar Magnolia"},
            {"name": "Not Fade Away"}, {"name": "Goin' Down the Road Feeling Bad"},
            {"name": "Not Fade Away"}
          ]},
          {"encore": 1, "song": [{"name": "It's All Over Now, Baby Blue"}]}
        ]
      },
      "url": "https://www.setlist.fm/setlist/grateful-dead/1974/winterland-san-francisco-ca-73d1f9bd.html"
    }
  ]
}
```

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_fixture.py tests/fixtures/gd74_windsor_metadata.json tests/fixtures/gd74_miller_metadata.json tests/fixtures/slfm_gd_1974_02_24.json
git commit -m "test: gd74-02-24 fixtures and setlist.fm capture mode"
```

---

### Task 9: Rewire gather — consensus, alignment, guard, provenance

This is the core task: gather builds the canonical setlist from all recordings (+ optional setlist.fm), `titles.py` stops assigning structure, and the 1974-02-24 regression is fixed.

**Files:**
- Modify: `src/llama/stages/gather.py`, `src/llama/titles.py`, `src/llama/models.py` (add `StructureInfo`, `Show.structure`)
- Test: `tests/test_stage_gather.py` (extend), `tests/test_titles.py` (adjust)

**Interfaces:**
- Consumes: everything from Tasks 3–7 (`SourcedParse`, `norm_title`, `from_setlistfm`, `rank_parses`, `blend_segues`, `align`, `apply_llm_alignment`, `structure_guard`, `AlignedStructure`), `StructureConfig` (Task 1), `SetlistFMClient.setlist` (Task 2).
- Produces:
  - `run_gather(show_ws, ia, provider, candidate, identifier, audio_format="mp3", force=False, align_provider=None, setlistfm=None, structure_cfg=None) -> Show` — the three new keyword args default to off, so existing callers (`pipeline.process_show`) stay valid until Task 10.
  - model `StructureInfo(BaseModel)`: `source: str`, `alignment: str` (`"deterministic" | "llm"`), `coverage: float`, `conflicts: list[str]`
  - `Show.structure: StructureInfo | None = None`
  - `resolve_titles(kept_files, setlist, sibling_titles=None) -> list[Track]` — same signature, but every returned track now has placeholder `set="1"`, `segue=False`; structure is stamped by gather.

- [ ] **Step 1: Write the failing regression tests**

In `tests/test_stage_gather.py`, replace the module header block (imports through `make_candidate`) with:

```python
import json
from pathlib import Path

from llama.config import StructureConfig
from llama.llm.fake import FakeProvider
from llama.models import Candidate, RecordingSummary
from llama.setlistfm import SetlistFMClient
from llama.stages.gather import run_gather
from llama.workspace import ShowWorkspace

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"
W_IDENT = "gd74-02-24.sbd.windsor.199.sbefail.shnf"
M_IDENT = "gd1974-02-24.sbd.miller.116902.flac16"


class StubIA:
    """Serves one metadata dict for every identifier (single-recording tests)."""

    def __init__(self, md=None):
        self.md = md or json.loads(FIXTURE.read_text())

    def metadata(self, identifier):
        return self.md


class MultiIA:
    """Serves per-identifier metadata (sibling-consensus tests)."""

    def __init__(self, mapping):
        self.mapping = mapping

    def metadata(self, identifier):
        return self.mapping[identifier]


def make_candidate():
    return Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
        date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        recordings=[RecordingSummary(identifier=IDENT)],
    )


def gd74_candidate():
    return Candidate(
        performance_id="GratefulDead/1974-02-24", collection="GratefulDead",
        date="1974-02-24", venue="Winterland Arena", city="San Francisco, CA",
        recordings=[RecordingSummary(identifier=W_IDENT), RecordingSummary(identifier=M_IDENT)],
    )


def gd74_ia():
    return MultiIA({
        W_IDENT: json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text()),
        M_IDENT: json.loads((FIXTURES / "gd74_miller_metadata.json").read_text()),
    })
```

Then append the new tests:

```python
def test_gather_recovers_structure_from_sibling(tmp_path: Path):
    """Regression: gratefuldead-1974-02-24 shipped with every track in set 1."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT)
    assert len(show.tracks) == 27
    sets = [t.set for t in show.tracks]
    assert sets[:11] == ["1"] * 11                     # US Blues .. Playin' In The Band
    assert sets[11:26] == ["2"] * 15                   # Cumberland Blues .. Not Fade Away
    assert sets[26] == "encore"                        # E: It's All Over Now, Baby Blue
    assert show.set_breaks == [11, 26]
    assert show.structure is not None
    assert show.structure.source == f"lma:{M_IDENT}"
    assert show.structure.alignment == "deterministic"
    assert show.structure.coverage == 1.0
    # segues from the sibling's taper notation
    assert show.tracks[6].segue is True                # China Cat Sunflower >
    assert show.tracks[12].segue is False              # Roses: windsor's own junk parse said True
    assert show.needs_review is False


def test_gather_setlistfm_wins_with_lma_segues(tmp_path: Path):
    import httpx

    slfm_body = json.loads((FIXTURES / "slfm_gd_1974_02_24.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=slfm_body)

    client = SetlistFMClient(
        cache_dir=tmp_path / "slfm-cache", api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_s=0, rate_limit_s=0,
    )
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT,
                      setlistfm=client)
    assert show.structure.source == "setlist.fm"
    assert show.set_breaks == [11, 26]
    assert show.tracks[6].segue is True                # blended back from the LMA parse


def test_gather_flags_long_flat_show(tmp_path: Path):
    md = json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text())
    ident = W_IDENT
    cand = Candidate(
        performance_id="GratefulDead/1974-02-24", collection="GratefulDead",
        date="1974-02-24", venue="Winterland Arena", city="San Francisco, CA",
        recordings=[RecordingSummary(identifier=ident)],   # no structured sibling
    )
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), cand, ident)
    assert show.needs_review is True
    assert "single-set structure for a long show" in show.review_flags


def test_gather_low_coverage_uses_llm_alignment(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    # Wreck the tag titles so deterministic alignment can't match them,
    # while the description still yields a good canonical setlist.
    for i, f in enumerate(f for f in md["files"] if f.get("format") == "VBR MP3"):
        f["title"] = f"Track {i + 1}"
    llm_resp = json.dumps({"tracks": [
        {"index": 1, "set": "1", "segue": False, "matched_title": "Morning Dew"},
        {"index": 2, "set": "1", "segue": True, "matched_title": "China Cat Sunflower"},
        {"index": 3, "set": "1", "segue": False, "matched_title": "I Know You Rider"},
        {"index": 4, "set": "2", "segue": False, "matched_title": "Dark Star"},
        {"index": 5, "set": "2", "segue": False, "matched_title": "Eyes of the World"},
        {"index": 6, "set": "encore", "segue": False, "matched_title": "Johnny B. Goode"},
    ]})
    sws = ShowWorkspace(tmp_path / "show")
    align_fake = FakeProvider(completes=[llm_resp])
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      align_provider=align_fake)
    assert align_fake.calls, "align_structure LLM was not invoked"
    assert show.structure.alignment == "llm"
    assert [t.set for t in show.tracks] == ["1", "1", "1", "2", "2", "encore"]
    assert show.set_breaks == [3, 5]


def test_gather_llm_alignment_garbage_falls_back_and_flags(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    for i, f in enumerate(f for f in md["files"] if f.get("format") == "VBR MP3"):
        f["title"] = f"Track {i + 1}"
    garbage = json.dumps({"tracks": [{"index": 1, "set": "afterparty"}]})
    sws = ShowWorkspace(tmp_path / "show")
    align_fake = FakeProvider(completes=[garbage, garbage, garbage])  # exhausts retries
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      align_provider=align_fake)
    assert show.needs_review is True
    assert "low-confidence structure alignment" in show.review_flags
    assert show.structure.alignment == "deterministic"
```

Also adjust `tests/test_titles.py`: any assertion that `resolve_titles` returns real set numbers or segue flags now expects placeholders (`set == "1"`, `segue is False` for every track) — structure stamping moved to gather. Keep all title-cascade assertions (`title_source`, titles themselves) unchanged. `set_breaks()` tests are unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_gather.py -q`
Expected: new tests FAIL (`run_gather` lacks the new kwargs / sets are all `"1"` / no `structure` attr); the three pre-existing gather tests still pass.

- [ ] **Step 3: Implement — models**

In `src/llama/models.py`, after `AlignedStructure`:

```python
class StructureInfo(BaseModel):
    source: str  # "setlist.fm" | "chosen" | "lma:<identifier>" | "llm"
    alignment: str  # "deterministic" | "llm"
    coverage: float
    conflicts: list[str] = Field(default_factory=list)
```

and add to `Show`:

```python
    structure: StructureInfo | None = None
```

- [ ] **Step 4: Implement — titles.py stops assigning structure**

Replace `resolve_titles` in `src/llama/titles.py` with (note: `by_norm` and the set/segue lookups are gone; `normalize_song` import becomes unused — remove it):

```python
def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
) -> list[Track]:
    """Resolve track titles (tags -> setlist -> sibling -> unresolved).

    Sets and segues are placeholders here; llama.structure.align stamps the
    real values from the canonical performance setlist."""
    files = sorted(kept_files, key=lambda f: f["name"])
    n = len(files)
    aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        tag_title = str(f.get("title") or "").strip()
        if tag_title:
            title, source = tag_title, "tags"
        elif aligned:
            title, source = aligned[pos].title, "setlist"
        elif sibling_titles and len(sibling_titles) == n:
            title, source = sibling_titles[pos], "sibling"
        else:
            title, source = f["name"], "unresolved"
        tracks.append(
            Track(index=pos + 1, set="1", title=title, filename=f["name"],
                  duration_sec=length_seconds(f.get("length")), segue=False,
                  title_source=source)
        )
    return tracks
```

- [ ] **Step 5: Implement — gather orchestration**

Replace `src/llama/stages/gather.py` with:

```python
import logging

from llama.config import StructureConfig
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.ia_client import IAError
from llama.llm.provider import LLMError, TaskFailed
from llama.llm.tasks import run_json_task
from llama.models import (AlignedStructure, Candidate, ParsedSetlist, Show,
                          SourcedParse, StructureInfo)
from llama.setlist import parse_setlist
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, rank_parses, structure_guard)
from llama.titles import resolve_titles, set_breaks
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact

log = logging.getLogger("llama")


def _description(meta: dict) -> str:
    desc = meta.get("description") or ""
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    return str(desc)


def _creator(meta: dict) -> str | None:
    creator = meta.get("creator")
    if isinstance(creator, list):
        creator = creator[0] if creator else None
    return creator


def _sibling_titles(ia, candidate: Candidate, identifier: str, want: str, n: int) -> list[str] | None:
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        kept, _ = filter_files(ia.metadata(rec.identifier).get("files", []), want_format=want)
        if len(kept) == n and all(str(f.get("title") or "").strip() for f in kept):
            return [f["title"] for f in sorted(kept, key=lambda f: f["name"])]
    return None


def _collect_parses(ia, candidate: Candidate, identifier: str, chosen_meta: dict):
    """Parse every recording's description. Chosen recording first so it wins
    rank ties among copy-paste descriptions."""
    parses: list[SourcedParse] = []
    notes: list[str] = []
    descriptions: list[str] = []
    ordered = sorted(candidate.recordings, key=lambda r: r.identifier != identifier)
    for rec in ordered:
        if rec.identifier == identifier:
            meta = chosen_meta
        else:
            try:
                meta = ia.metadata(rec.identifier).get("metadata", {})
            except IAError as err:
                notes.append(f"could not fetch sibling {rec.identifier}: {err}")
                continue
        desc = _description(meta)
        descriptions.append(desc)
        source = "chosen" if rec.identifier == identifier else f"lma:{rec.identifier}"
        parses.append(SourcedParse(source=source, parsed=parse_setlist(desc)))
    return parses, notes, descriptions


def _format_tracks(tracks) -> str:
    return "\n".join(
        f"{t.index} | {t.filename} | {t.title} | {t.duration_sec or '?'}" for t in tracks
    )


def _format_setlist(canonical: ParsedSetlist) -> str:
    return "\n".join(
        f"[set {i.set}] {i.title}{' >' if i.segue else ''}" for i in canonical.items
    )


def run_gather(
    show_ws: ShowWorkspace,
    ia,
    provider,
    candidate: Candidate,
    identifier: str,
    audio_format: str = "mp3",
    force: bool = False,
    align_provider=None,
    setlistfm=None,
    structure_cfg: StructureConfig | None = None,
) -> Show:
    if not should_run(show_ws.show, force):
        return read_model(show_ws.show, Show)
    structure_cfg = structure_cfg or StructureConfig()

    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    want = FORMAT_BY_AUDIO[audio_format]
    kept, excluded = filter_files(md.get("files", []), want_format=want)

    # Canonical performance setlist: every recording's description, plus
    # setlist.fm when configured, ranked pick-best.
    parses, notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    if setlistfm is not None:
        raw = setlistfm.setlist(_creator(meta) or candidate.collection, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            parses.insert(0, SourcedParse(source="setlist.fm", parsed=converted))

    best = rank_parses(parses, target_count=len(kept))
    if best is None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                   description=longest)
            best = SourcedParse(source="llm", parsed=parsed)
    canonical = best.parsed if best else ParsedSetlist()
    if best is not None and best.source == "setlist.fm":
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)

    siblings = None
    if any(not str(f.get("title") or "").strip() for f in kept) and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
        siblings = _sibling_titles(ia, candidate, identifier, want, len(kept))
    tracks = resolve_titles(kept, canonical, sibling_titles=siblings)

    result = align(tracks, canonical)
    alignment = "deterministic"
    flags = []
    if canonical.items and result.coverage < structure_cfg.align_coverage_threshold:
        llm_result = None
        if align_provider is not None:
            try:
                resp = run_json_task(align_provider, "align_structure", AlignedStructure,
                                     tracks=_format_tracks(tracks),
                                     setlist=_format_setlist(canonical))
                llm_result = apply_llm_alignment(tracks, resp)
            except (TaskFailed, LLMError) as err:
                log.warning("align_structure failed: %s", err)
        if llm_result is not None and llm_result.coverage >= structure_cfg.align_coverage_threshold:
            result, alignment = llm_result, "llm"
        else:
            flags.append("low-confidence structure alignment")

    tracks = [t.model_copy(update={"set": s, "segue": g})
              for t, s, g in zip(tracks, result.sets, result.segues)]
    breaks = set_breaks(tracks)
    guard = structure_guard(tracks, breaks,
                            structure_cfg.guard_min_minutes, structure_cfg.guard_min_tracks)
    if guard:
        flags.append(guard)

    if any(t.title_source == "unresolved" for t in tracks):
        flags.append("unresolved track titles")
    if canonical.confidence == "low":
        flags.append("low-confidence setlist")
    if not tracks:
        flags.append("no playable tracks")

    structure_info = None
    if best is not None:
        structure_info = StructureInfo(source=best.source, alignment=alignment,
                                       coverage=result.coverage,
                                       conflicts=result.conflicts + notes)

    show = Show(
        performance_id=candidate.performance_id,
        identifier=identifier,
        artist=str(_creator(meta) or candidate.collection),
        date=candidate.date,
        venue=candidate.venue,
        city=candidate.city,
        tracks=tracks,
        set_breaks=breaks,
        excluded_files=excluded,
        lineage=meta.get("lineage") or meta.get("source"),
        source_url=f"https://archive.org/details/{identifier}",
        needs_review=bool(flags),
        review_flags=flags,
        structure=structure_info,
    )
    write_artifact(show_ws.show, show)
    write_artifact(show_ws.reviews, md.get("reviews", []))
    return show
```

- [ ] **Step 6: Run the full suite and reconcile**

Run: `pytest -q`
Expected: all PASS. Notes for expected interactions:
- The pre-existing gd73 gather tests pass unchanged: the chosen description parses high-confidence multi-set, wins the rank, aligns 1:1.
- `test_gather_flags_unresolved` (empty description, no tags) now may also collect the guard flag — its assertions (`needs_review`, "unresolved" in flags) still hold.
- If `tests/test_titles.py` asserts sets/segues from `resolve_titles`, update those assertions per Step 1's note.

- [ ] **Step 7: Commit**

```bash
git add src/llama/stages/gather.py src/llama/titles.py src/llama/models.py tests/test_stage_gather.py tests/test_titles.py
git commit -m "feat: gather builds consensus structure, aligns tracks, flags long flat shows"
```

---

### Task 10: Wire pipeline and CLI

**Files:**
- Modify: `src/llama/pipeline.py`, `src/llama/cli.py`
- Test: `tests/test_pipeline.py` (extend `fake_providers`; add a wiring test)

**Interfaces:**
- Consumes: `make_client` (Task 2), `run_gather` kwargs (Task 9).
- Produces:
  - `TASK_KEYS` includes `"align_structure"` (so `make_providers` builds its provider).
  - `process_show(run_ws, ia, ledger, entry, providers, run_name, audio_format="mp3", force=False, setlistfm=None, structure_cfg=None) -> Path | None`
  - `cli._execute` constructs the setlist.fm client once per run via `make_client(config)` and threads it plus `config.structure` into `process_show`.

- [ ] **Step 1: Write the failing test**

First, guard test isolation: a developer shell exporting `SETLISTFM_API_KEY` must not make offline tests build a real client. Create `tests/conftest.py` if it does not exist (or append to it):

```python
import pytest


@pytest.fixture(autouse=True)
def _no_ambient_setlistfm_key(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
```

(Task 11's live test captures the key at module import time — before this per-test fixture deletes it — so `-m live` runs still see it.)

In `tests/test_pipeline.py`, add `"align_structure": FakeProvider(),` to the `fake_providers` dict, and append:

```python
def test_make_providers_includes_align_structure():
    from llama.config import Config
    from llama.pipeline import make_providers

    assert "align_structure" in make_providers(Config())
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `pytest tests/test_pipeline.py -q`
Expected: `test_make_providers_includes_align_structure` FAILS (`'align_structure' not in dict`); the end-to-end tests still pass.

- [ ] **Step 3: Implement**

In `src/llama/pipeline.py`:

- add `"align_structure"` to `TASK_KEYS`;
- change `process_show`'s signature to add the two kwargs and pass them through:

```python
def process_show(
    run_ws: RunWorkspace,
    ia,
    ledger: Ledger,
    entry: ShortlistEntry,
    providers: dict,
    run_name: str,
    audio_format: str = "mp3",
    force: bool = False,
    setlistfm=None,
    structure_cfg=None,
) -> Path | None:
```

and the gather call becomes:

```python
        show = run_gather(show_ws, ia, providers["extract_setlist"], cand, identifier,
                          audio_format=audio_format, force=force,
                          align_provider=providers.get("align_structure"),
                          setlistfm=setlistfm, structure_cfg=structure_cfg)
```

(`providers.get` keeps hand-built provider dicts in older tests working.)

In `src/llama/cli.py`:

- add import: `from llama.setlistfm import make_client`
- in `_execute`, before the `for entry in chosen:` loop, add:

```python
    setlistfm = make_client(config)
```

- and pass it in the `process_show` call:

```python
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force, setlistfm=setlistfm, structure_cfg=config.structure)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS (end-to-end `find` test exercises the whole wiring with no key configured, i.e. `setlistfm=None`).

- [ ] **Step 5: Commit**

```bash
git add src/llama/pipeline.py src/llama/cli.py tests/test_pipeline.py
git commit -m "feat: wire align_structure provider and optional setlist.fm through pipeline and CLI"
```

---

### Task 11: Live smoke test and docs

**Files:**
- Modify: `tests/test_live_smoke.py` (append), `CLAUDE.md`

**Interfaces:**
- Consumes: `SetlistFMClient` (Task 2).
- Produces: opt-in live test; docs that match reality.

- [ ] **Step 1: Add the live test**

Append to `tests/test_live_smoke.py` (match the file's existing `pytest.mark.live` idiom — read it first; if it uses a shared marker/skip helper, reuse it):

```python
import os

import pytest

SETLISTFM_KEY = os.environ.get("SETLISTFM_API_KEY")  # read at import: see tests/conftest.py


@pytest.mark.live
@pytest.mark.skipif(not SETLISTFM_KEY, reason="needs SETLISTFM_API_KEY")
def test_setlistfm_live_winterland_1974(tmp_path):
    from llama.setlistfm import SetlistFMClient

    c = SetlistFMClient(tmp_path / "cache", SETLISTFM_KEY)
    got = c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena",
                    city="San Francisco, CA")
    assert got is not None
    songs = [s["name"] for st in got["sets"]["set"] for s in st["song"]]
    assert any("Dark Star" in s for s in songs)
```

Run: `pytest -q` (live test auto-skips without the key) and, if a key is available, `pytest -m live -q`.

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`:
- In the **LLM layer** bullet: change "Six named touchpoints" to "Seven named touchpoints".
- In the same bullet, after the sentence about the `fake` backend, add: "Set/segue structure is performance-level: gather builds a canonical setlist from every recording's description plus setlist.fm (optional, key via `SETLISTFM_API_KEY` or `[setlistfm] api_key`; absent key = best-effort LMA-only) and aligns it onto the chosen recording's tracks (`structure.py`), falling back to the `align_structure` LLM touchpoint for messy alignments."
- In **Quality philosophy**: extend the suspicious-output list "(unresolved track titles, duration mismatches, low-confidence setlist parse, DJ notes contradicting the setlist)" to also include "a long show with zero set breaks".

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: all PASS (live test skipped).

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_smoke.py CLAUDE.md
git commit -m "test+docs: setlist.fm live smoke test; document structure recovery"
```

---

## Verification after all tasks

- `pytest -q` — everything green, offline.
- Real-world check of the motivating bug (network + LLM backend required):
  `llama run ~/.llama/runs/2026-07-14-grateful-dead-shows-1973-1974-with-a-chi --stage gather --force` then confirm `shows/gratefuldead-1974-02-24/show.json` has `set_breaks: [11, 26]` and `structure.source` naming the miller sibling — then re-run the downstream stages (`--stage synthesize`, `--stage package`) so dj-notes and the manifest pick up the two-set structure.
