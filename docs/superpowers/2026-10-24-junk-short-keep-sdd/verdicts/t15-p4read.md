# t15-p4read: premise 4 (briefing reuse is safe), hand read of 10 voiced-severe shows

**Verdict: the premise FAILS on 10 of 10 shows.** Every stored briefing says that at least one restored file is absent, excluded, unaccounted for or not a track. The cause is structural, not a matter of LLM style. `run_brief` passes the whole `show.json`, including `excluded_files` (each restored file is listed there as `implausibly short`) and the `structure.conflicts` naming the unmatched setlist item. So the briefing LLM was told about the gap, and it dutifully wrote a caution about it. After restoration that caution is false. `briefing_guard` checks songs, dates and set counts, not claims about which files are present, so it will not catch any of these.

Method: for each show I read the library `briefing.md` (what reuse ships) beside the packet's restored files and candidate titles, and then the station `dj-notes.md` (already voiced, context only). The station share was mounted. I did not read `briefing.json` in full. A check confirmed it holds the same `cautions` content (for example, "implausibly short" appears in 4 of the 5 I checked; Soulive words it as "left out"). Everything was read-only; I wrote nothing under ~/.llama or the station share.

## Per show

### 1. gratefuldead-1968-10-12. Restored: gd68-10-12t05.mp3 (98 s, "Cryptical Envelopment"), gd68-10-12t10.mp3 (90 s, "Drums")
Briefing:
- Set 2: "note that the track tags in the show data list The Other One before Cryptical Envelopment, and that the drum passages are not present as separate tracks." This is false on both counts. t05 restores a Cryptical Envelopment before The Other One, and t10 restores a Drums track.
- Cautions: "The set order in the show data does not match the researched performance order. The track tags list The Other One before Cryptical Envelopment ... Do not assert the tag order on air as the played order." With t05 restored, the tags now read Cryptical > Other One > Cryptical, which matches research, so this caution is false (t05).
- Cautions: "Two drum passages are documented in the second set but are not present as tracks in this recording's file list." This is false for t10, a Drums track.
- Cautions: "Two files from this source (tracks 5 and 10 in the original numbering) were excluded from the show data as implausibly short, so the file list is not a complete account of everything on the tape." False (t05, t10).
- Smaller point: "The Other One track runs about seven minutes and Cryptical Envelopment about eight and a half." There are now two Cryptical tracks, so "Cryptical Envelopment" is ambiguous here.
- Runtime: "roughly 79–80 minutes" is a research figure. The stored tracks total 75.5 min, or 78.6 min with the restored files. That is closer, not contradicted.

dj-notes (voiced): "although the tracks on our tape may be labeled in a different order" is now false (t05). "There's no encore on this tape" is unaffected.

### 2. gratefuldead-1973-02-09. Restored: gd73-02-09Berthad1t09.mp3 (68 s, "Beer Barrel Polka"), gd73-02-09Berthad2t06.mp3 (18 s, "Dead battery")
Briefing:
- Set 1: "The tape's archival description notes a 'Beer Barrel Polka' tease ... The corresponding short file is not present in this track listing (see cautions)." False (d1t09).
- Set 1: "Thirteen tracks in the circulating source, opening with a 3:04 Promised Land and closing with an 18:44 Playin' In The Band." This track count is now wrong: set 1 has 14 tracks (d1t09).
- Cautions: "Structural alignment against the reference source also left 'Beer Barrel Polka' ... as unmatched entries, meaning the tease and the debut annotations are not represented as tracks in this listing." False for the tease (d1t09).
- Cautions: "Two files were excluded from this track listing as implausibly short (gd73-02-09Berthad1t09.mp3 ... and gd73-02-09Berthad2t06.mp3 ...). The Beer Barrel Polka tuning segment most likely sits in the first of these, so it may not be audible in the listing as presented." False (d1t09, d2t06).
- Not counted: "one listener review ... states the encore was not actually included in the files." This is an attributed review about a different defect; Casey Jones is present.

dj-notes: none.

### 3. gratefuldead-1974-02-24. Restored: GD_022474_D3_T02.mp3 (82 s, "Weather Report Suite Part I >")
Briefing:
- Set 2: "The official and Archive track listings spell the sequence out as Prelude > Part I > Let It Grow, one element more than this recording's tags show." False (D3_T02).
- Cautions: "One file was excluded from this recording as 'implausibly short': GD_022474_D3_T02 ... The official and Archive listings show a Part I between those two, so this source's Weather Report Suite sequence is one element shorter than the released version. Do not describe the suite as complete based on this track list." False (D3_T02).
- Not counted: "circulates incomplete ... 'I wish the rest of it was here in SBD'." This is about missing sets and is unrelated to D3_T02.

dj-notes: none ("from its Prelude through Let It Grow" makes no claim that anything is absent).

### 4. gratefuldead-1976-07-18. Restored: gd76-07-18d2t06.mp3 (80 s, "Supplication"), gd76-07-18d3t04.mp3 (58 s, "St. Stephen")
Briefing:
- Set 2: "Fifteen tracks as recorded". The track count is now wrong: set 2 has 17 tracks (d2t06, d3t04).
- Set 2: "Note that Supplication is absent from the supplied track list — see cautions." False (d2t06).
- Cautions: "The supplied track list omits Supplication. ... the show data's excluded-file list shows gd76-07-18d2t06.mp3 dropped as 'implausibly short,' which is where Supplication sits." False (d2t06).
- Cautions: "The supplied track list shows St. Stephen once, but every consulted source has it twice ... A second excluded file, gd76-07-18d3t04.mp3, also flagged 'implausibly short,' sits where the St. Stephen reprise belongs." False (d3t04).
- Cautions: "The show data's structure block lists conflicts on ... 'Supplication,' 'St. Stephen' ..." This describes the stored structure, which the restoration resolves (d2t06, d3t04).

dj-notes: none.

### 5. gratefuldead-1977-05-13. Restored: gd1977-05-13d2t06.mp3 (32 s, "Drums"), gd1977-05-13d3t01.mp3 (60 s, "Drums")
Briefing:
- Set 2: "A drums segment is referenced in the structural sources ... but no 'Drums' track appears in the track list; two files were excluded from the recording data as implausibly short, and they fall at the point in the sequence where a drums segment would sit." False (d2t06, d3t01).
- Set 2 list: "Estimated Prophet (9:46) into The Other One (16:43)". Drums now sits between these two, so the implied direct segue is false (d2t06, d3t01).
- Cautions: "No 'Drums' track appears in the recording ... Two files were dropped from the track list as implausibly short. Do not assert on air that a drums segment was or was not played, or how long it ran." False (d2t06, d3t01).
- Cautions: "the alignment record flags conflicts over 'Drums'". This describes the stored structure, now resolved.

dj-notes: none ("Estimated Prophet into The Other One" only implies a direct segue; no absence is stated).

### 6. gratefuldead-1977-11-06. Restored: gd77-11-06d3t05.mp3 (35 s, "Saint Stephen")
Briefing:
- Set 2: "Ten songs in the circulating recording, running roughly 83 minutes: ... Wharf Rat (11:44) and Truckin' (11:01). The official track listing places a Saint Stephen reprise of roughly 1:04 between Wharf Rat and Truckin'." The count is now wrong: 11 tracks (d3t05). The adding of 35 s to the runtime is negligible.
- Cautions: "A Saint Stephen reprise of roughly 1:04 belongs between Wharf Rat and Truckin' per the official track listing. It is absent from the track list here: the file gd77-11-06d3t05.mp3 was excluded from processing as 'implausibly short' ..." False (d3t05).

dj-notes (voiced): "the official release keeps a brief return of the Saint Stephen theme, which the tape we played tonight does not include." This is a voiced absence claim, now false (d3t05).

### 7. gratefuldead-1985-06-24. Restored: gd85-06-24d3t04.mp3 (40 s, "Cryptical Envelopment ->")
Briefing:
- Set 2 list: "... Cryptical Envelopment, Drums, Space, Comes A Time, The Other One, Wharf Rat, Around and Around and Good Lovin'." This now omits a track that is present (d3t04).
- Cautions: "The supplied show data omits it. The excluded file gd85-06-24d3t04.mp3 sits exactly at that position and was dropped as 'implausibly short,' which is consistent with the reprise being the missing item." False (d3t04).
- Still true: "A second file, gd85-06-24d3t08.mp3, was also excluded". d3t08 is not restored and is still absent from the candidate.

dj-notes (voiced): "the published setlists show a brief Cryptical reprise after The Other One ... and our files don't carry it as a separate track." This is a voiced absence claim, now false (d3t04).

### 8. gratefuldead-1985-09-07. Restored: gd85-09-07d3t03.mp3 (70 s, "Hey Jude"), gd85-09-07d3t04.mp3 (25 s, "Dear Mr. Fantasy")
Briefing:
- Set 2: "Per the track data, the set runs Shakedown Street, ... Space, Dear Mr. Fantasy, Truckin', ... The tracks total about 84 minutes." The list now omits two present tracks (d3t03, d3t04); the runtime becomes about 85.6 min, a minor change.
- Cautions: "dead.net, setlist.fm and jerrygarcia.com list a reprise of another song inserted between two passages of Dear Mr. Fantasy, but it is not a titled track in the recording data." False: d3t03 is the titled track "Hey Jude".
- Cautions: "Two short files between Dear Mr. Fantasy and Truckin' (d3t03, 70 seconds; d3t04, 25 seconds) were excluded from the track list as 'implausibly short.' The data does not identify what they contain, so the track list may not reflect the full sequence at that point." False (d3t03, d3t04).
- Cautions: "The data marks Dear Mr. Fantasy as segueing directly into Truckin'." False: the data now has Dear Mr. Fantasy > Hey Jude > Dear Mr. Fantasy > Truckin' (d3t03, d3t04).

dj-notes: none.

### 9. karldensonstinyuniverse-2000-11-01. Restored: kdtu2000-11-01d2t02.mp3 (75 s, "Inner Crisis cont'd")
Briefing:
- Set 2: "The opening track is tagged as running straight into the next one. It is followed by 'Fallin' > The Grunt intro'". False: it is now followed by "Inner Crisis cont'd" (d2t02).
- Cautions: "One 75-second file from disc 2 (track 2) was excluded as implausibly short. The structure data lists a 1:15 continuation of the set 2 opener and a truncated encore entry as unresolved conflicts. Small parts of the set 2 tracking may be uncertain." False for the continuation (d2t02).
- Runtime: "about 2 hours and 18 minutes" and set 2 at "about 74 minutes" both still hold. The stored total is 137.3 min, or 138.5 min with the restored file.

dj-notes: none ("going from Inner Crisis into Fallin'" states no absence).

### 10. soulive-2009-09-12. Restored: soulive2009-09-12t01.mp3 (90 s, "intro", spoken), soulive2009-09-12t14.mp3 (70 s, "soulive > lettuce morph")
Briefing:
- Set 1: "The main set covers tracks 1 through 14 of the recording." The numbering is now wrong: the main set is tracks 1–16 (t01, t14).
- Set 1: "The set opens with 'Up Right'". Track 1 is now the spoken "intro" (t01). This is a mild point.
- Cautions: "Two short files were left out of this track list: track 1 (90 seconds) and track 14 (70 seconds). Their content is not confirmed. They likely correspond to an opening intro and to the 'soulive > lettuce morph' segue ..." False (t01, t14).
- Cautions: "The structure data contains unresolved conflicts: ... 'intro' and 'lettuce morph'." This describes the stored structure, now resolved.
- Runtime: "The recording runs 130:49 overall." This still holds and is closer: the stored total is 128.1 min, or 130.8 min with the restored files.

dj-notes: none.

## Summary
- **Briefing absence claims: 10 of 10 shows.** 6 briefings name a restored file by filename (1973, 1974, 1976, 1977-11-06, 1985-06-24, and 1985-09-07 by its d3t03/d3t04 shorthand). All 10 refer to the exclusion: 9 call the files "implausibly short", and Soulive says "left out".
- **Track counts made wrong:** 1973 (set 1 "Thirteen"), 1976 (set 2 "Fifteen"), 1977-11-06 (set 2 "Ten"), Soulive ("tracks 1 through 14").
- **Sequence or segue claims made wrong:** 1968 (tag order), 1977-05-13 (Prophet into Other One), 1985-09-07 (DMF directly into Truckin'), KDTU (opener followed by Fallin').
- **No runtime claim becomes materially wrong.** Where a total is given, the restored files bring the data closer to it.
- **dj-notes (already voiced, context only):** 3 shows voice an absence claim that is now false: 1968 ("labeled in a different order"), 1977-11-06 ("the tape we played tonight does not include"), 1985-06-24 ("our files don't carry it as a separate track").
- **Implication:** in this sample, a show's restored files are exactly the files the stored briefing's input listed as excluded. So any reuse of a briefing for a show with a restored piece ships a stale caution about those files. A deterministic gate would be: refuse reuse when any of the new show's newly kept short files is in the stored `show.json`'s `excluded_files`. On this sample that gate refuses all 10, which means reuse would effectively never apply to a show with a restored piece.

**Overall: premise 4 fails on 10 of 10 shows.**
