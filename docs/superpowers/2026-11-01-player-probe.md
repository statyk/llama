# Player: the early iPhone test

Results of plan Task 1 Steps 6-7, from the operator's runs on 2026-11-01. The test page was `antenna/public/assets/preview/probe.html`, from preview rounds 1 and 2. The log excerpts below are the parent session's summary of the operator's pasted logs.

# Early iPhone test: Safari results so far (2026-11-01, iOS Safari, UA iPhone OS 18_7, Version/27.0.1)

Summarised by the parent from the operator's pasted log (11:06-12:07 EST). Times are the log's.

## Test 1 (music on, locked 11:16:22-11:36:06, about 20 min). Operator: music and lock-screen display kept updating.
- setInterval ran at a steady 6.00 s (asked 5 s), no LATE lines; timeupdate every 5.02 s.
- `stalled` fired about every 11 s during HEALTHY playback (buf 105-125 s, ct advancing). It is not a dropout signal.
- Stopped and hidden, timers sleep: gaps of 349 s and 51 s, and 1016 s below.

## Test 2 (Start 11:38:35, locked 11:38:43, offline 11:38:48, online 11:43:39, unlocked 11:46:25). Operator: audio did not come back.
- Buffer ran out at 11:40:38: `event waiting`, rs=2, paused=false. ct stuck at 163.71 from then on. A real stall, STALL lines present.
- NO `pause`, NO `error`, NO `stalled`, no `ended` in the whole dropout. paused stayed false.
- Timers kept running at 6.00 s through the whole stall, locked (stuck reached 341 s, no LATE).
- `online` fired at 11:43:39. Timers still running. iOS then did nothing for 2 min 46 s: no event, ct stuck, rs=2.
- On unlock, Start worked in about 1 s.

## Test 3 (Start then Retry loop, locked 11:47:06, offline 11:47:13, unlocked 12:04:36). Operator: audio did not come back.
- This run did NOT test what it was meant to. Retry 3 fired at 11:47:30 while offline, with 94 s of good buffer left, and tore it down.
- `play()` REJECTED `NotSupportedError`, `error code=4`, ns=3. That is the network, not permission: a retry 4 after unlock resolved.
- Page then froze: last tick 11:47:39, next 12:04:36 (gap 1016 s). With no audio, iOS suspended the page within about 9 s.
- Retries 4 and 5 were on an unlocked page, so they say nothing about permission on a locked one.
- So D6 (may a locked page restart audio by itself?) is still UNANSWERED. Nobody has tried it with the network back.

## Extra run (Start 12:05:21, offline 12:05:29, online 12:07:30)
- Stall began 12:07:25 (`waiting`). `playing` at 12:07:29, online 12:07:30; ct advancing again by itself. iOS recovers a 5 s stall alone.
- Compare test 2: a roughly 3-minute stall did not recover alone. The threshold is unknown.

## Reading
- D1: `pause` does not fire in a dropout. The stall condition in pauseMeansStop is harmless. Use position, plus `waiting`, and NOT `stalled`.
- D3: timers survive locking while the element is in use. Metadata can run from the timer; no timeupdate fallback needed.
- D4: while the element is left alone, timers run through a locked stall at least 5 min 41 s. After a failed teardown they stop within seconds.
- The harmful act is the teardown while offline: it ends the audio session and iOS freezes the page, so nothing can recover. Leaving the element alone keeps the page alive.

## Tests 5, 6, 7 (12:11-12:56, Safari, Ford 2014 and Jeep 2018)
- Operator: car and lock-screen Play resumed after both Stop (teardown) and Pause only. Ford shows title and artist; Jeep also album. Bluetooth off: Ford flips to FM, Jeep "bluetooth disconnected"; the phone never moved to its speaker. Lock-screen Play within seconds resumes; after about 30 s it fails and the title details drop, controls remain; unlocking to Safari then resumes at once.
- Log, teardown then Play: `media session action play` reached the hidden page and play() resolved (12:11:34, 12:20:19, 12:31:52). Same after Pause only (12:12:16, 12:20:43, 12:32:03). No difference, so D2: a normal teardown Stop is fine, no keep-session branch.
- Log, Bluetooth off: a plain `event pause` with paused=true, rs=4, position advancing, no stall, no Media Session action (12:22:39, 12:24:35, 12:25:06, 12:26:22, 12:27:16, 12:32:13). So D1's rule holds: pause with no stall under way = Stop.
- Log, page sleep: stopped or paused and hidden, ticks ran for 6-12 s then gaps of 45-54 s (119 s and 400 s when stopped longer). A late Play was delivered only at wake, usually at the moment of unlock (12:20:05, 12:23:05, 12:25:59, 12:28:15). So Play from the car works only for a short time after stopping. iOS limitation; document it.
- Log, warning: at 12:33:17 a Play delivered at wake gave `playing` and play() resolved while hidden, then the page froze 1414 s with ct still 40.96. `playing` and a resolved play() do not prove audio: recovery must count only an advancing position, as the plan already says.

## Test 9 (preview round 2, Safari, 13:03-13:19)
- 9a, form full: offline 13:03:34, stall 13:05:30, online 13:11:09, fetch 200 at 13:11:12 (stuck 336 s), restart while vis=hidden, play() resolved 13:11:13, ct advanced 40.96 to 44.60 by the 13:11:17 tick, when the operator unlocked. Operator heard it within seconds of airplane mode off. No RECOVERED line only because the run was unlocked at about 4 s: the line needs 12 s. Audio demonstrably moved while hidden.
- 9b, form gentle: offline 13:12:24, stall 13:14:19, fetch 200 at 13:17:37 (stuck 192 s) with navigator.onLine still false, restart while hidden. `wait: RECOVERED ... restart_vis=hidden in=12s` with vis=hidden. A clean yes.
- Timers ran at 6 s through both locked stalls. All fetches while offline failed in about 15 ms and touched nothing.
- 9c (15 min offline) is not in this log. Log ends 13:19:13.

## Decisions (parent)
- D1: `pause` does not fire in a dropout; a Bluetooth disconnect is `pause` with no stall. `pauseMeansStop` stands. Use `waiting` and the position, never `stalled`.
- D2: normal teardown Stop, no keep-session branch.
- D3: timers survive while the element is in use: metadata runs from the timer.
- D4: timers run through a locked stall of at least 5 min 36 s with the element left alone. They stop within seconds of a failed teardown, or once stopped.
- D6: YES, a locked page may restart audio by itself, once the network is back, for stalls of at least 5 min 36 s. 9c extends this.
- Restart form: full, one code path with hls.js; both worked.
- Restart rule: never tear down until a probe gets an HTTP response. Use the fetch, not navigator.onLine, which lagged the network by a few seconds.
- D5: open until the home-screen run.

## Still open
- D5, the home-screen run: Task 11 waits for it.
- 9c, 15 minutes offline: it may shift a constant.
- A backwards playlist step can't be produced here: that case stays unverified and is left to the road.
- Both preview rounds still need `--remove-preview` (the operator's, from the worktree's `antenna/`).

## Go-live notes
- Restart form: full. Gentle worked too (9b); it is not used, so hls.js and native keep one code path.
- After Stop or a Bluetooth disconnect iOS sleeps the page within about a minute, so a car or lock-screen Play made after that waits until unlock.
