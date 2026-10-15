# t2-impl handback: Task 2, Cost guard: the Durable Object meters

**Status:** DONE
**Commit:** 7c6b69b feat(antenna): the cost guard prices Durable Object requests, duration and rows written (on top of 0d4d348)

## What I implemented
I applied every brief edit verbatim. A script pulled the brief's fenced code blocks out by index and replaced each old block only where it matched exactly once, so nothing was retyped by hand.
- `src/pricing.ts`: new doc comment. `Meter`/`METERS` now have 7 entries (doRequests, doDurationGbS, doRowsWritten). `PRICES.meters` has the three DO entries: 1M @ $0.15/M, 400k GB-s @ $12.50/M, 50M @ $1.00/M. `OpCounts` gains the three fields. The `periodToDate`/`projected` literals in `evaluateSpend` now carry all 7 meters.
- `src/meter.ts`: new doc comments. `USAGE_QUERY` gains `doToDate`, `doRecent`, `doPeriodicToDate` and `doPeriodicRecent`. `Rows.sum` is now `Record<string, unknown>`. Added `sumField` and `doCounts`, and `sumRequests` now delegates to `sumField`. `parseUsage` spreads the DO counts into both windows. Added the exported `assertMetronomeMetered(r: Reading)`, which throws `analytics: the metronome is on but ...`.
- `src/latch.ts`: `stored()` now builds the usage map over `METERS`. Counts are rounded to integers, and r2StorageGbMonth/doDurationGbS are rounded to 4 places.
- `src/clock.ts`: `ClockEnv.METRONOME?: string`. This is the only place it is declared.
- `src/guard.ts`: type import of `ClockEnv`. `guardConfigFromEnv(env: GuardEnv & Pick<ClockEnv, "METRONOME">)` sets `GuardConfig.metronomeOn = env.METRONOME === "on"`. In `guardStep`, `if (cfg.metronomeOn) assertMetronomeMetered(reading);` runs inside the existing try, so a throw counts as a failed reading.
- Tests: `test/support.ts` (`DoUsage`, the new `usageResponse`), `test/latch.test.ts` and `test/conditions.test.ts` (usage literal), `test/pricing.test.ts` (rewritten), `test/meter.test.ts` (import, two expectations, three new its, the assertMetronomeMetered describe), `test/guard.test.ts` (the metronome-on describe).

I did not touch the latch rules, the thresholds or the blind rule.

## Tests and results
- `cd antenna && npm test && npm run typecheck`: `Test Files  15 passed (15)`, `Tests  252 passed (252)`, and `tsc --noEmit` printed nothing. This is the 252 the plan expects, up from 240. Apart from vitest's standard "persist transforms" performance hint, the output has no warnings or stderr.

## TDD evidence
- RED: `cd antenna && npx vitest run test/pricing.test.ts test/meter.test.ts test/guard.test.ts` gave `Test Files 3 failed (3)`, `Tests 14 failed | 56 passed (70)`. These are the failures the brief predicts:
  - `PRICES.meters.doRequests` undefined ("expected undefined to deeply equal { included: 1000000 ...")
  - `TypeError: ... assertMetronomeMetered is not a function`
  - `USAGE_QUERY` "expected 'query StationUsage(...' to contain 'doToDate: durableObjectsInvocationsAd...'"
  - `metronomeOn` undefined ("expected undefined to be true")
  - plus METERS length 4 vs 7, guard.json having 4 keys, and the NaN DO reading not tripping.
  All of them are expected, because the source had not been changed yet.
- GREEN: `npm test && npm run typecheck` as above. The full output is in `t2-impl.log`.

## Files changed
antenna/src/{pricing,meter,latch,guard,clock}.ts
antenna/test/{support.ts,pricing.test.ts,meter.test.ts,guard.test.ts,latch.test.ts,conditions.test.ts}

## Self-review
- Wiring: `src/index.ts:22` calls `guardConfigFromEnv(env)` with the full `AntennaEnv`, which extends `ClockEnv`, so METRONOME reaches the guard. `wrangler.jsonc` does not declare METRONOME yet, so the check is off in production until a later task sets it.
- Backward compatibility: `parseGuardDoc` does not check which keys `period_to_date`/`projected` hold, so an existing 4-key guard.json still parses and the next evaluation rewrites it with 7 keys.
- The empty-is-not-zero check covers only the recent window, as the brief specifies. An empty period-to-date DO range while the recent window is non-empty would still read as zero. That is possible only in principle, because recent lies inside period-to-date.
- Names and patterns follow the existing code. `sumRequests` is kept as a thin wrapper, as the brief's code has it. Nothing extra was added.

## Concerns
None.
