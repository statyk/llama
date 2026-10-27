# Task 14 review (t14-review): overrule backfill, 5192e02b..da32e253

### Spec Compliance
- ✅ Spec compliant on every rule the brief names, with one ❌ on the undo surface (Important 1) and one silent-drop gap to raise at Checkpoint A (Minor 1).
  - Considered rule: `_considered` (outcome `newly-held`, base state != `held`) plus `derive_state(ws, delivered)[0] == "held"` -> skipped (`_plan_one`). `derive_state` decides `held` from `show.needs_review` alone (catalog.py:120-125), so the `delivered` set only matters for the other states. Pinned by `test_show_held_today_is_skipped`.
  - Base flags = gather + vet + brief (`_plan_one`). Layout A `flags[].verdict == "spurious"`, layout B `claims[].verdict == "flag-spurious"`, each honoured only in its own layout (`_RECORDED`). `overrule_if_reheld_on` records. All six listed reasons match the brief verbatim (constants at the top of the backfill block).
  - `titles` subject is built from the BASE row's `title_sources` mapped onto today's `show.json` filenames (`_titles_rule`), never via `records_for` on today's show. A count mismatch gives `cannot derive the unresolved files`. Pinned by `test_titles_subject_from_base_title_sources` (f3 shows base positions winning over today's unresolved file). I checked the 8 real `unresolved track titles` rows read-only: all have equal track counts today and non-empty base positions.
  - `identifier` is `show.json`'s (`records_for` / `_titles_rule`).
  - Dry run prints per-show `record:` / `list:` lines and the five totals. Apply order: `require_pinned_code` -> `require_tools(pin)` -> `take` (targets only) -> `retire_rekey_restore(by="bulk-apply overrule backfill <stamp>")` -> per show under the lock: re-plan, legacy refusal, `read_overrides`, `merge_rules`, `write_artifact`, `record_after`, `record.jsonl`. The test asserts take-before-retire and that a re-run is byte-identical.
  - The Task 11 binding holds on the success path: `record_after` is the last write to a tracked file (`record.jsonl` lives in `campaign/backfill/<stamp>/`, outside the show dir). The test's restore dry run is not refused.
- ⚠️ Cannot verify from the diff: whether "records the flags it names" (brief) / "listed in `overrule_if_reheld_on`" (spec) means "only the base flags it names". The implementation reads it that way (Minor 1). This is an operator question, not something the diff can settle.

### Strengths
- The titles subject is built from base positions, exactly as the Task 1 review required, and the test that pins it would catch the `records_for`-on-today regression (the implementer mutation-checked it).
- The gates run before anything is read, and a gate refusal leaves the tree byte-identical (`test_apply_refuses_without_gates` covers all three refusals). The dry run is proven write-free over all of `tmp_path`, not just the library.
- Targets are filtered before `take`, so the snapshot holds only shows that will be written, and a fully applied re-run writes no snapshot or batch dir.
- The extra listed reasons are judged acceptable: `no show.json` and `show.json unreadable: …` are list-only, and their total prints only when non-zero. Two of the implementer's design calls are conservative and correct:
  - a flag ruled more than once records only when every ruling is the false-hold value (0 such conflicts in the real data);
  - a corrupt verdict aborts the plan with exit 2 rather than guessing.
- The real overrides are safe to rewrite through `Overrides`: 663 real `overrides.json` files, 0 keys the model would drop (read-only check).
- No "Untouched" item appears in the diff. Only `scripts/bulk_apply.py` and the new test file changed.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **A failed `record_after` leaves an `overrides.json` write that the batch's restore refuses, and a re-run hides it** (scripts/bulk_apply.py, `_backfill_one`, the `with file_lock(ws.lock):` block: `write_artifact(...)` then `batch_snapshot.record_after(...)`).
   - **What's wrong:** the unit has no rollback. `record_after` reads the station manifest and raises `_Unfit` on an `OSError` (batch_snapshot.py:160-173). An SMB mount drop mid-batch is the plan's own Review Focus 2. A Ctrl-C between the two calls fails the same way. Either one leaves the overrides write in place with no after-record.
   - **Reproduced** in a scratch test (`record_after` patched to raise `OSError`, the fixture otherwise as `_apply_fixture`):
     - the first `--apply` exits 1 and `g1/overrides.json` has been rewritten;
     - a second `--apply` prints `nothing to record: every planned overrule is already present` and exits **0**;
     - `batch_snapshot.restore` then returns `('g1', 'refused: changed, and this batch recorded no write for it')`.
   - **Why it matters:** this is a strict surface, and spec "Undo" requires each library write batch to be restorable. The show can only be recovered by hand from the snapshot, and the clean re-run tells the operator nothing is wrong. The handback's concern 4 says such a show is "left alone"; it is actually refused, and the re-run masks it.
   - **Fix:** run the unit inside `show_unit(ws, None)` instead of the bare `file_lock`, the same way reapply runs `after_commit` inside the unit (reapply.py:150-175, 381-382). `show_unit` takes the lock itself and restores every file outside `package/audio/` on any `BaseException`. The `.txn/` dir is excluded from `_metadata_files` (batch_snapshot.py:132-135), so `record_after` inside the unit records the right state. Add a test where `record_after` raises: assert `overrides.json` is byte-identical afterwards and a re-run then writes it.

#### Minor (Nice to Have)
1. **Verdict rulings on flags the base arm did not raise are neither recorded nor listed** (`_plan_one` iterates base flags only; `named` and `ruled` entries that are not base flags are dropped silently).
   - **Measured read-only:** 174 unique (slug, flag) pairs over 36 shows (122 `overrule_if_reheld_on` entries and 107 spurious/flag-spurious rulings, which overlap), e.g. `bandofheathens-2009-07-27`'s ~25 `research asserts unknown song:` flags. **None of the 174 is raised by `migration-post.json`.**
   - **Why it matters:** the spec says "every other case is listed for Shawn". The brief's "`overrule_if_reheld_on` … records the flags it names" can be read as covering flags beyond the base set, and that list exists precisely for flags that might re-appear on re-hold. A missed one fails safe (the show re-holds), so this is Minor.
   - **Fix:** raise it at Checkpoint A beside the rehold-verdicts question. Either print these per show as a separate `not raised by the base arm` section (not counted in `flags listed`), or record the `overrule_if_reheld_on` ones too.
2. **`_append_jsonl` duplicates `record_after`'s durable-append loop verbatim** (open/O_APPEND, the memoryview write loop, `_sync_fd`, `_sync_dir`; batch_snapshot.py:363-372). It also imports the private `llama.catalog._sync_fd` and calls `batch_snapshot._sync_dir`. Extract a public `append_jsonl_durable(path, row)` into batch_snapshot (or catalog) and use it in both places.
3. **The dry run prints `record: unresolved track titles` without its subject** (`_print_plan`). At the checkpoint Shawn cannot see which files a titles overrule will cover. For example, `stevekimockband-2002-04-20` and `godspeedyoublackemperor-2022-02-25` record every track. Append the subject for `titles` (or for every kind with a subject).
4. **`retire_rekey_restore`'s return value is ignored** (`cmd_backfill`). An absent or unreadable `rekey-applied.json` retires nothing, silently. This is harmless, because rekey `--restore` already refuses an unreadable record. A one-line note when it returns False would make the log self-explanatory.
5. **A single corrupt verdict file aborts the whole dry run with exit 2** (`_verdict`). That is right for `--apply`. For the checkpoint dry run, listing the show as `verdict unreadable: …` would let the rest print. Optional.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The planning logic, gates, ordering and tests match the brief, and the titles subject is built correctly. However, the per-show write has no rollback: a `record_after` failure leaves an `overrides.json` write that the batch's own restore refuses and that a re-run reports as clean. Wrapping the unit in `show_unit` fixes this.

Evidence: probe at /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/14e1d77c-a4c4-4f81-b326-ae4463a500c5/scratchpad/t14/test_probe_record_after_failure.py; output and the read-only measurements are in t14-review.log. The focused test file passes (9 passed, no warnings).
