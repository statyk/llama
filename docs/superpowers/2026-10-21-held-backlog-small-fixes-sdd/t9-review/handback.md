VERDICT: ACCEPT WITH NOTES

## Findings
- Minor (spec-letter deviation, needs an owner ruling): an operator venue override does not fully shield the city from the tie-break. On jackiegreene-2010-05-29 [packaged], the venue override is "Furthur Festival, Furthur Stage" and there is no city override. The vote is a 1-1 tie ('Furthur - Dark Hollow Stage' vs 'furthur festival, furthur stage'). The shipped city changes from base 'Angels Camp, California' to cand 'angels camp, california'. Cause: gather.py applies `elif tie is not None: venue, city = tie  # slice B: no event` before `if overrides.venue is not None: venue, venue_source = overrides.venue, "override"`, and that line replaces only the venue. The spec says arms that choose the venue themselves, including "operator override", are unaffected. This matches the existing swap/1c precedent (a venue override keeps the chain's city). The change is case-only and the city gate held. It is 1 show of 3983, with no flag change. If the owner wants the letter of the spec: `tie = None if overrides.venue is not None else venue_tie_break(candidate, sel)`.
- Minor (report completeness): the owner hand-check lists in t9-cmp/handback.md are incomplete. List (b) gives only 40 of the 154 DELIVERED slugs; all 154 are below. List (a) is judgment-based and leaves out several festival-vs-site or different-name rows of the same class as its item 22; they are listed below. It also writes "robertrandolph-2002-06-23"; the slug is robertrandolphandthefamilyband-2002-06-23.
- Minor (premise detail; the ruling stands): of the 13 held drift rows, 12 are "current code clears or narrows stored flags". gratefuldead-1966-03-12 is the reverse: the base replay ADDS a 1d flag ("recordings of this date disagree on city: '???, CA' (selected) vs 'Los Angeles, CA'") that stored show.json lacks. It is still base-vs-library and identical in both arms, so it is not this branch.
- Minor (harness readability): venue_changes.txt prints `null` for a field that neither arm changed, because `_shipped` returns None when neither arm has a diff. Examples: jackiegreene shows "venue: null -> null", and 169 rows show "city: null -> null". The docstring documents this, but a human doing the hand-check can read it as "no city". The real values are the stored show.json values.

## Check 1: headline numbers (recomputed from base.json/cand.json with my own script)
- Both arms replayed 3983 shows, with the same slug set and 0 unreplayable.
- Venue or city changed (shipped value = the arm's diff `new`, else stored): 234 shows. 154 are delivered (packaged 60, delivered 154, held 18, briefed 2), and 65 change the city string. There is 1 city-only row: jackiegreene-2010-05-29 (above). **All match the runner.**
- Venue/city flags (`venue mismatch:` prefix or `recordings of this date disagree on city`) added or removed ANYWHERE in the 3983 shows: **0**.
- Shows whose flag multiset (gather + vet + brief) differs at all: 8. All are removals, there are 0 additions, and none is a venue_changes row.
  - johnkadlecik-2021-11-28 [held]: −4 "research asserts unknown song" (Don't Let Go; Ain't No Bread In The Breadbox; He Ain't Give You None; What's Become Of Mary). Goes still-held → needs-brief. Cause: slice D.
  - joerussosalmostdead-2017-10-07 [packaged]: −Uncle John's Band. Slice D.
  - joerussosalmostdead-2017-11-09 [packaged]: −He's Gone. Slice D.
  - joerussosalmostdead-2019-06-15 [packaged]: −He's Gone. Slice D.
  - joerussosalmostdead-2022-07-21 [packaged]: −He's Gone. Slice D.
  - joerussosalmostdead-2019-03-03 [packaged]: −9 unknown-song flags. Goes newly-held → clean. Slice D, which lets Tier-1 4a fire (details in check 3).
  - joerussosalmostdead-2016-02-12 [delivered]: −"low-confidence structure alignment", and needs_llm drops `align_structure`. Slice D.
  - thetravelinmccourys-2014-05-24 [packaged]: −"low-confidence structure alignment", and needs_llm drops `align_structure`. Slice D.
- Outcome transitions: clean → clean-changed 163 (venue rows), newly-held → clean 1, still-held → needs-brief 1. Nothing moves into a held state, and the newly-held sets differ only by joerussosalmostdead-2019-03-03, which leaves it.
- title_changes, date, set_changes, segue_changes, set_breaks and alignment are identical between the arms for every show, so there are 0 D-driven title changes. The one title_sources row (northmississippiallstars-2010-03-11 #12) is identical in both arms.
- flags.txt: "research-song: removed 1, added 0" is correct. Only held shows are in scope, and johnkadlecik is the only held one.
- packaged_exposure.txt says newly held = (none). Correct.
- predicted_list.json: 5 rows, sha 36473d8. In base, 4 of them are already needs-brief (northmississippiallstars-2010-03-11, themotet-2013-04-20, minutemen-1985-11-30, darkstarorchestra-2004-11-14). Only johnkadlecik-2021-11-28 changes outcome. **Correct.**
- briefing: 163 rows go reuse → fresh because a venue change invalidates briefing reuse, and 4 D rows change too. This is informational: any later regather of those shows spends a fresh brief.

## Check 2: every venue/city change is slice B as the spec defines it
- I built an independent model of the spec's chain over all 3983 shows from ~/.llama provenance/show/overrides (read-only). It uses grouping's raw-string Counter tie, the city gate, and these arms: no-event / 1a-unflagged / step 1 on the tie string's full test / not in swap, 2venue, 1c, else, enrichment / then 1d / then the overrides. It predicts base and cand shipped venue+city for **3983/3983 shows with 0 mismatches**.
- Ties with a selected venue: 293. 34 are refused by the city gate (correct). 25 pass the gate but do not ship, for the following reasons: event arms (step-1 tie string fails jerrybase, flagged 2venue/else, swap, 1c), or a venue override with an equal city. The remaining 234 change: 222 in the no-event arm, 11 in step 1, and 1 under a venue override (jackiegreene).
- On all 234 rows: the raw vote is truly tied (n=2: 23, n=3: 2, n=4: 1, the rest n=1). Cand venue == the selected recording's `.strip()`ped own venue (1 row had real surrounding whitespace). Cand city == `sel_city or vote_city`. 0 city-gate bypasses. Base == the vote on 233 rows (jackiegreene = override).
- The traced rows agree with literal archive.org metadata (`~/.llama/cache/md_<id>.json` `venue`/`coverage` fields), so **nothing is truncated or mangled by the code**:
  - smashingpumpkins-1993-08-24: the selected tsp1993-08-24.fm.flacf has venue='Melody', a 1-1-1 tie with 'Melody Club' and 'Melody - Stockholm, Sweden (13 thir13en Remaster)'. (a)
  - smashingpumpkins-1993-09-15: the selected tsp1993-09-15.shn has venue='Academy', a 1-1 tie. (a)
  - godspeedyoublackemperor-1999-09-04: the selected gybe1999-09-04.shn has venue='Nightclub' (the item title literally says "Live at Nightclub"), a 1-1 tie with '9:30 Club'. City 'Washington, DC' is compatible with 'Washington, District of Columbia', so the venue changes and the city does not. (a), but a worse string.
  - perpetualgroove-2004-10-09: venue='Speed of Surround Tour Presented in Dolby 5.1 Surround Live @ Ziggy's' is literal metadata. (a)
  - furthur-2010-02-19: the selected recording's coverage is 'Amhearst, MA'. `cities_compatible` accepts it as a one-edit typo of 'Amherst, MA' (both keys ≥ 6 chars), and the spec ships `sel_city or vote_city`, so the typo ships. 1-1-1 tie. (a)
  - campervanbeethoven-2004-10-24: the selected CVB2004-10-24b.FLAC has venue "Luther's Blues", a 1-1 tie with 'Mad City Music Exchange'. City 'Madison, Wisconsin' fits by containment. This is probably two performances grouped as one (spec non-goal). The new string matches the audio that ships. (a)
  - derektrucksband-2005-12-02 [held]: 'Headliners' → 'WFPK Radio', the same pattern as the previous row. (a)
  - jackiegreene-2010-05-29: city-only change under a venue override. (b)-ish, Minor (see Findings).

## Check 3: the non-held removals the runner attributed to D by inference
Traced, not inferred:
- I ran `vet_research.grounding_flags` on the stored show and vetting in both trees' interpreters.
  - 2017-10-07: tape 'Uncle John’s Band @#$ +' (U+2019) vs research "Uncle John's Band". Unknown count 15 → 14.
  - 2017-11-09, 2019-06-15 and 2022-07-21: tape 'He’s Gone …'. Each loses 1.
  - 2019-03-03: tape 'Don’t Ease Me In #' and 'King Solomon’s Marbles %' become known. Unknown goes 9 → 7, and 9/16 tape tracks are now asserted (≥ 0.5). The 4a right-show gate converts the remaining 7 to a note ("unknown-song flags suppressed by the right-show gate: 9/16 … ratio 0.56"). That is D enabling the existing Tier-1 4a rule, as designed.
  - johnkadlecik-2021-11-28: its sibling-format titles are curly ('What’s Become Of Mary', 'He Ain’t Give You None', 'Ain’t No Bread In The Breadbox', 'Don’t Let Go'). Unknown goes 4 → 0.
- The alignment flag removals come from `fuzzy_norm_title` in `align()`:
  - thetravelinmccourys-2014-05-24: the descriptions carry 'Let’s Sing Our Song' and 'Feudin’ Banjos' while the tape tags are straight. Base gives `fuzzy_norm_title('Let’s Sing Our Song')='let s sing our song'` ≠ 'lets sing our song'; cand makes them equal.
  - joerussosalmostdead-2016-02-12: the tape has 'Uncle John’s Band $ (All) >' and the canonical is straight. Base gives 'uncle john s band' ≠ 'uncle johns band'; cand makes them equal.
- The gather.py diff touches venue/city only (slice B), so it cannot reach alignment or vet.
- **0 removals without a branch cause.**

## Check 4: the 13 held drift rows
- cmp/drift.txt and cmp-norepro/drift.txt are byte-identical (197 rows). On all 13 held rows, base and cand agree exactly, on both the flags and `reproduces`.
- Of all 197 drift rows, the arms disagree only on 4 packaged joerussosalmostdead rows (the D removals above).
- Gate population: base reproduces 134/147 and cand 133/147. The difference is johnkadlecik-2021-11-28, where D clears flags that stored show.json still carries.
- So the 13 are base-vs-library, not this branch. One caveat (gratefuldead-1966-03-12) is in Findings.

## Check 5: hand-check lists (brief Step 5)
- (c) "No non-venue flag change on a venue-changed row" is correct (verified).
- (d) "No D-driven title change" is correct (verified).
- (b) is incomplete. All 154 DELIVERED rows:
  antibalasmusic-2003-04-28 antibalasmusic-2004-11-03 aquariumrescueunit-2004-10-20 aquariumrescueunit-2006-11-12 belafleckandtheflecktones-1991-08-02 belafleckandtheflecktones-1995-08-25 belafleckandtheflecktones-2002-08-10 belafleckandtheflecktones-2006-03-16 belafleckandtheflecktones-2009-12-12 billystrings-2020-02-21 billystrings-2021-09-17 blackberry-smoke-2014-01-23 bluegroundundergrass-2005-05-27 campervanbeethoven-2003-02-28 campervanbeethoven-2004-10-24 cowboyjunkies-1989-04-30 cracker-2005-08-26 cracker-2005-11-01 cracker-2014-12-31 darkstarorchestra-2015-09-24 deadandcompany-2016-06-10 deadandcompany-2016-07-10 derektrucksband-2002-04-05 derektrucksband-2005-11-13 derektrucksband-2006-10-28 derektrucksband-2009-04-16 derektrucksband-2009-08-15 discobiscuits-2000-08-26 discobiscuits-2000-11-02 discobiscuits-2000-11-25 discobiscuits-2004-05-29 discobiscuits-2009-02-28 drive-bytruckers-2005-07-27 drive-bytruckers-2006-09-27 dumpstaphunk-2009-11-14 dumpstaphunk-2011-07-21 elliottsmith-1996-11-18 elliottsmith-1998-04-15 fennario-2010-09-17 furthur-2010-02-19 garajmahal-2004-07-24 gratefuldead-1972-05-26 gratefuldead-1973-02-22 gratefuldead-1979-01-11 gratefuldead-1994-06-26 greenskybluegrass-2008-12-06 greenskybluegrass-2013-04-13 jeffaustinband-2018-04-28 jjgreyandmofro-2007-02-16 jjgreyandmofro-2007-03-09 joerussosalmostdead-2015-04-22 joerussosalmostdead-2015-05-24 joerussosalmostdead-2018-01-14 joerussosalmostdead-2018-08-16 joerussosalmostdead-2019-09-26 joerussosalmostdead-2020-02-21 johnkadlecik-2012-06-10 johnkadlecik-2012-09-14 karldensonstinyuniverse-1998-06-13 karldensonstinyuniverse-2005-07-03 karldensonstinyuniverse-2010-08-27 lettuce-2009-11-14 littlefeat-1973-04-10 littlefeat-1978-06-11 littlefeat-1978-07-08 localh-2008-05-13 loslonelyboys-2004-06-20 lotus-2007-11-23 lotus-2007-11-24 mekons-1989-12-02 mickeyhartband-2008-07-15 moe-2003-06-15 moe-2005-02-27 moe-2005-07-01 moe-2005-10-29 moe-2006-06-03 moe-2007-03-24 moe-2008-01-30 moe-2008-02-02 moe-2008-07-04 moe-2009-02-27 moe-2010-07-17 mogwai-1998-11-30 mymorningjacket-2004-05-16 mymorningjacket-2004-06-12 mymorningjacket-2005-06-23 mymorningjacket-2009-02-04 newridersofthepurplesage-2009-08-09 perpetualgroove-2004-10-09 perpetualgroove-2008-03-06 philleshandfriends-2008-05-13 radiators-1985-11-08 radiators-2003-07-03 railroadearth-2005-02-19 ratdog-2007-08-12 robertrandolphandthefamilyband-2004-02-20 robertrandolphandthefamilyband-2004-03-06 robertwalters20thcongress-2001-06-16 rosehilldrive-2005-06-18 ryanadams-2007-06-18 ryanadams-2008-01-26 ryanadams-2009-03-16 ryanadams-2017-05-06 shinyribs-2017-07-12 smashingpumpkins-1993-06-29 smashingpumpkins-1993-08-24 smashingpumpkins-1993-09-15 smashingpumpkins-1996-07-10 smashingpumpkins-2000-04-16 soundtribesector9-2004-06-18 soundtribesector9-2007-09-29 soundtribesector9-2007-10-02 stevekimock-2005-05-21 stevekimockband-2004-03-27 stringcheeseincident-2004-08-08 stringcheeseincident-2007-08-11 stringcheeseincident-2011-11-26 stuallenandmarshotel-2014-09-24 tealeafgreen-2005-12-15 tealeafgreen-2006-01-13 tealeafgreen-2008-02-08 tedeschitrucksband-2015-04-18 tedeschitrucksband-2015-07-25 tedeschitrucksband-2016-02-27 tedeschitrucksband-2017-02-24 tedeschitrucksband-2017-11-04 tedeschitrucksband-2018-07-17 tedeschitrucksband-2019-08-24 terrapinflyer-2007-01-13 thegourds-2005-06-04 thegourds-2009-12-05 thetravelinmccourys-2015-05-23 umphreysmcgee-2004-11-12 umphreysmcgee-2005-09-14 umphreysmcgee-2005-12-31 umphreysmcgee-2006-06-16 umphreysmcgee-2008-05-23 umphreysmcgee-2008-08-09 warrenzevon-1976-12-08 warrenzevon-1994-02-07 warrenzevon-2000-04-22 ween-2003-10-03 yondermountainstringband-2002-04-20 yondermountainstringband-2005-04-21 yondermountainstringband-2005-04-29 yondermountainstringband-2005-04-30 yondermountainstringband-2005-07-09 yondermountainstringband-2005-10-22 yondermountainstringband-2006-06-11 yondermountainstringband-2006-06-14 yondermountainstringband-2006-08-10 yondermountainstringband-2007-10-06 yondermountainstringband-2008-07-19 zero-1993-04-23
- (a): 58 rows are not `venues_equivalent` base→cand, and the runner names 35 of them (some by abbreviated slug). Of the unlisted 23, these deserve a look as "not a plain spelling variant":
  - mymorningjacket-2005-06-23: 'Festival Peir' → "Penn's Landing"
  - littlefeat-2012-09-02: 'Music In The Zoo' → 'Weesner Amphitheater, Minnesota Zoo'
  - discobiscuits-2000-08-26: 'Saw Mill Ski Area' → 'Camp Bisco, Ski Sawmill'
  - belafleckandtheflecktones-2002-08-10: 'Grassroots Festival, Oregon Ridge Park' → 'Grassroots Music Festival'
  - discobiscuits-2008-06-07: 'Starscape Festival - Fort Armistead Park' → 'Ft Armistead Park'
  - darkstarorchestra-2007-07-12 [held]: 'All Good Music Festival' → "All Good Festival - Marvin's Mountaintop"
  - belafleckandtheflecktones-1995-08-25: 'Green Acres Music Hall' → 'Green Acres Music Park'
  - derektrucksband-2001-12-31: 'Henry J Kaiser Auditorium' → 'Henry J Kaiser Arena'
  - guster-2003-09-28: 'Gray Cage, Bates College' → 'Clifton Daggett Gray Athletic Building, Bates College'
  - smashingpumpkins-1993-06-29: 'Studio 10S' → 'Studio 105' (a fix)

  The rest are spelling, stage-order or abbreviation variants (Knaack Klub/Club, Ironhorse, First/1st Avenue, Riviera Th./Theatre, etc.).

## Concerns for the owner, classified
1. furthur-2010-02-19 'Amherst, MA' → 'Amhearst, MA'. (a) Spec-conforming: the one-edit typo passes `cities_compatible`, and the spec ships `sel_city`.
2. Messy selected strings now ship: "Royal Oak,MI", "Lawrence , KS", trailing commas, "(24bit)" and "24 bit file set" markers, Ampitheater typos. (a) Spec-conforming: "no new normalization", stripped only.
3. 'Nightclub' (gybe), 'Melody', 'Academy' (smashingpumpkins), and the Perpetual Groove tour-title string. (a) Spec-conforming: each is the selected recording's literal archive.org `venue` field, not truncated by the code.
4. "Mad City Music Exchange" → "Luther's Blues" and "Headliners" → "WFPK Radio". (a) Spec-conforming: 1-1 ties of likely mis-grouped performances (a spec non-goal). The new string matches the shipped audio.
5. jackiegreene-2010-05-29: the city changes under an operator venue override. (b)-leaning Minor: it deviates from the letter of "operator override … unaffected", is consistent with the swap/1c precedent, and is cosmetic. It needs an owner ruling.
6. 163 venue-changed shows lose briefing reuse. (a) Spec-conforming ("the briefing header" reads `show.venue`). This only matters if they are regathered.

Nothing was written outside this file and the log. Scratch scripts are in /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-small-fixes/ebe57100-b9d1-4f05-a3b0-c4b5afb1ad48/scratchpad/t9r/ (c1.py–c7.py; c4.py is the independent spec model).
