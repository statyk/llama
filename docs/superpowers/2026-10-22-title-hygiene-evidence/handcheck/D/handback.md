# Agent D handback (Class D, 30 shows)
Rows: ~/.llama-harness/piece3/handcheck/D/rows.jsonl (30 rows, 319 unresolved-track verdicts).
Track verdicts: right 220, wrong 71, cant-tell 20, right-partial 8.
Show verdicts: all-right 17, some-wrong-not-shift 9, shifted 4 (furthur-2012-04-21, gracepotter-2009-07-26, gratefuldead-1983-09-04, zwan-2001-12-13).

Instructive examples
1. Placeholder descriptions (9 shows: charliehunter, fishbone "?", infamousstringdusters "Track N", zachdeputy "Track NN", pnuma timestamps, soulive-2012 filename stems, dalewatson/ratdog-2000 single "??"/"???"): the description line is not a title, so the copy is wrong on every such track. Needs a candidate-shape check, NOT the tagged-agreement gate (these shows' tagged tracks agree, gate passes, wrong titles ship).
2. gracepotter-2009-07-26: description has an extra line ("intro", tape starts d1t02) so positions are offset; track 5 candidate duplicates track 4's tag. Gate catches it (tagged tracks 1-4 disagree).
3. gratefuldead-1983-09-04: sole unresolved track 22 gets footnote text "One More Labor Day Night"; real is U.S. Blues because tags 13-21 are shifted. Gate catches it.
4. zwan-2001-12-13: scrambled tags vs description; candidates duplicate titles tagged elsewhere. Gate catches it.
5. furthur-2012-04-21: run-on one-line description, untagged, files missing numbers (d01t01, d03t03) and out of order: positions untrustworthy but gate is vacuous and would NOT catch it. Catch via non-contiguous tNN numbering or non-numbered single-line description.

Gate "every tagged track agrees with the line at the same position, none disagree":
- Blocks all 3 real shifted cases with tags (gracepotter, GD1983, zwan) and blocks darkstar-2014-07-31 whose fill (track 21) is right but whose 18 shipped tags are shifted (arguably correct to hold).
- Does NOT block any placeholder case, nor furthur-2012 (untagged, vacuous).
- Could falsely fire on a good show only if string comparison is strict: umphreys-2004-03-17 (tag "Joel Piano Solo (02:05)" vs line "piano solo^", quoted "Jimmy Stewart") needs normalization. Otherwise no good show blocked.
- Wholly untagged shows (darkstar x3, guster, minutemen, ratdog-1995, railroadearth, soulive-2005, whitedenim, keller) pass vacuously and were all right (railroadearth t17 cant-tell, disputed by one reviewer), so vacuous pass is fine only when lines are real titles 1:1 with files.

Patterns
- Good fills need: real-title lines, line count == file count, durations fitting. Candidate strings often carry junk to strip: trailing tab+duration (darkstar-2011), "(GA)/(DH)" initials (geoffachison), "(X cover)" (keller), "->"/">" markers, footnote symbols (jrad), "Encore:" prefix, "Filler:" prefix.
- Taper "?"/"??"/"???", "Track N", timestamps, filename stems: reject candidates matching these.
- Compare candidate with titles already on other tracks: duplicates flagged all shifted/scrambled cases.
