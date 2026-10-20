# t7-impl handback
Status: DONE. Commit 050c84b.
Implemented: _is_candidate/_narration_row/_narration_page in scripts/replay_holds.py; compare writes narration_candidates.html. Candidates = cand state held, flags non-empty, each flag single-set-structure prefix or low-confidence setlist (only if stored structure.source=="none" or coverage==0.0). Columns per brief; untitled yes/no; description excerpt 300 chars (existing _excerpt); html.escape on every cell; inline JS sort. Unreadable show.json -> "?" placeholders, slug kept.
Tests added (6): brief's test, exclusion of other flags/no flags, low-confidence proxy (3 cases), row content/escaping/untitled, unreadable show.json, OUTPUT_FILES-superset check.
RED: new tests failed with FileNotFoundError narration_candidates.html (5 failed, 1 passed - the OUTPUT_FILES test passes before as expected). GREEN: 42 passed in scripts/test_replay_holds.py.
Full: ./.venv/bin/python -m pytest -q -> 3292 passed, 1 skipped, 8 deselected.
Concerns: "held" = cand row state == "held" (not outcome), since test sets outcome only; a show with an unreadable show.json and only a low-confidence setlist flag is excluded (structure unknowable). Deviation from brief's test: none besides extra assertion.

## Fix round 1 (0038589)
Replaced parseFloat with a whole-string regex numeric test; numeric cells sort before text, text by localeCompare. Tests added: test_narration_sort_uses_whole_string_numeric_test, test_narration_sort_comparator_is_correct_and_transitive (runs comparator in node; skips if absent). Command: ./.venv/bin/python -m pytest -q -> 3294 passed, 1 skipped, 8 deselected.
