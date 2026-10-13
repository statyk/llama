VERDICT: ALL ADDRESSED

### Finding verdicts
- **F1: ADDRESSED.** `publish.py:372` `prune(p, now_us, notify=None)` pings `WATCHDOG=1` whenever `report.deleted % p.cfg.publish.batch_segments == 0`, inside the delete loop (publish.py:~441). `batch_segments` is `ge=1` (config.py:78), so the modulo cannot divide by zero. There is no progress persistence, as ruled. `service.py:154` `publish_all` passes its notifier through. Test `test_prune.py::test_prune_feeds_the_watchdog_every_batch_of_deletes` uses batch=10 and 200 deletes and asserts exactly 20 pings. Because the count is exact, it catches both a ping on every delete (200) and a hard-coded batch size.
- **F2: ADDRESSED.** `service.py:~229`: the fail-closed early return in `tick` now calls `self.notify("WATCHDOG=1")`. It is the only path through `tick` that runs no `_step`, because publish always runs after it. `test_systemd.py::test_a_tick_that_fails_closed_on_an_unreadable_publish_state_still_pings` asserts `sent == ["WATCHDOG=1"]`, which also proves no step ran. The handback records it red before the fix.
- **F3: ADDRESSED.** `pipeline.py:207` `render_step(..., notify=None)` pings straight after `encode_show` (pipeline.py:271-273), before the FrameCountDrift check. That is the only `encode_show` call site in src. `service.py:238` passes `notify=self.notify`. `test_render_step_pings_after_each_show_encode` asserts one ping per encode. I traced it and it encodes **2** shows (`['ENCODE','WATCHDOG=1','ENCODE','WATCHDOG=1']`), so it does pin the multi-show case. The `row_analysis` docstring (service.py:67-68) now notes that a lost-`cache/` recompute can meet WatchdogSec. That is a docs-only change, as ruled.
- **F4: ADDRESSED** (see the Minor below about the comment's wording). The runner test's comment now says the render step FAILS. The new test `test_a_step_that_raises_is_still_followed_by_a_watchdog_ping` calls `_step` with a raising fn and asserts `sent == ["WATCHDOG=1"]`, which pins the ping in `finally`.
- **F5: ADDRESSED.** The failure test asserts `"sd_notify(READY=1) failed"` through caplog on logger `transmitter`. `test_notify_sends_to_an_abstract_socket` is `skipif(sys.platform != "linux")`. It is skipped locally, and the Debian-12 gate passed with one more test (426 vs 425), which is consistent with it running there.
- **F6: ADDRESSED.** All four use `Callable[[str], object]`: `Runner.__init__` (service.py:178), `publish_all`, `prune` (publish.py:372) and `render_step` (pipeline.py:208). `Callable` is already imported in both pipeline.py and publish.py.

**Deviation (1), runner count 4 → 5: forced by F3, and the explanation is TRUE.** I instrumented the brief's runner test with no clock injected. The event trace is `READY=1, STEP plan, WATCHDOG=1, STEP render, ENCODE, WATCHDOG=1, WATCHDOG=1, STEP publish, WATCHDOG=1, WATCHDOG=1, STOPPING=1`. So the render step does reach `encode_show` and pings. It then raises in `store.build_segment` with `ValueError: segment index must be >= 0, got -215644705`, and `_step`'s `finally` pings again. F2's "keep 4 valid" was about the fail-closed path. F2's fix adds no ping on this path, and F3's per-encode ping is what makes the count 5.

**Deviation (2), prune lambdas gaining `notify=None`: forced.** Threading the notifier into `prune` (F1) breaks any 2-argument stub, whether the notifier is passed by position or by keyword. That covers all 8 stubs in test_service.py and 1 in test_systemd.py. A grep confirms no 2-argument `prune` stub remains (test_service.py:186 is a multi-line one that already has `notify=None`). Only the signature changed; no assertion did.

### New breakage in the fix diff
- **Minor:** the comment in `test_systemd.py` (runner test, about line 47) says "helpers.E is far in the past". It is the reverse: `E = 4_000_000_000 s` (helpers.py:145, the year 2096) is far in the FUTURE of the real clock, which is why the segment index comes out negative (`-215644705`). The comment gets the failure right but the reason wrong. It is a one-word fix ("past" → "future").
- **Minor (cosmetic):** the new `row_analysis` docstring line (service.py:68) runs into the old text, so that line is longer than its neighbours ("...ping). Acceptable: the cache is never garbage-collected, so this is reachable only"). It is still under 120 columns, so this is not a lint concern.

### Out-of-scope observations
- None new. The deferred minors (M3 STOPPING=1 unpinned, M6 the unit's After=/venv path, no RED capture) are still deferred, as ruled.

### Checks run
- Read the brief, the findings and rulings, the handback, and the diff 3e79a8a..8cfef0b. The worktree is at 8cfef0b and clean.
- Confirmed `transmitter.__file__` resolves inside the worktree.
- Trace script (in the scratchpad, run with `python -I`, nothing in the worktree touched) replicating the brief's runner test: the events are as quoted above, which proves render reaches `encode_show` before it raises.
- Trace of `render_step(st, NOW)` after `plan_step`: 2 encodes and 2 pings, 33 segments written.
- grep: one `encode_show` call site in src; no 2-argument `prune` monkeypatch left; `batch_segments` is `ge=1`.
- Focused run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_systemd.py packages/transmitter/tests_transmitter/test_prune.py -q` gave 25 passed, 1 skipped (the Linux-only abstract-socket test).
- No mutants: every new test asserts an exact ping list or count, and the handback records them red before the fix.
