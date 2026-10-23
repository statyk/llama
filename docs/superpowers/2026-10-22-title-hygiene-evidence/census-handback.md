# Piece 3 title-hygiene census (read-only, current code 11dbffb)

**Ground state.** The tree was clean at 11dbffb, and `llama.__file__` resolves inside the main checkout. I did not reuse `piece2/accept3/cand.json`: it was built at a9016b5, which has the same package source (`git diff` touches no package code), but it stores no per-track titles. I replayed all 3,983 shows in-process instead: `compute_legs` from `llama.replay`, plus wrappers around gather's own helpers to capture what gather sees along the way. Nothing in the repo was edited.
- **Title overrides removed for the main view.** Each show was replayed with `overrides.titles` removed (excludes, includes, narration and structure overrides kept), so the census sees what a fresh `llama get` would ship. A second pass keeps the overrides, for "as the library has it".
- **Library:** 2,566 delivered + 220 voiced, 842 packaged, 334 held, 21 briefed.
- **Replay coverage:** every show replayed; none was unreplayable. 692 are needs-LLM for structure only, and their titles are still current-code titles. 3 are needs-LLM for `extract_setlist` and were replayed without that canonical setlist.
- **"Silent"** means the class applies and current code would raise no flag, so the show ships unheld.

## A. Placeholder titles that pass as resolved: 86 shows, 741 tracks
- **By state:** 45 delivered, 2 voiced, 25 packaged, 14 held. 72 are not held now; 35 would ship silently.
- **By shape (tracks):**
  - Leading timestamp plus text: 379, in 29 shows. Examples: moe-2007-09-29 `16:34) Waiting For the Punchline`, stantonmoore-2008-09-11 `06:58 - Who Took the Happiness Out?`.
  - Filename or date residue inside the title: 236, in 18 shows. Examples: deadandcompany-2017-06-17 `d&co2017.06.17.mg21.set01t01`, greenskybluegrass-2013-05-04 `Greensky Bluegrass - d2t07-In Control`.
  - Bare or zero-led number: 45. Mostly the `setlist` rung copying numbered lines, e.g. deepbananablackout-2005-08-13 `01.`.
  - A track number equal to the track's position, joined or spaced: 42. Example: ryanadams-2017-05-06 `20-To Be Without You`.
  - 2b vocabulary that a cross-source match protects: 15 (all held). Set/disc prefix: 7. `.wav` inside the title: 3.
  - Nearly all come from `tags`.
- **Not counted (likely real titles):** 378 shows, 418 tracks. Number-led titles (`20 Eyes`, `3 AM`, `1 in 7`, `420 Hornpipe`), date-shaped titles (`Feb 14`, `June 16th`, `09-15-00`) and self-titled songs (`Railroad Earth`). A test that has no position check (number = track position, or a leading zero) would hit these.
- **Existing rungs:** 2b covers only bare timestamps, the vocabulary and pure residue. It does not cover a timestamp or residue with real text after it. `starts_with_timestamp` exists, but only 2a's veto uses it.
- **Against the overnight tags:** only 24 of the 144 `placeholder-titles-shipped` shows are in A. Most of the rest are `tmp`/`Track NN` tapes that 2b now demotes, or real-but-wrong tags (`instrumental`, the stale MP3 `Jack Straw` on gratefuldead-1977-05-17). Those belong to class C, not A.

## A-reverse. Real short or numeric titles current code drops: 74 shows, 95 tracks
- **Cause:** only 2 are true 2b demotions (`2:22`, on both gracepotterandthenocturnals-2009-07-24 and -07-26). The other 93 are tags that fail `is_real_title`, which 2a then does not rescue. 2a needs a cross-source witness, and the selected recording's own description does not count as one.
- **Most common titles:** `J` ×19 (thenewdeal-2004-12-31), GYBE's `12-28-99`/`12.28.99` ×7, `VA`, `420`, `RV`, `3.2`, `I-55`, `M80`, `7-11`.
- **Confirmed and silent:** for 62 of the tracks, the operator later set the same title at that position by override. Only 8 tracks would ship silently. The rest are held, or were fixed by the operator.
- **Overnight tags:** 45 of the 96 "false-demotion" verdicts fall in this class. Most of the others (discobiscuits `42`, `405`, `118`) now ship correctly through 2a.
- **This contradicts the overnight label:** the cause is the `is_real_title` gate plus 2a's corroboration rule, not 2b.

## B. Unknown-song flags that echo an untitled tape: 266 shows, 3,539 flags
- 163 shows have these flags even with title overrides kept. 108 of the 266 have operator title overrides.
- **Flags by class:**
  - 2,194 plausibly echo the tape: the song is named by a witness and the tape has unresolved tracks.
  - 456 have no witness, on an untitled tape.
  - 608 have a witness but the tape is fully titled. That looks like vet's song matcher missing a spelling, not an echo.
  - 281 have no witness at all: possibly a genuine wrong-show signal.
- **Shows:** 145 have at least one echo flag; 89 have only echo flags.
- **Collapsing them** would change why a show is held, not whether it is held, for 39 shows (64 if `low-confidence structure alignment` is also allowed to remain). The hold stays on `unresolved track titles`.
- **Silent:** 0 by construction. Seeds: 174 of 197 overnight `flags-echo-untitled-tape` shows are in class B.

## C. Lossless and MP3 tags disagree on the same item (recovery did not fire)
269 shows have per-track disagreements. 49 of those are shows where recovery did fire; they are excluded below.
- **Substantive disagreement: 388 tracks in 119 shows.** 71 delivered, 4 voiced, 40 packaged, 4 held; 65 would ship silently.
  - When only one side has a witness, it is the lossless side 191 times and the MP3 side 5 times. Both sides have one in 183 cases.
  - Examples: motherhips-2010-10-31 track 4 ships `Jenny Thompson`, lossless says `State Fair Letdown`; tortoise-1996-05-25 track 9.
- **MP3 placeholder, lossless real title: 218 tracks in 18 shows** (furthur/DSO `tmp`). Recovery is blocked because `tmp` passes `is_real_title`, so the delivered side's title fraction is 1.0. 2b only files a note.
- **MP3 blank, lossless real: 103 tracks in 36 shows.** These fall to the `setlist` rung 19 times, `setlist-gap` 15, `sibling-align` 5, unresolved 64.
  - derektrucksband-2007-05-27 is an example. Track 1's MP3 tag is blank, so the `setlist` rung shipped `Sailing On` from setlist.fm, without a flag. The lossless tag is `Announcements/crowd`, and track 2 is also `Sailin On`.
- **Cosmetic or lossless-blank only:** 64 shows.
- **Existing rungs:** recovery is all-or-nothing behind the 0.5/0.9 gates, so none of these are covered. Seeds: 67 of 75.

## D. Description gives a numbered list with exactly one title per track: 85 shows, 698 unresolved tracks
- **By state:** 5 delivered, 49 packaged, 30 held. Silent: 0, because an unresolved track is always flagged.
- **Where the list comes from:** for 25 shows, `parse_setlist`; for 60, only a census-only extraction of numbered description lines, i.e. lists `parse_setlist` mis-counts.
- **Gain:** 570 tracks would get a usable (hygienic) title by position.
- **Accuracy of position:**
  - It agrees with the tape's own tags at the same position 748 of 904 times (82.7%).
  - It agrees with operator override titles 561 of 609 times (92.1%).
  - 28 shows have at least one disagreement, typically a shift after a missing item (jackiegreene-2009-10-10) or a filler track.
- **Why the whole-tape `setlist` rung did not fire:**
  - canonical setlist count differs from the track count: 78;
  - the canonical came from setlist.fm, not the description: 40;
  - `parse_setlist` count mismatch: 60;
  - rung conditions met but the positions were 2b-demoted: 5 (e.g. elliottsmith-1997-05-15).
- **Why `setlist-gap` cannot cover it:** 31 of the tapes are wholly untagged, so there are no anchors (by design).
- **Off by one** (not the class, but sizable): 80 shows, 609 unresolved tracks.
- **Seeds:** only 32 of the 120 `description-positional-titles` shows. That tag also covers lists that differ by 2 or more items (45) or by one (12), and 31 that are now resolved.

## Union and overlaps
646 shows across A, A-reverse, B, C and D. 477 are not held now; 192 would ship silently. Biggest overlaps: B∩C 35, B∩D 35, A-reverse∩D 23, C∩D 18.

## Surprise outside the four classes
The whole-tape `setlist` rung, which the `titles.py` comment calls "MEASURED DEAD", now fires on 128 shows and 741 tracks (93 of those shows from setlist.fm). 77 of those shows ship unflagged, and 8 show adjacent duplicate titles, a sign of a positional shift. Its titles are excluded from the coverage measure (tautological source), so it is effectively a second silent positional adopter.

## What I could not measure
- **Correctness of any candidate title:** that is the Sonnet hand-check.
- **B's echo test is a proxy:** a witness plus any unresolved track, not a per-position match.
- **Some A shapes and D's numbered-line list come from census-only regexes** (labelled as such). The rest use llama's own predicates.
- **The 3 `extract_setlist` needs-LLM shows** were judged without the canonical setlist the LLM would have produced.
- **setlist.fm** was seen only through the cache, via the canonical setlist and the corroboration vocabulary.
- **Voiced** is known only for delivered shows, from the station manifest's `dj_audio`.

## Files and re-run
- **Files** (all in `~/.llama-harness/piece3/census/`):
  - `dump.py` and `dump.jsonl`: the per-show replay dump, about 6 minutes with 6 jobs;
  - `census.py` and `census.json`: summary plus per-show rows per class (`A_ambiguous` and `D_offby1` included);
  - `packets/{A,A_rev,B,C,D}/`: 30 packets per class plus `index.json`, stratified by held / would-hold / silent, shape or category, and family.
- **Re-run:**
  ```
  cd ~/.llama-harness/piece3/census
  /Users/shawn/projects/llama/.venv/bin/python dump.py --jobs 6
  /Users/shawn/projects/llama/.venv/bin/python census.py
  ```
  `dump.py --slugs FILE` replays a subset.
