# Task 5 — SPEC-COMPLIANCE review (Opus)

## Verdict: Spec ✅

The diff implements exactly what the brief requires, no less and no more.
`cli.py` carries the brief's `_interpret_and_stamp` verbatim (plus one
explanatory comment), `_get_query` is routed through it with the brief's
five-key dict, and `run_resume` gains **one** branch — matching the spec's
1(c) two-case description exactly (`no criteria + request` → re-interpret;
`no criteria + no request` → today's unchanged refusal). Only the two briefed
files are touched, across two well-formed commits.

## Evidence I generated myself (not taken from the report)

All of the following ran with the mandated command form
(`./.venv/bin/python -m pytest -q`), and every mutant ran in a COPY with
`PYTHONPATH` shadowing proved before use.

- **Suite, worktree, HEAD `3317b0c`:** `1884 passed, 7 deselected` — the gate.
  Interpreter check: `llama.__file__` resolves inside the worktree. Worktree
  clean; I modified nothing.
- **Step 2 red-first, independently replayed.** Copy with `cli.py` reverted to
  `5036d45` and the HEAD test file: `2 failed, 1 passed, 31 deselected`; both
  failures on `assert result.exit_code == 0` with output
  `no criteria.json in .../runs/{reinterp,flags}` and `assert 1 == 0`, and
  `..._still_refuses_a_dir_with_neither_artifact` **passed already**. This is
  exactly the Step 2 expectation, confirmed without relying on the report.
- **Copy proved live before any mutant:** sentinel (refusal string →
  `SENTINEL-COPY-RAN`) reddened `..._still_refuses_a_dir_with_neither_artifact`;
  `__pycache__`/`.pytest_cache` purged from the copy; copy diffed
  byte-identical to the worktree after restore, then deleted.
- **Mutant B (brief's mutant 1) — drop the `artist_cap is not None` clause.**
  Predicted red *by name before applying*:
  `test_run_resume_replays_the_flags_the_request_recorded`, and only it.
  Observed: `1 failed, 1883 passed, 7 deselected`, that test alone. Match.
- **Mutant C (brief's mutant 2) — delete Task 4's `write_artifact(ws.request, …)`.**
  Predicted red: `test_get_persists_the_request_before_interpreting` (+ any
  other request-artifact test); predicted **green**:
  `test_run_resume_reinterprets_a_session_that_never_got_criteria`.
  Observed: `2 failed, 1882 passed` —
  `test_get_persists_the_request_before_interpreting` and
  `test_request_is_written_even_when_interpret_fails`; the resume test is
  absent from the FAILED list. **The mandated asymmetry holds.**
- **Mutant D — `if req.get("limit"):` → `is not None`.** Predicted red:
  `test_run_resume_does_not_stamp_an_unspecified_limit` on `criteria.count == 1`.
  Observed in isolation: `assert 0 == 1` with `count=0` in the `Criteria` repr;
  full suite `22 failed, 1862 passed`. Confirms both the fourth test's pin
  **and** the implementer's self-correction (the fork was never silent — 21
  collateral `get`-path failures — but only the new test names the cause).
- **Mutant A (mine, testing the approved extra assertion).** Replaced the
  resume branch's call with the exact wrong implementation the implementer
  said the brief's three assertions could not exclude:
  `criteria = Criteria(query=…); write_artifact(ws.criteria, criteria)`.
  Predicted red: `..._reinterprets_a_session_that_never_got_criteria`, **on the
  added provider-calls assertion**. Observed exactly that:
  `> assert any(kind == "complete" and "GD 1973" in prompt` /
  `E AssertionError: []`. The brief's own three assertions all passed under
  that wrong implementation. **The implementer's finding is correct and the
  approved addition is load-bearing.**

## Findings

1. **Minor — `run resume` ignores the persisted `auto`/`plan`.** `request.json`
   carries them (Task 4's shape) but the resume path uses `run resume`'s own
   `--auto` and no `plan`. This is brief-consistent and, I judge, right:
   `run_resume` already passes `human_gate=False` unconditionally, so a run
   originally started `--interactive` was never replayed interactively anyway.
   Recording it as a deliberate choice rather than an oversight.
2. **Minor — the `nolimit` test's comment is slightly generous.** It says
   `count == 1` is "the interpret fixture's own count"; `1` is *also* the
   `Criteria` model default, so the assertion does not distinguish fixture from
   default. It does distinguish `0` from `1`, which is the whole point, and
   mutant D confirms it. No change needed; noted only so nobody later reads the
   comment as a stronger claim than it is.
3. **Minor — the two later tests keep the per-call `fake_providers(None)`
   lambda,** so their provider queues are fresh each `make_providers` call and
   could not see a *duplicated* interpret call. Test 1 (shared-dict pattern)
   does cover that, since `FakeProvider` raises on an exhausted queue. Not a
   brief gap; coverage is adequate in aggregate.
4. **Minor / for Task 7 — the implementer's side finding is real and I
   reproduced it.** Mutant B reddens *only* the new resume test: `_get_query`'s
   `--artist-cap` stamping has no direct pin of its own and is now covered only
   transitively through the shared helper. Pre-existing, not introduced here,
   but Task 7 touches this region and should not assume the `get` path is
   independently pinned.
5. **Minor — I agree with deferring the two stale comments to Task 7, with one
   caveat.** The comment above the `_interpret_and_stamp` call in `_get_query`
   now asserts the opposite of what the code does ("a checkpoint here would be
   unresumable — the query lives only in argv"), and `sessions.py:98`'s `query`
   comment is likewise stale. Deferring is right — Task 7 rewrites that block
   with `CLAUDE.md`, and splitting the rewrite would churn it twice. The caveat
   is a dependency, not a disagreement: **if Task 7 changes shape or is
   dropped, the branch ships a comment that contradicts its own code.** Worth a
   phase-level checklist line rather than trusting it to Task 7's memory.
6. **Informational — the brief's Step 6 count (1881) is stale**, superseded by
   the orchestrator's 1884 gate (1880 base + 4). Observed 1884. Not a defect.

## Interface for Task 7

`_interpret_and_stamp(config, ws, req) -> Criteria` is free of pause logic —
it contains no `RateLimited` handling, no `_render_pause`, no sleep, and no
meter read. `run_interpret` is its only LLM call, on the first line, so
wrapping the **call** to it in Task 7's retry loop is clean. Confirmed by
reading the shipped body.

## Nothing I could not verify

No `⚠️ Cannot verify from diff` items. Task 4's `RunWorkspace.request`
(`workspace.py:120`) sits outside this diff; I read it in the worktree and it
matches the shape the helper consumes.
