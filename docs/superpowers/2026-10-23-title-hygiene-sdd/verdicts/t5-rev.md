### Spec Compliance
- ✅ Spec compliant. All six interfaces exist with the brief's signatures (title_hygiene.py, new block after `judge`). Check 3 follows the brief's rules: filler/filler is neutral, a filler/song mismatch in either direction disagrees, otherwise `agrees` with no aliases, and a source outside `INDEPENDENT_SOURCES` is "skip". Written durations use a share denominator over all entries, multi-duration entries count as none (via `written_seconds`), and the test is strict `> max(15.0, 0.10*w)`. `agreement_share` is None with no canonical items or no song-like entries, and it is the only place aliases are passed (`agrees(e, it.title, aliases)`; `tape_disagreement`/`position_agreement` call `agrees` with none). `wholly_untagged` is `< MIN_ANCHORS` over song-like `is_real_title` tags not in `demoted`, which is the plan reading. All 14 brief tests are present. The `test_agreement_share` alias case uses Chinacat; the orchestrator has already ruled that.
- Protected names: the diff touches only `title_hygiene.py` and its test file. No protected name is edited. `MIN_ANCHORS`, `is_filler`, `is_real_title` and `GD_SHORTHAND` are imported read-only.
- ⚠️ Cannot verify from the diff:
  - That callers pass `tag_titles` from the tag layer (after slice 3 and before `resolve_titles`, with 2a/slice-4 tags excluded) and 0-based `demoted` positions. That is Tasks 6/9.
  - That callers pass `GD_SHORTHAND` only for `jerrybase.is_family_artist`. The parameter has no default, which forces the choice, which is good.
  - That callers convert the 0-based positions these functions return to 1-based track numbers for the notes. `judge` takes 1-based.

### Strengths
- `position_agreement` is factored out as the per-position judgement, so slice 4's neighbour test can share it without re-composing check 3 (title_hygiene.py `position_agreement`/`tape_disagreement`).
- Check 3 judges filler on the entry's cleaned text and, through `agrees`, compares cleaned copies on both sides. Probe: tags `Tuning (0:45)`, `Crowd [1:02]`, `Tuning*`, `E: Tuning` and `"Tuning"` against the entry `Tuning` all come out `neutral`, so a decorated filler tag does not create a false disagreement.
- `agreement_share` requires `aliases` with no default, so no caller can silently get or miss GD shorthand.
- Real-case fixtures are verbatim. I checked them read-only against `~/.llama/cache/md_gpn2009-07-26.akg463.16-44.flac.json`: the entries `intro`, `Some Kind of Ride`, `Joey` and `Tooth Brush and My Table >` match the description lines (taper numbers dropped), and the tags match show.json. Umphrey's `piano solo^` is verbatim. The tests cite the real slug (`gracepotterandthenocturnals-…`).
- The edge cases are covered: missing `duration_sec`, 2-of-5 vs 3-of-5 share, both sides of the tolerance (655/661 at 600; 135/136 at 120), and exactly-at-floor.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Check 2 compares a neighbour's RAW tag title, so a tag that carries a written time or footnote is not seen as a duplicate.** Location: title_hygiene.py `adjacent_duplicate` (`other = tracks[nb].title`).
   - Probe: `duplicate("Bertha", "Bertha (5:00)")` is False, as are `"Bertha [4:47]"` and `"Bertha (1)"`. On the cleaned text all three are True. Tags of this shape exist in the library (umphreysmcgee-2004-03-17's `Joel Piano Solo (02:05)`).
   - Why it matters: for D, check 3 (which cleans) catches the shift anyway. For S on a partly tagged tape, check 2 is the only shift detector, so a one-late fill beside such a tag would pass.
   - Status: this follows the brief and the spec literally. The spec says only check 3 "runs on cleaned copies" and is silent for check 2.
   - Fix: comparing `clean_one(tracks[nb].title).text` would change measured behaviour. Raise it with the operator as a spec question before Task 13's measurement, not as a quiet fix.
2. **`agreement_share` also drops `filler_marked` entries from the song-like denominator.** Location: title_hygiene.py `agreement_share`, the `songs = [...]` filter.
   - The spec's song-like means "not `is_filler`" only. The implementer reported this as a judgement call.
   - It is defensible: a `Filler:` entry names music that was not that night's, so a canonical should not be expected to contain it. But it is a reading of the spec, so the orchestrator should record it, or the gate should report it.
3. **The gracepotter test pins only the position, and only the filler/song arm.** Location: test_title_hygiene.py `test_check3_disagreement_declines`.
   - It asserts `tape_disagreement(...)[0] == 0`. The brief asks for "a hit naming the track". Pos 0 trips on `intro` (filler entry) against a song tag, never on song/song text.
   - Song/song disagreement is covered elsewhere (`test_check3_takes_no_aliases`, `test_filler_marked_entry_judged_on_its_text`).
   - Fix: assert the whole tuple `(0, "Some Kind of Ride", "intro")`.
4. **Test hygiene nit.** In test_title_hygiene.py `test_check2_finds_shift_signature`, `_tracks("Bertha", "Unresolved Thing")` builds a track that is overwritten on the next line. Build the two tracks directly.
5. **Import order nit.** In title_hygiene.py, `from llama.models import …` sits after `llama.placeholders`, which breaks the alphabetical order the rest of the block keeps. The repo has no linter configured, so this is cosmetic.

### Assessment
**Task quality:** Approved
**Reasoning:** The six functions do what the brief and spec say. Aliases are confined to `agreement_share`, and the tolerance, share and filler rules are correct and tested at their boundaries. The open items are a spec question (should check 2 clean the neighbour tag?) and test polish, not defects in this task.
