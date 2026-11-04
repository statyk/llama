Status: DONE_WITH_CONCERNS
Commit: 4acdf0ad antenna: probe waits for the network before restarting
Tests: cd antenna && npm test: 24 files, 460 passed. Chromium scenarios: 72 of 72 checks across 12 scenarios (over two runs; see below). Nothing iOS is tested.
Concerns: 4 below, all in how the probe's log reads; none block the phone test.
Handback: /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/sdd/player/t1b-impl/handback.md

## Implemented
Only antenna/public/assets/preview/probe.js and probe.html changed.
- New buttons #wait ("Wait then restart: off" / "ON (press to end)") and #waitform ("Restart form: full" / "gentle"; persists nothing).
- All wait logic runs from the existing interval tick, through waitTick(). No new timer except the 8 s AbortController setTimeout.
- begin() split into begin() + playLogged() so gentle shares the play logging. Existing line formats are unchanged. Full reuses restart(label).
- Mutual exclusion both ways, logged. Stop and Pause only turn both off; Pause only now also stops the retry loop, as ruled.

Log lines:
- wait: stall stuck=Ns <state>
- wait: fetch N start stuck=Ns <state>
- wait: fetch N status=200 ms=N <state>
- wait: fetch N FAILED <name>: <message> ms=N <state>
- wait: fetch N no restart: position moved <state>
- wait: restart N form=full|gentle stuck=Ns <state>
- wait: restart N form=F stuck=Ns vis=V: play() called | resolved <state> | REJECTED ... <state>
- wait: RECOVERED after restart N form=F in=Ns <state>
- wait: recovered alone <state>
- wait: no more restarts (2 made), watching only <state>   (logged once; fetching also stops)
- wait: off
- button Wait then restart on form=F wanted=B
- button Restart form F
<state> carries net= and vis=. navigator.onLine is logged, never gated on.

## Decisions the brief left open
1. RECOVERED needs a real advance: ct must rise by at least 1 s between two interval ticks, and by no more than the wall clock allows plus 2 s. The first tick after a restart only takes a reading, so RECOVERED lands up to two ticks after the restart (in=10s in Chromium, about 12 s on iPhone).
   Why: test 2 reads ct=163.71 after 123 s of play, so iOS starts the position at about 41, not 0. A plain ct>before would log a false RECOVERED on that jump alone. The inference that iOS jumps to 41 is from that one log line; no iPhone restart has been observed.
2. A response is re-checked when it arrives, up to 8 s after the tick that asked. If the stall is over or ct moved, it logs "no restart: position moved". The brief says no restart while advancing.
3. The second restart's 30 s runs from the later of the first restart and the last position change. The tick lines' stuck= still reads the whole dropout, as before.
4. Stop or Pause aborts a fetch in flight.
5. After "no more restarts" no further fetches run; the brief only required restarting nothing.

## Tests
Scratch server and harness: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-player/bb0670bb-11d6-4946-8914-23ea4ad6e0f1/scratchpad/t1b/harness.mjs. Per-scenario logs are next to it and under base/. Run with: cd /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-player/bb0670bb-11d6-4946-8914-23ea4ad6e0f1/scratchpad/t1b && node harness.mjs [scenario...]
Browser: Playwright driving chromium_headless_shell-1217 by executablePath. The repo's Playwright wants build 1248, which is not installed. The smoke config uses system Chrome instead.

Stand-in stream: a WAV the server can starve and release, so stalls are real (event waiting, rs=2, ct held at 7.71) and nothing is mocked in the page. fetch() is real too: the server scripts each answer (socket destroyed, hung, 503, delayed 200, 200). The one real offline case uses context.setOffline.
One shim, needed because Chromium sends any *.m3u8 src to its HLS path whatever the bytes: the harness's src setter points the element at /stream.wav. fetch still goes to /live.m3u8. The shim also records play/pause/load/src/removeAttribute calls.
Ticks ran at 5 s in Chromium, not iOS's 6 s.

Results by requirement:
- No fetch before 30 s stuck: first fetch line at stuck=30s. Failed fetches: destroyed socket and hang (AbortError at ms=8003) left ct, src and the element call list unchanged.
- First HTTP response restarts once: full gives src=,play,pause,removeAttribute(src),load,src=,play. Gentle with a 503 gives src=,play,load,play, src attribute kept, no teardown line.
- Second restart, both forms: comes after 30 s more stuck, a failed fetch restarts nothing, then a further success restarts.
- No third restart: "no more restarts" logged once, 40 s more with no fetch and no element call, ticks continuing.
- RECOVERED on advance, for restarts 1 and 2 and both forms. After it the count resets: the next stall restarts from 1.
- recovered alone: no RECOVERED, no restart, no further fetch.
- Stop mid-fetch: aborts, wait off, no fetch or restart in 36 s, stays off after a new Start. Pause turns both off. Retry and Wait exclude each other, logged.
- While advancing: 50 s with 0 fetches and the element untouched. Response arriving after the position moved: no restart.
- Not wanted: 40 s, nothing happens.
- Real offline: two fetches FAILED TypeError, nothing touched; online again gives status=200, restart, RECOVERED.
- fetch options: url /live.m3u8, cache no-store, signal present, read at the page's fetch call. One fetch at a time (server saw concurrency 1). Cadence at least 15 s.
- 390 px: no horizontal scroll, buttons full width (screenshot /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-player/bb0670bb-11d6-4946-8914-23ea4ad6e0f1/scratchpad/t1b/phone-390.png).

Run history, stated plainly: the full run was 69 of 70. The failure was my harness assuming a cache-control header, which Chromium does not send for no-store. I replaced that check with reading the fetch options, added the jump scenario, and re-ran only full and jump (14 of 14). The other 10 scenarios were not re-run, and probe.js did not change between runs.

Mutants, in scratch copies only (since deleted), predictions written to the log before running:
- m1, no wall-clock bound: predicted jump fails on "not RECOVERED". It failed there.
- m2, no moved check on response: predicted moved_in_flight fails. It failed there.
Only these two were mutated.

npm test: 24 files, 460 passed. Bans and pages are included.

Not tested: anything iOS. That covers locked behaviour, whether a locked page may restart audio, native HLS, and what load() does on iOS. This is the question the probe exists to ask.

## Self-review
Read the full diff. Nothing beyond the brief except the extra button-line field wanted=B and the stall line. No styling. deploy-assets.mjs and the page untouched. No deploy script run.

## Concerns
1. A restart the probe did not make can read as recovered alone: Start or a lock-screen play during a stall calls begin(), and a later advance logs "wait: recovered alone". The line just above (button Start or media session action play) shows it. Read those lines before believing recovered alone. Left as is to avoid more state.
2. A paused element counts as stuck. If iOS pauses the element itself (a phone call, say) wanted stays true, so after 30 s and a good fetch Wait restarts it. The rulings gate only on wanted. Test 2 showed no pause in a dropout, so this should not affect that test, but an interruption during a test would read as a restart.
3. If iOS never fires the 8 s abort timer, the at-most-one-fetch rule stops all further fetches for that stall. It would show as a fetch N start line with no result line. Timers did run through the locked stall, so unlikely.
4. With 6 s ticks on iPhone, the fetch spacing will be 18 s rather than 15 s, as ruled.

## Fix report, round 1
Commit: 663ce530 antenna: probe log can't credit a manual or unlocked restart. Only probe.js changed.

Changes:
- Important 1: waitManual(label), called only from the Start click and the media-session play handler, and only when Wait is on and the page already wants audio (so the first Start is not manual). It logs `wait: manual restart <label> <state>`, aborts a fetch in flight, ends the stall (attempts reset), sets the manual flag, waitRestartAt=now and waitCt=null. The advance logs `wait: recovered after manual restart <state>`. waitRestart does not go through it. If the manual restart also stays stuck, Wait starts a new stall 30 s later and may make restart 1 and 2 again; a RECOVERED then is the script's.
- Important 2: visibilityState saved at restart. Line: `wait: RECOVERED after restart N form=F restart_vis=V in=Ns <state>`.
- Minor 1: in the tick, a fetch older than twice the timeout logs `wait: fetch hung <state>`, is aborted and cleared; the next fetch goes on the same tick. Addition the fix needs: a late settle of the abandoned fetch cannot restart (signal.aborted check) or clear its replacement (done() compares the controller).
- Minor 2: Math.abs(audio.currentTime - waitCt) >= WAIT_MIN_PLAYED_S.

Tests: all 20 scenarios on the final probe.js: 91 of 92 checks. The one failure was the harness: `full` measured the 15 s cadence at server arrival and got 14999 ms, while the page's own lines are exactly 15.000 s apart. I gave that check a 50 ms tolerance and re-ran `full` only: 12 of 12. probe.js did not change after that run.
New scenarios: manual_after_fail, manual_after_giveup, manual_session, manual_loading (not torn down: no fetch or element call for 25 s, Wait resumes only after 30 s), vis_hidden (restart_vis=hidden with vis=visible), vis_visible (restart 2, restart_vis=visible), never_settles (hung, fetching continues, late answer ignored), jitter.
restart_vis is tested by faking document.visibilityState; never_settles by a fetch wrapper that ignores abort.
Mutants, predictions logged first, all failed where predicted:
- m3 no waitRestartAt in waitManual: manual_loading "gets its 30 s".
- m4 no waitClearStall in waitManual: manual_after_fail, no manual-recovered line.
- m5 restart_vis read live: vis_hidden, read visible.
- m6 no hung check: never_settles, no hung line.
- m7 no aborted check: never_settles, late answer restarted.
- m9 exact compare: jitter, "no restart: position moved".
Not mutated: the done() controller compare.
npm test: 24 files, 460 passed. Nothing iOS is tested.

Finding, not fixed (beyond the ruling): stuckSeconds, the shared stuck clock, treats any rise above its high mark as movement. A wobble bounded around a value is fine, and is what the jitter scenario covers. A position creeping upward by small amounts would keep stuck=0, so Wait never stalls and never fetches. My first jitter scenario hit this through a getter that changed per read. It would show in the log as stuck=0 with a slowly rising ct. Test 2 showed ct exactly fixed at 163.71, so there is no evidence iOS does it.

Earlier concerns: 1 (manual restart read as recovered alone) and 3 (abort never firing) are fixed. 2 (paused element counts as stuck) and 4 stand.
