## Global Constraints

- **Byte-identical, never edited:** `songs.normalize_song`, `songs.DEFAULT_ALIASES`, `titles.is_real_title`, `titles._TRACK_NUM_PREFIX`, `structure._STRUCTURE_PREFIX`, and every do-not-retune constant named in `CLAUDE.md`: the junk constants (`SHORT_FRACTION_OF_MEDIAN`, `MIN_PLAUSIBLE_SEC`, `MIN_MEDIAN_SAMPLE`), the tail-guard constants (`TAIL_GUARD_ITEMS`, `TRACKS_REMAINING`, `MAX_SKIP`) and `align()`'s default `lookahead=8`, `gather._RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, the sibling-align `AUTO`/`FLOOR`/`MIN_ANCHORS`, `_ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`, `RIGHT_SHOW_MIN_TAPE_FRACTION`, `RIGHT_SHOW_MIN_ASSERTED`, `ADJACENT_DAY_WINDOW`. Every code-quality review greps the diff for these names.
- `process_show` stays lock-free. Lock order stays **run ⊃ show ⊃ ledger**. Never take the show lock twice in one process (`file_lock` opens a new fd per call, and a second `LOCK_EX` deadlocks).
- No new config keys, no new CLI flags.
- Slice B adds and removes no flag, and `venue_source` stays `"item"` wherever B fires. `provenance.json`'s stored candidate is unchanged. The selected string is stripped (`_stripped`). B adds no new normalization and no operator note (plan's call: the spec names none).
- Slice D folds only U+2019 and U+2018 to `'`, on both sides of every comparison it touches. No other character is folded.
- Slice C fixed strings: refusal `"<slug>: changed by another command; run it again"`; removed show `"<slug>: the show was removed; nothing changed"`; no-`show.json` remedy suffix `"; rebuild it with: llama redo <slug> --from gather"`. The snapshot lives at `<show>/.txn/`.
- Nothing inside a unit signals success by raising, and nothing inside it writes to stdout after the last show write (a BrokenPipeError there would roll back a finished redo).
- Tests: run from the worktree root as `./.venv/bin/python -m pytest ...`. Never use a bare `pytest`, and never `.venv/bin/pytest` from a copy (CLAUDE.md). Each task ends with the full suite green: `./.venv/bin/python -m pytest -q`.
- No test may reach a real redo, archive.org or `claude -p`; stub `_redo_show_locked` (or use the fake backend and FakeIA).
- Every behavioural change gets a test that fails on today's code. A test that only pins existing behaviour is marked **(pin)** in this plan.
- Never write to `~/.llama`. Harness outputs go under `~/.llama-harness/small-fixes/`. No task runs `reapply`, `deliver`, `rm`, `fix` or `redo` against the live library.
- One commit per task. End each commit message with the attribution trailer the orchestrating session specifies.

## Review Focus

1. **Files that are not stage artifacts, present before or created during a failed unit** (an `llm-failure.txt` left by an earlier run, a `*.tmp` from a killed atomic write). Pre-existing ones are restored byte-identical. New ones are removed. Test: Task 4 `test_files_outside_the_known_artifacts_are_restored_and_new_ones_removed`.
2. **The first-ever edit: no `overrides.json` existed before the unit.** A failure removes the file the unit created rather than leaving it behind. Test: Task 6 `test_a_failed_first_edit_removes_the_overrides_file_it_created`.
3. **A selected recording whose raw venue is whitespace-only, or differs from the vote only by surrounding whitespace.** Raw strings are counted as grouping counts them, so either case can tie. A whitespace-only string never ships. A padded one ships stripped. Tests: Task 2 `test_a_whitespace_only_selected_venue_never_ships` and `test_tie_ships_the_selected_recordings_string_without_jerrybase`.
4. **A curly apostrophe at a title's edge or inside a segue chain on the tape side** (`He’s Gone > Truckin’`), with straight research or briefing mentions. Both sides are known. Tests: Task 1 `test_guard_folds_curly_apostrophes_inside_segue_chains` and `test_vet_folds_curly_apostrophes_in_a_tape_segue_chain`.

## Orchestrator additions (binding)
- Commit messages end with exactly these two lines (after a blank line):
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01YRawdtMCo2dUTWXzXESNHV
- State the test command and its result in the commit message body (e.g. "Tests: ./.venv/bin/python -m pytest -q — 3970 passed").
- Baseline before Task 1: `./.venv/bin/python -m pytest -q` → 3964 passed, 1 skipped, 8 deselected.
- Never write to ~/.llama. Never run deliver/rm/fix/redo/reapply against the live library.
