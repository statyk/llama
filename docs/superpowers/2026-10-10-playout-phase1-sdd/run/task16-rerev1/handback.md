# task16-rerev1: scoped re-review of fix 294be7a..8339d2e

- **Important (spend bounds): ADDRESSED.**
  - `MAX_PUTS = 10` ceiling: clock.ts:61 and putCap :126.
  - d refusal before `gridOf` and the loop, with one `horizon-refused` console.error and `result.refused`: clock.ts:166-171.
  - loopMs clamped to 75 000 with one `loop-clamped` log, inside runClock so a directly passed config is covered too: clock.ts:152-160.
  - Tests at clock.test.ts:170-212.
- **Probe re-run** at 8339d2e (scratch git-archive copy, same probe file), PUTs per invocation:

| Input | Before (294be7a) | After (8339d2e) |
|---|---|---|
| d=0.01 | 2501 | 0 |
| d=1 | 76 | 0 |
| LOOP_SECONDS=900 | 89 | 8 |

  The 8 matches the 75 s default, and the run ends by deadline.
- **Float robustness of `horizon.d !== 10.24`: safe.**
  - transmitter writes `D_US / 1_000_000` with `D_US = 10_240_000` (integer). Python's division is correctly rounded, so it gives the same double as the literal 10.24. Checked: `json.dumps` → `10.24`, and `== 10.24` is True.
  - In node, `JSON.parse` of `10.24`, `10.240` and `1.024e1` each give `=== 10.24` true, as does `10240000/1000000`.
  - Only a different value, or a string `"10.24"`, is refused, and both are tested.
- **Minor 1 (LIVE_MAX_AGE >= 1): ADDRESSED.** Clamped in configFromEnv (clock.ts:45) and again in runClock (:155). Tested at clock.test.ts:214-221. The probe confirms env "0" gives 1.
- **Minor 3 (clock line always emitted): ADDRESSED.** The handler is wrapped in try/catch/finally (index.ts:7-25) and the error is rethrown. On a throw the log line carries `error`; on success it spreads `result`. Tested at clock.test.ts:245-256 (rejects, exactly one line with `error` and `lagMs`).
- **Minor 2: subsumed (ADDRESSED).** The absolute `putCap` test at clock.test.ts:171-176 asserts <= 10 independently of the formula.
- **New breakage in the fix diff:** none found.
  - The refusal returns before `gridOf`, so a bad `d` can no longer throw.
  - The on-air path at d=10.24 is unchanged: the original tests still pass per the report.
  - Note: a refused horizon also suppresses the off-air ENDLIST. That is consistent with "write nothing" and the event is logged, so it is not a defect.
- **Out of scope:** none.

Verdict: Approved
