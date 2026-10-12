# task16-fix1 handback — Status: DONE

Commit `8339d2e` (on 294be7a). Files: antenna/src/clock.ts, antenna/src/index.ts, antenna/test/clock.test.ts.
Gates: `npm test` 29/29 (was 24; +5), `npm run typecheck` clean. No wrangler commands run.

IMPORTANT (spend):
- New `MAX_PUTS = 10`; `putCap` = `Math.min(MAX_PUTS, ceil(loopMs/dMs)+2)`.
- New `GRID_D = 10.24`: if `horizon.d !== 10.24`, runClock writes nothing. The check runs before gridOf and the loop. It emits one `console.error` with `{event:"horizon-refused", reason, d, epoch_id, scheduled}` and sets `result.refused`.
- New `MAX_LOOP_MS = 75_000`: runClock clamps loopMs, and logs one `{event:"loop-clamped", configuredMs, usedMs}` per invocation when it clamps. Done in runClock, not configFromEnv, so a config passed directly is clamped too.
- Tests:
  - `putCap` stays <= 10 across (loopMs, dMs) = (75k,10), (900k,10240), (75k,1), (10M,1000). This is the absolute check; it does not use the formula.
  - d in {0.01, 1, 10.25, "10.24"}: 0 PUTs, fake clock never advances, exactly 1 horizon-refused line naming d.
  - `LOOP_SECONDS=900` via configFromEnv: 8 PUTs (<= 10), ends by scheduledTime+75 s, 1 loop-clamped line.

MINOR 1: configFromEnv clamps liveMaxAge to >= 1, and runClock clamps again. Tested: env "0" gives 1, and a direct config of 0 writes `public, max-age=1`.
MINOR 3: the scheduled handler wraps runClock in try/catch/finally and always emits the `clock` line. On a throw the line includes `error`, and the error is rethrown so the invocation still fails. Tested with a horizon whose epoch is "nonsense": the handler rejects and exactly one clock line with `error` and `lagMs` is logged.

Mutations (scratch git-archive copies, predictions logged first):
- (a) MAX_PUTS dropped from the min. Predicted red: "caps PUTs at 10 absolutely" only. Result: exactly that test (7502 vs <=10); 28 passed.
- (b) d refusal disabled. Predicted red: the d-refusal test only. Result: exactly that test (10 PUTs vs 0); 28 passed. The 10 shows MAX_PUTS still bounding the bad-d case.

Concerns: none new. The loop-clamped error repeats every minute while LOOP_SECONDS is misconfigured. That is intended (loud), and it is one line per invocation.
