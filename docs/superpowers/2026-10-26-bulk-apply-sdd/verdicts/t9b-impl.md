# t9b-impl: DONE (9be72bde)
Implemented both fixes in packages/llama/src/llama/reapply.py (re-selection skip gated on awaiting_fix; after_commit moved before the purge).
Dry run: no existing test expectation moves (test_processed_and_reselection_rows_are_skipped has its select mark newer than processed, so still awaiting).
RED (live tree, before edit): test_processed_reselection_is_not_sent_back_to_select FAILED; test_after_commit_failure_keeps_library_audio FAILED (audio_files {} vs 6 files); pin test_awaiting_reselection_still_skipped passed (as expected, a pin).
GREEN: test_reapply.py 116 passed; full suite 6200 passed, 1 skipped, 8 deselected.
Files: reapply.py, tests/test_reapply.py. Concerns: none.
