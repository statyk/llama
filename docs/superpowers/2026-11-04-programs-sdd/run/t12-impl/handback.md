# Task 12 handback: bulk_apply takes the station lock; lock contract test

Status: DONE_WITH_CONCERNS (minor concerns, below)
Commit: 6937a751 scripts: bulk_apply takes the station lock; lock contract test (base 4a916ddb)

## What was implemented
- `scripts/bulk_apply.py`
  - `@dataclass(frozen=True) class _Stop: reason: str; lines: list[str]`; `_mark_one` now returns `tuple[str, bool, _Stop | None]` (the no-show-dir early return gives `None`).
  - In `_mark_one`, once the show is delivered and `_station_root_problem` passes, `with station_lock.for_package(out, command="bulk_apply mark")` wraps `_station_copy_problem(out)`, `station_mark.emcee_running()` and `_mark_station`. The emcee stop is `_Stop("emcee is running", running)`. On `StationLocked`: station outcome `refused: the station is locked` (single line, retryable because it starts with `refused`), `_Stop("the station is locked", str(exc).splitlines())`. These lines include the header with the lock path, the holder lines and the `emcee lock show/clear` hint. They are echoed only, never written to the record. A non-`StationLocked` `LlamaError` raised while *acquiring* (e.g. EACCES creating the lock) becomes `refused: <one line>` for that item with no stop. One raised after entering is re-raised, as before.
  - `mark_apply` prints `refusing to mark station copies: {reason}; the batch stops`, then `  <line>` for each stop line, and lists later items as `not reached ({reason})`.
  - `unmark(..., apply=True)` wraps each `_unmark_one` in `for_package(station_root / slug, command="bulk_apply unmark")` inside the show lock. On `StationLocked` it echoes `{slug}: refused: the station is locked`, then the indented lock lines, then `{rest}: not attempted` for every later slug in the record, and returns 1. With `apply=False` it takes no lock.
  - Docstrings of `_mark_one`, `mark_apply`, `unmark` updated.
- `scripts/CLAUDE.md`: a **Station lock:** sentence after the subcommand list. It says that mark/unmark --apply lock per show and stop on a held lock, and gives the exact outputs. It says the `ps` check stays, that the v2.20.1 pinned campaign worktree ignores the lock (`emcee retitle`'s `ps` check is the guard), and that the `backfill_*.py` one-offs are not lock-aware.
- `scripts/test_station_lock_contract.py` (new): the 5 contract tests named in the brief.
- `scripts/test_bulk_apply_mark.py`: the 7 tests named in the brief (+ `station_lock` import, a `_lock_state` fixture asserting no lock is left held).

## Tests
- RED: `./.venv/bin/pytest scripts/test_bulk_apply_mark.py scripts/test_station_lock_contract.py -q` → `5 failed, 56 passed`. Failing: test_mark_holds_the_station_lock_around_write_mark, test_mark_takes_the_lock_before_the_first_station_read, test_mark_stops_at_a_held_lock_and_lists_the_rest, test_unmark_apply_holds_the_lock_around_put_back, test_unmark_apply_stops_at_a_held_lock_and_lists_the_rest. Expected: there was no lock in bulk_apply yet (e.g. unmark returned 0 and put both copies back under a foreign lock).
  - The 5 contract tests and test_mark_emcee_running_stop_unchanged / test_unmark_dry_run_takes_no_lock PASSED at RED. That is expected: they pin behaviour that already existed (Tasks 5/10) or that must stay unchanged. They were not mutation-checked.
- GREEN focused: same command → `61 passed` (also clean with `-W error`).
- Full: `./.venv/bin/pytest -q` → `6865 passed, 1 skipped, 8 deselected, 26 warnings in 80.13s` (no warning from the touched files). One intermediate full run errored at collection (a docstring quoting slip of mine: `""""""`). It was fixed before the commit and the green run above is post-fix.

## Atomicity check (ruling R6)
- Mark write: `station_mark.write_mark` → `_rewrite` → `_swap_in` (packages/llama/src/llama/station_mark.py:122-137): temp `x`-created in the package dir, flushed, `os.replace`. Atomic. The before copy `_write_durable` → `batch_snapshot._durable_replace` (batch_snapshot.py:93-112): mkstemp + fsync + `os.replace`. Atomic (and library-side).
- Unmark put-back: `station_mark.put_back` (station_mark.py:195-205) → `_swap_in`. Atomic.
- Sequences: an exit between the mark rename and its record line is the existing M1 case (re-run recognises it). An exit between put-back and `campaign.remove_marks` is healed on re-run (current == before_sha → mark removed). One note, not a defect: `_rewrite`'s verify-failure path (station_mark.py:150-159) does a second rename (`put_back`). Each rename is atomic, but an exit between the two leaves the marked bytes over another writer's change. That path only fires when another writer intervened, which the lock now excludes except for lock-unaware tools (the existing documented residual window).

## Re-entrancy
Nothing under either new `with` acquires the lock again: `_station_copy_problem`, `emcee_running`, `_mark_station` (read_station_manifest, _write_durable, write_mark, _reversal) and `_unmark_one` (campaign.read_record, put_back, remove_marks). The `_lock_state` fixture asserts `_held is None` after each lock test.

## Self-review / concerns
1. The spec's lock paragraph also names a bulk_apply "clear" step. bulk_apply has no clear-mark writer (only `write_mark` at bulk_apply.py `_mark_station` and `put_back` in `_unmark_one`), so mark and unmark cover every station write in it.
2. `unmark --apply` also takes the station lock for not-delivered lines (the brief says "each `_unmark_one` call"). That is harmless but means a held lock stops even library-only reversals. It follows the brief literally.
3. The `_Stop.lines` for a held lock are all of `str(exc)`'s lines (header with the lock path, holder lines, emcee hint), not just the holder lines, so the operator sees the clear command. If the brief meant holder lines only, use `exc.holder.splitlines()`.
4. Choice not in the brief: a non-`StationLocked` acquire failure (cannot create the lock) records `refused: ...` and does not stop the batch.
5. The contract tests were green on arrival (they test Task 5/10 code). Their RED is not a demonstrated failure.

Files: scripts/bulk_apply.py, scripts/test_bulk_apply_mark.py, scripts/test_station_lock_contract.py, scripts/CLAUDE.md

---

# Fix round 1 (R13, R14)

Commit: f0b480ce scripts: bulk_apply stops on a station lock it cannot create; contract pins

## 1. A lock that cannot be created stops the batch (R13)
- New `_station_locked(out, *, command)` context manager in scripts/bulk_apply.py, used by both `_mark_one` and `unmark --apply`. Every failure to *take* the lock raises `_LockRefused(station, stop)`:
  - held: `refused: the station is locked`, `_Stop("the station is locked", str(exc).splitlines())`.
  - `LlamaError` from create: `refused: <one line>`, e.g. `refused: cannot create the station lock at <path>: [Errno 13] Permission denied`. The reason is the same text without `refused: `.
  - raw `OSError` from writing or fsyncing a new lock (acquire unlinks it and re-raises): `refused: cannot create the station lock ([Errno 5] Input/output error)`.
  - Errors from the body pass through untouched, because the lock is entered via ExitStack before the body.
- mark: the item's library mark is added, the record holds that one-line retryable outcome, the batch stops (`refusing to mark station copies: <reason>; the batch stops`), and later items are `not reached (<reason>)`.
- unmark --apply: echoes `<slug>: refused: ...`, then the stop lines (holder lines when held), then `<rest>: not attempted`, and returns 1.
- scripts/CLAUDE.md: the station lock sentence now says a lock that cannot be created stops the same way.
- New tests, each parametrized over `read-only root` (chmod 0555 station root), `open refuses` (os.open raises PermissionError on the lock path) and `fsync fails`:
  - `test_mark_stops_when_the_lock_cannot_be_created`: asserts the one-line `refused: cannot create the station lock...` record with no newline, the library mark added, the stop line, later items `not reached (<reason>)`, station byte-identical with no lock left, and a re-run after the fix marks everything.
  - `test_unmark_stops_when_the_lock_cannot_be_created`: asserts return 1, `d1: refused: cannot create the station lock...`, `d2`/`p1` `not attempted`, station byte-identical, and campaign records unchanged.
- RED: run in the scratch copy with HEAD's (6937a751) bulk_apply.py: `6 failed, 56 deselected` (all six parametrizations). The mark cases fail on `assert ('p' == 'a'`: the batch carried on, so later items wrote record lines. The unmark cases fail on `'d2: not attempted' in [...]`, and fsync gives `'d1: refused: [Errno 5] Input/output error'`.

## 2. Mutation check of the contract tests and the dry-run test (R13)
Scratch copy: `git archive HEAD | tar -x` into the scratchpad, with the three working files overlaid, run from an empty cwd. The command was `<worktree>/.venv/bin/python -m pytest -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1`, PYTHONPATH shadowing llama/emcee/herder/transmitter src and scripts, and `__pycache__` deleted before each mutant. Shadowing was proven first: `llama.__file__`, `emcee.__file__`, both `station_lock.__file__` and `bulk_apply.__file__` all resolved inside the scratch tree. Baseline in the scratch copy: 68 passed. After restoring: 68 passed. Each mutant's prediction was written in the driver before it ran. All 8 predicted red sets matched exactly.

| Mutant | Predicted red | Observed |
|---|---|---|
| M1 emcee `LOCK_NAME = ".lma-station.lck"` | test_lock_constants_agree, test_emcee_lock_refuses_llama_naming_emcee_holder, test_llama_lock_refuses_emcee_naming_llama_holder, test_emcee_lock_show_and_clear_handle_a_llama_lock | those 4 failed, 2 passed; `assert '.lma-station.lck' == '.lma-station.lock'` |
| M2 llama acquire drops O_EXCL | test_emcee_lock_refuses_llama_naming_emcee_holder | 1 failed; `Failed: llama acquired a lock emcee holds` |
| M3 emcee acquire drops O_EXCL | test_llama_lock_refuses_emcee_naming_llama_holder | 1 failed; `Failed: emcee acquired a lock llama holds` |
| M4 emcee `lock clear` exits 1 unless `tool: emcee` | test_emcee_lock_show_and_clear_handle_a_llama_lock | 1 failed; `assert 1 == 0` (exit_code of clear --yes) |
| M5 llama release skips the token check | test_release_of_one_tool_never_unlinks_the_others_lock | 1 failed; `FileNotFoundError: ... .lma-station.lock` (emcee's lock unlinked) |
| M6 emcee release silent on a foreign lock | test_release_of_one_tool_never_unlinks_the_others_lock | 1 failed; `assert ('was not ours' in '')` (the new reverse-direction pin) |
| M7 emcee writes `host:` before `command:` | test_both_tools_write_the_same_body_lines_in_the_same_order | 1 failed; `'host: Shawns-Mac-mini.local' == 'command: emcee test'` |
| M8 unmark takes the lock in the dry run too | test_unmark_dry_run_takes_no_lock | 1 failed, 61 passed; `assert 1 == 0` (unmark refused on the foreign lock) |

The full driver output is in t12-impl.log.

## 3. Minors (R14)
- a. `_mark_one`'s inputs-changed early return gives `None`, not `[]`.
- b. The `mark_apply` docstring is rewrapped, and so is unmark's lock sentence.
- c. New `test_both_tools_write_the_same_body_lines_in_the_same_order`: both tools write 6 newline-terminated lines, the magic first line, and body keys `["tool","command","host","pid","started"]` in that order. The reverse release direction now asserts emcee's `was not ours` warning (naming `tool: llama`).

## Tests
- Covering: `./.venv/bin/pytest scripts/test_bulk_apply_mark.py scripts/test_station_lock_contract.py -q` → 68 passed.
- Full: `./.venv/bin/pytest -q` → `6872 passed, 1 skipped, 8 deselected, 26 warnings in 83.94s`.

## Concerns
None new. Out of scope as ruled: unmark still locks never-delivered shows.
