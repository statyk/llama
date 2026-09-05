# Task 3 / 4 / 4b report — usage-pacing phase 1

Branch `usage-pacing`, worked directly in `/Users/shawn/projects/llama` (no worktree, no venv creation, per instructions). Three commits, one per task, each preceded by a full green suite run.

Final commits:
- Task 3: `e4c0786` — feat(herder): raise RateLimited and capture raw output on backend failure
- Task 4: `cb0b5ff` — fix(herder): stop retrying a usage-limit refusal as transport noise
- Task 4b: `682240d` — fix(gather): let a usage-limit refusal propagate instead of flagging the show

---

## Task 3: raise RateLimited from the claude_cli provider

**Files touched:** `packages/herder/src/herder/claude_cli.py`, `packages/herder/tests/test_claude_cli.py`

Followed the brief exactly. Appended the four brief tests verbatim to `test_claude_cli.py`:
- `test_session_limit_on_nonzero_exit_raises_rate_limited`
- `test_session_limit_in_an_error_envelope_raises_rate_limited`
- `test_dropped_connection_stays_a_plain_herder_error`
- `test_a_failure_is_captured_when_a_capture_dir_is_set`

**Step 2 (red):**
```
./.venv/bin/python -m pytest packages/herder/tests/test_claude_cli.py -q
```
Result: `3 failed, 14 passed` — the two RateLimited tests failed because a bare `HerderError` was raised instead, and the capture test found an empty directory (`assert 0 == 1`). Matches the brief's expected failure exactly.

**Step 3 (implementation):** Added `from herder.failures import capture_failure` and `from herder.limits import classify` to the imports, then replaced `_run`'s `if proc.returncode != 0:` through the `is_error` branch with the brief's literal code — computing the message first, calling `capture_failure(cmd, proc)`, then `classify(message)` and raising the `RateLimited` if non-None, else the plain `HerderError`. Same pattern added to the JSON-decode-failure branch (capture only, no classify needed there — brief's snippet already covers this).

**Step 4 (green):**
```
./.venv/bin/python -m pytest packages/herder/tests/test_claude_cli.py -q
```
Result: `17 passed`.

**Full suite before commit:**
```
./.venv/bin/python -m pytest -q
```
Result: `1678 passed, 7 deselected` (1674 baseline + 4 new tests).

No deviations from the brief. `limits.py`'s zone regex being widened during Task 2 review (noted in the assignment) did not affect anything here — `classify`/`RateLimited` are consumed as-is.

---

## Task 4: stop `_with_transport_retry` retrying a rate limit as transport noise

**Files touched:** `packages/herder/src/herder/tasks.py`, `packages/herder/tests/test_llm_tasks.py`

Followed the brief exactly. Confirmed the test file already has `from herder import FakeProvider, HerderError, ResearchNotSupported, TaskFailed, tasks` and an `Answer(BaseModel)` schema with a `value: int` field (brief said to reuse these — did so, only added the `RateLimited` import inline before the new test block). Appended `CountingLimitProvider`, `test_rate_limit_is_not_retried_as_transport_noise`, and `test_rate_limit_propagates_from_a_research_task` verbatim.

**Step 2 (red):**
```
./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q -k rate_limit
```
Result: `2 failed, 20 deselected` — `assert 3 == 1` in both new tests (the retry loop called the provider 3 times before giving up), matching the brief's expected failure exactly.

**Step 3 (implementation):** Added `from herder.limits import RateLimited` to imports, changed `except (TaskFailed, ResearchNotSupported):` to `except (TaskFailed, ResearchNotSupported, RateLimited):` on line 36-ish of `_with_transport_retry`, and extended the docstring with the brief's exact final paragraph explaining why RateLimited joins the other two.

**Step 4 (green):**
```
./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q
```
Result: `22 passed`.

**Full suite before commit:**
```
./.venv/bin/python -m pytest -q
```
Result: `1680 passed, 7 deselected`.

No circular-import issue: `herder/limits.py` imports `HerderError` directly from `herder.provider` (not via `herder/__init__.py`), so `tasks.py` importing from `herder.limits` is safe — verified by the suite passing including all `herder` package imports.

No deviations from the brief.

---

## Task 4b: stop `gather` swallowing a rate limit as an alignment failure

**Files touched:** `packages/llama/src/llama/stages/gather.py`, `packages/llama/tests/test_stage_gather.py`

### Deviation from the brief: filename

The brief and the task assignment both name `packages/llama/tests/test_gather.py`. **That file does not exist in the tree.** The actual test file exercising `run_gather` is `packages/llama/tests/test_stage_gather.py` (confirmed via `find`/`grep` — it's the only file importing `run_gather` from `llama.stages.gather`, 2021 lines, ~90 tests). I put the new test there. Flagging this per the report-contract instructions; it's a naming mismatch in the brief/assignment, not a scope violation — `test_stage_gather.py` is not in the explicit six-file scope list either, so worth double-checking against the plan doc if that matters downstream, but there was no other candidate file and the assignment's own text says "read `test_gather.py`... reuse whatever fixture that file already has" — I take that instruction's intent (reuse the file that already drives `run_gather`) as satisfied by using the real file.

### Finding the fallback branch

Read `gather.py` around line 992 (the target). The `align_structure` LLM fallback fires only when: no usable jerrybase anchoring evidence, `canonical.items` non-empty, `result.coverage < structure_cfg.align_coverage_threshold` (default 0.8), and `align_provider is not None`.

Found an existing test that already reaches exactly this branch: `test_gather_llm_alignment_garbage_falls_back_and_flags` (line ~268 pre-edit). It wrecks the tag titles on the `gd73_metadata.json` fixture (renaming every VBR MP3 file's tag to `Track N`) so deterministic alignment can't match them and coverage drops below threshold, then feeds `align_provider` a `FakeProvider` that returns garbage JSON three times (exhausting `run_json_task`'s retries), landing in the `except (TaskFailed, HerderError)` branch today.

I reused this exact setup (fixture, candidate, identifier) but swapped the garbage payload for a queued `RateLimited` exception — `FakeProvider.complete()` raises a queued `BaseException` instead of returning it (confirmed by reading `herder/fake.py`), and per Task 4's fix, `run_json_task`'s inner `_with_transport_retry` no longer retries `RateLimited`, so it propagates straight out of `run_json_task` on the first call — landing in `gather.py`'s `except (TaskFailed, HerderError)` (pre-fix) or the new `except RateLimited: raise` (post-fix).

New test: `test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag`, added `from herder.limits import RateLimited` to imports.

```python
def test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    for i, f in enumerate(f for f in md["files"] if f.get("format") == "VBR MP3"):
        f["title"] = f"Track {i + 1}"
    align_fake = FakeProvider(
        completes=[RateLimited("You've hit your session limit", scope="five_hour")])
    sws = ShowWorkspace(tmp_path / "show")
    with pytest.raises(RateLimited):
        run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                  align_provider=align_fake)
    assert align_fake.calls, "align_structure LLM was not invoked"
    assert not sws.show.exists(), "show.json must not be written on a rate-limit abort"
```

Both halves are asserted: `pytest.raises(RateLimited)` for propagation, and `not sws.show.exists()` for the "no wrong flag persisted" half — `run_gather` only calls `write_artifact(show_ws.show, show)` at line ~1130, well after this fallback block (~992), so an exception here means `show.json` is never written at all. That's a stronger and more direct check than grepping flags out of a returned object that never gets constructed, since the defect's actual harm is a **file on disk** surviving `should_run`'s stage-skip on resume.

**Step 2 (red):**
```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k rate_limit
```
Result: `1 failed, 91 deselected` — `Failed: DID NOT RAISE RateLimited`, captured log shows `WARNING llama:gather.py:993 align_structure failed: You've hit your session limit`, confirming the exception was swallowed by the broad clause exactly as the brief predicted.

**Step 3 (implementation):** Added `from herder.limits import RateLimited` to `gather.py`'s imports, and inserted the brief's literal `except RateLimited: raise` clause (with its comment) above the existing `except (TaskFailed, HerderError) as err:` clause — did not narrow the broad clause, per the brief's explicit instruction.

**Step 4 (green, file-scoped):**
```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q
```
Result: `92 passed`.

**Step 5 (full suite):**
```
./.venv/bin/python -m pytest -q
```
Result: `1681 passed, 7 deselected`.

### Mutation evidence (red/green proof the test is load-bearing)

1. Backed up `gather.py` to scratchpad.
2. Removed the `except RateLimited: raise` clause (restoring the old two-clause form).
3. Cleared `__pycache__` across the tree.
4. Ran `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k rate_limit` → **RED**: `Failed: DID NOT RAISE RateLimited`, log again shows the swallow-and-warn path firing (`WARNING llama:gather.py:994 align_structure failed: ...`).
5. Restored `gather.py` from the backup (`diff` confirmed byte-identical to the post-implementation state).
6. Cleared `__pycache__` again.
7. Ran `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q` → **GREEN**: `92 passed`.

The test is confirmed load-bearing: it fails without the fix and passes with it.

---

## Summary / concerns

- All three tasks landed exactly as specified in their briefs, with the one filename discrepancy noted above for Task 4b (brief says `test_gather.py`, actual file is `test_stage_gather.py` — no such file as `test_gather.py` exists anywhere in the tree, verified by `find`).
- No production code calls `set_capture_dir` — confirmed by inspection, only `claude_cli.py` calls `capture_failure` (read-only from the module's perspective).
- No circular imports: `herder.limits` imports `HerderError` directly from `herder.provider`, never via `herder/__init__.py`, so both `claude_cli.py` and `tasks.py` importing from `herder.limits` is safe.
- `herder` still does not import from `llama`/`emcee` (unaffected by these changes — Task 4b's `RateLimited` import is llama-side, the correct direction).
- Full suite green at every commit: 1678 → 1680 → 1681 passed, 7 deselected throughout (baseline was 1674 passed / 7 deselected before this work; net +7 new tests across the three tasks: 4 in Task 3, 2 in Task 4, 1 in Task 4b).
- No subagents were dispatched, per instructions.
- No takeover sentinel was ever present at any of the three check-in points.

---

# Fix round 1 report (Important-1, Minor-1, Minor-2, Minor-3)

Requested by `sdd-orchestrator` after the code-quality verdict (Approved, with one
Important test-gap finding and several Minor findings). Fixed exactly the four
findings named: Important-1, Minor-1, Minor-2, Minor-3. Minor-4 (TimeoutExpired
capture), Minor-5 (the `_fail` helper refactor), Minor-6 (import-source
consistency) and Minor-7 (indent nit) were explicitly deferred by the orchestrator
and left untouched.

Commit: `59ddbb4` — fix(herder): pin the two surviving capture mutations, close the last gap

## Important-1 — pin the two surviving capture mutations

Mutations M6 (`is_error` branch, `capture_failure` removed) and M7 (not-JSON
branch, `capture_failure` removed) both survived the reviewer's mutation pass —
the production code already called `capture_failure` on both branches (from Task
3), but no test asserted it. Test-only fix: added
`test_a_failure_is_captured_on_the_is_error_envelope` and
`test_a_failure_is_captured_on_not_json_stdout` to `test_claude_cli.py`, both
shaped after `test_a_failure_is_captured_when_a_capture_dir_is_set` per the
reviewer's suggestion, reusing the envelope `FakeProc` pattern
`test_session_limit_in_an_error_envelope_raises_rate_limited` already builds.

No production code change was needed for Important-1 itself — `capture_failure`
was already being called on both branches; the gap was purely in test coverage.

## Minor-3 — the "no string 'result' field" branch had no capture at all

This was the one raise site in `_run` that never called `capture_failure` at all,
not even before this round. Added the call:

```python
result = data.get("result")
if not isinstance(result, str):
    capture_failure(cmd, proc)
    raise HerderError("claude output has no string 'result' field")
```

and a pinning test, `test_a_failure_is_captured_when_result_field_is_missing`,
using an envelope with no `result` key at all (`{"not_result": "x"}`) so
`data.get("result")` is `None` and fails the `isinstance(..., str)` check.

## Minor-2 — document why the not-JSON branch skips classify()

Added a comment clause to the `json.JSONDecodeError` branch explaining the
omission is deliberate: that branch is only reachable at `returncode == 0`,
and the measured usage-limit signature (`limits.py`'s docstring) always exits
1 — a non-zero exit with non-JSON stdout already classifies via
`_error_detail`'s `stderr or stdout` fallback in the returncode branch above.
No `classify()` call added, per the orchestrator's instruction.

## Minor-1 — reword the gather.py forward-reference comment

The old comment ("Let it reach `_execute`, which pauses instead") stated the
pause as current fact; today it still lands in `cli.py`'s per-show
`except (TaskFailed, HerderError, IAError)` clause and is recorded as a per-show
failure — the pause handler is a later task. Reworded to state intent (why the
re-raise exists) and explicitly note the pause handler doesn't exist yet and
what happens today instead:

```python
except RateLimited:
    # A usage window ran out. Degrading to a review flag here
    # would write a `low-confidence structure alignment` the
    # recording did not earn, and `should_run` means the
    # resume never recomputes it - so the wrong flag would be
    # permanent. Re-raise so a future `_execute` can pause the
    # run on it instead of degrading. That pause handler does
    # not exist yet: today this still reaches `cli.py`'s
    # per-show `except (TaskFailed, HerderError, IAError)` and
    # is recorded as a per-show failure, same as any other
    # unrecovered error - a later task is what makes the
    # pause real.
    raise
```

## Test commands and output

**Step: run test_claude_cli.py after all four fixes landed:**
```
./.venv/bin/python -m pytest packages/herder/tests/test_claude_cli.py -q
```
Result: `20 passed` (17 baseline + 3 new).

**Mutation proof, per new test — clear `__pycache__` before and after every
mutation/restore, per the instrument-hazard warning:**

1. **M6 (is_error capture)** — removed `capture_failure(cmd, proc)` from the
   `is_error` branch, cleared `__pycache__`, ran
   `pytest packages/herder/tests/test_claude_cli.py -q -k is_error_envelope`
   → **RED**: `assert 0 == 1` on
   `test_a_failure_is_captured_on_the_is_error_envelope`. Restored from backup,
   `diff` confirmed byte-identical, cleared `__pycache__`, reran the same
   filter → **GREEN**: `1 passed`.

2. **M7 (not-JSON capture)** — removed `capture_failure(cmd, proc)` from the
   `json.JSONDecodeError` branch, cleared `__pycache__`, ran
   `pytest packages/herder/tests/test_claude_cli.py -q -k not_json_stdout`
   → **RED**: `assert 0 == 1` on `test_a_failure_is_captured_on_not_json_stdout`.
   Restored, `diff` confirmed identical, cleared `__pycache__`, reran →
   **GREEN**: `1 passed`.

3. **Minor-3 (result-field capture)** — removed the newly-added
   `capture_failure(cmd, proc)` from the "no string 'result' field" branch,
   cleared `__pycache__`, ran
   `pytest packages/herder/tests/test_claude_cli.py -q -k result_field_is_missing`
   → **RED**: `assert 0 == 1` on
   `test_a_failure_is_captured_when_result_field_is_missing`. Restored,
   `diff` confirmed identical, cleared `__pycache__` (final restore verified
   green at the full-file level next).

All three new tests confirmed load-bearing: RED without their guarded
`capture_failure` call, GREEN with it.

**File-scoped and full-suite green after restore:**
```
./.venv/bin/python -m pytest packages/herder/tests/test_claude_cli.py -q
```
→ `20 passed`

```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q
```
→ `92 passed` (comment-only change in `gather.py`, no behavioural change expected
or observed)

```
./.venv/bin/python -m pytest -q
```
→ `1684 passed, 7 deselected` (1681 baseline + 3 new tests)

## Scope and tree state

Touched exactly the three files in scope: `packages/herder/src/herder/claude_cli.py`,
`packages/herder/tests/test_claude_cli.py`, `packages/llama/src/llama/stages/gather.py`
(comment only). `git diff --stat` before commit showed exactly these three files,
62 insertions / 1 deletion. One commit for the round, `59ddbb4`. Did not touch
Minor-4, Minor-5, Minor-6, or Minor-7 per the orchestrator's explicit deferral.
Tree is clean after commit.
