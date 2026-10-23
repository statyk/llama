# A_rev handback (30 shows, 32 demoted-tag tracks)

Track verdicts: right 24, right-partial 1, wrong 5, cant-tell 1.
Show verdicts: fix-helps 21, fix-neutral 4, fix-hurts 5, mixed 0, cant-tell 0.

Where keeping the demoted tag is right (the large majority): the tag is a real short title that the taper's description lists at the same position (3/4, 2:22, 42, M80, RV, 420, 3.2, 634-5789, 12.28.99, 1 in 7, 7/4, FF>, X >, 986 ft).

Instructive examples
1. robertwalters20thcongress-2002-09-20 and -2003-10-23: demoted tag "VA" is the second half of "Quantico, VA", split on the comma by the tagger; the tagger also dropped "X". Every tag after is shifted one place, so "VA" is wrong (the file is X or Bygones Be) and so are neighbouring tags that pass today.
2. godspeedyoublackemperor-2011-03-15: tag and description both say "12-28-99", but a sibling taper's durations show this 1349 s file is mostly Gathering Storm (1218 s). Candidate names only the tail. Taper agreement is not proof.
3. jackiegreene-2011-12-31: demoted tag "d206" is filename residue the taper left in; the real song is Believe. It is a different kind of thing from a short title.
4. zwan-2001-12-13: tags are a scrambled permutation of the description; the candidates "El" and "W.P" are also truncated forms of El-A-Noy and W.P.
5. moe-2008-01-26 and discobiscuits-2006-08-26: track was not unresolved; a better corroborated title ("Z0Z (Zed Nought Z)", "7-11 (Ending)") already shipped, the demoted tag is a typo "Z02" or carries footnote/segue residue "(5) >>>". Minor cosmetic regression.

Patterns and safe gates
- Wrong cases are exactly three types: (a) tag equal to the filename's own disc/track token (d206), (b) tag fragment of a comma-containing neighbour line (VA after Quantico), (c) scrambled-tag tapes. A gate "the demoted tag is not a substring of the filename" blocks (a); "the tag appears as a whole description line at the same position AND the neighbouring tracks' tags also agree with description positions" blocks (b) and (c) (in both VA shows and zwan the neighbours disagree) and would have passed all 24 right cases I looked at.
- GYBE 2011-03-15 (duration-contradicted taper tag) would not be caught by any text gate; only a sibling-duration check. One instance in 30.
- Several candidates (X >, FF>, 7-11 (3)>, 415 ->, 12 - 1979) carry segue arrows/footnote marks or a number prefix. Strip these on adoption (class A cleaning) so the fix does not ship residue.
- 7 packets show the track already carried a title from the setlist rung or tags, not unresolved (GYBE 2002 x2, gsbg-2015, soulive, u-melt, moe, db-2006, smashingpumpkins). There the fix replaces a title: it helped when the old one was wrong (u-melt, smashingpumpkins, GYBE alias 09-15-00 vs 12.28.99), was neutral when both were right, slightly hurt for moe. Restrict the fix to unresolved tracks.
