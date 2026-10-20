### Spec Compliance

- ✅ Spec compliant. Every Task 5 file has its hunk: replay.py (`replay_show`, `_selected`, carried fixes), scripts/replay_holds.py, scripts/test_replay_holds.py (all 7 brief tests verbatim, at diff 912-997), fixture_library.py (helper moved out of test_replay.py, which imports it at diff 432-434), and the test_replay.py append (brief test verbatim at diff 578-590). The arm header keys match Contracts exactly (replay_holds.py diff 829-838). `ShowReplay` fields follow Contracts: `stored_core_flags` drops the package and briefing families (diff 202-203); `reproduces` is sorted core == sorted(gather+vet) (diff 218); `stored_brief_guard` is None without briefing.json (diff 204-206); `selected_venue/city` are the stripped venue/coverage of the recording matching `stored.identifier` (diff 170-176). Stored fields are filled before `compute_legs`, so a needs-LLM show has them (test at diff 634-639).
- ✅ Orchestrator rulings applied:
  - M2: `is_relative_to(<tree>/packages/llama/src)` (diff 745-750), with a test for a nested worktree (diff 1002-1012).
  - M3: shows enumerated by hand (diff 769), and in held scope `derive_state` is inside a try with the show kept (diff 773-779). `replay_show` re-derives the state inside its own catch (diff 191-192) and is tested at diff 1110-1120.
  - `logging.disable` is undone in `finally` (diff 824-825), tested at diff 1123-1136.
  - Carried fixes: slfm never raises (diff 59-65; parity with `SetlistFMClient.setlist` checked at setlistfm.py:84-102); `code_identity` tests for `-dirty` and the version fallback (diff 512-535); count-change `new`/`new_source` values (diff 102-110); a scratch inside the library's `shows/` is refused (diff 140-142).
- ✅ Deviation on `LLAMA_ROOT` is correct. The name appears nowhere in packages/ or scripts/ (grep), and the default is `DEFAULT_ROOT` (config.py:10).
- ✅ Do-not-retune grep over the diff (every constant in Global Constraints, plus `is_family_artist`) finds nothing.
- ⚠️ Task 6 (compare) must tolerate `state` values beyond held/packaged/delivered/clear. `derive_state` already returns `vetted`, `selected` and others (test at diff 687), and this task adds `unknown` (diff 189) and `missing` (diff 812). A held-scope arm can also contain `state == "unknown"` rows, kept because their state could not be read (diff 777-779). Compare's 99% reproduction denominator has to decide how to count them.
- ⚠️ Not verified (told not to re-run on ~/.llama): the smoke-run figures (1073 held, 581/581 reproduce, 492 needs-LLM).

### Named risks, checked

**(1) Can the harness have written `~/.llama/pacing-state.json` or `shows/darkstarorchestra-2004-12-04/provenance.json`? No.**
- Pacing state: I imported scripts/replay_holds.py and listed `sys.modules`. The llama modules loaded are catalog, config, errors, ia_client, jerrybase, junk, ledger, locks, models, prompts, replay, setlist, setlistfm, siblings, songs, stages.{brief,gather,vet_research}, status, structure, titles, util and workspace. The only files that mention pacing-state are cli.py, pacing.py and pacing_state.py, and none of them is loaded.
- Provenance: the only `write_artifact(..., provenance)` is in pipeline.py:70, which is not loaded either.
- The harness's write sites:
  - the `compute_legs` scratch rmtree/mkdir/copyfile (replay.py ~303-307), guarded against the show dir and `shows/`;
  - the script's per-show rmtree of `scratch/slug` and the `mkdtemp`/rmtree;
  - the arm temp file plus `os.replace`, guarded against the library root (diff 790-793).
- `compute_gather` has no write calls; only `run_gather` writes (gather.py:1298-1300), and the replay does not call it. `Ledger.entries()` and `load_config` only read. `CacheOnlyIA` and `CacheOnlySetlistFM` only read. `code_identity` runs `git -C <llama pkg dir>`, which touches the repo, not the library.
- The implementer's attribution to the concurrent `llama run resume` is therefore consistent with the code.

**(2) Would the zero-writes test catch a write?** Yes for a write whose error propagates; no for a write whose error is swallowed. I measured both with the plan's mutation recipe: a fresh rsync copy, the `PYTHONPATH` shadow proven by `llama.__file__` printing a path inside the copy, a private `PYTHONPYCACHEPREFIX`, and the prediction logged before each run.

| mutant (in `compute_legs`, before the scratch recreate) | predicted | result |
|---|---|---|
| A: `(ws.dir / "probe").write_text("x")` | `test_run_replays_the_library_under_a_read_only_root` fails | caught by that test (outcome `unreplayable=2`); 1 failed, 19 passed |
| B: the same write inside `try: ... except OSError: pass` | survives the whole scripts test file | SURVIVED (20 passed) |

`_tree_state` does compare size and mtime_ns over every file under the fixture root (diff 897-899). But under a read-only root a swallowed write simply fails, so the comparison can never differ. On a live, writable `~/.llama`, mutant B would drop `probe` into every show directory. See Important 1.

**(3) The extra refusals and new states, judged against the Contracts:**
- Refusing a `--out` inside the root (diff 790-791) follows from "writes exactly one file" and "never writes to the library".
- Refusing a missing explicit `--config` (diff 786-787) is necessary: `load_config` silently returns `Config()`, rooted at `~/.llama`, when the file is missing (config.py:177-178). Without the refusal, a typo'd fixture config would replay the live library.
- Refusing an overlapping `--scratch` and a bad slug (diff 756-757, 792-793) is warranted, since `scratch/<slug>` is rmtree'd.
- None of these conflict with the Contracts. The `missing` state with `outcome="unreplayable"` fits the Contracts' outcome set. On the `unknown`/`missing` states, see ⚠️ above.

### Strengths
- `replay_show` fills the stored-side fields before the replay. Every failure lands in exactly one `unreplayable` text, with `reproduces` forced False (diff 230-231). The `_OverridesUnreadable` pre-check is tested over five bodies, including non-object JSON, a pydantic type error and non-UTF-8 bytes (diff 650-658).
- The identity check is read at call time and is tested in both directions, including the nested-worktree trap that ruling M2 exists for.
- Shows are enumerated exactly as `catalog.iter_shows` does (catalog.py:277-282: the same sorted dirs and the same delivered set) without its abort-on-one-bad-overrides read.
- The implementer ran its own mutation spot-check with predictions, although Task 5 does not require one.
- The arm is written atomically, and the scratch is cleaned per show in `finally`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. scripts/test_replay_holds.py:912-931 (diff): the zero-writes test cannot see a write whose error is swallowed. This is measured: mutant B above survives the whole file. It matters because swallowing write errors is an established pattern in this codebase: `SetlistFMClient.setlist` writes its cache inside a never-raise `try/except Exception` (setlistfm.py:84-102). Later Tier 1 tasks (8-19) change the gather path that `compute_legs` runs. So the acceptance test for the live-library strict surface is blind to the most plausible way a regression would write.
   - Fix (cheap): also snapshot the root on a writable-root run and compare it afterwards. For example, in `test_run_writes_only_the_arm_and_empties_its_scratch` (diff 1035-1043), take `before = _tree_state(root)` and assert it is unchanged after the run.
   - Also make `_tree_state` record directories (path → kind), so a created empty directory is visible.
   - This fix kills mutant B. The code is clean today; this is about the durable guard.

#### Minor (Nice to Have)
1. replay_holds.py `_read_slugs` (diff 753-758): a `--slugs` file that does not exist raises `FileNotFoundError` with a traceback and exit 1, not a clean `Refusal`/exit 2 like the other bad inputs.
2. replay_holds.py `_check_identity` (diff 741-750): only `llama` is identity-checked. `herder` could still import from another tree (the plan's mutation recipe shadows both). This is low risk while Tier 1 does not touch herder. If wanted, add the same check against `<tree>/packages/herder/src`.
3. replay_holds.py:803-804 (diff): the default `mkdtemp` scratch is not overlap-checked against the root. It is only a hazard if `TMPDIR` lies inside the library, which is negligible, but the explicit-scratch guard could be applied to both for uniformity.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The code meets the brief, the Contracts and every orchestrator ruling. Its write surface is confined to the scratch directory and the arm file, so the harness cannot have produced the smoke run's library changes. The one gap is in the acceptance test: by measurement it is blind to a write whose error is swallowed. Closing it takes a single writable-root `_tree_state` assertion.
