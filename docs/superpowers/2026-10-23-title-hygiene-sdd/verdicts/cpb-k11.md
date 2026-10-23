# cpb-k11 handback (class K, stratum r16, 14 shows)

Rows: ~/.llama-harness/piece3/accept/handcheck/cpb-k11/rows.jsonl

All 14 packets: no `*` changed track, and no non-empty `path` except one S track (blindmelon-2008-06-24 track 3).
Every track is the file's own real tag (source `tags`), so I judged each shipped title and, in `note`, whether copying description entry N onto track N would have been right.

## Counts
- Tracks judged: 269 (all 14 shows). right 269, right-partial 0, wrong 0, cant-tell 0.
- Per path: S 1 (right); empty path (own tags) 268 (right).
- Show verdicts: all-right 14; shifted 0; some-wrong-not-shift 0; cant-tell 0.

## Wrong / cant-tell tracks
None.

## Shifted shows
None in the shipped titles. Positional description-copy (class D style) would have SHIFTED these, because the description lists entries the tape has no file for:
- discobiscuits-2006-02-04: 9 entries (incl. Banter) vs 8 tracks. Shifted by 1.
- soundtribesector9-2008-07-23: 16 entries (incl. Murph) vs 15 tracks. Shifted by 1.
- blindmelon-2008-06-24: 20 entries vs 19 tracks. Shifted from track 18 on.
- robynhitchcock-2009-03-21: 24 entries vs 23 tracks. Shifted from track 4 on, until the encore.
- gratefuldead-1980-05-10: 26 entries vs 24 tracks. Shifted by 2, then 1.
- maxcreek-2009-01-31: 19 entries vs 15 tracks. Badly shifted.
- moe-2009-01-30: 17 entries vs 16 tracks. Shifted at the end only.
Positional copy would have been right (entry count == track count, entry N == track N) for: assemblyofdust-2004-12-31 (21), furthur-2010-02-06 (20), moe-2009-02-27 (16), moe-2009-04-04 (15), mogwai-2006-04-25 (15), railroadearth-2005-08-20 (20), thedead-2009-05-02 (23).

## Instructive examples
1. discobiscuits-2006-02-04: the description starts with "01 Banter" and the tape has no banter file (starts at d1t02). Counts differ by exactly one. A length check against track count catches it. Tagged siblings and durations confirm the own tags are right (Sweating Bullets 468 vs 463 s, Shem-Rah Boo 1024 vs 1026 s).
2. maxcreek-2009-01-31: the taper wrote durations on the list (12:13 = 733 s, 3:01 = 181 s, 3:15 = 195 s). They confirm the own tags and also expose 4 list lines the files lack. Track 2 ships as "Tangled Up In Blue (12:13)", with a timestamp left in the title. Right song, cosmetic junk. (This is the `+5`-type residue, but the packet shows it as a plain tag, not a changed track.)
3. robynhitchcock-2009-03-21: the list has "04 talk" but the tape skips d1t04, so entry N lands on the wrong file from track 4 on. The own tags are right (Lizard follows Airscape).
4. thedead-2009-05-02: files are named dead2009-05-01, but the item id and setlist are 2009-05-02 Spectrum, and titles match the canonical order. Taper naming quirk, not a wrong show.
5. mogwai-2006-04-25 track 13: tag "Glsagow Megasnake" is a typo of "Glasgow Mega-Snake" (same song as description entry 13). Counted right.

## Pattern
Untouched own tags are safe on r16. The risk is only in a positional copy from the description, and the `entries == tracks` check separates the 7 safe lists from the 7 unsafe ones. Cosmetic residue left in titles by own tags: footnote marks (`*`, `^`), "->" or ">" markers, "(12:13)", stray "]" (railroadearth track 17), taper typos ("Alnouncements"). No song was misnamed.
