# SDD ledger — plan: docs/superpowers/plans/2026-10-10-playout-phase1.md
Orchestrator: peer session 1e18c958-066d-4cae-ae48-e032d3e8aa40 (Opus). Parent: llama-ba. Start: 2026-10-10T11:23:31-0400, base ff14e07.
Spec: docs/superpowers/specs/2026-10-09-playout-design.md (reachable).
Skill workspace (briefs, review packages): .superpowers/sdd/2026-10-10-playout-phase1/
Children: $D/<task>/ (handback.md, done, <task>.log).

## Escapes
- 2026-10-10 ~11:45 orchestrator appended `.venv311/` to the shared /Users/shawn/projects/llama/.git/info/exclude (local-only, untracked; outside the worktree). Reported to llama-ba.

## Log
- 2026-10-10T11:23:31-0400 setup: meter 5h 0% (resets 16:20), 7d 0%. Docker 29.4.1 up. No .venv yet (Task 1 implementer creates it).
- 2026-10-10T11:24:16-0400 dispatched preflight (Opus, agent a4fff864daee53688) and task1-impl (Sonnet, agent af33c67029250e005), BASE ff14e07
- 2026-10-10T11:26:00-0400 task1-impl DONE_WITH_CONCERNS 037162d (29 transmitter tests, 2178 repo). Concerns: .venv is py3.14 (3.11 covered by Debian12 gate from Task 2); impl-before-RED (RED shown on scratch copy). Dispatched task1-rev (Opus).
- 2026-10-10T11:28:41-0400 task1-rev (Opus): Spec ✅, quality Approved, 0 Critical/0 Important.
Task 1: minor (deferred): adts.parse_header ignores raw_data_blocks count (byte6 &3); require_station_format can't reject multi-block frames; 9-byte header with CRC unchecked
Task 1: minor (deferred): id3.parse_timestamp_tag raises IndexError (not ValueError) on truncated tag; no end<=len / version / ts<2^33 checks
Task 1: minor (deferred): segment.segment_key accepts negative n
Task 1: minor (deferred): adts.build_frame masks out-of-range fields silently
Task 1: minor (deferred): grid.us_to_iso truncates to ms (document)
Task 1: minor (deferred): test gaps — main_cli error mapping, __import__ arm, truncated-frame match=, length<7; ADTS comment says ffmpeg 8.1
Task 1: minor (deferred): segment.py typing.Sequence (brief-mandated style nit)
Task 1: complete (commits ff14e07..037162d, review clean)

## Pre-flight scan (2026-10-10T11:39:25-0400; preflight child, Opus; full tables at $D/preflight/handback.md — verbatim plan code for Tasks 1-14 ran 192/192 in a scratch tree; antenna checked by hand)
- Ruling: B1 (Path annotation NameError on 3.11 when Task 5/7 helpers land before Task 4) — Task 2's helpers.py addition also adds `from pathlib import Path`; and Task 5 runs before Task 7 (Task 7 imports build_package/make_root) — costs nothing if wrong.
- Ruling: I1 (test epoch E=1.8e9 s = 2027-01-15; real-clock mtimes make 16 tests red after that date) — Task 9 (and every later use of that test epoch) uses E = 4_000_000_000 * 1_000_000 µs; verified 192/192 in scratch — if wrong, a re-run of the affected tests.
- Ruling: I2 (venv is 3.14; no 3.11 locally) — I created .venv311 (uv, CPython 3.11.15, transmitter[dev] only; 29/29 green) and every transmitter implementer also runs `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`; Debian-12 gate additionally after Tasks 6 and 12 — costs a few minutes per task. Side effect: appended `.venv311/` to the repo's shared .git/info/exclude (local-only, untracked) so it stays out of git status.
- Ruling: M1 (config init uses plain write_text) — Task 3 uses atomic_write_text (Global Constraint "Atomic writes" binds) — trivial.
- Ruling: M2 (spec says 128 kbps CBR; native aac is ABR-ish) — recorded as a deviation for the final review; no plan edit — if wrong, a spec note.
- Ruling: M3 weak tests — Task 2 adds `assert frames` (L918-922); Task 14 L6072 test gets an assertion matching its name; Task 11 drops dead NOW_US=None — trivial.
- Ruling: M4 plan-mandated duplication (lock+guard preamble x3, seg-seconds x3, clip-pause samples x3, ffmpeg stderr x2, playlist header x2) — follow plan text; reviewers may flag; final review triages. Not correctness — cost: later cleanup.
- Ruling: M5 unused imports — implementers drop unused imports from the plan's listings — trivial.
- Ruling: M6 — Task 11 interface list includes check_epoch; L1861 comment says tests_transmitter/; L6068 comment says 168.64 s — trivial.
- M7 observation only (off-air notice has no PROGRAM-DATE-TIME; per-segment discontinuity numbering) — no action; final review sees it.
- 2026-10-10T11:40:12-0400 dispatched task2-impl (Opus, a025e2f37c659c055), BASE 037162d
- 2026-10-10T11:44:19-0400 task2-impl DONE_WITH_CONCERNS 575087c,0504571 (44 transmitter tests in .venv/.venv311/debian12 [ffmpeg 5.1.9, Py 3.11.2]; repo 2193). Offsets: segue 86.4s, gap 288.0s (B at 290.1s), wrap 430.1s; build deterministic. Concerns: AacFileEncoder cleanup only on in-block failure; debian runner copies .venv311; CDN hls.js on spike page; noqa Path import.
- 2026-10-10T11:44:41-0400 dispatched task2-rev (Opus, aca22896c25068fae) on 037162d..0504571
- 2026-10-10T11:49:31-0400 task2-rev (Opus): Spec ✅, quality Approved, 0 Critical, 1 Important (procedural, not code).
- Ruling: Task 2 Important #1 (ENDLIST spend check is by ear only) — added to the operator procedure: after ENDLIST, confirm in the serve terminal that GET /live.m3u8 requests stop within ~1 target duration, per player; recorded with the checkpoint result. No code change — if wrong, nothing lost.
Task 2: minor (deferred): extra_frames() value on ffmpeg 5.1 never recorded (only consistency) — folded into task2-fix1 measurement
Task 2: minor (deferred): AacFileEncoder __exit__ no-op on clean exit (plan-mandated); close() not idempotent; .tmp leak if os.replace fails; write() only maps BrokenPipeError
Task 2: minor (deferred): frame-count model pinned only on silence in tests (reviewer measured tones OK)
Task 2: minor (deferred): build test doesn't pin wrap<end of B; live-playlist test skips the two ENDLIST edge segments
Task 2: minor (deferred): debian runner copies .venv311 + .superpowers — folded into task2-fix1
Task 2: minor (deferred): printed offsets ~23 ms early (priming frame); banner "live starts at the beginning" loose
Task 2: complete (commits 037162d..0504571, review clean) — awaiting Step 11 human checkpoint
- Ruling: task2-fix1 (Sonnet) before Task 3 — runner excludes ./.venv* and ./.superpowers, and record extra_frames()/priming measured on ffmpeg 5.1 in the container. Reason: the runner runs ~7 more times and copying $D/spike-out into it is waste; the 5.1 value underpins Tasks 4/9. Cost if wrong: one small extra review.
- 2026-10-10T11:50:10-0400 GATE reported to llama-ba (listening checkpoint). Dispatched task2-fix1 (Sonnet, a363e962be8621282), BASE 0504571
- 2026-10-10T11:51:46-0400 task2-fix1 DONE f5256ac: runner --exclude="./.venv*" --exclude=./.superpowers; debian12 44 passed. Measured extra_frames()=1 and ENCODER_PRIMING_SAMPLES=1024 on BOTH ffmpeg 5.1.9 (debian12) and 8.1.1 (local) — closes Task 2 minor #1.
- Ruling: f5256ac's re-review is folded into Task 3's review (package base 0504571 covers it) — a one-line shell change I read myself (quoting correct inside the single-quoted sh -c body); separate Opus seat not worth it — cost if wrong: Task 3 reviewer catches it anyway.
- 2026-10-10T11:52:10-0400 dispatched task3-impl (Sonnet, a3ae2889f1dbc99be), BASE f5256ac (review base 0504571 to cover fix1)
- 2026-10-10T11:53:28-0400 task3-impl DONE 5382e82 (63 transmitter on 3.14 + 3.11; repo 2212). Rulings applied (atomic config init, tests_transmitter comment).
- 2026-10-10T11:53:47-0400 dispatched task3-rev (Opus, a2b3f327675a3a702) on 0504571..5382e82
- 2026-10-10T11:55:39-0400 task3-rev (Opus): Spec ✅ (incl. f5256ac verified in debian:12 tar), Approved, 0 Crit/0 Imp.
Task 3: minor (deferred): atomic_write_bytes has no fsync before os.replace — publish.json is the only R2 range record (no List), power loss could orphan segments (storage cost)
Task 3: minor (deferred): corrupt/truncated state JSON & config OSError surface as tracebacks, not ConfigError (fail closed)
Task 3: minor (deferred): prune_margin_minutes ge=0 allows deleting still-listed segments; consider floor — check again at Task 12 (prune)
Task 3: minor (deferred): load_or_create_epoch check-then-replace not exclusive — verify serialisation at Tasks 11/14
Task 3: minor (deferred): template test can't catch a knob missing from template; mkstemp→0600 config.toml; config init exists-check race
Task 3: complete (commits 0504571..5382e82 incl. task2-fix1 f5256ac, review clean)
- 2026-10-10T11:56:02-0400 dispatched task5-impl (Sonnet, a16edc7b377332458), BASE 5382e82
- 2026-10-10T11:57:06-0400 task5-impl DONE ed3ea95 (80 transmitter on 3.14+3.11; repo 2229).
- 2026-10-10T11:57:25-0400 dispatched task5-rev (Opus, a0d5c9a614bad8ab2) on 5382e82..ed3ea95
- 2026-10-10T11:59:34-0400 task5-rev (Opus): Spec ✅ (verbatim), Needs fixes: 1 Important (plan-mandated).
- Ruling: Task 5 Important #1 (plan-mandated: broadcast.m3u read unguarded → a package vanishing mid-scan crashes the whole scan) — FIX despite plan text: the spec/brief contract "a file vanishing mid-scan is Ineligible changing:, never a crash" governs. Also pulled Minor #1 into the same round because hugo is 3.11+NFS: evaluate maps OSError/RuntimeError/UnicodeDecodeError anywhere in its body to Ineligible("changing: …"); require_root maps an OSError (e.g. ESTALE) to StationRootError. Cost if wrong: a few lines + tests to revert.
Task 5: minor (deferred): non-dict show/source/dj_audio values in manifest raise AttributeError
Task 5: minor (deferred): no tests for outward symlink, file_set_key hash OSError path; dj-audio m3u entry not in dj_audio silently becomes kind "track" (would mix speech into music loudness/joins) — consider an Ineligible reason
Task 5: minor (deferred): station.py Iterable from typing vs collections.abc in helpers
- 2026-10-10T11:59:51-0400 task5 fix round 1 dispatched (resumed Sonnet a16edc7b377332458 as task5-fix1), FIX_BASE ed3ea95
- 2026-10-10T12:00:50-0400 task5-fix1 DONE 6ad53ff (86 transmitter 3.14+3.11; repo 2235). Dispatched task5-rerev1 (Opus, a8b8aedf9261d33b2) on ed3ea95..6ad53ff
Task 5: fix round 1/5 (1 addressed, 1 open — scan's per-package entry.is_dir()/manifest.exists() unguarded, reproduced on real 3.11 chmod 000 → PermissionError kills whole scan; commits ed3ea95..6ad53ff)
- Ruling: round 2 also folds in (a) sorted(root.iterdir()) OSError → StationRootError (matches scan_now contract), (b) narrow RuntimeError catch to the resolve()/symlink-loop site, (c) UnicodeDecodeError labelled "unreadable broadcast.m3u: …" not "changing:", (d) test for require_root's is_dir() arm. Cheap, same lines — cost if wrong: trivial.
- Note for Task 9 review: a stale mount mid-scan makes every package "changing" → shows==[] → PlanError, but in the recovery branch _drop_unpublished_segments runs before the PlanError (regenerable local files; check ordering there).
- 2026-10-10T12:03:08-0400 task5 fix round 2 dispatched (resumed Sonnet as task5-fix2), FIX_BASE 6ad53ff
- 2026-10-10T12:03:51-0400 task5-fix2 DONE 8bc35a7 (90 transmitter 3.14+3.11; repo 2239). Re-review round 2: resumed Opus re-reviewer a8b8aedf9261d33b2 as task5-rerev2 on 6ad53ff..8bc35a7
Task 5: fix round 2/5 (5 addressed, 0 open — scan per-entry OSError, iterdir→StationRootError, narrowed RuntimeError, unreadable m3u label, require_root is_dir pin; commits 6ad53ff..8bc35a7; reviewer re-ran real-3.11 chmod-000/symlink-loop probes)
Task 5: minor (deferred): persistent EACCES/symlink-loop still labelled "changing:" (cosmetic); 3.14 vs 3.11 divergence harmless (both Ineligible)
Task 5: complete (commits 5382e82..8bc35a7, review clean after 2 fix rounds)
- 2026-10-10T12:05:26-0400 dispatched task7-impl (Opus, a72a485990d7c1d73), BASE 8bc35a7
- 2026-10-10T12:08:20-0400 task7-impl DONE_WITH_CONCERNS 8a0c345 (107 transmitter 3.14+3.11+debian12 [5.1.9/3.11.2]; repo 2256). Concern: load_cached corrupt cache raises instead of miss.
- 2026-10-10T12:08:39-0400 dispatched task7-rev (Opus, a53cded1323097860) on 8bc35a7..8a0c345
- 2026-10-10T12:12:22-0400 task7-rev (Opus): Spec ✅, Needs fixes: 1 Important (plan-mandated) — corrupt analysis cache raises non-TransmitterError, wedging every plan/render tick.
- Ruling: Task 7 Important #1 — FIX despite plan text: corrupt/wrong-shaped cache = miss → re-analyse + overwrite. Also folded in (a) fsync of the temp file before os.replace in workspace.atomic_write_bytes (Task 3 deferred minor; the zero-length-after-power-loss path is what makes a corrupt cache likely, and publish.json is the only R2 range record), (b) tighten the clip-separation tolerance so it has real margin against the reviewer's mutant. Cost if wrong: an fsync per state write (tiny at this write rate).
Task 7: minor (deferred): silence-path tests thin (I=-70 with finite TP; finite I with TP -inf); no gain_db fed from parsed silent summary
Task 7: minor (deferred): gapless test checks lengths not sample continuity at the join; possible resampler transient at segue joins of 48 kHz sources (untested)
Task 7: minor (deferred): cache key ignores ffmpeg version; ffmpeg subprocesses have no timeouts (NFS hard-mount hang) — service-layer decision; iter_decode yields read-only arrays; LoudnessMeter.samples unused
- 2026-10-10T12:12:38-0400 task7 fix round 1 dispatched (resumed Opus a72a485990d7c1d73 as task7-fix1), FIX_BASE 8a0c345
- 2026-10-10T12:16:05-0400 task7-fix1 DONE e71dcc8 (112 on 3.14/3.11/debian12; repo 2261; mutant now 4.0 dB outside band). Re-review: resumed Opus reviewer a53cded1323097860 as task7-rerev1 on 8a0c345..e71dcc8
Task 7: fix round 1/5 (3 addressed, 0 open — corrupt cache = miss, fsync in atomic_write_bytes, clip-leak margin 0.1→4.0 dB; commits 8a0c345..e71dcc8; 4 mutants verified by reviewer)
Task 7: minor (deferred): test comment claims −14.8 on ffmpeg 5.1 (only bounded, not extracted); OSError from read_json escapes as non-TransmitterError (Task 9 may wrap); fsync on every render segment write — watch lead-fill speed; wrong-typed valid JSON passes from_json
Task 7: complete (commits 8bc35a7..e71dcc8, review clean after 1 fix round)
- 2026-10-10T12:17:45-0400 IDLE at gate: Tasks 1,2,3,5,7 complete; Task 4+ wait for listening PASS from llama-ba.
- 2026-10-10T13:19:38-0400 tick: idle at gate, reported to llama-ba (45-min)
- 2026-10-10T13:20:03-0400 llama-ba: listening test in progress (Shawn asked how to validate (b),(c)); stay idle at gate.
- 2026-10-10T14:19:36-0400 tick: idle at gate, 45-min report to llama-ba
- 2026-10-10T15:19:36-0400 tick: idle at gate, 45-min report to llama-ba
- 2026-10-10T16:19:36-0400 tick: idle at gate, 45-min report to llama-ba (noted 16-tick stop ~21:20)
- 2026-10-10T16:19:41-0400 llama-ba: all criteria passed PROVISIONALLY; Shawn re-checking live wrap on 2-min build (~/spike-out-wrap, wrap 71.7 s) before formal PASS. Stay at gate.

## GATE — Task 2 Step 11 human listening checkpoint: PASS (2026-10-10T16:34:16-0400, relayed by llama-ba)
Operator (Shawn), verbatim: "All passed, though I'm not sure if I tested the live wrap everywhere." Then, after re-testing the live-stream timestamp wrap in every player on a 2-minute build (~/spike-out-wrap, --minutes 2, wrap at 71.7 s, built from this worktree at e71dcc8): "All pass".
Recorded as an operator BLANKET PASS (no per-cell numbers given): Chrome/hls.js, Safari native, iOS, VLC — PASS on (a) segment boundaries/segue/gap, (b) timestamp wrap (VOD + live), (c) packed-audio ADTS+ID3 accepted, (d) iOS 10-min lock screen + AirPlay; step-6 live.m3u8 polling stops after ENDLIST — PASS.
Observation (no action): on live, the page's t= lags program time by the join offset (hls.js currentTime origin = window start at first load) — expected.
Container decision: packed audio stays; Appendix A (fMP4) NOT invoked.
- 2026-10-10T16:34:42-0400 dispatched task4-impl (Sonnet, abd1900635cfc4c13), BASE e71dcc8
- 2026-10-10T16:35:43-0400 task4-impl DONE b75dcda (10 layout tests; 122 transmitter on 3.11; repo 2271).
- 2026-10-10T16:36:02-0400 dispatched task4-rev (Opus, af1f8edf29acf45f7) on e71dcc8..b75dcda
- 2026-10-10T16:37:26-0400 task4-rev (Opus): Spec ✅, Approved, 0 Crit/0 Imp, 7 minors.
- Ruling: Task 4 minors #1 (no positive validate_rows test; abutting-rows mutant survives), #2 (past-the-plan boundary unpinned; > vs >= mutant survives), #4 (silent_frame not checked to be exactly one ADTS frame), #5 (_load maps only FileNotFoundError; other OSError escapes raw) fixed now in task4-fix1 (resume Sonnet) — they guard "never list a segment that does not exist"/the 441-frame invariant, and Task 6/9 build on them. Its re-review is folded into Task 6's review (package base b75dcda). Cost if wrong: one small commit.
Task 4: minor (deferred): build_segment doesn't call validate_rows or check n>=0 (plan-mandated; confirm Task 9 validates and passes n>=first)
Task 4: minor (deferred): FrameStore memory (~17 MB offsets + ~170 MB bytes per 3 h show × keep=2)
Task 4: minor (deferred): no tests for LRU eviction/cache hit, has(), path(), cut row via build_segment; test_layout binds unused F (plan-carried)
Task 4: complete (commits e71dcc8..b75dcda, review clean) — minors 1,2,4,5 in task4-fix1
- 2026-10-10T16:37:39-0400 task4-fix1 dispatched (resumed Sonnet abd1900635cfc4c13), BASE b75dcda
- 2026-10-10T16:38:22-0400 task4-fix1 DONE 783a934 (127 transmitter 3.14+3.11; repo 2276; mutants reasoned, not run) — re-review folded into Task 6 review
- 2026-10-10T16:38:46-0400 dispatched task6-impl (Opus, a822c9a9e9188043e), BASE 783a934 (review base b75dcda to cover task4-fix1)
- 2026-10-10T16:40:53-0400 task6-impl DONE_WITH_CONCERNS 6a65436 (13 planner tests; 140 on 3.11 + debian12 5.1.9/3.11.2; repo 2289). Concerns: corrupt plan.jsonl raises raw JSONDecodeError/TypeError; extend validates only at end; persistent skip re-reported each pass.
- 2026-10-10T16:41:16-0400 dispatched task6-rev (Opus, a999ec08103eaf42e) on b75dcda..6a65436 (incl. task4-fix1)
- 2026-10-10T16:45:06-0400 task6-rev (Opus): Spec ✅ (Task 6 + task4-fix1; mutants m1/m2 killed as predicted), Approved, 0 Crit/0 Imp.
Task 4: task4-fix1 verified in task6-rev (review clean)
- Ruling: Task 6 minors #1 (corrupt plan.jsonl → PlanError naming path+line; NOT treated as empty — reviewer is right that empty would restart over immutable published keys), #2 (pin cut_for_recovery start_frame==boundary row; m3 survives; reachable, would wedge every recovery tick), #3 (frames<=0 → PlanError inside the try → on_skip) fixed now in task6-fix1 (resume Opus implementer); its re-review folds into Task 8's review. Cost if wrong: trivial.
- Ruling: Task 6 minor #4 (persistently unmeasurable show retried first every extend call) → carried into Task 9's dispatch as a consideration (negative memo keyed on show.key in plan_step), not a fix here.
Task 6: minor (deferred): "no eligible packages" PlanError misleading when all skipped; rows appended in that call discarded; no test for run_start moving on skip-on-first-row; FrameStore non-ADTS silent frame raises AdtsError (cosmetic)
Task 6: complete (commits b75dcda..6a65436, review clean)
- 2026-10-10T16:45:11-0400 task6-fix1 dispatched (resumed Opus a822c9a9e9188043e), BASE 6a65436
- 2026-10-10T16:46:40-0400 task6-fix1 DONE 48565c9 (146 both venvs; repo 2295; m3 killed) — re-review folds into Task 8 review
- 2026-10-10T16:47:08-0400 dispatched task8-impl (Opus, ac8dc4e674c7a2fb6), BASE 48565c9 (review base 6a65436 covers task6-fix1)
- 2026-10-10T16:49:32-0400 task8-impl DONE 9fc3c57 (8 render tests; 154 on 3.14/3.11/debian12 5.1.9; repo 2303)
- 2026-10-10T16:49:53-0400 dispatched task8-rev (Opus, aa7077d5baf606f93) on 6a65436..9fc3c57 (incl. task6-fix1)
- 2026-10-10T16:52:16-0400 task8-rev (Opus): Spec ✅ (Task 8 + task6-fix1 verified), Approved, 0 Crit/0 Imp.
Task 6: task6-fix1 verified in task8-rev (review clean)
- Ruling: Task 8 minor #1 (plan-mandated: frame count verified after close() already renamed into the final path; AdtsError path doesn't unlink → FrameStore.has() sees an unverified encode → stuck state needing manual cleanup on an unattended station) and #2 (assert t1.samples+t2.samples == 6*44100 in the segue test) fixed now in task8-fix1 (resume Opus). Re-review folds into Task 9's review. Cost if wrong: small.
- Ruling: Task 8 minor #4 → carried into Task 9's dispatch: render_step must catch FrameCountDrift BEFORE any except RenderError (drift is fatal, RenderError is a per-show skip).
Task 8: minor (deferred): changed package detected only after decoding+encoding the whole changed file (by design)
Task 8: complete (commits 6a65436..9fc3c57, review clean)
- 2026-10-10T16:52:21-0400 task8-fix1 dispatched (resumed Opus ac8dc4e674c7a2fb6), BASE 9fc3c57
- 2026-10-10T16:54:08-0400 task8-fix1 DONE 2309c67 (155 on 3.14/3.11/debian12; repo 2304) — re-review folds into Task 9 review
- 2026-10-10T16:54:43-0400 dispatched task9-impl (Opus, a2df5530e40bf82e5), BASE 2309c67 (review base 9fc3c57 covers task8-fix1); carried I1 epoch ruling; FrameCountDrift catch order already right in brief
- 2026-10-10T16:58:25-0400 task9-impl DONE_WITH_CONCERNS f405b7a (13 pipeline tests; 168 on 3.14/3.11/debian12; repo 2317; 2 mutants killed). Concerns: PlanError when no show left to re-plan into (untested); skip exclusion per-call only; stray Debian output files outside task dir (cleaned, verified absent).
- 2026-10-10T16:58:50-0400 dispatched task9-rev (Opus, a1fe3bc1f5bac6134) on 9fc3c57..f405b7a (incl. task8-fix1)
- 2026-10-10T17:05:44-0400 task9-rev (Opus): Spec ✅ for focus #1/#2 and task8-fix1; Needs fixes: 1 Important (plan-mandated, reproduced) — a config change altering frame counts (clip_pause_seconds, or an ffmpeg extra_frames change) raises fatal FrameCountDrift every tick instead of the spec's re-plan after the render frontier.
Task 8: task8-fix1 verified in task9-rev (review clean)
- Ruling: Task 9 Important #1 — FIX despite plan text (spec "Frozen means rendered … re-planned on any config or library change" governs): before encoding, compare st.frames_of(show) with r.frames; mismatch → treat like a changed package (skip at its boundary, re-plan, log "plan-changed"). FrameCountDrift stays for an encode disagreeing with the CURRENT model.
- Ruling: Task 9 Minor #1 (recovery drop then PlanError → render_step renders past-due old-plan segments which publish would upload = wasted PUTs; spend is the strict surface) — FIX: recovery branch computes cut+extend first, then drops unpublished segments, then write_plan; and render_step refuses (no-op) while a recovery is pending (publish_next <= index_at(now)). Cost if wrong: small.
- Ruling: Task 9 Minor #3 (plan missing while publish.json has last → fresh run starts under published keys → on-air mid-show cut; operator rule "never cut mid-song") — FIX: when rows empty and pub.last set, drop segments > last and start at max(fresh, (last+1)*441).
- Ruling: Task 9 Minor #5 test gaps (drift test asserts the drifted encode is unlinked; recovery test asserts segments <= last survive; encode-failure test asserts replacement starts at victim's start; a render_step StationRootError test) — added in the same round, cheap.
Task 9: minor (deferred): no negative memo for persistently failing shows (CPU/log only; memo keyed by show.key would be safe)
Task 9: minor (deferred): PlanError when no eligible show remains for render-time re-plan untested; encode-failure variant redoes doomed encode each tick
Task 9: minor (deferred): stale .N.aac.XXXX.tmp in render/seg/<epoch>/ never GC'd; helpers imports pipeline at module top (collection blast radius)
- 2026-10-10T17:05:54-0400 task9 fix round 1 dispatched (resumed Opus a2df5530e40bf82e5 as task9-fix1), FIX_BASE f405b7a
- 2026-10-10T17:06:15-0400 RELAY-NOW from llama-ba: finish Task 9 through review/fix rounds, start no new task, write HANDOFF, disarm, report RELAY-READY.
- 2026-10-10T17:10:12-0400 task9-fix1 DONE 775f0c1 (174 on 3.14/3.11/debian12; repo 2323; 6 mutants killed as predicted). Widened: every fresh run drops local segments > last (all if nothing published). Re-review: resumed Opus a1fe3bc1f5bac6134 as task9-rerev1 on f405b7a..775f0c1
- task9-rerev1 (Opus): all 4 findings ADDRESSED (old probes now fail where the defects were), widening of the lost-plan drop judged safe, Approved.
Task 9: fix round 1/5 (4 addressed, 0 open — config-change re-plan, recovery order + render no-op while recovery pending, lost-plan start at max(fresh,(last+1)*441), 4 test gaps; commits f405b7a..775f0c1)
- Ruling: Task 9 parked (reviewer Minor, reproduced) — on a frame-count change (and, pre-existing, on a re-voiced package) render_step adds the slug to `excluded`; on a ONE-package station (or when every other package is momentarily ineligible) the re-plan pool is empty → PlanError every tick = permanent wedge until the package set changes. Reviewer's fix: for "plan-changed" and "package changed with an eligible new key", do NOT exclude (extend re-measures and re-plans the show in place); exclude only on a second mismatch in the same call and on "render failed". PARKED for the successor as a small task9-fix2 (Opus/Sonnet) BEFORE Task 10, not done here because RELAY-NOW said start no new work and the review approved. Cost if left: a real station has many packages, trigger is a deliberate config change or re-voice on a 1-package station.
Task 9: complete (commits 9fc3c57..775f0c1 incl. task8-fix1 2309c67, review clean after 1 fix round; 1 parked with ruling above)

## HANDOFF (2026-10-10T17:13:18-0400, peer 1e18c958-066d-4cae-ae48-e032d3e8aa40 → successor, on llama-ba's RELAY-NOW)

**State.** Branch playout-phase1, HEAD 775f0c1, tree clean. 18 commits since ff14e07 (git log ff14e07..HEAD). Tasks COMPLETE and reviewed: 1, 2 (+Step 11 PASS), 3, 4, 5, 6, 7, 8, 9. NEXT: Task 10 (Model hint: sonnet), then 11–19, then Fable final whole-branch review, then stop at the finish menu (never merge/push/tag). Nothing in flight; STATE.md mode: done; my tick disarmed.
**Suite at HEAD:** transmitter 174 passed on .venv (3.14), .venv311 (3.11.15) and debian:12 (ffmpeg 5.1.9 / Py 3.11.2); full repo 2323 passed, 7 deselected (implementer-reported at 775f0c1; re-verify before relying on it).
**Gate:** Task 2 Step 11 human listening checkpoint = operator blanket PASS (see GATE section above). Packed audio stays; Appendix A NOT invoked.

**Do first (parked ruling, see Task 9 line above):** task9-fix2 — don't exclude a show from render_step's re-plan pool for "plan-changed" or "package changed with an eligible new key"; exclude on a 2nd mismatch in-call and on "render failed"; test the one-package-station wedge (reviewer probe: scratchpad t9rerev/…/test_probe_rev.py in the old peer's scratchpad). Then re-review (Opus).

**Carry-forwards into later dispatches (rulings already made):**
- Task 10 / 11 (publisher): local publish.json `last` must be persisted BEFORE or atomically with the R2 state/horizon.json write (or reconciled on start) — lost-plan start and recovery now trust local `last` as "nothing above this is listed"; a crash between the two would re-render under immutable, CDN-cached keys. (task9-rerev1 out-of-scope obs.)
- Task 11: drop dead `NOW_US = None` (pre-flight M3); Task 11's interface list must include `check_epoch` (used by Task 12) (M6); verify load_or_create_epoch creation is serialised by the publish flock (Task 3 minor).
- Task 12 (prune): check `prune_margin_minutes` floor — ge=0 allows deleting still-listed segments (k=6×10.24 s + player lag) (Task 3 minor). Run the Debian-12 gate after Task 12 (ruling I2).
- Task 13 (fallback): the fallback builder is the other caller of segment.assemble; silent frame must be exactly one ADTS frame (FrameStore checks this; fallback may not).
- Task 14: the L6072 test "keeps publishing" needs an assertion matching its name (M3); verify Runner treats PlanError/StationRootError as alerts and FrameCountDrift as halting (Task 9 concerns).
- Plan-mandated duplication (pre-flight M4: lock+guard preamble ×3, seg-seconds ×3, clip-pause ×3, ffmpeg stderr ×2, playlist header ×2): ruling = follow plan text; final review triages.
- M2: spec's "128 kbps CBR" isn't achievable with native aac — a deviation for the final review to note.
- Pre-flight I1 epoch ruling is DONE (helpers E = 4e9 s). B1 DONE.

**Debian-12 gate cadence (ruling I2):** `packages/transmitter/scripts/test-in-debian12.sh` at the end of every ffmpeg-touching task (plan: 2, 7, 8, 9, 13, 14) PLUS after Tasks 6 and 12. Image debian:12 is cached; runner excludes ./.venv* and ./.superpowers (f5256ac). Docker Desktop is up. Children run it in background with ≤270 s polls. Never ssh to hugo without llama-ba's go.
**.venv311 arrangement:** `.venv311` = uv-created CPython 3.11.15 venv in the worktree root with ONLY `-e packages/transmitter[dev]` (`VIRTUAL_ENV=$PWD/.venv311 uv pip install -e "packages/transmitter[dev]"` if deps change). Every implementer runs `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` in addition to `./.venv/bin/python -m pytest` (3.14, full repo). Excluded from git status via the shared .git/info/exclude (see Escapes).
**Escapes:** exactly one — the `.venv311/` line appended to /Users/shawn/projects/llama/.git/info/exclude (outside the worktree, local-only, untracked). Also, task9-impl briefly wrote two stray files outside its task dir (`<worktree>/scratch-deb.out`, `$D/task9-deb.rc`), deleted by it and verified absent by me. Plus my own stray empty `~/.claude/sdd-state-helper.placeholder` (created by a mistaken `cat >`, removed immediately). No other writes outside the worktree.

**Conventions I used (successor may keep):**
- Briefs/review packages: superpowers scripts `task-brief` / `review-package` into .superpowers/sdd/2026-10-10-playout-phase1/; shared reviewer constraints file there: constraints.md (plan Global Constraints + spec Stakes; spend is the strict surface).
- Ruled minor follow-ups after an Approved review were done as `taskN-fixK` by resuming the implementer, and their re-review was FOLDED into the next task's review (package base = previous task head) — task2-fix1→T3 review, task4-fix1→T6, task6-fix1→T8, task8-fix1→T9; each verified there.
- Fix rounds resume the original implementer/reviewer via SendMessage with a NEW task name (single-use dirs).
- `orch/state.py` (copied here): `python3 state.py $D/STATE.md add <task> <agentId> | rm <task> | touch` keeps STATE.md in-flight/probe-dirs in step. Successor should claim its own orch dir (e.g. orch-r1) and its own STATE/tick per llama-ba.
**All rulings:** every "Ruling:" line in this ledger, in order (pre-flight section + per-task). Deferred minors: every "minor (deferred)" line — point the final reviewer at them.
**Dispatch log by model:** preflight Opus; T1 impl Sonnet/rev Opus; T2 impl Opus/rev Opus/fix1 Sonnet; T3 impl Sonnet/rev Opus; T5 impl Sonnet (+2 fix rounds)/rev Opus/rerev Opus×2; T7 impl Opus (+1 fix)/rev Opus/rerev Opus; T4 impl Sonnet (+fix)/rev Opus; T6 impl Opus (+fix)/rev Opus; T8 impl Opus (+fix)/rev Opus; T9 impl Opus (+1 fix round)/rev Opus/rerev Opus.
**Meter at handoff:** 5h ~3–5% (resets 21:19), 7d 2%.
- 2026-10-10T17:13:25-0400 tick 6c11c17a deleted; armed flag removed; armed-global kept iff another armed-* exists. RELAY-READY.
