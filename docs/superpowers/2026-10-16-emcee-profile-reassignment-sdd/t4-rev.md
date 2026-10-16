### Spec Compliance

- ✅ **Spec compliant.** All 8 files in the brief's list have their hunks. The new code is the brief's text verbatim, with only the import pruning the brief itself permits.
  - `station.py`:
    - `PackageStatus` gains the 11 defaulted fields (diff 262-272).
    - `Assessment` with the `ok` property (diff 340-353).
    - `profile_change_reason` has the four spec §4 texts (diff 356-366).
    - Also `assess`, `readiness(pkg, config, moves)`, `identity`, `package_status`, `unsupported_status` and `scan(root, config, moves)` (diff 369-522).
  - `cli.py`:
    - `_scan_broad` takes `config, moves`, and its success rows come from `package_status`, as `scan`'s do (diff 123).
    - `_station_statuses` and `_load_station` load moves, scan, then call `require_present` (diff 144-164).
    - `run` and `status_cmd` call `_load_station` (diff 187, 210).
    - `readiness`, `manifest_profile` and `manifest_voiced_by` were dropped from the import as unused (diff 49-50).
  - The helpers and the call-site updates in test_station, test_status_cmd:370, test_handshake:122 and test_voice_cmd (6 sites) match the brief.
  - The reason texts match the global constraints verbatim, including `(none)`.
- ✅ **Strict surface 3** (nothing ready today goes pending). I traced it through Task 3's code:
  - `manifest_voiced_profile` reads a legacy block (no `profile` key) as `manifest_profile`.
  - With no rules and no moves, `effective_profile` returns `manifest_profile`, so the comparison at diff 399-400 is always equal.
  - Both sides go through `manifest_profile`, as the global constraint requires.
  - Pinned by an 8-way parametrized test (test_profile_readiness.py, diff 734-749).
- ✅ **Strict surface 2** (moves loaded first and loudly in run/status). `_load_station` is the first statement after config and station-root resolution in both commands.
  - Bad file: pinned on 4 commands × 2 kinds of bad file.
  - Missing file with move-voiced packages: pinned on both the `scan` and `_scan_broad` paths.
  - Mutation check (scratch `git archive` copy, `PYTHONPATH`-shadowed, emcee resolved inside the copy): removing `moves.require_present(...)` in `_load_station` is **CAUGHT** by the predicted test, `test_a_missing_moves_file_with_move_voiced_packages_fails[run]`.
- ⚠️ **Cannot verify from this diff** (owned by later tasks; the controller should confirm they land):
  1. `voice` does not load moves yet: no `scan`/`readiness` caller remains in emcee src besides `_station_statuses`. Spec §3 requires `voice` and `move` to load moves.
  2. `status --json` does not yet carry `delivered_profile`, `profile_source` or `tts` (spec §1, §4). The table does not show the `southern (from funk)` mark.
  3. `status` does not print the stale-move `note: N recorded move(s) match no package`.
  4. `move_problem` is computed but nothing turns it into an error row in `run` yet.
  5. **Intermediate state hazard.** Between Task 4 and Task 5, a real `emcee run` with an artist rule picks the TTB package by its effective profile (southern) but voices it under the delivered one (funk). It records no `profile`, so it reads as funk ≠ southern and is pending again, which means a re-voice on every run. The brief says this is intended and only the suite is run in between. Do not release or run against the real station before Task 5 merges.

### Strengths
- One `identity()` builds the manifest-only fields for both success rows and post-manifest error rows. This keeps the two scan paths from drifting on what the `require_present` guard sees, and that exact drift is the strict-surface-2 risk on `_scan_broad`.
- `unsupported_status` / `_raw_manifest` removed two copies of the unsupported-row logic. Both copies used to do an unguarded `json.loads(...).get(...)`, which would raise on a non-object v2 manifest. The new one is total (diff 459-466).
- The tests check real behavior through real files and the CLI, with no mocks of the unit under test.
  - `forbid_spend` plus `dj_audio is None` proves "before any work" on four commands.
  - The `_scan_broad` call counter, `broad == ([1] if broken else [])`, proves the guard ran on the fallback path under test, not just on the fast path.
- The effective-profile filter test (diff 916-931) covers `--profile` in both directions plus `--assigned`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **cli.py:`_scan_broad`'s post-manifest error rows: their `identity()` is unpinned, on a strict-surface-2 path** (diff 125, `**identity(manifest, config, moves)`).
   - The brief claims "The `scan-broad` cases … pin this". They pin only the success rows: the malformed package in `_malformed()` has no `dj_audio`.
   - Mutation check (same scratch setup as above):
     - Mutant: in that error row, force `voiced_source=None`.
     - Prediction: survives.
     - Result: SURVIVED, 831 passed across the emcee suite.
   - So a move-voiced package whose own manifest is structurally malformed (e.g. a track missing `filename`) could silently drop out of the missing-`moves.json` count, and nothing would catch it.
   - Fix: add one case to `test_a_missing_moves_file_with_move_voiced_packages_fails` where `m1` is move-voiced and also has a filename-less track.
   - The code is correct today, so this is test-gap severity only.
2. **cli.py `_scan_broad`'s first `except Exception` arm (diff 115-120).** A manifest that is valid JSON but makes `pkg.manifest()` raise (e.g. a non-object top level, or a string `schema_version`, which hits the `<` TypeError in package_io.py:49-50) gets an error row with no `voiced_source`, so the guard never counts it either.
   - `identity(_raw_manifest(pkg.manifest_path), config, moves)` is total and would close this.
   - Same narrow class as item 1. Real-world likelihood is very low.
3. **Error rows have an inconsistent `voiced` field.** `identity()` omits `voiced`, so a post-manifest error row carries `voiced_by="casey"` (say) but `voiced=False`.
   - Harmless today, since nothing reads `voiced` on error rows.
   - Tasks 5-7 classify on `voiced`, so either add `"voiced": isinstance(_get(manifest, "dj_audio"), dict)` to `identity` or document that `voiced` is unset on error rows.
4. **Redundant reads.** Per package, `scan` reads and parses the manifest 3 times (`scan`'s probe, `package_status`, `assess`) and runs `effective_profile` twice (`assess` and `identity`).
   - Correct, but it triples NFS reads over a station of 341 packages.
   - It also opens a small window where `identity` and `assess` see different manifest versions.
   - Possible fix: have `assess` take the parsed manifest, or have `package_status` reuse `a.effective`. This is the brief's code verbatim.
5. **Stale help text.** `cli.py:322` `--profile` help ("Only packages delivered for this llama profile") and the `run` docstring at `cli.py:349` ("stamped with that llama profile") now misdescribe the selection, which uses the effective profile. The implementer flagged this; make sure the CLI/docs task picks it up.
6. **`status --state bogus` ordering change.** With a bad `moves.json`, `emcee status --state bogus` now reports the moves error rather than `BadParameter`, because `_load_station` precedes the `--state` validation (`cli.py` diff 210-216). Strict-first is defensible, so this is only noted.

### Assessment

**Task quality:** Approved

**Reasoning:** The diff implements the brief verbatim. Both strict surfaces this task owns are pinned on their main paths: surface 3 by trace and an 8-way parametrized test, surface 2 by a mutation the predicted test caught. The remaining gaps are untested error-row corners of the `_scan_broad` fallback (one confirmed by a surviving mutant) plus later-task items, none of which make this task's behavior incorrect today.
