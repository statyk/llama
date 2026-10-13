VERDICT: ALL ADDRESSED

### Finding verdicts
1. **I1 (no test reaches the network): ADDRESSED.**
   - Both scheduled-handler tests pass `noSecrets()`, which forces CF_ACCOUNT_ID, CF_ZONE_ID, CF_ANALYTICS_TOKEN and CF_WAF_TOKEN to `undefined`. They also spy `globalThis.fetch` with `mockRejectedValue` and assert `not.toHaveBeenCalled()` (antenna/test/clock.test.ts, "scheduled handler" describe, `noSecrets`/`noNetwork` plus the two `expect(net)` lines).
   - The spy is effective because index.ts's `fetchFn` resolves the global `fetch` at call time. guard.ts calls the network only through `deps.fetch` (guard.ts:274, 289).
   - The implementer's mutants A, B1 and B2 cover all three properties: the spy catches a real call, the override beats a `.dev.vars`, and the control reproduces the original failure.
   - `vi.restoreAllMocks` in `afterEach` restores the spy.
2. **I2 (flush contract): ADDRESSED.**
   - The sink signature is `alerts(conditions, nowMs, batch: AlertBatch)` (clock.ts:50-69).
   - `complete` starts false and is set true only immediately before the normal path's `return` (clock.ts ~l.323). Every early return and every throw therefore flushes incomplete.
   - The AlertBatch doc states the sink obligation: no "resolved" and no cooldown for a key absent from an incomplete batch; the conditions present may still be sent and repeated.
   - `logAlerts` logs the flag.
   - Each path is tested: normal (complete), unknown, crash, missing, corrupt, refused, readInputs throw, gridOf throw (all incomplete). Implementer mutants C and D bound it in both directions.
   - Note for the T9 ruling, not a defect here: horizon-missing and horizon-refused can persist for hours. During that time every batch is incomplete, so no resolution is announced, including the guard's (for example tripped-spend clearing after `--raise-to`), until the horizon recovers. The ledger's "cost if wrong: a genuine resolution is announced one invocation later" understates this for persistent early returns. If that matters, T9 could treat the guard's own keys as complete whenever the guard returned a known outcome (scope by key family). The ruling's coarse flag is safe; it only delays all-clears.
3. **M1 (flush-on-throw pinned): ADDRESSED.**
   - The test "a throw reading the inputs still flushes …" uses `failGets` on state/horizon.json. It asserts that `["tripped-spend","clock-inputs"]` reaches the sink with complete:false, that runClock rejects, and that there are 0 playlist PUTs.
   - Implementer mutant E (the reviewer's original surviving mutant) now goes red in 3 tests.
4. **M2 (lead-low while off-air, not tripped): ADDRESSED.**
   - The lead-floor test adds `guardSays(true, false)` and asserts `blocked === true` and that `lead-low` is raised.
   - My scratch mutant `!outcome.blocked` failed exactly that test, as predicted.
5. **M3 (horizon-missing message): ADDRESSED.**
   - The message is now "absent, or unreadable (not JSON) … or the object is corrupt" (clock.ts horizon-null branch).
   - It is pinned through the default-sink test (`/absent, or unreadable/`), and a corrupt-horizon case was added to the early-return test.
6. **M4 (`clock-inputs`): ADDRESSED.**
   - `failedInputs` pushes an urgent, resolvable `clock-inputs` before the rethrow for both `readInputs` and `gridOf` (clock.ts, step 3). It is flushed incomplete in `finally`.
   - Both cases are tested.
   - My scratch mutant (`gridOf` catch rethrows without the condition) failed the grid-derivation test and the handler throw test, as predicted.
7. **M5 (clock line keeps guardMs/blocked on a throw): ADDRESSED; the design is sound.**
   - `ClockError(cause, partial)` keeps `e.message` identical, so `/epoch/` still matches and observability still records a failed invocation. index.ts adds one `instanceof` line.
   - `partial` is the live `result` reference, not a snapshot. That is correct here: runClock's `finally` (flush, which fills `result.alerts`) completes before the rejection reaches index.ts's catch, which is why the handler test sees `alerts` containing `clock-inputs`.
   - Every throw out of the outer try is wrapped exactly once. The guard and reconcileIndex throws are caught inside it, so no double wrap is possible.
   - My scratch mutant (drop `result = e.partial`) failed the handler throw test, as predicted.
   - Minor nit, non-blocking: `super(message)` is called without `{ cause }`, and the ClockError's own stack starts at runClock's catch. A Workers log of the uncaught exception therefore shows the wrapper's stack, not the original throw site. The original is still on `.cause`. Passing `super(msg, { cause })` would let runtimes that print the cause chain show it.

**Implementer's flagged concern (a failed playlist `bucket.put` raises no alert key): a real gap, out of scope for this round, not blocking T8.**
- It was not among the findings and the fix diff did not introduce it. Before the fix, the same failure was equally key-less.
- It has no spend consequence: a failed PUT spends nothing more, and the guard has already decided and reconciled.
- The batch is correctly complete:false, and the clock line carries the error plus the partial result, so it is visible.
- hugo's dead-clock monitor (R4) backstops a stale live.m3u8.
- The ledger's M4 ruling says `clock-inputs` "closes the one cloud-side failure without a condition key", which is now known to be inaccurate. Recommendation for the orchestrator: a one-line ruling either to add a `playlist-write` key (urgent, resolvable), or to generalize the outer catch to push a catch-all `clock-failed` key when no more specific key was pushed. Fold it into T9 or a later minor pass, and have T9/T17 list it alongside `clock-inputs`.

### New breakage in the fix diff
None.
- The phase-1 spend bounds are untouched in code: the `write`/loop/`putCap`/`MAX_PUTS`/clamp/`liveMaxAge` lines are outside the diff.
- They are untouched in tests: the only diff line in that region is the import line gaining `type AlertBatch`.
- The `MAX_PUTS = 10`, `d ≠ 10.24` refusal, 75 s clamp and `LIVE_MAX_AGE ≥ 1` tests are all still present and green.
- Minor (cosmetic): the ClockError stack/cause nit under item 7.

### Out-of-scope observations
- The playlist-PUT-failure key gap (above).
- Persistent horizon-missing/refused suppresses every resolution, including the guard's (above). Carry this into the T9 dispatch with the ruling.

### Checks run
- Read the rereview instructions, the T8 brief, constraints, the implementer handback (including Fix round 1), the fix diff 4d1858b..12f796a, both original verdicts, and the three "Ruling: T8" ledger lines. Read HEAD clock.ts runClock in full (l.188-330), plus guard.ts's fetch call sites and conditions.ts's types.
- Scratch copy: `git archive HEAD antenna | tar -x` under the session scratchpad, with node_modules symlinked and vitest run from the scratch dir.
  - Baseline: `npx vitest run test/clock.test.ts` gave 30 passed.
  - `npx tsc --noEmit` exited 0.
- Mutants, each with the expected red named first:
  - (M5) drop `result = e.partial` in index.ts. Predicted: handler throw test red. Result: exactly that test failed (1 failed, 29 passed).
  - (M2) `!outcome.tripped` changed to `!outcome.blocked`. Predicted: lead-floor test red. Result: exactly that test failed.
  - (M4) the gridOf catch rethrows without `clock-inputs`. Predicted: the grid-derivation test and the handler throw test red. Result: exactly those 2 failed.
  - Reset: 30 passed.
- The implementer's mutants A, B1, B2, C, D and E were checked against the diff for plausibility and not re-run.
- Live worktree: `git status` clean, no antenna/.dev.vars or .env, and nothing written outside `$D/t8-rerev1/`. A stray `/tmp/idx.bak` copy I made of index.ts during mutant setup was deleted.
