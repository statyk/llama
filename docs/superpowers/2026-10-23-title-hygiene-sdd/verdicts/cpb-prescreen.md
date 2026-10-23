# cpb-prescreen handback (Opus pre-screen, Checkpoint B hand check)

Inputs: 12 checkers' rows (157 packets, 1,472 track rows; 16 tracks were judged twice, counted once at the worse verdict). All 87 wrong and cant-tell rows were re-judged (3 wrong, 84 cant-tell), plus a calibration sample of 135 right rows. Read-only throughout; the only code run was `desc_list.read_numbered` on cached descriptions.

## Per-path bar (unique tracks filled or replaced in the hand check, after pre-screen)
| path | filled/replaced | wrong | cant-tell | wrong% | wrong% if cant-tell = wrong |
|---|---|---|---|---|---|
| C1 | 86 | 0 | 0 | 0.0 | 0.0 |
| C2 | 91 | 0 | 2 | 0.0 | **2.2** |
| D | 341 | 0 | 0 | 0.0 | 0.0 |
| 4 | 22 | 0 | 0 | 0.0 | 0.0 |
| S | 2 | 0 | 0 | 0.0 | 0.0 |
| S-deferred | 0 | - | - | - | - |
| +5 | 355 | 0 | 0 | 0.0 | 0.0 |
| changed-no-path | 3 | 0 | 0 | 0.0 | 0.0 |
| pooled | 900 | 0 | 2 | 0.0 | 0.22 |

- Right-partial: 63 tracks. 59 are cosmetic residue. 3 are abbreviations: SOTM (D), O (4), and MRG (C2, which replaced the full name "Mark's Red Guitar"). 1 is a segue partial: derektrucksband-2006-12-31 #5 "Greensleeves", where the file is Mahjoun > Greensleeves.
- No `+5` strip damaged a real title. `4:20 Polka` survived.
- 67 tracks went from a title to unresolved: holds, listed below, not wrong titles.
- **One unchanged wrong title ships on a newly cleared show, outside every path:** darkstarorchestra-2014-07-31 #3 (see regression 4).

## Shifted bar: PASS
- No checker row has `shifted` for the candidate.
- In the gate's untagged hand check, both shifted shows are held: billystrings-2023-06-10 and derektrucksband-2003-11-26 are needs-llm with every track unresolved.
- Every gate row judged some-wrong or cant-tell is also held (needs-llm) in cand-fresh: belafleck-2003-06-08, charliehunter-2007-03-21, deepbananablackout-2005-08-13, delmccoury-2008-05-24, dumpstaphunk-2009-07-11, eotoband-2007-10-09, fishbone-2011-02-27, furthur-2012-04-21, pnuma ×3, rosehilldrive-2008-12-31 (19 right D fills, held by its two `?` entries), soulive-2012-02-24, splitlip-2012-06-01, elliottsmith-1997-05-15.
- The candidate ships no shifted show.

## Slice-1 bar (newly held on the fresh-get view with S withdrawn or declined)
Good S copy (today's S titles right), excluding Q1:
1. **lotus-2010-06-10**: #12 Sunrain was right. A pure good-show hold.
2. **umphreysmcgee-2005-11-12**: #12 Wife Soup was right. But the tape's own tags #13-#17 are one track early: tape #13 ends at 2137 s, exactly where the sibling's Let Me Go Home ends, yet it is tagged "Wife Soup,". So the hold also stops silently wrong tags.
3. **steepcanyonrangers-2004-05-21**: not in the hand check. #31 Orange Blossom Special was right, but tags #4-#30 are shifted; the operator's overrides re-titled #4-#31. The hold stops a silently shifted show.

Bad S copy (a correct catch):
- buttholesurfers-1988-11-22: #19 "Comb" contradicts the description and the sibling ("Lou Reed"), and the tape's tags are one early throughout.
- railroadearth-2007-01-28: "My Sisters & Brothers (6:40)" sits on the track that is really 420.
- derektrucksband-2007-05-25: the operator's override says "44"; the S title would duplicate #11.
- signalpath-2005-06-09 and dumpstaphunk-2008-04-25: S shipped a literal `?`.

Cant-tell: soulive-2004-02-08 #10 and stringcheeseincident-2005-07-23 #12.

Q1, reported separately:
- darkstarorchestra-2004-04-24: set 1 good; sets 2-3 cant-tell.
- darkstarorchestra-2015-07-11: bad, shifted on #1-8 (Feedback omitted by setlist.fm).
- philleshandfriends-2007-10-20: bad, shifted from #10 (the 1878 s medley file).
- gratefuldead-1989-07-19: not hand-checked.

Already held in both arms, not newly held: robertrandolph-2005-05-29 (bad) and perpetualgroove-2009-06-04 (bad, `s1t07:`).

**Good-S holds: 3 under the strict reading (fails the "no more than 2" bar by one). 1 if a show whose tape tags are shifted does not count as good.** Operator to rule.

## Regressions
1. **umphreysmcgee-2005-11-12 #12:** slice 1 check 2 (adjacent duplicate against tape tag #13 "Wife Soup,"). Working as specified: a hold, and the neighbouring tag really is shifted.
2. **lotus-2010-06-10 #12:** S was deferred, so it declined with D, as slice 1 requires after a shift signature.
   - D's list is 01 intro … 12 Flower Sermon>. The intro file is not kept, and the bare `13` line reads as a disc label (the builder's documented `_EMPTY_NUMBERED` choice), so a 13-line list counted as 12 and matched the 12 kept files.
   - Track 12's entry, Flower Sermon, then duplicates track 11's tag, so check 2 fired.
   - Working as specified (a hold). Had the bare `13` counted as an empty entry, the list would have been inadmissible, S would have run gated, and Sunrain would have shipped.
3. **railroadearth-2007-01-28 #9:** not a correctness regression, because today's title was wrong; check 2 caught it. 420 was not kept because slice 4 needs a count-matched admissible list:
   - reader (i) fails: `Disc One (59:44)` does not match `taper._DISC_LABEL` (a trailing duration is not allowed), so the restart at 1 reads as non-contiguous;
   - reader (ii) drops `2. 420 (4:44)` and keeps `(One set)`.
   - A header-grammar gap; working as specified (a hold).
4. **darkstarorchestra-2014-07-31 #3: a silent wrong title on a cleared show (spec gap; the code follows the spec).**
   - The MP3 tags are one track early. C2 repairs #4-#20 and C1 fills #21. #3's reference is the description's `?`, so C2 cannot fire there.
   - #3 keeps "Duprees Diamond Blues". Its FLAC tag is "Greatest Story Ever Told" (cache), and it now duplicates #4 "Dupree's Diamond Blues".
   - The fresh base held this show only for #21; the candidate clears it and ships #3.
5. **soulive-2004-02-08 #10:** a chosen canonical, so this is D's job under slice 1. D declined on check 2 ("Do It Again" against #9's tag); check 3 disagrees too. Working as specified (a hold); today's title is cant-tell.

## C2-conflict rulings
- **greenskybluegrass-2012-09-25 #9:** cant-tell.
  - For the candidate: the same taper's description entry 9 and FLAC tag ("Cassidy > Cryptical Envelopment > The Other One > Cassidy").
  - Against it: the item's MP3 tag, plus the second taper's item (Bird Song -> Cassidy 753 s and The Eleven -> Cassidy 363 s) and that item's description, which is the canonical. The canonical is not setlist.fm, as the checker said.
- **johnkadlecik-2017-10-31 #9:** cant-tell. Description and FLAC say "Many Rivers to Cross"; the MP3 tag and a second taper (Travitz, 443.55 s against 444.99 s here) say "Two Princes". They are unrelated songs, so one taper mislabelled; the direction cannot be told.
- In both, C2 follows the spec and the "taper list presumed" principle. **If either is wrong, C2 is 1.1-2.2%, against the 2% bar.**
- **greenskybluegrass-2013-05-04 #11/#16 are not C2.** They are `+5` tracks. C2 cannot reach them: 21 files against a 22-entry description and a 17-item canonical.
  - The strip did no damage, so both are right-partial (the artist-name prefix remains).
  - The song identity is a pre-existing conflict. #11 "Jam" (MP3) against "Broke Mountain Breakdown" (description, FLAC). #16 "Take Me Away" (MP3, setlist.fm) against "Letters to Seymour" (description, FLAC).

## Calibration (seed 20261023, 10% per path, ceil; n=135)
- Exact verdict agreement: 134/135 (99.3%). The one difference: billystrings-2017-07-15 #11 is right-partial, not right, because the C1 FLAC tag keeps a "(1)" footnote.
- "Not wrong" agreement: 135/135. By path: +5 31/31, D 33/33, C1 9/9, C2 9/9, 4 3/3, S 1/1, changed 1/1, desc-only 48/48.
- One weak agree: ryanadams-2002-02-06 #31, a 57 s "Call Me On Your Way Back Home" (snippet length, no sibling; the per-disc counts match).
- Note: on the r16/readerii (desc-only) packets, checkers judged the unchanged own tag rather than a D copy. That does not matter, since those lists are not count-matched, and their notes say so.

## Findings for the operator to rule on
1. darkstarorchestra-2014-07-31 #3 (regression 4): should a C2-repaired run hold when an untouched neighbour duplicates a C2 title (check 2 applied to C), or when the delivered tag equals the next stem's lossless tag?
2. The two C2 conflicts above: they decide whether C2 meets the 2% bar.
3. The slice-1 good-S count: strict 3 against 1 (umphreys and steepcanyon carry shifted tape tags).
4. D cleaning gaps (all right-partial):
   - a leading `--> ` segue marker (deepbananablackout-2004-04-01, 8 tracks);
   - trailing `^` (`Boot!^`) and `$` with padding (`cobra          $`, mymorningjacket-2004-06-18);
   - a duration glued after `)`: `Playing In The Band(reprise)6:51` (darkstarorchestra-2011-04-15 #22).
5. `+5` gaps:
   - the `Greensky Bluegrass - ` artist prefix is kept on all 21 tracks of greensky-2013-05-04 and would be spoken on air;
   - a recorder suffix ` H2` is kept (lotus-2008-02-07, 12 tracks);
   - an `Encore- ` prefix is kept (gratefuldead-1974-10-18 #24);
   - `E: ` prefixes are kept (11 tracks; the spec keeps them by design);
   - zentricksters-2002-12-31 #19: the stem strip ran inside a parenthetical and left `Banks of the Ohio (actually )`, a cosmetic defect that `+5` itself created.
6. Abbreviations replacing fuller titles:
   - C2 swaps "Mark's Red Guitar" for the taper's "MRG" (newmastersounds-2009-06-06 #5);
   - slice 4 ships "O" where today's S title was "O Is the One That Is Real" (mymorningjacket-2006-06-04 #14).
7. C1 ships lossless-tag residue unchanged: "(1)" footnotes, and an "E." prefix (darkstarorchestra-2014-07-31 #21 `E. Black Muddy River`).
8. Reader nuances that cost holds:
   - a bare trailing `N` line is treated as a disc label (lotus);
   - a disc header carrying a duration is not recognised (railroadearth-2007-01-28), which loses its real 420.
9. On the positive side: four new holds stop silently wrong *tape tags* that today's code ships: umphreysmcgee-2005-11-12, steepcanyonrangers-2004-05-21, buttholesurfers-1988-11-22, and philleshandfriends-2007-10-20 (the last one's wrong titles are S's).

## Files
- `~/.llama-harness/piece3/accept/handcheck/prescreen/adjusted.jsonl`: 222 rows (87 re-judged, 135 calibration).
  sha256 `ecf3844414e6821a17c0360967009b9c4cc46cb6bafe3753fb00e529e439020f`
- `~/.llama-harness/piece3/accept/handcheck/prescreen/tally.json`
  sha256 `d14284571932c365cd36db8711ed87e0f5c85d5678029f102dc4785bb8aeed00`
