# task9-fix3 handback
Status: DONE (test-only; pipeline.py untouched, no defect found)
Commit: c7b7391 test(transmitter): bound the unstable-measurement helper; pin the per-slug mismatch rule (amended over WIP 9e6d844, used as the mutant base)

1. `_unstable` now raises AssertionError ("... the re-plan loop is unbounded") past UNSTABLE_MAX_CALLS=10. Under correct code the guard tests need 3 (3-pkg) and 4 (1-pkg) measurements, measured.
2. New test_the_second_mismatch_rule_is_per_slug: rows[0] and rows[1] (different slugs) each read a frame count that is wrong once, then correct. Asserts replanned == [a, b], both stay at plan positions 0/1, both encoded, 2 plan-changed logs. A real config change cannot produce two mismatches in one call, because the first re-plan re-measures every later row, so this test uses a flaky-once measurement.

Mutants (scratch copies from git archive HEAD, empty cwd, `.venv/bin/python -m pytest`, PYTHONPATH shadow, PYTHONDONTWRITEBYTECODE=1; MUTANT_SENTINEL printed from the scratch pipeline.py):
- M2 (guard removed, exclude=False). Predicted: the two guard tests FAIL, no hang. Observed: exactly those 2 failed with "measured 11 times: the re-plan loop is unbounded", 23 passed, 0.73 s.
- M3 (exclude = bool(mismatched)). Predicted: only the per-slug test fails. Observed: exactly test_the_second_mismatch_rule_is_per_slug failed, 24 passed.

Commands: ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 2329 passed, 7 deselected; transmitter suite on 3.14 -> 180 passed; ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider -> 180 passed.
Concerns: none.
