# Task 15 fix round 1 — findings to fix (orchestrator rulings applied)

F1 (spec Important, plan-mandated — RULED: fix). `publish_all` calls `publish.prune(p, t_us)` after the last batch ping with no notifier. After a long stop prune issues thousands of sequential DELETEs (≈8.4k at lead_hours=24) and saves `state.runs` only at the end, so a watchdog kill mid-prune restart-loops forever. Fix: `prune(p, now_us, notify=None)` (optional, default None keeps every other caller unchanged) pings `WATCHDOG=1` every `batch_segments` deletes (use the publisher's configured batch size; mirror publish_all's batch ping); `publish_all` passes its notifier through. Do NOT add mid-loop progress persistence (ruled out: with pings, only a genuine hang is killed). Test in the style of `test_publish_all_feeds_the_watchdog_after_every_batch`: drive a prune of more than one batch of deletes and assert the ping count.

F2 (quality Important — RULED: fix). `tick` returns early when `_read_lead` fails (unreadable publish.json) without running any `_step`, so no WATCHDOG=1 is sent; a designed, alerted fail-closed state becomes a watchdog kill every 45 min. Fix: every path through `tick` that runs no `_step` sends exactly one `WATCHDOG=1` (e.g. on the early-return path). Keep the brief's runner test count (4) valid. Test: one tick with a corrupt publish.json sends at least one WATCHDOG=1 (must be red before the fix).

F3 (both reviewers' Minor on R15's bound — RULED: fold, partial). `render_step` can encode more than one show inside one step (a window crossing a show boundary; the restore case re-encodes the on-air show then the next). Fix: `pipeline.render_step(..., notify=None)` pings WATCHDOG=1 after each `encode_show`; `Runner.tick` passes `self.notify`. Pin with a test (monkeypatch encode is fine). The `row_analysis` lost-`cache/` path is NOT threaded (ruled: docs only) — update `row_analysis`'s docstring to say the recompute can be long enough to meet WatchdogSec when cache/ is lost, and nothing else.

F4 (quality M2 — RULED: fold). The runner test reaches its count of 4 through a FAILING render step (no clock injected; helpers.E is 2096). Keep the brief's test as is but correct its comment to say so; ADD an explicit test that a step which raises is still followed by a WATCHDOG=1 (ping in `_step`'s finally, not the success path).

F5 (quality M4 — RULED: fold). `test_notify_failure_is_logged_not_raised` should assert the warning is logged (caplog). Add a Linux-only (`skipif(sys.platform != "linux")`) test of the `@` abstract-socket branch; it runs in the Debian-12 gate.

F6 (quality M5 — RULED: fold). Make the notifier annotation consistent between `Runner` and `publish_all`/`prune`/`render_step` (`Callable[[str], object]` everywhere is fine).

Not in this round (deferred minors in the ledger): STOPPING=1 unpinned (M3); unit's After=remote-fs.target / hard-coded venv path (M6); no RED capture (process).
