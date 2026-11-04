### Spec Compliance

- ✅ Spec compliant for every listed requirement and ruling, checked against the diff:
  - Button and form toggle: probe.html (the two `<button>` lines), probe.js `$("wait")` and `$("waitform")` handlers. The form persists nothing.
  - Nothing is touched before 30 s stuck: probe.js:292. Nothing is touched while offline: `waitRestart` is reached only from the fetch fulfilment handler, probe.js:254-265.
  - Fetch: no-store, AbortController + setTimeout at 8 s, at most one at a time, cadence from the tick: probe.js:245, 302.
  - Any status counts, and status is logged; a rejection restarts nothing; net= is logged and never gated on: probe.js:254-268.
  - Two restarts per stall, a clear line once, no restart until advance: probe.js:297-301.
  - RECOVERED versus recovered alone, count reset: probe.js:283-291.
  - Same element, and restart lines carry form, attempt, stuck and vis=: probe.js:225-240.
  - Mutual exclusion both ways, logged; Stop and Pause turn both off; `wanted` gate: probe.js:274 and the button handlers.
  - Existing log formats unchanged: `begin` was split into `begin` + `playLogged` with the same strings.
  - Only probe.js and probe.html changed. No third-party request added.
- ❌ One global-constraint failure, not a brief rule: the evidence lines can claim a recovery the script did not make. See Important 1 and 2.
- ⚠️ Cannot verify from diff: everything iOS, as the implementer says. Not re-run: the harness results. They are claims; nothing in the code contradicts them.

### Strengths

- The position jump is handled properly. Test 2's 163.71 after 123 s gives a start of 40.96, exactly hold-back (163.84 - 122.88). The first post-restart tick only takes a reading, and the wall-clock bound at probe.js:280 refuses that jump. I walked 0→41, 163→0→41 and stuck-at-41: none gives a false RECOVERED, and restart 2 still fires because probe.js:292 runs from `max(movedAt, waitRestartAt)`.
- RECOVERED depends on position, not on `playing`, so a missing `playing` event cannot hide or fake a result.
- The re-check on response arrival (probe.js:260) closes the 8 s window in which playback could have resumed. A mutant was run against it.
- A real 8 s hang is bounded and logged; no restart path exists from a failed fetch.
- `teardown`, `src` and `play()` stay synchronous in one task, and the offline teardown that spoiled test 3 cannot happen from this path.
- Checked: no service worker in antenna/public or antenna/src (grep for `serviceWorker`, 0 hits). So an offline fetch cannot get a cached answer and license a restart.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **probe.js:284-285 with 147, 330, 344: an operator's own restart logs `wait: RECOVERED`.** This is worse than the implementer's Concern 1, which covers only `recovered alone`.
   - Cause: `waitLastRestart` is cleared only by `waitClearStall`. Neither `begin()` from the Start button nor the media-session `restart("media session play")` touches Wait's state.
   - Path: a locked restart fails. The operator unlocks, as the sheet says to, and presses Start, as he did in test 2 ("On unlock, Start worked"), or taps Play on the lock screen. The position advances and the log reads `wait: RECOVERED after restart 1 form=full`. The same happens after `no more restarts`.
   - Why it matters: operator-probe-test.md:47 says `wait: RECOVERED` means the restart worked, and "don't press anything until you unlock" permits pressing after unlock. The failed run is the one most likely to produce the false line, and D6 turns on it. The `button Start` line and `vis=visible` are nearby, but the greppable line states the opposite of what happened.
   - Second effect: `begin` leaves `movedAt` stale because `wanted` is already true (probe.js:148). If `ct` has not moved by the next tick, Wait is past 30 s at once, so a good fetch tears down the operator's Start while it loads. That spends an attempt, and the resulting RECOVERED is again credited to the script.
   - Fix: a manual begin during Wait (Start, media-session play) ends the stall with its own line. For example, call a `waitManual(label)` that logs `wait: manual restart <label>`, sets a flag, sets `waitRestartAt = now` and `waitCt = null`. The advance then logs `wait: recovered after manual restart`, never RECOVERED. Keep it out of the path `waitRestart` itself uses.

2. **probe.js:285 with operator-probe-test.md:47: RECOVERED does not say the restart that worked was made while locked.** A refused locked restart followed by an unlock produces the line with no key pressed.
   - Path: restart 1 fires hidden and fails. Test 3 shows the page then freezes within seconds. The operator unlocks and the page thaws. 30 s have passed, so the next tick fetches and restart 2 fires on a visible page. iOS allows it and RECOVERED is logged.
   - Variant: restart 1's pending play takes effect only at unlock. That also logs RECOVERED.
   - The lines are individually honest, since each carries vis=. But the RECOVERED line reports only the vis at the end, and the sheet tells the reader that RECOVERED means it worked, which answers D6 yes on a run that proves no.
   - Fix, code: save `document.visibilityState` at restart and put it in the line, e.g. `wait: RECOVERED after restart 2 form=full restart_vis=visible in=...`.
   - Fix, sheet (the controller's file, outside this task's diff): state that a run answers D6 only if the restart and RECOVERED lines both read vis=hidden.

#### Minor (Nice to Have)

1. probe.js:245, 302: the 8 s abort is the only way out of `waitFetching`. If the abort never settles the promise, every later fetch is skipped for the stall, and the only trace is a `start` line with no result. This is Concern 3; the brief's mechanism is implemented as ruled. The constraint names a hung fetch, and the tick can cover it in a few lines: if `waitFetching` and `now - waitFetchAt` is over twice the timeout, log `wait: fetch hung`, abort, and clear it.
2. probe.js:260: `audio.currentTime !== waitCt` is an exact float comparison across up to 8 s. Test 2 proves `ct` did not rise (stuck reached 341 s) but shows only 2 decimals of it and nothing about downward jitter. If iOS jitters it, every good fetch logs `no restart: position moved`, so the test visibly never restarts. Use `Math.abs(audio.currentTime - waitCt) >= WAIT_MIN_PLAYED_S`, the probe's own definition of movement at probe.js:280.
3. probe.js:69-76 and report Decision 3: "the tick lines' stuck= still reads the whole dropout" is untrue on iOS. After the reset of `movedCt`, the jump to about 41 sets `movedAt`, so `stuck=` (restart 2's line included) counts from the jump, and the comment at probe.js:69 goes stale. Clock times still give the true span, so nothing is misread.
4. Concern 2 (a paused element counts as stuck) stands as ruled. A restart line shows `paused=true`, so it is readable, and the sheet already says to repeat an interrupted run.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The gating is sound: no path touches the element offline or while advancing, and the position jump and missing `playing` are handled. But `wait: RECOVERED` can be produced by the operator's own Start or by a restart made after unlock, on exactly the runs where the locked restart failed, so the log can answer D6 falsely. Important 1 and 2 are small fixes; the second also needs one line on the operator sheet.
