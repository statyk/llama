# Task 15b, fix round 1: re-review (d6a9eb24..a2d5122d)

Scope: one commit, tests only (`scripts/test_bulk_apply_mark.py` +92). No production code changed (`scripts/bulk_apply.py` is identical to the fix base).

## Per-finding verdicts

### 1. M1 (`_mark_station` `return _UNVERIFIED, None, _sha(raw)`, bulk_apply.py:756): ADDRESSED
- The test is `test_unverified_own_mark_is_recorded_and_listed` (test_bulk_apply_mark.py:1074). It uses the helper `_crash_after_station_write` (:1053).
- The helper's run makes `_append_jsonl` raise after the station write. When it ends, the library mark and `before/d1.json` are on disk, the station copy is marked, and there is no record line.
- The test then rewrites `dj_notes` in the marked station copy. Evidence (1) therefore fails: the re-encoding of before plus mark is not `raw`. Evidence (2) also fails: there is no line.
- It asserts:
  - the line is `ba._UNVERIFIED`, with `mark_added` true, `before_sha256` None and `after_sha256` == sha(changed);
  - rc 1;
  - `d1` is listed;
  - the station bytes are unchanged.
- This matches what the finding asked for.
- Independent mutant run (a2d5122d scratch copy): the only failure is this test, at the rc assert (`assert 0 == 1`), 1 failed, 41 passed. That was my prediction.

### 2. M2 (`_own_station_mark` `if not saved.exists()`, bulk_apply.py:941): ADDRESSED
- The test is `test_unmark_lists_an_unreadable_station_copy_with_a_before_copy` (:1099). It is parametrized over a `refused: Input/output error` line and a `marked, before copy not saved (x)` line. The second starts with `_UNSAVED`, so both lines take the `_own_station_mark` branch at :977.
- Setup: the library mark is at the line's `at`, `before/d1.json` is present, the station manifest is `{not json`, and `mark_added` is true.
- It asserts:
  - `unmark --apply` gives rc 1;
  - a `d1: cannot check the station copy for this batch's mark` line is printed;
  - the library record is byte-equal (the mark is kept);
  - the station copy is untouched.
- Mutant `if True:`: both parametrizations fail at the rc assert, 2 failed, 40 passed, as predicted.
- The inverse direction (an unreadable copy with NO before copy is not a problem) was already pinned. In `test_unmark_removes_library_only_marks` (:749), the `bad` show is refused while unreadable and has no saved copy, and `unmark` exits 0.

### 3. M7 (evidence (1)'s `newline=before.endswith(b"\n")`, bulk_apply.py:726): ADDRESSED
- The test is `test_recognises_own_mark_on_a_copy_with_no_trailing_newline` (:1125). The station copy is re-encoded the way llama encodes it, with no trailing newline, and the test asserts that encoding (:1129). The run then crashes after the station write and runs again.
- It asserts:
  - the line is `marked` with `before_sha256` == sha(original), rc 0;
  - then `unmark` gives rc 0 and the station bytes are restored byte-identical to the original.
- Evidence (2) cannot mask the mutant, because there is no record line.
- Mutant `newline=True`: the only failure is this test (`assert 1 == 0` on the mark_apply rc), 1 failed, 41 passed, as predicted.

### Mutant method (mine, independent of the implementer's)
- A `git archive a2d5122d | tar -x` copy per mutant, plus an unmutated control (M0: 42 passed).
- Run from the scratch dir with `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<copy>/packages/llama/src:<copy>/scripts`, the worktree venv's `python -m pytest -p no:cacheprovider`.
- `llama.__file__`, `bulk_apply.__file__` and `llama.station_mark.__file__` all resolved inside each copy (logged in t15b-rereview.log).
- The scratch copies were removed afterwards.
- These results agree with the implementer's log (t15b-impl.log:402-421).

## New breakage in the fix diff
- Critical: none.
- Important: none.
- Minor (cosmetic, does not block):
  - unused locals in the new tests: `original` and `ws` in the M1 test, and `cfg` in the M2 test;
  - the helper's 7-tuple return is only partly used.
- Hygiene checks:
  - all writes are under `tmp_path`;
  - `emcee_running` is stubbed by the module's autouse fixture (:34-37), so no test reads `ps`;
  - every new test asserts outcome, record line and bytes.

## Deferred minors (out of scope)
- `_crash_after_station_write` simulates the "crash" with an exception that `mark_apply` catches per item (rc 1), not with a process death. That is adequate for the on-disk state it needs (it asserts no record line and a marked station copy). A real SIGKILL path is not exercised; no change is requested.

Verdict: all findings addressed
