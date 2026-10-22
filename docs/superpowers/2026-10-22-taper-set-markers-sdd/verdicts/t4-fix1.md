# t4-fix1 handback: Task 4 fix round 1 (Important 1)

**Status: DONE.** This round changes tests only; production code is unchanged.

## Commit
`f4c7a84` test(gather): pin each condition of the owned-show low-confidence flag (fix round 1). It sits on top of 19b0ad2.

## What was added
Three tests in `packages/llama/tests/test_stage_gather.py`, placed just before `test_track_title_veto_is_exactly_today`. They share `_WEAK_DESC` and the helper `_assert_weak_reader_no_flag`.

Every case keeps the reader's coverage weak: 2 of 7 song tracks match, and `structure.coverage == approx(2/7)` is asserted. Each case also asserts `taper_owned` is True, that `low-confidence structure alignment` is not among the flags, and that `needs_llm == ()`. Each removes exactly one of the other three conditions:

| Test | Condition removed | Setup |
|---|---|---|
| (a) `test_owned_low_confidence_needs_canonical_items` | canonical items | Empty description, no setlist.fm, weak markers in `notes`. Asserts `taper.source == "notes"`. |
| (b) `test_owned_low_confidence_needs_no_anchoring` | no anchoring | setlist.fm shares nothing with the tape (step-1 coverage 0), but jerrybase anchoring succeeds on closers Charlie/Golf. Asserts `step1_alignment == "jerrybase"`. |
| (c) `test_owned_low_confidence_needs_weak_step_one` | weak step-1 coverage | setlist.fm matches the tape, so step-1 coverage is 1.0; only the reader is weak. Asserts `step1_alignment == "deterministic"`. |

## Mutation evidence (mandate 5)
**Setup.** Each scratch copy is `git archive HEAD pytest.ini packages/llama`, plus the current test file, under `.../scratchpad/t4-fix1/{M0,M1,M2,M3}`. Each was run from its copy's directory as `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<copy>/packages/llama/src <worktree>/.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -p no:cacheprovider -k <task filter + owned_low_confidence>`.

**Import proof.** For every copy, `llama.stages.gather.__file__` printed that copy's own path.

**Results.** Predictions were written to the log before the run.

| Mutant | Change | Result | Failing assertion |
|---|---|---|---|
| M0 | none | 23 passed | — |
| M1 | drop `canonical.items and` | 1 failed: `test_owned_low_confidence_needs_canonical_items` | `assert "low-confidence structure alignment" not in res.show.review_flags` |
| M2 | drop `anchored is None and` | 1 failed: `test_owned_low_confidence_needs_no_anchoring` | same flag assertion |
| M3 | drop `result.coverage < threshold and` | 1 failed: `test_owned_low_confidence_needs_weak_step_one` | same flag assertion |

Each mutant is killed by exactly its predicted test, on the flag assertion, and by nothing else.

## Test results (live worktree, HEAD f4c7a84)
- `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q` gave 192 passed.
- `./.venv/bin/python -m pytest -q` gave 4394 passed, 1 skipped.
- No existing test changed; the diff is 41 added lines.

## Concerns
None. The reviewer's Minors are deferred to the final review, as instructed.
