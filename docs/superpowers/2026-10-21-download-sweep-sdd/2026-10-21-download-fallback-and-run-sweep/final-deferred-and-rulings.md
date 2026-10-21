# Deferred minors and rulings for the final whole-branch review

## From predecessor ledger (Tasks 1-3)
- Ruling: one combined Opus task reviewer per task (spec verdict + quality verdict, SDD v7 template) satisfies "spec-compliance and code-quality review on Opus" — both verdicts required — cost if wrong: one extra review seat per task.
- Ruling: SDD progress ledger = this file; briefs/packages in .superpowers/sdd/2026-10-21-download-fallback-and-run-sweep/; implementer report file = $D/<task>/handback.md (mandate 1) — cost if wrong: none (paths only).
- Task 1: minor (deferred): deadline lower bound unpinned (scratch mutant >=10.0 survives) — Ruling: fold into Task 2 dispatch (same file/tests) — cost if wrong: a few lines in T2's diff.
- Task 1: minor (deferred): metadata fetch httpx non-transport error can escape download_file (unreachable in prod) — Ruling: fold into Task 2 dispatch.
- Task 1: minor (deferred): DecodingError / non-dict metadata / mid-write OSError untested; 3xx non-retryable (disclosed); test hard-codes 1.0..4.0; rng "or" idiom.
- Ruling: accept the "owed" attempt after a trickle abandonment (skips the deadline check once) — the literal reading strands a file the abandonment promised to continue; bounded to one post-deadline attempt; spec §1 amended (d0e08c4) — cost if wrong: one extra attempt (~a transfer) past 60 s.
- Task 2: minor (deferred): transport error mid-append discard unpinned (mutant wrote=wrote survives) — Ruling: fold test into Task 3 dispatch (same test file).
- Task 2: minor (deferred): stitched md5 failure excludes only the finisher; if the prefix copy was the corrupt one the good finisher is lost for this call (liveness only; plan-mandated by test) — for final review.
- Task 2: minor (deferred): _continues does not check range end M==size-1 (short 206 appended, md5 catches, server excluded) — for final review.
- Task 2: minor (deferred): no test for '*' total with size known; condition 4 only on first request.
- Task 3: minor (deferred): _setup slots wiring unpinned (cli.py:125); duplicated _attempt call branches; _throttle sleeps inside slot (comment); non-FIFO polling (documented in T8); in-flight wait disables trickle after long slot wait; cap test detects breakage only after 30 s guard.
- Task 3: minor (deferred): os.close on the non-BlockingIOError path is unpinned.
Deferred minors for the final review: see "minor (deferred)" lines (T1 x4, T2 x4 incl. stitched-blame and range-end, T3 x7).

## From orch-r1 ledger (Tasks 4-8)
- Task 4: minor (deferred): failure_record trusts a naive caller-supplied now (no caller passes one); --no-pacing RateLimited site untested for kind; new test imports mid-module in test_sessions.py.
- Ruling: fold T4 minors "stale cli.py:560 comment {show, error}" and "pace-loop failure test should assert error startswith 'download of '" into Task 5's dispatch (same files) — cost if wrong: two extra lines in T5's diff.
- Task 5: minor (deferred, RECOMMEND FIX in final wave): pacing-state.json-absent assertions are vacuous (record is monkeypatched) in both no-boundary tests; already-packaged test duplicates download-only — replace with a mixed run ["a","b"], llm=lambda p: p=="a" → exactly one boundary (pins per-show calls_before vs run-level baseline, LLM-spend strict surface).
- Task 5: minor (deferred): _CountedProviders.get/__contains__ route through __getitem__ (creates defaultdict keys; test-only); _CountedProvider.__getattr__ recursion if built without __init__ (no copy/pickle anywhere).
- Task 6: minor (deferred, for final review): a running row in run list still prints the previous attempt's outcome + failure lines (spec silent; suggest suppress or "last attempt:" prefix in text only).
- Task 6: minor (deferred): RunWorkspace.lock unused (literal duplicated in locks.py); _run_locked extra blocking= kwarg (superset, accepted by reviewer); --name naming an existing regular file prints "no longer exists".
- Ruling: fold T6 minor "run list docstring should say 'or running'" (cli.py:1078) into Task 7's dispatch (T7 edits _print_sessions/run list area) — cost if wrong: one line.
- Task 7: minor (deferred, RECOMMEND FIX in final wave — strict surfaces): (1) body-raised Locked/RunMissing read as lock refusal (sweep: crash marker + reported 'running', exit 0) — separate acquisition from body in _resume_run; (2) one malformed updated_at crashes the whole sweep (_instant fromisoformat) — fall back on ValueError/TypeError; (4) turned-live test stubs run_lock instead of a real flock held by r1's stub.
- Task 7: minor (deferred): untested interpretations (unparseable resume_after, malformed failures -> needs attention); session annotation str -> str | None (cli.py:127); exit-only crash marker terse (as specified).
- Task 8: minor (deferred): README:152 "incomplete from a crash" should say "a killed process" (caught exceptions write a needs-attention marker); CLAUDE.md:94 marker-less eligibility omits criteria-without-request; :910 "marked not workable" (archive.org marks); :921 total checked only when size known; :457 ambiguous "--json".
