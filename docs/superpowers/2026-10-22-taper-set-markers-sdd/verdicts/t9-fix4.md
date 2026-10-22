# t9-fix4 handback (FIX_BASE cef2675)

**Status: DONE.** The narrowed B4 ruling is built, umphreys is owned again with its full owned-path gather test, the spec wording is fixed, and the mutation pins are recorded. The probe result is what llama-db expected: of the 15 shows lost at gate7, only joerussosalmostdead-2019-09-28 stays declined.

## Commits
- 77e5322 fix(taper): B4 checks a repeated set-1 opener's latest hit (narrowed ruling)
- 95c735a test(taper): pin B4's latest hit on the stevekimockband-2000-03-31 text
- a9016b5 docs: taper-markers mutation record, fix round 4 (B4 latest hit)

## Changes
1. **Narrowed B4 (llama-db).**
   - `_step1_break_before_set_1` takes `h = hits[-1]`: the latest hit in set 1's window, which is unchanged (tracks at or before set 1's placed boundary).
   - A stand-in item (when set 1's first item has no hit) gets the same treatment: its latest hit in the window.
   - `B4_AMBIGUOUS` and the `veto: set 1's first song matches several tracks` reason are gone. With several hits, `veto: step-1 break before set 1` applies against the latest hit.
   - Code comments and spec §2 attribute it as "(llama-db ruling, 2026-10-22, narrowed the same day)".
   - Spec §1: umphreysmcgee-2004-04-14 is back as a positive ("is taper-owned, identical to today").
2. **The umphreys gather test is back on the owned path (t9-rr1).** It is again `test_umphreys_2004_04_14_taper_owned_identical_to_today`, with the original assertions: owned True, labels equal to the oracle, set_breaks [11, 18], trailing encore, review_flags and alignment equal to the oracle, `_was_notes == []`. The reviewer's renamed-repeat variant was not needed.
3. **Spec §2 wording (t9-rr1).** The examples are now described as "Illustrations from the real-case test fixtures, not a population measurement":
   - stevekimockband-2000-03-31 declines against its latest hit;
   - umphreysmcgee-2004-04-14 (`The Fuzz`) and joerussosalmostdead-2017-03-11 (`Jam @`) have no step-1 break in the window and stay owned.

## Tests (packages/llama/tests/test_taper.py unless noted)
- `test_step1_break_before_set_1_real_case_declines`, re-pinned on the real tape:
  - step 1 [6,13] declines with `veto: step-1 break before set 1`;
  - a flat step 1 is owned at (13,);
  - a hypothetical step 1 breaking between the two `Severe Tire Damage` hits (after track 8) declines. This is the only assertion here that tells the latest hit from the earliest: [6,13] breaks before both hits (tracks 7 and 9).
- `test_repeated_set_1_opener_checks_the_latest_hit[today0-False, today1-True]`: a repeated `Jam` opener. A step-1 break between the earliest and latest hit declines; no break in the window stays owned.
- `test_a_repeat_after_set_1_is_outside_the_window`: the opener is heard again after set 1, and a step-1 break after the in-window hit still leaves the show owned.
- `test_the_stand_in_item_uses_its_latest_hit[today0-False, today1-True]`: my call, per the scope note.
- Removed:
  - `test_set_1_first_song_matching_several_tracks_declines`;
  - `test_uniqueness_applies_to_the_item_that_stands_in`;
  - `test_a_repeat_after_set_1_does_not_make_the_hit_ambiguous`;
  - `test_b4_ambiguous_real_cases_decline`.
  joerussosalmostdead-2017-03-11 is back in `test_annotated_header_real_cases_own`.
- Covering files (test_taper, test_stage_gather, test_replay_holds, test_taper_probe, test_replay, test_reapply): **800 passed**.
- Full suite: `./.venv/bin/python -m pytest -q` → **4474 passed, 1 skipped, 8 deselected**.
- `git diff main -- packages/llama/src/llama/setlist.py` is empty: **yes**.

## Probe (`gate --out ~/.llama-harness/piece2/gate8`; `delta gate7→gate8` → delta7-8; `delta gate6→gate8` → delta6-8)
- **Gate in scope:** 75/186 → **76/186**. joerussosalmostdead-2017-03-11 is owned again; it is graded `match=miss`, as it was before the uniqueness rule. gate6 → gate8: no change.
- **Library:** 613 → **627** owned. That is 14 newly owned, 0 newly not owned, and no owned show with changed labels.
- **gate6 → gate8 (library):** exactly 1 newly not owned, joerussosalmostdead-2019-09-28 (`veto: step-1 break before set 1`).

The 15 shows lost at gate7:

| show | gate8 | why |
|---|---|---|
| joerussosalmostdead-2019-09-28 | **stays declined** | Opener `Jam` hits tracks 1 and 5 in set 1's window (boundary after 8). Step 1 (stored labels) breaks after track 4, before the latest hit, so `veto: step-1 break before set 1`. The earliest hit would have hidden that break. |
| umphreysmcgee-2004-04-14 | owned | `The Fuzz` hits 1 and 3; stored breaks are after 11 and 18, none before the latest hit. |
| gratefuldead-1974-02-22 | owned | `U.S. Blues` hits 3, 4 and 8; stored breaks are after 19, 28 and 36, none before 8. |
| discobiscuits-2003-08-15 | owned | no step-1 break before the latest hit |
| gratefuldead-1982-09-15 | owned | no step-1 break before the latest hit |
| joerussosalmostdead-2018-05-04 | owned | no step-1 break before the latest hit (tier: songs moved) |
| joerussosalmostdead-2018-11-11 | owned | no step-1 break before the latest hit |
| joerussosalmostdead-2023-01-26 | owned | no step-1 break before the latest hit |
| philleshandfriends-2005-12-10 | owned | no step-1 break before the latest hit |
| radiators-2005-07-03 | owned | no step-1 break before the latest hit (tier: encore added) |
| stevekimockband-2000-04-28 | owned | no step-1 break before the latest hit |
| thedead-2009-05-09 | owned | no step-1 break before the latest hit |
| themotet-2011-10-29 | owned | no step-1 break before the latest hit |
| yondermountainstringband-2006-01-27 | owned | no step-1 break before the latest hit |
| yondermountainstringband-2006-12-29 | owned | no step-1 break before the latest hit |

The probe uses stored labels as step 1. For the 14 shows, "no step-1 break before the latest hit" is inferred from B4 passing at gate8, not printed separately. Their gate7 reason was the removed uniqueness veto, and their gate6 status was owned with identical labels, so nothing else moved.

## Mutation rows (mutation.md, "Fix round 4")
Bases `git archive 77e5322` and then `95c735a`, 800 tests, predictions logged first. S0 was 0 red on both bases. U1 and U2 are retired as moot, with a note; M1 and K1 stand.

| mutant | change | first run | after the re-pin |
|---|---|---|---|
| L1 | earliest hit instead of latest | SURPRISE-CATCH: the real-case test stayed green, because step 1 [6,13] breaks before both hits; caught by the two synthetic tests | CAUGHT-AS-PREDICTED, 3 tests |
| L2 | several-hits treatment removed, only the first hit kept | same as L1 (behaviourally the same mutant) | CAUGHT-AS-PREDICTED, 3 tests |
| L3 | window widened to the whole tape | CAUGHT, plus 1 declared extra red (`test_a_set_1_song_heard_only_after_set_1_does_not_widen_the_window`), read | not re-run |

L2: the narrowed rule has no separate uniqueness branch. Taking the latest hit is the several-hits treatment, so "branch removed" reduces to L1.

## Concerns / my calls
- My call: a stand-in item uses its latest hit in the window, per the scope note.
- My call: the hypothetical step 1 [8,13] on stevekimockband-2000-03-31 is a constructed step 1, not a measured one. It is there because the real step 1 cannot tell latest from earliest.
- The `B4_BREAK` constant remains; tests compare the literal string (t9-rr1's harmless note).
