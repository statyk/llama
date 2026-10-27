# Final-review fix wave (Task 18 Step 3): one dispatch, the complete findings list

The whole-branch review (Opus; full text `.superpowers/sdd/bulk-apply/final-review/handback.md`, read its Important 1-3 and the Minor list before starting) returned READY WITH FIXES. Fix everything below in one pass. **Implementer: Sonnet.** HEAD at dispatch: 44ae6cf2 (suite 6350 passed, 1 skipped, 8 deselected).

## Important (fix)

**I1 — CLAUDE.md misstates what `deliver` refuses** (`CLAUDE.md`, the `**Awaiting fix (bulk-apply):**` sentence in the `llama deliver` bullet, ~line 88). It says "a station copy marked `awaiting_fix` is refused by plain `deliver`". The code (`cli._awaiting_fix_check`) refuses a show whose LIBRARY campaign record is awaiting fix (unreadable record included); a marked station copy whose library show has been processed is replaced wholesale on delivery, which clears the mark (`_deliver_one`'s `voiced or marked or …` branch). Reword to say exactly that, keeping the fixed strings that follow. Check every other CLAUDE.md sentence the docs commit added about the mark for the same confusion (library record blocks; station mark is what `deliver --fixed` replaces and what emcee/transmitter honour).

**I2 — `reapply.py` module docstring has the post-commit order wrong** (`packages/llama/src/llama/reapply.py:11-14`): it says processed → purge → `after_commit`; the code (≈ lines 380-386, the Task 9b fix) runs processed → `after_commit` → purge, so a failing hook still finds the library audio in place. Fix the docstring to the code's order and say why in a few words (a future edit must not "restore" the old order). Also fix the inline comment near reapply.py:380 if it says otherwise.

**I3 — strict-reuse refusals fire only at package time in `_redo_show_locked`** (`packages/llama/src/llama/cli.py`, `_redo_show_locked`, the `reuse = plan_reuse(...)` call ≈ line 3079). With the station unmounted (or a copy that does not pair), `fix --set-title` on a delivered show, a triage edit, or a selector `redo --from gather|brief` over delivered shows pays for gather's align call and a fresh brief per show, and only then refuses (`StationUnreadable`/`StationUnpaired`) and rolls the unit back. Required: immediately after `plan_reuse(..., strict=strict)` — before any stage runs — call `audio_reuse.check_pairs(reuse, show_ws)` (same plan object; read `check_pairs` and confirm it has no side effects and raises the same exceptions `build_package` would, so the refusal text, hint and exit path are unchanged). Only when strict applies (the same condition `build_package`'s check uses); a non-strict redo is unaffected.
- Test (name fixed), shown RED in the live tree before the change: `test_redo_of_a_delivered_show_refuses_strict_reuse_before_any_llm_call` — a delivered show whose station copy is unreadable (or absent from a configured station root, whichever the existing strict tests use), run through the redo path from `gather` (or `brief`) with the `fake` backend: it refuses with the existing `station copy unreadable` / `does not pair` string and hint, and the fake provider recorded ZERO calls (today it records the align/brief calls first). Reuse the existing strict-reuse test fixtures in `packages/llama/tests/` (grep for `StationUnreadable` / `station copy unreadable`). Production passes provider LADDERS: configure the test the way the existing redo tests do (list form).

## Minor (fix — all small)

**M1 — `_deliver_batch` reports a delivered show as refused** (`cli.py` ≈ 2735-2775): a show processed between the selector scan and taking its lock is delivered, yet the summary still prints `  (refused: awaiting fix)` from the pre-scan `marks[slug]`. When the under-lock re-check passes and the show is delivered, drop its mark (`marks.pop(slug, None)`). Test `test_batch_deliver_does_not_report_a_show_processed_meanwhile_as_refused` (simulate by making the record processed after the scan, e.g. monkeypatching the scan result or the record read; follow the existing batch-deliver tests' style).

**M2 — `_fixed_for_delivery` docstring overstates its re-check** (`cli.py:2716-2719`): make it say precisely what `_deliver_one` re-checks under the lock (read the code; do not change behaviour).

**M3 — plan Appendix B (undo), three one-line additions** (`docs/superpowers/plans/2026-10-26-bulk-apply.md`):
- Restoring a wave empties a packaged, undelivered show's `package/audio/`, so its next package re-downloads from archive.org (bandwidth only; the station is never touched).
- A torn `after.jsonl` line (a process killed inside `record_after`) makes `restore` refuse; repair: delete the torn last line, and that show then refuses as "no write recorded" (restore it by hand or roll forward). Verify the exact refusal text in `packages/llama/src/llama/batch_snapshot.py` before writing it.
- `unmark` keeps the station mark for a `marked` line whose `mark_added` is false (the library is still awaiting from an earlier batch, so the two stay consistent; a mark only blocks voicing and airing).

## Parked (do NOT change)
- The equal-copy `--replace-voiced` refusal is checked before the held gate, so a held, voiced, marked show is pointed at `clear-mark`, which then refuses it as held with its own message — the operator is still guided; changing refusal order on the deliver path is not worth the risk this late.

## Constraints
- Global Constraints' Untouched list holds (junk constants, `DURATION_TOLERANCE_S`, `audio_reuse`'s pairing rule, `purge_package_audio`'s verification, `STOP_AFTER_LLM_FAILURES`, `load_list`'s gate, `briefing_reusable`). I3 adds a call; it must not change `check_pairs` or `plan_reuse`.
- Stub `station_mark.emcee_running()` / `ps` in any test that reaches it. Never write under `~/.llama`, `~/.llama-harness` or `/Volumes/media/lma-radio/delivered/`.
- Existing tests whose expectation moves: list each with the reason before editing.
- Full suite green: `./.venv/bin/python -m pytest -q` from the worktree root.
- Commits (one per coherent step is fine), each with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` and the test command; e.g. `fix(llama): redo checks strict station reuse before any LLM spend`, `fix(llama): batch deliver does not report a show processed meanwhile as refused`, `docs: deliver's awaiting-fix refusal is the library record; reapply post-commit order; undo caveats`.
