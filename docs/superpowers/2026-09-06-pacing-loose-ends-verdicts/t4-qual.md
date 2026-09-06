# Task 4 — CODE-QUALITY review (Opus)

## Verdict: Task quality: Changes requested

The change is small, correct, minimal and green. Two findings hold it back: the
task's central invariant (the write happens BEFORE the first LLM call) is not
pinned by any test, and one of the three query renderers was missed.

## Audit performed

- `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -c "import llama; print(llama.__file__)"`
  -> `/Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py` (correct checkout).
- `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
  -> **1878 passed, 7 deselected** in 5.90s. Matches the predicted count and the
  implementer's report exactly (1875 + 3).
- `git status --porcelain` -> clean. Commit `2b42172`, message is lowercase
  `feat(scope): subject` with a body that explains *why* and cites the verified
  counts. Style compliant.
- Implementer ran no mutation (none was owed) and left no stray edits, so the
  `git checkout` hazard from the earlier task did not recur. No process note.
- I made no modification to the worktree.

## Findings

### 1. Important — the "before the first LLM call" ordering is unpinned

`test_get_persists_the_request_before_interpreting` asserts only that
`runs/req/request.json` exists with the right content *after a successful run*.
Moving the `write_artifact` call below `run_interpret(...)` — or below
`_execute(...)` — leaves all three tests and the whole 1878-test suite green,
while destroying the single property T6b rests on. The test's own name asserts an
ordering it does not check.

This matters more than usual here: the brief assigns this task no mutation step,
so the red-first evidence is the only stand-in, and the recorded red for this
test (`FileNotFoundError` on the read) is equally consistent with a write placed
anywhere in `_get_query`. By inspection the constraint is unpinned; no mutation
run was needed to establish that.

Cheap fix, and it is genuinely red-first (it fails today only in the sense that
it fails against any reordered variant, and it fails against `28fbb9e` outright):
`run_interpret` is bound in cli's namespace at `cli.py:44`, so

```python
def test_request_is_written_even_when_interpret_fails(tmp_path, monkeypatch):
    ...
    def boom(*a, **k):
        raise HerderError("usage limit")
    monkeypatch.setattr(cli, "run_interpret", boom)
    result = runner.invoke(cli.app, [..., "get", "GD 1973", "--auto", "--name", "req"])
    assert result.exit_code != 0
    assert json.loads((tmp_path / "runs" / "req" / "request.json").read_text())["query"] == "GD 1973"
```

pins it. This is also the case Tasks 6/7 will actually produce, so the test is not
throwaway. If the orchestrator prefers, Task 7's pause test may subsume it — but
then say so explicitly, because between now and Task 7 the invariant is unguarded.

### 2. Important — `llama status --by-run` still renders the query as `""`

There are three places that render a run's query, not two. The brief warned about
`_session_json` (which is a pure projection of `SessionInfo` and needed nothing —
the implementer checked this correctly). It did not mention `_by_run_rollup`
(`cli.py:2680-2686`), which duplicates the criteria lookup instead of going
through `SessionInfo`:

```python
        query = ""
        if (d / "criteria.json").exists():
            query = read_model(RunWorkspace(config.root, d.name).criteria, Criteria).query
```

So for exactly the run this task exists for — parked before interpret, no
`criteria.json` — `llama run list` now shows the real query while `llama status
--by-run` still shows an empty string. The commit message claims "a run parked
before interpret still lists with its real query instead of \"\"", which is only
true of one of the two views. Either add the same `elif ws.request.exists()`
fallback (or better, route the rollup's query through `iter_sessions`, removing
the duplication), or record the gap deliberately.

### 3. Minor — the pre-existing comment four lines below now states a falsehood

`cli.py:679-682` still reads "a checkpoint here would be unresumable -- the query
lives only in argv", immediately after the new comment saying the query no longer
lives only in argv. The commit created that contradiction. Task 7 will rewrite
this region, so deferring is defensible, but it should not survive the series.
Same class: `sessions.py:98`'s field comment `query: str  # criteria.query, ""
when no criteria.json` is now stale (it can come from `request.json`).

### 4. Minor — redundant serialization, and an avoidable module-level import

`write_artifact` already serializes a non-str payload as `json.dumps(_to_jsonable(data), indent=2)`
(`workspace.py:41-44`; a plain dict of primitives passes through `_to_jsonable`
untouched). So `write_artifact(ws.request, {...})` is byte-identical to the
`json.dumps({...}, indent=2)` the brief prescribed, and the new module-level
`import json` in `cli.py` is unnecessary — it now coexists with five function-local
`import json as _json` statements, which is a readability wart even though it is
not a shadowing bug. Similarly `sessions.py` could use `workspace.read_json`
rather than a raw `json.loads(...read_text())`.

### 5. Minor — no error handling on the new read path

`json.loads(ws.request.read_text()).get("query")` in `iter_sessions` raises
`JSONDecodeError` on a truncated or hand-edited file, and `AttributeError` if the
top-level JSON is not an object. Either escapes `iter_sessions`, which takes down
`llama run list` and `llama status` for the *entire workspace*, not just the bad
run dir. Risk is genuinely low (the file is only ever written through the atomic
unique-temp + rename path, which cannot leave a partial file) and the existing
criteria branch has the same exposure, so this is not a regression — but a
one-run-dir fault becoming a whole-command fault is worth confining, since
`iter_sessions` is a sweep over untrusted-ish on-disk state.

### 6. Minor — test hygiene nits

- `test_run_list_json_survives_a_session_with_no_criteria`'s docstring says "both
  paths are pinned" / "either renderer", but the human table renderer
  `_print_sessions` is never invoked with a criteria-less paused session by any of
  the three tests. Only `--json` is exercised. The claim over-reaches; either add
  the table assertion (it is one more `runner.invoke` without `--json`) or soften
  the docstring.
- `test_run_list_shows_the_query_of_a_run_with_no_criteria` uses
  `iter_sessions(tmp_path)[0]` — positional indexing into an unordered directory
  walk. It is safe with one run dir, but the file's own convention two tests up
  (`{s.id: s for s in iter_sessions(...)}["bare"]`) is order-independent and
  should be matched.
- Otherwise the tests are well-aimed: test 2 is genuinely the only thing producing
  a non-empty `info.query` for a criteria-less run (nothing else in `iter_sessions`
  can satisfy that assertion), so the `sessions.py` fallback *is* pinned; and the
  recorded reds are real, with the reasons the brief predicted.

### 7. Minor — interface note for Task 5

The brief declares the shape's `limit` as `int|None`. In practice `get`'s `--limit`
is `typer.Option(0, ...)` (`cli.py:726`), so the persisted value is `0`, never
`null`. Task 5 must replay it with `if limit:` (as `_get_query` itself does at
line 686), not `if limit is not None:`, or every resumed run acquires an explicit
`count=0`. Also worth noting that `name`, `full_rationale`, `--wait/--max-wait/
--no-pacing` are deliberately absent from the artifact — correctly so: the run id
*is* the name, and the rest are re-supplied as options on `run resume`.

## What is good

- The write lands after the `artist_cap == 0.0 / year_cap == 0.0` validation, so a
  rejected invocation does not create a run dir.
- `atomic_write_bytes` mkdir's the parent, so the `--name` path (which skips
  `claim_run_dir`) still gets its dir — and a `--name` run that dies in interpret
  now leaves a listable, query-carrying dir where it previously left nothing.
  That behaviour change is exactly the intent and is covered by test 2.
- Task ordering is respected: nothing pauses before interpret yet, so the
  `elif ws.request.exists()` branch cannot park an unresumable run today.
- `_session_json` was checked empirically as well as by reading, per the brief's
  warning, and correctly needed no change.
