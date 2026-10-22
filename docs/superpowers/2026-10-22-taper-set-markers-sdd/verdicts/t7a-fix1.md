# t7a-fix1: DONE
Commit: 4e17576 fix(harness): grade renumbered rows, stricter known-disagreement checks, in-scope headline
Tests: test_taper_probe.py + test_replay_holds.py + packages/llama/tests/test_replay.py: 160 passed; full ./.venv/bin/python -m pytest -q: 4415 passed, 1 skipped.

Finding -> change -> test
- I1: replay_holds _shadow returns what it stripped; stripped rows carry "stripped": {set_breaks, encore_after} (absent in unstripped rows). taper_probe _fix_applied grades a renum row when stripped values == sort1 t_breaks/t_enc (non-empty stripped required). Tests: test_score_grades_a_renumbered_row_only_when_the_adjudicators_fix_was_stripped (both branches: applied; different breaks; nothing stripped; encore differs); test_strip_mode_removes_only_structure_overrides asserts the stripped record and its absence in unstripped arms.
- I2: stevekimockband -> no-encore; deadandcompany, ekoostikhook -> new not-asserted kind (owned = UNEXPECTED, declined = as expected); 1981-12-31 alone keeps ships. Test: test_score_refuses_an_unstripped_arm_and_scores_the_known_disagreements (both directions for each new kind).
- M3: summary headline renamed "yes/partial excluding filename/track-tag"; new "IN SCOPE (gate definition)" headline over row["in_scope"] with yes / partial split. Asserted in test_score_counts_matches_against_adjudicator_targets.
Other Minors deferred. Caveat: the "graded" line label text changed.
