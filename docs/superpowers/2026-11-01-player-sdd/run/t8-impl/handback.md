Status: DONE_WITH_CONCERNS
Commits: 20956a90 antenna: the new player with recovery and Media Session; 1d11b365 antenna: smoke pins a verdict's restart, the force gate and `playing`
Tests: cd antenna && npm test: 515 passed; npm run smoke: 31 passed (15 baseline + 16 new, 2.7 min). Frozen files and antenna/src unchanged against 23cad993.
Concerns: 5 judgement calls below (Stop no-op off-session, a 500 ms teardown hold, pause just after a join, Play during an outage, a wider console allowance). The native path is not exercised by any smoke (Chrome uses hls.js); Task 12 covers it.
Handback: /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/sdd/player/t8-impl/handback.md

## Implemented
- antenna/public/assets/player.js (new, 224 lines): `player = { start, stop, tick, audible, playbackMs }`. hls.js config and comments ported; recovery wired per the brief; probe with AbortController + setTimeout (8 s); restart in the full form; Media Session metadata (only when the text changes), playbackState, handlers play/pause/stop.
- antenna/public/assets/app.js: keys bound, loop per Step 3.
- antenna/e2e/serve.mjs: setLive("drop") (destroys the socket), startServer pdtOffsetMs.
- antenna/e2e/smoke.pw.mjs: guard uses context.on("request"), and fails a bare `?`; EXPECTED_STATUS also allows net::ERR_EMPTY_RESPONSE/CONNECTION_RESET/FAILED, which drop and route.abort produce.

## Scenarios
All ten from Step 4, plus: Stop during a probe (session counter); one failed probe after the network returns, next probe's answer restarts at once with the clock held; Media Session play and the forced-refresh gate (refreshTimeline(true) stopped and hidden fetches nothing, the play handler fetches, clock held so no tick can); phone pause is Stop and stays stopped; ENDLIST goes straight to off-air; NotAllowedError shows the notice, AbortError does not.
The 10-minute caps held as written (at most 60 live, at most 4 timeline). They were not widened. The caps test also requires more than 10 live requests, so it cannot pass idle.

## Evidence (no brief step was test-first; the scenarios were written with the code, so there is no RED-before-GREEN)
Mutants in a scratch copy, one test per mutant, expected red named first:
RED: drop the session check (Stop during a probe); tick after stop (Stop during a retry delay); teardown on probe, restart on unreachable (unreachable during a stall); a failed probe ends recovery (one probe failing); wall-clock title (follows the playback position); `/timeline.json?` from the page (guard); popup with a query (guard).
Survived the first pass, then tests tightened, then RED: no tick on a verdict; refreshTimeline(true) before start(); a `playing` event setting playing (a synthetic `playing` event is dispatched during the stall).
Real bugs found by tests during the work: none in player.js. Fixes were test timing: a phone pause just after the join (see concern 3), request snapshot taken before the stopped state, too short a window for two probes.

## Self-review and concerns
1. stop() is a no-op when no session is on: otherwise Stop on the off-air notice replaces it with "<artist> is on the air" and hides Try again. Beyond the brief's letter; one line.
2. selfTeardown is held by a 500 ms timer, not until a `pause` arrives. audio.load() removes queued media-element events, so the pause usually never fires and waiting for it would stick. 500 ms is a judgement, unmeasured on an iPhone. A real phone pause inside that window after a Play or restart is read as ours.
3. A pause within about a second of joining can land while `waiting` or a frozen sample still reads as stalled, so pauseMeansStop ignores it and recovery may restart audio 15+ s later. Follows the module's rule; seen in Chrome when the test paused at once. The test now waits for the hubs.
4. Pressing Play during an outage tears down at once: start() always rejoins, per "Play" = Stop then Play. It is the listener's own press, but offline on an iPhone it is the teardown the probe warns about. Left as is: tell me if Play should be ignored while reconnecting.
5. EXPECTED_STATUS is global, so a stray net error in any test no longer fails the console check. The request guard still sees the URL.
Also: the real-time stall scenario takes 1.1 min, because the restart right after the 404 fails and the next one waits out join + delay. The hidden, locked and native paths are unverified here; D5 is assumed nothing about.

## Fix round 1 (f8e021cc)
Changed:
- player.js: the old start() is rejoin(), which also clears #hubs turning. The new start() (key, #retry, Media Session play, with refreshTimeline(true) after it) rejoins at once when not wanted; while wanted it asks, and any HTTP answer, off-air included, rejoins; no answer does nothing. Stop drops the ask (session counter); a second press in flight adds nothing (asking holds the session, so a stale ask cannot block a new session). ask() is the shared fetch, used by probe() too. No Recovery change.
- tearDown comment rewritten: it was untrue after this change, and already untrue of Stop.
- Spec: one sentence after "Play always joins live".
- Smoke: Play during a dropout (key and Media Session, src untouched, audio still moving, probe sent); Play during a stall rejoins at once with the clock held; an off-air answer rejoins and the hubs stop with no tick; Stop during the ask with a double press; never-settling play() (no notice, no hubs, Reconnecting, synthetic pause stays on, real play() then gives playing); ENDLIST then Stop keeps the notice.
Tests: cd antenna && npm test: 515 passed. npm run smoke: 36 passed (2.9 min). Frozen files and antenna/src unchanged.
Mutants, expected red named first, scratch copy, all RED: immediate-teardown, rejoin-on-unreachable, handler-skips-ask (Play during a dropout); ask-ignores-stop, no-inflight-guard (Stop during Play's question); offair-answer-no-rejoin, hubs-not-cleared (off-air answer); stuck-play-reads-playing, pause-ignores-stall (never settles); stop-off-session (ENDLIST).

## Production change needed, not made (coordinator's instruction)
The synthetic pause passes only at a chosen moment. After a restart a `pause` reads as Stop in a window. Measured on the never-settling stub, mocked clock, pause k seconds after Reconnecting: k=0 stays on (the 500 ms hold, not the stall), k=1 STOPPED (src gone, "On Air Band is on the air"), k=2, 3, 4, 8 stay on. Cause: recovery.restarted() clears samples, so frozen is false at the baseline sample and at a jump sample, and pauseMeansStop sees no stall until the next frozen sample. At the iPhone's 6 s tick the window is up to about 6-12 s after every restart, and restarts recur every 30-60 s in a stuck play(), so iOS's own pause (measured 51.9 s after a stuck play) can land in it. Result: a session the listener wanted ends as Stop, with no recovery. The same applies to the first samples after a start. The scenario dispatches at k=3 and its comment says why, so it pins the stall rule, not this window. A fix would likely treat a pending join (joinUntilMs) as a stall for pauseMeansStop; that would also swallow a real Bluetooth pause in the join window, so it is a ruling for you.

## Fix round 2 (826f3e42)
Changed: recovery.js gains the getter `joining` (joinUntilMs !== null). player.js's pause listener passes stalled: recovery.stalled || recovery.joining. test/recovery.test.ts gains the getter test (false after begin, true after restarted, true once the join expired and failed, false after an advance). The never-settling scenario dispatches the pause at k=1, and its comment says only joining keeps it from being a Stop.
Tests: cd antenna && npm test: 516 passed. npm run smoke: 36 passed (2.9 min). Frozen files and antenna/src unchanged.
Mutants, scratch copy, expected red named first: player.js without `|| recovery.joining`, never-settling scenario RED (Expected "Reconnecting…", Received "On Air Band is on the air. Press Play."), unmutated control green. Getter also false once retryAtMs is set, unit test RED.
