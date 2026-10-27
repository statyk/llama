# t9b-review: Task 9b (dcfa5615..9be72bde)

### Spec Compliance
- ✅ Spec compliant.
  - Fix 1: packages/llama/src/llama/reapply.py:200-202 gates the re-selection skip on `awaiting and mark.start_stage == "select"`. The outcome string is unchanged. The existing order is kept: processed skip, then not-held skip, then digest check, then held path.
  - Fix 2: reapply.py:378-384 calls `after_commit(ws)` after `mark_processed` and before the voiced-rider purge. It is still inside `show_unit`: `_reapply` is called under `with show_unit(ws, None)` at reapply.py:168. The purge echo comes last.
  - All three required tests exist with the brief's names: test_reapply.py:2085, :2097 (pin) and :2107. `test_voiced_rider_purges_when_tracks_equal` (test_reapply.py:1605) is unchanged.
  - The dry-run claim holds. `test_processed_and_reselection_rows_are_skipped` (test_reapply.py:1656-1660) adds its select mark at 2099, so the show is still awaiting and the expected outcome does not move.
  - Task 9's flow holds: `mark_processed` still comes after the `show.json` commit, and every write is still inside the unit.
- ⚠️ Cannot verify from the diff: Task 13's `record_after` hook-in is future work. The new order (hook before purge) is what it needs.

### Strengths
- The fix is minimal: two moved lines per fix, and no new branches.
- The after_commit test checks the right invariants. `audio_files` is unchanged, and `tree_bytes(ws.dir)` is byte-identical, which also covers the rollback of `campaign.json`'s `processed` entry.
- The re-selection tests use real `campaign.add_mark`/`mark_processed`, and the processed test asserts `not awaiting_fix` as its premise.
- The implementer gave RED evidence for both behaviour tests.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. packages/llama/src/llama/reapply.py:11-14: the module docstring now gives the wrong order. It still says "...library audio purged as deliver purges it, and the caller's `after_commit` hook runs". The fix is to say the hook runs before the purge.
2. packages/llama/src/llama/reapply.py:380: the comment "a failure restores, and purged audio is gone" is hard to follow. A clearer wording: "a hook failure restores the unit, which cannot bring back purged audio".
3. Test gap: no test covers a HELD show whose select mark has since been processed now taking the held path (the brief's "for held shows too"). The brief required no such test.

### Checks run
- Grepped the diff for every Untouched name: junk constants and rule, DURATION_TOLERANCE_S, pairing, purge_package_audio, STOP_AFTER_LLM_FAILURES, load_list, briefing_reusable, and the piece-3 constants. The only hits are the unchanged context lines of the `purge_package_audio` call at reapply.py:381-384. None is modified.
- Named risk: does the purge raising after a successful hook undo a recorded success? I checked catalog.purge_package_audio. Its docstring says "Never raises", and OSError is caught and returned as `skipped`. There is no reverse-order hazard.
- Interpreter check: `./.venv/bin/python -c "import llama"` resolves inside the worktree.
- Targeted run: `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py -q -k "reselection or after_commit or voiced_rider or processed_and_reselection"` gave 8 passed.

### Assessment
**Task quality:** Approved
**Reasoning:** Both fixes do exactly what the brief asks, stay inside the unit and come with tests that pin them. The only remaining issue is a stale docstring sentence describing the old order, which is Minor.
