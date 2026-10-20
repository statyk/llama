### Spec Compliance

- ✅ Spec compliant, checked against the brief's Interfaces, spec "Slice 4 — 4a" (lines 697-728), "Failure modes" 4a (lines 1007-1012) and the plan's Contracts row.
  - All seven gate clauses are present: `vet_research.py` `right_show_gate`, `holds = (...)` block (diff hunk at new lines ~183-191). `resolved` excludes unresolved, filler and `TAUTOLOGICAL_TITLE_SOURCES` titles. `asserted` uses `_known_song(t.title, research_known)` in the tape-to-research direction. `unresolved_n * 2 < len(show.tracks)` means fewer than half the tracks are unresolved. `own_full` is computed via `normalize_date(d) == show.date`, which is the same test as 4b's `show.date in full`.
  - The gate reads `date_flags_raw`, Task 15's unwindowed local. `grounding_flags` moved the unknown-song emission below that local (diff hunk at new lines ~242-255). The orchestrator's wiring pin is `test_4a_reads_the_raw_date_flags_not_the_windowed_ones`. It asserts that 4b removed the adjacent-day flag AND that the unknown-song flags still fire with `notes == []`, so mutant b2 (feeding the windowed flags) must fail it.
  - The note text matches the plan's Contracts table row 4a byte for byte (plan line 79): same separators, `{ratio:.2f}`, `'; '.join`.
  - Ruling 6 holds. The note goes only into `grounding_flags`' `notes`, then `VetOutcome.notes`, then `notes.vet` in `notes.json` (vet_research.py:280-308, unchanged). Nothing is added to `VettingResult.flags`, `StructureInfo.conflicts` or `review_flags`. `test_4a_note_lands_in_vet_outcome_notes_and_flags_clear` pins the `apply_vet` path.
  - `info["asserted"]` and `info["resolved"]` are counts, as the orchestrator required. `test_right_show_gate_holds_at_exactly_half_the_tape` checks the full dict.
  - The flag texts, the `songs_grounded` rule and the flag order (songs, then dates, then set count) are unchanged. In the else branch the flags are built from the outer `unknown`, which is the same list as before.
  - Constants: `RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5` and `RIGHT_SHOW_MIN_ASSERTED = 4`, with a comment citing "New constants" and the Checkpoint E `2 / 3` rule.
  - Do-not-retune grep over the diff: no protected name is touched. The diff adds an import of `TAUTOLOGICAL_TITLE_SOURCES`/`is_filler` and does not change them.
- ⚠️ Cannot verify from diff: none needed. The notes.json routing was checked directly at vet_research.py:280-308. That code is unchanged, and the diff's own `apply_vet` test exercises it.

### Strengths

- The gate is a pure function with a returned info dict. The note is formatted only from that dict, so the verbatim contract text and `compare`'s parse depend on one place.
- The wiring test for raw vs windowed flags is the right shape. It asserts both halves (the window applied, the gate still declined) rather than just "flags present".
- The implementer found that the brief's table had no row at exactly 0.5. They added the boundary test, so mutant e is actually caught. They also added the filler exclusion test and two extra mutants (f, g).
- The brief's mid-file import was folded into the top import block, and unused `noqa: F841` was removed now that the local is consumed.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **No test makes the tape-fraction clause the sole deciding clause, so deleting it entirely survives.** packages/llama/tests/test_stage_vet.py, `test_right_show_gate_table` row `(8, 0, 3, ["1973-06-10"], False)  # below 0.5`. The row is labelled as the fraction case, but 3 asserted tracks also fails `RIGHT_SHOW_MIN_ASSERTED = 4`, so the min-count clause decides it alone. The exact-half and filler tests both expect `True`. The tautological and tmp-tape tests fail on `len(resolved) > 0` or on the min-count clause.
   - I ran the mutation to check this. Removing the line `and len(asserted) >= RIGHT_SHOW_MIN_TAPE_FRACTION * len(resolved)` (vet_research.py, in the `holds` block) gives `test_stage_vet.py`: **69 passed**, so the mutant SURVIVED. The run used the Global Constraints recipe in a scratch copy, with shadowing proven (`llama.__file__` under the copy) and a private PYTHONPYCACHEPREFIX. I deleted the copy afterwards. The log is at `$D/t16-rev/t16-rev.log`.
   - Why it matters: this clause is 4a's headline condition, on a STRICT surface (wrong-show research must never be waved through). Mutant e (`>=` to `>`) is caught only because a boundary test exists. A refactor that drops or misplaces the clause would pass the suite. A wrong numerator would also pass, for example `* len(asserted)`. A wrong denominator would be caught by the filler test.
   - Fix: change that row so that only the fraction fails, for example `(10, 0, 4, ["1973-06-10"], False)`. That is 4 of 10 = 0.4, at least 4 asserted, unknown 2 ≤ 4, no unresolved, own date present. Alternatively, add a dedicated test. Re-flip the "delete the clause" mutant and record it in the ledger table.

#### Minor (Nice to Have)
1. vet_research.py `right_show_gate`, `tape_known = [...]` / `unknown = [...]`: these duplicate `grounding_flags`' `known`/`unknown` computation (vet_research.py ~213-214) verbatim. They are two lines and both are defined as "today's list", so drift is unlikely, but the gate could take `unknown` as a keyword argument. It would then be the same object as the flag list, not a recomputation. Not blocking.
2. `test_right_show_gate_table` binds `info` and never uses it. It is harmless and verbatim from the brief.
3. Out of this diff, seen during my mutation run: compiling fresh emits `packages/llama/src/llama/stages/brief.py:178: SyntaxWarning: "\s" is an invalid escape sequence`. The cause is a backtick-quoted `\s+` in a non-raw docstring from an earlier slice 3 task. A cached `.pyc` hides it in the implementer's runs. The controller should route it to that task's owner: make the docstring raw or escape the backslash.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The gate, its wiring to the unwindowed date flags, the note contract and ruling 6 are all implemented correctly. However, on this strict surface the gate's central fraction clause can be deleted with the task's own test file still green, which I verified by mutation. Re-targeting the "below 0.5" row to something like 4 of 10, which still meets the minimum count, closes the gap.
