# tfw4-impl handback: FW4 (G5 + own alignment over pooling)

## Status
**DONE_WITH_CONCERNS.** Both items are built test-first, committed one per item, and the suite is green. No change is UNEXPLAINED: every differing row differs only in segue fields and their knock-ons, and every changed mark is traced to its mechanism.

The concern is scale. Item 2, built as the brief specifies, reaches **1055 shows (861 delivered)**, where the brief anticipated about 11 marks on 5 shows. It gains 2124 marks and removes 107. The gains are overwhelmingly corroborated:
- 92% carry the chosen recording's own `>` and/or the track's own `>` tag.
- The all-parses vote calls 1871 right and 34 wrong.

It also has knock-on costs:
- 383 more briefings go reuse -> fresh. These are LLM brief calls in the bulk apply.
- 6 real marks are lost to errors in the donor's own alignment.

The operator should see this before Task 23. See Concerns.

## Commits (branch held-backlog-junk-filter, base 8162620)
- `c6b0c5c` fix(gather): no segue transfer from a donor item followed by filler or nothing (FW4 G5). Suite 5450 passed, 1 skipped, 8 deselected.
- `20c4e6a` fix(gather): the segue donor's own alignment wins over exact-title pooling (FW4 item 2). Suite 5457 passed, 1 skipped, 8 deselected.

Both commit messages name the test command and carry the trailer.

## Suite
`./.venv/bin/python -m pytest -q -p no:cacheprovider` at 20c4e6a: **5457 passed, 1 skipped, 8 deselected**. `llama.__file__` is `/Users/shawn/projects/llama/.claude/worktrees/junk-filter/packages/llama/src/llama/__init__.py`.

## Where each change sits and why

### G5: `stages/gather.py`, `_drop_dangling_segues`, called in `build_canonical`'s setlist.fm branch
- It clears the segue flag of an item that is followed, in the donor's own list, by an `is_filler` item or by nothing.
- It is applied to the ranked donor only, after `rank_parses` picks it, and before `blend_segues`.
- I chose this over editing `blend_segues` because it is narrower:
  - `blend_segues` and `scripts/blind_tag_gapfill.py` are untouched.
  - The donor choice is unchanged. I apply G5 after ranking, not before the segue-bearing filter, so a donor that G5 empties is not swapped for another.
  - It covers every case the ruling names, because item 2 aligns this same G5'd donor. Without that, item 2 would re-add `Ripple > Outro` from the donor's own alignment. A test pins that the donor item 2 aligns carries G5.
- `is_filler`/`_FILLER` are unedited.
- Side reach (noted, not measured): the canonical's item segue flags also feed `correspondence._merge_legal` (`fix --suggest-titles`, operator-confirmed). G5 only removes merge legality across a donor item followed by filler or by nothing.

### Item 2: `stages/gather.py`, new `donor_segues`, plus `CanonicalBuild.segue_donor`
**Shape:**
- `build_canonical` also returns the segue donor as `CanonicalBuild.segue_donor`, with G5 applied and then cleaned exactly as the canonical is (head banner, artist items, footnote markers). It is None on every other path, and None when the donor has no segue left.
- `compute_gather`, right after `result = align(tracks, canonical)`, calls `donor_segues(tracks, result, cb.segue_donor, family_aliases)`. That aligns the donor to the same final tracks with the same `align()`.
- On every track the donor's own alignment matches, the segue is the matched donor item's, by position (a merged track takes its last component's, which is align()'s own rule).
- Tracks it does not match keep the pooled segue.
- Only `segues` is replaced. Sets, `matched`, coverage and conflicts stay the canonical alignment's.
- It is deterministic. There is no threshold and no new constant.

**Why this shape:**
- The blend happens on setlists before the tracks have titles, and the titles come from the cascade, which itself reads the canonical. So the only point where "the donor item align() would match to that track" exists is after the cascade, beside the canonical's own align().

**Left alone:**
- align()'s matching, `rank_parses`, the canonical choice and `blend_segues` itself.
- The no-setlist.fm path and the structure-override path.
- The LLM realignment branch. If `align_structure` wins, its result replaces `result` wholesale, as today. This is narrower, and the replay cannot measure that path.
- Taper-owned shows already ship step 1's segues, so they get item 2's.

**I did not narrow item 2 to "may only remove a pooled mark".** The brief is explicit that the segue "comes from that donor item, by position", and the measured gains are overwhelmingly corroborated. A remove-only variant would ship exactly the 107 removals and none of the 2124 gains. That is a one-line change if the operator wants it.

**Donor variants I measured and rejected:**
I ran three alternatives to the cleaned donor, as uncommitted in-process arms. Each trades about evenly or worse against what I committed:

| variant | real losses avoided | V0 gains given up | of which right/right |
|---|---|---|---|
| V1: raw donor, no cleaning | 1 (umphreys) | 26 | 8 |
| V2: cleaned, filler items excluded | 3 (moe, disco-2005, umphreys) | 57 (and it loses 3 right removals) | 50 |
| V3: raw, filler items excluded | 3 | 81 | 58 |

The switch was reverted. Data: `fw4/var-V*.json`, `var-V*-marks.json`.

## RED evidence (each fails first; run in `git archive` scratch copies with PYTHONPATH shadowing, llama.__file__ confirmed inside each copy)

**On 8162620:**
- (a) `test_g5_dc15_closers_into_outro_or_crowd_transfer_no_mark` gives `['Shakedown Street', 'Brown-Eyed Women', 'The Music Never Stopped', 'Eyes of the World', 'Let It Grow', 'Terrapin Station', 'Drums', 'Space', 'The Wheel', 'Looks Like Rain', 'Sugar Magnolia', 'Ripple']`. The expected list lacks Music Never Stopped, Terrapin, Sugar Magnolia and Ripple.
- (b) `test_g5_wz00_song_into_banter_transfers_no_mark` gives `['Excitable Boy', "Don't Let Us Get Sick", 'Poor Poor Pitiful Me', "My Shit's Fucked Up", 'Detox Mansion']`. Expected: `['Detox Mansion']`.
- (c) `test_g5_donor_final_item_segue_transfers_no_mark` gives `[..., 'Sugar Magnolia', 'Johnny B. Goode']`. Johnny B. Goode is extra.

**On both 8162620 and c6b0c5c:**
- (d) `test_fw4_radiators_medley_own_alignment_places_no_mark` gives `assert [4] == []`.
- (d) `test_fw4_radiators_own_alignment_by_position_both_ways` gives `assert [3, 4] == [2, 4]`: the medley loses its mark and `City of Refuge>` gains one.
- `test_fw4_gd88_space_takes_the_donors_jam_mark` gives `assert [12, 13, 15, 17] == [12, 13, 14, 15, 17]`.
- `test_fw4_donor_segues_none_is_a_no_op` fails with ImportError, and `test_fw4_segue_donor_carries_g5_and_the_canonical_cleaning` with AttributeError. These two are unit pins of the new API, so their RED is not behavioural.

**Pins (pass before and after):**
- (e) `test_fw4_pooling_stays_the_fallback_where_own_alignment_does_not_cover`. This is the moe-2008-03-07 shape: a donor repeating `Bullet` and `Rebubula`, with the pooled marks on tracks 2/3/7/9/12 corroborated by the tags.
- (f) `test_fw4_gd88_regained_marks_still_ship`: He's Gone, Drums, I Need A Miracle, Watchtower.
- (f) The "real interior segue followed by a real song still transfers" pin sits inside (a) and (b): Eyes > Let It Grow ... Looks Like Rain, and Detox Mansion > Guitar Solo.

All fixtures are verbatim from cached descriptions: deadandco2015-11-20.at4041, WZ2000-04-22.Solo, furthur2011-07-28.avatone, rads2010-10-29.flac16, moe2008-03-07.mk4.nbox, gd88-06-23.dsbd.terrapin-flyer.

The wiring is pinned too: (d), (d2) and the Space test go through `compute_gather`.

## Arm, compare, arms (cand-e at 20c4e6a, `run --all --rekey-overrides`)
- **Tallies:** clean 1240, clean-changed 1721, needs-brief 3, needs-llm 654, newly-held 220, still-held 135, still-held-package 1, structure-changed 9.
  - vs cand-d: clean 1619 -> 1240, clean-changed 1342 -> 1721, needs-brief 4 -> 3, structure-changed 8 -> 9.
- **`compare base cand-e --no-repro-gate`:** rc 0. Baseline reproduces 127/148, the same as before.
  - Files that differ from compare-d: summary, outcomes, packaged_exposure (1485 -> 2005), structure_changed (+motherhips-2010-10-16, plus one row's segue list), taper_changes (2 rows' segue lists), taper_cleared (motherhips' outcome) and title_rows (the sha).
  - Byte-identical: title_changes, flags, holds_delta, needs_llm, venue_changes, briefings, notes, title_sources, drift, closest_calls and the hand-check sample.
- **`short_keep_probe.py arms`:** **BLOCKS MERGE (0)**.
  - The arms dict is identical to d's: changed 1545, files added 2624, same 1447, unchanged 2438, flags-changed 43, added 34, cleared 21.
  - Reference reproduction differences went 218 -> 1233, all new rows `segues differ`. buckethead-2006-03-10 left the list: it now reproduces the reference.
- **Files:** `~/.llama-harness/piece4/cand-e.json` (+ `.log`, `.rc`), `compare-e/` (+ `.log`), `arms-e/` (+ `.log`).

## Row diff cand-d vs cand-e (`fw4/rowdiff.py`, `fw4/rowdiff-e.{txt,json}`)
- **Header:** only `sha` and `generated_at` differ. The slug sets are equal.
- **1063 rows differ:**
  - 672 in `segues` + `segue_changes` only.
  - 385 also in `outcome` + `briefing`.
  - 5 in `segues` + `segue_changes` + `briefing`.
  - 1 in `segues` + `segue_changes` + `outcome` + `would_be`.
- No title, set, break, filename, flag, needs_llm or title_source change on any row.
- **Knock-ons, all explained:**
  - outcome clean -> clean-changed: 382. clean-changed -> clean: 3. The 3 are buckethead-2006-03-10, derektrucksband-2007-07-21 and smashingpumpkins-2007-06-19, where FW3's added marks are removed and the shows reproduce the stored segues.
  - briefing reuse -> fresh: 383. fresh -> reuse: 7. On 4 of the 7, item 2 restores the stored marks that cand-d had dropped: billystrings-2019-01-24, derektrucksband-2004-06-11, greatamericantaxi-2011-06-19 and radiators-2000-12-15.
  - **One knock-on outside the brief's expected list:** motherhips-2010-10-16, a held show, goes needs-brief -> structure-changed (`would_be: needs-brief`). Item 2 gains it 4 marks, all the chosen description's own. `replay._structure_changed` counts segue labels for a held show (replay.py:236-239), so this follows from segues.
- **Decomposition:** cand-d -> cand-e = the G5-only arm (`fw4/g5only.json`, item 2 disabled in-process) ∪ item 2. Checked exactly, with no track in both. The final arm equals the pre-commit wip arm row for row.

## Per class (full per-show table: `~/.llama-harness/piece4/fw4/pershow.md`, 1063 rows)
| class | shows | marks removed | marks gained | in FW3 71 (shows; marks) | outside the 71 |
|---|---|---|---|---|---|
| G5 | 19 (16 delivered, 3 packaged) | 33 | 0 | 3 shows; 9 removed | 16 shows; 24 removed |
| item 2 | 1055 (861 delivered, 120 packaged, 70 held, 4 briefed) | 107 | 2124 | 31 shows; 14 removed, 68 gained | 1024 shows; 93 removed, 2056 gained |
| total | 1063 | 140 | 2124 | 32 of the 71 shows touched; 39 untouched | 1031 |

- The target 11 marks on 5 shows (tfw3-rev Minor 1) are all removed: buckethead-2006-03-10 #9 #11 #12, derektrucksband-2007-07-21 #4, joerussosalmostdead-2019-03-02 #12, radiators-2010-10-29 #4 #10 #17, warrenzevon-1976-10-13 #1 #6 #11.
- G5's expected 8 false marks are all removed: D&C 2015 x3, furthur `Johnny B Goode`, warrenzevon-2000 x4.
- **G5 in the 71:**
  - deadandcompany-2015-11-20 -4 (+1 from item 2: `New Minglewood Blues >`).
  - furthur-2011-07-28 -1 (+6 from item 2).
  - warrenzevon-2000-04-22 -4.
- **G5 outside the 71:** derektrucksband-2000-03-15 -2, joerussosalmostdead-2016-02-11 -1, kellerwilliams-2005-02-12 -1, littlefeat-1975-09-01 -1, littlefeat-1975-10-31 -1, littlefeat-1978-10-14 -1, philleshandfriends-2001-07-21 -1, philleshandfriends-2012-04-29 -1, railroadearth-2013-07-12 -1, stevekimockband-2005-10-07 -1, thedead-2015-07-05 -1, warrenzevon-1976-06-20 -4, warrenzevon-1986-06-12 -1, warrenzevon-1992-01-05 -1, warrenzevon-1994-02-07 -4, warrenzevon-2000-12-02 -2.
- **Mechanism, outside and inside the 71:**
  - G5 is the only difference between the G5-only arm and 8162620.
  - For item 2, all 2231 changed tracks were replayed (`fw4/mech.py` -> `mech.json`). Each is a track the donor's own alignment matches with a segue different from the pooled one.
  - Of the 2124 gains, 1185 are on tracks the setlist.fm alignment never matches. The other 939 are on tracks it matches where pooling transferred nothing or the wrong occurrence, typically because setlist.fm's name differs from the taper's (`Minglewood Blues` vs `New Minglewood Blues`, `I'm Gonna Run to the City of Refuge` vs `City of Refuge`).

## Real marks lost, hand-checked (every one; detail in `fw4/handchecks.md`)

**G5: 5 real song-to-song marks lost.** In 4 of them, `is_filler` matches a word inside a real song title or a music track:
- deadandcompany-2015-11-20 #11 Terrapin > Drums (`Drums Intro`). This is the expected one, and it is in the 71.
- joerussosalmostdead-2016-02-11 #5 Eyes Of The World > `Cumberland Blues (Band Intros)`.
- kellerwilliams-2005-02-12 #23 Up in my Cadillac > `Boomwhacker/Toy loop W/Crowd Response chant`.
- littlefeat-1975-09-01 #6 Dixie Chicken > `Tripe Face Boogie / crowd`.
- railroadearth-2013-07-12 #17 The Forecast > `River Intro Jam` (3/4 descriptions).

**G5: 6 more in the ruled class, but the tape itself carries the filler track and the taper marked the flow into it:**
- derektrucksband-2000-03-15 #10, #20 (`> Detuning`).
- littlefeat-1975-10-31 #17 and littlefeat-1978-10-14 #12 (`> Band Intros`).
- thedead-2015-07-05 #17 (`> Crowd Doing Not Fade Away`).
- philleshandfriends-2001-07-21 #19 (`> Crowd`).

**G5: 1 unclear:** warrenzevon-1986-06-12 #6. The other 21 are right.

**Item 2: 6 real marks lost, all from the donor's own alignment landing on the wrong item:**
- moe-2008-03-07 #5 `Bullet ->` (5/5 descriptions). The sibling donor's set-2 `Intro` takes tape track 1 `intro`.
- discobiscuits-2005-12-31 #14 `Reactor` (> Basis for a Day). A repeated title; the alignment takes the wrong occurrence.
- discobiscuits-2006-12-31 #15 `Basis For A Day` (4/4). Wrong occurrence.
- umphreysmcgee-2007-04-21 #10 `Pay the Snucka >`. The donor is the chosen description. The head-banner strip removes its first `~intro~`, so track 1 takes the set-2 `~intro~`.
- thedead-2009-04-24 #12 `alabama getaway > ... jam >` (in the 71). The sibling donor writes no `>` there, while the chosen description, the track's tag and nak100 all mark it.
- soundtribesector9-2003-07-04 #3 `Breathe In >`. The chosen description lists the show twice, and its unmarked `3+4. Breathe In` takes the track.

**Item 2: 1 unclear:** ratdog-2007-07-21 #9 Bird Song (2 descriptions mark it; the chosen and the donor do not). The other 100 are right: 91 medley ends that no description marks, and 9 read by hand.

## Gains (item 2): 2124, not hand-checked one by one
- **Corroboration:** 1944 (92%) carry the chosen's own mark (1762) and/or the track's own `>` tag (1499). 489 restore a mark the stored show.json ships today.
- **Votes (fw3 method, `fw4/i2-vote.json`, `fw4/verdict.py`):**

| vote | right | wrong | unclear |
|---|---|---|---|
| all parses | 1871 | 34 | 219 |
| notating parses only | 1925 | 26 | 173 |
| independent notating (donor excluded) | 1095 | 40 | 989 |

- **Random sample of 12** (`fw4/gain-sample.txt`): all 12 carry the chosen's own mark. None reads as false.
- **7 gains land on a show's last track**, a segue into nothing: gratefuldead-1967-10-22 #7, gratefuldead-1979-02-03 #12, greenskybluegrass-2016-10-31 #17, robertrandolphandthefamilyband-2005-02-20 #14, smashingpumpkins-2000-02-05 #13, smashingpumpkins-2007-06-06 #33, warrenzevon-2000-05-29 #11.
- **26 are wrong on the notating vote**, mostly one donor against many lists (e.g. gratefuldead-1991-04-01 Bird Song 1/21, gratefuldead-1990-03-15 Don't Ease Me In 1/11 into `Tuning`). Listed by `verdict.py --list`.

## Concerns
1. **Scale and spend.** Item 2 touches 1055 shows (861 delivered) where the ruling expected a targeted fix of 11 marks. It moves 382 rows clean -> clean-changed and 383 briefings reuse -> fresh, which is that many more LLM brief calls in the bulk apply. Size it with pacing. The effect is strongly net positive on every vote, and the gains are mostly the chosen recording's own notes, so this is steering-consistent ("tape notes presumed correct"). The operator may still want it, gate it, or take the remove-only variant: 107 removals, no gains, about 7 real or unclear losses.
2. **The donor's own alignment can misalign:**
   - A tape's leading filler track can take a later filler item (`Intro`, `~intro~`) and move the pointer past real songs (moe, umphreys).
   - A repeated title can resolve to the wrong occurrence (disco x2, sts9).
   - A sibling donor can contradict the chosen description (thedead-2009).
   - The cost is 6 real marks. I measured three donor variants and none is clean (table above).
3. **G5's cost is 5 real marks, not 1.** Four come from `is_filler` matching inside real titles: `(Band Intros)`, `/ crowd`, `Crowd Response chant`, `River Intro Jam`. Another 6 marks are flows into filler tracks the tape itself has, which is the ruled class but the taper's literal notation. `is_filler` was left alone per the brief.
4. The motherhips-2010-10-16 needs-brief -> structure-changed move is a segue knock-on outside the brief's expected list. It is explained (replay's held-show structure-changed rule counts segues), but it is listed here so it is not missed.
5. The LLM `align_structure` branch is unchanged. Pooled marks still reach its prompt, and its segues replace item 2's when it wins. This path is not measurable offline.

## Files
- **Code:** `packages/llama/src/llama/stages/gather.py`.
- **Tests:** `packages/llama/tests/test_stage_gather.py`. The G5 tests sit after the FW3 donor tests; the item 2 tests are at the end of the file.
- **Arm outputs:** `~/.llama-harness/piece4/cand-e.json` / `.log` / `.rc`, `compare-e/`, `arms-e/`.
- **Analysis** (`~/.llama-harness/piece4/fw4/`):
  - `handchecks.md`, `pershow.md`, `rowdiff-e.{txt,json}`
  - marks: `g5-marks.json`, `i2-marks.json`, `e-marks.json`
  - votes and mechanism: `g5-vote.json`, `i2-vote.json`, `mech.json`, `gain-sample.txt`
  - attribution and exploration arms: `g5only.json`, `wip.json`, `var-V{1,2,3}.json`
  - probe scripts: `probe.py`, `probe2.py`, `mech.py`, `vote.py`, `verdict.py`, `marks.py`, `near.py`, `rowdiff.py`, `run_noitem2.py`
- No writes to ~/.llama, the station or the main checkout. No subagents. No stash, merge, push or branch switch. The exploration switch was never committed, and the tree is clean at 20c4e6a.


---

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


---

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
