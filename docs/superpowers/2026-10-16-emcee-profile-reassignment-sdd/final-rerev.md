# final-rerev: scoped re-review of the final-review fix wave (885dad4..074e018)

### Finding Verdicts

- **I1: a move-voiced package that becomes a `_scan_broad` error row drops out of the missing-moves.json guard.** ADDRESSED.
  - Arm 1 (cli.py:196-213): `raw_manifest()` is taken, and when it is a dict the row is `identity(raw, config, moves)`. So the row carries `voiced_source`, `performance_id`, the effective profile, `profile_source` and `move_problem`. Non-dict raw falls back to `manifest_profile(raw)` only and never calls `identity(None)`. The documented limit is in a comment at cli.py:204-209.
  - Totality check: I probed `identity` with 11 adversarial dicts (source as a string, list or dict performance_id, artist 5 or "", dj_audio as a string or list, non-string profile, profile_source or tts). None raised. That matters because a raise inside the `except` arm would abort the whole broad scan.
  - The guard (cli.py:239) counts `s.voiced_source == "move"`, so a structurally wrong JSON manifest with raw `dj_audio.profile_source == "move"` now counts. Unreadable JSON stays the documented limit, pinned by `test_an_unreadable_manifest_error_row_resolves_nothing` (test_profile_readiness.py:675).
  - Arm 2 (cli.py:216-218) was unchanged and is now pinned: m2 itself is the broken package (test_profile_readiness.py:609-610), and the `"2 package(s)"` and m2 details-row asserts are at :624/:626.
  - **Mutant check (scratch copies via `git archive 074e018`, empty cwd, PYTHONPATH shadowing, per-copy pycache, `MUTANT` in `inspect.getsource` = True).** I flipped each arm on its own and wrote the prediction to the log first:
    - arm 1 only (`ident["voiced_source"] = None`): predicted and observed exactly `[status-scan-broad-arm1]` and `[run-scan-broad-arm1]` failing, 37 passed;
    - arm 2 only (`{**identity(...), "voiced_source": None}`): predicted and observed exactly `[status-scan-broad]` and `[run-scan-broad]` failing, 37 passed.
    - The surviving mutant is now caught, on each arm independently.
  - I1(b)'s effective-profile cell is pinned by `test_a_structurally_wrong_manifest_error_row_carries_the_effective_profile[move|artist-rule]` (:650-672: json profile, delivered_profile, profile_source, voiced_by, and `--list` showing "southern (from funk)").
- **M1: empty profile names.** ADDRESSED.
  - config.py:181-182 rejects `""` in `[assign.profiles]`. Rules must target an existing `profiles` key (config.py:194), so a rule cannot reach `""` either.
  - moves.py:146-147 runs the reader's own `_validated` before `atomic_write_bytes`, so a refusal writes nothing. This covers both `record_move` (:163) and `clear_move` (:186), the only callers. `moves_path` is written nowhere else in src (grep).
  - The `json.dumps` default `ensure_ascii` output always re-parses, so a validated dict cannot produce a file the reader rejects.
  - Tests: test_config.py:473, test_moves.py:530-549 (byte-identical, and not created when absent), test_move_cmd.py:504.
- **M2: NFC in `normalize_artist`.** ADDRESSED.
  - artists.py:113 applies NFC after casefold; :119-120 keeps category-M characters.
  - Probe: NFC and NFD "Béla Fleck" both give "béla fleck"; "İstanbul" gives "i̇stanbul" as one word.
  - Tests: test_artists.py:405-417 and test_config.py:458 (the duplicate-key error).
- **M3: `run --help` skip wording.** ADDRESSED. cli.py:461-463 now reads "A pending package with missing track audio is skipped, whatever else is wrong with it". That matches the code: the `missing_tracks` skip comes before any other pending reason.
- **M4: station-brief presenter rule.** ADDRESSED. docs/station-brief.md:78-82 adds the move/`[assign.artists]` exception, recorded as `dj_audio.profile`. That matches `manifest_voiced_profile`.
- **M5: runbook retry wording.** ADDRESSED. docs/playout-incident-runbook.md:251-252 now reads "until a later `emcee run` or `emcee voice <show>` succeeds". This is correct: a failed re-voice leaves the dj blocks cleared, so `run` sweeps the package as pending.
- **M6: `identity()` omits `voiced`.** ADDRESSED.
  - station.py:281 now sets `voiced`, and `package_status` (:290-295) no longer passes `voiced=a.voiced`.
  - The two values are equal on the success path. `assess` calls `.get` on any non-None `dj_audio`, so a non-dict raises and the package becomes an arm-2 error row. That leaves only dict or None reaching `package_status`.

**Implementer's behaviour change (arm-1 rows filtered by effective profile).** Judged safe.
- **Strict surface 1 (spend).** An error row hits `continue` at cli.py:491-496 before `to_voice.append`, whether it is filtered in or out. No path from an error row reaches the plan or `_process_one`.
- **Effect on exit codes.** The only change is which `--profile/--assigned` selection prints the row's `error:` line and exits 1. Before, it was the raw delivered profile; now it is the effective profile, the same as arm-2 rows. The "manifest unreadable" note now counts only rows whose effective profile is None.
- **Strict surface 3 (ready→pending).** The state still comes only from `assess`. The fix touched `PackageStatus` fields only on error rows, plus `voiced`, which is shown to be identical. The only consumer of `PackageStatus.voiced` is `_echo_plan`'s new/re-voice/repair labels (cli.py:387-392). So no untouched package changes state.
- **Stale callers.** A grep for `raw_profile`/`_raw_manifest` over *.py and *.md (excluding .superpowers) finds hits only in the historical plan doc (docs/superpowers/plans/2026-10-16-emcee-profile-reassignment.md). There is no code or test caller. `raw_manifest` is used at cli.py:197 and station.py:298.

**Focused tests:** `./.venv/bin/python -m pytest` over test_profile_readiness, test_moves, test_move_cmd, test_artists and test_config gave **194 passed**. `emcee.__file__` resolves inside the worktree.

### New Breakage in the Fix Diff

- **Minor: the `write_moves` refusal message reads like a read failure** (moves.py:147 via `_malformed`, moves.py:40-44). The message is "<path> is unreadable or malformed (...); fix or restore it ...". It is raised before any write, while the file on disk is intact. The CLI cannot reach it, because `target_problem` refuses `""` first. Only a future programmatic caller would see the misleading text, and the implementer flagged it. Non-blocking.

Otherwise none.

### Out-of-Scope Observations

- **An unsupported package can still drop out of the guard.** `unsupported_status` (station.py:297-304) carries no `voiced_source`, so a package with an int `schema_version < 3` and a recorded `dj_audio.profile_source == "move"` does not count toward the guard. This happens only if a voiced v3 manifest is hand-downgraded or re-delivered by an old llama; `--replace-voiced` wipes `dj_audio` anyway. A string `"3"` goes to arm 1 and is covered. Non-blocking; ledger it for the final review.

### Verdict

**Fix round: all findings addressed, no new Critical/Important breakage.** I1 and M1-M6 are closed. Each `_scan_broad` arm's `voiced_source` mutant is now caught independently. Log: /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/.superpowers/sdd/run1/final-rerev/final-rerev.log. Scratch copies: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/rerev/ (the live worktree was never mutated).
