# t16-impl handback (Task 16, slice 4a right-show gate)

Status: DONE
Commit: f0d7b9a feat(vet): 4a right-show gate turns unknown-song holds into notes (BASE 5622558)
Tests: `./.venv/bin/python -m pytest -q` -> 3656 passed, 1 skipped, 8 deselected (was 3638; +18 new). `test_stage_vet.py`: 69 passed.
llama import check: resolves inside the worktree.

## Changes
- `packages/llama/src/llama/stages/vet_research.py`
  - `RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5`, `RIGHT_SHOW_MIN_ASSERTED = 4`, with a comment citing spec "New constants" and saying the first may move to `2 / 3` only at Checkpoint E.
  - `right_show_gate(vetting, show, *, date_flags_raw) -> (bool, dict)`, built to the brief's Interfaces. It imports `TAUTOLOGICAL_TITLE_SOURCES` and `is_filler` from `llama.structure` and reuses `normalize_song` and `_known_song`; nothing is re-implemented. The info dict is `{asserted: int, resolved: int, ratio: asserted/resolved or 0.0, unknown: list[str], date_text: first asserted_dates entry normalising to show.date or None}`. `own_full` is `date_text is not None`, which is the same test as `show.date in {normalize_date(d) ...}`.
  - `grounding_flags`: the unknown-song flags are now decided after `date_flags_raw` (Task 15's local, the date flags without the 4b window) is computed. If `not songs_grounded` and the gate holds, the flags are dropped and the Contracts 4a note (verbatim f-string) goes into `notes`. Otherwise the flags are emitted exactly as before. The flag order (songs, then dates, then set count), the flag texts and the `songs_grounded` rule are unchanged. The return value is still the 3-tuple.
- `packages/llama/tests/test_stage_vet.py`: the brief's tests, verbatim. I moved its mid-file import into the top-level import block, as instructed. I added these tests:
  - `test_right_show_gate_holds_at_exactly_half_the_tape`: the 4/8 boundary, plus a full info-dict check. Needed for mutant e; no brief test sits at exactly 0.5.
  - `test_right_show_gate_excludes_filler_from_the_resolved_count`
  - `test_4a_reads_the_raw_date_flags_not_the_windowed_ones`: the wiring pin. The research asserts both 1973-06-10 and 1973-06-11. The test asserts that 4b removed the wrong-date flag AND that the three unknown-song flags fire with notes == [].
  - `test_4a_note_only_when_the_unknown_song_flags_would_fire`
  - `test_4a_note_lands_in_vet_outcome_notes_and_flags_clear`: via `apply_vet`.

## Mutation table (MROOT=$TMPDIR/mut-t16-impl-SLxmKN, shadowing proven per mutant, private PYTHONPYCACHEPREFIX each; I wrote the predictions into the log before flipping)
| mutant | predicted test | caught by |
|---|---|---|
| a drop own_full | gate_table[8-0-5-dates4-False], [dates5], test_right_show_gate_requires_the_own_full_date_with_year | all three, as predicted |
| b1 drop `not date_flags_raw` | gate_table[8-0-5-dates6-False], test_4a_reads_the_raw_date_flags_not_the_windowed_ones | both, as predicted |
| b2 pass windowed date flags to the gate | test_4a_reads_the_raw_date_flags_not_the_windowed_ones | that test only, as predicted |
| c drop unknown <= asserted | test_4a_unknown_songs_may_not_outnumber_the_asserted_tracks | as predicted |
| d count tautological sources as resolved | test_4a_excludes_tautological_titles_from_both_sides | as predicted |
| e `>=` -> `>` on tape fraction | test_right_show_gate_holds_at_exactly_half_the_tape, test_right_show_gate_excludes_filler_from_the_resolved_count | both, as predicted |
| f (extra) drop is_filler exclusion | test_right_show_gate_excludes_filler_from_the_resolved_count | as predicted |
| g (extra) drop unresolved-half clause | gate_table[8-9-5-dates3-False] | as predicted |
No survivors. I removed MROOT with `rm -rf` on that exact path.

## Deviations
- Added 5 tests beyond the brief (listed above). One of them is required, because without the exact-half test mutant e would have survived the brief's table.
- None in code.

## Concerns
- None blocking. `ruff` is not installed in the venv, so I ran no lint; the diff is small and I read it through.
- The do-not-retune grep over the diff found nothing.

## Fix round 1

Status: DONE
Commit: 3928398 test(vet): 4a gate row where only the tape fraction declines; raw _guard_prose docstring

### Changes
- `packages/llama/tests/test_stage_vet.py`: added the row `(10, 0, 4, ["1973-06-10"], False)  # 0.4: only the tape fraction fails` to `test_right_show_gate_table`. The comment on the `(8, 0, 3, ...)` row now reads `# fewer than 4 asserted`.
- `packages/llama/src/llama/stages/brief.py`: the `_guard_prose` docstring is now a raw string (`r"""`). Its wording is unchanged.

### Commands and results
- Before the fix: `git show HEAD:packages/llama/src/llama/stages/brief.py | ./.venv/bin/python -W error -c "import sys; compile(sys.stdin.read(),'brief.py','exec')"` printed `SyntaxError: "\s" is an invalid escape sequence...`.
- After the fix, the same compile on the working file shows no warning. The coordinator's exact command also exits 0. It does print a ResourceWarning, but that comes from the unclosed `open()` inside the command line itself, not from brief.py.
- `./.venv/bin/python -m pytest packages/llama/tests/test_stage_vet.py packages/llama/tests/test_stage_brief.py -q` -> `130 passed`
- `./.venv/bin/python -m pytest -q` -> `3657 passed, 1 skipped, 8 deselected`

### Mutation (MROOT=$TMPDIR/mut-t16-impl-r1-nBvLuG; shadowing proven per mutant; private PYTHONPYCACHEPREFIX for each; predictions written to the log before flipping; I removed that exact path afterwards)
| mutant | predicted test | caught by |
|---|---|---|
| f1 delete `len(asserted) >= RIGHT_SHOW_MIN_TAPE_FRACTION * len(resolved)` | test_right_show_gate_table[10-0-4-dates2-False] | that test only, as predicted |
| f2 numerator `RIGHT_SHOW_MIN_TAPE_FRACTION * len(asserted)` | test_right_show_gate_table[10-0-4-dates2-False] | that test only, as predicted |
