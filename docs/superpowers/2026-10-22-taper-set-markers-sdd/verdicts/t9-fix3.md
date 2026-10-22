# t9-fix3 handback (FIX_BASE 9388d09)

**Status: DONE_WITH_CONCERNS.** Every finding is fixed and the B4 uniqueness ruling is built.
The concern: the ruling's expected owned delta ("joerussosalmostdead-2019-09-28 and possibly nothing else") does not hold. The library loses **15** owned shows, not 1.

## Commits
- 4aa9f8c fix(harness): pin R1's needs-LLM-base branch; report 3 says step1 mechanism
- 6a117f2 fix(taper): today_reaches_llm required; B4 declines an ambiguous set-1 opener
- 722d4d0 docs(spec): B4 uniqueness rule, low-confidence and furthur notes, post-G1 D1 figure
- cef2675 docs: taper-markers mutation record, fix round 3 (M1, B4 uniqueness, required arg)

## Findings → fixes

**1. R1's needs-LLM branch was untested (t9-rev).**
- `test_taper_changes_segues_changed_tier` now sets the `seg-llm` base row's `segue_changes = lost`. That is the realistic shape: the base computes the step-1 diff before it marks the row needs-LLM.
- M1 was re-run in a scratch copy with the prediction logged first, and is now **CAUGHT-AS-PREDICTED**.

**2. `today_reaches_llm` defaulted to False (llama-db).**
- `today_reaches_llm` is now a required keyword argument with no default; the docstring gives the reason.
- Every caller passes it explicitly:
  - gather (unchanged behaviour);
  - the probe, whose `decide` and `r4_alone` also had their defaults removed;
  - 43 `decide_taper` calls in `test_taper.py`, with `today_reaches_llm=False`;
  - the gather test stubs (`_not_owned`, `spy`, `filler_only`), which now take it as a required keyword too.
- New pin: `test_today_reaches_llm_is_required` (TypeError when omitted). Mutant K1 is caught.

**3. Probe docstring heading (t9-rev).** The G1 stored-proxy bullet moved out from under "Judgment calls (each errs toward the taper owning LESS)" into its own block, "Approximate, direction mixed". The block names both directions of error and says the proxy is passed explicitly on every call.

**4. Two spec gaps (t9-rev).**
- §4, the low-confidence paragraph:
  - adds the missing "canonical items" conjunct;
  - adds that since G1 the owned flag can arise only on a taper with a recognised encore marker.
- The furthur-2012-07-08 limitation now says the show carries an operator structure override. Production ships the override, so the fold is seen only in the harness's override-ignoring mode.

**5. Report 3's step-1 label (rescreen2 O1).**
- Report 3 now prints `step1 mechanism: <x>`, or `overruled step1 mechanism: <x>`, instead of `step1:`/`overruled:`.
- Tests updated:
  - `test_provenance_only_row_says_step1_not_overruled` asserts `step1 mechanism: jerrybase`, and that no `step1: ` appears.
  - `test_taper_changes_report_tiers_and_states` asserts `overruled step1 mechanism: jerrybase`.

**6. D1's post-G1 figure (rescreen2 O2).** The verbatim ruling text is kept. The parenthetical now adds "After G1: 143 segues lost over 36 shows, about 139 of them real (acceptance run 2, 9388d09)."

**Addition: B4 uniqueness (llama-db ruling, 2026-10-22).**
- What it does: `_step1_break_before_set_1` now returns a reason or None.
  - If the item supplying set 1's hit matches more than one track in set 1's window, it returns `veto: set 1's first song matches several tracks`. "Set 1's window" is the tracks at or before set 1's placed boundary, the same window B4 already searched.
  - A unique hit goes through the break test as before.
  - The attribution "(llama-db ruling, 2026-10-22)" is in the code comment and in spec §2.
- My call: when set 1's first item has no hit and the next set-1 item stands in, the uniqueness test applies to the item that stands in (`test_uniqueness_applies_to_the_item_that_stands_in`).
- Tests:
  - `test_set_1_first_song_matching_several_tracks_declines`: a repeated `Jam` opener; declines with either step 1.
  - `test_a_repeat_after_set_1_does_not_make_the_hit_ambiguous`: the window is set 1's.
  - `test_uniqueness_applies_to_the_item_that_stands_in`.
  - `test_b4_ambiguous_real_cases_decline`: joerussosalmostdead-2017-03-11, opener `Jam @`. Its headers still assert. It is no longer in `test_annotated_header_real_cases_own`.
- Existing tests that changed because the rule applies to them:
  - **SKB real case** (`test_step1_break_before_set_1_real_case_declines`): stevekimockband-2000-03-31 itself now declines on uniqueness first, because `Severe Tire Damage` is tracks 7 and 9. The test asserts that reason for both step 1s. It keeps the break-rule check on the real text by renaming track 9: step 1 [6,13] then declines on the break, and a flat step 1 is owned at (13,).
  - **umphreys gather test** is renamed `test_umphreys_2004_04_14_identical_to_today`. The show is no longer taper-owned (`The Fuzz` is on the tape twice in set 1). It is asserted not owned with the new reason, and equal to the oracle on every field except `taper`.
  - **Spec §1's umphreys line** said "taper-owned, identical to today". I amended it to match.
  - `test_the_hit_is_the_earliest_match_of_set_1s_first_song` was replaced by the repeated-opener test, so mutant B4f is superseded. The mutation record says so.

## Tests
- Covering files (test_taper, test_stage_gather, test_replay_holds, test_taper_probe, test_replay, test_reapply): **798 passed**.
- Full suite: `./.venv/bin/python -m pytest -q` → **4472 passed, 1 skipped, 8 deselected**.
- `git diff main -- packages/llama/src/llama/setlist.py` is empty: **yes**.

## Probe deltas (`gate --out ~/.llama-harness/piece2/gate7`; `delta --old gate6 --new gate7 --out ~/.llama-harness/piece2/delta6-7`)
- **Gate, in scope:** 76/186 → **75/186** owned. One flip: joerussosalmostdead-2017-03-11. The all-rows view has the same single flip.
- **Library:** 628 → **613** owned. 15 newly not owned, all with `veto: set 1's first song matches several tracks`:
  - discobiscuits-2003-08-15
  - gratefuldead-1974-02-22
  - gratefuldead-1982-09-15
  - joerussosalmostdead-2018-05-04
  - joerussosalmostdead-2018-11-11
  - joerussosalmostdead-2019-09-28
  - joerussosalmostdead-2023-01-26
  - philleshandfriends-2005-12-10
  - radiators-2005-07-03
  - stevekimockband-2000-04-28
  - thedead-2009-05-09
  - themotet-2011-10-29
  - umphreysmcgee-2004-04-14
  - yondermountainstringband-2006-01-27
  - yondermountainstringband-2006-12-29
- Nothing is newly owned, and no owned show's labels changed.
- The probe uses stored labels as step 1. The flip count matches t9-rev's 15 multi-hit rows. Its "only joerussosalmostdead-2019-09-28" figure answered a different question: earliest vs latest hit, not declining an ambiguous one.

## Mutation rows (mutation.md, "Fix round 3")
- Setup: `git archive 722d4d0`, 798 tests, the same instrument as before, predictions logged first. S0 had 0 red.
- **M1** (R1's needs-LLM branch dropped): CAUGHT-AS-PREDICTED. It had survived t9-rev's run.
- **U1** (uniqueness check removed): CAUGHT-AS-PREDICTED, 5 tests.
- **U2** (window widened to the whole tape): CAUGHT, with 1 declared extra red, read. corblund-2004-11-04's opener is also track 34.
- **K1** (the default restored): CAUGHT-AS-PREDICTED.
- **Total:** 4/4 caught, 0 survived, 0 hangs.

## Concerns
- **The ruling's expected delta is wrong by 14 shows.** The library loses 15 owned shows, not 1.
  - Among them is gratefuldead-1974-02-22, which acc-explain B4 cited as an owned show "agreeing with today" through its leading filler songs.
  - umphreysmcgee-2004-04-14 was a spec-listed "taper-owned" positive. It is still computed identically to today, just not owned.
  - The change only makes the taper own less, so it is safe in direction. llama-db may still want to see the list before merge.
- My call: the uniqueness test applies to whichever set-1 item supplies the hit, including one standing in for a first item with no hit.
- My call: on stevekimockband-2000-03-31 the decline reason is now uniqueness, not the break. The break rule stays pinned on the same real text, with track 9 renamed so the opener is unique.
- My call: report 3 labels an overruled row `overruled step1 mechanism: <x>`, so the word "mechanism" appears on that row too.
