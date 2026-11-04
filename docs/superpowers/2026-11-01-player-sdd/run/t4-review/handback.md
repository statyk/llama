### Spec Compliance

- ❌ One issue: `failed()` is cancelled by the next tick on a real element, so "the failure counts at once" does not hold in the natural case (Important 1 below). Everything else in the brief's Interfaces and Step 3 is implemented as written.
- Nothing extra. Both listed files exist. `player.js`, `nowplaying.js` and `style.css` have no diff in b7e48066..676b9a42 (`git diff --stat` on the three printed nothing).
- ⚠️ Cannot verify from diff, for Task 8:
  - Review Focus 5 (Stop during a retry delay never restarts audio) cannot live in this module: it has no stop. Called after a Stop, `tick` still returns "probe", then "restart" (checked, R3). Task 8 must not call `tick` once stopped, and must drop a verdict from a cancelled session. The session counter in the plan does this; the smoke scenario must prove it.
  - `tick` and `mayPlay` need a wall clock (`Date.now()`), not `performance.now()`, or the frozen-timers rule fails.
  - The request-storm bound below covers this module's probes and restarts only. What hls.js itself fetches per restart is Task 8's smoke limit (at most 60 in 10 minutes).

### Journey traces

Run with node against the committed module (`git show 676b9a42:antenna/public/assets/recovery.js`, byte-equal to the worktree), driven as Task 8 will: probe answered at once, `tick` re-run at once, restart performed at once. Script: scratchpad `t4/trace.mjs`, output in `t4-review.log`. random 0.5 unless stated.

(a) iPhone dropout, native, 6 s ticks. Plays to 180 s (offline at 60 s, buffer ends at 180 s), stall 5 minutes, network back at 480 s.
- 6-180 s: "none", advancing every tick. 186-210 s: "none" (failure at 210 s, last advance + 30 s; delay to 215 s).
- 216 s to 468 s: 15 probes every 18 s (15 s spacing on a 6 s tick), all `unreachable`; tick returns "none" between. No restart.
- 486 s: probe, `reachable`, the re-run tick returns "restart", `mayPlay` true. 306 s since last audio, inside the 10-minute limit.
- After: with ct 0 then 41, a baseline then a jump, then real advances; with ct 41 at once, a baseline then advances. Both end advancing, not stalled.
- hls.js at 1 s ticks: failure at 195 s, probes from 200 s every 15 s, restart at 485 s.
- Network never back: probes only, "giveup" at 780 s (last audio + 600 s).

(b) Restarts that keep failing. Probes always HTTP 404, position frozen:
- hls.js: restarts at 20, 55, 100, ... gaps 35, 45, 55, 55... s; 12 restarts, 12 probes, "giveup" at 600 s.
- native: 11 restarts, 11 probes, "giveup" at 600 s. Native at 6 s ticks: gaps 42, 54, 60... s. random 0, the fastest jitter: gaps 33, 41, 49... s.
- 5 s of real audio after every restart, then frozen, 30 minutes: gaps 31, 41, 51, 51... s. It never gives up, because each advance is real audio; the spec counts from "the last advancing playback", so this is compliant. One restart per about 51 s.
- Fastest loop I could build, a native `error` right after each short advance, random 0: gaps 15, 18.5, 26.5, 26.5... s, min 15 s; 35 restarts in 15 minutes.

(c) Off-air with no network between probes:
- Native, 6 s ticks: probes at 156 `offair` (count 1), 174-228 four `unreachable` (count stays 1), 246 `offair` returns true. No restart.
- hls.js, `offair`, `reachable`, `unreachable`, `offair`: 20 s count 1; 35 s reachable and RESTART; 70 s unreachable; 85 s off-air true. Count survived the restart.
- Plain off-air on every probe (native): 155 s and 170 s, 15 s apart.
- One `offair`, then no network for good: "giveup" at 720 s, so "Lost the stream." instead of the off-air notice. Correct: nothing has shown off-air twice, and the limit applies. Bounded either way.

Answers:
- Tear down while unreachable: no path via "restart". It needs a `reachable` younger than 10 s (recovery.js:97), and a verdict can only read older than it is. The one teardown while offline is "giveup" at 10 minutes, which the spec asks for. That is still open against 9c ("15 minutes offline may shift a constant"), not a defect here.
- Loop faster than the delay: no. `retryAtMs` is set only by `fail`, cleared only by `restarted` or a real advance, and `failed` is ignored while one is set. Probes stay spaced across restarts. Minimum seen 15 s; the floor after 60 s of real playback is one 4 s delay per playback run.
- Never reach off-air: no. Two off-air answers reach it within two probe intervals; with no answers the 10-minute limit ends it.

### Implementer's concerns 2-6

- 2 (stale verdict returns "none" at 10-15 s): correct. Spacing is a strict limit and freshness only refuses a restart; test recovery.test.ts:204 still ends on "probe" more than 10 s later.
- 3 (baseline or jump sample reads as neither stalled nor advancing): correct. The wrong reading there is a Stop, which never plays aloud. `waiting` still counts.
- 4 (an advance clears a pending failure, including during its delay): correct for a position stall; the spec defines recovered that way. But the same rule causes Important 1 for `failed`.
- 5 (no join on first Play): accept. The brief's tick times force it, and the cost is one extra restart on a start over 20 s.
- 6 (`failed` ignored during a join): accept. The brief says so, it is bounded by 25 s, and it holds the rate down. A real advance ends the join.
- 1 (verdict time): agreed. It also keeps working on a slow tick: `nowMs` is the launching tick, so age is about the fetch time.

### Strengths

- `restart` has one gate and no other route: delay run out and a fresh `reachable` (recovery.js:96-100).
- One `lastAudioMs` as both clocks keeps stall and give-up from drifting apart; give-up is checked straight after sampling (recovery.js:92-93).
- The backoff index counts restarts, so a stall iOS recovers alone does not grow it.
- The mutation work caught and fixed a test passing for the wrong reason (the higher first sample), and the stale-verdict age concern is written down for Task 8.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. recovery.js:109-113 with :192-198, test recovery.test.ts:108. A native `error` on an element that was playing is swallowed. The position rose between the last sample and the error, so the next tick samples an advance, `advance` runs `clearAttempt`, and the failure is gone. Only the 30 s stall rule is left. Trace (error at 2.7 s, tick at 3 s with ct 2.7): `retryAtMs` null, first probe at 38 s, against 8 s when the position is flat. On a locked 6 s tick nearly every such error is lost. The test passes only because it holds the position flat across the error, which a real element wouldn't. Bounded (about 30 s late, then normal recovery), but it is the brief's stated behaviour for `failed` and the spec's "or an `error` event".
   Fix: in `failed`, after the guard, make the next sample a baseline (`this.lastPos = null`). Tried in a scratch copy, not the suite: dying element first probes at 8 s; an element that really keeps playing still never acts, because its second sample cancels the failure. Add a test with the position rising before `failed`.

#### Minor (Nice to Have)

1. recovery.js:173-189: a pre-load sample followed by a long freeze reads as audio. Trace: restart, sample ct 0, page frozen 1414 s, wake at ct 40.96 with no real audio. The rise is under the wall-clock bound, so it is an advance: `lastAudioMs` moves to now, `mayPlay` true, and a restart follows about 42 s later, 24 minutes after the last audio. The same goes for a Play that never got audio. Control: a wake with ct unchanged gives "giveup". It needs a tick inside the roughly 1 s pre-load gap and then a freeze; the measured 12:33 run had ct 40.96 before freezing, which takes the control path. Audio then starts on an awake page only. The brief's test `tick(900, 3_600_000)` pins the bound, so a fix is a brief-level decision. I would not block on it.
2. recovery.test.ts:384-385: time runs backwards (`failed(20000)`, then `tick(2, 9000)`). Harmless, since neither depends on it, but it reads as an error. Use ascending times.
3. recovery.js:176: the baseline sample computes `jump` from a null `lastSampleMs`. It is false only through null-to-zero coercion. `const jump = !baseline && ...` says what it means.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The module holds all three strict properties across the traced journeys: no restart while unreachable, no loop faster than the delay, and off-air or give-up always reached. One small defect remains: a native `error` on a playing element is cancelled by the next sample, and the test hides it. It is a one-line fix plus a test.
