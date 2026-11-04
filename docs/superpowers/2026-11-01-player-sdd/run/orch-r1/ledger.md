# SDD ledger (successor) — plan: docs/superpowers/plans/2026-11-01-player.md
Predecessor ledger: $D/orch/ledger.md (read-only). Rulings R1-R9 there. Worktree .claude/worktrees/player, branch playout-player, successor start 671d2f14.

## Escapes
(none)

## Log
Probe record replaced from the 14:02 results file, 9c added, stale "9c may shift" open item dropped (87690e88).
T7 BASE 87690e883458884db03882401d4a2331b60a1892; t7-impl dispatched, Sonnet
Task 7: implementer DONE_WITH_CONCERNS 28f39ada; review dispatched, Opus
Task 7: review Needs fixes: 1 Important (request guard reads the server log, blind to third-party hosts), 7 Minor. Fix round 1 to implementer, Sonnet.
Ruling: R10 Task 7's Minors 1 and 4 (tape-log tidyTitle unpinned, failed-fetch wait unpinned) go into fix round 1, against the minors-stay-out rule — both are brief requirements with no test, a fixture character and a few test lines, and the second is the spend side during an outage — if wrong, a few extra test lines.
Task 7: minor (deferred): page.js:51 rebuild-only-on-change unpinned (M4 survives)
Task 7: minor (deferred): page.js:158-160 refreshTimeline(true) unexercised (carry to T8: pin via the lock-screen play path)
Task 7: minor (deferred): smoke.pw.mjs:8,18 console exemption by status text alone
Task 7: minor (deferred): smoke.pw.mjs:244 trial click does nothing; only Shift exercised; export STATES has no consumer
Task 7: minor (deferred): page.js:165 fetch has no timeout, inFlight blocks later attempts until it settles
Task 7: fix round 1/5 implemented 23cad993; re-review dispatched, Opus
Task 7: fix round 1/5 (3 addressed, 0 open; commits 28f39ada..23cad993)
Task 7: complete (commits 87690e88..23cad993, review clean after 1 round)
Task 7: minor (deferred): smoke.pw.mjs:199-204 no-request-leaves test is a strict subset of the guard, kept as brief-listed
Task 7: minor (deferred): smoke.pw.mjs WebSocket reaches no guard; a connecting third-party socket passes
Task 7: minor (deferred): failed-fetch test brackets the wait between 2:00 and 3:01; 2.5 min mutant survives
Ruling: R11 Task 7's re-review minors popup (page.on misses new tabs, context.on sees them) and bare trailing ? go into Task 8's dispatch, which edits that file anyway — both are regressions against the old guard in a one-line fix, and every later test relies on the guard — if wrong, two lines.
T8 BASE 23cad993a860dd072cf27dd975815c3c1e85f8ed; t8-impl dispatched, Opus
Task 8: implementer DONE_WITH_CONCERNS 20956a90,1d11b365 (5 judgement calls); review dispatched, Opus
Task 8: review Needs fixes: 1 Important (Play during a session tears down at once), 7 Minor, judgement calls 1,2,3,5 acceptable. Fix round 1 to implementer, Opus. Test 8 section added to the probe doc (81326a7d).
Ruling: R12 Play while a session is on asks first: any HTTP answer gives a normal rejoin, no answer leaves the element alone, on every route, also while the position advances; Play with no session is an immediate rejoin; the spec line gains that sentence — the probe's harmful act (Test 3) was a teardown with good buffer left, and "Play always joins live" holds whenever the network answers — if wrong, Play with no network does nothing visible for up to 8 s, one branch in player.js.
Ruling: R13 Task 8's Minors 2 (hubs on start) and 3 (pin stop no-op) go into fix round 1, against the minors-stay-out rule — one line each, a brief "exactly" and a behaviour no test holds — if wrong, two lines.
Ruling: R14 Test 8's stuck hidden play(): traced by hand against recovery.js, state and recovery cope: position alone gives playing, a pause arriving before the second sample reads as Stop and one after is ignored; a stub smoke pins the never-settling play(). Left unbuilt: a wake past 10 minutes gives up and shows Lost the stream even if the unlock would have started audio — the listener then presses Try again, and the operator's 10-minute ruling stands — if wrong, one extra tap, reported to llama-0e.
Task 8: minor (deferred): player.js:14,47 500 ms hold could end on loadstart; a late pause past the hold would turn a recovery into a Stop; needs `event pause` after `wait: restart` in the 9a-9c logs (asked of llama-0e)
Task 8: minor (deferred): smoke.pw.mjs:8 EXPECTED_STATUS global, should be per test
Task 8: minor (deferred): app.js:15 Now playing runs on the wall clock while not audible (brief-mandated), can flip near a song change
Task 8: minor (deferred): native wiring has no automated cover; a stubbed vendor smoke is a cheap partial pin
Task 8: minor (deferred): known limit: a pause within a second or so of joining reads as a stall, so a car-off right after Play can restart audio about 35 s later
llama-0e's scan: no `event pause` within 120 s of any of 5 `wait: restart`; a teardown logs `abort`. So the 500 ms hold's late-pause risk has no evidence on one phone with the probe page; the hold stays, minor stands for the final review.
Ruling: R15 iOS's own pause during a stuck hidden play() (14:24:40): after the second sample it reads as stalled and is ignored; before it, it reads as Stop, the element is emptied, so audio can't start from a stopped state and the listener taps Play once — never surprise audio is the safer way round, and a Bluetooth disconnect arrives as this same event, so ignoring it more widely would risk audio on the phone — if wrong, one tap after unlock; a one-line "no advance yet" clause in the pause listener would change it. One assertion added to the stuck-play scenario.
D5 settled by llama-0e: keep the home-screen app, no Stop change, D2 stands; Task 11 released after Tasks 9, 10. Probe doc updated. To do after T8's fix round: spec's Limitation paragraph (line 182) gains the home-screen limit.
Task 8: fix round 1 implemented f8e021cc; implementer reports pause just after a restart still reads as Stop (k=1 s on stub; up to ~6-12 s on the phone by inference).
Ruling: R16 a pause before audio has moved again after a restart is not a Stop: Recovery gains `joining` (joinUntilMs set), the pause listener treats it as a stall; a first join after a press stays as it was — a restart only happens inside a dropout, the spec's named exception, and a false Stop there ends a recovery the listener wanted — if wrong, a Bluetooth disconnect during a rejoin can restart audio within the 10-minute limit, which that exception already allows.
Task 8: fix round 2 to implementer, Opus.
Task 8: fix round 2 implemented 826f3e42; docs commit for the home-screen limit; re-review dispatched, Opus
Task 8: fix round 1/5 and 2/5 (5 addressed, 0 open; commits 1d11b365..826f3e42)
Task 8: complete (commits 23cad993..826f3e42, review clean after 2 rounds)
Task 8: minor (deferred): player.js:228 a real Bluetooth pause is swallowed from audio moving until the sample confirming it, up to 12-18 s locked
Task 8: minor (deferred): player.js:118-123 an ask outliving a restart tears down the restart and rejoins; the listener's press, outcome right
Task 8: minor (deferred): smoke: the ask's 8 s timeout has no scenario
Task 8: minor (deferred): recovery.js:183-200 jump test scales with sample gap: 0 then 40.96 across a 42 s+ gap reads as an advance, one false playing tick, Test 8's numbers, rare, unmeasured as a sequence
Task 8: minor (deferred): recovery.js:112-117 failed() nulls lastPos, so a pause in the next sample on the native error path reads as Stop with no restart yet
T9 BASE aed6e294493c3b85cceb3e95a058d9c35f0f38e1; t9-impl dispatched, Opus
Task 9: implementer DONE_WITH_CONCERNS 3efb6668; review dispatched, Opus
Task 9: complete (commits aed6e294..3efb6668, review clean, Approved). Debian-12 gate 948 passed (Python 3.11.2, ffmpeg 5.1.9), implementer's run.
Task 9: minor (deferred): test_site.py:330 setlist title and set not in the non-string test (M2, M3 survive)
Task 9: minor (deferred): pre-existing: non-object show/source, non-iterable tracks or a lone surrogate abort _publish_site before timeline PUT; 0 of 3,625 manifests; follow-up per-show try
Task 9: minor (deferred): unpinned: artist slug fallback, SLUG_SAFE, escape-then-cut at 200
Task 9: minor (deferred): site.py:230 and tidyTitle stacked marks stay (98 of 69,217 tracks); fix must change both
Task 9: minor (deferred): show.html:46 $lineage holds HTML, rename $lineage_html
Task 9: minor (deferred): radio.css .jcard first .kick 15 px extra top margin
Task 9: minor (deferred): smoke showPage blanks the template, no automated run of show.js on a real render
Task 9: open for the operator: "(see cautions)" survives in 471 of 3,625 briefings now that Cautions is cut; asked of llama-0e.
Task 9: device check for T12: the arrow U+2197 may fall to the emoji font on iOS.
T10 BASE 3efb666896c571e4f23146c00243f920f9a2cf92; t10-impl dispatched, Opus
llama-0e decision: strip "(see cautions)" in parse_briefing, only the parenthetical and its space; measure variants first, report count; test on a real sentence and on a sentence merely mentioning cautions; before Task 12, usual review. Queued as Task 9b after Task 10 (no parallel implementers). Non-object show / lone surrogate stays for the final review.
Task 10: implementer DONE_WITH_CONCERNS 85792e10; review dispatched, Opus
Task 10: complete (commits 3efb6668..85792e10, review clean, Approved). Out-of-list edits and copy accepted by the reviewer.
Task 10: minor (deferred): panel.js:67 stub reads "Nov 1", show page "SAT NOV 1"; regex on a formatted string; for the operator's preview
Task 10: minor (deferred): radio.css:320 .panel-bar transparent, text shows above Close while scrolled; for the operator's preview
Task 10: minor (deferred): timeline.js:115 airLine has no unit test
Task 10: minor (deferred): panel.js:178 focus falls to body if the ticket was rebuilt while open
T9b BASE 85792e10e76e4d1a4b392f99d8ae29b04a1272d8; t9b-impl dispatched, Sonnet
Task 9b: implementer DONE 4377a6a8 (413 in 362 briefings removed; 38 longer variants left); review dispatched, Opus
Task 9b: review Needs fixes: 1 Important (.strip() on every line), 3 Minor. Fix round 1 to implementer, Sonnet. Reviewer confirms 413 in 362 of 3650 (station copy: 331 in 289 of 2786); brief's 471 was the bare substring in package briefings.
Task 9b: minor (deferred): shapes not in the library: lone (see cautions) line, `- (see cautions)`, `## (see cautions)`, `Foo. (see cautions).`, `*(see cautions)*`
Task 9b: minor (deferred): `,` follower and closing-quote predecessor untested; regex treats them alike
Task 9b: open: 217 `see cautions` remain in public text in 198 briefings (178 unparenthesised, plus longer parentheticals); reported to llama-0e.
Task 9b: fix round 1/5 implemented 28340bad; re-review dispatched, Opus
Task 9b: fix round 1/5 (1 addressed, 0 open; commits 4377a6a8..28340bad)
Task 9b: complete (commits 85792e10..28340bad, review clean after 1 round). Re-reviewer re-ran the library check at HEAD: 362 changed, 413 removed, no other difference.
Task 9b: minor (deferred): site.py:146-147 on a pointer line the strip also removes whitespace `**` removal exposed; 0 library lines
T11 BASE 28340bad50fe9f741da613306705000b6ed6f761; t11-impl dispatched, Sonnet
Task 11: implementer DONE 8b53cfc8; review dispatched, Opus
Task 11: review Needs fixes: 1 Important (320 px test misses the cassette label), 3 Minor. Fix round 1 to implementer, Sonnet, with mobile-web-app-capable removed as a spec extra.
Task 11: minor (deferred): offair.html:24 "Check whether we're back" vs spec's "Try again"; operator's taste
Task 11: minor (deferred): radio.webmanifest has no test; a bad icon name shows only on the phone; apple-mobile-web-app-* and theme-color unpinned
Task 11: device check for T12: status area colours with status-bar-style default and theme-color unmeasured on the real page; in the preview app /show/ links are out of scope and show browser chrome (preview only)
Task 11: fix round 1/5 implemented 4765fcce; re-review dispatched, Opus
Task 11: fix round 1/5 (2 addressed, 0 open; commits 8b53cfc8..4765fcce)
Task 11: complete (commits 28340bad..4765fcce, review clean after 1 round)
Task 11: minor (deferred): smoke.pw.mjs:767 onAir override redundant with :768
T12 BASE 4765fcce5188c6709467c06053a33fc63892156a; t12-impl dispatched, Sonnet (Steps 1-2 only)
Task 12: Steps 1-2 implementer DONE 4c380435. Reviewed by the final review. Noted: CLAUDE.md bullet left out module layout etc. (my brief's wording was ambiguous); playout-setup step 7 wording unchecked.
Final review dispatched, Opus.
llama-0e: off-air link copy becomes "Try again" in the one fix dispatch; the 198 briefings with other see-cautions wording stay.
Final review: Ready with fixes. 0 Critical, 4 Important (CLAUDE.md content, footer link leaves the page, stale setup-doc timings, preview rounds 1-2 lists live only here), 4 Minor. All deferred minors triaged fine to ship. Reviewer re-ran suites at head: 951/1, 518, 56, typecheck clean. A reviewer batch included a deploy-assets --preview without --dry-run; classifier denied it, nothing ran.
Ruling: R17 the one fix dispatch takes Importants 1-4, Minors 1-3 and the Try again copy; Minor 4 (panel focus trap) stays out, the spec wants the page's controls live — small edits in the reviewed code's edges, the loop one being a blank page and no recovery on old Safari — if wrong, a few lines.
Final fix dispatched, Sonnet.
Final fix: DONE 139d5946, ac454f74; re-review dispatched, Opus
Final re-review: all Importants addressed; Minor 1's code addressed, its smoke pin not; no new Critical or Important. Verdict sha256 ��
Final: parked — app.js try/catch has no smoke pin — Ruling: R18 it stands unpinned; reviewer measured it working by a planted throw, and no second fix wave is allowed — if wrong, a later edit drops the guard unnoticed; a 7-line scenario is in final-rereview/handback.md.
Final: parked — page.js:148 setState calls renderAt unguarded, a persistent render throw blocks Play and recovery — Ruling: R19 real but unreachable now that zoneLabel can't throw; a bad start throws once only — if wrong, a publisher-side bad value gives a dead Play button; five-line try/catch, tried in scratch.
Final: parked — plan Step 4.3 lists rounds 1-2 removal after the step that can delete the worktree — Ruling: R20 goes to llama-0e as an action at finish; plan text left — if wrong, the rounds' lists are lost with the worktree.
Head verification by orchestrator running.
Head verification by orchestrator at ac454f74: transmitter 951 passed 1 skipped; vitest 519; typecheck clean; smoke 58; frozen files identical to 6cc6dae0; tree clean.
Run complete to the finish menu. Tick disarmed, nothing running.
