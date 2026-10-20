# t13b-rev handback: Task 13b review (88f087a..4826487)

### Spec Compliance

- ✅ Spec compliant.
  - V at gather.py:1434: `and not (_stripped(vote_venue) and venues_equivalent(sel_venue, vote_venue))`. `vote_venue` is bound at gather.py:1384 as `candidate.venue`. It is never the swapped `venue` and never `event.venue`.
  - S at gather.py:1399-1406: `venues_equivalent(venue, event.venue) and (_venues_equivalent_pre1b(venue, event.venue) or cities_compatible(archive_city, jb_city))`. At that point `venue` is still the vote venue, because the chain runs before the swap.
  - The swap (gather.py:1407-1413), the two-venue signature, 1a (gather.py:1396-1398) and 1c are unchanged in the diff. Their city checks are byte-identical.
  - No note or flag text changed. The 1d flag still goes through `_CITY_CONFLICT_FLAG`. The mismatch string is untouched.
  - No do-not-retune constant appears in the diff.
- Frozen copy fidelity (structure.py:371-445 against `git show 9b74164:…structure.py` lines 247-320):
  - `_PLACE_STOPWORDS_PRE1B`, `_PLACE_ABBREV_PRE1B`, `_place_tokens_pre1b`, `_tokens_equal_pre1b`, `_token_subset_pre1b`, `_acronym_match_pre1b` and `_venues_equivalent_pre1b` match the old code token for token, modulo names and docstrings. The stopwords changed from a set to a frozenset, which makes no behavioural difference.
  - Differential check I ran: the old module's `venues_equivalent` against `_venues_equivalent_pre1b` over 296,869 pairs. The pairs were every intra-candidate venue pair in the library plus 300k random pairs drawn from 2,987 distinct library venue strings; 1,402 of them were old-True. **0 mismatches.**
- Blank vote venue under V counts as "not equivalent", so 1d still fires: **agreed**. It suppresses only on positive same-hall evidence. Without the guard, the result would differ only when `sel_venue` tokenizes to nothing (e.g. "---"): `venues_equivalent("---", "") == True`. Pinned by gather test `test_1d_a_blank_vote_venue_is_not_the_same_hall_and_still_holds["" / "   "]`.
- Required tests are present:
  - test_step_1 is re-targeted to Penns Landing / Penn's Landing (test_stage_gather.py:2869-2886).
  - The pre-slice companion uses Barrymore with incompatible cities (test_stage_gather.py:2900-2911).
  - The pre1b table holds every brief-12 row as False, and Barrymore and Fox Theatre Pavilion as True (test_structure.py:363-397).
  - The DSO swap test is unchanged.
- ⚠️ Cannot verify from the diff: the full-suite count (3571) and the mutation table are the implementer's claims; I did not re-run them. The real-slug replay was not re-run either. My own library probe (below) independently reproduces the 35 V-removals.

### Library measurement of V's risk (read-only probes over ~/.llama/shows, 3,468 dirs)

- The old 1d condition fires on 57 shows. **V suppresses 35**, which matches the brief's figure. 33 are equivalent under the pre-1b rule. 2 are equivalent only under 1b: alejandroescovedo-2008-09-09 (Troubador/Troubadour) and derektrucksband-2007-05-27 (Ampitheater/Amphitheater).
- I read all 35 pairs. Every one names the same hall (suburb vs metro, country code vs name, junk in the city field, and so on). gomez-2006-10-06 is even better off: V stops it shipping a wrong "Boston, MA" for the Bowery Ballroom.
- None of the 3 TRUE holds (ginblossoms-2003-01-24, stuallenandmarshotel-2012-11-11, ryanadams-2007-06-06) is in the suppressed set. darkstarorchestra-2003-01-25 is not in it either.
- To size the generic-name class you asked about, I widened the check to every recording vs the vote, not only the selected recording. 172 pairs have an equivalent venue and an incompatible city.
  - 11 have an all-generic shorter side (Civic Center, Civic Auditorium, Palace Theatre, Academy, The Forum, Convention Hall, Capitol Theatre). All 11 are the same hall with a misspelled or variant city.
  - 13 are equivalent only via 1b (Frost Ampitheater, Gelsten/Gelston, Snipe's/Snipes, Congresszentrum/-centrum). All 13 are the same hall.
  - **Measured true-hold loss: 0/172.**
- The theoretical class does exist and is unmeasured only because the library has no instance. V uses the live, widened rule, so all of these count as equivalent and would lose 1d:
  - generic subsets ("Auditorium" vs "Civic Auditorium", "Civic Center" vs "Hartford Civic Center": True under both rules);
  - the university strip: `venues_equivalent("Cornell University", "Cornell College")` is True (Ithaca vs Mount Vernon, IA);
  - one-edit names: "Capitol Theatre" vs "Capital Theatre" and "Barton Hall" vs "Burton Hall" are True live and False pre-1b.

  A mis-dated tape from another city at a generic-named hall would lose its 1d hold under V. That is the residual risk the operator accepted with V, as the brief prescribes. See Minor 1.

### Strengths

- V and S are each a single, minimal conjunct, with comments citing the operator decision. The chain order and every other arm are left alone.
- The frozen copy also freezes its tables, so a later edit to `_PLACE_ABBREV`/`_PLACE_STOPWORDS` cannot move `_pre1b`. That is the right call, and the comment at structure.py:371-379 tells future readers never to track the live code.
- The tests sit where the decision is made:
  - The V test uses a real two-recording Red Rocks shape and asserts the shipped (venue, city), not only that the flag is absent.
  - The S re-target uses a genuinely 1b-new pair, and a companion pins the pre-slice pass.
  - The pre1b table checks both argument orders.
- The mutation table covers all 6 required mutants plus m2a/m2b/m2c/m6b/m7. Every mutant was caught by its predicted test.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **gather.py:1434: V uses the live, widened `venues_equivalent`, so 1b's loosenings (one-edit, university strip, spelling folds) also widen V's suppression.** Live-only pairs include Cornell University / Cornell College and Capitol / Capital Theatre, where a different hall reads as "the same hall". This is as briefed, and measured harm is 0 (only 2 of the 35 suppressions depend on 1b, and both are correct). Scoping V to `_venues_equivalent_pre1b` would lose exactly those 2 correct clears in exchange for removing the one-edit and university-strip false-equivalence class from 1d. This is the operator's call; record it as a known residual, no code change.
2. **gather.py:1402-1404 and structure.py:371-374: the comment "a pair equivalent before slice 1 passes on equivalence alone" is not quite true.** The briefed formula also requires the live `venues_equivalent`, and the live rule is not a superset of the pre-1b one. Task 12's university strip turned these pre-1b True pairs False: `("UCLA", "Pauley Pavilion, UCLA")`, `("MIT", "Kresge Auditorium, MIT")`, `("University", "University Hall")`. The cause is that the subset test now runs only on stripped tokens and declines when a side empties. Such a pair now falls through step 1 and can flag `venue mismatch` where 9b74164 cleared it. This is a Task 12 behaviour, not introduced here. Measured in the library across vote/recording vs jerrybase, and recording vs recording: **0 pairs**. Either adjust the comment or note it for the branch reviewer. A code change belongs to Task 12's owner/operator, not 13b.
3. **gather.py:1434: the `_stripped(vote_venue)` guard is not pinned by any test.** Removing it changes behaviour only when the selected venue is punctuation-only (e.g. "---") and the vote venue is blank; m7 tests a different flip. It would survive mutation, though the case is nearly equivalent. A one-line test with `sel venue="---"` and vote `""` would pin it.
4. **test_stage_gather.py:2900-2911:** `test_step_1_pre_slice_equivalent_pair_clears_without_a_city_check` also asserts no 1d, but its vote and selected cities are both St. Louis, so 1d could never fire there. The assertion is harmless but proves nothing.

### Checks run

- Ran the focused tests: `./.venv/bin/python -m pytest -q test_structure.py test_stage_gather.py -k "pre1b or venues or step_1 or 1d or swap or signature"` → 66 passed.
- Ran the read-only probes; scripts are in /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-tier1/927bc958-2722-4419-85dd-93da116478c9/scratchpad:
  - probe_v.py: V suppression set.
  - probe_v2.py: all-recordings and generic-name class.
  - probe_fid.py: pre1b fidelity against 9b74164.
  - probe_univ.py: pre1b-True/live-False pairs, including jerrybase venues.
- No worktree, index or HEAD mutation. Nothing was written under ~/.llama.

### Assessment

**Task quality:** Approved

**Reasoning:** V and S are implemented exactly as briefed, with a frozen copy that is faithful to 9b74164 (0 mismatches over about 297k pairs), and V's suppressions are 35/35 same-hall in the library with all 3 true holds and DSO-2003-01-25 retained. The remaining risks are theoretical classes with zero library instances, and they belong to the operator, not to code fixes.
