# Task 2 handback (t2-impl): Overrules take effect and are recorded

Status: DONE_WITH_CONCERNS
Commit: 16cf2b3d feat(overrules): recorded overrules become notes on every re-gather

## Implemented
- `models.ShowNotes.brief: list[str] = []` (defaulted; old notes.json reads fine).
- `stages/gather.py`: `compute_gather` builds `show` exactly as before, then as its LAST step calls
  `_apply_overrules(show, overrides.overrules, op_notes)`. The new helper splits the flags with
  `split_overruled`, appends the `overruled: <flag>` notes to `op_notes` and recomputes
  `needs_review`. It is one clearly named spot that Tasks 9 and 10 can keep. Because `run_gather`
  writes `ShowNotes(gather=..., vet=[])`, `brief` resets on every gather, as `vet` does.
- `stages/vet_research.py`: `apply_vet(vetting, show, *, overrules=())` splits only vet's own
  grounding flags. Matched flags leave `result.flags` and go to the end of `VetOutcome.notes`.
  Kept flags from other stages are untouched. `run_vet_research` passes
  `read_overrides(show_ws).overrules`.
- `stages/brief.py`: `run_brief` splits the guard's `problems` before any flag write. The new
  `_write_brief_notes` does a read-modify-write of notes.json `brief` before briefing.json (the
  done-marker). It replaces a stale `brief` list and never creates a file only to hold an empty
  list.
- `replay.compute_legs`: passes `read_overrides(ws).overrules` to `apply_vet`. Gather already sees
  the records through the scratch copy of overrides.json.
- `reapply.reapply_show`: the fresh brief splits `problems` the same way as `run_brief`. The
  written `ShowNotes` carries `brief=brief_notes`, which is `[]` on reuse or none.
- `cli.py`:
  - `_clear_hold(show_ws, *, record=None)`. With `record`, it computes
    `records_for(show.review_flags, show, source=record, at=<UTC now ISO>)` and merges the result
    through `_edit_overrides(add_overrules=...)` before it clears the hold. Package-family flags
    are skipped. If no record results, overrides.json is not written.
  - `_edit_overrides(..., add_overrules=())` stores `merge_rules(ov.overrules, add_overrules)`.
    Every other edit keeps the existing rules unchanged.
  - Callers: `fix --overrule` uses "fix", triage `[o]` uses "triage", and `_untitled_resolution`
    uses "untitled" (`fix --untitled` and triage `[u]`). The two narration-vague callers pass
    nothing.
  - `llama show` now also prints `notes.brief` under `notes:`. This is a small addition beyond the
    brief; without it the brief notes would never be shown.

## Dry run: changed test expectations (logged before the edit)
- `test_show_cmd.py::test_json_carries_notes_and_empty_lists_without_notes_json`:
  `show --json` `notes` gains `"brief": []`. This follows from `ShowNotes.brief` (Task 2
  Interfaces; Global Constraints "New persisted fields, defaulted and permissive:
  `ShowNotes.brief`"). No other existing expectation changed: the full suite run before this edit
  had exactly this one failure.

## Tests added (19)
- test_stage_gather: `test_gather_turns_an_overruled_flag_into_a_note`,
  `test_unresolved_titles_overrule_needs_a_subset`.
- test_stage_vet: `test_vet_overrule`, `test_run_vet_research_reads_overrules`.
- test_stage_brief: `test_brief_overrule_goes_to_notes_brief`,
  `test_brief_overrule_on_another_recording_still_holds`,
  `test_a_clean_brief_replaces_stale_brief_notes`.
- test_replay: `test_replay_sees_overrules`.
- test_fix:
  - `test_fix_overrule_records_the_cleared_flags`
  - `test_fix_overrule_twice_records_each_rule_once`
  - `test_fix_overrule_of_a_package_flag_alone_writes_no_overrides`
  - `test_narration_vague_records_nothing` (pin)
  - `test_untitled_records_remaining_flags`
  - `test_edit_overrides_preserves_overrules` (pin)
  - `test_overrule_survives_a_regather`
- test_triage: `test_triage_overrule_records`, `test_triage_vague_records_nothing` (pin).
- test_reapply: `test_reapply_fresh_brief_overrule_goes_to_notes_brief`.
- test_show_cmd: `test_show_prints_brief_notes`.

Notes on the fixtures:
- The brief's gather fixture produces two flags: `low-confidence structure alignment` and
  `setlist evidence shows multiple sets...`. The test therefore checks three cases: the alignment
  rule alone (that flag becomes a note, the other still holds), both rules (`[]`,
  `needs_review False`), and rules recorded on another identifier (inert).
- `test_overrule_survives_a_regather` runs the real pipeline (packaged_gd73, then
  `redo --from gather` over `Track N` placeholder tags with a garbage align_structure provider,
  then `fix --overrule`, then `redo --from gather` again). The final show is packaged and not held.

## TDD evidence
- RED: `./.venv/bin/python -m pytest -q packages/llama/tests/test_stage_gather.py packages/llama/tests/test_stage_vet.py packages/llama/tests/test_stage_brief.py packages/llama/tests/test_replay.py packages/llama/tests/test_fix.py packages/llama/tests/test_triage.py -k "overrule or records_nothing or untitled_records or preserves_overrules or stale_brief_notes"`
  gave `11 failed, 16 passed`. The 11 failures are the gather 2, vet 2, brief 1, replay 1, fix 4 and
  triage 1 tests. The passes are the pins and existing tests that match the keyword. Each failure
  was checked to be the missing behavior: a TypeError on `overrules=`, flags still held, or no
  rules recorded.
  - The first version of `test_run_vet_research_reads_overrules` failed for the wrong reason: one
    unknown song does not trip vet's gate. I fixed the fixture to assert two songs, and mutant M2
    below then showed the test is RED without the wiring.
- GREEN: the same command plus test_reapply gave `28 passed`.
- Mutation check (scratch copy, PYTHONPATH-shadowed, `python -m pytest`, no bytecode). Every
  mutant was caught by its predicted test:
  - M1: reapply split removed.
  - M2: run_vet_research without overrules.
  - M3: compute_legs vet without overrules.
  - M4: show print without brief.
  - M5: `_clear_hold` records nothing. Caught by 5 tests: fix x4 (including survives_a_regather)
    and triage.
  - M6: `_edit_overrides` drops the existing rules.
  - M7: brief notes not written.
  - M8: vague callers record. Caught by both pins.
  - M9: gather split removed. Caught by gather x2, replay and survives_a_regather.
- Full suite: `./.venv/bin/python -m pytest -q` gave
  `6027 passed, 1 skipped, 8 deselected` (6008 + 19 new).

## Files changed
packages/llama/src/llama/{cli.py, models.py, reapply.py, replay.py, stages/brief.py,
stages/gather.py, stages/vet_research.py}; packages/llama/tests/{test_fix.py, test_reapply.py,
test_replay.py, test_show_cmd.py, test_stage_brief.py, test_stage_gather.py, test_stage_vet.py,
test_triage.py}.

## Self-review
- Global Constraints: the diff touches none of the listed constants or functions
  (`briefing_reusable`, `load_list`, `STOP_AFTER_LLM_FAILURES`, the junk rule, `audio_reuse`
  pairing, purge). `Manifest` has no new field. Lock order is unchanged: every `_clear_hold`
  write happens inside the existing `show_unit`, so a failed overrule restores overrides.json too
  (the existing `test_failed_overrule_restores_every_file` still passes).
- `_edit_overrides` runs `_legacy_message` before it writes. A legacy (track-number)
  overrides.json therefore now makes `fix --overrule`, triage `[o]` and `--untitled` refuse when
  there is something to record. `fix` already refuses a legacy file up front for every flag, and
  migration is done, so in practice this is only reachable through triage on an unmigrated file.
- The overrule split is in one place per function: `_apply_overrules` in gather, `apply_vet` for
  vet, a single `split_overruled` line in `run_brief` and in reapply.

## Concerns
1. A brief guard problem that is overruled still triggers `generate_briefing`'s second, feedback
   attempt. The split happens after `generate_briefing`, as the brief says, so a show whose
   overruled briefing problem recurs costs 2 brief calls instead of 1. If that spend matters for
   the bulk apply, `generate_briefing` could take the rules and treat overruled problems as
   passing. That is a small change, not made here.
2. `briefing_reusable` is on the untouched list. A stored briefing whose guard problem was
   overruled is therefore never reused by replay or reapply, and always costs a fresh brief.
3. `llama show` now prints `notes.brief` (not in the brief; one line, tested).
4. By mistake I ran `git stash list`, which is read-only, once, and changed nothing. No other
   stash command was run.
