# fixG-scope: DONE
Changed `_SCOPE_AFTER` in packages/llama/src/llama/stages/brief.py: `^\s*` -> `^[^\S\n]*` (rest byte-identical, comment added). No scope-before window exists, so nothing else touched.
Added test_3c_scope_window_does_not_cross_a_briefing_field_boundary (test_stage_brief.py).
Tests: test_stage_brief.py 62 passed; full suite 3762 passed, 1 skipped, 8 deselected.
Mutation (scratch copy, shadowing proven): revert to `^\s*` -> predicted new test -> caught by it (1 failed, 61 passed).
Deviations: none. Concerns: none.
