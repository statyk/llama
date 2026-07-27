# UX redesign Plan A — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything the CLI surface re-cut (Plan B) will consume, beneath the
command layer: library-as-dedup in winnow, ledger/history helpers, auto-unique session
ids + the `session.json` lifecycle marker, session-state derivation, the shared
selector layer, the deliver broadcast-ready refusal classifier, `rm` disposition
machinery, archive-URL/considered-recording extraction, and the profile-scratch
relocation.

**Architecture:** Every task is a helper or a below-the-surface change with its own
unit tests; the existing CLI keeps working unmodified throughout (old selector code
paths, old commands, old flags all stay until Plan B). The only user-visible changes
in this plan are two independently-desired fixes: winnow now also dedups against the
on-disk show library (spec §9), and same-day session-name collisions get a `-2`/`-3`
suffix instead of silently resuming (spec §4). New logic lives in `catalog.py`,
`ledger.py`, `workspace.py`, a new `sessions.py`, and a new `cli_select.py`; `cli.py`
is touched only where a foundation must be *fed* (`_execute` marker writes +
`library_ids`, run-name uniquing, profile-scratch relocation).

**Tech Stack:** Python ≥3.11, Typer, Pydantic v2, pytest (offline, deterministic,
`fake` LLM backend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-27-llama-ux-redesign-design.md` (approved) —
read it before starting; §§2, 4, 7.3, 8, 9, 10 govern this plan.
**Plan B dependency:** `2026-07-27-llama-ux-redesign-plan-b-surface.md` consumes every
interface produced here and MUST NOT start until this plan is complete and merged.

## Global Constraints

- No new dependencies. No schema migrations. Show state stays derived-never-stored;
  the one new stored file is `runs/<id>/session.json`, which is *process/lifecycle*
  state on a session (a process object), never anything under `shows/` (spec §4).
- Do not change when the `selected` ledger row is written (`pipeline.py:127`) — held
  shows keep having no ledger row; library-dedup is the mechanism that stops their
  re-offer.
- Do not modify existing command signatures, flags, or help text — that is Plan B.
  Existing CLI tests must keep passing untouched except where a task explicitly says
  otherwise.
- All tests offline and deterministic; match existing idioms
  (`tests/test_catalog.py` builders, `write_artifact`, `tmp_path` roots).
- Exact strings (reason strings, echo lines, marker states) are contracts — define
  once, assert verbatim in tests, never re-implement.
- Commit after every task with conventional prefixes plus the project's standard
  trailers.
- Run the full suite (`pytest -q`) before every commit; every task leaves the tree
  green.

## File Structure (new/changed)

```
src/llama/
  catalog.py        # + library_performance_ids, deliver_refusals, remove_show, recording_info
  ledger.py         # + remove_status, latest_dispositions
  util.py           # + parse_performance_id
  workspace.py      # + unique_run_name; RunWorkspace.session path
  sessions.py       # NEW: session lifecycle marker + SessionInfo/iter_sessions
  cli_select.py     # NEW: ShowState enum + shared selector reconciliation/held rule
  cli.py            # _execute feeds markers + library_ids; run-name uniquing;
                    # profile-setup scratch relocation; Criteria.profile stamp
  models.py         # + Criteria.profile (additive, optional)
  stages/winnow.py  # run_winnow gains library_ids
tests/
  test_library_dedup.py  test_sessions.py  test_cli_select.py
  test_deliver_gate.py   test_rm_machinery.py  test_recording_info.py
  test_ledger.py (extend)  test_util.py (extend)  test_profiles.py (extend)
```

---

### Task 1: Library-as-dedup (`library_performance_ids` + winnow `seen`)

**Files:**
- Modify: `src/llama/catalog.py` (add helper), `src/llama/stages/winnow.py`
  (`run_winnow` gains `library_ids`), `src/llama/cli.py` (`_execute` passes it)
- Create: `tests/test_library_dedup.py`

**Interfaces:**
- Produces: `catalog.library_performance_ids(root: Path) -> set[str]` — the
  performance id of every show dir under `root/shows/`, any state; unresolvable dirs
  (no provenance.json and no show.json) are skipped. Reuses the existing
  `_performance_id(ws)` (`catalog.py:51`).
- Produces: `run_winnow(..., library_ids: set[str] | None = None)`; the dedup line
  (`winnow.py:58`) becomes
  `seen = (library_ids or set()) | ledger.played_ids() | ledger.rejected_ids()`.
- Consumes (in `_execute`, `cli.py:237`): the `run_winnow` call gains
  `library_ids=library_performance_ids(config.root)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_library_dedup.py`. Build show dirs with `write_artifact` (per
`tests/test_catalog.py` idioms): one with only `provenance.json`, one with only
`show.json`, one empty dir, one non-dir file under `shows/`.

```python
from pathlib import Path

from llama.catalog import library_performance_ids
from llama.ledger import Ledger
from llama.models import Candidate, Criteria, Provenance, Show
from llama.stages.winnow import run_winnow
from llama.workspace import RunWorkspace, ShowWorkspace, write_artifact


def _prov(pid: str) -> Provenance:
    return Provenance(performance_id=pid, run="r1", processed_at="2026-07-27T00:00:00+00:00",
                      candidate=Candidate(performance_id=pid, collection=pid.split("/")[0],
                                          date=pid.split("/")[1], recordings=[]))


def test_library_ids_from_provenance_and_show(tmp_path: Path):
    a = ShowWorkspace(tmp_path / "shows" / "a")
    write_artifact(a.provenance, _prov("GratefulDead/1973-06-10"))
    b = ShowWorkspace(tmp_path / "shows" / "b")
    write_artifact(b.show, Show(performance_id="GratefulDead/1977-05-08", identifier="x",
                                artist="Grateful Dead", date="1977-05-08"))
    (tmp_path / "shows" / "empty").mkdir()          # unresolvable: skipped
    (tmp_path / "shows" / "stray.txt").write_text("")  # non-dir: skipped
    assert library_performance_ids(tmp_path) == {
        "GratefulDead/1973-06-10", "GratefulDead/1977-05-08"}


def test_no_shows_dir_is_empty_set(tmp_path: Path):
    assert library_performance_ids(tmp_path) == set()
```

Add a winnow-level test asserting `library_ids` excludes a candidate exactly like a
ledger row does. Follow the existing winnow test setup in `tests/test_stage_winnow.py`
(candidates.json + fake providers); the new test passes
`library_ids={"GratefulDead/1973-06-10"}` and asserts that performance is absent from
the shortlist while a sibling candidate survives, and that omitting `library_ids`
leaves today's behavior byte-identical.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_library_dedup.py -q`
Expected: FAIL — `ImportError: cannot import name 'library_performance_ids'`;
`run_winnow() got an unexpected keyword argument 'library_ids'`.

- [ ] **Step 3: Implement**

In `src/llama/catalog.py`, after `_performance_id` (line 57):

```python
def library_performance_ids(root: Path) -> set[str]:
    """Performance ids of every show currently on disk, any state. The library
    half of dedup memory: what you have is never re-offered (spec §9)."""
    shows_dir = root / "shows"
    if not shows_dir.is_dir():
        return set()
    out = set()
    for d in sorted(shows_dir.iterdir()):
        if d.is_dir():
            pid = _performance_id(ShowWorkspace(d))
            if pid:
                out.add(pid)
    return out
```

In `src/llama/stages/winnow.py`: add `library_ids: set[str] | None = None` to
`run_winnow`'s keyword args (after `ledger`); replace line 58 and extend the log line
at :61:

```python
    seen = (library_ids or set()) | ledger.played_ids() | ledger.rejected_ids()
    pool = [c for c in candidates if c.performance_id not in seen]
    survivors = [c for c in pool if _passes_mechanical(c, criteria)]
    log.info("winnow: %d candidates -> %d after library+ledger -> %d after mechanical",
             len(candidates), len(pool), len(survivors))
```

In `src/llama/cli.py` `_execute`, the `run_winnow` call (line 237) gains
`library_ids=library_performance_ids(config.root)` (import from `llama.catalog` at the
top of the module).

- [ ] **Step 4: Run the tests, then the full suite**

Run: `pytest tests/test_library_dedup.py -q` then `pytest -q`
Expected: PASS. Watch for pipeline tests that re-run winnow over a workspace that
already contains the show being processed — none should break because `run_winnow`
skips when `shortlist.json` exists (`winnow.py:54`), but if one does, it is asserting
the pre-spec re-offer behavior and should be updated to the spec (§9: on-disk shows
are excluded from *new* winnows).

- [ ] **Step 5: Commit**

```bash
git add src/llama/catalog.py src/llama/stages/winnow.py src/llama/cli.py tests/test_library_dedup.py
git commit -m "feat: winnow dedups against the on-disk show library"
```

---

### Task 2: Ledger helpers + performance-id parsing

**Files:**
- Modify: `src/llama/ledger.py`, `src/llama/util.py`
- Test: extend `tests/test_ledger.py`, `tests/test_util.py`

**Interfaces:**
- Produces: `Ledger.remove_status(performance_id: str, status: str) -> int` — remove
  only rows with that pid *and* that status (atomic rewrite like `remove`,
  `ledger.py:34`); returns count removed. `unsuppress` (Plan B) calls it with
  `"rejected"`.
- Produces: `Ledger.latest_dispositions() -> list[LedgerEntry]` — one entry per
  performance id: the row with the greatest `recorded_at` (later file position breaks
  ties), sorted ascending by `recorded_at`. `history list` (Plan B) prints this.
- Produces: `util.parse_performance_id(text: str) -> tuple[str, str] | None` —
  matches `^<collection>/<YYYY-MM-DD>(/e<N>)?$` (collection = no `/`), returning
  `(collection, date)`; `None` otherwise. Off-disk `suppress` (Plan B) derives the
  ledger row's artist/date from it (spec §8.2).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ledger.py` (reuse its `entry(pid, status=...)` helper; give it
distinct `recorded_at` values where ordering matters):

```python
def test_remove_status_only_touches_that_status(tmp_path: Path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record(entry("a", status="selected"))
    led.record(entry("a", status="rejected"))
    led.record(entry("b", status="rejected"))
    assert led.remove_status("a", "rejected") == 1
    assert [(e.performance_id, e.status) for e in led.entries()] == [
        ("a", "selected"), ("b", "rejected")]
    assert led.remove_status("a", "rejected") == 0   # idempotent


def test_latest_dispositions_one_row_per_pid(tmp_path: Path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record(entry("a", status="selected", recorded_at="2026-07-01T00:00:00+00:00"))
    led.record(entry("a", status="delivered", recorded_at="2026-07-03T00:00:00+00:00"))
    led.record(entry("b", status="rejected", recorded_at="2026-07-02T00:00:00+00:00"))
    latest = led.latest_dispositions()
    assert [(e.performance_id, e.status) for e in latest] == [
        ("b", "rejected"), ("a", "delivered")]   # ascending recorded_at
```

(Extend the `entry` helper with a `recorded_at="..."` keyword if it lacks one.)

Append to `tests/test_util.py`:

```python
from llama.util import parse_performance_id


def test_parse_performance_id():
    assert parse_performance_id("GratefulDead/1980-05-16") == ("GratefulDead", "1980-05-16")
    assert parse_performance_id("GratefulDead/1966-07-16/e2") == ("GratefulDead", "1966-07-16")
    assert parse_performance_id("not-a-pid") is None
    assert parse_performance_id("a/b/c") is None
    assert parse_performance_id("GratefulDead/16-05-1980") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_ledger.py tests/test_util.py -q`
Expected: FAIL — missing attributes/functions.

- [ ] **Step 3: Implement**

`Ledger.remove_status` mirrors `remove` (temp-file rewrite) with the two-field
predicate. `latest_dispositions`:

```python
    def latest_dispositions(self) -> list[LedgerEntry]:
        """One entry per performance id — the latest disposition (greatest
        recorded_at; later file position breaks ties) — ascending by recorded_at."""
        latest: dict[str, LedgerEntry] = {}
        for e in self.entries():
            cur = latest.get(e.performance_id)
            if cur is None or e.recorded_at >= cur.recorded_at:
                latest[e.performance_id] = e
        return sorted(latest.values(), key=lambda e: e.recorded_at)
```

`util.parse_performance_id`:

```python
_PID = re.compile(r"^([^/]+)/(\d{4}-\d{2}-\d{2})(?:/e\d+)?$")


def parse_performance_id(text: str) -> tuple[str, str] | None:
    """(collection, date) from a canonical performance id, else None."""
    m = _PID.match(text)
    return (m.group(1), m.group(2)) if m else None
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `pytest tests/test_ledger.py tests/test_util.py -q` then `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/ledger.py src/llama/util.py tests/test_ledger.py tests/test_util.py
git commit -m "feat: ledger remove_status + latest_dispositions; performance-id parser"
```

---

### Task 3: Auto-unique session ids + `session.json` lifecycle marker

**Files:**
- Create: `src/llama/sessions.py`
- Modify: `src/llama/workspace.py` (`unique_run_name`; `RunWorkspace.session` path),
  `src/llama/cli.py` (`find` :324 and `profile_run` :1263 use `unique_run_name`;
  `_execute` writes markers)
- Create: `tests/test_sessions.py`

**Interfaces:**
- Produces: `workspace.unique_run_name(root: Path, base: str) -> str` — `base` if
  `root/runs/base` doesn't exist, else `base-2`, `base-3`, … (lowest free suffix).
- Produces: `RunWorkspace.session = self.dir / "session.json"`.
- Produces (in `sessions.py`): marker constants
  `STATE_AWAITING = "awaiting-approval"`, `STATE_COMPLETE = "complete"`,
  `STATE_INCOMPLETE = "incomplete"`;
  `mark_awaiting(ws: RunWorkspace) -> None`;
  `mark_complete(ws: RunWorkspace, outcome: str | None = None) -> None`;
  `session_state(run_dir: Path) -> str` — the marker's `state` when the file exists
  and parses with a known state, else `"incomplete"` (absent, malformed, or unknown
  state all mean the session never reached a clean stop — spec §4).
  Marker shape (written via `write_artifact`, atomic):
  `{"state": ..., "updated_at": "<ISO-8601 UTC>", "outcome": <str|null>}`.
- Consumes/feeds: `_execute` (`cli.py:196`) writes markers at its three clean stops
  (see Step 3). `find`/`profile_run` build their run name through
  `unique_run_name` unless `--run-name` was given.

Behavioral notes (spec §4): markers are never written mid-flight; a crash leaves no
marker (or a stale `awaiting-approval`), which derives as needing attention.
Pre-redesign run dirs have no marker and derive `incomplete`; no migration.

- [ ] **Step 1: Write the failing tests**

`tests/test_sessions.py`:

```python
from pathlib import Path

from llama.sessions import (STATE_AWAITING, STATE_COMPLETE, STATE_INCOMPLETE,
                            mark_awaiting, mark_complete, session_state)
from llama.workspace import RunWorkspace, unique_run_name


def test_unique_run_name(tmp_path: Path):
    assert unique_run_name(tmp_path, "2026-07-27-x") == "2026-07-27-x"
    (tmp_path / "runs" / "2026-07-27-x").mkdir(parents=True)
    assert unique_run_name(tmp_path, "2026-07-27-x") == "2026-07-27-x-2"
    (tmp_path / "runs" / "2026-07-27-x-2").mkdir()
    assert unique_run_name(tmp_path, "2026-07-27-x") == "2026-07-27-x-3"


def test_marker_roundtrip(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    assert session_state(ws.dir) == STATE_INCOMPLETE          # absent
    mark_awaiting(ws)
    assert session_state(ws.dir) == STATE_AWAITING
    mark_complete(ws, "2 packaged, 1 held")
    assert session_state(ws.dir) == STATE_COMPLETE


def test_malformed_marker_is_incomplete(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    ws.dir.mkdir(parents=True)
    ws.session.write_text("{not json")
    assert session_state(ws.dir) == STATE_INCOMPLETE
    ws.session.write_text('{"state": "weird"}')
    assert session_state(ws.dir) == STATE_INCOMPLETE
```

CLI-feed tests (append to `tests/test_sessions.py`; use the existing pipeline-test
fixtures/fake-backend idioms from `tests/test_pipeline.py` / `tests/test_cli.py` to
drive `find` twice with the same query, asserting):

- two same-day `find` invocations of one query create `runs/<name>` and
  `runs/<name>-2` (no silent resume; assert both dirs exist and the second run's
  criteria was freshly interpreted),
- a completed `_execute` leaves `session.json` with `state == "complete"` and a
  non-empty `outcome`,
- an `_execute` that stops at the human gate (profile with `human_gate=True`, auto)
  leaves `state == "awaiting-approval"`,
- a winnow that yields nothing ("No shows survived winnowing.") still marks
  `complete`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_sessions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.sessions'`; no
`unique_run_name`.

- [ ] **Step 3: Implement**

`workspace.py` — add after `RunWorkspace` (line 103):

```python
def unique_run_name(root: Path, base: str) -> str:
    """Auto-unique session id: `base`, else `base-2`, `base-3`, ... (spec §4).
    Fixes the same-day silent-resume collision."""
    runs = root / "runs"
    if not (runs / base).exists():
        return base
    n = 2
    while (runs / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"
```

and `self.session = self.dir / "session.json"` in `RunWorkspace.__init__`.

`src/llama/sessions.py`:

```python
"""Session lifecycle: a session (run) is a process object, not a derived view
of content, so its lifecycle is recorded on its own directory as
runs/<id>/session.json. Show state stays derived-never-stored; this marker
never lives under shows/ (spec §4)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from llama.workspace import RunWorkspace, write_artifact

STATE_AWAITING = "awaiting-approval"
STATE_COMPLETE = "complete"
STATE_INCOMPLETE = "incomplete"          # derived: no clean stop recorded


def _write(ws: RunWorkspace, state: str, outcome: str | None) -> None:
    write_artifact(ws.session, json.dumps({
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
    }, indent=2))


def mark_awaiting(ws: RunWorkspace) -> None:
    _write(ws, STATE_AWAITING, None)


def mark_complete(ws: RunWorkspace, outcome: str | None = None) -> None:
    _write(ws, STATE_COMPLETE, outcome)


def session_state(run_dir: Path) -> str:
    path = run_dir / "session.json"
    if not path.exists():
        return STATE_INCOMPLETE
    try:
        state = json.loads(path.read_text()).get("state")
    except (OSError, json.JSONDecodeError):
        return STATE_INCOMPLETE
    return state if state in (STATE_AWAITING, STATE_COMPLETE) else STATE_INCOMPLETE
```

`cli.py` feeds — three edits in `_execute` (keep all existing echo text unchanged;
Plan B rewords):

1. the empty-winnow return (`:240-242`): `mark_complete(ws, "no shows survived winnowing")`
   before `return`;
2. the gate stop (`:254-257`, `chosen is None`): `mark_awaiting(ws)` before the echo;
3. after the per-entry loop's `finally` block: count outcomes while looping
   (`packaged`/`held`/`failed` counters around the existing `typer.echo` branches at
   `:276-281`) and `mark_complete(ws, f"{p} packaged, {h} held, {f} failed")` (omit
   zero-count parts).

Run-name uniquing — `find` (`cli.py:324`):

```python
    name = run_name or unique_run_name(config.root,
                                       f"{date.today().isoformat()}-{slugify(query)[:40]}")
```

and `profile_run` (`cli.py:1263`):

```python
    ws = RunWorkspace(config.root, unique_run_name(config.root,
                                                   f"{date.today().isoformat()}-{name}"))
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `pytest tests/test_sessions.py -q` then `pytest -q`
Expected: PASS. Any existing test that relied on running `find` twice into the *same*
run dir (silent resume) is asserting the collision bug — update it to resume via
`llama run <name>` explicitly.

- [ ] **Step 5: Commit**

```bash
git add src/llama/sessions.py src/llama/workspace.py src/llama/cli.py tests/test_sessions.py
git commit -m "feat: auto-unique session ids and session.json lifecycle marker"
```

---

### Task 4: Session listing (`SessionInfo` / `iter_sessions`) + `Criteria.profile`

**Files:**
- Modify: `src/llama/sessions.py`, `src/llama/models.py` (`Criteria.profile`),
  `src/llama/cli.py` (`profile_run` stamps `profile=name`)
- Test: extend `tests/test_sessions.py`; extend `tests/test_models.py`

**Interfaces:**
- Produces: `models.Criteria.profile: str | None = None` (additive; stamped for
  display, spec §4). `profile_run`'s criteria-stamp block (`cli.py:1271-1275`) adds
  `"profile": name`.
- Produces (in `sessions.py`):

```python
@dataclass
class SessionInfo:
    id: str
    state: str            # STATE_AWAITING | STATE_COMPLETE | STATE_INCOMPLETE
    updated_at: str       # marker updated_at, else dir-mtime ISO
    query: str            # criteria.query, "" when no criteria.json
    profile: str | None   # criteria.profile
```

  `iter_sessions(root: Path) -> list[SessionInfo]` — every dir under `runs/`,
  newest-first by `updated_at`; and
  `attention_sessions(root: Path) -> list[SessionInfo]` — the subset with
  `state != STATE_COMPLETE` (the attention-list; complete sessions vanish, spec §4).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sessions.py`:

```python
from llama.models import Criteria
from llama.sessions import SessionInfo, attention_sessions, iter_sessions
from llama.workspace import write_artifact


def _session(tmp_path, name, *, state=None, query="q", profile=None):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query=query, profile=profile))
    if state == STATE_AWAITING:
        mark_awaiting(ws)
    elif state == STATE_COMPLETE:
        mark_complete(ws, "done")
    return ws


def test_iter_and_attention_sessions(tmp_path: Path):
    _session(tmp_path, "a-complete", state=STATE_COMPLETE)
    _session(tmp_path, "b-awaiting", state=STATE_AWAITING, profile="sunday-dead-hour")
    _session(tmp_path, "c-crashed")                    # no marker -> incomplete
    infos = {s.id: s for s in iter_sessions(tmp_path)}
    assert infos["a-complete"].state == STATE_COMPLETE
    assert infos["b-awaiting"].state == STATE_AWAITING
    assert infos["b-awaiting"].profile == "sunday-dead-hour"
    assert infos["c-crashed"].state == STATE_INCOMPLETE
    assert {s.id for s in attention_sessions(tmp_path)} == {"b-awaiting", "c-crashed"}


def test_session_without_criteria(tmp_path: Path):
    RunWorkspace(tmp_path, "bare").dir.mkdir(parents=True)
    info = {s.id: s for s in iter_sessions(tmp_path)}["bare"]
    assert info.query == "" and info.profile is None
```

Also: a `test_models.py` addition asserting `Criteria(query="x").profile is None` and
round-trip; a `test_sessions.py` (or `test_profiles.py`) CLI-level check that
`profile run` stamps `criteria.profile == <name>` into the run's `criteria.json`
(drive `profile_run` per existing `tests/test_profiles.py` idioms).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_sessions.py tests/test_models.py -q`
Expected: FAIL — no `SessionInfo`/`iter_sessions`; `Criteria` has no `profile`.

- [ ] **Step 3: Implement**

`iter_sessions` reads each `runs/*/` dir: `session_state(d)`; `updated_at` from the
marker when present else `datetime.fromtimestamp(d.stat().st_mtime, timezone.utc)
.isoformat()`; query/profile from `criteria.json` via
`read_model(RunWorkspace(root, d.name).criteria, Criteria)` guarded by `exists()`.
Sort newest-first by `updated_at`. `Criteria.profile` is one optional field
(document: "profile that produced this session's criteria; display only, spec §4").
`profile_run` stamp: add `"profile": name` to the `model_copy(update={...})` dict at
`cli.py:1271`.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `pytest tests/test_sessions.py tests/test_models.py tests/test_profiles.py -q`
then `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/sessions.py src/llama/models.py src/llama/cli.py tests
git commit -m "feat: session listing with derived lifecycle state; Criteria.profile stamp"
```

---

### Task 5: Shared selector layer (`cli_select.py`)

**Files:**
- Create: `src/llama/cli_select.py`
- Create: `tests/test_cli_select.py`

**Interfaces (spec §2 — the one selector implementation Plan B wires into every
selector-capable command):**

```python
class ShowState(str, Enum):
    held = "held"; selected = "selected"; gathered = "gathered"
    researched = "researched"; vetted = "vetted"; scripted = "scripted"
    packaged = "packaged"; delivered = "delivered"

@dataclass(frozen=True)
class Selector:
    states: frozenset[str]        # empty = no state filter
    voiced: bool | None           # True/False/None (reconciled once here)
    artist: str | None
    run: str | None
    broadcast_ready: bool

def build_selector(*, held=False, packaged=False, states=(), voiced=False,
                   unvoiced=False, artist=None, run=None,
                   broadcast_ready=False) -> Selector
    # --held/--packaged are sugar: add "held"/"packaged" to the states set.
    # `states` is the repeatable --state values (ShowState or str).
    # voiced/unvoiced reconcile to the single tri-state (the three copies at
    # cli.py:737, :843, :1096 collapse here).

def selector_active(sel: Selector) -> bool          # any filter set at all

def apply_selector(entries, sel) -> list[CatalogEntry]
    # delegates to catalog.select_shows(states=..., voiced=..., artist=...,
    # run=..., broadcast_ready=...)

def split_held(entries, sel) -> tuple[list, list]
    # ACTING commands only (spec §2 held opt-in): when "held" NOT in
    # sel.states, partition off held entries; the caller prints HELD_NOTE
    # for the dropped list. When "held" IS in sel.states, nothing is dropped.

HELD_NOTE = "note: {n} held show(s) excluded (add --held to include them)"
```

Behavioral contract (assert all of it):
- filters AND together; multiple states OR together;
- `build_selector(held=True)` ≡ `build_selector(states=["held"])` (sugar identity);
- `voiced=True, unvoiced=True` raises `LlamaError` ("give --voiced or --unvoiced,
  not both") — today this silently resolved to voiced; the shared layer errors;
- `split_held` drops held only when the selector didn't explicitly ask for held;
- `Selector` is pure data — no Typer imports in this module (Plan B owns the
  option declarations).

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_select.py` — pure unit tests over synthetic `CatalogEntry` objects
(pattern from `tests/test_broadcast_ready.py::test_select_shows_broadcast_ready_filter`):
sugar identity, state OR, AND-composition with artist/voiced/broadcast_ready,
`selector_active` truth table, voiced/unvoiced conflict error, `split_held` in both
modes, `HELD_NOTE` formatting, `ShowState` has exactly the eight values.

- [ ] **Step 2: Run to verify they fail** — `pytest tests/test_cli_select.py -q`;
  Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `src/llama/cli_select.py` per the interface above
  (~60 lines; `apply_selector` is a thin wrapper over `catalog.select_shows`,
  `catalog.py:140` — do not duplicate its filtering).

- [ ] **Step 4: Run the tests, then the full suite** — Expected: PASS (existing CLI
  keeps using its old paths; nothing else changes).

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli_select.py tests/test_cli_select.py
git commit -m "feat: shared selector layer with state enum and held opt-in rule"
```

---

### Task 6: Deliver broadcast-ready refusal classifier

**Files:**
- Modify: `src/llama/catalog.py`
- Create: `tests/test_deliver_gate.py`

**Interfaces (spec §7.3):**
- Produces: `catalog.VOICE_BUNDLE_REASONS = ("no DJ script", "no DJ audio (unvoiced)",
  "no broadcast.m3u")` — must reference the exact strings `broadcast_readiness`
  emits (`catalog.py:89-113`); never re-spell them elsewhere.
- Produces: `catalog.deliver_refusals(ws: ShowWorkspace, allow_unvoiced: bool = False)
  -> list[str]` — `broadcast_readiness(ws)[1]`, minus the voice-bundle reasons when
  `allow_unvoiced`. Empty list = deliverable. `"held for review"`,
  `"not packaged"`, and `"... audio files missing"` are never removable — that is a
  property of the subtraction (only the bundle is subtracted), assert it explicitly.

- [ ] **Step 1: Write the failing tests**

`tests/test_deliver_gate.py` — reuse `build_ready` from
`tests/test_broadcast_ready.py` (import it):

```python
from tests.test_broadcast_ready import build_ready   # match existing intra-test imports;
                                                     # if the suite forbids test-package
                                                     # imports, lift build_ready into a
                                                     # tests/helpers module in this task
from llama.catalog import VOICE_BUNDLE_REASONS, deliver_refusals


def test_ready_show_has_no_refusals(tmp_path):
    assert deliver_refusals(build_ready(tmp_path)) == []


def test_unvoiced_show_blocked_then_allowed(tmp_path):
    ws = build_ready(tmp_path, voiced=False, broadcast_m3u=False, script=False)
    assert set(deliver_refusals(ws)) == set(VOICE_BUNDLE_REASONS)
    assert deliver_refusals(ws, allow_unvoiced=True) == []


def test_held_and_missing_audio_never_overridable(tmp_path):
    held = build_ready(tmp_path / "h", needs_review=True)
    assert deliver_refusals(held, allow_unvoiced=True) == ["held for review"]
    broken = build_ready(tmp_path / "b", drop_audio=True)
    assert deliver_refusals(broken, allow_unvoiced=True) == ["1 of 1 audio files missing"]


def test_unpackaged_never_overridable(tmp_path):
    ws = build_ready(tmp_path)
    (ws.package_dir / "manifest.json").unlink()
    assert deliver_refusals(ws, allow_unvoiced=True) == ["not packaged"]
```

- [ ] **Step 2: Run to verify they fail** — Expected: ImportError.

- [ ] **Step 3: Implement** in `catalog.py`, directly after `broadcast_readiness`:

```python
VOICE_BUNDLE_REASONS = ("no DJ script", "no DJ audio (unvoiced)", "no broadcast.m3u")


def deliver_refusals(ws: ShowWorkspace, allow_unvoiced: bool = False) -> list[str]:
    """Why deliver must refuse this show (empty = deliverable). Deliver requires
    broadcast-ready; --allow-unvoiced subtracts exactly the voice bundle — held,
    missing files, and not-packaged are never overridable (spec §7.3)."""
    reasons = broadcast_readiness(ws)[1]
    if allow_unvoiced:
        reasons = [r for r in reasons if r not in VOICE_BUNDLE_REASONS]
    return reasons
```

- [ ] **Step 4: Run the tests, then the full suite** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/catalog.py tests/test_deliver_gate.py
git commit -m "feat: deliver refusal classifier over broadcast-readiness reasons"
```

---

### Task 7: `rm` disposition machinery

**Files:**
- Modify: `src/llama/catalog.py`
- Create: `tests/test_rm_machinery.py`

**Interfaces (spec §8.1):**
- Produces: `catalog.remove_show(entry: CatalogEntry, ledger: Ledger, *,
  forget: bool = False, suppress: bool = False) -> list[str]` — deletes
  `entry.ws.dir` (rmtree) and applies the history disposition, returning the echo
  lines the CLI prints verbatim. `forget` and `suppress` are mutually exclusive
  (`LlamaError` if both).
- History dispositions:
  - default: ledger untouched; echo states what that means, depending on whether the
    pid has rows;
  - `forget`: `ledger.remove(pid)` (all rows);
  - `suppress`: append `LedgerEntry(status="rejected", run="manual", ...)` with
    artist/date/venue from `show.json` when present, else provenance's candidate
    (collection/date/venue).
- No-pid handling: if `_performance_id(entry.ws)` is `None`, default mode still
  deletes (echo notes no history involvement possible); `forget`/`suppress` raise
  `LlamaError("cannot resolve a performance id for <slug>; history flags need one")`.
- Echo lines (exact contracts; `{slug}`, `{n}`, `{pid}` interpolated):
  - `removed shows/{slug}`
  - default, no rows: `no history rows; this show can be re-offered`
  - default, rows exist: `history kept ({statuses}): stays excluded from future gets`
    ({statuses} = sorted unique statuses, comma-joined)
  - forget: `forgot {n} history row(s): re-eligible`
  - suppress: `suppressed: will not be offered again (undo: llama unsuppress {pid})`

- [ ] **Step 1: Write the failing tests**

`tests/test_rm_machinery.py` — build shows via the `test_catalog.py` builders +
`iter_shows` to get real `CatalogEntry`s; cover:

- default on a held-style show (no ledger rows): dir gone, ledger unchanged, echo has
  `can be re-offered`;
- default on a show with `selected`+`delivered` rows: rows retained, echo names both
  statuses;
- `forget=True`: all rows for the pid gone (other pids' rows untouched), echo counts;
- `suppress=True`: dir gone, a `rejected/manual` row appended with artist/date from
  show.json; on a provenance-only show, from the candidate;
- `forget=True, suppress=True` raises `LlamaError`;
- pid-less dir: default deletes; `forget=True` raises.

- [ ] **Step 2: Run to verify they fail** — Expected: ImportError.

- [ ] **Step 3: Implement** in `catalog.py` (import `shutil`,
  `LedgerEntry`, `datetime`). Structure: resolve pid → validate flags → collect the
  pid's existing rows → apply disposition → `shutil.rmtree(entry.ws.dir)` → build
  echo lines. Apply the ledger change *before* the rmtree so a failed disposition
  never leaves the show deleted with history in the wrong state; rmtree last.

- [ ] **Step 4: Run the tests, then the full suite** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/catalog.py tests/test_rm_machinery.py
git commit -m "feat: rm disposition machinery (default/forget/suppress) with history echo"
```

---

### Task 8: Archive-URL / considered-recordings extraction

**Files:**
- Modify: `src/llama/catalog.py`
- Create: `tests/test_recording_info.py`

**Interfaces (spec §10):**

```python
ARCHIVE_URL = "https://archive.org/details/{identifier}"

@dataclass
class ConsideredRecording:
    identifier: str
    score: float
    lineage: str
    kept_tracks: int

@dataclass
class RecordingInfo:
    identifier: str                       # the chosen recording
    url: str                              # ARCHIVE_URL filled in
    considered: list[ConsideredRecording] # scores keys minus chosen, score desc

def recording_info(ws: ShowWorkspace) -> RecordingInfo | None
    # None when selection.json is absent. `considered` is empty when scores
    # holds only the chosen recording. Reads selection.json's
    # {"identifier", "scores": {ident: {"score", "lineage", "kept_tracks", ...}}}
    # exactly as select_recording writes it (select_recording.py:105).
```

- [ ] **Step 1: Write the failing tests**

`tests/test_recording_info.py`: write a `selection.json` with three scored
recordings; assert chosen/url; `considered` excludes the chosen one and is sorted by
score descending; a single-recording selection yields `considered == []`; a missing
`selection.json` yields `None`; a scores entry missing optional keys (defensive:
`score` defaults 0.0, `lineage` `""`, `kept_tracks` 0) still parses.

- [ ] **Step 2: Run to verify they fail** — Expected: ImportError.

- [ ] **Step 3: Implement** in `catalog.py` (~25 lines; `read_json(ws.selection)`).

- [ ] **Step 4: Run the tests, then the full suite** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/catalog.py tests/test_recording_info.py
git commit -m "feat: recording_info extracts archive URL and considered recordings"
```

---

### Task 9: Profile-scratch relocation

**Files:**
- Modify: `src/llama/cli.py` (`profile_add`, :1228)
- Test: extend `tests/test_profiles.py`

**Interfaces:**
- `profile add` no longer creates anything under `<root>/runs/` (spec §11): the
  interpret scratch runs in a `tempfile.TemporaryDirectory`, e.g.
  `scratch = RunWorkspace(Path(tmpdir), "interpret")`, discarded with the tempdir.
  `run_interpret` only needs `ws.criteria` to write; verify by reading
  `stages/interpret.py` before assuming more.

- [ ] **Step 1: Write the failing test** — extend the existing `profile add` test in
  `tests/test_profiles.py` (or `tests/test_cli_commands.py`, wherever `profile add`
  is driven today): after a successful `profile add`, assert
  `not (root / "runs").exists() or not any((root / "runs").iterdir())`.

- [ ] **Step 2: Run to verify it fails** — the scratch dir
  `runs/profile-setup-<name>` exists today.

- [ ] **Step 3: Implement** — wrap the interpret call at `cli.py:1228-1229`:

```python
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = RunWorkspace(Path(tmpdir), "interpret")
        criteria = run_interpret(scratch, make_providers(config)["interpret"], query)
```

- [ ] **Step 4: Run the tests, then the full suite** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests
git commit -m "fix: profile add no longer leaks a scratch run dir"
```

---

## Review checkpoint (end of Plan A)

- [ ] Request a whole-plan code review (superpowers:requesting-code-review) covering
  Tasks 1-9 against spec §§2, 4, 7.3, 8, 9, 10. Key review questions: exact-string
  contracts defined once and asserted verbatim; no behavior change to existing
  commands beyond library-dedup and run-name uniquing; `session.json` confined to
  `runs/`; the held opt-in rule not yet enforced anywhere user-visible (that is
  Plan B's job). Full suite green. Plan A is mergeable on its own at this point.

## Docs (fold into the final task's commit)

- [ ] `CLAUDE.md`: extend the dedup sentence (ledger → "library ∪ ledger") in the
  profiles/ledger bullet; note run-name auto-uniquing. Nothing else — the command
  reference rewrite is Plan B's docs pass.

## Self-review notes

- **Spec coverage:** §9 (Task 1), §8.2 ledger halves + §11 history collapse (Task 2),
  §4 ids/marker/listing (Tasks 3-4), §2 (Task 5), §7.3 (Task 6), §8.1 (Task 7),
  §10 (Task 8), §11 scratch fix (Task 9).
- **Merge-safety:** every task leaves existing CLI behavior intact except Task 1
  (library dedup — spec-mandated, independently desired) and Task 3's uniquing
  (bug fix). `cli_select.py` and `sessions.py` are consumed by nothing user-facing
  until Plan B; that is intentional, not dead code — do not "clean it up".
- **Contracts reused, never re-spelled:** `VOICE_BUNDLE_REASONS` references
  `broadcast_readiness`'s strings; `remove_show` echoes are the CLI's verbatim
  output in Plan B; `HELD_NOTE` likewise.
