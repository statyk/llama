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

## Test 9c (preview round 2, Safari, form full, 13:31-13:58)
- Offline 13:31:43, stall 13:33:34, fetch 81 status=200 at 13:58:06 (stuck 1470 s, 24 min 30 s), online event at 13:58:06, restart form=full while vis=hidden, play() resolved 13:58:07.
- `wait: RECOVERED after restart 1 form=full restart_vis=hidden in=12s`, vis=hidden, at 13:58:18. The operator heard audio within seconds of airplane mode off. A clean yes.
- Timers ran at 6.00 s for the whole locked stall (no LATE); 81 fetches, each failing in about 16 ms while offline.
- An abandoned run before it (offline 13:26:00, online 13:30:32): one fetch failed in 102 ms at 13:30:43 with net=on, 11 s after `online`, and the operator reloaded. So a fetch can still fail just after the network returns: the probe must keep retrying, which it does.
- D4 extended: timers run through a locked stall of at least 24 min 30 s with the element left alone. D6 extended to the same length.
- The 10-minute give-up stays the operator's ruling; `giveUpMs` is the constant if it changes. Recovery past 10 minutes is possible, so the limit is a choice, not a technical bound.
- Every page load in this log says standalone=false. D5's home-screen run has NOT been done.

## Test 8 (home screen, preview round 2, 14:07-14:46; every load standalone=true)
- Test 1 (locked 14:09:06-14:16:37): timers 6.00 s, timeupdate 5.02 s, same as Safari.
- Test 2 (Wait off; offline 14:17:18, stall 14:19:17, online 14:22:12): no resume, same as Safari. Not a defect: iOS does not resume alone.
- 9a run 1 (Wait on; offline 14:27:42, stall 14:29:32, online 14:29:53): fetch 200 at 14:30:13, restart while hidden; operator unlocked at 14:30:13.838, so audio arrived just as they unlocked, 20 s after the network returned. No RECOVERED line, Stop at 14:30:18. This is very likely the operator's "did not resume": they stopped waiting about when it fired. It does not show the old icon blocked recovery.
- 9a run 2 (Wait on; offline 14:39:09, stall 14:40:57, online 14:44:38): fetch 200 at 14:44:50 (stuck 228 s), `wait: RECOVERED after restart 1 form=full restart_vis=hidden in=12s`, vis=hidden, 14:45:02. A clean yes for the home-screen app.
- Recovery delay after the network returns: up to about 18 s (probe interval), plus 30 s from stall start before the first probe.
- Back swipe: popstate 14:34:16, 14:34:37, 14:34:55, music uninterrupted. archive.org: repeated opens 14:30:54-14:31:33, audio continued, returned to the app.
- DIFFERENCE from Safari: Play after Stop while hidden. `media session action play` DOES reach the page (14:23:48, 14:36:59, 14:37:38, 14:38:07), play() is called, element sticks at rs=1 ct=40.96 buf=none with no `playing`, then `stalled`. Audio starts the moment the app becomes visible (14:27:13, 14:37:04, 14:37:59, 14:38:13). Safari reached `playing` hidden in 0.2-0.4 s for the same act. While stuck, timers slow and sleep (gaps 42 s, 153 s); `pause` and AbortError can follow; at 14:27:13 iOS itself started playback on unlock with paused=true beforehand.
- By contrast, a hidden teardown + play with the audio session still alive works in the app: 14:08:45 (0.5 s) and both 9a restarts.
- Unexplained, once: after the 14:36:59 Play, audio ran hidden briefly, then 14:37:17 `stalled ct=49.99 buf=none`; 14:37:28 page load with no pagehide. Unknown whether the operator closed the app.
- Not run from the icon: test 6 (Pause only, then lock-screen Play). It decides whether keeping the session would fix the difference.

## Test 6 from the home-screen icon (operator, no log)
- Start, Pause only, lock, lock-screen Play within 5 s: audio did not start.
- Caveat: the probe's Media Session play handler tears down before play(), so this tested pause + teardown + play, not a plain play() resuming the paused element. A plain resume is untested, and on a live stream it would rejoin stale audio anyway.
- The 14:37:28 reload: the operator does not recall, and may have closed the app. Not pursued.

## D5 (parent)
- The home-screen app matches Safari on locked playback, dropout recovery, back swipe and archive.org. Keep it. No Stop change.
- Documented limitation: in the home-screen app, once stopped, lock-screen and car Play reach the page but audio will not load until the app is opened, where it then starts. Safari allows Play for a short time after stopping.

## Second home-screen audio app (operator)
- Reinstalled the other app, a separate station built by someone else. Its lock-screen Play after stopping also fails, which points to an iOS limit rather than our code.
- Tapping the lock-screen player now opens our app whichever app is playing. Before, with the other app installed first, it opened that app. So the oldest-installed home-screen app appears to win. Two observations on one phone.
- Limitation to document: with several home-screen web apps, tapping the lock-screen player may open a different one. Audio controls are not the cause and Safari is not affected as far as tested.

## Still open
- A backwards playlist step can't be produced here: that case stays unverified and is left to the road.
- Both preview rounds still need `--remove-preview` (the operator's, from the worktree's `antenna/`).

## Go-live notes
- Restart form: full. Gentle worked too (9b); it is not used, so hls.js and native keep one code path.
- After Stop or a Bluetooth disconnect iOS sleeps the page within about a minute, so a car or lock-screen Play made after that waits until unlock.
- In the home-screen app, once stopped, lock-screen and car Play reach the page but audio will not load until the app is opened, where it then starts.
- A second station's home-screen web app fails lock-screen Play after stopping too, which points to iOS. With two such apps installed, tapping the lock-screen player opens the oldest-installed one, whichever is playing (two observations, one phone).
