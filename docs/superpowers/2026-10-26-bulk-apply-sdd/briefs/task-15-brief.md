### Task 15: Marking, its inputs and its reversal (CHECKPOINT B after it)

**Spec:** "The `awaiting_fix` contract" (Who gets marked, Writing a mark, The marking batch, No concurrent emcee), "The library side" (Marking skips), "Re-processing" (GD re-selections). Strict surfaces 1, 4. **Implementer: Opus.**

**Files:** Modify `scripts/bulk_apply.py` (`freeze`, `reselect-check`, `mark`, `unmark`); Test `scripts/test_bulk_apply_mark.py` (new; fixture library + fixture station + a hand-built arm).

**Interfaces:**
- Consumes: Tasks 3, 5, 12; `replay.row_visible_changes`, `row_label_only`.
- Produces (script functions, each tested):

```python
def freeze(root: Path, arm: dict) -> Path            # <root>/campaign/needs-llm-frozen.json; refuses an existing file
def reselect_rows(root: Path, config, source: list[dict]) -> list[dict]
    # per source row: stored identifier (show.json), pick = run_select_recording into a scratch
    # ShowWorkspace under a tempfile.TemporaryDirectory (never under the library) with
    # CacheOnlyIA, force=True, config.selection, the assessment built as _redo_show_locked
    # builds it; voiced = destination_voiced(...) for a delivered show, False otherwise; returns
    # [{slug, stored, pick}] for rows not voiced and pick != stored
def mark_plan(root: Path, arm: dict, frozen: set[str], reselections: list[dict],
              delivered: set[str]) -> list[MarkItem]
    # MarkItem(slug, reason, start_stage, digests | None)
def mark_apply(root, items, *, station_root: Path, batch: Path, echo) -> int   # exit code
def unmark(root, batch: Path, *, station_root: Path, apply: bool, echo) -> int
```
- `mark_plan` rule, per arm row: reasons in priority order: re-selection (from the re-checked list, start `select`, whatever the arm says), visible change, on the frozen list and not processed, `outcome` not `needs-llm` and `stored_brief_guard` non-empty. A row whose outcome is `needs-llm` or `unreplayable` never gets the visible-change reason (its diff comes from the provider-less fallback alignment, an artefact): it is marked only by re-selection or by the frozen-list rule (not processed); an `unreplayable` row left unmarked is listed. For other rows, a show whose record is processed (not awaiting) is skipped unless `row_visible_changes` is non-empty; label-only rows are never marked. Every state gets a record; only delivered shows get a station mark.
- `freeze`, `reselect-check` and `mark` take `--campaign-dir DIR` (default `<root>/campaign`); Checkpoint B points it at a scratch directory.
- `mark` CLI: `mark --arm <arm.json> [--apply]`; the arm's `sha` must equal `code_identity()` and its fingerprint the running config's; the frozen list and `reselections.json` must exist, and `reselections.json`'s `written_at` must not be older than the arm's `generated_at` (else exit 2 with the fixed string naming `reselect-check --write`). Dry run prints counts by reason × (delivered unvoiced, delivered voiced, packaged, briefed, held), the voiced slugs, unreadable station manifests, and whether emcee is running. `--apply`: gates; `retire_rekey_restore(by="bulk-apply marking <batch id>")` (idempotent, Task 12); `<root>/campaign/station-backup/` taken (every top-level non-dot station dir's `manifest.json`, sha-verified, `index.json` last) when absent; batch dir `marking/<sha256(arm bytes + frozen bytes + reselections bytes)[:16]>/`; per item under the show lock: digests re-checked (`skipped: inputs changed`), `add_mark` (durable) unless the record is already awaiting, then for a delivered show with a station copy: `emcee_running()` non-empty stops the batch (every remaining item listed as not marked), an already-marked station copy records `already marked`, else `before/<slug>.json` saved and `write_mark`; one `record.jsonl` line per item `{slug, reason, start_stage, mark_added: bool, station: "marked"|"already marked"|"no station copy"|"not delivered"|"refused: <why>", before_sha256, after_sha256, at}` (`mark_added`: this batch's `add_mark` wrote a library mark). A re-run of the same batch skips items already recorded with a non-refused `station`. Exit 0 only when every delivered item is `marked` or `already marked`; 1 listing every delivered item that was not (`skipped: inputs changed`, `refused: …`, or left unmarked by an emcee stop), since the runbook's emcee rule depends on it; 2 on a gate.
- `unmark --batch <dir> [--apply]`: per record line with `mark_added` (whatever its `station`): the record processed since that mark → listed `processed since marked: re-deliver instead`, nothing changed; else, for a `marked` line only, station sha ≠ `after_sha256` → listed `station copy changed since marking`, nothing changed, otherwise `put_back(before)`; then `remove_marks(ws, batch_id)`. Station bytes are restored only for `marked` lines.
- [ ] **Step 1: Write the failing tests:** `test_plan_marks_visible_changes_frozen_guard_and_reselections` (a same-count file swap is marked; a label-only row is not; a processed show is skipped unless visibly changed); `test_apply_writes_record_before_station`; `test_rerun_skips_marked_items`; `test_unreadable_station_manifest_is_refused_and_listed_exit_1`; `test_emcee_running_stops_the_batch`; `test_station_backup_taken_once`; `test_inputs_changed_row_skipped` (a delivered inputs-changed row → exit 1 listing it; a packaged one → exit 0); `test_mark_plan_skips_processed_needs_llm_row_with_diff` (processed show, `needs-llm` row with set changes → not marked); `test_mark_plan_ignores_needs_llm_diff_off_frozen_list` (unprocessed, not on the frozen list, `needs-llm` row with a diff → not marked); `test_mark_refuses_reselections_older_than_the_arm` (exit 2, the fixed string); `test_mark_apply_retires_the_rekey_restore`; `test_reselect_rows_write_nothing_under_the_library` (the library tree's file list and mtimes unchanged); `test_reselect_rows_drop_voiced_and_already_reselected`; `test_unmark_restores_bytes_and_removes_the_batch_mark`; `test_unmark_removes_library_only_marks` (a packaged show's and a `refused` station's batch marks are removed, their station bytes untouched; a line with `mark_added: false` keeps the earlier mark); `test_unmark_refuses_a_manifest_changed_since_marking`; `test_unmark_lists_processed_shows`; `test_freeze_refuses_to_overwrite`.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(bulk): marking batch, frozen needs-LLM list, re-selection check, reversal`.

### CHECKPOINT B (orchestrator; stop and report to Shawn)

Read-only, from the worktree at a clean HEAD: `./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/bulk/checkpoint-arm.json` (no pin exists yet; `arm` needs one), then, all with `--campaign-dir ~/.llama-harness/bulk/campaign`: `bulk_apply.py freeze --arm ~/.llama-harness/bulk/checkpoint-arm.json`, `bulk_apply.py reselect-check --source ~/.llama-harness/piece4/fw1/m3_changed-r1.json --write`, and the `mark --arm ~/.llama-harness/bulk/checkpoint-arm.json` dry run. Nothing is written under `~/.llama`. Report: counts by reason × state (the backfill has not run, so newly held is near the table's 220, not 29), voiced count and slugs, unreadable station manifests, the re-selection list (expected 17; the three voiced shows absent). Shawn confirms the rule before Task 16.

---

