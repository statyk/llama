# Usage-pacing loose ends — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four follow-ups the usage-pacing phase 2 ledger handed forward — T6b (a usage limit during `run_interpret`), rendering the `per_model` meter, and two test gaps.

**Architecture:** Three small independent items (Tasks 1–3) followed by T6b in four strictly-ordered tasks (4–7). The T6b order is load-bearing: `request.json` and the resume branch land *before* the pause site that depends on them, so the tree is never in a state where a pause parks an unresumable run.

**Tech Stack:** Python 3.11+, Typer CLI, Pydantic v2 models, pytest, `herder` (LLM/usage layer).

**Spec:** `docs/superpowers/specs/2026-09-06-pacing-loose-ends-design.md` — read it before Task 1. The plan argues from it.

## Global Constraints

- **Worktree venv.** In a git worktree, give it its own `.venv` and run `./.venv/bin/python -m pytest`. A bare `pytest`, or any `.venv/bin/*` console script from a copied tree, silently tests the *other* checkout and passes. Verify once, first thing: `./.venv/bin/python -c "import llama; print(llama.__file__)"` must resolve inside the worktree.
- **Test command:** `./.venv/bin/python -m pytest -q` from the worktree root.
- **Baseline:** 1871 passed, 7 deselected, on `main` @ `45f009b`.
- **Offline and deterministic.** The suite never touches the network and never reads a real usage meter. `_meter_applies` already gates reads on `backend == "claude_cli"`; tests monkeypatch `cli.read_usage`.
- **Do not retune measured constants.** `SHORT_FRACTION_OF_MEDIAN`, `MIN_PLAUSIBLE_SEC`, `MIN_MEDIAN_SAMPLE`, the tail-guard trio, the sibling-transfer four. None of them are in scope here; do not touch them.
- **`decide()` stays on two meters.** Task 1 renders `per_model` and nothing more.
- **Commit per task**, message in the repo's style (lowercase `type(scope): subject`, body explaining *why*).
- **Every mutation check names its expected red test BEFORE the mutant is applied.** "Some failure appeared" is not a caught mutant.

---

### Task 1: Render the `per_model` meter (render-only)

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — `_pacing_line`
- Test: `packages/llama/tests/test_pace_loop.py`

**Interfaces:**
- Consumes: `herder.usage.UsageReading.per_model: dict[str, Meter]`, already parsed and already carried through every call site.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_pace_loop.py`, beside the other `_pacing_line` tests:

```python
def test_the_line_renders_the_per_model_meter():
    """`/usage` reports a per-model window (`Current week (Fable)`) that the
    account may exhaust before either window `decide` watches. Rendering it
    is how an operator sees that coming; it deliberately does NOT bind."""
    from herder.usage import Meter, UsageReading
    reading = UsageReading(five_hour=Meter(12, RESET_5H),
                           seven_day=Meter(40, RESET_7D),
                           per_model={"Fable": Meter(42, None)}, fetched_at=NOW)

    line = cli._pacing_line(reading, pacing_state.PacingState(3.1, 3),
                            pacing.pace_options(Config()))

    assert line.startswith("pacing: 5h 12% · weekly 40% · Fable 42% · est 3.1%/show")


def test_per_model_meters_render_in_a_stable_order():
    """Dict order is insertion order, which is parse order, which is the
    account's. Sorting makes the line diffable across runs."""
    from herder.usage import Meter, UsageReading
    reading = UsageReading(five_hour=Meter(12, RESET_5H),
                           seven_day=Meter(40, RESET_7D),
                           per_model={"Zeta": Meter(9, None),
                                      "Alpha": Meter(1, None)}, fetched_at=NOW)

    line = cli._pacing_line(reading, pacing_state.PacingState(3.1, 3),
                            pacing.pace_options(Config()))

    assert "Alpha 1% · Zeta 9%" in line


def test_decide_ignores_the_per_model_meter():
    """The render is not a policy change. A per-model window at 99% must not
    pause a run: the key is account-dependent, so binding on it could stop an
    unattended run for hours against a window llama never spends. The
    reactive RateLimited backstop is what covers a real refusal."""
    from herder.usage import Meter, UsageReading
    reading = UsageReading(five_hour=Meter(10, RESET_5H),
                           seven_day=Meter(7, RESET_7D),
                           per_model={"Fable": Meter(99, None)}, fetched_at=NOW)

    verdict = pacing.decide(NOW, reading, pacing.Progress(4.0),
                            pacing.pace_options(Config()))

    assert isinstance(verdict, pacing.Proceed)
```

- [ ] **Step 2: Run them and confirm the first two fail, the third passes**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_pace_loop.py -k "per_model" -q`
Expected: `test_the_line_renders_the_per_model_meter` and `test_per_model_meters_render_in_a_stable_order` FAIL (the label is absent from the line); `test_decide_ignores_the_per_model_meter` PASSES already — it is a *pin* on behaviour that exists, not a driver. Say so in the commit rather than deleting it.

- [ ] **Step 3: Add the conditional part to `_pacing_line`**

In `cli.py`, in `_pacing_line`, immediately after the `seven_day` block and before the `per_show_delta` block:

```python
    # The account's per-model window, when /usage reported one. Rendered but
    # NOT consulted by `decide` -- see the spec's evidence bar for binding it.
    # Sorted because dict order here is the account's parse order.
    for label, meter in sorted(reading.per_model.items()):
        parts.append(f"{label} {meter.percent}%")
```

Nothing else changes. `per_model` defaults to `{}`, so the loop renders nothing when the meter is absent — matching this function's existing rule that a placeholder for an unknown value reads as a measurement.

- [ ] **Step 4: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: 1874 passed (1871 + 3), 7 deselected. Existing tests that assert full-line equality (e.g. `test_the_missing_reset_guard_follows_the_binding_window`) already pin the empty-`per_model` case and must stay green untouched — if one goes red, the loop was inserted in the wrong place.

- [ ] **Step 5: Mutation check**

Two mutants, each with its predicted red test named before it is applied:

1. Delete the `sorted()` wrapper → reddens `test_per_model_meters_render_in_a_stable_order` **by name**.
2. Make `decide()` read the per-model meter — add `_pause(max(reading.per_model.values(), key=lambda m: m.percent, default=None), opts.five_hour_ceiling, "five_hour", projected, now, opts)` to its rule chain → reddens `test_decide_ignores_the_per_model_meter` **by name**. This is the one that matters: it proves the render-only boundary is enforced by a test and not merely by intent.

Apply each, confirm the predicted name is the one that fails, restore.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_pace_loop.py
git commit -m "feat(pacing): render the per-model usage meter (render-only)"
```

---

### Task 2: Generalize the config-template key-set assertion

**Files:**
- Modify: `packages/llama/tests/test_config.py`

**Interfaces:**
- Consumes: `llama.config.DEFAULT_CONFIG_TOML`, `llama.config.Config`.
- Produces: nothing other tasks depend on.

**Context the implementer needs.** `test_default_config_template_matches_defaults` compares parsed *behaviour*, so a key omitted from the template still parses to its default and passes — it catches a wrong value, never an absent one. Two facts, both measured 2026-09-06, decide the shape of the fix:

1. The template documents `root`, `delivery_path` and `[setlistfm] api_key` as **commented-out examples**, so an assertion that reads only parsed TOML calls a correct template incomplete.
2. `[selection]`'s two fields are documented as **nested table headers** — `[selection.tapers.GratefulDead]` and `[[selection.lineage_eras]]` — not as `key =` lines, and one of those names is capitalized.

An extractor that misses either fact fails against a template that is actually correct. Do not "fix" that by weakening the assertion.

- [ ] **Step 1: Write the failing test**

Add to `packages/llama/tests/test_config.py`:

```python
_TEMPLATE_KEY = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_TEMPLATE_SECTION = re.compile(r"^\s*#?\s*\[\[?([A-Za-z_][A-Za-z0-9_.\-]*)\]\]?\s*$")


def _template_keys(text: str) -> dict[str, set[str]]:
    """Every key the seeded template mentions, per section path.

    Commented lines count: `config init` documents the path knobs and
    [setlistfm] as commented examples, so a parsed-only view would call a
    correct template incomplete. Nested table headers count too, and for the
    same reason -- [selection.tapers.X] and [[selection.lineage_eras]] are how
    `selection`'s two fields are documented; neither appears as `key =`.
    """
    out: dict[str, set[str]] = {"": set()}
    current = ""
    for line in text.splitlines():
        m = _TEMPLATE_SECTION.match(line)
        if m:
            current = m.group(1)
            parts = current.split(".")
            # `[a.b.c]` documents key `b` of section `a`, `c` of `a.b`, ...
            for i in range(1, len(parts) + 1):
                out.setdefault(".".join(parts[:i - 1]), set()).add(parts[i - 1])
            out.setdefault(current, set())
            continue
        m = _TEMPLATE_KEY.match(line)
        if m:
            out.setdefault(current, set()).add(m.group(1))
    return out


# Free-form maps: `dict[str, LLMTaskConfig]` and `dict[str, dict[Tier, str]]`
# have no fixed key set to assert against, so there is nothing here to check.
_FREE_FORM = {"llm", "tiers"}


def test_the_template_documents_every_config_key():
    """The behaviour comparison above cannot see a key that is simply absent:
    it parses to its default and agrees. And the seeded file is how an
    operator discovers a knob exists at all -- nothing else tells them a
    ceiling is there to lower. Measured 2026-09-06: this passes today with no
    template change; it exists to keep that true.
    """
    from pydantic import BaseModel

    sections = _template_keys(DEFAULT_CONFIG_TOML)
    undocumented: dict[str, list[str]] = {}
    for name, field in Config.model_fields.items():
        if name in _FREE_FORM:
            continue
        ann = field.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            missing = set(ann.model_fields) - sections.get(name, set())
            if missing:
                undocumented[name] = sorted(missing)
        elif name not in sections[""]:
            undocumented["<top-level>"] = undocumented.get("<top-level>", []) + [name]

    assert undocumented == {}, f"keys missing from DEFAULT_CONFIG_TOML: {undocumented}"
```

Add `import re` to the file's imports if it is not already there.

- [ ] **Step 2: Run it**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_config.py::test_the_template_documents_every_config_key -q`
Expected: **PASS.** This test is bit-rot protection, so a green first run is the correct outcome — the mutation in Step 3 is what proves it can fail. If it goes red, the extractor is wrong (check the two facts above), not the template.

- [ ] **Step 3: Mutation check — the real verification**

Prediction, written first: deleting the `five_hour_ceiling = 90` line from `DEFAULT_CONFIG_TOML` reddens `test_the_template_documents_every_config_key` **by name**, reporting `{'pacing': ['five_hour_ceiling']}`.

```bash
# apply the mutant, run, confirm the predicted test and message, then restore
./.venv/bin/python -m pytest packages/llama/tests/test_config.py -q
git checkout packages/llama/src/llama/config.py
```

Also confirm the mutant does **not** redden `test_default_config_template_matches_defaults` — that is the whole point: the old test cannot see this.

- [ ] **Step 4: Retire the narrow version**

`test_default_config_template_documents_every_pacing_knob` is now the `[pacing]`-only special case of the new test. Delete it and note in the commit that the general test subsumes it.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: 1874 passed (Task 1's +3, then +1 new and −1 retired), 7 deselected.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/tests/test_config.py
git commit -m "test(config): assert the template documents every key, not just every value"
```

---

### Task 3: "Resume costs nothing" — the call-counting test

**Files:**
- Modify: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes: `fake_providers`, `FakeIA`, `JB_OFF` from `test_pipeline` (already imported at the top of `test_sessions.py`).
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Write the test**

Add to `packages/llama/tests/test_sessions.py`:

```python
class CountingProvider:
    """Wraps a provider and counts every call that reaches it."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self.inner.complete(prompt)

    def research(self, brief: str) -> str:
        self.calls += 1
        return self.inner.research(brief)


def test_resuming_a_packaged_run_costs_no_llm_calls(tmp_path: Path, monkeypatch):
    """`CLAUDE.md` promises operators that "resuming costs nothing for shows
    already packaged" -- the property is `should_run`'s, and nothing tested
    it. A pause is only cheap to recover from if this holds.
    """
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = {k: CountingProvider(v) for k, v in fake_providers(None).items()}
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    first = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                    "--auto", "--name", "cheap"])
    assert first.exit_code == 0, first.output

    spent = sum(p.calls for p in providers.values())
    # The non-empty precondition, and the reason this test is worth having:
    # `== spent` below is satisfied just as happily by a run that never
    # happened. Assert the work occurred before asserting it is not repeated.
    assert spent > 0

    resumed = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "cheap"])
    assert resumed.exit_code == 0, resumed.output

    assert sum(p.calls for p in providers.values()) == spent
```

- [ ] **Step 2: Run it**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py::test_resuming_a_packaged_run_costs_no_llm_calls -q`
Expected: PASS.

**If it fails, do not weaken the assertion to `>=` or scope it to a subset of providers.** A resume that spends an LLM call means some stage is not gating on `should_run`, which is a real finding about shipped behaviour. Report which provider fired and how many times, and stop for a ruling.

- [ ] **Step 3: Mutation check**

Prediction, written first: changing the resume invocation to `["--config", cfg, "get", "GD 1973", "--auto", "--name", "cheap2"]` (a fresh run instead of a resume) reddens `test_resuming_a_packaged_run_costs_no_llm_calls` on the final equality. Apply, confirm, restore. This proves the test measures re-entry rather than the mere existence of a second invocation.

- [ ] **Step 4: Commit**

```bash
git add packages/llama/tests/test_sessions.py
git commit -m "test(sessions): pin that resuming a packaged run spends no LLM calls"
```

---

### Task 4: Persist the request at run-claim time

**Files:**
- Modify: `packages/llama/src/llama/workspace.py` — `RunWorkspace.__init__`
- Modify: `packages/llama/src/llama/cli.py` — `_get_query`
- Modify: `packages/llama/src/llama/sessions.py` — `iter_sessions`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Produces, and Tasks 5–7 consume:
  - `RunWorkspace.request: Path` — `runs/<id>/request.json`
  - the on-disk shape `{"query": str, "limit": int|None, "artist_cap": float|None, "min_score": float|None, "year_cap": float|None, "auto": bool, "plan": bool}`

- [ ] **Step 1: Write the failing tests**

```python
def test_get_persists_the_request_before_interpreting(tmp_path: Path, monkeypatch):
    """The query lives only in argv. Without this artifact a limit during
    interpret parks a session nothing can resume -- which is why T6b was a
    resumability design and not a try/except."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "req", "--limit", "2"])
    assert result.exit_code == 0, result.output

    req = json.loads((tmp_path / "runs" / "req" / "request.json").read_text())
    assert req["query"] == "GD 1973"
    assert req["limit"] == 2
    assert req["auto"] is True


def test_run_list_shows_the_query_of_a_run_with_no_criteria(tmp_path: Path):
    """A run paused at interpret has no criteria.json, and `iter_sessions`
    defaults `query` to "" -- so the one run whose query the operator most
    needs to see would list as an empty pair of quotes."""
    ws = RunWorkspace(tmp_path, "parked")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1977 Cornell"}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    info = iter_sessions(tmp_path)[0]

    assert info.query == "GD 1977 Cornell"
    assert info.profile is None
```

```python
def test_run_list_json_survives_a_session_with_no_criteria(tmp_path: Path):
    """`run list --json` renders the same sessions through `_session_json`.
    A run parked before interpret is the first session in this codebase to
    reach either renderer without a criteria.json, so both paths are pinned."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    ws = RunWorkspace(tmp_path, "parked2")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1977 Cornell"}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["query"] == "GD 1977 Cornell"
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "persists_the_request or shows_the_query or list_json_survives" -q`
Expected: FAIL — no `request.json` is written, and `info.query` is `""`.

- [ ] **Step 3: Add the workspace path**

In `packages/llama/src/llama/workspace.py`, in `RunWorkspace.__init__`, beside `self.criteria`:

```python
        self.request = self.dir / "request.json"
```

- [ ] **Step 4: Write it in `_get_query`**

In `cli.py`, in `_get_query`, immediately after `ws = RunWorkspace(config.root, run_name)` and **before** any LLM call:

```python
    # Persisted BEFORE the first LLM call: a limit during interpret parks a
    # session whose query would otherwise live only in argv. This artifact is
    # what makes such a session resumable at all (T6b).
    write_artifact(ws.request, json.dumps({
        "query": query, "limit": limit, "artist_cap": artist_cap,
        "min_score": min_score, "year_cap": year_cap,
        "auto": auto, "plan": plan}, indent=2))
```

`cli.py` does not import `json` at module level (only `import json as _json` inside `run_list`). Add `import json` to the module imports and leave the local alias alone — removing it is unrelated churn.

- [ ] **Step 5: Fall back to it in `iter_sessions`**

In `packages/llama/src/llama/sessions.py`, in `iter_sessions`, extend the existing branch:

```python
            query, profile = "", None
            if ws.criteria.exists():
                criteria = read_model(ws.criteria, Criteria)
                query, profile = criteria.query, criteria.profile
            elif ws.request.exists():
                # Paused before interpret ever wrote criteria: the persisted
                # request carries the only copy of the query.
                query = json.loads(ws.request.read_text()).get("query") or ""
```

- [ ] **Step 6: Run the tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "persists_the_request or shows_the_query or list_json_survives" -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1878 passed, 7 deselected.

`_session_json` may need the same fallback as `_print_sessions` if it reads criteria directly rather than going through `SessionInfo`. Check it before assuming the `--json` test passes for free.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/workspace.py packages/llama/src/llama/cli.py \
        packages/llama/src/llama/sessions.py packages/llama/tests/test_sessions.py
git commit -m "feat(runs): persist the raw query at run-claim time (T6b groundwork)"
```

---

### Task 5: `run resume` re-interprets when there is no criteria

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — new `_interpret_and_stamp`, `_get_query`, `run_resume`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes: `RunWorkspace.request` and the request shape from Task 4.
- Produces, and Task 7 consumes:
  - `_interpret_and_stamp(config, ws: RunWorkspace, req: dict) -> Criteria` — runs `run_interpret` on `req["query"]`, stamps the explicit flags into the run's criteria, writes `criteria.json`, and returns the `Criteria`.

- [ ] **Step 1: Write the failing tests**

```python
def test_run_resume_reinterprets_a_session_that_never_got_criteria(
        tmp_path: Path, monkeypatch):
    """The branch T6b exists for: a session parked before interpret finished
    has a request but no criteria, and today `run resume` refuses it."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "reinterp")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "reinterp"])

    assert result.exit_code == 0, result.output
    assert ws.criteria.exists()                    # interpret ran and persisted
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE


def test_run_resume_replays_the_flags_the_request_recorded(
        tmp_path: Path, monkeypatch):
    """A resumed interpret must behave like the original command, not like
    the defaults -- the flags were stamped into criteria on the first pass and
    have to be stamped again here or the replay silently differs."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "flags")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 3,
                                           "artist_cap": 0.5, "min_score": 7.5,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    runner.invoke(cli.app, ["--config", cfg, "run", "resume", "flags"])

    criteria = read_model(ws.criteria, Criteria)
    assert criteria.count == 3
    assert criteria.artist_cap == 0.5
    assert criteria.min_quality_score == 7.5


def test_run_resume_still_refuses_a_dir_with_neither_artifact(tmp_path: Path):
    """The pre-existing "not a llama run dir" case must keep its message."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    ws = RunWorkspace(tmp_path, "empty")
    ws.dir.mkdir(parents=True)

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "empty"])

    assert result.exit_code == 1
    assert "no criteria.json" in result.output
```

`read_model` and `Criteria` are already imported in `test_sessions.py`.

- [ ] **Step 2: Run them and confirm the first two fail on today's refusal**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "reinterprets or replays_the_flags or refuses_a_dir" -q`
Expected: the first two FAIL with exit code 1 and "no criteria.json"; the third PASSES (it pins behaviour that already exists).

- [ ] **Step 3: Extract the interpret-and-stamp helper**

In `cli.py`, add above `_get_query`:

```python
def _interpret_and_stamp(config, ws: RunWorkspace, req: dict) -> Criteria:
    """Interpret a persisted request and stamp its explicit flags.

    ONE function for both entry points -- `_get_query`'s first pass and
    `run resume`'s re-interpret -- because a resume that stamped a different
    set of flags than the original command would replay as a different run,
    silently. Two copies of this is exactly the drift T6b's checkpoint would
    otherwise introduce.
    """
    criteria = run_interpret(ws, make_providers(config)["interpret"], req["query"])
    updates = {}
    if req.get("limit"):
        updates["count"] = req["limit"]
    if req.get("artist_cap") is not None:
        updates["artist_cap"] = req["artist_cap"]
    if req.get("min_score") is not None:
        updates["min_quality_score"] = req["min_score"]
    if req.get("year_cap") is not None:
        updates["year_cap"] = req["year_cap"]
    if updates:
        criteria = criteria.model_copy(update=updates)
        write_artifact(ws.criteria, criteria)
    return criteria
```

- [ ] **Step 4: Route `_get_query` through it**

Replace `_get_query`'s `run_interpret` call and the `updates = {}` block that follows it with:

```python
    criteria = _interpret_and_stamp(config, ws, {
        "query": query, "limit": limit, "artist_cap": artist_cap,
        "min_score": min_score, "year_cap": year_cap})
```

Build that dict from the same values Task 4 persists — do not re-read `request.json` here; the file is the checkpoint, not the parameter-passing mechanism.

- [ ] **Step 5: Add the one new branch to `run_resume`**

In `run_resume`, replace the `if not ws.criteria.exists():` block with:

```python
    if not ws.criteria.exists():
        if not ws.request.exists():
            typer.echo(f"no criteria.json in {ws.dir}", err=True)
            raise typer.Exit(1)
        # Parked before interpret ever succeeded (T6b). The persisted request
        # is enough to re-interpret and carry on.
        criteria = _interpret_and_stamp(config, ws, json.loads(ws.request.read_text()))
    else:
        criteria = read_model(ws.criteria, Criteria)
```

- [ ] **Step 6: Run the tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "reinterprets or replays_the_flags or refuses_a_dir" -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1881 passed, 7 deselected.

- [ ] **Step 7: Mutation check**

Two mutants, each predicted before it is applied:

1. Drop the `if req.get("artist_cap") is not None:` clause from `_interpret_and_stamp` → reddens `test_run_resume_replays_the_flags_the_request_recorded` **by name**. A green suite here would mean the flags are not actually replayed.
2. Delete the `write_artifact(ws.request, ...)` call added in Task 4 → reddens `test_get_persists_the_request_before_interpreting` **and** leaves `test_run_resume_reinterprets_a_session_that_never_got_criteria` passing (it builds its own request by hand). That asymmetry is the point: the resume branch and the artifact that feeds it are pinned by different tests, so losing either is visible.

Apply each, confirm, restore.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_sessions.py
git commit -m "feat(cli): run resume re-interprets a session parked before criteria (T6b)"
```

---

### Task 6: Gate before interpret

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — new `_preflight_gate`, `_execute`, `_get_query`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes: `_meter`, `decide`, `Progress`, `PauseUntil`, `_render_pause`, `pacing_state.read_state` — all already in `cli.py`.
- Consumes from Task 3: the `CountingProvider` test class, already added to `test_sessions.py`. Do not define a second copy.
- Produces for Task 7: the module-level `PF_NOW` constant and `_preflight_reading` helper added to `test_sessions.py` in Step 1.
- Produces:
  - `_preflight_gate(ws, config, pace, state, *, note: str) -> tuple[bool, object]` — returns `(proceed, reading)`. `proceed=False` means a checkpoint was written and the caller must return. `reading` is the reading the final verdict was computed from.

**Why this task comes after Tasks 4 and 5.** It adds a pause site that can checkpoint a run *before* `criteria.json` exists. Landing it first would park runs nothing could resume. With the request artifact and the resume branch already in, the checkpoint is recoverable the moment it becomes possible.

- [ ] **Step 1: Write the failing test**

```python
def test_the_preflight_gate_runs_before_interpret_is_paid_for(
        tmp_path: Path, monkeypatch):
    """The gate lives at the top of `_execute`, which in query mode runs
    AFTER run_interpret -- so interpret was the one LLM call a run made with
    no proactive check at all, and an unattended `--wait` run could be
    defeated by its own first call."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n{JB_OFF}\n[llm.default]\nbackend = "claude_cli"\n')
    providers = {k: CountingProvider(v) for k, v in fake_providers(None).items()}
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _preflight_reading(five=99))
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                                     "--no-wait", "--name", "gated"])

    assert result.exit_code == 0, result.output
    assert providers["interpret"].calls == 0        # never paid for
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
```

with these module-level helpers in `test_sessions.py`:

```python
PF_NOW = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)


def _preflight_reading(five=10, seven=7):
    from herder.usage import Meter, UsageReading
    return UsageReading(five_hour=Meter(five, PF_NOW + timedelta(hours=2)),
                        seven_day=Meter(seven, PF_NOW + timedelta(days=3)),
                        per_model={}, fetched_at=PF_NOW)
```

The config sets `backend = "claude_cli"` deliberately: `_meter_applies` gates meter reads on the backend, so under the default fake backend the gate never fires and the test would pass for the wrong reason.

- [ ] **Step 2: Run it and confirm it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py::test_the_preflight_gate_runs_before_interpret_is_paid_for -q`
Expected: FAIL on `providers["interpret"].calls == 0` — interpret is called before the gate exists.

- [ ] **Step 3: Extract the gate**

In `cli.py`, add above `_execute`:

```python
def _preflight_gate(ws: RunWorkspace, config: Config, pace: PaceOptions,
                    state, *, note: str) -> tuple[bool, object]:
    """Meter, decide, and pause until the window can take the next unit.

    Returns `(proceed, reading)`. The reading comes back because the caller
    prints its pacing line from it: a second `_meter` call would spend
    another subprocess to print a line that could disagree with the decision
    already taken.

    Sleeps AT MOST ONCE. Nothing completes between naps at a site where no
    work has run, so a second pause passes `stalled=True` -- without it a
    `when` already in the past makes `sleep_until` return immediately and the
    pause becomes a hot spin, which hangs the suite rather than reddening it.
    """
    slept = False
    while True:
        reading = _meter(config, pace)
        verdict = decide(_pacing._now(), reading, Progress(state.per_show_delta), pace)
        if not isinstance(verdict, PauseUntil):
            return True, reading
        if not _render_pause(ws, verdict, pace, when=verdict.when,
                             header=f"paused: {verdict}", header_err=True,
                             stalled=slept, note=note):
            return False, reading
        # Re-read and re-decide rather than proceeding on the nap alone: the
        # meter is account-wide, so another session may have spent the window
        # we just waited for, and the reset itself may have moved.
        slept = True
```

- [ ] **Step 4: Route `_execute` through it**

Replace `_execute`'s `slept = False` / `while True:` pre-flight block with:

```python
    state = pacing_state.read_state(config.root)
    proceed, reading = _preflight_gate(ws, config, pace, state,
                                       note="nothing has run yet; resume when the "
                                            "window resets")
    if not proceed:
        return
```

Keep everything after it — the `_meter_applies` print block reads `reading` and `state` exactly as before.

- [ ] **Step 5: Gate `_get_query` too**

In `_get_query`, after the `request.json` write from Task 4 and before `_interpret_and_stamp`:

```python
    if pace is None:
        pace = pace_options(config)
    # BEFORE interpret, not after: interpret is this run's first LLM call, and
    # until now it was the one call spent with no proactive check at all.
    # `_execute` keeps its own gate -- it has four other entry points.
    proceed, _ = _preflight_gate(ws, config, pace,
                                 pacing_state.read_state(config.root),
                                 note="nothing has run yet; resume when the "
                                      "window resets")
    if not proceed:
        return
```

- [ ] **Step 6: Run the test, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py::test_the_preflight_gate_runs_before_interpret_is_paid_for -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1882 passed, 7 deselected.

The existing pre-flight tests in `test_pace_loop.py` (`test_preflight_gate_pauses_before_any_stage_runs`, `test_preflight_re_reads_the_meter_after_the_nap`, `test_preflight_sleeps_through_the_reset_and_then_proceeds`) drive `_execute` and must stay green **unchanged**. If one goes red, the extraction changed behaviour and the fix is the extraction, not the test.

- [ ] **Step 7: Mutation check**

Prediction, written first: replacing `stalled=slept` with `stalled=False` in `_preflight_gate` makes **`test_preflight_sleeps_at_most_once`** hang, because a `when` in the past makes `sleep_until` return without sleeping.

**CORRECTION (2026-09-06) — this step originally named `test_preflight_re_reads_the_meter_after_the_nap`, and that is WRONG in a way that would retire a live guard.** That test PASSES under the mutant (exit 0): its meter recovers on the second read, so there is never a second pause for the guard to prevent. Confirmed three times independently. **Do not narrow the `-k` below to the single test named in prose** — `-k preflight` is what makes this check work at all. Run it with a hard timeout:

```bash
timeout 60 ./.venv/bin/python -m pytest packages/llama/tests/test_pace_loop.py -k preflight -q; echo "exit=$?"
```

Expected with the mutant: `exit=124` (timeout). Restore, re-run, expect a normal pass. Record the exit code in the ledger — this is the one constraint in this plan that no assertion can see.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_sessions.py
git commit -m "feat(pacing): gate before interpret, not just before the opening burst (T6b)"
```

---

### Task 7: Catch a usage limit during interpret

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — `_get_query`
- Test: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes: `_interpret_and_stamp` (Task 5), `_render_pause`, `RateLimited`.
- Consumes from Task 6: the module-level `PF_NOW` constant in `test_sessions.py`.
- Consumes: `LimitedProvider`, which already exists in `test_sessions.py` (it is what the phase 1 pause tests use). Do not define a second copy.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_limit_during_interpret_parks_a_resumable_session(
        tmp_path: Path, monkeypatch):
    """Before T6b this exited 1 with nothing written. It is the first LLM
    call of the run, so an unattended run could spend its whole night here."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))
    providers = fake_providers(None)
    # 30h out, past the 6h default cap, so it checkpoints rather than sleeps
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "interp"])

    assert result.exit_code == 0, result.output          # parked, not failed
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.failures == []                           # not a show failure
    assert info.query == "GD 1973"                       # readable on run list
    assert "run resume interp" in result.output


def test_a_limit_during_interpret_within_max_wait_sleeps_and_finishes(
        tmp_path: Path, monkeypatch):
    clock = {"now": PF_NOW}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    real = providers["interpret"]
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=2),
                                             times=1, then=real)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "slept"])

    assert result.exit_code == 0, result.output
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
    # The state above holds just as well if interpret were skipped entirely.
    # This is what pins that it was refused once and then actually retried.
    assert providers["interpret"].calls >= 2
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "during_interpret" -q`
Expected: FAIL — the `RateLimited` escapes as an unhandled error and the exit code is 1.

- [ ] **Step 3: Wrap the call**

In `_get_query`, replace the `_interpret_and_stamp` call from Task 5 with:

```python
    req = {"query": query, "limit": limit, "artist_cap": artist_cap,
           "min_score": min_score, "year_cap": year_cap}
    stalled = False
    while True:
        try:
            criteria = _interpret_and_stamp(config, ws, req)
            break
        except RateLimited as limited:
            # The fourth pause site, through the same renderer as the other
            # three: same timing arithmetic, same sleep-or-checkpoint rule,
            # same KeyboardInterrupt contract. `stalled` after the first pass
            # for the reason `_preflight_gate` documents -- nothing can change
            # between naps here, so a second sleep would be a hot spin.
            if not _render_pause(ws, limited, pace,
                                 header=f"paused: {limited}", header_err=True,
                                 stalled=stalled,
                                 note="interpret did not complete; resume when "
                                      "the window resets"):
                return
            stalled = True
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -k "during_interpret" -q` → PASS
Run: `./.venv/bin/python -m pytest -q` → 1884 passed, 7 deselected.

- [ ] **Step 5: End-to-end check of the whole T6b story**

Confirm by hand that the parked run from `test_a_limit_during_interpret_parks_a_resumable_session` is actually resumable — this is the property the four tasks exist for, and no single task's tests assert it end to end:

```python
# add to the parks_a_resumable_session test, after the assertions above
providers["interpret"] = fake_providers(None)["interpret"]        # window reset
resumed = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "interp"])
assert resumed.exit_code == 0, resumed.output
assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
```

- [ ] **Step 6: Update the docs**

`CLAUDE.md`'s pacing paragraph currently says boundary (b) covers "three stages, not four" and names the `run_interpret` gap as T6b, deliberately unbuilt. That is now false. Rewrite it to say what ships — the gate runs before interpret, a limit there parks a resumable session, and `run resume` re-interprets — and keep the two boundaries that remain true: (a) `claude_cli`-specific, openrouter untouched; and the `profile_add` call site, which still exits 1 because it has no session to park.

Do **not** delete boundary (a) as collateral. It is still true and it was fixed once already for exactly this reason.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_sessions.py CLAUDE.md
git commit -m "feat(pacing): a usage limit during interpret parks a resumable run (T6b)"
```

---

## Final verification

The per-task counts above are expected deltas from the 1871 baseline, not
decorations: a task that lands its tests and reports a lower total than
predicted has lost an existing test, which is a finding, not a rounding
error. Report it rather than adjusting the number.

- [ ] `./.venv/bin/python -m pytest -q` → 1884 passed, 7 deselected, exit 0
- [ ] `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree
- [ ] Every mutation check in Tasks 1, 2, 3, 5 and 6 ran, with its predicted red test named first and observed
- [ ] `git log --oneline` shows one commit per task, tree clean
- [ ] The spec's "Closed as won't-build" ruling on `Progress`'s two counters is reflected in the phase 2 spec's marker (say *closed*, not *pending*)
