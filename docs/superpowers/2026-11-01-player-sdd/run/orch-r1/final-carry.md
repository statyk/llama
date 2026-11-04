# Deferred minors and rulings across the run
Ruling: R10 Task 7's Minors 1 and 4 (tape-log tidyTitle unpinned, failed-fetch wait unpinned) go into fix round 1, against the minors-stay-out rule — both are brief requirements with no test, a fixture character and a few test lines, and the second is the spend side during an outage — if wrong, a few extra test lines.
Task 7: minor (deferred): page.js:51 rebuild-only-on-change unpinned (M4 survives)
Task 7: minor (deferred): page.js:158-160 refreshTimeline(true) unexercised (carry to T8: pin via the lock-screen play path)
Task 7: minor (deferred): smoke.pw.mjs:8,18 console exemption by status text alone
Task 7: minor (deferred): smoke.pw.mjs:244 trial click does nothing; only Shift exercised; export STATES has no consumer
Task 7: minor (deferred): page.js:165 fetch has no timeout, inFlight blocks later attempts until it settles
Task 7: minor (deferred): smoke.pw.mjs:199-204 no-request-leaves test is a strict subset of the guard, kept as brief-listed
Task 7: minor (deferred): smoke.pw.mjs WebSocket reaches no guard; a connecting third-party socket passes
Task 7: minor (deferred): failed-fetch test brackets the wait between 2:00 and 3:01; 2.5 min mutant survives
Ruling: R11 Task 7's re-review minors popup (page.on misses new tabs, context.on sees them) and bare trailing ? go into Task 8's dispatch, which edits that file anyway — both are regressions against the old guard in a one-line fix, and every later test relies on the guard — if wrong, two lines.
Ruling: R12 Play while a session is on asks first: any HTTP answer gives a normal rejoin, no answer leaves the element alone, on every route, also while the position advances; Play with no session is an immediate rejoin; the spec line gains that sentence — the probe's harmful act (Test 3) was a teardown with good buffer left, and "Play always joins live" holds whenever the network answers — if wrong, Play with no network does nothing visible for up to 8 s, one branch in player.js.
Ruling: R13 Task 8's Minors 2 (hubs on start) and 3 (pin stop no-op) go into fix round 1, against the minors-stay-out rule — one line each, a brief "exactly" and a behaviour no test holds — if wrong, two lines.
Ruling: R14 Test 8's stuck hidden play(): traced by hand against recovery.js, state and recovery cope: position alone gives playing, a pause arriving before the second sample reads as Stop and one after is ignored; a stub smoke pins the never-settling play(). Left unbuilt: a wake past 10 minutes gives up and shows Lost the stream even if the unlock would have started audio — the listener then presses Try again, and the operator's 10-minute ruling stands — if wrong, one extra tap, reported to llama-0e.
Task 8: minor (deferred): player.js:14,47 500 ms hold could end on loadstart; a late pause past the hold would turn a recovery into a Stop; needs `event pause` after `wait: restart` in the 9a-9c logs (asked of llama-0e)
Task 8: minor (deferred): smoke.pw.mjs:8 EXPECTED_STATUS global, should be per test
Task 8: minor (deferred): app.js:15 Now playing runs on the wall clock while not audible (brief-mandated), can flip near a song change
Task 8: minor (deferred): native wiring has no automated cover; a stubbed vendor smoke is a cheap partial pin
Task 8: minor (deferred): known limit: a pause within a second or so of joining reads as a stall, so a car-off right after Play can restart audio about 35 s later
Ruling: R15 iOS's own pause during a stuck hidden play() (14:24:40): after the second sample it reads as stalled and is ignored; before it, it reads as Stop, the element is emptied, so audio can't start from a stopped state and the listener taps Play once — never surprise audio is the safer way round, and a Bluetooth disconnect arrives as this same event, so ignoring it more widely would risk audio on the phone — if wrong, one tap after unlock; a one-line "no advance yet" clause in the pause listener would change it. One assertion added to the stuck-play scenario.
Ruling: R16 a pause before audio has moved again after a restart is not a Stop: Recovery gains `joining` (joinUntilMs set), the pause listener treats it as a stall; a first join after a press stays as it was — a restart only happens inside a dropout, the spec's named exception, and a false Stop there ends a recovery the listener wanted — if wrong, a Bluetooth disconnect during a rejoin can restart audio within the 10-minute limit, which that exception already allows.
Task 8: minor (deferred): player.js:228 a real Bluetooth pause is swallowed from audio moving until the sample confirming it, up to 12-18 s locked
Task 8: minor (deferred): player.js:118-123 an ask outliving a restart tears down the restart and rejoins; the listener's press, outcome right
Task 8: minor (deferred): smoke: the ask's 8 s timeout has no scenario
Task 8: minor (deferred): recovery.js:183-200 jump test scales with sample gap: 0 then 40.96 across a 42 s+ gap reads as an advance, one false playing tick, Test 8's numbers, rare, unmeasured as a sequence
Task 8: minor (deferred): recovery.js:112-117 failed() nulls lastPos, so a pause in the next sample on the native error path reads as Stop with no restart yet
Task 9: minor (deferred): test_site.py:330 setlist title and set not in the non-string test (M2, M3 survive)
Task 9: minor (deferred): pre-existing: non-object show/source, non-iterable tracks or a lone surrogate abort _publish_site before timeline PUT; 0 of 3,625 manifests; follow-up per-show try
Task 9: minor (deferred): unpinned: artist slug fallback, SLUG_SAFE, escape-then-cut at 200
Task 9: minor (deferred): site.py:230 and tidyTitle stacked marks stay (98 of 69,217 tracks); fix must change both
Task 9: minor (deferred): show.html:46 $lineage holds HTML, rename $lineage_html
Task 9: minor (deferred): radio.css .jcard first .kick 15 px extra top margin
Task 9: minor (deferred): smoke showPage blanks the template, no automated run of show.js on a real render
Task 9: open for the operator: "(see cautions)" survives in 471 of 3,625 briefings now that Cautions is cut; asked of llama-0e.
Task 9: device check for T12: the arrow U+2197 may fall to the emoji font on iOS.
Task 10: minor (deferred): panel.js:67 stub reads "Nov 1", show page "SAT NOV 1"; regex on a formatted string; for the operator's preview
Task 10: minor (deferred): radio.css:320 .panel-bar transparent, text shows above Close while scrolled; for the operator's preview
Task 10: minor (deferred): timeline.js:115 airLine has no unit test
Task 10: minor (deferred): panel.js:178 focus falls to body if the ticket was rebuilt while open
Task 9b: minor (deferred): shapes not in the library: lone (see cautions) line, `- (see cautions)`, `## (see cautions)`, `Foo. (see cautions).`, `*(see cautions)*`
Task 9b: minor (deferred): `,` follower and closing-quote predecessor untested; regex treats them alike
Task 9b: open: 217 `see cautions` remain in public text in 198 briefings (178 unparenthesised, plus longer parentheticals); reported to llama-0e.
Task 9b: minor (deferred): site.py:146-147 on a pointer line the strip also removes whitespace `**` removal exposed; 0 library lines
Task 11: minor (deferred): offair.html:24 "Check whether we're back" vs spec's "Try again"; operator's taste
Task 11: minor (deferred): radio.webmanifest has no test; a bad icon name shows only on the phone; apple-mobile-web-app-* and theme-color unpinned
Task 11: device check for T12: status area colours with status-bar-style default and theme-color unmeasured on the real page; in the preview app /show/ links are out of scope and show browser chrome (preview only)
Task 11: minor (deferred): smoke.pw.mjs:767 onAir override redundant with :768
Ruling: R1 T1 Step 7's --remove-preview 1 is left to the operator or parent, not run here — the run brief bans wrangler r2 and it needs the operator's .env — if wrong, a preview lingers until they run it, which T12's go-live list would catch only if reminded, so it goes in the gate report.
Ruling: R2 T6 Step 6's frozen-file check diffs against 6cc6dae0, the branch start, not main — main may move during the run and the branch must not depend on it; the files are identical in both today — if wrong, nothing: the same bytes are compared.
Ruling: R3 the probe carries a static apple-mobile-web-app-capable meta tag alongside the inserted manifest link — test 8 needs a real standalone launch and an inserted link might be missed by iOS — if wrong, one harmless tag in a throwaway page.
Task 1: minor (deferred): deploy-assets.mjs:20,181 an unrecognised argument falls through to a live upload
Task 1: minor (deferred): probe.js:66-72 stuck=0 on a thaw line; read LATE STALL and played vs gap instead
Task 1: minor (deferred): probe.js:225-229 Pause only leaves the retry loop running
Task 1: minor (deferred): probe.js:250,275 comment overstates the copy fallback
Task 1: minor (deferred): probe.js:194 log-only handlers may leave Pause inaudible (plan-mandated, operator told)
Task 1: minor (deferred): deploy-assets.mjs:173 --remove-preview has no assets/preview/<n>/ prefix guard
Ruling: R4 Task 1's minors 1 and 6 are carried into Task 12, which edits deploy-assets.mjs anyway, not fixed before the gate — minors stay out of the loop, and the operator gets the exact command with a warning — if wrong, a mistyped flag re-uploads today's five live assets, whose content is unchanged. Probe minors die with the probe; 2, 3 and 5 are covered in the operator instructions.
Task 2: minor (deferred): test_site.py:184-216 no test of mid-section transitions (text then bullet, two paragraphs, text then ##); behaved correctly by hand
Task 2: minor (deferred): site.py:148-156 inline re-implementation of flush()
Task 2: minor (deferred): site.py:141 a # line does not end a paragraph; unreachable from brief.py
Task 2: minor (deferred): site.py:152-157 wrapped bullet and ### stay raw; not emitted by brief.py's template
Task 3: minor (deferred): timeline.js:114-119 longGeneric fallback dead on engines that throw RangeError; UTC renders GMT+00:00
Task 3: minor (deferred): timeline.js:109 airTime(null) throws; robustness test omits airTime, tidyTitle, clipLabel, hrefs
Task 3: minor (deferred): timeline.js:126 showHref(null) gives /show/null.html
Task 3: minor (deferred): timeline.js:50 nowLine on a parenthetical-only clip gives ""
Task 3: minor (deferred): timeline.js:39 tidyTitle "A>>" and bare ">"
Task 3: minor (deferred): timeline.js:22-34 findShow duplicates frozen nowplaying.js loop
Task 3: minor (deferred): Step 2 RED run skipped
Task 3: minor (deferred): timeline.js:71 redundant break
Ruling: R5 Task 7's tape log renders each entry through tidyTitle, and Task 8's playbackMs returns a finite number or null, as old player.js:110 does — spec line 264 requires " >" in the log, and the plan names no caller; positionMs passes NaN through — if wrong, nothing: both are the spec's behaviour. Carried into those dispatches.
Ruling: R6 album is venue and concert date only, no city — the spec's literal text, and the car display's room is short — if wrong, one line in media.js.
Task 5: minor (deferred): notes.js:40-41 model has where and date, no raw venue/city; Task 10 uses model.where and model.date (carry to T10 dispatch)
Task 5: minor (deferred): notes.js:24-25 null-entry guard inconsistent; unreachable from publisher
Task 5: minor (deferred): notes.js:25 set passes through unnormalized; Task 10 must not print null (carry to T10 dispatch)
Task 5: minor (deferred): timeline.js nowLine via media.js:12, parenthetical-only clip gives blank title
Task 5: minor (deferred): media.js:4 root-absolute artwork is absent in preview until deploy-assets runs (plan-mandated; spec's deploy order runs assets first)
Task 5: minor (deferred): test/media.test.ts:26 stray space
Ruling: R7 "ON THE AIR" gets id label-status, and Task 7's setState hides it in the offair state only; the art is not re-run — the spec says the cassette says what is happening, and the art is only seen while on the air — if wrong, a hidden word and one line.
Task 6: minor (deferred): radio.css:253 .sr misnames a visible element (Task 7 writes it)
Task 6: minor (deferred): radio.css:248,265 ::after text joins the link's accessible name
Task 6: minor (deferred): radio.css:382 .meta b loses emphasis, .tag has no equivalent (carry to T9 dispatch)
Task 6: minor (deferred): playwright.config.mjs:7 outputDir in the SDD scratch folder wipes shots/
Task 6: minor (deferred): index.html:40,56 empty Tape log and Just aired headings (carry to T7 dispatch: hide a section with an empty list)
Task 6: minor (deferred): handback's 3-columns claim slightly wrong; npm audit not investigated
Task 6: minor (deferred): look polish: torn tickets truncate hard at 320, stream URL breaks at its hyphen, notches overpaint focus ring
Ruling: R8 follow-up minors 1 (hung fetch recovered by the tick) and 2 (position compared with the movement threshold, not float equality) go into this fix round, against the minors-stay-out rule — the probe gets one real run per 15 minutes of the operator's time, and either failure silently ends the test — if wrong, a few lines in a throwaway file.
Task 1 follow-up: minor (deferred): probe.js:69-76 stuck= restarts from the position jump; clock times still give the span
Task 1 follow-up: minor (deferred): a paused element counts as stuck, as ruled; restart line shows paused=true
Task 1 follow-up: minor (deferred): waitManualRestart survives into the next stall; probe-only
Task 1 follow-up: minor (deferred): tolerance reopens a sub-1 s window at probe.js:278, mandated by R8; probe-only
Task 1 follow-up: minor (deferred): stuckSeconds treats an upward creep as movement; no iOS evidence
Ruling: R9 Recovery design under those rulings: a failure starts the delay, the probe comes when the delay runs out, a restart needs a reachable verdict younger than verdictFreshMs (10 s), player runs tick at once on a verdict, and a rise above wall clock + 2 s is a jump, not an advance — keeps a stale answer from tearing down offline, and the 41 s position jump from reading as recovery — if wrong, constants in one module.
Task 4: minor (deferred): recovery.js:173-189 pre-load sample then a long freeze reads as audio; a fix needs a brief-level decision (test tick(900, 3_600_000) pins the bound)
Task 4: minor (deferred): recovery.test.ts:384-385 time runs backwards
Task 4: minor (deferred): recovery.js:176 jump computed from null lastSampleMs
Task 4: minor (deferred): recovery.js:115,183-185 an error's baseline clears frozen during a stall; a pause in that sample reads as Stop; not reachable on the evidence; one-line close: this.waiting = true beside :115
Task 4: minor (deferred): recovery.js:110-111 comment wording
- Final review gets every "minor (deferred)" line above.
