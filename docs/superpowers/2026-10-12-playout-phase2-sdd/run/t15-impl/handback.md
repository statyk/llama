# t15-impl report
Status: DONE_WITH_CONCERNS (the concern is the R15 gap note below; nothing to fix in this task)

Commit: 3e79a8a feat(transmitter): systemd unit (Type=notify, WatchdogSec, Restart=always) and sd_notify pings

Implemented, as the brief wrote it: sdnotify.py; systemd/transmitter@.service; test_systemd.py (6 tests); service.py (the five edits, keeping Task 14's monitor and held).
Files: packages/transmitter/src/transmitter/{sdnotify,service}.py, packages/transmitter/systemd/transmitter@.service, packages/transmitter/tests_transmitter/test_systemd.py. Committed by explicit paths.
Deviations: none. TDD: I wrote the implementation before running the test file, so there is no RED capture (a process lapse; the tests are the brief's verbatim).
Tests: py3.14 `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` = 421 passed; py3.11 = 421 passed; Debian-12 gate (docker info OK) rc 0, all dots, so the real AF_UNIX datagram ran on Linux (the -q output printed no summary line).

## R15 self-review: WATCHDOG=1 placement within one tick (report only)
Pings: `_step`'s `finally` (after each of plan, render, publish, dead-clock, even on exception), and inside `publish_all` after each publish batch. There is none during prune, nor between `_read_lead` calls (cheap, local).
Blocking calls and the longest gap each can open:
- Render step: one ping only after render_step returns; the gap is up to one render_step call (limit=batch_segments, encoding one show per the brief's ~10-20 min). Dominant gap, well under 45 min unless a show is very long or ffmpeg stalls (that is what the watchdog is for).
- Alert sends: alerts.alert runs inside the failing step (and in `_read_lead`, `_report_stop`), before that step's finally ping. Each channel has its own timeout (SMTP 20 s, ntfy 10 s), and per CHANNEL_COOLDOWN_S failures cost one timeout per channel per cool-down, so at most about 30 s per alert call. Several alerts in one step (publish_all can alert per batch, plus prune) add up but stay in minutes; the dedupe and cool-down bound them.
- Dead-clock fetch: fetch_text has a 10 s timeout per socket op (not a wall-clock cap; a slow-drip server could stretch it, but it is a single GET), pinged after the dead-clock step.
- Publish step: pinged per batch, so the gap is one batch's PUTs plus prune (prune, publish_site, and the row_analysis fallback that may run a full ffmpeg analysis under the publish flock "for minutes" per its docstring, are not followed by a ping until the step ends).
- The sleep between ticks (up to tick_s = 60 s) is unpinged.
Conclusion: no single gap approaches 45 min in normal operation; the largest is one show's encode (10-20 min). Residual risk: a render step stacked behind a very long show or a stalled NFS read is by design a watchdog kill. Worst plausible stack in one tick (render ~20 min + a slow row_analysis re-analysis + alert timeouts) is still under about 30 min.
# t15-fix1 report
Status: DONE. Commit 8cfef0b fix(transmitter): watchdog pings in prune, render encodes and the fail-closed tick; notifier typing; sd_notify tests
Tests: py3.14 425 passed, 1 skipped (abstract-socket test, Linux-only) / py3.11 425 passed, 1 skipped / Debian-12 gate 426 passed (the abstract-socket test runs there).

RED first (before the fix, `./.venv/bin/python -m pytest .../test_systemd.py .../test_prune.py -q`): 3 failed, 22 passed, 1 skipped:
- F1 test_prune_feeds_the_watchdog_every_batch_of_deletes: TypeError: prune() got an unexpected keyword argument 'notify'
- F2 test_a_tick_that_fails_closed_on_an_unreadable_publish_state_still_pings: failed (no ping sent)
- F3 test_render_step_pings_after_each_show_encode: TypeError: render_step() got an unexpected keyword argument 'notify'
GREEN: full suite as above.

Per finding:
- F1: publish.prune(p, now_us, notify=None) pings WATCHDOG=1 every cfg.publish.batch_segments deletes; publish_all passes its notifier. No progress persistence. Test: batch=10, 200 deletes -> 20 pings.
- F2: tick's early return on an unreadable publish.json sends one WATCHDOG=1. Test asserts exactly one ping and no step ran.
- F3: pipeline.render_step(..., notify=None) pings after each encode_show (after the frame-count check call site's encode); Runner.tick passes self.notify. row_analysis docstring now says a lost cache/ recompute can be long enough to meet WatchdogSec (docs only).
- F4: comment on the brief's runner test corrected; added test that a raising step is still followed by a ping.
- F5: caplog assertion on the failure test; Linux-only abstract-socket test (skipif sys.platform != "linux").
- F6: notifier annotation is Callable[[str], object] in Runner, publish_all, prune, render_step.

Deviations (forced by the changes, flagged):
1. The brief's runner test count 4 became 5: the failing render step now pings once for its encode before it fails, plus its finally ping. Assertion and comment updated.
2. Test monkeypatches of publish.prune (`lambda p, t_us:` in test_systemd.py, `lambda p, t:` in 8 places in test_service.py) now take `notify=None`, because publish_all passes the notifier positionally. Mechanical signature change only.
