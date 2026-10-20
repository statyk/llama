# cpB-prescreen handback

prescreen: /Users/shawn/.llama-harness/cmp-B-all/prescreen.md
shasum -a 256: 913c852f19f495546492dbd85a8fbd7ec065ba0af5ee117c8d352f73c8844e12

## SUMMARY

1. **2b (511 rows): 217 flagged / 294 routine.** Residue 158 rows (12 shows) and recording-level 50 rows (3 shows) all hand-checked CORRECT. The flags that matter are 2 timestamp false positives and 7 re-adopted placeholders (items 4 and 5 below).
2. **2b check (a), "zero demoted pure-4-digit titles": FAILS as written.** ryanadams-2006-07-20 demotes `6040` on all 29 tracks. **`6040` is the 60% SBD / 40% AUD matrix ratio** (from the description: "SBD Source (60%)", "AUD Source (40&)"; it is also in the identifier `...Starland.6040.flac16` and the filenames `*_6040.mp3`). It is not a song, so the **demotion is correct.** The recording-level class has no 4-digit exemption in the spec; only residue does. Recommendation: accept, and read the check as covering the residue class only. The plan's literal grep `\d{4}` would also hit 150 identifier+date rows, so it is not a usable test.
3. **2b check (b), "zero demoted titles a sibling or setlist.fm lists": PASSES by construction, FAILS in spirit on 2 rows.** I checked all 288 distinct demoted tags in all 42 shows, not just 10: none is a cross-source parse item. But gracepotter 2009-07-24 and 2009-07-26 track 5 `2:22` is a real song: 5 of the 6 sibling descriptions on 07-26 list it, and both sources on 07-24 do. The exemption cannot see it because `parse_setlist`'s `_JUNK_TITLE` drops `2:22` as a bare duration.
4. **2b check (c), packaged exposure: PASSES.** The 5 expected shows (14 tracks) are there, plus gracepotterandthenocturnals-2009-07-26.
   - **gracepotter verdict:** this is 2b itself, and it is not a defect against the spec. Base: the tag `2:22` fails `is_real_title`. The whole-tape `setlist` rung fired (16 items = 16 files; the parser dropped `2:22`), so base shipped a **wrong** title, a duplicate `Big White Gate`. Cand: the timestamp arm demotes regardless of `is_real_title`, so the track goes to `unresolved` and the show is newly held.
   - The net effect is safe and removes a wrong shipped title. The class itself misfires on a real title: the operator sets it with `fix --set-title 5="2:22"`.
5. **NEW DEFECT CANDIDATE (owner: 2b): setlist-gap re-adopts demoted placeholders.**
   - Where: zachdeputy-2008-12-06 t1, t2, t3, t8, t14 (`Track 01`... -> same text) and infamousstringdusters-2010-10-15 t3, t9. That is 7 tracks on 2 held shows.
   - Cause: the canonical setlist is the selected recording's own description, which lists `Track 01`, `Track8`. The tracks re-ship as `setlist-gap`.
   - Both shows stay held only because another demoted track stayed unresolved. If every demoted track were gap-filled, junk would ship silently.
6. **2a (91 rows): 3 flagged / 88 routine.** Every core matches a whole item of a cross-source line; none is a substring of a line.
   - Pass checks: 0 cores without an alphanumeric, 0 junk-vetoed, 0 in metadata_norms (recomputed with jerrybase events omitted; no family artists here), `chosen` in sources 0.
   - **Shipped-title check: FAIL on 1, plus 2 cosmetic:** `M80,` (trailing comma; discobiscuits-2009-01-31, also on title_sources.txt), `E: 2x2` (leading encore marker; umphreysmcgee-2006-11-16), `42(1)` (footnote; discobiscuits-2004-12-29). No trailing `- @ ^ ~` on any 2a title.
7. **title_sources.txt: 31/31 OK**, each one `unresolved` in base. Library-wide, all 660 cand-vs-base title changes are accounted for:
   - 91 from 2a (unresolved -> tags);
   - 78 from 2c (tags -> tags);
   - 491 from 2b (470 tags -> unresolved, 1 setlist -> unresolved (gracepotter), 12 -> setlist-gap, 8 -> sibling-align);
   - 20 2b demotions are no-ops (base was already unresolved).
   - **No title that was not `unresolved` changed, except through 2b/2c.**
8. **2c (78 rows): 3 flagged (cosmetic) / 75 routine.** Every strip leaves a real title, and no numeric title is touched. The 3 flags: `The Cuckoo #`, `Cold Rain And Snow #`, `Walls Of Time #^` keep their footnote markers.
   - **All four Railroad Earth shows lose every research flag** (vet_flags empty in cand, and the base had 12-14 each) and also the low-confidence-alignment flag. They stay needs-LLM only because of "stored alignment llm".
   - **2c touched 0 sibling-format titles**: no title change in either arm has old_source sibling-format.
9. **closest_calls slice 2a (60 rows): 0 flagged.** **structure_changed (7): 7/7 correct.** The brief expected tnd2006-12-13; it is **not** on the list (no 2a there, base = cand). Its set_breaks move [10]->[12] in the 5c section is identical in both arms (stored LLM alignment vs replay), not a slice-2 effect. The list has thenewdeal-2006-07-19 instead (OL opens Set II; correct).
10. **format sibling tagged (36): 19 genuine, 17 inflated.** In the 17, the lossless sibling is itself 2b junk (`6040`, `Track 01`, identifier stems, `track one`).
11. **Newly held: base 4, cand 7.** The 4 are base drift and the same in both arms: aquariumrescueunit-2005-01-08, gd1971-04-29, gd1977-05-09, gd1985-06-24. The 3 new ones are all from 2b: blitzentrapper-2013-11-12 (`Trac3`), gracepotter-2009-07-26 (`2:22`), motherhips-2013-06-21 (`Track 16`, which the taper's list skips).
12. **One-word+date (operator's question): 0 rows** of the strict shape `<song word> <date>` (`Ripple 1970-09-20`, `Jam 12-31-99`); the P5 limitation does not fire in the library. The looser shape (leading words + date) has 150 rows on 9 shows. In every one the words are the artist/identifier, or a venue (`big meadow-7-3-10`). All are held, so **packaged exposure is 0**, and none is a song the show played.

