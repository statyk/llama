### Spec Compliance
- ✅ Spec compliant. The task matches the brief and the plan's readings.
  - **New files only.** Two files are new and nothing else is touched. No protected name is edited: `LOSSLESS_TITLE_FORMATS`, `hygienic_title`, `fuzzy_norm_title`, `MIN_ANCHORS` and `filter_files` are only imported (lossless_titles.py:36-49). `_RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE` appear only in the module docstring.
  - **Signature and fields.** `LosslessResult` and the `apply_lossless` signature match the brief exactly (lossless_titles.py:62-71, 113-116).
  - **Every required test is present:** the 12 named in the brief, plus 15 more. The two real-case fixtures (`_RADS_DESC` and file titles, `_DTB_DESC` and file titles) match `~/.llama/cache/md_rads1991-11-01.dantepper.flac.json` and `md_dtb2007-05-27..flac.json`. I checked both read-only.
  - **Named risk: the mirror of `_recover_format_titles`.** I compared against stages/gather.py:380-396.
    - `_lossless_map` (lossless_titles.py:98-110) walks `LOSSLESS_TITLE_FORMATS` in order and skips `ordering["format"]`.
    - It calls `filter_files(files, want_format=fmt)` and `sibling_format_titles(recovery_basis, other)`, the same shape recovery uses. That gives the same stem bijection on the basis and the same `clean_tag_titles` of the lossless side (titles.py:269-287).
    - The only difference is the threshold, `> 0` instead of `>= 0.9`, which is the plan's reading.
    - A re-admitted file reads `mapped.get(name) -> None` and is skipped as a vote (lossless_titles.py:132, 159-160).
  - **C1 reading.** The per-target (a)/(b) check, (c) computed only when needed, and all-or-nothing on the show match the plan's reading R17 (lossless_titles.py:173-195).
  - **C2.** It uses one reference, (a) before (b) (:140), and requires that the norms differ, the lossless tag agrees and the delivered tag disagrees (:197-203).
  - **Skip.** Two or more ±1-not-own matches against the one reference (:143-150).
  - **Vetoes.** :88-95.
  - **Notes.** Every changed track gets the brief's fixed string (:205-207).
  - **Accepted ruling.** The orchestrator's ruling (lossless tag must pass `hygienic_title` for C2 too) is implemented through `eligible()` (:152-155).
- ⚠️ Cannot verify from the diff:
  - **Whether "Whole-text containment is never used" (spec, slice 3, C2) is met.** Under one reading it is not. `agrees` calls `loosely_same_title` unmodified, as the Global Constraints require, and `loosely_same_title` contains a containment arm (structure.py, `na in nb or nb in na`).
    - Probe: delivered `Drums`, lossless `Drums > Space`, list entry `Space` gives **C2**, shipping `Drums > Space`. The test `test_c2_needs_the_delivered_tag_to_disagree` relies on this containment explicitly.
    - The spec phrase most plausibly means "never match against the whole description text" (the `contains_sequence` sense), and under that reading the code is correct. The implementer followed the plan. The orchestrator or operator should confirm the reading rather than the implementer changing code.
  - **The 26 warnings.** The implementer's full-suite run reports "26 warnings". The new test file alone runs clean (27 passed, no warnings; I checked), so the warnings come from elsewhere. Whether they are pre-existing cannot be told from this diff, since the brief's baseline line gives no warning count.
  - **Real-show behaviour.**
    - derektrucksband-2007-05-27 relies on route (a) through its own 14-entry list, because the real setlist.fm canonical is shifted and would trip the skip.
    - The C note may be written for an `overrides.titles` position.
    - Both depend on Task 11's wiring and the yield gate.

### Strengths
- **Pure and small, a good fit for a strict surface.** Every reference is count-gated at one site (lossless_titles.py:137-140), and each decision is a named predicate: `_real`, `_shape_2a`, `_vetoed`, `eligible`.
- **`c1_verdicts`/`c_holds` expose exactly what the R17 gate row needs.** `c_holds` stays `None` when no target needed (c) (:184).
- **Real evidence of load-bearing tests.** RED was taken against a stub, and the implementer ran 11 named mutants with the test each one broke. The four tests added afterwards close specific survivors: `exactly_two`, `reference_is_the_list`, `delivered_must_disagree`, `own_position`.
- **Tests run real behaviour** through the real `clean_tag_titles`, `sibling_format_titles`, `filter_files` and `read_numbered`, with no mocks. Two fixtures are verbatim real cases (radiators, derektrucksband).
- **The concerns in the implementer's report are candid and accurate.** The derek test departs from the real show, and two clauses are inert.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **`test_one_off_by_one_lossless_tag_does_not_skip_c` hides what it exercises (test_lossless_titles.py, the `one_off_by_one` test).** It asserts only `declined != "off by one"`.
   - Probe: the case actually **adopts** `Deal` at track 2 via (c), against the list's `Sugaree`. That produces adjacent `Deal, Deal`, unflagged: `changed={1:'C1'}`, `c1_verdicts={1:(False,None)}`, `c_holds=True`.
   - This is what the spec and the plan's reading prescribe: a single shift is below the 2+ skip, and (c) overrides a disagreeing reference.
   - It is exactly the strict-surface outcome the R17 gate row exists to surface, so the test should pin it explicitly (`changed == {1: "C1"}`, `c1_verdicts == {1: (False, None)}`). Then a later change to that behaviour is visible, and the operator can see the shape at Checkpoint A.
2. **The off-by-one note is written when C had nothing to do (lossless_titles.py:143-150).**
   - Probe: a fully tagged tape whose FLAC tags equal its MP3 tags, with a count-matched list shifted by one, writes `lossless titles declined: off by one against the taper's list (tracks 1, 2, 3)`.
   - No C1 target and no C2 candidate existed on that show.
   - The quiet declines ("out of scope", "no lossless format") deliberately write no note to avoid noise, so this is inconsistent. The note does carry some signal (list vs tape disagreement), though, so this is a judgement call.
   - Either compute the skip only when targets or C2 candidates exist, or keep `declined` but drop the note in that case.
3. **A C1 fill can ship a trailing taper marker (lossless_titles.py:88-95, 152-155).**
   - Probe: delivered blank, lossless `Blue Night @`, list `Blue Night` ships `Blue Night @` as C1.
   - The spec's third veto covers only "delivered plus marker", so this follows the spec. Slice 5's cosmetic stripping may be the intended remedy. It is worth a gate line.
   - As the implementer notes, the third veto itself is inert inside `apply_lossless`: delivered plus a symbol tail is always `fuzzy_norm`-equal to the delivered tag, so C2 can never fire, and a real delivered tag is never a C1 target. It is pinned only via `test_veto_predicate`. Keeping it because the spec names it is fine, but a comment at :94 saying it is belt-and-braces would stop a later reader assuming it is load-bearing.
4. **`test_case_or_punctuation_difference_is_not_c2` passed against the stub and no mutant broke it.** The implementer reports that the `fuzzy_norm_title` differs clause survived mutation. The clause is near-equivalent given `agrees`' containment, so the test pins nothing distinctive. A case where `clean_one` diverges between the two sides would make it load-bearing, for example a lossless footnote `(1)`. Otherwise, note it as a spec-named belt-and-braces clause.
5. **`_BRACKETED = r"\s*\[.*\]\s*"` (lossless_titles.py:58) fullmatches `[a] b [c]` greedily** and so vetoes a tag that is not wholly bracketed. This errs in the safe direction on a strict surface, so it is cosmetic only. `\[[^\]]*\]` states the "wholly bracketed" intent exactly.

### Assessment
**Task quality:** Approved

**Reasoning:** The implementation follows the brief, the spec's slice 3 and the plan's C1/C2 readings exactly. It mirrors the recovery path's stem and format handling, touches no protected name, and its tests are real-behaviour tests with mutation evidence. The open items are a spec-reading question for the orchestrator or operator (`loosely_same_title` containment versus "whole-text containment is never used") and test-explicitness polish around the single-shift (c) adoption, which the R17 gate row should surface.
