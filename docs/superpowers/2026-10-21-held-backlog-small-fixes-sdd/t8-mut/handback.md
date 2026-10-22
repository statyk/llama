# Task 8 handback: mutation run (slices B and C)

Baseline (unmutated copy, same env, files test_stage_gather + test_show_unit + test_fix + test_triage + test_redo_cmd): `372 passed`, green.
Shadowing proof per mutant (logged as `SHADOW <name>: <path>`): `llama.__file__` printed a path under the mutant's own `tree/` every time; exact diff against the live worktree logged as `APPLIED <name>` (30 diffs, all non-empty); each replacement asserted to occur exactly once. Driver: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-small-fixes/9847639b-42e2-4b9c-a407-cb7d6c8a5ada/scratchpad/t8/drive.py (python -m pytest from the copy, PYTHONPATH + PYTHONPYCACHEPREFIX; predictions logged as `PREDICT` before each run). Full log with the failing test ids per mutant: t8-mut.log.

Tally: 30 mutants run (C4 retired by the plan, not run): 30 caught by the predicted test, 0 survived. One nuance: C8b (initial discard removed) was predicted to go red in three tests, two did; `test_a_leftover_snapshot_is_deleted_not_restored` did NOT fail on it (the stale show.json is overwritten by the new snapshot flow), so that variant is pinned by the two newer leftover tests, as the notes anticipated.

| mutant | mutation (first line) | predicted | result |
|---|---|---|---|
| B1 | `n == 0 or n != counts.get(candidate.venue, 0) or sel.venue =` -> `n == 0 or sel.venue == candidate.venue` | test_stage_gather.py::test_a_majority_keeps_the_consensus | hit 1/1; also red: 2 others (see log) |
| B2 | `if sel_city is not None and not cities_compatible(sel_city, ` -> `return _stripped` | test_stage_gather.py::test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged | hit 1/1; also red: 1 others (see log) |
| B3 | `return _stripped(sel.venue), sel_city or candidate.city` -> `return _stripped(sel.venue), sel_city` | test_stage_gather.py::test_a_tie_with_a_blank_selected_city_keeps_the_vote_city | hit 1/1; also red: 1 others (see log) |
| B4 | `return _stripped(sel.venue), sel_city or candidate.city` -> `return sel.venue, sel_city or candidate.city` | test_stage_gather.py::test_tie_ships_the_selected_recordings_string_without_jerrybase | hit 1/1; also red: 1 others (see log) |
| B5 | `if sel is None or not _stripped(sel.venue):` -> `if sel is None or not sel.venue:` | test_stage_gather.py::test_a_whitespace_only_selected_venue_never_ships | hit 1/1; also red: 0 others (see log) |
| B6 | `elif tie is not None:` -> `elif False:` | test_stage_gather.py::test_tie_ships_the_selected_recordings_string_without_jerrybase | hit 1/1; also red: 1 others (see log) |
| B7 | `elif tie is not None:` -> `elif False:` | test_stage_gather.py::test_1a_tie_ships_the_selected_string_when_cities_agree | hit 1/1; also red: 0 others (see log) |
| B8 | `if not cities_compatible(archive_city, jb_city):` -> `if not cities_compatible(archive_city, jb_city):` | test_stage_gather.py::test_1a_tie_keeps_the_vote_when_the_cities_conflict | hit 1/1; also red: 0 others (see log) |
| B9 | `if (tie is not None and venues_equivalent(tie[0], event.venu` -> `if tie is not None:` | test_stage_gather.py::test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string | hit 1/1; also red: 1 others (see log) |
| B10 | `if (tie is not None and venues_equivalent(tie[0], event.venu` -> `if (tie is not None and venues_equivalent(tie[0], event.venu` | test_stage_gather.py::test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict | hit 1/1; also red: 0 others (see log) |
| B11 | `elif two_venue_signature(candidate):` -> `elif two_venue_signature(candidate):` | test_stage_gather.py::test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase | hit 1/1; also red: 0 others (see log) |
| B12 | `n == 0 or n != counts.get(candidate.venue, 0) or sel.venue =` -> `n != counts.get(candidate.venue, 0) or sel.venue == candidat` | test_stage_gather.py::test_venue_tie_break_unit_cases | hit 1/1; also red: 0 others (see log) |
| C1 | `if rel not in saved:` -> `if rel not in saved and False:` | test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical | hit 1/1; also red: 8 others (see log) |
| C2 | `atomic_write_bytes(show_ws.dir / rel, (files / rel).read_byt` -> `pass` | test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical | hit 1/1; also red: 15 others (see log) |
| C3 | `if name not in keep_audio:` -> `if False:` | test_redo_cmd.py::test_package_failure_on_purged_audio_removes_new_audio_and_restores_manifest | hit 1/1; also red: 1 others (see log) |
| C5a | `try:` -> `try:` | test_show_unit.py::test_keyboard_interrupt_restores_and_re_raises | hit 1/1; also red: 2 others (see log) |
| C5b | `take_snapshot(show_ws)` -> `take_snapshot(show_ws)` | test_show_unit.py::test_a_failing_take_snapshot_discards_and_re_raises[KeyboardInterrupt] | hit 1/1; also red: 0 others (see log) |
| C6 | `discard_snapshot(show_ws)` -> `discard_snapshot(show_ws)` | test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical | hit 1/1; also red: 27 others (see log) |
| C7 | `restore_snapshot(show_ws)      # if this raises, .txn/ stays` -> `restore_snapshot(show_ws)` | test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical | hit 1/1; also red: 19 others (see log) |
| C8 | `_discard_leftover(show_ws)         # a leftover is deleted, ` -> `_lf = show_ws.dir / TXN_DIR / "files"` | test_show_unit.py::test_a_leftover_snapshot_is_deleted_not_restored; test_show_unit.py::test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit | hit 2/2; also red: 1 others (see log) |
| C8b | `_discard_leftover(show_ws)         # a leftover is deleted, ` -> `pass` | test_show_unit.py::test_a_leftover_snapshot_is_deleted_not_restored; test_show_unit.py::test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit; test_show_unit.py::test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written | hit 2/3; also red: 0 others (see log) |
| C9 | `elif rel_dir == Path("package"):` -> `elif False:` | test_show_unit.py::test_existing_audio_is_never_snapshotted_or_rewritten | hit 1/1; also red: 0 others (see log) |
| C10 | `for rel in sorted(saved):                          # (b)` -> `(show_ws.dir / '.lock').unlink(missing_ok=True)` | test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical | hit 1/1; also red: 2 others (see log) |
| C10b | `if rel != ".lock":` -> `if True:` | test_show_unit.py::test_the_lock_file_is_never_touched_by_a_failed_unit | hit 1/1; also red: 0 others (see log) |
| C11 | `overrides=_read(show_ws.overrides)` -> `overrides=None` | test_show_unit.py::test_a_changed_show_refuses_and_changes_nothing[overrides] | hit 1/1; also red: 2 others (see log) |
| C12 | `show=_read(show_ws.show))` -> `show=None)` | test_show_unit.py::test_a_changed_show_refuses_and_changes_nothing[show] | hit 1/1; also red: 0 others (see log) |
| C13 | `provenance=show_ws.provenance.exists()` -> `provenance=False` | test_show_unit.py::test_a_removed_show_refuses_with_the_removed_message | hit 1/1; also red: 0 others (see log) |
| C14 | `with show_unit(sws, view):` -> `view = capture_view(sws)` | test_fix.py::test_fix_refuses_when_the_show_changed_after_the_prompt | hit 1/1; also red: 0 others (see log) |
| C15 | `# The prompts above ran with no lock; edit and redo are one ` -> `view = capture_view(entry.ws)` | test_triage.py::test_a_triage_edit_whose_show_changed_meanwhile_refuses_and_changes_nothing | hit 1/1; also red: 0 others (see log) |
| C16 | `if txn.exists():` -> `if False:` | test_show_unit.py::test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written | hit 1/1; also red: 0 others (see log) |

Notes on mutant spelling: B1 = dropped `n != counts.get(candidate.venue, 0)` (leaves `n == 0 or sel.venue == candidate.venue`); B12 = dropped `n == 0 or`; C8 = leftover `.txn/files` copied back over the show before the discard (hand-built, since a leftover has no index.json for restore_snapshot); C8b = `_discard_leftover` call replaced by `pass`; C10 = `.lock` unlinked after step (a); C10b = `.lock` filter replaced by `if True`; C14 = `view = capture_view(sws)` re-inserted right before `with show_unit` in `fix`; C15 = same re-capture in `_interactive_resolve` just before the edit unit (after the picker). Multi-line mutations for B6-B11 are in the log diffs.

Survivors: none. No test added, nothing committed. Live worktree untouched (git status clean).
Final full suite on the unmutated worktree: `./.venv/bin/python -m pytest -q` -> 4041 passed, 1 skipped, 8 deselected.
