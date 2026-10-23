# t21arms handback
## Tree identities
CAND HEAD 415f8d7bdbb7ded62127f7ba5e869b700e92bfe6; llama.__file__ = /Users/shawn/projects/llama/.claude/worktrees/title-hygiene/packages/llama/src/llama/__init__.py
BASE HEAD 74ec2671ed4b45e26307b75a762ac9ca3a91249c; llama.__file__ = /Users/shawn/projects/llama/.claude/worktrees/title-hygiene-base/packages/llama/src/llama/__init__.py
BASE 'git diff --stat 11dbffb HEAD -- packages': [] (empty = ok)
## Arms (all --all, exit codes all 0; 3983 rows each; arms ran 2 at a time)
| arm | tree | flags | secs | rc | rows | sha256 |
|--|--|--|--|--|--|--|
| base-asis | BASE | none | 42 | 0 | 3983 | 0bef062a9d355ad127468f0b015050c79f184ceab405373be2c414a0dbeda0b0 |
| base-fresh | BASE | strip-title, strip-structure | 62 | 0 | 3983 | 759cd2f31743d1008e715a6329c2fee568feb7b6664667e5a3ea82c4106a32e5 |
| cand-asis | CAND | none | 55 | 0 | 3983 | 2db77631095b0b752a614e5100760d26aba8552c333e9213144b5dac301a3f54 |
| cand-fresh | CAND | strip-title, strip-structure | 71 | 0 | 3983 | e1abc608c133323022455548c7c8c2dc562fc62d7db39c35b11caa17a347259a |
| cand-fresh-no5 | CAND | strip-title, strip-structure, disable-slices slice5 | 65 | 0 | 3983 | 1335aa28b42262221ab55b0db7368813abd17fa6760d1113314db15b5f6174f6 |
## Commands (cwd = CAND root, ./.venv/bin/python; options per --help, none missing)
CMD cmp-asis rc=0 secs=8
CMD cmp-fresh rc=0 secs=4
CMD cmp-slice5 rc=0 secs=4
CMD parity rc=0 secs=2
CMD packets rc=0 secs=2
Arms: scripts/replay_holds.py run --all [flags] --scratch /Users/shawn/.llama-harness/piece3/accept/scratch/<arm> --out /Users/shawn/.llama-harness/piece3/accept/arms/<arm>.json (BASE arms from BASE root)
compare lines: asis base-asis/cand-asis; fresh base-fresh/cand-fresh; slice5 cand-fresh-no5(base)/cand-fresh(cand); all --no-repro-gate
Repro line per compare: asis 132/146; fresh 130/145; slice5 125/147 (held, non-needs-LLM)
Note: packets --help does not mention an as-is compare for the delivered-show stratum; only the fresh packets run was done.

## cmp-asis summary.txt (verbatim)
base reproduces 132/146 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 188, cand 186
briefing guard reproduces 3/4
drift.txt: 201 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 4 famil(ies)
newly cleared: 3
packaged_exposure.txt: 113 entr(ies)
venue_changes.txt: 0 show(s), 0 with a flag change
title_sources.txt: 51 row(s)
structure_changed.txt: 2 show(s)
hand_check_sample.txt: 3 show(s)
closest_calls.txt: 803 row(s)
needs_llm.txt: base 651, cand 653
notes.txt: 1373 note(s)
holds_delta.txt: 7 cleared, 14 added
title_changes.txt: packaged 30, voiced 3, delivered 181
disabled slices: []
taper_cleared.txt: 9 show(s)
taper_changes.txt: songs moved 1, labels renamed 0, filler labels only 0, segues changed 0, provenance only 1, needs-llm not owned 463, unreplayable 0, stored-llm moved 2
voiced check: delivery_path /Volumes/media/lma-radio/delivered
holds_delta.txt: 'would-hold on a fresh get' is empty in an as-is arm by construction (only an overrides-stripped arm records `stripped`)
predicted_list.json: 7 row(s)
structure_changed_list.json: 2 row(s)
pilot_list.json: 7 row(s)

### cmp-asis holds_delta.txt head 40
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
  buttholesurfers-1988-11-22  flags: low-confidence structure alignment; unresolved track titles  slices: unattributed  (needs-llm)
  darkstarorchestra-2004-04-24  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Bertha; research asserts unknown song: Mama Tried; research asserts unknown song: Loser; research asserts unknown song: Big River; research asserts unknown song: You Ain't Woman Enough; research asserts unknown song: Here Comes Sunshine; research asserts unknown song: Black-Throated Wind; research asserts unknown song: Ramble On Rose; research asserts unknown song: Me and Bobby McGee; research asserts unknown song: Brown-Eyed Women; research asserts unknown song: Around and Around; research asserts unknown song: Scarlet Begonias; research asserts unknown song: Weather Report Suite; research asserts unknown song: Let It Grow; research asserts unknown song: Space; research asserts unknown song: The Other One; research asserts unknown song: Dark Star; research asserts unknown song: Comes a Time; research asserts unknown song: Uncle John's Band; research asserts unknown song: Sugar Magnolia; research asserts unknown song: Me and My Uncle; research asserts unknown song: Friend of the Devil; research asserts unknown song: Loose Lucy  slices: unattributed  (needs-llm)
  darkstarorchestra-2015-07-11  flags: low-confidence structure alignment; unresolved track titles; research asserts unknown song: White Rabbit; research asserts unknown song: Feedback; research asserts unknown song: Viola Lee Blues; research asserts unknown song: St. Stephen; research asserts unknown song: The Other One; research asserts unknown song: The Eleven; research asserts unknown song: Turn On Your Love Light; research asserts unknown song: Easy Wind; research asserts unknown song: China Cat Sunflower; research asserts unknown song: I Know You Rider; research asserts unknown song: Lovelight; research asserts unknown song: It Hurts Me Too  slices: unattributed  (needs-llm)
  lotus-2010-06-10  flags: unresolved track titles  slices: slice1, slice2, slice3
  philleshandfriends-2007-10-20  flags: low-confidence structure alignment; structure has 1 sets but jerrybase shows 2; unresolved track titles; research asserts unknown song: Friend of the Devil; research asserts unknown song: Deep Elem Blues; research asserts unknown song: Bertha; research asserts unknown song: Pride of Cucamonga; research asserts unknown song: Deal; research asserts unknown song: Shine; research asserts unknown song: Plasma; research asserts unknown song: Viola Lee Blues; research asserts unknown song: Cumberland Blues; research asserts unknown song: Viola Lee; research asserts unknown song: Cumberland; research asserts unknown song: Unbroken Chain; research asserts unknown song: Dark Star; research asserts unknown song: Wharf Rat; research asserts unknown song: Help on the Way; research asserts unknown song: Slipknot!; research asserts unknown song: Franklin's Tower; research asserts unknown song: Box of Rain; research asserts unknown song: Alabama Getaway; research asserts 2 sets but structure has 1  slices: unattributed  (needs-llm)
  railroadearth-2007-01-28  flags: unresolved track titles  slices: slice1, slice3
  signalpath-2005-06-09  flags: low-confidence structure alignment; unresolved track titles  slices: unattributed  (needs-llm)
  soulive-2004-02-08  flags: unresolved track titles  slices: slice2, slice3
  stringcheeseincident-2005-07-23  flags: low-confidence structure alignment; unresolved track titles  slices: unattributed  (needs-llm)
  umphreysmcgee-2005-11-12  flags: unresolved track titles  slices: slice1, slice3


### cmp-asis title_changes.txt head 40
titles changed on shows that stay unheld (base -> cand); a path is the cascade's (D, C1, C2, S, S-deferred, 4, optional +5); '(unattributed)' = no recorded path

== packaged: 7 show(s), 30 position(s)
-- title text (9)
   by path: (unattributed) 3, 4 1, C1 1, D 4
  darkstarorchestra-2005-02-19 #1: 'Deep Elem Blues' (setlist) -> 'Deep Elem' (desc-position)  [D]
  darkstarorchestra-2005-02-19 #4: 'The Monkey and the Engineer' (setlist) -> 'Monkey and Engineer' (desc-position)  [D]
  darkstarorchestra-2005-02-19 #7: "You Ain't Woman Enough (to Take My Man)" (setlist) -> "You Ain't Woman Enough" (desc-position)  [D]
  darkstarorchestra-2005-02-19 #8: 'Jack-A-Roe' (setlist) -> 'Jack A Roe' (desc-position)  [D]
  giantpandaguerilladubsquad-2006-11-11 #27: '.45' (setlist) -> '45' (tags)  [4]
  jimlauderdale-2011-07-22 #2: '1+1 makes 3' (setlist-gap) -> '1 plus 1 Makes 3' (sibling-format)  [C1]
  zero-1986-09-06 #2: 'Baby Baby' (setlist) -> 'Baby, Baby' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #4: 'Gomorrah' (setlist) -> 'Gommorah' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #6: 'Try a Little Tenderness' (setlist) -> 'Try A Little Tenderness' (sibling-align)  [(unattributed)]
-- source only (21)
   by path: (unattributed) 8, D 13
  blindmelon-1995-09-29 #1: '2x4' (setlist) -> '2x4' (tags)  [(unattributed)]
  darkstarorchestra-2005-02-19 #2: 'Dark Hollow' (setlist) -> 'Dark Hollow' (desc-position)  [D]
  darkstarorchestra-2005-02-19 #3: 'Dire Wolf' (setlist) -> 'Dire Wolf' (desc-position)  [D]
  darkstarorchestra-2005-02-19 #5: 'So Many Roads' (setlist) -> 'So Many Roads' (desc-position)  [D]
  darkstarorchestra-2005-02-19 #6: 'Cassidy' (setlist) -> 'Cassidy' (desc-position)  [D]
  darkstarorchestra-2005-02-19 #9: 'Ripple' (setlist) -> 'Ripple' (desc-position)  [D]
  newmastersounds-2007-06-01 #4: '102%' (setlist) -> '102%' (tags)  [(unattributed)]
  thegrassisdead-2001-10-21 #1: "He's Gone" (setlist) -> "He's Gone" (desc-position)  [D]
  thegrassisdead-2001-10-21 #2: 'Sugaree' (setlist) -> 'Sugaree' (desc-position)  [D]
  thegrassisdead-2001-10-21 #3: 'So Many Roads' (setlist) -> 'So Many Roads' (desc-position)  [D]
  thegrassisdead-2001-10-21 #4: 'Comes A Time' (setlist) -> 'Comes A Time' (desc-position)  [D]
  thegrassisdead-2001-10-21 #5: 'Black Peter' (setlist) -> 'Black Peter' (desc-position)  [D]
  thegrassisdead-2001-10-21 #6: 'Ripple' (setlist) -> 'Ripple' (desc-position)  [D]
  thegrassisdead-2001-10-21 #7: 'The Old Ashe Grove' (setlist) -> 'The Old Ashe Grove' (desc-position)  [D]
  thegrassisdead-2001-10-21 #8: 'Tennessee Jed' (setlist) -> 'Tennessee Jed' (desc-position)  [D]
  zero-1986-09-06 #1: 'Rigor Mortis' (setlist) -> 'Rigor Mortis' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #3: 'Tear Tags Off Mattresses' (setlist) -> 'Tear Tags Off Mattresses' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #5: 'Tangled Hangers' (setlist) -> 'Tangled Hangers' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #7: 'Straight Jackets' (setlist) -> 'Straight Jackets' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #9: 'Severe Tire Damage' (setlist) -> 'Severe Tire Damage' (sibling-align)  [(unattributed)]
  zero-1986-09-06 #10: 'Little Wing' (setlist) -> 'Little Wing' (sibling-align)  [(unattributed)]

== voiced: 3 show(s), 3 position(s)
-- title text (0)

## cmp-fresh summary.txt (verbatim)
base reproduces 130/145 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 189, cand 187
briefing guard reproduces 3/4
drift.txt: 310 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 4 famil(ies)
newly cleared: 3
packaged_exposure.txt: 185 entr(ies)
venue_changes.txt: 0 show(s), 0 with a flag change
title_sources.txt: 51 row(s)
structure_changed.txt: 2 show(s)
hand_check_sample.txt: 3 show(s)
closest_calls.txt: 1314 row(s)
needs_llm.txt: base 880, cand 858
notes.txt: 2226 note(s)
holds_delta.txt: 41 cleared, 15 added
title_changes.txt: packaged 363, voiced 3, delivered 184
disabled slices: []
taper reports: not written (arms replayed with --strip-structure-overrides)
voiced check: delivery_path /Volumes/media/lma-radio/delivered
holds_delta.txt: 'would-hold on a fresh get' is empty in an as-is arm by construction (only an overrides-stripped arm records `stripped`)
apply lists: not written (arms replayed with --strip-structure-overrides or --strip-title-overrides)

### cmp-fresh holds_delta.txt head 40
== holds cleared (41)
-- held now (5)
  blindmelon-1995-09-12  [held]  slices: slice4  still-held -> needs-brief
  minutemen-1984-12-01  [held]  slices: slice2  needs-llm -> structure-changed  (needs-llm)
  motherhips-2010-10-16  [held]  slices: slice2  needs-llm -> needs-brief  (needs-llm)
  radiators-1991-11-01  [held]  slices: slice3  still-held -> needs-brief
  robertwalters20thcongress-2004-01-02  [held]  slices: slice4  still-held -> structure-changed

-- would-hold on a fresh get (34)
  animalliberationorchestra-2006-12-29  [packaged]  slices: slice4  newly-held -> clean-changed
  bigheadtoddandthemonsters-1991-01-21  [packaged]  slices: slice3  needs-llm -> clean-changed  (needs-llm)
  billystrings-2017-07-15  [delivered]  slices: slice3  newly-held -> clean-changed
  billystrings-2021-12-04  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  blitzentrapper-2013-11-12  [packaged]  slices: slice3  newly-held -> clean-changed
  charlieparr-2003-01-10  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2005-05-30  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2011-04-15  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2012-07-21  [packaged]  slices: slice2  needs-llm -> clean-changed  (needs-llm)
  darkstarorchestra-2014-07-31  [packaged]  slices: slice3  newly-held -> clean-changed
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

### cmp-fresh title_changes.txt head 40
titles changed on shows that stay unheld (base -> cand); a path is the cascade's (D, C1, C2, S, S-deferred, 4, optional +5); '(unattributed)' = no recorded path

== packaged: 38 show(s), 363 position(s)
-- title text (308)
   by path: +5 1, 4 8, C1 69, C2 39, D 191
  animalliberationorchestra-2006-12-29 #6: 'alo2006-12-29.matrix.d1t06.mp3' (unresolved) -> '#2' (tags)  [4]
  bigheadtoddandthemonsters-1991-01-21 #3: '? (goodbye?) >' (tags) -> 'Battle of Billy the Kid' (sibling-format)  [C2]
  bigheadtoddandthemonsters-1991-01-21 #9: 'Been Without Him ?' (tags) -> 'Dinner With Ivan' (sibling-format)  [C2]
  bigheadtoddandthemonsters-1991-01-21 #12: '? (keep it in my heart?)' (tags) -> 'True Lady and Suspicious Minds' (sibling-format)  [C2]
  bigheadtoddandthemonsters-1991-01-21 #14: 'So Tired - Trying to get along with you?' (tags) -> "Tired Of Tryin'" (sibling-format)  [C2]
  bigheadtoddandthemonsters-1991-01-21 #17: '? (brother are you thinking for anotehr man?)' (tags) -> 'House Burned Down' (sibling-format)  [C2]
  bigheadtoddandthemonsters-1991-01-21 #23: 'bht_1991-01-21d2t10.mp3' (unresolved) -> 'Polk Salad Annie' (sibling-format)  [C1]
  billystrings-2021-12-04 #1: '01 Red Daisy.mp3' (unresolved) -> 'Red Daisy' (desc-position)  [D]
  billystrings-2021-12-04 #2: '02 Taking Water _ Ice Bridges.mp3' (unresolved) -> 'Taking Water > Ice Bridges' (desc-position)  [D]
  billystrings-2021-12-04 #3: '03 In the Morning Light.mp3' (unresolved) -> 'In the Morning Light' (desc-position)  [D]
  billystrings-2021-12-04 #4: '04 Southern Flavor.mp3' (unresolved) -> 'Southern Flavor' (desc-position)  [D]
  billystrings-2021-12-04 #5: '05 Hellbender.mp3' (unresolved) -> 'Hellbender' (desc-position)  [D]
  billystrings-2021-12-04 #6: "06 A Robin Built a Nest on Daddy's Grave.mp3" (unresolved) -> "A Robin Built a Nest on Daddy's Grave" (desc-position)  [D]
  billystrings-2021-12-04 #7: '07 Home of the Redfox _ John Hardy.mp3' (unresolved) -> 'Home of the Redfox > John Hardy' (desc-position)  [D]
  billystrings-2021-12-04 #8: '08 Today.mp3' (unresolved) -> 'Today' (desc-position)  [D]
  billystrings-2021-12-04 #9: '09 Wargasm.mp3' (unresolved) -> 'Wargasm' (desc-position)  [D]
  billystrings-2021-12-04 #10: '10 Cocaine Blues.mp3' (unresolved) -> 'Cocaine Blues' (desc-position)  [D]
  billystrings-2021-12-04 #11: '11 Slow Train.mp3' (unresolved) -> 'Slow Train' (desc-position)  [D]
  billystrings-2021-12-04 #12: "12 While I'm Waiting Here.mp3" (unresolved) -> "While I'm Waiting Here" (desc-position)  [D]
  billystrings-2021-12-04 #13: '13 Pyramid Country -- Ride Me High.mp3' (unresolved) -> 'Pyramid Country > Ride Me High > Pyramid' (desc-position)  [D]
  billystrings-2021-12-04 #14: '14 Show Me the Door.mp3' (unresolved) -> 'Show Me the Door' (desc-position)  [D]
  billystrings-2021-12-04 #15: '15 Must Be Seven.mp3' (unresolved) -> 'Must Be Seven' (desc-position)  [D]
  billystrings-2021-12-04 #16: '16 Paul Cauthen Intro.mp3' (unresolved) -> 'Paul Cauthen Intro' (desc-position)  [D]
  billystrings-2021-12-04 #17: '17 Mama Tried.mp3' (unresolved) -> 'Mama Tried' (desc-position)  [D]
  billystrings-2021-12-04 #18: '18 Friend of the Devil.mp3' (unresolved) -> 'Friend of the Devil' (desc-position)  [D]
  billystrings-2021-12-04 #19: '19 Hollow Heart -- Reynolds Wrap.mp3' (unresolved) -> 'Hollow Heart > Reynolds Wrap' (desc-position)  [D]
  billystrings-2021-12-04 #20: '20 Hide and Seek.mp3' (unresolved) -> 'Hide and Seek' (desc-position)  [D]
  billystrings-2021-12-04 #21: "21 'T' For Texas.mp3" (unresolved) -> "'T' For Texas" (desc-position)  [D]
  billystrings-2021-12-04 #22: '22 Long Gone.mp3' (unresolved) -> 'Long Gone' (desc-position)  [D]
  blitzentrapper-2013-11-12 #2: 'Evening Star' (tags) -> 'Fletcher' (sibling-format)  [C2]
  blitzentrapper-2013-11-12 #3: 'Blitzen_Trapper2013-11-12s01t03.mp3' (unresolved) -> 'Feel The Chill' (sibling-format)  [C1]
  charlieparr-2003-01-10 #1: 'cp03-01-10d1t01.mp3' (unresolved) -> 'Union Tramp' (desc-position)  [D]
  charlieparr-2003-01-10 #2: 'cp03-01-10d1t02.mp3' (unresolved) -> "Uncle Jack's Rag" (desc-position)  [D]
  charlieparr-2003-01-10 #3: 'cp03-01-10d1t03.mp3' (unresolved) -> "Roses While I'm Living" (desc-position)  [D]
  charlieparr-2003-01-10 #4: 'cp03-01-10d1t04.mp3' (unresolved) -> 'Lowdown' (desc-position)  [D]

## cmp-slice5 summary.txt (verbatim)
base reproduces 125/147 (held, not needs-LLM; gate skipped: --no-repro-gate)
needs-LLM held: base 187, cand 187
briefing guard reproduces 3/4
drift.txt: 316 show(s)
briefings.txt: 0 stored_brief_guard difference(s), 36 suppressed set-count/ordinal match(es)
flags.txt: 0 famil(ies)
newly cleared: 0
packaged_exposure.txt: 27 entr(ies)
venue_changes.txt: 0 show(s), 0 with a flag change
title_sources.txt: 51 row(s)
structure_changed.txt: 2 show(s)
hand_check_sample.txt: 0 show(s)
closest_calls.txt: 1309 row(s)
needs_llm.txt: base 858, cand 858
notes.txt: 2226 note(s)
holds_delta.txt: 0 cleared, 0 added
title_changes.txt: packaged 1, voiced 0, delivered 103
disabled slices: []
taper reports: not written (arms replayed with --strip-structure-overrides)
voiced check: delivery_path /Volumes/media/lma-radio/delivered
holds_delta.txt: 'would-hold on a fresh get' is empty in an as-is arm by construction (only an overrides-stripped arm records `stripped`)
apply lists: not written (arms replayed with --strip-structure-overrides or --strip-title-overrides)

### cmp-slice5 holds_delta.txt head 40
== holds cleared (0)
-- held now (0)
  (none)

-- would-hold on a fresh get (0)
  (none)

-- currently shipped (packaged/briefed/delivered/voiced) (0)
  (none)

== holds cleared by slice (a show with several is listed under each)
  (none)

== holds added (0)
  (none)

== holds added by slice (from the declines the cascade recorded)
  (none)

### cmp-slice5 title_changes.txt head 40
titles changed on shows that stay unheld (base -> cand); a path is the cascade's (D, C1, C2, S, S-deferred, 4, optional +5); '(unattributed)' = no recorded path

== packaged: 1 show(s), 1 position(s)
-- title text (1)
   by path: +5 1
  moe-2006-01-19 #19: 'Rise (encore)moe2006-01-19d1t01.flac:843ffe58aefdb9edc06434cddeb93a5a' (tags) -> 'Rise (encore)flac:843ffe58aefdb9edc06434cddeb93a5a' (tags)  [+5]
-- source only (0)
   by path: (none)
  (none)

== delivered: 7 show(s), 103 position(s)
-- title text (103)
   by path: +5 103
  gratefuldead-1983-10-12 #15: 'Tuning.wav' (tags) -> 'Tuning' (tags)  [+5]
  gratefuldead-1983-10-12 #19: 'Tuning.wav' (tags) -> 'Tuning' (tags)  [+5]
  gratefuldead-1984-10-14 #1: 's1t01 Alabama Getaway' (tags) -> 'Alabama Getaway' (tags)  [+5]
  gratefuldead-1984-10-14 #2: 's1t02 Greatest Story Ever Told' (tags) -> 'Greatest Story Ever Told' (tags)  [+5]
  gratefuldead-1984-10-14 #3: 's1t03 Dire Wolf' (tags) -> 'Dire Wolf' (tags)  [+5]
  gratefuldead-1984-10-14 #4: 's1t04 Little Red Rooster' (tags) -> 'Little Red Rooster' (tags)  [+5]
  gratefuldead-1984-10-14 #5: "s1t05 Dupree's Diamond Blues" (tags) -> "Dupree's Diamond Blues" (tags)  [+5]
  gratefuldead-1984-10-14 #6: 's1t06 My Brother Esau' (tags) -> 'My Brother Esau' (tags)  [+5]
  gratefuldead-1984-10-14 #7: 's1t07 Loser' (tags) -> 'Loser' (tags)  [+5]
  gratefuldead-1984-10-14 #8: 's1t08 New Minglewood Blues' (tags) -> 'New Minglewood Blues' (tags)  [+5]
  gratefuldead-1984-10-14 #9: 's1t09 Row Jimmy' (tags) -> 'Row Jimmy' (tags)  [+5]
  gratefuldead-1984-10-14 #10: 's1t10 I Need A Miracle' (tags) -> 'I Need A Miracle' (tags)  [+5]
  gratefuldead-1984-10-14 #11: 's1t11 Might As Well' (tags) -> 'Might As Well' (tags)  [+5]
  gratefuldead-1984-10-14 #12: 's2t01 China Cat Sunflower' (tags) -> 'China Cat Sunflower' (tags)  [+5]
  gratefuldead-1984-10-14 #13: 's2t02 I Know You Rider' (tags) -> 'I Know You Rider' (tags)  [+5]
  gratefuldead-1984-10-14 #14: 's2t03 Samson & Delilah' (tags) -> 'Samson & Delilah' (tags)  [+5]
  gratefuldead-1984-10-14 #15: 's2t04 High Time' (tags) -> 'High Time' (tags)  [+5]
  gratefuldead-1984-10-14 #16: 's2t05 Estimated Prophet' (tags) -> 'Estimated Prophet' (tags)  [+5]
  gratefuldead-1984-10-14 #17: 's2t06 Eyes Of The World' (tags) -> 'Eyes Of The World' (tags)  [+5]
  gratefuldead-1984-10-14 #18: 's2t07 Drums' (tags) -> 'Drums' (tags)  [+5]
  gratefuldead-1984-10-14 #19: 's2t08 Space' (tags) -> 'Space' (tags)  [+5]
  gratefuldead-1984-10-14 #20: 's2t09 China Doll' (tags) -> 'China Doll' (tags)  [+5]
  gratefuldead-1984-10-14 #21: 's2t10 Throwing Stones' (tags) -> 'Throwing Stones' (tags)  [+5]
  gratefuldead-1984-10-14 #22: 's2t11 Not Fade Away' (tags) -> 'Not Fade Away' (tags)  [+5]
  gratefuldead-1984-10-14 #23: 's2t12 Turn On Your Lovelight' (tags) -> 'Turn On Your Lovelight' (tags)  [+5]
  greatamericantaxi-2008-09-17 #1: '05:29 - One Of These Days' (tags) -> 'One Of These Days' (tags)  [+5]
  greatamericantaxi-2008-09-17 #2: '04:46 - Julia Belle Swain' (tags) -> 'Julia Belle Swain' (tags)  [+5]

## parity
parity of cand-fresh.json against the `all` arm of /Users/shawn/.llama-harness/piece3/gate-r16/dump.jsonl
dump sha version:0.1.0; arm disabled_slices []
compared 3983, matching 3983, mismatching 0; skipped 0; arm only 0; dump only 0

== mismatches
  (none)

== skipped
  (none)

== in the arm but not the dump
  (none)

## packets strata_index.txt
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
darkstarorchestra-2014-07-31	newly_cleared_sample	#4 C2; #5 C2; #6 C2; #7 C2; #8 C2; #9 C2; #10 C2; #11 C2; #12 C2; #13 C2; #14 C2; #15 C2; #16 C2; #17 C2; #18 C2; #19 C2; #20 C2; #21 C1
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
zentricksters-2002-12-31	delivered_changes	#19 +5
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
assemblyofdust-2004-12-31	r16	(none)
blindmelon-2008-06-24	r16	(none)
discobiscuits-2006-02-04	r16	(none)
furthur-2010-02-06	r16	(none)
gratefuldead-1980-05-10	r16	(none)
maxcreek-2009-01-31	r16	(none)
moe-2009-01-30	r16	(none)
moe-2009-02-27	r16	(none)
moe-2009-04-04	r16	(none)
mogwai-2006-04-25	r16	(none)
railroadearth-2005-08-20	r16	(none)
robynhitchcock-2009-03-21	r16	(none)
soundtribesector9-2008-07-23	r16	(none)
thedead-2009-05-02	r16	(none)
bigdaddybluegrassband-2004-07-24	readerii	(none)
bluestraveler-1993-04-09	readerii	(none)
gratefuldead-1979-02-17	readerii	(none)
hankwilliamsiii-2004-02-02	readerii	(none)
kungfuband-2013-01-25	readerii	(none)
moe-2008-06-20	readerii	(none)
motherhips-2011-02-04	readerii	#23 C2
pnuma-2005-05-09	readerii	(none)
soulive-2004-02-08	readerii	#10
stevekimockband-2004-08-21	readerii	(none)
yondermountainstringband-2005-02-04	readerii	(none)
yondermountainstringband-2005-04-30	readerii	(none)

## sha256 of every output file
0bef062a9d355ad127468f0b015050c79f184ceab405373be2c414a0dbeda0b0  arms/base-asis.json
759cd2f31743d1008e715a6329c2fee568feb7b6664667e5a3ea82c4106a32e5  arms/base-fresh.json
2db77631095b0b752a614e5100760d26aba8552c333e9213144b5dac301a3f54  arms/cand-asis.json
1335aa28b42262221ab55b0db7368813abd17fa6760d1113314db15b5f6174f6  arms/cand-fresh-no5.json
e1abc608c133323022455548c7c8c2dc562fc62d7db39c35b11caa17a347259a  arms/cand-fresh.json
5ce5f34a66d51426b41c026a67734663350f340f1ada7b12782cf7c2da868349  cmp-asis/briefings.txt
66f00bea2e24aac0453bbde5740c370362da62824d330d203d84e23f1c252b40  cmp-asis/closest_calls.txt
4aa0ded4f980e428ea6d0ed46b31e71ae4d03922ee1af3882e2ab4db4d1387ee  cmp-asis/drift.txt
3cdee8d1e5df8613ba51b6a5a076305443b756ae55bb951b501ced4317145671  cmp-asis/flags.txt
b5b52582425a4e3a7b8bb03b5a5019fde1d119dbed192f87752c0f6d6d4b7e22  cmp-asis/hand_check_sample.txt
7f3e03e2ad121625ea071b5d3b6bd5f88d8adcd1cd361a121c2788d97942d6e6  cmp-asis/holds_delta.txt
2b701bd0868ae5c338cf0389dcbb2e552741c072b7b1b58e21f6d5f42b861be0  cmp-asis/narration_candidates.html
e29cc8220151c6494de92b46780581b3f103060571e8ae7cbbfd6e47f50681b0  cmp-asis/needs_llm.txt
dce19001d6da2793418b38cd12fb7d97d9f5e913f7e13627f24b97a45c9066d5  cmp-asis/notes.txt
94d368a4ae28272a33531b35b94ac2db1ae52523aed11bd8945ca7e38099a6c4  cmp-asis/outcomes.txt
4046ba060c42d696ccb3681f97318d04dd7a4ef8ee090a1ebb092c5568358554  cmp-asis/packaged_exposure.txt
03db2f5e7f3709444876314ab8323089bc4897217c78fd1bf40f2d266835484e  cmp-asis/pilot_list.json
6d8fbf69552f7d52621a38d556aa717f44cb6a1b39b55e539a04be5124f15bbd  cmp-asis/predicted_list.json
e0b36bba69aa4308d684ca41ef76b70af7c11caf7585cda14fff22213bd228e4  cmp-asis/structure_changed_list.json
5a9ed84c8610b031d1fa5f69cbe19205197b20f8b0b326f038e786856065d498  cmp-asis/structure_changed.txt
b02e1a73d1f3b0120f3ae7a4af57c01540595104626abc779c59974a6a1b0648  cmp-asis/summary.txt
648d9abd7201cbd5b7f65475fa31473be0d0b856cf58fd2a33e2615123a266b1  cmp-asis/taper_changes.txt
fb2a08bd957169789adee662705abc75061b44fa4786fb69336c4d34a2dfc74e  cmp-asis/taper_cleared.txt
a525c31310e58a9054172cbf4ff5ae6df4be5797b2b650304079831fe09b6307  cmp-asis/title_changes.txt
189e82f1a7f28159b0538ff7ceefe74b37d9af0bb12ca85eb4c5c5f0bed09ee3  cmp-asis/title_rows.json
be56f2719b082f8a13403ba861345e104e0f0e30ad4119e5239e50a78e643d4a  cmp-asis/title_sources.txt
2d90a65c0ea820d710c09c76569ae7445f4d08ccd4ca3f811b5addc059dccd44  cmp-asis/venue_changes.txt
5ce5f34a66d51426b41c026a67734663350f340f1ada7b12782cf7c2da868349  cmp-fresh/briefings.txt
5ae2d7d31d8b15c00752828ec74f743ec95334764e93e76e2eadbb4794ca6b04  cmp-fresh/closest_calls.txt
82141ddbcbf11b2ced16e4f4592dd7e4aedd207b2d29e9f793b12cca9b3acc55  cmp-fresh/drift.txt
3cdee8d1e5df8613ba51b6a5a076305443b756ae55bb951b501ced4317145671  cmp-fresh/flags.txt
b5b52582425a4e3a7b8bb03b5a5019fde1d119dbed192f87752c0f6d6d4b7e22  cmp-fresh/hand_check_sample.txt
53531f99997966dd7cee7301a42b44ff054082d7344b8349d853e68c20176456  cmp-fresh/holds_delta.txt
2b701bd0868ae5c338cf0389dcbb2e552741c072b7b1b58e21f6d5f42b861be0  cmp-fresh/narration_candidates.html
3593166f0e880fe15aba850ffc2b7c1486177190d5d472168562c800200884b0  cmp-fresh/needs_llm.txt
9b00fee63374ed4a0545704bf5d6ee24c3ca3d9a9b3515901aae4ace3e6a546b  cmp-fresh/notes.txt
aa89eafcb6e58abccefa98254575b332ab1091bfa34be69a51b88d55b27dc448  cmp-fresh/outcomes.txt
3c1aee88debeea8ef9476d915b94f3188ab61cbc65f29d3c8d6de9e5028c07b6  cmp-fresh/packaged_exposure.txt
5a9ed84c8610b031d1fa5f69cbe19205197b20f8b0b326f038e786856065d498  cmp-fresh/structure_changed.txt
d1b23e4beebdd83e1173bb687cb3b283ac00cd24a628a99681e0a2544128c916  cmp-fresh/summary.txt
d84f0763646a8a19e8f919843731d0bed18bd3be75d6de44091b362ffb34ba8f  cmp-fresh/title_changes.txt
245bbe900f9a10d834cd48a541f02b7690ab43afe894cefa7908c49dfcd587bc  cmp-fresh/title_rows.json
be56f2719b082f8a13403ba861345e104e0f0e30ad4119e5239e50a78e643d4a  cmp-fresh/title_sources.txt
2d90a65c0ea820d710c09c76569ae7445f4d08ccd4ca3f811b5addc059dccd44  cmp-fresh/venue_changes.txt
5ce5f34a66d51426b41c026a67734663350f340f1ada7b12782cf7c2da868349  cmp-slice5/briefings.txt
4e430d6cc664829232ce8529dde3ffafbad5df5721006d4c2169c18f3236d22f  cmp-slice5/closest_calls.txt
6526c66a3e99aebe593ff76e49ea74625b7b1642fb62a592862e03865b3cf9b9  cmp-slice5/drift.txt
01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b  cmp-slice5/flags.txt
3dd946850c0bf9cbd1bba65a755f84357fe18b61b70af3478a0806055d42f0c6  cmp-slice5/hand_check_sample.txt
c4353b0addcc0bf3bf00fd14410ea7fbefd607d47bf0fa6844f08b3bce185fa9  cmp-slice5/holds_delta.txt
2b701bd0868ae5c338cf0389dcbb2e552741c072b7b1b58e21f6d5f42b861be0  cmp-slice5/narration_candidates.html
4cc74d49df8e3afca7cccd4d15b55f9f7cb623381d28732c86eb5a13ec049cbb  cmp-slice5/needs_llm.txt
9b00fee63374ed4a0545704bf5d6ee24c3ca3d9a9b3515901aae4ace3e6a546b  cmp-slice5/notes.txt
05ac9e081ca235d988a748ac5dc92c0fe257a636fd7dab0df054542e68565933  cmp-slice5/outcomes.txt
3f00e250b6dacc9e7f98495a78164de9d8921416b33e30e26202953d0bacaa01  cmp-slice5/packaged_exposure.txt
5a9ed84c8610b031d1fa5f69cbe19205197b20f8b0b326f038e786856065d498  cmp-slice5/structure_changed.txt
3d92a4e137d9d89cb5ce9d0f8f04a79bb4657d713416d7a477b7ca8cd1ebe302  cmp-slice5/summary.txt
0424a11ebc168d4cf9bc51ae630ce0a74fa413907d265b3cab8e40cddead627e  cmp-slice5/title_changes.txt
802acc9c7a3140504cf607089c00770f30bf44bc991be1cec895a95265d813db  cmp-slice5/title_rows.json
be56f2719b082f8a13403ba861345e104e0f0e30ad4119e5239e50a78e643d4a  cmp-slice5/title_sources.txt
2d90a65c0ea820d710c09c76569ae7445f4d08ccd4ca3f811b5addc059dccd44  cmp-slice5/venue_changes.txt
fd4ead749c76545313d3d0fb11c960beeb8b91701df6b4f2ae08af2397add84a  lists/r16.txt
310ab4873c61b1a95366de9de00bb139f94e8734a58f3732bbe506015b0d83d0  lists/readerii.txt
e57a060e3f32eb2ead7ad0ea65d7b478f3b6383969f0c0b11b8b9d23f58e31cb  packets/delivered_changes/alejandroescovedo-2008-03-02.md
7f7fb847ffe23d7a424939e6ee9d39df95ceea878a9be409a5387c14846b4bdc  packets/delivered_changes/alejandroescovedo-2014-03-30.md
3627b872eb62bdd0d032628fce30c44eb98fac99533a5f1a99a1edf65919f830  packets/delivered_changes/beneventorusso-2005-06-10.md
7536e46a769e7d1d14489f1c6204bbdc2fc02679c4528445d418d74ab8d70ad5  packets/delivered_changes/billystrings-2017-07-15.md
156db5a6dfdb4b0c83523a411701c4e2766945254d064be92b6c7bba28c0c5ee  packets/delivered_changes/billystrings-2020-02-21.md
63059761089a5c904bcb9309e8dc1464c4c6eb8aae4d26231634400b6198b0c7  packets/delivered_changes/buttholesurfers-1988-11-22.md
eb346149db2d41f02cbb4b62c92486f86e9adacae4d4964d008bacfa2a5846dc  packets/delivered_changes/cowboyjunkies-2012-04-15.md
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
ca5b82af14c0389f76e310d6219993b64d9eff3fc17afebd9a38fb2dc0a02160  packets/delivered_changes/gratefuldead-1974-10-18.md
e95656b3a861ca3fcf176fe9e39a8a96c1a2537e4fc38a4efc9ec928fa15d4ba  packets/delivered_changes/gratefuldead-1983-10-12.md
8de4121f6a8a015c3e72702ddcc7dafbdaaeebcee1e43fde5a5593209fb0fa22  packets/delivered_changes/gratefuldead-1984-10-14.md
be3a5198b564d44e5c2fbf4191fbe01d26bb54e3188f4dbcfa43614306cc5f7f  packets/delivered_changes/gratefuldead-1989-04-08.md
43b4fe40e953aa923cc4af1e4623823cec3d8622fd7ffdb0ebc018a349f9e820  packets/delivered_changes/greatamericantaxi-2008-09-17.md
17e73fea3750df57c5296ef8e2272f5735531fd5f17e4159db96b0c465118a89  packets/delivered_changes/greenskybluegrass-2012-09-25.md
62dcc884358b20a53faf9266a7a6de93aa311cda74caaa6ec2a84783f4c0aefd  packets/delivered_changes/greenskybluegrass-2013-05-04.md
0d32d14dfac767ac8d5e8334d021e46deacfbc5674bfde00e47d624ccb3e6967  packets/delivered_changes/greenskybluegrass-2015-02-27.md
62ed61ca3b8c36183a1f74103590f52cd64fa573b00bb30ae306e1ab25a65d04  packets/delivered_changes/johnkadlecik-2017-10-31.md
a102133fd927ad8d4b4972b2db869f514afa3d7d958aca22d9cd08630502450c  packets/delivered_changes/kungfuband-2013-02-13.md
6dca0458d98c9510225efd2459c461ba1eabca57fbaf1f0d922269f2dfa6fa49  packets/delivered_changes/leftoversalmon-1997-10-31.md
eef15449974b0173ce419ea68cbb8488a894b775bd04f30184cf7e163cf9d63d  packets/delivered_changes/lettuce-2010-11-14.md
401e7bf4e990354ab3bf8208262cfceccb7eecf7adc71021a8237158e9a6bace  packets/delivered_changes/lotus-2008-02-07.md
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
1525f9b62e6bddc35d76ec1eabb49519b01d95169512469ca885c15c5e8ce544  packets/delivered_changes/zentricksters-2002-12-31.md
0bc10b3d6811ced7aea9584788166ee1e4c262069c0282c37c85bf493aa83af7  packets/newly_cleared_sample/animalliberationorchestra-2006-12-29.md
dad4a52060d461915ca9c18b347a493cfd54ecc2a88300ef6d5702557fb3d47f  packets/newly_cleared_sample/bigheadtoddandthemonsters-1991-01-21.md
502d872c85b1900291abeb7efa714643e9acb700bb692ab66fe4773d81dc8f3c  packets/newly_cleared_sample/billystrings-2017-07-15.md
cfa163545f8b94cfaa2ee9463c8df440909e4b771e9c64151db0d58a0bd84f41  packets/newly_cleared_sample/blindmelon-1995-09-12.md
88f8d68d9d31dbacc54e2f6ad20ee1839ad3268fea717fc81fabced278cee6e6  packets/newly_cleared_sample/blitzentrapper-2013-11-12.md
3c220c1f86ad462906a0e538613083579f68e7d5783d97783329b66e1ef61941  packets/newly_cleared_sample/darkstarorchestra-2014-07-31.md
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
a174a65fb35d6e16fb104545fb423fb8f3682e3c6eef8a90d0cb35e24bfcf97e  packets/r16/assemblyofdust-2004-12-31.md
db4b5a152fd83b0970dcad563ef4fb1b2ccfd2e35f574e9f9326be524800335d  packets/r16/blindmelon-2008-06-24.md
f7304a54a56262a8b72247be7ffe97e65f89cc2626bbf4e9fa3375ec972328bb  packets/r16/discobiscuits-2006-02-04.md
cbc0bed1d21ccefb2995013c1d1cb294532beea4519856bdbb8989a79a097c66  packets/r16/furthur-2010-02-06.md
401b1551df258bcc9c0c68e651325b950b9cecb73b180a189ebf5da677983d19  packets/r16/gratefuldead-1980-05-10.md
f5c1505480363bedb355dc7d902a52f77cec7b07180fcda2bd9f7146218ce5e2  packets/r16/maxcreek-2009-01-31.md
d27afe70008cb65fa46031923c0edede75b98c8bb4e6e4983e54cb2d29740c7a  packets/r16/moe-2009-01-30.md
cc297b295da42b148395a4c80561bd1e76d6b105dedbfa34d1b2564529de062f  packets/r16/moe-2009-02-27.md
3c43a3e1af923b918d38b44f265c074af096ebfc791af59bd95cccf7be164e67  packets/r16/moe-2009-04-04.md
6264a67105187cd9f37355b608da26f49c415c58b66583368cec530a42fec21c  packets/r16/mogwai-2006-04-25.md
ce9378a092332dbb2a7f7fe4a4f6e5e52540ced760f2d8cc1a0ee2e346cbaad7  packets/r16/railroadearth-2005-08-20.md
28e8bf9a483440754860c577bca0a8ae4304473fc00ea4833333528d2511ad48  packets/r16/robynhitchcock-2009-03-21.md
cf646a536a38789824a3720f72f86e4c663d1264682048a594fd870a61f5b0d9  packets/r16/soundtribesector9-2008-07-23.md
5b86a9aa23002fd21a911f2add94cb26a5eb7a5c0cfe88c9bbdab45b3c6d2be8  packets/r16/thedead-2009-05-02.md
eac95e68731e30dcdf23afe9fc3345c1a193016280854c92b3ab431d9d16f940  packets/readerii/bigdaddybluegrassband-2004-07-24.md
2fb3d424549c231e5b278b2829479a43ea1d4bdc49f7b91878b54ff6ddc5affd  packets/readerii/bluestraveler-1993-04-09.md
19fb7d01e01abca66efcbb96686e605409d34fb61332a16ab2c2898c80ce01ba  packets/readerii/gratefuldead-1979-02-17.md
94c2f86ce77c9f98280664eac7e002a2d82853d5edcd4100323b0aa1757401ae  packets/readerii/hankwilliamsiii-2004-02-02.md
996239f3cef6ab26427d8b13f88bf3a3ed4d0062dd7b2110bb7c3f17dd7bf0fa  packets/readerii/kungfuband-2013-01-25.md
fb44e62b7f7a3b8aae2f28b777d01da0537ddf51d8a83728ccf141890ec0f50c  packets/readerii/moe-2008-06-20.md
20ea53d5b9cec01d66f0b7a482da7497ec9ce172b50bd2217cc88b9424288506  packets/readerii/motherhips-2011-02-04.md
364be72d781d4cc20378b44be33d8d9e5b5ba3c7be15a2117b09462aa440f31b  packets/readerii/pnuma-2005-05-09.md
c7a5ac79f25f35eb9bc3ac617e51580f6ece27ef0dcc3905ad9f0321728e353c  packets/readerii/soulive-2004-02-08.md
85e0d15085ead0c33129d649acdcca173b050bbccfd4b88157d79beda6161d09  packets/readerii/stevekimockband-2004-08-21.md
78ef0b606cc5c44a9a9ee799fbe1e9f2181247fdb59c93cff6c274bd9618eae0  packets/readerii/yondermountainstringband-2005-02-04.md
1976f5c2517c7323cdbb0e305fd55601870b593b892e5711b96a7eb32f5a6cd9  packets/readerii/yondermountainstringband-2005-04-30.md
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
b63cb1c912e65ffc4bf78aa21e15e1bfb142a1f010d31ac61264e808d45bef16  packets/strata_index.json
f1b4490a61c1ca05ff1a5214791a92410adc3a153807fea16904765f44ff843d  packets/strata_index.txt
9b05c6408393f32b6f5564de31290815dd51e813f706a87eb6d198ef05544218  packets/wholly_untagged_d3/billystrings-2021-12-04.md
6465e5f64e797366993048272ca0a4294887e07d51de7702ef4e1a71f920d070  packets/wholly_untagged_d3/charlieparr-2003-01-10.md
9237e51d918d1f0035599c7981776ffb2b6002722f74fb53368d1fb88f026722  packets/wholly_untagged_d3/darkstarorchestra-2005-02-19.md
41f86df72d2f98edbb4645a3c2658b7043f14818b496b6117677ed7496a875ab  packets/wholly_untagged_d3/darkstarorchestra-2005-05-30.md
c8888fa4355fbff02d372eabf0e35bee19b082cb6ac75d86cdf5e33690e85d27  packets/wholly_untagged_d3/darkstarorchestra-2011-04-15.md
70fb2ffcbb571cc25702a8c077457b9b21bce78f7b17b9fe96c680258b39a563  packets/wholly_untagged_d3/darkstarorchestra-2012-07-21.md
e4db32367d4a4d9b0189446bcb8574ef7f0d123c3fc5a0048cf342faf9febc5a  packets/wholly_untagged_d3/deepbananablackout-2004-04-01.md
5c3b85e4de4000cfa27d32189777ccf6de98ce5ae710cf4acc250e063e937fd4  packets/wholly_untagged_d3/derektrucksband-2006-12-31.md
b189463d0dc9545e5b064598bc2c04ce1cfb788e6e59058e9359f6ef7e9cb971  packets/wholly_untagged_d3/minutemen-1984-12-01.md
c04b6c5327bea5708cd2a2a2299a249ba476a833fbd7d59e81ad84cd4120cecf  packets/wholly_untagged_d3/motherhips-2010-10-16.md
ca0d2d0a36c8d2af3a152809772061f2e6ace8ea0f10893546c8902c31a5b653  packets/wholly_untagged_d3/mymorningjacket-2004-06-18.md
8a9611dfc288076876ea870b671f53cc3f08efafb34e9afdf8313ce0567a4bfc  packets/wholly_untagged_d3/railroadearth-2019-04-08.md
7238ac5d951d43c776df792d1d3f3c03c45a237aeeae351a05752cedd9f21363  packets/wholly_untagged_d3/ryanadams-2002-02-06.md
629759f5eef72b54e5e28617a2d11a63fed1f1a4b679f1d2ebc61ea7dfd5a8b6  packets/wholly_untagged_d3/soulive-2005-03-11.md
ab5c20824cde110564499e866ef0f80f387117d5385e40c675b408dbbd3f51ca  packets/wholly_untagged_d3/thecodetalkers-2005-08-06.md
5f44f8b153e2cb6475c87540cd956dd661f55eaa3238c90947f42abcc3b036b8  packets/wholly_untagged_d3/thegrassisdead-2001-10-21.md
c22d171d72a3e8244b0d6e56afbc3b2c271c5bdc132f31158398a6ec29ddf5fb  packets/wholly_untagged_d3/yondermountainstringband-2005-07-24.md
7394bb0695ab84f172011b2fdd0b004e45d93fd1dc8def096bbf866ad3e0639c  packets/wholly_untagged_d3/zero-1986-09-06.md
240e822b795ff84e2c8cd930e67b6ede6d68412dfda946174598358fb30df03b  parity/parity.txt

## packets stdout line
packets: wholly_untagged_d3 18, newly_cleared_sample 23, delivered_changes 74, slice4 16, r16 14, readerii 12
## parity stdout line
parity: 3983 compared, 0 mismatching (/Users/shawn/.llama-harness/piece3/accept/parity/parity.txt)
parity exit 0, mismatches 0
