# Class C handback (agent C, 30 shows, 247 differing tracks)

Track verdicts: right 139, right-partial 28, wrong 14, cant-tell 66 (cant-tell = 56 no-op tracks where the other-format tag is blank, plus 10 bracketed banter labels at mountaingoats).
Show verdicts: fix-helps 19, fix-neutral 8, fix-hurts 3 (builttospill-1997-10-13, greenskybluegrass-2014-07-18, mountaingoats-2017-06-02). cant-tell 0.

Most instructive:
1. builttospill-1997-10-13: FLAC tags are description fragments SHIFTED one track ("start (0:25):" on Joyride, "pt1:", "Joyride (6:43):" on Temporarily Blind). All 14 candidates wrong. Durations match the description (403s = 6:43). Tell: titles ending in "(m:ss):" and the true title sitting in the filename.
2. radiators-1991-11-01 and meatpuppets-2013-07-13: the MP3 tags are real-looking but wrong stale titles ("No Skin Off My Back" on Mood To Move). Delivered would air silently wrong; FLAC + description agree. Rule: when delivered title is absent from description and other-format is present in it, prefer other-format.
3. soundtribesector9-2000-09-26: the setlist positional rung shipped "Hubble" on what is TWELVE (866s). FLAC tags (Kamuy > Hubble > / TWELVE > / TWELVE >) are right: durations sum to the sibling item's (Kamuy 585 + Hubble 1208 = 1801; TWELVE 866+209 = 1075 vs 1082).
4. greenskybluegrass-2014-07-18 (and 2015-02-27 t6, neworleanssuspects-2013-05-25): FLAC tag adds taper footnote markers ("Blue Night @", "Airmail Special ^", "Down On the Farm *") that the delivered tag lacks. Song is right, title gets junk.
5. mountaingoats-2017-06-02: FLAC tags for banter/applause are bracketed annotations "[...]" -- would ship brackets over clean delivered titles. Only track 45 (a real song) improves.

Patterns:
- Different-format tag differing "substantively" splits into: stale/wrong MP3 tags (FLAC right: radiators, meatpuppets, greensky 2015, bobbyleerodgers t4), versus FLAC tags that are shifted/garbled (builttospill). In 3 of 30 shows the FLAC side is wrong or noisier. In all 14 'wrong' tracks, 13 are builttospill.
- Placeholder/'?'/'tmp'/'Track N' delivered vs real FLAC title: always right when the FLAC title agrees with description/setlist (bobbyleerodgers, georgeporterjr, jeffaustinband, motherhips, soundtribesector9-2012, neworleanssuspects x2).
- 'other-blank' (FLAC untagged) is a no-op: infasmousstringdusters, jrad-2016, moontaxi, thegourds.
- Cosmetic only (neutral): apostrophes (furthur), Ms./Miss (lilsmokies), Lovelight vs Turn On Your Lovelight.

Suggested gates for the fix (all tested against these 30 shows):
- Skip when the other-format title is wrapped in [...] , ends in ":" or "(m:ss):", or equals delivered plus a trailing symbol-only marker (@ ^ * #). That removes all 'wrong'/'right-partial junk' cases except the credit-bracket suffix in robertwalters (which was right-partial and still an improvement over filename junk) and would not fire on any show judged fix-helps except to leave the markers out.
- Require other-format title to agree with description or canonical text at that position (builttospill fails this; all 19 fix-helps pass).
- Never apply the fix per-track in a show where two or more other-format titles look like shifted description lines.
