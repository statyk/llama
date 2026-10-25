# t12-impl handback: Task 12, re-using existing audio (spec 5.4)

**Status: DONE_WITH_CONCERNS.** The concerns are small design calls, listed at the end. None of them blocks Task 13.

## Commits (branch held-backlog-junk-filter, on top of 5c78650)
- `bacf701` feat(audio_reuse): pair existing audio with source files by index. This adds the module, `test_audio_reuse.py` (the plan and `reuse_into` tests) and the shared fakes in `helpers.py`. Suite: 5031 passed, 1 skipped, 8 deselected.
- `57c1026` feat(package): build_package(reuse=) re-uses existing audio. Suite: 5038 passed, 1 skipped, 8 deselected.
- `5a89be0` feat(package): re-use existing audio when a show's track list changes. This is the show_unit part and uses the commit title the plan gives. Suite: **5045 passed, 1 skipped, 8 deselected** (80 s).

Each commit was put through the full suite in exactly its committed state. Command: `./.venv/bin/python -m pytest -q -p no:cacheprovider`, run from the worktree root. `llama.__file__` resolves inside the worktree. The suite still shows 26 warnings, the same count at every commit.

## Files
- New: `packages/llama/src/llama/audio_reuse.py`
- Modified: `packages/llama/src/llama/stages/package.py` (`build_package`), `packages/llama/src/llama/show_unit.py`
- Tests: `packages/llama/tests/test_audio_reuse.py` (new); appended to `test_stage_package.py`, `test_show_unit.py` and `helpers.py`.
- The fakes added to `helpers.py`: `fake_audio`, `fake_read_duration`, `fake_source`, `patch_fake_durations`, `ReuseIA`, `reuse_show`, `packaged_reuse_show`, `audio_files`. The fake audio bytes carry the source filename and a length. That lets a test tell which audio ended up under which packaged name, and it survives `tag_audio`.

## Dry run (existing expectations)
**No existing test expectation changes.** `reuse=None` keeps today's behaviour, and the show_unit changes only touch `.audio-aside/`, which no existing test creates. The diff against 5c78650 removes no line from any existing test file; it only appends. Every pre-existing test stayed green at each commit.

## Red, then green, for each test
The red run had all of the new tests in place, against a stub `audio_reuse`: the right interface, but no behaviour, and no `reuse=` on `build_package`. 24 of them failed. Each later stage was red again before it was implemented.

- `test_audio_reuse.py`:
  - **Red on assertion** (wrong plan values): `test_plan_pairs_library_and_station_by_index`; `test_pairing_is_by_index_and_any_title_mismatch_drops_the_copy` (Review Focus 5); `test_a_copy_of_another_length_contributes_nothing` (extra); `test_plan_without_show_json_pairs_nothing` [missing, unreadable]; `test_unreadable_station_manifest_contributes_nothing` [missing, not json, no tracks, track without title, a path instead of a name]; `test_reuse_into_tries_the_library_before_the_station` (extra).
  - **Red with `TypeError`, no `reuse` keyword**: `test_duration_mismatch_or_unreadable_falls_back_to_download` and `test_station_copy_used_when_the_library_was_purged`. Both were red again before the `build_package` commit.
  - **Passes on the stub too**: `test_unreadable_library_manifest_has_no_names` (extra; the stub's `None`/`{}` happen to be the right answer).
  - All green after the module and `build_package` work.
- `test_stage_package.py`:
  - **Red with `TypeError`, then green after `build_package`**: `test_changed_list_sets_old_audio_aside_and_reuses_it_under_the_new_name`, `test_same_title_renumbered_never_inherits_the_wrong_audio`, `test_retitle_only_change_reuses_under_the_new_name`, `test_unchanged_list_and_matching_manifest_keeps_files_in_place` **(pin)**.
  - **`test_audio_without_a_library_manifest_is_set_aside`** (Review Focus 6): red, then green only after show_unit. With the `build_package` work alone it still failed, on "the aside is gone after success", so it went into commit 3.
  - **`test_build_package_without_reuse_never_sets_aside`**: an extra **(pin)** for `reuse=None`, green throughout.
- `test_show_unit.py`: red until the show_unit work, then green.
  - `test_failed_unit_puts_aside_audio_back_under_old_names`. When red, it showed the real hazard: old `03 - Jam.mp3` came back holding j1's audio, and files were lost.
  - `test_failed_unit_mid_set_aside_puts_back_what_was_moved` (extra: a KeyboardInterrupt after two files have been moved aside).
  - `test_successful_unit_deletes_the_aside`.
  - `test_leftover_aside_is_deleted_at_unit_entry`, for a successful and a failing body. A stale aside is never put back.
  - `test_a_leftover_aside_that_cannot_be_removed_refuses_before_anything_is_written` (extra).

## Mutation check (scratch copies only)
**Method.** `git archive HEAD` was extracted into the scratchpad, one copy per mutant. Each ran with `PYTHONPATH` shadowing, a separate `PYTHONPYCACHEPREFIX` and `-p no:cacheprovider`, and `llama.__file__` was checked to resolve inside the copy before any run. The test expected to go red was named before each run. All 8 were caught by that test:

| mutant | caught by |
|---|---|
| (i) `set_aside` skipped | `test_same_title_renumbered_never_inherits_the_wrong_audio` (8 tests fail) |
| (i2), approximate: decide keep or aside from show.json filenames | `test_audio_without_a_library_manifest_is_set_aside` |
| `put_back` removed | `test_failed_unit_puts_aside_audio_back_under_old_names` |
| `_tracked_files` stops skipping the aside | `test_failed_unit_puts_aside_audio_back_under_old_names` (the restore would delete the aside files) |
| title check removed from the pairing | `test_pairing_is_by_index_and_any_title_mismatch_drops_the_copy` |
| tolerance check removed | `test_duration_mismatch_or_unreadable_falls_back_to_download` |
| success `discard_aside` removed | `test_successful_unit_deletes_the_aside` |
| entry `discard_aside` removed | `test_leftover_aside_is_deleted_at_unit_entry` |

**The (i2) mutant is only an approximation.** It compares against the CURRENT show.json, not the plan-time one, because the plan does not carry the plan-time list. The plan's full (i2) still needs to be run in the dedicated mutation task.

## Design decisions
1. **Expected length.** `expected_sec` is the cached metadata `length` of `t.filename`, parsed with `util.length_seconds`. It is read from the same `ia.metadata(...)` call `build_package` already makes for md5s, not from `t.duration_sec`. When the length is missing, the file downloads.
2. **Tolerance edge.** A length difference of exactly `DURATION_TOLERANCE_S` is reused (`abs(d - expected) <= tol`). This matches the package flag, which fires only on `>`. The constant itself is unchanged.
3. **Pairing.** Copies are paired by position, with equal length and an equal title at every index; that is all the spec asks, and I added no check on the manifest's `index` field. A manifest is "unreadable" on any OSError or JSON error, a missing `tracks`, `title` or `filename`, a non-string value, or a filename that is not a bare name (`Path(n).name != n`, or `.`/`..`). The last one is an extra guard so a station manifest cannot point outside its `audio/`. An unreadable show.json covers any exception from `read_model`.
4. **`reuse_into`.** It **copies, never moves**, so the aside survives for a put-back. The copy goes to `.<name>.reuse.tmp` beside `dest` and is then `os.replace`d into place. A crash mid-copy leaves at most a dot-temp in `package/audio/`; a failed unit's restore deletes it, since it is audio the unit added.
5. **`force` with `reuse`.** Under `force` every file downloads as today and `reuse_into` is not called. The keep-or-aside step still runs, so old-numbered orphans are set aside and deleted on success. No caller passes both today.
6. **Log line for a reused file**: `re-using i/n: <source> (library|station copy)`, through `status.detail`, the same channel as "downloading".
7. **`set_aside` and `put_back`** move only regular files, with `os.replace`. A partial `.part` left in `package/audio/` moves too, and comes back on failure. `put_back` replaces whatever a failed package stage left under the same name, then removes the aside directory.
8. **show_unit** (documented in its docstring as limitation 5):
   - Entry deletes a leftover aside right after the `.txn/` check. **If the aside cannot be removed, the unit refuses** (`<slug>: cannot remove leftover audio aside <path>`), exactly as a stuck `.txn/` does. Otherwise a failed unit's put-back would resurrect stale audio.
   - On failure the order is `restore_snapshot`, then `put_back`, then `discard_snapshot`.
   - **If `restore_snapshot` raises, `put_back` does not run.** The aside is left, and the next unit deletes it along with the `.txn/`. That is the "failed restore" case under limitations 3 and 5.
   - On success the order is `discard_aside`, then `discard_snapshot`.

## Concerns / notes for Task 13 and the reviewers
- The plan's Task 13 runs `reapply_show` outside `show_unit`, using its own cleanup and `put_back`/`discard_aside`. `build_package` itself never deletes the aside: success-side deletion always belongs to the caller.
- The keep-in-place branch consults the aside path too, through `reuse_into`. Inside a unit the aside has just been deleted at entry, so this is harmless. A caller that skips the entry deletion could reuse a stale aside file under a library name; it would still be length-checked. Task 13's reapply already deletes a leftover aside at entry.
- The (i2) mutant is approximate (see above).
- No `ruff` or `pyflakes` in the venv, so no lint was run.
