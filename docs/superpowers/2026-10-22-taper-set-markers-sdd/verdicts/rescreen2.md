VERDICT: NO RULE DEFECT

rescreen2: re-screen of what moved between acceptance run 1 (22f565a) and run 2 (9388d09). Read-only. Scratch and scripts are in ~/.llama-harness/piece2/accept2/work/rescreen2/ (dump.py, probe.py, cov.py, dump.txt, probe.json).

Evidence method. I re-ran the candidate's replay_show in-process for all 47 rows (30 segues-changed rows and 17 lost owners), with llama.taper.decide_taper wrapped to record the arguments gather actually passes (today_reaches_llm, has_encore, reason, owned). llama.__file__ was asserted to be inside the worktree. I wrapped gather.align for step-1 coverage on 3 rows. Segue reality was checked against the taper's track tags, the description and, where the tape gave no marker, the cached setlist.fm. The tier logic was re-derived independently from base.json, cand.json and the stored show.json.

## 1. The removals (17 lost owners)

The removals across tiers are exactly the 17 lost owners: songs moved -4, filler -1, provenance only -10 (the other -30 moved to the new tier), held -2 (jackiegreene, soulive), stored-llm -17. No row was added or changed in those tiers.

The rule holds for all 17, checked by the direct probe: placement succeeded, has_encore=False, today_reaches_llm=True, reason `veto: no encore on today's LLM path`, owned=False. Base needs_llm is ["align_structure", "stored alignment llm"] in every case. That is base's own LLM-branch predicate, the same `canonical.items and coverage < threshold` with no anchoring, so G1's predicate is gather's own, as the spec requires.

The result is exactly today for all 17: cand outcome needs-llm with the same needs_llm as base. The only base/cand field differences are `sets`/`filler`, which are cand-only diagnostic fields (base rows never carry them). No shipped field differs.

What each removal gives back (the ruling's measured cost, run-1 owned result against today's stored LLM structure, which stays):
- greenskybluegrass-2013-05-04 [delivered]: COST. The taper's correct `Set I`/`Set II` (1x8 2x13, no encore anywhere, verified in the description) is lost. The LLM's single set 1x21 stays.
- soulive-2001-12-15 [held]: COST. The taper's correct `Set 1`/`Set 2` (1x5 2x5) is lost. The LLM's 1x10 stays. Held anyway (unresolved titles).
- stevekimockband-2005-10-07 [packaged]: labels equal. Run 1's "gained segue" was t11 `One For Brother Mike > Band Intros`, the LAST track. Its `>` is inside the track and there is no next track, so I judge it internal, not real. Nothing real is given back. This disagrees with pre3-llm.
- greatamericantaxi-2010-08-07 [delivered]: GAIN on net. 2 real segues come back (t30 `For Twenty Long Years >`, t34 `Ripple > Jam >`). Run 1's one gain (t25, the merged `Nobody's Fault... > ...` into `Albuquerque`, a comma in the text) was internal.
- leftoversalmon-1997-10-31 [delivered]: GAIN, 12 real segues back.
- newridersofthepurplesage-2006-04-08 [delivered]: GAIN. Encore `Truck Drivin' Man`/`Ripple` kept, plus 2 real segues.
- johnkadlecik-2013-06-22 [packaged]: GAIN. Encore `After Midnight` kept, plus 1 real segue.
- radiators-2010-06-05 [delivered]: GAIN. The 4-track encore is kept, t13 filler is back in set 2, and 1 real segue returns.
- jackiegreene-2011-02-12 [held]: GAIN. Encore `Sugaree` kept.
- yondermountainstringband-2010-07-17 [packaged]: MIXED. `Set 2 intro` is back in set 2 (correct), but the LLM's 8 segues return, and they are spurious (no `>` in the text except the internal `Jam->Follow Me Down`).
- belafleckandtheflecktones-1996-11-09 [delivered]: small COST. 1 spurious LLM segue returns (t14 `Bela solo` into `Bela solo`).
- bobbyleerodgers-2010-01-13, melvinseals-2003-01-25, ryanadams-2006-12-04, stevekimockband-2002-07-03, stevekimockband-2005-10-01, zero-2008-08-08: no shipped difference either way (labels equal, no segue change). They only stop being offline-replayable.

Net: 2 correct taper structures are lost (greensky-2013-05-04 delivered, soulive held), 1 is mixed, and 1 spurious segue returns. Against that, 4 encores are kept and about 18 real segues return.

## 2. The segues-changed tier (30 rows)

Path. All 30 rows are on today's LLM path, so all 30 are covered by D1. The direct probe gives today_reaches_llm=True, owned=True, has_encore=True and reason None for every row. Base needs_llm contains `align_structure` on every row.

leftoversalmon-1997-08-14 is NOT off-path. Its step-1 coverage is 0.69 against a 0.8 threshold (billystrings-2019-01-24 0.714, chuckprophet-2012-01-15 0.783). The 1.0 in its stored structure is the LLM realignment's coverage, not step 1's. The `step1: deterministic` printed on every row is c.step1_alignment, which is step 1's MECHANISM (not jerrybase). It is not "step 1 at or above threshold". That label caused the suspicion, and it is a report-readability issue, not a rule issue. No row in the tier has step 1 off the LLM path, so there is no unexplained segue change. In every row the segues equal step 1's (gather.py: `segue: g for g in result.segues`), per §4 step 3. "before" is [] in every row because base is needs-llm, so the comparison is against the stored LLM structure.

Totals: 120 segues lost and 2 gained.
- Lost: 116 real (taper's `>`/`->` in the track tag and/or description, or setlist.fm) and 4 spurious, where the loss corrects an LLM error.
- Gained: 2, both spurious (internal to a merged track).

Per show (lost real / lost spurious / gained):
- billystrings-2019-01-24: 2/0/0 (t4 `Pyramid Country >`, t19 `10 Degrees... >`)
- chuckprophet-2012-01-15: 0/0/2 spurious. t1 `Feelin Good->...->Sonny Listons Blues` into `Castro Halloween`, and t15 `Look Both Ways->One More Cup Of Coffee->Look Both Ways` into `Temple Beautiful`. The taper writes a COMMA after both. In setlist.fm, `Sonny Liston's Blues` has info `Acoustic` and `One More Cup` has `> "Look Both Ways" reprise`, which is internal. These are step 1's merged-run rule taking an interior component's segue. pre3-llm called them real; I do not agree.
- darkstarorchestra-2009-07-03: 5/0/0 (Truckin' >, Alligator >, Drums >, Space >, Alligator >)
- darkstarorchestra-2009-11-14: 4/0/0 (Playin >, Drums >, Space >, Alligator >)
- deadandcompany-2015-10-29: 3/0/0 (Drums > Space > Other One > Stella; in the description and setlist.fm)
- derektrucksband-2004-06-11: 1/0/0
- greatamericantaxi-2011-06-19: 1/0/0
- greenskybluegrass-2015-01-22: 1/0/0
- hotbutteredrum-2008-10-10: 5/0/0 (t6 `Silas> (oops)` is the taper's own mark)
- joerussosalmostdead-2015-04-22: 3/0/0
- joerussosalmostdead-2015-05-09: 6/0/0
- joerussosalmostdead-2015-05-24: 2/0/0
- joerussosalmostdead-2015-12-12: 5/0/0
- joerussosalmostdead-2016-02-14: 3/0/0
- joerussosalmostdead-2017-01-12: 12/0/0 (the `->` is in the shipped titles)
- joerussosalmostdead-2017-11-09: 11/0/0
- joerussosalmostdead-2021-05-30: 2/0/0
- joerussosalmostdead-2021-12-03: 13/0/0
- joerussosalmostdead-2023-01-26: 6/0/0
- kellerwilliams-2006-01-27: 1/1/0. t1 is real-ish (the text's `Let's Rock >` opener; ambiguous). t20, the second `Mary Jane's Last Dance` into `Birdsong`, is spurious: the text has a comma.
- leftoversalmon-1997-08-14: 1/1/0. t25 `Chinese Song >` is real. t19, the second `Jugband Song` into `Green Thing`, is spurious: the text reads `04 Jugband Song` with no `>`.
- moe-2007-03-24: 3/0/0
- philleshandfriends-2001-11-17: 4/0/0
- radiators-1992-12-06: 4/0/0
- radiators-2000-12-15: 3/0/0
- soundtribesector9-2005-03-26: 1/0/0
- soundtribesector9-2005-03-31: 2/0/0
- stringcheeseincident-2005-03-25: 4/0/0 (t8 `Jam` into `Mountain Song` is real: `Land's End > Mountain Song` in the text)
- umphreysmcgee-2004-11-12: 3/0/0
- umphreysmcgee-2005-09-30: 5/2/0. t2 `Jazz Odyssey` and t13 `Der Bluten Kat` carry no `>` in the text, so the LLM was wrong.

Classification: every change is DESIGNED (§4 step 3: an owned show takes step 1's segues) and falls inside the accepted D1 limitation. The 2 spurious gains are pre-existing step-1 behaviour (base code is identical); they ship only because step 1's segues now ship on these owned LLM-path shows. No rule defect.

## 3. Tier correctness

- All 30 rows: labels before == after, cand taper_owned, base not owned, and the segue-change keys differ. 0 exceptions.
- Provenance only (498): 0 rows whose segue changes differ from before. That covers the 4 base-needs-llm rows (belafleckandtheflecktones-2006-01-21, soundtribesector9-2004-05-01, stringcheeseincident-2000-03-10, tedeschitrucksband-2019-11-11, each with no segue change) and every replayable-base row.
- 0 owned non-held replayable rows are missing from every tier.
- Losses outside the tier, by design: stored-llm owned rows whose LABELS also change sit in songs moved or filler, and their segue losses print only in the `stored-llm shows now replayable` section. There are 6 such rows with 23 losses, which I spot-checked as real: furthur-2011-04-03 (4), joerussosalmostdead-2016-03-25 (10), moe-2004-04-17 (2), soundtribesector9-2005-04-13 (1), thedead-2009-05-02 (1), umphreysmcgee-2005-09-02 (5). This matches the spec's tier definition (labels unchanged); it is not a mis-tier.

## Classes

None are rule defects. Observations:
- O1 (report readability): `step1: <mechanism>` on the segues-changed tier reads as "step 1 not on the LLM path" when it is not. Printing whether today reaches the LLM branch, or step-1 coverage, would remove the confusion.
- O2 (D1 figure): the spec's "157 real segues over 41 of 62" predates G1. After G1 the loss is 143 segues over 36 shows (30 in the tier, 6 label-changed): about 139 real and 4 spurious, plus 2 spurious gained.
- O3 (pre-existing step-1 behaviour): the merged-track rule can flag an interior segue as a segue to the next track (chuckprophet-2012-01-15 t1, t15; also run-1 greatamericantaxi-2010-08-07 t25 and stevekimockband-2005-10-07 t11). This piece did not introduce it.

## Things the operator should look at

1. G1's measured cost: greenskybluegrass-2013-05-04 (delivered) loses a correct taper set 2 and keeps the LLM's single set. soulive-2001-12-15 (held) is the same case. yondermountainstringband-2010-07-17 gets its filler label right again but gets 8 spurious LLM segues back. In return: 4 encores kept (johnkadlecik-2013-06-22, newridersofthepurplesage-2006-04-08, radiators-2010-06-05, jackiegreene-2011-02-12) and about 18 real segues back (mostly leftoversalmon-1997-10-31).
2. D1 as it now stands: 36 owned shows lose about 139 real segues, concentrated in joerussosalmostdead (12 shows, up to 13 each). In almost every case the taper's own track tags still carry the `>`. A re-process of these shows trades the LLM's segues for structure that was already identical (30 rows: labels unchanged). The operator may want to leave the 30 labels-unchanged rows out of any non-held re-processing, since for them the change is segue loss only.
3. Prior pre-screen correction: the 4 "real gained segues" (pre3-llm) are internal to merged tracks, not real segues to the next track.
4. Not examined (unchanged since run 1, outside this re-screen): joerussosalmostdead-2017-11-09 and joerussosalmostdead-2023-01-26 are newly held by vet flags (`research asserts unknown song` x8, `research asserts wrong date`), not by this piece's structure.
