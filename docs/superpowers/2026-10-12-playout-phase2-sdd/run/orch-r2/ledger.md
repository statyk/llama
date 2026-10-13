# SDD ledger — plan: docs/superpowers/plans/2026-10-11-playout-phase2.md
Orchestrator: peer session 631e3fb3-24da-46bb-b218-74e21a3ef091 (orch-r2; successor to 9d1f2929/orch-r1 and 1e675379/orch; their ledgers read-only). Parent llama-ba. Start 2026-10-12T05:19:58-0400 at 9adbe62.
Spec: docs/superpowers/specs/2026-10-09-playout-design.md (Stakes governs; spend is the strict surface).
Tasks 0–14 complete (predecessor ledgers). orch-r1 HANDOFF sha256 5fb9f8c3a192758019793710c7014accf28546938f98902d16432a86d193e2ae verified at start.
Order: T15 → T16 → T17 (docs only) → final whole-branch review on Fable (ccf0f16..HEAD) + fix wave + Opus re-review → STOP at T17 HUMAN CHECKPOINT.
Brakes: 5h 85%, weekly 60%. Docker check before each Debian-12 gate.

## Escapes
(none)

## Pre-flight scan (Tasks 15–17)
| rows | produces / consumes | finding |
|---|---|---|
| T14→T15 service.py | T14 Runner(monitor=…), publish_all(p,t_us,held); T15 brief's Runner signature carries monitor, publish_all adds notify after held | consistent |
| T15 test WATCHDOG count | brief expects 4 (plan, render, publish, one batch) with no monitor; T14's dead-clock step runs only when monitor is set | consistent |
| T15↔T16 service.py | T15 edits Runner/publish_all; T16 edits status_lines + adds cloud_lines | disjoint functions, sequential |
| T12/T13→T16 | cloudstate.GUARD_KEY/OFFAIR_KEY (re-exported from publish)/BUDGET_KEY/ALERTS_KEY, get_json, guard_summary, cli._cloud, alerts.active_codes(state,now,repeat_s), ws.alerts_path, cfg.alerts.repeat_hours | all exist at 9adbe62; guard_summary emits the lines T16's test asserts |
| T15–16→T17 | runbook names unit transmitter@<user>.service, status/offair/budget commands, [alerts] keys | consistent |
| T15 self | brief's commit  vs explicit-paths rule | ruled below |
| T16 self | test/impl agree (hugo line, cloud unavailable last line) | consistent |
| T17 self | brief's verbatim runbook text vs llama-ba's mandate (every operator-checkpoint item + full alert-key tables from both HANDOFFs, playout-setup.md:195 fix, [alerts] docs) | ruled below |

- Ruling: T15/T16 commit by explicit paths, not the brief's  — implementer-common's hard rule; same files land — cost if wrong: none.
- Ruling: T17's implementer writes the brief's text verbatim AND adds the operator-checkpoint items and both alert-key tables (cloud + hugo) from the HANDOFFs, the playout-setup.md:195 deploy:assets fix, and [alerts] key docs — llama-ba's order is binding over the brief's minimal text — cost if wrong: a longer runbook.
- Ruling: T15 reviewers get the HANDOFF's R15 question (where watchdog pings sit relative to blocking alert-channel and dead-clock calls) as a task-specific check — cost if wrong: none.

## Log
- 2026-10-12T05:19:58-0400 start; meter 5h 15% (resets 08:19), week 28%; docker info OK. T15 BASE=9adbe62
- 2026-10-12T05:20:23-0400 tick 7d0b551d armed 13,43. T15 implementer dispatched: Sonnet (a2d48f6727a545f31, t15-impl), budget 30 min
- 2026-10-12T05:26:30-0400 T15 implementer DONE_WITH_CONCERNS: 3e79a8a (transmitter 421 py3.14/py3.11; Debian-12 rc 0). No deviations; no RED capture (tests verbatim). R15 self-review: largest gap = render (~10-20 min); alert sends ≤~30 s per call; no gap near 45 min.
- 2026-10-12T05:26:30-0400 T15 review pkg orch-r2/pkg/t15-review.diff (9adbe62..3e79a8a). Spec reviewer: Opus (ae3aec9025c087739, t15-rev-spec); quality reviewer: Opus (a68a5ef64601ccb04, t15-rev-qual)
- 2026-10-12T05:29:58-0400 T15 spec review: NEEDS FIXES — 1 Important (plan-mandated: prune after last batch ping is unbounded after a long stop (~8.4k sequential DELETEs at lead 24 h) and saves runs only at the end → a watchdog kill mid-prune restart-loops forever, unalerted). Minor: render_step can encode 2 shows per step (R15 '~one encode' not a bound); no RED capture. sha256 9399cf26f19c0035
- 2026-10-12T05:33:27-0400 T15 quality review: NEEDS FIXES — 1 Important (tick's early return on unreadable publish.json sends no WATCHDOG → designed fail-closed state becomes a watchdog kill every 45 min; red test proposed). Minor: render 2 encodes + row_analysis lost-cache recompute can exceed 45 min (re-PUT ≤360 segs per kill, PUT-budget bounded); runner test's 4 pings come via a FAILING render step; STOPPING unpinned (mutant M5 survives); no caplog; annotation mismatch; unit After/ExecStart template notes. Mutants M1/M3/M6 red. sha256 cfa33f7d9701c6b8
- Ruling: T15 spec I1 (prune unpinged) enters the fix loop as pings every batch_segments deletes via prune(notify=None); NO mid-loop progress persistence — with pings only a genuine hang is killed, and persisting runs mid-loop adds state-file risk — cost if wrong: a kill during a genuinely hung prune restarts the pass from zero.
- Ruling: T15 quality I1 enters the fix loop — one WATCHDOG=1 on every tick path that runs no _step, keeping the brief's count of 4 — the brief's "after every step" left this path open — cost if wrong: none.
- Ruling: T15 render-bound Minor folded partially — render_step pings after each encode_show (cheap, one optional param); the row_analysis lost-cache path gets a docstring correction only (threading notify into publish_batch is a larger change on the publish path; the case is operator-triggered, self-healing and PUT-budget bounded) — cost if wrong: after a restore without cache/, a first publish may be watchdog-killed and re-PUT ≤360 segments per kill until analyses are cached.
- Ruling: T15 quality M2/M4/M5 folded (comment fix + explicit failing-step ping test; caplog + Linux-only abstract-socket test; consistent annotation) — test-only/cosmetic — cost if wrong: none.
Task 15: minor (deferred): STOPPING=1 in run's finally unpinned (mutant M5 survives; SIGTERM skips finally anyway)
Task 15: minor (deferred): unit After=remote-fs.target orders without requiring the NFS mount; ExecStart hard-codes /home/%i/.venvs/transmitter (runbook says edit)
Task 15: minor (deferred → T17 runbook): after restoring without cache/, the first publish recomputes analyses for ~48 h of shows and may meet WatchdogSec (self-healing; ≤360 re-PUTs per kill, PUT-budget bounded)
Task 15: note: no RED capture (tests verbatim from the brief)
- 2026-10-12T05:33:44-0400 T15 fix round 1 dispatched: resumed implementer Sonnet (a2d48f6727a545f31) in task dir t15-fix1; FIX_BASE=3e79a8a; findings orch-r2/pkg/t15-fix1-findings.md (F1–F6)
- 2026-10-12T05:42:47-0400 T15 fix1 landed 8cfef0b (transmitter 425+1 skip py3.14/py3.11; Debian-12 426). RED captured for F1–F3. Deviations: runner test count 4→5 (render step pings after its encode, then finally); prune monkeypatch lambdas take notify=None.
- 2026-10-12T05:42:47-0400 T15 re-review: Opus (a9e8b092e1b6c71a9, t15-rerev1); pkg orch-r2/pkg/t15-fix1.diff (3e79a8a..8cfef0b)
- 2026-10-12T05:44:34-0400 T15 re-review: ALL ADDRESSED (6/6); deviation 1 (count 4→5) traced true — render reaches encode_show then raises; deviation 2 forced. sha256 9e1d725b0f45063e
Task 15: fix round 1/5 (6 addressed, 0 open — prune pings per batch; fail-closed tick pings; render pings per encode; failing-step ping test; caplog + abstract-socket test; annotations; commits 3e79a8a..8cfef0b)
Task 15: minor (deferred, final wave): test_systemd.py runner-test comment says helpers.E is "far in the past" — it is the FUTURE (2096); one word
Task 15: minor (deferred): row_analysis docstring line runs long (cosmetic)
Task 15: complete (commits 9adbe62..8cfef0b, review clean)
T16 BASE=8cfef0b
- 2026-10-12T05:44:53-0400 T16 implementer dispatched: Sonnet (a36a21b039081a852, t16-impl); docker OK
- 2026-10-12T05:49:28-0400 T16 implementer DONE: 078e533 (transmitter 427+1 skip py3.14/py3.11; Debian-12 428). RED captured. No deviations. Unverified: missing-R2-keys error type from _cloud.
- 2026-10-12T05:49:28-0400 T16 review pkg orch-r2/pkg/t16-review.diff (8cfef0b..078e533). Spec: Opus (a7257905f9bb63ebb, t16-rev-spec); quality: Opus (a614813d3104868b3, t16-rev-qual)
- 2026-10-12T05:50:41-0400 T16 spec review: APPROVED, 2 Minor (plan-mandated: one corrupt budget/alerts doc collapses the whole cloud half to 'unavailable' — hides TRIPPED/killswitch; no cli.status test). Missing-R2-keys → ConfigError(TransmitterError) confirmed caught. ⚠️ guard_summary spend/period field names vs Worker (T12 contract). sha256 96f48113746f0515
- 2026-10-12T05:53:08-0400 T16 quality review: NEEDS FIXES — 5 Important: I1 corrupt local alerts.json → traceback, nothing prints; I2 malformed budget.json float() → traceback, and ignored raises shown as in force; I3 offair non-bool shown 'off' while the clock is off-air (fail-closed mismatch), corrupt guard shown at face value; I4 (plan-mandated) one bad cloud doc blanks the cloud half + get_json Body.read error escapes; I5 malformed endpoint_url ValueError → no local half. 4 Minor. Missing R2 keys → ConfigError confirmed caught. sha256 be4fda727976ab35
- Ruling: T16 I1–I5 all enter the fix loop (G1–G5 in orch-r2/pkg/t16-fix1-findings.md) — spec: "without them, the local half still prints"; status is the operator's view exactly when state is bad, and I3 misreports the spend/on-air state — I4's single-try shape is the brief's verbatim code, overruled for the spec — cost if wrong: status grows per-document handling.
- Ruling: get_json's unwrapped Body.read (deferred T12 minor) folded into G4 — one-line wrap; it also protects offair/budget — cost if wrong: none.
- Ruling: T16 M1 (cloud lines without a local epoch — the Mac case of R14) and M3 (tests per corrupt document, active filter) folded; M2 (_cloud reloads config) and M4 (loose rendering) deferred — cost if wrong: none.
Task 16: minor (deferred): cli._cloud re-loads the config already loaded by status (harmless)
Task 16: minor (deferred): cloud_lines renders raw hand-edited values loosely (cosmetic once G3 lands)
Task 16: minor (deferred, final review): pre-existing local readers status relies on (load_epoch, read_plan, load_publish_state, load_fallback_version) traceback on corrupt bytes (T12-and-earlier code)
Task 16: note (final review): guard_summary spend/period field names vs the Worker's guard.json (T12 contract) — no test populates evaluation/period in status
- 2026-10-12T05:53:20-0400 T16 fix round 1 dispatched: resumed implementer Sonnet (a36a21b039081a852) in task dir t16-fix1; FIX_BASE=078e533; findings G1–G7
- 2026-10-12T06:02:57-0400 T16 fix1 landed 76e3c16 (transmitter 439+1 skip py3.14/py3.11; Debian-12 440; 11 RED first). New errors.CloudDocumentError; shared cloudstate.raise_status_line (replaces cli._raise_status). Concerns: corrupt guard prints CORRUPT line + full summary; _load warns on non-dict; endpoint test monkeypatched.
- 2026-10-12T06:02:57-0400 T16 re-review: Opus (a0fe397ed83fc4e45, t16-rerev1); pkg orch-r2/pkg/t16-fix1.diff (078e533..76e3c16)
- 2026-10-12T06:07:12-0400 T16 re-review 1: OPEN FINDINGS — G1/G2/G4/G5/G6/G7 ADDRESSED; G3 NOT ADDRESSED for the guard (corrupt doc prints CORRUPT then the doc's own 'not tripped' — more permissive than the Worker; mutant 'every guard CORRUPT' survives, no healthy-guard status test). Minor: unreadable guard/offair line omits consequence; cli reader wrapper shadowed; long lines. OOS: raise shows honoured with unknown period end. 11-red-first confirmed. sha256 d3e2e0c2d71bf803
Task 16: fix round 1/5 (6 addressed, 1 open — corrupt guard still prints its own verdict; commits 078e533..76e3c16)
- Ruling: T16 H1 → option (a): CORRUPT line replaces summary[0] (as budget does); the brief's first status test gets a schema-valid guard doc — the brief's fixture predates the guard shape mirror and is not a document the Worker writes; its assertions stay — cost if wrong: one fixture differs from the plan text.
- Ruling: T16 H2 (consequence on unreadable guard/offair lines) and H3 (honoured → "honoured (period end unknown)" when the period end is unknown; budget too) folded into round 2 — both on the spend view, both small — cost if wrong: wording.
Task 16: minor (deferred): cli.status reader wrapper (cli.py:226) shadowed by cloud_lines' broad catch; untested
- 2026-10-12T06:07:24-0400 T16 fix round 2 dispatched: resumed implementer Sonnet (a36a21b039081a852) in task dir t16-fix2; FIX_BASE=76e3c16; findings H1–H3
- 2026-10-12T06:14:31-0400 T16 fix2 landed 4ff1126 (transmitter 443+1 skip py3.14/py3.11; Debian-12 444). H1 mutant 'if True' red on the brief test + one-doc test. H3 changed one test_cloudstate wording assertion.
- 2026-10-12T06:14:31-0400 T16 re-review 2: Opus (a952bb2b69bb99c46, t16-rerev2); pkg orch-r2/pkg/t16-fix2.diff (76e3c16..4ff1126)
- 2026-10-12T06:16:21-0400 T16 re-review 2: ALL ADDRESSED (3/3); mutants 'if True' and 'summary' (no [1:]) each red on the predicted tests. OOS: '(honoured (period end unknown))' nested parens; unknown base budget still plain honoured. sha256 161c1429cda33905
Task 16: fix round 2/5 (3 addressed, 0 open — corrupt guard replaces its verdict line; unreadable docs state consequence; honoured with unknown period end; commits 76e3c16..4ff1126)
Task 16: minor (deferred): raise line renders nested parens '(honoured (period end unknown))'; unknown base_budget_usd still prints plain honoured (read-only view)
Task 16: complete (commits 8cfef0b..4ff1126, 2 fix rounds, review clean)
T17 BASE=4ff1126
- 2026-10-12T06:17:25-0400 T17 implementer dispatched: Sonnet (a89ffaf88e70585a0, t17-impl); extras orch-r2/pkg/task-17-extras.md (A section-4 fix, B 7 checklist items, C operating facts incl. T15/T16 notes, D both alert-key tables verified against code, E config keys)
- 2026-10-12T06:18:58-0400 T17 implementer DONE: ea3ca04 (docs/playout-setup.md only; Step 2 greps clean; keys verified vs code, no deviations). Concerns: KILL_SWITCH_DESCRIPTION/ALERT_REPEAT_HOURS not documented (brief omits); '10 checks' and '~30 s buffer' unsourced in code.
- 2026-10-12T06:19:28-0400 T17 review pkg orch-r2/pkg/t17-review.diff (4ff1126..ea3ca04). Spec: Opus (a6d23552be1cf3cef, t17-rev-spec); quality: Opus (ac059ed95f07cff50, t17-rev-qual)
- 2026-10-12T06:22:46-0400 T17 spec review: NEEDS FIXES — 1 Important (plan-mandated: checklist expects alert 'Kill switch toggled by hand'; code sends 'Kill switch corrected' guard.ts:295 → false fail on the WAF path). Minor: deploy:assets also uploads offair.html (extras A wording wrong); KILL_SWITCH_DESCRIPTION/ALERT_REPEAT_HOURS not Missing (optional naming); STATION_NAME inserted as 6.2 step 5 renumbers brief's step; section-4 'hard stop' + phase-1 checklist toggle item stale after phase 2. '10 checks' (TROUBLE_CHECKS) and '~30 s' (liveSyncDurationCount 3) sourced. sha256 a2f0d07101d64d0a
- 2026-10-12T06:27:50-0400 T17 quality review: NEEDS FIXES — 2 Important: I1 (plan-mandated brief edit 4) broken-Worker 'triggers deploy from a config with no crons' keeps the cron (wrangler PUTs schedules only when crons set) → hand block undone; I2 operator commands need R2 keys from the env file + venv path, never stated. 11 Minor (alert title, resolved timing, leftover test raise, offair.html, stale labels, unfalsifiable B1, notes-as-items, curl status/max-age, systemctl revert, live tokens overwritten, no way back from broken-Worker block). sha256 1a0dd28cae644573
- Ruling: T17 all findings folded into one round (K1–K15 in orch-r2/pkg/t17-fix1-findings.md) — docs-only, cheap, and several sit on the spend/blocking path the checkpoint exercises; K2 overrides the brief's verbatim edit-4 text (the code/wrangler wins) — cost if wrong: a longer runbook.
- Ruling: my extras A wording ("JS/CSS/hls.js only") was wrong — deploy:assets also uploads offair.html; corrected in K6 — cost if wrong: none.
- 2026-10-12T06:28:02-0400 T17 fix round 1 dispatched: resumed implementer Sonnet (a89ffaf88e70585a0) in task dir t17-fix1; FIX_BASE=ea3ca04; K1–K15
- 2026-10-12T06:28:56-0400 T17 fix1 landed 01186ea (docs only; greps clean). Concern: worked from findings file only, not the full reviews.
- 2026-10-12T06:29:15-0400 T17 re-review: Opus (a4ab4e42e20488a78, t17-rerev1); pkg orch-r2/pkg/t17-fix1.diff (ea3ca04..01186ea)
- 2026-10-12T06:33:33-0400 T17 re-review: ALL ADDRESSED (15/15); wrangler 4.149.0 source confirms crons:[] and r2 object delete syntax. New Minor N1–N4 (fail-safe wording). sha256 b261484409feecfa
Task 17: fix round 1/5 (15 addressed, 0 open — alert title; broken-Worker crons:[] + confirm + way back; env-file/venv preamble; resolved timing; test-raise delete; offair.html; labels; B1 existence; notes; curl; revert; tokens; numbering; hand-toggle notes; verify fallback; commits ea3ca04..01186ea)
Task 17: minor (deferred, final wave): N1 doc:451 'any figure above the projected one' — must also exceed actual÷0.9 (trip = actual≥90% OR projected≥100%); same gap in section 7's pre-existing 'Raise above the projected figure'
Task 17: minor (deferred, final wave): N2 doc:452 'extra 50%/80% alerts at $5.50 and $7 are expected' overstates — 80% at $7 only if max(actual,projected) ≥ $5.60 (false fail risk at the checkpoint)
Task 17: minor (deferred, final wave): N3 Google App Password shown with spaces → sourcing the env file in bash errors; say 'paste without spaces'
Task 17: minor (deferred, final wave): N4 broken-Worker way back — 'redeploy with the committed wrangler.jsonc (output ends schedule: * * * * *)', else crons:[] stays
Task 17: minor (deferred): broken-Worker order — an in-flight invocation may still disable a rule enabled seconds after trigger removal; wait a minute and re-check; K15 instance-verify fallback may need the full /etc path
Task 17: complete (commits 4ff1126..01186ea, 1 fix round, review clean)
- 2026-10-12T06:34:24-0400 FINAL whole-branch review dispatched: Fable (a42a8848a4732992d, final-review) — sanctioned upgrade (spec review mode Fable; llama-ba order). Range ccf0f16..01186ea; pkg orch-r2/pkg/final-review.diff (465 KB); triage input orch-r2/pkg/final-triage.md (MUST-FIX 1–5 + all deferred minors); budget 75 min
- 2026-10-12T06:34:40-0400 llama-ba: pin $D/final-review/handback.md (full sha256) in the ledger the moment the verdict lands, BEFORE the fix wave; each re-review verdict gets its own pin.
- 2026-10-12T06:47:27-0400 FINAL review VERDICT: READY WITH FIXES. PIN (taken before the fix wave): sha256 79e0596907be9490019beae2ba6c6492509ccdfd2345edc458d50645a7215eca  (   30139 bytes) $D/final-review/handback.md. MUST-FIX 1/2/3 OPEN (1,3 = pins missing on correct code, each proven by a surviving mutant + probe; 2 = unguarded AbortSignal.timeout), 4 CONFIRMED. Critical: none. Minor M1–M8. Rulings challenged: none.
- Ruling: final fix wave = ONE dispatch with F1–F12 (orch-r2/pkg/final-fix-findings.md): the reviewer's 7 fix-before-merge items + M1 (step rename dead-clock-check), M2 (hugo cache mirrors the Worker's offair reading), M7 (ntfy isascii), M8 (comment), N4 (doc phrase) folded — each small and outward-facing (wrong alert text / noise alerts) — the remaining ~50 deferred minors stay deferred per the reviewer's triage table — cost if wrong: a slightly larger fix diff.
- Ruling: fix-wave implementer on Sonnet — every item is specified with exact text or a reviewer-written probe; spans antenna + transmitter + docs but needs no design judgment; Opus re-review follows — cost if wrong: escalate to Opus on BLOCKED.
- 2026-10-12T06:48:18-0400 Final fix wave dispatched: Sonnet (a41ad3d3a050ec906, final-fix), F1–F12, FIX_BASE=01186ea; docker OK; antenna dirs added to STATE probe-dirs
- 2026-10-12T06:56:45-0400 Final fix wave DONE: 93cbfba, f6c28fe, 6b42bde (antenna 217 + tsc; transmitter 451+1 skip py3.14/py3.11; Debian-12 452; email grep clean). F1/F3 red under mutants A/M1' in scratch. Deviations: F10 rewrote the old latin-1 café assertion; F9 JSON null offair reads absent (Worker: corrupt → off-air) — dead-clock noise only. antenna/src: guard.ts comment only. Verdict pin re-checked unchanged (79e05969…).
- 2026-10-12T06:57:02-0400 Final fix-wave re-review dispatched: Opus (a3fe0cf2ef1f6ff7a, final-rerev); pkg orch-r2/pkg/final-fix.diff (01186ea..6b42bde)
- 2026-10-12T07:02:06-0400 Final fix-wave re-review: OPEN FINDINGS — 11/12 ADDRESSED (F1/F3/F8/F10 mutants reproduced red in scratch); F9 PARTIAL (Minor, noise only): non-JSON/empty offair.json still caches offair=None on hugo (Uploader.get_json's json.loads error swallowed by except Exception) while the Worker reads it off-air → the unexpected-403 dead-clock noise after 17 checks remains for that case; JSON null reads absent. New Minors: F6 dropped the $5.50 50/80% mention; test name says latin1; describe title says delivered. OOS: F2 reaches listeners only via deploy:assets; unbounded probe without AbortSignal.timeout. PIN sha256 cc1b7208d7267ef8a06af702b07c31df75016f2b3e2026ae692aa4775d780c7f $D/final-rerev/handback.md
- Final-review: parked — F9 residual (non-JSON/empty/null offair.json → hugo cache offair None/False vs Worker off-air) — Ruling: parked, no second fix wave (SDD rule) — real but noise-only: it can cause one spurious unexpected-403 dead-clock alert after 17 checks beside the cloud's offair-corrupt alert; nothing on the spend or publishing path reads the field; the fix is one 'except ValueError: offair = True' + two parametrize cases — cost if wrong: a confusing extra alert while offair.json is corrupt.
- Final-review: parked — new cosmetic Minors (F6 $5.50 mention, test name 'not_latin1', alerts describe title) — Ruling: parked as cosmetic — cost if wrong: none.
Final review: complete (verdict READY WITH FIXES pinned 79e0596907be9490019beae2ba6c6492509ccdfd2345edc458d50645a7215eca; fix wave 01186ea..6b42bde; re-review 11/12 addressed, 1 Minor parked)
- 2026-10-12T07:02:06-0400 STOP at Task 17 HUMAN CHECKPOINT. HEAD 6b42bde, tree clean. Waiting on llama-ba.

## FINAL (orch-r2, peer 631e3fb3-24da-46bb-b218-74e21a3ef091)
- 2026-10-12T09:07:56-0400 llama-ba: the operator approved the merge; llama-ba merges playout-phase2 into main from the main checkout. Run ends; Tasks 18–19 are a separate follow-up.
- Final commit on playout-phase2: 6b42bde (tree clean). My range: 9adbe62..6b42bde — T15 9adbe62..8cfef0b, T16 8cfef0b..4ff1126, T17 4ff1126..01186ea, final fix wave 01186ea..6b42bde.
- Final review (Fable) READY WITH FIXES, sha256 79e0596907be9490019beae2ba6c6492509ccdfd2345edc458d50645a7215eca; fix-wave re-review (Opus) sha256 cc1b7208d7267ef8a06af702b07c31df75016f2b3e2026ae692aa4775d780c7f; 1 Minor (F9 non-JSON offair cache) + 3 cosmetic parked with rulings.
- Last counts: antenna 217 + tsc clean; transmitter 451 + 1 skipped py3.14/py3.11; Debian-12 452.
- Disarmed: tick 7d0b551d deleted; armed-631e3fb3 removed; armed-global per the other-flags rule; STATE.md mode done, in-flight empty. Nothing running.
