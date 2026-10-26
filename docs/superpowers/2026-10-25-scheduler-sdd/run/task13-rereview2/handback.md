# Task 13 re-review, fix round 2 (task13-rereview2): dcd0a2a..ff7ba19

**Setup.** Scratch `git archive ff7ba19` copy, run from an empty cwd with `PYTHONDONTWRITEBYTECODE=1`, `-B`, `-p no:cacheprovider`. Before each run I proved that both `transmitter` and `tests_transmitter` import from that mutant's own copy.
- **Baseline:** 886 passed, 1 skipped, which matches the fix report.
- **Mutants:** 6. Each had its expected red test named first, and each ran test_cli, test_report, test_service and test_probe_estimates. All 6 went red exactly as predicted. I confirmed the failing line in each with `--tb=line`.
- **Live worktree:** untouched. HEAD is ff7ba19 and `git status` is clean.
- **Log:** task13-rereview2.log.

### Finding Verdicts
1. **Trim hid a late block inside the horizon — ADDRESSED.**
   - New rule: `nominal_us is None or nominal_us < until_us or any(show.start_us < until_us)`.
   - This is the union of the d7f2bcf rule and the dcd0a2a rule, so the trim now hides nothing that either earlier version showed.
   - The new test reproduces the probe: Block 10 airs 10:00–13:00, Block 12 is nominal 12:00 with a MISS at about 13:00, previewed at 10:30 with `days=0.1`.
   - **R1** (revert to the dcd0a2a rule): red on `test_schedule_keeps_a_late_block_whose_nominal_start_is_inside_the_horizon`, with StopIteration at the Block 12 header (line 684).
   - **M17** (no trim): still red on `test_schedule_trims_views_at_the_horizon` (line 592), and also on the new test.
   - **Mnom** (drop the show-start half, i.e. the d7f2bcf rule): red on `test_schedule_open_time_shows_no_slip`. Both halves of the union are pinned.
2. **`live` admitted `(None, None)` — ADDRESSED.**
   - `live` now requires `r.block is not None`.
   - **R2** (drop that clause): red on `test_schedule_does_not_pull_old_phase1_rows_into_the_unscheduled_view`, at the `not any("09-30" …)` assertion (line 704).
3. **M30 pinned — ADDRESSED.**
   - **M30a** (per-show `[fill: {s.fill}]`, the raw cause): red at line 687.
   - **M30b** (summary `fill` line printing the raw cause): red at line 688.
   - Both are on the new late-block test.
4. **Test cruft — ADDRESSED.**
   - The vacuous `… or True` assert is removed. It always evaluated true, so it carried no coverage by construction. `engine.analyzed == []` is still pinned by `test_schedule_writes_nothing` (line 378) and by the test at line 436.
   - The dead `if False else rows[0]` line is removed. It was an identity, so nothing changes.
   - The mid-file `noqa: E402` imports are folded into one import block. The dropped `E` and `history` names have no remaining references.

### New Breakage in the Fix Diff
None. Three cosmetic nits, none of which needs another round:
- The consolidated import block (test_cli.py lines 33–40) still sits after the first two tests. That position predates Task 13, so it is not a regression.
- `import json` (line 1) is unused. It has been unused since d7f2bcf; the fix moved it rather than deleting it.
- The comment in `test_schedule_trims_views_at_the_horizon` says "every shown block's first show starts inside the horizon". That is now stricter than the code's rule, which also keeps a block whose nominal start is inside. It holds on that test's fixture, so the test is green and M17 is still red.
- In the new phase-1 test, `l.startswith("(unscheduled)") or "(unscheduled)" in l` is redundant. It is harmless; the `09-30` assertion is the one that does the work.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
