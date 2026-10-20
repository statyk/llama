# t5-impl handback — Task 5: `scripts/replay_holds.py run` + fixture library + zero-writes test

Status: DONE. Model: Opus 5.5 (implementer; no subagents dispatched).

## Commits (branch held-backlog-tier1)
- a838a66 fix(replay): carried review fixes — slfm cache never raises, diff carries new values, scratch guard covers shows/
- f39ad88 feat(scripts): replay_holds run, the offline hold replay

Full suite at f39ad88: `./.venv/bin/python -m pytest -q` -> **3270 passed, 1 skipped, 8 deselected** (baseline 3225; +45). Tree clean.

## What was implemented
**Carried fixes (replay.py, a838a66)**
- `CacheOnlySetlistFM.setlist`: read + `_pick` wrapped in try/except, returns None on a malformed/non-dict cache file, NOT recorded as a miss (mirrors SetlistFMClient). Test parametrized over 5 malformed bodies.
- `code_identity`: tests for the `-dirty` suffix and the `version:` fallback (FileNotFoundError, CalledProcessError, empty sha) via monkeypatched `subprocess.run`.
- `shipped_diff` on a track-count change: `new`/`new_source` and set/segue `new` come from `new.tracks[i]` when `i < len(new.tracks)`, None only past its end. The Task 4 test that pinned `None` is renamed `test_shipped_diff_track_count_change_reports_every_index` and now asserts the real values; a new test covers a longer replayed show.
- `compute_legs` scratch guard: also refuses a scratch inside `ws.dir.parent` (the library's `shows/`), message "it lies inside the library's shows directory"; the test covers another show's dir, a new dir and a nested dir, with nothing created.

**replay_show (replay.py, f39ad88)**: `replay_show(ws, *, config, ia, slfm, scratch, delivered) -> ShowReplay`. Order: `derive_state` (inside the try, ruling M3), an explicit `overrides.json` pre-check (`read_model(..., Overrides)`; OSError/ValueError incl. pydantic ValidationError -> `"overrides.json unreadable"`), `input_digests`, then the stored-side fields (stored_flags, stored_core_flags = minus package+briefing families, stored_brief_guard over the stored briefing vs the stored show (None without briefing.json), selected_venue/city from the provenance candidate's recording matching `stored.identifier`, stripped, None if blank or absent), and only then `compute_legs` + `classify` + `shipped_diff` (title/venue/city/date/set/segue/set_breaks/alignment) + notes (gather notes, then vet notes). `reproduces` = sorted(core) == sorted(gather+vet). CacheMiss -> `str(err)` ("cache miss: md_<id>.json"); any other exception -> `f"{type}: {err}"[:200]`. `slfm_miss` = `slfm.misses` grew during this show. Stored fields are filled before the replay, so they exist for needs-LLM shows and, where readable, for unreplayable ones. State is `"unknown"` when derive_state itself fails.

**fixture library (packages/llama/tests/fixture_library.py)**: `library_show` + `replay_config` + `IDENT` moved out of test_replay.py (test_replay imports them under the old `_library_show`/`_config` names). `build_library(root, *, held_for_real=False)` writes `root/config.toml` (`root = "<root>"`, `[jerrybase] enabled = false`), the md cache, `gratefuldead-1973-06-10` (held, vetting + reusable briefing; synthetic `unresolved track titles` hold by default, the wrong-date hold with `held_for_real=True`) and `gratefuldead-1973-06-11` (clean, packaged via `package/manifest.json`, own-date vetting; also has a briefing.json, as a real packaged show would).

**scripts/replay_holds.py `run`**: `main(argv) -> int`, `run --out ARM [--held|--all|--slugs FILE] [--config P] [--scratch DIR]` (the three scopes are mutually exclusive). The identity check runs first, before the config is read: it prints `llama: <llama.__file__>` to stderr and exits 2 with `refusing to run: llama imports from <path>, not from this tree <tree>` unless `Path(llama.__file__).resolve()` is under `<tree>/packages/llama/src` (M2). Shows are enumerated by hand (`sorted(shows/.iterdir())`); for `--held`, `derive_state` runs inside a try and a show whose state can't be read is KEPT, so replay_show records it. `slfm = setlistfm_client(config)`. Logging is disabled to CRITICAL during the loop and restored in a `finally`. Per-show scratch `scratch/slug` is rmtree'd after each show, and the default `mkdtemp(prefix="replay-")` is removed at exit. A progress line goes out every `PROGRESS_EVERY=100` shows and a one-line outcome summary at the end, both on stderr. The arm has the Contracts keys `sha, config_fingerprint, setlistfm_configured, scope, generated_at (UTC iso), llama_file, root, shows` (sorted, `to_dict()` incl. `date`), written atomically (temp in the same dir + os.replace). `replay_show`/`setlistfm_client` are imported by name, so `rh.replay_show` is patchable. `compare` is not stubbed (Task 6).

## Additions beyond the brief (safety; please rule if unwanted)
- Refuses (exit 2) a `--scratch` overlapping the library root in either direction, and a `--out` at/inside the root. The latter is "writes exactly one file, never under the library".
- Refuses (exit 2) an explicit `--config` that does not exist: `load_config` silently falls back to defaults (root `~/.llama`) on a missing file.
- `--slugs`: blank lines ignored, duplicates collapsed, a slug with `/` or `.`/`..` refused (exit 2: `scratch/<slug>` is rmtree'd). A slug with no directory gets a row `state="missing"`, `outcome="unreplayable"`, `unreplayable="show directory missing"`.

## Deviations
- `--config` default: the brief says "`LLAMA_ROOT` env else `~/.llama` ... as `llama` does", but llama has no LLAMA_ROOT (grep: only the plan mentions it). I followed llama: `DEFAULT_ROOT / "config.toml"`, root from `config.root`.
- Logging is restored to the PREVIOUS disable level, not hard NOTSET. That is identical in practice and asserted in a test (`logging.root.manager.disable == NOTSET` after the run).
- Brief test `test_stored_briefing_flags_...` was appended verbatim. Brief's script tests are verbatim, plus 13 more.

## TDD evidence
- Carried fixes: 7 red first (5 slfm-malformed, diff new values, shows/ guard); code_identity tests were green on arrival (coverage tests for existing behaviour).
- replay_show: red on `ImportError: cannot import name 'replay_show'`, then one red after the implementation (`{"narration": "loud"}` is a readable object, so my test case was wrong; it was replaced by `{"exclude": 3}` and non-UTF-8 bytes).
- Script: red on `ModuleNotFoundError: replay_holds`, then green.
- Mutation spot-check (not required for Task 5; recipe followed: fresh rsync copy, PYTHONPATH shadow proven, private PYTHONPYCACHEPREFIX, prediction logged before the flip):

| mutant | predicted test | caught by |
|---|---|---|
| identity check against tree root instead of packages/llama/src | scripts::test_run_refuses_a_llama_from_a_worktree_nested_in_this_tree | that test |
| overrides pre-check disabled | test_replay::test_replay_show_unreadable_overrides_is_unreplayable + scripts::test_unreadable_overrides_marks_... | both (all 5 params) |
| compute_legs shows/ guard disabled | test_replay::test_compute_legs_refuses_a_scratch_inside_the_library_shows_dir | that test |
| script scratch-overlap guard disabled | scripts::test_run_refuses_a_scratch_overlapping_the_library[parent] | all 4 params |
| shipped_diff count-change `new` back to None | test_replay::test_shipped_diff_track_count_change_carries_the_new_values (+ reports_every_index) | both |

## Real-library smoke run
After the zero-writes test passed, at f39ad88:
`T=$(mktemp -d)` = /var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T/tmp.5Z3LLgf33N; `touch $T/marker`; `find ~/.llama -newer $T/marker | wc -l` = 0 beforehand;
`./.venv/bin/python scripts/replay_holds.py run --out $T/arm.json --scratch $T/scratch` (default config, held scope).
- Runtime **18.4 s** real (15:34:12-15:34:30 EDT), exit 0. The scratch dir was empty afterwards.
- 1073 held shows: still-held 538, needs-llm 492, needs-brief 43, **unreplayable 0**. Reproduces **581/581** of the shows that are not needs-LLM. needs_llm reasons: align_structure 487, stored alignment llm 326 (overlapping), no vetting.json 3, extract_setlist 2. slfm_miss 0, setlistfm_configured true. stored_brief_guard is non-null on 55 (matches the spec's 55 briefing-guard holds). sha f39ad88 (not dirty).
- **Library-unchanged check, NOT empty: 4 paths are newer than the marker**: `~/.llama`, `~/.llama/pacing-state.json` (15:34:59), `shows/darkstarorchestra-2004-12-04/` and its `provenance.json` (15:34:34). They are attributed to the operator's concurrent **`llama run resume 2026-10-18-dead-tribute-10`** (PIDs 24213/24226, started 15:28:45, still running, with a `claude -p /usage` pacing read at 15:35:25). The rewritten provenance.json carries `run: 2026-10-18-dead-tribute-10`, `processed_at: 2026-10-19T19:34:34Z`, and DSO 2004-12-04 is on that run's shortlist. Both writes post-date the harness's exit (15:34:30). The harness writes no provenance and no pacing state; its only library access is reads. So the run is attributable as zero-write, but the marker check could not be literally empty while a live run was writing. The arm itself is therefore not a clean baseline (the library changed during and right after it), which doesn't matter for a smoke run. Arm left at $T/arm.json.

## Self-review
- Protected constants: grep of the diff is empty.
- replay.py stays pure except `compute_legs`'s scratch writes; `replay_show` writes nothing itself.
- The read-only-root test is load-bearing both ways: any write under root raises PermissionError -> unreplayable (fails the outcome asserts), and `_tree_state` compares size+mtime_ns.
- `scripts` tests put `packages/llama/tests` on sys.path (per the brief); no module-name collisions, full suite green.

## Concerns / for the orchestrator
1. **needs-LLM is 492/1073 (46%)** of the held set on the real library, 487 of them `align_structure` (gather reaches the LLM realignment branch). That is ruling 5's exclusion, but it is much larger than "listed and counted" suggests, and it caps what Tier 1 can clear. Worth knowing before Checkpoint A, since the spec's prototype numbers may not have counted this.
2. Checkpoint A should run while no `llama get`/`run resume` is live, or the digest/mtime checks will see concurrent writes, as here.
3. `state="unknown"` / `"missing"` are new state values beyond the spec's held/packaged/delivered/clear list. Task 6's compare should tolerate them.

---

# Fix round 1 (orchestrator review, Important 1)

Commit: **3263f45** test(replay_holds): zero-writes check also on a writable root; tree state sees directories. Test-only change, in `scripts/test_replay_holds.py`.

## What changed
- `_tree_state` records every path under the root: a file as `("file", size, mtime_ns)`, and a directory as `("dir", mtime_ns)`, the root itself included. A created empty directory, or a file created and then deleted, now changes the snapshot (the parent directory's mtime moves).
- `test_run_writes_only_the_arm_and_empties_its_scratch` now snapshots the root before the run. This root is writable, unlike the read-only test's. It asserts `_tree_state(root) == before` after the run and also checks the outcomes are `{clears, clean}`, so the run genuinely replayed.
- New `test_tree_state_sees_an_empty_directory_and_a_deleted_file` pins the helper itself, with each case measured against its own fresh snapshot.
- The read-only-root test and the refusal tests use the stronger `_tree_state` unchanged.

## Covering tests
- `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q` gives 21 passed.
- Full suite: `./.venv/bin/python -m pytest -q` gives **3271 passed, 1 skipped, 8 deselected** (was 3270; +1 new test).

## Mutant proof
I followed the Global Constraints recipe: a fresh rsync copy under $TMPDIR, a PYTHONPATH shadow, and a private PYTHONPYCACHEPREFIX. The shadow was proven: `llama.__file__` = `.../mut-TLkN/tree/packages/llama/src/llama/__init__.py`. I wrote the prediction to the log before the flip.

| mutant | predicted test | caught by |
|---|---|---|
| in `compute_legs`, before the scratch recreate: `try: (ws.dir / "probe").write_text("x")` / `except OSError: pass` | scripts/test_replay_holds.py::test_run_writes_only_the_arm_and_empties_its_scratch | **that test only** (1 failed, 20 passed). Before this fix the reviewer measured 20 passed: it survived. |
