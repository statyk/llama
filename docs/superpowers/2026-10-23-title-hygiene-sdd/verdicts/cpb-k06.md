# cpb-k06 handback (class K, stratum delivered_changes, 15 shows, 150 tracks judged)
Rows: ~/.llama-harness/piece3/accept/handcheck/cpb-k06/rows.jsonl (15 rows). No commits, no writes under ~/.llama.

## Counts per verdict (tracks): right 114, right-partial 33, wrong 0, cant-tell 3
By path:
- C1 (5 tracks, all GSBG 2015-02-27): 5 right.
- C2 (9): 7 right (eits #7, GSBG15 #2 #6 #11, kungfu #7 #8, lettuce #2), 2 cant-tell (GSBG12 #9, kadlecik #9).
- D (2): 2 right (gybe #3 12.28.99, gd89-04-08 #21 Box Of Rain).
- +5 (134): 100 right, 33 right-partial, 1 cant-tell.
Show verdicts: all-right 12, cant-tell 3, shifted 0, some-wrong-not-shift 0.
(cant-tell shows: greenskybluegrass-2012-09-25, greenskybluegrass-2013-05-04, johnkadlecik-2017-10-31; all-right: the other 12.)

## Every cant-tell / non-right track
- greenskybluegrass-2012-09-25 #9 cant-tell: candidate "Cassidy > Cryptical Envelopment > The Other One > Cassidy" (flac tag + description, same taper) vs today's "...The Eleven..." (same item's mp3 tag, second taper's item, setlist.fm). Slight lean to The Eleven. This change REPLACES the better-supported title.
- johnkadlecik-2017-10-31 #9 cant-tell: candidate "Many Rivers to Cross" (flac tag + description) vs today's "Two Princes" (item's mp3 tag, and a second taper's flac+mp3 at the same slot, 443.55s vs 444.99s). Same pattern as above.
- greenskybluegrass-2013-05-04 #16 cant-tell: "Take Me Away" (mp3 tag, filename, setlist.fm) vs "Letters to Seymour" (description + flac tag). #11 right-partial: shipped "Jam" where description + flac tag say Broke Mountain Breakdown.
- right-partial (song right, junk left in title): GSBG13 all 20 other tracks ("Greensky Bluegrass - " artist prefix survives the strip); lotus-2008-02-07 all 12 (" H2" recorder suffix); gd1974-10-18 #24 ("Encore- U.S.Blues").
No shifted show. No strip damaged a real title (4:20 Polka, Moose's, etc. intact).

## Instructive examples
1. mp3-tag vs flac-tag conflicts (GSBG12 #9, kadlecik #9, GSBG13 #11/#16): the taper's mp3 derivatives carry different tags from the FLACs and description. C2 "sibling-format" recovery picks the FLAC/description side. In two of the four a second taper independently agrees with the mp3 side. A deterministic guard: skip C2 adoption when a tagged sibling item's title at the matched duration disagrees with the flac tag.
2. kungfuband-2013-02-13 #7/#8 and lettuce-2010-11-14 #2: C2 fixed real errors (mp3 tags shifted one early; "Speak E.Z." vs "Nyack"). Description + sibling durations (Belatone 658s = 403+244) decisive.
3. greenskybluegrass-2013-05-04: the +5 strip removes "d1t02-" but not the artist prefix, so every title ships "Greensky Bluegrass - X". Same shape in lotus (" H2"). Strip is under-reaching, not damaging.
4. leftoversalmon-1997-10-31: 43 timestamp strips all clean; "4:20 Polka" keeps its name; a stripped-timestamp equals the file duration, which is a free check.
5. gybe2002-01-22 #3 and gd89-04-08 #21 (D): description-position copies correct, confirmed by sibling durations (1205s vs 1190s; Box Of Rain 312s exact).

## Notes
- Judgement leaned on "taper presumed correct" only where no independent taper disagreed; where one did, cant-tell.
- Cache files read: md_GSBG2012-09-25.sbd.flac16.json, md_GSBG2013-05-04.json, md_OteilandFriends2017-10-31.CA14.Flac16.json, md_oteil2017-10-31.travitz.schoepsMK4v.flac16.json.
