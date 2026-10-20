# t17-impl handback: DONE
Commit df602e0 (on BASE e59a6d8): structure._ENCORE_MARKER + encore_lost; compute_gather discards "encore" from evidence unless encore_lost; `encore_lost` imported at top of gather.py with the other structure imports.
Tests: new tests pass; full suite `./.venv/bin/python -m pytest -q` -> 3680 passed, 1 skipped, 8 deselected.
Deviations (per ruling B4): new helpers named `_titled_tracks` and `_encore_items` (no `_items` collision existed, renamed anyway for clarity); existing `_tracks` untouched.
Mutation (scratch under $TMPDIR/mut-t17-impl-05rLAf, shadowing proven, deleted):
| mutant | predicted | result |
| a encore_lost ignores _ENCORE_MARKER | test_encore_lost_on_an_unmatched_..._marked_track (Crowd Encore Call line) | caught by it |
| b returns True whenever encore item exists | test_encore_lost_is_false_..._when_it_matched | caught by it (+ the 5a gather test, extra) |
| c compute_gather always discards "encore" | test_5a_passes_numbered_sets_only_unless_the_encore_was_lost | caught by it |
No survivors. No concerns.
