# t9-rev: Task 9 review (slice 2b), e416018..de14749

Reviewed in three passes: source hunks, test hunks, then focused outside-diff checks. The furthur fixture JSON was not read line by line.

### Spec Compliance

- ✅ **Spec compliant.** Every Interface in the brief is present with the specified signature and semantics:
  - `titles.tag_layer`: titles.py:247.
  - `titles.placeholder_positions`: titles.py:265-296.
  - `resolve_titles` keyword-only `corroboration`/`item_title`, with the demoted branch ahead of `is_real_title`: titles.py:299, 360.
  - `compute_gather` wiring: gather.py:1028-1081.
  - The Contracts 2b note is verbatim (gather.py:1035), and so is the brief's format-sibling note (gather.py:1073).
  - Both notes go to `op_notes`, which becomes `GatherResult.notes` (gather.py:903, 1349). They never go to `notes`, which feeds `conflicts` (gather.py:1305). Ruling 6 holds, and test_stage_gather.py:2394 pins it.
- ✅ **Orchestrator rulings applied:**
  - M9: gather.py:1031-1033 filters on `overrides.titles`. Keys are `dict[int, str]` (models.py:211), so `(i + 1) not in overrides.titles` matches. Pinned at test_stage_gather.py:2425.
  - The residue arm is `is_real_title(t) and is_residue(t)` (titles.py:294), with the `d1t02` non-real row at test_titles.py:512.
  - The `is_placeholder_title` change is docstring only (placeholders.py diff).
  - `Ripple 1970-09-20` is in the residue pin (test_titles.py:524).
- ✅ **Do-not-retune grep.** Over the diff, `_RECOVER_BELOW` appears only in comments and `_RECOVER_SIBLING_ABOVE` is only read (gather.py:1072). `git diff e416018 de14749 -- junk.py structure.py songs.py` is empty. In titles.py the only removed lines are the 6-line tag-layer block and the `if is_real_title` line that became `elif`; `is_real_title`, `title_fraction`, `_TRACK_NUM_PREFIX`, `_ENUMERATED_MIN_*` and `_YEAR_LIKE_NUMERIC` are untouched.
- ✅ **Deviation 1 (format-sibling note gated on `format_titles is None`, gather.py:1063): accepted.** When recovery fired, the tag layer IS that sibling, so "recovery not triggered" would be false. The spec's harness count is of tapes where recovery did not move. Pinned at test_stage_gather.py:2446.
- ✅ **Deviation 2 (M9 enforced in gather, not in `resolve_titles`): verified output-equivalent.** The ORDER check:
  - `resolve_titles` (gather.py:1076) is followed immediately by the overrides loop (1079-1084). No statement reads `tracks` in between.
  - Every consumer runs after the loop: `_sibling_transfer` (1090), `adopt_gap_titles` (1123), `align`/coverage, and the `unresolved track titles` flag.
  - `fetch_siblings` (1057) and the format note (1063) both read the M9-filtered `demoted`, not the raw positions.
  - `build_canonical` runs before 2b and never sees tracks.
  - Inside `resolve_titles` each position is decided independently. `aligned` depends only on the count, and `recording_junk` depends only on the tag layer. So a demoted override position cannot change another position's outcome.
  - Conclusion: no path uses a demoted override position before the overrides loop replaces it.
- ✅ **Deviation 3 (`scripts/blind_tag_gapfill.py:241`): not shipped, never writes the library.**
  - Its docstring calls it a "Manual, read-only diagnostic (never run by the pipeline)", and the cache is opened read-only.
  - The only `resolve_titles` callers outside tests are gather.py:1076 and this script.
  - No shipped module references it. Its only references are in docs/ledgers.
  - Fidelity drift is filed as a Minor below.
- ✅ **Deviation 4 (extra `Track 01` corroboration row, test_titles.py:571): correct and needed.** `Song #1` is never a placeholder, so the brief's row alone cannot discriminate the exemption.
- ✅ **Unchanged behaviour on a tape with no placeholder tags** (with providers):
  - `tag_layer` is a pure move of the deleted block (diff titles.py hunk 2).
  - The `tag_gate_basis` hoist is a pure move: `kept`/`readmitted` are not mutated between its old and new position.
  - With `placeholder_positions` returning `[]`: no note, `fetch_siblings` equals the old expression, the format loop does not run, and `resolve_titles` takes the old branches.
- ✅ **A demoted position never receives other text from 2b or the setlist rung** (`if pos in demoted` precedes both, titles.py:360). Sibling-align and setlist-gap can still fill it, which spec 2b explicitly intends ("the only ways such a track can still get a title"). They fill only `title_source == "unresolved"` tracks (siblings.py:522-536; gather.py `_sibling_transfer` docstring). Demoted tracks are not anchors, because anchors require `INDEPENDENT_TITLE_SOURCES` (siblings.py:402).
- ⚠️ **Cannot verify from diff:** the spec's acceptance items (the library-wide demotion list, hand-checked; zero demoted 4-digit or corroborated titles; packaged-exposure list matching Evidence). These are harness/checkpoint deliverables, not Task 9 code.

### Strengths

- The `placeholder_positions` docstring (titles.py:265-286) states every scope decision: blank tags, cross-source corroboration, the `is_real_title` gate on residue only, and overrides left to the caller.
- Notes and demotions come from the same `tag_layer` + `placeholder_positions` call with identical arguments (gather.py:1030 vs titles.py ~352). The only difference is the gather-only M9 filter.
- Tests discriminate and are not decorative:
  - `test_resolve_titles_non_real_placeholder_skips_the_setlist_rung` (test_titles.py:545) checks a placeholder and a non-placeholder side by side on the setlist rung.
  - The item-title test uses two spellings, so the identical-string arm cannot mask it (test_stage_gather.py:2479).
  - The fetch-gate test patches `_sibling_transfer` and observes the call (2409).
- The mutation table covers the five brief mutants plus five gather wiring mutants (f-j). Each one is attributed to its predicted test.
- Test-output noise: the 26 warnings in the full-suite run are the pre-existing fork DeprecationWarning, with an identical count at every earlier task.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **gather.py:1063-1074: the format-sibling loop near-duplicates `_recover_format_titles`' loop (gather.py:337-343).** Same format iteration, same skip of `ordering["format"]`, same `filter_files`/`sibling_format_titles`/`title_fraction >= _RECOVER_SIBLING_ABOVE`; only the entry gate differs. The note asserts something about recovery ("recovery not triggered"), so the two should share one definition of "a tagged format sibling". Fix: extract `_tagged_format_sibling(files, basis, ordering) -> tuple[str, dict, float] | None`, used by both. Not a behaviour defect today: I compared the two and they agree, including the `recovered and` vs `is None` difference, since `sibling_format_titles` never returns `{}` for a non-empty basis.

2. **gather.py:1030/titles.py:288: the recording-level class votes over every kept file, re-admitted files included.** Elsewhere in this function, recording-level decisions vote on the tape minus `readmitted` (comments at gather.py ~930-958 and 1013-1021). Example: a tape of identical non-vocabulary strings × N. An operator `--include` of one differently-tagged file switches `recording_level_junk` off for the other N tracks; one identically-tagged file can switch it on for a 2-track tape. The scenario is narrow and the spec does not address it, and it never demotes a varied real-titled tape. Fix if wanted: compute `recording_level_junk` over the `tag_gate_basis` positions, or note it as accepted.

3. **scripts/blind_tag_gapfill.py:241: fidelity drift.** The script claims to replay `run_gather`'s prefix, but it now demotes with an empty `corroboration` and no `item_title`. It therefore over-demotes relative to production, which also shrinks its blindable runs. It is not shipped and is read-only. Before its next use, pass `cb.corroboration`/`meta["title"]`, or say in its docstring that it does not.

4. **gather.py:1030 vs titles.py:352: the positions are computed twice from separately-assembled arguments.** If a later change alters the `resolve_titles` call (e.g. a different `gate_basis`) without updating line 1030, the notes and the demotions drift silently. No test catches that today, since the tests take both from the same fixture. Optional fix: have `resolve_titles` return or expose the demoted set, or assert note count == unresolved-by-demotion in the furthur test (already true at test_stage_gather.py:2374 for the whole-tape case).

5. **The format note's threshold is plain `title_fraction`, so a lossless sibling tagged `tmp`/`Track NN` throughout would also be filed as "format sibling tagged … 1.00".** The brief mandates this exactly, and it is filed, not acted on. It only inflates the harness count; flag that to whoever reads that count.

### Assessment

**Task quality:** Approved

**Reasoning:** Every brief interface and orchestrator ruling is implemented exactly and pinned by a discriminating test. The do-not-retune constants are untouched. The four deviations each check out on the code: the M9 order is safe, the script is unreachable and read-only, and the gate on the format note is correct. What remains is maintainability and edge-case minors, none on the strict surface.
