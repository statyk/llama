# Task 20 implementer handback: `reapply --from-list` / `--dry-run`

**Status: DONE**

**Commit:** `23ac815` feat(reapply): --from-list batches with state, a pacing gate, stop rules and list checks (BASE `e73eea6`; there was no Task 19 fix commit after it.)

## What changed
- `packages/llama/src/llama/reapply.py`
  - `STOP_AFTER_LLM_FAILURES = 3`.
  - `load_list(path, *, sha, fingerprint) -> dict`. It raises `LlamaError` in three cases:
    - the file is unreadable or not JSON (`cannot read list ...`);
    - the shape is wrong: `rows` is not a list, or a row lacks a str `slug` or a dict `digests`;
    - the sha or fingerprint differs from the running code. That message is verbatim from the brief: `list {path} was written for code {list_sha} and config {list_fp}; running code is {sha}, config {fingerprint}`.
  - `batch_dir(root, list_path)` = `root/"reapply"/sha256(list bytes)[:16]`.
  - `read_progress(batch)` returns slug → last row. It returns `{}` when there is no file, and skips any line that does not parse (a crash mid-append), so that show is simply not finished.
  - `record_progress(batch, slug, outcome, retryable)` appends `{"slug","outcome","retryable","at"}` under `file_lock(batch/"progress.lock")`. If the file does not end in a newline, it writes one first, so a cut-short line cannot swallow the next row.
- `packages/llama/src/llama/cli.py`
  - `reapply`: passing both `names` and `--from-list` exits 1. The list form is `_reapply_list`. The names form now calls `set_capture_dir(config.root / "llm-failures")` unless `--dry-run`.
  - `_reapply_list` steps:
    1. `load_list` against `replay.code_identity()` and `config_fingerprint(config)`. A `LlamaError` exits 1.
    2. Unless `--dry-run`: `set_capture_dir`, create the batch dir, copy `list.json` if absent.
    3. Rows whose last progress row has `retryable` false are skipped silently.
  - Per row:
    - **Pacing gate** (not in dry-run): `_meter`, then `decide(_pacing._now(), reading, Progress(state.per_show_delta), pace)`. On `PauseUntil` it prints `paused: {str(verdict)}` and `  resume with: llama reapply --from-list {path}`, then returns (exit 0).
    - **Missing show:** an absent `root/shows/<slug>` prints `missing: {slug}` and records `skipped: missing` with `retryable=True`.
    - **Entry (M3):** built per row inside the try: `ShowWorkspace(dir)`, then `derive_state`, then `CatalogEntry`. `catalog.iter_shows` is never used.
    - **Exception arms:**
      - `RateLimited`: prints paused and the resume line, records nothing, returns.
      - `TaskFailed`/`HerderError`: `FAILED`, recorded retryable, `consecutive += 1`. At 3 it prints `stopping after 3 consecutive LLM failures; resume with: llama reapply --from-list {path}` and exits 1.
      - `IAError`/`LlamaError`/`ValueError` (which covers pydantic `ValidationError` and JSON decode errors)/`OSError`: `FAILED`, recorded retryable, continue. These do not touch `consecutive`.
    - **Success:** resets `consecutive`, records with `retryable=False`, prints `reapplied: {slug} -> {outcome}` and the re-deliver hint when the show is delivered and cleared. When `_meter_applies`, it prints `  meter: 5h {before}% -> {after}%` (`?` for a reading that failed).
    - `pacing_state.record` is never called.
  - `--dry-run`: no batch dir, no progress, no gate, no capture. Per row it prints `would: {slug} -> {predicted}`, then the `summary: ...` line verbatim from the brief.
  - Exit codes: 1 if any row failed or the 3-failure stop fired; 0 on a pause or a clean finish.
- `packages/llama/tests/test_reapply.py`: 15 new tests (25 → 40 in the file).
  - The brief's 8 tests, with M5's `herder.tasks._sleep` stub.
  - Additions:
    - `test_a_success_resets_the_consecutive_llm_failure_count`
    - `test_one_malformed_overrides_fails_its_row_and_the_batch_continues` (M3)
    - `test_a_corrupt_show_json_fails_its_row_and_does_not_count_as_an_llm_failure` (minor 4: three bad rows fail without the LLM stop firing)
    - `test_the_reapply_command_switches_on_llm_failure_capture` (C2: both forms set it, dry-run in both forms does not)
    - `test_the_show_lock_is_held_when_the_row_digests_are_checked` (mutant h)
    - `test_record_progress_survives_a_cut_short_line`
    - `test_the_gate_reads_the_meter_around_each_show_and_never_records_pacing_state` (meter line `5h 40% -> 42%`; `pacing_state.record` patched to raise)
  - An autouse fixture resets `herder.failures._capture_dir` after each test, so the command's global capture dir does not leak into later tests.

## Tests
- `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py -q` → `40 passed`.
- `./.venv/bin/python -m pytest -q` → `3728 passed, 1 skipped, 8 deselected, 26 warnings in 50.73s` (Task 19 head: 3713).
- `./.venv/bin/python -c "import llama; print(llama.__file__)"` → a path inside the worktree.

## Mutation table
Scratch root `MROOT=$(mktemp -d "$TMPDIR/mut-t20-impl-XXXXXX")` = `.../T//mut-t20-impl-OeZ7dn`, logged, and removed as that exact path afterwards. There was one rsync copy per mutant, a `PYTHONPATH` shadow and a per-mutant `PYTHONPYCACHEPREFIX`. The shadow check printed `$MROOT/<m>/tree/...` for every mutant. Predictions were written to the log before any flip.

| mutant | predicted test | caught by |
|---|---|---|
| (a) `consecutive` not reset on success | test_a_success_resets_the_consecutive_llm_failure_count | test_a_success_resets_the_consecutive_llm_failure_count |
| (b) a `RateLimited` show recorded as progress (finished) | test_a_refusal_mid_show_leaves_it_uncommitted_and_the_list_resumable | the same test |
| (c) `missing` recorded `retryable=False` | test_missing_show_is_skipped_and_not_finished | the same test |
| (d) `load_list` ignores the fingerprint | test_list_from_another_sha_or_config_is_refused | the same test |
| (e) M3 reverted to `iter_shows` | test_one_malformed_overrides_fails_its_row_and_the_batch_continues | the same test, and also test_a_corrupt_show_json_fails_its_row_and_does_not_count_as_an_llm_failure |
| (h) show.json re-read, not-held skip and digest skip moved above `with file_lock(ws.lock):` | test_the_show_lock_is_held_when_the_row_digests_are_checked | the same test |

No survivors.

## Deviations from the brief
1. **M3 / minor 4:** entries are built per row, never through `iter_shows`, and the non-LLM arm catches `ValueError` (a superset of `ValidationError`, as in `replay.py`) plus `OSError`.
2. **`downloads` / `fresh` in the dry-run summary** count only rows that `reapply_show` actually predicted (`dry-run: <x>`) other than `held`. A held show packages nothing, so counting it as a download would overstate the cost. Rows that are missing, failed, `needs-llm` or `skipped: ...` are not counted. The summary text is verbatim.
3. **Dry-run skips rows already finished** in an existing batch, counts them as `already finished`, and creates nothing. It runs no pacing gate and switches on no capture.
4. **Exit codes:** the list form exits 1 when any row failed or the 3-failure stop fired, matching the names form. A pause exits 0, which the brief's tests require. The brief named exit codes only for the mutual exclusion.
5. **A non-LLM failure leaves `consecutive` unchanged.** It neither resets nor increments it.
6. **`load_list` also validates the row shape** (str `slug`, dict `digests`), so a malformed list fails up front rather than as a `KeyError` mid-batch.

`reapply_show`'s contract is unchanged.

## Concerns
- `code_identity()` appends `-dirty` when the worktree has uncommitted changes. A list written from a dirty tree is therefore refused by a clean one, and the reverse. That is correct, but at Checkpoint G the operator needs the same committed tree for `compare` and `reapply`.
- "First-time downloads" is decided by whether `package/manifest.json` is absent, as the brief specifies. A show with a manifest but purged audio would re-download without being counted. Held shows are normally never delivered, so this should be rare.
- The meter line prints `?` when `_meter_applies` is true but the read failed. This is deliberate: the operator sees that the gate is blind.

---

# Fix round 1

**Status: DONE.** Commit `2eae5c6` fix(reapply): refuse -dirty code identities; last-resort row arm; stricter LLM-failure reset. It sits on top of `23ac815`.

## What changed
1. **IMPORTANT: a `-dirty` identity is now refused on either side.** `load_list` raises `LlamaError` when the list's `sha` or the running `code_identity()` ends in `-dirty`. The message is `list {path} was written for code {list_sha}; running code is {sha}: an uncommitted tree has no code identity, commit first and re-run the harness`. The clean/clean mismatch message is unchanged.
   - The suite must not depend on the checkout being committed. The autouse fixture in `test_reapply.py` now patches `llama.replay.code_identity` to a fixed clean `CLEAN_SHA`, and `_list_file` writes that same value.
   - Tests:
     - `test_a_dirty_code_identity_is_refused_on_either_side` covers a dirty list under both a dirty and a clean running identity, and a clean list under a dirty running identity; a clean/clean pair is still accepted.
     - `test_the_cli_refuses_a_list_when_the_running_tree_is_dirty`: the command exits 1 and creates no batch dir.
2. **Last-resort `except Exception` arm** in the per-row handling, placed after every other arm (`RateLimited` and the LLM arm stay above it). It goes through `fail()`: `FAILED {slug}: {exc}`, recorded with `retryable=True`. It leaves `consecutive` alone, and the batch continues.
   - Test: `test_any_other_exception_fails_only_its_row`. The rows are HerderError, RuntimeError, HerderError, then a success. There is no stop and no traceback, and the RuntimeError row is retryable.
3. **The counter resets only on a real LLM success.** That is an applied row (`out.outcome in ("cleared", "held")`) with `out.briefing == "fresh"`.
   - The outcome guard is there because `needs-llm` can carry `briefing="fresh"` from the replay without making any call.
   - `test_a_success_resets_...` already scripts its success as `("cleared", "fresh")`, so it stays meaningful.
   - New test: `test_rows_that_made_no_llm_call_do_not_reset_the_failure_count`. The rows are fail, reuse, fail, needs-llm(fresh), fail: it stops after 3 failures with exit 1, and the 6th row is never reached.
4. **Both pause paths exit `1 if failed else 0`** (the pacing `PauseUntil` and `RateLimited`).
   - Test: `test_a_pause_after_a_failed_row_exits_1` covers both paths: a LlamaError row followed by RateLimited, then a re-run where the row fails again and the gate pauses.
5. **New coverage:**
   - `test_dry_run_over_an_existing_batch_counts_and_skips_finished_rows` (D2): `1 already finished`, no `would:` line, `progress.jsonl` untouched.
   - `test_dry_run_counts_fresh_briefs_and_downloads_only_for_rows_it_would_apply` (D1): four rows predicted cleared, held, needs-llm and needs-brief, all `fresh`. The summary gives `2 fresh briefs, 2 first-time downloads (~0.3 GB)`.
   - The 3-failure-stop test now asserts `exit_code == 1`.
6. **Warnings check:** `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py -q -W error` gave `47 passed`, and `-rw` lists no warnings. The new tests emit none, so the suite's 26 warnings come from elsewhere.

## Commands and output
- `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py -q` → `47 passed in 1.33s`
- `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py -q -W error` → `47 passed in 1.75s`
- `./.venv/bin/python -m pytest -q` → `3735 passed, 1 skipped, 8 deselected, 26 warnings in 50.39s`

## Mutation
Scratch root `$TMPDIR/mut-t20-impl-XogPWt`, logged and removed as that exact path. Same recipe as before: one rsync copy per mutant, a `PYTHONPATH` shadow, a per-mutant `PYTHONPYCACHEPREFIX`, and a shadow check per mutant that printed the copy's path. Predictions were logged before any flip.

| mutant | predicted test | caught by |
|---|---|---|
| (i) the dirty check removed from `load_list` | test_a_dirty_code_identity_is_refused_on_either_side | that test, plus test_the_cli_refuses_a_list_when_the_running_tree_is_dirty |
| (j) the counter resets on any success | test_rows_that_made_no_llm_call_do_not_reset_the_failure_count | the same test |
| (k) the last-resort arm removed | test_any_other_exception_fails_only_its_row | the same test |
| (l) both pause paths exit 0 | test_a_pause_after_a_failed_row_exits_1 | the same test |
| (a') `consecutive` never reset | test_a_success_resets_the_consecutive_llm_failure_count | the same test |

No survivors.

## Not addressed
Minor 6 from the review (two concurrent runs of the same list overwrite the outcome record) was not among the ruled items, so it is unchanged. Finished-ness is unaffected.
