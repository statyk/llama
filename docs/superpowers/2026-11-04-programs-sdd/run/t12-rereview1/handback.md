### Finding Verdicts

- **1. (R13) A lock that cannot be created must stop the batch like a held lock** — ADDRESSED. `scripts/bulk_apply.py:955-981` adds `_LockRefused` and `_station_locked`. It turns `StationLocked`, every other `LlamaError` from acquire (llama `station_lock.py:152-153`, EACCES and similar on `os.open`) and a raw `OSError` (the write or fsync path, `station_lock.py:162-172`, which unlinks and re-raises) into one retryable `refused: ...` line plus a `_Stop`. The body is entered only after `stack.enter_context` succeeds, so body errors pass through as before. That matches the old `entered`/re-raise behaviour, and `StationLockReentry` (a RuntimeError) still escapes.
  - mark: `_mark_one` sets `station, stop = exc.station, exc.stop`. The library mark is already added at this point. `mark_apply:1062,1080` prints `refusing to mark station copies: <reason>; the batch stops` and lists `not reached (<reason>)`.
  - unmark: `unmark` (diff, the `except _LockRefused` branch) echoes `<slug>: <exc.station>`, then the stop lines, then `<rest>: not attempted`, and returns 1.
  - Tests pin both paths, each with three parametrizations (read-only root, os.open refuses, fsync fails): `test_mark_stops_when_the_lock_cannot_be_created` and `test_unmark_stops_when_the_lock_cannot_be_created` in `scripts/test_bulk_apply_mark.py`. They check the one-line record, that the library mark was added, that later items got no campaign record, that `not reached (<reason>)` is listed, that the station is byte-identical with no lock left, and that a re-run marks everything (retryable).
  - RED against the 6937a751 `bulk_apply.py` is in the t12-impl log: 6 failed, each for the right reason (the batch carried on: `'p' == 'a'`; `d2: not attempted` was missing; fsync gave the bare `[Errno 5]`).
- **2. (R13) Each contract test and `test_unmark_dry_run_takes_no_lock` shown failing once against a broken lock, in a scratch copy, prediction first** — ADDRESSED. The evidence is in `.superpowers/sdd/programs/t12-impl/t12-impl.log:189-275`.
  - Baseline: 68 passed. Restored: 68 passed.
  - Mutants M1-M8 each log `predicted red:` before `observed red:`, and all 8 match exactly.
  - Every contract test is covered: constants by M1; both refusal directions by M2 and M3; show/clear by M4; release in both directions by M5 and M6 (M6 hits the new reverse-direction pin); same body order by M7. The dry-run test is covered by M8.
  - Each failure message fits its mutant: `.lck != .lock`, "llama acquired a lock emcee holds", clear exit_code 1, FileNotFoundError, `'was not ours' in ''`, `host != command`, unmark returning 1 on the foreign lock.
  - The report says shadowing was proven (`__file__` of llama, emcee, both `station_lock` modules and `bulk_apply` all inside the scratch tree), the bytecode cache was isolated (`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `__pycache__` deleted per mutant), and pytest ran via `python -m` from an empty cwd. The log's `../tree/scripts/...` test paths agree that the scratch tree was the one collected. Credible.
- **3a. Early return gave `[]`, must be `None`** — ADDRESSED. The diff in `_mark_one` now has `return "skipped: inputs changed", delivered, None`.
- **3b. `mark_apply` docstring line about 125 columns** — ADDRESSED. It is re-wrapped, and no line of `mark_apply` is now over 100 columns (awk check).
- **3c. Same body keys in the same order; reverse release direction asserts emcee's "not ours" warning** — ADDRESSED.
  - `scripts/test_station_lock_contract.py:103-117` adds `test_both_tools_write_the_same_body_lines_in_the_same_order`: 6 lines ending in `\n`, the magic first line, both `token_of` parse it, and the keys are `[tool, command, host, pid, started]` for both tools. M7 shows it catching a key-order mutant.
  - `test_station_lock_contract.py:97-98` asserts `was not ours` and `tool: llama` in stderr after `esl.release(theirs)`.

### New Breakage in the Fix Diff

- Minor: `scripts/bulk_apply.py:1182`, the `unmark` docstring line ("stops the reversal there, ... The dry run takes no station lock.""""), is 118 columns. The fix report says unmark's lock sentence was re-wrapped, but this line got longer. It is the same class of defect as 3b, but on a line the fix itself introduced. It should be wrapped, and it does not block.

### Out-of-Scope Observations

- `scripts/bulk_apply.py:1777` and `:1982` are 102 columns. They predate this fix and are cosmetic.

### Checks run

- Read the diff file, the implementer report and fix report, the t12-impl log lines 150-294, and `station_lock.py` acquire and `for_package` (`:127-173`, `:319-324`).
- Ran awk for lines over 100 columns in `bulk_apply.py` and the two test files.
- Checked the `TAKEN_OVER` and `taken-over/t12-rereview1` flags: absent.
- Re-ran no tests. Reading the code raised no doubt that the logged runs don't already answer (68 passed covering; full suite 6872 passed).

### Verdict

**Fix round:** All findings addressed, no new Critical or Important breakage. One new Minor: the 118-column `unmark` docstring line at `bulk_apply.py:1182`.
