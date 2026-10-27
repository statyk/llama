### Finding Verdicts
- **IMPORTANT: `_backfill_one`'s per-show unit had no rollback, so a `record_after` failure or Ctrl-C left `overrides.json` rewritten with no after-record** — ADDRESSED.
  - `scripts/bulk_apply.py:316`: the unit now runs in `with show_unit(ws, None):`. The `file_lock` import is gone (diff hunk at line 30), so there is no nested lock and no deadlock.
  - `show_unit` itself (`packages/llama/src/llama/show_unit.py`, `show_unit()`) does three things:
    - It takes `file_lock(show_ws.lock)`. With `expect=None` the view check is trivially equal.
    - It deletes any leftover `.txn/` or `.audio-aside/`, then snapshots every file outside `package/audio/`, `.txn/`, `.audio-aside/` and `.lock`.
    - On any `BaseException` it restores those files byte-identical, deletes files the unit created, puts the aside back, and re-raises.
  - So both the `OSError` case and the Ctrl-C case are covered. `cmd_backfill` catches only `Exception` (`bulk_apply.py:388-392`), so a `KeyboardInterrupt` still propagates after the restore.
  - `record_after` stays the last write to a tracked file (`bulk_apply.py:331`). The only write after it is `record.jsonl`, which is outside the show directory.
  - `record_after` runs while `.txn/` is in the show directory. `batch_snapshot._metadata_files` skips `TXN_DIR` (`batch_snapshot.py:144`), so the after-record is not polluted by it.
  - The early returns ("skipped…", "nothing new") are normal exits, so the snapshot is discarded and nothing is restored, which is correct.
  - The test `test_a_failed_after_record_rolls_the_show_back` (`scripts/test_bulk_apply_backfill.py:340-369`) checks:
    - `overrides.json` is byte-identical after the failure.
    - There is no after.jsonl, no record.jsonl and no leftover `.txn/`.
    - The batch restore reports `untouched`.
    - A later successful `--apply` writes both rules and records g1 in the new batch's after.jsonl and record.jsonl.
  - I re-ran `scripts/test_bulk_apply_backfill.py` from the worktree's own interpreter (llama resolves inside the worktree): 10 passed.

### New Breakage in the Fix Diff
None.

I checked the two points the implementer raised:
- **`_stamp()` seam** (`bulk_apply.py:341-342`, used at `:376`): it only factors out the timestamp format, so behaviour is unchanged. The `bdir.exists()` refusal still guards a same-second collision.
- **A `record.jsonl` append failing after the after-record:** the unit rolls back, so the after-record describes a state that no longer exists. `_restore_one` then finds `current == snap_files`, and with the station unchanged (backfill never writes the station) it returns `"already restored"` (`batch_snapshot.py:460-461`) and writes nothing. That is harmless and does not refuse the batch. `record.jsonl` has no programmatic reader (grep: only `_append_jsonl` writes it), so a torn line there affects nothing downstream.

### Out-of-Scope Observations
- (Minor, pre-existing `show_unit` limitation 3, not introduced here.) If `show_unit`'s own restore fails, `.txn/` stays and `overrides.json` may stay rewritten. A re-run's `_new_rules` pre-check would then see the rules as present, report "nothing to record" and exit 0, so that write has no after-record in any batch. This needs a second failure inside the rollback itself; it is documented as the general unit limitation and is not worth gating on.
- (Minor.) After an append-failure rollback, a re-run in a new batch may produce `overrides.json` bytes identical to the old batch's after-record (when the merged rules serialise the same). In that case the old batch's restore would match its after-record and rewind the new batch's write. The end state is still the pre-backfill one, and the new batch's restore then reads `already restored`, so nothing is lost.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
