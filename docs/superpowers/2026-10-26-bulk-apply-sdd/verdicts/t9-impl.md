# Task 9 handback: `reapply` for packaged, briefed and delivered shows

Status: DONE_WITH_CONCERNS
Commit: a2e0f20b feat(reapply): every state, inside show_unit, strict reuse, processed
Suite: `./.venv/bin/python -m pytest -q` -> 6178 passed, 1 skipped, 8 deselected (was 6159; +19 new test cases)

## What I implemented
- `reapply_show` (packages/llama/src/llama/reapply.py), following the brief's flow order:
  1. Every write runs inside `show_unit(ws, None)`; a dry run takes only `file_lock`. reapply's
     own audio/manifest undo, `discard_aside` and `put_back` calls are gone (the unit does both).
  2. `campaign.read_record` (`CampaignUnreadable` propagates). A last mark with start `select`
     gives `skipped: re-selection (llama redo <slug> --from select)`. For a non-held show, a
     record that is not awaiting and has `processed` gives `skipped: processed`. Then the
     existing digest check.
  3. Held shows keep `classify`'s path and outcomes.
  4. Non-held: flags -> held commit (today's held writes, `drop:brief` included). No flags, no
     `visible_changes`, `legs.brief == "reuse"`, and NOT (awaiting and delivered and
     `destination_voiced` is False) -> `show.json`-only commit, outcome `label-only` if
     `shipped_diff` has any value, else `unchanged`. Otherwise brief (reuse/fresh) + package ->
     `cleared`.
  5. The structure gate applies to every state (non-held: `_structure_changed(shipped_diff)`).
  6. A show on the package route plans reuse before the fresh brief. For a delivered show this is
     `plan_reuse(strict=not allow_download)`, then `check_pairs`, then `destination_voiced`, which
     the purge rider needs. Every station read raises `StationUnreadable` (no `delivery_path`
     too), except that with `allow_download` an unreadable copy reads as unvoiced.
  7. The first write of a packaged or delivered show is `write_anchor_if_absent`. `show.json`
     stays the commit marker. After it come `campaign.mark_processed(ws, held=bool(flags))`;
     then, for a cleared delivered show with a voiced destination, `purge_package_audio` with
     its result echoed; then `after_commit(ws)`, all inside the unit. Each package echoes
     `<slug>: audio reused r, downloaded d` (`build_package(..., tally=...)` is threaded).
- `ReapplyOutcome` gains `kind` (`fresh`/`reuse`/`needs-llm`/`label-only`/`none`), `audio`
  (`{"reused", "downloaded"}` after a package) and `align_reproduced` (None; Task 10).
  `reapply_show` takes `with_gather_llm` (accepted, unused until Task 10), `allow_download` and
  `after_commit`.
- cli `reapply`:
  - Takes `--allow-download`. With `--from-list`, or with more than one name, it refuses with
    `--allow-download takes one named show`.
  - A strict refusal on the names form prints `FAILED <slug>: <reason>`, then the
    `  if the station copy cannot be fixed: re-run this one show with --allow-download` hint.
  - In the list dry-run summary, briefs and downloads are counted only for rows that package
    (`cleared`, `needs-brief`, `structure-changed`), so `label-only`/`unchanged` count nothing.
  - The help text and short_help no longer say "held".
- `cli._is_delivered` and `reapply._delivered` are now one helper, `ledger.is_delivered`.
- Review Focus 5: `_reapply_list` still builds its `CatalogEntry` without `awaiting_fix`, which
  is safe because `reapply_show` never reads `entry.awaiting_fix`. It reads `campaign.json`
  itself, so an unreadable record raises `CampaignUnreadable` (a `LlamaError`). The list runner
  records that as a retryable failure (tested).

## Dry-run list (Step 1, before any edit; also in t9-impl.log)
Each existing `test_reapply.py` expectation that moved, with the clause behind it:
1. `test_a_show_no_longer_held_is_skipped`: asserted `skipped: not held` on a briefed, unheld
   show. **Reapply extended** (spec "Re-processing", flow step 4): the show now takes the
   `show.json`-only commit (`unchanged`, written `["show.json"]`). Renamed to
   `..._is_reapplied_extended`.
2. `test_cli_reapply_names_form`: delivered, with a `delivery_path` but no station dir.
   **Strict reuse** (flow step 6, spec "Audio reuse never silently falls back"): the test now
   creates a station copy that pairs.
3. `test_reapply_hint_suppressed_for_a_voiced_destination[*]`: **strict reuse** (flow step 6).
   - `voiced` and `unvoiced` now get a station manifest that pairs.
   - `unreadable`, `missing` and `no delivery_path` now run with `--allow-download`, so the
     test still checks the hint.
4. `test_reapply_flags_a_delivered_show_for_redelivery_and_writes_no_ledger_row`: delivered with
   no `delivery_path`. **Strict reuse**: it now runs with `allow_download=True`. `_run` gained
   `**kw`.
5. `test_reapply_reuses_audio_and_puts_it_back_on_failure`: asserted `not manifest.exists()`
   after the failure. Under **show_unit** (flow step 1, spec Known constraints), the manifest is
   restored byte-identical and the re-run re-uses its audio (`ia.downloads == []`).
6. `test_reapply_refuses_when_a_leftover_aside_cannot_be_removed`: the patch target moves from
   `reapply_mod.discard_aside` to `llama.show_unit.discard_aside`, because the unit now does both
   (flow step 1). The error text is the same.
7. `_stub_package` and two inline `build_package` fakes gain `tally=None`, because reapply now
   threads `tally` (flow step 7).
8. `test_a_package_failure_leaves_the_show_held_and_a_rerun_completes_it`: only the comment
   changed ("earlier writes stay" -> "restored by the unit"); the assertion is the same.

The stub-only use of `skipped: not held` in `test_cli_reapply_reports_a_failure_continues_and_exits_1`
does not move. No other test file changed.

## Tests and results
New tests, all in `packages/llama/tests/test_reapply.py`:
- The brief's 13: `test_reapply_repackages_a_changed_delivered_show_from_the_station`,
  `test_label_only_commits_show_json_only`,
  `test_marked_unvoiced_unchanged_show_is_repackaged_for_redelivery` (also runs
  `deliver --fixed --yes`, which re-delivers and clears the mark),
  `test_voiced_unchanged_show_commits_show_json_only_and_clear_mark_then_works`,
  `test_voiced_rider_purges_when_tracks_equal[equal|differ]`,
  `test_newly_held_delivered_show_keeps_an_anchor` (a later `fix --overrule` re-packages from the
  station through the anchor with 0 downloads), `test_processed_and_reselection_rows_are_skipped`,
  `test_processed_held_show_is_not_skipped`, `test_after_commit_runs_inside_the_unit`,
  `test_reapply_allow_download_by_name_only`, `test_failure_restores_every_file`,
  `test_station_check_runs_before_the_brief`, `test_held_show_behaviour_unchanged` (pin).
- Five more:
  - `test_an_unchanged_show_commits_show_json_only_and_a_dry_run_predicts_it`
  - `test_unreadable_campaign_record_fails_the_row_retryably` (Review Focus 5)
  - `test_a_non_held_show_not_yet_briefed_is_skipped`
  - `test_structure_gate_applies_to_a_non_held_show`
  - `test_dry_run_counts_no_brief_or_download_for_a_show_json_only_row`

Full suite: 6178 passed, 1 skipped, 8 deselected (71.7 s).

## TDD evidence
RED, live tree, before implementation:
`./.venv/bin/python -m pytest -q packages/llama/tests/test_reapply.py -k "<the 17 new names>"`
-> 16 failed, 2 passed. Reasons:
- `assert 'skipped: not held' == 'cleared'`: repackages, marked_unvoiced, voiced_rider[equal],
  voiced_rider[differ].
- `assert 'skipped: not held' == 'label-only'`, `'dry-run: unchanged'`, `'unchanged'`, `'held'`,
  `'skipped: processed'` and `'skipped: structure changed'`: one each.
- `TypeError: unexpected keyword argument 'after_commit'`.
- `exit_code 0 == 1` (allow_download).
- `DID NOT RAISE OSError` (failure_restores) and `DID NOT RAISE StationUnpaired` (station_check).
- `'ReapplyOutcome' object has no attribute 'kind'` (held pin).
- `DID NOT RAISE CampaignUnreadable`.

The 2 that passed are pins of behaviour that already held: `test_processed_held_show_is_not_skipped`
and `test_a_non_held_show_not_yet_briefed_is_skipped`. I showed they bite with mutants in a
scratch copy (rsync of the tree, run with `PYTHONPATH` shadowing and `llama.__file__` checked
inside the copy, a separate `PYTHONPYCACHEPREFIX` per mutant). I named the expected red test
before each run:
- M1 (processed-skip applied to held shows) -> `test_processed_held_show_is_not_skipped` FAILED.
- M2 (scope guard removed) -> `test_a_non_held_show_not_yet_briefed_is_skipped` FAILED.
- M3 (awaiting/unvoiced clause removed) -> `test_marked_unvoiced_unchanged_show_is_repackaged_for_redelivery`
  FAILED.
- M4 (`plan_reuse(strict=False)`) -> `test_station_check_runs_before_the_brief` FAILED. I also
  predicted the allow-download test would fail; it did not, because `destination_voiced` refuses
  a missing station regardless.

`test_dry_run_counts_no_brief_or_download_for_a_show_json_only_row` was written after the cli
change. Its RED was shown in the scratch copy with the old counting rule restored:
`... 1 fresh briefs, 2 downloads` != expected `0 ... 0`. It is GREEN in the live tree.

GREEN: `./.venv/bin/python -m pytest -v packages/llama/tests/test_reapply.py -k "<names>"` ->
19 passed. All teed output is in `t9-impl.log`.

## Files changed
- packages/llama/src/llama/reapply.py (module docstring, `ReapplyOutcome`, `reapply_show`/`_reapply`,
  `_station_dir`, `_destination_voiced`, `_purge_line`)
- packages/llama/src/llama/cli.py (`reapply` command, `_reapply_list` dry-run count, `is_delivered`)
- packages/llama/src/llama/ledger.py (`is_delivered`)
- packages/llama/tests/test_reapply.py

## Self-review findings
- The diff touches none of the Global Constraints' untouched items (junk constants, `DURATION_TOLERANCE_S`,
  the pairing rule, `purge_package_audio`'s verification, `STOP_AFTER_LLM_FAILURES`, `load_list`,
  `briefing_reusable`). `Manifest` gains no field. There is no nested `file_lock`: the unit takes
  the lock once. Lock order is unchanged.
- The fresh brief keeps `overrules=` and the caller-side `split_overruled`, and still writes
  `ShowNotes.brief`.
- `written` does not list `reuse-anchor.json` or `campaign.json` (bookkeeping), so the existing
  held tests' exact `written` lists still hold.

## Concerns
1. **Scope guard (my reading of the spec).** A non-held show that is not briefed, packaged or
   delivered still returns `skipped: not held`. The spec extends reapply only to "packaged,
   briefed and delivered shows", and such a show is mid-pipeline. The brief's flow does not
   state this guard.
2. **Re-selection skip is literal.** Any show whose LAST mark starts at `select` is skipped,
   held shows included and even once it is processed (its redo hint stays). I followed flow
   step 2 verbatim; gating it on `awaiting_fix` would be the alternative.
3. **`--allow-download` with several names refuses** ("takes one named show"). The brief writes
   `<name>...`, so this is my reading.
4. **With `--allow-download`, an unreadable or missing station copy reads as unvoiced.** No purge
   rider runs, and a marked unchanged show is re-packaged rather than committing `show.json` only.
5. **A `label-only`/`unchanged` commit leaves a `reuse-anchor.json`** on packaged or delivered
   shows (step 7 literal; the anchor equals the station's list, so it is harmless).
6. **Task 6 line kept.** On a purged voiced show, a `show.json`-only commit re-fetches no audio,
   so `clear-mark`'s equal case still prints
   `warning: kept library audio for <slug>: already purged`. No quieter line was natural here.
7. **Voiced rider with changed tracks** prints deliver's warning (`station copy is a different
   package version`) verbatim, as skip-and-warn.
8. **Purge-then-hook limitation.** The purge runs before `after_commit`. If the hook fails after
   purging audio that stayed in place (no aside), that audio cannot be restored (`show_unit`
   limitation 1 class). The usual delivered case (library already purged, or an aside) restores
   correctly.
9. **List dry-run download count is still approximate.** It counts a purged delivered show's
   `needs_audio_download` even though strict reuse will copy from the station.
10. **`kind` choices.** A not-applied `needs-llm` row has kind `needs-llm`; `unchanged` has kind
    `label-only` (the `show.json`-only path).
