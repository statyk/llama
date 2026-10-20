### Finding Verdicts

1. **99% boundary untested (mutant `< 1.0` survived)**: ADDRESSED. The gate is now in integer arithmetic, `ok * 100 < 99 * len(denom)`, at scripts/replay_holds.py:544. `test_compare_gate_boundary_is_99_percent` (scripts/test_replay_holds.py, parametrized `(99, 0), (98, 3)`) runs a synthetic 100-row held arm. The 98 case asserts `98/100` in stderr. The `< 1.0` mutant (99/100 then returns 3) fails the `[99-0]` case. The implementer's mutant table reports the 99→100 mutant caught by that case.
2. **Pilot swap never exercised (`while False:` survived)**: ADDRESSED. `test_pilot_list_swaps_in_reuse_rows` now builds rows from a list already sorted by `_skey`, with reuse only at positions 10–13. It asserts the exact set `ordered[:8] | ordered[10:12]`. I traced `_pilot` (replay_holds.py:512-520): idx 9 gets ordered[10] and idx 8 gets ordered[11], which matches the assertion. Under `while False:` the result is `ordered[:10]`, so the mutant is caught. The test calls `_pilot` directly with a pre-ordered list, which is the alternative the finding allowed. `compare` passes `predicted` already in `_skey` order (replay_holds.py:563-567).
3. **`structure_changed_list.json` content untested**: ADDRESSED. `test_structure_changed_and_needs_llm_rows_reach_the_right_lists` covers it:
   - It sets a cand row to `outcome="structure-changed"`, `would_be="needs-brief"` and asserts `[(slug, outcome)] == [("sc", "needs-brief")]`. A mutant writing `r["outcome"]` would produce "structure-changed" and fail.
   - It asserts predicted_list and pilot_list rows are `[]`, so the sc and nl rows are absent from both.
   - It asserts the needs-llm row `nl` is absent from structure_changed_list.
4. **Stale `--out` outputs after exit 3**: ADDRESSED.
   - `OUTPUT_FILES` (replay_holds.py:177-181) lists every file `compare` writes. I checked it against each `_write` and `write_text` call at lines 536-576. It also lists Task 7's `narration_candidates.html` ahead of time, which is correct per plan line 107.
   - The files are unlinked one by one with `missing_ok=True` after `_gates` and before drift.txt (replay_holds.py:532-533). There is no rmtree.
   - `test_compare_clears_stale_outputs_before_a_failing_gate` runs a successful compare and then an exit-3 compare into the same directory. It asserts predicted/pilot/structure_changed lists and summary.txt are gone, the fresh drift.txt names the failing show, and a foreign `keep.txt` survives.
   - Exit 2 writes and removes nothing, because `_load_arm` and `_gates` run before `mkdir` and the unlink loop. The existing exit-2 tests assert `not out.exists()` (test_replay_holds.py:353, 363, 376).

### New Breakage in the Fix Diff

- Minor: no test pins "exit 2 removes nothing" against a directory that already has outputs. The existing exit-2 tests use a fresh `--out`. A mutant that moved the unlink loop above `_gates` would survive. Today's code ordering is correct (replay_holds.py:528-533).
- Minor: `OUTPUT_FILES` is a hand-kept list. A later task that adds an output file but not the name will leave that file stale after exit 3, and nothing will catch it. The test checks only four names. A test could assert that every file a successful compare writes is in `OUTPUT_FILES`.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. There are two Minor notes above; neither blocks.

Check run: read-only trace of `_pilot` and `compare` against the new tests. I ran no tests and made no mutants. I relied on the implementer's mutant table (scratch copy, PYTHONPATH shadowing proven), which is consistent with my trace.
