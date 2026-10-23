# S2 handback (class S, part02): 32 shows, 203 setlist-rung tracks
Tracks: right 140, wrong 58, right-partial 2, cant-tell 3.
Shows: all-right 19, some-wrong-not-shift 7, shifted 5, cant-tell 1.

Shifted: mountaingoats-2008-10-21 (tracks 13-21, extra untitled jam), railroadearth-2007-01-28, robertrandolph...-2005-05-29, smashingpumpkins-2012-05-26, soulive-2004-02-08.
Not-shift wrong: pnuma-2005/2006 (title = track number), perpetualgroove-2009-06-04 ('s1t07:'), particle-2003-06-14 (t13 should be 'W >'), robertrandolph-2002-06-23 (setlist.fm list from wrong night, 5/7 wrong), rosehilldrive-2008-12-31 ('(mm:ss) NN-' residue), signalpath-2005-06-09 ('?').
Cant-tell: philleshandfriends-2007-10-20 (tail, possible Donor Rap off-by-one).

Instructive examples
1. railroadearth-2007-01-28: canonical starts with a junk '(One set)' item, so item N is the song for track N-1; the rung put 'My Sisters & Brothers (6:40)' on the 284s file whose raw tag and taper line say '420' (4:44).
2. robertrandolph-2005-05-29: taper left blank lines; canonical dropped them, so the copy for t03 is 'I need more love', which is track 4's own real tag (adjacent duplicate).
3. particle-2003-06-14: t13 gets 'Another Brick in the Wall, Part 2' right after track 12 with the same song; real tag 'W >' was demoted.
4. mountaingoats-2008-10-21: no tags, no description; only an outside review reveals a wrong-count shift. Nothing in the packet's own data catches it.
5. philleshandfriends-2014-09-21 (all-right): 0/18 raw tags equal canonical at the same position, but the one S track is right. Tag-vs-canonical check misfires here.

Pattern and check scorecard
- Whole-tape fills where tags/description exist: mostly right (short real titles like It, ML, RV, W7, 102%, 1 in 7 are the usual S tracks, all right).
- Failures come from (a) canonical list not 1:1 with tape (junk first item, split/merged lines, dropped blanks, extra jam), (b) junk text as a 'title' (digits, 's1t07:', '?', '(mm:ss) NN-'), (c) wrong-night setlist.fm.
- Adjacent duplicate title (fuzzy): caught particle, RRFB-2005, soulive-2004, RRE-2007; no false fires on my 19 good shows.
- Junk-title regex (all digits / equals position, sNtNN:, '?', leading '(mm:ss) NN-'): caught pnuma x2, perpetualgroove, rosehill, signalpath; no false fires.
- Raw tag disagrees with canonical at same position: catches 5 of the wrong shows but misfires on good shows (philleshandfriends-2014, soulive-2008, partly railroadearth-2007 tracks). Do not use alone.
- Candidate title absent from description text: catches robertrandolph-2002, fine as 'most titles miss' trigger; misfires on spelling variants if per-track.
- Short filler-length track given a song title: only weakly useful (166s Franklin's, 101s encore break); would fire on legitimate short songs.
- Not catchable by any packet-internal check: mountaingoats-2008 (no tags, no description).
