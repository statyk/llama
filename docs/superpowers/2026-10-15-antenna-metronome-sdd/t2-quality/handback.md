**Task quality:** Approved. No Critical or Important findings. Three Minor notes follow, two of which are forward-looking couplings for later tasks.

### Strengths
- Fail-closed holds at every layer of the new meters.
  - Parse: `count()` rejects NaN, negatives, non-numbers and missing values. `rows()` rejects a missing or truncated dataset, at `antenna/src/meter.ts:290-300`, and `doCounts` reuses both (`meter.ts:311-317`).
  - Pricing: a NaN or undefined value that does get through still propagates to a NaN total, which trips. This is pinned at `antenna/test/pricing.test.ts:888-895`.
- Empty-is-not-zero:
  - The check is inside the existing `try` (`antenna/src/guard.ts:151`), so a throw is an ordinary failed reading. A test pins that through `guardStep` with the switch on and with it off (`antenna/test/guard.test.ts:528-536`).
  - It tests one field from each dataset: `doRequests` from invocations and `doRowsWritten` from periodic (`meter.ts:357-362`). A silent drop-out in either dataset is caught.
- `stored()` now builds its map over `METERS` (`antenna/src/latch.ts:204-206`). A future meter therefore can't be dropped from guard.json by a hand-written literal. The fractional rounding is pinned by `period_to_date.doDurationGbS === 5.5` (`pricing.test.ts:879`).
- `pricing.test.ts:762-773` is a structural guard. Every meter must have a positive, finite price, and one million units past its allowance must cost money. "Free by omission" can't come back.
- Separation is clean:
  - The policy switch is parsed once, in `guardConfigFromEnv` (`guard.ts:129`).
  - The dataset knowledge stays in `meter.ts`.
  - `ClockEnv.METRONOME` is declared once (`antenna/src/clock.ts:36-37`).
  - The `clock.ts` <-> `guard.ts` cycle is `import type` on both sides (`guard.ts:16`, `clock.ts:4`), so it is erased at runtime.
- Mutants I reasoned through. Each is caught by a named test:
  - `||`->`&&` in `assertMetronomeMetered`: caught by `meter.test.ts:704`, since `[0,1,5]` no longer throws.
  - Checking `periodToDate` instead of `recent`: caught by `meter.test.ts:703`.
  - Dropping `if (cfg.metronomeOn)`: caught by `guard.test.ts:535`, the off case.
  - `METRONOME?.trim()==="on"`: caught by `guard.test.ts:540`, the `"on "` case.
  - Swapping duration and rowsWritten in `doCounts`: caught by `meter.test.ts:612-615`, the `toEqual`.
  - Wiring `doRecent` to `doToDate`: caught by the same `toEqual`.
  - Wrong DO rate key in `projected`: caught by `pricing.test.ts:821-823`.
  - Removing `doDurationGbS` from the fractional set: caught by `pricing.test.ts:879`.
  - Wrong unit price: caught by `pricing.test.ts:757-759`.
  - One mutant is not caught, and it is harmless: adding `doRowsWritten` to the fractional set. Integer inputs round the same either way.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **A later task must preserve an assumption the guard now relies on.** It is stated at `antenna/src/meter.ts:350-356` ("every renew writes at least one row (`stalls`)").
   - **The assumption:** while `METRONOME` is "on", the guard can only get a successful reading if the DO writes at least one storage row on every `renew()`, in every lease state: blocked, `hold`, and `renew(null)` with `stalls` already 0.
   - **Why it matters:** clearing a spend trip, and a blind trip, needs a successful reading (`latch.ts`, the header rules). Suppose a later DO implementation skips an unchanged `stalls` put while the station is held or blocked, so no alarms are writing. Then every reading after 3 h fails, and the trip can never clear by a budget raise or a new period. The station stays dark until an operator flips `METRONOME` off.
   - **What I checked:** spec renew steps 2-4 (spec lines 238-250). They update `stalls` and apply the lease on every call, so the assumption holds as designed. Nothing in this task can pin it.
   - **Fix:** the DO task should add a test that `renew()` advances storage on every call in each lease state, including `stalls` 0->0. Alternatively, the comment should name the DO test that pins it.
2. **A long DO outage while `METRONOME="on"` eventually takes the station off-air.**
   - **Mechanism:** an outage where renews never reach the object empties the recent window after about 3 h (`RECENT_MS`). From then on every reading fails (`meter.ts:357-362`), and the blind rule trips about 6 h later. That is roughly 9 h into an outage, even though cron's fallback loop is playing and spend is otherwise fully metered.
   - **Assessment:** this is fail-closed and the spec mandates it (spec lines 363-367), so it is not a code defect. `metronome-down` fires much earlier.
   - **Fix:** the runbook (Task 9 or docs) should say that a `metronome-down` lasting hours means flipping `METRONOME` off, or the guard will blind-trip.
3. **A small per-call allocation:** `antenna/src/latch.ts:204` builds the `fractional` Set on every `stored()` call, and the `usage` closure runs twice per call.
   - **Impact:** trivial cost, but the Set is a constant.
   - **Fix:** hoist it to a module-level `const FRACTIONAL_METERS: ReadonlySet<Meter>`. This is optional, because the brief specifies the code verbatim.

### Checks I ran
- **Downstream readers of the stored meters.** Risk: an older 4-key guard.json is read by code that indexes the new keys. I grepped `src/` for `period_to_date`, `.projected` and `METERS`. Nothing reads the stored meters, so older docs are harmless and the next evaluation rewrites them with 7 keys. transmitter reads only top-level `evaluation` fields, per the brief.
- **Import cycle.** Risk: a runtime cycle between `clock.ts` and `guard.ts`. Both imports are `import type`, so there is none.
- **Spec vs. empty-is-not-zero.** Risk: the check could deadlock while the station is blocked or held. I read spec lines 165-170, 238-268 and 350-372, which gave Minor 1 and Minor 2.
- **Tests.** I did not re-run the suite. The implementer reports 252 passed and tsc silent, and nothing in the code raised a doubt that a focused run would answer.
