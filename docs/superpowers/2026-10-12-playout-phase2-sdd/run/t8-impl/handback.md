# Task 8 handback (t8-impl): clock integration and Worker wiring

Status: DONE
Commit: 4d1858b feat(antenna): the clock runs the cost guard first; blocked drives index.html and the off-air playlist
Tests: `cd antenna && npm test && npx tsc --noEmit` -> 12 files, 158 passed (was 150); tsc clean.

## What was implemented
The brief's code, verbatim, for:
- `antenna/src/clock.ts` (replaced): `guard` is a required `ClockDeps` member, run first; `alerts?` defaults to
  `logAlerts`. A null outcome or a throwing guard (`guard-crashed`, urgent) writes nothing (no index, no playlist).
  `index.html` follows `blocked` through `reconcileIndex`; a throw there is caught -> `index: "failed"` plus
  `index-write`, and the playlist still runs. `readInputs(bucket, blocked)` no longer reads offair.json. New
  conditions: `horizon-missing`, `horizon-refused`, `lead-low` (suppressed while tripped), `offair-without-fallback`.
  Alerts are flushed once in `finally` (after the last playlist write or an early return). `ClockResult` gains
  `blocked`, `guardMs`, `index`, `alerts`. `ClockConfig.leadFloorMs` (var `LEAD_FLOOR_HOURS`, default 16).
  Re-export of `BucketLike`, `r2Bucket`, `StoredObject` from `./bucket` kept.
- `antenna/src/env.ts` (new): `AntennaEnv extends ClockEnv, GuardEnv { BUCKET: R2Bucket }`.
- `antenna/src/index.ts` (replaced): wires the real `guardStep` with `guardConfigFromEnv(env)`; the per-invocation
  clock line now carries `guardMs` (spread from the result); `satisfies ExportedHandler<AntennaEnv>`.
- `antenna/wrangler.jsonc` (replaced): adds `LEAD_FLOOR_HOURS` and the guard vars (`MONTHLY_BUDGET_USD` 15,
  `BILLING_ANNIVERSARY_DAY` 11, `GUARD_EVAL_SECONDS` 900, `BLIND_AFTER_SECONDS` 21600, `KILL_SWITCH_DESCRIPTION`).
  No account_id, no address, no secret values.
- `antenna/test/clock.test.ts` (replaced with the brief's file, plus one test, below).

The brief's code needed no adaptation against the current guard.ts (Task 6 + fixes) or indexpage.ts (Task 7):
`GuardOutcome`'s shape matches, `reconcileIndex` returns "written" | "unchanged" and lets HEAD/PUT errors propagate,
which the brief's try/catch already handles.

## Deviations
1. **`antenna/worker-configuration.d.ts` regenerated** (`npx wrangler types`, local only, no account access) and
   committed. Not in the brief's file list; the tracked generated file would otherwise be stale against the new
   wrangler vars. Diff is the six new vars in `__BaseEnv_Env` / `ProcessEnv` plus the hash line (8+/2-).
   I first generated to the scratchpad and diffed to confirm nothing else (runtime types) would change.
2. **One extra test** in clock.test.ts: "a failed index.html HEAD while blocked still writes the off-air playlist,
   and alerts" (uses `MemoryBucket.failGets` on `index.html`, which fails the HEAD; guard blocked+tripped). The
   brief only covered a failed PUT on the player page; the manager's context pointed at the HEAD path.

## TDD evidence
RED: `cd antenna && npx vitest run test/clock.test.ts` with the new test file against the old clock:
`Tests 15 failed | 8 passed (23)` (e.g. configFromEnv lacks leadFloorMs; scheduled handler: state/guard.json is
null because no guard ran).
GREEN: same command after the implementation: `Tests 23 passed (23)`; with the extra test `24 passed (24)`.
Full: `npm test && npx tsc --noEmit` -> `Test Files 12 passed (12)`, `Tests 158 passed (158)`, tsc clean.

## Mutation check (scratch copy under the session scratchpad, node_modules symlinked; each with a predicted red test)
- M1 index catch removed (rethrow) -> predicted+caught: both "failed index.html write/HEAD" tests.
- M2 null outcome proceeds (`blocked === null && false`) -> predicted+caught: "writes nothing at all when the guard
  cannot tell" and "a guard that throws is treated as unknown".
- M3 flush right after the guard -> predicted "passes the guard's conditions ... after the last playlist write":
  caught (plus 6 others whose late conditions were lost).
- M4 lead-low not suppressed while tripped -> caught by the lead-floor test only.
- M5 playlist ignores blocked (`readInputs(bucket, false)`) -> caught by 4 tests incl. "blocked: the off-air playlist".
- M6 index ignores blocked -> caught by "index.html follows the blocked state".
The worktree source was never mutated (the scratch copy's failures show it ran the scratch source).

## Self-review
- Guard first: the guard call is the first await in runClock; the only thing before it is the loop-clamp log line
  (a console.error, no I/O). Test "runs the guard before reading or writing anything" pins this.
- Spend bounds unchanged: MAX_PUTS 10, putCap, GRID_D refusal (now also an alert), 75 s clamp, max-age >= 1;
  all phase-1 tests kept (adapted to pass `guard: onAir`). `result.puts` counts playlist PUTs only; the index PUT
  is at most one per invocation and only when the page's sha256 differs.
- `guardMs` is recorded even for an unknown/throwing guard.

## Concerns (minor, for the reviewer)
- A throw from `readInputs` (e.g. an R2 get failure on `state/horizon.json`) after the guard still propagates out
  of runClock as before: index.html may already have been reconciled, no playlist is written, the guard's
  conditions are flushed, and the failure surfaces only as the clock line's `error` / a failed invocation, not as
  an alert condition. That matches the brief (and phase 1); flagging in case an alert key is wanted.
- Until Task 9 wires alerts.ts, index.ts uses the default `logAlerts` sink (structured console.error lines only).

---

# Fix round 1 (reviews: t8-rev-qual NEEDS FIXES, t8-rev-spec APPROVED; rulings "Ruling: T8" in orch/ledger.md)

Status: DONE
Commit: 12f796a fix(antenna): clock review round 1 -- no-network handler tests, scoped alert batches, clock-inputs
Tests: `cd antenna && npm test && npx tsc --noEmit` -> 12 files, 164 passed (was 158); tsc clean.
Focused: `npx vitest run test/clock.test.ts` -> 30 passed.

## What changed
- **I1 (no network):** both scheduled-handler tests now pass `noSecrets()`, which is `{ ...env, LOOP_SECONDS: "0" }` with
  CF_ACCOUNT_ID/CF_ZONE_ID/CF_ANALYTICS_TOKEN/CF_WAF_TOKEN forced to `undefined`. They also spy on
  `globalThis.fetch` (`mockRejectedValue`) and assert it was never called. `afterEach` restores the spy through
  `vi.restoreAllMocks`. No .dev.vars/.env was created in the live worktree.
- **I2 (flush contract):** `ClockDeps.alerts(conditions, nowMs, batch: AlertBatch)`, where `AlertBatch = { complete: boolean }`.
  - `complete` is set true only immediately before the normal path's final `return`. It is false on an unknown
    outcome, a guard crash, the horizon-missing and horizon-refused returns, and any throw.
  - The `AlertBatch` doc comment states that a sink MUST NOT resolve, or start a cooldown for, a key absent from an
    incomplete batch, but may send and repeat the conditions present.
  - `logAlerts` puts `complete` on every alert line.
- **M1:** flush-on-throw is pinned. `failGets` on state/horizon.json makes runClock reject. The sink still gets
  `["tripped-spend", "clock-inputs"]` with complete:false, and there are 0 playlist PUTs.
- **M2:** the lead-floor test adds `guardSays(true, false)` (off-air, not tripped). It asserts blocked and that
  `lead-low` is still raised.
- **M3:** the horizon-missing message now reads "state/horizon.json is absent, or unreadable (not JSON): live.m3u8 was
  not written. Either nothing is on air yet ... or the object is corrupt." Pinned through the default-sink test, and
  a corrupt-horizon case was added to the early-return test.
- **M4:** a new urgent, resolvable condition `clock-inputs` is raised when `readInputs` or `gridOf` throws. It is
  pushed before the rethrow and flushed with complete:false. Both cases are tested (get failure; `epoch: "nonsense"`).
- **M5:** runClock wraps any throw from its body in `ClockError` (exported), which has the original message, `cause`,
  and `partial: ClockResult`. In index.ts's catch, `result = e.partial` when the error is a ClockError, so the clock
  line keeps `guardMs`, `blocked`, `puts`, `index` and `alerts` on a failed invocation. The handler throw test asserts
  `guardMs` is a number, `blocked === false` and `alerts` contains `clock-inputs`. The rejection message is unchanged
  (`/epoch/` still matches).
- All phase-1 spend-bound tests are untouched.

## Deviations (each authorized by a T8 ruling)
- The test file deviates from the brief's verbatim file: secrets are forced unset, fetch is spied, and new tests were
  added. clock.ts changes the `alerts` signature and adds `AlertBatch`, `ClockError` and `clock-inputs`.
- Design choice for M5: I wrapped the error in a `ClockError` instead of returning a result alongside, so runClock
  still rejects (observability still sees a failed invocation) and index.ts needs only one `instanceof` check.
  `e.message` is the original message.

## Mutants (scratch: `git archive HEAD antenna | tar -x`, node_modules symlinked, vitest from the scratch dir; expected red named first)
- **A (I1, fetch spy):** removed guard.ts's `wafProblems` short-circuit, so the WAF fetch runs with empty secrets.
  Predicted both handler tests red. Result: 2 failed, both handler tests ("expected fetch to not be called").
- **B1 (I1, env override):** scratch `.dev.vars` with `CF_ACCOUNT_ID=dummy-not-real` only (cannot authenticate),
  run against the fixed tests. Predicted GREEN. Result: 30 passed. The forced-undefined secrets hold against .dev.vars.
- **B2 (control):** the same .dev.vars, with the PRE-FIX test file from HEAD~1. Predicted "runs the guard then one
  clock invocation" red. Result: 1 failed with `expected 'secret CF_ANALYTICS_TOKEN is not set' to match /CF_ACCOUNT_ID/`,
  which reproduces the reviewer's finding.
- **C (I2):** `let complete = true` initially. Predicted the 5 incomplete-path tests red. Result: exactly those 5 failed.
- **D (I2):** removed `complete = true` at the end of the normal path. Predicted "is complete only at the end of the
  normal path" red. Result: exactly that test failed.
- **E (M1):** `catch (e) { flushed = true; throw ... }`. Predicted the readInputs-throw test, the gridOf-throw test and
  the handler throw test red. Result: exactly those 3 failed.
- Reset copy: 30 passed. The live worktree was untouched (`git status` clean, no .dev.vars/.env in antenna/).

## Notes for Task 9 / Task 17
- `planAlerts` must honour `batch.complete === false` (no resolution pass), per the ruling. The sink signature is
  `(conditions, nowMs, { complete })`.
- `clock-inputs` is a new key to list alongside R13's.
- Not raised as a condition still: a throw from the playlist `bucket.put` itself. The batch is complete:false and the
  clock line has the error, but there is no alert key. This was out of scope for the ruling; flagging it only.
