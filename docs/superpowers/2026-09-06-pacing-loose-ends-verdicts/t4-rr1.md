# Task 4 — scoped re-review, fix round 1 (commit a15ff4a)

Reviewer: Opus. Scope: the three open findings + new breakage introduced by the
fix diff only.

## Verdicts

- **QF-1: ADDRESSED**
- **QF-2: ADDRESSED**
- **QF-3: ADDRESSED**

No new Critical or Important breakage in the fix diff.

## Method — mutation ran in a COPY, not the worktree

The implementer mutated in place in the worktree (committed first, then
`git checkout --`). I did not take that on trust and re-derived every mutant
independently in an isolated copy.

- Copy: `/private/tmp/.../scratchpad/rr1copy` (`tar` of the worktree, `.venv`
  and `.git` excluded).
- Shadowing: `PYTHONPATH=<copy>/packages/{llama,herder,emcee}/src`, driven by
  `<worktree>/.venv/bin/python -m pytest` (never a `.venv/bin/*` console
  script, which would have acted on the original).
- Proof of shadowing, both plain and **under pytest**: `import llama` resolved
  to `<copy>/packages/llama/src/llama/__init__.py`, and a planted
  `_RR1_SENTINEL` in the copy's `cli.py` was visible to a pytest-collected
  test importing `llama.cli` (`PATH:` printed the copy's path). Sentinel then
  removed and the copy byte-restored from the worktree.
- Copy baseline: **1880 passed, 7 deselected** — matches the worktree.
- Worktree, official command
  (`cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`):
  **1880 passed, 7 deselected**. Expected count met. `git status` clean at
  `a15ff4a`; the implementer's in-place mutation was fully reverted.

## QF-1 — write-before-interpret ordering

**Mutant re-derived independently.** Prediction stated before applying: moving
the `write_artifact(ws.request, ...)` block below
`criteria = run_interpret(...)` in `_get_query` fails **exactly**
`test_request_is_written_even_when_interpret_fails` with `FileNotFoundError`
on `runs/req2/request.json`, and nothing else.

Observed: `1 failed, 1879 passed, 7 deselected`; the single failure was that
test, with that exception on that path. **Predicted test, predicted mode,
predicted blast radius — CAUGHT.** This is not an "any failure = caught"
score.

The reviewer's second variant (write moved below `_execute(...)`) is caught by
the same test transitively: the monkeypatched `run_interpret` raises, so no
statement after it executes at all.

**Exception type is genuine.** `RateLimited` is raisable by `run_interpret`'s
real chain — `stages/interpret.py:run_interpret` → `herder.tasks.run_json_task`
→ `_with_transport_retry`, whose `except (TaskFailed, ResearchNotSupported,
RateLimited): raise` (tasks.py:40) re-raises it on the first raise with no
retry. Constructor signature matches: `RateLimited(message, scope=None,
resets_at=None)` (limits.py:114). `_get_query` deliberately does not wrap the
call, and `get` has no try/except around `_get_query`, so it propagates
uncaught.

**`result.exit_code != 0` is not accidentally satisfied.** I probed the test in
the copy with an added `assert isinstance(result.exception, RateLimited)`:
it passed, printing `RR1-EXC: RateLimited RateLimited("You've hit your session
limit")`. So the monkeypatch genuinely fires, the non-zero exit is caused by
the intended exception, and the run does not reach `_execute`. (Probe reverted;
this is an observation, not a requested change — the existing assertion is
adequate because the subsequent `json.loads(...read_text())` would itself raise
`FileNotFoundError` if the command had died before the write.)

## QF-2 — `llama status --by-run` fallback

The `elif ws.request.exists()` fallback is mirrored into `_by_run_rollup`
(`cli.py`) exactly as ruled, with no refactor through `iter_sessions`/
`SessionInfo`. Per the ruling, the surviving duplicated lookup is **not**
verdicted here.

**Fallback is genuinely reached by `llama status --by-run`, and the new test is
genuinely red without it.** Prediction stated before applying: deleting the
`elif` branch fails exactly
`test_status_by_run_shows_the_query_of_a_run_with_no_criteria` with an
AssertionError.

Observed: `1 failed, 1879 passed, 7 deselected`; the failure was that test, at
that assertion. The mutant's failure output is decisive on the one way this
test could have been vacuous — the query could have leaked into
`result.output` from the "sessions needing attention" block above the rollup
(that block renders via `iter_sessions`, which already had the fallback). It
does not:

```
assert 'GD 1977 Cornell' in 'sessions needing attention:\n  parked3   paused   llama run resume parked3\nparked3   no shows   \n'
```

The attention block prints no query for this session, so the assertion is
measuring `_by_run_rollup` and nothing else.

**Behaviour-identity check on the refactored condition.** The diff swaps
`(d / "criteria.json").exists()` for `ws.criteria.exists()`.
`workspace.py:119` defines `self.criteria = self.dir / "criteria.json"`, so
these are the same path — no silent behaviour change on the criteria branch.

## QF-3 — the docstring's claim is now actually delivered

The implementer's honest report (assertion passed on first run, because
`_print_sessions` → `_session_criteria_str(s)` reads `s.query` off the same
`SessionInfo` the `iter_sessions` fallback populates) is **true**, and the
assertion is **not** one that cannot fail.

Prediction stated before applying: mutating `_session_criteria_str` to stop
reading `s.query` (`return f'"{s.query:.40s}"'` → `return '""'`) fails
`test_run_list_json_survives_a_session_with_no_criteria` **at the new table
assertion**, with the `--json` assertion above it still passing.

Observed exactly that:

```
        assert json.loads(result.output)[0]["query"] == "GD 1977 Cornell"
        assert table_result.exit_code == 0, table_result.output
>       assert "GD 1977 Cornell" in table_result.output
E       assert 'GD 1977 Cornell' in 'SESSION ... CRITERIA\nparked2  paused  0s  ""   resumes ...'
```

Full suite under that mutant: `3 failed, 1877 passed` — the target test plus
two pre-existing `test_run_namespace.py` human-table tests, which is the
correct blast radius for a renderer mutant and confirms the mutant really
disabled the human path.

So `_print_sessions` **is** now invoked with a criteria-less paused session,
the docstring's "both paths"/"either renderer" is delivered by an assertion
rather than by softened words, and the claim is verified rather than asserted.

## New breakage introduced by the fix diff

**None at Critical or Important.** Specifically checked:

- `json` is imported at `cli.py:1`; `RateLimited` is already imported in
  `test_sessions.py:20`. No missing imports.
- `ws.criteria` is path-identical to the old `d / "criteria.json"` (above).
- Suite count is exactly the predicted 1880 (+2 test functions, QF-3 extended
  an existing one). No test was disabled, renamed away, or made
  unconditionally green.
- The new tests are hermetic (`tmp_path`, `monkeypatch`); no ordering or
  shared-state coupling.
- `_session_criteria_str` truncates to 40 chars; the QF-3 fixture query is 15
  chars, so the assertion is not silently truncation-dependent.

## Out of scope — recorded and deferred, not part of this loop

1. `_by_run_rollup` still duplicates the criteria/request lookup rather than
   routing through `iter_sessions`. **Explicitly ruled deferred** for the final
   whole-branch review; noted here only so it is not lost.
2. `json.loads(ws.request.read_text()).get("query")` now has **two** call sites
   (`sessions.py:127` and the new one in `cli.py`) with no error handling: a
   truncated or non-dict `request.json` raises `JSONDecodeError`/`AttributeError`
   out of the read-only `llama run list` and `llama status --by-run` views.
   Ruled deferred as low-risk; flagging only that whoever eventually hardens it
   now has two sites, not one.
3. Stale comments at `cli.py:679-682` and `sessions.py:98` — deferred, Tasks 6/7
   rewrite that region.
4. `write_artifact` already serializes dicts, so `_get_query`'s explicit
   `json.dumps(..., indent=2)` is redundant — deferred.
5. Positional `iter_sessions(tmp_path)[0]` against the file's id-keyed
   convention — deferred.
6. Pre-existing and untouched by this diff: `run_name = name or
   claim_run_dir(...)`, so `--name` bypasses `claim_run_dir` entirely. Both
   `request.json` tests pass `--name`, so the spec phrase "immediately after
   `claim_run_dir`" is not directly exercised. Structurally harmless — the
   write sits after `ws = RunWorkspace(config.root, run_name)` on both paths —
   but Tasks 5-7 should know the claimed-name path is the one under test.

## Process note

The implementer mutated in the worktree rather than in a copy. It was
committed first and cleanly reverted (`git status` clean, suite back to 1880),
so no measurement was corrupted this time. Independently re-derived here in a
copy regardless; future rounds should mutate in a copy so a concurrent agent in
the worktree cannot be affected.
