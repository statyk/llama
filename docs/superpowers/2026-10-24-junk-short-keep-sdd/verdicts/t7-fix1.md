# Task 7 fix round 1
Status: DONE. Commit: 5d3e452 fix(scripts): short-keep probe guards repro --out, pins reproduction fields and class precedence
Test: ./.venv/bin/python -m pytest -q -> 4980 passed, 1 skipped, 8 deselected (+12 over 4968).

## Changes (scripts/short_keep_probe.py, scripts/test_short_keep_probe.py)
1. _guard_out(out, config, *others): library root read as replay_holds.run does (load_config(config or DEFAULT_ROOT/"config.toml").root; a given but missing --config is a refusal), uses _overlaps. arms and repro both call it (repro gained --config; its pre/post overlap check now goes through the same guard). Tests: test_arms_refuses_an_out_inside_the_configured_library_root, test_repro_refuses_an_out_inside_the_configured_library_root (exit 2, nothing written, and a non-overlapping out succeeds with 0).
2. test_reference_reproduction_pins_each_field[6 params]: one candidate per field differing only in it, asserts exactly ["s1: <field> differ"].
3. Precedence: test_class_precedence_positional_lost_beats_new_unresolved (ratdog shape), ..._new_unresolved_beats_later_classes, ..._long_single_set_beats_closer, test_low_confidence_plus_another_new_flag_is_not_low_confidence_remains.

## Mutation table (scratch copies via git archive HEAD + overlay, PYTHONPATH shadow; __file__ printed and inside the copy each time; baseline M0: 31 passed)
- M1 drop filenames comparison -> FAILED test_reference_reproduction_pins_each_field[filenames]
- M1b drop sets -> [sets]; M1c drop segues -> [segues]; M1d flags compared to nothing -> [flags]
- M2 swap positional-lost/new-unresolved -> test_class_precedence_positional_lost_beats_new_unresolved
- M6 low-confidence all->any -> test_low_confidence_plus_another_new_flag_is_not_low_confidence_remains
- M5a arms guard removed -> test_arms_refuses_an_out_inside_the_configured_library_root
- M5r repro guard removed -> test_repro_refuses_an_out_inside_the_configured_library_root
(full output in t7-fix1.log)

## Concerns
- Pre-existing: test_arms_refuses_candidate_rows_without_fields_and_overlapping_out's ref-dir half also exits 2 from the missing-fields refusal, so removing only the ref-dir guard is not caught. Not in this round's scope; deferred minors untouched.
