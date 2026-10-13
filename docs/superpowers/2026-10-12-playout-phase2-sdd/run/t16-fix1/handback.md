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
