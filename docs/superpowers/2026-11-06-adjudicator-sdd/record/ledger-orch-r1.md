# SDD ledger — plan: docs/superpowers/plans/2026-11-06-adjudicator.md
# orch-r1 (successor peer ab20f34c-4f80-470f-a514-bcece5dc8de7). Predecessor ledger: $D/orch/ledger.md (Tasks 1-7 complete, HANDOFF CO1-CO6).

## Escapes
- my post-opus restore check looked only for .txn/.audio-aside and missed empty created dirs (parent caught via path list).
- t11b-quality read ~/.llama/ledger.jsonl read-only (python, no CLI, no write) to measure exposure; reported to parent.

## Log
2026-11-07 08:44 start at e57be91c; meter 5h 72% (resets 09:10), 7d 8%. Shared W files reused; implementer-common Claude-Session line updated to this session.
Ruling: implementer-common.md attribution URL switched to this session's — commits are made under this orchestrator — cost if wrong: cosmetic.
2026-11-07 08:44 Task 8: dispatched t8-impl (Sonnet) base e57be91c, budget 75; carries CO1, CO3
Task 8: implementer DONE_WITH_CONCERNS ae0739ce (7334 passed); no RED run (tests written after code), no mutation run; render_proposal slug = slugify(show.performance_id); _interactive() seam for TTY.
Task 8: dispatched t8-spec (Opus)
Parent directive (llama-adjudicator): (1) Tasks 10/11 briefs must require the RED (failing-test) output pasted into handback.md before any implementation commit; a handback without it is incomplete, not DONE. (2) spec reviewer must check slugify(performance_id) == canonical shows/<slug>; use an existing resolver if one exists. -> (2) sent to t8-spec via SendMessage.
Task 8: spec review ✅ (t8-spec Opus), 0 Critical/Important; 4 Minor: bundle-OSError test doesn't assert show 2 judged; pause/RateLimited-after-a-judged-show "report so far" untested; held_proposal edit lines also print evidence quotes (Extra); run: slug re-derived.
Task 8: slug check: slugify(performance_id) == shows/<slug> for every pipeline-made show (workspace.py:131), but CatalogEntry.slug is the dir name — second source of truth.
Ruling: render_proposal takes the slug from the caller (CatalogEntry.slug) — keyword `slug` added to the plan's signature — parent directive "use the existing resolver" + spec has no signature; one source of truth for the dir name — cost if wrong: a signature differing from the plan text, Tasks 10 callers must pass entry.slug.
Ruling: ⚠️ production sweep of ~/.llama/shows dir-name vs performance_id not run — moot once slug comes from entry.slug — cost: none.
Ruling: spec minors 1-2 (assert show 2 judged; pause/RateLimited after one judged show prints that report) into the fix round; minor 3 (held_proposal evidence lines) kept — strictly more information, pinned — cost: a layout line beyond the brief.
Task 8: dispatched t8-quality (Opus) incl. ~6-mutant audit
Task 8: quality review Needs fixes (t8-quality Opus): 4 Important (I1 RateLimited break MISSED, I2 PauseUntil break MISSED, I3 CLI voiced() wiring MISSED, I4 test_force_rejudges doesn't exercise --force); 13-mutant audit 10 CAUGHT / 3 MISSED; 5 Minor.
Ruling: quality minors m1 (accept preview gated on an acceptable proposal; public runner.accept_verdict), m2 (accepted changes under own header `accepted track-list changes:` — auto-applied lists only gate-applied), m3, m4 (OUTCOME_ORDER in runner), m5 into fix round 1 — cheap, operator-facing — cost if wrong (m2): one header beyond the brief.
Task 8: fix round 1 sent to t8-impl (Sonnet, resumed), FIX_BASE ae0739ce; findings $W/task-8-fix1-findings.md; RED evidence required per test item.
Task 8: fix commit eb8b7384 (7338 passed); RED evidence via scratch mutants for I1-I4, S1, m2; SLUG by new test vs old code. render_proposal(rec, show, *, slug) — `show` now unused, kept for the plan signature.
Task 8: dispatched t8-rereview (Opus) incl. I1/I2/I3 mutant re-run
Task 8: fix round 1/5 (12 addressed, 1 open — m1 render-fails half regressed: render failure applied an unconfirmed proposal; commits ae0739ce..eb8b7384); re-reviewer mutants I1/I2/I3 now CAUGHT.
Ruling: a proposal render failure never applies, even under --yes; outcome NO_PROPOSAL "proposal could not be rendered: <exc>" — confirmation surface, fail closed — cost if wrong: an operator with a bad record must fix it by hand before accepting.
Task 8: fix round 2 sent to t8-impl (Sonnet, resumed), FIX_BASE eb8b7384; R1 + deferred re-review minors R2, R3.
Task 8: fix commit 6e2e3af1 (7340 passed); R1 RED against eb8b7384 both variants (accept_proposal called); I3 mutant re-run still red after R2.
Task 8: dispatched t8-rereview2 (Opus) incl. R1-guard mutant
Task 8: fix round 2/5 (3 addressed, 0 open; commits eb8b7384..6e2e3af1); R1-guard mutant CAUGHT.
Task 8: minor (deferred): cli --accept reads the record without ctx.sink's path while runner.accept_proposal reads _record_path(ctx, entry); agree only because CLI never sets sink.
Task 8: minor (deferred): render_proposal's `show` parameter unused after SLUG (kept for the plan signature).
Task 8: complete (commits e57be91c..6e2e3af1, review clean)
Task 9: dispatched t9-impl (Opus) base 6e2e3af1, budget 100; carries CO2, CO3; RED-pasted-before-commit required; own 4-mutant check
Task 9: implementer DONE_WITH_CONCERNS ef494b0e (7374 passed); RED pasted pre-commit (31 failed/3 passed); 7 own mutants CAUGHT.
Ruling: pause exit code — "1 when any show failed" applied to adjudication-caused pauses, via _PausedExit(typer.Exit) so `run resume --all` doesn't mark a paused checkpoint as crashed; ordinary pacing pauses unchanged (exit 0) — brief's line sits under the adjudication hook; crash-marker safety — cost if wrong: an exit-code difference reviewers can flag.
Ruling: no-op checks (not held / record current / hook disabled) before the pacing gate — no LLM spend on a no-op, matches "no-op returning None" — cost: none.
Ruling: single redo hooks with the pre-redo CatalogEntry — adjudicator re-reads from disk — cost: none unless the redo renames the show dir (it cannot).
Task 9: dispatched t9-spec (Opus)
Task 9: spec review ✅ (t9-spec Opus), 0 Critical/Important, 3 Minor: unjudged line carries " (<detail>)"; gate PauseUntil after a processed show skips that show's pacing boundary; _PausedExit reading confirmed defensible.
Task 9: ⚠️ resolved by controller: runner re-raises RateLimited on every path (runner.py:256, 278, 305, 413 all `raise`).
Ruling: ⚠️ exit-code scope stays adjudication-only (my earlier ruling) — changing every checkpointed _execute pause's exit code is out of Task 9's scope — cost: inconsistent exit codes inside one run, recorded for final review.
Ruling: keep " (<detail>)" on the unjudged line — the rate-limit reason helps the operator; prefix is the brief's — cost: a literal-match difference.
Ruling: gate-PauseUntil boundary skip goes into the quality fix round if one happens (record the boundary for a fully-processed show before breaking on a gate pause; RateLimited keeps the refused-show exclusion), else deferred — cost: one show's cost missing from EWMA learning per pause.
Task 9: dispatched t9-quality (Opus) incl. ~5-mutant audit
Task 9: quality review Needs fixes (t9-quality Opus): 2 Important (I1 deferred-pass adjudication pause untested — Q7 MISSED; I2 watermark `+ judged` untested — Q6 MISSED); 8-mutant audit 6 CAUGHT / 2 MISSED; conftest fixture proven load-bearing (228 calls / 15 hook entries from 13 pre-existing tests when neutered, 0 with it); 3 Minor.
Task 9: fix round 1 sent to t9-impl (Opus, resumed), FIX_BASE ef494b0e; I1, I2, M2 (ruled: record boundary on gate PauseUntil), M1 docstring.
Task 9: minor (deferred): conftest fixture uses raising=False (covered by test_config_default_enables_hook on rename).
Task 9: fix commit 66646b19 (7378 passed); RED: M2 test vs ef494b0e, I1 under Q7, I2 under Q6.
Task 9: dispatched t9-rereview (Opus) incl. Q6/Q7/M2 mutant re-run
Task 9: fix round 1/5 (4 addressed, 0 open; commits ef494b0e..66646b19); re-reviewer mutants Q6, Q7, M2a, M2b CAUGHT.
Task 9: minor (deferred): cli.py:704 `ran` term redundant (mirrors :709); deferred-pass gate pause records no boundary (consistent with cli.py:738-742 rule).
Task 9: complete (commits 6e2e3af1..66646b19, review clean)
Task 10: dispatched t10-impl (Sonnet) base 66646b19, budget 60; carries CO4, render_proposal slug kwarg, accept_verdict reuse, Task-8 render-failure rule (no [a]); RED-pasted-before-commit required; 4-mutant check.
Ruling: triage applies Task 8's render-failure rule — a proposal that cannot render offers no [a] — same confirmation surface — cost: operator falls back to llama adjudicate.
Task 10: implementer DONE e66b9a30 (7392 passed); RED pasted pre-implementation (11 failed); 4 own mutants CAUGHT; did not share the `acceptable` helper (accept_verdict returns a verdict for propose-only-only records, triage adds an applicable-edits check). Stray red.txt/full.out in t10-impl dir (mandate 2 deviation, harmless).
Task 10: dispatched t10-spec (Opus)
Task 10: spec review ✅ (t10-spec Opus), 0 Critical/Important; Minor: brief test name differs (assertion stronger, new name); slug=entry.slug unpinned by any test; Task 8's `acceptable` prompts for stale/propose-only-only records that accept_proposal then refuses (outcome-safe).
Ruling: one shared acceptability predicate (current + accept_verdict + at least one non-propose-only edit) used by both triage [a] and `adjudicate --accept`'s prompt gate; plus a test pinning slug=entry.slug — into Task 10's fix round (it edits cli.py), or a dedicated fix if quality is clean — cost: none; operator stops seeing a useless prompt.
Task 10: dispatched t10-quality (Opus) incl. ~4-mutant audit
Task 10: quality review Needs fixes (t10-quality Opus): 1 Important (CHANGED re-entry unpinned — M5 MISSED); 5-mutant audit 4 CAUGHT / 1 MISSED; Minor: accept_verdict error swallowed; accepted record may differ from rendered one; make_providers outside try; doubled wording; no re-deliver hint.
Ruling: shown == accepted — runner.accept_proposal(expected_at=) refuses when the stored record's `at` differs from the rendered one; both triage and adjudicate --accept pass it — confirmation surface, fail closed — cost: one more runner kwarg beyond the plan.
Ruling: keep "skipped: changed changed…" wording (brief format) and no re-deliver hint in triage (consistent with other triage edits) — cost: cosmetic.
Task 10: fix round 1 sent to t10-impl (Sonnet, resumed), FIX_BASE e66b9a30; I1, P1, P2, S1, m1, m2.
Task 10: fix commit f2c2b28a (7401 passed); runner.acceptable_state(ws, rec) -> ok|stale|none shared by triage and --accept; accept_proposal(expected_at=); RED via pre-fix tests + mutants.
Task 10: dispatched t10-rereview (Opus) incl. M5 + expected_at mutants
Task 10: fix round 1/5 (6 addressed, 0 open; commits e66b9a30..f2c2b28a); re-reviewer M5 and P2 mutants CAUGHT.
Task 10: minor (deferred): acceptable_state judges currency via is_current(ws) re-reading disk rather than rec.digest vs show_digest (expected_at guards the apply).
Task 10: minor (deferred): adjudicate --accept `acceptable` closes over loop var `entry` (late binding).
Task 10: complete (commits 66646b19..f2c2b28a, review clean)
Task 11: dispatched t11-impl (Sonnet) base f2c2b28a, budget 75; RED-pasted required; 5-mutant check.
Ruling: Task 11 additions beyond the brief — compare.md tallies partial-tape-class shows the gate could not auto-apply with blocking reasons (CO5, parent's step-3 ask); select prints absolute show dirs (parent snapshots them); run refuses while llama OR emcee runs (parent stop rule) — cost: small script surface beyond the plan.
Parent directive (Task 11): run's llama/emcee refusal matches process NAME (campaign_gate machinery), never cmdline substring; must not self-match pilot/parent/wrapper shells; test pilot-only-running must not refuse. -> sent to t11-impl.
Task 11: implementer DONE c6d2e189 (7417 passed; 16 pilot tests); RED pasted (collection ModuleNotFoundError — per-test red via 11 mutants, all CAUGHT); process refusal via campaign_gate.tool_processes name match; dry-run records carry outcome dry-run so compare derives auto/held from gate fields.
Task 11: dispatched t11-spec (Opus)
Task 11: spec review ❌ (t11-spec Opus): 1 Important — compare never reports trial-apply results (rec["result"] unread; cost means mix trial and judge-only rows); Minor: no switch verdict trialled end to end in a test; no per-show cost rows; Extras (population.json, --config, --verdicts, resume) acceptable.
Ruling: ⚠️ pilot pacing — the pilot gets a resumable ceiling: `run --stop-at <pct>` (default 85) checks the injected meter's before-reading per show and stops cleanly (resume skips done slugs) instead of llama's full decide() — operator-sequenced pilot, parent watches the meter, 85% matches the run's stop band — cost if wrong: not literally the pacing gate the global constraint names.
Ruling: ⚠️ trial applies may leave cache downloads outside show dirs — cache, not library state; parent's snapshot covers the show dirs — cost: none.
Ruling: spec Important + both Minors go into the fix round together with the quality findings.
Task 11: dispatched t11-quality (Opus) incl. ~4-mutant audit
Parent ruling (Task 11 pacing): --stop-at is enough; check both windows — 5h default 85%, weekly default 80%, each overridable; meter read fails closed (unreadable or 'Showing last-known usage' / stale reading stops the run). Supersedes my --stop-at 5h-only ruling.
Task 11: quality review Needs fixes (t11-quality Opus): 6 Important (Q1 compare arm attribution M2 MISSED; Q2 strict switch clause M3 MISSED; Q3 cross-arm resume M1 MISSED; Q4 vanished show wedges resume; Q5 trial limit resets per resume; Q6 trial apply leaves ledger.jsonl modified); 5-mutant audit 2 CAUGHT / 3 MISSED; 8 Minor.
Ruling: Q6 in the pilot — snapshot+restore ledger.jsonl bytes around each trial show under the ledger lock (pilot refuses while llama runs); docs say snapshot ledger.jsonl too — cost: a concurrent llama started mid-pilot could lose a ledger row (refused at start only).
Ruling: Q6's production analogue — apply_verdict's non-trial restore paths (whole-show/coverage/re-hold failure after a redo that cleared the hold) also leave a `selected` ledger row for a show restored to held; show_unit has never covered the ledger (pre-existing class: reapply/fix restores). Not fixed in Task 11; flagged for the final whole-branch review and the parent — cost: `llama history`/played_ids list a held show as selected.
Task 11: fix round 1 sent to t11-impl (Sonnet, resumed), FIX_BASE c6d2e189: S1-S3, P1, Q1-Q6, m7-m14.
Parent directive: fix the production ledger-restore gap BEFORE PRE-PILOT as its own task (Task 11b) after Task 11 closes; Opus implementer, Opus spec + quality reviewers; RED + a mutation row (restore skips the ledger -> named test red); lock order show ⊃ ledger, never re-enter a flock; prefer a compensating row if the ledger is append-only; same mechanism for the pilot's trial restore.
Finding: the ledger is NOT append-only — ledger.py already has remove(pid) and remove_status(pid, status) (atomic rewrite under the ledger lock). So precise removal of the rows the restored unit added is consistent with existing writers; a compensating row would need a new status that played_ids/latest_dispositions don't know.
Ruling: Q6 dropped from the Task 11 fix round (sent to t11-impl); Task 11b fixes it at the root in apply_verdict's restore paths, trial restore included, and adds the pilot ledger byte-identity test — one mechanism — cost: none.
Parent ruling: precise removal (no compensating row); only rows the unit itself added — a foreign row for the same pid appended mid-unit must survive (test); zero-rows removal is a clean no-op (test). -> written into $W/task-11b-brief.md.
Task 11: fix commits c0ae8534, 1415002a (7436 passed; 35 pilot tests); Q6 dropped (never implemented); 20 mutants CAUGHT; switch trial test patches runner.evaluate for an auto gate (apply/coverage/restore real); m11 unreadable show.json still fails in iter_shows (out of scope).
Task 11: dispatched t11-rereview (Opus) incl. M1/M2/M3 + P1 mutants
Task 11: fix round 1/5 (S1-S3, P1, Q1-Q5, m7-m14 addressed, 0 open; Q6 ruled to 11b; commits c6d2e189..1415002a); re-reviewer M1, M2, M3, P1-None mutants CAUGHT.
Ruling: re-review minors (85/80 defaults unpinned from below; cost-table header mislabelled) ride with Task 11b, which edits the pilot tests anyway — operator's brake — cost: none.
Task 11: complete (commits f2c2b28a..1415002a, review clean)
Task 11b: dispatched t11b-impl (Opus) base 1415002a, budget 75; RED + 3 mutation rows required; + brake-default pins, cost header
Task 11b: implementer DONE 571f66fa, a0a579a1 (7454 passed); RED pasted pre-commit; 10 mutants CAUGHT (incl. the 3 required). Identity: rows of key (candidate pid, "selected", prov.run) absent before the unit, removed under the show lock before file restore; apply_verdict gains required ledger=. Minor: an absent ledger.jsonl becomes an empty file after restore.
Task 11b: dispatched t11b-spec (Opus)
Parent directive (11b): spec reviewer must state which same-key foreign writes the identity claim rules out, with call sites of every 'selected' writer and their locks; whether the test exercises the allowed case. -> sent to t11b-spec.
Task 11b: spec review ✅ (t11b-spec Opus), Minor only: KeyboardInterrupt during the ledger removal replaces the original exception (undo catches Exception); no same-key mid-unit foreign-row test (unreachable in-process). Same-key analysis: pipeline.py:176 is the only 'selected' writer and every process_show call holds this show's lock; concurrent `get` claims a unique run name; only a hand-renamed show dir (two locks, one pid) breaks the claim — show_unit limitation 4.
Ruling: renamed-dir precondition gets a docstring/docs note (into the quality round if any, else deferred); no same-key test (unreachable without a lock violation) — cost: a hand-renamed dir could mis-remove one ledger row.
Ruling: KeyboardInterrupt-during-removal minor into the quality fix round if one happens (catch BaseException in undo, re-raise after noting, keep the original as the primary) — cost: sub-ms window.
Task 11b: dispatched t11b-quality (Opus) incl. ~4-mutant audit
Task 11b: quality review Needs fixes (t11b-quality Opus): 2 Important (MB undo ordering/lock unpinned MISSED; MC/MF removal-failure note on refused/transient/trial unpinned MISSED); 6-mutant audit 3 CAUGHT / 3 MISSED; Minor: raw-byte identity vulnerable to concurrent re-serializing rewrite (0/7630 lines non-round-tripping today — reviewer read ~/.llama/ledger.jsonl READ-ONLY); long lines; absent ledger -> 0-byte file.
Ruling: identity via append-once — any pre-existing key row => removal no-op; else remove by parsed key — robust to re-serialization — cost: a hand-duplicated key row is never removed (it already wasn't added by the unit).
Ruling: absent ledger -> 0-byte file kept (readers treat it as empty), documented — cost: cosmetic.
Escape: t11b-quality read ~/.llama/ledger.jsonl read-only (no llama CLI, no write) to measure round-trip exposure — outside the "never run llama against ~/.llama" letter? It ran no CLI; reported to parent.
Task 11b: fix round 1 sent to t11b-impl (Opus, resumed), FIX_BASE a0a579a1; I1, I2, R1-R3, m4.
Task 11b: fix commit e32b405f (7462 passed); RED vs a0a579a1 for R1/R2; MB, MC, MF + MR1/MR2/MR2b CAUGHT. R2 design: KI during removal re-raised after restore/outcome; if RateLimited/ShowChanged was propagating, KI wins with original as __cause__.
Ruling: accept R2's KI-wins-when-propagating choice — Ctrl-C must stop the batch; the original survives as cause and the files are restored — cost: a rate-limit pause reason shows as cause, not primary, in a sub-ms window.
Task 11b: dispatched t11b-rereview (Opus) incl. MB/MC/MF/R1 mutants
Task 11b: fix round 1/5 (6 addressed, 0 open; commits a0a579a1..e32b405f); re-reviewer MB, MC, MF, MR1 CAUGHT.
Task 11b: minor (deferred): R2 propagating-Exception branch unpinned (MR2c MISSED, double fault: ShowChanged propagating + Ctrl-C in the rewrite -> batch continues).
Task 11b: minor (deferred): an interrupted log.warning inside undo()'s handler replaces the original (theoretical).
Task 11b: complete (commits 1415002a..e32b405f, review clean)
Final: dispatched final-review (Opus) over c251f440..e32b405f vs spec + deferred-minor triage (/Users/shawn/projects/llama/.claude/worktrees/adjudicator-impl/.superpowers/sdd/adjudicator-impl/../2026-11-06-adjudicator/deferred-minors.md, 45 lines) + ruling audit
Final review: Needs fixes (final-review Opus): 2 Important (I1 set_title rendered without its title; I2 failed/transient adjudication writes no record -> pipeline re-pays the LLM call every resume pass); 4 Minor; deferred-minor triage: defer all except T5 F3 (case-sensitive same-stem compare, fail-open); no ruling flagged wrong; partial-tape ruling and shown==accepted flagged for operator attention at the pilot.
Ruling: I2 — digest-keyed `failed` record on FAILED/transient outcomes (RateLimited and CHANGED still write nothing); pipeline hooks skip a current failed record; backlog `llama adjudicate` retries it without --force — bounds spend per digest, keeps the RateLimited constraint — cost: a transient network failure isn't retried by the pipeline until the show changes or the operator runs llama adjudicate.
Ruling: final fix wave = I1, I2, M1, M2, M4, F3, MR2c in ONE dispatch on Opus (strict surfaces, multi-file); M3 deferred (safe direction).
Final: dispatched final-fix (Opus) base e32b405f, budget 90; findings /Users/shawn/projects/llama/.claude/worktrees/adjudicator-impl/.superpowers/sdd/adjudicator-impl/../2026-11-06-adjudicator/final-fix-findings.md
Final: final-fix DONE_WITH_CONCERNS f46318d0, 5f6bc5f3, ee698e27 (7481 passed); RED 16 failing vs e32b405f; 23/23 mutants CAUGHT.
Ruling: `failed` records only for paid failures (LLM call failed, apply raised/transient); pre-call failures (read show, stale, bundle, no provider, prompt render) write nothing — they cost no LLM spend, and recording would block a free retry — cost: a show whose bundle fails every pass is retried every pass (no LLM spend).
Ruling: dry runs never write `failed`; acceptable_state checks "none" before "stale" (a stale non-proposal reads `no proposal`) — accurate wording — cost: cosmetic.
Final: dispatched final-rereview (Opus) incl. 4 mutants
Final: fix wave re-review: all 7 addressed, no new breakage (final-rereview Opus); mutants a-d CAUGHT; implementer interpretations 1-3 accepted.
Final: parked — `llama adjudicate --force` whose paid call fails replaces a current acceptable proposal with a `failed` record — Ruling: parked, not fixed (no second fix wave): the proposal is re-judgeable by re-running, nothing on disk outside adjudication.json changes — cost: one extra LLM call to regain a proposal after a forced failure.
Final: parked — post-call exceptions outside the three covered arms (validate_targets, _facts, evaluate, proposal write) leave no failed record — Ruling: parked: rare, each is a code defect that would surface in the pilot — cost: a re-paid call per sweep for such a show until fixed.
Final: parked — a --dry-run replacing a failed record removes the guard for one call — Ruling: parked: one call, not a loop — cost: one call.
Final: minor (deferred): _adjudicate_after docstring line >100 cols.
PRE-PILOT (2026-11-07): controller-run `./.venv/bin/pytest -q -p no:cacheprovider` at ee698e27 -> 7481 passed, 1 skipped, 8 deselected, 26 warnings; llama.__file__ inside the worktree; tree clean. Stopped for parent's go on pilot step 1 (select).
Pilot step 1: select run 11:31:50 at ee698e27, rc 0, no refusal; ~/.llama-harness/adjudicate-pilot/shows.json (30 shows, sha256 dbb28fb8…349f) + population.json; 30 absolute dirs under ~/.llama/shows printed. Waiting for GO-RUN.
Parent: snapshot 11:32 of 30 show dirs (320-file sha256 manifest) + ledger.jsonl (03f13972…); GO-RUN withheld until the llama status pager exits. Idle.
11:34 Pilot step 2: GO-RUN received; opus arm started (bg shell bl9mu2pok), default brakes 85/80.
11:55 opus arm rc 0 (11:34-11:55): 30 rows — dry-run 23, stale 6, malformed 1; 3 trials (all other) status applied+restored; no .txn left; ledger.jsonl sha 03f13972… unchanged. Starting sonnet.
Parent finding (interim, after opus arm): trial restore leaves empty package/ and package/audio/ dirs the redo created (littlefeat-1977-08-08, infamousstringdusters-2010-10-15); files byte-identical. Parent: let sonnet finish, do NOT compare yet, report as before; parent removes the empty dirs; then GO-COMPARE + a show_unit fix task (remove dirs the unit created that are empty after restore; RED, mutation row, Opus reviews), after compare.
Escape: my own post-opus check (only .txn/.audio-aside) missed the empty-dir restore diff; the parent's path check caught it. Lesson: a restore check must compare the path list, not just leftover markers.
12:12 sonnet arm rc 0 (11:56-12:12): dry-run 22, stale 6, malformed 2 (waynehancock, discobiscuits); 3 trials applied+restored (buttholesurfers, littlefeat, gratefuldead-1971-12-01); no .txn/.audio-aside; ledger sha 03f13972… unchanged; empty package/audio in 5 dirs (parent snapshot is the reference). Stopped for GO-COMPARE.
12:13 GO-COMPARE: parent verified 320 files + ledger identical, removed 4 trial-created empty package/audio pairs. Running compare.
12:13 compare done (~/.llama-harness/adjudicate-pilot/compare.md, 434 lines). RELAY-NOW received (context ~409k): finish step 3 (Opus review child + report), do NOT start show_unit fix, HANDOFF, RELAY-READY.
Pilot step 3: dispatched pilot-review (Opus): auto-apply review, disagreements, acceptance bar, stale/malformed causes, CO5, strict list, model recommendation

## HANDOFF (RELAY-NOW, peer ab20f34c context ~409k)
State: Tasks 1-11 + 11b complete and reviewed; final whole-branch review + fix wave done; HEAD ee698e27 on adjudicator-impl, tree clean; controller suite 7481 passed, 1 skipped, 8 deselected (parent re-verified). PRE-PILOT reported. Pilot steps 1 (select, 11:31) and 2 (opus 11:34-11:55, sonnet 11:56-12:12, both rc 0) done; parent verified 320 files + ledger.jsonl byte-identical and rmdir'd 4 trial-created empty package/audio pairs. Step 3: compare.md written (~/.llama-harness/adjudicate-pilot/compare.md, 12:13); pilot-review (Opus) dispatched at ~12:15 — its report $D/pilot-review/handback.md is the step-3 deliverable (relay to parent if I could not).
Successor's FIRST task (parent-directed, after step 3 is reported): show_unit restore removes directories the unit created that are empty after the restore (trial redo left empty package/ + package/audio/). Own task: implementer Opus (strict: show_unit restore), RED required, a mutation row (restore skips the empty-dir removal -> named test red), spec + quality reviewers on Opus. Must not remove dirs that pre-existed (philleshandfriends-2007-10-20 has a pre-existing empty package/audio). Then STOP for Shawn's model decision.
Open pilot items for Shawn (carried): model decision (opus vs sonnet; projected full sweep opus 77 pts / 1.9 h, sonnet 38 pts / 1.1 h; projected held-with-proposal opus 129, sonnet 67 of 345); propose-only demotions; strict-surface spot-check list (compare.md ~line 238); 6 stale shows unjudged by both arms (mymorningjacket-2004-05-28, robertwalters20thcongress-2004-01-02, leftoversalmon-1996-03-16, greatamericantaxi-2009-11-03, soulive-2003-08-07, elliottsmith-1997-05-06); malformed waynehancock-2004-04-08 (both arms; edits name date-swapped WayneHancock2004-08-04d2-* files) and discobiscuits-2002-10-02 (sonnet); CO5 partial-tape: 2/4 partial-tape auto-applicable per arm, partial+sibling 0/3 opus, 1/3 sonnet (station-marked blocks switches).
Process: shared W files in .superpowers/sdd/2026-11-06-adjudicator/ (implementer-common.md now carries this session's attribution URL — successor updates it to its own); state.py for STATE in-flight; dispatch via sdd-dispatch.sh with mandates 1-5; RED-pasted-before-commit is required for every implementer (parent directive).
Parked/deferred for later: see "Final: parked" lines and all "minor (deferred)" lines in this ledger and $D/orch/ledger.md; $W/deferred-minors.md (triaged by the final reviewer: defer all).
Escapes: see the Escapes list at the top.
Tick: to be disarmed at RELAY-READY (cron 07ecffe3, flag armed-ab20f34c). Successor arms its own.
Pilot step 3 DONE: pilot-review (Opus) — Sonnet FAILS the acceptance bar (Yonder 30db duo set airs; GD71 structure overrule breaks the ruling); Opus PASSES as written but stringdusters title-bar overrules would air Track N placeholders. Recommends Opus + two deterministic vetoes (sibling-coverage, placeholder), validator fix (include+set_title/structure same file), dedupe review_flags. 109/345 held shows (31.6%) are stale with unprocessed campaign marks. Report $D/pilot-review/handback.md.
HANDOFF addendum: successor's first task stays the show_unit empty-dir fix (parent-directed); the reviewer's pre-sweep fixes (two vetoes, validator include-then-title/structure, review_flags dedupe, optional quote relevance) are Shawn's call after the model decision — do NOT start them without the parent's go.
12:23 RELAY-READY: tick 07ecffe3 deleted, armed-ab20f34c removed (armed-global kept: other flags remain), no children/shells/monitors.
