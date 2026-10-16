# Task 4 handback: readiness fifth leg; scan and status threading of config and moves

**Status:** DONE_WITH_CONCERNS (minor concerns only, listed at the end)
**Commit:** 9fe43c2 feat(emcee): profile check as a fifth readiness leg; scan threads config and moves (on top of c5760a0)

## What I implemented (per task-4-brief.md, code taken verbatim)
- `packages/emcee/src/emcee/station.py`: a new module docstring (five legs); `PackageStatus` gains `delivered_profile`, `profile_source`, `performance_id`, `voiced`, `voiced_profile`, `voiced_source`, `profile_reason`, `missing_tracks`, `clips`, `move_problem` and `tts`, all defaulted, and `profile` is now the effective profile. Also `_raw_manifest`; `raw_profile` now goes through it. New: frozen `Assessment` (with an `ok` property), `profile_change_reason`, `assess`, `readiness(pkg, config, moves)`, `identity`, `package_status`, `unsupported_status` and `scan(root, config, moves)`. Task 3's block is untouched, and so are the bodies of `manifest_profile` and `manifest_voiced_by`.
- `packages/emcee/src/emcee/cli.py`: imports `Moves` and `load_moves`. The station import is now `PackageStatus, identity, package_status, raw_profile, scan, unsupported_status`; `readiness`, `manifest_profile` and `manifest_voiced_by` were dropped as unused. `_scan_broad(root, config, moves)` builds its success rows with `package_status`, its unsupported rows with `unsupported_status`, and its error rows with `identity(...)` after a successful `manifest()` (or the raw profile otherwise). Also `_station_statuses(root, config, moves)` and the new `_load_station(config, root)`: it loads moves, scans, and then calls `require_present`. `run` uses `moves, statuses = _load_station(...)`; `status_cmd` uses `_moves, statuses = ...`.
- `packages/emcee/tests/helpers.py`: `build_package(..., artist="Grateful Dead")`, plus `set_dj_audio`, `write_moves_file`, `HOUSE_TTS`, `station_home`, `forbid_spend` and `notes_json`, all verbatim.
- New `packages/emcee/tests/test_profile_readiness.py`, verbatim from the brief (34 tests).
- Existing call sites updated as listed: test_station.py (every `scan`/`readiness`), test_status_cmd.py:370 `_scan_broad`, test_handshake.py:122 `scan(station, load_config(), no_moves())`, and test_voice_cmd.py (six `readiness(pkg, load_config(), no_moves())`). Imports were added for each.

The brief and the code from earlier tasks agreed everywhere I looked: `Moves.require_present` takes (slug, performance_id, voiced profile) tuples, as `_load_station` passes them.

## TDD evidence
RED: `./.venv/bin/python -m pytest packages/emcee/tests/test_profile_readiness.py -q` (helpers already in place) gave `33 failed, 1 passed`. The failure kinds were:
- 15 x `TypeError: readiness() takes 1 positional argument but 3 were given`
- 3 x `TypeError: scan() takes 1 positional argument but 3 were given`
- 9 x `assert 0 == 1` (the CLI did not fail on a bad or missing moves.json)
- 4 x `assert False` (the malformed-path `voiced`/exception checks)
- 1 x `assert 'would voice: ttb  southern  gregg' in "note: no package has profile 'southern'..."` (filters still used the delivered profile)

These were expected, since none of the new signatures or guards existed yet. The one pass is `test_a_missing_moves_file_with_no_move_voiced_package_is_no_moves`, which already held before the change.

GREEN (focused): `./.venv/bin/python -m pytest packages/emcee/tests/test_profile_readiness.py packages/emcee/tests/test_station.py packages/emcee/tests/test_status_cmd.py packages/emcee/tests/test_handshake.py packages/emcee/tests/test_voice_cmd.py -q` gave `102 passed in 1.36s`.
The new file under `-W error` gave `34 passed`, so it raises no warnings.

GREEN (full): `./.venv/bin/python -m pytest -q` gave `3057 passed, 1 skipped, 8 deselected, 26 warnings in 47.06s` (3023 at the previous HEAD plus 34). The 26 warnings already existed (os.fork DeprecationWarnings and similar) and none come from the new tests.
Log: .superpowers/sdd/run1/t4-impl/t4-impl.log

## Self-review
- I grepped for remaining callers of `scan`/`readiness`/`_scan_broad`/`_station_statuses` in emcee src, tests and scripts: all are updated. transmitter's `station.scan` is a different module and is unaffected.
- `json` is still used in cli.py (`status --json`), so its import stays.
- Strict surface 3 is covered by the parametrized legacy test: with no rules and no moves, a legacy-voiced package stays ready in 8 variants (llama profile dead, empty or None, or the `source` key missing; no moves file or an empty one).
- Strict surface 2 is covered on four commands (`run`, `run --dry-run`, `status`, `status --json`): a bad file fails before any work in both the truncated and wrong-shape cases. A missing file while packages were move-voiced also fails, on both the `scan` and `_scan_broad` paths.

## Concerns (minor)
1. **Stale `--profile` help text.** The `run` and `status` docstrings still say `--profile` selects packages "stamped with that llama profile", but selection now uses the effective profile. The brief did not ask me to change them, so I left them alone. A later task (CLI/docs) should update them.
2. **`moves` is unused in `run` until Task 5.** The brief intends this. A linter would flag it, but the repo has no ruff/flake8 config.
3. **Three manifest reads per package in `scan`.** `scan`'s probe, `package_status` and `assess` each call `pkg.manifest()`, and `Package` does not cache it. This is the brief's code verbatim and is correct, just redundant I/O over NFS-sized stations. Not changed.
