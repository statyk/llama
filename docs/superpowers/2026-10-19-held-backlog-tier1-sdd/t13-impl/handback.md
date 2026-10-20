# t13-impl handback — Task 13 (slice 1 gather venue block)

**Status: DONE**

**Commit:** `110f72d` feat(gather): slice 1 venue tripwire: swap, 1a, 1c, two-venue signature, 1d city-conflict hold (on BASE 2f72aff)

**Tests:** `./.venv/bin/python -m pytest -q` -> 3539 passed, 1 skipped, 8 deselected (baseline at BASE: 3538 + the 1 survivor test added; the brief's 12 tests are inside the 3538). `llama.__file__` confirmed in the worktree.

## What changed
- `packages/llama/src/llama/stages/gather.py`:
  - new `jerrybase_city(event)` (`"City, State"`, or the city alone when no state), `two_venue_signature(candidate)` (any pair of recordings with stripped non-empty venues: not `venues_equivalent` and `cities_compatible(coverage or candidate.city, ...)`), private `_stripped`, `_CITY_CONFLICT_FLAG`; `cities_compatible` imported from structure.
  - venue block = ONE if/elif chain in the brief's order: enrichment (byte-identical apart from the 1a guard `event.venue.strip()`; blank vote + blank jerrybase venue -> nothing, no flag), 1a, step 1, step 2 swap (+ swap note), signature (today's flag), 1c (`len(events) == 1`, + 1c note), else today's flag. `sel` = candidate recording whose identifier is the selected one (None -> no swap/1c/1d).
  - 1d after the chain on every show; then the overrides block, extended so a venue OR city override removes the 1d flag (the venue-mismatch removal stays venue-override-only, as today).
  - Note/flag texts verbatim from Contracts; notes go to `op_notes` (`GatherResult.notes`) only.
- Fixtures (cut offline with `scripts/capture_fixture.py --from-cache`): `packages/llama/tests/fixtures/dso2003-01-25.json`, `guster2003-07-10.json`, `gd78-11-17_dodd.json`.
- `packages/llama/tests/test_stage_gather.py`: the brief's tests appended verbatim, plus one survivor test.

## Deviations
1. **B3 (orchestrator ruling):** `test_gather_venue_equivalent_passes_no_mismatch` went red as predicted (`Washington, DC` vs `Washington, ST`). Fixed the fixture: `_jb_event` gained `state="ST"` keyword (default unchanged), that test passes `state="DC"`, with a 2-line comment. Stated in the commit message.
2. **Added test** `test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase` (mutant (a) survivor; see below). It selects the GD78 wiley tape (Uptown Theatre, agrees with jerrybase) in a candidate that also has the Rambler Room tape: only the signature keeps the vote + `venue mismatch` and suppresses the swap note.
3. None in logic. Note for reviewer: 1d uses the brief's literal `vote_city` truthiness (a whitespace-only or punctuation-only vote city with a known selected city fires 1d — a hold, the conservative direction); `sel_venue`/`sel_city` are stripped per the brief.

## Mutation table (MROOT under $TMPDIR, `mut-t13-impl-*`, removed after; shadowing proven per mutant — `llama.__file__` printed under `$MROOT/<m>/tree`; private PYTHONPYCACHEPREFIX; run over test_stage_gather.py)

| mutant | predicted test | result |
|---|---|---|
| (a) swap without `not two_venue_signature(candidate)` | `test_two_venue_signature_keeps_the_same_city_double_held` (predicted in the log to SURVIVE: that test selects the Rambler Room tape, which never meets the swap's equivalence) | **SURVIVED** (144 passed) -> added survivor test; rerun predicted `test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase` -> caught by it (only failure) |
| (b) 1c without `len(events) == 1` | `test_1c_does_not_apply_on_a_per_event_candidate_of_a_multi_event_date` | caught by it (only failure) |
| (c) 1d evaluated before the swap | `test_swap_ships_the_selected_venue_when_it_agrees_with_jerrybase_and_1d_still_holds` | caught by it (only failure) |
| (d) overrides block no longer removes the 1d flag | `test_an_operator_venue_override_suppresses_the_1d_hold` | caught by it (only failure) |
| (e) enrichment fires on a blank `event.venue` | `test_1a_blank_vote_venue_on_a_blank_jerrybase_venue_takes_nothing_from_jerrybase` | caught by it (only failure) |

Log: `.superpowers/sdd/tier1/t13-impl/t13-impl.log`.

---

# Fix round 1

**Status: DONE.** Commit `88f087a` "fix(gather): pin slice 1's city checks on step 1 and the swap; a blank vote city is no 1d conflict", on top of `110f72d`.

**Changes**
- `gather.py`, 1d: now `if (sel_venue and sel_city and _stripped(vote_city) and not cities_compatible(sel_city, vote_city))`, following the ruling that an unknown city is no conflict. The comment was updated to match.
- New tests in `test_stage_gather.py`:
  - `test_step_1_needs_compatible_cities_not_just_an_equivalent_venue`: the vote and its one recording are both "Barrymore Theater" in St. Louis, MO, against jerrybase's Barrymore Theatre in Madison, WI. Expected: `venue mismatch: archive 'Barrymore Theater' vs jerrybase 'Barrymore Theatre'`, and the venue unchanged.
  - `test_the_swap_needs_compatible_cities_not_just_an_equivalent_venue`: the vote is "The Pageant" in St. Louis, MO, and its one recording is "Barrymore Theater" in St. Louis, MO. Expected: today's flag, the venue "The Pageant", and no swap note.
  - `test_1d_a_whitespace_only_vote_city_is_unknown_and_no_conflict`: the vote city is `"   "`, and the selected recording is Barrymore Theater in Madison, WI. Expected: no "disagree on city" flag, and the vote venue kept.
  - Both single-recording tests assert `not two_venue_signature(cand)`.

**Tests**
- `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q`: 148 passed.
- `./.venv/bin/python -m pytest -q`: 3542 passed, 1 skipped, 8 deselected.

**Mutation run**
- Mutation copies went under `$TMPDIR/mut-t13-impl-r1-0W7KOR`, which has since been removed. Shadowing was proven for each mutant, and each had its own private PYTHONPYCACHEPREFIX.
- The first f/g/h attempt was **invalid**. My mutation-applier script had a syntax error, so no mutant was applied and the runs reported 148 passed on unmutated code. The log records this. I fixed the script, made the runner abort when a mutant is not applied, and reran all three on fresh copies with the same predictions.

| mutant | predicted test | result |
|---|---|---|
| (f) step 1 without `cities_compatible(archive_city, jb_city)` | `test_step_1_needs_compatible_cities_not_just_an_equivalent_venue` | caught by it (only failure) |
| (g) swap without `cities_compatible(sel_city or vote_city, jb_city)` | `test_the_swap_needs_compatible_cities_not_just_an_equivalent_venue` (also predicted: `test_step_1_...`, whose selected tape would now swap) | caught by both predicted tests (only failures) |
| (h) 1d on the raw `vote_city` (revert `_stripped`) | `test_1d_a_whitespace_only_vote_city_is_unknown_and_no_conflict` | caught by it (only failure) |
