# t17-review: Task 17 (ranked re-voice list + trial cost report), range c225ca33..cce3309e

### Spec Compliance
- ✅ Spec compliant on every brief interface item, with one Important correctness gap in how a trial block is bounded (below).
  - revoice-list (scripts/bulk_apply.py:1505-1595): it lists voiced shows (`voiced_by` non-null) awaiting fix per the library campaign record. The five components come from the arm row against `show.json`, paired by filename. The ranking key is lexicographic and descending, then slug. Cost comes from `tts_now.backend` with the four brief strings. `needs-llm` and `unreplayable` rows print last as `components unknown until re-processed`. Each row prints rank, slug, presenter, backend, cost and every component.
  - trial-report (:1598-1734): before = first `meter.before` and after = last `meter.after`. A reset produces the discard string. A small block gets a ±1/n bound. The 7d/5h ratio is Σd7/Σd5 over kept blocks. Shapes are kept apart above 0.25, and a profile outside every shape takes the max. Only `fresh` and `needs-llm` are projected, in weeks at the share, per profile and in total. The align_reproduced rate is printed.
- ⚠️ Cannot verify from the diff: behaviour against a real trial batch. None exists yet, and the tests hand-build `progress.jsonl`. The seams were checked against the real writers instead (below).

**Seam checks (one focused check each):**
- **Progress `meter` shape:** `cli._meter_row` (packages/llama/src/llama/cli.py:4182-4188) writes `{five_hour, five_hour_resets, seven_day, seven_day_resets}`. Both writers nest it as `meter.before`/`meter.after` and also write `llm_calls`: the failure path at :4323 and the applied path at :4440. The applied path adds `kind` and `align_reproduced`. The reader keys match. `read_progress` (reapply.py:435) keeps the last row per slug, as the report assumes. ✅
- **Batch `list.json` row `kind`:** cli.py:4251-4252 `shutil.copyfile`s the input list into the batch dir. Task 16's `lists` writes `rows[].kind` from `_row_kind` (bulk_apply.py:1277-1284, :1430), so `fresh`/`needs-llm` are the real values. ✅
- **`--counts` JSON:** bulk_apply.py:1403-1409 prints `{profile or "(none)": {kind: {"unvoiced", "voiced"}}}` to stdout, and its problems go to stderr, so a redirect gives clean JSON. This matches the reader. ✅
- **`emcee status --json`:** packages/emcee/src/emcee/cli.py:826-848. `slug` = station dir name. `voiced_by` is None when unvoiced, else `"?"`/`"house"`/an id (station.py:59, :84-96), so "non-null = voiced" is right. `tts_now` is `{backend, model}`, `{unresolved}` or null. `view()` (:817-823) gives an `awaiting-fix`-state package a real `tts_now`; only `error`/`unsupported` get null. ✅ No emcee import is added.

**The implementer's flagged interpretations:**
1. (max − min)/max > 0.25 as the material difference: **accepted.** "Differ materially" is left to the builder, and max as denominator is the less trigger-happy choice. The denominator is unpinned, though (mutant m3 below), and the constant's comment does not name it. Minor.
2. Reset check over every row: **accepted.** A crossed reset always moves `resets_at` forward, so first-vs-last would be enough; checking all rows is harmless except for None readings. Minor M2.
3. A block under `MIN_BLOCK_POINTS` still counts toward the projection and the ratio, flagged ±1/n: **accepted.** This matches "a block whose pool runs dry first reports its error bound". The spec discards only reset-crossing blocks.
4. An unmapped profile is its own shape, and a profile outside every shape (incl. `(none)`) takes the highest measured cost: **accepted.** It is exactly the brief.
5. needs-LLM re-voice rows continue the rank numbering: **accepted.** Including `unreplayable` (via `_NO_DIFF`) is a sensible extension.
6. A voiced show missing from the arm is skipped with a stderr note: **accepted.** It is reported, not silent.

### Strengths
- The seams are right first time. The meter keys, the `list.json` kind, the `--counts` shape and `tts_now` all match the real producers, and emcee is read as a file, never imported.
- Each report reads from one place: `_components` is pure over (row, Show), and `_measure_block` is pure over rows.
- The tests are concrete numeric fixtures: brief numbers 0.5 / 0.2 / 0.1, a projection with zero-cost kinds, and both kept-apart and pooled shapes. The ranking test exercises every tie-break level including slug.
- Sorting rows by `at` and taking the last row per slug is consistent with how reapply resumes.
- Diff hygiene: only `scripts/bulk_apply.py` and the new test file change. None of the "Untouched" items appear (no junk constants, `DURATION_TOLERANCE_S`, audio_reuse pairing, purge verification, `STOP_AFTER_LLM_FAILURES`, `load_list` gate or `briefing_reusable`).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **A block's meter delta silently includes other kinds' spend, and the kind filter is untested.** scripts/bulk_apply.py:1605-1616 (`_block_rows`) and :1622-1636 (`_measure_block`).
   - **What's wrong:** `_block_rows` drops rows of other kinds, then `_measure_block` takes `rows[0].meter.before` → `rows[-1].meter.after`. Any spending row of another kind that falls between them still moves the meter, but it is not counted in `n`.
   - **When it happens:** a wave list run with `--with-gather-llm`, because there `fresh` and `needs-llm` rows both spend and interleave in slug order. If the same batch is passed as both `dead-fresh=D` and `dead-needs-llm=D`, each block absorbs the other's spend: double counting.
   - **Why it matters:** the orchestrator's own decision ("a block counts only rows of the block's kind that spent") implies mixed batches are expected input. The resulting per-show cost feeds the weekly-ceiling projection with no warning. The spec requires "one contiguous block per kind of work", and the tool should enforce that, not assume it.
   - **The test gap:** `test_non_spending_and_other_kind_rows_are_not_counted` (scripts/test_bulk_apply_reports.py:221-234) says in its comment (:227) "a row in the list of another kind that did spend must not count either". Its extra row has `llm_calls: 0`, so the spend filter alone excludes it.
   - **Measured:** mutant m1 removes `kinds.get(s) == kind and` at :1612. All 12 tests still pass. The kind filter is unpinned.
   - **Fix:**
     - Refuse the block (or print `not contiguous: N spending row(s) of another kind inside it` and skip it) when any row with `llm_calls > 0` and a different list kind has an `at` between the block's first and last rows.
     - Give the test's extra row `llm_calls > 0`, place it inside the window, and assert the refusal.
     - Add a row of another kind that spent outside the window, and assert it is not counted.

#### Minor (Nice to Have)
1. **A missing reset time reads as a crossed reset.** bulk_apply.py:1628-1631. A failed meter read on any row (`_meter_row(None)` → `five_hour_resets: None`), or an unparseable reset, puts None in the set, so the block is reported as `discarded: crossed a 5-hour reset; re-run`. Fix: build the set from non-None values, and report missing readings as "no usable measurement". Optionally fall back to the nearest row whose reading is usable for the first and last values.
2. **The material-difference denominator is unpinned.** bulk_apply.py:1690. Mutant m3 changes `/ hi` to `/ lo` and all 12 tests pass (0.5 vs 1.0 is apart either way; 0.5 vs 0.6 pools either way). Fix: name the denominator in the comment at :1497, and add a pair that separates the two rules. For example 0.5 vs 0.65: 0.23 against max pools, 0.30 against min keeps them apart.
3. **The `MIN_BLOCK_POINTS` boundary is unpinned.** `test_small_block_reports_its_bound` catches a changed constant only through the message text (mutant m2, `= 50`, failed on the string). No test has a block of exactly 5 points asserting no bound, so `<` → `<=` would survive. Fix: assert `"error bound" not in out` for a d5 == 5 block.
4. **An unreadable campaign record drops the show from the re-voice list.** bulk_apply.py:1550-1554. It goes to stderr only. Review Focus 5's rule is that nothing treats an unreadable record as "no record". A stderr line keeps it visible, but listing the show in the trailing unknown group (`campaign.json unreadable`) would keep it on the ranked list Shawn works from.
5. **The presenter and the cost can describe different voices.** bulk_apply.py:1561. The presenter column is the recorded `voiced_by`, while the cost is the current assignment's `tts_now` backend. After a reassignment, or with a legacy `?`, the row names one voice and prices another. Consider adding `assigned_presenter` from the same status row (e.g. `presenter phil (now: kurt)`).
6. **Queue kinds outside the known five are dropped silently.** bulk_apply.py:1710-1711. Any kind not in `MEASURED_KINDS` is skipped as costing 0, including an unexpected kind (`_row_kind` falls back to `str(row.get("briefing"))`, e.g. `"None"`). Print a note for kinds outside {reuse, label-only, held}. Also, a non-dict cell raises a traceback, not a GateRefused (low risk, since it is the tool's own output).
7. **align_reproduced re-reads every block.** bulk_apply.py:1725-1731. It re-parses and re-reads each block, including discarded or unusable ones, and a batch passed twice is counted twice. Counting discarded blocks is defensible, since reproduction is not a cost measure, but say so. Reusing the rows already read would avoid the second read.
8. **revoice-list does not check the arm's `sha`/`config_fingerprint`** against the pin, as `lists` does (:1376-1382). A stale arm silently ranks by a stale diff. It is read-only, so low stakes.

### Mutation evidence
Scratch copies under /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/6d6081a6-72bc-4b0b-afbd-ff5351b19e6a/scratchpad/t17/m{1,2,3}. Each was made by `git archive HEAD scripts` and run with the worktree venv's `python -m pytest`, with no bytecode cache, from the copy's cwd. `bulk_apply.__file__` was confirmed to resolve inside each copy.

| Mutant | Change | Result |
|---|---|---|
| m1 | kind filter removed | 12 passed: **survived** |
| m2 | `MIN_BLOCK_POINTS = 50` | 1 failed: caught, by the message string |
| m3 | `/ hi` → `/ lo` | 12 passed: **survived** |

### Assessment
**Task quality:** Needs fixes
**Reasoning:** Both reports match the brief, and every input seam matches its real producer. However, a trial block silently absorbs spend from interleaved rows of another kind, which corrupts the per-show figure that sets the weekly ceiling. The kind filter that is meant to guard this has no test; mutant m1 survives.
