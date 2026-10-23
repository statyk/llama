# S3 handback (class S, list-S-part03, 32 shows, 205 setlist-filled tracks)
Track verdicts: right 168, right-partial 3, wrong 31, cant-tell 3.
Show verdicts: all-right 22, shifted 1, some-wrong-not-shift 7, cant-tell 2.
Done: 32/32 rows in rows.jsonl.

Most instructive examples
1. stevekimockband-2000-03-31 (shifted): setlist.fm omits the Severe Tire Damage return and adds Memphis Soul Stew; counts still 19=19 because band-intro files were dropped. Tracks 9-14 land one late. Taper description is keyed to filenames (d2t03...), so a filename-keyed check would catch it.
2. soundtribesector9-2000-09-26 (wrong x2): counts equal only because Kamuy+Hubble merged in one file while an EB tail and a TWELVE tail are separate. The other-format (FLAC) tags had the truth (TWELVE at 4, EB at 9; shipped Hubble, Space).
3. u-melt-2008-08-29 and umphreysmcgee-2005-11-12: the filled track sits next to a neighbour whose OWN tag equals the copied title (adjacent duplicate). U-Melt track 2 raw tag was "415 ->" (real title 415, demoted), copy gave "Question Matters". UM 2005-11-12 track 12 is an unlisted jam before the tagged Wife Soup.
4. splitliprayfield-2012-06-01: description is bare "01".."18"; all 18 shipped titles are numbers, not songs.
5. themotet-2013-01-07: "1 + 1 + 1=3" shipped as "+ 1 + 1=3" (leading 1 eaten by track-number strip, then canonical copied the mangled form).

Pattern
- Of 32 shows, the large majority (about 20) fill only ONE track, where the raw tag is a numeric/short title (2x2, FF, 118, 20-12, EB, 102.4, Go): all right. Here the rung is just rescuing a demoted real tag; no risk.
- Whole-tape fills (all tracks setlist): STS9 2004-06-24, thecodetalkers, thegrassisdead, stevekimock x4, umphreys 2004-01-30, zero, yonder, splitlip, sts9 2000. Right when the taper's list or sibling durations confirm the count one-for-one; wrong when count equality is coincidental (merged files, extra stub files, bare-number list).
- Bad-fill signature: a copied title that is (a) a bare 1-2 digit number, (b) equal to an adjacent track's own title (fuzzy), (c) absent from the taper description, or (d) different from the raw/other-format tag at that position. These four checks catch every wrong fill I found (31 wrong tracks over 8 shows), plus fire on 2 uncertain shows (SCI 2005-07-23 track 12, STS9 2008-01-30 track 8) that I rated cant-tell.
- False-fire cost on shows I rated all-right: adjacent-duplicate check: 0 (Steep Canyon track 31 does duplicate track 30 but only because the tape's own tags are shifted, a real problem the hold would be right to surface). "Absent from description" check fires on a few spelling variants (Rock You vs Rock It, Eudemon vs untitled new song, Bossa/Bosso) so it needs fuzzy match and cannot be strict.
- Short filler with a song title: nothing seen; a filler-length check never was the failure here.
- The fill from setlist.fm is least trustworthy when taper and setlist.fm disagree (SKB 2000-04-01 track 6, Yonder track 29); taper presumption would reject those.
