### Spec Compliance

- ❌ Issues found: one. Everything else in Steps 1-5 and the carried requirements matches. `player.start()` tears down during a stall, which breaks "the element is not touched between a failure and a restart result" and the spec's "while the network is unreachable the element is left alone" (`antenna/public/assets/player.js:98-106`). See Important 1. The spec line "Play always joins live" pulls the other way, so the behaviour needs a ruling; a recommendation is below.
- ✅ Verified by reading the diff:
  - Probe: `cache: "no-store"`, 8 s limit via AbortController + setTimeout, no `onLine`. Any HTTP response is `reachable`; off-air goes through `classifyProbe`; a verdict acts at once through `step(Date.now())` (player.js:115-131).
  - Session counter: `asked !== session` drops a late verdict before `recovery.verdict` is called (player.js:128). `begin()` resets `probing`, so a dropped verdict cannot wedge it.
  - No tick after Stop (player.js:183-185).
  - `tick` and `mayPlay` use `Date.now()`: app.js passes it, and `restart()` checks with the same `nowMs` in the same synchronous run before `attach()`.
  - `playing` and hubs are driven by `recovery.advancing` alone, apart from `start`'s brief-mandated `playing` (player.js:155-157). No `playing` listener; a resolved `play()` does nothing.
  - `stalled` is not handled; `waiting` goes to `noteWaiting`; `ended` goes to offair; `pause` goes through `pauseMeansStop`.
  - `refused` only via `playBlockedNotice`; any other rejection falls through.
  - Media Session: three handlers, metadata only on a text change, `start()` before `refreshTimeline(true)`.
  - app.js matches Step 3. All ten Step 4 scenarios are present, plus the required extras.
  - The request guard is on `context` and fails a bare `?`.
  - Only four files changed, none of them frozen.
- ⚠️ Cannot verify from the diff, needs the iPhone (Task 12 or the operator):
  - Whether WebKit ever delivers `pause` after a restart. The pasted logs for tests 9a, 9b and 9c are the cheapest evidence: look for `event pause` just after each `wait: restart` line. They are not in the repo (the doc is a summary), so I could not check. They need reading before the 500 ms question is closed.
  - A restart failing on a locked phone. The probe says HTTP reached but the join fails: the element has no audio, and iOS freezes the page in about 9 s (Test 3), before the 25 s join runs out. Recovery then waits for unlock, where `mayPlay` guards it. This is inherent to the design and not this task's defect, but no measurement covers it.
  - D5, the home-screen run: still open.
- Mutant evidence is the implementer's claim; I did not re-run it. No brief step was test-first, and the report says so.

### Strengths

Native path traced by hand against the probe; it holds at each step:
- Stall: `waiting`, no `pause`. Nothing touches the element for about 30 s + 4-6 s (`failAfterMs` native, then `fail()` jitter). The first `probe` sets `reconnecting`.
- Offline: fetches fail fast, `unreachable` changes nothing but the next probe's time, and the element stays attached, so timers stay alive (D4).
- First HTTP answer: the verdict runs `step` in the fetch continuation. `sample` runs first, so an element that moved by itself cancels the restart. That is the probe's "position moved" check (probe.js:277-281).
- Restart: the sequence is `pause`, `removeAttribute`, `load`, `src=`, `play()`, from the fetch continuation, identical to probe.js:156-166 + 282, the path measured working on a locked phone in 9a and 9c. D6 therefore applies to this code as written.
- After a restart: `restarted()` clears samples, so a first position of 0, or iOS's own jump to 40 s, is a baseline or a `jump`, not progress.
- Native off-air: 403 gets `error`, then `failed`, then probes, two `offair` verdicts about 15 s apart, then `halt("offair")`; the count survives. ENDLIST gets `ended`.
- `error` during a join is ignored by `failed()`, and the join expiry then counts the failure, so a `NotSupportedError` restart (Test 3) loops correctly and `refused` still ends at Try again.

Also well done:
- The probe's answer is computed in one place with `clearTimeout` on both paths, and the body read sits inside the limit.
- `selfTeardown` matters only while `wanted`, and `clearTimeout(settleTimer)` stops an earlier timer ending a later hold.
- The "follows the playback position" scenario uses a real PDT offset instead of a stub.
- The one-failed-probe scenario holds the clock, so only the verdict can restart: a strong pin of "runs tick at once".
- The caps test requires more than 10 requests, so it cannot pass idle.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `antenna/public/assets/player.js:98-106`, reached from `#play`, `#retry` (not visible during reconnecting) and the Media Session `play` handler (player.js:210-213). Play pressed during a stall calls `tearDown()` at once, whether or not the network is back.
   - Why it matters: this is the "harmful act" in the probe's Reading, and pressing Play at "Reconnecting…" is the natural thing to do in a dead spot. Test 3 is this trace exactly. Unlocked and offline, `play()` rejects `NotSupportedError` and `error` code 4 follows. While unlocked, recovery still works (`failed`, probes, restart). Lock the phone and iOS freezes the page within about 9 s, so nothing recovers and audio does not come back when the network does. A car or lock-screen `play` on a hidden page reaches the same freeze directly. `playbackState` is "playing" throughout, so that route needs a car with a discrete Play button, but the page key alone is enough. The press also resets the 10-minute give-up clock via `begin()`.
   - A plain "ignore Play" is not right either: Test 2 measured "on unlock, Start worked in about 1 s" with the network back, and ignoring the press costs up to 15 s there.
   - What the behaviour should be: Play during a stall asks instead of tearing down.
     ```js
     if (wanted && (state === "reconnecting" || recovery.stalled)) { /* probe now */ }
     ```
     Bring the probe forward through a small new `Recovery` method (retry due now, `lastProbeMs` cleared; create the failure if none is pending) and return. A reachable answer then restarts within a fetch, by the existing path; an unreachable one leaves the element alone and the page still reads "Reconnecting…". The `recovery.stalled` half matters because state still reads `playing` for the first 35 s of a stall, with the hubs stopped. Leave the give-up clock alone. Press Play when not stalled: unchanged, rejoin. `refreshTimeline(true)` in the handler stays.
   - Pin it with a unit test on the new method, and a smoke test: Play during `setLive("drop")` leaves `src` untouched and gives a probe; Play after `setLive("live")` restarts without waiting out the interval.
   - The implementer asked for a ruling, and the spec's two sentences conflict. It is the manager's or operator's call, but leaving it as is should be a recorded decision, not a default.

#### Minor (Nice to Have)

1. `player.js:14,47`: the `selfTeardown` hold is a wall-clock guess. Assessment of concern 2 is below; no defect traced. Better shape: clear it on `loadstart` instead of a timer. `load()` drops queued media tasks (HTML spec; WebKit's `prepareForLoad` does the same, from memory, not measured here), and any pause still queued precedes the `loadstart` of the new source in FIFO order. The hold only matters while `wanted`, and in `start` and `restart` a `src` always follows, so `loadstart` always arrives. That removes the unmeasured constant and shrinks the window. Keep the timer only if that fails on the iPhone.
2. `player.js:98-106`: `start()` does not clear `#hubs`. Pressing Play while playing leaves `turning` up to one tick (6 s locked) though `recovery.begin` has cleared `advancing`. The brief says "exactly". Add `hubs.classList.remove("turning")`.
3. `smoke.pw.mjs`: no test pins concern 1. No scenario clicks `#stop` on a notice, so removing the `if (wanted)` at player.js:109 goes unnoticed. Add one line to the ENDLIST scenario (smoke.pw.mjs:582): click Stop, expect the off-air text and `#retry` still visible.
4. `smoke.pw.mjs:8`: `EXPECTED_STATUS` is global, so a stray `ERR_FAILED` on a segment or timeline in any test no longer fails. The URL guard still catches a wrong host or path, but not a real failed fetch. Make the net-error half a per-test flag set by the scenarios that use `drop` or `route.abort`.
5. `player.js:34-36`: the `tearDown` comment says never between a failure and a restart, which `start()` currently breaks. It goes true once Important 1 is settled; otherwise reword it.
6. `app.js:15` (brief-mandated Step 3): `playing: player.audible` means Now playing runs on the wall clock in the first ticks after Play and through the 35 s stall window before `reconnecting`, about 123 s ahead of the audio. Near a song change the line can flip to the next song and back. Passing `wanted`-with-`playbackMs` would hold the last playback position, but the brief wrote it this way. Noted only.
7. Native wiring has no automated cover. A cheap partial pin: a smoke with `navigator.vendor` and `canPlayType` stubbed to take the native branch in Chromium. The stream won't play, but `error`, `failed`, probes and "src untouched" would run through the native arm. Optional; Task 12 is the real check.

### The five judgement calls

1. **`stop()` a no-op off-session (player.js:108-110).** Right. Otherwise Stop on a notice replaces "The station is off the air." with the "press Play" line and hides Try again, against the spec's table. Keep it; pin it (Minor 3).
2. **The 500 ms `selfTeardown` hold.** Sound in direction, acceptable to ship, and worth replacing.
   - The implementer is right that waiting for a `pause` would stick, since `load()` cancels it.
   - Two things differ from the report. On a locked phone a 500 ms timer does not fire at 500 ms: the probe shows timers quantised to 6.00 s (asked 5 s). The hold can therefore last about 6 s after a locked restart, not 500 ms.
   - The harm in that direction is small: a real pause in that window is swallowed, and audio could restart later. A restart only happens inside a dropout, which the spec's exception covers. After a Play press the listener is present.
   - The opposite direction is the one to check. If WebKit delivers a late `pause` past the hold on an unlocked phone, then `stalled` is already false (cleared by `restarted()`), `pauseMeansStop` is true, and a recovery silently turns into a Stop. Nothing suggests this happens, and the pasted 9a-9c logs can settle it (see ⚠️).
   - Should be: end the hold on `loadstart`, deterministic and independent of timer throttling.
3. **A pause just after a join.** Acceptable, with a limit. Frozen or `waiting` during the initial join reads as a stall, so a Bluetooth disconnect in the first seconds after Play is ignored and audio can restart about 35 s later. Spec-wise this is not "a dropout under way", so it is a real small gap. But it takes a car-off within seconds of pressing Play, it stays bounded by the 10-minute limit, and fixing it means changing `stalled` in a reviewed module. Leave it and record it as a known limit. The test waiting for the hubs is right: it tests the rule past the join.
4. **Play during an outage.** Not acceptable as is. Important 1.
5. **Wider console allowance.** Fine for now, better scoped per test (Minor 4). The URL guard remains the real protection.

### Checks run (named risk, then what I checked)

- Restart form differs from the measured one: read probe.js:138-166, 251-258, 276-283. Same order, same continuation.
- `load()` versus the queued pause: read `public/player.js:30-40`, which has the same order but never met a queued pause with `playing` true, so it is no evidence. WebKit is not installed under ms-playwright, so no browser measurement.
- `refreshTimeline` gate versus handler order: read page.js:157-158.
- Keys remain live during reconnecting: index.html:41-42 and `public/assets/radio.css` have no disabled state, so Important 1 is reachable.
- Smoke not re-run, per the rubric.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The automatic recovery path is correct, and traced by hand it matches the measured iPhone behaviour step by step, including restart form and verdict timing. One gap remains: a Play press during a stall performs the teardown the whole design exists to avoid. It needs a probe-first fix or a recorded operator ruling.
