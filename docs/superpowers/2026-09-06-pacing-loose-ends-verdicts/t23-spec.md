# Spec-compliance review — Tasks 2 & 3 (pacing-loose-ends)

Reviewer: spec-compliance, Opus. Worktree read-only throughout; all mutation
was done in `git archive` copies under the scratchpad, proven by
`python -c "import llama; print(llama.__file__)"` resolving inside the copy,
and run via `python -m pytest` (never a `.venv/bin/*` console script).
Worktree confirmed clean at `126bd72` before and after.

## Verdicts

- **Task 2 spec ✅** — implements the brief exactly; asymmetry independently reproduced.
- **Task 3 spec ✅** — implements the brief exactly; one Minor informational finding, measured.

## Verification performed

Gates, run from the correct checkout with the mandated command
(`cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`):

- HEAD `126bd72`: **1875 passed, 7 deselected** — matches Task 3's predicted 1875.
- `c462c0b` (Task 2 alone, rebuilt in a copy): **1874 passed, 7 deselected** — matches Task 2's predicted 1874 (+1 new, −1 retired).

Diff scope: only `packages/llama/tests/test_config.py` and
`packages/llama/tests/test_sessions.py`. No source changes, so no constant was
retuned. Both test bodies match their brief's prescribed code verbatim
(`import re` added as instructed). Commit style is lowercase
`type(scope): subject` with bodies explaining why.

### Task 2 specifics

- `test_default_config_template_documents_every_pacing_knob` is **deleted**
  (`grep` over `packages/` finds no trace), and commit `c462c0b`'s body states
  "the new test subsumes it as the [pacing]-only special case." Requirement met.
- Mutation prediction was stated in the brief before application, and the
  implementer's report records prediction-before-observation. I reproduced it
  independently in a copy, stating my prediction first:
  deleting `five_hour_ceiling = 90` → **1 failed, 21 passed**, failing test
  `test_the_template_documents_every_config_key` with
  `AssertionError: keys missing from DEFAULT_CONFIG_TOML: {'pacing': ['five_hour_ceiling']}`.
  Name and message both match the prediction.
- **The required asymmetry is confirmed by direct measurement**: under that same
  mutant, `test_default_config_template_matches_defaults` run on its own **passes**.
  This is the entire justification for the new test's existence, and it holds.
- Two extra mutants of my own (not required, run to check the test is not
  passing for accidental reasons — both stated before application):
  - removing the commented `# root = ...` example → `{'<top-level>': ['root']}`,
    1 failed / 21 passed, old test still green. The commented-line handling
    (brief fact 1) is load-bearing.
  - removing the `[[selection.lineage_eras]]` header → `{'selection': ['lineage_eras']}`.
    The nested-table-header handling (brief fact 2) is load-bearing. (This mutant
    is not behaviour-neutral, so it reddens two other config tests as well —
    expected, and irrelevant to the asymmetry claim, which mutant 1 settles.)
- `_FREE_FORM = {"llm", "tiers"}` checked, not assumed: both **are** real
  `Config` fields and both are free-form maps, so neither exclusion hides a
  fixed key set. No dead exclusion.
- Nothing was weakened to make it pass: the test is the brief's assertion
  verbatim, and three distinct mutants redden it.

### Task 3 specifics

- The forbidden weakenings are absent: the final assertion is `==`, not `>=`,
  and it sums over **all** providers rather than a subset. The required
  non-empty precondition `assert spent > 0` is present, above the equality,
  with the brief's rationale comment.
- Green on first run, which is the expected/correct outcome here.
- Implementer's mutation: prediction stated first; the predicted test reddened
  **by name**. The implementer disclosed honestly that the failure landed on
  `assert resumed.exit_code == 0` rather than the predicted final equality.
- I investigated that divergence independently rather than accepting or
  penalising it, and it is a property of the fixture, not of their mutant choice.
  Measurements (predictions stated before each):
  - Unmutated resume genuinely re-reaches the show (`packaged: …` in output)
    and spends **zero** calls. The test is **not** vacuous.
  - Isolating the true regression class — disabling only the per-show gate at
    `stages/research.py:13` — **reddens the test**, at
    `assert resumed.exit_code == 0` (line 461), with
    `FakeProvider: no queued research responses left` and exit 1. My prediction
    that it would land on the final equality was **wrong**, and this is the
    finding below.
  - This also confirms the docstring's mechanism attribution ("the property is
    `should_run`'s") for the per-show stages.

## Findings

1. **[Task 3 — Minor]** The final call-count equality is currently the test's
   statement of intent rather than its active detector. Every `fake_providers`
   queue is sized exactly for one show, so any re-spend raises
   `AssertionError: no queued … responses left` and exits 1, tripping
   `assert resumed.exit_code == 0` first — I measured this for the real
   regression class (per-show `research` gate disabled), not just for the
   brief's fresh-run mutant. The test **does** go red on the regression, so it
   is correct and must not be weakened; but if the equality itself should be
   the detector, the fixture needs spare queued responses. Recommend accepting
   as-is and filing, not reworking.
2. **[Task 3 — Minor, informational]** A blunt global `should_run → True`
   mutant does **not** redden this test: run-level winnow re-runs and the
   library dedup empties the shortlist ("No shows survived winnowing."), so the
   show is never revisited. That is a bad isolation on my part, not a weakness
   in the test — recorded so nobody repeats it and misreads the result as the
   test failing to pin `should_run`.
3. **[Task 2 — none]** No findings.

## ⚠️ Cannot verify from diff

None. Every requirement in both briefs was verifiable from the diff, the commit
messages, the tree, or a measurement I ran myself. The implementer's report
names its test command for every reported result, so all reported numbers are
auditable, and both gate counts reproduced exactly.
