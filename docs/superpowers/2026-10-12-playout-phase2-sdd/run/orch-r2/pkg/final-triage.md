# Final whole-branch review — MUST-FIX list and deferred-minor triage input

## MUST-FIX (confirm each is fixed in the range, or list it as an open Important finding)
1. (T6) A committed test pins that blind still trips 6 h after the last successful reading while the state/budget.json get keeps throwing (a mutant gating applyBlindRule on !budgetReadFailed must go red).
2. (T11) antenna/public player probe guards AbortSignal.timeout with typeof AbortSignal.timeout === "function" (pre-2022 browsers, e.g. iOS 15: otherwise every probe reads unknown and mid-play detection never fires).
3. (T9, spend surface) Test P10: a failed re-alert over an active NEVER-delivered episode stays delivered:false and sends no 'resolved' on re-clear (sequence: /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/.superpowers/sdd/phase2/t9-rerev3/handback.md; mutant M1 'force delivered:true for any active prev' survives today; the code is believed correct).
4. (Ruling 18) clock-failed (folded into T9 at 733439f) covers a failed playlist PUT and is not double-raised after clock-inputs.
5. Triage EVERY deferred-minor line below: fix-before-merge (say why) / defer (say why) / already-resolved (cite the commit).

## orch-r1 HANDOFF's 'recommend fix' candidates (weigh these first)
- T13: ntfy Title predicate should be isascii() not latin-1 ('café' reaches ntfy as invalid UTF-8); Header(...).encode(maxlinelen=0) to avoid obs-fold.
- T13: pin the plan step's 'plan' resolve (mutant A) and the newer-wins memory/disk merge (mutant D: 'resolved' re-sent every tick after a failed write).
- T14: a corrupt/non-bool offair.json reads as on-air in the guard cache (antenna reads off-air) → possible noise dead-clock alert after 17 min.
- Spend-adjacent: T3 15 s GraphQL timeout unpinned; T5 5 s timeout unpinned; T5 post-PATCH verify checks only 'enabled'; T1 billingPeriod(NaN) not refused; T6 waf-corrected text in the M1 fold case; T8 ClockError without { cause }.
- T15 (orch-r2): test_systemd.py runner-test comment says helpers.E is 'far in the past' — it is the FUTURE (2096).

## Already resolved later (verify, do not re-triage): T1 minors 1–2 (fixed in T6: create-only first write; corrupt-read etag pinned); T6 'budget-unreadable not in R13' (listed in alerts + runbook); T12 'get_json catches only ValueError around body read' (fixed in T16 76e3c16: Body.read wrapped as CloudStateError); T12 'view (honoured) with a malformed guard' (T16 4ff1126: corrupt guard is not used to judge the raise; '(period end unknown)').

## Every deferred minor and note, verbatim from the three ledgers

### $D/orch/ledger.md
- Task 1: minor (deferred): putJson etag-truthiness → unconditional create when guard.json absent; first-creation race could lose a trip (carry to Task 6 implementer + reviewers)
- Task 1: minor (deferred): no test pins that a corrupt read carries the etag (Task 6 relies on it) (carry to Task 6)
- Task 1: minor (deferred): billingPeriod(NaN) returns NaN period instead of throwing — latent, could read as "new period" under R3
- Task 1: minor (deferred): fakeFetch ignores Request-object input / non-string bodies — latent
- Task 1: minor (deferred): MemoryBucket failGets also fails head; puts() counts precondition-failed puts
- Task 1: minor (deferred): clock.test.ts playlistPuts duplicates MemoryBucket.puts
- Task 1: minor (deferred): period tests lack a leap-year case
- Task 2: minor (deferred): analytics lag window counted in neither term (~0.01%; projection not a strict upper bound for op counts)
- Task 2: minor (deferred): METERS/PRICES exported mutable (not readonly/frozen)
- Task 2: minor (deferred): ALERT_LEVELS untested here (consumed by T6)
- Task 2: minor (deferred): negated overThreshold not fail-closed for +Inf budget / -Inf actual|projected (unreachable: inputs validated finite upstream)
- Task 3: minor (deferred): errors-without-message fallback prints JSON instead of "error" (undeclared, harmless)
- Task 3: minor (deferred): 15 s GraphQL timeout unpinned (fakeFetch does not record init.signal) — a hung POST delays the whole invocation
- Task 3: minor (deferred): pricing-page-only Class A types (CopyObject, UploadPart, ...) unpinned in class sets
- Task 3: minor (deferred): missing actionType reported as "" in unknown_action_types (hard to read)
- Task 3: minor (deferred): empty dataset reads as zero usage (storage [] ~45 min after period start; negligible)
- Task 3: minor (deferred): metadataSize ?? 0 vs payloadSize throws — asymmetry deserves a comment
- Task 3: minor (deferred): brief's five-mode error test lacks per-case labels
- Task 4: minor (deferred): parseGuardDoc returns the raw object — unknown keys carried forever (note for T12)
- Task 4: minor (deferred): malformed raise (string budget_usd, bad expires, lowering raise) ignored silently — only "outlives period" sets invalid
- Task 4: minor (deferred): StoredEvaluation.base_budget_usd typed number but unchecked by parseGuardDoc (T12 readers)
- Task 4: minor (deferred, T6 awareness): with a NaN base, effectiveBudget honours any raise even below $5 (usd <= NaN false) — cannot unblock while over
- Task 4: minor (deferred): latch.test.ts:213 dead reassignment in loop
- Task 5: minor (deferred): null envelope / result:null → TypeError not WafError (still fails closed before PATCH)
- Task 5: minor (deferred): 5 s timeout value unpinned (only presence of signal asserted)
- Task 5: minor (deferred): post-PATCH verify checks only enabled, not action/expression
- Task 5: minor (deferred): found-0/found-2 refusal tests don't assert GET-only
- Task 5: note (for T6/final): WafError messages carry the request path → zone ID lands in guard.json waf.error and alerts (not public while state/ is off the allowlist)
- Task 6: minor (deferred): corrupt-winner path raises guard-state-corrupt one minute late (spec m3)
- Task 6: note (for T9/final): waf-api alert text embeds the zone ID via WafError path → decide redaction before alerts leave the account
- Task 6: note (for T9): guard-state-corrupt is resolvable — "resolved" wording must not imply the spend trip it caused is cleared
- Task 6: minor (deferred, MUST-FIX in final wave): no committed test pins "blind still trips while budget.json reads keep throwing" — the I1 ruling's cost-if-wrong rests on it (mutant gating applyBlindRule on !budgetReadFailed survives)
- Task 6: minor (deferred): M1 fold case emits waf-corrected "…to match blocked=false" while outcome is blocked:true (confusing text)
- Task 6: minor (deferred): budget-unreadable is a new condition key not in R13 — T9 dispatch / T17 runbook must list it
- Task 6: minor (deferred): ok-but-malformed budget.json still silently ignored by effectiveBudget (T4 code)
- Task 6: minor (deferred): corrupt-budget message renders $NaN when base invalid (already alerted via meterProblems)
- Task 7: minor (deferred): "corrects a hand-uploaded index.html" test asserts only the return value, not body/metadata
- Task 7: minor (deferred): off-air page negative check covers only player.js (use not.toContain("<script"))
- Task 7: minor (deferred): unconditional index PUT race (self-healing ≤1 min) deserves a comment
- Task 8: minor (deferred): worker-configuration.d.ts regenerated outside the brief's file list (accepted, correct)
- Task 8: minor (deferred): ClockError calls super(message) without { cause } — runtime log shows wrapper stack
- - Final reviewer should triage every "minor (deferred)" line above. Already resolved later, so skip: Task 1 minors 1–2 (fixed in T6: create-only first write; corrupt-read etag pinned), Task 6 "budget-unreadable not in R13" (covered by item 5 above). Candidates worth fixing (spend-adjacent): T3 15 s GraphQL timeout unpinned; T5 5 s timeout unpinned; T5 post-PATCH verify checks only `enabled`; T1 billingPeriod(NaN) not refused; T6 waf-corrected text in the M1 fold case; T8 ClockError without { cause }.

### $D/orch-r1/ledger.md
- Task 11: note (for T17 runbook/checklist): end-to-end kill-switch latency on an already-playing page ≈ buffer (~30 s) + 25 s; verify live against RF5's ~45 s
- Task 11: minor (deferred): backwards currentTime jump stops progress registering until the old high-water mark (shows Reconnecting…, probes return unknown; never off-air)
- Task 11: minor (deferred): permanent stall with a healthy station probes every 10 s and shows Reconnecting… forever (phase-4 player UX)
- Task 11: minor (deferred): player.js has no tests of its own (DOM wiring; matches phase-1 pattern)
- Task 11: minor (deferred): networkDetails.status presence in vendored hls.min.js unverified
- Task 11: minor (deferred, recommend fix in final wave — introduced by my M2 ruling): AbortSignal.timeout throws on pre-2022 browsers (iOS 15 WebKit) → every probe "unknown" → mid-play detection silently never fires there; guard with typeof AbortSignal.timeout === "function"
- - final reviewer triages every "minor (deferred)" line in both ledgers
- Task 9: minor (deferred): trailing batch default COMPLETE fails open for a future caller (alertSink passes it; production safe)
- Task 9: minor (deferred → T17 runbook): STATION_NAME must be ASCII/Latin-1 (raw ntfy Title header) — document
- Task 9: minor (deferred, final): budget-file-invalid is once with a constant key → a second invalid raise within 35 days unalerted (safe direction; T6 design)
- Task 9: note (T17 runbook): guard-unknown can arise on a known outcome (raceUnknown); R2 outage reading alerts.json silences cloud alerts (hugo dead-clock is the cover — verify at T14)
- Task 12: note (T17 runbook): guard-state-corrupt alert says --raise-to but while readings fail the raise is refused (no period) — runbook: wait for the next successful evaluation
- Task 12: minor (deferred): _iso_ok vs JS Date.parse differ on hand-edited since (stricter on naive/date-only → permanent refusal with untrue "retry" advice; looser on basic-format)
- Task 12: minor (deferred): json.loads accepts NaN/Infinity tokens JS rejects → mirror passes a doc the Worker deems corrupt (parse_constant raise)
- Task 12: minor (deferred): wording — offair off shape note "until it rewrites it" (rewrite is a spend trip); view "(honoured)" with a malformed guard
- Task 12: minor (deferred): get_json catches only ValueError around body read (botocore streaming error → traceback after offair off's write); _finite OverflowError on huge ints (pre-existing)
- Task 12: minor (deferred): R7 test midnight window lets a mutant escape (correct code never flakes); optional: monkeypatch publish.datetime
- Task 9: minor (deferred, MUST-FIX in final wave — spend surface): add P10 test pinning that a failed re-alert over an active NEVER-delivered episode stays delivered:false (reviewer's sequence in t9-rerev3/handback.md)
- Task 9: minor (deferred): prev.active truthiness on hand-editable JSON ("active":"no" reads active; conservative side)
- Task 13: note (T17): docs for [alerts] keys (Global Constraint: model + template + docs)
- Task 13: note (final review): plan/render codes resolve only while filling — a persisting plan failure can leave 'plan' active after render refills the lead (R16 as written)
- Task 10: note (T17): playout-setup.md:195 — deploy:assets no longer uploads index.html (R8)
- Task 10: minor (deferred): vite/client widens ambient types project-wide (src/ could import ?raw and pass tsc but fail bundling) — brief chose it
- Task 10: minor (deferred): vite not an explicit devDependency (hoisted via vitest)
- Task 10: note (T17 runbook): deploy:assets before/alongside the Worker deploy on a fresh bucket (index.html from the clock references player.js/style.css/hls)
- Task 10: minor (deferred): 32-hex regex will reject a future KV namespace id (intended for a public repo; that task edits the test)
- Task 13: minor (deferred, recommend final wave): ntfy Title predicate should be isascii (latin-1 non-ASCII "café" arrives as invalid UTF-8 at ntfy) + Header.encode(maxlinelen=0) to avoid obs-fold
- Task 13: minor (deferred): plan step's "plan" resolve unpinned (mutant A); newer-wins merge comparison unpinned (mutant D → resolved re-sent each tick after a failed write)
- Task 13: minor (deferred): cool-down uses wall clock (time.monotonic); one-shot event alert during a full cool-down is logged only
- Task 14: minor (deferred): corrupt/non-bool offair.json reads as on-air in the cache (antenna reads off-air) → possible noise dead-clock alert after 17 min (spec M3)
- Task 14: minor (deferred): dead-clock check skipped on fail-closed ticks (publish-state alerts instead); 403/unreachable thresholds are tick counts, can stretch during long renders (plan wording)
- Task 14: note (T17): confirm site_url serves live.m3u8 at root; confirm the WAF block answers 403 on the R2 custom domain (else counted unreachable → alarm after 10 checks)
- Task 14: minor (deferred): while guard.json reads fail the monitor times only the failure, so a pre-existing stall is reported ≤guard_stale_s late; in-memory timer restarts with the service (optional: keep last good guard_evaluated_at monitor-side)
- Task 14: minor (deferred): empty str(exc) leaves "…: " in the message; test-style nits (__import__ in parametrize, late-bound m_clock); error-clears-but-still-stale case untested
- 5. The final reviewer triages EVERY "minor (deferred)" line in BOTH ledgers: $D/orch/ledger.md (predecessor; skip T1 minors 1–2 and the T6 "budget-unreadable not in R13" line, already resolved) and $D/orch-r1/ledger.md.

### $D/orch-r2/ledger.md
- Task 15: minor (deferred): STOPPING=1 in run's finally unpinned (mutant M5 survives; SIGTERM skips finally anyway)
- Task 15: minor (deferred): unit After=remote-fs.target orders without requiring the NFS mount; ExecStart hard-codes /home/%i/.venvs/transmitter (runbook says edit)
- Task 15: minor (deferred → T17 runbook): after restoring without cache/, the first publish recomputes analyses for ~48 h of shows and may meet WatchdogSec (self-healing; ≤360 re-PUTs per kill, PUT-budget bounded)
- Task 15: note: no RED capture (tests verbatim from the brief)
- Task 15: minor (deferred, final wave): test_systemd.py runner-test comment says helpers.E is "far in the past" — it is the FUTURE (2096); one word
- Task 15: minor (deferred): row_analysis docstring line runs long (cosmetic)
- Task 16: minor (deferred): cli._cloud re-loads the config already loaded by status (harmless)
- Task 16: minor (deferred): cloud_lines renders raw hand-edited values loosely (cosmetic once G3 lands)
- Task 16: minor (deferred, final review): pre-existing local readers status relies on (load_epoch, read_plan, load_publish_state, load_fallback_version) traceback on corrupt bytes (T12-and-earlier code)
- Task 16: note (final review): guard_summary spend/period field names vs the Worker's guard.json (T12 contract) — no test populates evaluation/period in status
- Task 16: minor (deferred): cli.status reader wrapper (cli.py:226) shadowed by cloud_lines' broad catch; untested
- Task 16: minor (deferred): raise line renders nested parens '(honoured (period end unknown))'; unknown base_budget_usd still prints plain honoured (read-only view)

### Added after T17 re-review (orch-r2)
- Task 17: minor (deferred, final wave): N1 doc ~451 'any figure above the projected one' — a raise must also exceed actual ÷ 0.9 (trip = actual ≥ 90% OR projected ≥ 100%); same gap in section 7's 'Raise above the projected figure'
- Task 17: minor (deferred, final wave): N2 doc ~452 'extra 50%/80% alerts at $5.50 and $7 are expected' overstates — the 80% at $7 fires only if max(actual, projected) ≥ $5.60 (a false fail at the checkpoint)
- Task 17: minor (deferred, final wave): N3 a Google App Password is shown with spaces → sourcing the env file in bash errors; say 'paste without spaces'
- Task 17: minor (deferred, final wave): N4 broken-Worker way back — 'redeploy with the committed wrangler.jsonc (output ends schedule: * * * * *)', else crons:[] stays
- Task 17: minor (deferred): broken-Worker order — an in-flight invocation may still disable a rule enabled seconds after the trigger is removed (wait a minute, re-check); the K15 instance-verify fallback may need the full /etc path
