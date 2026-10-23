# Checkpoint A pre-screen (Opus): title hygiene, piece 3

## Operator summary
- **B, 9 judged-wrong or inferred-wrong tracks.** 4 verdicts are sound and the error is real. 2 are sound with a caveat. 3 are unsound.
  - Sound, real S residual errors: deadandcompany-2016-07-15 t10, ericmcfadden-2005-10-06 t12, smashingpumpkins-2012-05-26 t12, karldenson-2001-03-08 t7. Karl Denson is a generic "Jam" where the taper wrote "Fried Grease": low severity.
  - Sound with a caveat:
    - godspeed-2011-03-15 t4: the checkers disagree. The D checker says right-partial, A_rev says wrong. By the brief's own segue rule it is right-partial. The spec already accepts it as a limitation.
    - rosehilldrive-2008-12-31 t7: right song, but it ships with the junk prefix `07-`. This is a real cosmetic D defect.
  - Unsound:
    - belafleck-2003-04-12 t9 (S): cant-tell. "Bela's Tune" is setlist.fm's name for the slot the taper calls "Natalie McMaster Tune". The two lists line up 1:1, so this is not a shift.
    - gratefuldead-1974-10-18 t24 (slice 5): string-inference artefact. It ships the right song.
    - mymorningjacket-2006-06-04 t14 (slice 4): string-inference artefact. It ships the right song.
  - Net: S has 4 real wrongs, plus 1 cant-tell. **Slices 4 and 5 have 0 real wrongs. D has 0 wrong songs** (1 right-partial, 1 cosmetic prefix).
- **R8, 13 adjacent-duplicate declines.**
  - 10 right: each stopped a wrong fill.
  - 1 false hold: darkstarorchestra-2004-08-31, a `Jam`/`Jam` split across a disc change. This was already accepted in the spec.
  - 2 lost a right fill, but the hold is warranted:
    - steepcanyonrangers-2004-05-21: the tape's tags are shifted one early from t4.
    - delmccouryband-2014-03-07: the tag and the list disagree on the order of t13/t14.
- **R9, 7 agreement declines.**
  - 0 stopped a wrong fill.
  - 5 changed nothing: every candidate had already been declined as `?`, `....` or a filename.
  - **2 are false holds on fills the A_rev checker judged right**: godspeed 2000-10-30 and 2000-10-31, where the taper's `12.28.99` meets setlist.fm's aliases for the same pieces.
- **R10, block size.** 3 declines: 2 right (billystrings, derektrucks-2003) and 1 false hold (railroadearth-2004-04-08, caused only by the encore fold).
- **R10, encore fold (all 52 classified, 15 inspected closely).**
  - Fold gives the right outcome on 44, no fold on 7, and 1 changes nothing.
  - **But 48 of the 52 are tagged tapes, where block size never runs.** In real behaviour only 3 shows change: the fold is right on DSO-2005-06-04 and RRE-2004-04-09, and no fold is right on RRE-2004-04-08.
  - Every "pass" in the 52 is the inert path (block count ≠ disc count). No reading ever passed a list because the sizes matched.
- **U4b.** Re-judged against the `all` arm.
  - railroadearth-2019-04-08 is **all-right**. All 21 D fills equal the filename's song; ISINMID is the taper's shorthand for Farewell to Isinglass; RV is a real title.
  - elliottsmith-1997-05-15 keeps 1 wrong title and 16 unresolved tracks. D was held falsely: tape agreement fired on a junk header-fragment tag, and that tag also ships as t1's title.
- **What could mislead a keep/drop ruling:**
  1. "R9 on right shows: 0" counts only the D/U classes. Two right lists (A_rev) are held, and the check caught nothing.
  2. "R10: 52 shows the fold changes" covers 48 shows where the check never runs.
  3. **The slice-1 bar (3 newly held good S shows) needs a closer look:**
     - gomez is held by a check-3 defect: a `???` slot-placeholder entry is counted as disagreeing with a sibling-align title. It should be neutral.
     - steepcanyonrangers's hold is beneficial: it surfaces 27 shifted tag titles.
     - Only lotus is a clean cost.
  4. The S row's 8.8% includes belafleck (cant-tell).
  5. "Judged" scoring takes the harshest verdict across classes, and "inferred" compares strings. Both make slices look worse than they are.
  6. A class no slice touches: tag layers shifted against the description or the FLAC originals. Examples: deadandcompany-2016-07-15, delivered with every MP3 tag one late; belafleck-2003-04-12; steepcanyonrangers. C's show-level ±1 decline also blocked a right C2 fix on delmccoury t1.

## A. U4 re-judged against the `all` arm (rows: `~/.llama-harness/piece3/handcheck/U4b/rows.jsonl`)
The old U4 rows judged the census reader, which kept description header lines as entries. The arm's `parse` reader drops them. Both shows change.

**railroadearth-2019-04-08: all-right.**
- The arm ships 21 `desc-position` fills. Each equals the song name in its own filename (files `02 Mighty River.mp3` … `21 Lordy Lordy.mp3`, `23 Chase a Rainbow.mp3`). The header (artist, venue, city, date) is gone.
- Today's S fills were setlist.fm spellings. The arm ships the taper's wording instead.
- Odd fills:
  - `ISINMID`: the taper's shorthand. setlist.fm has Farewell to Isinglass at the same slot, with every neighbour aligned. Judged right (same piece; odd on air).
  - `RV`: real. setlist.fm agrees.
  - `Lone Croft Farewell`: setlist.fm calls it Lonecroft Ramble, at the same slot. The taper is presumed right.

**elliottsmith-1997-05-15: some-wrong-not-shift. Held.**
- Track 1 ships its raw tag `15.97 - ej�s - portland, or` (source `tags`): a mangled copy of the date/venue header. Today ships the same; no slice touches it. The correct title is Division Day.
- Tracks 2-17 are `unresolved`, so the show stays held.
  - D declined at show level on tape agreement, because t1's junk tag counts as a real tag and disagrees with `division day`.
  - S declined under Q1 (wholly untagged).
- The 17-entry list is count-matched and positionally right. Durations show it: the short-song slots fit, with Some Song at 154 s, Big Decision at 140 s and Say Yes at 150 s.
- The tags of t1/t2 (`15.97 - …`, `45 am`) are the tagger mis-splitting `05.15.97` and `2:45 am`. The FLAC tags are identical.
- So D's decline is a false hold caused by a junk tag that passes as real.

## B. The 9 wrong tracks
1. **belafleck-2003-04-12 t9 `Bela's Tune` (S, setlist.fm, gated). Unsound; should be cant-tell.**
   - Kept tracks 1-15 align 1:1 with setlist.fm. The taper's disc 2 reads Dm 5/4, **Natalie McMaster Tune**, Sherpas, Moment So Close; setlist.fm's set 2 reads Sleeper, **Bela's Tune**, Sherpa, A Moment So Close.
   - So t9 (d2t02) is the same slot in both lists. These are two informal names for one piece, not a shift.
   - The checker's "offset" reading came from the tape's tags, which are wrong: t1-t3 are tagged `Massey Hall`/`Toronto`/`ON`, and the rest are shifted. About 10 wrong tag titles ship on this show, including `Throwdown at the Hoedown` twice (t3 from S, t5 from its tag). No slice touches them.
2. **deadandcompany-2016-07-15 t10 `Dark Star` (S). Sound. Real S residual.**
   - setlist.fm omits the opening Jam, so its item 10 lands one late.
   - The correct title is **St. Stephen**, not "unlisted jam" as the checker wrote. The FLAC original `set02t01.flac` is tagged `St. Stephen >` at 615 s.
   - The whole delivered show ships MP3 tags that are one late against the FLAC originals: t1 is `July 2016`, and so on.
   - C's show-level ±1 decline fired against setlist.fm, which is itself off by one.
3. **ericmcfadden-2005-10-06 t12 `II: ?` (S, chosen canonical). Sound. Real S residual.**
   - This is a check-1 gap: the roman-numeral set prefix `II:` is not removed before the `?`-only / no-alnum tests, so `II: ?` passes.
   - One-track fix: strip `^[IVX]+:\s*` (set marker) before the placeholder tests.
4. **godspeed-2011-03-15 t4 `12-28-99` (D). The cross-class verdicts conflict.**
   - D checker: right-partial. A_rev checker: wrong. The table takes "wrong beats right".
   - The DPA sibling has Gathering Storm at 1218 s and the 12-28-99 outro at 481 s. Our t04 + t05 equals the sibling's t04 + t05, so t4 is about 90% Gathering Storm and ends in the outro.
   - The brief's segue-pair rule makes this right-partial. The spec already accepts it ("not caught by any text check").
   - It is not the "12-28-99 is not a real title" artefact.
5. **gratefuldead-1974-10-18 t24 `Encore- U.S.Blues` (path +5, inferred). Unsound.**
   - It is the right song. Slice 5 deliberately keeps encore markers.
   - The inference failed because `agrees('Encore- U.S.Blues','U.S. Blues')` does not strip a dash-form `Encore-`.
   - Slice 5 improved it from today's `5:46] Encore- U.S.Blues`.
6. **karldenson-2001-03-08 t7 `Jam` (S, a sibling item's canonical). Sound. Low severity.**
   - The selected taper wrote `Satisfied* Fried Grease*` (a missing comma). The sibling item's list calls the same slot `Jam`.
   - The position is right; the name is generic. The raw tag is `? (13:53)`.
   - Separately, all tags on this show keep a trailing `(m:ss)`, which slice 5 does not strip.
7. **mymorningjacket-2006-06-04 t14 `O` (slice 4, inferred). Unsound.**
   - `O` is the taper's own shorthand for O Is the One That Is Real, like `OBH` on t7. Right song.
   - It reads as wrong because `agrees` compares cores under 3 letters by equality only.
   - It is a cosmetic downgrade: slice 4 runs before S-deferred, so it replaces today's full setlist.fm title. This follows the "taper wording ships" ruling.
8. **rosehilldrive-2008-12-31 t7 `07-8th Wonder` (D). Unsound as "wrong song", but a real cosmetic D defect.**
   - The wrong verdict came from S2, which judged today's `(08:10) 07-8th Wonder`. U2 judged right-partial.
   - D ships `07-8th Wonder` while every other entry lost its `NN-`. `parse_setlist` stripped those but not this one, so D's leader vote sees 1 of 21. The digit-follow guard (`8`) would block the cut anyway.
   - Any `NN-<digit>…` title keeps its track number.
9. **smashingpumpkins-2012-05-26 t12 `The Everlasting Gaze` (S, setlist.fm, gated). Sound. Real S residual.**
   - setlist.fm splits two combined lines, so items sit 2 late.
   - The duplicate is at t10, two positions away, so check 2 is blind to it.
   - This show also ships `- Zero`-style leading-dash residue on every tag, which slice 5 does not strip. The real show carries an operator override.

## C. R8 / R9 / R10

**R8, adjacent duplicate (13).**
- Right decline, stopping a wrong fill:
  - derektrucks-2007-05-25 (t10 is `44` Blues);
  - GD-1972-04-26 (OMSN already on t29);
  - jackiegreene-2009-10-10 (the tape lacks 1969, so the list shifts from t8);
  - lotus-2010-06-10 (the list counts the excluded intro file);
  - radiators-1992-04-29 (the list is one late from about t22);
  - railroadearth-2007-01-28 (t9 is `420`);
  - robertrandolph-2005-05-29;
  - soulive-2004-02-08;
  - stringcheese-2005-07-23 (Freeker is not kept, and d2t06 is unlisted);
  - umphreys-2005-11-12.
- False hold: DSO-2004-08-31 (`Jam` 81 s + `Jam` 174 s across d2/d3; U0 all-right).
- Right fill lost, hold warranted:
  - steepcanyon-2004-05-21: the tags are shifted one early from t4. Today this ships unheld with 27 wrong titles.
  - delmccoury-2014-03-07: the FLAC and MP3 tags put Smoking Gun on t13 (143 s, which fits Shuckin' the Corn), against the list. Separately, t1's MP3 tag `If You Don't Want Me` disagrees with the FLAC original, the list and the canonical (`Dry My Tears and Move On`). C2 would have fixed it, but C's show-level ±1 decline (on t13/t14) skipped the show.
- Lotus and stringcheese side effects:
  - D's decline withdraws a deferred S fill. On lotus that S fill (`Sunrain`) was right, which is the newly-held cost.
  - The S note text names D's candidate (`setlist adjacent duplicate (track 12 'Flower Sermon')`) although S's candidate was Sunrain. This is misleading in triage.

**R9, agreement (7).**
- Changed nothing, because every candidate was already declined per track or by hygiene: charliehunter-2004-05-22 (`?`), fishbone-2011-02-27 (all `?`), eoto-2007-10-09 (`....`), soulive-2012-02-24 (filename stems), dalewatson-2009-08-02 (only `??`; its canonical is another stage's set).
- False holds:
  - godspeed-2000-10-30: fill t3 `12.28.99`, A_rev fix-helps. Tape agreement also fired on `Beaten Down (with Mecca Normal)` vs `(Mecca Normal with GYBE)`.
  - godspeed-2000-10-31: fill t7 `12.28.99`, A_rev fix-helps.
  - Cause: setlist.fm's GY!BE aliases put the share below 0.5. This is the misfire the spec avoided for S, now reached by D.
- Quirk: `?` entries count as song-like non-matches. A `?`-heavy list fails agreement even against its own chosen canonical (charliehunter).

**R10, block size (3).** billystrings-2023-06-10 and derektrucks-2003-11-26 are right declines, made under either reading. railroadearth-2004-04-08 is a false hold under the fold only:
- Its sets are Set 1 = 7, Set 2 = 2 + 6, Encore = 1, and its discs hold 9 + 7.
- Folding the encore gives 7 / 9 against 9 / 7, so it declines.
- The description also carries `Disc 1:`/`Disc 2:` headers that would match exactly (9 / 7). The reader keyed on the set headers.

**Encore fold (52).** The right outcome is "pass" when the list agrees with the tags or the hand-check, else "decline".
- Fold right, list right (the no-fold reading misfires), 41 shows:
  - DSO-2001-12-15, DSO-2005-06-04, DSO-2007-11-21, DSO-2009-12-30;
  - furthur-2010-02-20;
  - GD 77-05-11, 77-05-18, 77-06-07, 77-10-29, 78-04-08, 79-02-17, 81-12-05, 82-04-19, 82-07-31, 82-09-21, 83-09-11, 83-10-17, 84-06-27, 87-07-08, 89-04-08;
  - guster ×4, moe ×3, motherhips-2011-02-04, mmj-2004-05-16, nrps-2009-08-09, perpetualgroove, phil-2006-07-14, radiators-1993-09-08;
  - RRE-2004-04-09, RRE-2007-03-31, RRE-2009-08-22;
  - ryanadams-2007-10-27, thedead-2009-05-02, toad-2011-04-07, ymsb-2005-02-04, ymsb-2006-01-28.
- Fold right, list shifted against the tags, fold declines, 3 shows:
  - GD-72-04-17: the list reorders from t13; Dark Star is the 1845 s file.
  - GD-74-07-21: the tape has a Tuning file the list lacks.
  - GD-74-07-31: 2 entries are garbled by a merged `Let It Grow Set 3: Seastones` line.
- No fold right, list right, fold misfires, 3 shows: bluestraveler-1993-04-09, GD-85-06-30, RRE-2004-04-08.
- No fold right, list shifted, no fold declines, 4 shows:
  - GD-74-10-20: the list has an extra `Other One Jam`; t27 is 102 s `Crowd`.
  - GD-89-07-09: t1 is Tuning.
  - GD-90-07-18: d2t01 is Tuning.
  - thegourds-2009-04-29: `Swine Flu Poem` is extra and `Thanks/Banter` is missing.
- No effect: belafleck-2003-06-08, which hygiene declines anyway.

I inspected 15 of the 52 closely: the 12 side-by-side tables, plus belafleck, DSO-2005-06-04 and RRE-2004-04-09 through their hand-checks. I classified the rest by list-vs-tag agreement at every position. Each had 0 disagreements, except DSO-2001-12-15, motherhips and ymsb-2006 with 1-2 each: abbreviations, an `Unknown` tag, and `I Am The Slime` vs `Jam`.
- **Only 4 are wholly untagged**, so the real effect is 3 shows: fold right ×2, no fold right ×1.
- Every pass is the inert path. Every decline compares set blocks with disc cuts, and those match only by accident. In the differing population, 3 of 6 fold declines and 41 of 46 no-fold declines hit right lists.

## D. Notes for the ruling
- **Slice-1 bar.** gomez-2008-07-05 is newly held because check 3 compares the slot-placeholder entry `???` with t7's `sibling-align` title `Very Strange` and counts it as a disagreement. Placeholder entries should be neutral in check 3, the same way they are per-track declines in check 1. Fix that and the bar is met. steepcanyon's hold is a benefit, and lotus is the one real cost.
- **Tag-layer shifts are the largest silent error seen in this pre-screen, and they sit outside every slice.**
  - deadco-2016-07-15 (delivered): the MP3 tags are one late against the FLAC originals.
  - belafleck-2003-04-12: the tags are +3, with header words as titles.
  - steepcanyon-2004-05-21: the tags are one early.
  - A per-stem MP3-vs-FLAC "shifted by one" signature, with no reference needed, would catch the deadco class.
- **Junk tags that pass as real titles** both ship and poison check 3: elliottsmith t1, belafleck t1-3.
- **Cosmetic residue slice 5 leaves:** trailing `(m:ss)` (karldenson), a leading `- ` (smashingpumpkins), and `NN-` before a digit (rosehilldrive).

Files:
- `/Users/shawn/.llama-harness/piece3/handcheck/U4b/rows.jsonl`
- scratch: `/Users/shawn/.llama-harness/piece3/scratch/prescreen/` (show.py, v.py, side.py, md.py, fold_eval.py, fold_eval.txt, fold52.txt)
