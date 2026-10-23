S0 handback: class S, list-S-part00, 32 shows
Track verdicts: {'right': 116, 'wrong': 46, 'right-partial': 4, 'cant-tell': 12}
Show verdicts: {'some-wrong-not-shift': 10, 'all-right': 19, 'shifted': 1, 'cant-tell': 2}

Instructive examples
1. billystrings-2023-06-10 (shifted): untagged tape, 13+12 canonical items vs 12+13 files; D1T12 holds two songs and two later songs span two files each, so every title from track 13 to 22 is off by one or two. Count equality is coincidental. Catchable: canonical set-1 count != disc-1 file count.
2. darkstarorchestra-2015-07-11: canonical omits the taper's 'Feedback >' so a 116s file is labelled Viola Lee Blues. Catchable: canonical count (11) != taper description count (12).
3. belafleckandtheflecktones-2003-06-08: description headers ('Set' 1:) copied as titles, 105s and 280s tracks given songs; 5 of 17 wrong, the rest right.
4. derektrucksband-2007-05-25 / -05-27 and buttholesurfers-1988-11-22: one wrong fill each, where a neighbouring raw tag or the taper's list names a different song (adjacent near-duplicate; intro-length track given a song).
5. charliehunter-2004-05-22 and dumpstaphunk-2008-04-25: titles '?' (taper's unknown marker); deepbananablackout-2005-08-13: '01.' list numbers. All wrong, trivially catchable by a non-title-token check.

Patterns
- About 15 of 32 shows are single-track fills where the only filled track has a short/numeric raw tag (9x9, 2x4, 51-7, 42, 405, 7-11, 35, 72, 44). The raw tag equals the copy in all but two of these (derektrucksband-2007-05-25 track 10, where raw tag '44' disagreed with canonical): these are safe, and a 'raw tag disagrees with canonical' check fires only on that one, correctly.
- Wrong fills come from: placeholders in the source list ('?', '01.', headers) in 4 shows; canonical vs taper count mismatches masked by coincidence (billystrings, dso-2015, dso-2004 uncertain, dtb-2007-05-27); setlist.fm items absent from taper list (buttholesurfers Comb).
- Worth gating: reject non-title tokens (^\d+\.?$, '?', quoted 'Set N:' headers); require the taper description item count to equal canonical count; flag a short (<~200s) track given a non-short song title.
- A 'description numbering vs file numbering' check would misfire on derektrucksband-2004-11-20 (an all-right show with blanks and a misnumbered 'crowd'); sibling-item durations were the only decisive evidence there.
- cant-tell: charliehunter-2001-12-08 track 9 (taper: untitled), darkstarorchestra-2004-04-24 tracks 14,20-22, darkstarorchestra-2015-07-11 tracks 2-8.
