### Finding Verdicts
- **Important 1: the "removed lease" assertion pinned nothing (`toEqual` ignores keys whose value is undefined)**: ADDRESSED. `antenna/test/metronome-core.test.ts:200` now reads `expect(stateChanges(before, { ...before, lease: null })).toStrictEqual({ lease: undefined })`. Vitest's `toStrictEqual` checks keys whose value is undefined, so `{}` no longer matches. The reviewer's mutant (`if (k === "lease" && next.lease === null) continue;`) would return `{}` and now fails here. The implementer did not show a RED run for this mutant. It said the assertion passes on current code, which is correct. The kill follows from the matcher's documented semantics, so I did not re-run it.
- **Important 2: a NaN `nowMs` opens the cap**: ADDRESSED. `antenna/src/metronome-core.ts:175` adds `if (!Number.isFinite(nowMs)) return false;` as the first line of `capAllows`. That trips on NaN, plus or minus Infinity, and a missing (undefined) value, which matches "NaN or missing values trip, never pass". It is pinned at `antenna/test/metronome-core.test.ts:146` by `expect(capAllows([], Number.NaN, 10)).toBe(false)`, inside the existing "rolling windows" `it` as the controller ruled, so the count stays 278. The pin is discriminating: with an empty history and no guard, `0 < 10` returns true. The implementer's report shows that RED (`expected true to be false`, 1 failed | 25 passed), then GREEN 26/26, then the full suite at 278 passed (16 files) with tsc silent.

### New Breakage in the Fix Diff
None. The guard only changes the result for a non-finite `nowMs`, where it can only turn an allow into a deny. Finite behaviour is the same, and the boundary assertions at lines 144-145 are unchanged and still pass.

### Out-of-Scope Observations
- `recordTime` (`metronome-core.ts:180`, not touched by the fix): a NaN `nowMs` there empties the window and stores `[NaN]`. That throws away the cap history, and the NaN entry is dropped from every later window. It is harmless only if callers always check `capAllows` before `recordTime` with the same clock value. Worth a glance when the Task 4 call sites land. Non-blocking.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
