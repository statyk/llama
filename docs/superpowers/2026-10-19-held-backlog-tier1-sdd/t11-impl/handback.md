# t11-impl handback
Status: DONE. Commit: see `git log -1` (feat(titles): 2c glued track-number prefix strip).
Implemented: titles._GLUED_NUM_PREFIX + independent second vote in clean_tag_titles (runs on both the spaced-vote-pass and fail paths; _TRACK_NUM_PREFIX/_ENUMERATED_* byte-identical; control flow restructured from early return to fallthrough). gather imports it and emits `stripped glued track number: track {n} '{raw}' -> '{title}'` into op_notes only when tag_source=="tags" and position not in overrides.titles (M9). Fixture rre2013-11-30.json cut with --from-cache (23 of 23 glued).
TDD: RED observed (4 failed: 3 titles, 1 gather) before implementation.
Tests added: both-paths (spaced fails -> still stripped; spaced passes alongside), vote floors, near-miss test reworked so the vote PASSES (8 glued + 3AM + 01ABBA), gather RRE test (note + 23 notes).
Mutant: drop lookahead -> predicted test_glued_strip_never_reaches_uppercase_or_digit_second_characters; caught by it (plus 4 others: four_digit_year x2, strips_once_never_loops, runs_beside_a_passing_spaced_vote). Shadowing proven (llama.__file__ under scratch tree), private PYTHONPYCACHEPREFIX.
Full suite: ./.venv/bin/python -m pytest -q -> 3432 passed, 1 skipped, 8 deselected.
Files: packages/llama/src/llama/titles.py, stages/gather.py, tests/test_titles.py, tests/test_stage_gather.py, tests/fixtures/rre2013-11-30.json.
Concerns: gather imports a private name (_GLUED_NUM_PREFIX) per brief. Only one mutant run (lookahead); the early-return/both-paths structure is pinned by test_glued_strip_applies_when_the_spaced_vote_fails but not mutated.
