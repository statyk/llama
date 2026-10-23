# U3 handback (class U, 11 shows, 158 tracks)
Track verdicts: right 119, right-partial 3, wrong 35, cant-tell 1.
Show verdicts: all-right 9, some-wrong-not-shift 2, shifted 0, cant-tell 0.

No shift found in any show. Per-disc/per-set list sizes matched per-disc file counts in every show where the list had disc structure (ryanadams, soulive-2005, whitedenim, zero, stevekimock).

Instructive cases:
- soulive-2012-02-24: the "numbered list" is the filename stems (01. soulive2012-02-24-d1t01). All 17 positional candidates are placeholders. A check "candidate looks like the file's own stem" blocks it.
- splitliprayfield-2012-06-01: the list is bare "01".."18". All 18 candidates wrong. A check "candidate is all digits" blocks it. Titles exist only in reviews.
- zero-1986-09-06: a tagged sibling's durations match file-for-file; confirms alignment. Candidates carry junk ("Baby Baby*", "E: Higher & Higher") that needs stripping.
- soundtribesector9-2004-06-24: positions right, but taper's "Galactivation" (track 4) vs setlist.fm/reviewer "Vibyl" is disputed (cant-tell); several candidates are generic "improv"/abbreviations (Trinoc, Wika, Rilly Wut?).
- ryanadams-2002-02-06: 32/32 with per-disc 12/10/10; the 57s and 89s tracks fit aborted songs, no shift despite short files.

Patterns:
- The real hazard in this batch is not positional shift but non-title list content (stems, digits). A "candidate is a real title" gate catches both wrong shows; it fires on none of the 9 good ones.
- Candidates from taper lists carry junk: trailing ">", "*", "E:" prefix, missing spaces around ">". Song is right but a cleaner is needed before shipping.
- Unnumbered plain lists (codetalkers) are right-by-count but have no independent confirmation: moderate confidence.
- A per-disc-list-size == per-disc-file-count check would pass all 9 good shows and is vacuous for the two bad ones.
