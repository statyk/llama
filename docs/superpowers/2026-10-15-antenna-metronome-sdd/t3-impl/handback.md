# t3-impl handback: Task 3, metronome-core.ts

**Status:** DONE
**Commit:** fb30bd5 feat(antenna): metronome-core, the lease, its ordering and expiry, targets, caps and stalls

## What I implemented
- `antenna/src/metronome-core.ts` (new): exactly the brief's Step 4 code, extracted byte-for-byte from the brief's last ts block. That covers the constants, the Lease/StoredLease/MetronomeStatus/MetronomeClient/MetronomeState types, STORAGE_KEYS/StorageKey and all the listed functions.
- `antenna/src/grid.ts`: `export const GRID_D = 10.24` with the brief's doc comment, placed immediately before `export interface Grid {`.
- `antenna/src/clock.ts`: now imports `GRID_D` from `./grid`, and its own definition is replaced by `export { GRID_D };`. Its in-file uses (the d check at ~line 268) still resolve.
- `antenna/test/metronome-core.test.ts` (new): the brief's Step 1 test, verbatim.

## Tests
- RED: `cd antenna && npx vitest run test/metronome-core.test.ts` gave `Error: Cannot find module '../src/metronome-core'` with `Tests no tests`. That was expected because the module did not exist yet.
- GREEN (focused): same command, `Tests 26 passed (26)`.
- Full: `cd antenna && npm test && npm run typecheck` gave `Test Files 16 passed (16)`, `Tests 278 passed (278)`, and tsc silent. That matches the plan's 278 (252 + 26). There were no stderr or warning lines in the output (grep checked).
- Log: $D/t3-impl/t3-impl.log

## Self-review
- The code and tests are verbatim from the brief, with no deviations. The diff touches only the 4 files listed.
- Some behaviour is by design but worth the reviewer's attention:
  1. `stalledFor(true, null, null, now)` returns `now - 0`, an enormous stall. It can only happen if the engine reports live while `playSince` is unset. Task 4/5's engine must keep `playSince` set whenever the lease is live. This is not covered by a test here.
  2. `validateLease` keeps `raw.horizon` by reference, extra fields included. It does not check `published_at` or `container`. Only d, epoch_id, epoch (parseable), integer first/last and fallback_version are validated. The playlist code reads nothing else, as far as I saw.
  3. `isLive` passes `offair: false` to `isOffair`, so the offair.json flag reaches the DO only through `blocked`. That matches the lease design (`blocked = tripped OR offair`).
  4. `parseStoredLease` accepts a NaN `expiresAt` because it checks `typeof number`. `expired()` treats NaN as expired, and a test pins that.

## Concerns
None blocking.

## Fix round 1

**Commit:** bec70fb fix(antenna): a NaN clock trips the metronome caps; pin the removed-lease change strictly

### Changes
1. `antenna/test/metronome-core.test.ts`, the "writes only the keys that changed" test: the removed-lease assertion now uses `toStrictEqual({ lease: undefined })` instead of `toEqual`. `toEqual` ignores keys whose value is undefined, so `{}` used to pass as well.
2. `antenna/src/metronome-core.ts` `capAllows`: added `if (!Number.isFinite(nowMs)) return false;` as its first line. It is pinned by `expect(capAllows([], Number.NaN, 10)).toBe(false)`, added inside the existing "rolling windows" `it` block (the first one), so no new `it` was added.

### Evidence
- RED, with the new assertions in place but no guard: `cd antenna && npx vitest run test/metronome-core.test.ts` failed on `rolling windows > just over 60 s after the oldest timestamp is allowed, just under is not` with `AssertionError: expected true to be false`, giving `Tests 1 failed | 25 passed (26)`. That is the NaN cap opening. The `toStrictEqual` assertion passed against the current code, which is correct because the code does emit `lease: undefined`.
- GREEN: the same focused command gives `Tests 26 passed (26)`.
- Full run: `cd antenna && npm test && npm run typecheck` gives `Test Files 16 passed (16)`, `Tests 278 passed (278)`, and tsc silent.
