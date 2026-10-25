# tfw4-fix1 handback: FW4 fix round 1

## Status
**DONE_WITH_CONCERNS.** I-1, I-2, the llama-db G5 addition and both Minors are built test-first in one commit, and the suite is green. Nothing is UNEXPLAINED.

The concern is that rule (b), as specified (it reads `result.sets`, the canonical labels before anchoring and taper), drops **14 real marks** among the 22 dropped gains that the all-parses vote calls right. 10 of the 14 sit inside ONE shipped set.

## Commit
`0d5165c` fix(gather): FW4 round 1 - guard item 2's gains; G5 needs a leading filler word. Suite **5466 passed, 1 skipped, 8 deselected**; the command is in the message. It is one commit, not one per item: the three changes share gather.py hunks and their tests, and I can't split hunks without interactive git.

## Changes
**I-1, `donor_segues`.** The own alignment may still remove a mark anywhere. It may add one (pooled False, own True) only when both hold:
- the track is not the show's last;
- `result.sets[k] == result.sets[k+1]`, or the track's title ends in `>` (`t.title.rstrip().endswith(">")`, which covers `>`, `->` and `=>`).

No constant. I did not use the substring heuristic.

**G5, the llama-db addition: a narrow, constant-free form exists, and I adopted it.**
- `_leads_with_filler(title)`: past any leading non-word characters, the next donor entry must BEGIN with a `_FILLER` word. It uses `structure._FILLER` verbatim, with `.match` where `is_filler` uses `.search`.
- `is_filler` and `_FILLER` are unedited.
- I tested the coordinator's "wholly filler" form against the measured removals, and it reopens closers: it keeps the mark into `Banter and  Switches to Guitar` and into `Banter and Guitar Tuning` (warrenzevon-2000-04-22, 2 of its 4 banter marks). The leading form keeps all four cleared, and the D&C closers too.

**I-2.** G5's docstring now gives the measured cost at 20c4e6a: 5 marks, 4 of them from `is_filler` word matches inside real titles. It names the leading-word form's own cost.

**Minors.**
- The moe and gd88 pins are now exact. The moe test names #5 `Bullet ->` as the known loss.
- New pin `test_fw4r1_g5_runs_after_the_donor_ranking`: a donor whose only segue G5 clears gives no donor at all, and the sibling's `Bertha >` is not promoted in its place.

## RED evidence (20c4e6a, `git archive` scratch copy, `llama.__file__` confirmed inside the copy)
Tests that fail on 20c4e6a:
- `test_fw4r1_no_gain_on_the_last_track` (warrenzevon-2000-05-29 shape): `[3] == []`.
- `test_fw4r1_no_cross_set_gain_from_a_run_on_blob` (gd1987-03-27 blob): `[1, 8, 12, ...] == [1, 12, ...]`.
- The 4 parametrized `test_fw4r1_g5_keeps_a_mark_into_a_title_carrying_a_filler_word` cases (jrad-2016-02-11, littlefeat-1975-09-01, railroadearth-2013-07-12, kellerwilliams-2005-02-12), each missing its real mark.
- (a) and the segue_donor test, which now include Terrapin.

Pins that pass on both 20c4e6a and 0d5165c:
- the tagged cross-set gain (`The Music Never Stopped >`);
- the last-track removal (the radiators medley as the last track);
- G5 after ranking;
- the exact moe and gd88 sets;
- the gd88 Space gain, which is the interior, untagged, same-set gain.

The D&C closers and the wz2000 `> Banter` marks are still cleared, by the (a) and (b) tests and in the arm.

## Measurement (~/.llama-harness/piece4/: cand-f.json, compare-f/, arms-f/, fw4/r1/)
**Arm.** clean 1253, clean-changed 1708, needs-brief 3, needs-llm 654, newly-held 220, still-held 135, still-held-package 1, structure-changed 9.

**Compare vs base:** rc 0. Only outcomes, packaged_exposure, summary and title_rows differ from compare-e.

**Arms:** **BLOCKS MERGE (0)**. The dict is unchanged. Reference reproduction differences fell from 1233 to 1206.

**Row diff cand-e -> cand-f** (`fw4/r1/rowdiff-ef.txt`): 72 rows differ.
- 59 differ in segues/segue_changes only.
- 13 also move clean-changed -> clean and fresh -> reuse.
- No other field, so UNEXPLAINED 0.

**Mark changes, cand-e -> cand-f:** 60 removed, all item-2 gains declined; 15 restored, all from G5's leading-word form. Detail in `fw4/r1/attribution.txt`.

**Removals unchanged.** All 107 of item 2's removals are still removed in cand-f.

**Gains dropped.** 7 by rule (a), 53 by rule (b).
- (a): all 7 are segues into nothing. Declining them is right.
- (b): the vote calls 22 of the 53 right; the other 31 are minority, tie or no-vote, the reviewer's false class.
- My read of the 22 (`fw4/r1/majority-reads.md`):
  - **14 real marks dropped.** 10 of them have equal SHIPPED sets: (b) reads the canonical labels before anchoring and taper. They are furthur-2009-09-19 #9, gd1968-10-12 #5, gd1971-08-14 #24, gd1974-06-23 #19, gd1977-05-01 #14, gd1982-08-08 #23, gd1984-04-17 #9, gd1985-09-15 #9, jrad-2017-04-29 #11 and phil-2006-02-19 #11. The other 4 sit under a wrong shipped set label: discobiscuits-1999-12-30 #16, discobiscuits-2009-07-01 #9 and #17, gd1990-07-14 #8.
  - **2 right drops.** gd1973-11-21 #13 and gd1974-07-29 #11 are Weather Report Suite's internal `->`, and set 2 opens next.
  - **6 unclear:** gd1987-04-19 #21, lf1976-02-14, lf1978-06-11, rre2014-02-07, sp1994-04-17, um2005-12-31.

**G5 (leading-word form).** G5 now removes 23 marks, down from 33.
- **10 restored:**
  - all 5 real marks: Terrapin (D&C 2015), jrad-2016-02-11 #5, kellerwilliams-2005-02-12 #23, littlefeat-1975-09-01 #6, railroadearth-2013-07-12 #17;
  - 4 flows into filler tracks the tape itself carries: derektrucks-2000-03-15 #10 and #20, littlefeat-1975-10-31 #17, littlefeat-1978-10-14 #12;
  - 1 false mark reopened: warrenzevon-1994-02-07 #16 (`... > Roland Chorale Outro.` inside the track).
- **5 new gains, also from G5's leading-word form.** Each donor flag is now kept, and the own alignment adds the mark in the same set:
  - deepbananablackout-2003-11-26 #12 (> `Rocker intro`);
  - jackiegreene-2009-06-06 #7 and radiators-2007-03-31 #1 and #3, all three carrying the track's own `>`;
  - philleshandfriends-2007-11-05 #23 (> `audience, donor rap, intros`, a filler track).
- warrenzevon-1976-06-20 #7 and warrenzevon-1986-06-12 #6 stay removed: the own alignment ends them on the unmarked `[band intros and banter]` / `[Dr. Babyhead intro]` item.

**Totals vs cand-d.**
- Fresh briefs: **+370**, down from +383.
- Rows differing: 1035.

**Real marks lost: 6 + 0 = 6** (not the 6 + 5 the findings expected), plus the 14 real gains that (b) declines.
- The 6 are item 2's, unchanged: moe, disco x2, umphreys, thedead-2009, sts9.
- G5 loses none now.

## Concerns
1. **(b) reads the pre-anchoring labels.** Using the SHIPPED sets instead (decided after anchoring and taper) would keep the 10 same-set real marks. It would newly decline 5 kept gains that cross a shipped break: gd1970-11-06 #42 (1/2), gd1971-12-15 #24 Lovelight (5/5), gd1975-06-17 #10 (2/13), gd1990-03-15 #10 (1/11) and gd1993-08-22 #8 (1/9). That figure is predicted from the cand-f data, not run as an arm. It needs `donor_segues`' add guard to move after the shipped set decision, so it needs a ruling. I kept `result.sets` as specified.
2. A wrong shipped set label (setlist.fm or jerrybase) also defeats (b) on 4 real marks. This is not fixable inside FW4.
3. G5's leading-word form reopens 1 false mark (wz1994-02-07 #16) and keeps 5 flows into filler tracks that the tape carries, which is the ruled class. That is weighed against recovering 5 real marks.
4. Out of scope, noted only:
   - The LLM `align_structure` branch replaces item 2's segues wholesale.
   - Pooled marks still feed `correspondence._merge_legal` and that prompt.

No writes outside the allowed paths. No subagents, stash, merge or push.
