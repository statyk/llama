Agent A, class A: 30 shows, 243 track rows.
Show verdicts: strip-fixes-it 15, strip-not-enough 9, strip-would-damage 6, cant-tell 0.
Track verdicts: right 150, right-partial 4, wrong 89, cant-tell 0. (In the 89 "wrong" rows the candidate was empty or a placeholder, i.e. strip yields nothing.)

Strip-fixes-it (15): timestamp prefixes ("04:59) ", "09:07 - ", "03:48] "), filename stems (dcYYYYMMDD.NN., sNtNN, dNNtNN), set/disc markers (S2:, set1:, E:), ".wav", and NN- file numbers (blackberry, deadandco-12-31, ryanadams). Every stripped title was the right song.
Strip-not-enough (9): deepbananablackout, pnuma (bare numbers, no names anywhere), chrisduarte ("Disc 1, Track 10" is the taper's own placeholder), jeffaustin ("Track 11"), themainsqueeze (Track One..Eight), travelinmccourys ("track seventeen"), furthur-2013, littlefeat, meatpuppets (filename/date/place residue; nothing left after stripping, titles only via description position/overrides/FLAC tags).
Strip-would-damage (6): "4:20 Polka" x2 (leftoversalmon), "1 Samuel 15:23" (mountaingoats), "16 Military Wives" (decemberists), "8 Cylinders" x2 (yonder 2002 and 2006).

Instructive examples:
1. "4:20 Polka" matches a leading-timestamp shape; a naive timestamp strip makes it "Polka". Need a guard: only strip timestamps followed by ] ) or " - ", never "m:ss Word".
2. yonder 2006: canonical setlist already has "Cylinders" (the parser stripped "8 "), while the tape tag/flac sibling says "8 Cylinders". The number-prefix problem has already damaged one title upstream.
3. NN- prefix does not always equal position: ryanadams prefixes run 02..26 against positions 1..25 (intro file dropped); blackberry prefix 13 at position 12. A strip rule keyed on prefix==position would refuse most of these; stripping a joined 'NN-' prefix is still right here.
4. moe-2006 #19 has a pasted ".flac:<md5>" tail inside the title; needs a dedicated rule, not a timestamp rule. lotus has a trailing " H2" recorder tag as well as leading dNNtNN.
5. Placeholders that are the taper's own text (Track 11, Track One, track seventeen, Disc 1 Track 10) survive any strip and still must hold.

Patterns:
- The junk-shape census column has high precision for "strip it" when the pattern is: leading m:ss + ] or ), leading "sNtNN"/"dNNtNN"/"dcDATE.NN.", leading "N: " set marker, "set1:" prefix, ".wav". The only damaged cases were bare "N Word" patterns (spaced-num-prefix, joined-num-prefix on an actual title) and "4:20".
- Safe automatic rule candidate: strip only when the stripped title is nonempty, not a placeholder word (track/number words), and the removed prefix is not "digits + space + word" without a bracket/dash separator. spaced-num-prefix(=position) rows in this sample were 3 of 3 real titles (Mountain Goats, Decemberists, Yonder x2); do not auto-strip them.
- Candidates left with taper annotation residue (>, ->, *, @, (2)) are still the right song; separate cosmetic issue.
