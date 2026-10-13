# t14-impl report
Status: DONE_WITH_CONCERNS
Implemented the brief as written: deadclock.py (+tests), publish.guard_blocks_publishing caches guard_evaluated_at/offair, service.open_monitor + Runner(monitor=) + `dead-clock` step after publish, cli run wiring.
Deviations: (1) OFFAIR_KEY defined in publish.py; cloudstate.py now imports it from publish instead of defining its own (same string, no cycle since cloudstate already imported publish). (2) Added one extra test in test_publish.py: cache fields recorded, offair never gates, unreadable offair never gates, unreadable guard still fails closed with error recorded.
Gating: unchanged (tripped only; fail-closed on guard read error; same freshness check). Only addition: a second get of state/offair.json on a cache refresh, errors swallowed (offair=None). Behaviour changes: one extra R2 Class B read per guard refresh (every 15 min); existing test asserts it.
LEVEL_CODES in alerts.py already includes dead-clock and guard-stale.
Concerns: a guard-cache.json written by the old code lacks guard_evaluated_at; right after upgrade, until the next refresh (<=15 min), the guard-stale alert can fire spuriously (guard_cache error None, no timestamp). Brief's logic; not changed.
Unused `import logging` in test_deadclock.py (from brief).
Tests: transmitter py3.14 404 passed; py3.11 404 passed; Debian-12 gate 404 passed; full llama suite 2560 passed, 7 deselected. TDD RED step not separately captured (code and tests applied together).

# Fix round 1
Changes (all 10 items): fetch_text catches URLError/OSError/HTTPException/ValueError -> (0,"") (HTTPError first, 403 kept), reads at most 1 MiB; monitor tracks `guard_error_since_us` and alerts `guard-stale` (naming the error) after guard_stale_s of a persisting cache error, cleared when the error goes; a cache with no `guard_evaluated_at` key is silent, a null one alerts; service.tick passes `self.clock()` (wall clock at check time) to the monitor; comment that counters reset only on a good read; message wording updated; unused `import logging` removed; tests for each (stale/fresh/stale/fresh, 403 with blocked=True over 20 checks, raising urlopen incl. 403 status kept and no alert on first call, unreadable-guard persistence/alert/recovery, key-absent vs null, cli run passes monitor=open_monitor(st)). publish.py untouched.
Deviations (ruled): item 2 (monitor-side unreadable-guard alert), item 4 (absent key = unknown), item 5 (wall clock at check time; thresholds remain counts). The existing service test now injects a clock.
Mutants (scratch copy, PYTHONPATH shadow proven: transmitter.__file__ resolved in scratch; python -m pytest; base 18 passed):
- M1 (remove `self.stale = 0`): RED test_stale_fresh_stale_fresh_never_alerts (1 failed, 17 passed).
- M3 (drop guard_cache.get("blocked") from 403-expected): RED test_403_while_the_guard_says_blocked_never_alerts_even_past_the_threshold (1 failed, 17 passed).
Gates: transmitter py3.14 415 passed; py3.11 415 passed; Debian-12 415 passed (docker OK); full llama suite 2571 passed, 7 deselected.
