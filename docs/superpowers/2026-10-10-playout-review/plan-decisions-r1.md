# Plan-review decisions for docs/superpowers/plans/2026-10-10-playout-phase1.md

Apply each exactly, updating code blocks, tests, Interfaces blocks and prose wherever
the change reaches. Keep task boundaries. Every changed test must still be real code.

## Important
1. **Checkpoint dependency note:** change "Tasks 3, 5, 6 and 7 may proceed while the
   operator listens" to "Tasks 3, 5 and 7" (Task 6 consumes `layout.PlanRow` /
   `validate_rows` from Task 4).
2. **Timeline must not depend on the cache surviving:** the Publisher obtains each
   row's analysis through an injected `analysis_for(row)` callable (production: the
   engine's `analyze`, which reads-or-computes and caches), not by reading
   `analysis.load_cached` alone. Update Task 11/14 Interfaces and the
   `FakeEngine.analyze` double so `test_run_once_end_to_end` passes (notes/ and show/
   keys present).
3. **The run loop must survive ordinary errors:**
   - Task 5 `station.evaluate`: skip `dj-audio` entries whose names end in `.tmp`
     (emcee's temp files); treat any `OSError` during stat/hash as
     `Ineligible("changing")`. Add a test where a watched file vanishes between listing
     and stat.
   - Task 14 `Runner.tick`: catch `Exception` per step (plan, render, publish), log the
     traceback, call `alerts.alert(step, ...)`, continue. Add a test where a step raises
     `KeyError` and the next tick still runs.
   - Task 11 `publish_batch`: the site step catches `Exception` (record
     `report.error`; segments and horizon still advance). Task 10 uses
     `string.Template.safe_substitute`.
4. **Runbook service survives logout and crashes** (Task 18 §3 step 5): add
   `loginctl enable-linger <user>` and `--property=Restart=always
   --property=RestartSec=30` to the `systemd-run --user` line; say it runs as the
   operator's user in phase 1 (the system unit is phase 2).
5. **Off-air playlist MEDIA-SEQUENCE must not decrease** (Task 15 `offairPlaylist`):
   `EXT-X-MEDIA-SEQUENCE = indexAt(scheduledTime + loopMs)` (constant within an
   invocation, never decreasing). Remove the "static bytes on purpose" rationale.
   Player: on ENDLIST/off-air it stops playback (not only `showNotice`). Add a test
   that the off-air sequence ≥ the last live sequence for the same clock time.
6. **Pin "every attempt counts against the PUT budget"** (Task 11): the retry test
   asserts the persisted daily count equals the number of attempts (3); `test_r2`
   asserts `client.meta.config.retries["max_attempts"] == 1`.

## Minor (accepted)
7. **Prune horizon writes** (Task 12/14): prune runs only when at least
   `prune_min_segments` (default 60) are prunable; update the `daily_put_budget`
   comment's expected count to include prune/horizon writes (expected ≈ 8.9k/day,
   budget stays 17,500 ≈ 2×). Add a test that a tick with fewer prunable segments
   writes no horizon.
8. Task 16: declare `scheduled(controller, env, _ctx)`; drop "and the `* * * * *`
   trigger" from the dry-run expectation (check `wrangler.jsonc` instead); tests
   import `env`, `createScheduledController`, `createExecutionContext`,
   `waitOnExecutionContext` from `cloudflare:test`.
9. Task 11 `_publish_site`: when a package is unreadable (`manifest is None`) and a
   digest already exists for that slug, skip — never publish a degraded page.
10. Task 11 `publish_batch`: record the attempted segment range in local state
    *before* the first PUT, so prune covers segments uploaded by a batch that later
    stopped (budget or horizon PUT failure). Test it.
11. Task 9 `render_step`: if a row with no encode has already started airing
    (`r.start_frame < n*441`), raise `LayoutError` (alert) rather than re-plan into a
    mid-show cut. Test it.
12. Task 9/14 `FrameCountDrift`: set a `halted` latch on the Runner — stop filling,
    alert once, keep publishing what exists and keep the loop alive. Test it.
13. Task 9 `_gc_encodes`: also delete `.*.tmp` files in `render/shows/` older than
    1 h.
14. Task 10: rename `test_file_starts_follow_actual_frame_positions_minus_priming` to
    `..._plus_encoder_priming` (the code is right).
15. Global Constraints: add a short **Deliberate deviations/additions** block:
    Playwright smoke deferred to phase 4 (manual local smoke in Task 17); the safety
    stage is a clamp to [−1, 1] because the gain rule already keeps true peak ≤ −1
    dBTP; minimal `transmitter status` lands in phase 1; added knobs
    (`start_delay_minutes`, `batch_segments`, `prune_min_segments`, clip↔clip pause,
    `d` in `fallback/index.json`, the clock's `vars`, one-show-per-tick fill,
    null playlist = write nothing); `publish_lock` refuses rather than waits (a manual
    `publish` while `run` holds it exits 1 with a clear message).
16. Global Constraints commit trailer: replace the hard-coded model line with "end
    each commit with the attribution lines the harness supplies to you".

## Rejected
- Moving `spike.py` out of the package (its reuse of production modules is the point).
- Making `publish_lock` blocking (documented instead, item 15).
