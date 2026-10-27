# Task 8 handback: strict station reuse and the held-outcome anchor

**Status: DONE_WITH_CONCERNS** (the concerns are small and listed at the end)

**Commit:** `6a8f7d81 feat(reuse): strict station reuse for delivered shows, held-outcome anchor`
(one commit, on top of 402d138c)

**Suite:** `./.venv/bin/python -m pytest -q` gives 6159 passed, 1 skipped, 8 deselected (71.9 s). That is 6128 + 31 new.

## What was implemented

### audio_reuse.py
- **New names:** `ANCHOR = "reuse-anchor.json"` (the same file as `ShowWorkspace.reuse_anchor`) and `class StationUnpaired(LlamaError)`. A helper `unpaired(show_ws, detail)` builds the message `<slug>: station copy does not pair: <detail>`.
- **`ReusePlan`** gains two defaulted fields, `strict: bool = False` and `station_problem: str | None = None`. Existing equality tests are unchanged.
- **`plan_reuse(show_ws, station_dir, *, strict=False)`:**
  - **Station:** pairs against `show.json` first. When that pairs nothing, it pairs against the anchor, using the same rule (same length, same title at every index) via `_pair_anchor`. The anchor is used only when its identifier equals the station manifest's `source.identifier`.
  - **Library:** pairs against the library manifest first. When that pairs nothing, anchor track i pairs `filename` to `packaged_filename(i, title, suffix)` when that file is in `package/audio/`.
  - **Strict:** records `station_problem` in two cases:
    - `station_dir is None` gives `"no delivery_path in config"`.
    - Otherwise `station_mark.read_station_manifest` is called, and a `StationUnreadable` gives its one-line detail (`no directory …`, `no manifest.json in …`, `invalid JSON in …`, …).
- **Tightening beyond the brief's literal text (see Self-review 1):** the anchor is used only when its identifier also equals the current `show.json`'s identifier. This applies to both the station and the library pairing.
- **`check_pairs(plan, show_ws)`:** does nothing unless the plan is strict. It raises `StationUnreadable("<slug>: station copy unreadable: <station_problem>")` when there is a station problem. It raises `StationUnpaired("no copy pairs")` when `plan.station` is empty and no `plan.library` name exists in `package/audio/`.
- **`write_anchor_if_absent(show_ws) -> bool`:** writes `{"identifier", "tracks": [{"filename","title"}], "written_at"}` from the current `show.json` with an atomic write. It returns False when an anchor already exists (that anchor is never replaced) or when `show.json` is missing or unreadable. `drop_anchor` deletes the file (`unlink(missing_ok=True)`).

### station_mark.py
- `StationUnreadable` gains a `detail` attribute (the one-line `<detail>` part), set by `_unreadable`. No second exception class was added.

### stages/package.py: `build_package(..., tally=None)`
- After the existing-manifest short-circuit, it calls `campaign.read_record(show_ws)`. An unreadable record therefore refuses before any write. This was the Task 3 review minor: it was cheap and safe, and has its own test.
- **Strict plan:** runs `check_pairs` first. An identifier mismatch then raises `StationUnpaired("a different recording")`. A source paired at plan time (`reuse.library ∪ reuse.station`, captured before the in-place or different-item narrowing) that is not placed raises instead of downloading:
  - `<file> has no metadata length` when there is no cached length;
  - `<file> failed its length check` otherwise.
- An unpaired source downloads.
- Under strict, reuse is attempted even with `force`, so a paired source never downloads.
- Counts are kept in `tally["reused"]` / `tally["downloaded"]` (both set to 0 when a tally dict is given). With a plan, it logs one `detail(f"audio reused {r}, downloaded {d}")`.
- After the manifest write it calls `audio_reuse.drop_anchor(show_ws)`, immediately before `campaign.after_package`.

### cli.py
- **`_redo_show_locked(..., allow_download=False)`** (and `_redo_show`):
  - `strict = <ledger has a delivered row for prov.performance_id> and from_stage != "select" and not allow_download`.
  - Before `drop_stage_artifacts`, it calls `write_anchor_if_absent` when the show is delivered or `package/manifest.json` exists.
  - It then calls `plan_reuse(..., strict=strict)`.
  - The anchor is written inside the unit, so a failed unit's restore deletes it.
- **`--allow-download` on `llama redo`:** with no name, `--run`, or any selector, it refuses before `_setup` and before any write with `--allow-download takes one named show`.
- **`--allow-download` on `llama fix`:** also passed through `_untitled_resolution` for `--untitled`. `--no-run` adds ` --allow-download` to the staged-redo line.
- **Refusal output:** the context manager `_strict_refusal_hint()` wraps the show unit from outside on by-name `redo`, `fix` and `fix --untitled`. It catches `StationUnpaired`/`StationUnreadable` after the unit's restore, prints the refusal, then the hint line `  if the station copy cannot be fixed: re-run this one show with --allow-download`, and exits 1.
- Batch redo still prints `FAILED <slug>: <msg>`, with no hint, as the contract says.

## Dry run (Step 1, done before any edit)

How I searched:
- An AST scan of every `packages/llama/tests/test_*.py` for test functions that both deliver (`"deliver"`, `status="delivered"`, `_deliver…`) and re-process (`"redo"`, `"fix"`, `"triage"`, `_redo_show*`, `process_show`, `reapply_show`, `_untitled_resolution`, `_interactive_resolve`).
- A grep of every ledger `delivered` write in the tests.
- A read of `test_deliver_cmd.py` and `test_purge_audio.py`.

**Result: no existing test expects a ledger-delivered show's `redo`/`fix` re-package to re-download purged audio.** Nothing moves under "Audio reuse never silently falls back".
- `test_fix.py::test_fix_auto_redo_of_a_delivered_show_reuses_the_station_copy` and `::test_held_reselection_then_overrule_never_ships_the_old_items_station_audio` use a station copy, but write no `delivered` ledger row (`reuse_gd73(delivery=True)` only sets `delivery_path`). They stay non-strict and their expectations are unchanged.
- `test_deliver_cmd.py`:
  - `test_redelivering_a_purged_show_points_at_redo`, `test_missing_audio_refused` and `test_unpackaged_show_refused` pin the deliver gate's hint `re-package: llama redo <slug> --from package`. That route still works and now copies from the station copy. Unchanged.
  - `_repackaged` stands in for that redo by writing the file by hand. Its docstring says "re-fetch", but it runs no redo. Unchanged.
- `test_purge_audio.py` runs no redo. Unchanged.
- `test_reapply.py` writes delivered rows but goes through `reapply_show`, which this task does not make strict (that is Task 9). Unchanged.

The full suite after the change confirmed this: the only failure was a real bug in my own anchor logic (Self-review 1), not a moved expectation.

## Tests (31 new; all in the live tree)

**test_audio_reuse.py**
- `test_strict_downloads_only_files_the_station_never_held` (Review Focus 3: `ia.download_file` once for `s.mp3`, `tally == {"reused": 3, "downloaded": 1}`, log line `audio reused 3, downloaded 1`)
- `test_strict_refuses_a_source_with_no_metadata_length`
- `test_strict_refuses_a_paired_copy_failing_its_length_check_in_the_build`
- `test_strict_refuses_another_recording_in_the_build`
- `test_check_pairs_strict_only` (`no copy pairs`, `no delivery_path in config` → `StationUnreadable`, exact strings)
- `test_strict_plan_records_why_the_station_copy_is_unreadable`
- `test_strict_passes_when_the_library_copy_pairs`
- `test_anchor_is_written_once`
- `test_anchor_pairs_after_a_held_commit`
- `test_anchor_of_another_item_pairs_nothing`
- `test_anchor_pairs_library_audio_of_a_packaged_show`
- `test_undelivered_reuse_unchanged` (pin)
- `test_anchor_pairs_no_station_copy_for_a_show_json_of_another_item`

**test_redo_cmd.py**
- `test_strict_redo_of_a_delivered_show_reuses_the_station_copy`
- `test_strict_refuses_a_paired_copy_failing_its_length_check` (no download, the unit restores byte-identical)
- `test_strict_refuses_when_nothing_pairs`
- `test_strict_refuses_a_missing_or_unreadable_station_copy[missing|not json]` (CLI lines plus `StationUnreadable` raised through `_redo_show`)
- `test_strict_refuses_without_a_delivery_path`
- `test_allow_download_lets_one_named_show_download[redo --from package | fix --set-venue X]`
- `test_allow_download_refuses_a_selector[--held|--packaged|--state delivered|--run r|no name]`
- `test_reselection_redo_is_not_strict` (pin)
- `test_held_redo_of_a_delivered_show_keeps_an_anchor_the_clear_reuses` (held `redo --from gather` writes the pre-commit anchor; `fix --overrule` then packages with zero downloads through it and removes it)

**test_fix.py**
- `test_fix_strict_refusal_names_allow_download_and_restores`
- `test_fix_no_run_with_allow_download_names_it_in_the_staged_redo`

**test_campaign.py**
- `test_package_build_refuses_an_unreadable_record_before_any_write` (Task 3 minor)

**helpers.py**
- `delivered_gd73(tmp_path, monkeypatch, old_tracks)`: `reuse_gd73(delivery=True)` plus a station copy, purged library audio, and a `delivered` ledger row.

## TDD evidence

RED, in the live tree, without `-x`:
```
./.venv/bin/python -m pytest packages/llama/tests/test_audio_reuse.py packages/llama/tests/test_redo_cmd.py \
  packages/llama/tests/test_fix.py packages/llama/tests/test_campaign.py -q -rA \
  -k "strict or anchor or allow_download or reselection_redo_is_not_strict or undelivered_reuse_unchanged or check_pairs or unreadable_record_before_any_write"
PASSED test_redo_cmd.py::test_strict_redo_of_a_delivered_show_reuses_the_station_copy
PASSED test_redo_cmd.py::test_reselection_redo_is_not_strict
FAILED test_audio_reuse.py::test_strict_downloads_only_files_the_station_never_held
FAILED test_audio_reuse.py::test_strict_refuses_a_source_with_no_metadata_length
FAILED test_audio_reuse.py::test_strict_refuses_a_paired_copy_failing_its_length_check_in_the_build
FAILED test_audio_reuse.py::test_strict_refuses_another_recording_in_the_build
FAILED test_audio_reuse.py::test_check_pairs_strict_only
FAILED test_audio_reuse.py::test_strict_plan_records_why_the_station_copy_is_unreadable
FAILED test_audio_reuse.py::test_strict_passes_when_the_library_copy_pairs
FAILED test_audio_reuse.py::test_anchor_is_written_once
FAILED test_audio_reuse.py::test_anchor_pairs_after_a_held_commit
FAILED test_audio_reuse.py::test_anchor_of_another_item_pairs_nothing
FAILED test_audio_reuse.py::test_anchor_pairs_library_audio_of_a_packaged_show
FAILED test_audio_reuse.py::test_undelivered_reuse_unchanged
FAILED test_redo_cmd.py::test_strict_refuses_a_paired_copy_failing_its_length_check
FAILED test_redo_cmd.py::test_strict_refuses_when_nothing_pairs
FAILED test_redo_cmd.py::test_strict_refuses_a_missing_or_unreadable_station_copy[missing]
FAILED test_redo_cmd.py::test_strict_refuses_a_missing_or_unreadable_station_copy[not json]
FAILED test_redo_cmd.py::test_strict_refuses_without_a_delivery_path
FAILED test_redo_cmd.py::test_allow_download_lets_one_named_show_download[cmd0]
FAILED test_redo_cmd.py::test_allow_download_lets_one_named_show_download[cmd1]
FAILED test_redo_cmd.py::test_allow_download_refuses_a_selector[sel0..sel4]   (5)
FAILED test_redo_cmd.py::test_held_redo_of_a_delivered_show_keeps_an_anchor_the_clear_reuses
FAILED test_fix.py::test_fix_strict_refusal_names_allow_download_and_restores
FAILED test_fix.py::test_fix_no_run_with_allow_download_names_it_in_the_staged_redo
FAILED test_campaign.py::test_package_build_refuses_an_unreadable_record_before_any_write
28 failed, 2 passed, 218 deselected in 1.27s
```

Two of these passed before the change, as expected:
- `test_reselection_redo_is_not_strict` is a pin.
- `test_strict_redo_of_a_delivered_show_reuses_the_station_copy` records today's working reuse; its anchor-removal leg is pinned by mutant M4 below.

`test_undelivered_reuse_unchanged` was red only on the new `plan.strict` attribute.

GREEN, same command after the implementation: `30 passed, 218 deselected in 0.84s`.

**Second RED/GREEN, after the first full suite run failed** (`test_fix.py::test_held_reselection_then_overrule_never_ships_the_old_items_station_audio`):
- The new test `test_anchor_pairs_no_station_copy_for_a_show_json_of_another_item` was RED: `assert {'a.mp3': …, 'b.mp3': …, 'x.mp3': …} == {}`, 1 failed.
- After the fix, `test_audio_reuse.py` plus that test gave 34 passed.

**Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` gave 6159 passed, 1 skipped, 8 deselected, 26 warnings in 71.90s.

**Mutation check.** Each mutant ran in a scratch `git archive HEAD` copy, run from the scratch directory with `python -m pytest`, PYTHONPATH shadowing and `PYTHONDONTWRITEBYTECODE=1`. `llama.__file__` resolved inside the copy. The baseline M0 gave 238 passed. Every mutant turned its predicted tests red:

| Mutant | Change | Tests that went red |
|---|---|---|
| M1 | drop the `select` exemption | `test_reselection_redo_is_not_strict` |
| M2 | drop the paired-not-placed raise | the no-metadata-length test, the length-check test in the build, and the length-check test in redo (3) |
| M3 | drop the anchor's show.json-identifier guard | the new cross-item anchor test and the existing held-reselection fix test |
| M4 | drop `drop_anchor` | 4 anchor-removal assertions |
| M5 | `strict = False` | 8 strict-refusal and allow-download tests |
| M6 | anchor rewritten every time | `test_anchor_is_written_once` and the held-redo anchor test |
| M7 | drop the selector refusal | all 5 selector cases |
| M8 | drop the `a different recording` raise | its test. Without that raise the build still refuses, but with `a.mp3 failed its length check` instead. |

## Files changed
- `packages/llama/src/llama/audio_reuse.py`
- `packages/llama/src/llama/stages/package.py`
- `packages/llama/src/llama/cli.py`
- `packages/llama/src/llama/station_mark.py` (the `detail` attribute only)
- `packages/llama/tests/helpers.py`, `test_audio_reuse.py`, `test_redo_cmd.py`, `test_fix.py`, `test_campaign.py`

## Self-review findings

1. **Real bug found and fixed (strict surface).** The brief's anchor station-pairing rule says only "the anchor's identifier equals the station manifest's `source.identifier`".
   - Implemented literally, a held re-selection (show.json now names item B; the anchor and station are item A) paired item A's station audio under item B's same-named sources. The build's identifier guard compares the plan-time `show.json` identifier, which is B, so it let the pairing through.
   - The existing test `test_held_reselection_then_overrule_never_ships_the_old_items_station_audio` caught it.
   - Fix: the anchor is ignored unless its identifier equals the current `show.json`'s. The library rule already had this condition; it now applies to the station pairing too.
   - The intended case (reapply's held commit, which never re-selects) is unaffected.
   - This is a deliberate tightening beyond the brief's literal text. The reviewer should confirm it.
2. **Untouched, as the Global Constraints require:** `DURATION_TOLERANCE_S` (still 5.0), `_pair`'s rule (index + title + `source.identifier`), and `catalog.purge_package_audio`. `_pair_anchor` reuses the same rule against the anchor's list.
3. **"Not placed" covers a missing file too.** A paired copy that is absent (for example, a partially purged library whose station copy also does not pair) refuses with `<file> failed its length check`, following the brief's "one whose copy is not placed". The detail wording is slightly loose for a missing file; it is never a download.
4. **`_is_delivered` in cli duplicates `reapply._delivered`.** It is a two-line ledger scan. I did not import reapply's private helper.

## Concerns
- **Triage gives no hint.** `triage` edits run strict through `_redo_show_locked`. A refusal prints `error: <slug>: station copy …` and returns to the prompt, with no hint, because triage has no `--allow-download`.
- **Batch redo gives no hint.** A batch redo prints `FAILED <slug>: …` without the hint, as the contract specifies.
- **Shows held before this change can refuse strictly.** A delivered show that was held before this task (its `show.json` already retitled, its library manifest dropped, and no anchor) gets an anchor equal to the retitled list. It therefore refuses strictly with `no copy pairs` and needs `--allow-download`. This is the pre-existing gap the spec describes, not a regression.
- **The project CLAUDE.md is out of date.** It still says "A purged show re-delivers via `llama redo <name> --from package`, which re-downloads what is missing". For a ledger-delivered show this now copies from the station copy, or refuses. I did not edit CLAUDE.md because it is outside this task's file list.
- **Neither tally nor strictness reaches reapply yet.** `tally` is not threaded through `process_show`/`run_package`, and `reapply.py`'s `plan_reuse` call is still non-strict. I expect both to be Task 9's job.
