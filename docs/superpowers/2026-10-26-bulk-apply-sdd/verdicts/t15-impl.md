# Task 15 handback (t15-impl): marking, its inputs and its reversal

**Status: DONE_WITH_CONCERNS** (the concerns are interpretation calls, listed below; none changes the marking rule)

**Commit:** `5fb225b6 feat(bulk): marking batch, frozen needs-LLM list, re-selection check, reversal` (one commit, on top of 0295d3d7)

## What was implemented (`scripts/bulk_apply.py`)

- `MarkItem(slug, reason, start_stage, digests, state="")`. The four fields are the brief's. `state` is an extra field with a default, filled from mark_plan's `delivered` argument and used only by the dry run's table. The apply step re-reads delivered-ness under the show lock.
- `freeze(root, arm, *, campaign_dir=None) -> Path`
  - Writes `<campaign>/needs-llm-frozen.json` `{arm_sha, arm_generated_at, slugs}` (the arm's rows with outcome `needs-llm`, sorted).
  - Refuses an existing file with a LlamaError, so the CLI exits 2.
- `reselect_rows(root, config, source) -> list[dict]`
  - A source row is named by `slug` or `show`; `m3_changed-r1.json` uses `show`.
  - The stored recording is `show.json`'s `identifier`. The pick comes from `run_select_recording`:
    - into `ShowWorkspace(<TemporaryDirectory>/<slug>)`;
    - with `CacheOnlyIA(root/cache)`, `force=True`, `config.audio_format` and `config.selection`;
    - with the assessment built as `_redo_show_locked` builds it.
  - Drops a row when the pick equals the stored recording. For a ledger-delivered show it also drops the row when `destination_voiced(delivery_path/slug)` is true.
  - Returns `[{slug, stored, pick}]`.
- `mark_plan(root, arm, frozen, reselections, delivered) -> list[MarkItem]`, in priority order:
  1. **Re-selection**, from the re-checked list, whatever the arm says: start `select`, digests None.
  2. Rows whose outcome is `needs-llm` or `unreplayable`. This check runs BEFORE `row_visible_changes` (pointer d). Such a row is marked only by the frozen-list rule, and only if not processed.
  3. Label-only rows (`row_label_only`): never marked.
  4. **Visible change** (`row_visible_changes`): marked even when processed. The reason is `changed by the held-backlog fixes: <fields joined ", ">`.
  5. A processed show is skipped from here on.
  6. **On the frozen list**: `replay needs an LLM call: <needs_llm joined ", ">`.
  7. **Stored briefing guard** (pointer a): the row's `stored_brief_guard` is split with `overrules.split_overruled(problems, read_overrides(ws).overrules, show)`. The show is marked only when held problems remain. An unreadable `overrides.json` honours no overrule.
  - "Processed" means the record is readable, `processed` is not None and the show is not awaiting fix. An unreadable record counts as not processed.
- `take_station_backup(station_root, dest)`
  - Copies `manifest.json` from every top-level non-dot station dir. Each copy goes through `batch_snapshot._write_copy`, then is re-read and its sha256 checked.
  - `index.json` (`{taken_at, station_root, manifests: {slug: sha}, missing, unreadable}`) is written last. A partial earlier attempt is discarded.
- `mark_apply(root, items, *, station_root, batch, echo) -> int`
  - Per item, under the plain show lock (`file_lock(ws.lock)`), in this order:
    1. Digests re-checked: on a mismatch, `skipped: inputs changed` and nothing is written.
    2. `add_mark` (durable) unless `is_awaiting`.
    3. `mark_added` is set when the campaign record holds a mark with this batch's id.
    4. Station side:
       - `not delivered` when the ledger has no delivered entry;
       - `refused: station root … is not readable` when the station root is gone;
       - `no station copy` when the station dir is absent;
       - otherwise `emcee_running()` is checked before EACH write (pointer b). A running emcee records `refused: emcee is running` for this item and stops the batch; every remaining item is listed as not reached;
       - an already-marked copy records `already marked`;
       - otherwise `before/<slug>.json` is saved durably, then `write_mark` runs, giving `marked` plus before/after sha256.
    5. Any `LlamaError`/`OSError` from the station read or write becomes `refused: <one line>` for that item (pointer c).
    6. One `record.jsonl` line `{slug, reason, start_stage, mark_added, station, before_sha256, after_sha256, at}`. The campaign mark's `at` and the station's `marked_at` are the same value.
  - A re-run skips slugs whose last record line has a station outcome that is not `refused…`.
  - Exit codes: 1 when any delivered item is not `marked` / `already marked` / `no station copy`, when an item hit an error or its show dir is missing, or when emcee stopped the batch. The list ends with `not marked (N); do not run emcee on their profiles until a re-run of this batch exits 0:`. Otherwise 0.
- `unmark(root, batch, *, station_root, apply, echo) -> int`
  - Works per slug's LAST record line.
  - `mark_added: false`: kept, with no library or station change.
  - Otherwise, under the show lock:
    - If the record was processed at or after this batch's mark: listed as `processed since marked: re-deliver instead`, nothing changed.
    - For a `marked` line:
      - station sha == `after_sha256`: `put_back(before)`, after checking that the saved before-file's sha equals `before_sha256`;
      - station sha == `before_sha256`: already put back, so this re-run is idempotent;
      - anything else: listed as `station copy changed since marking`, nothing changed.
    - Then `remove_marks(ws, batch_id)`.
  - `emcee_running()` is checked before each `put_back`.
  - Dry run unless `apply`. Exit 1 when anything is listed.
- **CLI**
  - `freeze --arm A [--campaign-dir D]`
  - `reselect-check --source F [--write] [--campaign-dir D]`
  - `mark --arm A [--apply] [--campaign-dir D]`
  - `unmark --batch DIR [--apply]`
  - `mark` gates, each refusing with exit 2:
    - `delivery_path` set and the station root a directory;
    - with `--apply`: `require_pinned_code` and `require_tools`;
    - arm `sha == llama.replay.code_identity()`, never `-dirty` on either side;
    - the arm's `config_fingerprint` equals the running config's;
    - the frozen list and `reselections.json` exist and are well formed;
    - `reselections.json` `written_at` is not before the arm's `generated_at`, else the fixed string `reselections.json predates the arm; re-run: bulk_apply.py reselect-check --write`.
  - The dry run prints:
    - counts by reason kind × (delivered unvoiced, delivered voiced, packaged, briefed, held, plus any extra state present, e.g. `delivered unreadable`);
    - counts by arm outcome (so Checkpoint B can see newly-held);
    - `voiced: N: slugs`;
    - `unreadable station manifests: N` with one line each;
    - `unreplayable, not marked: N: slugs`;
    - `emcee running: no|yes` (+ lines).
  - `--apply`, after the gates:
    1. `retire_rekey_restore(by="bulk-apply marking <batch id>")`;
    2. the station backup, if `index.json` is absent;
    3. `marking/<sha256(arm bytes + frozen bytes + reselections bytes)[:16]>/inputs.json`, if absent;
    4. `mark_apply`.

## Tests (`scripts/test_bulk_apply_mark.py`, 25 tests)

- **Every test named in the brief:**
  - test_plan_marks_visible_changes_frozen_guard_and_reselections
  - test_apply_writes_record_before_station
  - test_rerun_skips_marked_items
  - test_unreadable_station_manifest_is_refused_and_listed_exit_1
  - test_emcee_running_stops_the_batch
  - test_station_backup_taken_once
  - test_inputs_changed_row_skipped
  - test_mark_plan_skips_processed_needs_llm_row_with_diff
  - test_mark_plan_ignores_needs_llm_diff_off_frozen_list
  - test_mark_refuses_reselections_older_than_the_arm
  - test_mark_apply_retires_the_rekey_restore
  - test_reselect_rows_write_nothing_under_the_library (file list, sha and mtime of the whole root unchanged)
  - test_reselect_rows_drop_voiced_and_already_reselected
  - test_unmark_restores_bytes_and_removes_the_batch_mark
  - test_unmark_removes_library_only_marks
  - test_unmark_refuses_a_manifest_changed_since_marking
  - test_unmark_lists_processed_shows
  - test_freeze_refuses_to_overwrite
- **Pointer tests:**
  - (a) test_mark_plan_guard_uses_only_held_problems: when every guard problem is overruled, the show is not marked; one held problem left still marks it.
  - (c) test_oserror_from_the_station_write_is_refused_not_fatal.
- **Extra tests:**
  - test_mark_refuses_an_arm_of_other_code_or_config
  - test_mark_dry_run_prints_counts_and_writes_nothing (also drives `freeze --campaign-dir`)
  - test_already_marked_station_copy_is_recorded
  - test_mark_apply_refuses_without_the_pin_or_tools
  - test_reselect_check_cli_writes_the_list (`--campaign-dir`; nothing under the root)
- **Stubbing:** an autouse fixture stubs `station_mark.emcee_running` and `campaign_gate.ps_lines` in every test; tests opt in to a running emcee. No test touches `~/.llama` or the station.

## TDD evidence

- **RED** (the API stubbed in bulk_apply.py, each function raising NotImplementedError, with argparse placeholders for the 4 subcommands):
  - Command: `./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q -p no:cacheprovider`
  - Result: `25 failed in 0.64s`. Every failure is `E NotImplementedError` (grep of the `E ` lines: `25 E NotImplementedError`), as expected: nothing was implemented yet.
  - One assertion was strengthened after GREEN: the label-only row also gets a failing stored guard and sits on the frozen list. Mutant m7 below shows it red against code without the label-only rule.
- **GREEN:**
  - `./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q -p no:cacheprovider`: `25 passed`. With `-W error`: `25 passed`.
- **Full suite:**
  - `./.venv/bin/python -m pytest -q -p no:cacheprovider`: `6288 passed, 1 skipped, 8 deselected, 26 warnings in 79.60s`. That is the baseline 6263 plus 25 new. The 26 warnings are pre-existing; the new file is clean under `-W error`.
- **Mutation check** (in a scratch copy of `scripts/`, run from an empty cwd with `PYTHONDONTWRITEBYTECODE=1`; a planted sentinel proved the copy was the code under test). Each mutant failed the test predicted for it:

| Mutant | What it changes | Tests that failed |
|---|---|---|
| m1 | no overrule split (pointer a) | guard test |
| m2 | outcome check skipped (pointer d) | both needs-LLM plan tests |
| m3 | no emcee check (pointer b) | emcee test |
| m4 | OSError not caught (pointer c) | OSError test |
| m5 | add_mark skipped | 8 tests, incl. record-before-station |
| m6 | unmark sha guard removed | changed-since-marking test |
| m7 | label-only rule removed | plan test |
| m8 | processed skip removed | plan test |
| m9 | re-run skip removed | re-run test |
| m10 | voiced kept in re-selection | reselect-drop test |
| m11 | stale re-selection gate removed | refusal test |
| m12 | `mark_added` ignored in unmark | library-only test |
| m13 | processed check removed in unmark | processed test |
| m14 | backup retaken every run | backup-once test |

## Files changed

- `scripts/bulk_apply.py` (modified)
- `scripts/test_bulk_apply_mark.py` (new)

## Self-review

- **Completeness:**
  - Every function, CLI option (incl. `--campaign-dir` on freeze/reselect-check/mark), gate, record.jsonl field, exit rule, unmark rule and fixed string from the brief is present.
  - The reason strings are asserted verbatim in the tests: visible fields `, `-joined in VISIBLE_FIELDS order, `recording re-selection: <stored> -> <pick>`.
  - Pointers (a)-(d) are implemented and each is caught by a mutant. (e) is a runbook note for a later task, with no code here: restoring the overrule backfill after marking refuses every marked delivered show until marking is reversed, so reverse marking first.
- **Untouched:** junk filter, `DURATION_TOLERANCE_S`, `audio_reuse`, purge verification, piece-3 constants, `STOP_AFTER_LLM_FAILURES`, `load_list`, `briefing_reusable`. The `Manifest` model is unchanged. Nothing imports emcee. No llama source file is changed; only the script and its test.
- **Lock:** there is no nested `file_lock`. `mark_apply` and `unmark` take one show lock per item. Ledger reads take no lock.

## Concerns / interpretation calls (for the reviewer)

1. **Plain show lock, not `show_unit`, for marking.**
   - The brief says to use `show_unit` "where a failure must roll the library back". For marking, the library mark is the safe direction: a station refusal must leave it in place, listed.
   - So `_mark_one` uses `file_lock(ws.lock)` and never rolls the campaign mark back.
2. **"no station copy" counts as OK for the exit code.** That outcome means the item is ledger-delivered and the station root is mounted, but `<station>/<slug>` does not exist.
   - I read "Exit 0 only when every delivered item is marked or already marked" together with "for a delivered show with a station copy" and the enumerated not-marked cases (`skipped: inputs changed`, `refused: …`, emcee stop).
   - A missing station ROOT refuses up front (exit 2), so a dropped mount cannot pass as "no station copy". A missing dir under a live root has no package for emcee to voice.
3. **Delivered-ness is the ledger's** (`is_delivered`, as everywhere else in llama), re-read under each item's lock via a stat-keyed cache.
   - A station dir for a slug with no ledger `delivered` entry is NOT station-marked.
   - The plan's table classifies a held delivered show as delivered, because that decides the station mark.
4. **`mark_added`** is "the campaign record holds a mark with this batch's id". It is not "this particular attempt wrote one".
   - Otherwise a re-run of a refused item, whose library is already awaiting from this batch's first attempt, would record `mark_added: false` on its `marked` line. `unmark` would then leave this batch's station mark in place.
   - `unmark` uses each slug's LAST line, for the same reason.
5. **Frozen-rule reason when the row has no `needs_llm`** (an unreplayable or no-longer-needs-LLM row still on the frozen list):
   - It reads `replay needs an LLM call: on the frozen needs-LLM list`. The contract string has nothing to put after the colon in that case.
   - With a non-empty `needs_llm` the reason is exactly the contract's.
6. **unmark order** follows the brief: `put_back(before)` then `remove_marks`.
   - If `remove_marks` fails after a successful `put_back`, the library stays awaiting and the station is unmarked.
   - A re-run sees the station sha equal to `before_sha256` and just removes the mark.
   - unmark also checks emcee before each `put_back` (the same concurrency risk as marking). This is my addition.
7. **reselect_rows refuses the whole check** on a show it cannot read, on a cache miss, or on an unreadable delivered station manifest (StationUnreadable → exit 2). It does not silently drop that row, since a dropped row would silently change a show's route.
8. **Limitation (safe direction):** a crash between `write_mark` and the record append leaves a station mark with no record line.
   - The re-run records `already marked` (no shas), so `unmark` cannot put those station bytes back.
   - The mark goes with re-delivery, as every mark does.

---

# Fix round 1 (review I1)

**Commit:** `d1bb0127 fix(bulk): marking lists a delivered show with no station copy; a stat error refuses`

## Changes (`scripts/bulk_apply.py`), per the orchestrator's ruling
1. **The station copy is decided with `os.stat`.** The new helper `_station_copy_problem(out)` returns:
   - `no station copy` only on `FileNotFoundError`;
   - `refused: station copy unreadable (<one line>)` on any other `OSError`, or when `out` exists but is not a directory;
   - None when the directory is there.

   `_mark_one` uses it in place of `out.is_dir()`. The dry run's `_station_state` uses it too: a stat error there goes to `delivered unreadable` with the detail.
2. **The brief's exit rule, literally.** `_STATION_OK` is now `("marked", "already marked")`. A delivered `no station copy` item is listed and the batch exits 1.
3. **The exit code and listing cover the whole record.**
   - After the loop, every slug whose last `record.jsonl` line is not `marked`, `already marked` or `not delivered` is listed as `<slug>: <station> (recorded)`. This includes lines from earlier runs of the batch.
   - This run's own listings take precedence: inputs changed, errors, not reached, and fresh station outcomes.
   - A re-run that skips a terminal `no station copy` therefore still exits 1 and lists it. A refused item is still retried as before.
   - The docstring is updated.

Moved expectation (listed before editing): `test_unmark_removes_library_only_marks`. Its second `mark_apply` on the same batch now expects 1, not 0, because that batch's record still holds `bad` refused (ruling 3). No other expectation moved. Minor review items were left alone, as instructed.

## Covering tests (new)
- `test_missing_station_copy_is_listed_exit_1_and_stays_listed`: a ledger-delivered show with no station dir gives `no station copy`, is listed and exits 1. A re-run still exits 1 and lists it, with no new record line.
- `test_station_copy_stat_error_is_refused_then_retried`: an `os.stat` wrapper raises EIO for that path only. The item is `refused: station copy unreadable (... Input/output error ...)`, listed, exit 1, station bytes untouched. A re-run with the real stat marks it and exits 0.
- `test_unreadable_station_root_is_refused_per_item`: the per-item `refused: station root <p> is not readable`, with `mark_added` true, listed, exit 1. It covers existing behaviour, so it passed at RED, as expected.

## RED (live tree, before the fix)
`./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q -p no:cacheprovider`
```
E       AssertionError: assert 0 == 1
E       AssertionError: assert 0 == 1
FAILED scripts/test_bulk_apply_mark.py::test_missing_station_copy_is_listed_exit_1_and_stays_listed
FAILED scripts/test_bulk_apply_mark.py::test_station_copy_stat_error_is_refused_then_retried
2 failed, 26 passed
```
Both failures were the bug itself: exit 0 where `no station copy` should have been listed, and the EIO swallowed as `no station copy`.

## GREEN
- `./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q -p no:cacheprovider -W error`: `28 passed`.
- Full suite, `./.venv/bin/python -m pytest -q`: `6291 passed, 1 skipped, 8 deselected, 26 warnings` (6288 + 3 new).

Breaking the fix on purpose in a scratch copy: each breakage was caught by the predicted test.

| Breakage | What it does | Tests that failed |
|---|---|---|
| f1 | `no station copy` back in the OK set | missing-copy test |
| f2 | `is_dir()` before the stat | stat-error test |
| f3 | whole-record pass removed | missing-copy test and library-only test |
