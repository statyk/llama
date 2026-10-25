# tfw3-impl handback: FW3 (A segue donor + B M1 apostrophes)

## Status
**DONE_WITH_CONCERNS.** Both items are built test-first and committed, and the suite is green. The measurement found **no UNEXPLAINED change**: 71 rows differ, only in the expected fields, and all 71 are in the expected mechanism class. The concern is quality. Fix (A) gains 328 segue marks and loses none. The description vote calls many of the gained marks false, though that vote is itself biased (see Concerns). I fixed none of it, per the brief.

## Commits (on held-backlog-junk-filter, base eacad39)
- `9873f47` fix(gather): rank the segue donor only among segue-bearing LMA parses (FW3 A). `stages/gather.py` build_canonical's setlist.fm branch: the donor candidates are now `p.source != "setlist.fm" and any(i.segue for i in p.parsed.items)`. Nothing else changed: not the canonical choice, `rank_parses`, `blend_segues`, align() or the no-setlist.fm path. 3 tests sit beside the corroboration tests in `packages/llama/tests/test_stage_gather.py`.
- `8162620` fix(replay): fold the modifier-letter apostrophes U+02BB and U+02B9 (FW3 B, FW2 M1). `replay.py` `_APOSTROPHES` gains `ʻ`/`ʹ` -> `'`. The comment and docstring that list the fold are updated. There is 1 parametrized test (2 cases) in `packages/llama/tests/test_replay.py`.

## Suite
`./.venv/bin/python -m pytest -q -p no:cacheprovider`: **5447 passed, 1 skipped, 8 deselected**, at 8162620. It was 5445 at 9873f47. `llama.__file__` resolves inside the worktree.

## RED evidence
- A, test 1 `test_build_canonical_segue_donor_skips_a_closer_in_count_parse_with_no_segue` on eacad39 code: `AssertionError: assert [] == ['Bertha', 'S...ated Prophet']`. It passes after the fix.
- A, tests 2 (`..._no_segue_bearing_lma_parse_leaves_setlistfm_unchanged`) and 3 (`..._segue_donor_best_by_count_is_unchanged`) are pins, as the brief specifies. They pass both before and after the fix.
- B, `test_fw3_modifier_letter_apostrophes_fold[ʻ]` / `[ʹ]` on the old code: `assert 'the reprise is notʻlisted' == 'the reprise is not listed'` (and the same for ʹ). Both pass after the fix. The test also asserts that `briefing_reusable` refuses with `says 'not listed' in cautions`.

## Arm, compare, arms (cand-d at 8162620, `run --all --rekey-overrides`)
- Tallies: clean 1619, clean-changed 1342, needs-brief 4, needs-llm 654, newly-held 220, still-held 135, still-held-package 1, structure-changed 8. Against cand-c2, only clean and clean-changed move: 1653 -> 1619 and 1308 -> 1342 (34 rows).
- `compare base cand-d --no-repro-gate`: rc 0. Baseline reproduces 127/148, the same as c2. Against compare-c2, only summary, outcomes, packaged_exposure (1440 -> 1485) and title_rows (the sha only) differ. title_changes, flags, holds_delta, needs_llm, structure_changed, taper_*, venue_changes, briefings and notes are byte-identical.
- `short_keep_probe.py arms`: **BLOCKS MERGE (0)**. The arms dict is identical to c2's: changed 1545, files added 2624, same 1447, unchanged 2438, flags-changed 43, added 34, cleared 21. Reference reproduction differences went 148 -> 218, all 70 new rows `segues differ`. The 71st show, gratefuldead-1988-06-23, was already listed for its de-doubling differences. No other line changed.

## Row diff cand-c2 vs cand-d (`~/.llama-harness/piece4/fw3/rowdiff.{py,txt,json}`)
- Header: only `sha` and `generated_at`. The slug sets are equal.
- **71 rows differ**:
  - 37 differ in `segues` + `segue_changes` only.
  - 34 differ in `segues` + `segue_changes` + `outcome` (clean -> clean-changed) + `briefing` (reuse -> fresh).
  - No other field differs: no title, set, break, filename, flag, needs_llm or title_source change. **UNEXPLAINED: 0.**
- By state: 58 delivered, 7 packaged, 6 held.
- Mechanism, checked for all 71 by replaying each under this tree (shadow + rekey, as `run` does) and logging build_canonical's `rank_parses` calls (`fw3/segevidence.py`):
  - setlist.fm won the canonical on 71/71.
  - The old count-only donor carried 0 segues on 71/71.
  - The new donor carries >0 on 71/71.
  - The replay's segues equal cand-d's on 71/71 (asserted).
  - The fix cannot act on any other show: when the old donor had any segue, it is still the max of the filtered subset.

## Segue table (`fw3/segtable.txt`: all 328 changed tracks; `fw3/pershow.md`: per show)
Method: t22-seg's vote, i.e. align() of the replayed tracks against every description parse, k marking / n matching. "Own" is the chosen description's flag plus the track's own `>`/`->` tag. Mechanical verdict: the change agrees with the majority -> right, unless own evidence contradicts it -> unclear. It opposes the majority -> wrong, unless own evidence supports it -> unclear. A tie or n=0 -> unclear.

I also report a second vote over **notating parses only**, meaning parses carrying at least one segue. A description with no `>` anywhere votes "no segue" on every track, and that is absence of notation, not evidence. The second vote is biased the other way: the donor itself always notates.

- **Gained 328, lost 0** (by construction every c2 mark survives; c2 had none from the blend on these shows).
- t22-seg vote: **right 133, wrong 78, unclear 117**.
- Notating vote: **right 194, wrong 24, unclear 110**. Of the 78 "wrong", 48 become unclear and 6 become right; 24 stay wrong on both votes.
- Description-majority agreement over voted tracks, ties excluded:
  - All parses: c2 990/1217 -> d **1044/1217** (+54).
  - Notating parses: 769/1151 -> 1022/1151.
- The changed tracks break down as follows:
  - The donor's own alignment marks the track on 292.
  - It matches the track but does not mark it on 13.
  - It does not match the track on 23. On these 36, `blend_segues`' exact-title pooling took the mark from another occurrence.
  - 7 marks land on the show's **last track**, a segue into nothing: buckethead-2006-03-10 #12, deadandcompany-2015-11-20 #17 `E: Ripple` (`Ripple > Outro`), furthur-2011-07-28 #23, smashingpumpkins-1993-08-12 #15, smashingpumpkins-1996-04-24 #19, smashingpumpkins-2007-10-04 #25, warrenzevon-1976-10-13 #11.
- **gratefuldead-1988-06-23 regains He's Gone (8/9), Drums (8/8), I Need A Miracle (8/8) and All Along The Watchtower (8/8).** Space is still missing, as expected (donor terrapin-flyer). He's Gone grades unclear only because the chosen description's own parse matched it unmarked.
- The shows that are all or mostly "wrong" on the t22-seg vote:
  - bobweir-2012-04-27 (10/10). The donor is a careful `>`-notated taper list (`Lost Sailor >`, `Playing > Dark Star > Josephine > Other One > Days Between`). Its siblings carry no notation, so by the tape-notes-presumed-correct steering these are plausibly real.
  - deadandcompany-2015-11-20 (12/12). The donor writes `>` after nearly every track, including `Sugar Magnolia >` before `Crowd` and `Ripple > Outro`, so this one looks like track-flow notation and largely false.
  - deadandcompany-2017-06-09 (9/9). The donor's own align does not place them (0/3), which points to a pooling transfer.
  - furthur-2011-07-28 (5 wrong on both votes).
  - radiators-2010-10-29 and warrenzevon-1976-10-13 (3 each, `[interview]` and medley titles).
  - buckethead-2006-03-10 (3, medley titles).
  - The 1-3-mark Smashing Pumpkins, GY!BE, dumpstaphunk and ryanadams rows.
- Shows that are clearly right: deadandcompany-2023-05-08 (8/8), gratefuldead-1985-07-13 (9/10), gratefuldead-1990-12-12 (10/13), joerussosalmostdead-2021-12-03 (10/10), moe-2008-06-15 (7/7), furthur-2012-09-22 (7/7), joerussosalmostdead-2014-08-01 (6/6), umphreysmcgee-2008-06-13 (6/6), and the other GD rows.

Per-show (gained / lost / t22-seg right-wrong-unclear / notating right-wrong-unclear / donor change):

| show | state | gained | lost | right/wrong/unclear (t22-seg vote) | (notating vote) | donor change (items, segues), target |
|---|---|---|---|---|---|---|
| billystrings-2019-02-16 | delivered | 2 | 0 | 0/0/2 | 0/0/2 | lma:billystrings2019-02-16.mk4v.flac16 (21, 0) -> chosen (27, 4), 12 |
| bobweir-2012-04-27 | delivered | 10 | 0 | 0/10/0 | 0/0/10 | chosen (19, 0) -> lma:bw2012-04-27.nak300.bleich-sirmic... (22, 11), 19 |
| buckethead-2006-03-10 | delivered | 3 | 0 | 0/3/0 | 0/3/0 | lma:Buckethead2006-03-10.flac16 (8, 0) -> chosen (25, 13), 12 |
| campervanbeethoven-2003-02-28 | delivered | 1 | 0 | 0/0/1 | 0/0/1 | chosen (48, 0) -> lma:CVB2003-02-28.sbd (99, 2), 48 |
| cracker-2001-09-01 | delivered | 1 | 0 | 0/0/1 | 1/0/0 | lma:cracker2001-09-01.Lazor.Master.16... (26, 0) -> chosen (14, 1), 14 |
| darkstarorchestra-2008-02-17 | held | 4 | 0 | 0/0/4 | 0/0/4 | chosen (30, 0) -> lma:dso2008-02-17.cm1k.flac16 (26, 5), 18 |
| davidnelsonband-2007-09-07 | held | 3 | 0 | 0/0/3 | 0/0/3 | chosen (14, 0) -> lma:dnf2007-09-07.mk4.nbox.flac24 (15, 5), 14 |
| deadandcompany-2015-11-20 | delivered | 12 | 0 | 0/12/0 | 0/0/12 | chosen (18, 0) -> lma:deadandco2015-11-20.at4041-bp4025... (23, 16), 17 |
| deadandcompany-2017-06-09 | delivered | 9 | 0 | 0/9/0 | 0/0/9 | lma:dead2017-06-09.ccm41_flac24 (21, 0) -> lma:dco2017-06-09.aud.flac24 (34, 11), 18 |
| deadandcompany-2023-05-08 | delivered | 8 | 0 | 8/0/0 | 8/0/0 | lma:deadco2023-05-08.jdwtyl (21, 0) -> chosen (27, 9), 20 |
| deadandcompany-2023-06-07 | delivered | 1 | 0 | 0/0/1 | 1/0/0 | lma:deadco2023-06-07.SchoepsMK21-MixP... (20, 0) -> chosen (23, 4), 17 |
| deadandcompany-2023-07-16 | delivered | 7 | 0 | 0/5/2 | 7/0/0 | lma:deadco2023-07-16.jdwtyl (24, 0) -> lma:deadco2023-07-16.soundfield (25, 9), 23 |
| deadandcompany-2025-05-11 | packaged | 2 | 0 | 0/0/2 | 2/0/0 | lma:deadco2025-05-11.MK41.seedy (19, 0) -> chosen (27, 2), 21 |
| derektrucksband-2005-11-13 | delivered | 1 | 0 | 0/0/1 | 0/0/1 | chosen (13, 0) -> lma:dtb2005-11-13.dsm6p.flac16 (26, 3), 14 |
| derektrucksband-2007-07-21 | delivered | 1 | 0 | 0/1/0 | 0/1/0 | lma:dtb2007-07-21.berliner.flac16 (13, 0) -> chosen (24, 3), 13 |
| dumpstaphunk-2011-07-21 | delivered | 2 | 0 | 0/2/0 | 0/0/2 | lma:dumpsta2011-07-21.ck1x-tinybox.flac (11, 0) -> lma:dumpstaphunk2011-07-21 (18, 2), 10 |
| furthur-2009-09-20 | delivered | 6 | 0 | 0/0/6 | 0/0/6 | chosen (21, 0) -> lma:furthur2009-09-20.dsbd.102048.sbe... (20, 9), 21 |
| furthur-2010-02-12 | delivered | 5 | 0 | 4/1/0 | 4/1/0 | lma:furthur2010-02-12.akg1000.nchell.... (23, 0) -> lma:furthur2010-02-12.km184.hughey.10... (21, 5), 23 |
| furthur-2010-11-20 | delivered | 4 | 0 | 0/0/4 | 0/0/4 | chosen (18, 0) -> lma:furthur2010-11-20.158869.MG210.pa... (20, 5), 19 |
| furthur-2011-03-29 | delivered | 7 | 0 | 4/1/2 | 4/0/3 | lma:furthur2011-03-29.akg481.laporte.... (22, 0) -> lma:furthur2011-03-29.akg568ebs.goldb... (20, 7), 21 |
| furthur-2011-07-28 | packaged | 10 | 0 | 0/5/5 | 0/5/5 | chosen (23, 0) -> lma:furthur2011-07-28.avatone-ck1.bry... (23, 16), 23 |
| furthur-2012-09-22 | delivered | 7 | 0 | 7/0/0 | 7/0/0 | lma:furthur2012-09-22.furthur2012-09-... (21, 0) -> chosen (22, 9), 21 |
| godspeedyoublackemperor-2002-01-22 | delivered | 3 | 0 | 0/3/0 | 0/0/3 | lma:gybe2002-01-22.alt (9, 0) -> lma:gybe2002-01-22.mtx (23, 7), 9 |
| gratefuldead-1982-04-19 | delivered | 9 | 0 | 2/0/7 | 8/0/1 | chosen (22, 0) -> lma:gd1982-04-19.sbd.clugston.2316.shnf (22, 10), 22 |
| gratefuldead-1985-06-28 | delivered | 8 | 0 | 7/0/1 | 7/0/1 | lma:gd1985-06-28.nakcm304.suraci.7960... (18, 0) -> chosen (17, 11), 18 |
| gratefuldead-1985-07-13 | delivered | 10 | 0 | 9/0/1 | 9/0/1 | lma:gd1985-07-13.nak300.tonys.77489.s... (20, 0) -> lma:gd1985-07-13.senn441.mccue.ford.8... (20, 11), 20 |
| gratefuldead-1986-03-24 | delivered | 6 | 0 | 4/1/1 | 4/1/1 | lma:gd1986-03-24.nak300.mandel.79610.... (19, 0) -> lma:gd1986-03-24.148732.mtx.tobin.fla... (18, 8), 21 |
| gratefuldead-1986-12-30 | delivered | 11 | 0 | 3/1/7 | 10/0/1 | lma:gd1986-12-30.137978.sbd.miller.fl... (26, 0) -> lma:gd1986-12-30.171472.mtx.tobin.fla... (29, 13), 27 |
| gratefuldead-1988-06-23 | delivered | 4 | 0 | 3/0/1 | 3/0/1 | chosen (20, 0) -> lma:gd88-06-23.dsbd.terrapin-flyer.13... (20, 8), 19 |
| gratefuldead-1988-07-02 | delivered | 11 | 0 | 0/0/11 | 11/0/0 | lma:gd1988-07-02.140674.FOB.Neumann.S... (21, 0) -> lma:gd1988-07-02.nak100.unknown.32636... (21, 11), 21 |
| gratefuldead-1988-09-03 | delivered | 8 | 0 | 7/0/1 | 8/0/0 | lma:gd1988-09-03.136750.upg-sbd.tobin... (20, 0) -> lma:gd1988-09-03.150549.FOB.Nak.700.d... (20, 8), 20 |
| gratefuldead-1990-03-15 | delivered | 5 | 0 | 5/0/0 | 5/0/0 | lma:gd1990-03-15.senn-hubbard.cpb.836... (22, 0) -> lma:gd1990-03-15.28293.sbeok.shnf (20, 8), 22 |
| gratefuldead-1990-12-12 | delivered | 13 | 0 | 10/3/0 | 10/2/1 | lma:gd1990-12-12.140071.FOB.Schoep.Ka... (22, 0) -> lma:gd1990-12-12.149544.ultramatrix.s... (22, 14), 22 |
| jackiegreene-2010-05-29 | packaged | 1 | 0 | 1/0/0 | 1/0/0 | lma:jackiegreene2010-05-29.Furthur-An... (10, 0) -> chosen (14, 1), 11 |
| joerussosalmostdead-2014-08-01 | delivered | 6 | 0 | 6/0/0 | 6/0/0 | lma:jrad2014-08-01.461.bsc1.littlebox (11, 0) -> lma:jrad2014-08-01.cmc621.sbd.matrix.... (13, 8), 13 |
| joerussosalmostdead-2015-12-31 | delivered | 3 | 0 | 3/0/0 | 3/0/0 | lma:JRAD2015-12-31.schoepsMK4V.travit... (26, 0) -> lma:jrad2015-12-31.cmc65.sbd.matrix.f... (62, 14), 27 |
| joerussosalmostdead-2016-12-02 | delivered | 1 | 0 | 0/0/1 | 1/0/0 | lma:JR2016-12-02.16bit (25, 0) -> lma:jrad2016-12-02.dpa4011.flac16 (26, 16), 22 |
| joerussosalmostdead-2019-03-02 | delivered | 8 | 0 | 7/1/0 | 7/1/0 | lma:jrad2019-03-02 (19, 0) -> chosen (46, 12), 17 |
| joerussosalmostdead-2019-08-29 | delivered | 7 | 0 | 2/1/4 | 5/1/1 | lma:jrad2019-08-29.travitz.litz.schoe... (16, 0) -> lma:jrad2019-08-29.RedRocksAmpitheatre (17, 9), 15 |
| joerussosalmostdead-2021-12-03 | delivered | 10 | 0 | 10/0/0 | 10/0/0 | lma:jrad2021-12-03.ck930.flac24 (16, 0) -> lma:jrad2021-12-03.akg61.stearns.flac16 (17, 11), 16 |
| littlefeat-1977-08-02 | held | 2 | 0 | 1/0/1 | 2/0/0 | lma:lf1977-08-02.sbd.135985.sbeok.fla... (18, 0) -> chosen (20, 2), 13 |
| littlefeat-1978-06-18 | delivered | 1 | 0 | 0/1/0 | 0/0/1 | chosen (13, 0) -> lma:lf1978-06-18.fm2.lma.plaz.flyingm... (91, 6), 13 |
| moe-2008-06-15 | delivered | 7 | 0 | 7/0/0 | 7/0/0 | lma:moe2008-06-15.FOB_NeumannKM150 (18, 0) -> lma:moe2008-06-15.dpa4021s.v3 (18, 7), 18 |
| motherhips-1995-08-06 | delivered | 2 | 0 | 0/0/2 | 0/0/2 | chosen (28, 0) -> lma:MotherHips1995-08-06 (33, 4), 28 |
| mymorningjacket-2008-06-17 | delivered | 1 | 0 | 0/0/1 | 0/0/1 | chosen (22, 0) -> lma:mmj2008-06-17.oktava.shnf (24, 1), 22 |
| philleshandfriends-1999-08-14 | packaged | 6 | 0 | 1/0/5 | 1/0/5 | lma:paf1999-08-14.122420.dobert.flac (14, 0) -> lma:paf1999-08-14.Nak701s-Baker.13130... (15, 6), 12 |
| philleshandfriends-2004-12-18 | delivered | 8 | 0 | 0/0/8 | 8/0/0 | chosen (22, 0) -> lma:2004-12-18.paf.dsbd.philleshnet.f... (46, 18), 23 |
| philleshandfriends-2005-10-29 | held | 7 | 0 | 2/2/3 | 4/2/1 | lma:paf2005-10-29.paf.nak701.unknown.... (14, 0) -> lma:paf2005-10-29.120964.adk.Wentland... (15, 10), 13 |
| philleshandfriends-2006-07-09 | delivered | 4 | 0 | 4/0/0 | 4/0/0 | lma:paf2006-07-09 (17, 0) -> lma:paf2006-07-09.neumann.clarke.7459... (23, 5), 17 |
| philleshandfriends-2017-11-16 | delivered | 6 | 0 | 5/0/1 | 6/0/0 | lma:paf2017-11-16.akg481 (22, 0) -> chosen (23, 11), 20 |
| radiators-2010-10-29 | delivered | 8 | 0 | 1/3/4 | 5/3/0 | lma:rads2010-10-29.mahoney.FLAC16 (25, 0) -> chosen (37, 16), 27 |
| robertrandolphandthefamilyband-2005-06-04 | delivered | 2 | 0 | 2/0/0 | 2/0/0 | lma:RR2005-06-04.RobertRandolphHunter... (12, 0) -> chosen (13, 2), 11 |
| ryanadams-2008-09-25 | packaged | 3 | 0 | 0/3/0 | 0/0/3 | lma:ra2008-09-25.mc012.flac.16 (26, 0) -> lma:ra2008-09-25.flac24_edited (37, 3), 26 |
| ryanadams-2008-09-27 | delivered | 3 | 0 | 0/0/3 | 0/0/3 | lma:ra2008-09-27.sbd.sd702.flac16 (23, 0) -> chosen (43, 9), 23 |
| smashingpumpkins-1993-08-12 | delivered | 1 | 0 | 0/0/1 | 0/0/1 | chosen (16, 0) -> lma:tsp1993-08-12 (18, 3), 15 |
| smashingpumpkins-1996-04-24 | delivered | 2 | 0 | 0/2/0 | 0/0/2 | chosen (19, 0) -> lma:tsp1996-04-24.Hi8.flac16 (52, 11), 19 |
| smashingpumpkins-1996-07-10 | delivered | 2 | 0 | 0/0/2 | 0/0/2 | chosen (17, 0) -> lma:tsp1996-07-10.dat.flac16 (20, 3), 16 |
| smashingpumpkins-2007-06-19 | delivered | 1 | 0 | 0/1/0 | 0/1/0 | lma:tsp2007-06-19.dpa4061.rob.flac16 (31, 0) -> lma:tsp2007-06-19.mbho.flac24 (34, 2), 31 |
| smashingpumpkins-2007-06-27 | delivered | 1 | 0 | 0/1/0 | 0/0/1 | lma:tsp2007-06-27.aud5 (43, 0) -> lma:tsp2007-06-27.akgck93.flac16 (35, 1), 33 |
| smashingpumpkins-2007-07-27 | delivered | 2 | 0 | 0/2/0 | 0/0/2 | chosen (32, 0) -> lma:tsp2007-07-27.flac16 (34, 2), 31 |
| smashingpumpkins-2007-10-04 | packaged | 3 | 0 | 0/0/3 | 0/0/3 | chosen (26, 0) -> lma:tsp2007-10-04.flac16 (32, 6), 25 |
| tedeschitrucksband-2014-08-15 | held | 1 | 0 | 0/1/0 | 0/0/1 | chosen (17, 0) -> lma:ttb2014-08-15.spyder9.flac16 (14, 1), 17 |
| tedeschitrucksband-2016-08-05 | delivered | 2 | 0 | 0/0/2 | 0/0/2 | chosen (17, 0) -> lma:ttb2016-08-05.akg63.stearns.flac16 (22, 4), 15 |
| tedeschitrucksband-2018-10-10 | delivered | 1 | 0 | 1/0/0 | 1/0/0 | lma:ttb2018-10-10.mk41v.edtyre (17, 0) -> chosen (18, 1), 16 |
| thedead-2009-04-24 | held | 2 | 0 | 1/0/1 | 2/0/0 | lma:dead2009-04-24.mg210.flac16 (18, 0) -> lma:thedead2009-04-24.krall.flac16 (21, 4), 19 |
| tortoise-2023-03-30 | delivered | 3 | 0 | 0/0/3 | 3/0/0 | chosen (33, 0) -> lma:tortoise2023-03-30.m300.flac16 (19, 3), 16 |
| umphreysmcgee-2008-06-13 | delivered | 6 | 0 | 6/0/0 | 6/0/0 | lma:um2008-06-13.sonic (16, 0) -> chosen (19, 6), 10 |
| warrenzevon-1976-10-13 | packaged | 4 | 0 | 0/3/1 | 1/3/0 | lma:wz1976-10-13.wz1976-10-13-WMMS-no... (12, 0) -> chosen (26, 13), 11 |
| warrenzevon-1990-03-02 | delivered | 1 | 0 | 0/0/1 | 0/0/1 | chosen (23, 0) -> lma:zevon1990-03-02.lobster.flac16 (28, 1), 22 |
| warrenzevon-1990-12-08 | delivered | 1 | 0 | 0/0/1 | 0/0/1 | chosen (26, 0) -> lma:wz1990-12-08.flacf (19, 1), 26 |
| warrenzevon-2000-04-22 | delivered | 5 | 0 | 0/0/5 | 0/0/5 | chosen (11, 0) -> lma:WZ2000-04-22.Solo.sbd.Fixed.happy... (55, 5), 10 |

## M1 gate re-measure (`fw3/gate_fw3.{py,txt,json}`, over `ckb/15a/dump.jsonl`, compared row by row to `fw2/gate_fw2.json`)
- Refused 1014/1014 (fw2: 1014/1014). Reuse arm 901/901 (fw2: 901/901). Reusable 0.
- 0 rows lose a term, 0 gain a term, 0 reasons change, 0 newly reusable. **Unchanged.**
- One dump briefing contains U+02BB: davidnelsonband-2014-01-16 (`ʻĪao Theater`, a Hawaiian ʻokina at the start of a word, not glued after a negation). Its verdict is unchanged.

## Concerns
1. **Fix (A) adds marks the description vote calls false.** On t22-seg's own method it is net positive (+54 agreement over 1217 voted tracks; right 133 > wrong 78), but 78 single marks are judged wrong. 24 of those are wrong even on the notating-only vote, and 7 sit on a show's last track.
   - The false marks come from two pre-existing behaviours that the fix now reaches more often:
     - (i) A donor that uses `>` as track-flow notation (`X > Outro`, `> Crowd`). `blend_segues` trusts any donor's flags.
     - (ii) `blend_segues` pools by exact title, so a donor much longer than the tape (55, 62, 91 or 99 items against targets of 10-48) or one that repeats a title can transfer a mark from another occurrence (36 tracks).
   - Both are outside the brief's scope: `blend_segues` and `rank_parses` were frozen. I changed neither. The operator should decide whether (A) ships as is or waits for a donor-quality guard, for example a donor item count near the target or no mark on the final item.
   - 58 of the 71 shows are delivered, so a re-process would ship these marks. They reach the manifest and, on the 34 reuse -> fresh rows, the briefing LLM.
2. **The verdict rule is mechanical.** t22-seg judged by hand; I did not. My rule reproduces its calls on 1988-06-23 except He's Gone, which I grade unclear because the chosen parse's alignment matched it unmarked. The t22-seg vote also counts no-notation descriptions as "no", which inflates "wrong". That is why both votes are reported.
3. Brief ambiguity: test (3) says "identical to today". I pinned it as the segue output equal to the segue-bearing chosen parse's marks, which is what today's code gives.

## Files
- Code: `packages/llama/src/llama/stages/gather.py`, `packages/llama/src/llama/replay.py`. Tests: `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_replay.py`.
- Arm and outputs: `~/.llama-harness/piece4/cand-d.json` (+ `.log`, `.rc`), `compare-d/` (+ `compare-d.log`), `arms-d/` (+ `arms-d.log`).
- FW3 analysis: `~/.llama-harness/piece4/fw3/` contains rowdiff.py/.txt/.json, segevidence.py/.txt/.json, segtable.py/.txt, pershow.md and gate_fw3.py/.txt/.json.
- No writes to ~/.llama, the station or the main checkout. No subagents. No stash, merge or push.
