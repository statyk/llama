### Spec Compliance

- ✅ Spec compliant. All five brief files present (alerts.py, service.py, cli.py, test_service.py, test_cli.py); every Produces item is implemented as briefed. Orchestrator rulings:
  - (a) `_report_stop` (service.py diff 254-277) covers both publish and prune: put-budget goes to an alert; guard goes to info; prune high-water and "horizon held" go to WARNING; any other stop or error goes to an alert.
  - (b) cli.py 145-148 prints "horizon updated" / "horizon deferred"; pinned by test_cli 475-487.
  - (c) test_service 540-551 pre-renders, asserts seg/ PUTs and `state/horizon.json`.
  - (d) PlanError/StationRootError go through the generic `except Exception` arm and are pinned by the parametrized test 613-633. FrameCountDrift latches `halted` (service 307-313); pinned at 576-591 and 636-647.
  - (e) `E = 4_000_000_000 * 1_000_000` is in helpers.py:145; no unused imports in either test file.
- ⚠️ Cannot verify from diff: `transmitter plan` / `transmitter render` (cli 78-98) take no lock against a running `transmitter run`. Two processes can run plan_step/render_step concurrently, and render_step re-plans (write_plan) mid-loop (pipeline.py:258-262). The constraints only mandate a flock for publish and prune, so this is not a task defect. The whole-branch review should decide whether manual plan/render need to refuse while `run` is live.

### Strengths
- The spend posture of the loop is sound:
  - One tick per 60 s, with the sleep adjusted for time already spent (service 332-340).
  - `publish_all` is bounded at 100 batches and breaks on empty/stopped/error (285).
  - The guard and the PUT budget are enforced inside publish_batch and prune, so the runner cannot get around them.
  - While the guard is tripped or the budget is exhausted, filling only renders locally up to the lead target (bounded). Nothing reaches R2.
- The FrameCountDrift latch is correct. Ticks after the first cannot re-arm `filling` (321), so there is exactly one alert and no re-encodes.
- The tests check behaviour rather than mocks. The held-horizon and high-water tests also assert the record level (WARNING), not just the absence of "ALERT".

### Checks run (scratch `git archive a3daa36`; PYTHONPATH shadowing proven by a sentinel attribute; per-mutant PYTHONPYCACHEPREFIX; expected red named before each run)
- M1: dropped `not self.halted` from the fill condition. Expected red: test_frame_count_drift_halts_filling_but_keeps_publishing. CAUGHT (3 alerts vs 1).
- M2: drift arm leaves `filling` set. Expected red: the same test. CAUGHT (line 89).
- M3: high-water routed to an alert. Expected red: test_publish_all_warns_on_high_water_without_alerting. The first version was malformed (died on a TypeError, so not scored). The re-run was CAUGHT on the intended assertion.
- M4: HELD_MARKER broken. Expected red: test_publish_all_warns_on_a_held_horizon_without_alerting. CAUGHT.
- M5: prune report dropped. Expected red: test_publish_all_alerts_put_budget_from_prune. CAUGHT.
- M7: sleep removed. Expected red: test_run_with_max_ticks_sleeps_between_ticks. CAUGHT.
- M6: publish_all break reduced to `not r.uploaded`. Predicted to survive, and it SURVIVED. It is near-equivalent: publish_batch sets `report.uploaded` only after a successful horizon PUT, so uploaded+error only happens for "site: …" errors. Benign.
- Probe of `status_lines` with a populated state: it rendered the plan, on-air slug, published range and lead correctly. That path is untested in the suite (Minor 3).
- Probe of PublishLocked during a runner tick: it produces `ERROR publish step failed` with a traceback plus `ALERT publish: PublishLocked: …` (Minor 2).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. service.py 251, 271-276: held-horizon detection matches the string prefix "horizon held" on the `"; "`-split `PublishReport.error`.
   - Adequate for phase 1. It fails in the safe direction: if publish.py rewords the text, a held horizon becomes an alert, not silence. A real error is never swallowed, because non-matching parts are re-joined and alerted.
   - Still recommended: add a structured field (e.g. `PublishReport.held: bool`, or `stopped="horizon-held"`) when publish.py is next touched.
   - Related gap: a held horizon that never clears is WARNING-only, and each tick re-PUTs the same partial batch. The case is local segments missing in (last, high_water] while `halted` blocks the re-render. It surfaces only when the PUT budget trips, which is a bounded cost. Consider escalating to an alert after N consecutive held ticks (phase 2 dedupe).
   - The `and stopped != "put-budget"` at 275 can never be true, because put-budget returns at 261. Remove it.
2. service.py 314-316: PublishLocked inside the runner, caused by an operator's manual `publish` / `fallback render` overlapping a tick, raises a full ERROR traceback and an alert. The constraints describe that case as "the next tick simply retries". Once phase 2 wires email/ntfy, every overlap pages the operator. Suggest catching PublishLocked in `_step` and logging at INFO/WARNING.
3. No test covers `status_lines` with a populated state (plan rows, on-air, published lead). The probe shows it works today, but formatting regressions there would go unseen. Add one assertion on "published  segments" and "on air".
4. cli.py 101-108: `transmitter publish` exits 0 even when the batch hit put-budget, guard or an error. The problem is only visible as an ERROR log line. Consider a non-zero exit when any report has `stopped`/`error`, for scripted use.
5. test_cli.py 396-397: mid-file import block (E402), carried over from the brief's "append". test_service.py 612-613: a single blank line before the decorator. Style only; the mid-file imports are plan-mandated.
6. service.py 234: `row_analysis` uses `time.time()` rather than the tick clock, and on a cache miss it runs `engine.analyze` (ffmpeg) inside publish_batch's flock. It is only reached on a cache miss and is acceptable, but note it for the whole-branch review: a slow analyze extends the lock hold, and a manual publish during that window gets PublishLocked.

### Assessment

**Task quality:** Approved

**Reasoning:** The loop's cadence, its bounds and the drift latch are correct and pinned by tests that kill the obvious mutants. Every ruling a–e is implemented and tested. The string-based held detection fails loud rather than silent, so it is acceptable now, with a structured field recommended.
