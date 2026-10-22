### Task 8: Mutation run on slice B's conditions and slice C's restore and re-resolve

**Files:** none committed, unless a survivor needs a test.

The recipe for each mutant (spec "Measurement and acceptance"; CLAUDE.md):
1. Write the predicted red test (`file::name`) down **before** flipping the mutant.
2. Fresh copy per mutant: `M=$(mktemp -d "$TMPDIR/mut-XXXX"); rsync -a --exclude .venv --exclude .git "$W/" "$M/tree/"`. Apply the mutant in `$M/tree` only.
3. Prove the shadowing: `cd "$M/tree" && PYTHONPATH="$M/tree/packages/llama/src:$M/tree/packages/herder/src" PYTHONPYCACHEPREFIX="$M/pyc" "$W/.venv/bin/python" -c "import llama; print(llama.__file__)"` must print a path under `$M/tree`.
4. Run with the same environment: `... "$W/.venv/bin/python" -m pytest <test files> -q`. Never use `.venv/bin/pytest`.
5. Record `mutant → predicted → caught by (test id) | SURVIVED`. A mutant counts as caught only by the predicted test or another named test, never by "some failure". A survivor gets a test (committed as `test: pin <mutant>`) or a written equivalence argument.

**Mutants (predicted red test in brackets):**

Slice B (`gather.venue_tie_break` and the chain), test file `test_stage_gather.py`:
- B1 count test `counts.get(sel.venue, 0) == counts.get(candidate.venue, 0)` replaced with `counts.get(sel.venue, 0) >= 1` [`test_a_majority_keeps_the_consensus`]
- B2 city gate removed [`test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged`]
- B3 returned city `sel_city or candidate.city` replaced with `sel_city` [`test_a_tie_with_a_blank_selected_city_keeps_the_vote_city`]
- B4 returns the raw `sel.venue` instead of the stripped one [`test_tie_ships_the_selected_recordings_string_without_jerrybase`]
- B5 the whitespace guard dropped (`sel.venue` truthiness only) [`test_a_whitespace_only_selected_venue_never_ships`]
- B6 no-event arm does not apply `tie` [`test_tie_ships_the_selected_recordings_string_without_jerrybase`]
- B7 unflagged-1a arm does not apply `tie` [`test_1a_tie_ships_the_selected_string_when_cities_agree`]
- B8 `tie` also applied in flagged 1a [`test_1a_tie_keeps_the_vote_when_the_cities_conflict`]
- B9 step 1 applies `tie` without testing it against jerrybase [`test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string`]
- B10 step 1's test on the selected string drops the city half [`test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict`]
- B11 `tie` applied in the `two_venue_signature` arm [`test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase`]
- B12 the `> 0` half of the count test dropped [`test_venue_tie_break_unit_cases`]

Slice C (`show_unit.py`; CLI view capture), test files `test_show_unit.py`, `test_fix.py`, `test_triage.py`, `test_redo_cmd.py`:
- C1 restore step (a) removed (new files kept) [`test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical`]
- C2 restore step (b) removed (no write-back) [same]
- C3 restore step (c) removed (new audio kept) [`test_redo_cmd.py::test_package_failure_on_purged_audio_removes_new_audio_and_restores_manifest`]
- C4 removed (the directory cleanup it targeted is not built)
- C5 `except BaseException` replaced with `except Exception` [`test_keyboard_interrupt_restores_and_re_raises`]
- C6 the `raise` after restore removed [`test_a_failed_unit_restores_every_file_byte_identical` (`pytest.raises`)]
- C7 `discard_snapshot` after restore removed [`test_a_failed_unit_restores_every_file_byte_identical` (`.txn` absent)]
- C8 a leftover snapshot restored instead of discarded [`test_a_leftover_snapshot_is_deleted_not_restored`]
- C9 snapshot includes `package/audio` [`test_existing_audio_is_never_snapshotted_or_rewritten`]
- C10 restore step (a) also unlinks `.lock` [`test_a_failed_unit_restores_every_file_byte_identical` (`ws.lock.exists()`)]
- C11 view check ignores `overrides` [`test_a_changed_show_refuses_and_changes_nothing[overrides]`]
- C12 view check ignores `show` [`test_a_changed_show_refuses_and_changes_nothing[show]`]
- C13 view check ignores `provenance` [`test_a_removed_show_refuses_with_the_removed_message`]
- C14 `fix` captures its view after the prompt instead of before [`test_fix.py::test_fix_refuses_when_the_show_changed_after_the_prompt`]
- C15 triage re-captures its view inside the branch, after the picker [`test_triage.py::test_a_triage_edit_whose_show_changed_meanwhile_refuses_and_changes_nothing`]

- [ ] **Step 1: Run every mutant by the recipe; fill in the table in the SDD ledger**
- [ ] **Step 2: Add a test for each survivor, re-run that mutant, and confirm it is caught**
- [ ] **Step 3: Full suite green on the unmutated worktree, then commit any added tests**

```bash
git add packages/llama/tests
git commit -m "test: pin mutation survivors (slices B/C)"
```

---

