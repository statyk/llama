# SDD ledger — plan: docs/superpowers/plans/2026-10-31-emcee-batch.md
Peer d3739b43-d932-4561-950a-b0857df39b86, base 99606b44. Parent llama-62. Baseline: packages/emcee 1039 passed.

## Preflight scan
| rows | produces / consumes | found |
|---|---|---|
| T1 self | prompt edits vs test_scriptwrite 358,367-8 | consistent; new section sits between Names and {{narration_note}} |
| T2 self | tests vs text; clear step vs failure safety | consistent |
| T3 self | reuses status --drifted; requires T2 selection state | consistent |
| T4 self | --tts overrides vs resolve | consistent |
| T5 self | voiced_on carry | consistent, see T2/T5 |
| T6 self | window constants, utime | consistent |
| T2/T3 (cli, audio, station) | T3 consumes keep_script path, kept-script reason, presenter check | ordered 2 before 3 |
| T2/T4 (cli, process) | disjoint commands | none |
| T2/T5 (cli, process) | T5 reads raw dj_audio before clear in the same step T2 changes; rendered set must exclude adopted clips | ruling R1 |
| T4/T5 (process) | disjoint functions | none |
| T5/T6 (models) | T6 writes keys T5 defines | ordered |
| T1 / all | prompt only | none |

Ruling: R1 a failed attempt clears dj_audio, so a retry that renders nothing has no block to carry: voiced_on and voiced_before stay null, and the backfill treats null as unset — the plan says "read before the clear", and no other source exists — if wrong, one package has a null date until a re-render or the backfill.
Ruling: R2 ledger lives at $D/orch per the brief, not the skill's sdd-workspace path; task briefs/packages stay in the skill's workspace dir — brief outranks skill — no cost.

## Escapes
(none)

## Log
23:50 Task 1 implementer dispatched on Opus (t1-impl), base 99606b44
00:04 t1-impl DONE_WITH_CONCERNS 98d39cc0, 1044 passed; sample gate reached
00:05 gate reported to llama-62; t1-review (Opus) and t2-impl (Opus) dispatched, Task 2 base 98d39cc0
00:07 t1-review: spec OK, quality Approved, 0 Critical/Important. Task 1 held open at the gate for wording only.
Task 1: minor (deferred): prompt example "a title I can't say on the air" invites catchphrase (plan-mandated; at gate)
Task 1: minor (deferred): script_guard has no prose check for profane titles (out of scope; operator decision)
Task 1: minor (deferred): "character" wording reaches the house narrator, unsampled
Task 1: minor (deferred): approval/listen-for test pins partial; revisit once wording settles
Task 1: minor (deferred): rules.count(" - ") == 6 brittle
Task 1: unverified: Zevon call took 150 s, may be a guard retry, so 6 or 7 calls (internal retry, not iteration)
00:13 t2-impl DONE_WITH_CONCERNS 00fe11a9..29228539, re-run tests; t2-review dispatching (Opus)
00:18 t2-review: spec OK, quality Approved, 2 Important both plan-mandated.
Ruling: R3 retry line prints only from the unlink onward, not on preflight/adoption failures — those change nothing and bare --keep-script would drop --fresh — if wrong, one extra printed line is missing.
Ruling: R4 code stands on the null-dj_audio presenter pass — the plan says "When dj_audio is null the check passes" and no record survives the clear — if wrong, a move between failure and retry voices a persona script in another voice; fix is a warn/refuse in move. Surfaced to operator.
Ruling: R5 code stands on llama deliver overwriting the failed-attempt state — the plan records it as a Limit, documented in README and CLAUDE.md — if wrong, a kept script at a destination is lost on deliver; fix is one condition in _destination_is_voiced. Surfaced to operator.
Task 2: minor (deferred): _process_one docstring "a bad bed" true only for keep+fresh (strict surface wording)
Task 2: minor (deferred): adopt_clips trusts disk over text; off-route retry can adopt old-wording clip after a repair
Task 2: minor (deferred): warning is keep+fresh only; bare --keep-script on partial-match packages can mix takes unwarned
Task 2: minor (deferred): invalid dj_notes + null dj_audio reads kept script; refusal points to plain voice
Task 2: minor (deferred): test_a_backend_change_warns_too has no exit-code assertion
Task 2: complete (commits 98d39cc0..29228539, review clean, 2 plan-mandated rulings)
00:19 t4-impl (Sonnet) dispatched, base 29228539
00:21 t4-impl DONE_WITH_CONCERNS f81bc872
00:22 llama-62 relayed operator's gate outcome: wording changes, second sample run; R3, R4, R5 accepted, R4 documented as a limit beside R5, no llama change. Gate stays with operator. Brief: /Users/shawn/projects/llama/.claude/worktrees/emcee-batch/.superpowers/sdd/2026-10-31-emcee-batch/task-1-wording-brief.md
00:22 t1-wording (Opus) dispatched
00:23 t4-review: spec OK, quality Approved, 0 Critical/Important.
Task 4: minor (deferred): unpinned preset presenter under mlx_audio house with --tts voxtral gets a false "preset voice for mlx_audio" message (refusal still safe)
Task 4: minor (deferred): refusal hint is a dead end when target is mlx_audio (--voice is refused next); should use clone-only message
Task 4: minor (deferred): house-clone branch process.py:214, presenter-clone on elevenlabs and presenter-clip no transcript untested
Task 4: minor (deferred): stale wording process.py:164, cli.py:733,777, resolve.py:40, cli.py:811 house_mlx name
Task 4: minor (deferred): cli.py:828 conditional kwargs exist only for a test seam
Task 4: minor (deferred): no-flag test only covers --voice path
Task 4: complete (commits 29228539..f81bc872, review clean)
00:24 t5-impl (Sonnet) dispatched, base 2516dc89
00:29 t5-impl DONE ba7d0f92, full suite claimed 6475 passed
00:31 t5-review: spec OK, quality Approved, 0 Critical/Important.
Task 5: minor (deferred): README says --keep-script --fresh carries both dates; it stamps today because it renders the named clip (fix in final wave, plus a test)
Task 5: minor (deferred): _clear_and_process voiced default could silently drop dates; make required
Task 5: minor (deferred): manifest_voiced_on/before near-duplicate helpers
Task 5: complete (commits 2516dc89..ba7d0f92, review clean)
00:31 t6-impl (Sonnet) dispatched, base ba7d0f92
00:34 t6-impl DONE cf726ca3
00:35 t1-wording DONE_WITH_CONCERNS 2516dc89; second samples at /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-batch/d3739b43-d932-4561-950a-b0857df39b86/scratchpad/t1-samples/v2/side-by-side.md; Zevon took 2 LLM calls (guard retry), so 7 calls in all. Gate stays with operator.
Task 1: minor (deferred): script_guard refuses a correctly named song inside a merged track, colliding with "Name every other title plainly"; a second miss fails the show (out of scope, operator decision)
00:36 llama-62: operator accepts wording as of 2516dc89, no more wording or samples; review it now. New Task 1b (Sonnet) after t6-review, before Task 3. R3-R5 stand. Brief: /Users/shawn/projects/llama/.claude/worktrees/emcee-batch/.superpowers/sdd/2026-10-31-emcee-batch/task-1b-brief.md
00:38 t1-wording-review: spec OK, quality Approved, 0 Critical/Important.
Task 1: minor (deferred): "Name every other title plainly" vs vague note "Do NOT name specific songs"; low risk (1 package), unmeasured, no precedence test; ruled wording, operator's call
Task 1: minor (deferred): "stories, asides, jokes and memories" pulls against no-invented-history text; operator watch item
Task 1: minor (deferred): closing sentence of Tell don't gush has no positive test pin
Task 1: complete (commits 99606b44..98d39cc0 + 2516dc89, operator accepted wording, review clean)
00:38 t6-review: spec OK, quality Approved, 0 Critical/Important. Measured read-only: 328/328 reproduce, all clips resolve, 118 voiced_before / 210 voiced_on.
Task 6: minor (deferred): backfill changes manifest sha, so bulk_apply unmark refuses 'station copy changed since marking' on 136 marked voiced shows; loses that batch's reversal; tell operator before --apply, document
Task 6: minor (deferred): apply_one trusts classification from earlier read; recheck block in apply_one (strict surface, final wave)
Task 6: minor (deferred): test gaps: pre-existing voiced_before, formatting skip, no trailing newline, no clips, unreadable manifest, print assertion
Task 6: minor (deferred): dry-run counts can overstate --apply; success line prints before write
Task 6: minor (deferred): refusal mid-run drops summary
Task 6: complete (commits ba7d0f92..cf726ca3, review clean)
00:39 t1b-impl (Sonnet) dispatched, base cf726ca3
00:39 llama-62: GDTRFB seed row rides with Task 1b; sent to t1b-impl, brief appended
00:41 t1b-impl DONE 4c8f7dd0, b2fdd589
00:45 t1b-review: spec OK, quality Approved, 0 Critical/Important.
Task 1b: minor (deferred): 'w/' (64 titles) splits, so a guest name becomes known and the song stays refused; brief asked text uses be handled deliberately (final wave)
Task 1b: minor (deferred): (?<!\d) lookbehind protects nothing, declines 3 true merges, unpinned
Task 1b: minor (deferred): '->' alternative dead; docstring 'can never' too strong
Task 1b: minor (deferred): E:/parenthetical components and ' - ' merges still refuse; a second miss can fail those shows (scope note)
Task 1b: minor (deferred): GDTRFB -> speaks a stray '-' (pre-existing symbol pass)
Task 1b: complete (commits cf726ca3..b2fdd589, review clean)
00:45 t3-impl (Sonnet) dispatched, base b2fdd589
00:49 t3-impl DONE 62c646eb, b03ef08e
00:53 t3-review: spec partial (empty-selection note), quality Approved, 0 Critical/Important.
Task 3: minor (deferred): count_clips_to_render tolerates corrupt segments.json but render raises after the clear; plan promises a re-render for a package that will fail (final wave: at least docstring)
Task 3: minor (deferred): invalid presenter file aborts mid-scan, untested
Task 3: minor (deferred): no bed test; no test that plan N equals clips synthesized
Task 3: minor (deferred): lexicon re-read per selected package
00:53 t3-fix1 DONE; Task 3: fix round 1/5 (2 addressed pending re-review)
00:54 t3-rereview, final-review dispatched (Opus) at 6706ca85; full suite running
Task 3: fix round 1/5 (2 addressed, 0 open; commits b03ef08e..6706ca85)
Task 3: complete (commits b2fdd589..6706ca85, review clean)
00:55 full suite at 6706ca85: 6513 passed, 1 skipped, 8 deselected, 26 warnings in 78.32s (0:01:18)
01:02 final-review: Ready to merge with fixes; 0 Critical, 2 Important. Fix wave brief: /Users/shawn/projects/llama/.claude/worktrees/emcee-batch/.superpowers/sdd/2026-10-31-emcee-batch/final-fix-brief.md
Ruling: R6 'run --keep-script' keeps sweeping ready all-match packages (94 of 328 measured, a clear and rewrite for nothing, manifest mtime moves) — plan says every package, task is lowest priority — if wrong, a needless off-air window on those shows; fix is a skip when count is 0 of M. Surfaced to operator.
Ruling: R7 notes 6 and 7 of final review (--profile false note; house under ? in backfill counts) stay deferred — display only — cosmetic.
01:03 final-fix (Sonnet) dispatched, base 6706ca85
01:03 llama-62: R6 reversed by parent: add the skip. R7 stands. Add E: prefix to guard parts. Sent to final-fix as items 13, 14.
Ruling: R8 the 0-of-M skip applies to READY packages only — a pending or failed-attempt package has no usable dj_audio, so skipping would strand it at 0 of M — if wrong, a pending all-match package gets a rewrite it would have needed anyway.
01:08 final-fix DONE a10db854..e1f67e76
01:09 full suite at e1f67e76: 6532 passed, 1 skipped, 8 deselected, 26 warnings in 77.84s (0:01:17)
01:12 final-rereview: 14/14 addressed, no new Critical/Important. Stopped at the finish menu at e1f67e76.
Residual (deferred): apply_one stat/read/write not wrapped; a vanished manifest or SMB OSError aborts the run (idempotent re-run)
Residual (deferred): no committed test for pending with a live block at 0 of M (probed, passes)
Residual (deferred): --drifted on a ready no-TTS-record package at 0 of M now skips, so it is listed each run
Residual (deferred): house twin of the false preset message (process.py:228)
