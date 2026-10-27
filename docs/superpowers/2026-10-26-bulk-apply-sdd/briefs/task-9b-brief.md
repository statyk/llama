# Task 9b (parent-directed addition): two reapply fixes from Task 9's review

Context: Task 9 (commit a2e0f20b) extended `reapply_show` (packages/llama/src/llama/reapply.py) to every state, inside `show_unit`. Its review found two literal readings of the plan brief that should change. Task 10 (`--with-gather-llm`) has since edited reapply.py as well; work on top of HEAD.

## Fix 1: gate the re-selection skip on awaiting fix
Today (reapply.py ~179): a campaign record whose LAST mark has `start_stage == "select"` always yields `skipped: re-selection (llama redo <slug> --from select)`, even after the show was re-selected and processed (`campaign.awaiting_fix(rec)` is False), and for held shows too. So a processed re-selected show is sent to another full `redo --from select`.
Change: the re-selection skip applies only when `campaign.awaiting_fix(rec)` is True. When the record is processed after the select mark, the show goes on through the rest of the flow, with the existing order kept: the non-held `skipped: processed` rule, the held path, and the digest check. The outcome string is unchanged: `skipped: re-selection (llama redo <slug> --from select)`.
Tests (RED first, in the live tree):
- `test_processed_reselection_is_not_sent_back_to_select`: a select mark followed by processed. The outcome is NOT the re-selection skip. A non-held show gets `skipped: processed`.
- `test_awaiting_reselection_still_skipped` **(pin)**: a select mark that is not yet processed still gives the re-selection skip string exactly.

## Fix 2: run `after_commit` before the library-audio purge
Today (reapply.py ~330-336), after the `show.json` commit and `mark_processed`, a cleared delivered show with a voiced destination runs `purge_package_audio`, and only THEN `after_commit(ws)`. A hook failure restores every file outside `package/audio/`, but the purged library audio is gone.
Change: call `after_commit(ws)` (when given) BEFORE the voiced-rider purge, still inside the unit. The purge and its echo come last. Behaviour is unchanged when the hook succeeds.
Tests (RED first):
- `test_after_commit_failure_keeps_library_audio`: a cleared delivered show with a voiced destination whose tracks equal the station's, and an `after_commit` that raises. Expect: the unit restores, every file outside `package/audio/` is byte-identical, and `package/audio/` still holds its files (nothing purged). The outcome is a failure.
- The existing `test_voiced_rider_purges_when_tracks_equal` still passes unchanged (the purge still happens on success).

## Constraints
- Global Constraints of the plan apply (lines 15-84 of docs/superpowers/plans/2026-10-26-bulk-apply.md). Untouched names are untouched.
- Dry run: list any existing test whose expectation moves, with the fix that moves it. An unexplained change is BLOCKED.
- Commit message: `fix(reapply): re-selection skip only while awaiting fix; after_commit before the purge`.
