VERDICT: RULE DEFECT (1 class). Rows checked 91 (83 songs moved + 8 filler labels only): after-better 70, after-equal 14, after-worse 5, unclear 2.

The defect class needs an operator ruling before any fix. The code follows the letter of ruling (d). The problem is what ruling (d) is compared against: on these shows today's path does not ship the step-1 labels, so step 1 is the wrong reference.

Of the 5 worse rows, 3 are the defect class (G). 1 is the rule working as designed and held anyway (mymorningjacket-2018-03-05). 1 is a cosmetic filler label (yondermountainstringband-2010-07-17).

Reviewer: pre3-moved (Opus), read-only. Inputs: taper_changes.txt sections `songs moved (83)` and `filler labels only (8)`, cand.json/base.json, ~/.llama/shows/<slug>/show.json, ~/.llama/cache md_/slfm_ files. A per-show dump (tracks with stored/before/after labels, reader items, taper text) is at ~/.llama-harness/piece2/accept/work/pre3-moved/dump.txt. I also ran one offline probe (replay_holds `run --slugs` over 6 stored-llm rows, with `decide_taper`/`align` wrapped to log step-1 coverage and `today_sets`). It wrote only under that work dir: probe.jsonl, probe_arm.json.

## Classes

**A. The taper's encore marker relabels a tail that setlist.fm or step 1 left in set 2, or called set 3/4.** The rule works as designed; after is better in every case.
assemblyofdust-2004-12-31 (`Encore 2:` → spurious set 3 becomes encore), chuckprophet-2012-01-08, darkstarorchestra-2007-07-07, davealvin-2008-11-01, greatamericantaxi-2010-03-13, joerussosalmostdead-2014-10-11, -2016-02-10, -2017-05-06, -2018-10-25, -2022-04-30, moe-2006-10-06, moe-2009-03-29, moe-2009-04-04, radiators-2005-07-03, radiators-2006-04-21, railroadearth-2004-03-27, -2008-03-01, -2009-08-22, -2013-07-12, soundtribesector9-2004-12-31, -2005-02-11, -2007-04-26, stringcheeseincident-2004-11-26, -2004-12-31, -2006-07-20, -2010-07-30, tedeschitrucksband-2023-03-31, thebrew-2009-04-18, umphreysmcgee-2005-04-15, yondermountainstringband-2006-10-21, -2007-06-20, -2008-02-09.

**B. The taper's set break restores sets that shipped as one (or as 1 + a giant encore).** Rule working; better.
bigdaddybluegrassband-2004-01-10, derektrucksband-2006-01-22, greenskybluegrass-2006-05-16 (1 → 3 + E), greenskybluegrass-2013-05-04, lotus-2006-02-18, lotus-2008-08-02, perpetualgroove-2006-12-29, -2007-08-18, -2008-05-03, radiators-1981-07-11, railroadearth-2005-02-19, ryanadams-2007-07-21, ryanadams-2008-01-29, yondermountainstringband-2006-06-14, furthur-2011-03-11, darkstarorchestra-2017-02-10.

**C. A break moves one or two songs at the set boundary: setlist.fm alignment had put set 2's opener at the end of set 1, or the reverse.** Rule working; better.
discobiscuits-2002-03-06, joerussosalmostdead-2013-12-27, -2017-04-29, -2018-05-04, -2019-03-02, -2019-09-28, kellerwilliams-2005-02-12, mermen-2003-07-19, stringcheeseincident-2000-01-31, -2000-10-27, -2007-07-28, tealeafgreen-2005-03-11, tedeschitrucksband-2018-10-13.

**D. The taper's set count overrides extra segment sets from setlist.fm.** Rule working.
tedeschitrucksband-2019-11-15 (4 → 2 + E, better), tedeschitrucksband-2020-02-21 (3 → 2 + E, better; the taper's own note says "Acoustic start to second set"), joerussosalmostdead-2019-09-28 (better), ryanadams-2008-01-19 (3 → 2, equal: setlist.fm counts the solo opener as a set, the taper puts "Ryan Solo" and "Cardinals" both under Set 1).
mymorningjacket-2018-03-05 (3 → 2) is WORSE for the performance, but by design. setlist.fm's three album sets (Evil Urges / Circuital / The Waterfall) are right, and the taper merged the last two into "Set 2". The candidate is newly held by vet ("research asserts 3 sets but structure has 2"), so it does not ship unseen.

**E. Taper beats jerrybase anchoring.** By design (section 4: jerrybase never moves a taper break). In most rows setlist.fm's pre-anchor alignment, the stored "was" note, agrees with the taper.
- Better: darkstarorchestra-2001-12-15, furthur-2010-05-29, furthur-2010-06-26, philleshandfriends-2006-07-03, thedead-2009-05-01, furthur-2011-03-11.
- UNCLEAR: darkstarorchestra-2006-11-29 (the taper alone puts OMSN in the encore and calls Baby Blue filler; jerrybase and setlist.fm both put OMSN in set 2 and Baby Blue as the encore). Also gratefuldead-1974-09-18 (voiced): taper "Set Two: Phil And ned / Set Three:" gives 3 sets, and jerrybase's 2-set count became a note.

**F. A non-music track crosses the set-2/encore line per the taper** (donor rap, encore call, trophy presentation). Rule working; equal.
furthur-2009-12-13, -2010-06-27, -2011-02-13, -2011-04-03, -2011-09-23, radiators-1997-04-12, radiators-2006-02-10, tedeschitrucksband-2022-03-26.

**G. RULE DEFECT: an encore folds into set 2 on stored-llm shows whose step 1 is below the coverage threshold.**
Members: johnkadlecik-2013-06-22 (packaged), newridersofthepurplesage-2006-04-08 (delivered), radiators-2010-06-05 (delivered). Library-wide sweep of the cand arm (taper-owned, no encore after, encore in stored show.json) finds exactly one more: jackiegreene-2011-02-12, held and outside my sections.

Mechanism:
- The taper writes no recognised encore marker, so section 2 runs the last set to the end of the tape.
- Ruling (d) ("keep the encore") vetoes ownership only when `today_sets`, the step-1 labels, has an `encore` after the last taper break.
- On these shows step 1 has no encore. The probe measured step-1 coverage at 0.789, 0.792 and 0.773, all below `align_coverage_threshold` 0.8, with no anchoring. So today's path does NOT ship step 1: it calls `align_structure`, and that LLM structure (the stored one) has the encore.
- The taper now owns the show, the LLM is skipped, and the encore is lost.
- Each has outside evidence that the encore is real:
  - NRPS: setlist.fm's encore set is `Truck Driving Man, Ripple`. That encore is in the canonical; step 1 just failed to align it.
  - JK Band: the sibling recording jkb2013-06-22.fob.akg391.kindrec marks `~ENCORE~ 11. Band Introduction 12. After Midnight`.
  - Radiators: the sibling rad2010-06-05.flac16 marks `Encores … Bring It On Home To Me, Smokin' Hole, Train Kept A-Rollin'`, and the selected taper itself writes `23. Kenny, Todd & Mackie calls em' back`. That line slips past the veto words because it has no `encore`/`enc`.

Why it is a defect and not just "repeat the taper": ruling (d) exists to keep an encore llama ships today. It uses step 1 as its stand-in for "today", and that only holds when today ships step 1. When today's path would reach the LLM branch, step 1's lack of an encore is evidence of nothing.

Fix (the operator's call, since it changes how ruling (d) is read; it only ever makes the taper own less): in `decide_taper`/gather, when the taper marks no encore and today's path would reach the LLM branch (canonical has items, no anchoring, step-1 coverage < threshold), the taper owns nothing (`veto: today's encore unknown`). A narrower variant would veto only when the canonical setlist labels any item `encore`; that catches NRPS but not JK or Radiators, whose current canonicals carry no encore. Either variant affects future gathers too, not only these stored rows.

**H. Filler labels follow step 1's split point even against the taper's explicit text.** As specified ("the split point stays where today's puts it … moves no filler"), and cosmetic only. `_place_boundary` treats a step-1 break at either edge of the filler run as today's split.
- yondermountainstringband-2010-07-17: "Set Two: 01. Set 2 intro" now ships in set 1, where before (stored llm) had set 2. Counted worse, cosmetic.
- Against the taper's text with no song effect: radiators-2010-06-05 track 13 (listed under "Set Two"), moe-2008-06-20 ("E / 1 crowd"), soundtribesector9-2005-04-13 ("(encore) 08. Encore Break").
- stringcheeseincident-2004-12-31's "Set 2 Intro" stays in set 1, unchanged from before.
- The filler rows where after matches the taper: aquariumrescueunit-1992-07-07, thedead-2009-05-02, joerussosalmostdead-2016-03-25, umphreysmcgee-2005-09-02, moe-2004-04-17.

## Per row

### songs moved (83)
- assemblyofdust-2004-12-31 [delivered] [7,16,20]→[7,16] OK better: "Encore 2: 01. Songs We Sing" (was set 3)
- bigdaddybluegrassband-2004-01-10 [delivered] []→[12] OK better: "Disc 2/Set 2: 1. Hillbilly Hot Tub"
- chuckprophet-2012-01-08 [delivered] [10]→[10,20] OK better: "You Did, E:Hot Tramp*, Goodtime Crowd*"
- darkstarorchestra-2001-12-15 [delivered] [9,20]→[9,21] OK better: "Set 2 (cont): … Death Don't> Lovelight / Encore: Baby Blue" (setlist.fm pre-anchor agreed; jerrybase put Lovelight in the encore)
- darkstarorchestra-2006-11-29 [delivered] [13,23]→[13,22] UNCLEAR: "d3t05 Encore: Saturday Night … d3t07 Filler: Baby Blue" (jerrybase and setlist.fm put OMSN in set 2 and Baby Blue as the encore)
- darkstarorchestra-2007-07-07 [delivered] [10]→[10,20] OK better: "set 2 continued / Encore: / 11. Brokedown Palace"
- darkstarorchestra-2017-02-10 [delivered] [12]→[12,23] OK better: "Set 2-----01. Greatest Story … Encore------12. Brokedown Palace" (was 1 + encore×13)
- davealvin-2008-11-01 [delivered] [10]→[10,19] OK better: "-(encore)- 11. California Bloodlines"
- derektrucksband-2006-01-22 [delivered] []→[8,18] OK better: "disc 2 / set 2 / 1. Key To The Highway … 12. E: Hook & Sling"
- discobiscuits-2002-03-06 [delivered] [6,10]→[5,10] OK better: "Set 2: Sound 1, Spaga >"
- furthur-2009-12-13 [delivered] [9,19]→[9,20] OK equal: "11. Phil's Donor Rap 12. E: US Blues" (donor rap → set 2)
- furthur-2010-05-29 [delivered] [9,18,24]→[10,18,25] OK better: "Set I … 10.Truckin'", "7. Donor Rap / E1: Muli Guli" (setlist.fm pre-anchor agreed; jerrybase closer note)
- furthur-2010-06-26 [delivered] [8,18]→[8,21] OK better: "Terrapin Station* > At a Siding* > Terrapin Flyer*, Donor Rap, E: Brokedown Palace" (jerrybase had started the encore at At a Siding)
- furthur-2010-06-27 [delivered] [8,19]→[8,20] OK equal: "Franklin's Tower, Donor Rap, E: Box Of Rain"
- furthur-2011-02-13 [delivered] [9,19]→[9,20] OK equal: "Set 2 (cont.)/Disk 3: … 04. Doner Rap / ENCORE:"
- furthur-2011-03-11 [delivered] [18]→[9,19] OK better: "Set 2: (1:52:03) 201. Box of Rain … 212. E: Like A Rolling Stone"
- furthur-2011-04-03 [delivered] [9,22]→[9,21] OK equal: "-Encore- 14. Phil Donor Rap 15. Brokedown Palace" (before = stored llm)
- furthur-2011-09-23 [delivered] [8,17]→[8,18] OK equal: "11. Donor Rap / Encore: 12. Ripple"
- gratefuldead-1974-09-18 [voiced] [12,25]→[12,13,25] UNCLEAR: "Set Two: d2t02 - Phil And ned / Set Three: d2t03 - Loose Lucy" (Seastones as its own set; jerrybase 2 sets → note)
- greatamericantaxi-2010-03-13 [delivered] [12]→[12,26] OK better: "15. E: Maud"
- greenskybluegrass-2006-05-16 [delivered] [36]→[11,23,36] OK better: "disc2/set2", "disc3/set3", "encore"
- greenskybluegrass-2013-05-04 [delivered] []→[8] OK better: "Set II (78:42:08) d2t01-Intro" (stored llm one set; no encore anywhere)
- joerussosalmostdead-2013-12-27 [delivered] [9,17]→[8,17] OK better: "Set Two: 01. Space ->"
- joerussosalmostdead-2014-10-11 [delivered] [6]→[6,12] OK better: "-ENCORE- 07. Brokedown Palace"
- joerussosalmostdead-2016-02-10 [delivered] [7,14]→[7,14] OK better: notes "Encore: 08. Big Railroad Blues" (was set 3)
- joerussosalmostdead-2017-04-29 [delivered] [10,17]→[9,17] OK better: "SET TWOMorfbeats->Dark Star"
- joerussosalmostdead-2017-05-06 [delivered] [7,13]→[7,13] OK better: notes "Encore: 07. Bertha" (was set 3)
- joerussosalmostdead-2018-05-04 [delivered] [9,16]→[8,16] OK better: notes "Set Two (11:01PM - 12:44AM): 01. Marco Solo - >"
- joerussosalmostdead-2018-10-25 [delivered] [5]→[5,11] OK better: notes "Encore: 07. Deal &"
- joerussosalmostdead-2019-03-02 [delivered] [8,15]→[7,14] OK better: "Set Two …:01. Jam ->", "Encore: 08. Marco Solo ->"
- joerussosalmostdead-2019-09-28 [delivered] [4,15]→[8,15] OK better: "Set One …08. MB Solo -> (Turn On Your) Lovelight", "Encore:08. The Weight" (was 3 sets)
- joerussosalmostdead-2022-04-30 [delivered] [7,14]→[7,14] OK better: "Encore: 10. Absolutely Sweet Marie > 11. Goin' Down the Road" (was set 3)
- johnkadlecik-2013-06-22 [packaged] [8,18]→[8] WORSE (class G): "Disc 3 Set 2 … 05 John Rap > Band Intros 06 After Midnight", no encore marker; sibling taper "~ENCORE~ … 12. After Midnight"; stored llm had the encore
- kellerwilliams-2005-02-12 [packaged] [19,34]→[18,34] OK better: "Set 2 / Disc 2 / 01. Shapes Of M&Ms >"
- lotus-2006-02-18 [delivered] []→[5] OK better: "~Disc 2: Set 2~ … 02. Wax"
- lotus-2008-08-02 [packaged] [14]→[7,14] OK better: "~Set 2~ … 02. Expired Slang"
- mermen-2003-07-19 [packaged] [16]→[15] OK better: "Set 2: Batman tease, Casbah"
- moe-2006-10-06 [delivered] [6,14]→[6,12] OK better: "Encore: Godzilla, The Ghost Of Ralph's Mom" (the track is even tagged "Godzilla (Encore)")
- moe-2009-03-29 [delivered] [8,16]→[8,15] OK better: "Encore: Alnouncements / Good Trip> / Akimbo"
- moe-2009-04-04 [delivered] [6,14]→[6,12] OK better: "Encore 1. Crowd 2. AlNouncements 3. Plane Crash"
- mymorningjacket-2018-03-05 [delivered] [14,24,34]→[14,34] WORSE (by design, newly held by vet): "Set 2 … 21: Only Memories Remain / encore"; setlist.fm's 3 album sets are right
- newridersofthepurplesage-2006-04-08 [delivered] [11,22]→[11] WORSE (class G): "Set 2: … 12.Truck Drivin' Man 13.Ripple*", no encore marker; setlist.fm encore = Truck Driving Man, Ripple; stored llm had it
- perpetualgroove-2006-12-29 [delivered] [12]→[6,12] OK better: "Disc 2 - Set II … E: 3. Walkin' in Place"
- perpetualgroove-2007-08-18 [delivered] [13]→[7,13] OK better: "Disc 2 - Set II 1. Teakwood Betz"
- perpetualgroove-2008-05-03 [delivered] [13]→[7,13] OK better: "Disc 2 - Set II 1. Teakwood Betz"
- philleshandfriends-2006-07-03 [delivered] [5,13]→[5,16] OK better: "- set 2 * -", "07. Viola v3 08. crowd 09. Donor Rap 10. encore: Midnight Hour" (jerrybase had started the encore at Viola v3)
- radiators-1981-07-11 [delivered] [27]→[18,27] OK better: "(Set 2) 07) Haunted House", "-Encore 09) Chevy 39"
- radiators-1997-04-12 [delivered] [12,24]→[12,23] OK equal: "Encore: 07. calling them back 08. Junco Partner"
- radiators-2005-07-03 [delivered] [14]→[14,23] OK better: "encores: 14 Texas Chainsaw Massacre > 15 Cissy Strut"
- radiators-2006-02-10 [packaged] [12,20]→[12,21] OK equal: "10 callin em back / encores: 11 Junco Partner" (before = stored llm)
- radiators-2006-04-21 [delivered] [12]→[12,28] OK better: "encores: 18 Psychotic Reaction>"
- radiators-2010-06-05 [delivered] [12,21]→[13] WORSE (class G, plus class H on track 13): "Set Two: 14. tuning > Kenny's intro … 23. Kenny, Todd & Mackie calls em' back 24. Bring It On Home", no encore marker; sibling taper "Encores"; stored llm had the encore
- railroadearth-2004-03-27 [delivered] [7]→[7,16] OK better: "Encores: 8. El //Cumbanchero"
- railroadearth-2005-02-19 [delivered] [19]→[7,19] OK better: "Set 2: Disc 2: 01. Old Man & the Land"
- railroadearth-2008-03-01 [delivered] [7]→[7,15] OK better: "Encores: 09. Bird in a House"
- railroadearth-2009-08-22 [delivered] [8]→[8,19] OK better: "Encore: 05 Railroad Earth"
- railroadearth-2013-07-12 [delivered] [8]→[8,21] OK better: "Encore: Railroad Earth"
- ryanadams-2007-07-21 [delivered] []→[9] OK better: "Set 2 10. Pearls On A String"
- ryanadams-2008-01-19 [delivered] [4,16]→[16] OK equal: "Set 1: Ryan Solo 01.Intro … Cardinals 05. … Set 2: 01.A Kiss Before I Go" (setlist.fm counted the solo opener as a set)
- ryanadams-2008-01-29 [delivered] [18]→[10,18] OK better: "Disc 2 (69:56) Set 2 01. Why Do They Leave"
- soundtribesector9-2004-12-31 [delivered] [8,18]→[8,17] OK better: "Encore: Improv Jam*, Havona Ascent**, Breathe In"
- soundtribesector9-2005-02-11 [delivered] [8]→[8,15] OK better: "E: ASAA"
- soundtribesector9-2007-04-26 [delivered] [7]→[7,13] OK better: "Encore: Really Wut?"
- stringcheeseincident-2000-01-31 [delivered] [8,16]→[7,16] OK better: "Set 2: (acoustic) Think What You've Done"
- stringcheeseincident-2000-10-27 [delivered] [9,15]→[8,15] OK better: "Set 2: Tom Thumb's Blues > Jam > Rivertrance"
- stringcheeseincident-2004-11-26 [delivered] [7,15]→[7,14] OK better: "Encore: On the Road² > Give It Away"
- stringcheeseincident-2004-12-31 [delivered] [10]→[10,20] OK better: "Encore: Boogie on Reggae Woman" ("Set 2 Intro" stays in set 1 as before)
- stringcheeseincident-2006-07-20 [delivered] [7]→[7,15] OK better: "E: Travis Drums > On the Road"
- stringcheeseincident-2007-07-28 [delivered] [10,21,26]→[10,19,26] OK better: "Disc 3 (Set 3) 1. Ritual Jam>"
- stringcheeseincident-2010-07-30 [delivered] [9]→[9,19] OK better: "Encore: 07 Hey Pocky Way*"
- tealeafgreen-2005-03-11 [delivered] [14,24]→[13,24] OK better: "(set II) 15) Bouncin' Betty", "(encore) 11) Freedom"
- tedeschitrucksband-2018-10-13 [voiced] [11,20]→[10,20] OK better: "Set 2:1. Sitting Here In Limbo"
- tedeschitrucksband-2019-11-15 [delivered] [9,14,20]→[9,20] OK better: "set ii10 - Keep Your Lamp … 21 - crowd encore22 - I Walk on Guilded Splinters" (was 4 sets)
- tedeschitrucksband-2020-02-21 [packaged] [9,13,19]→[9,19] OK better: "Set Two 10. Calling Out To You … 20. E: Made Up Mind"
- tedeschitrucksband-2022-03-26 [voiced] [9,20]→[9,19] OK equal: "Encore 211-s2t11 - Trophy Presentation 212 - I Pity The Fool"
- tedeschitrucksband-2023-03-31 [voiced] [7,17]→[7,16] OK better: "Encore:210. Sweet Soul Song211. More And More"
- thebrew-2009-04-18 [delivered] [11]→[11,20] OK better: "Enc: 11 Kiss#"
- thedead-2009-05-01 [delivered] [7,17]→[8,17] OK better: "Set I: … 08 Playin' reprise / Set II: 01 Jack Straw" (setlist.fm pre-anchor agreed)
- umphreysmcgee-2005-04-15 [delivered] [8]→[8,19] OK better: "Encore: 2. A 5th of Beethoven"
- yondermountainstringband-2006-06-14 [delivered] [19]→[10,19] OK better: "Disk 2/Set II: 1. Intro 2. Lord Only Knows"
- yondermountainstringband-2006-10-21 [delivered] [13]→[13,24] OK better: "ENCORE 1 03. Snow On The Pines … ENCORE 2"
- yondermountainstringband-2007-06-20 [delivered] [11]→[11,18] OK better: "Encore: 8. 2 Hits and The Joint Turned Brown"
- yondermountainstringband-2008-02-09 [delivered] [15]→[15,29] OK better: "ENC: d3t09: Holdin', d3t10: Down The River Road"

### filler labels only (8)
- aquariumrescueunit-1992-07-07 [delivered] [11,23]→[10,23] OK better: "Set II 11) Band Intros > Jam" (filler → set 2)
- joerussosalmostdead-2016-03-25 [packaged] [8,13]→[8,14] OK equal: notes "07. encore break/crowd / Encore: 08. Sugar Magnolia" (crowd now in set 2, as listed)
- moe-2004-04-17 [delivered] [7,12]→[7,13] OK equal: "Encore: Faker> Moth" (Crowd/Banter → set 2; the taper lists no filler)
- moe-2008-06-20 [delivered] [6,12]→[6,13] OK equal (class H): "E / 1 crowd / 2 godzilla" (crowd ships in set 2 on step 1's split)
- soundtribesector9-2005-04-13 [delivered] [7,14]→[7,15] OK equal (class H): "(encore) 08. Encore Break 09. What is Love?" (break ships in set 2)
- thedead-2009-05-02 [delivered] [7,21]→[7,20] OK better: "Encore 1. Crowd 2. Organ Donor Rap 3. Sampson and Delilah"
- umphreysmcgee-2005-09-02 [delivered] [9,18]→[9,19] OK equal: "Disc 3 1. ~encore break~ 2. E: Lenny >" (taper-literal)
- yondermountainstringband-2010-07-17 [packaged] [10]→[11] WORSE cosmetic (class H): "Set Two: 01. Set 2 intro" now ships in set 1 (stored llm had set 2)

## Checks asked for
1. Taper text placed on the right tracks: yes in all 91 rows. Every placed break sits at the taper's stated last-song/first-song pair on this tape's titles. No placement error was found.
2. After vs before: worse only in class G (3), mymorningjacket (by design, held) and yondermountainstringband-2010-07-17 (filler, cosmetic).
3. Encore changes: every grow or shrink matches the taper's text. Ruling (d) is respected to the letter: in every row with no taper encore, the base replay or step 1 had no encore after the last taper break. The 3 lost encores all come from stored LLM structures that step 1 does not reproduce (class G).
4. Set-count changes are genuine per the taper text: GSBG-2006 1→3, GD-1974 2→3 (Seastones), MMJ 3→2, TTB-2019 4→2+E, TTB-2020 3→2+E, JRAD 3→2+E, RyanAdams-2008-01-19 3→2, and several 1→2. Two are debatable on the performance: GD-1974 (unclear) and MMJ (worse, held).

## Things the operator should look at before re-processing
1. **Class G ruling.** Decide whether ruling (d) should also turn ownership off when the taper marks no encore and today's path would reach the LLM branch (step-1 coverage < threshold, no anchoring). That fixes johnkadlecik-2013-06-22, newridersofthepurplesage-2006-04-08, radiators-2010-06-05, and held jackiegreene-2011-02-12. It also guards future gathers, where the same fold would ship with no listing. Until then, exclude these from any re-processing of non-held shows.
2. **Voiced rows** (re-delivery discards DJ audio): gratefuldead-1974-09-18 (unclear: Seastones as "Set Two", the third set opening with Loose Lucy would be read on air), tedeschitrucksband-2018-10-13 (better), -2022-03-26 (equal: only Trophy Presentation moves), -2023-03-31 (better).
3. **Taper vs jerrybase disagreements** that are now only notes: darkstarorchestra-2006-11-29 (unclear), plus darkstarorchestra-2001-12-15, furthur-2010-05-29, philleshandfriends-2006-07-03, thedead-2009-05-01 (the taper is plausible; setlist.fm agreed in most).
4. **mymorningjacket-2018-03-05** is newly held by vet: the taper's 2 sets merge two of the three album sets. Re-processing it holds a show that is clean today, and clearing it needs an operator structure override.
5. **Class H filler placement** (cosmetic): a "Set 2 intro"/"Encore Break" track can carry the wrong side's label when step 1 put it there. That follows the spec's "moves no filler" rule; change the rule only if the operator wants the taper's explicit filler lines to win.
6. Aside, not structural: tedeschitrucksband-2023-03-31's description header reads "Chicago Theatre … March 18, 2023". The library date may deserve a glance.
