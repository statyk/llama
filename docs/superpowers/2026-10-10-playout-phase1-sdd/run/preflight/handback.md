# preflight: mechanical consistency scan of the playout phase-1 plan

Plan: `docs/superpowers/plans/2026-10-10-playout-phase1.md` (lines cited as `L…`). Spec: `docs/superpowers/specs/2026-10-09-playout-design.md` (`S…`).
Read-only. I changed no tracked files, made no commits and made no network calls.

## How I checked it (measured, not just read)

1. **I assembled the plan's final-state Python code verbatim into a scratch tree.** It came to 53 files: every `src/transmitter/*.py`, every `tests_transmitter/*`, the helper appends in plan order, the three `cli.py` edits, and `antenna/templates/show.html`. Then I ran the whole suite with `./.venv/bin/python -m pytest`, with PYTHONPATH pointing at the scratch tree; `transmitter.__file__` confirmed it resolved inside the scratch tree.
   **Result: 192 passed, 0 skipped, 0 failed** on ffmpeg 8.1.1 and CPython 3.14.7. In its final state, the plan's code agrees with the plan's tests.
2. **I checked that Task 1's commit `037162d` matches the plan.** Its 10 core files are byte-identical to the plan's text: grid, id3, adts, segment, errors and their five tests.
3. **I scanned for anything newer than Python 3.11.** Two checks over all extracted code:
   - a tokenizer pass for PEP 701 f-strings (nested quotes of the same kind, backslashes inside expressions) plus a regex for 3.12+ names;
   - an AST pass that mimics 3.11's eager evaluation of annotations.
   **Both came back clean.**
4. **I ran two mutation experiments in scratch copies.** They are described under B1 and I1.
5. **I did not execute antenna (TypeScript); I hand-simulated it instead.** There is no `node_modules` and installing it needs the network. I worked through every assertion in `playlist.test.ts` (12 tests), `clock.test.ts` (7) and `nowplaying.test.ts` (4) against `playlist.ts`, `clock.ts` and `nowplaying.js`, and all of them are consistent.
   - **Not verifiable offline:** the package names and exports `@cloudflare/vitest-plugin@1` / `cloudflareTest` / `vitest@5` (L6564–6608, L6625). The plan states these as measured facts.

## Findings (severity, lines, suggested ruling)

### B1 — BLOCKER, depending on task order: `helpers.py` has no `Path` import until Task 4 runs
- **Where it bites:**
  - Task 5's helpers append uses `Path` in annotations: `def make_root(tmp_path: Path)` (L2486) and `build_package(root: Path…)` (L2499).
  - Task 7's append does too: `write_mp3(path: Path…)` (L3231).
  - The only `from pathlib import Path` in `helpers.py` comes from Task 4's append (L2176).
- **Why the order matters:** L116 explicitly allows Tasks 3, 5 and 7 to run *before* Task 4, while the operator is still listening. On Python 3.11, annotations are evaluated when the `def` runs, so `helpers.py` then fails to import with `NameError: name 'Path' is not defined`, and every test file fails with it.
- **Why it can hide:** it is **invisible on the worktree venv (CPython 3.14.7)**, because 3.14 evaluates annotations lazily (PEP 649). I confirmed this: helpers built from Tasks 1+2+5 only, and from 1+2+7 only, both import fine on 3.14. It first surfaces at Task 7 Step 5's Debian 12 run (L3706).
- **Ruling:** move `from pathlib import Path` out of Task 4's append (L2176) into Task 2's append (L870–874), or have Task 5 add it.
- **Also:** state at L116 that Task 7 depends on Task 5. Task 7 imports `build_package` and `make_root` (L3345) and the `station.Show` interface (L3212).

### I1 — IMPORTANT: test time bomb on 2027-01-15
- **Cause:**
  - The test epoch is `E = 1_800_000_000 * 1_000_000`, i.e. 2027-01-15T08:00Z (L4026), and `NOW = E + 1000·d`.
  - `Station.scan_now` checks the quiet period against `NOW/1e6` (L4337).
  - But `build_package` sets every file's mtime to the *real* clock minus 3600 s (L2493–2496), and `make_station` uses `quiet_minutes = 0`.
  - Once the real clock passes about **2027-01-15T11:50Z**, `now_s − newest < 0`, so every package becomes Ineligible.
- **Measured:** I moved E into the past in a scratch copy, which simulates that date. **16 tests went red:** all 13 in `test_pipeline` and 3 in `test_service`, failing with `PlanError: no eligible packages`. The 4 CLI tests that use the real clock are unaffected.
- **Ruling:** set `E = 4_000_000_000 * 1_000_000` (year 2096) and fix the "(2027-01-15)" comment. I verified this: **192/192 pass**. Nothing else depends on E's actual value; `make_publisher`'s `today=lambda: "2027-01-15"` is only a label.

### I2 — IMPORTANT (environment): local runs cannot catch Python 3.11 regressions
- **Facts:**
  - `./.venv/bin/python` is **3.14.7**, and the host has no 3.11.
  - Only `test-in-debian12.sh` exercises 3.11 and ffmpeg 5.1. It runs at Tasks 2, 7, 8, 9, 13 and 14 (L1523, L3706, L3984, L4504, L5996, L6518). Tasks 3–6 and 10–12 never run it.
- **Ruling:** the orchestrator also runs the Debian script after Tasks 6 and 12, or at minimum treats Task 9's Debian run as the 3.11 gate for Tasks 3–6.
  - Docker 29.4.1 is up, but no `debian:12` image is cached, so the first run pulls it (network).
  - Host Node is v26 (hugo runs 22; `engines` says `>=22`).

### M1 — MINOR: `config init` does not write atomically, against Global Constraint L24
- `target.write_text(DEFAULT_CONFIG_TOML)` at L2135 writes under `~/.transmitter/` without temp-and-rename.
- **Ruling:** use `workspace.atomic_write_text`. The exists-check stays. (It is a one-shot write, so the exposure is low.)

### M2 — MINOR: spec says "128 kbps CBR" (S298); the plan uses native `aac` at `-b:a 128k`, which is not CBR
- L985–992 acknowledges this, and Global Constraint L17 just says "128 kbps".
- **Ruling:** add it to the deliberate deviations list at L29–34, so reviewers don't flag it.

### M3 — MINOR: tests that can pass vacuously or claim more than they check
- **L918–922 `test_encode_pcm_yields_station_format_frames`:** the loop asserts nothing if the encode returns zero frames. Ruling: add `assert frames`.
- **L6072–6078 `test_runner_alerts_and_keeps_publishing_when_planning_fails`:** it asserts only the alert, never that publishing happened. Ruling: rename it to `…_alerts_when_planning_fails`, or seed a segment and assert it was PUT.
- **L5010 `NOW_US = None`:** dead constant. Ruling: delete.

### M4 — MINOR: logic duplicated verbatim that the plan mandates
- The lock + guard preamble appears three times: `publish_batch` L5489–5492, `prune` L5712–5715, `upload_fallback` L5977–5979.
- The segment length in seconds is computed three times: `_D_SECONDS` L2040, `horizon_doc` L5425, `FallbackBuild.index` L5912.
- The clip pause in samples is derived three times: `Station.pause_samples` L4346, `RenderSettings.from_config` L3932, `_publish_site` L5454.
- The ffmpeg stdin-close / stderr-tempfile pattern is duplicated in `AacFileEncoder` (L1081–1116) and `LoudnessMeter` (L3557–3586).
- The playlist header is duplicated in `offairPlaylist` (L6903–6907) and `buildPlaylist` (L6944–6948).
- **Ruling:** optional. If a reviewer flags these, accept a small helper (e.g. `grid.D_SECONDS`). None is a correctness issue.

### M5 — MINOR: lint-level problems (the repo has no linter configured)
- Unused imports: `PlanRow` in `test_planner` (L2931), `audio` in `test_analysis` (L3346), `json` in `fallback.py` (L5887).
- The append-style edits put imports in the middle of `helpers.py` and `test_cli.py` (L1733, L2176, L2480, L4019, L4872, L6144).
- **Ruling:** leave as is, or have each implementer hoist the imports.

### M6 — MINOR: interface lists and comments out of step with the code
- **Interface:** Task 11's Produces list (L4864) omits `check_epoch` and `BucketClient`, yet Task 12 consumes `check_epoch` (L5578). The code has it at L5435.
- **Comment, L1861:** cites "tests/test_config.py"; the path is `tests_transmitter/`.
- **Comment, L6068:** "160 s of lead"; the computed value is 168.64 s.

### M7 — MINOR (observation, not a change): the off-air playlist carries no PROGRAM-DATE-TIME
- `offairPlaylist` (L6902–6913) gives the notice segment no `EXT-X-PROGRAM-DATE-TIME`. S391–392 asks for PDT "on every segment"; that rule is plausibly meant for grid segments only.
- Similarly, the per-segment discontinuity numbering (L6934–6943) makes `DISCONTINUITY-SEQUENCE` equal `floor(n0/len)−1` when the first listed segment starts a loop. S398 says "the sequence is floor(N/len)". The plan's own statement of intent (L6935) is per segment and self-consistent, and the tests check per-segment numbering.
- **Ruling:** none needed; already design-reviewed.

### Python 3.12+ and ffmpeg >5.1
- **Python: none found.**
  - No `itertools.batched`, `Path.walk`, PEP 695 generics or `type` statements, `typing.override`, `datetime.UTC`, or PEP 701 f-strings.
  - No annotation names a symbol before it is bound.
  - `tomllib` is 3.11 and fine; `functools.cache` and `str | None` in dataclasses are fine.
- **ffmpeg: nothing that clearly needs more than 5.1.** The features used are native `aac`, `-f adts`, the `aac` demuxer, `ebur128=peak=true:framelog=verbose`, `-map 0:a:0`, input-side `-ac`/`-ar`, and `-nostats`. L3707 already has a fallback if `framelog` is rejected.
- **Runtime-dependent facts the Debian run must confirm:** `extra_frames` (1 on 8.1), 1024 samples of priming not trimmed from raw ADTS, and LAME end-padding trimming. These are already gated at L1524.

## Table 1: pairs of tasks that share a file or an interface

| Tasks | Producer → consumer (names, signatures, files) | Result |
|---|---|---|
| 1→2 | `grid` constants, `adts.split_frames/parse_header/require_station_format/build_frame`, `segment.assemble/parse`, `errors.EncodeError` → used by aacenc/spike/tests | consistent |
| 1→2 helpers.py | T1 creates it (L329–344, imports `shutil`, `pytest`); T2 appends `subprocess`, `numpy`, `decode_adts` (L870–886) | consistent |
| 1→3 cli.py / test_cli.py | T1 `app`, `_main` callback, `main_cli` (L278–323); T3 adds `config_app` after `app` (L2111–2137) and appends tests (L1732) | consistent; the mid-file imports are M5 |
| 1→14 cli.py | T14 adds imports at the top, commands after `config_init`, and `logging.basicConfig` in `main_cli` (L6413–6511); `render`/`run`/`status` names don't shadow any imported module | consistent (the assembled cli passes all CLI tests) |
| 1→4 | `adts.frame_offsets/build_frame`, `segment.assemble`, `grid.SEGMENT_FRAMES`, `LayoutError` | consistent |
| 2→4 | `silent_frame()` → `bytes` → `FrameStore(shows_dir, silent_frame)` (L2391) | consistent |
| 2→4 helpers.py | T4 appends `from pathlib import Path`, `fake_frame`, `write_fake_show`, `payloads` (L2175–2194) | consistent, but see B1 |
| 4↔5 / 4↔7 helpers.py | T5 (L2486) and T7 (L3231) use `Path` that only T4 imports; L116 allows 5 and 7 before 4 | **MISMATCH, B1** |
| 5→7 | `build_package(..., audio=Callable[[Path,int],None])`, `make_root`, `station.evaluate` → `test_analysis` (L3345, L3387) | consistent; dependency not stated at L116 (B1) |
| 2→7 | `aacenc.as_station_pcm` → `LoudnessMeter.write` (L3552) | consistent |
| 2→8 | `AacFileEncoder(out, ffmpeg)`, `.write`, `.write_silence`, `.close`, `.abort`, `frames_for`, `pad_to_frame`, `extra_frames`, `ENCODER_PRIMING_SAMPLES` | consistent |
| 2→9 | `extra_frames(ffmpeg)`, `silent_frame(ffmpeg)` → `FfmpegEngine` (L4310–4314) | consistent |
| 2→10 | `ENCODER_PRIMING_SAMPLES` → `file_starts` base (L4723) | consistent; matches S310–312 |
| 2→13 | `encode_pcm`, `extra` (frames_for model) → `_encode_exact` (L5939) | consistent |
| 2→7,8,9,13,14 test-in-debian12.sh | T2 creates it (L1502–1521); the others run it | consistent; copies `antenna/` into /work, which `test_site` and helpers need |
| 3→6 | `workspace.atomic_write_text` → `write_plan` | consistent |
| 3→7 | `read_json`, `write_json` → analysis cache | consistent |
| 3→8 | `RenderConfig` fields `ffmpeg`, `music_target_lufs`, `speech_target_lufs`, `clip_pause_seconds` → `RenderSettings.from_config` | consistent |
| 3→9 | `TransmitterConfig(root, station={...}, planner={...}, render={...})`, `Workspace.plan_path/shows_dir/seg_dir/cache_dir`, `Epoch(epoch_id, epoch_us).index_at`, `load_publish_state` | consistent |
| 3→10 | `Epoch.epoch_us/.iso/.start_us` | consistent |
| 3→11 | `PublishConfig.bucket/batch_segments/daily_put_budget/prune_min_segments/guard_check_minutes`, `AntennaConfig.site_url/station_name`, `Workspace.puts_path/guard_cache_path/lock_path`, `PublishState` fields, `load_fallback_version` | consistent |
| 3→12 | `prune_margin_minutes`, `prune_min_segments`, `save_publish_state` | consistent |
| 3→13 | `Workspace.fallback_dir`, `save_fallback_version` | consistent |
| 3→14 | `load_config`, `load_epoch`, `load_or_create_epoch`, `default_root`, `AntennaConfig.dir` | consistent |
| 4→6 | `PlanRow(seq, slug, dir, key, start_frame, frames, run_start, cut_frame)`, `.end_frame`, `validate_rows` | consistent |
| 4→9 | `FrameStore.has/path/build_segment`, `rows_overlapping`, `segment_pieces` (tests) | consistent |
| 4→9 helpers.py | `fake_frame`, `write_fake_show` → `FakeEngine` (L4056, L4062) | consistent |
| 4→10, 4→11 | `PlanRow` → `row_span_us`, `file_starts`, `_publish_site` (uses `.dir`, `.key`, `.slug`) | consistent |
| 5→6 | `Show(slug, dir, entries, key, meta)` → `extend` uses `.dir.name`, `.key`, `.slug` | consistent |
| 5→7/8 | `Show.entries: tuple[Entry(path, kind, title)]`, `Show.dir`, `Show.meta` → `analyze_show`, `render_show` | consistent |
| 5→9 | `station.scan(root, now_s=, quiet_s=)` raises `StationRootError` → `Station.scan_now` | consistent; the clock mismatch here is I1 |
| 5→9 helpers.py | `make_root`, `build_package`, `set_age` → `make_station`, `test_pipeline` | consistent |
| 5→10/11 | `build_package` manifest (`show`, `source`, `tracks`, `briefing.file`) → `read_package_notes`, `build_notes` | consistent |
| 5→14 | `station.evaluate(..., quiet_s=0)`, `station.Show` → `row_analysis` | consistent |
| 6→9 | `extend(..., on_skip=)`, `next_start`, `replan_from`, `cut_for_recovery`, `publish_next`, `read_plan`, `write_plan` | consistent |
| 6→11 | `read_plan`, `publish_next` → `publish_batch` | consistent |
| 6→14 | `read_plan` → `status_lines` | consistent |
| 7→8 | `ShowAnalysis.files[].samples/kind/i_lufs/tp_dbfs`, `tracks_i_lufs/tp_dbfs`, `gain_db`, `iter_decode` | consistent |
| 7→9 | `load_or_analyze(cache_dir, show, ffmpeg)` | consistent |
| 7→9 helpers.py | `FileAnalysis`, `ShowAnalysis` constructors → `FakeEngine.analyze` | consistent |
| 7→10/11 | `ShowAnalysis.meta`, `.files` → `build_timeline`, `make_publisher` | consistent |
| 7→13 | `iter_decode`, `LoudnessMeter`, `gain_db` → `_decode_all`, `_gained` | consistent |
| 7→14 | `analysis.load_cached(cache_dir, key)` → `row_analysis` | consistent |
| 8→9 | `render_show(show, analysis, out, *, settings, extra)`, `planned_frames(analysis, pause, extra)`, `RenderSettings.from_config` | consistent |
| 8→9 helpers.py | `planned_frames` → `FakeEngine.encode_show` (L4061); FakeEngine's pause (0.75 s default, L4035) equals `make_station`'s config pause | consistent |
| 8→10 | `show_layout(analysis, pause).spans[].start_sample/kind/title` → `file_starts` | consistent |
| 9→14 | `Station(ws, cfg, epoch, engine, log=)`, `FfmpegEngine(ws, cfg)`, `plan_step(st, t, max_new=)`, `render_step(st, t, limit=)`, `FrameCountDrift` | consistent |
| 9→11/14 helpers.py | `E`, `Epoch`, `TransmitterConfig`, `Workspace` (T9 imports) → `make_publisher` (L4938–4942) | consistent; E is I1 |
| 9→14 helpers.py | `NOW`, `FakeEngine`, `make_station` → `test_service` | consistent |
| 10→11 | `DAY_US`, `row_span_us`, `build_timeline(..., last_n=, pause_samples=)`, `airtimes`, `read_package_notes`, `build_notes`, `render_show_page(template, notes, site_url=, station_name=)` | consistent |
| 10→11/14 show.html | T10 creates `antenna/templates/show.html`; `TEMPLATE_PATH = parents[3]/antenna/templates/show.html` (L4926), `load_template` uses `cfg.antenna.dir/templates/show.html` (L6281) | consistent |
| 10→17 | page links `../style.css` and classes `lineage`/`set`; T17 `style.css` defines them (L7624) | consistent |
| 10→17 | timeline `shows[].{start,end,artist,date,venue,city,files[].{title,start}}` → `findNowPlaying`, `nowPlayingText` | consistent |
| 11→12 publish.py | T12 appends `PruneReport`, `prune` using `publish_lock`, `guard_blocks_publishing`, `check_epoch`, `put_json`, `horizon_doc`, `HORIZON_KEY`, `STATE_CACHE`, `PutBudgetExceeded`, `PublishError` | consistent; interface omits `check_epoch` (M6) |
| 11→12 helpers.py | `FakeBucket.objects/log/delete_object` (instance-overridable), `make_publisher(prune_min=)` | consistent |
| 11→13 | `Publisher.uploader/ws/cfg/epoch`, `AAC_TYPE`, `IMMUTABLE`, `HORIZON_KEY`, `STATE_CACHE`, `put_json`, `horizon_doc(epoch, first, last, now, v)`, `publish_lock`, `guard_blocks_publishing` | consistent |
| 11→14 | `PutBudget(path, limit)`, `Uploader(client, bucket, budget)`, `Publisher(..., analysis_for=)`, `publish_batch`, `PublishReport.stopped/error/uploaded` | consistent |
| 11→14 helpers.py | `FakeBucket`, `TEMPLATE_PATH`, `write_seg` → `test_service`, `test_cli` | consistent |
| 12→14 | `prune(p, t)` → `PruneReport.error/deleted` → `publish_all`, the `publish` command | consistent |
| 13→14 | `build_fallback(loop, notice, *, ffmpeg, music_target_lufs, speech_target_lufs, extra)`, `write_local(ws, build)`, `upload_fallback(p, build, now)` | consistent |
| 11→15 | `horizon_doc` keys `epoch_id, epoch(ISO), d=10.24, first, last, published_at, container="adts", fallback_version` = TS `Horizon` (L6813–6822); `seg/<epoch_id>/<N>.aac` = `segment_key` | consistent |
| 13→15/16 | `index.json` `{len, notice: "fallback/<v>/notice.aac", d}` → `FallbackIndex{len, notice}`; keys `fallback/<v>/<k>.aac` | consistent |
| 15→16 | `gridOf`, `indexAt`, `startMs`, `buildPlaylist(inputs incl. offairSeqMs)`, `FallbackIndex`, `PlaylistConfig`, `Horizon` | consistent |
| 15→16 index.ts | T15 placeholder `scheduled()`; T16 replaces it | consistent |
| 15→17 package.json / tsconfig | T17 adds `hls.js`; `tsconfig.include` already has `public`, `allowJs: true`, `checkJs: false` (so `player.js` needs no DOM lib) | consistent |
| 16→17 | `live.m3u8` with ENDLIST → `LEVEL_LOADED live===false` → `offAir` | consistent |
| 2→15 .gitignore | T2 adds `*.aac`; T15 adds `antenna/node_modules/`, `antenna/.wrangler/` | consistent |
| 11,14,16,17→18 | bucket `llama-radio` (L6584), `R2_ACCESS_KEY_ID/SECRET` (L5236), `fallback render LOOP --notice` (L6483), `deploy:assets` (L6560), asset keys = WAF allowlist (L7771–7777) | consistent |
| all→19 | CLAUDE.md commands match the CLI, the test dir and the scripts | consistent |

## Table 2: does each task agree with itself?

| Task | Tests vs code, files created vs touched, imports | Result |
|---|---|---|
| 1 | All constants and expected bytes recomputed (ID3 sizes 0x35/0x3f/73; ADTS header `fff1508003dffc`; offsets 0,8,17,27,38,50; wrap 9321→299 008); the Step 3 failure prediction is right; the import guard does not match its own source. Committed code is byte-identical. | consistent |
| 2 | `frames_for(4096,1)=5`; spike build at 1.5 min → n0 = 9316, count = 9, wrap inside show B; the segue window derivative is 0.0197 < 0.0214; the live-playlist window maths holds; meta.json round-trip | consistent (passes) |
| 3 | Template = defaults; strictness reaches nested sections; epoch whole-second id `e20261010T120000Z`; `d` float 10.24 round-trips | consistent; M1 |
| 4 | Every piece/segment payload count re-derived (159 + 87 + 195 = 441, etc.) | consistent |
| 5 | All 9 break legs match their reason substrings; the vanishing-file monkeypatch hits `dj_dir.iterdir`; dot dirs are skipped | consistent; B1 (helpers) |
| 6 | Order, cycles, the new-show-once rule, recovery boundary 5733, `publish_next` cases | consistent |
| 7 | ebur128 regexes against the sample text; silence → (None, None); gain arithmetic | consistent (passes on 8.1); B1 (helpers `Path`) |
| 8 | Layout 0/107/1107/2114, padded 3072; `file_gain` 4 dB / 6 dB; abort leaves no temp file | consistent |
| 9 | 2-row plan at start 1003·441; recovery at last = 1013 → cut 447 174; replan keeps the boundary; the on-air refusal at seg 1033 | consistent; I1 |
| 10 | Window 1764, `recent=[a]`, cut stops `file_starts`, template fully substituted | consistent |
| 11 | PUT order, retry sleeps [1.0, 2.0], budget 5, runs recorded first, guard cache 15 min, flock on a second fd | consistent; M3 (`NOW_US`), M6 |
| 12 | n_max/prunable arithmetic for all 7 tests (200, 151/150, 21+10, 0, 5 then 45, 59 then 60) | consistent |
| 13 | 25 s loop → 3 segments; notice truncated to 441 frames; content-hash version | consistent |
| 14 | Runner fill trace (29 + 4 segments, lead 368.6 s ≥ 349.8 s; low water at +200 s); drift latch; CLI paths | consistent; M3, M6 (comment) |
| 15 | Hand-simulated all 12 playlist tests (grace, fallback disc = 14 at 101, empty horizon, MS 1007, off-air boundary, nulls) | consistent |
| 16 | 8 puts (immediate + 51..57), cap 10, offair 1 put + 7 skipped, guard first, cap formula `ceil(75000/10240)+2=10` | consistent |
| 17 | nowplaying cases (file null before 12:00:00.023, formatting with "—" and "·"); dry run = 6 lines | consistent |
| 18 | Doc-only; names match the code | consistent |
| 19 | Doc-only; Setup line and commands match | consistent |

## Conflicts with the Global Constraints or the spec
- **Atomic writes:** `config init` (M1), against L24.
- **"128 kbps CBR":** S298 vs the native-aac average bitrate (M2). It is not in the deviation list.
- **Nothing else.**
  - Eligibility, joins, gain rule, the ordering invariant, no List calls, flock, PUT budget, guard read cadence, prune-before-delete, the recovery cut, clock grace/fallback/off-air/PUT cap/identical-byte skip, and `workers_dev`/`preview_urls`: all match S181–203, S225–237, S296–358 and S380–402.
  - Phase-1 omissions (static `index.html`, the clock not reading `timeline.json`, no Media Session/embed) are declared at L8018–8022.

## Scratch artefacts (not in the repo)
- **Tools:** `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-playout-phase1/1e18c958-066d-4cae-ae48-e032d3e8aa40/scratchpad/tools/{extract.py,py311check.py,eager_ann.py}`.
- **Trees:** the assembled tree is `…/scratchpad/repo`, and the I1 mutation copy is `…/scratchpad/bomb`.
- **Log:** `$D/preflight/preflight.log`.
