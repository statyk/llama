# Task 14 handback
Status: DONE (docs only).
Wrote: docs/playout-setup.md -- rewrote "Rolling transmitter back" (names 4fa87a7, af46d72, 684d323 by hash+subject; af46d72 = oldest safe target once scheduler ran), new 7.2 "Clock and schedule (phase 3)" (clock/last-good, strict rules, draft workflow, invalid clock, awaiting_fix, aired.jsonl, plan lock, reporting semantics), new 7.3 "Announcements and station IDs" (ids, two-block rule, zones, export + emcee say workflow, quiet period, fallback chain, station-name note). CLAUDE.md -- transmitter Commands bullet extended (announcements, clock, plan lock), phases 1-3, new Scheduler architecture paragraph with evidence doc path.
Rollback-commit check: existing subsection named no hashes; now corrected. Hashes verified against git log (4fa87a7, af46d72, 684d323 subjects match).
Verification:
- ./.venv/bin/python -m pytest -q: 5215 passed, 1 skipped, 8 deselected, 26 warnings in 59.18s
- cd antenna && npm test: Test Files 21 passed (21); Tests 426 passed (426)
- packages/transmitter/scripts/test-in-debian12.sh: 887 passed in 38.07s
Concerns: config.py untouched (no change needed). Plan lock is non-waiting (PlanLocked), documented as refusal, not waiting. Quiet period = config quiet_minutes (default 10), assumed to govern interstitial clips too (it governs station.evaluate for packages; not verified for interstitial scan).
