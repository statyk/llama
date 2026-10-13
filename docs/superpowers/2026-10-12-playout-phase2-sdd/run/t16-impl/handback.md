# t16-impl report
Status: DONE. Commit 078e533 feat(transmitter): status shows the cost guard, off-air flag, kill switch and active alerts
Files: service.py (cloud_lines, status_lines +cloud/cloud_error, imports cloudstate/TransmitterError), cli.py (status), tests_transmitter/test_service.py (2 tests appended).
Deviations: none; brief code used verbatim.
RED: test_service.py -> 2 failed, 26 passed (TypeError: status_lines() got an unexpected keyword argument 'cloud').
GREEN: py3.14 427 passed 1 skipped; py3.11 427 passed 1 skipped; Debian-12 gate 428 passed (rc 0).
status writes nothing; tests inject cloud=, no network. cli.status catches TransmitterError from _cloud (ConfigError subclass; missing keys from r2.make_client assumed TransmitterError-derived, not separately exercised).
Concerns: none.
# t16-fix1 report
Status: DONE_WITH_CONCERNS (one deviation). Commit 76e3c16.
RED: 11 new tests failed before the fixes (command: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_service.py -q -> "11 failed, 29 passed"; e.g. TypeError/JSONDecodeError/ValueError traceback from cli status).
GREEN: py3.14 439 passed 1 skipped; py3.11 439 passed 1 skipped; Debian-12 gate 440 passed.
G1: alerts.load_state(path)->dict|None (None for unreadable, non-JSON, non-dict); Dispatcher._load uses it (now also warns for a non-dict file); status prints `alerts     hugo: unreadable (<path>)`. Tests: corrupt alerts bytes `{not json`, `[1,2]`.
G2: cloudstate.raise_status_line(raised, guard, now_us) shared by `budget` (cli._raise_status removed) and status; amount via usd_text, verdict via raise_verdict; guard passed only when it passes guard_doc_problem. Test: budget_usd "abc", expired raise.
G3: offair absent/False -> off, True -> ON, anything else -> CORRUPT line; guard_doc_problem -> `guard      CORRUPT (<problem>): the clock treats it as a spend trip`. Tests: {"offair":"true"}, {}, absent/false, rejected guard doc.
G4: cloud_lines reads each key separately; new errors.CloudDocumentError(CloudStateError) raised by get_json for non-JSON/non-object, which prints `<label> unreadable: <exc>` and continues; any other failure ends with `cloud      unavailable: <exc>` (brief test unchanged and passing). get_json now wraps Body.read() failures in CloudStateError. Tests: offair.json not JSON, inactive alerts entry not listed, Body.read ConnectionError.
G5: cli.status catches Exception around client construction and wraps non-Transmitter exceptions from reads as CloudStateError; cloud_lines also has a broad catch. Test: malformed endpoint (make_client raising ValueError) exits 0 with local half + unavailable line.
G6: no-epoch branch appends cloud lines / cloud_error line. Test added.
Deviation: for a CORRUPT guard doc the full guard_summary lines (including the document's own `guard      TRIPPED (...)` line) follow the CORRUPT line instead of summary[1:], because the brief's test (unchanged, uses a schema-less guard doc) asserts `guard      TRIPPED (blind)` appears.
Concerns: Dispatcher now logs the "unreadable" warning for non-dict alerts.json too. Used monkeypatched make_client for the endpoint test rather than a real botocore ValueError.
# t16-fix2 report
Status: DONE. Commit 4ff1126.
RED: 4 new tests failed before the change (2 parametrized never-shows-own-verdict, unreadable-consequence, period-end-unknown); the brief's first test, given a schema-valid guard doc, stays green.
H1: corrupt guard prints the CORRUPT line in place of summary[0] (lines += summary[1:]). Brief test's guard doc now schema-valid (assertions unchanged). New test: for corrupt docs claiming tripped false/true no `guard      not tripped|TRIPPED` line, exactly one guard line.
  Mutant (scratch copy of HEAD, PYTHONPATH-shadowing proven: transmitter.__file__ resolved in scratch): `if problem is not None:` -> `if True:`. Mutant-only failures vs unmutated scratch baseline (baseline has env-artifact failures from missing files): test_status_shows_the_cloud_state_and_active_alerts (the brief test, RED as required) and test_one_unreadable_document_blanks_only_its_own_line.
H2: unreadable guard/offair lines now end `-- the clock treats it as a spend trip` / `-- the clock treats the station as off the air`; pinned.
H3: raise_status_line appends ` (period end unknown)` to an honoured verdict when period end is None (budget too); test_cloudstate's one budget assertion updated to the new wording; pinned in service tests.
Counts: py3.14 443 passed 1 skipped; py3.11 443 passed 1 skipped; Debian-12 444 passed.
Concerns: none.
