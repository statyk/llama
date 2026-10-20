# fw3 impl report: DONE
Commit: see `git log -1` on held-backlog-tier1 ("fix(reapply): a held outcome drops a briefing written against older titles").
Change: reapply.py reapply_show, new block before `if not flags:` drops via `drop_stage_artifacts(ws, "brief")` when briefing is None and flags and a stored briefing.json/.md exists and `any(replay.shipped_diff(stored, final_show).values())`; appends "drop:brief" to written. Helper reused: `llama.replay.shipped_diff`. drop_stage_artifacts("brief") drops briefing.json, briefing.md AND package/manifest.json (brief + downstream package stage); the stale manifest also carried old titles and the redo-from-package path needs it gone. Comment records the crash-ordering reasoning.
Tests: 6 added in test_reapply.py (drop test; no-drop (c) twice; (a); (b) forced via wrapped compute_legs since reuse+flags is unreachable by construction; (d)). Full suite: 3792 passed, 1 skipped, 8 deselected.
Docs: one sentence in CLAUDE.md reapply bullet.
Mutants (shadowing proven each, under -> $TMPDIR/mut-fw3-*, removed):
- M1 never drop -> drop test -> caught by test_a_held_outcome_with_changed_titles_drops_the_stale_briefing
- M2 drop whenever held -> case (c) -> caught by test_a_held_outcome_with_no_shipped_change_keeps_the_briefing, ..._and_no_carried_flag_keeps_the_briefing (+ existing test_a_show_still_flagged_after_vet_is_written_held_with_no_briefing_or_package)
- M3 drop even when briefing not None -> case (a) -> caught by test_a_failed_fresh_brief_is_not_dropped_even_when_titles_changed (+ test_a_reused_briefing_is_not_dropped)
Concerns: none. Fixture lacks briefing.md, so tests write one.
