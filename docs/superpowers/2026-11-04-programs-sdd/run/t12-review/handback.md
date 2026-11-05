### Spec Compliance

- ✅ Spec compliant. I checked every requirement in the brief and in the spec's "The station lock" section (design.md:57-63) against the diff.
  - `_Stop` is a frozen dataclass and `_mark_one` returns `tuple[str, bool, _Stop | None]`.
  - The lock is taken after `_station_root_problem` and before `_station_copy_problem`. It spans `emcee_running()` and `_mark_station`, all inside `with station_lock.for_package(out, command="bulk_apply mark")` (bulk_apply.py:988-1000).
  - A held lock gives station `refused: the station is locked` (retryable) and stops with `_Stop("the station is locked", …)`.
  - `mark_apply` prints `refusing to mark station copies: {reason}; the batch stops` and lists later items as `not reached ({reason})`.
  - `unmark --apply` takes `for_package(station_root / slug, command="bulk_apply unmark")` inside the show lock. On a held lock it prints `{slug}: refused: the station is locked` and lists later slugs as `not attempted`, then returns 1. The dry run takes no lock (bulk_apply.py:1169-1193).
  - The `scripts/CLAUDE.md` text covers the three required points: lock per show with a stop, the v2.20.1 pin ignores the lock, and the `backfill_*.py` scripts are not lock-aware.
  - All 7 named mark tests and all 5 named contract tests are present.
- ✅ Claim (1), "bulk_apply has no clear-mark writer". The spec names "each `bulk_apply` mark, clear and put-back step"; I checked whether bulk_apply has a station writer that escapes the lock. Grepping bulk_apply.py for `station_mark` writers finds only `write_mark` (:872, inside `_mark_station`) and `put_back` (:1141, inside `_unmark_one`), plus `emcee_running()` at :993, :1138 and :1293 (read-only plan print). There is no `clear_mark` call. `batch_snapshot.restore` (bulk_apply.py:130) also takes `station_root`. Its docstring says it "never writes the station" (batch_snapshot.py:18-19); I did not read the restore code itself. So every station write in bulk_apply is now under the lock.
- ✅ Ruling R6 (atomicity under `os._exit`). The handler releases the lock by token and calls `os._exit`; neither touches caller code (llama/station_lock.py:249-273). Both station writes in the locked spans are single renames, according to the implementer's citations, which I did not re-read: `write_mark` and `put_back` go through `_swap_in`, and the before copy goes through `_durable_replace`.
  - An exit inside `_mark_station` leaves a durable library mark and no record line. That is the existing M1 case: `unmark` lists "no record line".
  - An exit between `put_back` and `remove_marks` is healed on a re-run: current == `before_sha256`, so the `elif` at bulk_apply.py:1127 is skipped and the code falls through to `remove_marks`.
- ✅ Re-entrancy. Nothing under either new `with` acquires the lock again (`_station_copy_problem`, `emcee_running`, `_mark_station`, `_unmark_one`). `StationLockReentry` is a `RuntimeError`, not a `LlamaError` (station_lock.py:70). So the acquire-failure branch at bulk_apply.py:1002 cannot turn a reentry bug into a retryable `refused:`. It reaches `mark_apply`'s `except Exception` as `error: …` and is listed.
- ✅ Claim (3), the stop lines are the whole `str(exc)`. That is the right call: it is the only form that carries the `emcee lock show`/`emcee lock clear` hint the spec requires the refusal to name, and `StationLocked`'s docstring says the whole refusal lives in `str(self)` (station_lock.py:55-60).
- ⚠️ Cannot verify from the diff: the atomicity of `station_mark._swap_in` and `batch_snapshot._durable_replace` (R6) rests on the implementer's citations. The controller or the branch reviewer should confirm that each is one `os.replace`.

### Strengths

- The lock span matches the brief exactly. The test that wraps `_station_copy_problem` and `emcee_running` (test_bulk_apply_mark.py, `test_mark_takes_the_lock_before_the_first_station_read`) would go red if either ran outside the lock.
- The `entered` flag (bulk_apply.py:987-1003) separates "the lock could not be created" from errors raised in the body, which still propagate as they did before the change.
- The held-lock mark test checks four things: the station tree is byte-identical, the one-line record carries no holder text, later items get no library mark, and a re-run marks every item once the lock is gone.
- The `_lock_state` fixture asserts that no lock is left held after each test.
- The contract tests go both ways (emcee refuses llama, llama refuses emcee, a release never unlinks the other tool's lock) and cover `emcee lock show`/`emcee lock clear` on a lock that llama wrote.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. bulk_apply.py:968: the early return on changed inputs still returns `[]` as its third element, not `None`. That contradicts the new `_Stop | None` annotation and the brief's interface. It works only because `[]` is falsy in `if stop:`. Fix: return `None`.

2. bulk_apply.py:1002-1005: when the lock cannot be created (EACCES, an unmounted share), the item is recorded as `refused: cannot create the station lock …` and the batch continues. The brief does not ask for this, and no test covers it.
   - It is safe, because the refusal is retryable and the item is listed.
   - Every later delivered item will almost certainly be refused the same way, so the output is noisy.
   - Fix: add a test that pins the branch (a station root made read-only). Optionally, treat this case as a stop as well.

3. bulk_apply.py:1178-1185 (follows the brief literally): `unmark --apply` takes the station lock for every `mark_added` line, including `not delivered` lines whose reversal touches only the library.
   - Before this change, a library-only reversal worked with the station unmounted. Now `for_package` fails to create the lock, and the line is refused through the generic `except Exception` at bulk_apply.py:1190.
   - A held lock also stops the library-only reversals.
   - On an empty, unmounted mountpoint directory, the lock file is briefly created on the local disk.
   - All of this fails in the safe direction. If it is unwanted, take the lock only when `line.get("station") != _NOT_DELIVERED`. That needs a brief change, so it is the controller's call.

4. bulk_apply.py:1023: the edited `mark_apply` docstring line runs to about 125 columns. The re-wrap was left unfinished.

5. test_station_lock_contract.py:
   - Nothing checks that the bodies the two tools write have the same line keys in the same order (`tool:`/`command:`/`host:`/`pid:`/`started:`). Only the magic first line is cross-parsed, through `token_of`. A cheap pin: acquire with each tool and compare `[l.split(":")[0] for l in body.splitlines()[1:]]`.
   - The reverse release (`esl.release(theirs)`, :95) does not assert emcee's "not ours" warning, while the llama direction does.

6. The contract tests and `test_unmark_dry_run_takes_no_lock` were green before the change; the implementer says so. They have never been seen red. A one-line mutant would show that each one bites, run in a scratch copy: for example, emcee's `LOCK_NAME`, or dropping the token check in either tool's `release`. Recommended, not run.

### Assessment

**Task quality:** Approved

**Reasoning:** The lock is taken at the specified point, it spans the station copy's first read through its last station write, it is token-safe and not re-entrant, and both batch loops stop on a held lock with retryable records. The tests that matter would go red if the span or the stop regressed. What remains is cosmetic or a choice for the controller (the not-delivered case in `unmark`).
