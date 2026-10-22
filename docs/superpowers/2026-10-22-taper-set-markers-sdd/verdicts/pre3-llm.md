VERDICT: RULE DEFECT (2 classes). Both are spec-level wiring gaps that need an operator ruling before the fix: the code does what the spec text says, but section 7's justification does not hold on these rows. (A): 62 rows; 9 cand-better, 44 equal, 7 cand-worse (4 at song level, 3 filler only), 2 unclear. Segues: 171 lost (157 real, 14 spurious), 4 gained (all real).

Scope: pre3-llm, report-3 pre-screen at HEAD 22f565a. (A) covers all 62 rows of `stored-llm shows now replayable`. (B) covers `provenance only` (538). Read-only: nothing committed, nothing written to ~/.llama. Scratch output is in ~/.llama-harness/piece2/accept/work/pre3-llm/: dump62.json and canon62.json (per-track re-replay through `compute_legs`, the step-1 canonical captured by wrapping `gather.align`), segues.tsv, segue_counts.json, vs_text.txt, strata538.json, sample_b.json, viewb.txt, rows_a.txt.

Method (A). I replayed each row again in scratch through `replay.compute_legs`; per-track labels equal cand.json's `sets` on all 62. For each row I compared three things side by side: the stored labels and segues, the candidate's, and the taper's text (the reader's items, plus the description or notes). An automated check matched each non-filler track to the taper's items by `fuzzy_title_eq` (vs_text.txt). For every segue change I checked whether the description or the taper's own track tag carries `>`/`->`/`=>`, and whether the step-1 canonical item carries a segue.

== Classes

D1. RULE DEFECT (spec-level): taper-owned stored-llm shows lose the segues the LLM had recovered, and most of those segues were the taper's own.
- Mechanism. Section 4 step 3 takes segues from step 1's alignment, unchanged. On these rows step 1 is exactly what fell below `align_coverage_threshold`; that is why today's path called `align_structure`. The canonical is setlist.fm first, which mostly carries no segues. `blend_segues` overlays the LMA segues only on exact `normalized` equality, so tag-decorated titles get nothing (`Truckin' (SM) ->`, `Dancing In The Streets # (SM & NA) ->`). The LLM put those segues back. The taper reader splits on segues but `TaperItem` keeps no segue field, so the taper's own `>` marks are thrown away.
- Size. 157 real segues lost on 41 of the 62 shows. Every one is written in the selected recording's description or in the taper's own track tag. The worst rows:
  - joerussosalmostdead-2021-12-03: 13.
  - joerussosalmostdead-2017-01-12: 12 (the description writes `->`/`>` on every one).
  - leftoversalmon-1997-10-31: 12.
  - joerussosalmostdead-2017-11-09: 11.
  - joerussosalmostdead-2016-03-25: 10.
- Where it is invisible. 34 of these 41 shows sit in report 3's `provenance only` tier (132 of the 157 real segues). That tier compares set labels only, so for these rows the tier claim is false (see R1).
- Why this is not as designed in substance. Section 7 justifies the relaxation "only where the shipped structure is wholly the taper's". Segues are not the taper's on a taper-owned show: they come from the very alignment the LLM was replacing. Re-processing these shows, which is the relaxation's whole purpose, strictly degrades them. The same mechanism applies to every future gather whose step 1 is weak and whose taper owns the structure, because the LLM is skipped by design.
- Fix options, all needing a ruling:
  - (a) Taper-owned shows take segues from the taper's own `>` marks on placed songs (spec 4 step 3 change).
  - (b) Keep stored-llm rows needs-LLM when the replay drops a stored segue. That is a second predicate, which section 7 forbids.
  - (c) Accept it, document it, and leave these 41 shows out of any re-processing.
- 14 lost segues are spurious (the text has none; the LLM inferred them):
  - yondermountainstringband-2010-07-17: 8.
  - furthur-2011-04-03: 3, inside the Terrapin suite (plausible musically, but not in the text).
  - one each: belafleckandtheflecktones-1996-11-09, soundtribesector9-2005-03-31 (the text has a comma), umphreysmcgee-2005-09-30 t2.
  - Losing these is an improvement.
- The 4 gained segues are real (setlist.fm and the text agree): chuckprophet-2012-01-15 ×2, greatamericantaxi-2010-08-07, stevekimockband-2005-10-07.

D2. RULE DEFECT (spec-level): the keep-the-encore veto (ruling (d)) reads step 1 only, so on stored-llm rows it erases a shipped encore.
- Mechanism. On a stored-llm show, "today's" shipped structure is the LLM's, not step 1's. Step 1 lost the encore through unmatched titles: tracks after the last match inherit the previous set. So the veto never fires. The taper wrote no encore marker, so its last set runs to the end of the tape and the shipped encore folds into set 2.
- 4 members. The candidate is the taper's text in each; in each the encore is factually real:
  - newridersofthepurplesage-2006-04-08 [delivered]: setlist.fm has Truck Driving Man and Ripple as the encore. Step 1 missed `Truck Drivin' Man`, so it has no encore.
  - jackiegreene-2011-02-12 [held, stays held]: setlist.fm encore Sugaree. The tape's track 17 is tagged `Gone Wondering-Sugaree`.
  - johnkadlecik-2013-06-22 [packaged]: the canonical's sibling description has `~ENCORE~` before After Midnight. It parses as a song item in set 1, so step 1 has no encore.
  - radiators-2010-06-05 [delivered]: a 4-track encore starting at `Kenny, Todd & Mackie calls em' back`. The canonical has no encore label.
- On the literal spec text this is designed: the no-encore ruling, plus ruling (d) read as "step-1". Against ruling (d)'s intent ("keep the encore") it is a defect, exposed precisely by section 7. A wrong set-2 closer would be spoken (for example "closing the second set with Ripple").
- Fix options, needing a ruling: (a) for the replay relaxation, treat the stored structure's encore as "today's encore", so these stay needs-LLM; (b) for every gather, also honour an `encore` label in the winning canonical (it would catch newriders and jackiegreene).

C3. As designed (spec section 3, filler between *a* and *b*), cosmetic: filler placement follows step 1 even when the taper's text explicitly lists that filler under the next header.
- `_place_boundary` counts a step-1 boundary at either edge of the filler run as a split (`range(a, b)`). So "agrees with today's at song level" keeps step 1's filler side, and step 1's side there is just the "unmatched inherits the previous set" artifact.
- Against the text: yondermountainstringband-2010-07-17 (`Set 2 intro` ships in set 1), radiators-2010-06-05 t13, moe-2008-06-20 (`crowd` under `E`), soundtribesector9-2005-04-13 (`Encore Break` under `(encore)`).
- With the text by the same rule: thedead-2009-05-02 (`Crowd` under Encore), joerussosalmostdead-2016-03-25.
- Unclear: moe-2004-04-17, umphreysmcgee-2005-09-02.
- Not a rule defect. The operator may want filler that the taper listed to follow the taper, which would be a spec change. Labels only; no song moves.

C4. Rule working as designed: the taper fixes or keeps the structure the LLM had. Song-level labels match the taper's text on all 62 rows; the only automated mismatches are jackiegreene t17 (a merged tag naming songs from both sides) and stringcheeseincident-2005-03-25 t8 (a `Jam`, a matcher artefact).
- Better than stored: derektrucksband-2003-12-26, -2004-04-15 and -2008-10-23, greenskybluegrass-2013-05-04 and soulive-2001-12-15 (the LLM shipped one set where the taper marks Set 1 / Set 2); furthur-2011-04-03 (Phil Donor Rap moves to the encore, as listed); radiators-2006-02-10 (`callin em back` moves to set 2, listed before `encores:`).
- Equal to stored: 44.

C5. As designed (spec 4, the low-confidence rule): 3 delivered shows become newly-held on `low-confidence structure alignment`. Their labels equal stored and taper; only the coverage hold is new. Re-processing would put these delivered shows on hold.
- darkstarorchestra-2009-11-14.
- deadandcompany-2015-10-29 (junk-prefixed tags, `Dead&Co2015-10-29ii 13_ Drums`).
- stringcheeseincident-2005-03-25.

C6. Not this piece: 2 newly-held on vet flags that the base replay also computes; needs-LLM used to mask them. joerussosalmostdead-2017-11-09 (`research asserts unknown song` ×8) and joerussosalmostdead-2023-01-26 (`research asserts wrong date`).

C7. Held rows, not caused by the taper rule.
- Still-held: derektrucksband-2003-12-26 and soulive-2001-12-15 (`unresolved track titles`); jackiegreene-2011-02-12 (`research asserts unknown song` ×7, plus D2).
- Outcome `structure-changed`, i.e. would clear on `reapply --allow-structure-change`; report 2's business: derektrucksband-2004-04-15 (on the adjudicator's partial-tape list) and derektrucksband-2008-10-23. Neither loses a segue.
- On every stored-llm row the alignment changes from `llm`, so `_structure_changed` gates each held one. Good.

R1. Harness report defect, not a rule defect: report 3's `provenance only` tier ignores segue changes. 34 stored-llm rows (above) lose segues yet are labelled provenance only. Their segue changes appear only in the stored-llm section. Fix before the operator reads the tier counts: tier on `segue_changes` too, or a `segues only` tier. For the 494 non-stored-llm provenance rows, segue_changes equal base's, so they are unaffected.

O1. Observation, harmless: the reader takes lineage text after the last encore song as encore items. furthur-2011-04-03's encore items include `Notes: Team FInd Recording / AOTJ Release`, `Linage: Edirol R4 Pro @ 24/48`, `HD`, `Wavelab 6`. Placement reads only the boundary items, and the also-on-the-other-side test can only decline, so shipped output cannot get worse.

O2. Observation: soulive-2001-12-15's title change against stored (t3 -> `1 in 7`) is Tier-1 2a drift, also present in base. It is not this piece.

== (A) one line per row
- belafleckandtheflecktones-1996-11-09 [delivered, clean-changed] src=description align llm->deterministic | stored 1x7 2x9 -> cand 1x7 2x9 | equal | segues lost 0 real/1 spurious, gained 0
- belafleckandtheflecktones-2006-01-21 [delivered, clean-changed] src=description align llm->deterministic | stored 1x7 2x7 encorex3 -> cand 1x7 2x7 encorex3 | equal | segues lost 0 real/0 spurious, gained 0
- billystrings-2019-01-24 [delivered, clean-changed] src=description align llm->deterministic | stored 1x10 2x10 encorex1 -> cand 1x10 2x10 encorex1 | equal | segues lost 2 real/0 spurious, gained 0
- bobbyleerodgers-2010-01-13 [packaged, clean-changed] src=description align llm->deterministic | stored 1x7 2x6 -> cand 1x7 2x6 | equal | segues lost 0 real/0 spurious, gained 0
- chuckprophet-2012-01-15 [delivered, clean-changed] src=description align llm->deterministic | stored 1x11 2x13 encorex1 -> cand 1x11 2x13 encorex1 | equal | segues lost 0 real/0 spurious, gained 2
- darkstarorchestra-2009-07-03 [delivered, clean-changed] src=description align llm->taper | stored 1x9 2x8 encorex2 -> cand 1x9 2x8 encorex2 | equal | segues lost 5 real/0 spurious, gained 0
- darkstarorchestra-2009-11-14 [delivered, newly-held] src=description align llm->taper | stored 1x9 2x11 encorex1 -> cand 1x9 2x11 encorex1 | equal | segues lost 4 real/0 spurious, gained 0
- deadandcompany-2015-10-29 [delivered, newly-held] src=description align llm->deterministic | stored 1x7 2x9 encorex1 -> cand 1x7 2x9 encorex1 | equal | segues lost 3 real/0 spurious, gained 0
- derektrucksband-2003-12-26 [held, still-held] src=description align llm->taper | stored 1x16 encorex2 -> cand 1x8 2x8 encorex2 | cand-better (taper set 2 the LLM lacked) | segues lost 0 real/0 spurious, gained 0
- derektrucksband-2004-04-15 [held, structure-changed] src=description align llm->taper | stored 1x16 encorex1 -> cand 1x8 2x8 encorex1 | cand-better (taper set 2 the LLM lacked) | segues lost 0 real/0 spurious, gained 0
- derektrucksband-2004-06-11 [delivered, clean-changed] src=description align llm->taper | stored 1x7 2x8 encorex3 -> cand 1x7 2x8 encorex3 | equal | segues lost 1 real/0 spurious, gained 0
- derektrucksband-2008-10-23 [held, structure-changed] src=description align llm->taper | stored 1x16 encorex2 -> cand 1x9 2x7 encorex2 | cand-better (taper set 2 the LLM lacked) | segues lost 0 real/0 spurious, gained 0
- furthur-2011-04-03 [delivered, clean-changed] src=description align llm->taper | stored 1x9 2x13 encorex1 -> cand 1x9 2x12 encorex2 | cand-better (Phil Donor Rap -> encore, as the text lists it) | segues lost 1 real/3 spurious, gained 0
- greatamericantaxi-2010-08-07 [delivered, clean-changed] src=description align llm->taper | stored 1x16 2x23 -> cand 1x16 2x23 | equal | segues lost 2 real/0 spurious, gained 1
- greatamericantaxi-2011-06-19 [delivered, clean-changed] src=description align llm->deterministic | stored 1x14 2x14 encorex1 -> cand 1x14 2x14 encorex1 | equal | segues lost 1 real/0 spurious, gained 0
- greenskybluegrass-2013-05-04 [delivered, clean-changed] src=description align llm->taper | stored 1x21 -> cand 1x8 2x13 | cand-better (taper set 2 the LLM lacked) | segues lost 0 real/0 spurious, gained 0
- greenskybluegrass-2015-01-22 [delivered, clean-changed] src=description align llm->taper | stored 1x10 2x9 encorex1 -> cand 1x10 2x9 encorex1 | equal | segues lost 1 real/0 spurious, gained 0
- hotbutteredrum-2008-10-10 [delivered, clean-changed] src=description align llm->taper | stored 1x9 2x13 encorex7 -> cand 1x9 2x13 encorex7 | equal | segues lost 5 real/0 spurious, gained 0
- jackiegreene-2011-02-12 [held, still-held] src=description align llm->taper | stored 1x7 2x9 encorex1 -> cand 1x7 2x10 | cand-worse: encore Sugaree folded (setlist.fm encore) [D2] | segues lost 0 real/0 spurious, gained 0
- joerussosalmostdead-2015-04-22 [delivered, clean-changed] src=notes align llm->deterministic | stored 1x6 2x6 encorex1 -> cand 1x6 2x6 encorex1 | equal | segues lost 3 real/0 spurious, gained 0
- joerussosalmostdead-2015-05-09 [delivered, clean-changed] src=description align llm->taper | stored 1x7 2x7 encorex1 -> cand 1x7 2x7 encorex1 | equal | segues lost 6 real/0 spurious, gained 0
- joerussosalmostdead-2015-05-24 [delivered, clean-changed] src=notes align llm->deterministic | stored 1x8 2x7 encorex1 -> cand 1x8 2x7 encorex1 | equal | segues lost 2 real/0 spurious, gained 0
- joerussosalmostdead-2015-12-12 [delivered, clean-changed] src=notes align llm->deterministic | stored 1x6 2x6 encorex4 -> cand 1x6 2x6 encorex4 | equal | segues lost 5 real/0 spurious, gained 0
- joerussosalmostdead-2016-02-14 [delivered, clean-changed] src=notes align llm->taper | stored 1x6 2x7 encorex1 -> cand 1x6 2x7 encorex1 | equal | segues lost 3 real/0 spurious, gained 0
- joerussosalmostdead-2016-03-25 [packaged, clean-changed] src=notes align llm->deterministic | stored 1x8 2x5 encorex2 -> cand 1x8 2x6 encorex1 | cand-better, filler only ('encore break/crowd' listed before 'Encore:') | segues lost 10 real/0 spurious, gained 0
- joerussosalmostdead-2017-01-12 [delivered, clean-changed] src=notes align llm->taper | stored 1x5 2x9 encorex2 -> cand 1x5 2x9 encorex2 | equal | segues lost 12 real/0 spurious, gained 0
- joerussosalmostdead-2017-11-09 [packaged, newly-held] src=notes align llm->taper | stored 1x6 2x7 encorex2 -> cand 1x6 2x7 encorex2 | equal | segues lost 11 real/0 spurious, gained 0
- joerussosalmostdead-2021-05-30 [delivered, clean-changed] src=description align llm->deterministic | stored 1x8 2x6 encorex1 -> cand 1x8 2x6 encorex1 | equal | segues lost 2 real/0 spurious, gained 0
- joerussosalmostdead-2021-12-03 [delivered, clean-changed] src=description align llm->taper | stored 1x6 2x9 encorex1 -> cand 1x6 2x9 encorex1 | equal | segues lost 13 real/0 spurious, gained 0
- joerussosalmostdead-2023-01-26 [packaged, newly-held] src=description align llm->deterministic | stored 1x6 2x7 encorex1 -> cand 1x6 2x7 encorex1 | equal | segues lost 6 real/0 spurious, gained 0
- johnkadlecik-2013-06-22 [packaged, clean-changed] src=description align llm->taper | stored 1x8 2x10 encorex1 -> cand 1x8 2x11 | cand-worse: encore After Midnight folded into set 2 (sibling taper marks ~ENCORE~) [D2] | segues lost 1 real/0 spurious, gained 0
- kellerwilliams-2006-01-27 [delivered, clean-changed] src=description align llm->deterministic | stored 1x15 2x16 encorex1 -> cand 1x15 2x16 encorex1 | equal | segues lost 2 real/0 spurious, gained 0
- leftoversalmon-1997-08-14 [delivered, clean-changed] src=description align llm->taper | stored 1x13 2x15 encorex1 -> cand 1x13 2x15 encorex1 | equal | segues lost 2 real/0 spurious, gained 0
- leftoversalmon-1997-10-31 [delivered, clean-changed] src=description align llm->deterministic | stored 1x21 2x22 -> cand 1x21 2x22 | equal | segues lost 12 real/0 spurious, gained 0
- melvinseals-2003-01-25 [delivered, clean-changed] src=description align llm->taper | stored 1x5 2x7 -> cand 1x5 2x7 | equal | segues lost 0 real/0 spurious, gained 0
- moe-2004-04-17 [delivered, clean-changed] src=description align llm->deterministic | stored 1x7 2x5 encorex3 -> cand 1x7 2x6 encorex2 | unclear, filler only: 'Crowd/Banter' (not in text) set 2 vs stored encore | segues lost 2 real/0 spurious, gained 0
- moe-2007-03-24 [delivered, clean-changed] src=description align llm->taper | stored 1x6 2x10 encorex3 -> cand 1x6 2x10 encorex3 | equal | segues lost 3 real/0 spurious, gained 0
- moe-2008-06-20 [delivered, clean-changed] src=description align llm->deterministic | stored 1x6 2x6 encorex2 -> cand 1x6 2x7 encorex1 | cand-worse, filler only: 'crowd' listed under E ships in set 2 [C3] | segues lost 0 real/0 spurious, gained 0
- newridersofthepurplesage-2006-04-08 [delivered, clean-changed] src=description align llm->deterministic | stored 1x11 2x11 encorex2 -> cand 1x11 2x13 | cand-worse: encore Truck Drivin' Man/Ripple folded (setlist.fm encore) [D2] | segues lost 2 real/0 spurious, gained 0
- philleshandfriends-2001-11-17 [packaged, clean-changed] src=description align llm->deterministic | stored 1x8 2x9 encorex2 -> cand 1x8 2x9 encorex2 | equal | segues lost 4 real/0 spurious, gained 0
- radiators-1992-12-06 [delivered, clean-changed] src=description align llm->taper | stored 1x16 2x14 encorex4 -> cand 1x16 2x14 encorex4 | equal | segues lost 4 real/0 spurious, gained 0
- radiators-2000-12-15 [delivered, clean-changed] src=description align llm->taper | stored 1x10 2x8 3x7 encorex3 -> cand 1x10 2x8 3x7 encorex3 | equal | segues lost 3 real/0 spurious, gained 0
- radiators-2006-02-10 [packaged, clean-changed] src=description align llm->taper | stored 1x12 2x8 encorex4 -> cand 1x12 2x9 encorex3 | cand-better by text ('callin em back' listed before 'encores:') | segues lost 0 real/0 spurious, gained 0
- radiators-2010-06-05 [delivered, clean-changed] src=description align llm->deterministic | stored 1x12 2x9 encorex4 -> cand 1x13 2x12 | cand-worse: 4-track encore folded (from 'calls em' back') [D2]; filler t13 'tuning > Kenny's intro' to set 1 though text lists it under Set Two [C3] | segues lost 1 real/0 spurious, gained 0
- ryanadams-2006-12-04 [delivered, clean-changed] src=description align llm->deterministic | stored 1x10 2x12 -> cand 1x10 2x12 | equal | segues lost 0 real/0 spurious, gained 0
- soulive-2001-12-15 [held, still-held] src=description align llm->taper | stored 1x10 -> cand 1x5 2x5 | cand-better (taper set 2 the LLM lacked) | segues lost 1 real/0 spurious, gained 0
- soundtribesector9-2004-05-01 [delivered, clean-changed] src=description align llm->taper | stored 1x9 2x7 encorex2 -> cand 1x9 2x7 encorex2 | equal | segues lost 0 real/0 spurious, gained 0
- soundtribesector9-2005-03-26 [delivered, clean-changed] src=description align llm->deterministic | stored 1x7 2x7 encorex1 -> cand 1x7 2x7 encorex1 | equal | segues lost 1 real/0 spurious, gained 0
- soundtribesector9-2005-03-31 [delivered, clean-changed] src=description align llm->taper | stored 1x7 2x7 encorex1 -> cand 1x7 2x7 encorex1 | equal | segues lost 1 real/1 spurious, gained 0
- soundtribesector9-2005-04-13 [delivered, clean-changed] src=description align llm->deterministic | stored 1x7 2x7 encorex2 -> cand 1x7 2x8 encorex1 | cand-worse, filler only: 'Encore Break' listed under (encore) ships in set 2 [C3] | segues lost 1 real/0 spurious, gained 0
- stevekimockband-2002-07-03 [packaged, clean-changed] src=description align llm->taper | stored 1x6 2x6 -> cand 1x6 2x6 | equal | segues lost 0 real/0 spurious, gained 0
- stevekimockband-2005-10-01 [delivered, clean-changed] src=description align llm->deterministic | stored 1x6 2x7 -> cand 1x6 2x7 | equal | segues lost 0 real/0 spurious, gained 0
- stevekimockband-2005-10-07 [packaged, clean-changed] src=description align llm->deterministic | stored 1x6 2x5 -> cand 1x6 2x5 | equal | segues lost 0 real/0 spurious, gained 1
- stringcheeseincident-2000-03-10 [delivered, clean-changed] src=description align llm->taper | stored 1x6 2x6 encorex2 -> cand 1x6 2x6 encorex2 | equal | segues lost 0 real/0 spurious, gained 0
- stringcheeseincident-2005-03-25 [delivered, newly-held] src=description align llm->deterministic | stored 1x11 2x6 encorex2 -> cand 1x11 2x6 encorex2 | equal | segues lost 4 real/0 spurious, gained 0
- tedeschitrucksband-2019-11-11 [delivered, clean-changed] src=description align llm->deterministic | stored 1x9 2x9 encorex1 -> cand 1x9 2x9 encorex1 | equal | segues lost 0 real/0 spurious, gained 0
- thedead-2009-05-02 [delivered, clean-changed] src=description align llm->taper | stored 1x7 2x14 encorex2 -> cand 1x7 2x13 encorex3 | cand-better, filler only ('Crowd' listed under 'Encore') | segues lost 1 real/0 spurious, gained 0
- umphreysmcgee-2004-11-12 [delivered, clean-changed] src=description align llm->taper | stored 1x8 2x8 encorex2 -> cand 1x8 2x8 encorex2 | equal | segues lost 3 real/0 spurious, gained 0
- umphreysmcgee-2005-09-02 [delivered, clean-changed] src=description align llm->taper | stored 1x9 2x9 encorex3 -> cand 1x9 2x10 encorex2 | unclear, filler only: '~encore break~' (before 'E:') set 2 vs stored encore | segues lost 5 real/0 spurious, gained 0
- umphreysmcgee-2005-09-30 [packaged, clean-changed] src=description align llm->deterministic | stored 1x8 2x8 encorex2 -> cand 1x8 2x8 encorex2 | equal | segues lost 6 real/1 spurious, gained 0
- yondermountainstringband-2010-07-17 [packaged, clean-changed] src=description align llm->deterministic | stored 1x10 2x13 -> cand 1x11 2x12 | cand-worse, filler only: 'Set 2 intro' listed under Set Two ships in set 1 [C3] | segues lost 0 real/8 spurious, gained 0
- zero-2008-08-08 [delivered, clean-changed] src=description align llm->deterministic | stored 1x9 2x7 -> cand 1x9 2x7 | equal | segues lost 0 real/0 spurious, gained 0

== (B) provenance only: strata
Automated, all 538 rows:
- The 494 that are not stored-llm: every shipped field and flag equals the base replay (set/segue/title changes, set_breaks, alignment, gather/vet flags, outcome) on 492 rows. The other 2 differ only in a jerrybase closer flag becoming the `(taper's markers)` operator note, which is spec 5. deadandcompany-2017-11-28 and gratefuldead-1971-04-29 both have correct dates, and the taper's structure matches the known setlists (UJB encore 4/29/71; BMR > Playin' reprise encore 11/28/17).
- The 44 stored-llm rows in this tier are label-equal to stored, but 34 lose segues (R1, D1). They are covered under (A).

Primary form, taken from the header lines the reader matched; first match in this order: notes > disc/set > time > ordinal > decorated > roman > word > same-line > arabic.

| form | rows | of which stored-llm | sampled | confirmed |
|---|---|---|---|---|
| notes as source | 12 | 6 | 4 | 4 |
| disc then set (`Disc I 1st Set`, `CD 1 - Set 1`, `Disc 1 / Set 1`, `Disc Three - Set Two cont:`) | 39 | 4 | 5 | 5 |
| set then disc (`set 1/Disc 1`, `Set 1 Disc 1:`, `Set1/CD1`, `Set 1/ Disc 2` cont.) | 11 | 3 | 4 | 4 |
| header + time annotation (`Set One (9:00PM - 10:14PM):`, `Set I: (1:15:11)`) | 20 | 5 | 4 | 4 |
| ordinal (`1st Set:`) | 5 | 0 | 4 | 4 |
| decorated (`---Set II---`, `(Set I)`, `--Set One--`, `~SET I~`) | 8 | 1 | 4 | 4 |
| roman (`Set I`/`Set II`, incl. `Set II` only with a leading block) | 73 | 4 | 5 | 5 |
| word number (`Set One:`, `Set Two` only + `E:`) | 60 | 5 | 5 | 5 |
| header + songs on the same line (`Set 1: a, b > c`) | 47 | 7 | 5 | 5 |
| plain arabic (`Set 1`, `Set 1:`, `Set1`) | 263 | 9 | 8 | 8 |
| total | 538 | 44 | 48 | 48 |

The sampled encore forms were `Encore`/`Encores`/`(Encore)`/`~ENCORE~` (33), `E:` (5) and none (10). The sample was drawn from the rows that are not stored-llm. Each sampled row is confirmed on four counts: the stored labels equal the candidate's, the base replay equals the candidate on shipped fields, every non-filler track matched to the taper's items carries that item's set (0 mismatches over 48 rows), and the breaks agree with the taper's headers. Exceptions: none in the sample. Outside it, see R1 (the 34 segue-losing stored-llm rows) and the 2 closer-note rows above.

== Things the operator should look at before re-processing
1. D1 and D2 need your ruling before any stored-llm show is re-processed. Under the current code a `redo --from gather` of the 41 D1 shows drops 157 real taper-written segues, and the 4 D2 shows lose a real encore. Re-delivering voiced ones would also discard their DJ audio for a regression.
2. Read report 3's `provenance only` count (538) as "labels unchanged", not "nothing shipped changes", until R1 is fixed.
3. C5: re-processing darkstarorchestra-2009-11-14, deadandcompany-2015-10-29 and stringcheeseincident-2005-03-25 (all delivered) would hold them on low confidence. Their structure is right.
4. C6: joerussosalmostdead-2017-11-09 and -2023-01-26 would hold on vet flags unrelated to this piece.
5. C3, if you care about filler labels: 4 shows put an intro or encore-break track on the other side from where the taper listed it.
6. derektrucksband-2004-04-15 (adjudicator partial-tape) and -2008-10-23 clear on reapply with `--allow-structure-change`. Their structure is the taper's and correct; report 2 covers them.
