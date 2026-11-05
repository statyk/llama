# Task 13 handback
Status: DONE. Commit: see `git log -1` (scripts: station_probe, the go-live lock and mtime probes).
Files: scripts/station_probe.py, scripts/test_station_probe.py (6 tests: the 5 briefed + a cross test), scripts/CLAUDE.md.
RED: script moved away, `./.venv/bin/pytest scripts/test_station_probe.py -q` -> 6 failed (file missing). GREEN: 6 passed in ~4s.
Full suite: 6878 passed, 1 skipped, 8 deselected. antenna npm test: 545 passed.
Python 3.11: test file run under a 3.11 venv with only pytest: 6 passed. Imports are stdlib only (AST test).
Broken-create test: workers synchronise on a multiprocessing Barrier at start, n=50 -> 60-87 doubles over 8 manual runs, so not flaky; no n/hold changes needed (hold 5 ms).
Scratch cleanup in finally; tests assert tmp_path is empty after race (pass and broken) and cross.
Decisions: cross uses lock name `.lock-race-<tag>` and removes only its own marker; the shared lock is unlinked only by its token holder.
Not run: never touched the share or hugo.

## Fix round 1
Commit: 33198e55 scripts: station_probe review fixes (pin writer order, cross start gate and exit 3, unreadable counter, dead-worker exit, input validation)
- Important 1: mtime test now loads the module in-process and spies os.rename (records src mtime at rename time == 1767225600); a second test has rename bump the destination mtime and asserts the final mtime is still 1767225600. Scratch-copy mutants (git-free copy in the session scratchpad, PYTHONDONTWRITEBYTECODE, python -m pytest from the scratch cwd; the test resolves the script by __file__, so the mutation applying proves resolution): m1 (drop pre-rename utime) predicted and got red test_mtime_replace_sets_mtime_before_rename; m2 (drop re-apply) predicted and got red test_mtime_replace_reapplies_when_rename_bumps_mtime.
- Minor 1: cross takes --start-at EPOCH (chosen over a go file) and exits 3 with a message when contended == 0; race warns on stderr (exit tied to double). Because one side can win every round, the go-live pass is neither side 1 and at least one side 0 (documented). Tests: alone -> 3; two sides with --start-at -> codes (0, 0|3).
- Minor 2: cross finally unlinks the lock only if it holds this side's own token (tested via KeyboardInterrupt); by-hand cleanup documented.
- Minor 3: unreadable counter appended AFTER "(advisory)" so existing fields/order are intact; tested with a PermissionError holder read.
- Minor 4: parent polls the queue at 1 s and checks worker exitcodes; exits 2 with "a worker died". Test via hidden STATION_PROBE_TEST_CRASH=1 (worker os._exit(9)); returns in seconds, scratch removed.
- Minor 5: --workers >= 2, --n >= 1 via argparse (exit 2); tested.
- Minor 6 (ns compare) not changed.
Tests: scripts/test_station_probe.py 14 passed (3 repeat runs, stable); py3.11 venv in the session scratchpad: 14 passed; full suite 6886 passed, 1 skipped, 8 deselected.
