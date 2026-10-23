# cpb-k08 handback (class K, stratum delivered_changes, 15 shows, 127 tracks judged)
Rows: ~/.llama-harness/piece3/accept/handcheck/cpb-k08/rows.jsonl

## Counts
Track verdicts: right 101, right-partial 0, wrong 0, cant-tell 26.
Show verdicts: all-right 8, cant-tell 7 (shifted 0, some-wrong-not-shift 0 for the CANDIDATE).
Per path:
- +5 (strip): 75 tracks (ratdog-2008-04-11 20, rrfb-2004-07-25 22, ryanadams 21, sci-2005-07-24 12), all right. No real title damaged; only the "mm:ss) " / "NN dNtN " prefix removed.
- D (desc-position): 19 (ratdog-2007-08-12), all right.
- C2/C1 (lossless-tag repair): 8 tracks, all right (pfh-2014 #11,#16,#19; radiators #16; stuallen #3,#12).
- tags/unchanged-but-flagged: signalpath #3 right.
- unresolved placeholder (no path): 24 tracks, all cant-tell (candidate is a filename, not a title; show is held).

## Wrong or cant-tell tracks (candidate is an unresolved placeholder in every case)
- perpetualgroove-2009-06-04 #7: description line "s1t07:" blank. cant-tell.
- philleshandfriends-2007-10-20 #1-#18: all placeholders. Correct titles: #1-8 as today; #9 Viola Lee Blues > Cumberland (one 1878s medley file); #10 Plasma, #11 Unbroken Chain, #12 Dark Star, #13 Wharf Rat, #14 Dark Star, #15 Help on the Way > Slipknot, #16 Franklin's Tower, #17 Donor Rap, #18 Box of Rain.
- railroadearth-2007-01-28 #9: raw tag "420" (284s = 4:44 per description) demoted; correct is "420".
- rrfb-2005-05-29 #3, #7, #9: description entries blank; real title unknown.
- signalpath-2005-06-09 #8: description "?"; unknown.
- soulive-2004-02-08 #10: untagged 554s tail; unprovable (description vs tags off by one around "?").
- sci-2005-07-23 #12: untagged 486s tail after tagged Quinn; unprovable.

## Shifted shows
Candidate: none. TODAY'S delivered titles are shifted in philleshandfriends-2007-10-20 from #10 (see below); the candidate's hold fixes that.

## Instructive examples
1. philleshandfriends-2007-10-20 (delivered, clean today): 18 files = 18 setlist.fm items, so positional "setlist" copy shipped, but the five-part Viola/Cumberland medley is ONE 1878s file, so every title from #10 on is one late (shipped Cumberland for Plasma ... Box of Rain for nothing real). Sibling Shaunpeker durations prove it (Plasma 638s = our #10 642s). The candidate marks all 18 unresolved: clean -> needs-llm. Correct hold, but it also blanks #1-9 which were right (all-or-nothing). A real catch.
2. philleshandfriends-2014-09-21: MP3 tags swapped The Eleven / The Other One; FLAC (C2) tags plus the description repair them. Real win. Same for stuallen (Catfish John, Struggling Man) and radiators (Henri > Big Chief over a wrong Firewater).
3. railroadearth-2007-01-28: raw tag "420" is demoted, so the show goes newly-held and the right title is lost (today shipped a wrong duplicate). Candidate behaviour is the A_rev miss: "420"-style numeric tags still don't survive here.
4. rrfb-2005-05-29: three setlist-rung copies (I need more love, Jesus is Just Alright, War Pigs) duplicated titles already tagged on neighbouring tracks, so they were wrong today; unresolved is an improvement.
5. +5 strips never damaged a title. Misses: footnote marks (@ * ** # % ^ + ~) and trailing "->" stay in titles (cosmetic), and ryanadams #17 "17d2t7 Beautiful Sorta" (unchanged, outside +5) keeps its glued junk prefix.

## Notes
- Out-of-scope but seen: pfh-2014-09-21 unchanged #9 "Tuning" (206s = sibling "Jam") and #10 "Terrapin Station->" (831s, likely Lady With a Fan) look wrong in the raw tags; taper list omits Jam/Lady.
- Gate "tagged positions agree with description at same position": n/a for all D here (ratdog-2007 untagged, entry count 19 = file count after excluding t10 57s).
- Unfilled placeholders mean the candidate arm never ships a silent wrong title in this stratum.
