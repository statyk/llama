### Finding Verdicts

1. **IMPORTANT: city checks on step 1 and the swap were unpinned (mutants survived)**: ADDRESSED.
   - Step 1 (`packages/llama/src/llama/stages/gather.py:1398`): pinned by `test_step_1_needs_compatible_cities_not_just_an_equivalent_venue` (`packages/llama/tests/test_stage_gather.py:2866`). It uses the vote "Barrymore Theater" in St. Louis, MO, one recording with the same venue and city, and the DSO event at Barrymore Theatre in Madison, WI. It asserts the venue mismatch flag, that the vote venue is kept, and `not two_venue_signature`. I traced the chain: step 1 fails on the city; the swap fails on the city; there is no signature; 1c fails on the city; today's flag fires; 1d does not fire, because the cities are equal. This matches the required scenario.
   - Swap (`gather.py:1401`): pinned by `test_the_swap_needs_compatible_cities_not_just_an_equivalent_venue` (`test_stage_gather.py:2878`). It uses the selected recording at Barrymore Theater, St. Louis, MO, and the vote The Pageant, St. Louis, MO, with one recording. It asserts the venue The Pageant, today's mismatch flag, no swap note, and no signature. This matches the required scenario.
   - Re-checked mutant (f) myself in a scratch copy, with shadowing proven (gather imports from the copy) and a private PYTHONPYCACHEPREFIX. Removing `and cities_compatible(archive_city, jb_city)` from step 1 gave 1 failed and 147 passed. The only failure was the predicted `test_step_1_...`.
   - I did not re-run mutant (g). By trace it is caught: with the swap's city check removed, the swap fires and the venue becomes "Barrymore Theater", so the venue assertion and the no-swap-note assertion both fail. This agrees with the implementer's table.
2. **RULED: 1d must test `_stripped(vote_city)`, with a whitespace-vote-city test and a caught reverting mutant**: ADDRESSED.
   - The fix is at `gather.py:1422-1423`: `if (sel_venue and sel_city and _stripped(vote_city) and not cities_compatible(sel_city, vote_city))`. The comment at :1421 states the ruling.
   - The test is `test_1d_a_whitespace_only_vote_city_is_unknown_and_no_conflict` (`test_stage_gather.py:2891`). It uses vote city `"   "` and the selected recording in Madison, WI, and asserts no "disagree on city" flag and that the vote venue is kept.
   - Re-checked mutant (h) myself: reverting to the raw `vote_city` gave 1 failed and 147 passed. The only failure was the predicted 1d test. This is expected, because `cities_compatible("Madison, WI", "   ")` returns False on its empty key (`structure.py:423-424`), so the unstripped guard would hold the show.
   - Scratch dir `$TMPDIR/mut-t13-rr1-Bp2HTz` has been removed.

### New Breakage in the Fix Diff

None.
- The only production change narrows 1d: a whitespace-only vote city no longer triggers 1d, and every other input behaves exactly as before, because `sel_city` was already `_stripped`.
- The flag text still prints `vote_city` verbatim, but it cannot now be whitespace-only, so the output is unaffected.
- The three new tests assert exact flag strings and notes, not loose `any()` checks over a broad substring, apart from the 1d-absence check, which is correctly negative.

### Out-of-Scope Observations

The brief's Interfaces line for 1d (task-13-brief.md:26) still says plain `vote_city`. The ruling supersedes it, so the brief or spec text could be aligned in the final pass. Non-blocking.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
