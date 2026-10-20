# t13b-impl handback

STATUS: DONE

## Commit
- 4826487 fix(gather): narrow slice 1 -- 1d only on a second venue (V), step 1's city check only for 1b-new pairs (S)  (on BASE 88f087a)

## Tests
`./.venv/bin/python -m pytest -q` -> 3571 passed, 1 skipped, 8 deselected (48 s). llama resolves inside the worktree.

## What changed
- structure.py: a frozen private copy of `venues_equivalent` as of 9b74164: `_venues_equivalent_pre1b`, `_place_tokens_pre1b`, `_tokens_equal_pre1b`, `_token_subset_pre1b`, `_acronym_match_pre1b`, plus frozen tables `_PLACE_STOPWORDS_PRE1B` / `_PLACE_ABBREV_PRE1B`. The comment cites "Checkpoint C operator decision (2026-10-19), narrowing S". `_token_subset` was copied as well, because it calls `_tokens_equal`. The live `venues_equivalent` and its helpers are untouched.
- gather.py step 1: `venues_equivalent(venue, ev) and (_venues_equivalent_pre1b(venue, ev) or cities_compatible(archive_city, jb_city))`. The swap, the signature, 1a and 1c are unchanged.
- gather.py 1d: adds `and not (_stripped(vote_venue) and venues_equivalent(sel_venue, vote_venue))`. `vote_venue = candidate.venue`, never the swapped `venue` or jerrybase's venue.
- No new note or flag text was added.

## Blank-vote-venue decision (V)
A blank or whitespace-only vote venue counts as NOT equivalent, so 1d fires as it does today. Reasoning: V suppresses 1d only on positive evidence that both recordings name one hall. A blank vote venue gives no such evidence, so the city conflict is the only signal left, and holding is the safe error. The explicit `_stripped(vote_venue)` guard also stops a selected venue whose tokens are empty (e.g. "---") from matching an empty vote through `venues_equivalent("", "") == True`. A test pins this for both "" and "   ".

## Tests added or changed
- test_structure.py::test_venues_equivalent_pre1b_is_the_cp_b2_rule: 24 pairs, each checked in both argument orders. Every expected value comes from running 9b74164's structure.py; a scratch script compared the old module with the copy on all 26 pairs, and all agreed. The 1b-new rows are False: Penn's, Jahrhundert, Meramec, Cornell U, Red Rocks, Merriweather, Barton/Cornell U, Barton/Burton. The pre-slice rows are True: Barrymore, Fox Theatre Pavilion, RFK, MSG, Roosevelt, Rams Head Live!, and others.
- RE-TARGETED (per ruling) test_stage_gather.py::test_step_1_needs_compatible_cities_not_just_an_equivalent_venue: jerrybase is monkeypatched to `Penn's Landing`, Philadelphia PA. The vote and the single recording are `Penns Landing` in Camden, NJ. Expected: `venue mismatch: archive 'Penns Landing' vs jerrybase 'Penn's Landing'`, and the vote venue is kept.
- NEW test_step_1_newly_equivalent_pair_with_compatible_cities_clears (Penns Landing in Philadelphia: clears).
- NEW companion test_step_1_pre_slice_equivalent_pair_clears_without_a_city_check: Barrymore Theater in St. Louis against jerrybase Barrymore Theatre in Madison gives no venue mismatch and no 1d.
- NEW test_1d_does_not_fire_when_the_selected_venue_is_the_votes_hall. Shape: mymorningjacket-2008-08-21, Red Rocks with Denver as the vote's city and Morrison as the selected recording's; Guster fixture, no jerrybase.
- NEW test_1d_a_blank_vote_venue_is_not_the_same_hall_and_still_holds["" and "   "].
- test_swap_ships_the_selected_venue_when_it_agrees_with_jerrybase_and_1d_still_holds is unchanged and green: DSO stays 1d-held.

## Mutation table (scratch root /var/folders/yn/.../T//mut-t13b-impl-F3XURd, deleted after; shadowing proven per mutant; every mutant applied with count==1)
| mutant | predicted | caught by |
|---|---|---|
| m1 remove V | gather::test_1d_does_not_fire_when_the_selected_venue_is_the_votes_hall | same (only failure) |
| m2a V against post-swap `venue` | gather::test_swap_ships_..._1d_still_holds | same (only failure) |
| m2b V against jerrybase venue | gather::test_swap_ships_..._1d_still_holds | same (only failure) |
| m2c V inverted | gather::test_1d_ships_the_selected_recording_on_a_city_conflict_without_jerrybase | same (+ DSO swap test, both V tests) |
| m7 blank vote venue counts as equivalent | gather::test_1d_a_blank_vote_venue_is_not_the_same_hall_and_still_holds | same, both params (only failures) |
| m3 remove S (always city check) | gather::test_step_1_pre_slice_equivalent_pair_clears_without_a_city_check | same (only failure) |
| m4 S widened (no city check) | gather::test_step_1_needs_compatible_cities_not_just_an_equivalent_venue | same (only failure) |
| m5 pre1b delegates to live | structure::test_venues_equivalent_pre1b_is_the_cp_b2_rule[1b rows]; gather step-1 retarget | same: all 8 1b rows + the retarget |
| m6 _place_tokens_pre1b gains apostrophe deletion | structure::...[Penn's Landing-Penns Landing-False]; gather step-1 retarget | same (only failures) |
| m6b _tokens_equal_pre1b gains one-edit | structure::...[Barton Hall-Burton Hall-False] | same (+ the Merriweather row) |
No survivors.

## Real-slug check (scripts/replay_holds.py run --slugs, read-only, output in scratch)
- darkstarorchestra-2003-01-25: still held by 1d (Madison vs St. Louis), Barrymore Theater ships. OK.
- ginblossoms-2003-01-24, stuallenandmarshotel-2012-11-11, ryanadams-2007-06-06: still newly held by 1d (the 3 TRUE holds). OK.
- gratefuldead-1973-08-01 (Roosevelt Stadium): clean, venue mismatch gone. OK.
- gratefuldead-1972-04-26 (Jahrhundert Halle, newly equivalent, cities incompatible): still held with venue mismatch. OK.
- mymorningjacket-2008-08-21, gratefuldead-1991-06-09, philleshandfriends-2006-02-25, gratefuldead-1971-08-26: clean.
Summary line: replayed 10: clean=5, newly-held=3, still-held=2.

## Deviations
- The mutation rsync also excluded `.superpowers` (on top of .venv and .git), to avoid copying the SDD ledger into scratch. It has no effect on the code under test.
- The pre-1b stopword and abbreviation tables are frozen copies rather than references to the live tables. They are identical today. The brief asked only for frozen copies of helpers that Task 12 changed; freezing the tables as well means a later edit to the live tables cannot move `_pre1b`.
