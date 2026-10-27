# Task 13b report
Status DONE. Commit: see git log (fix(reapply): trial counts the shows that spent; ...).
Impl: cli._reapply_list wraps providers with pipeline.count_llm_calls (pacing's detector); per-row spent = llm_calls() > before; new trial() helper used by success and fail paths; fail() records meter {before,after}; snapshot verify before first show when snapshot/ exists (refusal line per brief, first problem as detail).
Moved test: test_stop_at_points_ends_the_block (brief clause 1: its stubbed shows made no LLM call, so n would be 0; now each show makes one counted call).
TDD: both new tests RED against unmodified cli.py (n=5 not 3; snapshot case failed the show after package instead of refusing), GREEN after. Full suite: 6263 passed, 1 skipped, 8 deselected.
Concern: failed rows now read the meter once more (fail path); tests with scripted meters unaffected.

## Fix round 1
Added "llm_calls": llm_calls() - calls_before to extra on the fail() record and the success record_progress. Test test_trial_count_excludes_shows_that_spent_nothing extended (7 rows; added a zero-spend IAError row; asserts llm_calls >0 on spending failed and committed rows, ==0 on zero-spend failed and a skip row; n unchanged at 3).
RED (before cli.py change): `pytest packages/llama/tests/test_reapply.py -k trial_count` -> KeyError: 'llm_calls'. GREEN: 4 passed on covering tests; full suite `./.venv/bin/python -m pytest -q` 6263 passed, 1 skipped, 8 deselected.
