# Task 13 handback
Status: DONE_WITH_CONCERNS. Commit: see git log ("feat(transmitter): hugo alerts by SMTP (STARTTLS) and ntfy, deduped per code in alerts.json").
Implemented the brief verbatim (alerts.py, AlertsConfig + R4 validator, Workspace.alerts_path, Runner._step resolves/station-root, cli run configure/finally, template, tests).
Deviations (hardening, small):
- Dispatcher._load tolerates corrupt JSON / OSError (starts afresh); fire() tolerates non-dict entries, non-numeric last_sent_at/count.
- resolve(): if the entry had been sent and channels exist but none accepts the "resolved" message, the code stays active (retried at next success) instead of being cleared silently.
- Added 3 tests (corrupt state, undelivered not recorded + resolve retry, channels have timeouts).
Already OK in brief: undelivered fire leaves last_sent_at None (retried); channels have timeouts (SMTP 20s, ntfy 10s).
Tests: transmitter suite 384 passed on py3.14, py3.11, Debian-12 (docker); full llama suite 2540 passed. config init prints [alerts]. RED run not separately captured (files were installed with implementation in one step).
Concerns: a down channel costs up to 20s+10s blocking on each alert/resolve call in the service loop (bounded by timeouts, retried per occurrence, not per repeat window). SMTP timeout covers socket ops, not total wall time.

## Fix round 1
Changes (alerts.py): per-channel failure cool-down (CHANNEL_COOLDOWN_S = 300, keyed by id(channel), a skipped channel counts as not delivered); Dispatcher keeps its own record (_mem) merged with alerts.json by `updated_at`, newer wins, so an unwritable file no longer storms; suppressed note now also on a late first delivery ("N more since the first"); ntfy Title RFC 2047-encoded when not latin-1; docstring/comment on the deliberate failed-resolve lag.
Deviations from the brief (ruled): items 2, 3, 5, 6.
Tests: R16 wiring (test_service parametrized plan/render, Dispatcher + recorder, asserts "resolved" and active()==[]); test_cli run installs and clears dispatcher (configure == [sentinel, None]); corrupt-state test now asserts exact send counts and no "alert dispatch/resolve failed" warning; cool-down, skipped-counts-as-undelivered, unwritable-file dedupe (write_json raising), late-delivery note, partial success, RFC 2047 title, ntfy timeout == 10.0, smtp 20.0.
Mutants (scratch copy, PYTHONPATH shadowing proven, python -m pytest, empty cwd), predictions named first, all RED:
- M1 both resolves=() -> test_a_successful_step_resolves_its_level_codes (both params): 2 failed.
- M2 drop configure line -> test_run_installs_the_alert_dispatcher_and_clears_it_afterwards: 1 failed.
- M3 drop last_sent_at normalisation -> test_a_corrupt_state_file_does_not_wedge_alerting: 1 failed.
Gates: transmitter 393 passed on py3.14, py3.11, Debian-12; full llama suite 2549 passed.
