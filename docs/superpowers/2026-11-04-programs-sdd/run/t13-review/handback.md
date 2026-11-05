### Spec Compliance

- ✅ Spec compliant. All three briefed files are touched: `scripts/station_probe.py` (new), `scripts/test_station_probe.py` (new), and `scripts/CLAUDE.md` (diff line 28). `race`, `mtime --create|--replace|--remove`, `cross` and the hidden `STATION_PROBE_TEST_DROP_EXCL` switch match the interface.
  - Output format and exit code: station_probe.py:143-145 prints the briefed line verbatim, and :181 exits 0 only on `double 0`.
  - `double` comes only from the token re-read (:107-113). The marker overlap only increments `overlap` (:102-105).
  - A contender reads the holder and counts a vanished file (:86-95).
  - Every scratch file is removed in a `finally` (:170-174, `_cleanup` :148-153). The leading-dot glob matches, and the tests assert `tmp_path` is empty.
  - Writer order at :213-225 is temp, write, flush, fsync, close (with-exit), `os.utime`, rename, re-check, re-apply. This matches the Global Constraints. It also matches `emcee/retitle.py:186-214`, minus retitle's compare-before-replace step, which the constraint does not require.
  - The env switch is absent from `--help` (docstring :46-54). The switch is read inside the worker (:78), so spawned workers inherit it through the environment.
- ⚠️ Cannot verify from the diff: the py3.11 and pytest-only run, the full suite (6878 passed) and `npm test` (545 passed) are implementer claims. A static read finds no syntax newer than 3.10, and `sys.stdlib_module_names` exists in 3.10 and later. The test file imports only ast, os, subprocess, sys and pathlib.
- Extra: `test_cross_runs_one_side_and_cleans_up` (test :319-323) was not briefed, but it covers a briefed subcommand cheaply. Acceptable.

### Strengths

- Detection that can actually fail. In the scratch mutant m3 (env switch ignored, `if True:` at :78) `test_race_detects_a_broken_exclusive_create` failed, as I predicted. That confirms the DROP_EXCL path really reaches spawned workers, and that the exit code tracks `double`.
- The `Barrier` start (:80-81, :159) makes contention real at n=50 rather than relying on luck.
- Worker exceptions go back through the queue (:128-132) and give exit 2 rather than hanging the parent.
- `cross` never unlinks the shared lock unless its own token is in it, and removes only its own marker (:184-195).
- The AST stdlib test (test :326-336) is a real check (`assert mods` guards against an empty set).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **`test_mtime_replace_sets_mtime_before_rename` does not pin the order its name claims** (test_station_probe.py:301-309, code at station_probe.py:218 and :224-225).
   - **What I checked:** I ran scratch mutants with `python -m pytest`, no bytecode, from the scratch cwd.
     - m1 replaced the pre-rename `os.utime(tmp, ...)` (:218) with `pass`: all 6 passed.
     - m2 replaced the post-rename re-apply (:225) with `pass`: all 6 passed.
     - I predicted both survivals before running them.
   - **Why it matters:** the lens says this probe is worthless if its order differs from the writer's. Today the code order is correct. But either half could be deleted and the suite would stay green, and the test name would say it is pinned.
   - **Fix:** import the module in-process (it is stdlib-only, so this works under 3.11), wrap `os.rename` with monkeypatch to record `os.stat(src).st_mtime` at rename time, and assert it equals 1767225600. For the re-check, patch `os.rename` to also bump the destination's mtime, then assert the final mtime is still 1767225600.

#### Minor (Nice to Have)

1. **A race with no contention passes as proof** (station_probe.py:181, :195). Exit 0 needs only `double 0`, so `contended 0` would also exit 0.
   - This matters most for `cross`, which has no start synchronisation across hosts. If one side finishes before the other starts, the run proves nothing and still exits 0.
   - Fix: make `cross` exit nonzero, or warn, when `contended == 0`. Or add a start gate, such as waiting for a `.lock-race-<tag>.go` file or a `--start-at` epoch.
2. **A killed `cross` can leave the shared lock behind** (station_probe.py:186-193). The `finally` removes only this side's marker.
   - If role a is killed while holding the lock, `.lock-race-<tag>` stays, and role b counts every remaining round as `contended`. Afterwards nobody removes it.
   - Fix: in the `finally`, unlink the lock if it holds this side's last token. Also document the by-hand cleanup in `scripts/CLAUDE.md`.
3. **A contender's non-ENOENT `OSError` is swallowed uncounted** (station_probe.py:93-94). On SMB, a read of a delete-pending file may come back as EACCES. A counter such as `unreadable` would make that visible in the go-live run, rather than hiding it under `contended`.
4. **A failed worker start can hang the parent for about 6 minutes** (station_probe.py:167). If one worker dies before reporting (for example, killed at spawn), the other worker's `barrier.wait(timeout=60)` reports an error. The parent then blocks on `queue.get(timeout=300)` for the missing result and exits with a `queue.Empty` traceback, not a clean exit 2.
5. **No validation on `--n` or `--workers`** (station_probe.py:236-237). `--workers 0` returns `double 0` and exit 0 vacuously, and `--workers 1` cannot race.
6. **The re-check compares whole seconds** (station_probe.py:224), while the real writer compares `st_mtime_ns` (retitle.py:213). With an integer target this is equivalent, so it is only a divergence to note.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The probe is correct, stdlib-only, and its double-acquisition detection demonstrably fails when it should (m3 was caught). However, the mtime test passes whether or not either half of the writer order is present (m1 and m2 survived), so the order this go-live probe exists to prove is not pinned. That is a small test-only fix.
