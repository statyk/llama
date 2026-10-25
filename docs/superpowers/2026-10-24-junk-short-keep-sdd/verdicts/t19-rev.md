### Spec Compliance

- ✅ Spec compliant for spec 4.3 "`--apply`", "Routes for an `--apply` refusal", "Output", the process check, and 6(f)'s `--apply` items. I checked each one against the diff:
  - **Gates, in order, before the lock.** The order is snapshot, then version, then process. A shows-dir check runs first. Each gate raises `_Refused` and writes nothing (`scripts/rekey_overrides.py:1044-1058`).
    - The snapshot gate is `find_snapshot` followed by `verify_snapshot` (`:840-849`).
    - The version gate (`:823-837`) refuses an empty list as `no llama on PATH`, and refuses any low binary with `llama on PATH below 2.18.0: <path> <out>`.
    - `version_ok` (`:786-796`) compares numerically and refuses `0.1.0` and `0.0.0+unknown`.
    - The process gate reuses Task 18's `_process_gate`.
  - **Lock order.** `.rekey.lock` is taken non-blocking in an ExitStack (`:1062-1067`), and only then `file_lock(ws.lock)` per show (`:994`). The migration lock is outermost, as required.
  - **Up-front pass under the migration lock.** It runs `check_library` (`:1082`), then a coverage gate over `library_shows(root)` (`:1084-1088`, as carried), then the sha256 comparison with the snapshot for every legacy show (`:1089-1095`). Any refusal prints everything, prints `nothing written`, and exits 1 (`:1097-1103`).
  - **Per show, under the show lock.**
    - Both files are re-read once (`:995`) and compared with the snapshot's manifest and copy (`:856-872`).
    - `check_show` gets BOTH `overrides_bytes` and `show_bytes` (`:1000`), as carried.
    - `rekey_raw` runs on `json.loads(ov_bytes)`, with names from the same `show_bytes` (`:1007-1009`). This is a call, not a copy of the logic, as carried.
    - The result is dumped with `indent=2`, written durably (temp, F_FULLFSYNC, rename, then a dir fsync, `:922-934`), and recorded durably after each show (`:1014-1018`).
    - A refusal or an error stops the run (`:1113-1132`).
  - **Routes.** `first:` (only when a show classifies `filename`), then `then:`, then `repair:` with the slug pasted in (`:1022-1033`). This matches spec 4.3's wording and the brief's strings.
  - **Output and exit.** `rekeyed: <slug> (T titles, B breaks[, encore])`, `refused: <slug>: <reason> (<detail>)`, then the summary. Exit 1 on any gate failure or refusal.
  - **Constant.** `REKEY_MIN_VERSION = "2.18.0"` (`:68`), as carried.
  - **Husk test.** `test_lock_only_show_dir_is_not_a_show` now covers `--apply`: exit 0, the husk is untouched, and the husk is not named in the output.
  - **Brief tests.** Every test the brief names is present and asserts `tree_bytes` unchanged after each refusal.
  - **Global constraints.** I grepped the diff for every protected name (SHORT_FRACTION_OF_MEDIAN, MIN_MEDIAN_SAMPLE, MIN_PLAUSIBLE_SEC, _dedupe_duplicate_listings, FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, is_filler/_FILLER, TAUTOLOGICAL_TITLE_SOURCES, clean_tag_title, is_real_title, _TRACK_NUM_PREFIX, DURATION_TOLERANCE_S, purge_package_audio). No `+`/`-` line touches any of them; `FORMAT_BY_AUDIO` appears only in unchanged context.
- ⚠️ **Cannot verify from this diff: how Task 20 consumes the record.**
  - Task 19 writes `rekey-applied.json` as `{snapshot: <dir name>, updated_at, shows}`.
  - `_read_record` (`:941-962`) expects a successful `--restore` to rename the record away. Without that rename, a later `--apply` after a NEW snapshot refuses: "records snapshot X, not the newest".
  - The controller should confirm that Task 20 renames the record only when a restore succeeds. It should also replace `_hand_restore` (`scripts/test_rekey_overrides.py`, the `test_apply_after_a_restore_starts_a_fresh_record` stand-in) with the real `--restore`.

**Implementer calls beyond the brief.** I judged each one. None writes more than the spec allows.
1. **Coverage gate over every `library_shows` slug, legacy or not.** Correct and stricter than the spec. A show the snapshot does not cover means something ran between steps 4 and 6, and `--restore` would refuse that show later anyway. It uses `library_shows`, so husks are excluded.
2. **A separate `APPLY_REASONS`.** Correct. It keeps `REASONS` verbatim from the spec table. The `then:` line, which already names a NEW snapshot, still precedes each of these reasons.
3. **Round-trip check before writing** (`:900-919`). This is a sound extra guard on the strict surface:
   - The expected positions are rebuilt independently, with `legacy_int` and `resolve_positions` over the same names.
   - The check also requires that key order and every non-positional key are unchanged.
   - Mutant M11 is pinned by `test_a_rekey_that_does_not_round_trip_is_refused`.
   - It can only refuse, never write.
4. **Record and snapshot-name validation, plus re-finding the newest snapshot under the lock.** Correct.
   - After any migration, `--snapshot` refuses a library holding filename values. So a record naming a snapshot other than the newest really is unexplained, and refusing is right.
   - Re-running `find_snapshot` under the lock closes the window in which a newer snapshot could finish between the gate and the lock.
5. **Reconcile of an interrupted, unrecorded rewrite only on byte equality** (`:965-986`).
   - It writes only the record, never an `overrides.json`, and only after the up-front pass is clean (`:1104-1110`).
   - Its conditions are strict: the current file is filename-form, the snapshot copy matches its manifest sha and classifies `legacy`, and the current bytes equal `_expected_rewrite` of the snapshot's two files. Together these mean only a file `--apply` itself produced is recorded.
   - It does not touch the strict surface.
6. **A record is written only when a show is rewritten or reconciled.** Consistent with spec step 4 ("after each show").
7. **Gates stop at the first failure.** The spec only says "refuses unless all hold". Acceptable.

### Strengths
- **Strict surface (a) holds.** Every write happens only after:
  - the per-show sha256 equality with the snapshot (manifest and copy) on the exact bytes read under the show lock;
  - `check_show` on those same bytes;
  - a round-trip proof of the mapping.

  A show edited, created or re-gathered after the snapshot cannot be rewritten (`:994-1013`).
- **Durability is right.** The order is temp file with O_EXCL, F_FULLFSYNC, rename, then a dir F_FULLFSYNC, for both `overrides.json` and the record. A failed write unlinks its temp file (`:922-934`). The record is written after the rename, so a crash leaves either legacy bytes (re-keyed on the next run) or the exact migration output (reconciled).
- **The version gate is tight.** It is numeric and refuses suffixes and extra words (`:786-796`). I checked one named risk here: does a release binary's `--version` print a bare version? Yes. `cli.py:98-102` echoes `llama.__version__`, and `packaging/build.py:82-85` stamps `__version__ = "<ver>"` from the tag with the `v` stripped (`release.yml:61`). A release `2.18.0` passes, and a venv or dev `llama` on PATH refuses, as the spec intends.
- **The tests are behavioural and assert the tree byte-identical after every refusal.** `test_apply_rekeys_and_records` re-gathers each fixture show and proves the titles, sets and breaks land on the same files. Concurrency is simulated faithfully by wrapping `_rekey_show`, so the up-front checks really have passed when the edit lands.
- **The mutation evidence is credible.** There are 16 mutants, each with its red test named before the run, run with PYTHONPATH shadowing proven by `__file__`, plus a sentinel.
- **Test output is clean.** The full suite reports 26 warnings, the same as the Task 0 baseline (t1-rev and t15a handbacks record 26). I checked the implementer's log, `t19-impl.log:2507`: `5359 passed, 1 skipped, 8 deselected, 26 warnings`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The `first: --restore` line is untested on the up-front refusal path.**
   - `FIRST` is asserted only at `scripts/test_rekey_overrides.py:1271` and `:1291`, and both are under-lock stops.
   - Spec 4.3 says the line is printed when the library holds a show "rewritten in this run **or by an interrupted earlier one**". That is the up-front path after an interrupted run. It is exactly where the operator most needs `--restore` before reinstalling v2.17.0.
   - `test_apply_output_and_exit_codes` reaches that state (S1 migrated, S4 refused), but it asserts only `out.splitlines()[-2:]` (`:1431`).
   - A mutant that passes `migrated=False` from the up-front call would survive. I judged this by reading the code; I did not run it.
   - Fix: in that test, also assert `_refused_block(lines, S4, ...)[1] == FIRST.format(snap=...)`.
2. **The byte arguments to `check_show` are not pinned** (the implementer's own concern).
   - A spy on `rk.check_show` that asserts the call inside `_rekey_show` passes non-None `overrides_bytes` and `show_bytes` would pin the carried binding item cheaply.
   - Today, a mutant that drops them is unobservable without a race.
3. **`_interrupted` swallows every exception** (`scripts/rekey_overrides.py:983`, `except Exception: continue`).
   - A rewritten show whose snapshot copy cannot be read is left out of the record silently.
   - This writes no audio or overrides, so it is low impact. But the record is meant to name every rewritten show.
   - Consider echoing a `not recorded: <slug> (<error>)` line.
4. **`_summary` counts husks as "without positional keys"** (`:1038`, it uses `_show_dirs`), while the coverage gate excludes them through `library_shows`. This is cosmetic.
5. **Exceptions in the up-front pass are not turned into refusal lines.** An unexpected error in `_apply_locked` before the loop (for example an OSError from `check_library` or `_interrupted`'s record write) escapes as a traceback rather than an `error:` line (`:1079-1110`). It still writes nothing, so this is cosmetic.
6. **Two tests call `monkeypatch.undo()`** (`scripts/test_rekey_overrides.py:993`, `:1466`). This also reverts the autouse `DEFAULT_ROOT` patch. It is harmless today, because both tests pass `--config` or never reach `main`, but it is a hermeticity trap for later edits. Prefer re-patching only `llama_versions`.

### Assessment

**Task quality:** Approved

**Reasoning:** Every write is gated on byte-equality with the verified snapshot, re-checked under the show lock on the exact bytes read, plus a round-trip proof of the mapping. Every refusal writes nothing, and every carried binding item is met. The remaining gaps are test-coverage and cosmetic Minors, none of which can place a title, break or encore on the wrong file.
