# Scoped re-review: task-3-4-4b fix round (682240d..59ddbb4)

Read-only. Diff: `review-682240d..59ddbb4.diff`. No edits, no commits made.

## Findings verdicts

- **Important-1 (two unpinned capture branches, M6/M7)** — ADDRESSED.
  `packages/herder/tests/test_claude_cli.py:262-278` (`is_error` branch, M6) and
  `packages/herder/tests/test_claude_cli.py:280-291` (not-JSON branch, M7).
  Production `capture_failure` calls in `claude_cli.py` at the `is_error` branch
  (line ~148) and the `json.JSONDecodeError` branch (line ~140) were already
  present pre-fix (Task 3); this round is test-only and closes exactly the gap
  the mutation testing found.
- **Minor-3 (missing-`result` branch had no capture)** — ADDRESSED.
  `packages/herder/src/herder/claude_cli.py:154` adds `capture_failure(cmd, proc)`
  immediately before the `raise HerderError("claude output has no string
  'result' field")` on line 155; pinned by
  `packages/herder/tests/test_claude_cli.py:293-304`
  (`test_a_failure_is_captured_when_result_field_is_missing`).
- **Minor-2 (undocumented deliberate omission of `classify()`)** — ADDRESSED.
  `packages/herder/src/herder/claude_cli.py:138-142` adds a comment clause on
  the `json.JSONDecodeError` branch explaining the omission (only reachable at
  `returncode == 0`; the measured usage-limit signature always exits 1). No
  `classify()` call was added — confirmed by reading the diff hunk; the branch
  body is unchanged apart from the comment.
- **Minor-1 (falsehood in `gather.py` comment)** — ADDRESSED, comment-only.
  `packages/llama/src/llama/stages/gather.py:996-1004`. Reworded to state
  intent ("Re-raise so a future `_execute` can pause the run on it instead of
  degrading") and explicitly notes the pause handler doesn't exist yet, that
  today it lands in `cli.py`'s per-show `except (TaskFailed, HerderError,
  IAError)` and is recorded as a per-show failure. Verified against
  `packages/llama/src/llama/cli.py:237`, which does catch that tuple, and
  `RateLimited` (`packages/herder/src/herder/limits.py:53`) is a subclass of
  `HerderError`, so the claim is factually accurate. The `raise` statement
  itself and surrounding code are byte-identical apart from the comment —
  confirmed no behavioural change in the diff hunk (only comment lines carry
  `+`/`-`).

## My own kill verdict per test (independent reasoning, not just trusting the report)

1. **`test_a_failure_is_captured_on_the_is_error_envelope`** (M6). Envelope
   `{"is_error": True, "result": "boom", "api_error_status": "internal_error"}`,
   `FakeProc(returncode=0, stdout=json.dumps(envelope))`. Trace: returncode==0
   skips the first branch; `json.loads` succeeds; `data.get("is_error")` is
   `True` → enters the `is_error` branch → `capture_failure(cmd, proc)` →
   `classify(message)` returns `None` (message is "claude reported an error:
   boom", matches no `_SIGNATURES` pattern) → raises `HerderError`. Test
   asserts `len(written) == 1` and `"api_error_status" in written[0].read_text()`
   — that field only appears in the file because `capture_failure` writes the
   full raw `proc.stdout`, which contains the whole envelope JSON. **Deleting
   the `capture_failure` call in this branch makes `written` empty → `len(written)
   == 1` fails → RED.** Kills M6. Confirmed genuine.

2. **`test_a_failure_is_captured_on_not_json_stdout`** (M7).
   `FakeProc(returncode=0, stdout="not json")`. Trace: returncode==0 skips
   first branch; `json.loads("not json")` raises `JSONDecodeError` → enters
   the except branch → `capture_failure(cmd, proc)` → raises `HerderError`.
   Test asserts `len(written) == 1` and `"not json" in written[0].read_text()`
   (present because `capture_failure` writes raw stdout verbatim). **Deleting
   the call here likewise empties `written` → RED.** Kills M7. Confirmed
   genuine.

3. **`test_a_failure_is_captured_when_result_field_is_missing`** (Minor-3).
   `FakeProc(returncode=0, stdout=json.dumps({"not_result": "x"}))`. Trace:
   returncode==0; JSON parses fine; `data.get("is_error")` is falsy (key
   absent) → skips that branch; `result = data.get("result")` is `None`, fails
   `isinstance(result, str)` → enters the new branch → `capture_failure(cmd,
   proc)` → raises `HerderError`. Test asserts `len(written) == 1` and
   `"not_result" in written[0].read_text()`. **Deleting the newly-added
   `capture_failure` call empties `written` → RED.** Kills the mutation.
   Confirmed genuine.

All three tests assert on the capture directory's *contents* (file count plus
a distinguishing substring pulled from the raw envelope/stdout), not merely
that the exception was raised — this is exactly the shape M6/M7 needed and
Important-1 required. Each test's `FakeProc` construction genuinely reaches
the branch it names, and the three target three different branches (no
overlap). The implementer's claimed RED/GREEN mutation cycle is internally
consistent with a straight reading of the diff: each capture call sits in a
distinct `if`/`except` block, so deleting one and only one leaves the other
two branches' captures intact and only the matching test would flip red
(single-mutation, single-test correspondence holds).

## Placement check (missing-`result` branch)

`capture_failure(cmd, proc)` is inserted as the first statement inside the
`if not isinstance(result, str):` block, directly before the `raise
HerderError(...)` on the next line — it executes before the raise, and
`capture_failure` never itself raises (catches `Exception` internally per
`failures.py`), so the raise still fires unconditionally afterward. No
control-flow change.

## New breakage in the fix diff — none found

- No capture call was moved to a position that could swallow or alter control
  flow; the only new call is a straight addition before an existing raise.
- No global state leak: `failures.set_capture_dir(tmp_path)` / `finally:
  failures.set_capture_dir(None)` in each new test mirrors the existing
  pattern (`test_a_failure_is_captured_when_a_capture_dir_is_set`);
  `monkeypatch.setattr(subprocess, "run", ...)` auto-reverts per pytest
  fixture scope. No new fixtures or session-scoped patches introduced.
- Scope check: `git diff --stat` in the diff header confirms exactly three
  files touched — `packages/herder/src/herder/claude_cli.py`,
  `packages/herder/tests/test_claude_cli.py`, and
  `packages/llama/src/llama/stages/gather.py` (comment-only) — matching the
  contract. No other files appear in the diff.
- Reported suite delta (1681 → 1684, +3, 7 deselected unchanged) matches the
  diff's content exactly: three new test functions added, none removed or
  modified elsewhere, no production logic that would change existing test
  counts (the `gather.py` change is comment-only, the two production
  `claude_cli.py` capture calls in the `is_error`/not-JSON branches are
  unchanged, and the one new production capture call is unconditionally
  followed by the same raise as before, so no existing test's control flow
  through that branch changes).

## Deferred (out of scope, does not affect verdict)

Nothing new to add beyond what the task explicitly ruled out of scope
(`TimeoutExpired` capture, the `_fail` helper refactor, `gather.py`'s
`RateLimited` import source, the `test_stage_gather.py` indent nit,
`openrouter.py`'s plain-`HerderError` 429). No other out-of-scope
observations surfaced while reading this diff.

## Overall verdict

**APPROVED.** All four findings (Important-1, Minor-1, Minor-2, Minor-3) are
ADDRESSED, each pinning test genuinely kills the mutation/gap it targets by
asserting on capture-directory contents rather than just the raised
exception, the new capture call is correctly positioned, and no new breakage
was introduced within the scoped diff.
