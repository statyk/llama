### Verdict — ✅ mutation run sound

### Coverage table check
All 30 mutants in the brief, with the orchestrator's amendments, were run; C4 is recorded as retired. I read every logged diff (t8-mut.log `APPLIED` blocks) against the code at HEAD 36473d8:
- B1 OK. Drops `n != counts.get(candidate.venue, 0)`, leaving `n == 0 or …`. That is `n >= 1`, the brief's mutant in the implementation's form.
- B2 OK. The city gate is removed.
- B3 OK.
- B4 OK. Raw `sel.venue` is returned.
- B5 OK. The guard tests `sel.venue` truthiness only.
- B6 OK. The no-event `elif tie` becomes `elif False`; a comment is stripped, which is harmless.
- B7 OK. The unflagged 1a arm is disabled.
- B8 OK. `venue, city = tie` is inserted after `flags.append(mismatch)` in flagged 1a.
- B9 OK. Step 1 becomes `if tie is not None:`.
- B10 OK. Removes `and (_pre1b or cities_compatible)`, the city half of step 1's full test.
- B11 OK. `tie` is applied inside the `two_venue_signature` arm.
- B12 OK. Drops `n == 0 or`.
- C1 OK. Step (a) is disabled.
- C2 OK. Step (b) becomes `pass`.
- C3 OK. Step (c) is disabled.
- C5a OK. `BaseException`→`Exception` around the yield.
- C5b OK. The same change around `take_snapshot`.
- C6 OK. The `raise` after restore is removed, so the generator swallows the exception.
- C7 OK. The `discard_snapshot` after restore is removed.
- C8 OK. Hand-built: the leftover `.txn/files` is copied back over the show before the discard, i.e. restored instead of discarded.
- C8b OK. The `_discard_leftover` call becomes `pass`.
- C9 OK. The `package` arm's audio prune is disabled, so audio is snapshotted and rewritten.
- C10 OK. `.lock` is unlinked between steps (a) and (b), which is equivalent to "step (a) also unlinks .lock".
- C10b OK. The `.lock` filter in `_tracked_files` becomes `if True`.
- C11, C12, C13 OK. Each sets one view leg to a constant.
- C14 OK. `view = capture_view(sws)` is re-inserted directly before `with show_unit` in `fix`, i.e. after `_propose_and_confirm_titles`.
- C15 OK. The re-capture is in `_interactive_resolve` directly before the edit unit, after the picker.
- C16 OK. `if txn.exists()` becomes `if False`.

The tally checks out: each mutant was caught by its predicted test. C8b hit 2 of its 3 predictions; see below.

Method (drive.py, scratchpad/t8/drive.py):
- Fresh `rsync` copy per mutant, excluding `.venv`, `.git` and `.superpowers`.
- `PYTHONPYCACHEPREFIX` per mutant.
- `assert s.count(old)==1`, then a logged diff.
- Shadowing is asserted (`llama.__file__` startswith tree) and logged.
- Runs use `.venv/bin/python -m pytest` with `-p no:cacheprovider`.
- Predictions are encoded in the driver and logged as `PREDICT` before each run.
- A hit is counted only when a predicted id appears in the `FAILED` lines; the other failing ids are listed by name.
- Collection `ERROR`s are not counted as caught, which is conservative: they would read as SURVIVED.
- Baseline is 372 passed. The live worktree is untouched (`git status` clean).

### Independent re-runs
My own driver: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-small-fixes/9847639b-42e2-4b9c-a407-cb7d6c8a5ada/scratchpad/t8v/rerun.py
- **Copy method:** `git archive HEAD | tar -x`, a different method from the runner's rsync. A fresh dir per mutant, its own `PYTHONPYCACHEPREFIX`, run from the copy's cwd with `python -m pytest`.
- **Shadowing proof:** `llama`, `llama.show_unit`, `llama.stages.gather` and `llama.cli` `__file__` all asserted under `…/t8v/work/v-<name>-*/tree/packages/llama/src/…`, and logged.
- **Spelling:** where independent spelling was possible I wrote my own (B1 as `n < 1 or`, C8's restore loop, C10b dropping the `if` line).
- **Baseline:** the git-archive copy gives 372 passed.

| mutant | failing test ids | reproduced |
|---|---|---|
| B9 | test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string; test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict | Y |
| B1 (my spelling `n < 1 or`) | test_a_majority_keeps_the_consensus; test_venue_tie_break_unit_cases; test_1d_does_not_fire_without_a_selected_city_or_with_compatible_cities | Y (identical set) |
| C8 (my own hand-built restore) | test_show_unit::test_a_leftover_snapshot_is_deleted_not_restored; test_show_unit::test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit; test_redo_cmd::test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo | Y (identical set) |
| C8b | test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit; test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written | Y (and the plan's test passes, as reported) |
| C10b | test_the_lock_file_is_never_touched_by_a_failed_unit | Y |
| C14 | test_fix::test_fix_refuses_when_the_show_changed_after_the_prompt | Y |
| C15 | test_triage::test_a_triage_edit_whose_show_changed_meanwhile_refuses_and_changes_nothing | Y |

I also ran conditions the brief did not list (point 5). Each was predicted first and each was caught:

| extra mutant | caught by |
|---|---|
| X1: `.txn` prune in `_tracked_files` removed | test_a_failed_unit_restores_every_file_byte_identical plus 24 others |
| X2: `or sel.venue == candidate.venue` leg dropped | test_venue_tie_break_unit_cases |
| X3: `sel is None` leg dropped | test_venue_tie_break_unit_cases; test_selected_recording_missing_from_candidate_is_no_swap_and_no_1d |
| X4: the "removed" message branch disabled | test_a_removed_show_refuses_with_the_removed_message |
| X5: `sel_city is not None` half of the city gate dropped | test_a_tie_with_a_blank_selected_city_keeps_the_vote_city; test_venue_tie_break_unit_cases |

### Issues
#### Critical
None.

#### Important
None.

#### Minor
1. **C8b: the plan's predicted test cannot catch this variant, and no fix is needed.** `test_show_unit.py:95` plants only `.txn/files/show.json`. Under C8b, `take_snapshot` overwrites that file with the current bytes, the unit succeeds, and the final discard removes `.txn`, so nothing stale ever reaches the show. The variant is pinned behaviourally by:
   - `test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit` (`:136`): a ghost file absent from the show is written back by a failed unit's restore, and the `tree_bytes` equality fails.
   - `test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written` (`:143`): the refusal is missing, so `pytest.raises` fails.

   That is adequate.
2. **B12's catch comes from a call shape production never produces (informational).** It is caught only by the `stray` case in `test_venue_tie_break_unit_cases` (`test_stage_gather.py:3147`), where the selected recording is not in `candidate.recordings`. In production, `sel` is drawn from `candidate.recordings` and has a non-blank venue, so `n >= 1` always, the `n == 0` guard is unreachable, and B12 is equivalent in production. The pin is still legitimate: `venue_tie_break` is called directly as a unit.
3. **The fragile-catch check found nothing fragile.**
   - C13 is caught by a test that removes only `provenance.json`, so under the mutant there is no refusal at all. That is strong, not a message-only catch.
   - C11 and C12 assert both the refusal message and byte-identity.
   - X3 is caught through an `AttributeError` on `None`, which is a real behavioural failure on that input.
4. **Cosmetic: the runner's log starts with a malformed baseline line.** The first `BASE` block in t8-mut.log has `RESULT BASE: ............ [100%]`, apparently an earlier driver revision. The second `BASE` (372 passed) is the valid baseline.
5. **The brief's list did not enumerate every condition the spec's acceptance names (spec l.296-299).** The conditions it left out are X1-X5: the `.txn` exclusion, the same-venue leg, the `sel is None` leg, the removed-message branch and the `sel_city is not None` half. I ran them all (above) and all are caught, so the acceptance is met. Nothing needs adding.

### Assessment — Approved
The mutation run is sound. I reproduced all 7 re-runs exactly, from a differently built copy with proven shadowing, and the 5 extra conditions are also caught. No survivor needs a test.
