# Task 8 fix round 1: DONE
Commit: see `git log -1` (fix(scripts): short-keep probe review fixes). Full suite: `./.venv/bin/python -m pytest -q` -> 4986 passed, 1 skipped, 8 deselected.
- Important 1: test_packet_membership_comes_from_the_candidate_not_r1_dec (tiny world, all rows drawn: r1_dec keep but not in cand is never drawn; drop-junk music kept by cand is drawn as music/keep; in-show not-short_kept file never drawn). Kills M1/M2 (not mutation-run; passed on the unchanged code as a coverage addition).
- Important 2: INSTRUCTIONS phrase replaced with "a mixed tag such as `tuning/banter` is kept".
- Minor 2: packets refuses (exit 2) replayable candidate rows lacking filenames/short_kept or of unequal length; membership via set(filenames). Test: test_packets_refuse_candidate_rows_without_valid_short_kept (failed before).
- Minor 5: score test adds exactly-90% (9 of 10) PASS, kept spoken-broadcast, dropped fragment and segue-or-continuation each FAIL.
- Minor 7: first10.md blind with position and floor_sec; answers in first10-answers.md (asserted in test_score_bar_and_wrong_rows, failed before).
