# Artist Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route artist-less fuzzy queries ("well-known folk/acoustic performer, '60s–'70s") through an artist-discovery step — LLM proposes artists from world knowledge, deterministic matching keeps the ones that exist among the LMA's 9,267 artist collections, search fans out per artist — instead of today's unsteered 500-row sweep.

**Architecture:** New `discover` stage (propose → match → `artists.json`) triggered only when `collection` and `artist` are both null and `soft_preferences` is set; `run_search` gains an optional per-artist fan-out; the CLI prints the artist list for interactive pruning (auto mode takes it as-is). Everything downstream (winnow onward) is untouched.

**Tech Stack:** Existing project (Python ≥3.11, pydantic v2, pytest). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-14-artist-discovery-design.md`.

## Global Constraints

- Trigger condition exactly: `criteria.collection is None and criteria.artist is None and criteria.soft_preferences` — otherwise discover never runs and no `artists.json` exists.
- Collections enumeration query exactly: `collection:etree AND mediatype:collection`, fields `["identifier", "title"]`, `rows=10000` (disk-cached by the existing IAClient).
- Matching: normalized (lowercase, apostrophes dropped, punctuation → space, whitespace collapsed) equality beats containment (either direction); one best collection per proposed name; first-listed collection wins ties; LLM order preserved; deduped; capped at `max_artists=10`.
- Zero matches: write the empty list; CLI reports `none of the proposed artists were found on the LMA - try naming an artist or broadening the style` to stderr and returns without searching.
- New LLM task key `propose_artists`, default tier `medium`. Prompt placeholders exactly: `query`, `soft_preferences`, `date_from`, `date_to`.
- `run_search(..., artists=None)` behavior byte-identical to today.
- Stage discipline: skip-if-exists unless force, atomic writes. Tests offline. Conventional commits.
- All existing tests keep passing (currently 124 passed, 2 deselected).

## File Structure

```
src/llama/models.py            # + ProposedArtists
src/llama/prompts/propose_artists.md  # new prompt
src/llama/llm/__init__.py      # + propose_artists in DEFAULT_TIERS
src/llama/stages/discover.py   # new: _norm, match_artists, run_discover
src/llama/workspace.py         # + RunWorkspace.artists path
src/llama/stages/search.py     # + artists fan-out parameter
src/llama/pipeline.py          # + propose_artists in TASK_KEYS
src/llama/cli.py               # discovery + interactive prune in _execute
README.md                      # fuzzy-query usage example
tests/: test_prompts.py, test_model_tiers.py, test_stage_discover.py (new),
        test_workspace.py, test_stage_search.py, test_cli_commands.py
```

---

### Task 1: ProposedArtists model, propose_artists prompt, tier default

**Files:**
- Modify: `src/llama/models.py` (append one model), `src/llama/llm/__init__.py` (DEFAULT_TIERS), `tests/test_prompts.py` (EXPECTED table), `tests/test_model_tiers.py` (pinned-tables test)
- Create: `src/llama/prompts/propose_artists.md`

**Interfaces:**
- Produces: `models.ProposedArtists(artists: list[str])`; prompt `propose_artists` loadable via `tasks.load_prompt`; `DEFAULT_TIERS["propose_artists"] == "medium"`. Task 2's `run_discover` calls `run_json_task(provider, "propose_artists", ProposedArtists, ...)`.

- [ ] **Step 1: Update the two pinned tests (they will fail until implementation)**

In `tests/test_prompts.py`, add to the `EXPECTED` dict:

```python
    "propose_artists": {"query", "soft_preferences", "date_from", "date_to"},
```

In `tests/test_model_tiers.py`, in `test_tables_match_spec`, replace the `DEFAULT_TIERS` assertion with:

```python
    assert DEFAULT_TIERS == {
        "interpret": "medium", "score_reviews": "medium",
        "light_research": "medium", "extract_setlist": "medium",
        "deep_research": "high", "synthesize": "high",
        "propose_artists": "medium",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py tests/test_model_tiers.py -q`
Expected: 2 FAIL (prompt file missing; DEFAULT_TIERS mismatch)

- [ ] **Step 3: Implement**

Append to `src/llama/models.py`:

```python
class ProposedArtists(BaseModel):
    artists: list[str] = Field(default_factory=list)
```

In `src/llama/llm/__init__.py`, add to `DEFAULT_TIERS`:

```python
    "propose_artists": "medium",
```

Create `src/llama/prompts/propose_artists.md`:

```markdown
Name well-known performers matching a radio programmer's style brief, for
lookup in archive.org's Live Music Archive (LMA) — a live-concert archive
built around taper-friendly acts.

Request: {{query}}
Style/mood guidance: {{soft_preferences}}
Era: {{date_from}} to {{date_to}}

List up to 25 artists, best fit first. Favor performers who:
- match the style and era of the request
- are well known enough to be widely written about
- plausibly permit audience taping (jam bands, folk, bluegrass, blues, and
  roots acts are heavily represented on the LMA; mainstream major-label pop
  mostly is not)

Respond with ONLY JSON: {"artists": ["Artist Name", ...]} — names as
commonly written, no commentary, no markdown fences.
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `pytest tests/test_prompts.py tests/test_model_tiers.py -q`
Expected: all pass (7 prompt cases now)
Run: `pytest -q`
Expected: 125 passed, 2 deselected

- [ ] **Step 5: Commit**

```bash
git add src/llama/models.py src/llama/llm/__init__.py src/llama/prompts/propose_artists.md tests/test_prompts.py tests/test_model_tiers.py
git commit -m "feat: add propose_artists prompt, model, and tier default"
```

---

### Task 2: discover stage

**Files:**
- Create: `src/llama/stages/discover.py`
- Modify: `src/llama/workspace.py` (RunWorkspace gains `artists` path)
- Test: `tests/test_stage_discover.py` (new), `tests/test_workspace.py` (one test appended)

**Interfaces:**
- Consumes: `models.ProposedArtists` + prompt from Task 1; `llm.tasks.run_json_task`; `workspace` helpers; `ia` duck-typed (`.search`).
- Produces: `discover.match_artists(proposed: list[str], collections: list[dict], max_artists: int = 10) -> list[dict]`; `discover.run_discover(ws, provider, ia, criteria, *, max_artists: int = 10, force: bool = False) -> list[dict]` (writes `artists.json` as `[{"identifier", "title"}]`); `RunWorkspace.artists` path (`<run>/artists.json`). Task 3's CLI calls `run_discover` and reads/rewrites `ws.artists`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workspace.py`:

```python
def test_run_workspace_artists_path(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r")
    assert ws.artists == ws.dir / "artists.json"
```

Create `tests/test_stage_discover.py`:

```python
import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Criteria
from llama.stages.discover import match_artists, run_discover
from llama.workspace import RunWorkspace

COLLECTIONS = [
    {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    {"identifier": "JoanBaez", "title": "Joan Baez"},
    {"identifier": "GratefulDead", "title": "Grateful Dead"},
    {"identifier": "JoanJett", "title": "Joan Jett"},
]


class StubIA:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def search(self, query, fields, rows=500):
        self.queries.append((query, rows))
        return self.docs


def crit() -> Criteria:
    return Criteria(query="well-known folk/acoustic performer 60s-70s",
                    soft_preferences="folk/acoustic, well known",
                    date_from="1960-01-01", date_to="1979-12-31")


def proposed(names):
    return json.dumps({"artists": names})


def test_discover_matches_orders_and_writes(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[proposed(["Joan Baez", "Doc Watson", "Nick Drake"])])
    ia = StubIA(COLLECTIONS)
    got = run_discover(ws, fake, ia, crit())
    assert got == [
        {"identifier": "JoanBaez", "title": "Joan Baez"},
        {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    ]  # LLM order kept; Nick Drake (not on LMA) dropped
    assert ia.queries[0][0] == "collection:etree AND mediatype:collection"
    assert ia.queries[0][1] == 10000
    assert json.loads(ws.artists.read_text()) == got


def test_equality_beats_containment_and_first_wins_ties():
    cols = [{"identifier": "JoanJett", "title": "Joan"},
            {"identifier": "JoanBaez", "title": "Joan Baez"}]
    assert match_artists(["Joan Baez"], cols)[0]["identifier"] == "JoanBaez"
    tie = [{"identifier": "A", "title": "The Seldom Scene Live"},
           {"identifier": "B", "title": "Seldom Scene (live)"}]
    assert match_artists(["Seldom Scene"], tie)[0]["identifier"] == "A"


def test_cap_and_dedup():
    cols = [{"identifier": f"A{i}", "title": f"Artist Number {i}"} for i in range(20)]
    names = [f"Artist Number {i}" for i in range(20)] + ["Artist Number 0"]
    got = match_artists(names, cols, max_artists=10)
    assert len(got) == 10
    assert len({a["identifier"] for a in got}) == 10


def test_zero_matches_writes_empty(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[proposed(["Nick Drake"])])
    assert run_discover(ws, fake, StubIA(COLLECTIONS), crit()) == []
    assert json.loads(ws.artists.read_text()) == []


def test_skip_if_exists(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    run_discover(ws, FakeProvider(completes=[proposed(["Joan Baez"])]),
                 StubIA(COLLECTIONS), crit())
    again = run_discover(ws, FakeProvider(), StubIA(COLLECTIONS), crit())
    assert again[0]["identifier"] == "JoanBaez"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_discover.py tests/test_workspace.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.stages.discover'` and missing `artists` attribute

- [ ] **Step 3: Implement**

In `src/llama/workspace.py`, add one line to `RunWorkspace.__init__` after `self.shortlist = ...`:

```python
        self.artists = self.dir / "artists.json"
```

Create `src/llama/stages/discover.py`:

```python
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
    first-listed collection wins ties; LLM order preserved; deduped; capped."""
    normed = [(c, _norm(str(c.get("title") or ""))) for c in collections if c.get("identifier")]
    out: list[dict] = []
    seen: set[str] = set()
    for name in proposed:
        n = _norm(name)
        if not n:
            continue
        best = None
        for c, ct in normed:
            if not ct:
                continue
            if ct == n:
                best = c
                break
            if best is None and (n in ct or ct in n):
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
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `pytest tests/test_stage_discover.py tests/test_workspace.py -q`
Expected: all pass
Run: `pytest -q`
Expected: 131 passed, 2 deselected

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/discover.py src/llama/workspace.py tests/test_stage_discover.py tests/test_workspace.py
git commit -m "feat: add artist-discovery stage (propose-then-match)"
```

---

### Task 3: Search fan-out, CLI integration, docs

**Files:**
- Modify: `src/llama/stages/search.py` (fan-out), `src/llama/pipeline.py` (TASK_KEYS), `src/llama/cli.py` (`_execute`), `README.md`
- Test: `tests/test_stage_search.py`, `tests/test_cli_commands.py` (extend)

**Interfaces:**
- Consumes: `discover.run_discover`, `RunWorkspace.artists` (Task 2).
- Produces: `run_search(ws, ia, criteria, artists: list[dict] | None = None, rows=500, force=False)`; `pipeline.TASK_KEYS` includes `"propose_artists"` (so `make_providers` builds its provider).

**Read before editing:** `src/llama/cli.py`'s current `_execute` — it contains per-show error isolation (try/except around `process_show`) and the `_parse_ranks` helper from the final fix wave. Your edit inserts a discovery block and changes ONE call; everything else in the function must be preserved exactly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stage_search.py`:

```python
def test_run_search_fans_out_per_artist(tmp_path: Path):
    docs_by_collection = {
        "JoanBaez": [{"identifier": "jb1963-11-23", "date": "1963-11-23T00:00:00Z",
                      "venue": "Club 47"}],
        "DocWatson": [{"identifier": "dw1964-03-07", "date": "1964-03-07T00:00:00Z",
                       "venue": "Ash Grove"}],
    }

    class FanStubIA:
        def __init__(self):
            self.queries = []

        def search(self, query, fields, rows=500):
            self.queries.append(query)
            for ident, docs in docs_by_collection.items():
                if f"collection:{ident}" in query:
                    return docs
            return []

    ws = RunWorkspace(tmp_path, "r1")
    ia = FanStubIA()
    artists = [{"identifier": "JoanBaez", "title": "Joan Baez"},
               {"identifier": "DocWatson", "title": "Doc and Merle Watson"}]
    crit = Criteria(query="q", date_from="1960-01-01", date_to="1969-12-31")
    cands = run_search(ws, ia, crit, artists=artists)
    assert len(ia.queries) == 2
    assert all("mediatype:etree" in q and "date:[1960-01-01 TO 1969-12-31]" in q
               for q in ia.queries)
    pids = sorted(c.performance_id for c in cands)
    assert pids == ["DocWatson/1964-03-07", "JoanBaez/1963-11-23"]
```

Append to `tests/test_cli_commands.py` (module already imports `json`, `Path`, `runner`, `cli`, `write_artifact`, `RunWorkspace`):

```python
FUZZY_CRITERIA = json.dumps({
    "query": "x", "collection": None, "artist": None,
    "date_from": "1960-01-01", "date_to": "1979-12-31",
    "setlist_constraints": [], "soft_preferences": "folk/acoustic, well known",
    "min_avg_rating": 3.5, "min_reviews": 3, "count": 1,
})

ARTIST_COLLECTIONS = [
    {"identifier": "JoanBaez", "title": "Joan Baez"},
    {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    {"identifier": "TownesVanZandt", "title": "Townes Van Zandt"},
]


class FuzzyFakeIA:
    def __init__(self, *args, **kwargs):
        self.etree_queries = []

    def search(self, query, fields, rows=500):
        if "mediatype:collection" in query:
            return ARTIST_COLLECTIONS
        self.etree_queries.append(query)
        return []  # no shows: pipeline ends at "No shows survived winnowing."


def fuzzy_providers(config):
    from llama.llm.fake import FakeProvider
    return {
        "interpret": FakeProvider(completes=[FUZZY_CRITERIA]),
        "propose_artists": FakeProvider(completes=[json.dumps(
            {"artists": ["Joan Baez", "Doc Watson", "Townes Van Zandt"]})]),
        "score_reviews": FakeProvider(),
        "light_research": FakeProvider(),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(),
        "synthesize": FakeProvider(),
    }


def _fuzzy_setup(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ia = FuzzyFakeIA()
    monkeypatch.setattr(cli, "make_providers", fuzzy_providers)
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: ia)
    return ia


def test_fuzzy_query_interactive_prune(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--run-name", "fz",
        "--config", str(tmp_path / "config.toml"),
    ], input="2\n")
    assert result.exit_code == 0, result.output
    assert "Doc and Merle Watson" in result.output
    assert len(ia.etree_queries) == 1
    assert "collection:DocWatson" in ia.etree_queries[0]
    saved = json.loads((tmp_path / "runs" / "fz" / "artists.json").read_text())
    assert [a["identifier"] for a in saved] == ["DocWatson"]


def test_fuzzy_query_auto_uses_all(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--auto", "--run-name", "fz2",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert len(ia.etree_queries) == 3


def test_fuzzy_query_zero_matches_exits_cleanly(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: {
        **fuzzy_providers(config),
        "propose_artists": __import__("llama.llm.fake", fromlist=["FakeProvider"]).FakeProvider(
            completes=[json.dumps({"artists": ["Nick Drake"]})]),
    })
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--auto", "--run-name", "fz3",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "none of the proposed artists" in result.output
    assert ia.etree_queries == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_search.py::test_run_search_fans_out_per_artist tests/test_cli_commands.py -q`
Expected: new tests FAIL (`artists` unexpected kwarg; prune/zero-match behavior absent)

- [ ] **Step 3: Implement — search fan-out**

In `src/llama/stages/search.py`, add to the imports:

```python
import logging

log = logging.getLogger("llama")
```

and replace `run_search` with:

```python
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
```

- [ ] **Step 4: Implement — pipeline key and CLI**

In `src/llama/pipeline.py`, add `"propose_artists"` to `TASK_KEYS`:

```python
TASK_KEYS = ["interpret", "score_reviews", "light_research",
             "extract_setlist", "deep_research", "synthesize", "propose_artists"]
```

In `src/llama/cli.py`: add the import

```python
from llama.stages.discover import run_discover
```

and in `_execute`, replace the line `run_search(ws, ia, criteria, force=force)` with:

```python
    artists = None
    if criteria.collection is None and criteria.artist is None and criteria.soft_preferences:
        artists = run_discover(ws, providers["propose_artists"], ia, criteria, force=force)
        if not artists:
            typer.echo("none of the proposed artists were found on the LMA - "
                       "try naming an artist or broadening the style", err=True)
            return
        if not auto:
            typer.echo("Proposed artists:")
            for i, a in enumerate(artists, 1):
                typer.echo(f"{i:2d}. {a.get('title') or a['identifier']}")
            picks = typer.prompt("Search which artists? (comma-separated, empty = all)",
                                 default="", show_default=False)
            wanted = _parse_ranks(picks)
            if wanted:
                artists = [a for i, a in enumerate(artists, 1) if i in wanted]
                write_artifact(ws.artists, artists)
    run_search(ws, ia, criteria, artists=artists, force=force)
```

(Everything else in `_execute` — the winnow call, shortlist printing, the per-show try/except loop — stays exactly as it is. If `_parse_ranks` has a different name in the current file, report BLOCKED rather than adapting.)

- [ ] **Step 5: Update README**

In `README.md`'s Use section, add after the existing `find` examples:

```markdown
    llama find "well-known folk/acoustic performer, 1960s-70s, highly rated"
                                     # artist-less queries propose artists first
                                     # (interactive runs let you prune the list)
```

- [ ] **Step 6: Run the new tests, then the full suite**

Run: `pytest tests/test_stage_search.py tests/test_cli_commands.py -q`
Expected: all pass
Run: `pytest -q`
Expected: 135 passed, 2 deselected

- [ ] **Step 7: Commit**

```bash
git add src/llama/stages/search.py src/llama/pipeline.py src/llama/cli.py README.md tests/test_stage_search.py tests/test_cli_commands.py
git commit -m "feat: fan search out across discovered artists with interactive prune"
```

---

## Plan Self-Review Notes

- **Spec coverage:** trigger condition (Task 3 CLI block, exact expression); enumeration query/fields/rows (Task 2 impl + test assertion); propose prompt with 4 placeholders + 25-name framing (Task 1); matching rules incl. equality-beats-containment, tie-break, dedup, cap (Task 2 matcher + table tests); zero-match message verbatim + clean exit without searching (Task 3, tested); artists.json artifact with skip-if-exists (Task 2, tested — hand-edit replay follows from it); fan-out with per-query rows, per-artist grouping, `(date, performance_id)` sort, `artists=None` unchanged (Task 3 + existing tests); progress log line (Task 3 impl); TASK_KEYS/make_providers wiring (Task 3); README (Task 3). Out-of-scope items absent.
- **Placeholder scan:** clean.
- **Type consistency:** `run_discover(ws, provider, ia, criteria, *, max_artists=10, force=False) -> list[dict]` matches Task 3's call (positional through criteria, `force=` keyword); `artists: list[dict]` shape `{"identifier","title"}` consistent across matcher output, artifact, fan-out, and CLI display; `ws.artists` defined in Task 2, used in Task 3.
- **Task-23 lesson applied:** Task 3's CLI edit is anchor-based with an explicit read-current-code directive and a BLOCKED instruction on mismatch, rather than a full-function replacement written blind.
