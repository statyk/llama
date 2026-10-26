# SDD ledger — plan: docs/superpowers/plans/2026-10-25-scheduler.md

Peer orchestrator session 6a271170-52a3-49a3-b4db-a9d5cd08acfc; parent llama-69.
Worktree /Users/shawn/projects/llama/.claude/worktrees/scheduler, branch playout-scheduler, start 02b6d49.
Spec: docs/superpowers/specs/2026-10-25-scheduler-design.md (binding authority).
$D = .superpowers/sdd/scheduler ; SDD workspace (briefs, review packages) = .superpowers/sdd/2026-10-25-scheduler

## Escapes
- Task 5 implementer: tests written after code; one red commit amended to green (mandate 4)
- Task 10 fix-round implementer: left a background wrapper hung on stdin (stray `cat > /tmp/dummy`); controller killed it after confirming rc=0 — the kill released the wrapper, which re-ran the measurement into the worktree (cache-only, no share access); controller restored the files
- Task 10 fix round 3 implementer: mutant test copies created in the live tests dir (mandate 5), deleted afterwards

## Pre-flight scan

Per-task self-consistency:

| Task | Check | Found |
|---|---|---|
| 1 | tests vs Interfaces: PlanRow built without run_start/cut_frame | ok: both already default (layout.py:31-32) |
| 1 | files vs commit list | ok |
| 2 | lock tests vs Interfaces (PlanLocked text, CLI exit 1) | ok |
| 3 | probe gate text: plan says escalate before Task 8 | conflicts with parent brief (gate before Task 11; Tasks 4-9 proceed) -> Ruling R1 |
| 4 | IMPLICIT_CLOCK wiggle 720 vs "effective window positive" | ok |
| 5 | commit lists test_config.py, test_render.py; Files list omits test_config | ok (config template test must stay green) |
| 6 | new `pieces.Piece` vs existing `layout.Piece` (segment piece) | name collision across modules -> Ruling R2 |
| 7 | history step not in STEP_CODES; ungated | ok, self-consistent |
| 8 | modifies planner.py (shuffle_rank -> rules.tie_rank, re-export) | ok; Task 11 removes re-export |
| 9 | typical_id_frames = median ID length | ok |
| 10 | Step 3 reads /Volumes/media/lma-radio/delivered (read-only, Mac) | mounted; read-only use is the plan's own step, not "touching the live station" -> Ruling R3 |
| 11 | mutation step uses scratch copy + PYTHONPATH | matches mandate 5 |
| 12 | antenna npm ci needs network | ok |
| 13 | consumes Station.scan_pieces(read_only) from Task 11 | ok, ordered after 11 |
| 14 | docker check | docker running on this Mac (2026-10-25 09:33) |

Pairs sharing a file/interface:

| Pair | Producer -> consumer | Found |
|---|---|---|
| 1 / 7 / 11 / 13 | PlanRow fields -> AiredRow, to_row, report | consistent field names (kind, block, nominal_start, role, miss, degraded, fill, bends, names, package, announcement_broken) |
| 1,2,7,11,13 | service.py edited in five tasks | serial, no overlap |
| 2,5,13 | cli.py edited in three tasks | serial |
| 3 / 6 | estimate_frames, LengthCache; pieces.py created in 3, extended in 6 | ok |
| 4 / 5 / 9 | Occurrence, AnnounceConfig -> announce.text_for, project | ok |
| 5 / 6 / 11 | interstitials.scan meta sizes -> estimate_frames on a clip; row_dir -> clip_dir | ok |
| 7 / 8 / 9 / 11 | Recency.with_piece, recency(...) | ok |
| 8 / 9 | fill_block signature (boundary_frames, final_boundary_frames) | ok |
| 8 / 11 | planner.shuffle_rank re-export removed in 11 | ok |
| 9 / 10 / 11 / 13 | project(until_frame, ahead) | ok |
| 3 / 8 / 11 | probe gate (plan: before 8; brief: before 11) | Ruling R1 |

## Rulings

- Ruling R1: the hugo-probe escalation gate sits before Task 11, not Task 8; Tasks 4-9 proceed while the operator runs the probe — the parent's brief and the handoff (both later than the plan text, and binding) say so; estimates only steer choice and written rows are exact — cost if wrong: Tasks 8-9 built on an estimate premise that fails, reworked before 11 anyway.
- Ruling R2: `pieces.Piece` (new) and `layout.Piece` (segment piece) coexist under the plan's names; implementers are told to import them module-qualified where both are in scope — the plan names `Piece` and the spec calls it a piece; renaming would diverge from the plan text — cost if wrong: a confusing import, fixable by rename later.
- Ruling R3: Task 10's measurement reads the mounted delivered library (/Volumes/media/lma-radio/delivered) read-only from this Mac; nothing touches hugo, R2 or Cloudflare — it is the plan's own step and the parent asked for the numbers — cost if wrong: none to the station (read-only).
- Ruling R4: implementers run strictly one at a time (never two writers in the worktree, never a reviewer running tests against a tree another child is editing) — the plan allows no explicit overlap, and all tasks commit in one worktree — cost if wrong: wall-clock only.

## Log
- 2026-10-25T09:33:29-0400 Task 1: implementer dispatched (Sonnet), BASE 02b6d49
- 2026-10-25T09:36:23-0400 Task 1: implementer DONE 4fa87a7 (586 passed, 1 skipped); reviewer dispatched (Opus) on 02b6d49..4fa87a7
- 2026-10-25T09:39:08-0400 Task 1: review Needs fixes — Important: (I1) test_publish_site_never_asks_for_an_interstitial_analysis does not pin its guard (row outside published window); (I2) to_json writes every scheduler field, so this deploy-first build rewrites phase-1 plans into a shape the previous build rejects; runbook text understates it. Verdict sha256 above in orch.log.
- Ruling R5: Task 1 to_json omits scheduler fields (kind, block, nominal_start, role, miss, degraded, fill, bends, names, package, announcement_broken) when they hold their default; phase-1 fields always written as before; runbook says this commit alone stays reversible to the previous build until the scheduler writes its first scheduler row, and a pre-commit build cannot read a plan holding scheduler rows — the spec's purpose for the deploy-first reader is safe rollback, and the brief's "known fields via dataclasses.fields" did not consider that a rewrite of phase-1 rows would wedge the previous build — cost if wrong: none to correctness (from_json defaults missing keys); only the on-disk row shape differs from the plan text.
- Task 1: minor (deferred): scheduler fields not type-checked on read beyond kind (bends/names element types) — revisit when Task 7/11 first read them
- Task 1: minor (deferred): extra is read-only one level deep only
- Task 1: minor (deferred): key literally named "extra" round-trip untested
- Task 1: minor (deferred): status_lines "on air" line would name an interstitial slug (service.py:439) — carry to Task 13
- 2026-10-25T09:39:33-0400 Task 1: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 4fa87a7, dir task1-fix1
- 2026-10-25T09:40:42-0400 Task 1: fix round 1 implementer DONE af46d72 (588 passed, 1 skipped); re-review dispatched (Opus) on 4fa87a7..af46d72
- 2026-10-25T09:42:18-0400 Task 1: fix round 1/5 (2 addressed, 0 open; commits 4fa87a7..af46d72); re-review verdict sha256 3518f53c23e0ec2f5b34d7fd57d96f9caf00d1061b529e11355d88f0aa53f62a
- Task 1: minor (deferred): to_json "known fields win" no longer holds for a default-valued known field present in a hand-built extra (unreachable via from_json) — skip extra keys in the known set
- Task 1: complete (commits 02b6d49..af46d72, review clean)
- 2026-10-25T09:42:18-0400 GATE 1: stopped after Task 1; reported to llama-69; waiting for go (operator deploys the tolerant reader to hugo first)
- 2026-10-25T09:43:38-0400 llama-69: hold at gate 1; run Debian-12 gate at af46d72 (running in background, log scratchpad/deb12-af46d72.log)
- 2026-10-25T09:44:38-0400 Debian-12 gate at af46d72: Python 3.11.2, ffmpeg 5.1.9-0+deb12u1, 589 passed in 21.30s, rc=0
- 2026-10-25T10:36:00-0400 GATE 1 cleared by llama-69 (af46d72 deployed to hugo). Task 2: implementer dispatched (Sonnet), BASE af46d72
- 2026-10-25T10:38:30-0400 Task 2: implementer DONE 36d3979 (592 passed, 1 skipped); reviewer dispatched (Opus) on af46d72..36d3979
- 2026-10-25T10:40:29-0400 Task 2: review Approved (Opus), verdict sha256 cb40b85c538f20a256019627bd6536afbb3228ce7e95e086d07dc47e8d2f8fbc
- Task 2: minor (deferred): service._step docstring/comment still name only PublishLocked (service.py:227-231, 247) — carry to Task 7 (also edits service.py)
- Task 2: minor (deferred): CLI lock test asserts result.exception, not main_cli's stderr "error: …" line
- Task 2: minor (deferred): locks.plan_lock duplicates publish.publish_lock's flock idiom
- Task 2: minor (deferred): cli plan/render take the lock after open_station (epoch write only, under epoch.lock)
- Task 2: complete (commits af46d72..36d3979, review clean)
- 2026-10-25T10:40:30-0400 Task 3: implementer dispatched (Sonnet), BASE 36d3979
- 2026-10-25T10:43:09-0400 Task 3: implementer DONE_WITH_CONCERNS 162e7e3 (605 passed, 1 skipped; RED not captured separately; ShowAnalysis.meta now carries sizes; probe runs ffmpeg via aacenc.extra_frames with a system tempfile); reviewer dispatched (Opus)
- 2026-10-25T10:49:00-0400 Task 3: review Needs fixes (Opus), verdict sha256 fadb8ed702e4c3d3757a85f690a3fad9820ebc6c32a40b1a7cae6c6e313c217c. Important (plan-mandated): test_file_set_key_unchanged is tautological (mutant changing key bytes survived the whole suite).
- Ruling R6: fix the plan-mandated tautological key test with an independently computed pre-task key; also fold into this round, because the probe ships to the operator now and the tests are cheap: in-tag false sync in the ID3 test (M6) plus MPEG-2.5, reserved-index and >64 KiB cases; isfinite/non-negative guard on total_duration_sec; probe refuses a missing --config file — the key test is the only guard on the refactor most able to disrupt hugo; the rest are minutes of work — cost if wrong: a slightly larger fix diff.
- Task 3: minor (deferred, carry to Task 6/8): estimate_frames lets OSError from a vanished clip propagate — map to the fallback or treat as ineligible
- Task 3: minor (deferred, carry to Tasks 6/11): ShowAnalysis.meta now freezes total_duration_sec/voiced_profile; read estimate inputs and voiced_profile from live Show.meta only, tolerate absence in old cache files
- Task 3: minor (deferred): mp3info _RATES unused, emphasis 0b10 not rejected; syncsafe decode duplicates id3._unsyncsafe; probe re-derives cache_dir and back-computes bitrate in _is_64k
- Task 3: minor (deferred): RED not captured by the implementer (mutation run stands in)
- 2026-10-25T10:49:17-0400 Task 3: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 162e7e3
- 2026-10-25T10:50:31-0400 Task 3: fix round 1 implementer DONE 084d6f9 (609 passed, 1 skipped; 6 mutants killed as predicted); re-review dispatched (Opus)
- 2026-10-25T10:52:14-0400 Task 3: fix round 1/5 (4 addressed, 0 open; commits 162e7e3..084d6f9); re-review verdict sha256 a92b0896293296ee1a9bcfdf612d46d469ff3089f2727d4ec94ca142cc6e3cdf
- Task 3: minor (deferred): a 400-digit integer total_duration_sec raises OverflowError in isfinite (unchanged behaviour)
- Task 3: complete (commits 36d3979..084d6f9, review clean)
- 2026-10-25T10:52:14-0400 GATE 2: probe ready (report-and-continue). Note: probe imports transmitter.mp3info/pieces, absent from hugo's deployed af46d72 — operator must run it with PYTHONPATH at a copy of 084d6f9's packages/transmitter/src.
- 2026-10-25T10:52:14-0400 Task 4: implementer dispatched (Sonnet), BASE 084d6f9
- 2026-10-25T10:54:37-0400 Task 4: implementer DONE 57a15a6 (635 passed, 1 skipped; extra validation: ascending years, no repeated weekday, HH:MM start; last-good write OSError swallowed); reviewer dispatched (Opus)
- 2026-10-25T10:59:12-0400 Task 4: review Needs fixes (Opus), verdict sha256 53d042c380508c68bede635252aed10728d93a7e21487d96b1394a261148ff15. Important: TOML inf in any window field loads, is saved as last-good, then OverflowError in occurrences() every plan step; huge finite window overflows us_to_iso.
- Ruling R7: fix round 1 = allow_inf_nan=False on the clock's strict base (with a comment why it is stricter than config's), window minutes bounded to <= one week (7*24*60; IMPLICIT 720 fits), ConfigError tests for inf windows and inf concert_gap_days; plus the cheap spec-required test gaps (last-good rewritten only when bytes differ; failed copy swallowed; unreadable clock falls back), UTF-8 decode in load_clock, max_shows=0 asserting ConfigError — the headline invariant is "a clock that loads cannot crash planning" — cost if wrong: an operator window over a week is refused (meaningless anyway).
- Task 4: minor (deferred, carry to Tasks 8/9/13): Occurrence is unhashable (BlockConfig) — key sets/dicts on occ.key; IMPLICIT_CLOCK is a shared mutable model
- Task 4: minor (deferred, carry to Task 8): Prefer weight > 0 and on_this_day >= 0 are undocumented constraints — confirm against the additive score; document in runbook (Task 14)
- Task 4: minor (deferred, carry to Task 11): live_clock problem text is pydantic's multi-line message with URLs — make the clock alert readable
- Task 4: minor (deferred, carry to Task 5): templates validated with str dummies — the renderer must pass strings for title/time
- 2026-10-25T10:59:29-0400 Task 4: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 57a15a6
- 2026-10-25T11:00:42-0400 Task 4: fix round 1 implementer DONE 6a230bc (640 passed, 1 skipped; 3 mutants killed as predicted); re-review dispatched (Opus)
- 2026-10-25T11:02:50-0400 Task 4: fix round 1/5 (4 addressed, 0 open; commits 57a15a6..6a230bc); re-review verdict sha256 2df8308036343413f7ba374f5db25b36f822cca0a1862996f4268932fb0c5fef
- Ruling R8 (out-of-scope Important from Task 4 re-review): concert_gap_days = 0 loads; Task 8's scorer must guard it — 0 means "no minimum gap": the gap rule never counts a violation, and the recency term is 0.9 for any aired show (1.0 never aired); every gap comparison in float (never timedelta/int conversion of the field) — carried into Task 8's dispatch — an operator may plausibly set 0 to disable the rule, so rejecting it would be the wrong call — cost if wrong: one extra branch in the scorer.
- Task 4: minor (deferred, carry to Task 8): huge finite weights/on_this_day load (inf sums, no crash); max_shows up to int64 loads (bounded by pool in the search)
- Task 4: complete (commits 084d6f9..6a230bc, review clean)
- 2026-10-25T11:02:50-0400 Task 5: implementer dispatched (Sonnet), BASE 6a230bc
- 2026-10-25T11:07:12-0400 Task 5: implementer DONE 684d323 (654 passed, 1 skipped; ffmpeg single-clip render test ran). Process escape: implementation written before tests (RED reconstructed by moving modules aside); a red commit was amended to green (mandate 4 bent, final commit green). Concerns: "present" ignores quiet period; daily single block needs 4 ids; needed() looks 2 days past span. Reviewer dispatched (Opus).
- 2026-10-25T11:12:39-0400 Task 5: review Needs fixes (Opus), verdict sha256 4e18e21aecfc87289c3fb5ef56be4788075485c6edd28b23197ef0a78a7a4cc4. Important (brief-mandated assertion vacuous): announcements test always passes --clock, so live_clock(save=False) is unpinned (mutant save=True survived).
- Ruling R9: fix round 1 = live-clock invocation test (no --clock, clock under TRANSMITTER_ROOT, assert no clock.last-good.toml; invalid live clock pins the note path); InterstitialsConfig rejects a relative dir (a relative path resolves against the service cwd, and row_dir's invariant breaks); scan uses one stat per clip (file_set_key_and_sizes + S_ISREG); cheap tests for per-file OSError skip, a directory named id-x.mp3, needed()'s until bound, --clock bad file exits 1; one stderr note when no interstitials folder exists — small and cheap; the relative-dir case would write rows render resolves elsewhere — cost if wrong: an operator with a relative dir gets a ConfigError instead of a silently wrong path.
- Ruling R10: the self-following two-block announcement ("Stay tuned for Funk at 7 Eastern, followed by Funk at 7 Eastern" when the occurrence after X is X's own block the next day, and more generally a following occurrence on a later day read as a bare time) stays as the spec literally says for now; escalated to llama-69 as an operator question before any clip is voiced (ids are a contract); whichever rule the operator picks must apply identically in announce.needed() and Task 9's placement — the spec's qualification rule is followed literally and changing announcement semantics is the operator's call — cost if wrong: none until clips are voiced; a rule change later is a small edit in two places.
- 2026-10-25T11:12:55-0400 Task 5: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 684d323
- 2026-10-25T11:14:40-0400 Task 5: fix round 1 implementer DONE 0afcb9a (663 passed, 1 skipped; tests first, RED captured; mutants not re-run); re-review dispatched (Opus)
- 2026-10-25T11:17:20-0400 Task 5: fix round 1/5 (5 addressed, 0 open; commits 684d323..0afcb9a); re-review verdict sha256 4a397647f4670827118a92649a08b6d149af11382ae255711650337ef1bd094b
- Task 5: minor (deferred): invalid-live-clock note assertion is loose ("note: " and "clock"); folder-missing (not None) note branch unasserted
- Task 5: minor (deferred): scan's two stats leave a self-healing window (quiet/size from stat 1, key from stat 2); "~/..." dir rejected as relative (not expanded)
- Task 5: complete (commits 6a230bc..0afcb9a, review clean)
- 2026-10-25T11:17:20-0400 Task 6: implementer dispatched (Sonnet), BASE 0afcb9a
- Task 6 carried: OSError-in-estimate fallback (Task 3 minor), live Show.meta only (Task 3 minor)
- 2026-10-25T11:19:17-0400 Task 6: implementer DONE a649f78 (676 passed, 1 skipped; addition: manifest-only estimate falls back to summed track duration_sec when total_duration_sec invalid); reviewer dispatched (Opus)
- 2026-10-25T11:22:37-0400 Task 6: review Approved (Opus), verdict sha256 3bfaf612a24ca31704c99e89c41c7b86ef1ad56835c52619a0c266b1b908b310
- Task 6: minor (deferred): manifest-only fallback sums track duration_sec when total_duration_sec absent (inconsistent with estimate_frames counting 0; untested; practically dead)
- Task 6: minor (deferred): a malformed v3 manifest (show/source not an object, list in set_intros) crashes scan_delivered (same class as station.evaluate)
- Task 6: minor (deferred): m- key asserted by prefix/length only; voiced-but-ineligible branch untested; Piece date parsing untested on odd dates
- Task 6: minor (deferred): manifest-only Show entry order is not broadcast order (descriptive only)
- Task 6: ⚠️ carry to Task 11: LengthCache must be built with the Station's pause_samples and engine.extra_frames()
- Task 6: complete (commits 0afcb9a..a649f78, review clean)
- 2026-10-25T11:22:37-0400 Task 7: implementer dispatched (Sonnet), BASE a649f78
- 2026-10-25T11:25:42-0400 Task 7: implementer DONE_WITH_CONCERNS 69c7c58 (685 passed, 1 skipped; RED not isolated; test_systemd watchdog ping count 5->6; local_date as ISO strings; artists_on not deduped); reviewer dispatched (Opus)
- 2026-10-25T11:30:53-0400 Task 7: review Needs fixes (Opus), verdict sha256 5d53d718f27b427376f3da8aef54fd2de3f2e0454529f5adc1f6f0c0be168dae. Important: (I1) a crash-left partial line is joined by the next append (permanent corrupt line, warning every minute, out-of-order rows); (I2) load_aired admits rows recency() cannot use (missing start -> ValueError; string start_frame -> duplicate append) — would stop Task 8's plan step.
- Ruling R11: fix round 1 = both Importants plus minors folded in because Task 8 builds directly on this: epoch guard (skip with alert history unless publish state's epoch_id matches); pin placement after publish, .last vs listed bound, no end_observation error; the end==now boundary; index Recency by package/clip slug/local date at build time (interface unchanged); reuse pieces._date_parts for the year; local_date typed datetime.date — cheaper now than after Task 8 depends on it — cost if wrong: a larger fix diff.
- Task 7: minor (deferred): aired start_us at ms precision vs plan rows at µs; append_aired re-reads both files every tick (O(history)); test_systemd comment wording
- 2026-10-25T11:31:12-0400 Task 7: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 69c7c58
- 2026-10-25T11:33:25-0400 Task 7: fix round 1 implementer DONE c9568c8 (693 passed, 1 skipped; RED 5 failures captured; item-4 mutants not run); re-review dispatched (Opus)
- 2026-10-25T11:37:07-0400 Task 7: fix round 1/5 (8 addressed, 0 open; commits 69c7c58..c9568c8); re-review verdict sha256 98bb72c0c2e6f7aba29f13b1a61877ca7fa03039b2fa2ec985ed1df0fe6fc005; 11 mutants caught
- Task 7: minor (deferred, carry to Task 11 — where recency enters the plan step): AiredRow.package not type-checked (list/dict package makes recency() raise)
- Task 7: minor (deferred, carry to Task 9): Recency is unhashable (dict fields) — do not hash SchedulerInput
- Task 7: minor (deferred, runbook Task 14): a crash fragment in aired.jsonl stays and is warned on every load; epoch-mismatch history alert repeats per repeat window
- Task 7: complete (commits a649f78..c9568c8, review clean)
- 2026-10-25T11:37:07-0400 Task 8: implementer dispatched (Opus, per plan header), BASE c9568c8
- OPERATOR RULINGS 2026-10-25 (via llama-69, binding, verbatim):
  1. Announcement two-block forms (`next`, `later`): use them only when the following occurrence is a DIFFERENT block AND starts within 12 hours of X's start; otherwise use the one-block forms (`next_one`, `later_one`). Apply identically in announce.needed() and Task 9's placement. Make the 12 h a named module constant (not config). Fold the change into Task 5's code as its own small reviewed commit (Opus review) at a point that doesn't collide with Task 8's writer, or into Task 9's dispatch if that is cleaner — your call, but it must land before Task 10.
  2. `concert_gap_days = 0` means no gap rule (the rule is disabled). R8 stands as dispatched.
  3. Hugo probe: operator is running it now; results to follow before Task 11.
- 2026-10-25T11:44:36-0400 Ruling R12: operator ruling 1 lands as the FIRST commit of Task 9's dispatch (announce.needed() + a shared predicate in announce.py, constant TWO_BLOCK_MAX_HOURS = 12, tests), then Task 9's placement uses the same predicate; reviewed by Task 9's Opus reviewer as part of that diff — avoids a second writer during Task 8 and keeps the predicate single-sourced — cost if wrong: Task 9's review package is slightly larger. R10 superseded.
- 2026-10-25T12:15:23-0400 Task 8: implementer DONE_WITH_CONCERNS dec0016,05f6699,5acb9f5 (742 passed, 1 skipped; 3000-pool 3.7-244 ms/call; 14/16 mutants caught, 2 tie-only). Deviations: value = fsum(score-1) - distance (not mean); tier 1 ranks own-show count first; rule-aware greedy; no piece twice in a block; fill_block re-runs search per added show for continuation closure. Concern for Task 9: projection 'used' vs live persisted rows inconsistency. Reviewer dispatched (Opus).
- 2026-10-25T12:16:39-0400 llama-69: deviations (1) fsum vs mean and (2) tier-1 own-count-first need the operator's ruling; after Task 8's review and fix rounds, report verdicts on (1)-(5) with a concrete example each for (1) and (2), and HOLD before Task 9 until the ruling is relayed. Asked the Task 8 reviewer to add the examples.
- 2026-10-25T12:25:11-0400 Task 8: review Needs fixes (Opus), verdict sha256 75bef4bd45f39e0bf7f003316be4df3342d8fe7976567181c8453c83b7ad2510. Important: (I1) fill_cause reports "structural" for pool-short blocks when fill follows >= 2 own shows (24/1032 tier-1 fixture blocks); (I2) no-repeat-within-block (deviation 4) reorders the operator-confirmed compromise order — needs operator ruling. Deviations 1,2 spec-consistent, operator ruling pending; 3,5,6 accepted.
- Ruling R13: fix round 1 = I1 (cause computed once per call from the block's own start over own_all incl. placed own shows, test with the reviewer's a/b/c/f example) plus minors 2 (offer-level agreement test covering _Search.pairs, and a score-agreement test), 4 (_has_fill uses own_slugs), 5 (Piece.year/month_day instead of pieces._date_parts); I2 goes to the operator with deviations 1-2; module split (minor 3) deferred to Task 9's judgment — the cause misreport hides real compromises in reporting — cost if wrong: none.
- Task 8: minor (deferred, carry to Task 9): bends/show_bends are unions of per-step bends; show_bends[i] includes later shows' bends — define per-row attribution so status sums don't double count
- Task 8: minor (deferred, carry to Task 9): rec/used contract — both built from every show placed before this occurrence not yet in aired.jsonl (persisted-unaired rows + earlier projection picks), via with_piece and used
- Task 8: minor (deferred): scheduler.py 671 dense lines (Task 9 appends); 3000-piece speed test wall-clock bound 2 s (0.35 s here; hugo slower); surplus value drifts open blocks with on-this-day shows toward late edge
- 2026-10-25T12:25:40-0400 Task 8: fix round 1 dispatched (resumed implementer, Opus), FIX_BASE 5acb9f5
- 2026-10-25T12:29:37-0400 Task 8: fix round 1 implementer DONE 392dfde (748 passed, 1 skipped; mutants caught except the unreachable in-block repeat check); re-review dispatched (Opus)
- 2026-10-25T12:34:39-0400 Task 8: fix round 1/5 (4 addressed, 0 open; commits 5acb9f5..392dfde); re-review verdict sha256 ca6a81491a0fe56b1707c682a059c929aac4137a2233026cf7dabe3443641d53
- Task 8: minor (deferred, carry to Task 9): test gaps — (a) placed own shows counted in "longest" unpinned (add two 30-min own shows to the whole-pool test), (b) boundary term of block_start unpinned (large gap test)
- Task 8: minor (deferred, carry to Task 9): caller contract — own_pool must include placed own shows unfiltered and boundary_frames must equal the placed layout's; fill cause attaches only to the call that adds the fill (carry cause on the plan rows)
- Task 8: if operator rejects deviation 4, a repeat-agreement test for _Search.pairs becomes required (re-review gives the shape)
- Task 8: complete (commits c9568c8..392dfde, review clean) — deviations 1, 2, 4 await operator ruling; may reopen
- 2026-10-25T12:34:39-0400 HOLD before Task 9 (llama-69): waiting for operator ruling on Task 8 deviations 1, 2, 4
- OPERATOR RULINGS 2026-10-25 (via llama-69, binding, verbatim): Task 8 deviations (1) surplus value fsum(score-1), (2) tier 1 own-show count first, and (4) no piece plays twice in one block are all ACCEPTED. Proceed with Task 9 (Opus implementer per the plan; announcement rule R12 as its first commit).
  Operator context, not a code change: the "country" profile will probably be folded into americana; the station will not go live with two-concert profiles. No fixture changes needed for this.
  Hugo probe results (Gate 2 part of the Task 11 gate): Estimates: n=136 median |diff|=0.00s max |diff|=0.00s (verified independently: gratefuldead-1968-01-20 decoded 1993.2267 s vs manifest 1993.2266667). Cold analysis on hugo: gratefuldead-1973-06-10 146.0 s, 35 files; gratefuldead-1974-09-11 215.4 s, 48 files — use as Task 11's cold-analysis cost. Escalation threshold not met. Task 11 still needs llama-69's explicit go after Gate 3 (Task 10).
  Minor for the ledger: --time-one prints only "no eligible package" for an ineligible or quiet package; it should print the Ineligible reasons from station.scan (fold into Task 13 or the next task touching the probe).
- 2026-10-25T13:28:33-0400 HOLD lifted; Task 9 next (Opus).
- 2026-10-25T13:28:33-0400 Task 9: implementer dispatched (Opus), BASE 392dfde
- Task 13 carried: probe --time-one should print Ineligible reasons (operator minor)
- 2026-10-25T14:03:29-0400 Task 9: implementer DONE_WITH_CONCERNS b32f700..c981d23 (787 passed, 1 skipped; 17 mutants killed; live-vs-one-shot stress 13 runs 0 mismatches; 3000-pool 0.21 s). Deviation: step-function projection (each show from a fill_block run at its exact start) instead of phase A/phase B; new required SchedulerInput.now_us; exclude_profiles bend once per block; mid-block entry records miss=True. Concerns: later-clip re-plan off-by-one; fill cause from estimated block start; IMPLICIT_CLOCK ~0.3 s/project (Task 11 may pass ahead=1); gap 0 flattens recency (R8, operator-accepted). Reviewer dispatched (Opus).
- 2026-10-25T14:13:52-0400 Task 9: review Needs fixes (Opus), verdict sha256 a7862d1cabb6dc11e250199f106d0b19f5c5573f6fb967e1d829736302272d6c. Important: later not confined to the last internal boundary (decided at ID length, clip of different length re-plans; up to 7% of occurrences carry 2-3 laters). Deviations accepted: step function, rec contract, exclude_profiles once per block, mid-block miss, fresh start in next window; now_us accepted pending controller decision (Minor 4).
- Ruling R14: replace the now-anchored used with a frame-anchored one — used for a run starting at frame F = slugs of show pieces (persisted or projected) whose start_frame lies in [F - USED_WINDOW_HOURS, F), USED_WINDOW_HOURS = 24 (named module constant); SchedulerInput.now_us removed — spec "Lookahead is anchored to the frame line ... never from now"; live and preview and the measurement then agree — cost if wrong: a show could recur after 24 h when the gap rule is disabled (operator chose gap 0 = no gap rule).
- Ruling R15: fix round 1 = Important 1 per the reviewer's (i)+(ii) plus property test; Minor 2 (horizon until a projected piece reaches until_frame, then ahead more); Minor 3 (exact block start passed to _BlockRun); Minor 5 (ahead >= 1 enforced with ValueError); Minor 9 typing; R14 — Task 10 measures on this code next — cost if wrong: none.
- Task 9: minor (deferred, carry to Task 13): per-row bends can drop a bend a re-plan undid (rare); mid-block miss counts cutovers/outages and measurement start
- Task 9: minor (deferred, carry to Task 11): project lays out the whole horizon for one piece — pass ahead=1 in the live extend
- Task 9: minor (deferred, Task 8 / clock / Task 13 note): MAX_FILL=3 cannot fill a long profile block with small max_shows (17.5 h max_shows=1 lands +3 h, following blocks race early) — schedule/status note or clock warning
- 2026-10-25T14:14:14-0400 Task 9: fix round 1 dispatched (resumed implementer, Opus), FIX_BASE c981d23
- OPERATOR RULING 2026-10-25 (via llama-69, binding, verbatim): with `concert_gap_days = 0`, least-recently-aired ordering must still apply, per the spec. Implement your proposed fix: with gap 0, scale the recency term by days since airing over a fixed horizon (a named module constant, not config), so a show aired yesterday ranks below one aired months ago; with gap > 0, behaviour unchanged. Fold it into Task 9's current fix round if the writer can take it without collision (otherwise its own small commit right after, before Task 10), with a test that pins the ordering at gap 0, and include it in the re-review's scope. This also covers the R14 cost you named (recurrence after 24 h at gap 0 now loses to older shows).
- 2026-10-25T14:16:41-0400 Ruling R16: folded into Task 9 fix round 1 (same writer, rules.py not otherwise touched this round): GAP0_RECENCY_HORIZON_DAYS = 365 in rules.py; at gap 0 recency term = 0.9 * min(days_since / 365, 1.0); gap > 0 unchanged; gap rule still disabled at 0 — a year spreads months-apart airings across the score range while keeping never-aired (1.0) on top — cost if wrong: a different horizon constant.
- 2026-10-25T14:26:31-0400 Task 9: fix round 1 implementer DONE a839abb (items 1-6), cdc9dc4 (R16) (797 passed, 1 skipped; p7 probe 0 double laters; live/one-shot 12 runs 0 mismatches; implicit-clock live ~0.6 s/project). Re-review dispatched (Opus).
- 2026-10-25T14:37:21-0400 Task 9: fix round 1/5 (7 addressed, 0 open; commits c981d23..cdc9dc4); re-review verdict sha256 b814a1f69474275989ee6e23597cd21b78403f377de62b4ff0f95ef83e7bf8e0; p1 800 clocks later-not-last 79 -> 0; live/one-shot 0 mismatches (40x30h, 25x72h)
- Task 9: minor (deferred, final review): sliding used window is a new mid-block re-plan source (untruthful two-block predictions 8 -> 10 lines in 800 clocks, within the accepted announcement-broken limitation); remedy: per-step used window at run creation (also recovers the +22% implicit-clock live cost)
- Task 9: minor (deferred, final review): max(clock_pos, ...) horizon clause unpinned (mutant survived)
- Task 9: minor (deferred, final review): later predicts X's start with the boundary estimate, not X's next clip length (pre-existing class)
- Task 9: complete (commits 392dfde..cdc9dc4, review clean)
- 2026-10-25T14:37:22-0400 Task 10: implementer dispatched (Sonnet), BASE cdc9dc4
- 2026-10-25T14:51:34-0400 Task 10: implementer DONE_WITH_CONCERNS 854d00a..20e78aa (798 passed, 1 skipped). Floor (clock a): scheduler 0/1151 = 0.0% outside window vs naive overran 15 + not fillable 17 of 1100 = 2.9% -> PASS. Concern: Dead repeats heavily (clock a: 39/413 dead shows aired in 50 weeks, median repeat gap 5 d, 824/1540 repeats within 7 d; b 38/413; c-delivered 66 dead, 87/221 funk). Comparison not fully like-for-like; no interstitials loaded. Reviewer dispatched (Opus) with a root-cause diagnosis of the Dead repeats as a named risk.
- 2026-10-25T14:52:33-0400 GATE 3: preliminary numbers reported to llama-69; Task 11 not started (needs explicit go); Task 10 review in flight
- 2026-10-25T15:02:42-0400 Task 10: review Needs fixes (Opus), verdict sha256 ffdc3c47e34c85100577c3079b220fc0d594e9602a6d7c3afe0aae99024dff87. Scripts sound, reproduced independently, floor PASS valid. Important: evidence.md misdiagnoses the Dead repeats (station-wide figures labelled Dead; blames the compromise order).
- DIAGNOSIS (Task 10 reviewer): scheduler defect — options ranked lexicographically on violation counts summed per show; in a single-artist pool (all 413 dead = Grateful Dead) every extra show adds an unavoidable adjacency + artist_day violation, so any single beats every pair before the gap rule is consulted; the ~2 singles that fill dead-am alone repeat daily (6,950 fresh in-window pairs never chosen). _blocksearch.py:188-200, 357-368, _Tier.offer 122-124. Spec: a rule the pool makes impossible "is not applied within that pool at all"; plan narrowed it to "not reported as a bend". Prototype fix (single-artist own pool: don't count adjacency/artist_day for that artist; rules.violations too): clock a Dead aired 39 -> 384/413, gap bends 347 -> 0, misses 0, own share 92.4 -> 92.9%.
- LIBRARY DEFECT (upstream, llama): 17 Dead packages list every track twice (272-424 min), incl. voiced gratefuldead-1974-09-11; they are the singles filling dead-am and the only own pairs filling 12 h blocks.
- Task 10: minor (deferred): weeks are UTC spans (DST makes 1151 not 1150); --scan-cache pickle not keyed by root/library; no per-profile repeat gaps; smoke test checks keys only
- 2026-10-25T15:02:42-0400 HOLD at GATE 3: reported to llama-69 with a proposal (reopen Task 8 for the spec-aligned single-artist exemption on Opus; Task 10 fix round: corrected diagnosis, per-profile repeat gaps, UTC-week note, scan-cache keying, re-run all clocks after the fix); waiting for go
- OPERATOR GO 2026-10-25 (via llama-69, binding, verbatim): approved all 3 steps of your Gate 3 proposal: (1) reopen Task 8 on Opus for the single-artist exemption in `_blocksearch` and `rules.violations` with the fresh-pair-beats-recent-single regression test, then review; (2) the Task 10 fix round as you listed it; (3) report Gate 3 again. Task 11 still needs my explicit go after that.
  Operator context for step 2: the doubled-track library defect is known and being worked in another session, but the library fix may be deferred for LLM-spend reasons, and some delivered shows will soon get a "needs fix" status that holds them from broadcast. So the library is likely to SHRINK before it grows. In the re-run, add one variant of each clock with the 17 doubled Dead packages excluded (a proxy for the holds), and report the dead-am / 12-hour-block behaviour there (fill share, misses, repeat gaps per profile) next to the full-library numbers.
- 2026-10-25T15:30:55-0400 Ruling R17: Task 8 reopen is a fresh Opus implementer (task8-fix2) working from the reviewer's prototype rather than resuming the 400k-token original — cheaper, focused brief — cost if wrong: none.
- 2026-10-25T15:30:55-0400 Task 8 (reopened): fix round 2 dispatched (fresh implementer, Opus), FIX_BASE 20e78aa
- 2026-10-25T15:41:41-0400 Task 8: fix round 2 (reopen) implementer DONE 9260dbd (805 passed, 1 skipped; 6 mutants caught; departs from prototype: fill judged by own-pool membership, open/degraded included). Re-review dispatched (Opus).
- QUEUED (operator-approved 2026-10-25 via llama-69; DO NOT dispatch until llama-69's go), verbatim: "Task 1b: honor awaiting_fix". llama's bulk apply will write a top-level `awaiting_fix` field (object with at least reason + timestamp; null/absent = none) into delivered manifest.json, in place, atomically, without touching tracks/audio/broadcast.m3u/dj_*. transmitter must treat a non-null value as not airable: station.scan Ineligible with reason `awaiting fix from llama: <reason>`, visible in status/library. Already-planned rows: confirm render's existing skip path (replan_from) drops a planned-but-unrendered show that becomes marked, pinned by a test; already-encoded/published pieces air as planned (bound: up to lead_hours after the mark). Name/shape are NOT final until docs/superpowers/specs/2026-10-25-bulk-apply-design.md is committed on main; I'll tell you when. It ships with the scheduler branch (no separate hugo deploy: soft launch, airing a damaged show meanwhile is acceptable). Slot it in whenever it doesn't collide with a writer once I give the go, at the latest before Task 13. Current steps 1-3 unchanged.
  Note: a manifest edit in place changes the package's estimate inputs but not its file-set key (manifest not in the key); scan_delivered's m- key does change; the analysis cache is unaffected.
- 2026-10-25T15:46:27-0400 Task 8: fix round 2/5 (reopen; 1 addressed, 0 open; commits 20e78aa..9260dbd); re-review verdict sha256 e67f2452a9fbb6dfb8bf5b32a77ae804d4766e65cc3173e9d864b51cbf2c9a7f. Gate 3 step 1 DONE.
- Task 8: minor (deferred, Task 14/final): plan text still says pool-impossible rules are "not reported as a bend"; code follows the spec's "not applied within that pool at all" — add a one-line plan note
- Task 8: complete again (commits c9568c8..9260dbd incl. reopen, review clean)
- 2026-10-25T15:46:27-0400 Task 10: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 9260dbd — Gate 3 step 2
- 2026-10-25T16:17:27-0400 Task 10: fix round 1 implementer DONE 29635e1, d5c84c6 (805 passed, 1 skipped). Floor PASS 0/1150 vs 2.9%. Dead a full 384/413 (gap min 1.0 d, median 13 d; dead-pm 12 h block repeats via doubled packages), excl-17 396/396 (45 d / 52 d; dead-pm fill 40.9%). Concern: funk on clock c 91/221 aired, median 21 d, 230 repeats < 7 d (multi-artist pool). Re-review dispatched (Opus) with funk diagnosis.
- 2026-10-25T16:17:45-0400 Task 10 fix: implementer's background wrapper hung on a stray `cat > /tmp/dummy` reading stdin after the run finished (rc=0, ALLDONE); killed the cat (pid 39924) to release it. Escape noted.
- 2026-10-25T16:29:27-0400 CONTROLLER ERROR (Escape): killing the stray `cat` (pid 39924) let its wrapper shell continue: it rewrote scratchpad/f1/run.sh, deleted and re-generated results-*.json in the worktree (finished 16:22). All 9 runs read the keyed scan cache (scan 0.0 s) — no share access. Results reproduced (only project_seconds differed). Controller restored the 8 tracked files with git checkout and removed the untracked duplicate results-c-delivered-ex17.json; tree clean at d5c84c6. Lesson: inspect a stuck process's full command before killing a blocking step — the block may be the first command, not the last.
- Task 10: re-review verdict sha256 b9928518fec7543ae5f4d6734cdcccc0164566105643ea83abfa46df47967c0f: findings 1-5 ADDRESSED; 1 new Important: evidence.md bends label says "existed" but the code counts only options offered by the bounded search (35 + 30 passed-over gap-keeping options). Funk root cause: library/clock limitation (clock c funk block 360 min, max_shows 2, only 8 funk shows >= 183 min land); max_shows = 3 clears it (221/221 aired, min gap 45 d). Search miss defect: _blocksearch.py:326-337 firsts ignore whether a rule-keeping partner exists (prototype gives mixed results; Task 8 follow-up, not a blocker). Clock a ±15 bluegrass: one landing pair airs near-daily (295 of 301 sub-week repeats).
- 2026-10-25T16:29:37-0400 Task 10: fix round 2 dispatched (resumed implementer, Sonnet), FIX_BASE d5c84c6; docs only + naive cache key check; no share access, no re-runs
- 2026-10-25T16:31:21-0400 Task 10: fix round 2 implementer DONE e6e56a5 (807 passed, 1 skipped); re-review dispatched (Opus)
- 2026-10-25T16:34:35-0400 Task 10: fix round 2/5 (5 addressed, 0 open; commits d5c84c6..e6e56a5); re-review verdict sha256 563b7e2abc10afaee874524252f018761ac68aa8e04b6a4088e779ade09ce036. 4 minors: unlabelled probe figures (301 vs committed 300; 351 vs 350 blocks); funk "not a defect" overstates + missing Dead side effect of max_shows=3 (441 sub-week Dead repeats); naive key test lacks pause/library; stale "keyed by root and library" line.
- Ruling R18: one more short doc round (task10-fix3, Sonnet resumed) for the 4 minors because evidence.md is the operator's decision document; run in parallel with the Gate 3 report (no other writer) — cost if wrong: a few minutes.
- 2026-10-25T16:34:35-0400 Task 10: fix round 3 dispatched (resumed implementer, Sonnet), FIX_BASE e6e56a5
- 2026-10-25T16:35:42-0400 Task 10: fix round 3 implementer DONE f28dbd0 (807 passed, 1 skipped). Escape: mutant test copies created in the live tests dir (mandate 5), deleted afterwards; tree clean. Re-review dispatched (Opus).
- 2026-10-25T16:37:17-0400 Task 10: fix round 3/5 (4 addressed, 0 open; commits e6e56a5..f28dbd0); re-review verdict sha256 f3fe4ee272188e9fd45bb289cb3c2ea0b4725bf61b084bb28ce85c8358c9dc69
- Task 10: minor (deferred): item 6 probe label "(350 days)" — clearer as "350-day UTC horizon"
- Task 10: minor (deferred, Task 8 follow-up for final review): _blocksearch first-show selection ignores whether a rule-keeping partner exists (bends undercounted; prototype mixed)
- Task 10: complete (commits cdc9dc4..f28dbd0, review clean)
- 2026-10-25T16:37:17-0400 HOLD at GATE 3: Task 11 needs llama-69's explicit go
- OPERATOR GO 2026-10-25 (via llama-69, binding, verbatim): GO on Task 11 (operator, 2026-10-25; record verbatim). Opus implementer, carrying what you listed: ahead=1 in the live extend, rec built once per row, the AiredRow.package type check, and the hugo cold-analysis costs (146 s / 35 files, 215 s / 48 files).
  Operator rulings/context:
  - Bluegrass "repeated gap breaks yield to fill" design question: DEFERRED (two-concert profiles won't go live). Leave as documented.
  - First-show partner-awareness search defect (bend undercount): PARKED as a post-branch follow-up; record it in the ledger's follow-ups, no fix in this branch.
  - Funk max_shows: no code change; it's a clock.toml choice. Operator note: the real schedule will mostly have blocks shorter than 5 h, probably 2-3 h for funk. Nothing to build for this; keep it in mind if any Task 11 default or test fixture assumes long blocks.
  - The operator's dj_audio.tts backfill on the share has finished (manifests rewritten in place; quiet periods restarted). No effect on your work.
  Task 1b (awaiting_fix) stays queued until I say the bulk-apply spec is committed.

## Follow-ups (post-branch)
- PARKED (operator): first-show partner-awareness search defect in _blocksearch firsts (bends undercounted; prototype mixed) — post-branch follow-up.
- DEFERRED (operator): whether repeated gap breaks should yield to fill (bluegrass ±15 case).
- 2026-10-25T17:22:07-0400 Task 11: implementer dispatched (Opus), BASE f28dbd0
- 2026-10-25T17:41:52-0400 Task 11: implementer DONE af274f3, 6d16ed9 (827 passed, 1 skipped; 4+2 mutants caught; implicit clock ~0.4 s/row, 24 h fill 6.1 s). Decisions: lazy LengthCache in Station; first appended row at caller's start_frame (skip path keeps dropped row's start); render mismatch forgets learned length; changed clip dropped for rest of call. Concerns: clock not a level alert code; ~2 extra ffmpeg probes/tick; cli.py help string touched; Debian-12 not run. Reviewer dispatched (Opus).
- 2026-10-25T17:50:50-0400 Task 11: review Needs fixes (Opus), verdict sha256 826bd8142237eaaafb1f5cebd5a2a6155a903004fe04b66213d098b932757b03. Important: render skip path after a show_gap_seconds change unpinned (mutant MA wedges render with LayoutError, suite green). Decisions 1-9 accepted (incl. first appended row at caller's start_frame; clock as ungated event code).
- Ruling R19: fix round 1 = Important 1 (render skip-path gap-change scenario test + comment at pipeline.py:322) plus Minors 1 (forget learned length test), 2 (degraded announcement_broken test), 3 (plan_step asserts start == next_start(rows, gap) on the extend branch), 4 (config template comment) — all cheap, on the strict surface — cost if wrong: none. Minor 5 (memoise extra_frames probe) deferred.
- Task 11: minor (deferred): extra_frames ffmpeg probe not memoised (~2 extra encodes per filling tick)
- Task 11: note: a clock that turns invalid is first alerted at the next fill (plan_step returns before extend while covered)
- 2026-10-25T17:50:51-0400 Task 11: fix round 1 dispatched (resumed implementer, Opus), FIX_BASE 6d16ed9
- 2026-10-25T17:54:04-0400 Task 11: fix round 1 implementer DONE e157449 (831 passed, 1 skipped; MA, M8, M1 caught). Re-review dispatched (Opus).
- 2026-10-25T17:57:17-0400 Task 11: fix round 1/5 (5 addressed, 0 open; commits 6d16ed9..e157449); re-review verdict sha256 3783bd783e67fdf04959497c97a5f319eda6aa205ecb5bdb537f0a7aa8bb73de
- Task 11: minor (deferred): scratch-copy recipe must include antenna/src and docs/superpowers/2026-10-25-scheduler-measurement for a full-suite run
- Task 11: complete (commits f28dbd0..e157449, review clean)
- 2026-10-25T17:57:17-0400 Task 12: implementer dispatched (Sonnet), BASE e157449
- OPERATOR GO 2026-10-25 (via llama-69, binding, verbatim): GO on Task 1b (awaiting_fix), slotted after Task 12 and before Task 13. The bulk-apply spec is drafted (not yet committed) at /Users/shawn/projects/llama/docs/superpowers/specs/2026-10-25-bulk-apply-design.md, section "The `awaiting_fix` contract (fixed here; the scheduler session builds against it)": `"awaiting_fix": {"reason": "<one line>", "marked_at": "<UTC ISO-8601>"}`; absent or null = no fix pending; ANY other value = not to be aired. Read that section (read-only; it is in the main checkout, which you must not modify). Build the reader tolerant of the draft changing shape: any non-null value makes the package Ineligible; the displayed reason is `awaiting fix from llama: <reason>` when `reason` is a string, else `awaiting fix from llama`; never crash on a malformed value (a malformed mark still means not airable). Pin: station.scan Ineligible; render's skip path drops a planned-but-unrendered row whose package becomes marked (the file-set key does not change, as you noted); already-encoded pieces air as planned. Sonnet implementer, Opus review. If the committed spec later renames the field, that's a follow-up I'll relay.
- 2026-10-25T17:58:47-0400 Ruling R20: Task 1b brief written by the controller (task-1b-brief.md); scan_delivered also excludes marked packages from the rehearsal pool (held from broadcast until re-delivered) — cost if wrong: rehearsal under-counts packages that will be re-delivered soon.
- 2026-10-25T17:58:56-0400 Task 12: implementer DONE 6e0e282 (antenna npm test 426 passed; off-air path verified never reaches nowPlayingText). Reviewer dispatched (Opus).
- Ruling R21: Task 12's review (antenna JS only, read-only) overlaps Task 1b's implementer (Python only) — disjoint files and test suites, so R4's single-writer rule holds — cost if wrong: none.
- 2026-10-25T17:58:56-0400 Task 1b: implementer dispatched (Sonnet), BASE 6e0e282
- 2026-10-25T18:00:30-0400 Task 12: review Approved (Opus), verdict sha256 a3cb7332b6f3ef69c4145985196a04465d47c595067b28c566ccbc121ab90f2f
- Task 12: minor (deferred): stale test title "says the station will be back"; document.title implicit coupling (capture STATION_NAME once / comment); empty <title> gives empty text
- Task 12: minor (deferred, operator note for Task 14/runbook): station name inconsistent — player "llama radio" vs the spec's station-ID example "LMA Radio"
- Task 12: complete (commits e157449..6e0e282, review clean)
- 2026-10-25T18:01:10-0400 Task 1b: implementer DONE 30a359a (859 passed, 1 skipped). Reviewer dispatched (Opus).
- 2026-10-25T18:08:50-0400 Task 1b: review Needs fixes (Opus), verdict sha256 db35505d50d217124031eed1f6180e0ac3f24f3f96bbfdc8b7ab91d77dd5476f. Important: test helper mark_awaiting_fix re-stamps every package file (set_age), so the file-set key changes in the tests; the operator's pin "the file-set key does not change" is not exercised. 9 mutants run, all caught.
- Ruling R22: fix round 1 = helper ages only manifest.json + the drop test asserts the key is unchanged after marking; also cap the displayed reason at 200 chars with an ellipsis (Minor 3). Minor 1 (lost encode + mark on an on-air show -> render LayoutError until recovery) ACCEPTED as the existing damage class, documented in the runbook (Task 14) and the follow-ups; Minor 2 (row_analysis fallback after cache loss) accepted — cost if wrong: a marked on-air show whose encode was lost by hand stalls render until recovery cuts a new run.
## Follow-ups (post-branch), continued
- Lost encode + awaiting_fix mark on an on-air show raises LayoutError until recovery (could allow on-air re-encode when ineligible only for awaiting_fix).
- 2026-10-25T18:08:50-0400 Task 1b: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 30a359a
- 2026-10-25T18:11:08-0400 Task 1b: fix round 1 implementer DONE cd80cbe (861 passed, 1 skipped); re-review dispatched (Opus)
- 2026-10-25T18:13:27-0400 Task 1b: fix round 1/5 (2 addressed, 0 open; commits 30a359a..cd80cbe); re-review verdict sha256 113cbd380fb7e5ed7e9114f1c48df72b9604630a654d8bec667cf3216fd063e3
- Task 1b: minor (deferred): reason cap can cut just after a space ("word …")
- Task 1b: complete (commits 6e0e282..cd80cbe, review clean)
- 2026-10-25T18:13:27-0400 Task 13: implementer dispatched (Sonnet), BASE cd80cbe
- 2026-10-25T18:20:42-0400 Task 13: implementer DONE d7f2bcf (877 passed, 1 skipped). Extra: edited repo CLAUDE.md Commands bullet (Task 14's file); block_views gains meta_of kwarg. Reviewer dispatched (Opus).
- 2026-10-25T18:29:38-0400 Task 13: review Needs fixes (Opus), verdict sha256 e6ff4d02e3d6130842b48f750f199127ad08de44038a7c08900910b1e418c2f6. Important: (I1) schedule mis-reports the block on air when its first show has ended (start/slip/miss/bends from the show on air); (I2) persisted-plan path of schedule, status's no-last-good-write, and every status count unpinned (10 of 19 mutants survived).
- Ruling R23: fix round 1 = I1, I2 plus minors 1 (stale "block now"), 2 (dead condition), 3 (normalise leading counts in library reasons), 5 (label "longer than max_shows" not "structural" in output), 6 (no slip for open blocks), 7 (CLAUDE.md wording incl. clock files), 8 (delivered test asserts) — operator-facing output; cheap — cost if wrong: none. Minors 4 (library double scan) and 9 (mixed-block projected label) deferred.
- Task 13: minor (deferred): library scans the station root twice; mixed persisted/projected block labelled "(projected)" as a whole
- 2026-10-25T18:29:38-0400 Task 13: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE d7f2bcf
- 2026-10-25T18:36:37-0400 Task 13: fix round 1 implementer DONE dcd0a2a (884 passed, 1 skipped; mutants M4..M21 now caught; extra fix: views trimmed by first-show start). Re-review dispatched (Opus).
- 2026-10-25T18:43:04-0400 Task 13: fix round 1/5 (9 addressed, 0 open; commits d7f2bcf..dcd0a2a); re-review verdict sha256 c1b609027d8f61c7d9fd6a2251bb78cdafe9937d1f96c7584bd21b0de67817a3. Two new Minor regressions from the fix: (a) trim by first-show start hides a late block nominally inside the horizon (and its MISS); (b) live admits (None, None) so (unscheduled) shows a stale start from old phase-1 rows. Out of scope: M30 ([fill: …] schedule label unpinned), test cruft in test_cli.py.
- Ruling R24: fix round 2 for the two regressions (they were introduced by fix round 1, and (a) hides a MISS) + pin M30 + remove the vacuous/dead test lines — small — cost if wrong: none.
- 2026-10-25T18:43:04-0400 Task 13: fix round 2 dispatched (resumed implementer, Sonnet), FIX_BASE dcd0a2a
- 2026-10-25T18:44:51-0400 Task 13: fix round 2 implementer DONE ff7ba19 (886 passed, 1 skipped); re-review dispatched (Opus)
- 2026-10-25T18:48:14-0400 Task 13: fix round 2/5 (4 addressed, 0 open; commits dcd0a2a..ff7ba19); re-review verdict sha256 5c5aa6edfd1933ca3aeb4c4408caa9158d5d5afe9b5ba12837f69c66515dcec5
- Task 13: minor (deferred): unused import json in test_cli.py; trim test comment stricter than the rule; redundant startswith in phase-1 test
- Task 13: complete (commits cd80cbe..ff7ba19, review clean)
- 2026-10-25T18:48:14-0400 Task 14: implementer dispatched (Sonnet), BASE ff7ba19
- 2026-10-25T18:54:13-0400 Task 14: implementer DONE 36282ce. Verification: repo pytest 5215 passed, 1 skipped, 8 deselected, 26 warnings; antenna 426 passed; Debian-12 887 passed. Reviewer dispatched (Opus).
- Task 14 implementer: wrote extra output files into its child dir (pytest/npm/deb .out/.rc) — mandate 2 says only the log; harmless
- 2026-10-25T19:01:36-0400 Task 14: review Needs fixes (Opus), verdict sha256 190f457b56d06a36bfcd3dbf84f0f0b965c35b00610db33a5673f1979b37734d. All load-bearing claims correct. Important (doc completeness): (1) CLAUDE.md contradicts itself on phases (lines 274, 461-462); (2) clock/history alert codes missing from 7.1 and the incident runbook; (3) no clock field reference/template; (4) player assets deploy (deploy:assets) and cutover steps missing. 26 warnings: CPython 3.14 popen_fork DeprecationWarning from llama multiprocessing tests; Debian-12 transmitter run 0 warnings.
- Ruling R25: fix round 1 (doc-only) = Importants 1-4 + minors 1-4, 6-8, 10, 11; voicing loop skips existing mp3s and notes `emcee say --no-bed` as the operator's choice (spec: clips loudness-normalised like DJ clips; bed not specified); minor 9 (branch-only hash 684d323 — merge with --no-ff) goes to the finish notes, not the doc — cost if wrong: none.
- 2026-10-25T19:01:36-0400 Task 14: fix round 1 dispatched (resumed implementer, Sonnet), FIX_BASE 36282ce
- 2026-10-25T19:03:08-0400 Task 14: fix round 1 implementer DONE 5077763 (docs; clock example validated with load_clock). Re-review dispatched (Opus).
- 2026-10-25T19:07:45-0400 Task 14: fix round 1/5 (Important 1, 4 and all minors addressed; 2 open); re-review verdict sha256 2f5b572b1210bc49a82d7ae54eeddd3851eb6b0ed083c7f42e2cec479bdd7d16. Open: incident-runbook headings say clock/history send no "resolved" (they do, alerts.py:318-332); clock example's "2-3 h blocks" comment false (blocks run 6/18/24 h; doc never says a block runs to the next start). New minors: placeholder profile unmarked; exclude_profiles wording; probe script path; cutover MISS placement.
- Ruling R26: fix round 2 (docs) = both open findings + all new minors + CLAUDE.md "one all-week open block" nit — cost if wrong: none.
- 2026-10-25T19:07:45-0400 Task 14: fix round 2 dispatched (resumed implementer, Sonnet), FIX_BASE 5077763
- 2026-10-25T19:08:26-0400 Task 14: fix round 2 implementer DONE 3a8f30e (docs). Re-review dispatched (Opus).
- 2026-10-25T19:10:46-0400 Task 14: fix round 2/5 (6 addressed, 0 open; commits 5077763..3a8f30e); re-review verdict sha256 8a82e709d9e02026eb06d5fcede11552ed73e86402d3a1b28b7b160582161a4c
- Task 14: minor (deferred): cutover MISS wording "records a MISS" should be "may record a MISS" (only when the plan end lands outside the entered block's window) in 7.2, 7.4 and CLAUDE.md
- Task 14: complete (commits ff7ba19..3a8f30e, review clean)
- 2026-10-25T19:10:46-0400 ALL 14 TASKS (+1b) COMPLETE. Final whole-branch review next (Fable).
- 2026-10-25T19:11:23-0400 Final review dispatched (Fable, spec review mode), range 02b6d49..3a8f30e
- OPERATOR RULING 2026-10-25 (via llama-69, binding, verbatim): the station's on-air name is "LMA Radio" (exact capitalisation). Change the player's between-shows text (Task 12's `document.title` path, so the page <title> and anything `npm run pages` regenerates in src/pages.ts) and replace the runbook's "use one station name everywhere" note with the name itself. Do it as its own small commit before the Fable whole-branch review (Sonnet implementer, Opus review; antenna `npm test` must stay green, including the pages.ts freshness check), so Fable reviews the final text. Leave any spec text alone unless it contradicts the ruling.
- 2026-10-25T19:11:43-0400 Final review (Fable) told to STOP (it was dispatched minutes before the ruling arrived); a fresh final review (final-review-r2) follows the station-name commit.
- 2026-10-25T19:11:51-0400 Ruling R27: station-name change scope = player pages only (index.html <title>, og:title, <h1>; offair.html <title>, <h1>; nowplaying.js default; regenerated src/pages.ts) + playout-setup.md:558 note replaced with the name; alert-subject station_name defaults (config.py, alerts.py, antenna alerts.ts, playout-setup.md:361) left as they are and raised to llama-69 as a question — the ruling names the player text and the runbook note; alert subjects are not on air — cost if wrong: alerts keep saying 'llama radio' until a follow-up.
- 2026-10-25T19:12:47-0400 Station name: implementer DONE 579f619 (antenna 426 passed incl. pages freshness). Reviewer dispatched (Opus).
- 2026-10-25T19:13:07-0400 Final review (Fable) stopped cleanly after pass 1 + partial pass 2; 7 preliminary notes kept (stub handback); they go to final-review-r2.
- OPERATOR RULING 2026-10-25 (via llama-69, binding, verbatim): leave the alert subjects as they are ("llama radio": transmitter station_name default, antenna STATION_NAME fallback in alerts.ts, playout-setup.md:361). R27's scope stands. Proceed: name commit + Opus review, then the fresh Fable whole-branch review, then the finish menu.
- 2026-10-25T19:14:42-0400 Station name: review Approved (Opus), verdict sha256 3dce80c1c1f7a462ca49b31df886dd0fccda2be8a07fb883b6c7531fca3d260a. Important escalation: [antenna] station_name is not alert-only — it brands the public show pages (publish.py:263-264 -> templates/show.html: <title>, og:site_name, back link), so show pages still say "llama radio". Options: (a) change transmitter default+seed (moves alert subjects too); (b) leave code, set station_name in hugo config.toml at cutover, fix runbook row 361.
- Station name: complete (commit 579f619, review clean)
- 2026-10-25T19:14:42-0400 HOLD before final-review-r2: operator decision needed on show-page branding (R27 premise incomplete)
- OPERATOR RULING 2026-10-25 (via llama-69, binding, verbatim): option (b). No code change. In the runbook: correct row 361 to say `[antenna] station_name` brands the public show pages (title, og:site_name, back link) as well as alert/push titles; and add to the phase-3 cutover checklist a step to set `station_name = "LMA Radio"` in hugo's config.toml together with antenna's `STATION_NAME` var (they must match, per :373), noting that this renames alert subjects too and that the antenna side takes effect at the next Worker deploy. Small docs commit, Opus review, then the fresh Fable whole-branch review, then the finish menu.
- 2026-10-25T19:44:28-0400 name-docs implementer dispatched (Sonnet), BASE 579f619
- 2026-10-25T19:45:07-0400 name-docs implementer DONE e7a27ab, 00afe1f (docs only). Reviewer dispatched (Opus).
- 2026-10-25T19:46:59-0400 name-docs: review Approved (Opus), verdict sha256 799f67d51ce0f5d1a3adbbbe190c2856ecd7b300eaf367ec069804ada0f07299
- name-docs: minor (deferred to final wave): 7.3 line 558 says alerts take the name from station_name (antenna emails use STATION_NAME); step 8 ordering vs step 1 restart; step 8 could note re-PUT of notes/show pages, old show pages outside the window keep the old name, and that the wrangler.jsonc edit must be committed
- name-docs: complete (commits 579f619..00afe1f)
- 2026-10-25T19:46:59-0400 Final review r2 dispatched (Fable), range 02b6d49..00afe1f
- 2026-10-25T19:49:51-0400 RELAY-NOW received from llama-69: let final-review-r2 finish, do NOT start its fix rounds, write HANDOFF, disarm, report RELAY-READY. Successor orch-r1 (Opus) runs the fix wave and the finish menu.

## HANDOFF (2026-10-25T20:05:38-0400, peer 6a271170-52a3-49a3-b4db-a9d5cd08acfc -> successor orch-r1, Opus)

**State at HEAD:** branch playout-scheduler, HEAD 00afe1f, tree clean. All plan Tasks 1-14 plus Task 1b (awaiting_fix), the Task 8 reopen (single-artist exemption, 9260dbd), the station-name commit (579f619) and the name-docs commits (e7a27ab, 00afe1f) are implemented, reviewed and complete. Last verification (at 36282ce, before docs-only and antenna-only commits): whole-repo `./.venv/bin/python -m pytest -q` 5215 passed, 1 skipped, 8 deselected; `cd antenna && npm test` 426 passed (re-run green at 579f619: 426 passed incl. pages freshness); `packages/transmitter/scripts/test-in-debian12.sh` 887 passed. Code commits after 36282ce: Task 14 docs only, 579f619 (antenna pages/test only), name-docs (docs only) — the successor should re-run all three gates before the finish menu.

**Final whole-branch review (Fable, r2):** verdict file /Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/final-review-r2/handback.md, sha256 42d5dea6df496b917daedf101441cb33f1ad07684b541c8181667c7bf9fc4723. Verdict: **Ready to merge: Yes.** Critical: none. Important: none. Minor (6):
  1. ahead=1 equivalence correct but unpinned: test_scheduler.py live() helper uses default ahead=2; run test_appending_first_pieces_reproduces_one_projection with ahead=1 (and 2).
  2. Docs say a mid-block cutover "records a MISS" unconditionally (cli.py schedule docstring, playout-setup.md 7.2 and 7.4 step 3, CLAUDE.md schedule bullet); with no clock file it never does, with one only if the plan end lands outside the entered block's window -> "may record a MISS (...)". Recommended doc-only commit in the finish wave.
  3. plan_step start guard is tautological (pipeline.py:318-321 vs planner.next_start): drop it or make it check something independent.
  4. render_step's cold analysis (pipeline.py:432, st.engine.analyze direct) pings the watchdog only after the encode; add self._ping() after analyze; runbook watchdog paragraph could note a render-path re-plan has no max_new (worst ~40-55 min of analyses under the plan lock; publish waits).
  5. interstitials.scan stats each clip twice (R9 said one) — no correctness effect.
  6. DEFAULT_CONFIG_TOML writes an uncommented [interstitials] header; a config made by config init on this build is refused by builds before 684d323 — consider commenting it.
  The stopped review's 7 notes: all resolved in r2's report (1 discarded/sound, others confirmed as minors or no finding). Deferred-minors triage: must-fix-before-merge NONE; full per-item triage in the verdict file.

**Fix wave (successor's job; NOT started per RELAY-NOW):** SDD says one fix dispatch with the complete findings list, one scoped re-review, then the finish menu. Suggested scope: r2 Minors 1-4 and 6 (5 optional), plus the deferred final-wave doc minors: name-docs (7.3 line 558 should name STATION_NAME for antenna emails; step 8 ordering vs step 1 restart; step 8 should say commit the wrangler.jsonc edit, notes/show re-PUT on the next publish, old show pages outside the window keep the old name); Task 14 "may record a MISS" (same as r2 Minor 2).

**Deferred minors list:** every "minor (deferred" line in this ledger (also extracted with the rulings at .superpowers/sdd/2026-10-25-scheduler/final-review-context.md); r2 triaged each (resolved / stay).

**Post-branch follow-ups (operator-parked/deferred):** ledger sections "## Follow-ups (post-branch)" (line ~230) and "continued" (line ~257): first-show partner-awareness search defect / bend undercount (PARKED); whether repeated gap breaks should yield to fill (DEFERRED); lost encode + awaiting_fix on an on-air show -> LayoutError until recovery (R22, accepted).

**Task 1b open items:** (a) the awaiting_fix contract comes from a DRAFT spec (main checkout docs/superpowers/specs/2026-10-25-bulk-apply-design.md, uncommitted when built) — if the committed spec renames/reshapes the field, llama-69 relays a follow-up; the reader only checks "present and non-null", reason is display-only; (b) deferred minor: reason cap may cut just after a space; (c) the accepted lost-encode limitation (follow-ups).

**Still owed before the finish report:** copy this ledger (/Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/orch/ledger.md) and the reviewer verdicts (every /Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/*review*/handback.md, /Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/final-review*/handback.md) into docs/superpowers/2026-10-25-scheduler-sdd/ and commit them (.superpowers/ is gitignored). Then the finish menu (merge/push/tag are the root's after the operator's choice). Finish-menu note: 684d323 (named in runbook 7.5) exists only on this branch — merge with --no-ff or re-check the hash after any rebase/squash.

**Operator rulings, verbatim, ledger line numbers:** 145 (announcement two-block rule 12 h; gap 0; hugo probe); 165 (Task 8 deviations 1/2/4 accepted; country context; probe results; --time-one minor); 180 (gap-0 least-recently-aired); 196 (Gate 3 proposal approved; excluded-17 variants); 222 (GO Task 11; bluegrass DEFERRED; search defect PARKED; funk max_shows clock choice); 245 (GO Task 1b, awaiting_fix contract); 294 (station name "LMA Radio"); 299 (alert subjects stay "llama radio"); 303 (option (b) docs). Controller rulings R1-R27 are the "Ruling R" lines.

**Escapes:** see "## Escapes" near the top (Task 5 red commit amended; Task 10 hung wrapper + controller-caused re-run; Task 10 fix3 mutants in live tests dir; Task 14 extra files in child dir).
- 2026-10-25T20:05:49-0400 RELAY: tick 21695300 CronDeleted; armed-6a271170 removed; STATE.md mode done; no children, background shells or Monitors running.
