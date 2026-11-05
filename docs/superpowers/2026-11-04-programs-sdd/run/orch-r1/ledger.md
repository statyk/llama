# SDD ledger — plan: docs/superpowers/plans/2026-11-04-programs-and-lineup.md
Successor peer orchestrator 7a0126d5-2768-4b15-a220-aa7277257102 (orch-r1); predecessor ledger $D/orch/ledger.md (read-only; rulings R1-R12 apply, R5 superseded by R6).
Start: programs-lineup @ 4a916ddb, tree clean. Tasks 1-11 + t5b complete per predecessor.
Shared files reused from $D/orch/: reviewer-instructions.md, rereview-instructions.md, global-constraints.md, mandates.txt. implementer-common.md copied into orch-r1 with THIS session's Claude-Session attribution.

## Rulings

## Escapes

## Progress
04:33 start: read handoff; meter 5h 57% 7d 62%
04:33 Task 12: implementer dispatched (opus) agent ada6615e0ef890cfc, BASE 4a916ddb; tick e166a594 armed
04:39 Task 12: implementer DONE_WITH_CONCERNS 6937a751 (suite 6865 passed 1 skipped); reviewer dispatched (opus) agent ae742b7d435be9f0e
Task 12: implementer concerns: no clear-mark writer in bulk_apply; unmark --apply locks never-delivered shows too; stop lines = full refusal text; lock-create OSError -> refused + continue (own call); contract tests never RED
Escape E1 (orch-r1): reviewer-prompt build used an unquoted heredoc, so a backticked `refused: ...` was executed as a command and dropped from the text; caught by grep and patched before dispatch. Fix: quote heredocs when composing prompts.
- Ruling R13 (llama-player's): a station lock that cannot be CREATED (EACCES or any other create error) STOPS the bulk_apply batch like a held lock, listing what was not attempted/reached — not refused-and-continue. Unmark-locks-never-delivered and no clear-mark writer accepted as is. Contract tests must each be shown failing once against a deliberately broken lock in a scratch copy (mandate 5). Both are Task 12 fix-round items whether or not the reviewer raises them.
04:39 llama-player ruling R13 recorded; waiting on t12-review
04:41 Task 12: review Approved (0 Critical/Important, 6 minor); ⚠️ R6 atomicity resolved by controller: station_mark._swap_in (station_mark.py:134) and batch_snapshot._durable_replace (batch_snapshot.py:106) are each one os.replace
- Ruling R14: Task 12 review minors 1 (early return [] not None), 4 (docstring wrap), 5 (contract body-key order pin + reverse not-ours warning) ride R13's fix round — cheap, same files — cost if wrong: slightly larger fix diff.
Task 12: minor (accepted by llama-player): unmark --apply locks never-delivered lines too (fails safe; station unmounted now refuses library-only reversals)
Task 12: minor 2 (lock create error carries on) and 6 (contract tests never red) -> fix round per R13
04:41 Task 12: fix round 1 dispatched (resume implementer opus): R13 create-error stop + contract mutants; R14 minors 1,4,5
04:45 Task 12: fix round 1 implementer DONE f0b480ce (suite 6872 passed 1 skipped; 8 mutants all matched predictions); re-review dispatched (opus) a61908695fc91ea61
Task 12: fix round 1/5 (5 addressed, 0 open; commits 6937a751..f0b480ce) — re-review: mutants M1-M8 credible
Task 12: minor (deferred): bulk_apply.py:1182 unmark docstring line 118 cols (introduced by fix round 1)
Task 12: minor (deferred): bulk_apply.py:1777, :1982 102 cols (pre-existing)
Task 12: minor (deferred): scripts/CLAUDE.md gained an unrequested sentence on create-error stop (consistent with R13)
Task 12: complete (commits 4a916ddb..f0b480ce, review clean after fix round 1)
04:47 Task 13: implementer dispatched (sonnet) af22688f46648f1ce, BASE f0b480ce (told: test file also py3.11 + stdlib/pytest only for the py311 gate)
04:50 Task 13: implementer DONE ba83a992 (suite 6878 passed 1 skipped 8 deselected [pre-existing]; vitest 545; probe tests pass under a pytest-only py3.11 venv); reviewer dispatched (opus) ae23eca7f85678a31
04:52 Task 13: review Needs fixes — Important 1: test_mtime_replace_sets_mtime_before_rename does not pin the order (scratch mutants m1 drop pre-rename utime, m2 drop post-rename re-apply both survived); DROP_EXCL mutant m3 caught
- Ruling R15: Task 13 minors 1 (cross exits 0 with contended 0 — proves nothing at go-live), 2 (killed cross leaves the shared lock), 3 (non-ENOENT OSError on contender read swallowed — add an unreadable counter, SMB EACCES), 4 (dead worker hangs parent ~6 min on queue.get), 5 (no --n/--workers validation; workers<2 races vacuously) ride fix round 1 — this script's only purpose is go-live evidence in Task 19, and a probe that passes vacuously defeats it; all small — cost if wrong: a larger fix diff on a test-only script.
Task 13: minor (deferred): re-check compares whole seconds vs writer's st_mtime_ns (equivalent for the integer target)
04:52 Task 13: fix round 1 dispatched (resume implementer sonnet): Important 1 + R15 minors 1-5
04:56 Task 13: fix round 1 implementer DONE 33198e55 (probe tests 14, py311 14, suite 6886 passed 1 skipped); re-review dispatched (opus) a8ba9e25c7e3d3708. Implementer concern: one cross side can exit 3 while the other contended; go-live pass = neither side 1 and at least one 0 (documented)
Task 13: fix round 1/5 (6 addressed, 0 open; commits ba83a992..33198e55) — re-reviewer's own m1/m2 mutants caught
Task 13: minor (deferred, FINAL REVIEW should fix): stale .lock-race-<tag> makes cross pass vacuously (acquired 0, contended N, both rc 0 — measured); fix: exit 3 when acquired==0 or refuse a pre-existing lock before --start-at
Task 13: minor (deferred): test_race_warns_when_nothing_contended is vacuous (--n 1 always contends; warning-removal mutant survived 5/5)
Task 13: minor (deferred): cmd_race early return 2 terminates workers without join (harmless)
Task 13: ⚠️ for llama-player (Task 19, not ours): plan Task 19 Step 4 (plan:860) says "started within a few seconds of each other" — runbook doesn't mention --start-at or the exit-3 pass rule
Task 13: complete (commits f0b480ce..33198e55, review clean after fix round 1)
04:59 Task 14: final whole-branch review dispatched (opus) a36058009af6ce9f8 over b7ec7bda..33198e55 (465 KB diff) with carry-over triage file orch-r1/final-carryovers.md; py3.11 gate running in background (log orch-r1/py311-gate.log, venv /tmp/programs-py311)
04:59 py3.11 gate PASSED at 33198e55 (Python 3.11.15, /tmp/programs-py311): transmitter 994 passed 1 skipped; scripts/test_station_probe.py 14 passed (log orch-r1/py311-gate.log)
05:05 Task 14: final review "With fixes" — MUST-FIX T9-N1, T9-N2 (+ before-line title in record.jsonl); SHOULD-FIX T13b (stale-lock vacuous cross pass), T11a/T11i (atomic-rename doc claim false for deliver), T11g (flock wording), T12b (wrap), T4b optional (tab a11y). Verdict file t14-final-review/handback.md
- Ruling R16: final fix wave takes MUST-FIX + SHOULD-FIX except T4b (optional tab a11y: needs npm run pages + full smoke on page code no other fix touches; stays a deferred minor for a later page change) — cost if wrong: lineup tabs ship with incomplete ARIA (functional, screen-reader naming weaker).
05:05 Task 14: fix wave dispatched (opus) ac2655aad6bf567c6, FIX_BASE 33198e55: N1, N2(+record title), T13b, T11a/i, T11g, T12b
05:14 Task 14: fix wave DONE_WITH_CONCERNS b8cecddf, ac65114f, 434c2637 (suite 6889 passed 1 skipped; vitest 545; probe 17 on 3.14 and 3.11); concern: added cross pacing (loser got acquired 0 in 3/3 real runs, would fail exit-3 rule); scoped re-review dispatched (opus) a719f7ca8ad996c8b
05:16 Task 14: fix wave re-review — all 6 findings ADDRESSED, no new Critical/Important; cross pacing judged sound (DROP_EXCL under paced two-sided cross: doubles 22/26, 35/18, 25/31)
Task 14: parked — no test pins paced cross detecting doubles under DROP_EXCL (re-reviewer verified by hand) — Ruling: real, deferred; no second fix wave per SDD; cheap follow-up before Task 19 relies on cross
Task 14: parked — restore snippet swallows every fchmod OSError (writer tolerates only _FCHMOD_REFUSED) — Ruling: harmless for a hand restore (worst case server default mode)
Task 14: parked — restore snippet leaves its temp on write/fsync error — Ruling: documented known cost; retitle --dry-run lists strays
Task 14: deferred (R16) — T4b lineup tab ARIA markup
05:19 Final verification (controller-run at 434c2637; imports resolve in worktree): ./.venv/bin/pytest -q 6889 passed 1 skipped 8 deselected 26 warnings (baseline); antenna npm test 545/545 (27 files); py3.11 (/tmp/programs-py311, 3.11.15) transmitter 994 passed 1 skipped, scripts/test_station_probe.py 17 passed. Tree clean. Log orch-r1/final-verify.log
Task 14: complete (final review With fixes -> fix wave 33198e55..434c2637, scoped re-review clean; 3 parked, T4b deferred)

## FINISH (at finish menu; nothing merged or pushed)
- Branch programs-lineup head 434c2637, tree clean. Tasks 1-14 complete.
- Final verdict: t14-final-review/handback.md; fix-wave re-review: t14-rereview/handback.md (sha256s in the finish report).
- Rulings by orch-r1: R13 (llama-player's), R14, R15, R16; parked: 3 (Task 14). Predecessor R1-R12 stand.
- Workspace NOT deleted (merge not done; the root decides).
05:19 tick e166a594 deleted; armed-7a0126d5 removed; armed-global kept (armed-9d247c76 still present)
