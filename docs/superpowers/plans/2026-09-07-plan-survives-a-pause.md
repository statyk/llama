# `--plan` survives a pause in both run modes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `llama get --profile <name> --plan`, parked by the run-level usage-limit catch, must resume as a plan run instead of performing a full acquisition.

**Architecture:** Widen `request.json` from a query-mode artifact into a mode-agnostic invocation record, and have `_get_profile` write one. The reading side in `run_resume` is unchanged — its existing `plan` expression covers both modes once the artifact exists.

**Tech Stack:** Python 3.11+, Typer CLI, Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-plan-survives-a-pause-design.md` — read it first. It records why the two rejected designs (the pause marker, and stamping `plan` into `Criteria`) were rejected; do not re-derive them.

## Global Constraints

- **Worktree with its own venv.** Reuse `/Users/shawn/projects/llama-wt-pacing-loose-ends` (its `.venv` is already installed) on a NEW branch cut from `origin/main`: `git checkout -b plan-both-modes origin/main`. Verify before anything else: `./.venv/bin/python -c "import llama; print(llama.__file__)"` must print a path inside the worktree.
- **Test command:** `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`. Never a bare `pytest`; never a `.venv/bin/<script>` console script — those are shebanged to another checkout, so a mutation does nothing and the suite stays green.
- **Baseline: 1905 passed, 7 deselected.** State the command with flags in every commit message.
- **`auto` is never replayed.** `run resume` has its own explicit `--auto/--interactive` flag; a persisted value must not override it. `auto` stays in the artifact as informational only.
- **Do not touch** `Criteria`, `session.json`, the manifest, or `run approve`.
- Every mutation names its expected red test BEFORE the mutant is applied. A different test failing is a failed prediction to record, not a pass.

---

### Task 1: Mode on the invocation record, plus the migration default

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — `_get_query`, `_interpret_with_pause`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Produces, and Tasks 2–3 consume: `request.json` gains `"mode": "query" | "profile"` and `"profile": str | None`. **A missing `mode` reads as `"query"`** — every artifact written before this change was a query run, because `_get_profile` wrote none.

- [ ] **Step 1: Write the failing tests**

```python
def test_get_stamps_query_mode_on_the_request(tmp_path: Path, monkeypatch):
    """`mode` is explicit rather than inferred from which of query/profile is
    set: a reader that infers will one day meet a run where both or neither is
    populated and pick silently."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "modes"])
    assert result.exit_code == 0, result.output

    req = json.loads((tmp_path / "runs" / "modes" / "request.json").read_text())
    assert req["mode"] == "query"
    assert req["profile"] is None
    assert req["query"] == "GD 1973"


def test_a_request_without_mode_resumes_as_a_query_run(tmp_path: Path, monkeypatch):
    """Runs parked by 67aa074 have no `mode` key, and they are all query runs
    by construction -- `_get_profile` wrote no request at all. Reading a
    missing mode as anything else strands them."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "oldreq")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "auto": True, "plan": False}))
    mark_paused(ws, None, [], "2026-09-07T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "oldreq"])

    assert result.exit_code == 0, result.output
    assert ws.criteria.exists()
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE


def test_interpret_refuses_a_profile_request(tmp_path: Path, monkeypatch):
    """Unreachable today -- `_get_profile` writes criteria.json before
    anything can fail, so a profile run is never criteria-less. The guard
    exists so that if it ever BECOMES reachable it fails loudly instead of
    calling the LLM with query=None."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    called = []
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: called.append(1) or fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "profreq")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"mode": "profile", "query": None,
                                           "profile": "prime-dead",
                                           "auto": True, "plan": False}))
    mark_paused(ws, None, [], "2026-09-07T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "profreq"])

    assert result.exit_code == 1
    assert "profile" in result.output.lower()
    assert called == []              # no LLM call attempted
```

- [ ] **Step 2: Run them and confirm the first and third fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "query_mode_on_the_request or without_mode_resumes or refuses_a_profile_request" -q`
Expected: `test_get_stamps_query_mode_on_the_request` FAILS on `KeyError: 'mode'`; `test_interpret_refuses_a_profile_request` FAILS (it currently calls interpret with `query=None`); `test_a_request_without_mode_resumes_as_a_query_run` PASSES already — it pins behaviour that exists and must survive. Say so in the commit rather than deleting it.

- [ ] **Step 3: Stamp the mode in `_get_query`**

In `cli.py`, in `_get_query`, extend the existing `write_artifact(ws.request, ...)` call:

```python
    write_artifact(ws.request, json.dumps({
        "mode": "query", "query": query, "profile": None,
        "limit": limit, "artist_cap": artist_cap,
        "min_score": min_score, "year_cap": year_cap,
        "auto": auto, "plan": plan}, indent=2))
```

- [ ] **Step 4: Guard `_interpret_with_pause`**

At the top of `_interpret_with_pause`, before any provider is built:

```python
    # A profile run is never criteria-less -- `_get_profile` writes
    # criteria.json before anything can fail -- so this branch is
    # unreachable for one today. The guard is here so that if that ever
    # changes it fails loudly rather than asking the LLM to interpret None.
    if req.get("mode", "query") != "query":
        typer.echo(f"cannot re-interpret a {req['mode']} run: "
                   f"{ws.dir} has no criteria.json", err=True)
        raise typer.Exit(1)
```

`req.get("mode", "query")` is the migration default in its only load-bearing spot: an old request has no `mode` and must be treated as a query run.

- [ ] **Step 5: Run the tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "query_mode_on_the_request or without_mode_resumes or refuses_a_profile_request" -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1908 passed, 7 deselected.

- [ ] **Step 6: Mutation checks**

Two mutants, each predicted first:

1. Change the guard's default to `req.get("mode", "profile")` → predicted red: `test_a_request_without_mode_resumes_as_a_query_run`. This is the migration direction; getting it backwards strands every run parked by `67aa074`.
2. Delete the guard entirely → predicted red: `test_interpret_refuses_a_profile_request`.

Apply each, confirm the observed failing test is the predicted one, restore, confirm clean and green.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_sessions.py
git commit -m "feat(runs): mode on the invocation record, with a query default for old ones"
```

---

### Task 2: `_get_profile` writes the record — the actual fix

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — `_get_profile`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes Task 1's schema. Produces nothing new; `run_resume`'s existing `plan` expression is untouched and now covers both modes.

- [ ] **Step 1: Write the failing tests**

```python
def _parked_profile_run(tmp_path: Path, name: str, *, plan: bool,
                        with_shortlist: bool = False):
    """A profile run parked exactly as the run-level RateLimited catch leaves
    one: criteria.json present (written before any stage ran), request.json
    present, session paused."""
    from llama.profiles import Profile, save_profile

    save_profile(tmp_path, Profile(
        name="prime-dead",
        criteria=Criteria(query="x", collection="GratefulDead",
                          artist="Grateful Dead",
                          date_from="1973-01-01", date_to="1973-12-31"),
        count=1, human_gate=False))
    ws = RunWorkspace(tmp_path, name)
    ws.dir.mkdir(parents=True)
    write_artifact(ws.criteria, Criteria(query="x", collection="GratefulDead",
                                         artist="Grateful Dead",
                                         date_from="1973-01-01",
                                         date_to="1973-12-31", count=1,
                                         profile="prime-dead"))
    write_artifact(ws.request, json.dumps({"mode": "profile", "query": None,
                                           "profile": "prime-dead",
                                           "auto": True, "plan": plan}))
    if with_shortlist:
        write_artifact(ws.shortlist, [])
    mark_paused(ws, None, [], "2026-09-07T15:10:00+00:00", "five_hour", "limit")
    return ws


def test_a_parked_profile_plan_run_resumes_as_a_plan_run(tmp_path: Path, monkeypatch):
    """The bug: the operator asked to see a shortlist, the run was interrupted,
    and following the CLI's own `run resume` hint packaged shows instead."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    ws = _parked_profile_run(tmp_path, "profplan", plan=True)

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "profplan"])

    assert result.exit_code == 0, result.output
    assert "packaged:" not in result.output          # nothing was processed
    assert "run approve profplan" in result.output
    assert iter_sessions(tmp_path)[0].state == STATE_AWAITING


def test_a_parked_profile_run_without_plan_still_processes(tmp_path: Path, monkeypatch):
    """Guards against replaying plan unconditionally."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    _parked_profile_run(tmp_path, "profgo", plan=False)

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "profgo"])

    assert result.exit_code == 0, result.output
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE


def test_a_parked_profile_plan_run_processes_once_a_shortlist_exists(
        tmp_path: Path, monkeypatch):
    """`--plan` means "stop AT the shortlist", so the directive is satisfied
    once one exists. Without this, `request.json` carries plan:true forever
    and every later resume re-parks the session -- permanently."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    _parked_profile_run(tmp_path, "profdone", plan=True, with_shortlist=True)

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "profdone"])

    assert result.exit_code == 0, result.output
    assert iter_sessions(tmp_path)[0].state != STATE_AWAITING


def test_get_profile_writes_the_invocation_record(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    save_profile(tmp_path, Profile(
        name="prime-dead",
        criteria=Criteria(query="x", collection="GratefulDead",
                          artist="Grateful Dead",
                          date_from="1973-01-01", date_to="1973-12-31"),
        count=1, human_gate=False))
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile",
                                     "prime-dead", "--auto", "--plan"])
    assert result.exit_code == 0, result.output

    run_dir = next((tmp_path / "runs").glob("*-prime-dead"))
    req = json.loads((run_dir / "request.json").read_text())
    assert req["mode"] == "profile"
    assert req["profile"] == "prime-dead"
    assert req["query"] is None
    assert req["plan"] is True
```

- [ ] **Step 2: Run them and confirm three fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "parked_profile or get_profile_writes" -q`
Expected: `test_a_parked_profile_plan_run_resumes_as_a_plan_run` FAILS (the run completes and packages instead of parking awaiting) and `test_get_profile_writes_the_invocation_record` FAILS on a missing file. The other two PASS already and are pins.

- [ ] **Step 3: Write the record in `_get_profile`**

In `cli.py`, in `_get_profile`, immediately after `ws = RunWorkspace(...)` and before `_execute`:

```python
    # The same invocation record `_get_query` writes. Without it a profile
    # run parked by the run-level catch resumes with plan=False and performs
    # a full acquisition -- from the recovery path the CLI itself prints.
    # The query-mode selection flags are None here: a profile run takes those
    # values from its stored criteria, not from argv.
    write_artifact(ws.request, json.dumps({
        "mode": "profile", "query": None, "profile": name,
        "limit": None, "artist_cap": None,
        "min_score": None, "year_cap": None,
        "auto": auto, "plan": plan}, indent=2))
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "parked_profile or get_profile_writes" -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1912 passed, 7 deselected.

- [ ] **Step 5: Mutation checks**

1. Delete the `write_artifact(ws.request, ...)` call → predicted red: `test_a_parked_profile_plan_run_resumes_as_a_plan_run` and `test_get_profile_writes_the_invocation_record`. Name both before applying; a mutant predicted to redden two tests must redden exactly those two.
2. Drop `and not ws.shortlist.exists()` from `run_resume` → predicted red: `test_a_parked_profile_plan_run_processes_once_a_shortlist_exists` (and the equivalent query-mode test from `67aa074`). This guard is already pinned for query mode; confirm the profile pin is independent.
3. Make `_get_profile` write `"mode": "query"` → predicted red: Task 3's `test_run_list_names_a_parked_profile_run_with_no_criteria`. Run this one AFTER Task 3 lands and record it there; noted here because it is this task's line that the mutant edits.
4. Replay `auto` from the request — pass `auto=bool(req.get("auto"))` into `_execute` instead of the explicit flag → predicted red: the existing `auto`-not-replayed test from `67aa074`. `run resume` has its own `--auto/--interactive`, and a persisted value must never override an explicit one. Confirm that pin still holds now that a second writer produces requests.

Apply each, confirm, restore.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_sessions.py
git commit -m "fix(cli): --plan survives a pause on a profile run too"
```

---

### Task 3: `run list` names a parked profile run

**Files:**
- Modify: `packages/llama/src/llama/sessions.py` — `iter_sessions`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes Task 1's `mode` and Task 2's writer.

- [ ] **Step 1: Write the failing test**

```python
def test_run_list_names_a_parked_profile_run_with_no_criteria(tmp_path: Path):
    """A criteria-less parked run renders from the request. For a profile run
    that must be `profile: <name>`, not an empty pair of quotes -- the same
    defect fixed for query runs, one mode over.

    Both renderers are checked: `_print_sessions` and `_session_json` are
    separate code paths over the same SessionInfo, and the query half of this
    branch needed both pinned.
    """
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    ws = RunWorkspace(tmp_path, "profparked")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"mode": "profile", "query": None,
                                           "profile": "prime-dead",
                                           "auto": True, "plan": True}))
    mark_paused(ws, None, [], "2026-09-07T15:10:00+00:00", "five_hour", "limit")

    info = iter_sessions(tmp_path)[0]
    assert info.profile == "prime-dead"
    assert info.query == ""

    plain = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert plain.exit_code == 0, plain.output
    assert "profile: prime-dead" in plain.output

    as_json = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])
    assert as_json.exit_code == 0, as_json.output
    assert json.loads(as_json.output)[0]["profile"] == "prime-dead"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py::test_run_list_names_a_parked_profile_run_with_no_criteria -q`
Expected: FAIL — `info.profile` is `None`.

- [ ] **Step 3: Teach `iter_sessions` the mode**

In `packages/llama/src/llama/sessions.py`, in `iter_sessions`, extend the existing `elif` branch:

```python
            elif ws.request.exists():
                # Paused before criteria existed: the persisted request is the
                # only copy of what this run was asked to do. A missing `mode`
                # means an artifact written before modes existed, and those
                # were all query runs.
                req = json.loads(ws.request.read_text())
                if req.get("mode", "query") == "profile":
                    profile = req.get("profile")
                else:
                    query = req.get("query") or ""
```

- [ ] **Step 4: Run the test, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py::test_run_list_names_a_parked_profile_run_with_no_criteria -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1913 passed, 7 deselected.

The existing `test_run_list_shows_the_query_of_a_run_with_no_criteria` and `test_run_list_json_survives_a_session_with_no_criteria` must stay green untouched — they pin the query half of this same branch.

- [ ] **Step 5: Mutation check**

Two mutants, each predicted first:

1. Make the branch read `req.get("mode", "profile")` → reddens `test_run_list_shows_the_query_of_a_run_with_no_criteria`, because an old modeless request would render as a profile run with no name.
2. Task 2's deferred mutant, now runnable: make `_get_profile` write `"mode": "query"` → reddens `test_run_list_names_a_parked_profile_run_with_no_criteria`. Record the result in this task.

Apply each, confirm, restore.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/sessions.py packages/llama/tests/test_sessions.py
git commit -m "fix(runs): name a parked profile run on the attention list"
```

---

## Final verification

- [ ] `./.venv/bin/python -m pytest -q` → 1913 passed, 7 deselected, exit 0
- [ ] `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree
- [ ] `--collect-only` node-ID diff against `origin/main`: 8 added, 0 removed
- [ ] Every mutation ran with its predicted red test named first, and the observed failure matched
- [ ] `git log --oneline` shows one commit per task, tree clean

The per-task counts are expected deltas from the 1905 baseline, not decoration: a task that lands its tests and reports a lower total has lost an existing test. Report that rather than adjusting the number.
