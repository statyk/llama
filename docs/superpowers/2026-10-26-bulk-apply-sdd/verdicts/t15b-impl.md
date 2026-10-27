# t15b-impl handback (Task 15b: M1-M3 marking fixes)

**Status:** DONE_WITH_CONCERNS (the concerns are about edge cases that remain, listed below; nothing is blocked)
**Commit:** d6a9eb24 (one commit on bulk-apply, BASE d1bb0127)
**Tests:** `./.venv/bin/python -m pytest -q` gives 6301 passed, 1 skipped, 8 deselected (baseline 6291 + 10 new). `scripts/test_bulk_apply_mark.py` has 38 passed.
**Files:** `scripts/bulk_apply.py`, `scripts/test_bulk_apply_mark.py`. No llama source changed, `Manifest` is untouched, and no existing Contracts string changed.

## M1: design (a), recognise the batch's own mark, plus evidence-based reversal

I chose (a), not (b) (a `pending` line written before the station write). The evidence (a) needs is already on disk: the before copy is made durable before any station write, and the station mark carries the batch's `at`. (b) would add a second record-line protocol, and a reader for it in `mark_apply`, `unmark` and the exit rule. With (a), `record.jsonl` keeps a single line shape.

How it works (`_mark_station`, `_reversal`, `_mark_one`, `mark_apply`):
- **Same `at` on every run.** `_mark_one` now writes the station mark with this batch's library-mark `at` whenever the library already has one. Before, a re-run used a fresh `_now()`. Without this change, a refused run followed by a re-run that crashed after its station write would leave `marked_at` different from the library mark's `at`, so the re-run would not recognise its own mark. `_has_batch_mark` became `_batch_mark`, which returns the mark.
- **Recognising the mark.** If the station copy already carries a mark whose `marked_at` equals this batch's library `at`, `_reversal` tries to verify the pre-mark bytes. It accepts exact evidence only:
  1. `before/<slug>.json` parses to an unmarked dict, and re-encoding it with the station's mark the way `write_mark` does (`station_mark._encode`, same key position, same trailing newline) gives exactly the station bytes; or
  2. the record line's `after_sha256` equals sha(station bytes), and the station bytes with the mark removed, re-encoded, hash to the line's `before_sha256`.
  - If either holds: the verified bytes are saved durably as the before copy if they differ, and the line is recorded `marked` with before = sha(verified) and after = sha(current).
  - If neither holds: the line is `marked by this batch, no verified before copy` (`_UNVERIFIED`).
  - Either way, the station copy is never re-written.
- **Before-copy re-save fails after `write_mark`.** The line is now `marked, before copy not saved (<detail>)` (`_UNSAVED`) with both shas, never `refused`. A save failure in the recognise path also records `_UNSAVED`.
- **Exit and re-runs.** Neither `_UNSAVED` nor `_UNVERIFIED` is in `_STATION_OK`, so both are listed and `mark --apply` exits 1. Both are in `_RETRIED` together with `refused`, so a re-run retries them. A re-run heals `_UNSAVED` to `marked` through evidence 2.
- **`unmark`** (`_own_station_mark`, `_unmark_one`, `unmark`):
  - Any last line with `mark_added: true` whose station is neither `marked` nor `not delivered` gets its station copy checked. If the copy carries a mark with this batch's `marked_at` (the library mark's `at`, or the line's `at`), it is put back when `_reversal` verifies the bytes. `put_back` expects sha(current), and the emcee check runs first as before. Otherwise the line is listed: `the station copy carries this batch's mark and there is no verified before copy; check it by hand`, exit 1. It is never skipped silently.
  - If the copy cannot be read, the line is a problem only when `before/<slug>.json` exists, meaning the batch attempted a station write. Without a before copy the batch never wrote that copy. This keeps the existing `test_unmark_removes_library_only_marks` (`bad`, invalid JSON, refused before any write) at exit 0. It also means an unmounted station root with a before copy present is listed.
  - New: a `before/<slug>.json` with no record line at all is listed as `no record line (a marking run stopped part-way); re-run the batch, then unmark`, exit 1. This covers a crash that is never re-run, which the record alone could not show `unmark`.
- **Review Focus 1 is held.** `emcee_running()` still runs before every station write; the recognise path writes no station bytes. `write_mark`/`put_back` are unchanged. `put_back` runs only while the file holds bytes verified to be the ones this batch's mark produced.

## M2

- `mark_plan` now returns `(items, unplannable)`, where `unplannable` is a list of `(slug, problem)`.
- `_stored_show` raises `_Unplannable("show.json unreadable (<detail>)")` and `_plan_one_mark` lets it through. show.json is read only on paths that need it, so a re-selection or a no-diff frozen row is still planned without it. With show.json now always present on those paths, the `stored is not None` guards are gone.
- **Missing directory: my scope choice.** A missing show directory is `no show directory` only for rows the plan could mark (`_could_mark`): a re-selection, a frozen slug, or an arm row whose outcome is not in `_NO_DIFF`. A clean or unreplayable row off the frozen list is never marked, so a removed show there is not counted. If the reviewer reads "only a missing directory makes it unplannable" as covering every missing dir, it is a one-line change.
- `_print_mark_plan` prints `unplannable shows: N` and then `  <slug>: <problem>`, always, after `unreplayable, not marked:`. `unplannable` is now a required argument, so a caller cannot drop it silently.
- The dry run exits 1 while any are unplannable. `--apply` raises `GateRefused("refusing to mark: N unplannable show(s): a, b")` (exit 2) before `retire_rekey_restore`, the backup or the batch dir.

## M3

`cmd_mark` refuses `--apply` with `--campaign-dir` right after `_config` (it needs `root` for the message) and before every other check or read. Exit 2, with the exact line `refusing --campaign-dir with --apply: campaign state must live in <root>/campaign (the dry run may use a scratch dir)`, where `<root>` is replaced by the config root. `cmd_unmark` takes no `--campaign-dir`, so it needs no change.

## Tests, each shown RED before the fix

The first nine ran RED in the live tree before any implementation (command: `./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q --tb=line -k ...`):

| Test | RED output |
|---|---|
| `test_crash_after_station_write_is_reversible` | `:840 AssertionError: assert ('already marked' == 'marked'` |
| `test_before_save_failure_after_write_is_not_recorded_refused` | `:892 AssertionError: assert not True` (the line was `refused: ...`) |
| `test_rerun_heals_an_unsaved_before_copy` (extra) | `:914 AssertionError: assert 'already marked' == 'marked'` |
| `test_unmark_never_reports_success_over_this_batchs_station_mark` | `:940 AssertionError: assert 0 == 1` |
| `test_unmark_lists_a_before_copy_with_no_record_line` (extra) | `:965 AssertionError: assert 0 == 1` |
| `test_missing_show_dir_is_reported_not_dropped` | `:978 AssertionError: assert 0 == 1` |
| `test_unreadable_show_json_is_reported_not_dropped` | `:994 AssertionError: assert 0 == 1` |
| `test_apply_refuses_while_shows_are_unplannable` | `:1005 AssertionError: assert 0 == 2` (it made the backup and a batch) |
| `test_campaign_dir_refused_with_apply` | `:1020 'no frozen ne...frozen.json\n' == 'refusing --c...cratch dir)\n'` |

The tenth was added after implementing, so its RED was taken against BASE in a scratch copy instead of the live tree:
- `test_rerun_marks_the_station_with_the_batchs_own_at` (extra) pins the same-`at` change.
- The copy was made with `git archive d1bb0127 | tar -x` plus the new test file, run from the scratchpad as `venv python -m pytest` with PYTHONPATH shadowing.
- The import check printed paths inside the copy for both `llama.__file__` and `bulk_apply.__file__`.
- RED: `:1046 AssertionError: assert '2026-10-27T07:00:21.551875Z' == '2026-10-27T07:00:21.529713Z'`.

All RED output is in `t15b-impl.log`.

## Existing tests changed

The only edits are to the call shape: `mark_plan` now returns a tuple, which M2 requires because the unplannable rows have to come back with the items. No expected value changed.
- `test_plan_marks_visible_changes_frozen_guard_and_reselections`, `test_mark_plan_guard_uses_only_held_problems` and `test_mark_plan_ignores_needs_llm_diff_off_frozen_list`: now `items, unplannable = ...` plus `assert unplannable == []`.
- `test_mark_plan_skips_processed_needs_llm_row_with_diff` and the first assert of `test_mark_plan_ignores_needs_llm_diff_off_frozen_list`: `== []` became `== ([], [])`.

## Full suite

`./.venv/bin/python -m pytest -q -p no:cacheprovider` from the worktree root: **6301 passed, 1 skipped, 8 deselected** (rc 0, 81.6 s).

## Concerns

1. **`_UNVERIFIED` cannot clear itself.** This happens when the station copy carries this batch's mark but neither kind of evidence verifies, typically because emcee rewrote the copy after the mark. Every re-run retries it and lists it again, and `unmark` lists it. Clearing it takes a hand decision. The reversal-by-record rule is kept by listing it.
2. **Private names used.** I added `station_mark._encode` (needed so the re-encoding cannot drift from `write_mark`'s) and kept `campaign._now`/`_parse`. These are in the same family as review M5.
3. **A crashed library-only item is not reversed by `unmark`.** This is a show that is not delivered, whose library mark was written and whose record line was not. It makes no station write and no before copy, so `unmark` cannot see it until a re-run records the line. It is library-only and the safe direction. This was already true before this task.
4. **`no record line` listing can fire when the station was never written.** It also fires when the crash came between the before-copy save and `write_mark`'s rename. The message says to re-run the batch, which resolves it either way.

## Fix round 1 (FIX_BASE d6a9eb24, commit a2d5122d; tests only)

No production code changed. None of the new tests exposed a bug.

### What was added
New tests in `scripts/test_bulk_apply_mark.py`, plus a helper `_crash_after_station_write`. The helper simulates a crash between the station write and the record line (`_append_jsonl` raises). It can also write the copy in llama's own encoding, with no trailing newline.

1. **`test_unverified_own_mark_is_recorded_and_listed`**
   - Setup: crash after the station write; then `dj_notes` is rewritten in the marked station copy; then a re-run.
   - Asserts: the line is `ba._UNVERIFIED` (with `mark_added` true, `before_sha256` None and `after_sha256` = sha of the current copy); rc is 1; the slug is listed; the station bytes are unchanged.
2. **`test_unmark_lists_an_unreadable_station_copy_with_a_before_copy`**
   - Parametrized over a `refused: Input/output error` line and a `marked, before copy not saved (x)` line.
   - Setup: `mark_added` true; `before/d1.json` present; station manifest is `{not json`.
   - Asserts: `unmark --apply` exits 1; there is a `d1: cannot check the station copy for this batch's mark ...` line; the library record is byte-equal (mark kept); the station is untouched.
3. **`test_recognises_own_mark_on_a_copy_with_no_trailing_newline`**
   - Setup: the station copy is llama-encoded with no trailing newline; crash; re-run.
   - Asserts: the line is `marked` with `before_sha256` = sha(original); rc is 0; `unmark` restores the original bytes and exits 0.

### Mutant results in scratch copies
Each copy was made with `git archive d6a9eb24 | tar -x` plus the new test file, and run from the scratchpad as `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<copy>/packages/llama/src:<copy>/scripts <worktree>/.venv/bin/python -m pytest -p no:cacheprovider <copy>/scripts/test_bulk_apply_mark.py`. For every copy, `llama.__file__` and `bulk_apply.__file__` printed paths inside that copy (logged). Each mutant was killed only by its predicted test:

| Mutant | Change | Failing test | Result |
|---|---|---|---|
| M1 | `return _UNVERIFIED, None, _sha(raw)` → `return "already marked", None, None` | `test_unverified_own_mark_is_recorded_and_listed` (`:1087` mark_apply rc, `assert 0 == 1`) | 1 failed, 41 passed |
| M2 | `if not saved.exists():` → `if True:` in `_own_station_mark` | both parametrizations of test 2 (`:1119` unmark rc, `assert 0 == 1`) | 2 failed, 40 passed |
| M7 | evidence (1) `newline=before.endswith(b"\n")` → `newline=True` | test 3 (`:1133` mark_apply rc, `assert 1 == 0`) | 1 failed, 41 passed |

The scratch copies were removed afterwards.

### Live tree and full suite
- Live tree: `./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q`: 42 passed.
- Full suite: `./.venv/bin/python -m pytest -q -p no:cacheprovider` from the worktree root: **6305 passed, 1 skipped, 8 deselected** (rc 0, 79.8 s).
