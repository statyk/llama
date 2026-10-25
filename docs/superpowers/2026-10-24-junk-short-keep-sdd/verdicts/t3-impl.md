# Task 3 handback (t3-impl): filename-valued positional overrides

Status: DONE_WITH_CONCERNS (concerns are judgement calls, listed below; nothing blocked)
Commits (branch held-backlog-junk-filter, worktree junk-filter):
- 08a35fd feat(overrides): override_keys, the legacy test and the migration's mapping
- 853239a feat(overrides): filename-valued positional overrides, one resolver
Tests: `./.venv/bin/python -m pytest -q` -> 4887 passed, 1 skipped, 8 deselected, 4 xfailed
(baseline was 4856 passed; +31 new tests; the 4 xfails are the test_triage ones below).
Commit 1 was checked green on its own staged tree: extracted with `git archive $(git write-tree)`
into the scratchpad and run from there with PYTHONPATH shadowing (llama.__file__ confirmed inside
the copy, Overrides still `dict[int, str]`): 4877 passed, 1 skipped, 8 deselected.

## What I implemented
- `packages/llama/src/llama/override_keys.py` (new): `POSITIONAL_KEYS`; `legacy_int` (pydantic
  `TypeAdapter(int).validate_json(json.dumps(v))`, else None); `classify` (none/legacy/filename/
  mixed over titles keys, set_breaks items, encore_after; `[]`/None/missing add nothing);
  `filename_values`; `rekey_raw` (deep copy, only the three keys change, top-level and titles key
  order kept, filename values left alone, IndexError outside 1..len, including 0 and negatives);
  `legacy_message`, `mixed_message`, `dangling_message` (the fixed strings verbatim), `refusal`
  (mixed first, then legacy); `Positions` (frozen dataclass); `resolve_positions` (mixed, then
  legacy, then every dangling key in ONE message, de-duplicated, in key order).
- `packages/llama/tests/fixtures/overrides_v2_17_0.py` (new): e37f670's `Overrides` verbatim as
  `OverridesV2170`, with that file's `from __future__ import annotations` and pydantic import, plus
  a header naming the commit.
- `models.Overrides`: `titles: dict[str, str]`, `set_breaks: list[int | str] | None`,
  `encore_after: int | str | None` (types only, plus a comment).
- `stages/gather.py`: `title_inputs(..., slug: str)` (required kwarg) runs
  `resolve_positions(overrides, [f["name"] for f in kept], slug=slug)` right after the exclusion,
  before the canonical build; `TitleInputs.positions: Positions`; `title_cascade` reads
  `inp.positions.titles` everywhere it read `overrides.titles` (overridden set, 2b/2c/2d skips,
  the override loop); `compute_gather` passes `slug=slugify(candidate.performance_id)` and the
  structure-override branch plus the `StructureInfo` branch read `positions.set_breaks` /
  `positions.encore_after`. `_validate_structure_override` and `_sets_from_breaks` unchanged.
- `cli.py`: `_legacy_message(sws, slug)`; `_edit_overrides` keeps its signature, refuses
  (LlamaError, nothing written) via `_legacy_message`, and translates `set_titles` keys,
  `set_breaks` items, `encore_after` and all-digit `clear_titles` items through
  `show.json` `tracks[n - 1].filename` (lazily read once). Out of range ->
  `no track N (show has M tracks)`; no show.json when a number needs translating ->
  `track N names a file through show.json, which is missing; rebuild it with: llama redo <slug>
  --from gather`. Non-digit `clear_titles` items are removed as given. Slug = `show_ws.dir.name`
  (the library dir, as `_resolve_exclude_tokens` already does).
- `scripts/title_hygiene_probe.py`: passes `slug=slugify(cand.performance_id)`.

## TDD evidence
RED (before any implementation; log t3-impl.log):
- `test_override_keys.py`: collection error `ModuleNotFoundError: No module named 'llama.override_keys'`.
- 9 failed: test_iter_shows_lists_legacy_migrated_and_mixed (ValidationError on filename keys),
  test_delmccoury_shape_through_gather, test_gather_refuses_a_legacy_overrides_file,
  test_filename_title_follows_its_file_across_an_insertion, test_set_title_writes_the_show_json_filename,
  test_edit_overrides_translates_through_show_json, test_edit_overrides_needs_show_json_to_translate,
  test_edit_overrides_refuses_a_legacy_file, test_legacy_message (AttributeError).
GREEN: those plus test_override_keys (27 incl. parametrised) all pass.

New tests (all named in the brief, plus a few extras marked +):
- test_override_keys.py: test_legacy_agrees_with_the_v2_17_0_model (13 probes, set_breaks item and
  titles key, oracle = vendored model), test_legacy_values_spec_pins (spec 4.1's list explicitly),
  test_old_model_rejects_a_migrated_file (3), +test_new_model_parses_every_form, test_classify,
  +test_classify_through_the_model, +test_filename_values_lists_every_filename_valued_entry,
  test_rekey_raw_maps_only_positional_keys_and_keeps_the_rest, +test_rekey_raw_refuses_a_number_outside_the_list,
  test_filename_keys_with_dir_prefix_and_spaces_round_trip (Review Focus 4: `<id>/gd74 d1t02.mp3`,
  `GD_022474_D3_T02.mp3`), +test_resolver_maps_filenames_onto_the_kept_list (None vs [] presence),
  test_resolver_refusals (exact legacy, mixed and two-key dangling strings).
- test_catalog.py: test_iter_shows_lists_legacy_migrated_and_mixed.
- test_stage_gather.py: test_delmccoury_shape_through_gather (windsor, 18 filename titles +
  `set_breaks: []`), test_gather_refuses_a_legacy_overrides_file (asserts the library slug, the ws
  dir being `show`), test_filename_title_follows_its_file_across_an_insertion (windsor D3_T03 keeps
  its title at track 18 behind short-kept D3_T02; encore by filename lands at 27).
- test_fix.py: test_set_title_writes_the_show_json_filename (CLI, --no-run; titles, breaks, encore,
  numeric clear), +test_edit_overrides_translates_through_show_json (out of range incl. 0, `[]`),
  +test_edit_overrides_needs_show_json_to_translate (and filename clears still work without it),
  test_edit_overrides_refuses_a_legacy_file (5 edit kinds, byte-identical), +test_legacy_message.

## Step 4 dry run (86 failures before editing any existing test; full list in the log)
test -> clause -> action
- test_title_cascade.py, 24 tests via `_inputs_like_gather` (all `test_gather_threads_enabled_slices_to_the_cascade[*]`,
  test_cascade_cases_are_not_vacuous, test_gd73_chosen_canonical_s_fill_survives, test_each_slice_runs_at_its_place,
  test_s_declines_are_what_stop_setlist_gap, test_d_reuses_the_sibling_donor, test_donor_closures_return_none_without_durations,
  test_c_changed_stems_leave_2b_and_fetch_and_notes, test_c_declines_without_a_reference_and_2b_stands,
  test_wholly_untagged_evaluated_after_c, test_exclusion_changes_the_count_d_sees, and in test_stage_gather
  test_short_kept_file_votes_like_any_kept_file) -> interface `title_inputs(..., slug)` -> helper passes
  `slug=slugify(cand.performance_id)`.
- test_title_cascade: test_gather_threads...[*-overrides] (titles {1,2}), test_cascade_out_of_range_override_raises_like_gather
  ({9}), test_override_positions_are_not_s_positions ({6}), test_overrides_survive_every_new_rung_and_anchor_check_3
  ({2,6} x2), test_shifted_set_demotion_never_touches_an_override ({3}) -> 4.1 filename values -> converted to the
  file each number named (out-of-range one becomes a dangling filename; both paths still raise equal messages).
- test_stage_gather: test_override_path_leaves_matched_unmeasured (Task 1's `encore_after=27` -> `GD_022474_D4_T06.mp3`,
  break 11 -> `GD_022474_D2_T01.mp3`; the "re-keyed by filename in Task 3" comment replaced),
  test_gather_title_override_forces_title, test_gather_title_override_out_of_range_errors (-> dangling, match added),
  test_gather_set_breaks_override_numbers_sets, test_gather_encore_override_labels_tracks_and_implies_a_break,
  test_2b_never_judges_an_override_title, test_2a_never_judges_an_overridden_position,
  test_structure_override_bypasses_the_taper, test_short_kept_survives_to_show_json -> 4.1 (ValidationError on int
  title keys, or the resolver's legacy refusal on int breaks) -> converted to filenames.
  Also converted though still passing (they would have passed for the wrong reason, the legacy refusal):
  test_gather_set_breaks_out_of_range_errors (`[99]` -> break after the last file, `match="out of range"`),
  test_overrides_accepts_encore_after (filename form, legacy int still parses).
- test_fix.py: test_set_title (stored `{"a.mp3": ...}`), test_set_breaks_and_clear / test_set_encore_and_clear /
  test_set_encore_composes_with_set_breaks / test_set_encore_redoes_from_gather (`9,17`/`16` on a 1-track
  show.json now refuse `no track N`; moved to a 6-track show.json with in-range numbers) -> 4.2 translation.
  test_untitled_one_confirmation_writes_titles_narration_and_one_set_then_redoes (titles stored by t01..t03),
  test_untitled_clears_a_pre_existing_encore_so_the_tape_is_one_set (show uses gd73's filenames so the real gather
  resolves the written keys; `_all_unresolved_show` gained `names=`), test_untitled_gather_makes_no_align_structure_call,
  `_billy_shape` (test_a_refused_structure_fix_leaves_every_file_byte_identical, test_no_run_stages_bad_overrides...:
  encore stored as show.json track 20's filename), test_a_fix_adding_one_override_keeps_the_others,
  test_fix_on_a_show_with_no_show_json_takes_metadata_and_filename_edits (legacy breaks would now refuse the
  writer) -> 4.1/4.2 -> converted. Also converted (passing): test_untitled_declined_says_so... (`encore_after=2`).
- test_cli.py, 10 suggest-titles tests (test_suggest_titles_writes_every_row_into_overrides,
  test_explicit_set_title_wins_over_the_proposal, test_never_clobbers_a_track_that_already_has_a_title,
  test_untagged_fixture_with_tagged_donor_renders_sibling_proposal, test_operator_band_sibling_titles_diverge_from_the_canonical_dp,
  test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows, test_below_floor_donor_with_usable_canonical_falls_through_to_dp,
  test_weak_evidence_decline_keeps_the_dp_candidate_out_of_the_write, test_best_donor_picks_the_higher_agreement_donor_not_the_worse_one,
  test_operator_band_donor_untitled_on_the_gaps_falls_through_to_the_dp) -> 4.2 stored values are filenames ->
  read back through a new `_titles_by_track(sws)` helper that asserts every key is a show.json filename and maps
  it to its track number, so the number-keyed expectations (ANCHORED_GAPS etc.) stay readable.
- test_reapply.py::test_reapply_on_refused_overrides_raises_and_writes_nothing -> 4.1 (legacy refusal changed the
  message the regex expects) -> filename breaks/encore; the encore-ordering refusal still fires.
- test_workspace.py::test_overrides_metadata_fields_round_trip -> 4.1 types -> filename round trip.
- scripts/test_replay_holds.py::test_strip_mode_removes_only_structure_overrides (row unreplayable via the legacy
  refusal) -> `_OVERRIDES` converted to gd73 filenames, and the literal stripped/seen expectations in that test,
  test_strip_titles_removes_only_titles and test_both_strip_flags_together updated to match.
- scripts/test_title_hygiene_probe.py (7: test_gate0_parity_on_fixtures, test_gate0_reports_the_first_difference,
  test_strips_titles_and_structure_overrides_in_the_shadow, test_arms_present_and_slice5_applied_last,
  test_alternatives_present, test_jobs_workers_capture, test_refuses_out_inside_library; all the library
  fixture's int title keys) -> 4.1 -> filenames (windsor without D3_T02, so tracks 1/4/10 = D1_T01/D1_T04/D1_T10),
  stripped expectation updated. The `slug=` argument was the probe's own change, not a test edit.
- test_triage.py: test_metadata_action_writes_overrides_and_redoes_gather, test_metadata_empty_input_keeps_values_and_returns_to_prompt
  (`9,17` on a 1-track show.json now `no track 9`), test_suggest_titles_resolution_writes_overrides_and_redoes_gather,
  test_suggest_titles_sibling_arm_shares_the_triage_seam (stored keys are filenames) -> 4.2 -> marked
  `pytest.mark.xfail(strict=True, reason="re-keyed in Task 5")`, otherwise unedited.
- test_show_cmd.py: no failures, untouched.
No failure was left untied to a clause.
Not converted (harness rows, not overrides.json files; Task 6's re-key): scripts/test_replay_holds.py:1390 and
scripts/test_taper_probe.py:318-321 build synthetic arm rows with `stripped={"set_breaks": [2], ...}`.

## Step 5 greps (also in 853239a's message)
`grep -rn "\.titles\b\|\.set_breaks\b\|\.encore_after\b" packages/llama/src scripts` -- Overrides readers left:
- override_keys.resolve_positions: the resolver.
- cli._edit_overrides: the writer (translates).
- cli._metadata_editor (`ov.titles`, `ov.set_breaks`): triage [m]'s defaults, Task 5. Accepting a filename
  default unchanged writes nothing; editing one fails its `N=Title` parse. Never mis-points.
- cli._print_show_entry / _print_show_json: print the mapping as stored (spec 4.2 Readers).
- gather reads `positions.*` only; `overrides.*` strings in `_validate_structure_override` are message text.
- replay.py:228/251, manifest.py:26: `Show.set_breaks` (play-order), not overrides.
- scripts/replay_holds.py strips the keys by name (Task 6).
- everything else in the grep is `.titles` of non-Overrides objects (LosslessResult, TagLayer, DonorTape,
  replay rows) or import lines/comments.
`grep -rn "\.index\b" packages/llama/src scripts packages/emcee/src` -- Track.index readers: package.py
(output names, ID3 track, manifest index, from the current show.json), structure.py/jerrybase.py/titles.py
(play order within one gather), gather/title_hygiene note text and the LLM prompt rows, replay.py diff rows,
cli displays (`_pick_excludes`, `--untitled` listing, proposal tables) and number->filename lookups
(`_resolve_exclude_tokens`; proposal picks and `--untitled` numbers go through `_edit_overrides`'
show.json translation), probe/regather_diff displays. None is a persisted positional key (spec 8 premise 5).
emcee: no Track.index reader. `grep -rn overrides packages/emcee/src packages/transmitter/src`: no reader
(English uses of the word only).

## Files changed
New: packages/llama/src/llama/override_keys.py, packages/llama/tests/fixtures/overrides_v2_17_0.py,
packages/llama/tests/test_override_keys.py.
Modified: packages/llama/src/llama/models.py, packages/llama/src/llama/stages/gather.py,
packages/llama/src/llama/cli.py, scripts/title_hygiene_probe.py; tests test_catalog.py, test_cli.py,
test_fix.py, test_reapply.py, test_stage_gather.py, test_title_cascade.py, test_triage.py (xfail marks only),
test_workspace.py, scripts/test_replay_holds.py, scripts/test_title_hygiene_probe.py.

## Decisions
1. `_legacy_message` returns the MIXED message for a mixed file, not None. The brief's interface says "the
   legacy refusal text when classify == legacy, else None", but spec 4.1 says writers refuse "when the show's
   file holds any legacy value", and a mixed file does. Returning None would let `fix --no-run` write to a
   mixed file that gather then refuses. Task 4's `_refuse_legacy` and Task 5's triage check inherit this.
   Pinned in test_legacy_message. Easy to revert (one branch in `override_keys.refusal`) if the orchestrator
   prefers the brief's literal reading.
2. The dangling message keeps `--clear-title <file>` literally as the usage placeholder (the fixed string
   lists the three routes once for however many keys are named before it); only `<slug>` and the
   `<key> <file>` list are substituted.
3. The no-show.json translation error text is mine (the brief fixes only that it names
   `llama redo <slug> --from gather`): `track N names a file through show.json, which is missing; rebuild it
   with: llama redo <slug> --from gather`.
4. `title_cascade`'s own `overrides.titles: no track k` check is kept (now over resolver positions), though
   the resolver makes it unreachable from gather: a defence for a hand-built `TitleInputs`.
5. Two commits instead of three: the model change breaks the CLI writers' tests until the translation lands,
   so model + gather + cli + conversions are one green state. Commit 1 (keys module, vendored model, the
   model-independent tests) is green on its own; the five model-dependent key tests land in commit 2.
6. test_cli conversions read stored titles back through `_titles_by_track` (asserting every key is a
   show.json filename) instead of rewriting each number-keyed expectation as literal filenames.

## Self-review
- Fixed strings checked character for character against global-constraints.md in test_resolver_refusals and
  test_gather_refuses_a_legacy_overrides_file / test_edit_overrides_refuses_a_legacy_file.
- The resolver runs on the post-exclusion kept list and before `build(kept)`, so a refused file costs no
  canonical build; replay/reapply get the library slug through `candidate.performance_id`.
- `[]` presence semantics: preserved by the model, the resolver (`Positions.set_breaks == []`) and
  `_edit_overrides` (`set_breaks=[]` needs no translation; `--untitled` still writes `[]`).
- Protected names: the only diff line touching one is the probe call passing `FORMAT_BY_AUDIO` unchanged.
- `_edit_overrides` translates everything before the single write, so a refusal writes nothing.

## Concerns
- Decision 1 deviates from the brief's literal `_legacy_message` contract (spec-faithful, but flagging it).
- Stale comments left for Task 4, which owns that code: cli.py's `--suggest-titles` I2 guard comment and
  `_propose_titles_for_show`'s C1 comment still say `overrides.titles` is applied "by 1-based position".
  The refusal and decline they explain still hold.
- `fix --clear-title <filename>` is still refused at the CLI parse (`--clear-title expects a track number`):
  `_edit_overrides` already accepts a filename, but the flag change is Task 4's (plan).
- triage [m] shows filename keys in its defaults until Task 5 (4 tests xfailed strict).
