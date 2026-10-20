# T22 handback
Status: DONE. Commit e408703 (docs only: CLAUDE.md +179, README.md +53). Suite: 3761 passed, 1 skipped, 8 deselected.
CLAUDE.md: Commands bullets (reapply; fix --untitled/[u] + eotoband route; replay_holds run|compare; notes.json) and one Architecture bullet for the Tier 1 guards (1a-1d, 2a-2c, 3a-3c, 4a-4d + day-00 rule, 5a, 5c.1, 5c.3; 5c.2 recorded as dropped). Names/flags taken from cli.py (reapply, _reapply_list, _untitled_resolution, fix), reapply.py (load_list, batch_dir, STOP_AFTER_LLM_FAILURES), replay.py (code_identity, input_digests, briefing_reusable), replay_holds.py (main, OUTPUT_FILES, _gates exit 2, repro gate exit 3), vet_research.py constants, brief.py, titles.py.
README.md: new section "Re-checking the held backlog" (harness, reapply, dry-run/pilot/waves) and an --untitled paragraph in the held-show resolutions.
Concerns: 1c/swap/2a etc. described at one-sentence depth; reapply single-show form has no pacing gate (documented). BASE test count not independently re-run before edit.

## Fix round 1 (commit 030caa7)
Diff vs ed8b0c5: CLAUDE.md +90, README.md +55/-1. Suite 3761 passed, 1 skipped, 8 deselected.
Cut: write-order and digest enumerations, outcome-class list, procedure sentence, 14-file enumeration (now OUTPUT_FILES pointer), checkpoint/task history in guards, token-level fold lists.
Findings: Important 1 -> reapply bullet (durable EWMA statement, no number). Important 2 -> Commands and one Architecture bullet shortened. Minors: _ENUMERATED_MIN_COVERAGE, exit-2 causes, "one fresh brief task", vet writes notes.json, 2b item-title arm, ADJACENT_DAY_WINDOW = 1, 4d unmeasured, 3c ordinals (in CLAUDE.md); README "three resolutions (plus a fourth)", compare paths, "any missing audio". Plan pointer kept (evidence doc absent).
