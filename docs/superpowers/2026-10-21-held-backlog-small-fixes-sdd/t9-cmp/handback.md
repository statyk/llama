# t9-cmp handback: Task 9 compare (--no-repro-gate) for held-backlog small-fixes

Status: DONE_WITH_CONCERNS (compare exit 0; no venue/city flag change, no flag added, no newly held; concerns listed below)

Preflight: llama.__file__ = .../held-backlog-small-fixes/packages/llama/src/llama/__init__.py (inside worktree); git status --porcelain empty. Compare run once, output dir /Users/shawn/.llama-harness/small-fixes/cmp-norepro/. cmp/ untouched. Nothing re-run.

Compare text: "baseline reproduces 134/147 held shows that are not needs-LLM (gate skipped: --no-repro-gate)"; "jerrybase: skipped 117 malformed rows"; exit 0.

## Acceptance verdict
- B: no flag change on any venue_changes row (234/234 "flags: unchanged"; summary says 0 with a flag change). No venue or city flag added or removed. PASS.
- D: flags.txt has one family, research-song: removed 1, added 0. No family has added > 0. packaged_exposure.txt "newly held" = (none). PASS.
- predicted_list.json: 5 rows. (Not for apply; see below.)

## B: venue_changes.txt
- Shows listed: 234 (base -> cand venue or city string changed).
- Rows marked `flags CHANGED`: 0.
- Rows marked DELIVERED: 154 (states: delivered 154, packaged 60, held 18, briefed 2).
- Rows whose CITY string changes: 65 (all 65 also change venue string, except 1 city-only row where the venue is identical).
- Flag changes on venue-changed rows: none, so no add/remove list and no attribution needed.

Outcome diffs base->cand over all 3983 shows: clean->clean-changed 163 (venue/city string rows), newly-held->clean 1 (joerussosalmostdead-2019-03-03), still-held->needs-brief 1 (johnkadlecik-2021-11-28). Nothing moved into a held state.

## D: flags, titles
- flags.txt: research-song: removed 1, added 0 (johnkadlecik-2021-11-28: 4 "research asserts unknown song" flags removed: Don't Let Go; Ain't No Bread In The Breadbox; He Ain't Give You None; What's Become Of Mary). Newly cleared: 1 (that show, held -> needs-brief). Attribution: slice D (apostrophe fold in vet matching); the songs all carry apostrophes.
- Other D-pattern flag removals seen in cand.json vs base.json, on NON-held shows (so not in flags.txt, which is held scope; none added): vet_flags "research asserts unknown song" removed on joerussosalmostdead-2017-10-07 (Uncle John's Band), -2017-11-09 (He's Gone), -2019-03-03 (9 songs; this one flips newly-held -> clean), -2019-06-15 (He's Gone), -2022-07-21 (He's Gone). gather_flags "low-confidence structure alignment" removed on joerussosalmostdead-2016-02-12 and thetravelinmccourys-2014-05-24 (neither is in venue_changes). I attribute these to slice D (fuzzy_norm_title reaches align) by inference only; I did not trace them. All are removals.
- Title changes: title_sources.txt has 1 row: northmississippiallstars-2010-03-11 #12 'nma2010-03-11t13.mp3' (unresolved) -> 'ML' (tags). base.json and cand.json carry IDENTICAL title_changes for every show, so this is NOT branch-driven (same in the base arm). No D-driven title changes found.
- packaged_exposure.txt: 214 entries (the 'shipped fields that would change' list is the same venue/city set as B); title changes section = the one row above; "newly held" = (none).

## predicted_list.json (cmp-norepro)
5 rows: northmississippiallstars-2010-03-11, themotet-2013-04-20, minutemen-1985-11-30, johnkadlecik-2021-11-28, darkstarorchestra-2004-11-14, all outcome needs-brief, briefing fresh. Only johnkadlecik-2021-11-28 changed between arms (still-held -> needs-brief). The other four were already needs-brief in the base arm (base needs-brief 4, cand 5), i.e. Tier-1 leftovers and the minutemen-1985-11-30 owner-left-held case: not this branch. This list is MEASUREMENT ONLY, was produced with --no-repro-gate, is tied to this branch's sha (36473d8...), and was not copied anywhere. Do not apply it.

## Concerns for the owner (not defects against the acceptance text)
1. Tie-break ships the selected recording's own string verbatim, so some messy formatting now ships where the vote's string was cleaner. Examples: "Amhearst, MA" (furthur-2010-02-19, base "Amherst, MA"), "Royal Oak,MI", "Philadelphia,Pa", "Lawrence , KS", "Louisville , KY", "Philadelphia Pa", "House of Blues,", "The Spirit of Suwanee Music Park,", "Alexian Field,", "Red Rocks Ampitheater/Ampitheatre" (typos), "Studio 105" (a typo FIX vs "Studio 10S"), format markers "BB King Blues Club (24bit)", "Wanee @ Spirit of the Suwanee -- 24 bit file set". This is the spec's stated behaviour (the selected recording's string wins), but the owner may want to look.
2. Truncations: smashingpumpkins-1993-08-24 "Melody - Stockholm, Sweden (13 thir13en Remaster)" -> "Melody"; -1993-09-15 "Manchester Academy - Manchester, UK ..." -> "Academy"; perpetualgroove-2004-10-09 "Ziggy's" -> "Speed of Surround Tour Presented in Dolby 5.1 Surround Live @ Ziggy's"; godspeedyoublackemperor-1999-09-04 "9:30 Club" -> "Nightclub".
3. Baseline reproduction was 134/147 (known drift, ruled; below).

## Owner hand-check lists (Step 5)

### (a) venue_changes rows whose two venue strings are NOT plain spelling variants of one place
Judgment-based, from the 180 rows that differ beyond case/punctuation/leading "The". Full file: /Users/shawn/.llama-harness/small-fixes/cmp-norepro/venue_changes.txt (234 rows). A mechanical pre-list of all 180 non-trivial rows is at /private/tmp/nontriv.txt (scratch). My judged list (about 38 rows; slug [state]: old -> new; note):
Different place or different named thing:
1. campervanbeethoven-2004-10-24 [delivered]: Mad City Music Exchange -> Luther's Blues
2. derektrucksband-2002-04-05 [delivered]: 103.5 The Fox -> Bluebird
3. derektrucksband-2005-12-02 [HELD]: Headliners -> WFPK Radio (city Louisville Ky -> KY only)
4. derektrucksband-2009-08-15 [delivered]: Oregon Ridge Park -> Hot August Blues Festival (park vs event)
5. godspeedyoublackemperor-1999-09-04 [packaged]: 9:30 Club -> Nightclub (generic, worse)
6. jeffaustinband-2018-04-28 [delivered]: Charm City Bluegrass Festival -> 8x10 (event vs club)
7. jjgreyandmofro-2007-02-16 [delivered]: CD Connection -> Florida Theatre (city Jacksonville Beach, FL -> Jacksonville, FL)
8. mekons-1989-12-02 [delivered]: Wax Trax -> Metro
9. minutemen-1983-12-16 [packaged]: Love Hall -> The Love Club
10. minutemen-1985-11-30 [HELD, owner-left-held]: WREK Air Studio -> Georgia Institute Of Technology
11. ryanadams-2007-06-18 [delivered]: Cities 97 - Studio C -> The Cedar
12. stevekimock-2005-05-21 [delivered]: Oakly Farm -> Haymaker Festival
13. thegourds-2009-12-05 [delivered]: Texas Union Ballroom -> Jovita's (city Austin, Tx -> TX only)
14. belafleckandtheflecktones-2007-06-29 [packaged]: Syracuse Jazz Fest-Main Stage -> Onondaga Community College
15. belafleckandtheflecktones-1991-08-02 [delivered]: Lonesome Pine -> Kentucky Center for the Arts, Bomhard Hall, Lonesome Pine Special (series vs hall)
16. greenskybluegrass-2010-05-29 [HELD]: Allegany County Fairgrounds -> DelFest - Potomac Stage; thetravelinmccourys-2015-05-23 [delivered]: DelFest Grand Stage -> DelFest - Allegany County Fairgrounds
17. yondermountainstringband-2006-06-11 [delivered]: Wakarusa ... Sun Up Stage -> Sun-Down Stage, Wakarusa Festival (different stage)
18. yondermountainstringband-2005-10-22 [delivered]: The State Theater -> State Theatre; city Falls Church, VA -> East Falls Church, VA
19. fennario-2010-09-17 [delivered]: Wormtown ... Vernville Stage -> Camp Kee-Wanee
20. moe-2007-03-24 [delivered]: Herb Brooks Arena -> Olympic Center (arena vs complex); moe-2008-01-30 [delivered]: Promowest Pavillion -> Lifestyle Communities Pavilion (renamed venue)
21. tedeschitrucksband-2015-04-18 [delivered]: Blue Ridge Ampletheatre -> Blue Ridge Bowl at Lockn' Farm; -2019-08-24: Arrington Virginia -> Lockn'; -2018-07-17: Artpark Amphitheater -> Artpark Lewiston, NY (Wheels Of Soul)
22. Festival-vs-stage reframings (same site, different level of name): billystrings-2020-02-21, bluegroundundergrass-2005-05-27, gracepotterandthenocturnals-2009-07-24 (Floydfest 8), karldensonstinyuniverse-2005-07-03 (Grandstand Stage, HSMF), lettuce-2009-11-14 and dumpstaphunk-2009-11-14 (Spirit of the Suwannee -> Bear Creek ...), jjgreyandmofro-2008-04-11 (Peach Stage), railroadearth-2008-07-03 (Sherwood Court), meatpuppets-2013-07-13 (TC Roots ... Harriett Brewing stage), moe-2003-06-15 (Which Stage, Bonnaroo), pnuma-2006-05-19, robertrandolph-2002-06-23 (Ballroom Stage - Bonnaroo -> Bonnaroo), umphreysmcgee-2008-05-23, umphreysmcgee-2008-08-09, mymorningjacket-2004-06-12, larrykeel-2001-06-09, newmastersounds-2010-07-03, strangefolk-2002-09-01
Lossy/odd forms: smashingpumpkins-1993-08-24 ("Melody"), -1993-09-15 ("Academy"), perpetualgroove-2004-10-09 (tour title string), papamali-2008-04-11 [HELD] (24 bit file set marker), stevekimockband-2004-03-27 (16bit -> 24bit marker), gratefuldead-1970-01-02-spans [HELD] ("Fillmore East (show b- Late?)" -> "(Early and Late Shows)"), furthur-2010-02-19 (city "Amhearst, MA").
All remaining rows are spelling/punctuation/article/abbreviation variants (Theatre/Theater, Pavilion, Ft./Fort, "The", state abbreviations, etc.).

### (b) Every DELIVERED row
154 rows (informational; delivered shows keep their spelling until re-gathered). Path: /Users/shawn/.llama-harness/small-fixes/cmp-norepro/venue_changes.txt (grep DELIVERED). First 40 slugs: antibalasmusic-2003-04-28, antibalasmusic-2004-11-03, aquariumrescueunit-2004-10-20, aquariumrescueunit-2006-11-12, belafleckandtheflecktones-1991-08-02, belafleckandtheflecktones-1995-08-25, belafleckandtheflecktones-2002-08-10, belafleckandtheflecktones-2006-03-16, belafleckandtheflecktones-2009-12-12, billystrings-2020-02-21, billystrings-2021-09-17, blackberry-smoke-2014-01-23, bluegroundundergrass-2005-05-27, campervanbeethoven-2003-02-28, campervanbeethoven-2004-10-24, cowboyjunkies-1989-04-30, cracker-2005-08-26, cracker-2005-11-01, cracker-2014-12-31, darkstarorchestra-2015-09-24, deadandcompany-2016-06-10, deadandcompany-2016-07-10, derektrucksband-2002-04-05, derektrucksband-2005-11-13, derektrucksband-2006-10-28, derektrucksband-2009-04-16, derektrucksband-2009-08-15, discobiscuits-2000-08-26, discobiscuits-2000-11-02, discobiscuits-2000-11-25, discobiscuits-2004-05-29, discobiscuits-2009-02-28, drive-bytruckers-2005-07-27, drive-bytruckers-2006-09-27, dumpstaphunk-2009-11-14, dumpstaphunk-2011-07-21, elliottsmith-1996-11-18, elliottsmith-1998-04-15, fennario-2010-09-17, furthur-2010-02-19.

### (c) Non-venue flag changes on venue-changed rows
None. All 234 rows say "flags: unchanged".

### (d) D-driven title changes
None. The single title change (northmississippiallstars-2010-03-11 #12) is identical in base and cand, not D-driven.

## summary.txt (full)
base reproduces 134/147 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 192, cand 192
briefing guard reproduces 3/4
drift.txt: 197 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 1 famil(ies)
newly cleared: 1
packaged_exposure.txt: 214 entr(ies)
venue_changes.txt: 234 show(s), 0 with a flag change
title_sources.txt: 1 row(s)
structure_changed.txt: 0 show(s)
hand_check_sample.txt: 1 show(s)
closest_calls.txt: 703 row(s)
needs_llm.txt: base 697, cand 697
notes.txt: 455 note(s)
predicted_list.json: 5 row(s)
structure_changed_list.json: 0 row(s)
pilot_list.json: 5 row(s)

## Files compare wrote (/Users/shawn/.llama-harness/small-fixes/cmp-norepro)
briefings.txt
closest_calls.txt
drift.txt
flags.txt
hand_check_sample.txt
narration_candidates.html
needs_llm.txt
notes.txt
outcomes.txt
packaged_exposure.txt
pilot_list.json
predicted_list.json
structure_changed_list.json
structure_changed.txt
summary.txt
title_sources.txt
venue_changes.txt

## sha256
ea080f4d4313808e10c8267e4af4c2f0919512204a08ca6676ee6b4eb6b7b867  summary.txt
5ba508263b3688d0d1034a5eed08a868a24674e1489c8aecbb525b639b608514  venue_changes.txt
cbd2c7cde383fbfde8747e143366c6582868d8da2f34d1a66844774ccb630790  flags.txt
f3c71dae66c341352beba1af28282b0b11ac9426eb2102edac34022e1d5afe39  packaged_exposure.txt
2b06f70352bee282657e413c845db579455daaad8a289a07be2bd55c455aeae5  predicted_list.json

## Known base drift (Tier-1 owner-rejected / not applied)
13 held slugs from ~/.llama-harness/small-fixes/cmp/drift.txt:
- corblund-2004-11-04
- discobiscuits-2006-02-04
- gratefuldead-1966-03-12
- gratefuldead-1979-02-03
- gratefuldead-1983-06-18
- gratefuldead-1991-06-25
- littlefeat-1977-08-02
- minutemen-1985-11-30
- northmississippiallstars-2010-03-11
- radiators-2010-07-17
- ratdog-2000-06-24
- soundtribesector9-2008-07-05
- umphreysmcgee-1998-09-17
The remaining 185 drift rows (packaged/delivered/briefed) are the same base-vs-library class: stored flags written by older code that current code does not reproduce. Not this branch.

## State
Nothing applied. ~/.llama untouched (no writes). Base worktree /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes-base left in place for the owner to remove. arms base.json and cand.json and cmp/ untouched. predicted_list.json (cmp-norepro) is measurement-only, built under --no-repro-gate, and tied to this branch's sha (llama reapply --from-list refuses it under a different installed code); after merging, the owner re-runs both arms from the merged tree before any apply.
