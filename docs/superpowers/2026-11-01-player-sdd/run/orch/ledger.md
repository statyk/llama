# SDD ledger — plan: docs/superpowers/plans/2026-11-01-player.md
Worktree .claude/worktrees/player, branch playout-player, start 6cc6dae0. Spec docs/superpowers/specs/2026-11-01-player-design.md. Review mode Opus.

## Preflight scan
Task pairs sharing a file or interface:
| Pair | Produced vs consumed | Found |
|---|---|---|
| T1/T11/T12 deploy-assets | T1 --preview rewrites radio.webmanifest once it exists; T11 creates it; T12 removes probe manifest code | consistent |
| T1 decisions/T4,7,8,11 | D1-D6 feed pause rule, ticks, session, home screen | gated by GATE 1 and 2 |
| T2/T9/T10 sections | parse_briefing shape; archive_link; template and panel render it | consistent; build_notes signature and META verified in site.py/test_site.py |
| T3/T5/T7/T8/T9/T10 timeline.js | helper list matches every consumer's list | consistent |
| T4/T8 recovery | Interfaces listed match T8 use; prefersNativeHls, classifyProbe, playBlockedNotice, hlsErrorNotice exist in nowplaying.js | consistent |
| T5/T8/T10 media.js, notes.js | sessionText, ARTWORK; panelModel, setlistLine, groupSets | consistent |
| T6/T7-T11 ids and harness | ids, startServer, makeTimeline | consistent |
| T7/T8/T10 page.js exports | renderAt, refreshTimeline, currentTimeline, setState, ticketLinks | consistent |
| T7/T9/T10 hostile.json | created T7, read by pytest T9 and smoke T10 | consistent; repo mounted whole in debian script |
| T6/T11 index.html, indexpage.test | T6 swaps player.js for assets/app.js; T11 adds tests. Existing OFFAIR tests stay valid | consistent |
Task self-consistency:
| Task | Found |
|---|---|
| T1 | Step 7 --remove-preview conflicts with the run's no-production rule: R1. Probe lacks a static standalone marker: R3 |
| T2 | tests match implementation text |
| T3 | date and zone cases checked by hand: 2026-11-01 DST end, Sunday; consistent |
| T4 | test timings traced against stated semantics; consistent |
| T5 | consistent |
| T6 | Step 6 diffs against moving main: R2. *.aac ignored at .gitignore:15; Chrome and ffmpeg present |
| T7 | consistent; tsconfig has vite/client types, so import.meta.glob typechecks |
| T8 | 10-minute request caps may be tight with hls.js's own retries: left to the task, a failure stops and reports |
| T9 | Debian-12 gate needs docker, currently down: reported at T9. render_show_page signature kept. 2008-11-01 is a Saturday |
| T10 | consistent |
| T11 | consistent |
| T12 | Steps 4-6 are operator's and parent's, per brief |
Ruling: R1 T1 Step 7's --remove-preview 1 is left to the operator or parent, not run here — the run brief bans wrangler r2 and it needs the operator's .env — if wrong, a preview lingers until they run it, which T12's go-live list would catch only if reminded, so it goes in the gate report.
Ruling: R2 T6 Step 6's frozen-file check diffs against 6cc6dae0, the branch start, not main — main may move during the run and the branch must not depend on it; the files are identical in both today — if wrong, nothing: the same bytes are compared.
Ruling: R3 the probe carries a static apple-mobile-web-app-capable meta tag alongside the inserted manifest link — test 8 needs a real standalone launch and an inserted link might be missed by iOS — if wrong, one harmless tag in a throwaway page.

## Escapes
(none)

## Log

T1 BASE 6cc6dae01fbff5c8d0a936d76f87d91af1bf8d07; t1-impl dispatched, Opus
Task 1: implementer DONE_WITH_CONCERNS 745c106c; review dispatched, Opus
Task 1: Steps 1-5 complete (commits 6cc6dae..745c106, review clean, Approved by Opus reviewer). Steps 6-7 await the operator.
Task 1: minor (deferred): deploy-assets.mjs:20,181 an unrecognised argument falls through to a live upload
Task 1: minor (deferred): probe.js:66-72 stuck=0 on a thaw line; read LATE STALL and played vs gap instead
Task 1: minor (deferred): probe.js:225-229 Pause only leaves the retry loop running
Task 1: minor (deferred): probe.js:250,275 comment overstates the copy fallback
Task 1: minor (deferred): probe.js:194 log-only handlers may leave Pause inaudible (plan-mandated, operator told)
Task 1: minor (deferred): deploy-assets.mjs:173 --remove-preview has no assets/preview/<n>/ prefix guard
Ruling: R4 Task 1's minors 1 and 6 are carried into Task 12, which edits deploy-assets.mjs anyway, not fixed before the gate — minors stay out of the loop, and the operator gets the exact command with a warning — if wrong, a mistyped flag re-uploads today's five live assets, whose content is unchanged. Probe minors die with the probe; 2, 3 and 5 are covered in the operator instructions.
Go received for T2,3,5,6; R4 accepted. T2 BASE 745c106c; t2-impl dispatched, Sonnet
Task 2: implementer DONE 76beab7; review dispatched, Opus
Task 2: complete (commits 745c106..76beab7, review clean, Approved)
Task 2: minor (deferred): test_site.py:184-216 no test of mid-section transitions (text then bullet, two paragraphs, text then ##); behaved correctly by hand
Task 2: minor (deferred): site.py:148-156 inline re-implementation of flush()
Task 2: minor (deferred): site.py:141 a # line does not end a paragraph; unreachable from brief.py
Task 2: minor (deferred): site.py:152-157 wrapped bullet and ### stay raw; not emitted by brief.py's template
T3 BASE 76beab71; t3-impl dispatched, Sonnet
Task 3: implementer DONE d77fa88 (no RED run captured, per its report); review dispatched, Opus
Task 3: review Needs fixes: 1 Important (vacuous recent test), 8 Minor. Fix round 1 to implementer, Sonnet.
Task 3: minor (deferred): timeline.js:114-119 longGeneric fallback dead on engines that throw RangeError; UTC renders GMT+00:00
Task 3: minor (deferred): timeline.js:109 airTime(null) throws; robustness test omits airTime, tidyTitle, clipLabel, hrefs
Task 3: minor (deferred): timeline.js:126 showHref(null) gives /show/null.html
Task 3: minor (deferred): timeline.js:50 nowLine on a parenthetical-only clip gives ""
Task 3: minor (deferred): timeline.js:39 tidyTitle "A>>" and bare ">"
Task 3: minor (deferred): timeline.js:22-34 findShow duplicates frozen nowplaying.js loop
Task 3: minor (deferred): Step 2 RED run skipped
Task 3: minor (deferred): timeline.js:71 redundant break
Ruling: R5 Task 7's tape log renders each entry through tidyTitle, and Task 8's playbackMs returns a finite number or null, as old player.js:110 does — spec line 264 requires " >" in the log, and the plan names no caller; positionMs passes NaN through — if wrong, nothing: both are the spec's behaviour. Carried into those dispatches.
Task 3: fix round 1/5 (1 addressed, 0 open; commits d77fa88..03e513f; suite re-run by orch: 445 passed, tsc clean)
Task 3: complete (commits 76beab7..03e513f, review clean after 1 round)
T5 BASE 03e513f7; t5-impl dispatched, Sonnet (T4 parked at gate)
Task 5: implementer DONE 96dc8b1; review dispatched, Opus
Task 5: review Needs fixes: 2 Important (panelModel no airtimes; album carries city), 6 Minor. Fix round 1 to implementer, Sonnet.
Ruling: R6 album is venue and concert date only, no city — the spec's literal text, and the car display's room is short — if wrong, one line in media.js.
Task 5: minor (deferred): notes.js:40-41 model has where and date, no raw venue/city; Task 10 uses model.where and model.date (carry to T10 dispatch)
Task 5: minor (deferred): notes.js:24-25 null-entry guard inconsistent; unreachable from publisher
Task 5: minor (deferred): notes.js:25 set passes through unnormalized; Task 10 must not print null (carry to T10 dispatch)
Task 5: minor (deferred): timeline.js nowLine via media.js:12, parenthetical-only clip gives blank title
Task 5: minor (deferred): media.js:4 root-absolute artwork is absent in preview until deploy-assets runs (plan-mandated; spec's deploy order runs assets first)
Task 5: minor (deferred): test/media.test.ts:26 stray space
Task 5: fix round 1/5 (2 addressed, 0 open; commits 96dc8b1..1fa89c8)
Task 5: complete (commits 03e513f..1fa89c8, review clean after 1 round)
T6 BASE 1fa89c84; t6-impl dispatched, Opus
Task 6: implementer DONE_WITH_CONCERNS 6cab53a; review dispatched, Opus
Task 6: review Needs fixes: 3 Important (ON THE AIR has no hook; wide panel loses safe-area; torn tickets lose focus ring), 7 Minor, Look approved. Fix round 1 to implementer, Opus.
Ruling: R7 "ON THE AIR" gets id label-status, and Task 7's setState hides it in the offair state only; the art is not re-run — the spec says the cassette says what is happening, and the art is only seen while on the air — if wrong, a hidden word and one line.
Task 6: minor (deferred): radio.css:253 .sr misnames a visible element (Task 7 writes it)
Task 6: minor (deferred): radio.css:248,265 ::after text joins the link's accessible name
Task 6: minor (deferred): radio.css:382 .meta b loses emphasis, .tag has no equivalent (carry to T9 dispatch)
Task 6: minor (deferred): playwright.config.mjs:7 outputDir in the SDD scratch folder wipes shots/
Task 6: minor (deferred): index.html:40,56 empty Tape log and Just aired headings (carry to T7 dispatch: hide a section with an empty list)
Task 6: minor (deferred): handback's 3-columns claim slightly wrong; npm audit not investigated
Task 6: minor (deferred): look polish: torn tickets truncate hard at 320, stream URL breaks at its hyphen, notches overpaint focus ring
Carry to T9: class list in t6-impl/handback.md. Carry to T7: ticket markup in t6-impl/handback.md.
Task 6: fix round 1/5 (3 addressed, 0 open; commits 6cab53a..439ad0c)
Task 6: complete (commits 1fa89c8..439ad0c, review clean after 1 round)
Carry to T7: brief must name #label-status (R7); nothing pins it yet; pin in a smoke scenario.
Parked at gate: T4, T7, T8, T11 await D1-D6; T9, T10 need T7's hostile.json and ticketLinks.
Task 1 follow-up: llama-0e sent Safari results; test 3 never tested D6. BASE 439ad0c. t1b-impl dispatched, Opus (Wait then restart, restart form toggle, test 9).
Task 1 follow-up: implementer DONE_WITH_CONCERNS 4acdf0a; operator doc gained test 9; review dispatched, Opus
Task 1 follow-up: review Needs fixes: 2 Important (operator's own restart logs RECOVERED; RECOVERED doesn't show the restart was locked), 4 Minor. Fix round 1 to implementer, Opus. Operator sheet updated to match.
Ruling: R8 follow-up minors 1 (hung fetch recovered by the tick) and 2 (position compared with the movement threshold, not float equality) go into this fix round, against the minors-stay-out rule — the probe gets one real run per 15 minutes of the operator's time, and either failure silently ends the test — if wrong, a few lines in a throwaway file.
Task 1 follow-up: minor (deferred): probe.js:69-76 stuck= restarts from the position jump; clock times still give the span
Task 1 follow-up: minor (deferred): a paused element counts as stuck, as ruled; restart line shows paused=true
Task 1 follow-up: fix round 1/5 (4 addressed, 0 open; commits 4acdf0a..663ce53). Operator sheet REJECTED wording corrected.
Task 1 follow-up: minor (deferred): waitManualRestart survives into the next stall; probe-only
Task 1 follow-up: minor (deferred): tolerance reopens a sub-1 s window at probe.js:278, mandated by R8; probe-only
Task 1 follow-up: minor (deferred): stuckSeconds treats an upward creep as movement; no iOS evidence
Task 1 follow-up: complete (commits 439ad0c..663ce53, review clean after 1 round). Stopped: test 9 pending.
Go for T4,7,8,9,10; hold T11 for D5. Amending spec and plan per llama-0e's rulings.
Spec and plan amended per llama-0e's rulings (commit b7e48066): reachable/unreachable verdicts, probe after delay, freshness, advancing getter, D2 D3 branches dropped.
Ruling: R9 Recovery design under those rulings: a failure starts the delay, the probe comes when the delay runs out, a restart needs a reachable verdict younger than verdictFreshMs (10 s), player runs tick at once on a verdict, and a rise above wall clock + 2 s is a jump, not an advance — keeps a stale answer from tearing down offline, and the 41 s position jump from reading as recovery — if wrong, constants in one module.
T4 BASE b7e48066; t4-impl dispatched, Opus
RELAY-NOW received 2026-11-01 13:23:50: finish T4 through review, then HANDOFF, start no new task
Task 4: implementer DONE_WITH_CONCERNS 6b73ea6, 676b9a4; review dispatched, Opus
Task 4: review Needs fixes: 1 Important (failed() cancelled by the next sample), 3 Minor. Journeys (a) (b) (c) all hold. Fix round 1 to implementer, Opus.
Task 4: minor (deferred): recovery.js:173-189 pre-load sample then a long freeze reads as audio; a fix needs a brief-level decision (test tick(900, 3_600_000) pins the bound)
Task 4: minor (deferred): recovery.test.ts:384-385 time runs backwards
Task 4: minor (deferred): recovery.js:176 jump computed from null lastSampleMs
Carry to T8: never call tick after Stop; drop a verdict from a cancelled session (session counter); tick and mayPlay use Date.now(), not performance.now(); smoke proves Review Focus 5.
Task 4: fix round 1/5 (1 addressed, 0 open; commits 676b9a4..671d2f1)
Task 4: complete (commits b7e4806..671d2f1, review clean after 1 round)
Task 4: minor (deferred): recovery.js:115,183-185 an error's baseline clears frozen during a stall; a pause in that sample reads as Stop; not reachable on the evidence; one-line close: this.waiting = true beside :115
Task 4: minor (deferred): recovery.js:110-111 comment wording

## HANDOFF
Written 2026-11-01 13:41:08 EST on RELAY-NOW. Head 671d2f14, tree clean, branch playout-player. Successor is the next orchestrator for this worktree; dir, ledger format and D as in this file.

Done and reviewed: Task 1 Steps 1-5 plus follow-up; Task 1 Step 7 record (docs/superpowers/2026-11-01-player-probe.md); Tasks 2, 3, 4, 5, 6. Spec and plan amended at b7e48066.
Next, in order: Task 7, Task 8, Task 9, Task 10. Task 11 is HELD for D5 (home-screen run) from llama-0e. Then Task 12 Steps 1-2, final whole-branch review on Opus, finish menu. Task 12 Steps 4-6 are the operator's and llama-0e's.
Open from llama-0e: D5; 9c may shift a constant (giveUpMs is the likely one).
The two preview rounds need --remove-preview, by the operator, from the worktree's antenna/ (.preview-1.json; round 2's list if uploaded here).

Workspace: briefs and review packages in .superpowers/sdd/2026-11-01-player/ (scripts/task-brief, scripts/review-package from the skill). orch/implementer-rules.md, orch/reviewer-rubric.md, orch/rereview-rubric.md, orch/global-constraints.md are reusable; hand them by path, and put mandates 1-5 verbatim in each dispatch. Implementer models per the plan's lines: T7 Sonnet, T8 Opus, T9 Opus, T10 Opus; every reviewer Opus. Fix rounds resume the implementer by agent id; handbacks at $D/<task>/handback.md.

Carry into dispatches:
- T7: ticket and tape-log markup are in t6-impl/handback.md ("Markup Task 7 must use"); also a comment in radio.css. #label-status hidden in offair and pinned by a smoke scenario (nothing pins it yet). tapeLog titles through tidyTitle. Harness: requests holds raw url with query; screenshots in .superpowers/player-smoke are wiped by each smoke run. .sr class is visible, a misnomer (minor).
- T8: tick and mayPlay use Date.now(), never performance.now(). Never call tick after Stop; a session counter drops any verdict from a cancelled session; smoke proves Review Focus 5. Run tick at once on a verdict: a verdict's age counts from the module's last seen time. classifyProbe returns offair or unknown; unknown from an HTTP response maps to verdict("reachable"). Add setLive("drop") to serve.mjs (destroy connections). playlist() is Date.now()-aligned; a PDT offset for the "follows playback position" scenario goes there. recovery.advancing, not playing events, drives playing state and hubs. Phone-paused element: pauseMeansStop has already stopped it, so no stall follows. ARTWORK is root-absolute, absent in preview until deploy-assets.
- T9: show-page classes in t6-impl/handback.md (.bigt .bstub .bmain .btn .cols .jcard .liner .meta .fineprint, .top .brand .kick). .meta b needs the oxblood colour; mockup's .tag link has no equivalent. Docker is down: Debian-12 gate unrun, say so. Report it to llama-0e.
- T10: panelModel gives where, date (formatted), airtimes; set may be null or absent: don't print null. panel element is created by panel.js, not in index.html.
- T12: deploy-assets.mjs minors 1 and 6 (R4): refuse unknown args, exit 2; prefix guard on --remove-preview. Also remove probe manifest code.
- Final review gets every "minor (deferred)" line above.

Rulings so far: R1-R9 above, each with its cost. Reports to llama-0e list each dispatch with its model, and the meter.
