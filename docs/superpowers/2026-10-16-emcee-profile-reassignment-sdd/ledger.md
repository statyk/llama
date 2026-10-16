# SDD ledger — plan: docs/superpowers/plans/2026-10-16-emcee-profile-reassignment.md
Run: peer orchestrator eb75daa6-4117-4f2c-a82b-07d987d6b499, parent llama-ed. Start 2026-10-16T14:30:54-0400 @ 16f0e72. Baseline (per parent brief): 2953 passed, 1 skipped, 8 deselected.
Workspace (briefs, review packages): /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/.superpowers/sdd/2026-10-16-emcee-profile-reassignment

## Preflight scan
| rows | produces -> consumes | found |
|---|---|---|
| T1->T3,T4 (config.py, artists.py) | ArtistRule/AssignConfig.artists, normalize_artist -> effective_profile | consistent per plan self-review type table |
| T2->T3..T7 (moves.py) | Moves/load_moves/read_moves_data/write_moves/record_move/clear_move | names consistent across tasks (self-review) |
| T3->T4,T5 (station.py) | Effective(profile,source,rule), effective_profile | consistent |
| T4->T5..T8 (station.py, cli.py, helpers.py) | scan(root,config,moves), readiness, assess.effective, station_home/forbid_spend/notes_json | consistent; later tasks import helpers, never redefine |
| T5->T7 (cli.py, process.py) | _process_one(config,moves,pkg,force,fresh=()), process_package(...,*,voicing) | consistent |
| T7->T8 (cli.py) | _stale_moves/_stale_note | consistent |
| T9 | docs only | — |
| per-task self-agreement | not re-read line by line | see Ruling |
Ruling: preflight scan done at the interface level (File Structure + self-review type table), not by re-reading all 4,199 plan lines — the plan already passed two independent review rounds (16f0e72) and the 7-day meter is 89%; cost if wrong: an intra-task inconsistency surfaces in the task review loop instead of here.

## Escapes
(none)

## Log
- 2026-10-16T14:30:54-0400 setup: meter 5h 8% / 7d 89% (resets 10-17 07:00); tick armed
- 2026-10-16T14:31:23-0400 Task 1 implementer dispatched: Sonnet (t1-impl, agent ace5d9fff7fa0e1fe), BASE 16f0e72
- 2026-10-16T14:33:38-0400 Task 1 implementer DONE: ba15aa4 (suite 2976 passed, 1 skipped, 8 deselected per report)
- 2026-10-16T14:33:38-0400 Task 1 reviewer dispatched: Opus (t1-rev, agent ab474b180ea25ae48), range 16f0e72..ba15aa4
- 2026-10-16T14:34:41-0400 Task 1 review: spec ✅, quality Approved, 0 Critical/Important (t1-rev)
Task 1: minor (deferred): normalize_artist has no Unicode normalization — NFD input ("Béla" decomposed) yields "be la fleck"; spec silent; candidate NFKC before casefold (spec-level call)
Task 1: minor (deferred): ArtistRule populate_by_name=True accepts `from_` as a TOML key (brief-mandated)
Task 1: minor (deferred): redundant extra="forbid" on ArtistRule (config.py:150)
Task 1: minor (deferred): mid-module import test_config.py:499 (brief-mandated)
Task 1: minor (deferred): comment alignment test_artists.py:32
Task 1: complete (commits 16f0e72..ba15aa4, review clean)
- 2026-10-16T14:35:23-0400 Task 2 implementer dispatched: Sonnet (t2-impl, agent affe5da5755a58600), BASE ba15aa4; meter 5h 9% / 7d 89%
- 2026-10-16T14:37:33-0400 Task 2 implementer DONE: 0633649 (suite 3001 passed, 1 skipped, 8 deselected per report; concern: no RED run captured)
- 2026-10-16T14:37:33-0400 Task 2 reviewer dispatched: Opus (t2-rev, agent a21292a3e5d451e56), range ba15aa4..0633649
- 2026-10-16T14:38:49-0400 Task 2 review: spec ✅, quality Approved; 1 Important (plan-mandated): write_moves duplicates workspace.atomic_write_bytes' unique-temp+replace block, which the repo says must not be duplicated
Task 2: Ruling: fold write_moves into atomic_write_bytes(..., fsync=True) — the spec/constraint require temp+fsync+replace, not a second copy of the helper, and workspace.py/package_io.py explicitly forbid duplicating it; cost if wrong: one small helper signature change to revert
Task 2: minor (deferred): no parent-dir fsync after os.replace (atomic, not fully durable on power loss)
Task 2: minor (deferred): identical-profile record_move does not refresh a renamed package name (spec "unchanged")
Task 2: minor (deferred): lock release on exception paths / after clear_move unpinned by tests
Task 2: minor (deferred): no RED evidence captured for T2
- 2026-10-16T14:39:02-0400 Task 2 fix round 1 dispatched: resumed Sonnet implementer (t2-impl), FIX_BASE 0633649
- 2026-10-16T14:40:32-0400 Task 2 fix round 1 implementer DONE: c626a2d (suite 3001 passed per report); re-review dispatched: Opus (t2-rerev1, agent ab21f6d65fac1c8ae)
Task 2: fix round 1/5 (1 addressed, 0 open; commits 0633649..c626a2d)
Task 2: minor (deferred): workspace.py module docstring lists only presenters/package_io as users of the atomic writers (out of date)
Task 2: complete (commits ba15aa4..c626a2d, review clean)
- 2026-10-16T14:41:33-0400 Task 3 implementer dispatched: Sonnet (t3-impl, agent a8fc954ddbce9b1c1), BASE c626a2d; meter 5h 9% / 7d 89%
- 2026-10-16T14:43:19-0400 Task 3 implementer DONE: c5760a0 (suite 3023 passed, 1 skipped, 8 deselected per report; RED captured)
- 2026-10-16T14:43:19-0400 Task 3 reviewer dispatched: Opus (t3-rev, agent a6513440d9702a10b), range c626a2d..c5760a0
- 2026-10-16T14:44:23-0400 Task 3 review: spec ✅, quality Approved, 0 Critical/Important (t3-rev)
Task 3: minor (deferred): test_accessors_are_total does not exercise manifest_voiced_profile on garbage nor a non-string dj_audio.profile
Task 3: minor (deferred): Effective invariant (rule None unless source=="artist") is docstring-only
Task 3: complete (commits c626a2d..c5760a0, review clean)
- 2026-10-16T14:44:54-0400 Task 4 implementer dispatched: Opus (t4-impl, agent a4029158c27c11519), BASE c5760a0; meter 5h 9% / 7d 89%
- 2026-10-16T14:48:21-0400 Task 4 implementer DONE_WITH_CONCERNS: 9fe43c2 (suite 3057 passed, 1 skipped, 8 deselected; RED 33 failed). Concerns (observations): run/status --profile help still says "llama profile" though selection is now effective-profile; moves unused in run until T5 (by design); scan reads each manifest 3x
Task 4: minor (deferred): `emcee run --profile` help (cli.py:322) still says "delivered for this llama profile" — selection is effective now; check T8/T9 fix it
Task 4: minor (deferred): scan reads each package manifest three times (Package has no cache)
- 2026-10-16T14:48:21-0400 Task 4 reviewer dispatched: Opus (t4-rev, agent a16398c08b9869e4b), range c5760a0..9fe43c2
- 2026-10-16T14:51:38-0400 Task 4 review: spec ✅, quality Approved, 0 Critical/Important (t4-rev). Reviewer mutation: removing require_present in _load_station CAUGHT by predicted test.
Task 4: minor (deferred, FINAL-REVIEW MUST TRIAGE — strict surface 2): _scan_broad post-manifest error rows' identity() unpinned; mutant forcing voiced_source=None SURVIVED (831 passed). Fix: one case in test_a_missing_moves_file_with_move_voiced_packages_fails with a move-voiced + malformed-track package
Task 4: minor (deferred, FINAL-REVIEW MUST TRIAGE — strict surface 2): _scan_broad's first except arm (pkg.manifest() raises on valid-JSON-but-bad manifest) emits a row with no voiced_source, so require_present cannot count it; identity(_raw_manifest(...)) would close it
Task 4: minor (deferred): identity() omits `voiced`, so error rows carry voiced_by but voiced=False — carried to T5/T7 dispatch as a heads-up
Task 4: minor (deferred): status --state bogus with a bad moves.json reports the moves error first (strict-first; noted)
Task 4: cannot-verify items resolved by plan ownership: voice loads moves (T5), --json delivered_profile/profile_source/tts + "(from …)" (T8), stale note (T7/T8), move_problem error rows (T7). Intermediate T4→T5 state re-voices rule-moved packages every run — no real-station run until T5 lands (none planned)
Task 4: complete (commits c5760a0..9fe43c2, review clean)
- 2026-10-16T14:52:10-0400 Task 5 implementer dispatched: Opus (t5-impl, agent a5ff1291367c1ff43), BASE 9fe43c2; meter 5h 0% (new window) / 7d 89%
- 2026-10-16T14:52:27-0400 PARENT RULING (llama-ed): final-review fix wave MUST include (a) a test pinning the surviving T4 _scan_broad mutant; (b) close the arm: a JSON-readable but structurally wrong manifest whose raw dj_audio.profile_source == "move" counts toward the missing-moves.json check (unreadable JSON stays a documented limit); (c) fold unicodedata NFC into normalize_artist (T1 minor). Not optional.
- 2026-10-16T14:57:19-0400 Task 5 implementer DONE: 9960cf3 (suite 3069 passed, 1 skipped, 8 deselected; RED captured)
Task 5: minor (deferred): models.py module docstring still says emcee blocks are "shape-identical" to llama's DJAudio (check T9 updates it)
Task 5: minor (deferred): voice --fresh help text silent on moves/artist rules
- 2026-10-16T14:57:35-0400 Task 5 reviewer dispatched: Opus (t5-rev, agent a14e68dc215f817e9), range 9fe43c2..9960cf3
- 2026-10-16T15:00:21-0400 Task 5 review: spec ✅, quality Approved, 0 Critical/Important (t5-rev)
Task 5: minor (deferred): bed computed twice (speech_for_voicing's bed discarded at cli.py:226; process.py:312 recomputes) — plan-mandated return type
Task 5: minor (deferred): SpeechProvider Protocol does not declare voice/model though TTSRecord depends on them
Task 5: minor (deferred): pre-existing llama fork() DeprecationWarnings in full-suite output
Task 5: minor (deferred, runbook candidate): _process_one clears dj_audio before process_package, so a failed re-voice of a move-voiced package loses its "move" record and the missing-moves.json guard no longer counts it (two independent failures; within spec's acknowledged limit)
Task 5: cannot-verify: run-side error row for an invalid move target — owned by Task 7 (verify there)
Task 5: complete (commits 9fe43c2..9960cf3, review clean)
- 2026-10-16T15:00:53-0400 Task 6 implementer dispatched: Sonnet (t6-impl, agent a1b62b35ce6a8adbe), BASE 9960cf3; meter 5h 1% / 7d 89%
- 2026-10-16T15:02:56-0400 Task 6 implementer DONE: 1f609d0 (suite 3110 passed, 1 skipped, 8 deselected; RED 36 failed)
- 2026-10-16T15:03:12-0400 Task 6 reviewer dispatched: Opus (t6-rev, agent a04e498c4f2130750), range 9960cf3..1f609d0
- 2026-10-16T15:05:21-0400 Task 6 review: spec ✅, quality Approved, 0 Critical/Important (t6-rev)
Task 6: minor (deferred, FINAL-REVIEW SHOULD TRIAGE — strict surface 2): writer/reader mismatch — with [assign.profiles.""] configured, `emcee move X ""` writes "profile": "" which load_moves rejects; reported as success exit 0, then every command hard-fails. Fix: record_move validates before write (or Assign forbids empty profile names)
Task 6: minor (deferred): --list marks a stale --delivered exemption to an unassigned profile "[no assign entry]" on a missing row (re-implements target_problem; untested)
Task 6: minor (deferred): unchanged move does not refresh renamed package name (dup of T2 minor)
Task 6: minor (deferred): broad except Exception around post-write assess (cli.py) — narrow to (EmceeError, OSError)
Task 6: minor (deferred): usage-error test checks only exit code
Task 6: complete (commits 9960cf3..1f609d0, review clean)
- 2026-10-16T15:05:56-0400 Task 7 implementer dispatched: Opus (t7-impl, agent aadfbe418552765b9), BASE 1f609d0; meter 5h 2% / 7d 89%
- 2026-10-16T15:08:24-0400 Task 7 implementer DONE: 441b586 (suite 3129 passed, 1 skipped, 8 deselected; RED 19 failed)
Task 7: minor (deferred): --yes and new exit codes documented only in CLI help (T9 docs should cover README/CLAUDE.md)
- 2026-10-16T15:08:42-0400 Task 7 reviewer dispatched: Opus (t7-rev, agent a8d2820c37e5b915b), range 1f609d0..441b586
- 2026-10-16T15:12:14-0400 Task 7 review: spec ✅, quality Needs fixes — 1 Important (plan-mandated): test_eof_at_the_prompt_spends_nothing is vacuous (run's per-package except swallows forbid_spend's AssertionError into an error row; an "EOF means yes" mutant SURVIVED all 19 tests)
Task 7: Ruling: fix it, and fix the class — forbid_spend also records each attempt so a swallowed spend is still visible; the EOF and declined tests assert no attempts, no "error:", no "voiced:" — strict surface 1 is the plan's top stake and its only EOF test must be able to fail; cost if wrong: a helper change touching T4-T7 tests
Task 7: minor (deferred): _stdin_is_tty raises AttributeError when sys.stdin is None (fails closed, with a traceback)
Task 7: minor (deferred): -y alias and bare-Enter default decline untested
Task 7: minor (deferred): test_run_cmd.py:437 weakened stderr=="" to "error:" not in stderr (brief-mandated)
Task 7: minor (deferred): --assigned/--profile filter silently drops a package whose move targets an unassigned profile (no error row unless unfiltered); pre-existing filter semantics
Task 7: minor (deferred): EOF/Ctrl-C exits 1 "Aborted." — exit-code docstring does not mention it
- 2026-10-16T15:12:30-0400 Task 7 fix round 1 dispatched: resumed Opus implementer (t7-impl), FIX_BASE 441b586
- 2026-10-16T15:15:17-0400 Task 7 fix round 1 DONE: 16fc790 (suite 3129 passed; mutant proof: EOF test now fails under the Abort→True mutant)
- 2026-10-16T15:15:35-0400 Task 7 re-review dispatched: Opus (t7-rerev1, agent a8d7d9b9cf06a6f3c), range 441b586..16fc790
Task 7: fix round 1/5 (1 addressed, 0 open; commits 441b586..16fc790)
Task 7: minor (deferred, final review): other forbid_spend callers (test_recording, test_profile_readiness, test_move_cmd) ignore the returned attempts list — check for broad-catch blindness there
Task 7: complete (commits 1f609d0..16fc790, review clean after 1 fix round)
- 2026-10-16T15:16:37-0400 GATE (a) reached at 16fc790: scratch station prepared at scratchpad/gate-a; non-TTY path verified by orch (plan, refusal, rc=1, manifest unchanged); interactive check sent to llama-ed
- 2026-10-16T16:30:24-0400 GATE (a) PASSED (llama-ed): interactive n -> 'nothing voiced' rc0; </dev/null -> refusal rc1, no Proceed; manifest unchanged. Go for Task 8.
- 2026-10-16T16:30:57-0400 Task 8 implementer dispatched: Sonnet (t8-impl, agent a1f72c1abc12abe0d), BASE 16fc790; meter 5h 3% / 7d ~90%
- 2026-10-16T16:32:18-0400 Task 8 implementer DONE: 3cb8b00 (suite 3136 passed, 1 skipped, 8 deselected; RED 5 failed)
- 2026-10-16T16:32:35-0400 Task 8 reviewer dispatched: Opus (t8-rev, agent a45c5e713767cfdb7), range 16fc790..3cb8b00
- 2026-10-16T16:33:53-0400 Task 8 review: spec ✅, quality Approved, 0 Critical/Important (t8-rev); display-only diff, state untouched
Task 8: minor (deferred): unused `from pathlib import Path` in test_status_profiles.py:4 (plan-mandated)
Task 8: minor (deferred): no test of unsupported/error row's profile cell under a rule/move
Task 8: complete (commits 16fc790..3cb8b00, review clean)
- 2026-10-16T16:34:52-0400 GATE (b) run by orch (read-only): main @16f0e72 (root .venv -> main checkout) vs branch @3cb8b00 (worktree .venv); no [assign.artists], no moves.json; status --json rows main=341 branch=341, ZERO differences (219 ready, 122 pending both); ~/.emcee unchanged, no lock created. Waiting on llama-ed go for Task 9.
- 2026-10-16T16:35:45-0400 GATE (b) independently confirmed by llama-ed. Go for Task 9 + final review + fix wave. PARENT RULING: T6 empty-profile write (record_move validates before write) joins the mandatory final-wave items.
Ruling: Task 9 dispatch also carries two doc-only fixes from deferred minors (emcee models.py "shape-identical" docstring → "shape-compatible"; CLAUDE.md resolve_assignment "keyed off manifest source.profile" → effective profile) — they sit in T9's files and are cheaper there than in the final wave; cost if wrong: one extra docstring line in T9's diff
- 2026-10-16T16:36:04-0400 Task 9 implementer dispatched: Sonnet (t9-impl, agent a94bab51307705b33), BASE 3cb8b00
- 2026-10-16T16:37:52-0400 Task 9 implementer DONE: e7821fa (suite 3137 passed, 1 skipped, 8 deselected; RED 1 failed)
- 2026-10-16T16:38:12-0400 Task 9 reviewer dispatched: Opus (t9-rev, agent acb4d896850af9bf6), range 3cb8b00..e7821fa
Orch note (final wave): CLAUDE.md:109 still says emcee run `--profile` "limits it to those llama profiles' packages" — selection is by effective profile (same staleness as T4's cli.py:322 help minor)
- 2026-10-16T16:40:57-0400 Task 9 review: spec ✅, quality Needs fixes — 1 Important: CLAUDE.md:109-112 (+215-217, README 315-316) still describe run --profile/--assigned and [assign] keying by llama's delivered profile; they select by EFFECTIVE profile
Task 9: Ruling: the fix round also corrects CLAUDE.md:108 "only problem is missing track audio" (code skips ANY pending package with missing tracks) — it is the same defect class (a doc claim the code contradicts), not polish; cost if wrong: one extra sentence edit
Task 9: minor (deferred): runbook bullet "until emcee voice <show> succeeds" — next emcee run also retries
Task 9: minor (deferred): emcee models.py:4-5 stacked parentheticals
Task 9: minor (deferred): CLAUDE.md long unwrapped inserted lines (cosmetic)
Task 9: minor (deferred): CLAUDE.md:104 "its own six models" count stale (pre-existing)
- 2026-10-16T16:40:57-0400 Task 9 fix round 1 dispatched: resumed Sonnet implementer (t9-impl), FIX_BASE e7821fa
- 2026-10-16T16:42:31-0400 Task 9 fix round 1 DONE: 885dad4 (suite 3137 passed)
- 2026-10-16T16:42:49-0400 Task 9 re-review dispatched: Opus (t9-rerev1, agent ab138523fd415c64f), range e7821fa..885dad4
Task 9: fix round 1/5 (2 addressed, 0 open; commits e7821fa..885dad4)
Task 9: minor (deferred): cli.py:436-438 run docstring still says "whose only problem is missing track audio" (shows in emcee run --help)
Task 9: minor (deferred): docs/station-brief.md:78-81 presenter chosen by source.profile — no mention of moves/rules
Task 9: complete (commits 3cb8b00..e7821fa..885dad4, review clean after 1 fix round)
- 2026-10-16T16:44:19-0400 FINAL whole-branch review dispatched: Opus (final-rev, agent a2b6d7542887b8eb6), range 16f0e72..885dad4 (12 commits), triage list final-triage-list.md
- 2026-10-16T16:50:43-0400 FINAL review: Ready after fixes; 0 Critical; Important I1 (T4 _scan_broad arm 1 + arm-2 mutant still survives at HEAD); Minor M1 (empty profile names: config + write_moves validates), M2 (NFC after casefold + keep combining marks), M3 (run --help docstring), M4 (station-brief), M5 (runbook), M6 (identity voiced, optional). Verdict file final-rev/handback.md
Ruling: final fix wave = I1 (a,b) + M1..M6 in ONE dispatch on Opus — it touches two strict surfaces (2 via _scan_broad/moves writer) across cli/station/moves/config/artists plus tests, so judgment over mechanics; cost if wrong: Opus spend on partly mechanical doc lines
Ruling: final reviewer's OK-TO-DEFER verdicts accepted for all other deferred minors (reasons in final-rev/handback.md triage table) — cost if wrong: those minors ship as known debt, listed in the finish report
- 2026-10-16T16:51:10-0400 FINAL fix wave dispatched: Opus (final-fix, agent a3826871170baa0c8), FIX_BASE 885dad4
- 2026-10-16T17:01:14-0400 FINAL fix wave DONE: e76feb0 fe69b04 945c912 074e018 (suite 3152 passed, 1 skipped, 8 deselected; I1 mutant now caught 4/4 as predicted)
Final: minor (deferred): write_moves refusal reuses the reader's "unreadable or malformed … fix or restore it" wording on a write (CLI never reaches it for "")
- 2026-10-16T17:01:34-0400 FINAL re-review dispatched: Opus (final-rerev, agent a0f558fa7dff6fdbd), range 885dad4..074e018
Final: fix wave re-review: all of I1, M1-M6 ADDRESSED; each _scan_broad arm's voiced_source mutant now caught independently; no new Critical/Important (final-rerev)
Final: minor (deferred): an unsupported (int schema_version < 3) package with a recorded profile_source "move" carries no voiced_source, so it does not count toward the missing-moves guard (hand-downgrade/old-llama redelivery only)
- 2026-10-16T17:04:31-0400 orch: verifying full suite at 074e018 myself before the finish report
- 2026-10-16T17:05:48-0400 orch VERIFIED: `./.venv/bin/python -m pytest -q -p no:cacheprovider` at 074e018 → 3152 passed, 1 skipped, 8 deselected, rc 0 (emcee/llama __file__ inside worktree)
Ruling: SDD workspace and $D NOT deleted at finish — the parent ratifies from the verdict files there; cost if wrong: git-ignored scratch lingers until the parent removes the worktree (copy the ledger into the repo first if it is to be kept)
- 2026-10-16T17:05:48-0400 FINISH MENU reached @ 074e018 (16 commits on 16f0e72). Tick 28d2e121 deleted, armed flag removed. No merge/push/tag.
