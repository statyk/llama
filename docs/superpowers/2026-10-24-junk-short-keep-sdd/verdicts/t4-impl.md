# Task 4 handback (t4-impl): the shared kept-list helper and fix's writer rules

Status: DONE_WITH_CONCERNS (concerns are judgement calls and Task 5 hand-offs; nothing blocked)
Commit (branch held-backlog-junk-filter, worktree junk-filter): 904eeb5
`feat(fix): writers translate show.json numbers, refuse legacy and stale positional edits`
Tests: `./.venv/bin/python -m pytest -q` -> 4922 passed, 1 skipped, 8 deselected, 4 xfailed
(baseline 4887 passed; +35 new test cases; the 4 strict xfails in test_triage.py are unchanged, none XPASSes).

## What I implemented
- `stages/gather.py`: `FinalKept` (frozen: `unexcluded`, `kept`, `excluded`, `ordering`) and
  `final_kept(files, overrides, want, *, short_keep=True)`: title_inputs' filter / include /
  exclude block moved verbatim, warnings included; `short_keep` passed to `filter_files`.
  `title_inputs` calls it, computes `recovery_basis`/format recovery from `fk.unexcluded` exactly
  as before, then takes `kept = fk.kept`. (Only observable difference: the exclusion's log
  warnings are now emitted before format recovery runs, instead of after. No output changes.)
- `cli.py`:
  - `_refuse_legacy(sws, slug)`: echoes `_legacy_message`'s text (legacy, or mixed per Task 3's
    ruling) to stderr, `typer.Exit(1)`.
  - `_stale(ia, config, sws, slug)`: show.json's filename list vs
    `gather.final_kept(ia.metadata(show.identifier)["files"], read_overrides(sws), FORMAT_BY_AUDIO[...]).kept`;
    returns the fixed staleness string or None.
  - `_keyed_files(sws, extra={}, cleared=())` per the brief's interface; `_exclusion_refusal(slug, file, key)`
    builds the fixed exclusion string with `--clear-title <file>` / `--clear-set-breaks` / `--clear-encore`.
  - `fix`: `_refuse_legacy(sws, entry.slug)` right after resolving the show, before `capture_view`,
    any flag parsing, prompt, lock or other refusal, on every invocation. `--untitled`: after its
    combination/show.json/provenance refusals, `_stale` runs before the counts check and the prompt.
    `--clear-title` accepts a filename (non-all-digit, removed as given; empty/blank is a parse error).
    Then: the `--suggest-titles` + file-edit combination guard (hoisted, no IO); positional flags
    (`--set-title`, `--set-breaks`, `--set-encore`, `--suggest-titles`) and a numeric `--clear-title`
    refuse without show.json (`refuse_no_show_json`); the positional flags except the numeric clear run
    `_stale`. Then, if `--exclude` is given: targets resolved (numbers through show.json, filenames as
    given) and checked against `_keyed_files(sws, extra, cleared)` where `extra` = this invocation's
    `--set-title`/`--set-breaks`/`--set-encore` files (through show.json) and `cleared` = its
    `--clear-title` items (`titles:<file>`), `set_breaks` for `--clear-set-breaks` OR `--set-breaks`,
    `encore_after` for `--clear-encore` OR `--set-encore`. Every hit prints its exclusion line; exit 1.
    All before the unit, so it holds with or without `--no-run`.
  - `_propose_titles_for_show`: `kept = final_kept(md["files"], entry.overrides, want).kept`; the C1
    decline stays as the second line of defence. Docstring (A1 paragraph), C1 comment and the I2
    guard comment on `--suggest-titles` rewritten to the filename form (no more "applied by 1-based
    position").

## TDD evidence (log: t4-impl.log)
RED before any implementation:
- test_stage_gather: `test_final_kept_is_title_inputs_block` failed (ImportError: final_kept);
  `test_title_inputs_unchanged_by_final_kept` (pin) passed on 853239a, as a pin must; its literals
  were captured on 853239a before the refactor.
- test_fix: 30 failed: all 8 `test_every_fix_flag_refuses_a_legacy_file[*]`, all 5
  `test_positional_edit_refuses_when_stale[*]`, `test_exclude_and_title_on_the_same_file_refuses`,
  all 12 `test_exclusion_refuses_a_keyed_file[*]`, `test_replacing_a_key_frees_its_old_file_for_exclusion`,
  `test_clear_flags_work_without_show_json`, `test_clear_title_by_filename_skips_the_staleness_check`,
  `test_suggest_titles_kept_list_comes_from_final_kept` (AttributeError: final_kept).
  Passed already (stated, not hidden): `test_a_fresh_show_passes_the_staleness_check` and
  `test_exclude_with_its_own_clear_is_allowed` (positive controls: no check existed to block them),
  `test_exclude_then_title_numbers_are_show_json_numbers` (Task 3's show.json translation already
  delivers the behaviour change against v2.17.0; on this branch it is a pin).
GREEN: all 38 selected pass; then the full suite (below).

New tests (test_fix.py unless named):
- test_stage_gather.py: `test_title_inputs_unchanged_by_final_kept` (pin; gd73, include the spam file,
  exclude d2t01: kept, excluded rows, ordering, recovery_basis, and the list `build` receives, all
  literal); `test_final_kept_is_title_inputs_block` (+; unexcluded/kept/excluded/ordering, the three
  warnings verbatim, `short_keep` reaching `filter_files` True/False).
- `test_every_fix_flag_refuses_a_legacy_file` (8 flags as in the brief, `input=""`, exit 1, legacy
  text in output, whole show dir byte-identical, no redo, no prompt; `_propose_titles_for_show`
  patched to fail if reached).
- `test_positional_edit_refuses_when_stale` (windsor's show.json without short-kept D3_T02, i.e. what a
  pre-rule gather left; parametrised over --set-title/--set-breaks/--set-encore/--suggest-titles/
  --untitled; exact staleness string; byte-identical; then `--clear-set-breaks` succeeds and redoes).
- `test_a_fresh_show_passes_the_staleness_check` (+; windsor gathered under the rule: `--set-title 17=`
  lands on GD_022474_D3_T02.mp3, the short-kept file).
- `test_exclude_then_title_numbers_are_show_json_numbers` (windsor, literally `--exclude 3 --set-title 7=X`).
- `test_exclude_and_title_on_the_same_file_refuses` (Review Focus 3: `--exclude 3 --set-title 3=X`, exact
  exclusion string with `--clear-title <file>`, byte-identical, no redo).
- `test_exclusion_refuses_a_keyed_file` (3 keys x {`4`, filename} x {with, without --no-run} = 12).
- `test_exclude_with_its_own_clear_is_allowed` (`--exclude 4 --clear-title 4 --no-run`; `--exclude 4 --clear-encore`).
- `test_replacing_a_key_frees_its_old_file_for_exclusion` (+; decision 2 below, both directions).
- `test_clear_flags_work_without_show_json` (dangling filename title/break/encore cleared with no
  show.json; `--set-title 1=X`, numeric `--clear-title 1`, `--set-breaks 2`, `--set-encore 2` refuse
  naming `llama redo <slug> --from gather`, byte-identical).
- `test_clear_title_by_filename_skips_the_staleness_check` (+; stale windsor show).
- `test_suggest_titles_kept_list_comes_from_final_kept` (decision 1 below).

## Step 4 dry run (19 failures in the full suite before editing any existing test)
test -> clause -> update
- test_fix: test_set_title, test_set_breaks_and_clear, test_set_encore_and_clear,
  test_set_encore_composes_with_set_breaks, test_set_encore_redoes_from_gather,
  test_set_title_writes_the_show_json_filename -> 4.2 staleness (hand-built show.json: `make_show`'s
  `a.mp3`, or `_six_track_show`'s hand-written tracks) -> `_six_track_show(tmp_path, monkeypatch)` now
  writes gd73's REAL gather (its six kept files are exactly `_SIX`, asserted) and stubs `cli.IAClient`;
  test_set_title/test_clear_title expect `_SIX[0]` instead of `a.mp3`.
- test_fix::test_clear_title_non_numeric_errors_cleanly -> 4.2 AUTHOR'S CALL (`--clear-title` takes a
  filename) -> renamed `test_clear_title_non_numeric_is_a_filename`: `abc` is a filename (no-op, exit 0,
  stored title untouched); a blank value is the parse error `--clear-title expects a track number or a filename`.
- test_fix, 10 `--untitled` tests (test_untitled_is_refused_when_any_track_is_resolved,
  _lists_filenames_and_declining_writes_nothing, _one_confirmation_writes_titles_narration_and_one_set_then_redoes,
  _clears_a_pre_existing_encore_so_the_tape_is_one_set, _declined_says_so_exits_zero_and_leaves_overrides_alone,
  _confirmed_but_still_held_says_still_held_not_declined, _overrules_remaining_flags_then_continues_from_brief,
  _is_refused_when_only_some_tracks_are_resolved, test_untitled_failure_after_the_overrule_restores_everything)
  -> 4.2 staleness (`--untitled` is positional; hand-built `t01..t03` show.json) -> `_all_unresolved_show(tmp_path,
  monkeypatch, *, empty=False)` = gd73's real gather with every title unresolved; expectations moved to
  `_SIX` names and 6 tracks (`(1 of 6 resolved)`, `(6 of 6 resolved)`, `   6  gd73-06-10d3t01.mp3`,
  `Untitled (track 1..6)`).
- test_fix::test_untitled_is_refused_on_a_zero_track_show -> did NOT fail, but only because the
  un-stubbed IAClient fetched archive.org item "gd73" over the NETWORK (no files -> kept [] == 0 tracks).
  Converted (`empty=True`: metadata with no files, so final kept list [] == 0 tracks, offline).
- test_fix::test_clear_title -> did NOT fail (its `--set-title` silently refused stale; the clear then
  removed nothing) -> converted to the gathered show and now asserts the title was set first.
- test_fix::test_fix_refuses_when_the_show_changed_after_the_prompt -> 4.2 staleness (`--suggest-titles`
  on `make_show`) -> `_gd73_show(needs_review=True)`; its "changed by another command" assertion unchanged.
- test_cli::test_suggest_titles_declines_when_show_json_is_stale_against_pending_exclude and
  test_suggest_titles_c1_staleness_guard_still_fires_before_donor_work -> 4.2 staleness check runs before
  any prompt (fix now refuses with exit 1 and the staleness string instead of exit 0 and the C1
  decline) -> CLI half asserts the new refusal (exit 1, titles untouched, no table); the C1 decline is
  still pinned by calling `_propose_titles_for_show` directly (its "23 files kept"/"24 tracks on disk"
  text; the second with `_sibling_proposal` patched to record, asserting no donor work).
No failure was left untied to a clause. test_triage.py: untouched; its 4 strict xfails still xfail.

Network check: the first dry run took 270 s instead of ~80 s because the un-converted tests reached
archive.org through a real IAClient. After conversion the full suite was run with a recording-only
plugin wrapping `IAClient._get` (scratchpad, `-p netspy`): every recorded call is from
test_ia_client.py (its own mocked transport); none from fix/cli/gather tests. Suite 73 s.

## Files changed
packages/llama/src/llama/stages/gather.py, packages/llama/src/llama/cli.py,
packages/llama/tests/test_fix.py, packages/llama/tests/test_cli.py, packages/llama/tests/test_stage_gather.py.

## Decisions
1. `--suggest-titles` calls `final_kept` TWICE (the staleness check, then the proposal), not once as the
   brief's test line says: spec 4.2 requires both comparisons to use the one helper, and `_stale`'s
   interface returns only the message, so it cannot hand its list on. The test asserts the CLI path's two
   calls both carry the stored overrides, and that `_propose_titles_for_show` alone calls it once with them.
2. A same-invocation `--set-breaks`/`--set-encore` counts as clearing the stored value for the exclusion
   check (it replaces it), and its new files count as keyed. So `--exclude 4 --set-breaks 2` is allowed
   when 4 was the stored break, and `--exclude 3 --set-encore 3` refuses. Pinned.
3. A file carrying several keys is reported with the first in titles, set_breaks, encore_after order;
   clearing it reveals the next. Every excluded target that hits prints its own line before exit 1.
4. Out-of-range numbers are skipped when building the exclusion check's `extra` (the writer refuses them
   with `no track N` inside the unit anyway).
5. `_stale` lets an `IAError` from `ia.metadata` propagate (fails loud, never treated as "not stale").
   In production gather has cached the metadata.
6. The `--suggest-titles` + `--exclude/--unexclude/--include` guard was hoisted above the positional
   checks (it needs no IO and its message is more specific). `--exclude` targets are resolved a second
   time before the unit for the keyed check; the in-unit resolution and the clash check stay where they
   were (test_a_typer_exit_inside_the_unit_leaves_the_show_byte_identical pins an Exit inside the unit).
7. `--set-breaks ","` (forced no breaks) counts as positional and is stale-checked; conservative.
8. `--clear-title <filename>` naming no stored title is a silent no-op (redo/stage still happens), like
   `--unexclude` of an unlisted file. A blank value is a parse error.

## Self-review
- Fixed strings (legacy via Task 3's helper, staleness, exclusion) asserted character for character.
- Every refusal added is before `show_unit` (no `.txn`, byte-identical tree asserted) and before any
  prompt (`input=""` and prompt text absent asserted).
- Ordering: legacy refusal is the first thing after show resolution, ahead of the --untitled combination
  refusals, parse errors and "nothing to fix".
- Protected-name grep over the diff: only reads of `FORMAT_BY_AUDIO`; none of the other names appear.
- Lock order untouched; `_stale` and the keyed check read files with no lock held, and the unit's view
  check re-verifies them, as the existing refusals do.

## Concerns
- Decision 1 deviates from the brief's literal "calls it once".
- The dry run showed tests silently reaching the network through an un-stubbed `IAClient` once `fix`
  reads metadata; two passed by accident that way. Task 5 should expect the same when triage gains
  `_stale`: any triage test doing a positional edit needs `cli.IAClient` stubbed and a show.json that IS
  gather's kept list (`_all_unresolved_show`/`_gd73_show` in test_fix.py are reusable patterns).
- Task 5 hand-offs: triage `[t]` still reaches `_propose_titles_for_show` without `_stale` (C1 catches it);
  triage `[e]` has no keyed-file exclusion refusal yet; triage's legacy refusal should reuse `_refuse_legacy`
  (it raises `typer.Exit`, so triage may want `_legacy_message` directly to stay in the walkthrough).
- The `--suggest-titles` combination refusal's text ("renumbers tracks before the proposal's numbering
  would apply") is left as is; still true enough, but it predates filename keys.
