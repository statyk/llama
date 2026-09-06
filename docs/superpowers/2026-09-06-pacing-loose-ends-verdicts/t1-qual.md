# Task 1 — CODE-QUALITY review (Opus)

## Verdict

**Task quality: Approved**

No Critical or Important findings. Two Minor findings, recorded and deferred.

## What I verified independently (not taken from the report)

All commands run from `/Users/shawn/projects/llama-wt-pacing-loose-ends`.

1. **Workspace identity.** `./.venv/bin/python -c "import llama, herder; print(...)"` resolves both
   packages inside the worktree. `git status --porcelain` is empty — no mutation residue,
   no uncommitted edits. HEAD is `8933fdb`, one commit on top of `cb5ff4e`.

2. **Full suite, the mandated command.**
   `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
   -> `1874 passed, 7 deselected, 26 warnings`. Matches the brief's prediction (1871 + 3)
   and the implementer's report exactly.

3. **The two render tests are load-bearing, not vacuous.** I did NOT mutate the worktree.
   I built a shadow copy of `packages/llama/src` in scratch, planted
   `git show cb5ff4e:packages/llama/src/llama/cli.py` (the pre-change file) over it, proved
   the shadow was actually in effect (`llama.cli.__file__` printed the scratch path — the
   planted-sentinel discipline this project requires), and ran the new tests against it:
   - `test_the_line_renders_the_per_model_meter` FAILS pre-change
   - `test_per_model_meters_render_in_a_stable_order` FAILS pre-change
   - `test_decide_ignores_the_per_model_meter` PASSES pre-change
   So the first two genuinely constrain the new behaviour, and the third is exactly what the
   brief and the commit message say it is: a pin on an existing boundary, not a driver.
   That is disclosed honestly in both the report and the commit body.

4. **Both mutants re-run independently, in the shadow tree, against the FULL suite**
   (the implementer ran them under `-k per_model`, which is 3 tests; I widened it to check
   that the predicted test is not merely *a* failure but the *only* one):
   - Mutant 1, `sorted()` wrapper deleted: `1 failed, 1873 passed` —
     the single failure is `test_per_model_meters_render_in_a_stable_order`.
     Predicted name == observed name, and uniquely so.
   - Mutant 2, `decide()` given a per-model rule (`_pause(max(reading.per_model.values(), ...))`
     appended to the chain): `1 failed, 1873 passed` — the single failure is
     `test_decide_ignores_the_per_model_meter`. Predicted name == observed name, uniquely.
     This is the mutant that matters, and it does what it claims: the render-only boundary
     is enforced by a test, not by intent.
   Both mutants exercise the constraint their test claims to pin. No "some failure appeared"
   scoring here — each prediction was named in the brief before application and each matched.

5. **The empty-`per_model` case is pinned by a pre-existing test.**
   `test_the_missing_reset_guard_follows_the_binding_window` asserts full-line equality with
   `per_model={}` and stayed green untouched, which is what confirms the loop landed in the
   right position in the line rather than merely somewhere.

## Correctness / design

- `UsageReading.per_model` is `field(default_factory=dict)` in `herder/usage.py`, so
  `reading.per_model` is never `None` — the loop needs no guard, and the "renders nothing
  when absent" claim holds by construction rather than by luck.
- Both `_pacing_line` call sites (`cli.py:385`, the run-start block, and `cli.py:1521`,
  `llama pacing`) go through the one function, so there is no second render site left
  showing a stale format. Correct place for the change.
- `decide()`, `binding_forecast` and `shows_that_fit` are untouched — the global constraint
  ("`decide()` stays on two meters") is honoured in the code, not only in the comment.
- The inserted comment earns its place: it says *rendered but not consulted* and points at
  the evidence bar for changing that, which is the exact thing a future reader would
  otherwise be tempted to "fix".
- Diff is 5 production lines and 46 test lines, byte-for-byte what the brief specified.
  No scope creep, nothing speculative — YAGNI respected.
- Test style matches the file: the local `from herder.usage import Meter, UsageReading`
  is this file's established convention (7 occurrences, 4 of them pre-existing), not a
  novelty introduced here.
- Commit message: correct `feat(pacing): ...` form, body explains *why* render-only, names
  the test command and its result, and explicitly records that the third test is a pin.
  Exemplary.

## Findings

**Minor 1 — the per-model segment does not say which window it is.**
The line renders `pacing: 5h 12% · weekly 40% · Fable 42% · est 3.1%/show`. The source
line is `Current week (Fable)`, i.e. a *weekly* per-model window, but next to a segment
already labelled `weekly`, a bare `Fable 42%` invites an operator to read it as a third,
differently-scoped meter. `weekly Fable 42%` (or `Fable weekly 42%`) would carry the scope.
This was specified verbatim by the brief and is pinned by the test's asserted string, so it
is a deliberate choice to revisit at spec level, not an implementation slip. Deferred.

**Minor 2 — `test_the_line_renders_the_per_model_meter` uses `startswith`, not `==`.**
Its neighbours in this file assert full-line equality. `startswith` is defensible here
(the forecast clause appends a variable tail), but it means the test cannot see anything
appended after `est` — e.g. a per-model segment accidentally emitted a second time later in
the line. Pinning the prefix *and* asserting `line.count("Fable") == 1` would close that
without coupling to the forecast text. Low value; the empty-case full-equality test and
mutant 1 already cover the realistic failure modes. Deferred.

**Observation (not a finding).** There is no end-to-end test that the per-model segment
reaches `llama pacing`'s stdout. Both call sites share `_pacing_line` and that function is
unit-tested, so an additional integration assertion would be duplicated coverage. Correctly
not written.

## Process compliance

- Test command used and reported by the implementer is the mandated one, quoted in full,
  with its `cd`. Auditable. No bare `pytest` and no `.venv/bin/<script>` console entry point
  anywhere in the report.
- Mutation restores were verified by the implementer via `git diff`; I confirm the worktree
  is clean at HEAD, so no mutant survived into the commit.
- I made no commits and modified nothing in the worktree; all my mutation work was done in
  a scratch shadow tree, which I have since removed.
