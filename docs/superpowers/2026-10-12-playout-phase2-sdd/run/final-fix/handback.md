# final-fix handback (Sonnet 5.5)
Status: DONE. Commits: 93cbfba (antenna F1,F2,F3,F11), f6c28fe (transmitter F4,F8,F9,F10), 6b42bde (docs F5,F6,F7,F12 + dead-clock-check in 7.1).

## Per finding
- F1 antenna/test/guard.test.ts (end of "races and failure paths" describe): "blind still trips 6 h after the last success while state/budget.json gets keep throwing". Test-only on correct code, so green on HEAD; RED = mutant A (scratch copy, guard.ts:282 `if (!budgetReadFailed) doc = applyBlindRule(...)`): `x blind still trips 6 h ...` failed. Green with real src.
- F2 antenna/public/player.js (~125): AbortSignal.timeout guarded; signal passed only when defined. build-pages --check passes (player.js not inlined). No test possible (player.js has none).
- F3 antenna/test/alerts.test.ts (4th test of "a failed fresh alert over a still-active delivered episode..." describe): P10. Mutant M1' (alerts.ts:349 `delivered: o.kind === "alert" ? !!prev[o.key]?.active : wasDelivered(prev[o.key])`) -> `x P10 ...` failed; green on HEAD.
  Mutants A + M1' together on guard+alerts files: 2 failed, exactly those two tests (baseline with real src 81 passed).
- F4 test_systemd.py comment "far in the past" -> "far in the future".
- F5 docs/playout-setup.md: spend checklist step 2 and section 7 guard bullet now say raise must exceed projected AND actual/0.9 (trip = actual >= 90% OR projected >= 100%).
- F6 docs: step 3 says 50% alert at $7 expected; 80% only if max(actual, projected) >= $5.60, absence not a failure.
- F7 docs 6.1 step 3: App Password pasted without spaces.
- F8 service.py: step renamed "dead-clock-check" (+comment). Test test_a_monitor_that_raises_alerts_the_event_code_not_the_level_code (test_service.py). RED: scratch copy with step name reverted ("dead-clock"), PYTHONPATH shadowing proven (transmitter.__file__ in the scratch tree): failed, `ALERT dead-clock: RuntimeError: boom`. Green on HEAD. Runbook 7.1 event-code list gains dead-clock-check.
- F9 publish.py guard cache: absent->False, bool->value, anything else present->True (non-dict too). guard_blocks_publishing's return/gating unchanged; existing test untouched and green. New parametrized test_the_guard_cache_reads_offair_like_the_worker (7 cases); RED before the fix: 4 cases failed ("yes", 0, {}, [1]).
- F10 alerts.py: `subject.isascii()` predicate, else `Header(subject,"utf-8").encode(maxlinelen=0)`. test_alerts.py: the existing café assertion (which pinned the old raw-latin-1 behaviour) was rewritten to expect an RFC 2047 ASCII title that decodes to "café: x", plus a long non-ASCII title (no CR/LF, round-trips). RED before the fix: test_ntfy_title_is_rfc2047_encoded_when_not_latin1 failed on `'café: x'.isascii()`.
- F11 guard.ts: comment only on mergeLostRace.
- F12 docs: way back = "redeploy with the committed wrangler.jsonc (its output ends with `schedule: * * * * *`)".

## Counts
- antenna: `npm test` 217 passed (14 files, build-pages check ok); `npx tsc --noEmit` clean.
- transmitter py3.14 (.venv): 451 passed, 1 skipped. py3.11 (.venv311): 451 passed, 1 skipped.
- docker info OK; Debian-12 gate: 452 passed (exit 0).
- Email grep (`grep -nE ... docs/playout-setup.md | grep -v example/alerts@lma-radio.com`): no output.

## Deviations / concerns
- F10: modified an existing test assertion (old latin-1 café pin) because F10 deliberately changes that behaviour.
- F9: a JSON `null` offair.json body reads as absent via get_json (cannot distinguish from missing); the Worker would treat null as corrupt->off-air. Edge only, alert-only surface (dead-clock noise), not spend.
- F1/F3 have no literal RED on HEAD by nature (tests pin correct code); RED evidence is the scratch-copy mutants. Antenna src changed only in player.js and a guard.ts comment.
- Scratch copies in the session scratchpad; live worktree clean after commits.
