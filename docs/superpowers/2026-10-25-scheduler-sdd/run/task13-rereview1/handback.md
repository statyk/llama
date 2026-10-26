# Task 13 re-review, fix round 1 (task13-rereview1): d7f2bcf..dcd0a2a

**Setup.** I made scratch `git archive` copies of dcd0a2a and of d7f2bcf, ran them from an empty cwd with `PYTHONDONTWRITEBYTECODE=1`, `-B` and `-p no:cacheprovider`, and proved the imports resolve inside each copy. This was checked again for every mutant.
- **Baseline at dcd0a2a:** 884 passed, 1 skipped.
- **Python 3.11:** `report.py` and `service.py` parse under a real 3.11.
- **Mutants:** 19 run. Each had its expected red test named first, and each ran against test_cli, test_report, test_service and test_probe_estimates.
- **Probes:** three, each run on both the old and the new code.
- The live worktree was untouched: HEAD is still dcd0a2a and `git status` is clean.
- Everything is logged in task13-rereview1.log.

### Finding Verdicts
1. **(Important) `schedule` mis-reported the block on air — ADDRESSED.**
   - `live = {(block, nominal) of base rows ending after now}` keeps every row of an occurrence that is still airing.
   - `block_views` takes start, slip, miss and bends from all of those rows. `since_frame` drops ended shows from the per-show listing only.
   - `test_schedule_inside_a_blocks_second_show_…` asserts the slip (-4 min, with a tolerance of ±1), MISS, `bent: gap`, that the aired Block 6 is absent, and that only the show on air is listed.
   - Red as predicted:
     - R1 (the old `shown = end_frame > now` filter)
     - M18 (`shown = list(base)`)
     - M22 (`since_frame=None`)
     - M31 (`start_frame >= since_frame`, which drops the show on air)
   - The weekday string in the "Block 6 absent" assertion is real: M18 goes red on it, so the assertion is not vacuous.
2. **(Important) Unpinned guarantees and surviving mutants — ADDRESSED.** Each previously surviving mutant is now red on the predicted test:
   - M4 (`live_clock(save=True)` in status): red on `test_status_writes_nothing_even_with_a_differing_last_good_clock`.
   - M7 (`miss is not None`), M8 (fill over all rows), M12 (`recent = whole plan`) and M15 (`next` may name the current block): red on `test_status_numbers_over_hand_written_rows`. Its exact lines are hand-checked against rows at −30/−10/−9.5/−1/−0.1/+0.5/+2/+30 h.
   - M17 (no trim): red on `test_schedule_trims_views_at_the_horizon`.
   - M18: red on the second-show test.
   - M19 (`rows = []`), M20 (`start = end`, `run_start = True`) and M21 (empty history): red on `test_schedule_after_a_plan_continues_it_and_writes_nothing`. M19 is also red on the second-show test.
   - The new schedule snapshot covers `plan.jsonl` (written by `plan_step`), `aired.jsonl`, `cache/` and a differing last-good file.
3. **(Minor) Stale "block now" — ADDRESSED.**
   - `cur` becomes None when the last show of its occurrence has ended. The line then reads `none now; next X`, or `next not planned yet`.
   - This also covers a boundary interstitial.
   - M24 is red on `test_status_block_is_none_between_blocks_and_after_the_plan`.
4. **(Minor) Dead condition — ADDRESSED.** It is removed.
5. **(Minor) Library reasons grouped regardless of leading counts — ADDRESSED.**
   - `reason_key` strips `^\d+( of \d+)? `. M25 is red on `test_profile_stats_and_reason_key`.
   - I checked every reason string in `station.py`. Only the two count forms start with a digit, and "changed Ns ago" is handled before the strip.
6. **(Minor) Fill-cause labels — ADDRESSED.**
   - "pool short" and "longer than max_shows" are now used in the status lines, the schedule per-show `[fill: …]` and the schedule summary.
   - M29 (the status label) is red.
   - M30, which reverts the per-show `[fill: …]` label in `schedule`, survives. That label is unpinned; see Out-of-Scope.
7. **(Minor) No slip for open blocks — ADDRESSED.**
   - "Open" means a clock block with no profiles. `schedule_lines` now prints `starts X` without a slip when the slip is None.
   - M23 is red on `test_schedule_open_time_shows_no_slip`.
8. **(Minor) CLAUDE.md wording — ADDRESSED.** It now reads "persisted rows, the clock files and the interstitials folder only".
9. **(Minor) Delivered-library test — ADDRESSED.** The test asserts `library    delivered: 4 package(s)` and `Unvoiced Act 1999-09-09`.

### New Breakage in the Fix Diff
No Critical or Important problems. There are two Minor regressions; I reproduced both by running the same probe on d7f2bcf and on dcd0a2a.

1. **(Minor) The new trim hides a late block that is nominally inside the horizon, and its MISS with it** (service.py, the `views = [... any(sh.start_us < until_us ...) ...]` filter).
   - **Probe:** a persisted plan where Block 10 airs 10:00–13:00 and Block 12 (nominal 12:00, `miss=True`) starts at about 13:00. I previewed at 10:30 with `--days` set to 2 h and to 2.4 h.
   - **d7f2bcf:** prints `Block 12 starts … 12:59 (+60 min) [MISS]`.
   - **dcd0a2a:** omits the block entirely, and the summary says `misses 0`.
   - Trimming by the start of the first show is the right test for the case the fix targeted (an open-time occurrence whose next nominal start is past the horizon). But it drops an occurrence that is due inside the window and runs late past the horizon, which is the most notable thing such a view could show.
   - This only happens at the horizon edge, so at the default `--days 7` it is rare. It bites a short `--days` look-ahead.
   - **Suggested fix:** keep the union of the two rules, `nominal_us < until_us or any(sh.start_us < until_us ...)`. Neither the new open-time test nor the trim test (M17) rely on excluding these blocks.
   - I also checked the reverse direction: the new rule shows no block beyond `--days` other than ones whose first remaining show starts inside the window.
   - On the 3-tiny-package fixture it lists far more occurrences than before (test clock, `--days 3`: 37 → 355 views). That is because the projection really does run blocks early when the pool is short. It matches what would air and is not a trim error. Shows after `until` inside a kept view were also listed under the old rule.
2. **(Minor, cutover only) A stale `(unscheduled)` start.**
   - `live` also admits the key `(None, None)` while a phase-1 row (one with `block=None`) is still airing.
   - `plan.jsonl` keeps every aired row; nothing in `pipeline` or `planner` trims history. So every phase-1 row since the first plan is pulled into the `(unscheduled)` view.
   - That view takes `starts` from the earliest one. Combined with the new "print `starts` without a slip" branch, this gives the following.
   - **Probe:** previewing 30 min into an airing phase-1 row, with an earlier phase-1 row 2 days before.
   - **dcd0a2a** prints `(unscheduled)  starts Tue 10-02 05:00`, which is 2 days before now. **d7f2bcf** printed no start.
   - **Suggested fix:** `live = {... if r.end_frame > now_f and r.block is not None}`.

### Out-of-Scope Observations
- M30 survives: the per-show `[fill: …]` label in `schedule` and the summary `fill` line's labels are unpinned. Only `fill_label()` and the status line are tested. It is a nit; one `"[fill: pool short]"` assertion would pin it.
- There is test cruft in `test_cli.py`:
  - `assert engine.analyzed == [] or set(...) <= ... or True` is vacuous. The old `test_schedule_writes_nothing` still pins `analyzed == []`.
  - `rows[0] = PlanRow(...) if False else rows[0]` is dead code.
  - The "fix round 1" block re-imports `re`, `grid` and others mid-file under `# noqa: E402`, the same pattern as the earlier section.
  - Cosmetic only.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
- All 9 findings are addressed.
- Every previously surviving mutant (M4, M7, M8, M12, M15, M17, M18, M19, M20, M21) is now red on its predicted test.
- The new-code mutants R1, M22–M26, M29 and M31 are red on their predicted tests.
- Two new Minor regressions (above) are recommended for a small follow-up: the trim should keep blocks whose nominal start is inside the horizon, and `live` should exclude the `(None, None)` key.
