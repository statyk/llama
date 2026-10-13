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
