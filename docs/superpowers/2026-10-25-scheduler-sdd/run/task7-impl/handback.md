# Task 7 handback
Status: DONE. Commit: see `git log -1` on playout-scheduler ("transmitter: aired.jsonl history ...").
Implemented history.py (AiredRow, aired_rows_due, append_aired, load_aired, Recency/recency), Workspace.aired_path, service `_step("history")` after publish (resolves/alerts `history`, not in `ran`), _step docstring/comment name PlanLocked.
Tests: full transmitter suite 685 passed, 1 skipped. New: test_history.py (7), test_service.py (2).
TDD: tests were written alongside; first run (before the service import landed) showed 10 failures in test_service/new tests (NameError/AttributeError on `history`), then green after the import. Not a clean isolated RED capture for test_history.
Existing test changed: test_systemd watchdog ping count 5 -> 6 (history step adds one ping per tick).
Concerns: local_date args are ISO strings (date objects accepted via str()); artists_on/artist_years_on do not dedupe per row; Recency last_used_us covers non-show kinds only, last_aired_us shows only.
