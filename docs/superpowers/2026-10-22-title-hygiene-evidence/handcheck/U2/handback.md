U2 handback (class U, 13 shows, 214 tracks, rows in rows.jsonl)

show_verdict: all-right 9 (kellerwilliams, minutemen, motherhips, mymorningjacket, railroadearth x3, ratdog x2); some-wrong-not-shift 4 (pnuma x3, rosehilldrive); shifted 0; cant-tell 0.
Track verdicts: no shifted show found. Wrong = 29 (pnuma 29 tracks: all positional candidates are durations or bare numbers; rosehilldrive 2 "?" lines). right-partial = 21 (rosehilldrive 19 junk-prefixed lines whose song is correct, kellerwilliams t4, railroadearth-08-15 t3). Remainder right.

Instructive examples
- pnuma-2005-05-09 / 2005-08-26 / 2006-06-09: the "numbered list" holds no titles (mm:ss durations, "01.", "01"). The count match is coincidence; candidate is never a song. A check "list entry contains no letters / parses as mm:ss / equals its own index" catches all three and fires on none of the 9 good shows.
- rosehilldrive-2008-12-31: alignment exact (every file duration equals the duration written on its list line) but lines are "(05:12) 01-Sneak Out" and two are "?". Needs prefix strip; "?" must stay unresolved, not ship. Written-duration check confirms alignment.
- railroadearth-2004-08-15: tagged sibling has 22 tracks vs our 21; sibling's separate "mighty river intro jam" (268s) + Carrying Coal (425s) = our t03 (693s). Sibling duration alignment proves the 21=21 match is honest; t03 right-partial.
- ratdog-1995-08-09: two siblings agree to a few seconds on all 19 files; list splits Drums and Bass Solo like the flaschner sibling.
- ratdog-2007-08-12: taper typo "Birsdong" for Bird Song would ship; casing/typos need normalisation ("Mexicalli", '"stuff"').

Patterns
- Where the list contains real titles and disc/set headers agree with filename disc boundaries (motherhips, mmj, railroadearth x3, ratdog-2007), positional copy was right throughout. Where a tagged sibling existed (kw, rre-08-15, ratdog-95) it confirmed the alignment.
- Candidates frequently carry cosmetic junk (trailing ">", "$", "(Beatles cover)", "(1st time played)", lowercase, leading ".01  ", "(mm:ss) NN-"), so a title cleaner is needed even when alignment is right.
- Weak-evidence shows (minutemen: no sibling; judged by song-length plausibility and a review saying the posted list is correct, tape lacks its start) are rated right at moderate confidence.
- Non-song entries ("post show chatter" t21 rre-04-09, "encore break" rhd) are correctly placed but would air as titles.
