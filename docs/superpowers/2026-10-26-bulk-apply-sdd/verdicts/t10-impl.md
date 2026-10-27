# Task 10 handback (t10-impl): DONE_WITH_CONCERNS
Commit: 120b0405 feat(reapply): --with-gather-llm for shows whose replay needs an LLM call

## Implemented
- gather.py: compute_gather(llm_failures_raise=False). Only the align_structure `except (TaskFailed, HerderError)` arm re-raises when True (extract_setlist already raises; RateLimited arm untouched).
- replay.py: GATHER_LLM constant; compute_legs(gather_providers=None, llm_failures_raise=False). With providers, they go to compute_gather and "stored alignment llm" is not appended.
- reapply.py: _reapply(with_gather_llm). Flow: first compute_legs, then if with_gather_llm and needs_llm non-empty and <= GATHER_LLM: dry run returns "dry-run: needs-llm"; delivered show runs strict plan_reuse/check_pairs (reuse object kept and reused by the later package step); recompute with (extract_setlist, align_structure) providers + llm_failures_raise=True before any write; continue as Task 9, final kind = "needs-llm". align_reproduced (filenames, sets, segues, set_breaks equal) set only when first needs_llm held align_structure or stored alignment llm; None otherwise. Applied to every later result (incl. skipped: structure changed). Fresh brief's overrules= and split_overruled, STOP_AFTER_LLM_FAILURES, split_overruled/overrules pass-through in compute_legs all untouched.
- cli.py: `--with-gather-llm` on reapply (names form passes it; `_reapply_list` too). No change to the list runner's except arms.

## Dry-run list (existing tests whose expectation changes)
None. No existing test edited; 14 new tests only.

## Tests
Full: `./.venv/bin/python -m pytest -q` -> 6192 passed, 1 skipped, 8 deselected (6178 + 14 new).

## TDD evidence
RED run in a scratch worktree at HEAD (pre-change source, new test files copied, PYTHONPATH shadow, llama.__file__ verified in scratch): 10 failed, 7 passed (selection includes 3 old tests). Failed (RED): test_needs_llm_show_is_reapplied_with_gather_llm, test_align_reproduced_true_and_false, test_refusal_on_the_align_call_writes_nothing, test_dry_run_makes_no_llm_call, test_with_gather_llm_align_failure_is_a_retryable_row_failure, test_unpaired_delivered_show_spends_no_align_call, test_cli_with_gather_llm_flag_reaches_reapply_show, test_gather_llm_set_names_the_three_verdicts, test_compute_legs_with_gather_providers_does_not_append_the_stored_alignment_verdict, test_compute_gather_llm_failures_raise.
Passing pre-change by design (pins of unchanged behaviour): test_without_the_flag_needs_llm_writes_nothing, test_no_vetting_json_stays_needs_llm, test_align_reproduced_is_none_when_no_llm_ran, test_compute_gather_degrades_llm_failure_by_default.
GREEN: same selection in the live tree passed (10 passed in the reapply group), then full suite as above. Log: t10-impl.log.

## Files
packages/llama/src/llama/{cli,reapply,replay}.py, stages/gather.py; tests test_reapply.py, test_replay.py, test_stage_gather.py.

## Self-review / concerns
- Fixture quirk: in the gd73 fixture titles come from the description, so tests force the align call via operator `titles` overrides + empty vetting assertions (needs a fresh brief response).
- The pre-check plan_reuse for delivered shows runs even when the outcome ends label-only/held/skipped (per brief); the show's later package reuse the same plan.
- A delivered show with `allow_download` plans non-strict (strict=not allow_download), consistent with Task 9.
- No-vetting-json combined with a gather verdict stays needs-llm (not a subset), by design.
- The sample for ReapplyOutcome.kind on `skipped: structure changed` after a recompute stays "none"; only committed rows are "needs-llm".

## Fix round 1
- reapply.py: align provider wrapped in `_CallCounter`; `align_reproduced` set iff stored alignment was llm or the counted align provider was called in the recompute.
- Tests: `test_with_gather_llm_align_failure_is_a_retryable_row_failure` parametrized (HerderError, TaskFailed); new `test_align_reproduced_is_set_when_an_extract_only_show_calls_align_in_the_recompute` (RED on pre-fix source in a scratch worktree: 1 failed, 3 passed; GREEN now) and `test_with_gather_llm_extract_setlist_failure_writes_nothing`.
- Command: `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py packages/llama/tests/test_replay.py packages/llama/tests/test_stage_gather.py -q` -> 693 passed (there is no test_gather.py; gather tests live in test_stage_gather.py). Full suite: 6195 passed, 1 skipped, 8 deselected.

## Fix round 2
- reapply.py: removed `_CallCounter`; uses `pipeline.count_llm_calls({"align": providers["align_structure"]})` (wraps each rung of a ladder, or a single provider, with one shared counter).
- Tests (RED at previous HEAD in a scratch worktree: both fail with AttributeError 'list' has no 'complete'; GREEN now): `test_align_ladder_of_providers_is_counted_and_reproduced_is_set`, `test_align_ladder_where_every_rung_raises_is_a_retryable_failure_not_a_crash`.
- Covering: 695 passed (reapply/replay/stage_gather); full suite 6197 passed, 1 skipped, 8 deselected.
