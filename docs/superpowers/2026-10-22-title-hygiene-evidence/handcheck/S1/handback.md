S1 handback (class S, 32 shows, rows.jsonl complete)
Track verdicts (setlist-rung tracks): right 87, wrong 34, cant-tell 11, right-partial 0.
Show verdicts: all-right 25, some-wrong-not-shift 4, shifted 2, cant-tell 1 (kungfuband-2010-07-22: no evidence at all).

Most instructive:
- joerussosalmostdead-2023-10-13: all 15 wrong, shifted. Filenames carry titles; canonical list lacks two Jams and has two annotation lines ("w/Eric Johnson...", "Fruit Bats opened") as items, so 15=15.
- leftoversalmon-1996-03-16: localised shift of tracks 18-22. A real 63s song (Jackknife) was dropped as "implausibly short" while the canonical lacks the taper's "E: talk"; errors cancel. A sibling item with titles proved it.
- loslobosmusic-2024-06-14: one wrong (t3 Rattlesnake Shake, file is Maricela); the other 17 right. Filename text exposes it.
- ericmcfadden-2005-10-06: 11 shipped titles are literal "?".
- gratefuldead-1972-04-26: t30 duplicates t29's own tag (One More Saturday Night).
- karldensonstinyuniverse-2001-03-08: t7 "Jam" but the taper's list (comma missing) names Fried Grease (moderate).

Checks, with false-fire cost on the 25 all-right shows:
- Candidate has no letters/digits or is a "?" form: catches ericmcfadden; 0 false fires.
- Adjacent duplicate title: catches gd1972-04-26 t30; fires on 2 other shows for reasons unrelated to the rung (jacobfred tag junk, g-love tag titles); not on rung tracks of good shows.
- Filename contains a canonical title for a different position (or the copied title absent from a titled filename): catches joerusso (15), loslobos (1); 0 false fires (needs title normalization like Carabina 30-30). Only applies where filenames carry titles.
- Raw tag disagreeing with canonical at same position: WRONGLY fires on kellerwilliams, greatamericantaxi, greensky-2015 (spelled-out 33443), the three gybe shows (12-28-99 vs 09-15-00 alias), elliottsmith-1997: about 8 good shows. Do not use as a hold.
- Excluded "implausibly short" file while counts match: catches leftoversalmon-1996; wrongly fires on lotus-2010, loslobos-2024 (excluded intros).
- Short track (<~120s) with a song title: catches leftoversalmon t22 (95s); would fire on legitimate short songs (heavy false-fire risk, e.g. 130s tracks 420, Chuck Dub).
- Canonical item that is an annotation (starts "w/", contains "opened"/"Set:"): catches joerusso; elliottsmith-style okay.

Patterns: the rung is right in the typical case (exactly one gap in an otherwise tagged tape, neighbours agree: ~all single-position fills were right). Failures concentrate in fully untagged tapes (rung fills every track) and where canonical source (setlist.fm/LMA review) has extra annotation items or lacks an item the tape has. Fully untagged + no description (kungfu 2010) is unverifiable.
