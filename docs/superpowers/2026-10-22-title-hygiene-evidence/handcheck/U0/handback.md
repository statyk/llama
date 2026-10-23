# U0 handback (class U, 13 shows, 269 tracks)

Show verdicts: all-right 10, shifted 1, some-wrong-not-shift 1, cant-tell 1.
Track verdicts: right 241, right-partial 5, wrong 23, cant-tell 0.

Wrong shows:
- billystrings-2023-06-10 (SHIFTED from track 13): two tagged siblings (Schoeps, mk4v) decisive. File 12 (652 s) is the single sibling file "I'm Still Here > Dealing Despair", so the list's Dealing Despair has no file and every title from 13 to 23 is one slot late (13 is really Gone a Long Time, 14-15 Run Down > Pretty Daughter, 16 All of Tomorrow, 17 Home ...). The shift resets at 24-25 because Thunder spans two files. A same-count coincidence: the sibling's song-per-file layout is the only check that catches it.
- belafleckandtheflecktones-2003-06-08 (some-wrong): list contains set-header lines ('"Set" 1:', '"Set" 2:') that are not songs, plus songs the list omits (Scratch and Sniff, Band Intros, Ovombo Summit). Wrong tracks 1, 2, 3, 6, 7; the d2 half is right. Filename number gaps (d1t06, d2t06, d2t09-10) mark the omitted banter/crowd files.
- charliehunter-2007-03-21 (cant-tell): the taper's own placeholders "track one".."track nine" (raw tags identical) are not titles; all 9 candidates wrong in the sense of not being songs.

Right shows, and what confirmed them:
- Written durations on the list (darkstarorchestra-2011-04-15: all 23 within 1 s; bandofheathens-2009-01-23: set totals 84.30 / 57.40 vs 84:23 / 57:36).
- Description disc/set segment sizes equal filename disc counts (charlieparr, dso 2004-08-31, 2005-05-30, 2005-11-19, 2005-06-04).
- Tagged sibling durations (dso 2005-06-04, dso 2012-07-21).
- Filenames embedding the titles (billystrings-2021-12-04).

Patterns / caveats for the gate design:
1. Disc-size vs set-size and written-duration checks never fired falsely on a good show and would have caught nothing wrong beyond the two real failures only via sibling alignment; the Bela Fleck failure is catchable by a "list line ends in ':' (header)" test and by filename gaps.
2. An adjacent-duplicate-title check WOULD wrongly fire on darkstarorchestra-2004-08-31 (Jam, Jam across a disc change, real).
3. Candidates need cleaning before use: trailing durations/segue marks (dso 2011-04-15, every line), "Filler: " prefix (dso 2005-06-04 t21, 2005-11-19 t17), "EN: "/"E: " encore prefixes, trailing "*" (billystrings-2021-12-04 t17-18), literal quote marks ("Dialogue"). Taper typos ship as-is (dso 2012-07-21: "My And My Uncle", "Women Enough").
4. Taper-flagged fillers (Filler: Scarlet / Terrapin) are right in song identity but not part of that night's show: marked right-partial.
5. Only 2 of 13 shows were wrong, and both are detectable by sibling alignment or header lines; a gate "no sibling disagrees AND no header-like lines AND no placeholder-word titles" would hold exactly those 3.
