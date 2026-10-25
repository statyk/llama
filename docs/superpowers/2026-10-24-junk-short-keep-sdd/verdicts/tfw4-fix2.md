# tfw4-fix2 handback: FW4 fix round 2 (rule (b) reads the shipped set labels)

## Status
**DONE.** Nothing is UNEXPLAINED, and the prediction from round 1 held exactly.

## Commit
`4dd0ea6` fix(gather): FW4 round 2 - item 2's add guard reads the shipped set labels. Suite **5468 passed, 1 skipped, 8 deselected**; the command is in the message.

## Change
- `donor_segues` takes a required `shipped_sets` and rule (b) compares `shipped_sets[k] == shipped_sets[k+1]`.
- In compute_gather the call moves from right after align() to just before the tracks are rebuilt. It gets `final_sets` (the jerrybase-anchored `result.sets`, or the taper's labels), and the rebuild uses the same `final_sets`.
- No set relabel follows the rebuild; I checked the rest of compute_gather.
- Like round 1, it does not run when an `align_structure` result won (`alignment == "llm"`). That result replaced item 2 wholesale before too.
- No step between the old and new positions reads `result.segues`: anchoring changes sets only, and the taper reads labels only. So the move changes only what (b) reads.
- Unchanged from round 1: rule (a), the own-title `>` exception, removals, G5's leading-word form, the override path. No constant.

## Tests (RED on 0d5165c in a `git archive` copy, llama.__file__ confirmed)
- `test_fw4r2_gain_ships_when_the_shipped_sets_agree` uses the joerussosalmostdead-2017-04-29 shape (verbatim selected description, tags, setlist.fm). `Morfbeats` sits in canonical set one but shipped set two, beside `Dark Star`. It fails on 0d5165c, where the mark is missing.
- `test_fw4r2_gain_across_a_shipped_set_break_is_still_declined` is a pin on gd1987-03-27 and passes on both commits.
- `test_fw4_donor_segues_none_is_a_no_op` also fails on 0d5165c, but only because of the new keyword argument.
- Every round-1 test still passes.

## Measurement (~/.llama-harness/piece4: cand-g.json, compare-g/, arms-g/, fw4/r2/)
- **Arm:** clean 1252, clean-changed 1709, needs-brief 3, needs-llm 654, newly-held 220, still-held 135, still-held-package 1, structure-changed 9.
- **compare vs base:** rc 0. Only outcomes, packaged_exposure, summary and title_rows differ from compare-f.
- **arms:** **BLOCKS MERGE (0)**. The dict is unchanged; reference differences are 1207.
- **Row diff cand-f -> cand-g** (`fw4/r2/rowdiff-fg.txt`):
  - 18 rows differ, all delivered.
  - 17 differ in segues/segue_changes only; 1 also moves clean -> clean-changed and reuse -> fresh.
  - No other field changed, so UNEXPLAINED 0.
  - All 18 changes are on rule-(b) gains: 17 are item-2 gains (fw4/i2-marks.json) and 1 is round 1's G5-enabled gain. No removal moved.
- **Gains, read against the cached descriptions** (`fw4/r2/reads.md`):

| | count | right | unclear |
|---|---|---|---|
| restored | 12 | 10 (the predicted 10, all real) | 2 (deadandcompany-2017-06-22 #15, thedead-2009-05-05 #21) |
| newly declined | 6 | 5 | 1 (gratefuldead-1970-11-06 #42 Good Lovin' > Alligator) |

  - The 6 declined are the predicted 5 plus philleshandfriends-2007-11-05 #23, round 1's G5-enabled gain into the `audience, donor rap, intros` track, which now crosses a shipped set break.
  - The 5 right declines: gd1971-12-15 #24, gd1975-06-17 #10, gd1990-03-15 #10, gd1993-08-22 #8, phil-2007-11-05 #23.
- **Real marks lost:** 6 (item 2's own-alignment misses, unchanged) + 0 (G5) = **6**.
- **Real gains that (b) still declines:** 4 of round 1's 14, all because the shipped set label is itself wrong: discobiscuits-1999-12-30 #16, discobiscuits-2009-07-01 #9 and #17, gratefuldead-1990-07-14 #8.
- **Fresh briefs vs cand-d:** **+371** (round 1 +370, cand-e +383). 1036 rows differ vs cand-d.

## Concerns
None new. Unchanged from earlier rounds and out of scope: the LLM branch, and pooled marks feeding `correspondence._merge_legal` and the `align_structure` prompt.
