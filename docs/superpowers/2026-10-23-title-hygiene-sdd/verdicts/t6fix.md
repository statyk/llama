# t6fix handback
Commit 174995e (tests only, packages/llama/tests/test_title_hygiene.py).
Tests added:
- test_decide_d_agreement_exactly_at_floor_passes: decide_d with share exactly 0.5 -> failed == (), fill made.
- test_apply_d_guard_skips_a_resolved_position: hand-built DDecision({0:"Wrong Title",1:"Jack Straw"},(),{}); resolved track 0 untouched, unresolved track 1 filled.
Mutants (scratch ~/.llama-harness/piece3/mutation/t6fix/{a,b}; llama.__file__ confirmed under scratch):
- (u) `<` -> `<=` at :428: 1 failed (the new floor test), 90 passed.
- (zD) guard removed at :439: 1 failed (the new apply_d test), 90 passed.
Real code: module 91 passed; full suite 4762 passed, 1 skipped, 8 deselected.
