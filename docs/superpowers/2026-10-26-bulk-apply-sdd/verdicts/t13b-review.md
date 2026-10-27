### Spec Compliance
- ✅ Spec compliant on both clauses' behaviour, with one gap in the brief's stated purpose (see Important 1):
  - Clause 1: `n` now counts the shows during which an LLM provider was invoked, committed or failed (cli.py `trial()` and `block[1] += spent`; `spent = llm_calls() > calls_before` at all four `fail(...)` arms and the success path). It reuses pacing's own detector `pipeline.count_llm_calls` (the same call `_execute` makes at cli.py:422 and checks at cli.py:650), not a second one. Failed rows now carry `meter {before, after}`.
  - Clause 2: on a non-dry run with an existing `snapshot/`, `batch_snapshot.verify(snap)` runs before `set_capture_dir`, `batch.mkdir`, the `list.json` copy, `retire_rekey_restore`, the provider build and the first show. Any problem refuses with exit 1 and the brief's line verbatim, using `problems[0]` as the detail. A fresh batch (no `snapshot/`) and the warning path for progress-without-snapshot are untouched.
- ⚠️ Cannot verify from diff: the RED evidence. The implementer wrote the code first and then reverted cli.py to show RED (n=5 instead of 3; the snapshot case failed after package). That is equivalent evidence but not the order the brief asked for, and there is no captured output to look at. I did not see the full-suite numbers (6263 passed, 1 skipped, 8 deselected) myself.

### Strengths
- **Ladder counting is correct (named risk from Task 10).** `_CountedProviders.__getitem__` (pipeline.py ~62-70) wraps each rung of a list/tuple ladder in its own `_CountedProvider`, and all rungs share one counter. The nested `count_llm_calls({"align": ...})` in reapply.py:235 wraps an already-counted rung, so both counters go up and the outer count stays right. Both new tests feed the list form (`{"brief": [FakeProvider([])]}`).
- **Risk (a), which provider answers and escalation: no change.** `_CountedProvider` only increments a counter before delegating `complete`/`research`, and `__getattr__` forwards everything else. The ladder order and length are kept, so escalation sees the same rungs. This is the wrapper the `get` path already runs in production. I grepped reapply.py, replay.py, brief.py and package.py for any other way to build a provider (`make_providers`/`provider_for`/`get_provider`) and found none, so no LLM call escapes the count.
- **Risk (b), snapshot gate: placement is right.** It sits inside `if not dry_run:` and under `if snap.exists():` (cli.py ~4237-4246), before anything is written. `verify` is a full hash check of the snapshot's metadata copies. Snapshot files are never rewritten after `take`, and `record_after`/`seal` only append to `after.jsonl`, which `verify` does not read. So a healthy batch in mid-wave keeps verifying, and a resume is never refused falsely. One side benefit: a `snapshot/` that a killed `take` left behind without its manifest is now refused instead of rolling every show back.
- **Risk (c), the extra meter read on the failure path: safe.** `herder.usage.read_usage` (usage.py:107-129) catches every failure and returns None, so a meter read inside `fail()`'s `except` arm cannot abort the batch. It costs a zero-token subprocess per failed row, and none on the fake backend or with `--no-pacing` (`_meter_applies`).
- The success-path trial block was moved into one `trial()` helper and is not duplicated in `fail()`. The block now ends after the row's progress record on both paths.
- Untouched list: the diff does not modify `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES` (only referenced), the junk constants, `load_list`, or `briefing_reusable`.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The progress file still cannot reproduce `n`.** cli.py `fail()` (~4312-4323) and the success `record_progress` (~4430-4434) record `meter`, but no row records whether the show spent. The brief says failed rows get the meter record "so the progress file can reproduce the count". That needs a spend marker as well:
   - On a failed row there is nothing that separates a spending failure (a brief paid for, then a download fails) from a zero-spend one. For example, `StationUnreadable` from `check_pairs` is raised "before any call" (reapply.py:228), and that is exactly Review Focus 2's mount-drop case.
   - On a success row, `kind` only approximates spend.

   This matters for the trial's evidence. A block that crossed a reset, or a printed line that was lost, can only be recomputed from `progress.jsonl`, and today that recount would be wrong whenever the block holds a failed row.

   Fix (one line on each path): add `"llm_calls": llm_calls() - calls_before` (or `"spent": bool`) to `extra` in both `fail()` and the success `record_progress`. Then assert it in `test_trial_count_excludes_shows_that_spent_nothing` on the failed row and on one skip row.

#### Minor (Nice to Have)
1. **A failed row that did not spend is untested** (test_reapply.py, `test_trial_count_excludes_shows_that_spent_nothing`). The only failing row in the plan (`slugs[2]`) spends. A mutant passing `spent=True` unconditionally in `fail()` would survive, even though zero-spend failures (unreadable station copies, a corrupt show.json) are the common kind. I found this by reading the code; I did not run the mutant. Fix: add one row that fails without spending (e.g. `(False, IAError(...))`) and keep the expected `n` at 3.
2. **The same trial test does not assert the exit code or that `slugs[5]` was never processed**, so the block ending early is only implied by the output text. Add `r.exit_code == 1` (a row failed) and a check that `slugs[5]` has no progress row.
3. **`_spend` swallows `AssertionError`** (test_reapply.py helper). It depends on `FakeProvider` raising `AssertionError` on an empty queue. In `test_stop_at_points_ends_the_block` it wraps the real `reapply_show`. If that fake ever has responses queued, `_spend` would consume one the real brief needs, without any sign. A dedicated counting stub, or asserting the queue is empty first, would remove that coupling.
4. **The refusal names only the first problem.** cli.py ~4243 uses `problems[0]`. The brief's single-line format allows this. If there are several problems, a count (e.g. `(… and 3 more)`) would tell the operator whether the snapshot is a little damaged or badly damaged before they choose between removing and restoring. Cosmetic.
5. **`block[1] += spent` adds a bool to an int** (cli.py `trial()`). It is correct, but `int(spent)` reads more plainly.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** Both behaviours are right. The ladder-aware counting reuses pacing's detector, and the snapshot gate refuses before any write or spend without affecting fresh or warning-path batches. But the brief's stated reason for adding `meter` to failed rows is that the progress file can reproduce the trial count, and it cannot until each row records whether it spent. That is a one-line fix per path, plus a test for a failed row that did not spend.
