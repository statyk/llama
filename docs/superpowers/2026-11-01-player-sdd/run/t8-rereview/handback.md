### Finding Verdicts

- **1. Play during a session tore down at once** — ADDRESSED.
  - Play while `wanted` asks first: player.js:117-123. Any HTTP answer, off-air included, rejoins (`answer !== "unreachable"`, :123). A rejected or timed-out fetch does nothing: no `verdict`, no state change, no element touch.
  - Play while not `wanted` is immediate and synchronous: :113-116. It still runs before the first `await`, so the Media Session comment "start first" (:233) and the `refreshTimeline` gate (page.js:158) stay true. :235-236 keep `refreshTimeline(true)` after it.
  - Stop drops the ask: `halt` bumps `session` (:54), checked at :121.
  - A second press adds nothing: :117.
  - Key and #retry bind `player.start` (app.js:9-10); the Media Session `play` calls it too (:235). #retry only shows in gaveup, offair and refused, all not `wanted` (page.js:147), so it takes the immediate route.
  - The fetch is shared: `ask()` :132-145, used by `probe()` :151.
  - Spec: one sentence added beside "Play always joins live" (design spec, Play and Stop keys bullet).
  - Mutants claimed in the report (immediate-teardown, rejoin-on-unreachable, handler-skips-ask, ask-ignores-stop, no-inflight-guard, offair-answer-no-rejoin) match the new scenarios by reading. Not re-run.
- **2. start clears `turning` on #hubs** — ADDRESSED: player.js:104, before attach. `recovery.begin` also clears `advanced`, so `step` cannot turn them back on without an advance.
- **3. ENDLIST then Stop keeps the notice and #retry** — ADDRESSED: player.js:127 gates on `wanted`, and `halt("offair")` already cleared it (:53). Pinned in the ENDLIST scenario (smoke diff lines 34-36).
- **4. A play() that never settles** — ADDRESSED.
  - No `refused`: a pending promise never reaches :92-93.
  - Hubs and `playing` come only from `recovery.advancing` (:180-181), with a frozen position. The one exception is in Out-of-Scope, item 1 below: a measured-gap arithmetic case in `sample()`, not this fix.
  - Reconnecting comes from the first probe or restart result (:174-175).
  - iOS's own `pause` is covered by `stalled || joining` (:228).
  - Scenario pins the state after the pause, 40 s later, and then a real play() giving Song 3 with hubs.
  - The first join after a press is uncovered by `joining`, by finding 5's terms.
- **5. A `pause` before audio moved after a restart is no Stop** — ADDRESSED.
  - recovery.js:158-160, player.js:228.
  - `begin` clears `joinUntilMs` through `clearAttempt` (:84), so the first join after a press is unchanged.
  - `restarted` sets it after `tearDown` and `attach` (player.js:162-164). The queued pause is async, so there is no gap.
  - Mutant report (never-settling RED without `|| recovery.joining`) fits the k=1 dispatch and the stated k-table.

### Weighed specifically

- **`joining` staying true too long:** `advance()` is the only exit besides a new `begin` or `restarted`, and any real rise reaches it. A jump sample does not trap it. Ran the real `Recovery` at a 6 s tick after a restart with positions 0, 40.96, 46.9: `joining` true, true, false. It clears within two or three samples of audio moving, and cannot stick while audio plays. Residue is new-breakage item 1 below.
- **`asking` left set so Play goes dead:** not possible.
  - `ask()` always settles (the whole body is in try/catch, and the 8 s abort also covers `res.text()`).
  - On a same-session answer it is cleared (:122).
  - On a stale answer it keeps an old session number, which can never equal the current one, since `session` only rises.
- **Stale answer rejoining:** dropped at :121 across Stop, offair, gaveup and refused, and across Stop-then-Play (session +2).
- **Ask vs recovery probe:** the two are independent fetches. At most one extra per press, and only listener-driven. A probe in flight when the ask rejoins is dropped (session bump), and `begin` resets `probing`.
- **Ask vs restart:** `restart()` does not bump `session`, so an ask can outlive a restart. See new-breakage item 2. No wrong end state.
- **Rejoin after an `await`:** it loses the user gesture, so `play()` runs without one. This is the same unprompted same-element play the recovery restart already relies on (probe Test 9c, Test 8 restarts). If refused, `halt("refused")` drops `wanted`, and the next press takes the synchronous route. It self-heals.

### New Breakage in the Fix Diff

No Critical or Important.

1. Minor, player.js:228, recovery.js:158. A real plain `pause` (Bluetooth disconnect) is swallowed from the moment audio actually moves until the sample that confirms it.
   - That is up to 12-18 s at the locked 6 s tick (baseline, possible jump, then advance), slightly beyond finding 5's letter.
   - Recovery then restarts audio by itself after the join runs out.
   - The Media Session `pause` and `stop` go straight to `stop` and are not affected, so only the event route is.
   - Same class as the handback's concern 3, and the coordinator already ruled on the window. Note it; no fix needed.
2. Minor, player.js:118-123 with :162-164. If a recovery probe's answer restarts while Play's ask is in flight, the ask's answer tears down the just-made restart and rejoins (`begin` also resets `restarts` and the give-up clock). Two teardowns close together, both after an HTTP answer. It is the listener's own press, so the outcome is correct, and the worst cost is a slightly later audio start. Leave as is.
3. Minor, test gap, smoke diff. The ask's timeout has no scenario: `drop` is an instant rejection, and no smoke test holds a fetch past 8 s. The timeout is now what stops `asking` blocking Play on a hung fetch, and finding 1 says "rejected or timed-out". The code is right by reading. A held route plus 8 s of `page.clock`, then a second press producing a new probe, would pin it.

### Out-of-Scope Observations

1. Minor, recovery.js:183-200 (`sample`, untouched). The jump test scales with the sample gap, so a sleeping-timer gap defeats it.
   - Ran the real class: positions 0 then 40.96 with a 42 s or 153 s gap give `advancing: true`, `stalled: false`, `joining: false`. With a 6 s gap it is correctly no advance.
   - Those are the Test 8 numbers (`ct=40.96`, gaps 42 s and 153 s).
   - It needs the first sample taken before the element reaches 40.96, then a gap of at least 39 s. Effect: one false `playing` tick with hubs, `lastAudioMs` refreshed, and a stuck join cleared, so an iOS `pause` right then reads as a Stop.
   - Rare and unmeasured as a sequence; for the final review.
2. Minor, recovery.js:112-117. `failed()` nulls `lastPos`, so the next sample clears `frozen` while a retry is pending. With no earlier restart `joining` is false, so a `pause` in that one sample reads as a Stop. Same shape as finding 5, on the native `error` path only. `|| this.retryAtMs !== null` in the check would cover it, if it matters.
3. The working tree's HEAD is aed6e294, two docs-only commits past the reviewed 826f3e42. `git diff --stat 826f3e42 HEAD -- antenna docs` shows only the probe doc and the spec, so the code read is the code reviewed.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

Checks run: one scratchpad node script on the real `Recovery` (results above). No suite run, as the rubric directs; test results are the fix report's claims (516 and 36 passed), unverified here.
