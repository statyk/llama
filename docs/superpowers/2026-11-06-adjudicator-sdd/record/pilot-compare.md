# Adjudicator pilot comparison

## Outcomes per class and arm

| class | arm | sampled | population | outcomes |
|---|---|---|---|---|
| partial tape | opus | 4 | 31 | held with proposal: 1, malformed: 1, would auto-apply: 2 |
| partial tape | sonnet | 4 | 31 | held, no proposal: 1, malformed: 1, would auto-apply: 2 |
| partial tape with a better sibling | opus | 3 | 28 | held with proposal: 3 |
| partial tape with a better sibling | sonnet | 3 | 28 | held with proposal: 1, malformed: 1, would auto-apply: 1 |
| better sibling | opus | 3 | 23 | held with proposal: 3 |
| better sibling | sonnet | 3 | 23 | held with proposal: 1, held, no proposal: 1, would auto-apply: 1 |
| untitled or untitled-echo | opus | 6 | 85 | held with proposal: 3, stale: reprocess first: 2, would auto-apply: 1 |
| untitled or untitled-echo | sonnet | 6 | 85 | held with proposal: 2, held, no proposal: 2, stale: reprocess first: 2 |
| scrambled or shifted tags | opus | 3 | 25 | held, no proposal: 1, stale: reprocess first: 1, would auto-apply: 1 |
| scrambled or shifted tags | sonnet | 3 | 25 | held with proposal: 1, held, no proposal: 1, stale: reprocess first: 1 |
| needs a listen | opus | 5 | 71 | held with proposal: 2, held, no proposal: 1, stale: reprocess first: 2 |
| needs a listen | sonnet | 5 | 71 | held with proposal: 1, held, no proposal: 2, stale: reprocess first: 2 |
| other | opus | 6 | 82 | held, no proposal: 2, stale: reprocess first: 1, would auto-apply: 3 |
| other | sonnet | 6 | 82 | held, no proposal: 2, stale: reprocess first: 1, would auto-apply: 3 |

## Projected held-with-proposal

Sampled share of each class that ends held with a proposal, scaled to the held population.

| class | arm | held with proposal | population | projected |
|---|---|---|---|---|
| partial tape | opus | 1 of 4 | 31 | 7.8 |
| partial tape | sonnet | 0 of 4 | 31 | 0.0 |
| partial tape with a better sibling | opus | 3 of 3 | 28 | 28.0 |
| partial tape with a better sibling | sonnet | 1 of 3 | 28 | 9.3 |
| better sibling | opus | 3 of 3 | 23 | 23.0 |
| better sibling | sonnet | 1 of 3 | 23 | 7.7 |
| untitled or untitled-echo | opus | 3 of 6 | 85 | 42.5 |
| untitled or untitled-echo | sonnet | 2 of 6 | 85 | 28.3 |
| scrambled or shifted tags | opus | 0 of 3 | 25 | 0.0 |
| scrambled or shifted tags | sonnet | 1 of 3 | 25 | 8.3 |
| needs a listen | opus | 2 of 5 | 71 | 28.4 |
| needs a listen | sonnet | 1 of 5 | 71 | 14.2 |
| other | opus | 0 of 6 | 82 | 0.0 |
| other | sonnet | 0 of 6 | 82 | 0.0 |

Projected total: opus 129, sonnet 67

## Partial-tape classes

Could the gate auto-apply them at all?

- partial tape, opus: 2 of 4 auto-applicable; 2 blocked
    - 1 x kind is hold
    - 1 x show not judged correct after the action (no)
    - 1 x flag judged real-not-fixable: low-confidence setlist
    - 1 x structure: structure bar needs high confidence
    - 1 x no edits
- partial tape, sonnet: 2 of 4 auto-applicable; 2 blocked
    - 2 x no edits
    - 1 x kind is hold
    - 1 x show not judged correct after the action (no)
    - 1 x flag judged real-not-fixable: low-confidence setlist
- partial tape with a better sibling, opus: 0 of 3 auto-applicable; 3 blocked
    - 2 x switch_recording: show is station-marked
    - 1 x kind is hold
    - 1 x show not judged correct after the action (no)
    - 1 x switch_recording: sibling's lineage class ranks worse than the current recording's; switch needs high confidence; show is station-marked
- partial tape with a better sibling, sonnet: 1 of 3 auto-applicable; 2 blocked
    - 1 x no edits
    - 1 x switch_recording: show is station-marked

## Disagreements between arms

- darkstarorchestra-2010-07-02 (partial tape): opus held with proposal [('structure', "breaks_after=['dso2010-07-02d1t10-GDTRFB.mp3'] encore_after=dso2010-07-02d2t08-EvansRap.mp3")] / sonnet held, no proposal []
- waynehancock-2004-04-08 (partial tape): opus malformed [('include', 'WayneHancock2004-08-04d2-01.mp3'), ('include', 'WayneHancock2004-08-04d2-02.mp3'), ('include', 'WayneHancock2004-08-04d2-03.mp3'), ('include', 'WayneHancock2004-08-04d2-04.mp3'), ('include', 'WayneHancock2004-08-04d2-05.mp3'), ('include', 'WayneHancock2004-08-04d2-06.mp3'), ('include', 'WayneHancock2004-08-04d2-07.mp3'), ('include', 'WayneHancock2004-08-04d2-08.mp3'), ('include', 'WayneHancock2004-08-04d2-09.mp3'), ('include', 'WayneHancock2004-08-04d2-10.mp3'), ('include', 'WayneHancock2004-08-04d2-11.mp3'), ('set_title', 'WayneHancock2004-08-04d2-08.mp3'), ('set_title', 'WayneHancock2004-08-04d2-10.mp3'), ('structure', 'breaks_after=[] encore_after=WayneHancock2004-08-04d2-10.mp3')] / sonnet malformed [('include', 'WayneHancock2004-08-04d2-01.mp3'), ('include', 'WayneHancock2004-08-04d2-02.mp3'), ('include', 'WayneHancock2004-08-04d2-03.mp3'), ('include', 'WayneHancock2004-08-04d2-04.mp3'), ('include', 'WayneHancock2004-08-04d2-05.mp3'), ('include', 'WayneHancock2004-08-04d2-06.mp3'), ('include', 'WayneHancock2004-08-04d2-07.mp3'), ('include', 'WayneHancock2004-08-04d2-08.mp3'), ('include', 'WayneHancock2004-08-04d2-09.mp3'), ('include', 'WayneHancock2004-08-04d2-10.mp3'), ('include', 'WayneHancock2004-08-04d2-11.mp3'), ('set_title', 'WayneHancock2004-08-04d2-08.mp3'), ('set_title', 'WayneHancock2004-08-04d2-10.mp3'), ('structure', "breaks_after=['Wayne2004-04-08d1-19.mp3'] encore_after=WayneHancock2004-08-04d2-10.mp3")]
- discobiscuits-2002-10-02 (partial tape with a better sibling): opus held with proposal [('switch_recording', 'db2002-10-02.shnf')] / sonnet malformed [('switch_recording', 'db2002-10-02.shnf')]
- gratefuldead-1971-12-01 (partial tape with a better sibling): opus held with proposal [('switch_recording', 'gd71-12-01.aud.minches-vernon.24765.sbeok.shnf')] / sonnet would auto-apply [('overrule', 'structure has 1 sets but jerrybase shows 2')]
- gratefuldead-1982-04-14 (better sibling): opus held with proposal [('switch_recording', 'gd1982-04-14.mtx.griesman.30206.sbeok.flac16')] / sonnet held, no proposal []
- thenewdeal-2004-11-26 (better sibling): opus held with proposal [('overrule', 'research asserts wrong date: Thursday, Nov 25'), ('switch_recording', 'tND2004-11-26')] / sonnet held with proposal [('switch_recording', 'tND2004-11-26')]
- yondermountainstringband-2009-07-11 (better sibling): opus held with proposal [('switch_recording', 'ymsb2009-07-11.u89i_16bit')] / sonnet would auto-apply [('overrule', 'low-confidence structure alignment'), ('overrule', 'research asserts unknown song: 2 Hits & The Joint Turned Brown'), ('overrule', 'research asserts unknown song: 20 Eyes'), ('overrule', 'research asserts unknown song: Angel'), ('overrule', 'research asserts unknown song: Casualty'), ('overrule', 'research asserts unknown song: Complicated'), ('overrule', "research asserts unknown song: Dave's New Instrumental"), ('overrule', "research asserts unknown song: Don't You Lean On Me"), ('overrule', 'research asserts unknown song: East Nashville Easter'), ('overrule', 'research asserts unknown song: Fingerprint'), ('overrule', 'research asserts unknown song: Follow Me Down To The Riverside'), ('overrule', 'research asserts unknown song: King Ebeneezer'), ('overrule', 'research asserts unknown song: Left Me In A Hole'), ('overrule', 'research asserts unknown song: Peace Of Mind'), ('overrule', "research asserts unknown song: Sharecropper's Son"), ('overrule', 'research asserts unknown song: Troubled Mind')]
- hollybowling-2019-09-12 (untitled or untitled-echo): opus held with proposal [('set_title', 'hollyb-2019-09-12-at853-s1t03.mp3'), ('set_title', 'hollyb-2019-09-12-at853-s2t04.mp3'), ('set_title', 'hollyb-2019-09-12-at853-s2t05.mp3'), ('structure', "breaks_after=['hollyb-2019-09-12-at853-s1t08.mp3'] encore_after=hollyb-2019-09-12-at853-s2t09.mp3")] / sonnet held with proposal [('structure', "breaks_after=['hollyb-2019-09-12-at853-s1t08.mp3'] encore_after=hollyb-2019-09-12-at853-s2t09.mp3")]
- infamousstringdusters-2010-10-15 (untitled or untitled-echo): opus would auto-apply [('overrule', 'research asserts unknown song: Count Me In'), ('overrule', 'research asserts unknown song: Dream You Back'), ('overrule', 'research asserts unknown song: Get On With It'), ('overrule', 'research asserts unknown song: Sunny Side Of The Mountain'), ('overrule', 'research asserts unknown song: Well, Well')] / sonnet held, no proposal []
- philleshandfriends-2007-10-20 (untitled or untitled-echo): opus held with proposal [('overrule', 'research asserts unknown song: Alabama Getaway'), ('overrule', 'research asserts unknown song: Bertha'), ('overrule', 'research asserts unknown song: Box of Rain'), ('overrule', 'research asserts unknown song: Cumberland'), ('overrule', 'research asserts unknown song: Cumberland Blues'), ('overrule', 'research asserts unknown song: Dark Star'), ('overrule', 'research asserts unknown song: Deal'), ('overrule', 'research asserts unknown song: Deep Elem Blues'), ('overrule', "research asserts unknown song: Franklin's Tower"), ('overrule', 'research asserts unknown song: Friend of the Devil'), ('overrule', 'research asserts unknown song: Help on the Way'), ('overrule', 'research asserts unknown song: Plasma'), ('overrule', 'research asserts unknown song: Pride of Cucamonga'), ('overrule', 'research asserts unknown song: Shine'), ('overrule', 'research asserts unknown song: Slipknot!'), ('overrule', 'research asserts unknown song: Unbroken Chain'), ('overrule', 'research asserts unknown song: Viola Lee'), ('overrule', 'research asserts unknown song: Viola Lee Blues'), ('overrule', 'research asserts unknown song: Wharf Rat'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t01.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t02.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t03.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t04.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t05.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t06.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d1t07.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d2t01.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d2t02.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d2t03.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t01.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t02.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t03.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t04.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t05.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t06.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t07.mp3'), ('set_title', 'plf2007-10-20.md421.flac16/plf2007-10-20d3t08.mp3'), ('structure', "breaks_after=['plf2007-10-20.md421.flac16/plf2007-10-20d1t07.mp3'] encore_after=plf2007-10-20.md421.flac16/plf2007-10-20d3t06.mp3")] / sonnet held with proposal [('switch_recording', 'plf2007-10-20.spyder9.flac16')]
- southerncultureontheskids-2006-11-18 (untitled or untitled-echo): opus held with proposal [('set_title', 'SCOTS2006-11-18D2T07.mp3')] / sonnet held, no proposal []
- soundtribesector9-2000-09-26 (scrambled or shifted tags): opus would auto-apply [('set_title', '01 STS92000.09.26.mp3'), ('set_title', '02 STS92000.09.26.mp3'), ('set_title', '03 STS92000.09.26.mp3'), ('set_title', '04 STS92000.09.26.mp3'), ('set_title', '05 STS92000.09.26.mp3'), ('set_title', '06 STS92000.09.26.mp3'), ('set_title', '07 STS92000.09.26.mp3'), ('set_title', '08 STS92000.09.26.mp3'), ('set_title', '09 STS92000.09.26.mp3'), ('set_title', '10 STS92000.09.26.mp3')] / sonnet held with proposal [('set_title', '03 STS92000.09.26.mp3'), ('set_title', '04 STS92000.09.26.mp3'), ('set_title', '05 STS92000.09.26.mp3'), ('set_title', '09 STS92000.09.26.mp3')]
- deepbananablackout-2010-07-31 (needs a listen): opus held with proposal [('overrule', 'research asserts unknown song: Get Up Offa That Thang'), ('overrule', 'research asserts unknown song: Get Up Offa That Thing'), ('overrule', 'research asserts unknown song: God Made You Funky'), ('overrule', 'research asserts unknown song: Take The Time'), ('overrule', 'research asserts unknown song: Working Like a Dog'), ('set_title', 'dbb2010-07-31t02.mp3'), ('set_title', 'dbb2010-07-31t03.mp3'), ('set_title', 'dbb2010-07-31t04.mp3'), ('set_title', 'dbb2010-07-31t05.mp3'), ('set_title', 'dbb2010-07-31t06.mp3'), ('set_title', 'dbb2010-07-31t07.mp3'), ('set_title', 'dbb2010-07-31t08.mp3'), ('set_title', 'dbb2010-07-31t09.mp3'), ('set_title', 'dbb2010-07-31t10.mp3'), ('set_title', 'dbb2010-07-31t11.mp3'), ('set_title', 'dbb2010-07-31t12.mp3'), ('set_title', 'dbb2010-07-31t13.mp3'), ('structure', 'breaks_after=[] encore_after=dbb2010-07-31t10.mp3')] / sonnet held, no proposal []
- explosionsinthesky-2004-10-13 (needs a listen): opus held with proposal [('overrule', 'research asserts unknown song: Greet Death'), ('set_title', 'eits2004-10-13t05.mp3')] / sonnet held with proposal [('overrule', 'research asserts unknown song: Greet Death')]

## Agreement with the prototype verdicts

### opus: by kind (prototype -> opus)

| prototype | opus | shows |
|---|---|---|
| fix | fix | 2 |
| fix | hold | 3 |
| fix | overrule | 3 |
| hold | fix | 4 |
| hold | hold | 7 |
| hold | overrule | 2 |
| overrule | overrule | 1 |

### opus: by edit target

| edit | both | arm only | prototype only |
|---|---|---|---|
| exclude | 0 | 0 | 3 |
| include | 1 | 0 | 0 |
| overrule | 3 | 6 | 4 |
| set_title | 5 | 0 | 5 |
| structure | 4 | 0 | 5 |
| switch_recording | 0 | 6 | 0 |

### sonnet: by kind (prototype -> sonnet)

| prototype | sonnet | shows |
|---|---|---|
| fix | fix | 1 |
| fix | hold | 5 |
| fix | overrule | 2 |
| hold | fix | 2 |
| hold | hold | 7 |
| hold | overrule | 4 |
| overrule | overrule | 1 |

### sonnet: by edit target

| edit | both | arm only | prototype only |
|---|---|---|---|
| exclude | 0 | 0 | 3 |
| include | 1 | 0 | 0 |
| overrule | 3 | 5 | 4 |
| set_title | 1 | 0 | 9 |
| structure | 2 | 0 | 7 |
| switch_recording | 0 | 3 | 0 |

## Trial applies

A trial apply is applied, then restored: what it measured about the re-run.

### opus

- buttholesurfers-1987-11-07 (partial tape) other: applied, hold cleared
- littlefeat-1977-08-08 (partial tape) other: applied, hold cleared
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) other: applied, hold cleared

### sonnet

- buttholesurfers-1987-11-07 (partial tape) other: applied, hold cleared
- littlefeat-1977-08-08 (partial tape) other: applied, hold cleared
- gratefuldead-1971-12-01 (partial tape with a better sibling) other: applied, hold cleared

## Cost and wall time

Judge-only rows (one LLM call) and trial rows (judge plus a trial apply, which re-runs vet and brief) are separate. Rows whose 5-hour meter fell or is unread (a window reset) are counted in the last column and left out of the point means.

| arm | kind | rows | mean 5h-meter points/show | mean wall s | dropped from points |
|---|---|---|---|---|---|
| opus | judge-only | 27 | 0.22 | 19.5 | 0 |
| opus | trial | 3 | 0.67 | 195.6 | 0 |
| sonnet | judge-only | 27 | 0.11 | 11.3 | 0 |
| sonnet | trial | 3 | 1.00 | 177.5 | 0 |

Projected full sweep (345 held shows), from the judge-only rows:
- opus: 77 points, 1.9 h wall
- sonnet: 38 points, 1.1 h wall

## Per-show cost

### opus

| slug | class | outcome | trial | 5h delta | wall s |
|---|---|---|---|---|---|
| buttholesurfers-1987-11-07 | partial tape | dry-run | other | 0.0 | 147.4 |
| darkstarorchestra-2010-07-02 | partial tape | dry-run | - | 0.0 | 15.3 |
| littlefeat-1977-08-08 | partial tape | dry-run | other | 1.0 | 186.0 |
| waynehancock-2004-04-08 | partial tape | malformed | - | 0.0 | 33.3 |
| discobiscuits-2002-10-02 | partial tape with a better sibling | dry-run | - | 1.0 | 18.5 |
| gratefuldead-1971-12-01 | partial tape with a better sibling | dry-run | - | 0.0 | 19.9 |
| soulcoughing-1998-10-25 | partial tape with a better sibling | dry-run | - | 0.0 | 21.9 |
| gratefuldead-1982-04-14 | better sibling | dry-run | - | 1.0 | 22.4 |
| thenewdeal-2004-11-26 | better sibling | dry-run | - | 0.0 | 33.6 |
| yondermountainstringband-2009-07-11 | better sibling | dry-run | - | 1.0 | 27.4 |
| hollybowling-2019-09-12 | untitled or untitled-echo | dry-run | - | 0.0 | 25.1 |
| infamousstringdusters-2010-10-15 | untitled or untitled-echo | dry-run | other | 1.0 | 253.3 |
| mymorningjacket-2004-05-28 | untitled or untitled-echo | stale: reprocess first | - | 0.0 | 1.9 |
| philleshandfriends-2007-10-20 | untitled or untitled-echo | dry-run | - | 0.0 | 85.9 |
| robertwalters20thcongress-2004-01-02 | untitled or untitled-echo | stale: reprocess first | - | 0.0 | 1.9 |
| southerncultureontheskids-2006-11-18 | untitled or untitled-echo | dry-run | - | 0.0 | 12.2 |
| leftoversalmon-1996-03-16 | scrambled or shifted tags | stale: reprocess first | - | 0.0 | 1.2 |
| railroadearth-2005-04-06 | scrambled or shifted tags | dry-run | - | 0.0 | 13.6 |
| soundtribesector9-2000-09-26 | scrambled or shifted tags | dry-run | - | 1.0 | 27.2 |
| deepbananablackout-2010-07-31 | needs a listen | dry-run | - | 0.0 | 47.4 |
| explosionsinthesky-2004-10-13 | needs a listen | dry-run | - | 1.0 | 18.2 |
| greatamericantaxi-2009-11-03 | needs a listen | stale: reprocess first | - | 0.0 | 1.8 |
| karldensonstinyuniverse-2008-12-19 | needs a listen | dry-run | - | 0.0 | 20.9 |
| soulive-2003-08-07 | needs a listen | stale: reprocess first | - | 0.0 | 0.8 |
| elliottsmith-1997-05-06 | other | stale: reprocess first | - | 0.0 | 0.8 |
| garajmahal-2003-05-16 | other | dry-run | - | 0.0 | 14.0 |
| gratefuldead-1993-03-17 | other | dry-run | - | 0.0 | 21.3 |
| joerussosalmostdead-2019-06-15 | other | dry-run | - | 0.0 | 9.0 |
| moe-2004-10-31 | other | dry-run | - | 0.0 | 12.1 |
| themotet-2013-04-20 | other | dry-run | - | 1.0 | 19.1 |

### sonnet

| slug | class | outcome | trial | 5h delta | wall s |
|---|---|---|---|---|---|
| buttholesurfers-1987-11-07 | partial tape | dry-run | other | 1.0 | 226.5 |
| darkstarorchestra-2010-07-02 | partial tape | dry-run | - | 0.0 | 10.3 |
| littlefeat-1977-08-08 | partial tape | dry-run | other | 1.0 | 182.2 |
| waynehancock-2004-04-08 | partial tape | malformed | - | 0.0 | 25.1 |
| discobiscuits-2002-10-02 | partial tape with a better sibling | malformed | - | 0.0 | 11.1 |
| gratefuldead-1971-12-01 | partial tape with a better sibling | dry-run | other | 1.0 | 123.9 |
| soulcoughing-1998-10-25 | partial tape with a better sibling | dry-run | - | 0.0 | 13.8 |
| gratefuldead-1982-04-14 | better sibling | dry-run | - | 0.0 | 14.6 |
| thenewdeal-2004-11-26 | better sibling | dry-run | - | 1.0 | 17.1 |
| yondermountainstringband-2009-07-11 | better sibling | dry-run | - | 0.0 | 20.9 |
| hollybowling-2019-09-12 | untitled or untitled-echo | dry-run | - | 0.0 | 12.5 |
| infamousstringdusters-2010-10-15 | untitled or untitled-echo | dry-run | - | 0.0 | 9.6 |
| mymorningjacket-2004-05-28 | untitled or untitled-echo | stale: reprocess first | - | 0.0 | 0.7 |
| philleshandfriends-2007-10-20 | untitled or untitled-echo | dry-run | - | 0.0 | 41.5 |
| robertwalters20thcongress-2004-01-02 | untitled or untitled-echo | stale: reprocess first | - | 0.0 | 0.7 |
| southerncultureontheskids-2006-11-18 | untitled or untitled-echo | dry-run | - | 1.0 | 9.2 |
| leftoversalmon-1996-03-16 | scrambled or shifted tags | stale: reprocess first | - | 0.0 | 0.7 |
| railroadearth-2005-04-06 | scrambled or shifted tags | dry-run | - | 0.0 | 10.1 |
| soundtribesector9-2000-09-26 | scrambled or shifted tags | dry-run | - | 0.0 | 20.9 |
| deepbananablackout-2010-07-31 | needs a listen | dry-run | - | 0.0 | 14.9 |
| explosionsinthesky-2004-10-13 | needs a listen | dry-run | - | 0.0 | 11.7 |
| greatamericantaxi-2009-11-03 | needs a listen | stale: reprocess first | - | 0.0 | 1.4 |
| karldensonstinyuniverse-2008-12-19 | needs a listen | dry-run | - | 0.0 | 10.6 |
| soulive-2003-08-07 | needs a listen | stale: reprocess first | - | 0.0 | 0.8 |
| elliottsmith-1997-05-06 | other | stale: reprocess first | - | 0.0 | 0.8 |
| garajmahal-2003-05-16 | other | dry-run | - | 1.0 | 7.6 |
| gratefuldead-1993-03-17 | other | dry-run | - | 0.0 | 10.6 |
| joerussosalmostdead-2019-06-15 | other | dry-run | - | 0.0 | 6.6 |
| moe-2004-10-31 | other | dry-run | - | 0.0 | 7.5 |
| themotet-2013-04-20 | other | dry-run | - | 0.0 | 13.3 |


## Strict surface (for Shawn)

Auto-applied edits with bar long, title or structure, or op switch_recording.

### opus

- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Something conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Rocky conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Sweat Loaf conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Ricky conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Graveyard conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Paranoid conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 100 Million People Dead conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Backass conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Julio Iglesias conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Psychedelic Jam conf=high: [taper-description] 3. Psych
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Pittsburgh to Lebanon conf=high: [taper-description] 4. Pittsburg to Lebanon
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 22 Going on 23 conf=high: [taper-description] 6. JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: I Saw an X-Ray of a Girl Passing Gas conf=high: [taper-description] 6. JIMI (cuts)
- littlefeat-1977-08-08 (partial tape) overrule bar=structure setlist evidence shows multiple sets but alignment found none conf=high: [taper-description] Unnumbered tracks are missing.; [taper-description] Tripe Face Boogie ends about halfway through.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: All That You Dream conf=high: [taper-description] All That You Dream
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Skin It Back conf=high: [taper-description] Skin It Back
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Walkin' All Night conf=high: [taper-description] Walkin' All Night
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Fat Man in the Bathtub conf=high: [taper-description] Fat Man In The Bathtub
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Red Streamliner conf=high: [taper-description] Red Streamliner
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Oh Atlanta conf=high: [taper-description] Oh Atlanta
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Spanish Moon conf=high: [taper-description] This was one of the shows where the tracks that became Waiting For Columbus were recorded.; [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Willin' conf=high: [taper-description] This was one of the shows where the tracks that became Waiting For Columbus were recorded.; [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Don't Bogart That Joint conf=high: [taper-description] This was one of the shows where the tracks that became Waiting For Columbus were recorded.; [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Rock and Roll Doctor conf=high: [taper-description] Rock & Roll Doctor
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Count Me In conf=high: [taper-description] 3. Track 3
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Well, Well conf=high: [taper-description] 8. Fork In The Road
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Get On With It conf=high: [taper-description] 9. Track 9
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Dream You Back conf=high: [taper-description] 11. Track 11
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Sunny Side Of The Mountain conf=high: [taper-description] 12. Track 12
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 01 STS92000.09.26.mp3 conf=high: [original-tag] 01 STS92000.09.26.flac | 24bit Flac | Squares & Cubes
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 02 STS92000.09.26.mp3 conf=high: [original-tag] 02 STS92000.09.26.flac | 24bit Flac | Itzamana
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 03 STS92000.09.26.mp3 conf=high: [original-tag] 03 STS92000.09.26.flac | 24bit Flac | Kamuy > Hubble >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 04 STS92000.09.26.mp3 conf=high: [original-tag] 04 STS92000.09.26.flac | 24bit Flac | TWELVE >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 05 STS92000.09.26.mp3 conf=high: [original-tag] 05 STS92000.09.26.flac | 24bit Flac | TWELVE >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 06 STS92000.09.26.mp3 conf=high: [original-tag] 06 STS92000.09.26.flac | 24bit Flac | Water Song >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 07 STS92000.09.26.mp3 conf=high: [original-tag] 07 STS92000.09.26.flac | 24bit Flac | Evasive Maneuvers >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 08 STS92000.09.26.mp3 conf=high: [original-tag] 08 STS92000.09.26.flac | 24bit Flac | EB >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 09 STS92000.09.26.mp3 conf=high: [original-tag] 09 STS92000.09.26.flac | 24bit Flac | EB
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 10 STS92000.09.26.mp3 conf=high: [original-tag] 10 STS92000.09.26.flac | 24bit Flac | Bossa Profundo

### sonnet

- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Something conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Rocky conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Sweat Loaf conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Ricky conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Graveyard conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Paranoid conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 100 Million People Dead conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Backass conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Julio Iglesias conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Psychedelic Jam conf=high: [taper-description] 3. Psych
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Pittsburgh to Lebanon conf=high: [taper-description] 4. Pittsburg to Lebanon
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 22 Going on 23 conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: I Saw an X-Ray of a Girl Passing Gas conf=high: [taper-description] JIMI (cuts)
- littlefeat-1977-08-08 (partial tape) overrule bar=structure setlist evidence shows multiple sets but alignment found none conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: All That You Dream conf=high: [taper-description] All That You Dream
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Skin It Back conf=high: [taper-description] Skin It Back
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Walkin' All Night conf=high: [taper-description] Walkin' All Night
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Fat Man in the Bathtub conf=high: [taper-description] Fat Man In The Bathtub
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Red Streamliner conf=high: [taper-description] Red Streamliner
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Oh Atlanta conf=high: [taper-description] Oh Atlanta
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Spanish Moon conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Willin' conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Don't Bogart That Joint conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Rock and Roll Doctor conf=high: [taper-description] Rock & Roll Doctor
- gratefuldead-1971-12-01 (partial tape with a better sibling) overrule bar=structure structure has 1 sets but jerrybase shows 2 conf=high: [taper-description] Set 2:
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=structure low-confidence structure alignment conf=high: [taper-description] Duration:  29min
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Casualty conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: 2 Hits & The Joint Turned Brown conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Left Me In A Hole conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Dave's New Instrumental conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Fingerprint conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Angel conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Follow Me Down To The Riverside conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Sharecropper's Son conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Don't You Lean On Me conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Troubled Mind conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: 20 Eyes conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Complicated conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: East Nashville Easter conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Peace Of Mind conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: King Ebeneezer conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)

## Auto-apply list (for the Opus reviewer)

Every edit of a verdict the gate would auto-apply.

### opus

- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Something conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Rocky conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Sweat Loaf conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Ricky conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Graveyard conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Paranoid conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 100 Million People Dead conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Backass conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Julio Iglesias conf=high: [taper-description] 1. Cherub
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Psychedelic Jam conf=high: [taper-description] 3. Psych
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Pittsburgh to Lebanon conf=high: [taper-description] 4. Pittsburg to Lebanon
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 22 Going on 23 conf=high: [taper-description] 6. JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: I Saw an X-Ray of a Girl Passing Gas conf=high: [taper-description] 6. JIMI (cuts)
- littlefeat-1977-08-08 (partial tape) overrule bar=structure setlist evidence shows multiple sets but alignment found none conf=high: [taper-description] Unnumbered tracks are missing.; [taper-description] Tripe Face Boogie ends about halfway through.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: All That You Dream conf=high: [taper-description] All That You Dream
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Skin It Back conf=high: [taper-description] Skin It Back
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Walkin' All Night conf=high: [taper-description] Walkin' All Night
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Fat Man in the Bathtub conf=high: [taper-description] Fat Man In The Bathtub
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Red Streamliner conf=high: [taper-description] Red Streamliner
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Oh Atlanta conf=high: [taper-description] Oh Atlanta
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Spanish Moon conf=high: [taper-description] This was one of the shows where the tracks that became Waiting For Columbus were recorded.; [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Willin' conf=high: [taper-description] This was one of the shows where the tracks that became Waiting For Columbus were recorded.; [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Don't Bogart That Joint conf=high: [taper-description] This was one of the shows where the tracks that became Waiting For Columbus were recorded.; [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Rock and Roll Doctor conf=high: [taper-description] Rock & Roll Doctor
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Count Me In conf=high: [taper-description] 3. Track 3
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Well, Well conf=high: [taper-description] 8. Fork In The Road
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Get On With It conf=high: [taper-description] 9. Track 9
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Dream You Back conf=high: [taper-description] 11. Track 11
- infamousstringdusters-2010-10-15 (untitled or untitled-echo) overrule bar=title research asserts unknown song: Sunny Side Of The Mountain conf=high: [taper-description] 12. Track 12
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 01 STS92000.09.26.mp3 conf=high: [original-tag] 01 STS92000.09.26.flac | 24bit Flac | Squares & Cubes
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 02 STS92000.09.26.mp3 conf=high: [original-tag] 02 STS92000.09.26.flac | 24bit Flac | Itzamana
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 03 STS92000.09.26.mp3 conf=high: [original-tag] 03 STS92000.09.26.flac | 24bit Flac | Kamuy > Hubble >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 04 STS92000.09.26.mp3 conf=high: [original-tag] 04 STS92000.09.26.flac | 24bit Flac | TWELVE >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 05 STS92000.09.26.mp3 conf=high: [original-tag] 05 STS92000.09.26.flac | 24bit Flac | TWELVE >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 06 STS92000.09.26.mp3 conf=high: [original-tag] 06 STS92000.09.26.flac | 24bit Flac | Water Song >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 07 STS92000.09.26.mp3 conf=high: [original-tag] 07 STS92000.09.26.flac | 24bit Flac | Evasive Maneuvers >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 08 STS92000.09.26.mp3 conf=high: [original-tag] 08 STS92000.09.26.flac | 24bit Flac | EB >
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 09 STS92000.09.26.mp3 conf=high: [original-tag] 09 STS92000.09.26.flac | 24bit Flac | EB
- soundtribesector9-2000-09-26 (scrambled or shifted tags) set_title bar=title 10 STS92000.09.26.mp3 conf=high: [original-tag] 10 STS92000.09.26.flac | 24bit Flac | Bossa Profundo
- joerussosalmostdead-2019-06-15 (other) overrule bar=medium briefing claims 2 sets but structure has 1 conf=high: [taper-description] One Set (1:10AM - 3:27AM):
- moe-2004-10-31 (other) overrule bar=medium briefing claims 2 sets but structure has 3 conf=high: [taper-description] Set 3: Timmy Tucker> The Road> Meat> The Pit, Spine Of A Dog> Buster; [taper-description] Encore: George> Godzilla
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Pass the Dutchie conf=high: [taper-description] Weed Medley-Pass The Dutchie-Legalize It - Mary Jane
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Legalize It conf=high: [taper-description] Weed Medley-Pass The Dutchie-Legalize It - Mary Jane
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Mary Jane conf=high: [taper-description] Weed Medley-Pass The Dutchie-Legalize It - Mary Jane
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Handcuffs conf=high: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Mothership Connection conf=high: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Tear the Roof Off The Sucker (Give Up The Funk) conf=high: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
- themotet-2013-04-20 (other) overrule bar=medium briefing claims 2 sets but structure has 1 conf=medium: [original-tag] motet2013-04-20FillmoreDenverMatrixT17EncoreBreak.flac | Flac | Encore Break

### sonnet

- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Something conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Rocky conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Sweat Loaf conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Ricky conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Graveyard conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Paranoid conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 100 Million People Dead conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Backass conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Julio Iglesias conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Psychedelic Jam conf=high: [taper-description] 3. Psych
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: Pittsburgh to Lebanon conf=high: [taper-description] 4. Pittsburg to Lebanon
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: 22 Going on 23 conf=high: [taper-description] JIMI (cuts)
- buttholesurfers-1987-11-07 (partial tape) overrule bar=title research asserts unknown song: I Saw an X-Ray of a Girl Passing Gas conf=high: [taper-description] JIMI (cuts)
- littlefeat-1977-08-08 (partial tape) overrule bar=structure setlist evidence shows multiple sets but alignment found none conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: All That You Dream conf=high: [taper-description] All That You Dream
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Skin It Back conf=high: [taper-description] Skin It Back
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Walkin' All Night conf=high: [taper-description] Walkin' All Night
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Fat Man in the Bathtub conf=high: [taper-description] Fat Man In The Bathtub
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Red Streamliner conf=high: [taper-description] Red Streamliner
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Oh Atlanta conf=high: [taper-description] Oh Atlanta
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Spanish Moon conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Willin' conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Don't Bogart That Joint conf=high: [taper-description] Unnumbered tracks are missing.
- littlefeat-1977-08-08 (partial tape) overrule bar=title research asserts unknown song: Rock and Roll Doctor conf=high: [taper-description] Rock & Roll Doctor
- gratefuldead-1971-12-01 (partial tape with a better sibling) overrule bar=structure structure has 1 sets but jerrybase shows 2 conf=high: [taper-description] Set 2:
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=structure low-confidence structure alignment conf=high: [taper-description] Duration:  29min
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Casualty conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: 2 Hits & The Joint Turned Brown conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Left Me In A Hole conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Dave's New Instrumental conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Fingerprint conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Angel conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Follow Me Down To The Riverside conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Sharecropper's Son conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Don't You Lean On Me conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Troubled Mind conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: 20 Eyes conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Complicated conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: East Nashville Easter conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: Peace Of Mind conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- yondermountainstringband-2009-07-11 (better sibling) overrule bar=title research asserts unknown song: King Ebeneezer conf=high: [taper-description] 30db (Jeff Austin and Brenden Bayliss)
- joerussosalmostdead-2019-06-15 (other) overrule bar=medium briefing claims 2 sets but structure has 1 conf=high: [taper-description] One Set (1:10AM - 3:27AM):
- moe-2004-10-31 (other) overrule bar=medium briefing claims 2 sets but structure has 3 conf=high: [taper-description] Set 3: Timmy Tucker> The Road> Meat> The Pit, Spine Of A Dog> Buster
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Pass the Dutchie conf=high: [taper-description] Weed Medley-Pass The Dutchie-Legalize It - Mary Jane
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Legalize It conf=high: [taper-description] Weed Medley-Pass The Dutchie-Legalize It - Mary Jane
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Mary Jane conf=high: [taper-description] Weed Medley-Pass The Dutchie-Legalize It - Mary Jane
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Handcuffs conf=high: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Mothership Connection conf=high: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
- themotet-2013-04-20 (other) overrule bar=medium briefing mentions unknown song: Tear the Roof Off The Sucker (Give Up The Funk) conf=high: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
- themotet-2013-04-20 (other) overrule bar=medium briefing claims 2 sets but structure has 1 conf=medium: [taper-description] PFunk Medley-Handcuffs-Mothership-Tear the roof off
