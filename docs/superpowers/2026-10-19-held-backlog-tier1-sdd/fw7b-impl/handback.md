# fw7b handback: DONE
Commits (on held-backlog-tier1): b30bed5 docs (CLAUDE.md/README, items 1-4, 12); 17d3ba9 comments (5,6,7,11); 0fead4d fix(reapply) dry-run skip (13, code); cd9a0b6 tests + hygiene (8,9,10,13 test).
Full suite: `./.venv/bin/python -m pytest -q` -> 3802 passed, 1 skipped, 8 deselected (was 3762).
Item 13: reapply_show dry-run returns "dry-run: skipped: structure changed" (briefing "none") without the flag; cli dry-run counting excludes predicted "skipped*".
Item 8: fix test + triage [u] test (both). Item 9: briefing.md-only drop test (held_for_real env, json unlinked).
Item 10: mid-file imports moved to top via an ast script in 22 touched test modules (incl. scripts/); cities_not_compatible both orders; _two_arms 3-positional call sites now keyword; logging.disable(NOTSET) in a finally in the restore-logging test.
## Mutation table (scratch rsync copy, PYTHONPATH shadow proven, per-mutant PYTHONPYCACHEPREFIX)
| mutant | predicted | caught by |
| confirmed-but-held returns "declined" (cli) | test_untitled_confirmed_but_still_held_says_still_held_not_declined; triage ...still_held | both caught |
| drop `or ws.briefing_md.exists()` | test_a_held_outcome_with_only_a_stale_briefing_md_drops_it | caught |
| dry-run counts skipped structure row (cli guard removed) | test_dry_run_of_a_structure_changed_row_is_skipped_unless_allowed | caught |
| dry-run skip in reapply.py disabled | same | caught |
Notes: first M13a attempt had a syntax error in my patch script (not applied; re-run properly, caught). Deviation: item 2's "re-wrap the fw3 sentence" done by rewriting that paragraph. Import moves are appended after the last top import (not isort-sorted).

## Fix round 1: DONE
Commit: see `git log -1` ("docs,test: fw7b review minors"). Suite: 3803 passed, 1 skipped, 8 deselected.
Minors 1-7 done: "llm" alignment moved to the gather clause; README wording; _two_arms keywords at the last 3-positional site; reapply/untitled/replay_holds bullets, the Tier 1 1c-3c passage and README paragraph re-wrapped to ~80 cols (wording unchanged); dry-run sentence corrected (list form prints would: ... skipped, names form dry-run: skipped, summary only for --from-list); new names-form dry-run test; duplicate briefing_guard import dropped.
