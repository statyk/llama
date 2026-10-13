# t16-fix2 report
Status: DONE. Commit 4ff1126.
RED: 4 new tests failed before the change (2 parametrized never-shows-own-verdict, unreadable-consequence, period-end-unknown); the brief's first test, given a schema-valid guard doc, stays green.
H1: corrupt guard prints the CORRUPT line in place of summary[0] (lines += summary[1:]). Brief test's guard doc now schema-valid (assertions unchanged). New test: for corrupt docs claiming tripped false/true no `guard      not tripped|TRIPPED` line, exactly one guard line.
  Mutant (scratch copy of HEAD, PYTHONPATH-shadowing proven: transmitter.__file__ resolved in scratch): `if problem is not None:` -> `if True:`. Mutant-only failures vs unmutated scratch baseline (baseline has env-artifact failures from missing files): test_status_shows_the_cloud_state_and_active_alerts (the brief test, RED as required) and test_one_unreadable_document_blanks_only_its_own_line.
H2: unreadable guard/offair lines now end `-- the clock treats it as a spend trip` / `-- the clock treats the station as off the air`; pinned.
H3: raise_status_line appends ` (period end unknown)` to an honoured verdict when period end is None (budget too); test_cloudstate's one budget assertion updated to the new wording; pinned in service tests.
Counts: py3.14 443 passed 1 skipped; py3.11 443 passed 1 skipped; Debian-12 444 passed.
Concerns: none.
