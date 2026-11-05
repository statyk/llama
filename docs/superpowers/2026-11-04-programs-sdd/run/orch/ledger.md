# SDD ledger — plan: docs/superpowers/plans/2026-11-04-programs-and-lineup.md
Peer orchestrator e1c9d972-5748-4fa8-aa4d-b37f2e80851d; worktree .claude/worktrees/programs, branch programs-lineup, start b7ec7bda.
Spec: docs/superpowers/specs/2026-11-04-programs-and-lineup-design.md (reachable).
Setup: own .venv (Python 3.14; imports resolve in worktree), npm ci done.

## Pre-flight scan (tasks 1-13; 14 is final review; 15-20 not ours)
| pair / task | produces -> consumes | found |
|---|---|---|
| T1->T2 | build_timeline(clock=), program_title, build_lineup; T1's temp clock arg in _publish_site replaced by T2 | consistent |
| T1->T3 | blocks[] {block,nominal_start,title,start,end?}; lineup {occurrences[{block,nominal_start,end,title,variety}]} | consistent |
| T2->T4 | LINEUP_KEY notes/_lineup.json; smoke serves notes key `_lineup` | consistent |
| T3->T4 | programs.js exports; notes.js panelModel.presents | consistent |
| T1<->T4 | show.html $presents vs panel/page ticket fallback LMA RADIO PRESENTS | consistent |
| T5->T6,T9 | station_lock(), StationLocked(.details); _COMMAND_ORDER: T5 adds lock, T9 inserts retitle before lock | consistent |
| T5<->T10 | same contract, separate impls; message shapes differ (emcee: msg+details; llama: 3-line msg) | consistent (by design) |
| T5,T10->T12 | contract test imports both; scripts may import both | consistent |
| T7->T8 | DJAudioBlock.title last; raw writer appends title key at end of dj_audio when absent | consistent |
| T8->T9 | plan_retitle/write_title/TitleWriteFailed/procs.other_tool_processes | consistent |
| T10->T11,T12 | for_package(out, command) | consistent |
| T6/T9/T11/T12 | all edit CLAUDE.md files (root, emcee, llama, scripts) at different paragraphs | sequential, no conflict |
| T1 self | tests reference site.DAY_US (new constant) and iso helpers; Step 3 matches tests | ok |
| T2 self | tests vs Step 3 (lineup digest, failure handling) | ok |
| T3 self | lineupDays algorithm vs DST/zone tests | ok |
| T4 self | old-index.html must be copied before Step 3 edits index.html | ok (ordering noted to implementer) |
| T5 self | tests vs interfaces | ok |
| T6 self | wraps _process_one; dry-run takes no lock | ok |
| T7 self | process_package passes voicing.title | ok |
| T8 self | rules order + writer order vs tests | ok |
| T9 self | "re-read every planned manifest" (spec: "every planned package") — ambiguous scope | Ruling R2 |
| T10-T13 self | ok |

## Rulings
- Ruling R1: one Opus task reviewer per task issuing both verdicts (spec compliance + code quality), per SDD skill v7's combined reviewer — the brief's "spec-compliance and code-quality review" is satisfied by the two verdicts; strict tasks (5,6,8-12) get the spec's lock/backfill sections as the constraints lens — cost if wrong: less reviewer independence than two separate seats.
- Ruling R2: T9 drift check re-reads every package in plan.writes (the packages the plan decided to write) — those are the only ones written; drift in an unchanged/awaiting show cannot produce a bad write — cost if wrong: a show that became writable between plan and lock is missed until the next run.

## Escapes


## Progress
01:58 Task 1: implementer dispatched (sonnet), BASE b7ec7bda
baseline: pytest 6624 passed 1 skipped 26 warnings; vitest 524; smoke 108; typecheck ok
02:02 Task 1: implementer DONE b6cf5adf; reviewer dispatched (opus)
Task 1: minor (deferred): occurrence_spans revisit branch (site.py:84-85) untested (A,B,A case)
Task 1: minor (deferred): test_lineup_bytes_are_stable compares NOW vs NOW+1 only (plan-mandated, weak)
Task 1: minor (deferred): lineup window test doesn't pin the lower bound's earliest inclusion
Task 1: minor (deferred): publish.py:240 temp clock= param unannotated (Task 2 replaces)
Task 1: ⚠️ Debian12 gate not run (Docker down) — carry to Task 14
Task 1: complete (commits b7ec7bda..b6cf5adf, review clean)
02:04 Task 2: implementer dispatched (sonnet), BASE b6cf5adf
Escape E1: t2-impl dispatched with a literal MANDATES_PLACEHOLDER instead of the mandates; sent them by SendMessage right after spawn. Fix: dispatches now splice mandates.txt via sed before sending.
02:09 Task 2: implementer DONE_WITH_CONCERNS (docker down) edaa6548; reviewer dispatched (opus)
Task 2: minor (deferred): test_lineup_failure_never_stops_the_timeline doesn't pin notes digests kept (no title change in pass 2)
Task 2: minor (deferred): test_publish.py:39-41 lineup compared to itself (tautological)
Task 2: minor (deferred): unreadable-manifest test lacks show/<slug>.html count==1 check
Task 2: minor (deferred): PutBudgetExceeded at lineup loses this pass's notes digests (same as timeline today; acceptable)
Task 2: minor (deferred): transmitter CLAUDE.md:22 reflow; test_publish inline imports/helper placement
Task 2: ⚠️ Debian12 gate not run (Docker down) — carry to Task 14
Task 2: complete (commits b6cf5adf..edaa6548, review clean)
02:11 Task 3: implementer dispatched (sonnet), BASE edaa6548
02:12 llama-player: py3.11 gate at Task 14 via uv venv -p 3.11 OUTSIDE the worktree (use scratchpad /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-programs/e1c9d972-5748-4fa8-aa4d-b37f2e80851d/scratchpad/py311), install herder + transmitter[dev], run python -m pytest packages/transmitter -q AND scripts/test_station_probe.py. Replaces the Docker gate.
02:13 Task 3: implementer DONE_WITH_CONCERNS (no RED run) de5ec1a6; reviewer dispatched (opus)
- Ruling R3: Task 3 review minors 1-3 (westward-move test not pinned, DST fixture empty, blockSpan throws on malformed blocks entry) enter a fix round despite "Approved" — Review Focus 2 says the westward move is pinned in Task 3 and RF5 says the page never breaks on partial data; treated as confirmed spec gaps — cost if wrong: one extra small fix round.
Task 3: minor (deferred): show.block/s.start throw on a null element in timeline.shows (consistent with timeline.js)
Task 3: fix round 1 dispatched (resume implementer sonnet; findings 1-3)
Task 3: fix round 1/5 (3 addressed, 0 open; commits de5ec1a6..5a7eb910)
Task 3: minor (deferred): Tokyo eastward case dropped from programs.test.ts in fix round
Task 3: minor (deferred): exported blockSpan still throws on unparseable start if called directly; redundant nonEmpty(entry.end) at programs.js:27
Task 3: minor (deferred): fix report gave summary line only, not raw test output
Task 3: complete (commits edaa6548..5a7eb910, review clean after fix round 1)
02:17 Task 4: implementer dispatched (opus), BASE 5a7eb910
02:41 Task 4: implementer DONE_WITH_CONCERNS 13b380aa (4 minor concerns); reviewer dispatched (opus)
Task 4: accepted implementer judgement calls (reviewer concurred): off-air -> no on-air highlight; long program ellipsized on tickets (fixed ticket height) — FOR SHAWN'S EYE; empty lineup day shows empty list; on-air block with tomorrow's nominal date not highlighted
Task 4: minor (deferred): tab pattern incomplete — #lineup-list lacks role=tabpanel/aria-labelledby, tablist has no accessible name
Task 4: minor (deferred): lineupDays recomputed every 1 s renderAt (~60+ Intl.DateTimeFormat constructions/tick) — memoize
Task 4: minor (deferred): .block-head restates .kick values instead of sharing the selector
Task 4: minor (deferred): lineup refetch rides refreshTimeline's 3-min gate (30-33 min); force refresh doesn't force lineup
Task 4: minor (deferred): refreshTimeline has the same unread-404-body pattern refreshLineup fixed (implementer note)
Task 4: ⚠️ cross-check lineup.mjs fixture shape vs site.build_lineup — for Task 14
Task 4: complete (commits 5a7eb910..13b380aa, review clean; controller full smoke pending)
02:45 Task 5: implementer dispatched (opus), BASE 13b380aa
Task 4: controller full smoke at 13b380aa: 131/131 passed (npx playwright --list = 131)
02:52 Task 5: implementer DONE_WITH_CONCERNS b0be756a; reviewer dispatched (opus). Escape E2: t5-impl ran read-only 'git stash list' (mandate 4 says never git stash in any form); no mutation.
Task 5: review Needs fixes — Important 1: signal/close-error windows in acquire tail and release leave an unreleased lock (fail-safe but wedges writers)
- Ruling R4: Task 5 minors 2 (lock show/clear tracebacks on non-ENOENT) and 3 (wrong warning when lock vanishes mid-release) ride fix round 1 — Task 10 mirrors this module, so fixing once avoids copying defects — cost if wrong: slightly larger fix round.
Task 5: minor (deferred): lock clear compare-then-unlink TOCTOU (inherent; rename-aside could narrow) — final review
Task 5: minor (deferred): plain fsync (no F_FULLFSYNC/dir fsync) acceptable for a lock
Task 5: fix round 1 dispatched (resume implementer opus; Important 1 + minors 2,3)
Task 5 note for Task 10: unblock signals in the context manager itself, not in a returning helper (else signal fires before held assigned)
Task 5: fix round 1/5 (4 addressed, 1 open — new Important: signal between with-body end and release-side _block leaves lock (reproduced); + minor: signal inside _block's SIG_BLOCK leaves mask blocked; commits b0be756a..395e6455)
Task 5: out-of-scope (deferred): SIGINT not masked around acquire/release (brief names only TERM/HUP) — final review
Task 5: fix round 2 dispatched (resume implementer opus)
- Ruling R5: accept Task 5 round-2 design where the SIGTERM/SIGHUP handler itself releases the lock (signals blocked) before raising; finally releases only if not already released — the spec's "release in finally, handlers raise into it" left an unclosable window in the finally prologue; handler-release closes it — cost if wrong: a signal inside a `with` body releases the lock before that body's own except/finally runs, so any station write in such a clause would run unguarded. Constraint carried to Tasks 6, 9, 10, 11, 12: no station writes in except/finally clauses inside the lock's with-body; reviewers check it.
Task 5: minor (deferred): outer finally's last unblock is defence-in-depth with no discriminating test
- Ruling R6 (llama-player's, REPLACES R5): SIGTERM/SIGHUP handler releases the lock (token-checked, both signals blocked) then ends the process with os._exit(128+signum); never raises into caller code. Every station write is an atomic rename, so ending mid-sequence leaves at most a stray temp file (as SIGKILL, minus the stuck lock). R5's except/finally constraint on Tasks 6, 9-12 is withdrawn. SIGINT unchanged (KeyboardInterrupt -> normal finally release). Applied as Task 5 fix round 3 unless re-review 2 shows a concrete problem with it — cost if wrong: unflushed stdout/stderr and skipped non-lock cleanup on TERM/HUP.
Task 5: fix round 2/5 (2 addressed, 0 open; commits 395e6455..ff724fe4) — re-review 2: 107 line-level signal injections all clean
Task 5: minor (deferred/superseded by R6?): SIG_SETMASK restores whole entry mask (folded into round 3); handler releases _held regardless of thread (moot under os._exit); final _unblock untested
Task 5: out-of-scope (deferred): KeyboardInterrupt inside release-side _block or handler's release can leave lock (SIGINT class) — final review
Task 5: fix round 3 dispatched (R6: handler releases then os._exit; resume implementer opus)
Task 5: fix round 3/5 (R6 + mask minor addressed, 0 open; commits ff724fe4..56df66a0)
Task 5: minor (deferred, FLAG FOR FINAL REVIEW): pthread_sigmask covers the main thread only; with another live thread a process-directed SIGTERM runs the handler mid-release (after _held=None, before unlink) or mid-acquire (after open, before _held set) -> stuck lock (fail-safe, lock clear recovers; reproduced rr3/t.py, r.py). Fix shape: clear _held after unlink attempt; publish path/token before os.open. emcee run may have TTS/HTTP threads.
Task 5: out-of-scope (deferred): KeyboardInterrupt between acquire return and held assignment leaves lock (SIGINT class)
Task 5: complete (commits 13b380aa..56df66a0, 3 fix rounds, review clean; 1 deferred minor flagged)
03:15 Task 6: implementer dispatched (opus), BASE 56df66a0
03:16 llama-player: do NOT defer the threaded-signal window — T5 follow-up (t5b) after Task 6, before Task 10: clear _held only after unlink, publish token before os.open; test with a live second thread; implementer Opus + Opus re-review. Controller ordering: after Task 6 (single-writer worktree).
03:21 Task 6: implementer DONE_WITH_CONCERNS 840e74fe (README still says no lock; voice . empty slug pre-existing); reviewer dispatched (opus)
Task 6: minor (deferred): non-StationLocked acquire error (EACCES/ENOSPC) repeats per package rather than stopping (brief-prescribed)
Task 6: minor (deferred): `emcee voice .` prints empty slug (pre-existing; pkg.dir.absolute().name)
Task 6: minor (deferred): voice --fresh stems validated before lock, unlinked under it (clean failure)
Task 6: complete (commits 56df66a0..840e74fe, review clean)
- Ruling R7: README.md:633-637 "Single-writer station, no lock" is a plan gap (no task owns README); fix rides the t5b follow-up — cost if wrong: one doc hunk outside a plan task.
03:23 t5b: implementer dispatched (opus), BASE 840e74fe
03:29 t5b: implementer DONE_WITH_CONCERNS c1d486eb+6c969f10 — used deferral (_critical/_deferred/_exiting) instead of llama-player's publish-before-open/clear-after-unlink (argued: an empty just-created file can't be token-checked); reviewer dispatched (opus); reported to llama-player
03:30 llama-player: withdraws publish-before-open mechanism; keep deferral + _exiting if Opus review passes; refused-acquire+deferred-signal exit 128+signum is accepted — pin with one test that the other holder's lock survives; Task 10 mirrors the FINAL (deferral) design.
t5b: review Approved (deferral design sound; mirror it in Task 10); reviewer note for Task 10: in-body signal taken by another thread while main blocks in non-EINTR wait is delayed (not lost) until main wakes
t5b: fix round 1 dispatched (resume implementer opus): refused + warn-release (+create/write-error) window pins; comment fixes
t5b: fix round 1/5 (3 addressed, 0 open; commits 6c969f10..30f72cff)
t5b: minor (deferred): _unblock KeyboardInterrupt comment could also name the gap between _critical=False and the _deferred swap
t5b: complete (commits 840e74fe..30f72cff, review clean). Task 10 mirrors THIS design (deferral + _exiting + os._exit) incl. comment on KeyboardInterrupt limit and stale-_deferred consequence.
03:38 Task 7: implementer dispatched (sonnet), BASE 30f72cff
03:41 Task 7: implementer DONE_WITH_CONCERNS (no RED run) c4a1916f; reviewer dispatched (opus)
Task 7: minor (carried into Task 8 dispatch): emcee CLAUDE.md:126 and models.py:74 say "Task 8's raw writer" — name the backfill instead
Task 7: minor (deferred): test_the_cut.py:94 checks model_dump()["title"] only (full round-trips covered elsewhere)
Task 7: complete (commits 30f72cff..c4a1916f, review clean)
03:43 Task 8: implementer dispatched (opus), BASE c4a1916f
03:50 Task 8: implementer DONE 25a10201; reviewer dispatched (opus)
Task 8: review Approved (0 Critical/Important, 6 minor)
- Ruling R8: Task 8 minors 1 (temp-collision cleanup deletes foreign temp), 2 (raw OSErrors escape write_title / inconsistent vanish handling), 5 (temp mode from umask, rewrite can change manifest perms) enter fix round 1 — strict live-share writer, all cheap — cost if wrong: one small extra round.
Task 8: minor (carried to Task 9 dispatch): Task 9 treats any exception from write_title as stop-run; dry run may list stray .manifest.json.emcee-*.tmp files
Task 8: minor (deferred): fsync assertion not tied to temp fd; put-back-after-foreign-change path untested; 26 suite warnings pre-existing (baseline 26)
Task 8: ⚠️ go-live: utime-before-rename over SMB->NFS unprovable locally; Task 19 probe should exercise retitle._swap's real path (for llama-player)
Task 8: fix round 1 dispatched (resume implementer opus)
Task 8: fix round 1/5 (3 addressed, 0 open; commits 25a10201..97e5febf)
Task 8: complete (commits c4a1916f..97e5febf, review clean after fix round 1)
- Ruling R9: Task 8 re-review minors folded into Task 9's dispatch (same writer, reviewed with Task 9): fchmod on the SMB share may be refused (EPERM/ENOTSUP) and would block every write — make that failure non-fatal (mode is then the server's); cleanup-unlink OSError escaping untranslated -> map to before-rename failure; _AfterRename message wording ("replaced with this write's bytes (not verified); its mtime unknown") — cost if wrong: Task 9's diff touches retitle.py.
Task 8: ⚠️ go-live: one real retitle write on the share before relying on fchmod/utime (for llama-player, Task 19/20)
03:59 Task 9: implementer dispatched (opus), BASE 97e5febf
04:08 Task 9: implementer DONE_WITH_CONCERNS (backup dir not fsynced) 8570e890,7cc39090; reviewer dispatched (opus)
Task 9: review Approved (0 Critical/Important, 8 minor)
- Ruling R10: Task 9 minors 1 (hand-restore doc omits mtime restore and the before-without-after case), 3 (fsync backup dirs), 7 (drift test doesn't pin "under the lock"), 6 (test name) enter fix round 1 — operator restore runbook on a strict surface; cheap — cost if wrong: one small round.
Task 9: minor (deferred): unlink "temp was left" add_note not shown in TitleWriteFailed message; `<n> written` extra copy; nothing-written stream inconsistency; Ctrl-C mid-write prints no not-attempted list
Task 9: ⚠️ go-live: _stray_temps readdir of all 2,786 package dirs on SMB on every plan — time it (llama-player)
Task 9: fix round 1 dispatched (resume implementer opus)
Task 9: fix round 1/5 (4 addressed, 0 open; commits 7cc39090..b7e137a6)
Task 9: minor (deferred, FINAL REVIEW should fix): restore doc N1 — copy-then-utime on live file; should be temp+utime+os.replace, restore with no emcee/llama running (or under lock)
Task 9: minor (deferred, FINAL REVIEW should fix): restore doc N2 — before-only cause list incomplete (failed put-back etc.); spell out three outcomes; new title not in record.jsonl
Task 9: minor (deferred): emcee root parent entry not fsynced if mkdir created the root
Task 9: complete (commits 97e5febf..b7e137a6, review clean after fix round 1)
04:16 Task 10: implementer dispatched (opus), BASE b7e137a6
04:20 Task 10: implementer DONE_WITH_CONCERNS 259fd05c (llama has no no-emcee-imports guard test); reviewer dispatched (opus)
Task 10: minor (deferred): llama StationLocked str(exc) is multi-line — single-line record writers (ledger rows/JSON) would embed newlines; note for Tasks 11-12
Task 10: complete (commits b7e137a6..259fd05c, review clean)
- Ruling R11: llama lacks a test_no_emcee_imports guard (emcee/transmitter have theirs); the ~25-line mirror rides Task 11's dispatch — cost if wrong: one extra test file in Task 11's diff.
04:22 Task 11: implementer dispatched (opus), BASE 259fd05c
04:22 RELAY-NOW received from llama-player: finish Task 11 through review/fix rounds, start nothing new, write HANDOFF, report RELAY-READY idle+disarmed.
- Ruling R12: Task 11 runs the deliver gate check BEFORE creating a missing station folder (then again under the lock), instead of the brief's mkdir-right-after-awaiting-fix order — three existing tests assert no destination after a gate refusal; with no folder the gate is the only possible refusal, output identical — cost if wrong: gate evaluated twice.
Task 11: R6 finding (FOR FINAL REVIEW / SHAWN): deliver overlay path shutil.copytree(dirs_exist_ok=True) copies into the live package in place — SIGTERM (now = SIGKILL semantics under R6) can leave a truncated manifest.json (next deliver refuses) or truncated audio that could air until re-delivered; pre-existing under SIGKILL; only unvoiced/unmarked same-tracklist destinations
Task 11: R6 finding: replace path interrupted between its two renames removes the show from station (.slug.old-* + .slug.deliver-* left); next deliver warns about .old-* but doesn't restore; voiced original needs hand restore
Task 11: R6 finding: clear-mark exit between clear and add_clear leaves station cleared but no campaign clear row; stray .manifest.json.llama-*.tmp never swept
Task 11: minor: clear-mark with missing delivery_path folder now says "cannot create the station lock ... Errno 2" instead of "station copy unreadable"
04:28 Task 11: implementer DONE_WITH_CONCERNS 4a916ddb; reviewer dispatched (opus)
Task 11: minor (deferred): batch "not attempted" list includes unreadable/awaiting slugs already listed as refused
Task 11: minor (deferred): no-imports guard regexes (llama and emcee) miss comma-list imports (`import os, emcee`)
Task 11: minor (deferred): llama CLAUDE.md "emcee does not share this locking scheme" now reads as a contradiction next to the station-lock paragraph — say "flock scheme"
Task 11: minor (deferred): test_clear_mark span test re-wraps spies in its second scenario (fragile)
Task 11: R6 note: station_lock docstrings claim every station write is an atomic rename; deliver overlay copytree contradicts it
Task 11: complete (commits 259fd05c..4a916ddb, review clean)

## HANDOFF (written on RELAY-NOW)
- State: Tasks 1-11 complete (plus t5b follow-up). Branch programs-lineup head 4a916ddb, tree clean. Last full suite (implementer-reported at 4a916ddb): 6853 passed, 1 skipped; antenna vitest ~545, smoke 131/131 (controller-run at 13b380aa), typecheck clean.
- Remaining: Task 12 (bulk_apply takes the lock + scripts/test_station_lock_contract.py; Opus; STRICT — station marks), Task 13 (station_probe.py; Sonnet), Task 14 (final whole-branch review on Opus ONLY + py3.11 gate via uv venv OUTSIDE worktree, e.g. scratchpad/py311: herder + transmitter[dev], run packages/transmitter AND scripts/test_station_probe.py; no merge/push).
- Next orchestrator: start a NEW $D-orch dir (e.g. orch-r1); per-task dirs here are single-use (t12-impl etc. still free).
- Briefs: .superpowers/sdd/2026-11-04-programs-and-lineup/task-12-brief.md, task-13-brief.md. Shared files in $D/orch/: implementer-common.md, reviewer-instructions.md, rereview-instructions.md, global-constraints.md, mandates.txt, setflight.py.
- Carry into Task 12 dispatch: R6 (handler releases + os._exit; no caller cleanup) — check bulk_apply's mark/put-back writes are atomic and report; llama StationLocked str(exc) is multi-line (single-line ledger/JSON writers would embed newlines); use for_package only; take lock BEFORE _station_copy_problem; no lock across prompts; contract test imports both emcee and llama station_lock (scripts/ only).
- Carry into Task 14 final review: all "minor (deferred)" lines above, plus the FLAGGED ones: Task 9 restore-doc N1/N2 (should be fixed before any restore at scale); Task 11 overlay-copytree R6 finding; Task 4 ticket ellipsis (Shawn's eye); Task 5 SIGINT-class windows; Task 4 cross-check lineup.mjs fixture vs site.build_lineup; go-live notes (Task 8: exercise retitle._swap on the real share; Task 9: time stray-temp readdir over SMB).
- Rulings made (R1-R12; R5 superseded by R6, R6 is llama-player's): see the Rulings section and inline "- Ruling" lines above.
04:31 tick d601606a deleted; armed flag removed (armed-global kept only if another armed-* exists)
