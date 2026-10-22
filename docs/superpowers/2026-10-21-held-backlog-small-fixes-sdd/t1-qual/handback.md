### Spec Compliance (SPEC role) — n/a (CODE-QUALITY role). Nothing Critical noticed outside my lane.

### Strengths
- The fold is a two-character replace (`structure.py:62-64`) that touches nothing else, and the test pins this exactly: `fold_curly_apostrophes("a’b‘c“d") == "a'b'c“d"`. It is applied at the matching layer only. `fuzzy_norm_title` calls it first (`structure.py:82`), so `title_components` and `contains_sequence` inherit it with no extra call sites.
- The two module-local wrappers (`vet_research._song_tokens`, `brief._song_norm`) send every `normalize_song` use in those two stages through the fold. A grep of both files shows `normalize_song` now appears only inside the wrappers, so no comparison is folded on one side and not the other. `song_comma_components` and the `components` builders reach the fold through `song_components`.
- Protected names: I grepped the diff for every do-not-retune name in global-constraints.md. The only `+`/`-` lines that mention one are `normalize_song` *call sites* being replaced and the new pin test. `songs.py` has no diff, and `ADJACENT_DAY_WINDOW` and the `RIGHT_SHOW_*` constants appear in context lines only.
- No outside callers: `known_song`, `song_components`, `grounding_flags` and `right_show_gate` are not called from anywhere else in `packages/llama/src` or `scripts/`, so the contracts are unchanged.
- I verified the RED claim independently. I made `fold_curly_apostrophes` the identity in a scratch `git archive` copy (shadowed via PYTHONPATH, `llama.__file__` confirmed inside the copy). 9 of the 10 targeted tests fail; only the `normalize_song` pin passes, as it should. All four Review Focus #4 cases (curly titles in a tape segue chain) are among the 9 failures.
- The vet tests' negative asserts are not vacuous. The flag text really is `research asserts unknown song: …` (`vet_research.py:287`), and each fixture fails `right_show_gate` (fewer than 4 asserted songs, or no own date), so the flags are not converted to a note.

### Issues
#### Critical
None.

#### Important
None.

#### Minor
1. **`right_show_gate`'s `research_known` fold has no test of its own** (`vet_research.py:193`; test `test_stage_vet.py`, `test_right_show_gate_counts_a_curly_tape_title_as_asserted`). In a scratch copy I reverted only that line to `normalize_song(s).split()`. All 171 tests in test_stage_vet.py and test_stage_brief.py still pass. The gate test only covers curly on the tape side. With curly research and a straight tape, the reverted line drops `asserted` (["he","s","gone"] vs ["hes","gone"]), so the change does have an observable effect that no test covers. Fix: parametrize the gate test both ways, as `test_vet_matches_curly_and_straight_apostrophes_both_ways` already is.
2. **Mid-file import with `# noqa: E402`** (`test_structure.py:2076`). `fuzzy_norm_title` is already imported at line 22, so `contains_sequence, fold_curly_apostrophes` could join that import. The file already scatters imports through lines 1-29, so this matches local practice; polish only.
3. **CLAUDE.md line wrap** (`CLAUDE.md:778`). The inserted clause makes one ~200-character line inside a paragraph wrapped at about 80 columns. Cosmetic: re-wrap it.
4. (Note, not a defect) The fold in `known_song`'s exact test (`brief.py:163`) duplicates the `song_components` fallback. Reverting just that line in a scratch copy leaves every test green, and I could not construct an input where the two paths differ, because `song_components` folds each part. The brief mandates the fold there, and it keeps both sides of the `exact` comparison symmetric with the `exact` set builder, so keep it.

### Assessment
**Task quality:** Approved
**Reasoning:** The change is minimal and symmetric, and it stays at the matching layer as the spec requires. Protected names are untouched, and mutation confirms the new tests catch the fold. The only gap is one call site the tests don't cover separately (Minor 1), worth a one-line parametrize but not blocking.

Evidence log: .superpowers/sdd/small-fixes/t1-qual/t1-qual.log (identity-fold mutant: 9 failed / 1 passed; per-site mutants `rk` and `kse`: 171 passed each). Scratch copies were under the session scratchpad, not the worktree.
