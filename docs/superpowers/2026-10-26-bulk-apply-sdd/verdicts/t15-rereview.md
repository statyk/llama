### Finding Verdicts
- **I1: "no station copy" came from an error-swallowing `is_dir()`, counted as OK, and was terminal on a re-run.** ADDRESSED. Each part of the ruling is met:
  - **(1) The decision is stat-based.** `scripts/bulk_apply.py:720-731` `_station_copy_problem` calls `os.stat(out)`. `FileNotFoundError` returns `no station copy`. Any other `OSError` returns `refused: station copy unreadable (<_one_line>)`. A non-directory also returns refused. `_mark_one` uses it at `:761-762` in place of `out.is_dir()`. A refused line starts with `refused`, so the `done` filter in `mark_apply` (`:792-793`) drops it and a re-run retries the item.
  - **(2) The exit rule is the brief's, literally.** `_STATION_OK` is now `("marked", "already marked")` (diff lines 49-53). This matches brief line 27, "Exit 0 only when every delivered item is `marked` or `already marked`". `_mark_one`'s `problem` flag is `delivered and station not in _STATION_OK`.
  - **(3) The exit is computed over the whole record.** The post-loop pass (diff lines 182-185) walks `_last_lines(record)`, the last parseable line per slug. It lists every slug whose last station is neither OK nor `not delivered` and that this run has not already listed.
  - **Superseded lines cannot fail a batch.** `_last_lines` overwrites per slug in file order, so a `refused` line followed by `marked` reads as `marked`. The stat-error test exercises exactly this: one refused line, then a marked line, and the batch exits 0 (`test_bulk_apply_mark.py`, diff lines 316-319).
  - **The dry run uses the same decision.** `_station_state` (`:944-958`) calls `_station_copy_problem`. ENOENT goes to the `delivered no station copy` column. Any other error goes to `delivered unreadable` with the detail, which `_print_mark_plan` prints under "unreadable station manifests". `cmd_mark` gates `station_root.is_dir()` before both the dry run and `--apply` (`:999`), so the dry run cannot read an unmounted root as missing copies.
  - **The moved expectation is correct.** In `test_unmark_removes_library_only_marks`, the second `mark_apply` runs on the same batch dir, whose record still ends `bad` with `refused: …`. Under ruling 3 that must exit 1. The test's intent is still asserted: `earlier` gets `mark_added False` and `station == "marked"`, and the unmark assertions are unchanged.
  - **All three ruled tests are present.** They are the absent station dir (listed, exit 1, and a re-run still exits 1 with no new record line), EIO (refused, listed, bytes untouched, then a re-run marks it and exits 0), and the per-item station-root-unreadable refusal. The implementer's breakage table shows each fix element caught (f1-f3).

### New Breakage in the Fix Diff
- **Minor.** At `scripts/bulk_apply.py:756` (current file), `copy_problem = None` is a dead assignment: the walrus at `:761` always binds it before use. Cosmetic.
- **Minor (operator guidance, by ruling).** A recorded `no station copy` can never clear within its batch.
  - The outcome is terminal: it is in `done` and never revisited. Yet it is permanently listed, so that batch can never exit 0.
  - The listing header (`:808-809`) still tells the operator "do not run emcee on their profiles until a re-run of this batch exits 0". For this row that condition can never be met.
  - The batch id is a hash of the arm, frozen list and reselections bytes. Re-running with the same inputs therefore lands in the same record.
  - This is the behaviour rulings 2 and 3 asked for, and it is the safe direction. The runbook (or the listing line for a `(recorded)` `no station copy`) should still say what clears it, for example re-delivering, or accepting it by hand.
  - It is not blocking.
- **Minor (coverage).** No test exercises the dry run's stat-error branch in `_station_state` (`delivered unreadable` with a stat detail). That branch only affects the dry-run display.

### Out-of-Scope Observations
- `_mark_one`'s root check is still `station_root.is_dir()` (`:759`). That method swallows errors, but every outcome it can produce is `refused`, which is the safe direction, so it is fine.
- An item recorded `not delivered` is never revisited if the ledger later shows the show delivered. This predates the diff and is the brief's re-run rule. It is mentioned only for completeness.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. Open items are Minor only: the dead assignment, the operator guidance for a terminal `no station copy`, and the untested dry-run stat-error branch.
