# Carry-overs for the final review (extracted verbatim from both orchestrator ledgers)

## Predecessor ledger ($D/orch/ledger.md)
Task 1: minor (deferred): occurrence_spans revisit branch (site.py:84-85) untested (A,B,A case)
Task 1: minor (deferred): test_lineup_bytes_are_stable compares NOW vs NOW+1 only (plan-mandated, weak)
Task 1: minor (deferred): lineup window test doesn't pin the lower bound's earliest inclusion
Task 1: minor (deferred): publish.py:240 temp clock= param unannotated (Task 2 replaces)
Task 1: ⚠️ Debian12 gate not run (Docker down) — carry to Task 14
Task 2: minor (deferred): test_lineup_failure_never_stops_the_timeline doesn't pin notes digests kept (no title change in pass 2)
Task 2: minor (deferred): test_publish.py:39-41 lineup compared to itself (tautological)
Task 2: minor (deferred): unreadable-manifest test lacks show/<slug>.html count==1 check
Task 2: minor (deferred): PutBudgetExceeded at lineup loses this pass's notes digests (same as timeline today; acceptable)
Task 2: minor (deferred): transmitter CLAUDE.md:22 reflow; test_publish inline imports/helper placement
Task 2: ⚠️ Debian12 gate not run (Docker down) — carry to Task 14
Task 3: minor (deferred): show.block/s.start throw on a null element in timeline.shows (consistent with timeline.js)
Task 3: minor (deferred): Tokyo eastward case dropped from programs.test.ts in fix round
Task 3: minor (deferred): exported blockSpan still throws on unparseable start if called directly; redundant nonEmpty(entry.end) at programs.js:27
Task 3: minor (deferred): fix report gave summary line only, not raw test output
02:41 Task 4: implementer DONE_WITH_CONCERNS 13b380aa (4 minor concerns); reviewer dispatched (opus)
Task 4: accepted implementer judgement calls (reviewer concurred): off-air -> no on-air highlight; long program ellipsized on tickets (fixed ticket height) — FOR SHAWN'S EYE; empty lineup day shows empty list; on-air block with tomorrow's nominal date not highlighted
Task 4: minor (deferred): tab pattern incomplete — #lineup-list lacks role=tabpanel/aria-labelledby, tablist has no accessible name
Task 4: minor (deferred): lineupDays recomputed every 1 s renderAt (~60+ Intl.DateTimeFormat constructions/tick) — memoize
Task 4: minor (deferred): .block-head restates .kick values instead of sharing the selector
Task 4: minor (deferred): lineup refetch rides refreshTimeline's 3-min gate (30-33 min); force refresh doesn't force lineup
Task 4: minor (deferred): refreshTimeline has the same unread-404-body pattern refreshLineup fixed (implementer note)
Task 4: ⚠️ cross-check lineup.mjs fixture shape vs site.build_lineup — for Task 14
Task 5: minor (deferred): lock clear compare-then-unlink TOCTOU (inherent; rename-aside could narrow) — final review
Task 5: minor (deferred): plain fsync (no F_FULLFSYNC/dir fsync) acceptable for a lock
Task 5: fix round 1 dispatched (resume implementer opus; Important 1 + minors 2,3)
Task 5: fix round 1/5 (4 addressed, 1 open — new Important: signal between with-body end and release-side _block leaves lock (reproduced); + minor: signal inside _block's SIG_BLOCK leaves mask blocked; commits b0be756a..395e6455)
Task 5: out-of-scope (deferred): SIGINT not masked around acquire/release (brief names only TERM/HUP) — final review
Task 5: minor (deferred): outer finally's last unblock is defence-in-depth with no discriminating test
Task 5: minor (deferred/superseded by R6?): SIG_SETMASK restores whole entry mask (folded into round 3); handler releases _held regardless of thread (moot under os._exit); final _unblock untested
Task 5: out-of-scope (deferred): KeyboardInterrupt inside release-side _block or handler's release can leave lock (SIGINT class) — final review
Task 5: fix round 3/5 (R6 + mask minor addressed, 0 open; commits ff724fe4..56df66a0)
Task 5: minor (deferred, FLAG FOR FINAL REVIEW): pthread_sigmask covers the main thread only; with another live thread a process-directed SIGTERM runs the handler mid-release (after _held=None, before unlink) or mid-acquire (after open, before _held set) -> stuck lock (fail-safe, lock clear recovers; reproduced rr3/t.py, r.py). Fix shape: clear _held after unlink attempt; publish path/token before os.open. emcee run may have TTS/HTTP threads.
Task 5: out-of-scope (deferred): KeyboardInterrupt between acquire return and held assignment leaves lock (SIGINT class)
Task 5: complete (commits 13b380aa..56df66a0, 3 fix rounds, review clean; 1 deferred minor flagged)
Task 6: minor (deferred): non-StationLocked acquire error (EACCES/ENOSPC) repeats per package rather than stopping (brief-prescribed)
Task 6: minor (deferred): `emcee voice .` prints empty slug (pre-existing; pkg.dir.absolute().name)
Task 6: minor (deferred): voice --fresh stems validated before lock, unlinked under it (clean failure)
t5b: minor (deferred): _unblock KeyboardInterrupt comment could also name the gap between _critical=False and the _deferred swap
Task 7: minor (carried into Task 8 dispatch): emcee CLAUDE.md:126 and models.py:74 say "Task 8's raw writer" — name the backfill instead
Task 7: minor (deferred): test_the_cut.py:94 checks model_dump()["title"] only (full round-trips covered elsewhere)
Task 8: review Approved (0 Critical/Important, 6 minor)
Task 8: minor (carried to Task 9 dispatch): Task 9 treats any exception from write_title as stop-run; dry run may list stray .manifest.json.emcee-*.tmp files
Task 8: minor (deferred): fsync assertion not tied to temp fd; put-back-after-foreign-change path untested; 26 suite warnings pre-existing (baseline 26)
Task 8: ⚠️ go-live: utime-before-rename over SMB->NFS unprovable locally; Task 19 probe should exercise retitle._swap's real path (for llama-player)
Task 8: ⚠️ go-live: one real retitle write on the share before relying on fchmod/utime (for llama-player, Task 19/20)
Task 9: review Approved (0 Critical/Important, 8 minor)
Task 9: minor (deferred): unlink "temp was left" add_note not shown in TitleWriteFailed message; `<n> written` extra copy; nothing-written stream inconsistency; Ctrl-C mid-write prints no not-attempted list
Task 9: ⚠️ go-live: _stray_temps readdir of all 2,786 package dirs on SMB on every plan — time it (llama-player)
Task 9: minor (deferred, FINAL REVIEW should fix): restore doc N1 — copy-then-utime on live file; should be temp+utime+os.replace, restore with no emcee/llama running (or under lock)
Task 9: minor (deferred, FINAL REVIEW should fix): restore doc N2 — before-only cause list incomplete (failed put-back etc.); spell out three outcomes; new title not in record.jsonl
Task 9: minor (deferred): emcee root parent entry not fsynced if mkdir created the root
Task 10: minor (deferred): llama StationLocked str(exc) is multi-line — single-line record writers (ledger rows/JSON) would embed newlines; note for Tasks 11-12
Task 11: R6 finding (FOR FINAL REVIEW / SHAWN): deliver overlay path shutil.copytree(dirs_exist_ok=True) copies into the live package in place — SIGTERM (now = SIGKILL semantics under R6) can leave a truncated manifest.json (next deliver refuses) or truncated audio that could air until re-delivered; pre-existing under SIGKILL; only unvoiced/unmarked same-tracklist destinations
Task 11: R6 finding: replace path interrupted between its two renames removes the show from station (.slug.old-* + .slug.deliver-* left); next deliver warns about .old-* but doesn't restore; voiced original needs hand restore
Task 11: R6 finding: clear-mark exit between clear and add_clear leaves station cleared but no campaign clear row; stray .manifest.json.llama-*.tmp never swept
Task 11: minor: clear-mark with missing delivery_path folder now says "cannot create the station lock ... Errno 2" instead of "station copy unreadable"
Task 11: minor (deferred): batch "not attempted" list includes unreadable/awaiting slugs already listed as refused
Task 11: minor (deferred): no-imports guard regexes (llama and emcee) miss comma-list imports (`import os, emcee`)
Task 11: minor (deferred): llama CLAUDE.md "emcee does not share this locking scheme" now reads as a contradiction next to the station-lock paragraph — say "flock scheme"
Task 11: minor (deferred): test_clear_mark span test re-wraps spies in its second scenario (fragile)
Task 11: R6 note: station_lock docstrings claim every station write is an atomic rename; deliver overlay copytree contradicts it
- Carry into Task 14 final review: all "minor (deferred)" lines above, plus the FLAGGED ones: Task 9 restore-doc N1/N2 (should be fixed before any restore at scale); Task 11 overlay-copytree R6 finding; Task 4 ticket ellipsis (Shawn's eye); Task 5 SIGINT-class windows; Task 4 cross-check lineup.mjs fixture vs site.build_lineup; go-live notes (Task 8: exercise retitle._swap on the real share; Task 9: time stray-temp readdir over SMB).

## orch-r1 ledger
04:41 Task 12: review Approved (0 Critical/Important, 6 minor); ⚠️ R6 atomicity resolved by controller: station_mark._swap_in (station_mark.py:134) and batch_snapshot._durable_replace (batch_snapshot.py:106) are each one os.replace
- Ruling R14: Task 12 review minors 1 (early return [] not None), 4 (docstring wrap), 5 (contract body-key order pin + reverse not-ours warning) ride R13's fix round — cheap, same files — cost if wrong: slightly larger fix diff.
Task 12: minor (accepted by llama-player): unmark --apply locks never-delivered lines too (fails safe; station unmounted now refuses library-only reversals)
Task 12: minor 2 (lock create error carries on) and 6 (contract tests never red) -> fix round per R13
04:41 Task 12: fix round 1 dispatched (resume implementer opus): R13 create-error stop + contract mutants; R14 minors 1,4,5
Task 12: minor (deferred): bulk_apply.py:1182 unmark docstring line 118 cols (introduced by fix round 1)
Task 12: minor (deferred): bulk_apply.py:1777, :1982 102 cols (pre-existing)
Task 12: minor (deferred): scripts/CLAUDE.md gained an unrequested sentence on create-error stop (consistent with R13)
- Ruling R15: Task 13 minors 1 (cross exits 0 with contended 0 — proves nothing at go-live), 2 (killed cross leaves the shared lock), 3 (non-ENOENT OSError on contender read swallowed — add an unreadable counter, SMB EACCES), 4 (dead worker hangs parent ~6 min on queue.get), 5 (no --n/--workers validation; workers<2 races vacuously) ride fix round 1 — this script's only purpose is go-live evidence in Task 19, and a probe that passes vacuously defeats it; all small — cost if wrong: a larger fix diff on a test-only script.
Task 13: minor (deferred): re-check compares whole seconds vs writer's st_mtime_ns (equivalent for the integer target)
04:52 Task 13: fix round 1 dispatched (resume implementer sonnet): Important 1 + R15 minors 1-5
Task 13: minor (deferred, FINAL REVIEW should fix): stale .lock-race-<tag> makes cross pass vacuously (acquired 0, contended N, both rc 0 — measured); fix: exit 3 when acquired==0 or refuse a pre-existing lock before --start-at
Task 13: minor (deferred): test_race_warns_when_nothing_contended is vacuous (--n 1 always contends; warning-removal mutant survived 5/5)
Task 13: minor (deferred): cmd_race early return 2 terminates workers without join (harmless)
Task 13: ⚠️ for llama-player (Task 19, not ours): plan Task 19 Step 4 (plan:860) says "started within a few seconds of each other" — runbook doesn't mention --start-at or the exit-3 pass rule

## Rulings in force (context; R5 superseded by R6)
- Ruling R13 (llama-player's): a station lock that cannot be CREATED (EACCES or any other create error) STOPS the bulk_apply batch like a held lock, listing what was not attempted/reached — not refused-and-continue. Unmark-locks-never-delivered and no clear-mark writer accepted as is. Contract tests must each be shown failing once against a deliberately broken lock in a scratch copy (mandate 5). Both are Task 12 fix-round items whether or not the reviewer raises them.
- Ruling R14: Task 12 review minors 1 (early return [] not None), 4 (docstring wrap), 5 (contract body-key order pin + reverse not-ours warning) ride R13's fix round — cheap, same files — cost if wrong: slightly larger fix diff.
- Ruling R15: Task 13 minors 1 (cross exits 0 with contended 0 — proves nothing at go-live), 2 (killed cross leaves the shared lock), 3 (non-ENOENT OSError on contender read swallowed — add an unreadable counter, SMB EACCES), 4 (dead worker hangs parent ~6 min on queue.get), 5 (no --n/--workers validation; workers<2 races vacuously) ride fix round 1 — this script's only purpose is go-live evidence in Task 19, and a probe that passes vacuously defeats it; all small — cost if wrong: a larger fix diff on a test-only script.
- Ruling R1: one Opus task reviewer per task issuing both verdicts (spec compliance + code quality), per SDD skill v7's combined reviewer — the brief's "spec-compliance and code-quality review" is satisfied by the two verdicts; strict tasks (5,6,8-12) get the spec's lock/backfill sections as the constraints lens — cost if wrong: less reviewer independence than two separate seats.
- Ruling R2: T9 drift check re-reads every package in plan.writes (the packages the plan decided to write) — those are the only ones written; drift in an unchanged/awaiting show cannot produce a bad write — cost if wrong: a show that became writable between plan and lock is missed until the next run.
- Ruling R3: Task 3 review minors 1-3 (westward-move test not pinned, DST fixture empty, blockSpan throws on malformed blocks entry) enter a fix round despite "Approved" — Review Focus 2 says the westward move is pinned in Task 3 and RF5 says the page never breaks on partial data; treated as confirmed spec gaps — cost if wrong: one extra small fix round.
- Ruling R4: Task 5 minors 2 (lock show/clear tracebacks on non-ENOENT) and 3 (wrong warning when lock vanishes mid-release) ride fix round 1 — Task 10 mirrors this module, so fixing once avoids copying defects — cost if wrong: slightly larger fix round.
- Ruling R5: accept Task 5 round-2 design where the SIGTERM/SIGHUP handler itself releases the lock (signals blocked) before raising; finally releases only if not already released — the spec's "release in finally, handlers raise into it" left an unclosable window in the finally prologue; handler-release closes it — cost if wrong: a signal inside a `with` body releases the lock before that body's own except/finally runs, so any station write in such a clause would run unguarded. Constraint carried to Tasks 6, 9, 10, 11, 12: no station writes in except/finally clauses inside the lock's with-body; reviewers check it.
- Ruling R6 (llama-player's, REPLACES R5): SIGTERM/SIGHUP handler releases the lock (token-checked, both signals blocked) then ends the process with os._exit(128+signum); never raises into caller code. Every station write is an atomic rename, so ending mid-sequence leaves at most a stray temp file (as SIGKILL, minus the stuck lock). R5's except/finally constraint on Tasks 6, 9-12 is withdrawn. SIGINT unchanged (KeyboardInterrupt -> normal finally release). Applied as Task 5 fix round 3 unless re-review 2 shows a concrete problem with it — cost if wrong: unflushed stdout/stderr and skipped non-lock cleanup on TERM/HUP.
- Ruling R7: README.md:633-637 "Single-writer station, no lock" is a plan gap (no task owns README); fix rides the t5b follow-up — cost if wrong: one doc hunk outside a plan task.
- Ruling R8: Task 8 minors 1 (temp-collision cleanup deletes foreign temp), 2 (raw OSErrors escape write_title / inconsistent vanish handling), 5 (temp mode from umask, rewrite can change manifest perms) enter fix round 1 — strict live-share writer, all cheap — cost if wrong: one small extra round.
- Ruling R9: Task 8 re-review minors folded into Task 9's dispatch (same writer, reviewed with Task 9): fchmod on the SMB share may be refused (EPERM/ENOTSUP) and would block every write — make that failure non-fatal (mode is then the server's); cleanup-unlink OSError escaping untranslated -> map to before-rename failure; _AfterRename message wording ("replaced with this write's bytes (not verified); its mtime unknown") — cost if wrong: Task 9's diff touches retitle.py.
- Ruling R10: Task 9 minors 1 (hand-restore doc omits mtime restore and the before-without-after case), 3 (fsync backup dirs), 7 (drift test doesn't pin "under the lock"), 6 (test name) enter fix round 1 — operator restore runbook on a strict surface; cheap — cost if wrong: one small round.
- Ruling R11: llama lacks a test_no_emcee_imports guard (emcee/transmitter have theirs); the ~25-line mirror rides Task 11's dispatch — cost if wrong: one extra test file in Task 11's diff.
- Ruling R12: Task 11 runs the deliver gate check BEFORE creating a missing station folder (then again under the lock), instead of the brief's mkdir-right-after-awaiting-fix order — three existing tests assert no destination after a gate refusal; with no folder the gate is the only possible refusal, output identical — cost if wrong: gate evaluated twice.
- Rulings made (R1-R12; R5 superseded by R6, R6 is llama-player's): see the Rulings section and inline "- Ruling" lines above.
