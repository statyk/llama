U1 handback (class U, 13 shows, 209 tracks judged)
Show verdicts: all-right 6 (dbb-2004-04-01, dtb-2006-12-31, geoff-achison, gybe, gomez, guster); shifted 1 (dtb-2003-11-26); some-wrong-not-shift 2 (dumpstaphunk, furthur); cant-tell 4 (dbb-2005, delmccoury, eoto, fishbone: lists carry no titles).
Track verdicts: see rows.jsonl (right, right-partial, wrong; 4 shows have every track wrong because the candidate is not a title).

Instructive examples
1. derektrucksband-2003-11-26: list line 3 "Feel So Bad Sahib>Maki>Sahib" spans two files, so everything from track 4 shifts +1 (To Know You lands on the Sahib medley file) until a dropped 111s crowd file (d2t03, list has a "Crowd" entry) shifts it back. Last two tracks come out right by accident. Tells: disc entry counts (9+5) vs file counts (10+4) and a gap in file numbering.
2. furthur-2012-04-21: prose list has an extra "Tuning" with no file, file order d01t06-08 differs from the performance, and a missing d03t03 shifts the end. Middle 9 tracks right, ends wrong. Three tagged siblings were decisive.
3. guster-2003-09-28: all 20 right, but only because the junk filter dropped d1t01 and a 109s Fa Fa tail (d2t08); count match is partly coincidence. Sibling alignment proves it.
4. gomez-2006-10-06: list lines carry written durations equal to file durations on all 24 files plus filename stems; strongest possible evidence, candidates only need trailing "6.32", "*", "@" stripped.
5. dbb-2005, delmccoury, eoto, fishbone: list entries are "01.", "Track 01 .... [20:47]" or "?" with no titles. Candidates are junk on every track.

Patterns
- Reject candidates with no alphabetic title (bare numbers, "?", "Track NN [mm:ss]"): catches 4 of 4 title-less lists and fires on none of the 6 all-right shows.
- Strip trailing durations, "*", "(GA)" initials, "Encore:", "E:" before use; right-songs otherwise.
- Wrong cases came from list lines not 1:1 with files (merged lines, a Tuning/Crowd line, a junk-dropped file). Cheap checks: gaps in filename numbering, per-disc entry counts vs file counts, a "Crowd"/"Tuning" entry, sibling duration alignment (sibling alignment would not false-fire on the 6 all-right shows).
- Dumpstaphunk track 6: taper says "In This World", siblings and setlist.fm say "Deeper" (marked cant-tell).
