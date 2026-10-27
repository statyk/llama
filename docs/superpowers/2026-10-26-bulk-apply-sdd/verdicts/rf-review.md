# Task RF review (rf-review), commits 547b5cb7 (RF1) and a82b0755 (RF2)

### Spec Compliance
- ✅ Spec compliant, for both fixes.
  - **RF1:** `_all_progress_rows` (scripts/bulk_apply.py:1756-1770) reads every parseable line and skips unparseable ones. `reapply.read_progress` is unchanged. `_foreign_inside` (bulk_apply.py:1773-1787) still takes its window from `_spending_rows`, which uses the last row per slug. It counts every line where: the slug's list kind differs from the block's, `llm_calls > 0`, and `lo <= at <= hi`. `_block_rows` and `_measure_block` are untouched, so `n` and the measurement are as before.
  - **RF2:** one helper, `_station_root_problem` (bulk_apply.py:899-913), serves all four sites:
    - `cmd_mark` gate (1263-1267)
    - `cmd_lists` gate (1497-1502)
    - `cmd_wave_check` gate (1566-1571)
    - `_mark_one` per-item check (964-967)

    The helper requires `is_dir` plus `os.access(R_OK)`, then scans until the first entry whose name does not start with `.`; it never lists the whole directory. Each site keeps its existing "not mounted / not a (readable) directory" wording. The empty case uses the exact string `station root <p> is empty (is the station mounted?)`. The per-item outcomes are `refused: …`, which falls under `_RETRIED` (bulk_apply.py:528), so the item is retried and never recorded as `no station copy`. `no delivery_path in config` is unchanged.
  - All six required tests are present with the brief's names. The existing-test change is only a placeholder dir in `test_kind_held_from_briefing_none`; no assertion was weakened.
- ⚠️ **RED in the live tree (process requirement): not met as specified.**
  - RF2: the implementer says it was shown RED "in a scratch copy". The log has the 4 FAILED lines, with no path showing which tree they ran in.
  - RF1: the report says "RED before the fix", but `rf-impl.log` has no RF1 RED output and does not say which tree.

  My mutants below reproduce every RED independently, so the tests are proven. This is a process deviation, not a defect in the tests.
- Strict surface:
  - Review Focus 1 is untouched: no hunk touches `_mark_station` or the `station_mark` write path. My grep of the diff for the station_mark/write_mark identifiers found nothing.
  - The new check runs before `_station_copy_problem` and only adds `refused:` outcomes, so it cannot turn a refused item into a recorded `no station copy`. A narrow pre-existing race remains; see Minor 1.
- Untouched-list grep over the diff: no hit for any listed constant or function. The one hit was a `reapply.read_progress` mention in a docstring.

### Mutation check (scratch copy `git archive a82b0755 scripts pytest.ini`, run with the worktree venv's `python -m pytest`, bytecode isolated per mutant)
Scratch dir: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/37b18383-1197-4fee-a2e8-e8a01895d11b/scratchpad/rfmut

- **Setup checks:** the unmutated copy passed (79 passed). The import sentinel (a `SystemExit` at module level) stopped collection, which proves the copy's `bulk_apply` is the one tested.

| Mutant | Predicted red | Result |
|---|---|---|
| M1: revert `_foreign_inside` to last-row-only | hidden-retry test | CAUGHT, only that test |
| M2: `lo <` | inclusive[first] | CAUGHT |
| M3: `< hi` | inclusive[last] | CAUGHT |
| M4: drop `llm_calls > 0` filter in `_foreign_inside` | existing `test_non_spending_and_other_kind_rows_are_not_counted` | CAUGHT |
| M5: dot entries count as entries | lists-empty + mark-empty (dot-only cases) | CAUGHT, both |
| M6: `_mark_one` reverted to `is_dir()` only | mid-batch test | CAUGHT |
| M7: wave-check gate without empty branch | wave-check-empty | CAUGHT |
| M8: mark gate without empty branch | mark-empty | CAUGHT |
| M9: lists gate without empty branch | lists-empty | CAUGHT |
| M10: per-item empty case worded as "not readable" | mid-batch (exact string) | CAUGHT |
| M11: drop `os.access(R_OK)` from the helper | (none expected) | SURVIVED (see Minor 4) |

Every new test catches the defect it was written for.

### Strengths
- One small helper, used at all four sites, that stops at the first visible entry. Wording at each site is preserved, and a scandir `OSError` maps to "unreadable" rather than "empty".
- RF1 leaves `reapply.read_progress` and the block measurement alone. It widens only the foreign-spend count, as the brief scoped.
- Tests assert the exact strings. They cover the dot-only case, the `--counts` path, both dry run and `--apply`, and "nothing written". The inclusive-boundary test is parametrized over both ends, which closes the surviving mutant from the earlier review.
- The existing-fixture change was disclosed, and it gives the station a real entry rather than weakening the check.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. **Pre-existing race between the root check and the copy stat** (bulk_apply.py:964-969).
   - If the share unmounts between `_station_root_problem` and `_station_copy_problem(out)`, `os.stat` gets ENOENT. The item is then recorded `no station copy`, which is terminal: it is not in `_RETRIED`, so a re-run will not retry it. It is still listed, and exit is 1.
   - The window is microseconds and predates this task; this task made it smaller.
   - Fix: when `_station_copy_problem` returns `no station copy`, re-run `_station_root_problem` and refuse if it is non-None.
2. **`_foreign_inside` re-reads `list.json` and rebuilds the same `kinds` map as `_spending_rows`** (bulk_apply.py:1782-1783 vs 1742-1745).
   - The second read skips the shape validation and relies on `_spending_rows` having raised first.
   - Fix: have `_spending_rows` (or a small `_list_kinds(batch)`) return the map, and use it in both places.
3. **Test helper duplication** (scripts/test_bulk_apply_reports.py `_append_line`): it copies `_add_row`'s row-writing body. Fix: add a flag to `_add_row` that skips the `list.json` append.
4. **The `os.access(R_OK)` leg of the helper is unpinned** (M11 survived). No test exercises a non-readable directory, and that branch is newly applied at the `lists`, `mark` and `_mark_one` sites. Pinning it needs a chmod-000 dir or an `os.access` monkeypatch.
5. **Fragile mid-batch test** (scripts/test_bulk_apply_mark.py, `test_mark_item_refused_when_the_station_empties_mid_batch`). The stubbed `campaign._now` calls `shutil.rmtree(station / "d1")` on every call. A second `_now` call inside `_mark_one` would raise FileNotFoundError instead of testing the behaviour. Fix: guard with a once-flag or `ignore_errors=True`.
6. **Commit-message test counts are inaccurate.** 547b5cb7 says "6345 passed"; the log shows 6346, and the implementer disclosed this. That message also omits the "1 skipped, 8 deselected" that a82b0755 includes.
7. **Pre-existing suite warnings.** The full-suite runs show 26 warnings both at baseline and after, so none were introduced here. They are noted per the rubric as pre-existing.

### Assessment
**Task quality:** Approved
**Reasoning:** Both fixes match the brief exactly, and every new test is mutation-proven to catch its defect. The strict `mark` surface is unchanged except for added retryable refusals. What remains is minor: a pre-existing race, small duplication, and RED having been shown in a scratch copy rather than the live tree (RF2) or not evidenced at all (RF1).
