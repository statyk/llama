# final-fix handback: emcee profile reassignment, final-review fix wave

**Status:** DONE

## Commits (on 885dad4; each one has a green full suite)
- e76feb0 fix(emcee): _scan_broad error rows count toward the missing-moves guard (I1 + M6)
- fe69b04 fix(emcee): empty profile names are refused at config load and on write (M1)
- 945c912 fix(emcee): normalize_artist applies NFC after casefold and keeps combining marks (M2)
- 074e018 docs(emcee): run --help skip wording, station brief moves/rules, runbook retry (M3/M4/M5)

Final full suite: `./.venv/bin/python -m pytest -q` gives **3152 passed, 1 skipped, 8 deselected**. That is 15 more tests than the 3137 baseline.

## What changed

### I1: `_scan_broad` (packages/emcee/src/emcee/cli.py)
- **Arm 1.** When `raw_manifest(...)` returns a dict, the error row is now built from `identity(raw, config, moves)`. The row therefore carries:
  - the effective profile;
  - `profile_source`;
  - `performance_id`;
  - `voiced_source`;
  - `voiced_profile`;
  - `move_problem`.
- **Non-dict fallback.** Unreadable JSON, or a non-object top level, keeps today's fallback: `profile` and `delivered_profile` from `manifest_profile(raw)`, which is always None. It never calls `identity(None)`. A code comment there records the documented limit: a move-voiced package whose manifest is unreadable does not count toward the missing-moves.json guard.
- **Helpers.** I renamed `station._raw_manifest` to the public `raw_manifest`, because cli now imports it. I removed `station.raw_profile`: its only caller was the line I replaced, and nothing in the tests or docs references it.

### M6: `identity()` (packages/emcee/src/emcee/station.py)
- `identity()` now returns `"voiced": isinstance(_get(manifest, "dj_audio"), dict)`.
- `package_status` no longer passes `voiced=a.voiced`. Passing it as well would be a duplicate keyword, and the two values are identical on the success path: `assess` raises on any dj_audio that is neither None nor a dict.
- The suite shows no ready/pending change. Error rows are never in `to_voice`, so the plan classification is unaffected.

### M1: empty profile names
- `AssignConfig._check_artists` (config.py) raises `[assign.profiles.""]: profile names must be non-empty`.
- `moves.write_moves` runs `_validated(data, path)` before writing, so a refusal writes nothing.

### M2: `normalize_artist` (packages/emcee/src/emcee/artists.py)
- It now applies `unicodedata.normalize("NFC", name.casefold())`.
- The character filter also keeps characters whose `unicodedata.category(ch)` starts with "M".
- The docstring is updated.

### M3, M4, M5: wording fixes
- **M3.** The `run` docstring now says: "A pending package with missing track audio is skipped, whatever else is wrong with it". I reflowed the paragraph.
- **M4.** docs/station-brief.md adds: "...unless an emcee move (`emcee move`) or an `[assign.artists]` rule changes the profile the show is voiced as (recorded in the manifest as `dj_audio.profile`)".
- **M5.** docs/playout-incident-runbook.md now reads "until a later `emcee run` or `emcee voice <show>` succeeds".

## Tests added or changed
- **test_profile_readiness.py**
  - `test_a_missing_moves_file_with_move_voiced_packages_fails`: in the broken parametrizations, the move-voiced **m2 itself** is now malformed:
    - `_break_track` (a track with no `filename`) hits arm 2;
    - new `_break_schema` (`"schema_version": "3"`) hits arm 1, with the ids status-/run-scan-broad-arm1.
  - Those cases keep `"2 package(s)"` and now also assert the m2 details row.
  - The `_malformed` helper is still used by the moved-ready test.
  - New `test_a_structurally_wrong_manifest_error_row_carries_the_effective_profile[move|artist-rule]`. On an arm-1 error row it checks:
    - `status --json` profile, delivered_profile and profile_source equal (southern, funk, move/artist);
    - `voiced_by` is gregg;
    - `status --list` shows `southern (from funk)`.
  - New `test_an_unreadable_manifest_error_row_resolves_nothing`: unparseable JSON gives profile, delivered_profile and profile_source all None.
- **test_config.py**
  - `test_an_empty_profile_name_is_a_load_error`
  - `test_decomposed_and_precomposed_artist_keys_are_a_duplicate`
  - `import unicodedata` is at the top of the file.
- **test_moves.py**
  - `test_record_of_an_empty_profile_is_refused_and_writes_nothing[file-present|file-absent]`: present means the file is byte-identical afterwards; absent means it is not created.
  - `test_write_moves_refuses_what_the_reader_would_reject`
- **test_move_cmd.py**
  - `(["move", "ttb", ""], "[assign.profiles.] entry")` was added to `test_each_refusal_exits_1_and_leaves_the_file_alone` (both file-present and file-absent): exit 1, EmceeError, file untouched.
- **test_artists.py**
  - `test_decomposed_and_precomposed_spellings_meet`
  - `test_a_combining_mark_with_no_precomposed_form_stays_in_its_word`, with "İstanbul" giving "i\u0307stanbul" and "Ex\u0301ample Band" giving "ex\u0301ample band"

## I1 mutation proof (mandate 5)
- **Copies.** Scratch copies came from `git archive e76feb0 | tar -x`: `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut` (mutated) and `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/ctl` (control).
- **Run setup.** Everything ran from the empty cwd `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/empty` with:
  - `PYTHONDONTWRITEBYTECODE=1`;
  - a fresh `PYTHONPYCACHEPREFIX` per copy;
  - `PYTHONPATH=<copy>/packages/emcee/src:<copy>/packages/herder/src`;
  - `-p no:cacheprovider -c <copy>/pytest.ini --rootdir <copy>`.
- **Shadowing check.** `emcee.__file__` resolved inside each copy: mut printed `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut/packages/emcee/src/emcee/__init__.py`. `'MUTANT' in inspect.getsource(emcee.cli)` was True for mut and False for ctl.
- **Mutant.** It forces `voiced_source=None` on both error-row arms of `_scan_broad`:
  - arm 1: `ident["voiced_source"] = None`;
  - arm 2: `**{**identity(...), "voiced_source": None}`.
  The diff is in the log.

**Prediction, written to the log before the run:** exactly 4 failures, all in `test_a_missing_moves_file_with_move_voiced_packages_fails`, ids status-scan-broad, run-scan-broad, status-scan-broad-arm1 and run-scan-broad-arm1. Each fails on `"2 package(s)" in str(exc)` because the guard counts only m1. The control has 0 failures.

**Command** (shown for mut; ctl is the same with ctl substituted):
`cd /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/empty && PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/pyc-mut PYTHONPATH=/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut/packages/emcee/src:/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut/packages/herder/src <worktree>/.venv/bin/python -m pytest -q -p no:cacheprovider -c /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut/pytest.ini --rootdir /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/mut/packages/emcee/tests`

**Results:**
- **mut:** 4 failed, 910 passed. The 4 FAILED are exactly the predicted ids. Each fails at test_profile_readiness.py:222 because the message reads "...1 package(s) were voiced under a recorded move...".
- **ctl:** 914 passed, 0 failed.

**RED evidence for the arm-1 fix.** I ran the new tests against the pre-fix 885dad4 source. Prediction: the 2 arm-1 guard params and both effective-profile params fail, and the arm-2 params pass, since arm 2 was already correct and that test is a pin. Result: exactly those 4 failed (status-scan-broad-arm1, run-scan-broad-arm1, ...effective_profile[move], [artist-rule]), with 910 passed.

## RED evidence for M1 and M2 (new tests against the pre-fix source, scratch copies)
- **M1** (fe69b04's parent source, e76feb0). Predicted and observed: 4 failed, 132 passed. The failures are the config empty-name test, both record_move "" params, and the write_moves refusal test. The CLI `move ttb ""` case passes even pre-fix, because `target_problem` already refuses it; it is a pin.
- **M2** (fe69b04 source). Predicted and observed: 4 failed, 80 passed. The failures are the NFD/NFC artists test, both combining-mark params, and the config NFD/NFC duplicate test.

## Self-review and concerns
- The `write_moves` refusal reuses the reader's message ("<path> is unreadable or malformed (entry ...: \"profile\" must be a non-empty string or null); fix or restore it ..."). That wording reads oddly for a write, but it was the spec ("run the reader's own `_validated`"). The CLI never reaches it for `""`, because `target_problem` refuses first, so it is defence in depth only.
- Arm-1 rows now take the effective profile, so `run --profile/--assigned` filters and the summary treat them like arm-2 rows rather than as "manifest unreadable" skips. The reviewer intended this.
- **Not changed** (out of scope or deferred per the review): the unused `Path` import in test_status_profiles.py, and the other OK-TO-DEFER items.
- The log is /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/.superpowers/sdd/run1/final-fix/final-fix.log. The scratch copies are under /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/ (mut, ctl, red, red-m1, red-m2). The live worktree was never mutated.
