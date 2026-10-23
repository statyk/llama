# cpb-k07 handback (class K, stratum delivered_changes, 15 shows, 136 tracks judged)
Rows: ~/.llama-harness/piece3/accept/handcheck/cpb-k07/rows.jsonl

## Counts
Verdicts: right 122, right-partial 13, wrong 1, cant-tell 0.
By path (verdict counts):
- +5 (119 tracks): right 108, right-partial 11, wrong 0
- C2 (10): right 9, right-partial 1
- C1 (5): right 5
- 4 (1): right-partial 1
- no path, changed (1): wrong 1 (lotus #12)
Show verdicts: all-right 14, some-wrong-not-shift 1 (lotus-2010-06-10). No shifted shows.

## Wrong / partial tracks
- lotus-2010-06-10 #12: WRONG. Candidate is the bare filename (unresolved). Today ships Sunrain (setlist), which is correct (setlist 12th item, 364s tail; description entry 13 blank). Not a silent wrong title: show goes newly-held (base clean -> cand newly-held). A regression in help terms, not an on-air risk.
- mymorningjacket-2006-06-04 #14 (path 4): right-partial. Ships "O"; real song is "O Is the One That Is Real" (taper wrote "O"; today shipped the full setlist title). Abbreviation regression.
- mymorningjacket-2008-06-20 #19-28 (+5): right-partial. M:SS strip worked but the "E: " encore prefix stayed ("E: Bermuda Highway" ... "E: One Big Holiday"). Song right; prefix would be read on air.
- perpetualgroove-2007-09-08 #12 (+5): right-partial, same "E: Only Always".
- newmastersounds-2009-06-06 #5 (C2): right-partial. Ships "MRG" where today's own tag has "Mark's Red Guitar". MRG is the taper/sibling/setlist abbreviation, so full name is lost.

## Instructive examples
1. newmastersounds-2011-06-04: six C1/C2 fixes; own tags were wrong (#1 Run the Gauntlet vs Hole In The Bag, #7 The Minx vs Fast Man / Miracles, #17 duplicate Baby Bouncer vs Nervous). Matrix tagged sibling durations match to 1 s on all six and the description agrees. Strong-win case.
2. mymorningjacket-2012-08-10 #1: raw tag Circuital duplicated #2; sibling-format gives At Dawn (filename, description, setlist agree). Fixes an adjacent duplicate.
3. newmastersounds-2009-06-06 #6: own tag Dusty Bin, candidate Dusty Groove (description and sibling at 355 s). Taper list overrides a wrong tag; right.
4. moe 2005-2008 (5 shows, 79 tracks): "M:SS) " prefix strips all clean, no real title damaged (32 Things, 3 AM-type cases absent). Trailing taper symbols (> * ^ + ~>) survive in titles; cosmetic.
5. MMJ 2008 / Perpetual Groove: the +5 strip handles "MM:SS - " but not an "E: " set/encore prefix after it.

## Patterns
- No shifts; the changed tracks were all tag-anchored or sibling-confirmed. The only failure was a placeholder filename (lotus), which holds rather than ships.
- Suggest a strip rule for a leading "E: " (or "Encore: ") after the timestamp strip; it accounts for 11 of 13 partials.
- Abbreviation tags kept under path 4 / C2 (O, MRG) lose the long title that other tiers had.
