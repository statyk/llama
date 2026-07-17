# Workspace UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move shows to a canonical `~/.llama/shows/<slug>/` library and give the CLI show-centric, name-addressed commands: `status`, `runs`, `redo`, `migrate`, plus name resolution for `show`/`deliver`/`run`/`review`.

**Architecture:** Shows get one directory per performance (slug = `slugify(performance_id)`, globally unique by construction). A new `catalog.py` derives show state from artifacts on disk + the ledger (never stored) and owns name resolution. A new `provenance.json` per show records which run processed it, the dossier, candidate, and script setting, so `redo` and `deliver` never need the originating run directory.

**Tech Stack:** Python 3.11+, typer, pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-17-workspace-ux-design.md`

## Global Constraints

- All tests offline and deterministic (`pytest -q`); fake LLM provider, `tmp_path` workspaces, `FakeIA` for archive.org.
- Never delete user data: migration collisions leave the loser in place with a warning.
- `redo --from` is required (no default stage); `research.md` is preserved by default.
- Show state precedence: `held` > `delivered` > `packaged` > `scripted` > `vetted` > `researched` > `gathered` > `selected`.
- Name resolution: exact match, else unique substring, else print candidates and exit 1. An existing path bypasses resolution.
- Commands that touch shows refuse to run on a legacy layout (shows nested under runs) with "run `llama migrate`".
- Follow existing code style: module-level helpers, comments only for non-obvious constraints, `typer.echo`, `write_artifact` for writes.

---

### Task 1: Provenance model, written by process_show

**Files:**
- Modify: `src/llama/models.py` (after `LedgerEntry`, ~line 213)
- Modify: `src/llama/workspace.py` (`ShowWorkspace.__init__`, ~line 42)
- Modify: `src/llama/pipeline.py` (`process_show`, ~line 44)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `llama.models.Provenance` (fields: `performance_id: str`, `run: str`, `dossier: str = ""`, `candidate: Candidate`, `script: bool = True`, `processed_at: str`), `ShowWorkspace.provenance` (Path to `provenance.json`), written by every `process_show` call before any stage runs. Tasks 4, 5, 8, 10 consume all of this.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py`:

```python
def test_process_show_writes_provenance(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973 best soundboard", "--auto", "--script",
        "--run-name", "provrun", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output

    from llama.models import Provenance
    from llama.workspace import read_model
    prov_path = (tmp_path / "runs" / "provrun" / "shows"
                 / "gratefuldead-1973-06-10" / "provenance.json")
    prov = read_model(prov_path, Provenance)
    assert prov.performance_id == "GratefulDead/1973-06-10"
    assert prov.run == "provrun"
    assert prov.script is True
    assert "monumental Dark Star" in prov.dossier          # rationale
    assert "Widely ranked top-5" in prov.dossier           # external reputation
    assert prov.candidate.collection == "GratefulDead"
    assert prov.processed_at  # ISO timestamp present
```

(The nested path is correct *for this task*; Task 3 moves it and updates this test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py::test_process_show_writes_provenance -q`
Expected: FAIL — `ImportError: cannot import name 'Provenance'`.

- [ ] **Step 3: Implement**

`src/llama/models.py`, after `LedgerEntry`:

```python
class Provenance(BaseModel):
    """Why this show exists: the run and shortlist context that processed it.
    Lets redo/deliver work standalone after the originating run is gone."""
    performance_id: str
    run: str
    dossier: str = ""  # shortlist rationale + external reputation, as fed to research
    candidate: Candidate
    script: bool = True
    processed_at: str  # ISO-8601 UTC
```

`src/llama/workspace.py`, in `ShowWorkspace.__init__` after `self.selection`:

```python
        self.provenance = dir / "provenance.json"
```

`src/llama/pipeline.py`: add `Provenance` to the `llama.models` import. In `process_show`, the dossier is currently built between gather and research (`dossier = entry.assessment.rationale ...`). Move that construction up and write provenance right after the `drop_stage_artifacts` block:

```python
    pid = cand.performance_id
    dossier = entry.assessment.rationale
    if entry.external_reputation:
        dossier += "\n\nExternal reputation: " + entry.external_reputation
    write_artifact(show_ws.provenance, Provenance(
        performance_id=pid, run=run_name, dossier=dossier, candidate=cand,
        script=script, processed_at=datetime.now(timezone.utc).isoformat(),
    ))
```

Delete the old two-line dossier construction further down (research keeps using the `dossier` variable). `write_artifact` is already imported? It is not — add it to the `llama.workspace` import line.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_pipeline.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/models.py src/llama/workspace.py src/llama/pipeline.py tests/test_pipeline.py
git commit -m "feat: record provenance.json per processed show"
```

---

### Task 2: Ledger.record idempotence

**Files:**
- Modify: `src/llama/ledger.py` (`record`, ~line 25)
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces: `Ledger.record(entry)` silently skips when an entry with the same `(performance_id, status, run)` already exists. Tasks 6 and 10 rely on replays not duplicating rows.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ledger.py` (match its existing imports/fixtures):

```python
def test_record_is_idempotent_per_performance_status_run(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    e = LedgerEntry(performance_id="GratefulDead/1973-06-10", artist="Grateful Dead",
                    date="1973-06-10", status="selected", run="r1",
                    recorded_at="2026-07-17T00:00:00+00:00")
    ledger.record(e)
    ledger.record(e.model_copy(update={"recorded_at": "2026-07-18T00:00:00+00:00"}))
    assert len(ledger.entries()) == 1
    # different status for the same performance still records
    ledger.record(e.model_copy(update={"status": "delivered"}))
    assert len(ledger.entries()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ledger.py -q`
Expected: FAIL — `assert 2 == 1`.

- [ ] **Step 3: Implement**

In `src/llama/ledger.py`, replace `record`:

```python
    def record(self, entry: LedgerEntry) -> None:
        """Append-once: a replayed run must not duplicate history rows."""
        for e in self.entries():
            if (e.performance_id, e.status, e.run) == (entry.performance_id, entry.status, entry.run):
                return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_ledger.py tests/test_pipeline.py tests/test_cli_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/ledger.py tests/test_ledger.py
git commit -m "fix: ledger.record skips duplicate (performance, status, run) rows"
```

---

### Task 3: Canonical shows layout

**Files:**
- Modify: `src/llama/workspace.py` (`RunWorkspace`, ~line 79)
- Modify: `tests/test_workspace.py:42`, `tests/test_pipeline.py` (paths at lines ~100, 134, 156, 171, 190, 220, 240, 275, 306 and the Task-1 test), `tests/test_cli_commands.py:194`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Produces: `RunWorkspace.show_ws(pid)` returns `ShowWorkspace(root / "shows" / slugify(pid))`; `RunWorkspace.root` attribute. Every later task assumes this layout.

- [ ] **Step 1: Update the workspace test to the new layout (failing)**

In `tests/test_workspace.py:42`, replace the nested-path assertion:

```python
    assert sws.dir == tmp_path / "shows" / "gratefuldead-1973-06-10"
```

(Adjust to that test's actual local variables — the run workspace there is built from `tmp_path`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_workspace.py -q`
Expected: FAIL on the changed assertion.

- [ ] **Step 3: Implement**

In `src/llama/workspace.py`, `RunWorkspace`:

```python
class RunWorkspace:
    def __init__(self, root: Path, name: str):
        self.root = root
        self.name = name
        self.dir = root / "runs" / name
        self.criteria = self.dir / "criteria.json"
        self.candidates = self.dir / "candidates.json"
        self.shortlist = self.dir / "shortlist.json"
        self.artists = self.dir / "artists.json"

    def show_ws(self, performance_id: str) -> ShowWorkspace:
        return ShowWorkspace(self.root / "shows" / slugify(performance_id))
```

- [ ] **Step 4: Update path expectations in the other tests**

In `tests/test_pipeline.py` and `tests/test_cli_commands.py`, replace every
`tmp_path / "runs" / <run> / "shows" / <slug>` with `tmp_path / "shows" / <slug>`
(and `run_dir / "shows" / <slug>` at test_pipeline.py:220 with `tmp_path / "shows" / <slug>`), including the Task-1 provenance test. The deliver tests at test_cli_commands.py:313/338 keep working unchanged for now (they pass explicit paths and `deliver` still accepts paths); update their `show_dir` to `tmp_path / "shows" / "gratefuldead-1973-06-10"` anyway so they model the real layout — but note `deliver` currently derives the ledger `run` field from `show_dir.parent.parent.name`, which now yields the workspace root's name; Task 8 fixes that properly via provenance. If one of those tests asserts the `run` field, relax it to assert only status/performance_id in this task.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/llama/workspace.py tests/test_workspace.py tests/test_pipeline.py tests/test_cli_commands.py
git commit -m "feat: canonical shows library at <root>/shows/<slug>"
```

---

### Task 4: catalog.py — state derivation, iteration, name resolution

**Files:**
- Create: `src/llama/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `ShowWorkspace` artifact paths, `Ledger`, `Provenance` (Task 1), layout (Task 3).
- Produces (Tasks 5-10 consume):

```python
class CatalogError(Exception):
    """Resolution failure; .matches lists candidate names (empty = no match)."""
    def __init__(self, message: str, matches: list[str] = ...)

@dataclass
class CatalogEntry:
    slug: str
    ws: ShowWorkspace
    state: str           # held|delivered|packaged|scripted|vetted|researched|gathered|selected
    flags: list[str]     # review_flags when held, else []
    provenance: Provenance | None
    artist: str
    date: str

STAGE_DEPTH: dict[str, int]                       # selected=1 .. packaged=6
def derive_state(ws: ShowWorkspace, delivered: set[str]) -> tuple[str, list[str]]
def stage_depth(ws: ShowWorkspace) -> int          # deepest completed stage, 0 = nothing
def iter_shows(root: Path, ledger: Ledger) -> list[CatalogEntry]   # sorted by slug
def resolve_show(root: Path, ledger: Ledger, name: str) -> CatalogEntry
def resolve_run(root: Path, name: str) -> str      # run directory name
def legacy_show_dirs(root: Path) -> list[Path]     # runs/*/shows/* leftovers
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_catalog.py`:

```python
import json
from pathlib import Path

import pytest

from llama.catalog import (CatalogError, derive_state, iter_shows, legacy_show_dirs,
                           resolve_run, resolve_show, stage_depth)
from llama.ledger import Ledger
from llama.models import Candidate, LedgerEntry, Provenance, RecordingSummary, Show, Track
from llama.workspace import ShowWorkspace, write_artifact


def make_show(needs_review=False):
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="a.mp3",
                      title_source="tags")],
        needs_review=needs_review,
        review_flags=["research asserts wrong date: x"] if needs_review else [],
    )


def build(root: Path, slug: str, *, stages: set[str], needs_review=False,
          pid="GratefulDead/1973-06-10", run="r1"):
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.provenance, Provenance(
        performance_id=pid, run=run, dossier="great",
        candidate=Candidate(performance_id=pid, collection="GratefulDead",
                            date="1973-06-10",
                            recordings=[RecordingSummary(identifier="gd73")]),
        processed_at="2026-07-17T00:00:00+00:00"))
    if "select" in stages:
        write_artifact(ws.selection, {"identifier": "gd73"})
    if "gather" in stages:
        write_artifact(ws.show, make_show(needs_review))
    if "research" in stages:
        write_artifact(ws.research, "## Reputation\nfine")
    if "vet" in stages:
        write_artifact(ws.vetting, {"vetting": {"asserted_songs": [],
                                                "asserted_dates": [],
                                                "context": ""}, "flags": []})
    if "synthesize" in stages:
        write_artifact(ws.dj_notes_json, {"intro": "i", "set_intros": {},
                                          "outro": "o"})
    if "package" in stages:
        write_artifact(ws.package_dir / "manifest.json", {"schema_version": 2})
    return ws


def test_derive_state_matrix(tmp_path: Path):
    cases = [
        ({"select"}, "selected"),
        ({"select", "gather"}, "gathered"),
        ({"select", "gather", "research"}, "researched"),
        ({"select", "gather", "research", "vet"}, "vetted"),
        ({"select", "gather", "research", "vet", "synthesize"}, "scripted"),
        ({"select", "gather", "research", "vet", "synthesize", "package"}, "packaged"),
    ]
    for i, (stages, expected) in enumerate(cases):
        ws = build(tmp_path / str(i), f"s{i}", stages=stages)
        state, flags = derive_state(ws, delivered=set())
        assert state == expected and flags == []


def test_held_beats_everything(tmp_path: Path):
    ws = build(tmp_path, "s", stages={"select", "gather", "research", "vet",
                                      "synthesize", "package"}, needs_review=True)
    state, flags = derive_state(ws, delivered={"GratefulDead/1973-06-10"})
    assert state == "held"
    assert flags == ["research asserts wrong date: x"]


def test_delivered_beats_packaged(tmp_path: Path):
    ws = build(tmp_path, "s", stages={"select", "gather", "research", "vet",
                                      "synthesize", "package"})
    state, _ = derive_state(ws, delivered={"GratefulDead/1973-06-10"})
    assert state == "delivered"


def test_stage_depth(tmp_path: Path):
    ws = build(tmp_path, "s", stages={"select", "gather"})
    assert stage_depth(ws) == 2
    assert stage_depth(ShowWorkspace(tmp_path / "shows" / "empty")) == 0


def test_iter_shows_and_resolve(tmp_path: Path):
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    build(tmp_path, "mekons-1989-12-02", stages={"select", "gather"},
          pid="mekons/1989-12-02")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    entries = iter_shows(tmp_path, ledger)
    assert [e.slug for e in entries] == ["gratefuldead-1973-06-10", "mekons-1989-12-02"]
    assert entries[0].artist == "Grateful Dead"
    assert entries[0].provenance.run == "r1"

    assert resolve_show(tmp_path, ledger, "mekons-1989-12-02").slug == "mekons-1989-12-02"
    assert resolve_show(tmp_path, ledger, "mek").slug == "mekons-1989-12-02"
    with pytest.raises(CatalogError) as exc:
        resolve_show(tmp_path, ledger, "19")   # substring of both
    assert set(exc.value.matches) == {"gratefuldead-1973-06-10", "mekons-1989-12-02"}
    with pytest.raises(CatalogError) as exc:
        resolve_show(tmp_path, ledger, "nomatch")
    assert exc.value.matches == []


def test_resolve_show_accepts_existing_path(tmp_path: Path):
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    ledger = Ledger(tmp_path / "ledger.jsonl")
    assert resolve_show(tmp_path, ledger, str(ws.dir)).slug == "gratefuldead-1973-06-10"


def test_resolve_run(tmp_path: Path):
    (tmp_path / "runs" / "2026-07-16-countryish").mkdir(parents=True)
    (tmp_path / "runs" / "2026-07-16-dead").mkdir(parents=True)
    assert resolve_run(tmp_path, "countryish") == "2026-07-16-countryish"
    assert resolve_run(tmp_path, "2026-07-16-dead") == "2026-07-16-dead"
    with pytest.raises(CatalogError):
        resolve_run(tmp_path, "2026-07-16")
    with pytest.raises(CatalogError):
        resolve_run(tmp_path, "nope")


def test_legacy_show_dirs(tmp_path: Path):
    legacy = tmp_path / "runs" / "r1" / "shows" / "old-show"
    legacy.mkdir(parents=True)
    assert legacy_show_dirs(tmp_path) == [legacy]
    assert legacy_show_dirs(tmp_path / "elsewhere") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_catalog.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.catalog'`.

- [ ] **Step 3: Implement `src/llama/catalog.py`**

```python
"""Show/run discovery: derived state, iteration, and name resolution.

State is never stored; it is derived from which artifacts exist plus the
ledger, so it cannot go stale. Scan-on-demand — at this scale (~10^2 shows)
a walk is milliseconds.
"""
from dataclasses import dataclass, field
from pathlib import Path

from llama.ledger import Ledger
from llama.models import Provenance, Show
from llama.workspace import ShowWorkspace, read_model


class CatalogError(Exception):
    """Resolution failure; matches lists the candidates (empty = no match)."""

    def __init__(self, message: str, matches: list[str] | None = None):
        super().__init__(message)
        self.matches = matches or []


@dataclass
class CatalogEntry:
    slug: str
    ws: ShowWorkspace
    state: str
    flags: list[str] = field(default_factory=list)
    provenance: Provenance | None = None
    artist: str = ""
    date: str = ""


# (artifact attribute, depth, state name) from shallowest to deepest.
_STAGES = [
    ("selection", 1, "selected"),
    ("show", 2, "gathered"),
    ("research", 3, "researched"),
    ("vetting", 4, "vetted"),
    ("dj_notes_json", 5, "scripted"),
]
STAGE_DEPTH = {"select": 1, "gather": 2, "research": 3, "vet": 4,
               "synthesize": 5, "package": 6}


def stage_depth(ws: ShowWorkspace) -> int:
    """Deepest completed stage (0 = nothing). Used for migration collisions."""
    depth = 0
    for attr, d, _ in _STAGES:
        if getattr(ws, attr).exists():
            depth = d
    if (ws.package_dir / "manifest.json").exists():
        depth = 6
    return depth


def _performance_id(ws: ShowWorkspace) -> str | None:
    if ws.provenance.exists():
        return read_model(ws.provenance, Provenance).performance_id
    if ws.show.exists():
        return read_model(ws.show, Show).performance_id
    return None


def derive_state(ws: ShowWorkspace, delivered: set[str]) -> tuple[str, list[str]]:
    """(state, flags). held > delivered > packaged > ... > selected."""
    if ws.show.exists():
        show = read_model(ws.show, Show)
        if show.needs_review:
            return "held", show.review_flags
    pid = _performance_id(ws)
    if pid and pid in delivered:
        return "delivered", []
    if (ws.package_dir / "manifest.json").exists():
        return "packaged", []
    state = "selected"
    for attr, _, name in _STAGES:
        if getattr(ws, attr).exists():
            state = name
    return state, []


def iter_shows(root: Path, ledger: Ledger) -> list[CatalogEntry]:
    delivered = {e.performance_id for e in ledger.entries() if e.status == "delivered"}
    entries = []
    shows_dir = root / "shows"
    for d in sorted(shows_dir.iterdir()) if shows_dir.is_dir() else []:
        if not d.is_dir():
            continue
        ws = ShowWorkspace(d)
        state, flags = derive_state(ws, delivered)
        prov = read_model(ws.provenance, Provenance) if ws.provenance.exists() else None
        artist, date = "", ""
        if ws.show.exists():
            show = read_model(ws.show, Show)
            artist, date = show.artist, show.date
        elif prov is not None:
            artist, date = prov.candidate.collection, prov.candidate.date
        entries.append(CatalogEntry(slug=d.name, ws=ws, state=state, flags=flags,
                                    provenance=prov, artist=artist, date=date))
    return entries


def _resolve(name: str, candidates: list[str], kind: str) -> str:
    if name in candidates:
        return name
    hits = [c for c in candidates if name in c]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CatalogError(f"no {kind} matches {name!r}", [])
    raise CatalogError(f"{name!r} is ambiguous", sorted(hits))


def resolve_show(root: Path, ledger: Ledger, name: str) -> CatalogEntry:
    p = Path(name).expanduser()
    if p.is_dir():  # an existing path is an exact match
        name = p.name
    entries = {e.slug: e for e in iter_shows(root, ledger)}
    return entries[_resolve(name, sorted(entries), "show")]


def resolve_run(root: Path, name: str) -> str:
    p = Path(name).expanduser()
    if p.is_dir() and (p / "criteria.json").exists():
        name = p.name
    runs_dir = root / "runs"
    runs = sorted(d.name for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.is_dir() else []
    return _resolve(name, runs, "run")


def legacy_show_dirs(root: Path) -> list[Path]:
    """Show directories still nested under runs (pre-migration layout)."""
    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(d for d in runs_dir.glob("*/shows/*") if d.is_dir())
```

Note: `resolve_run(root, "2026-07-16")` must raise even though it is a prefix of two runs — that is what the ambiguity branch does.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_catalog.py -q`
Expected: all pass. Then `.venv/bin/pytest -q` — all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/catalog.py tests/test_catalog.py
git commit -m "feat: catalog - derived show state, iteration, name resolution"
```

---

### Task 5: llama migrate

**Files:**
- Create: `src/llama/migrate.py`
- Modify: `src/llama/cli.py` (new command)
- Test: `tests/test_migrate.py`

**Interfaces:**
- Consumes: `catalog.stage_depth`, `catalog.legacy_show_dirs`, `Provenance`, `ShortlistEntry`.
- Produces: `migrate.plan_migration(root) -> list[Move]`, `migrate.apply_migration(root, moves)`; CLI `llama migrate [--dry-run]`. `Move` is `@dataclass: src: Path, dest: Path, run: str, winner: bool` (`winner=False` rows are skipped with a warning).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_migrate.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.migrate import apply_migration, plan_migration
from llama.models import (Candidate, Criteria, Provenance, QualityAssessment,
                          RecordingSummary, ShortlistEntry)
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, write_artifact

runner = CliRunner()


def seed_run(root: Path, run: str, slug: str, pid: str, *, packaged: bool):
    """A legacy run with one nested show and a matching shortlist entry."""
    ws = RunWorkspace(root, run)
    write_artifact(ws.criteria, Criteria(query=f"{run} query", script=True))
    entry = ShortlistEntry(
        rank=1,
        candidate=Candidate(performance_id=pid, collection=pid.split("/")[0],
                            date=pid.split("/")[1],
                            recordings=[RecordingSummary(identifier="x")]),
        assessment=QualityAssessment(performance_id=pid, quality_score=9.0,
                                     rationale="great show"),
        external_reputation="ranked top-5 (example.org)")
    write_artifact(ws.shortlist, [entry])
    legacy = ws.dir / "shows" / slug
    (legacy / "package").mkdir(parents=True)
    (legacy / "selection.json").write_text('{"identifier": "x"}')
    if packaged:
        (legacy / "package" / "manifest.json").write_text('{"schema_version": 2}')
    return legacy


def test_migrate_moves_and_backfills_provenance(tmp_path: Path):
    seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
             "GratefulDead/1973-06-10", packaged=True)
    moves = plan_migration(tmp_path)
    assert len(moves) == 1 and moves[0].winner
    apply_migration(tmp_path, moves)
    dest = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert (dest / "selection.json").exists()
    assert not (tmp_path / "runs" / "r1" / "shows").exists()  # emptied and removed
    prov = read_model(ShowWorkspace(dest).provenance, Provenance)
    assert prov.run == "r1"
    assert prov.performance_id == "GratefulDead/1973-06-10"
    assert "great show" in prov.dossier and "ranked top-5" in prov.dossier
    assert prov.script is True


def test_migrate_collision_deeper_wins_loser_stays(tmp_path: Path):
    deep = seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
                    "GratefulDead/1973-06-10", packaged=True)
    shallow = seed_run(tmp_path, "r2", "gratefuldead-1973-06-10",
                       "GratefulDead/1973-06-10", packaged=False)
    moves = plan_migration(tmp_path)
    winners = [m for m in moves if m.winner]
    assert len(winners) == 1 and winners[0].src == deep
    apply_migration(tmp_path, moves)
    assert (tmp_path / "shows" / "gratefuldead-1973-06-10" / "package"
            / "manifest.json").exists()
    assert shallow.exists()  # loser left in place, nothing deleted


def test_migrate_idempotent_and_existing_target_wins(tmp_path: Path):
    legacy = seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
                      "GratefulDead/1973-06-10", packaged=False)
    (tmp_path / "shows" / "gratefuldead-1973-06-10").mkdir(parents=True)
    moves = plan_migration(tmp_path)
    assert [m.winner for m in moves] == [False]  # already-migrated target wins
    apply_migration(tmp_path, moves)
    assert legacy.exists()
    assert plan_migration(tmp_path) == moves  # stable on re-run


def test_migrate_cli_dry_run_moves_nothing(tmp_path: Path):
    seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
             "GratefulDead/1973-06-10", packaged=True)
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["migrate", "--dry-run", "--config",
                                     str(tmp_path / "config.toml")])
    assert result.exit_code == 0, result.output
    assert "gratefuldead-1973-06-10" in result.output
    assert not (tmp_path / "shows").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_migrate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.migrate'`.

- [ ] **Step 3: Implement `src/llama/migrate.py`**

```python
"""One-time move of runs/*/shows/* into the canonical shows/ library."""
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from llama.catalog import legacy_show_dirs, stage_depth
from llama.models import Criteria, Provenance, ShortlistEntry
from llama.util import slugify
from llama.workspace import (RunWorkspace, ShowWorkspace, read_model,
                             read_model_list, write_artifact)

log = logging.getLogger("llama")


@dataclass
class Move:
    src: Path
    dest: Path
    run: str
    winner: bool  # False: left in place (collision loser or target exists)


def plan_migration(root: Path) -> list[Move]:
    by_slug: dict[str, list[Path]] = {}
    for d in legacy_show_dirs(root):
        by_slug.setdefault(d.name, []).append(d)
    moves: list[Move] = []
    for slug, sources in sorted(by_slug.items()):
        dest = root / "shows" / slug
        # An existing target always wins: keeps migration idempotent.
        winner = None if dest.exists() else max(
            sources, key=lambda s: (stage_depth(ShowWorkspace(s)), s.parent.parent.name))
        for src in sorted(sources):
            moves.append(Move(src=src, dest=dest, run=src.parent.parent.name,
                              winner=src == winner))
    return moves


def _backfill_provenance(root: Path, move: Move) -> None:
    ws = ShowWorkspace(move.dest)
    if ws.provenance.exists():
        return
    run_ws = RunWorkspace(root, move.run)
    script = True
    if run_ws.criteria.exists():
        script = read_model(run_ws.criteria, Criteria).script
    if not run_ws.shortlist.exists():
        log.warning("no shortlist in %s: %s left without provenance", move.run, move.dest.name)
        return
    for entry in read_model_list(run_ws.shortlist, ShortlistEntry):
        if slugify(entry.candidate.performance_id) == move.dest.name:
            dossier = entry.assessment.rationale
            if entry.external_reputation:
                dossier += "\n\nExternal reputation: " + entry.external_reputation
            write_artifact(ws.provenance, Provenance(
                performance_id=entry.candidate.performance_id, run=move.run,
                dossier=dossier, candidate=entry.candidate, script=script,
                processed_at=datetime.now(timezone.utc).isoformat()))
            return
    log.warning("no shortlist entry for %s in %s: left without provenance",
                move.dest.name, move.run)


def apply_migration(root: Path, moves: list[Move]) -> None:
    for move in moves:
        if not move.winner:
            log.warning("left in place (collision or already migrated): %s", move.src)
            continue
        move.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.src), str(move.dest))
        _backfill_provenance(root, move)
    # tidy now-empty runs/*/shows dirs
    for shows_dir in (root / "runs").glob("*/shows"):
        if shows_dir.is_dir() and not any(shows_dir.iterdir()):
            shows_dir.rmdir()
```

In `src/llama/cli.py` add (after `deliver`):

```python
@app.command()
def migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan, move nothing"),
    config_path: Path = typer.Option(None, "--config"),
):
    """One-time move of runs/*/shows/* into the canonical shows/ library."""
    from llama.migrate import apply_migration, plan_migration

    config, _, _ = _setup(config_path)
    moves = plan_migration(config.root)
    if not moves:
        typer.echo("nothing to migrate")
        return
    for m in moves:
        action = "move" if m.winner else "skip (collision/already migrated)"
        typer.echo(f"{action}: {m.src} -> {m.dest}")
    if dry_run:
        return
    apply_migration(config.root, moves)
    typer.echo(f"migrated {sum(m.winner for m in moves)} shows to {config.root / 'shows'}")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_migrate.py -q` then `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/migrate.py src/llama/cli.py tests/test_migrate.py
git commit -m "feat: llama migrate - move nested shows to the canonical library"
```

---

### Task 6: llama status

**Files:**
- Modify: `src/llama/cli.py` (new command + `_legacy_guard` helper)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `catalog.iter_shows`, `catalog.legacy_show_dirs`.
- Produces: `llama status [--held] [--packaged] [--run NAME] [--artist SUBSTR] [--all] [--json]`; `cli._legacy_guard(root)` (exits 1 naming `llama migrate` when legacy dirs exist) — Tasks 8-10 reuse it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_commands.py` (uses `build` semantics via direct artifact writes; keep it self-contained):

```python
from llama.models import Provenance, RecordingSummary, Show, Track


def _seed_show(root: Path, slug: str, pid: str, run: str, *, held=False,
               packaged=True, delivered=False):
    sws = ShowWorkspace(root / "shows" / slug)
    write_artifact(sws.provenance, Provenance(
        performance_id=pid, run=run, dossier="d",
        candidate=Candidate(performance_id=pid, collection=pid.split("/")[0],
                            date=pid.split("/")[1],
                            recordings=[RecordingSummary(identifier="x")]),
        processed_at="2026-07-17T00:00:00+00:00"))
    write_artifact(sws.show, Show(
        performance_id=pid, identifier="x", artist=pid.split("/")[0],
        date=pid.split("/")[1],
        tracks=[Track(index=1, set="1", title="T", filename="a.mp3",
                      title_source="tags")],
        needs_review=held, review_flags=["two sets missing"] if held else []))
    if packaged:
        write_artifact(sws.package_dir / "manifest.json", {"schema_version": 2})
    if delivered:
        Ledger(root / "ledger.jsonl").record(LedgerEntry(
            performance_id=pid, artist=pid.split("/")[0], date=pid.split("/")[1],
            status="delivered", run=run, recorded_at="2026-07-17T00:00:00+00:00"))
    return sws


def test_status_orders_held_first_and_filters(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", delivered=True)
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "r1", held=True)
    _seed_show(tmp_path, "ccc-1972-01-01", "ccc/1972-01-01", "r2")

    result = runner.invoke(cli.app, ["status", "--config", cfg])
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    rows = [ln for ln in lines if not ln.startswith("      ")]  # drop flag detail lines
    assert rows[0].startswith("bbb-1971-01-01")       # held first
    assert "two sets missing" in result.output
    assert "packaged" in rows[1]                       # ccc next
    assert "delivered" in rows[-1]                     # aaa last

    held_only = runner.invoke(cli.app, ["status", "--held", "--config", cfg])
    assert "bbb-1971-01-01" in held_only.output
    assert "ccc-1972-01-01" not in held_only.output

    by_run = runner.invoke(cli.app, ["status", "--run", "r2", "--config", cfg])
    assert "ccc-1972-01-01" in by_run.output
    assert "bbb-1971-01-01" not in by_run.output


def test_status_json(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1")
    result = runner.invoke(cli.app, ["status", "--json", "--config", cfg])
    rows = json.loads(result.output)
    assert rows[0]["slug"] == "aaa-1970-01-01"
    assert rows[0]["state"] == "packaged"
    assert rows[0]["run"] == "r1"


def test_status_refuses_legacy_layout(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    (tmp_path / "runs" / "r1" / "shows" / "old").mkdir(parents=True)
    result = runner.invoke(cli.app, ["status", "--config", cfg])
    assert result.exit_code == 1
    assert "llama migrate" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli_commands.py -k status -q`
Expected: FAIL — `No such command 'status'`.

- [ ] **Step 3: Implement in `src/llama/cli.py`**

Add near the other helpers:

```python
def _legacy_guard(root: Path) -> None:
    from llama.catalog import legacy_show_dirs

    legacy = legacy_show_dirs(root)
    if legacy:
        typer.echo(f"{len(legacy)} show dirs still nested under runs/ - "
                   "run `llama migrate` first", err=True)
        raise typer.Exit(1)


_STATE_RANK = {"held": 0, "packaged": 1, "scripted": 2, "vetted": 3,
               "researched": 4, "gathered": 5, "selected": 6, "delivered": 7}
RECENT_DELIVERED = 5
```

Add the command:

```python
@app.command()
def status(
    held: bool = typer.Option(False, "--held", help="Only shows held for review"),
    packaged: bool = typer.Option(False, "--packaged", help="Only packaged, undelivered shows"),
    run: str = typer.Option(None, "--run", help="Only shows processed by this run"),
    artist: str = typer.Option(None, "--artist", help="Substring filter on artist"),
    all_shows: bool = typer.Option(False, "--all", help="Include all delivered shows"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Triage view: every show and its state, held-for-review first."""
    import json as _json

    from llama.catalog import iter_shows

    config, _, ledger = _setup(config_path)
    _legacy_guard(config.root)
    entries = iter_shows(config.root, ledger)
    if held:
        entries = [e for e in entries if e.state == "held"]
    if packaged:
        entries = [e for e in entries if e.state == "packaged"]
    if run:
        entries = [e for e in entries if e.provenance and e.provenance.run == run]
    if artist:
        entries = [e for e in entries if artist.lower() in e.artist.lower()]
    entries.sort(key=lambda e: (_STATE_RANK[e.state], e.slug))
    if not all_shows and not (held or packaged):
        delivered = [e for e in entries if e.state == "delivered"]
        keep = {id(e) for e in delivered[-RECENT_DELIVERED:]}
        entries = [e for e in entries if e.state != "delivered" or id(e) in keep]
    if as_json:
        typer.echo(_json.dumps([{
            "slug": e.slug, "state": e.state, "artist": e.artist, "date": e.date,
            "run": e.provenance.run if e.provenance else None,
            "flags": e.flags, "path": str(e.ws.dir),
        } for e in entries], indent=2))
        return
    if not entries:
        typer.echo("no shows")
        return
    for e in entries:
        run_name = e.provenance.run if e.provenance else "?"
        typer.echo(f"{e.slug:42.42s} {e.state:10s} {e.artist:20.20s} {e.date:10s} {run_name}")
        for f in e.flags:
            typer.echo(f"      - {f}")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_cli_commands.py -q` then `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: llama status - global show triage view"
```

---

### Task 7: llama runs

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `catalog.iter_shows`, `Criteria`.
- Produces: `llama runs` listing each run with its query and show-state counts.

- [ ] **Step 1: Write the failing test**

```python
def test_runs_lists_runs_with_counts(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="countryish bluegrass"))
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "2026-07-16-countryish")
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "2026-07-16-countryish",
               held=True)
    result = runner.invoke(cli.app, ["runs", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "2026-07-16-countryish" in result.output
    assert "countryish bluegrass" in result.output
    assert "held 1" in result.output and "packaged 1" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_commands.py::test_runs_lists_runs_with_counts -q`
Expected: FAIL — `No such command 'runs'`.

- [ ] **Step 3: Implement in `src/llama/cli.py`**

```python
@app.command()
def runs(config_path: Path = typer.Option(None, "--config")):
    """List runs with their criteria and show-state counts."""
    from collections import Counter

    from llama.catalog import iter_shows

    config, _, ledger = _setup(config_path)
    by_run: dict[str, Counter] = {}
    for e in iter_shows(config.root, ledger):
        if e.provenance:
            by_run.setdefault(e.provenance.run, Counter())[e.state] += 1
    runs_dir = config.root / "runs"
    run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.is_dir() else []
    if not run_dirs:
        typer.echo("no runs")
        return
    for d in run_dirs:
        query = ""
        if (d / "criteria.json").exists():
            query = read_model(RunWorkspace(config.root, d.name).criteria, Criteria).query
        counts = by_run.get(d.name, Counter())
        summary = "  ".join(f"{s} {n}" for s, n in sorted(counts.items())) or "no shows"
        typer.echo(f"{d.name:34.34s} {summary:40.40s} {query:40.40s}")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_cli_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: llama runs - run listing with show-state counts"
```

---

### Task 8: Name-addressed show and deliver

**Files:**
- Modify: `src/llama/cli.py` (`show` ~line 362, `deliver` ~line 394)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `catalog.resolve_show`, `CatalogError`, `_legacy_guard`, `Provenance`.
- Produces: `llama show <name>` (adds stage table; keeps `--clear`), `llama deliver <name>` (ledger `run` from provenance). Both still accept full paths.

- [ ] **Step 1: Write the failing tests**

```python
def test_show_resolves_by_name_and_lists_stages(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "mekons-1989-12-02", "mekons/1989-12-02", "r1", held=True)
    result = runner.invoke(cli.app, ["show", "mek", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "needs-review: yes" in result.output
    assert "show.json" in result.output          # stage table
    assert "research.md" in result.output
    assert "missing" in result.output            # research.md was never written


def test_show_ambiguous_name_fails_loud(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1")
    _seed_show(tmp_path, "aab-1970-01-01", "aab/1970-01-01", "r1")
    result = runner.invoke(cli.app, ["show", "aa", "--config", cfg])
    assert result.exit_code == 1
    assert "aaa-1970-01-01" in result.output and "aab-1970-01-01" in result.output


def test_show_clear_still_works_by_name(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "mekons-1989-12-02", "mekons/1989-12-02", "r1", held=True)
    result = runner.invoke(cli.app, ["show", "mekons", "--clear", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert read_model(sws.show, Show).needs_review is False


def test_deliver_by_name_records_provenance_run(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "myrun")
    (sws.package_dir / "audio").mkdir(parents=True, exist_ok=True)
    write_artifact(sws.package_dir / "manifest.json", {
        "schema_version": 2,
        "show": {"artist": "aaa", "date": "1970-01-01", "venue": None,
                 "city": None, "context": ""},
        "source": {"performance_id": "aaa/1970-01-01"},
        "tracks": [], "set_breaks": [],
        "total_duration_sec": 0, "set_durations_sec": {},
    })
    dest = tmp_path / "inbox"
    result = runner.invoke(cli.app, ["deliver", "aaa", "--dest", str(dest),
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert (dest / "aaa-1970-01-01" / "manifest.json").exists()
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered" and entries[0].run == "myrun"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli_commands.py -k "resolves_by_name or ambiguous or clear_still or provenance_run" -q`
Expected: FAIL (show exits 1 on a non-path name today; deliver records the wrong run).

- [ ] **Step 3: Implement**

Add a resolver helper in `cli.py`:

```python
def _resolve_show_or_exit(config, ledger, name: str):
    from llama.catalog import CatalogError, resolve_show

    _legacy_guard(config.root)
    try:
        return resolve_show(config.root, ledger, name)
    except CatalogError as err:
        typer.echo(str(err), err=True)
        for m in err.matches:
            typer.echo(f"  {m}", err=True)
        raise typer.Exit(1)
```

Rewrite `show`:

```python
@app.command()
def show(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    clear: bool = typer.Option(False, "--clear",
                               help="Overrule the hold: clear needs-review and its flags"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Inspect one show: state, stage artifacts, needs-review flags."""
    config, _, ledger = _setup(config_path)
    entry = _resolve_show_or_exit(config, ledger, name)
    sws = entry.ws
    if not sws.show.exists():
        typer.echo(f"no show.json in {sws.dir} (state: {entry.state})", err=True)
        raise typer.Exit(1)
    s = read_model(sws.show, Show)
    place = ", ".join(p for p in [s.venue, s.city] if p)
    typer.echo(f"{s.artist}  {s.date}  {place}".rstrip())
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks)")
    typer.echo(f"state: {entry.state}   path: {sws.dir}")
    typer.echo("stages:")
    artifacts = [("selection.json", sws.selection), ("show.json", sws.show),
                 ("research.md", sws.research), ("vetting.json", sws.vetting),
                 ("dj-notes.json", sws.dj_notes_json),
                 ("package/manifest.json", sws.package_dir / "manifest.json")]
    now = datetime.now(timezone.utc).timestamp()
    for label, path in artifacts:
        if path.exists():
            age_days = (now - path.stat().st_mtime) / 86400
            typer.echo(f"  {label:22s} {age_days:5.1f}d old")
        else:
            typer.echo(f"  {label:22s} missing")
    if not s.needs_review:
        typer.echo("needs-review: no")
        return
    typer.echo("needs-review: yes")
    for f in s.review_flags:
        typer.echo(f"  - {f}")
    if clear:
        s.needs_review = False
        s.review_flags = []
        write_artifact(sws.show, s)
        typer.echo("cleared")
        typer.echo(f"next: llama redo {entry.slug} --from package")
    else:
        typer.echo(f"to overrule after inspecting: llama show --clear {entry.slug}")
```

Rewrite `deliver`'s addressing and ledger record (body between the guard and copytree stays):

```python
@app.command()
def deliver(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    dest: Path = typer.Option(None, "--dest", help="Defaults to config delivery_path"),
    force: bool = typer.Option(False, "--force", help="Deliver even if the show is marked needs-review"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Copy a show package to the station's watched folder and record delivery."""
    import json as _json

    from llama.models import Provenance

    config, _, ledger = _setup(config_path)
    entry = _resolve_show_or_exit(config, ledger, name)
    show_dir = entry.ws.dir
    target_dir = dest or config.delivery_path
    if target_dir is None:
        typer.echo("no --dest given and no delivery_path in config", err=True)
        raise typer.Exit(1)
    show_json = show_dir / "show.json"
    if show_json.exists() and not force:
        show_data = _json.loads(show_json.read_text())
        if show_data.get("needs_review"):
            flags = ", ".join(show_data.get("review_flags", []))
            typer.echo(
                f"refusing to deliver: show is marked needs-review ({flags}); use --force to override",
                err=True,
            )
            raise typer.Exit(1)
    pkg = show_dir / "package"
    manifest = _json.loads((pkg / "manifest.json").read_text())
    out = target_dir / show_dir.name
    shutil.copytree(pkg, out, dirs_exist_ok=True)
    show = manifest["show"]
    run_name = entry.provenance.run if entry.provenance else "unknown"
    ledger.record(LedgerEntry(
        performance_id=manifest["source"].get("performance_id", show_dir.name),
        artist=show["artist"], date=show["date"], venue=show.get("venue"),
        status="delivered", run=run_name,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    ))
    typer.echo(f"delivered: {out}")
```

Update the two existing deliver tests (test_cli_commands.py ~313/338): they seed a bare package with no provenance — after this change they must either seed provenance via `_seed_show` or assert `run == "unknown"`. Prefer converting them to `_seed_show` + explicit manifest write, as in the new test.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_cli_commands.py -q` then `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: name-addressed show/deliver via the catalog resolver"
```

---

### Task 9: Run-name resolution for run and review

**Files:**
- Modify: `src/llama/cli.py` (`run` ~line 279, `review` ~line 325)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `catalog.resolve_run`, `CatalogError`, `_legacy_guard`.
- Produces: `llama run <name>` / `llama review <name>` accept run names, substrings, or paths.

- [ ] **Step 1: Write the failing test**

```python
def test_review_resolves_run_by_substring(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["review", "countryish", "--config", cfg],
                           input="1\nn\n")
    assert result.exit_code == 0, result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True


def test_run_unknown_name_fails_loud(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["run", "nope", "--config", cfg])
    assert result.exit_code == 1
    assert "no run matches" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli_commands.py -k "resolves_run or unknown_name" -q`
Expected: FAIL (`review countryish` exits nonzero on the missing shortlist path; `run nope` prints "no criteria.json").

- [ ] **Step 3: Implement**

Helper in `cli.py`:

```python
def _resolve_run_or_exit(config, name: str) -> RunWorkspace:
    from llama.catalog import CatalogError, resolve_run

    _legacy_guard(config.root)
    try:
        return RunWorkspace(config.root, resolve_run(config.root, name))
    except CatalogError as err:
        typer.echo(str(err), err=True)
        for m in err.matches:
            typer.echo(f"  {m}", err=True)
        raise typer.Exit(1)
```

In `run`, change the argument to `run_name: str = typer.Argument(..., help="Run name, unique substring, or path")` and replace `ws = RunWorkspace(config.root, run_dir.name)` with `ws = _resolve_run_or_exit(config, run_name)`. Same change in `review` (argument `run_name: str`, `ws = _resolve_run_or_exit(config, run_name)`). Existing tests pass full paths — `resolve_run` accepts them via the path branch.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_cli_commands.py tests/test_pipeline.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: run/review resolve run names via the catalog"
```

---

### Task 10: llama redo

**Files:**
- Modify: `src/llama/workspace.py` (`drop_stage_artifacts`, ~line 71)
- Modify: `src/llama/cli.py` (new command)
- Test: `tests/test_workspace.py`, `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `resolve_show` (Task 8 helper), `Provenance`, `process_show`, `drop_stage_artifacts`.
- Produces: `llama redo <show> --from <stage> [--with-research] [--script/--no-script]`; `drop_stage_artifacts(show_ws, stage, keep_research: bool = False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workspace.py`:

```python
def test_drop_stage_artifacts_can_keep_research(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    for p in [sws.selection, sws.show, sws.research, sws.vetting, sws.dj_notes_json]:
        write_artifact(p, "x")
    drop_stage_artifacts(sws, "gather", keep_research=True)
    assert sws.selection.exists()
    assert not sws.show.exists() and not sws.vetting.exists()
    assert sws.research.exists()          # preserved
    drop_stage_artifacts(sws, "research")
    assert not sws.research.exists()      # default still drops it
```

Append to `tests/test_cli_commands.py`:

```python
def test_redo_requires_from_and_reruns_tail(tmp_path: Path, monkeypatch):
    # tests/ has no __init__.py; pytest puts the tests dir on sys.path
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    # First, produce a real packaged show via find (writes provenance).
    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--script", "--run-name", "redorun",
        "--config", cfg,
    ])
    assert result.exit_code == 0, result.output
    sws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")
    research_before = sws.research.read_text()

    # --from is required
    missing = runner.invoke(cli.app, ["redo", "gratefuldead", "--config", cfg])
    assert missing.exit_code != 0

    result = runner.invoke(cli.app, ["redo", "gratefuldead", "--from", "gather",
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert sws.show.exists() and (sws.package_dir / "manifest.json").exists()
    assert sws.research.read_text() == research_before   # preserved by default


def test_redo_without_provenance_errors(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "orphan-1970-01-01")
    write_artifact(sws.show, Show(
        performance_id="orphan/1970-01-01", identifier="x", artist="orphan",
        date="1970-01-01", tracks=[Track(index=1, set="1", title="T",
                                         filename="a.mp3", title_source="tags")]))
    result = runner.invoke(cli.app, ["redo", "orphan", "--from", "vet",
                                     "--config", cfg])
    assert result.exit_code == 1
    assert "provenance.json" in result.output and "migrate" in result.output
```

Note for the redo test: the `find` run consumed the fake providers' queued responses; `fake_providers` is called again inside `redo` via `cli.make_providers`, giving fresh queues, so gather/vet/synthesize replies are available. `deep_research` is NOT re-consumed (research preserved) — this is exactly what the test asserts.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_workspace.py tests/test_cli_commands.py -k "keep_research or redo" -q`
Expected: FAIL (`drop_stage_artifacts` rejects the keyword; `No such command 'redo'`).

- [ ] **Step 3: Implement**

`src/llama/workspace.py`:

```python
def drop_stage_artifacts(show_ws: ShowWorkspace, stage: str, keep_research: bool = False) -> None:
    """Delete one show's artifacts for `stage` and every stage after it.
    keep_research spares research.md (the expensive deep-research output)
    while still dropping everything derived from it."""
    for st in SHOW_STAGE_ORDER[SHOW_STAGE_ORDER.index(stage):]:
        for path in show_stage_artifacts(show_ws, st):
            if keep_research and path == show_ws.research:
                continue
            if path.exists():
                path.unlink()
```

`src/llama/cli.py`:

```python
@app.command()
def redo(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    from_stage: str = typer.Option(..., "--from",
                                   help="Stage to re-run from: select|gather|research|vet|synthesize|package"),
    with_research: bool = typer.Option(False, "--with-research",
                                       help="Also drop research.md (kept by default)"),
    script: bool = typer.Option(None, "--script/--no-script",
                                help="Override the script setting recorded at process time"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Re-run one show's pipeline from a stage; earlier artifacts are reused."""
    from llama.models import Provenance, QualityAssessment
    from llama.workspace import drop_stage_artifacts

    show_stages = VALID_STAGES - RUN_LEVEL_STAGES
    if from_stage not in show_stages:
        typer.echo(f"unknown stage {from_stage!r}; valid: {sorted(show_stages)}", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup(config_path)
    entry = _resolve_show_or_exit(config, ledger, name)
    if entry.provenance is None:
        typer.echo(f"no provenance.json in {entry.ws.dir} - "
                   "run `llama migrate` (or reprocess via its run) first", err=True)
        raise typer.Exit(1)
    prov = entry.provenance
    keep_research = not with_research and from_stage in ("select", "gather")
    drop_stage_artifacts(entry.ws, from_stage, keep_research=keep_research)
    shortlist_entry = ShortlistEntry(
        rank=1, candidate=prov.candidate,
        assessment=QualityAssessment(performance_id=prov.performance_id,
                                     quality_score=0.0, rationale=prov.dossier))
    ws = RunWorkspace(config.root, prov.run)
    effective_script = prov.script if script is None else script
    pkg = process_show(ws, ia, ledger, shortlist_entry, make_providers(config),
                       prov.run, config.audio_format, script=effective_script,
                       setlistfm=make_client(config), structure_cfg=config.structure,
                       selection_cfg=config.selection)
    if pkg:
        typer.echo(f"packaged: {pkg}")
    else:
        typer.echo(f"needs-review, skipped: {prov.performance_id}")
```

Note: `process_show` rebuilds the dossier from `assessment.rationale` — provenance's dossier already contains the external-reputation suffix, so `external_reputation` is left `None` to avoid doubling it. `process_show` also rewrites `provenance.json` with the same values (dossier round-trips).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/workspace.py src/llama/cli.py tests/test_workspace.py tests/test_cli_commands.py
git commit -m "feat: llama redo - per-show stage re-run from provenance"
```

---

### Task 11: Documentation

**Files:**
- Modify: `CLAUDE.md` (Commands section)
- Modify: `docs/station-brief.md` (command surface, if it lists commands)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update CLAUDE.md**

In the `## Commands` section, replace the Run line with:

```markdown
- Run: `llama find "..."`, `llama artists "..."`, `llama profile run <name>`,
  `llama status` (global triage view), `llama runs`, `llama show <name>`,
  `llama redo <name> --from <stage>`, `llama review <run>`, `llama deliver <name>`.
  Shows/runs are addressed by name or unique substring; paths still work.
  One-time after upgrading: `llama migrate` moves nested show dirs to `~/.llama/shows/`.
```

Also update the architecture bullet that says "per-run directory" to mention the canonical shows library:

```markdown
- **Staged pipeline over an on-disk workspace** (default `~/.llama/`): ... Every
  stage reads/writes plain files; run-level artifacts live in a per-run directory,
  show-level artifacts in a canonical `shows/<slug>/` library (one dir per
  performance, reused across runs); stages write outputs only on success and are
  individually re-runnable (`llama redo <show> --from <stage>`).
```

- [ ] **Step 2: Update docs/station-brief.md**

Read the file; wherever it references `llama deliver <path>` or run-nested show paths, switch to name-based commands and mention `llama status` as the way to see deliverables. Keep edits minimal and factual.

- [ ] **Step 3: Verify and commit**

Run: `.venv/bin/pytest -q` (docs shouldn't break anything — sanity only)

```bash
git add CLAUDE.md docs/station-brief.md
git commit -m "docs: show-centric CLI surface (status, redo, name addressing)"
```

---

## Self-review notes

- Spec coverage: layout+provenance (T1/T3), derived state (T4), status (T6), runs (T7), name-addressed show/deliver (T8), run/review names (T9), redo with research preservation (T10), migrate with collision rule + dry-run (T5), ledger idempotence (T2), legacy-layout guard (T6 helper, used by T8-T10), docs (T11).
- The spec's "states below packaged describe in-flight shows" is covered by the `_STAGES` cascade in T4.
- `--held`/`--packaged`/`--run`/`--artist`/`--json`/`--all` all present in T6.
- Type consistency: `CatalogEntry`, `resolve_show`, `resolve_run`, `Move`, `drop_stage_artifacts(keep_research=)` names match across tasks.
