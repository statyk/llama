# t21arms2 handback
## Identities
CAND HEAD: c49cdd169de1af576fa7a1126108a658f2f1fdbe
llama.__file__: /Users/shawn/projects/llama/.claude/worktrees/title-hygiene/packages/llama/src/llama/__init__.py
OUT: /Users/shawn/.llama-harness/piece3/accept/r2

## Arms (all --all, scratch OUT/r2/scratch/<arm>)
| arm | rc | secs | rows | sha256 |
|--|--|--|--|--|
| cand-asis | 0 | 56 | 3983 | 3b793503c7c5cc3807670d1a6d8db02c3dbf96746f065a51ed34e82fde3ddfc9 |
| cand-fresh | 0 | 67 | 3983 | 35ddd97016115409247c9dd326942502fb0a785c7159128c6c768d0867c97c1c |
| cand-fresh-no5 | 0 | 59 | 3983 | 0753f9396711d01fbf4c1eeaaafc2d296a2553539a37cb5a870fea20ce2ea896 |

Flags: cand-fresh and cand-fresh-no5 used --strip-title-overrides --strip-structure-overrides; no5 added --disable-slices slice5.

## Commands (exit codes)
- CMD cmp-asis rc=0 secs=6
- CMD cmp-fresh rc=0 secs=6
- CMD cmp-slice5 rc=0 secs=5
- CMD parity rc=1 secs=2
- diff rc=1
- CMD packets rc=0 secs=3
- old_vs_new.py (OUT/r2/old_vs_new.py): first run exit 1 (json.dumps tuple-key bug in summary print, after all files were written); fixed and rerun rc=0
- parity rc=1 (mismatches present, expected)

## cmp-asis/summary.txt (verbatim)
```
base reproduces 132/146 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 188, cand 186
briefing guard reproduces 3/4
drift.txt: 201 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 4 famil(ies)
newly cleared: 3
packaged_exposure.txt: 114 entr(ies)
venue_changes.txt: 0 show(s), 0 with a flag change
title_sources.txt: 51 row(s)
structure_changed.txt: 2 show(s)
hand_check_sample.txt: 3 show(s)
closest_calls.txt: 803 row(s)
needs_llm.txt: base 651, cand 653
notes.txt: 1407 note(s)
holds_delta.txt: 7 cleared, 14 added
title_changes.txt: packaged 30, voiced 3, delivered 181
disabled slices: base [], cand []
taper_cleared.txt: 9 show(s)
taper_changes.txt: songs moved 1, labels renamed 0, filler labels only 0, segues changed 0, provenance only 1, needs-llm not owned 463, unreplayable 0, stored-llm moved 2
voiced check: delivery_path /Volumes/media/lma-radio/delivered
holds_delta.txt: 'would-hold on a fresh get' is empty in an as-is arm by construction (only an overrides-stripped arm records `stripped`)
predicted_list.json: 7 row(s)
structure_changed_list.json: 2 row(s)
pilot_list.json: 7 row(s)
```

## cmp-fresh/summary.txt (verbatim)
```
base reproduces 130/145 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 189, cand 187
briefing guard reproduces 3/4
drift.txt: 310 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 4 famil(ies)
newly cleared: 3
packaged_exposure.txt: 186 entr(ies)
venue_changes.txt: 0 show(s), 0 with a flag change
title_sources.txt: 51 row(s)
structure_changed.txt: 2 show(s)
hand_check_sample.txt: 3 show(s)
closest_calls.txt: 1314 row(s)
needs_llm.txt: base 880, cand 858
notes.txt: 2262 note(s)
holds_delta.txt: 40 cleared, 15 added
title_changes.txt: packaged 345, voiced 3, delivered 184
disabled slices: base [], cand []
taper reports: not written (arms replayed with --strip-structure-overrides)
voiced check: delivery_path /Volumes/media/lma-radio/delivered
holds_delta.txt: 'would-hold on a fresh get' is empty in an as-is arm by construction (only an overrides-stripped arm records `stripped`)
apply lists: not written (arms replayed with --strip-structure-overrides or --strip-title-overrides)
```

## cmp-slice5/summary.txt (verbatim)
```
base reproduces 125/147 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 187, cand 187
briefing guard reproduces 3/4
drift.txt: 317 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 0 famil(ies)
newly cleared: 0
packaged_exposure.txt: 28 entr(ies)
venue_changes.txt: 0 show(s), 0 with a flag change
title_sources.txt: 51 row(s)
structure_changed.txt: 2 show(s)
hand_check_sample.txt: 0 show(s)
closest_calls.txt: 1309 row(s)
needs_llm.txt: base 858, cand 858
notes.txt: 2262 note(s)
holds_delta.txt: 0 cleared, 0 added
title_changes.txt: packaged 1, voiced 0, delivered 103
disabled slices: base ["slice5"], cand []
taper reports: not written (arms replayed with --strip-structure-overrides)
voiced check: delivery_path /Volumes/media/lma-radio/delivered
holds_delta.txt: 'would-hold on a fresh get' is empty in an as-is arm by construction (only an overrides-stripped arm records `stripped`)
apply lists: not written (arms replayed with --strip-structure-overrides or --strip-title-overrides)
```

## cmp-asis/holds_delta.txt (full)
```
== holds cleared (7)
-- held now (5)
  blindmelon-1995-09-12  [held]  slices: slice4  still-held -> needs-brief
  minutemen-1984-12-01  [held]  slices: slice2  needs-llm -> structure-changed  (needs-llm)
  motherhips-2010-10-16  [held]  slices: slice2  needs-llm -> needs-brief  (needs-llm)
  radiators-1991-11-01  [held]  slices: slice3  still-held -> needs-brief
  robertwalters20thcongress-2004-01-02  [held]  slices: slice4  still-held -> structure-changed

-- would-hold on a fresh get (0)
  (none)

-- currently shipped (packaged/briefed/delivered/voiced) (2)
  darkstarorchestra-2005-02-19  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  thegrassisdead-2001-10-21  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)

== holds cleared by slice (a show with several is listed under each)
-- slice2 (4)
  darkstarorchestra-2005-02-19
  minutemen-1984-12-01
  motherhips-2010-10-16
  thegrassisdead-2001-10-21
-- slice3 (1)
  radiators-1991-11-01
-- slice4 (2)
  blindmelon-1995-09-12
  robertwalters20thcongress-2004-01-02

== holds added (14)
-- delivered (10)
  buttholesurfers-1988-11-22  flags: low-confidence structure alignment; unresolved track titles  slices: slice1, slice2, slice3  (needs-llm)
  darkstarorchestra-2004-04-24  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Bertha; research asserts unknown song: Mama Tried; research asserts unknown song: Loser; research asserts unknown song: Big River; research asserts unknown song: You Ain't Woman Enough; research asserts unknown song: Here Comes Sunshine; research asserts unknown song: Black-Throated Wind; research asserts unknown song: Ramble On Rose; research asserts unknown song: Me and Bobby McGee; research asserts unknown song: Brown-Eyed Women; research asserts unknown song: Around and Around; research asserts unknown song: Scarlet Begonias; research asserts unknown song: Weather Report Suite; research asserts unknown song: Let It Grow; research asserts unknown song: Space; research asserts unknown song: The Other One; research asserts unknown song: Dark Star; research asserts unknown song: Comes a Time; research asserts unknown song: Uncle John's Band; research asserts unknown song: Sugar Magnolia; research asserts unknown song: Me and My Uncle; research asserts unknown song: Friend of the Devil; research asserts unknown song: Loose Lucy  slices: slice1, slice3  (needs-llm)
  darkstarorchestra-2015-07-11  flags: low-confidence structure alignment; unresolved track titles; research asserts unknown song: White Rabbit; research asserts unknown song: Feedback; research asserts unknown song: Viola Lee Blues; research asserts unknown song: St. Stephen; research asserts unknown song: The Other One; research asserts unknown song: The Eleven; research asserts unknown song: Turn On Your Love Light; research asserts unknown song: Easy Wind; research asserts unknown song: China Cat Sunflower; research asserts unknown song: I Know You Rider; research asserts unknown song: Lovelight; research asserts unknown song: It Hurts Me Too  slices: slice1, slice3  (needs-llm)
  lotus-2010-06-10  flags: unresolved track titles  slices: slice1, slice2, slice3
  philleshandfriends-2007-10-20  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Friend of the Devil; research asserts unknown song: Deep Elem Blues; research asserts unknown song: Bertha; research asserts unknown song: Pride of Cucamonga; research asserts unknown song: Deal; research asserts unknown song: Shine; research asserts unknown song: Plasma; research asserts unknown song: Viola Lee Blues; research asserts unknown song: Cumberland Blues; research asserts unknown song: Viola Lee; research asserts unknown song: Cumberland; research asserts unknown song: Unbroken Chain; research asserts unknown song: Dark Star; research asserts unknown song: Wharf Rat; research asserts unknown song: Help on the Way; research asserts unknown song: Slipknot!; research asserts unknown song: Franklin's Tower; research asserts unknown song: Box of Rain; research asserts unknown song: Alabama Getaway; research asserts 2 sets but structure has 1  slices: slice1, slice3  (needs-llm)
  railroadearth-2007-01-28  flags: unresolved track titles  slices: slice1, slice3
  signalpath-2005-06-09  flags: low-confidence structure alignment; unresolved track titles  slices: slice1, slice2  (needs-llm)
  soulive-2004-02-08  flags: unresolved track titles  slices: slice2, slice3
  stringcheeseincident-2005-07-23  flags: low-confidence structure alignment; unresolved track titles  slices: slice1, slice2  (needs-llm)
  umphreysmcgee-2005-11-12  flags: unresolved track titles  slices: slice1, slice3

-- packaged (3)
  charliehunter-2004-05-22  flags: unresolved track titles  slices: slice2, slice3, slice4
  kinggizzardandthelizardwizard-2022-10-22  flags: low-confidence structure alignment  slices: unattributed  (needs-llm)
  stevekimockband-2002-04-20  flags: unresolved track titles; research asserts unknown song: Tongue 'n Groove; research asserts unknown song: Moon People; research asserts unknown song: A New Africa; research asserts unknown song: Severe Tire Damage; research asserts unknown song: Sabertooth; research asserts unknown song: Five B4 Funk; research asserts unknown song: You're the One; research asserts unknown song: Elmer's Revenge; research asserts unknown song: Why Can't We All Just Samba; research asserts unknown song: Long Form Part IV; research asserts unknown song: Hillbillies on PCP; research asserts unknown song: Avalon  slices: slice1, slice3

-- voiced (1)
  dumpstaphunk-2008-04-25  flags: unresolved track titles  slices: slice2, slice3, slice4

== holds added by slice (from the declines the cascade recorded)
-- slice1 (10)
  buttholesurfers-1988-11-22
  darkstarorchestra-2004-04-24
  darkstarorchestra-2015-07-11
  lotus-2010-06-10
  philleshandfriends-2007-10-20
  railroadearth-2007-01-28
  signalpath-2005-06-09
  stevekimockband-2002-04-20
  stringcheeseincident-2005-07-23
  umphreysmcgee-2005-11-12
-- slice2 (7)
  buttholesurfers-1988-11-22
  charliehunter-2004-05-22
  dumpstaphunk-2008-04-25
  lotus-2010-06-10
  signalpath-2005-06-09
  soulive-2004-02-08
  stringcheeseincident-2005-07-23
-- slice3 (11)
  buttholesurfers-1988-11-22
  charliehunter-2004-05-22
  darkstarorchestra-2004-04-24
  darkstarorchestra-2015-07-11
  dumpstaphunk-2008-04-25
  lotus-2010-06-10
  philleshandfriends-2007-10-20
  railroadearth-2007-01-28
  soulive-2004-02-08
  stevekimockband-2002-04-20
  umphreysmcgee-2005-11-12
-- slice4 (2)
  charliehunter-2004-05-22
  dumpstaphunk-2008-04-25
-- unattributed (1)
  kinggizzardandthelizardwizard-2022-10-22
```

## cmp-fresh/holds_delta.txt (full)
```
== holds cleared (40)
-- held now (5)
  blindmelon-1995-09-12  [held]  slices: slice4  still-held -> needs-brief
  minutemen-1984-12-01  [held]  slices: slice2  needs-llm -> structure-changed  (needs-llm)
  motherhips-2010-10-16  [held]  slices: slice2  needs-llm -> needs-brief  (needs-llm)
  radiators-1991-11-01  [held]  slices: slice3  still-held -> needs-brief
  robertwalters20thcongress-2004-01-02  [held]  slices: slice4  still-held -> structure-changed

-- would-hold on a fresh get (33)
  animalliberationorchestra-2006-12-29  [packaged]  slices: slice4  newly-held -> clean-changed
  bigheadtoddandthemonsters-1991-01-21  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  billystrings-2017-07-15  [delivered]  slices: slice3  newly-held -> clean-changed
  billystrings-2021-12-04  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  blitzentrapper-2013-11-12  [packaged]  slices: slice3  newly-held -> clean-changed
  charlieparr-2003-01-10  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2005-05-30  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2011-04-15  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2012-07-21  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  deepbananablackout-2004-04-01  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  derektrucksband-2006-12-31  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  drive-bytruckers-2008-03-15  [packaged]  slices: slice4  newly-held -> clean-changed
  godspeedyoublackemperor-2002-01-24  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  greyboyallstars-1996-03-09  [packaged]  slices: slice3  newly-held -> clean-changed
  infamousstringdusters-2012-03-16  [packaged]  slices: slice4  newly-held -> clean-changed
  jimlauderdale-2011-07-22  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  lettuce-2002-07-13  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  mymorningjacket-2004-06-18  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  newmastersounds-2012-11-10  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  newridersofthepurplesage-2006-06-30  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  papamali-2010-03-17  [packaged]  slices: slice3  newly-held -> clean-changed
  pnuma-2006-09-21  [packaged]  slices: slice4  needs-llm -> clean-changed  (needs-llm)
  railroadearth-2010-10-02  [packaged]  slices: slice4  newly-held -> clean-changed
  railroadearth-2019-04-08  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  ryanadams-2002-02-06  [briefed]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  soulive-2005-03-11  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  tedeschitrucksband-2015-06-27  [packaged]  slices: slice3  newly-held -> clean-changed
  thecodetalkers-2005-08-06  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  thenewdeal-2009-08-28  [packaged]  slices: slice4  needs-llm -> clean-changed  (needs-llm)
  umphreysmcgee-2006-08-31  [packaged]  slices: slice4  newly-held -> clean-changed
  whitedenim-2013-07-04  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  yondermountainstringband-2005-07-24  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  zero-1986-09-06  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)

-- currently shipped (packaged/briefed/delivered/voiced) (2)
  darkstarorchestra-2005-02-19  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  thegrassisdead-2001-10-21  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)

== holds cleared by slice (a show with several is listed under each)
-- slice2 (19)
  billystrings-2021-12-04
  charlieparr-2003-01-10
  darkstarorchestra-2005-02-19
  darkstarorchestra-2005-05-30
  darkstarorchestra-2011-04-15
  darkstarorchestra-2012-07-21
  deepbananablackout-2004-04-01
  derektrucksband-2006-12-31
  godspeedyoublackemperor-2002-01-24
  minutemen-1984-12-01
  motherhips-2010-10-16
  mymorningjacket-2004-06-18
  railroadearth-2019-04-08
  ryanadams-2002-02-06
  soulive-2005-03-11
  thecodetalkers-2005-08-06
  thegrassisdead-2001-10-21
  yondermountainstringband-2005-07-24
  zero-1986-09-06
-- slice3 (12)
  bigheadtoddandthemonsters-1991-01-21
  billystrings-2017-07-15
  blitzentrapper-2013-11-12
  greyboyallstars-1996-03-09
  jimlauderdale-2011-07-22
  lettuce-2002-07-13
  newmastersounds-2012-11-10
  newridersofthepurplesage-2006-06-30
  papamali-2010-03-17
  radiators-1991-11-01
  tedeschitrucksband-2015-06-27
  whitedenim-2013-07-04
-- slice4 (9)
  animalliberationorchestra-2006-12-29
  blindmelon-1995-09-12
  drive-bytruckers-2008-03-15
  infamousstringdusters-2012-03-16
  pnuma-2006-09-21
  railroadearth-2010-10-02
  robertwalters20thcongress-2004-01-02
  thenewdeal-2009-08-28
  umphreysmcgee-2006-08-31

== holds added (15)
-- delivered (10)
  buttholesurfers-1988-11-22  flags: low-confidence structure alignment; unresolved track titles  slices: slice1, slice2, slice3  (needs-llm)
  darkstarorchestra-2004-04-24  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Bertha; research asserts unknown song: Mama Tried; research asserts unknown song: Loser; research asserts unknown song: Big River; research asserts unknown song: You Ain't Woman Enough; research asserts unknown song: Here Comes Sunshine; research asserts unknown song: Black-Throated Wind; research asserts unknown song: Ramble On Rose; research asserts unknown song: Me and Bobby McGee; research asserts unknown song: Brown-Eyed Women; research asserts unknown song: Around and Around; research asserts unknown song: Scarlet Begonias; research asserts unknown song: Weather Report Suite; research asserts unknown song: Let It Grow; research asserts unknown song: Space; research asserts unknown song: The Other One; research asserts unknown song: Dark Star; research asserts unknown song: Comes a Time; research asserts unknown song: Uncle John's Band; research asserts unknown song: Sugar Magnolia; research asserts unknown song: Me and My Uncle; research asserts unknown song: Friend of the Devil; research asserts unknown song: Loose Lucy  slices: slice1, slice3  (needs-llm)
  darkstarorchestra-2015-07-11  flags: low-confidence structure alignment; unresolved track titles; research asserts unknown song: White Rabbit; research asserts unknown song: Feedback; research asserts unknown song: Viola Lee Blues; research asserts unknown song: St. Stephen; research asserts unknown song: The Other One; research asserts unknown song: The Eleven; research asserts unknown song: Turn On Your Love Light; research asserts unknown song: Easy Wind; research asserts unknown song: China Cat Sunflower; research asserts unknown song: I Know You Rider; research asserts unknown song: Lovelight; research asserts unknown song: It Hurts Me Too  slices: slice1, slice3  (needs-llm)
  lotus-2010-06-10  flags: unresolved track titles  slices: slice1, slice2, slice3
  philleshandfriends-2007-10-20  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Friend of the Devil; research asserts unknown song: Deep Elem Blues; research asserts unknown song: Bertha; research asserts unknown song: Pride of Cucamonga; research asserts unknown song: Deal; research asserts unknown song: Shine; research asserts unknown song: Plasma; research asserts unknown song: Viola Lee Blues; research asserts unknown song: Cumberland Blues; research asserts unknown song: Viola Lee; research asserts unknown song: Cumberland; research asserts unknown song: Unbroken Chain; research asserts unknown song: Dark Star; research asserts unknown song: Wharf Rat; research asserts unknown song: Help on the Way; research asserts unknown song: Slipknot!; research asserts unknown song: Franklin's Tower; research asserts unknown song: Box of Rain; research asserts unknown song: Alabama Getaway; research asserts 2 sets but structure has 1  slices: slice1, slice3  (needs-llm)
  railroadearth-2007-01-28  flags: unresolved track titles  slices: slice1, slice3
  signalpath-2005-06-09  flags: low-confidence structure alignment; unresolved track titles  slices: slice1, slice2  (needs-llm)
  soulive-2004-02-08  flags: unresolved track titles  slices: slice2, slice3
  stringcheeseincident-2005-07-23  flags: low-confidence structure alignment; unresolved track titles  slices: slice1, slice2  (needs-llm)
  umphreysmcgee-2005-11-12  flags: unresolved track titles  slices: slice1, slice3

-- packaged (4)
  derektrucksband-2007-05-25  flags: unresolved track titles  slices: slice1
  gratefuldead-1989-07-19  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Hell in a Bucket; research asserts unknown song: Sugaree; research asserts unknown song: Mama Tried; research asserts unknown song: Mexicali Blues; research asserts unknown song: Althea; research asserts unknown song: Victim or the Crime; research asserts unknown song: West L.A. Fadeaway; research asserts unknown song: Desolation Row; research asserts unknown song: Deal; research asserts unknown song: Box of Rain; research asserts unknown song: Foolish Heart; research asserts unknown song: Looks Like Rain; research asserts unknown song: Terrapin Station; research asserts unknown song: Drums; research asserts unknown song: Jam; research asserts unknown song: Space; research asserts unknown song: The Other One; research asserts unknown song: The Wheel; research asserts unknown song: Morning Dew; research asserts unknown song: Turn On Your Love Light  slices: slice1, slice3  (needs-llm)
  kinggizzardandthelizardwizard-2022-10-22  flags: low-confidence structure alignment  slices: unattributed  (needs-llm)
  steepcanyonrangers-2004-05-21  flags: unresolved track titles  slices: slice2, slice3

-- voiced (1)
  dumpstaphunk-2008-04-25  flags: unresolved track titles  slices: slice2, slice3, slice4

== holds added by slice (from the declines the cascade recorded)
-- slice1 (11)
  buttholesurfers-1988-11-22
  darkstarorchestra-2004-04-24
  darkstarorchestra-2015-07-11
  derektrucksband-2007-05-25
  gratefuldead-1989-07-19
  lotus-2010-06-10
  philleshandfriends-2007-10-20
  railroadearth-2007-01-28
  signalpath-2005-06-09
  stringcheeseincident-2005-07-23
  umphreysmcgee-2005-11-12
-- slice2 (7)
  buttholesurfers-1988-11-22
  dumpstaphunk-2008-04-25
  lotus-2010-06-10
  signalpath-2005-06-09
  soulive-2004-02-08
  steepcanyonrangers-2004-05-21
  stringcheeseincident-2005-07-23
-- slice3 (11)
  buttholesurfers-1988-11-22
  darkstarorchestra-2004-04-24
  darkstarorchestra-2015-07-11
  dumpstaphunk-2008-04-25
  gratefuldead-1989-07-19
  lotus-2010-06-10
  philleshandfriends-2007-10-20
  railroadearth-2007-01-28
  soulive-2004-02-08
  steepcanyonrangers-2004-05-21
  umphreysmcgee-2005-11-12
-- slice4 (1)
  dumpstaphunk-2008-04-25
-- unattributed (1)
  kinggizzardandthelizardwizard-2022-10-22
```

## parity (parity.txt counts; exit 1)
```
parity of cand-fresh.json against the `all` arm of /Users/shawn/.llama-harness/piece3/gate-r16/dump.jsonl
dump sha version:0.1.0; arm disabled_slices []
compared 3983, matching 3971, mismatching 12; skipped 0; arm only 0; dump only 0

```
Mismatching slugs (first differing track; count of differing tracks):
- cowboyjunkies-2017-11-05 (16 tracks): cowboyjunkies-2017-11-05  #1: dump ('Cowboy Junkies - 02 - He Will Call You Baby', 'tags') vs arm ('02 - He Will Call You Baby', 'tags')
- darkstarorchestra-2011-04-15 (1 tracks): darkstarorchestra-2011-04-15  #22: dump ('Playing In The Band(reprise)6:51', 'desc-position') vs arm ('Playing In The Band(reprise)', 'desc-position')
- darkstarorchestra-2014-07-31 (1 tracks): darkstarorchestra-2014-07-31  #3: dump ('Duprees Diamond Blues', 'tags') vs arm ('dso2014-07-31d1t03.mp3', 'unresolved')
- deepbananablackout-2004-04-01 (9 tracks): deepbananablackout-2004-04-01  #2: dump ('--> Take the Time', 'desc-position') vs arm ('Take the Time', 'desc-position')
- gratefuldead-1974-10-18 (1 tracks): gratefuldead-1974-10-18  #24: dump ('Encore- U.S.Blues', 'tags') vs arm ('U.S.Blues', 'tags')
- greenskybluegrass-2013-05-04 (21 tracks): greenskybluegrass-2013-05-04  #1: dump ('Greensky Bluegrass - Dustbowl Overtures', 'tags') vs arm ('Dustbowl Overtures', 'tags')
- greenskybluegrass-2015-02-27 (1 tracks): greenskybluegrass-2015-02-27  #6: dump ("Butcher's Girl ^", 'sibling-format') vs arm ("Butcher's Girl", 'sibling-format')
- guster-2006-07-28 (19 tracks): guster-2006-07-28  #1: dump ('Guster - Careful (4:15)', 'tags') vs arm ('Careful (4:15)', 'tags')
- joerussosalmostdead-2015-10-29 (1 tracks): joerussosalmostdead-2015-10-29  #16: dump ('Jam ^', 'desc-position') vs arm ('Jam', 'desc-position')
- lotus-2008-02-07 (12 tracks): lotus-2008-02-07  #1: dump ('Lucid Awakening H2', 'tags') vs arm ('Lucid Awakening', 'tags')
- mymorningjacket-2004-06-18 (2 tracks): mymorningjacket-2004-06-18  #13: dump ('cobra          $', 'desc-position') vs arm ('cobra', 'desc-position')
- zentricksters-2002-12-31 (1 tracks): zentricksters-2002-12-31  #19: dump ('Banks of the Ohio (actually )', 'tags') vs arm ('Banks of the Ohio (actually d2t10)', 'tags')

## Old-vs-new candidate diff (summary json)
```
{
 "asis": {
  "shows_changed": 7,
  "tracks_changed": 71,
  "by_new_path": {
   "+5": 69,
   "C2": 1,
   "": 1
  },
  "by_new_source": {
   "tags": 70,
   "sibling-format": 1
  },
  "outcome_changes": {},
  "gather_flag_changes": 0,
  "lines": 71
 },
 "fresh": {
  "shows_changed": 12,
  "tracks_changed": 85,
  "by_new_path": {
   "+5": 69,
   "D": 13,
   "": 2,
   "C2": 1
  },
  "by_new_source": {
   "tags": 70,
   "desc-position": 13,
   "unresolved": 1,
   "sibling-format": 1
  },
  "outcome_changes": {
   "clean-changed -> newly-held": 1
  },
  "gather_flag_changes": 1,
  "lines": 87
 }
}
```
changed_asis=       7 changed_fresh=      12 changed_union=      12

### old_vs_new_fresh.txt (      87 lines; <150, full)
```
cowboyjunkies-2017-11-05	track 1	'Cowboy Junkies - 02 - He Will Call You Baby'/tags/'' -> '02 - He Will Call You Baby'/tags/'+5'
cowboyjunkies-2017-11-05	track 2	'Cowboy Junkies - 03 - Southern Rain'/tags/'' -> '03 - Southern Rain'/tags/'+5'
cowboyjunkies-2017-11-05	track 3	'Cowboy Junkies - 04 - Mountain Stream'/tags/'' -> '04 - Mountain Stream'/tags/'+5'
cowboyjunkies-2017-11-05	track 4	'Cowboy Junkies - 05 - Missing Children'/tags/'' -> '05 - Missing Children'/tags/'+5'
cowboyjunkies-2017-11-05	track 5	'Cowboy Junkies - 06 - 200 More Miles'/tags/'' -> '06 - 200 More Miles'/tags/'+5'
cowboyjunkies-2017-11-05	track 6	'Cowboy Junkies - 07 - My Little Basquiat'/tags/'' -> '07 - My Little Basquiat'/tags/'+5'
cowboyjunkies-2017-11-05	track 7	'Cowboy Junkies - 08 - 3rd Crusade'/tags/'' -> '08 - 3rd Crusade'/tags/'+5'
cowboyjunkies-2017-11-05	track 8	'Cowboy Junkies - 09 - Powderfinger'/tags/'' -> '09 - Powderfinger'/tags/'+5'
cowboyjunkies-2017-11-05	track 9	'Cowboy Junkies - 10 - Fairytale'/tags/'' -> '10 - Fairytale'/tags/'+5'
cowboyjunkies-2017-11-05	track 10	'Cowboy Junkies - 11 - River Waltz'/tags/'' -> '11 - River Waltz'/tags/'+5'
cowboyjunkies-2017-11-05	track 11	'Cowboy Junkies - 12 - State Trooper'/tags/'' -> '12 - State Trooper'/tags/'+5'
cowboyjunkies-2017-11-05	track 12	'Cowboy Junkies - 13 - Sweet Jane'/tags/'' -> '13 - Sweet Jane'/tags/'+5'
cowboyjunkies-2017-11-05	track 13	'Cowboy Junkies - 14 - Good Friday'/tags/'' -> '14 - Good Friday'/tags/'+5'
cowboyjunkies-2017-11-05	track 14	'Cowboy Junkies - 15 - Blue Moon Revisited (Song for Elvis) (w encore break)'/tags/'' -> '15 - Blue Moon Revisited (Song for Elvis) (w encore break)'/tags/'+5'
cowboyjunkies-2017-11-05	track 15	'Cowboy Junkies - 16 - Five Years'/tags/'' -> '16 - Five Years'/tags/'+5'
cowboyjunkies-2017-11-05	track 16	'Cowboy Junkies - 17 - Just Want to See'/tags/'' -> '17 - Just Want to See'/tags/'+5'
darkstarorchestra-2011-04-15	track 22	'Playing In The Band(reprise)6:51'/desc-position/'D' -> 'Playing In The Band(reprise)'/desc-position/'D'
darkstarorchestra-2014-07-31	OUTCOME clean-changed -> newly-held
darkstarorchestra-2014-07-31	GATHER_FLAGS [] -> ['unresolved track titles']
darkstarorchestra-2014-07-31	track 3	'Duprees Diamond Blues'/tags/'' -> 'dso2014-07-31d1t03.mp3'/unresolved/''
deepbananablackout-2004-04-01	track 2	'--> Take the Time'/desc-position/'D' -> 'Take the Time'/desc-position/'D'
deepbananablackout-2004-04-01	track 4	'--> Homo Lingo'/desc-position/'D' -> 'Homo Lingo'/desc-position/'D'
deepbananablackout-2004-04-01	track 7	'--> Breakfast at Volos'/desc-position/'D' -> 'Breakfast at Volos'/desc-position/'D'
deepbananablackout-2004-04-01	track 8	'--> Rocker'/desc-position/'D' -> 'Rocker'/desc-position/'D'
deepbananablackout-2004-04-01	track 9	'--> Escapism/Good to Your Earhole'/desc-position/'D' -> 'Escapism/Good to Your Earhole'/desc-position/'D'
deepbananablackout-2004-04-01	track 11	'--> Brunch'/desc-position/'D' -> 'Brunch'/desc-position/'D'
deepbananablackout-2004-04-01	track 12	'--> Getchall 2004'/desc-position/'D' -> 'Getchall 2004'/desc-position/'D'
deepbananablackout-2004-04-01	track 14	'--> TUG'/desc-position/'D' -> 'TUG'/desc-position/'D'
deepbananablackout-2004-04-01	track 24	'Boot!^'/desc-position/'D' -> 'Boot!'/desc-position/'D'
gratefuldead-1974-10-18	track 24	'Encore- U.S.Blues'/tags/'+5' -> 'U.S.Blues'/tags/'+5'
greenskybluegrass-2013-05-04	track 1	'Greensky Bluegrass - Dustbowl Overtures'/tags/'+5' -> 'Dustbowl Overtures'/tags/'+5'
greenskybluegrass-2013-05-04	track 2	'Greensky Bluegrass - Gumboots'/tags/'+5' -> 'Gumboots'/tags/'+5'
greenskybluegrass-2013-05-04	track 3	'Greensky Bluegrass - Train Junkie'/tags/'+5' -> 'Train Junkie'/tags/'+5'
greenskybluegrass-2013-05-04	track 4	'Greensky Bluegrass - Steam Powered Aeroplane'/tags/'+5' -> 'Steam Powered Aeroplane'/tags/'+5'
greenskybluegrass-2013-05-04	track 5	'Greensky Bluegrass - Worried About The Weather'/tags/'+5' -> 'Worried About The Weather'/tags/'+5'
greenskybluegrass-2013-05-04	track 6	'Greensky Bluegrass - Atlantic City'/tags/'+5' -> 'Atlantic City'/tags/'+5'
greenskybluegrass-2013-05-04	track 7	'Greensky Bluegrass - All Four'/tags/'+5' -> 'All Four'/tags/'+5'
greenskybluegrass-2013-05-04	track 8	'Greensky Bluegrass - Leap Year'/tags/'+5' -> 'Leap Year'/tags/'+5'
greenskybluegrass-2013-05-04	track 9	'Greensky Bluegrass - Intro'/tags/'+5' -> 'Intro'/tags/'+5'
greenskybluegrass-2013-05-04	track 10	'Greensky Bluegrass - Through the Trees'/tags/'+5' -> 'Through the Trees'/tags/'+5'
greenskybluegrass-2013-05-04	track 11	'Greensky Bluegrass - Jam'/tags/'+5' -> 'Jam'/tags/'+5'
greenskybluegrass-2013-05-04	track 12	'Greensky Bluegrass - Booty Jam(Bend Over)'/tags/'+5' -> 'Booty Jam(Bend Over)'/tags/'+5'
greenskybluegrass-2013-05-04	track 13	'Greensky Bluegrass - After Midnight'/tags/'+5' -> 'After Midnight'/tags/'+5'
greenskybluegrass-2013-05-04	track 14	"Greensky Bluegrass - Don't Lie"/tags/'+5' -> "Don't Lie"/tags/'+5'
greenskybluegrass-2013-05-04	track 15	'Greensky Bluegrass - In Control'/tags/'+5' -> 'In Control'/tags/'+5'
greenskybluegrass-2013-05-04	track 16	'Greensky Bluegrass - Take Me Away'/tags/'+5' -> 'Take Me Away'/tags/'+5'
greenskybluegrass-2013-05-04	track 17	"Greensky Bluegrass - Can't Stop Now"/tags/'+5' -> "Can't Stop Now"/tags/'+5'
greenskybluegrass-2013-05-04	track 18	"Greensky Bluegrass - That's What Love Will Make You Do"/tags/'+5' -> "That's What Love Will Make You Do"/tags/'+5'
greenskybluegrass-2013-05-04	track 19	"Greensky Bluegrass - Can't Stop Now (Reprise)"/tags/'+5' -> "Can't Stop Now (Reprise)"/tags/'+5'
greenskybluegrass-2013-05-04	track 20	'Greensky Bluegrass - Working On A Building'/tags/'+5' -> 'Working On A Building'/tags/'+5'
greenskybluegrass-2013-05-04	track 21	'Greensky Bluegrass - Whole Lotta Love'/tags/'+5' -> 'Whole Lotta Love'/tags/'+5'
greenskybluegrass-2015-02-27	track 6	"Butcher's Girl ^"/sibling-format/'C2' -> "Butcher's Girl"/sibling-format/'C2'
guster-2006-07-28	track 1	'Guster - Careful (4:15)'/tags/'' -> 'Careful (4:15)'/tags/'+5'
guster-2006-07-28	track 2	'Guster - Barrel of a Gun (4:58)'/tags/'' -> 'Barrel of a Gun (4:58)'/tags/'+5'
guster-2006-07-28	track 3	'Guster - The Captain (3:35)'/tags/'' -> 'The Captain (3:35)'/tags/'+5'
guster-2006-07-28	track 4	'Guster - Ramona (3:58)'/tags/'' -> 'Ramona (3:58)'/tags/'+5'
guster-2006-07-28	track 5	'Guster - Satellite (4:50)'/tags/'' -> 'Satellite (4:50)'/tags/'+5'
guster-2006-07-28	track 6	'Guster - Come Downstairs and Say Hello (7:07)'/tags/'' -> 'Come Downstairs and Say Hello (7:07)'/tags/'+5'
guster-2006-07-28	track 7	'Guster - Demons (4:07)'/tags/'' -> 'Demons (4:07)'/tags/'+5'
guster-2006-07-28	track 8	'Guster - Center of Attention (4:42)'/tags/'' -> 'Center of Attention (4:42)'/tags/'+5'
guster-2006-07-28	track 9	'Guster - Ruby Falls (6:47)'/tags/'' -> 'Ruby Falls (6:47)'/tags/'+5'
guster-2006-07-28	track 10	"Guster - C'mon (4:39)"/tags/'' -> "C'mon (4:39)"/tags/'+5'
guster-2006-07-28	track 11	'Guster - Airport Song (4:52)'/tags/'' -> 'Airport Song (4:52)'/tags/'+5'
guster-2006-07-28	track 12	'Guster - Manifest Destiny (4:57)'/tags/'' -> 'Manifest Destiny (4:57)'/tags/'+5'
guster-2006-07-28	track 13	'Guster - Hang On (4:47)'/tags/'' -> 'Hang On (4:47)'/tags/'+5'
guster-2006-07-28	track 14	'Guster - Amsterdam (4:45)'/tags/'' -> 'Amsterdam (4:45)'/tags/'+5'
guster-2006-07-28	track 15	'Guster - I Spy (5:31)'/tags/'' -> 'I Spy (5:31)'/tags/'+5'
guster-2006-07-28	track 16	'Guster - Fa Fa (6:27)'/tags/'' -> 'Fa Fa (6:27)'/tags/'+5'
guster-2006-07-28	track 17	'Guster - Lightning Rod (3:07)'/tags/'' -> 'Lightning Rod (3:07)'/tags/'+5'
guster-2006-07-28	track 18	'Guster - New Underground (3:47)'/tags/'' -> 'New Underground (3:47)'/tags/'+5'
guster-2006-07-28	track 19	'Guster - Happier (4:53)'/tags/'' -> 'Happier (4:53)'/tags/'+5'
joerussosalmostdead-2015-10-29	track 16	'Jam ^'/desc-position/'D' -> 'Jam'/desc-position/'D'
lotus-2008-02-07	track 1	'Lucid Awakening H2'/tags/'+5' -> 'Lucid Awakening'/tags/'+5'
lotus-2008-02-07	track 2	'Simian H2'/tags/'+5' -> 'Simian'/tags/'+5'
lotus-2008-02-07	track 3	'Bellweather H2'/tags/'+5' -> 'Bellweather'/tags/'+5'
lotus-2008-02-07	track 4	'Sid H2'/tags/'+5' -> 'Sid'/tags/'+5'
lotus-2008-02-07	track 5	'Flower Sermon H2'/tags/'+5' -> 'Flower Sermon'/tags/'+5'
lotus-2008-02-07	track 6	'RockIt H2'/tags/'+5' -> 'RockIt'/tags/'+5'
lotus-2008-02-07	track 7	'Its All Clear To Me Now H2'/tags/'+5' -> 'Its All Clear To Me Now'/tags/'+5'
lotus-2008-02-07	track 8	'Sunrain H2'/tags/'+5' -> 'Sunrain'/tags/'+5'
lotus-2008-02-07	track 9	'Expired Slang H2'/tags/'+5' -> 'Expired Slang'/tags/'+5'
lotus-2008-02-07	track 10	'One Last Hurrah H2'/tags/'+5' -> 'One Last Hurrah'/tags/'+5'
lotus-2008-02-07	track 11	'Intro To A Cell H2'/tags/'+5' -> 'Intro To A Cell'/tags/'+5'
lotus-2008-02-07	track 12	'Spiritualize H2'/tags/'+5' -> 'Spiritualize'/tags/'+5'
mymorningjacket-2004-06-18	track 13	'cobra          $'/desc-position/'D' -> 'cobra'/desc-position/'D'
mymorningjacket-2004-06-18	track 14	'dancefloors    $'/desc-position/'D' -> 'dancefloors'/desc-position/'D'
zentricksters-2002-12-31	track 19	'Banks of the Ohio (actually )'/tags/'+5' -> 'Banks of the Ohio (actually d2t10)'/tags/''
```

## Packets strata (strata_index.txt)
```
billystrings-2021-12-04	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D
charlieparr-2003-01-10	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D; #24 D; #25 D; #26 D; #27 D; #28 D; #29 D; #30 D; #31 D
darkstarorchestra-2005-02-19	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D
darkstarorchestra-2005-05-30	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D
darkstarorchestra-2011-04-15	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D
darkstarorchestra-2012-07-21	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D
deepbananablackout-2004-04-01	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D; #24 D
derektrucksband-2006-12-31	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D
minutemen-1984-12-01	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D
motherhips-2010-10-16	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D; #24 D; #25 D; #26 D
mymorningjacket-2004-06-18	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D
railroadearth-2019-04-08	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D
ryanadams-2002-02-06	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D; #24 D; #25 D; #26 D; #27 D; #28 D; #29 D; #30 D; #31 D; #32 D
soulive-2005-03-11	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D
thecodetalkers-2005-08-06	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D
thegrassisdead-2001-10-21	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D
yondermountainstringband-2005-07-24	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D
zero-1986-09-06	wholly_untagged_d3	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D
animalliberationorchestra-2006-12-29	newly_cleared_sample	#6 4
bigheadtoddandthemonsters-1991-01-21	newly_cleared_sample	#3 C2; #9 C2; #12 C2; #14 C2; #17 C2; #23 C1
billystrings-2017-07-15	newly_cleared_sample	#6 C1; #9 C1; #11 C1
blindmelon-1995-09-12	newly_cleared_sample	#1 4
blitzentrapper-2013-11-12	newly_cleared_sample	#2 C2; #3 C1; #10 C1
drive-bytruckers-2008-03-15	newly_cleared_sample	#21 4
godspeedyoublackemperor-2002-01-24	newly_cleared_sample	#4 D
greyboyallstars-1996-03-09	newly_cleared_sample	#2 C2; #4 C1; #19 C1
infamousstringdusters-2012-03-16	newly_cleared_sample	#4 4
jimlauderdale-2011-07-22	newly_cleared_sample	#2 C1; #5 C2; #6 C1; #7 C1; #8 C1; #9 C1; #11 C1
lettuce-2002-07-13	newly_cleared_sample	#1 C2; #2 C2; #3 C2; #4 C2; #5 C2; #6 C2; #7 C2; #8 C2; #9 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2
newmastersounds-2012-11-10	newly_cleared_sample	#1 C1; #2 C1; #3 C1; #4 C1; #6 C1; #7 C1; #8 C1; #9 C1; #10 C1; #12 C1; #13 C1; #15 C1; #16 C1; #17 C1
newridersofthepurplesage-2006-06-30	newly_cleared_sample	#1 C1; #2 C1; #3 C1; #4 C1; #5 C1; #6 C1; #7 C1; #8 C1; #9 C1; #10 C1; #11 C1; #12 C1; #13 C1; #14 C1; #15 C1; #16 C1; #17 C1; #18 C1; #19 C1; #20 C1; #21 C1; #22 C1
papamali-2010-03-17	newly_cleared_sample	#5 C1
pnuma-2006-09-21	newly_cleared_sample	#10 4
radiators-1991-11-01	newly_cleared_sample	#3 C2; #4 C2; #6 C2
railroadearth-2010-10-02	newly_cleared_sample	#2 4
robertwalters20thcongress-2004-01-02	newly_cleared_sample	#13 4
tedeschitrucksband-2015-06-27	newly_cleared_sample	#8 C1
thenewdeal-2009-08-28	newly_cleared_sample	#5 4
umphreysmcgee-2006-08-31	newly_cleared_sample	#1 4
whitedenim-2013-07-04	newly_cleared_sample	#1 C1; #2 C1; #3 C1; #4 C1; #5 C1; #6 C1; #7 C1; #8 C1; #9 C1; #10 C1; #11 C1; #12 C1; #13 C1; #14 C1; #15 C1; #16 C1; #17 C1; #18 C1; #19 C1; #20 C1
alejandroescovedo-2008-03-02	delivered_changes	#10 C2
alejandroescovedo-2014-03-30	delivered_changes	#13 C2
beneventorusso-2005-06-10	delivered_changes	#1
billystrings-2017-07-15	delivered_changes	#6 C1; #9 C1; #11 C1
billystrings-2020-02-21	delivered_changes	#4 C2
buttholesurfers-1988-11-22	delivered_changes	#18; #19
cowboyjunkies-2012-04-15	delivered_changes	#15 C2; #16 C2
cowboyjunkies-2017-11-05	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5
crisjacobs-2020-04-17	delivered_changes	#20 C2
darkstarorchestra-2004-04-24	delivered_changes	#1; #2; #3; #4; #5; #6; #7; #8; #9; #10; #11; #12; #13; #14; #15; #16; #17; #18; #19; #20; #21; #22; #23; #24
darkstarorchestra-2015-07-11	delivered_changes	#1; #2; #3; #4; #5; #6; #7; #8; #9; #10; #11
deadandcompany-2015-11-17	delivered_changes	#13 C2
derektrucksband-2007-05-27	delivered_changes	#1 C1
drive-bytruckers-2007-07-18	delivered_changes	#5 C2
dumpstaphunk-2008-04-25	delivered_changes	#2; #12
emmittnershiband-2008-07-05	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5
explosionsinthesky-2010-09-02	delivered_changes	#7 C2
godspeedyoublackemperor-2002-01-22	delivered_changes	#3 D
gratefuldead-1974-10-18	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5; #23 +5; #24 +5
gratefuldead-1983-10-12	delivered_changes	#15 +5; #19 +5
gratefuldead-1984-10-14	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5; #23 +5
gratefuldead-1989-04-08	delivered_changes	#21 D
greatamericantaxi-2008-09-17	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5
greenskybluegrass-2012-09-25	delivered_changes	#9 C2
greenskybluegrass-2013-05-04	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5
greenskybluegrass-2015-02-27	delivered_changes	#2 C2; #3 C1; #6 C2; #9 C1; #11 C2; #16 C1; #17 C1; #21 C1
guster-2006-07-28	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5
johnkadlecik-2017-10-31	delivered_changes	#9 C2
kungfuband-2013-02-13	delivered_changes	#7 C2; #8 C2
leftoversalmon-1997-10-31	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5; #23 +5; #24 +5; #25 +5; #26 +5; #27 +5; #28 +5; #29 +5; #30 +5; #31 +5; #32 +5; #33 +5; #34 +5; #35 +5; #36 +5; #37 +5; #38 +5; #39 +5; #40 +5; #41 +5; #42 +5; #43 +5
lettuce-2010-11-14	delivered_changes	#2 C2
lotus-2008-02-07	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5
lotus-2010-06-10	delivered_changes	#12
moe-2005-08-20	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5
moe-2005-09-04	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5
moe-2006-03-17	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5
moe-2007-09-02	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5
moe-2008-02-02	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5
motherhips-2011-02-04	delivered_changes	#23 C2
motherhips-2016-05-14	delivered_changes	#16 C2
mymorningjacket-2006-06-04	delivered_changes	#14 4
mymorningjacket-2008-06-20	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5; #23 +5; #24 +5; #25 +5; #26 +5; #27 +5; #28 +5
mymorningjacket-2012-08-10	delivered_changes	#1 C2
newmastersounds-2009-06-06	delivered_changes	#5 C2; #6 C2; #11 C1; #13 C1
newmastersounds-2011-06-04	delivered_changes	#1 C2; #7 C2; #9 C2; #14 C1; #16 C1; #17 C2
newmastersounds-2018-05-08	delivered_changes	#10 C2; #14 C1
perpetualgroove-2007-09-08	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5
perpetualgroove-2009-06-04	delivered_changes	#7
philleshandfriends-2007-10-20	delivered_changes	#1; #2; #3; #4; #5; #6; #7; #8; #9; #10; #11; #12; #13; #14; #15; #16; #17; #18
philleshandfriends-2014-09-21	delivered_changes	#11 C2; #16 C2; #19 C1
radiators-1997-04-12	delivered_changes	#16 C2
railroadearth-2007-01-28	delivered_changes	#9
ratdog-2007-08-12	delivered_changes	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D
ratdog-2008-04-11	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5
robertrandolphandthefamilyband-2004-07-25	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5
robertrandolphandthefamilyband-2005-05-29	delivered_changes	#3; #7; #9
ryanadams-2006-12-04	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5
signalpath-2005-06-09	delivered_changes	#3; #8
soulive-2004-02-08	delivered_changes	#10
stringcheeseincident-2005-07-23	delivered_changes	#12
stringcheeseincident-2005-07-24	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5
stuallenandmarshotel-2012-04-18	delivered_changes	#3 C2; #12 C2
tedeschitrucksband-2016-08-27	delivered_changes	#11 C2
tedeschitrucksband-2017-02-25	delivered_changes	#8 C2
tedeschitrucksband-2018-10-30	delivered_changes	#19 C1
tedeschitrucksband-2019-02-15	delivered_changes	#14 C2; #15 C2
tedeschitrucksband-2020-01-15	delivered_changes	#10 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2; #16 C2; #17 C2
themotet-2013-01-07	delivered_changes	#1
thewalkmen-2011-04-28	delivered_changes	#7 C2
tortoise-1996-05-25	delivered_changes	#9 C2
u-melt-2008-08-29	delivered_changes	#2 4
umphreysmcgee-1998-04-15	delivered_changes	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5
umphreysmcgee-2005-11-12	delivered_changes	#12
umphreysmcgee-2010-06-05	delivered_changes	#4 C2
wacobrothers-2005-03-16	delivered_changes	#7 C2; #11 C2
animalliberationorchestra-2006-12-29	slice4	#6 4
blindmelon-1995-09-12	slice4	#1 4
drive-bytruckers-2008-03-15	slice4	#21 4
giantpandaguerilladubsquad-2006-11-11	slice4	#27 4
heavypets-2011-03-12	slice4	#9 4
hotbutteredrum-2005-07-02	slice4	#12 4
infamousstringdusters-2012-03-16	slice4	#4 4
mymorningjacket-2006-06-04	slice4	#14 4
northmississippiallstars-2015-04-10	slice4	#12 4
pnuma-2006-09-21	slice4	#10 4
railroadearth-2010-10-02	slice4	#2 4
robertwalters20thcongress-2004-01-02	slice4	#13 4
thenewdeal-2006-12-13	slice4	#1 4; #3 4; #5 4; #7 4; #8 4; #12 4; #14 4
thenewdeal-2009-08-28	slice4	#5 4
u-melt-2008-08-29	slice4	#2 4
umphreysmcgee-2006-08-31	slice4	#1 4
cowboyjunkies-2017-11-05	changed	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5
darkstarorchestra-2011-04-15	changed	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D
darkstarorchestra-2014-07-31	changed	#3; #4 C2; #5 C2; #6 C2; #7 C2; #8 C2; #9 C2; #10 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2; #16 C2; #17 C2; #18 C2; #19 C2; #20 C2; #21 C1
deepbananablackout-2004-04-01	changed	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D; #19 D; #20 D; #21 D; #22 D; #23 D; #24 D
gratefuldead-1974-10-18	changed	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5; #22 +5; #23 +5; #24 +5
greenskybluegrass-2013-05-04	changed	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5; #20 +5; #21 +5
greenskybluegrass-2015-02-27	changed	#2 C2; #3 C1; #6 C2; #9 C1; #11 C2; #16 C1; #17 C1; #21 C1
guster-2006-07-28	changed	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5; #13 +5; #14 +5; #15 +5; #16 +5; #17 +5; #18 +5; #19 +5
joerussosalmostdead-2015-10-29	changed	#5 D; #16 D; #18 D; #22 D
lotus-2008-02-07	changed	#1 +5; #2 +5; #3 +5; #4 +5; #5 +5; #6 +5; #7 +5; #8 +5; #9 +5; #10 +5; #11 +5; #12 +5
mymorningjacket-2004-06-18	changed	#1 D; #2 D; #3 D; #4 D; #5 D; #6 D; #7 D; #8 D; #9 D; #10 D; #11 D; #12 D; #13 D; #14 D; #15 D; #16 D; #17 D; #18 D
zentricksters-2002-12-31	changed	#19 +5
darkstarorchestra-2014-07-31	signature	#3; #4 C2; #5 C2; #6 C2; #7 C2; #8 C2; #9 C2; #10 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2; #16 C2; #17 C2; #18 C2; #19 C2; #20 C2; #21 C1
lettuce-2002-07-13	signature	#1 C2; #2 C2; #3 C2; #4 C2; #5 C2; #6 C2; #7 C2; #8 C2; #9 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2
tedeschitrucksband-2019-02-15	signature	#14 C2; #15 C2
tedeschitrucksband-2020-01-15	signature	#10 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2; #16 C2; #17 C2
```

## sha256 of outputs
```
3b793503c7c5cc3807670d1a6d8db02c3dbf96746f065a51ed34e82fde3ddfc9  arms/cand-asis.json
0753f9396711d01fbf4c1eeaaafc2d296a2553539a37cb5a870fea20ce2ea896  arms/cand-fresh-no5.json
35ddd97016115409247c9dd326942502fb0a785c7159128c6c768d0867c97c1c  arms/cand-fresh.json
5ce5f34a66d51426b41c026a67734663350f340f1ada7b12782cf7c2da868349  cmp-asis/briefings.txt
66f00bea2e24aac0453bbde5740c370362da62824d330d203d84e23f1c252b40  cmp-asis/closest_calls.txt
4aa0ded4f980e428ea6d0ed46b31e71ae4d03922ee1af3882e2ab4db4d1387ee  cmp-asis/drift.txt
3cdee8d1e5df8613ba51b6a5a076305443b756ae55bb951b501ced4317145671  cmp-asis/flags.txt
b5b52582425a4e3a7b8bb03b5a5019fde1d119dbed192f87752c0f6d6d4b7e22  cmp-asis/hand_check_sample.txt
9b000324e393fe5638af205584f058b109021a7d71b2f50bda24b818bf73e817  cmp-asis/holds_delta.txt
2b701bd0868ae5c338cf0389dcbb2e552741c072b7b1b58e21f6d5f42b861be0  cmp-asis/narration_candidates.html
e29cc8220151c6494de92b46780581b3f103060571e8ae7cbbfd6e47f50681b0  cmp-asis/needs_llm.txt
eb7ed3747580c16f95ff3908dbd33b0de4bb5345a6613699e59afa8d0beb874f  cmp-asis/notes.txt
94d368a4ae28272a33531b35b94ac2db1ae52523aed11bd8945ca7e38099a6c4  cmp-asis/outcomes.txt
d2d3dd2605e5678c527b20e18b5149e57a3b7cfa6b5dbff8b79d0c52cb7e8b20  cmp-asis/packaged_exposure.txt
af6bed6126658d275692eb60bb58edc7dd92eda70eef65cdf22663c4afd0f607  cmp-asis/pilot_list.json
df3995b666b7c8c811869fc6b1c167de2f3358ec289d81fadbe6cc762622f944  cmp-asis/predicted_list.json
43d9c546c91b3d1ba3529d8f3fbed6791ce97a29833763d012ceaf6b4f5b820c  cmp-asis/structure_changed_list.json
5a9ed84c8610b031d1fa5f69cbe19205197b20f8b0b326f038e786856065d498  cmp-asis/structure_changed.txt
29e45a0baff4edd237a1d4ef02f37c59618e8bced580764edb502c8bc940059f  cmp-asis/summary.txt
648d9abd7201cbd5b7f65475fa31473be0d0b856cf58fd2a33e2615123a266b1  cmp-asis/taper_changes.txt
fb2a08bd957169789adee662705abc75061b44fa4786fb69336c4d34a2dfc74e  cmp-asis/taper_cleared.txt
94240cd556361a14c347f68473965397a5fc12566a6c73ee7c0dc13fda438e88  cmp-asis/title_changes.txt
cfbdd2fb2b2f90ffb4c7137709726a93b3dcdbe0fc4a35a613c4bb296a1c60ec  cmp-asis/title_rows.json
be56f2719b082f8a13403ba861345e104e0f0e30ad4119e5239e50a78e643d4a  cmp-asis/title_sources.txt
2d90a65c0ea820d710c09c76569ae7445f4d08ccd4ca3f811b5addc059dccd44  cmp-asis/venue_changes.txt
5ce5f34a66d51426b41c026a67734663350f340f1ada7b12782cf7c2da868349  cmp-fresh/briefings.txt
29d3644f4cbfddb6d2161d21e3da2c24962710680a920b29b47bba7cac3bbca0  cmp-fresh/closest_calls.txt
82141ddbcbf11b2ced16e4f4592dd7e4aedd207b2d29e9f793b12cca9b3acc55  cmp-fresh/drift.txt
3cdee8d1e5df8613ba51b6a5a076305443b756ae55bb951b501ced4317145671  cmp-fresh/flags.txt
b5b52582425a4e3a7b8bb03b5a5019fde1d119dbed192f87752c0f6d6d4b7e22  cmp-fresh/hand_check_sample.txt
bd4f853ae5ac281cadd4e631502468b097e7f1d9d617f9c0ba1b0df9fd1c0578  cmp-fresh/holds_delta.txt
2b701bd0868ae5c338cf0389dcbb2e552741c072b7b1b58e21f6d5f42b861be0  cmp-fresh/narration_candidates.html
3593166f0e880fe15aba850ffc2b7c1486177190d5d472168562c800200884b0  cmp-fresh/needs_llm.txt
0e85e5a815bf42888c808451edb086af07bff5d611e7c305ccc1e1b33890e27b  cmp-fresh/notes.txt
22e7ac7e4293bba7a26a4041d4921afd889f628194f8bd2566e8ba304f472fc2  cmp-fresh/outcomes.txt
16b40e9ad133ae99e8f155ed36b83e4d55563dbbbc592f409855d14b9e6abbcc  cmp-fresh/packaged_exposure.txt
5a9ed84c8610b031d1fa5f69cbe19205197b20f8b0b326f038e786856065d498  cmp-fresh/structure_changed.txt
cee7fe18153571eb3bd8b5e45d6b92560843efea1796c40234c1eb3765f94f74  cmp-fresh/summary.txt
bffcefe54ac572a56dd290a6c468453f1c434e0c3803d06f865de208dfd20efb  cmp-fresh/title_changes.txt
d13a5578674931c32acd71c386888777d8b49ba84b6f893e6b04ce299420adeb  cmp-fresh/title_rows.json
be56f2719b082f8a13403ba861345e104e0f0e30ad4119e5239e50a78e643d4a  cmp-fresh/title_sources.txt
2d90a65c0ea820d710c09c76569ae7445f4d08ccd4ca3f811b5addc059dccd44  cmp-fresh/venue_changes.txt
5ce5f34a66d51426b41c026a67734663350f340f1ada7b12782cf7c2da868349  cmp-slice5/briefings.txt
3ea2cdf9b7943361040f2b6bff1ba9e2650f21f97a4ebf332093091071d05936  cmp-slice5/closest_calls.txt
62e598c31fcbe3a89ac7698233b83a11a6b9614a43914fd3240dcaca4eaf85aa  cmp-slice5/drift.txt
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b  cmp-slice5/flags.txt
3dd946850c0bf9cbd1bba65a755f84357fe18b61b70af3478a0806055d42f0c6  cmp-slice5/hand_check_sample.txt
c4353b0addcc0bf3bf00fd14410ea7fbefd607d47bf0fa6844f08b3bce185fa9  cmp-slice5/holds_delta.txt
2b701bd0868ae5c338cf0389dcbb2e552741c072b7b1b58e21f6d5f42b861be0  cmp-slice5/narration_candidates.html
4cc74d49df8e3afca7cccd4d15b55f9f7cb623381d28732c86eb5a13ec049cbb  cmp-slice5/needs_llm.txt
0e85e5a815bf42888c808451edb086af07bff5d611e7c305ccc1e1b33890e27b  cmp-slice5/notes.txt
5b9feecc799914c04c655d54714a82bbc72e636dd6505987e0772ee20bf5ff89  cmp-slice5/outcomes.txt
462b7609981213bff6aafa7c4d682c42d7b45c32dc683b359a266a9a23497430  cmp-slice5/packaged_exposure.txt
5a9ed84c8610b031d1fa5f69cbe19205197b20f8b0b326f038e786856065d498  cmp-slice5/structure_changed.txt
1b00dc9658fd78a9cbb090a15c8c4d4168fa39b82840cbcad41b297190bc00b7  cmp-slice5/summary.txt
ac00df5a5d8d52cd2e50df68d4c70a316c04fdc4481bd9235aae3be105812ce6  cmp-slice5/title_changes.txt
45ffe9cd86690b6c54dae5fd6300bd6cd8a0ca9bdb1ebf29f296c2564b568e52  cmp-slice5/title_rows.json
be56f2719b082f8a13403ba861345e104e0f0e30ad4119e5239e50a78e643d4a  cmp-slice5/title_sources.txt
2d90a65c0ea820d710c09c76569ae7445f4d08ccd4ca3f811b5addc059dccd44  cmp-slice5/venue_changes.txt
c3124dae7d42a77bb18aa5e89ae9c90818e29f61173de543d0872669eca7bf0a  lists/changed_asis.txt
7425af805b41d9d0fd6b7c05c5c531c8e5bab33a962fe843fff6227b6de2ef9a  lists/changed_fresh.txt
7425af805b41d9d0fd6b7c05c5c531c8e5bab33a962fe843fff6227b6de2ef9a  lists/changed_union.txt
8332c2918bd98d7a7a49c11b3ba6c199c17d6e8ec3f206d3d90f2020cc43ad01  old_vs_new_asis.txt
5617cc94265a1b25fbc56138dc79a70f4b9057877174b70257af382b2e6af241  old_vs_new_fresh.txt
95b9a70ed12dde2ed69363a4664d721d682eb6f6986e01ae212e1c0ffa6a9814  old_vs_new_summary.json
0167ec2259cc3ab58f2cbd9a316edcdfca872b895075d546017db7fa28c59fa5  old_vs_new.py
1a0148c2f1d8d45d87844505bc491ad0749720f69206dd94970a2c3452923a0d  packets/changed/cowboyjunkies-2017-11-05.md
14ccccd307f44cca0d411ebfaf5a7afd6d6ab1eb4e884345f2e099293e9ceb93  packets/changed/darkstarorchestra-2011-04-15.md
8e2c63213b080a0a5766d770261ae26a81de35247ea6ec052e733866a845c37a  packets/changed/darkstarorchestra-2014-07-31.md
dee9675baea27757e35b5499e066c63ec24474053f6c33a3df62599533dc4fdc  packets/changed/deepbananablackout-2004-04-01.md
816077f99983f85f62a5928197b1c37bc488d68ec8804f5d4337670aece62c27  packets/changed/gratefuldead-1974-10-18.md
ab3214dc03ba124e944a7b391db19dda2ba9e0825180295f321c6cd4ed80d8df  packets/changed/greenskybluegrass-2013-05-04.md
9dabd969c6ed05d25ca9801930910038607e1cf43a26c1f205d984a5a33121bd  packets/changed/greenskybluegrass-2015-02-27.md
347855d274aa2a56826d5c524c807d520f019d5c8a272687012380c92438b647  packets/changed/guster-2006-07-28.md
2f5cd6a05f16a188822b0e860fa03e3a2fd1bcacfc95d34b56fff9eefa62db5b  packets/changed/joerussosalmostdead-2015-10-29.md
0b4382e580ab3252c7270784d062cf2a294fd478b4af274ad830062b5b609bde  packets/changed/lotus-2008-02-07.md
24d0be716677bb07c7bdb78b0d578bfcc1b146e069e1d595c39e4eccb5074bb7  packets/changed/mymorningjacket-2004-06-18.md
3624e4af48d801b7c6ac9b5eed87ee0f49bbac89efa4d1d3ca70205963eda845  packets/changed/zentricksters-2002-12-31.md
e57a060e3f32eb2ead7ad0ea65d7b478f3b6383969f0c0b11b8b9d23f58e31cb  packets/delivered_changes/alejandroescovedo-2008-03-02.md
7f7fb847ffe23d7a424939e6ee9d39df95ceea878a9be409a5387c14846b4bdc  packets/delivered_changes/alejandroescovedo-2014-03-30.md
3627b872eb62bdd0d032628fce30c44eb98fac99533a5f1a99a1edf65919f830  packets/delivered_changes/beneventorusso-2005-06-10.md
7536e46a769e7d1d14489f1c6204bbdc2fc02679c4528445d418d74ab8d70ad5  packets/delivered_changes/billystrings-2017-07-15.md
156db5a6dfdb4b0c83523a411701c4e2766945254d064be92b6c7bba28c0c5ee  packets/delivered_changes/billystrings-2020-02-21.md
63059761089a5c904bcb9309e8dc1464c4c6eb8aae4d26231634400b6198b0c7  packets/delivered_changes/buttholesurfers-1988-11-22.md
eb346149db2d41f02cbb4b62c92486f86e9adacae4d4964d008bacfa2a5846dc  packets/delivered_changes/cowboyjunkies-2012-04-15.md
f54534b9b5b574dcc0194e815be9a3ce2b9f990ccf60519ebb22ff53ed91db60  packets/delivered_changes/cowboyjunkies-2017-11-05.md
afc7f4ce08d11d3b010f71715ed527e41a9af26df0a04149575ab52414c815bf  packets/delivered_changes/crisjacobs-2020-04-17.md
920ee9d7246f0df7cb781f04ff3c76ef83727e6d0e9ecbadcee54aa5544ce127  packets/delivered_changes/darkstarorchestra-2004-04-24.md
ed592798418f7e05a934b54ad5e93cb5ebf85baeba4fbf5eb9683fbf77f59555  packets/delivered_changes/darkstarorchestra-2015-07-11.md
dea5b6e0f22402ba7dd863b7a98f0149dd1d0f68ab7a768e02d2705a10a6da3e  packets/delivered_changes/deadandcompany-2015-11-17.md
63726845c7c23c15992e78f568a23169a80b1a0d5d383ff7d894555ae6143791  packets/delivered_changes/derektrucksband-2007-05-27.md
d5f4f1bb859b332de8f875ee090c3368ffd18af6e258b703a992f13dbb8cdd5f  packets/delivered_changes/drive-bytruckers-2007-07-18.md
9651881d99cc7ea2a989a0f8255f5085115c9f290333312c61eeab05dfccc4a3  packets/delivered_changes/dumpstaphunk-2008-04-25.md
eb94bf6d394085a04f50468b9edea2a26d4b9fd56fa5c069b09b99dfd8083b4e  packets/delivered_changes/emmittnershiband-2008-07-05.md
c15258576a4bcf647ec7fbbb6c5481ab5862a235d239044c92d45b2c28ba73e8  packets/delivered_changes/explosionsinthesky-2010-09-02.md
9583fe022b7833235e4d8029ce883d2e601492443996fbc3ae2b6686cd5a6646  packets/delivered_changes/godspeedyoublackemperor-2002-01-22.md
7848f7fe68a82677eafbf86a0bafb006dcbcc60ea2a1acbe364b2977ebb31789  packets/delivered_changes/gratefuldead-1974-10-18.md
e95656b3a861ca3fcf176fe9e39a8a96c1a2537e4fc38a4efc9ec928fa15d4ba  packets/delivered_changes/gratefuldead-1983-10-12.md
8de4121f6a8a015c3e72702ddcc7dafbdaaeebcee1e43fde5a5593209fb0fa22  packets/delivered_changes/gratefuldead-1984-10-14.md
be3a5198b564d44e5c2fbf4191fbe01d26bb54e3188f4dbcfa43614306cc5f7f  packets/delivered_changes/gratefuldead-1989-04-08.md
43b4fe40e953aa923cc4af1e4623823cec3d8622fd7ffdb0ebc018a349f9e820  packets/delivered_changes/greatamericantaxi-2008-09-17.md
17e73fea3750df57c5296ef8e2272f5735531fd5f17e4159db96b0c465118a89  packets/delivered_changes/greenskybluegrass-2012-09-25.md
10488c3ab079cde49569dd8c37d22b99b09f6e53dc4bfbf00b7fb31ed2538ff0  packets/delivered_changes/greenskybluegrass-2013-05-04.md
9cd170bf3206d91eebd8d9e07e5e08839069f4740f35e879fbcb59b5c2157bfd  packets/delivered_changes/greenskybluegrass-2015-02-27.md
a2cb4cbf68660e3355e6f5a550188ffc41e1f0d8aa59487b4e2a7d26ff503d40  packets/delivered_changes/guster-2006-07-28.md
62ed61ca3b8c36183a1f74103590f52cd64fa573b00bb30ae306e1ab25a65d04  packets/delivered_changes/johnkadlecik-2017-10-31.md
a102133fd927ad8d4b4972b2db869f514afa3d7d958aca22d9cd08630502450c  packets/delivered_changes/kungfuband-2013-02-13.md
6dca0458d98c9510225efd2459c461ba1eabca57fbaf1f0d922269f2dfa6fa49  packets/delivered_changes/leftoversalmon-1997-10-31.md
eef15449974b0173ce419ea68cbb8488a894b775bd04f30184cf7e163cf9d63d  packets/delivered_changes/lettuce-2010-11-14.md
f680481687de258b66aa468a32e09a0613607cc75ee67918354047f7525e6fc6  packets/delivered_changes/lotus-2008-02-07.md
e9898fe9afea1e6cafc163c6fa6fd9b8effc3b2e9cd73f61b28b847b8101956d  packets/delivered_changes/lotus-2010-06-10.md
0628becfdcfe814df5419ae0ddce3614802deb1045c62e053e91bf49f1d10add  packets/delivered_changes/moe-2005-08-20.md
afc87ea8a8156a123d44371a38a3acd6aab5dfda87e8f5b30da0bd71e302953f  packets/delivered_changes/moe-2005-09-04.md
d3ab44fbf313ee8cae3d50923aa197f23bd79355e755eee0c7e1aef7f6d68522  packets/delivered_changes/moe-2006-03-17.md
6c3030393b171a23a6d30f1321aed91ab4583bd80249c608b62eca5d776b51f5  packets/delivered_changes/moe-2007-09-02.md
ff2c1be8dc448b48f08c3c59ec2af600252c6a2769a157a8cb8fc6ef6bc4be90  packets/delivered_changes/moe-2008-02-02.md
43cbc3636be9eb5b71b130e8d84171ab821c3c55e6cdb8005038cfa749cced41  packets/delivered_changes/motherhips-2011-02-04.md
3a57e02e762951491d9dc2f10e41bf7e0c0de2bf03cf98e312165f15eab557d5  packets/delivered_changes/motherhips-2016-05-14.md
3e5a5e185f4a7cde3c67d16144adc5c9e435950b5afd5cc9a0ac4bd679c2b08f  packets/delivered_changes/mymorningjacket-2006-06-04.md
d6a0635649b42c7a9b4f3ca5dab19c6807935e84d3fbed9f329eac626c18352a  packets/delivered_changes/mymorningjacket-2008-06-20.md
79656d9d99f6f0180004153d7ee36ccaa88cb14ff2a916faca671924e67de755  packets/delivered_changes/mymorningjacket-2012-08-10.md
0b0fc05d0be42357f067a6b5da92869e2eff11e0666d4f0d32a6395a2b5778be  packets/delivered_changes/newmastersounds-2009-06-06.md
5ac4d69dbd190e932fdb26ce27bbf22ffb675ccf1223d2f8bac291435d6a4a03  packets/delivered_changes/newmastersounds-2011-06-04.md
235df8759920e63f79c18fc8896f57fc6a5522ac7bcfe0724ac3b45fa48d2d9f  packets/delivered_changes/newmastersounds-2018-05-08.md
1d85a533bbf85aa5063683eb88882823dd09b8d2fee81ffb62cedd9bf9a2fcac  packets/delivered_changes/perpetualgroove-2007-09-08.md
fb56aed55410a08adcbec510bdd9f8b3df7a2c99d73755f9ed76d83783161d03  packets/delivered_changes/perpetualgroove-2009-06-04.md
45d43df5eabcaff1eb35abfe7455a689989cdcc2388cd317fcdefeb4597d2a11  packets/delivered_changes/philleshandfriends-2007-10-20.md
75f64721fe586590645e6230fb8e6a21dcb838970b4d8d3b21b547cdf5d6d41d  packets/delivered_changes/philleshandfriends-2014-09-21.md
2ba70964d0cd0229cb75127d89c44f6367e2f531a13d651ce4fb81859da2a07d  packets/delivered_changes/radiators-1997-04-12.md
d6d085781d2293cbe4c66e4f76efdf90cc1d71f58b5032b09a6bdc1f15520ada  packets/delivered_changes/railroadearth-2007-01-28.md
4f46504d3d72976e53ca266c74792ff68f17cba79a6becb0e20cda6d7ba9c0b4  packets/delivered_changes/ratdog-2007-08-12.md
0bb83294fcdbb56edfaa8613531ca5d8c0c187da880ef1a2f0822eb4d0f0632e  packets/delivered_changes/ratdog-2008-04-11.md
298ebacc9c48d0618c9a7e91f0e5a1f68a49540684e59e8f8fccf9761028399f  packets/delivered_changes/robertrandolphandthefamilyband-2004-07-25.md
4c7ba60724f7a39629ac0de47c8a805dc32477ce87256f189ea4fdb1adf811cc  packets/delivered_changes/robertrandolphandthefamilyband-2005-05-29.md
763f858d4143f1661f5ef6a93671e8454ea9d47c89b1c502269e1b6bbe5118bd  packets/delivered_changes/ryanadams-2006-12-04.md
dc676b588b843e00a5d48d464be74c1a315117b4c4f6ddbd2d15a28f317184be  packets/delivered_changes/signalpath-2005-06-09.md
16bb6e45529a7e868e144d9c8df413df78fad56490897e5f7e9293fb90ecae30  packets/delivered_changes/soulive-2004-02-08.md
04b9787716de544a504211c3fd982a0d5da8dff2322a4d5c182dcd481f241aaa  packets/delivered_changes/stringcheeseincident-2005-07-23.md
2b8783d0d208ce68889d04169f49db4b26c4472515f5ffdb3226cd4565c9760b  packets/delivered_changes/stringcheeseincident-2005-07-24.md
c132aca6709cbeaae937a3924043f1148f7beeb1202259ab87ff66cd0ae3ad49  packets/delivered_changes/stuallenandmarshotel-2012-04-18.md
39bbc4078d9bfa0cfa02dfaa6dfb5d738c82764698b01b5567b416dede21979c  packets/delivered_changes/tedeschitrucksband-2016-08-27.md
219da3fe1c90722e4324f0f6a5e39a34f66d8a68abd35f1cbc54226b74a77787  packets/delivered_changes/tedeschitrucksband-2017-02-25.md
dec413deaac40886132d13839fda83b29ca1e703faf664b3833ebad13966bf7b  packets/delivered_changes/tedeschitrucksband-2018-10-30.md
86e5d8207c22f59f40a040144b181c8efb63b247dca0ce97ae1e538260230482  packets/delivered_changes/tedeschitrucksband-2019-02-15.md
d0f836de99f34850e177b65f248b70b9dbcdaba963d0302c3bb0375bf5464f6a  packets/delivered_changes/tedeschitrucksband-2020-01-15.md
53858d8216e25d178087252cc8ff910e06455f540e002d5de1b8e796fad14186  packets/delivered_changes/themotet-2013-01-07.md
829c7794924391b2ff64519c1da983dac573291634fde02cfb183b6f74e1e296  packets/delivered_changes/thewalkmen-2011-04-28.md
3c52dcea607b6c7db719f265ca8a12f300581e0e2ea0f34de7753a5ddb79346b  packets/delivered_changes/tortoise-1996-05-25.md
d35ec011ca7ba7297c48d64e3c74f969d6f5735ba18388da30a827071169557e  packets/delivered_changes/u-melt-2008-08-29.md
bb2359443e3f22b91dba9be7f6b2feabb6181cb5e52988362465ba8fe27c51c0  packets/delivered_changes/umphreysmcgee-1998-04-15.md
f09d8823d53b9698d23eb93bb2859456f98d2074e4db3557ed076812e863dc80  packets/delivered_changes/umphreysmcgee-2005-11-12.md
54cdc919219c12948fe98eb8e9e4eb16ce231d476b8ee3889442a9c249968831  packets/delivered_changes/umphreysmcgee-2010-06-05.md
ae863e2956936fe5e420f4dfea7fb065c08f8aad5a587cc3a70ba711860909d8  packets/delivered_changes/wacobrothers-2005-03-16.md
0bc10b3d6811ced7aea9584788166ee1e4c262069c0282c37c85bf493aa83af7  packets/newly_cleared_sample/animalliberationorchestra-2006-12-29.md
dad4a52060d461915ca9c18b347a493cfd54ecc2a88300ef6d5702557fb3d47f  packets/newly_cleared_sample/bigheadtoddandthemonsters-1991-01-21.md
502d872c85b1900291abeb7efa714643e9acb700bb692ab66fe4773d81dc8f3c  packets/newly_cleared_sample/billystrings-2017-07-15.md
cfa163545f8b94cfaa2ee9463c8df440909e4b771e9c64151db0d58a0bd84f41  packets/newly_cleared_sample/blindmelon-1995-09-12.md
88f8d68d9d31dbacc54e2f6ad20ee1839ad3268fea717fc81fabced278cee6e6  packets/newly_cleared_sample/blitzentrapper-2013-11-12.md
142fd4abe5ce3a0e44e4c6c631f2d38736337660d273b9d738f7eee253f6e50e  packets/newly_cleared_sample/drive-bytruckers-2008-03-15.md
7fe553c73e19b2871f9c2434cd7c3829470795ef9464397e85235daa26a63ef2  packets/newly_cleared_sample/godspeedyoublackemperor-2002-01-24.md
e1c3b14d90c82af3140862afbd49b9ec65ee1e3a285a6f1c5897ff84109385b3  packets/newly_cleared_sample/greyboyallstars-1996-03-09.md
bb0633eade76bc1984fa75ae22bb4171ede1669a3c74b684aea7f4342471f13c  packets/newly_cleared_sample/infamousstringdusters-2012-03-16.md
6652d1892fdda616e98903cf38aeb8e61d47479ddd656c9443e0a2b37d78bbb1  packets/newly_cleared_sample/jimlauderdale-2011-07-22.md
3c619b1ce15327844550b1b9f6206b6a451a7cbdec4753428940a4a423d29fea  packets/newly_cleared_sample/lettuce-2002-07-13.md
df213b7e0783f462a38e189de5d659100167d88997848e4709ffb25be865f33e  packets/newly_cleared_sample/newmastersounds-2012-11-10.md
5fd2a08f4a7523ce70bc35fa3c6bf251ab6b39ea6bd2e758f3a407c951224dad  packets/newly_cleared_sample/newridersofthepurplesage-2006-06-30.md
08bb33641f8ce4e85ec225aff84cf37e51d804f3b919a4d8922df70a6fd13de9  packets/newly_cleared_sample/papamali-2010-03-17.md
daa8b7f1a644d4ab96ce22cb25f5c2b7c027de09989636674a0cf0c581cb8a36  packets/newly_cleared_sample/pnuma-2006-09-21.md
12a5cb715721a46cfc65f32dbbb920a91afc023017eb98f3cc6b6c546ae7b5bc  packets/newly_cleared_sample/radiators-1991-11-01.md
0af7bf84f7777432487b356bbb8604485055d57e404377811ce13b717322a7bb  packets/newly_cleared_sample/railroadearth-2010-10-02.md
5ddfca58771e64f0b65c92c73ca70ce64eb772264c61a362336778cf1a233895  packets/newly_cleared_sample/robertwalters20thcongress-2004-01-02.md
e6f8e2a76d8e8cd5749bd2faee50172763f38470b4dba1c4fd9a3b93f6b1d668  packets/newly_cleared_sample/tedeschitrucksband-2015-06-27.md
697bc0785e61364b298282a3d8696aeef89a63345a68af6ffa997ac3cff2f454  packets/newly_cleared_sample/thenewdeal-2009-08-28.md
bae3d0c4f3340dce917b276f836c32875188d30cf28f472785bd1c6e57b3364a  packets/newly_cleared_sample/umphreysmcgee-2006-08-31.md
3ded9cb67a3c1e2ae1f2c218776daaaf7a08a072cd3a156bd040d139e5b5a241  packets/newly_cleared_sample/whitedenim-2013-07-04.md
b240501b2178f366b10662bc7b5e366f6cfc2cdac37d9ceed8481a85f0b35815  packets/signature/darkstarorchestra-2014-07-31.md
78e0465121dd3385544acace4d585e3210c29e13d927a4c6b576814cd2234de5  packets/signature/lettuce-2002-07-13.md
70931e0f197bc50d887235c8847bb41ec635efe8cbfac752a8d94786014351b7  packets/signature/tedeschitrucksband-2019-02-15.md
05553f816be2158241d58b50ff38d3fe7c4afff1cdf3088806aa481c08ac78e3  packets/signature/tedeschitrucksband-2020-01-15.md
51ddef8e0691d0be9d751783c51c3f120ce42f1cfd3a2543269d87c0652f200b  packets/slice4/animalliberationorchestra-2006-12-29.md
f93b0432f5cffa3569cd688e93b1960ab266fe7027f033e84f170929530a59b2  packets/slice4/blindmelon-1995-09-12.md
e476359d5aa2c3a04a045a7047efee17a049614e0d21f45d0eab03a7a7645908  packets/slice4/drive-bytruckers-2008-03-15.md
5d58e961294b7b9b04fb718a8660c6bf768e8f964bc82fd20fe2833a0e1a702f  packets/slice4/giantpandaguerilladubsquad-2006-11-11.md
b236f80a5070121365fa210631b9870c056f65321a4a903ae112dc09b0dd5ceb  packets/slice4/heavypets-2011-03-12.md
b40befc6a67c81a30472bb97d349a5a6c7dd14ab41c5f9343fc0edd75987eb92  packets/slice4/hotbutteredrum-2005-07-02.md
31c069ae97efd68b7d38e12ff39abd0f894e5ab6019027eb49ad2982153039e9  packets/slice4/infamousstringdusters-2012-03-16.md
05f8ce843f046fa20344e3a8c2e8fe31d654b92dc2e8cb99d0f18e456f53793f  packets/slice4/mymorningjacket-2006-06-04.md
05c6fa2b9518d6ff498ace3f8c2b9e491655d7d7f061046417e2c98df09a2576  packets/slice4/northmississippiallstars-2015-04-10.md
3392c624ebb9b34f45e75986368c4bd84c93da963e51db05c23faa89b2bd1d29  packets/slice4/pnuma-2006-09-21.md
d57b4bff5de84b61c9261da7c1308ede355da08fe11b4b7c8086fac9d870d83e  packets/slice4/railroadearth-2010-10-02.md
1286d9d9810ce81a60f6d8ce6d6d24e9cfac10076d342d133f37e51ea18d41a4  packets/slice4/robertwalters20thcongress-2004-01-02.md
bc9c1002086b56619dd159351580339a53e19abbff520e9bfd6ba7fbfc12651f  packets/slice4/thenewdeal-2006-12-13.md
e652174815cbf52ac9f6954d9f694f428d83cdaffdeb086813301efb8ffb37a1  packets/slice4/thenewdeal-2009-08-28.md
cad211ffe57cfcfdfac436f9bced125bb0c42bd20b21f932ecd1a87bbd1c7b14  packets/slice4/u-melt-2008-08-29.md
b6d365d2338005f020035738da2995c3048049cc15fa74c39c0e7e401f6db0e2  packets/slice4/umphreysmcgee-2006-08-31.md
c696a4e6eafff82a29a203874e2f5bab3d9e8a984cec6fb52c705085920f756e  packets/strata_index.json
c7d86dbae6c373e783d0e276eef39096f581eadd5e3e64552fa05c823771ab30  packets/strata_index.txt
9b05c6408393f32b6f5564de31290815dd51e813f706a87eb6d198ef05544218  packets/wholly_untagged_d3/billystrings-2021-12-04.md
6465e5f64e797366993048272ca0a4294887e07d51de7702ef4e1a71f920d070  packets/wholly_untagged_d3/charlieparr-2003-01-10.md
9237e51d918d1f0035599c7981776ffb2b6002722f74fb53368d1fb88f026722  packets/wholly_untagged_d3/darkstarorchestra-2005-02-19.md
41f86df72d2f98edbb4645a3c2658b7043f14818b496b6117677ed7496a875ab  packets/wholly_untagged_d3/darkstarorchestra-2005-05-30.md
1c11e388c8b722cc65e096b1028fdd7220594659a59d9c1b736f9c34378a6cb6  packets/wholly_untagged_d3/darkstarorchestra-2011-04-15.md
70fb2ffcbb571cc25702a8c077457b9b21bce78f7b17b9fe96c680258b39a563  packets/wholly_untagged_d3/darkstarorchestra-2012-07-21.md
70c643810ba8de942c9126c322d05ea78c9e5cee3db854a0899f2b32b9173f32  packets/wholly_untagged_d3/deepbananablackout-2004-04-01.md
5c3b85e4de4000cfa27d32189777ccf6de98ce5ae710cf4acc250e063e937fd4  packets/wholly_untagged_d3/derektrucksband-2006-12-31.md
b189463d0dc9545e5b064598bc2c04ce1cfb788e6e59058e9359f6ef7e9cb971  packets/wholly_untagged_d3/minutemen-1984-12-01.md
c04b6c5327bea5708cd2a2a2299a249ba476a833fbd7d59e81ad84cd4120cecf  packets/wholly_untagged_d3/motherhips-2010-10-16.md
cd26b84e21b6073017e64fc69da4d95dd171ed93c2903ee11790f8f4affaf6b8  packets/wholly_untagged_d3/mymorningjacket-2004-06-18.md
8a9611dfc288076876ea870b671f53cc3f08efafb34e9afdf8313ce0567a4bfc  packets/wholly_untagged_d3/railroadearth-2019-04-08.md
7238ac5d951d43c776df792d1d3f3c03c45a237aeeae351a05752cedd9f21363  packets/wholly_untagged_d3/ryanadams-2002-02-06.md
629759f5eef72b54e5e28617a2d11a63fed1f1a4b679f1d2ebc61ea7dfd5a8b6  packets/wholly_untagged_d3/soulive-2005-03-11.md
ab5c20824cde110564499e866ef0f80f387117d5385e40c675b408dbbd3f51ca  packets/wholly_untagged_d3/thecodetalkers-2005-08-06.md
5f44f8b153e2cb6475c87540cd956dd661f55eaa3238c90947f42abcc3b036b8  packets/wholly_untagged_d3/thegrassisdead-2001-10-21.md
c22d171d72a3e8244b0d6e56afbc3b2c271c5bdc132f31158398a6ec29ddf5fb  packets/wholly_untagged_d3/yondermountainstringband-2005-07-24.md
7394bb0695ab84f172011b2fdd0b004e45d93fd1dc8def096bbf866ad3e0639c  packets/wholly_untagged_d3/zero-1986-09-06.md
6e5282cda1837d34c25a3a7207d664898721a29bf11cf19d3c1bb1214ec054d0  parity/parity.txt
```
