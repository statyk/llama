# t8-impl handback: title backfill plan + raw single-field writer, procs

Status: DONE
Commit: 25a10201 emcee: title backfill plan and raw single-field writer

## Implemented
- `packages/emcee/src/emcee/retitle.py`: `encode`, `TitleWrite`, `RetitlePlan`, `TitleWriteFailed(EmceeError)`,
  `plan_retitle(station_root, config)`, `write_title(pkg_dir, *, expect, title)`, `_unchanged_except_title(before, after, title)`.
  - Plan follows the brief's rule order exactly. It covers non-dot dirs with manifest.json, sorted; a missing root gives an empty plan.
    The refusal reasons are: `cannot read manifest.json (<err>)`, `manifest.json is not valid JSON` (also for non-UTF-8),
    `manifest.json is not a JSON object`, `unsupported (v<N>; re-deliver from llama)` (also for a missing/non-int/bool schema_version),
    `dj_audio is not an object` and `not in emcee's encoding`. `awaiting` holds slugs.
  - The writer follows the brief's order (stat, build, `xb` temp `.manifest.json.emcee-<16hex>.tmp`, write/flush/fsync/close, utime on the closed temp,
    re-read==expect else unlink+None, os.replace, mtime re-check/re-apply once, verify). Steps 3-7 live in one helper, `_swap(path, payload, st, *, current)`,
    which the put-back reuses (the put-back also re-checks that the file holds exactly `new` right before its own rename). Any exception before the
    rename unlinks the temp. Under os._exit only a stray temp can remain.
- `packages/emcee/src/emcee/procs.py`: a full port of campaign_gate's `_unquote/_shell_string/_simple_commands/_runs_tool` + `tool_processes`
  as `tool_lines(ps_lines, tools, *, self_pid)` (multi-tool). A scripts/*.py matches for both tools. There is no self_script parameter (not in the interface).
  `other_tool_processes(tools=("emcee","llama"))` runs `ps -axo pid=,ppid=,command=`.
- Carried minor: CLAUDE.md:129 and models.py:76-77 now say "the title backfill (emcee retitle)".

## Choices beyond the brief (for review)
1. Verify step 8 also requires the re-read bytes == `new`, in addition to `_unchanged_except_title`. This guarantees that the returned bytes are what is on
   disk (Task 9's put_back sha rule). Same-content-different-bytes counts as a foreign write: "left as the other writer wrote it".
2. `_unchanged_except_title` compares values by `json.dumps(sort_keys=True)` and checks key order, so 1 vs 1.0 vs True are not "equal".
3. `write_title` raises ValueError (nothing written) if `expect` is not in emcee's encoding or has no dict dj_audio. This is a caller-contract guard
   (the plan already refuses such files).
4. A manifest gone at the step-5 re-read means skipped (None). Gone after the rename means TitleWriteFailed "left as the other writer wrote it".

## Tests / TDD
- RED: `./.venv/bin/pytest packages/emcee/tests/test_retitle_writer.py packages/emcee/tests/test_procs.py -q` gave
  `ImportError: cannot import name 'procs' from 'emcee'`, 2 collection errors (expected: modules absent).
- GREEN: same command, 21 passed (18 retitle + 3 procs). All 16 tests in the brief are present. Also added: missing root, file gone before rename,
  encoding guard on write, strictness of `_unchanged_except_title`, other_tool_processes reading ps.
- `./.venv/bin/pytest packages/emcee -q`: 1254 passed, 1 deselected.
- Full suite `./.venv/bin/pytest -q`, background, teed: 6747 passed, 1 skipped, 8 deselected, 26 warnings, rc 0.
  (The warnings include a multiprocessing fork DeprecationWarning that is not from these files.)
- Mutation check (scratch copy, PYTHONPATH shadow proven with a sentinel that failed 15/18; no bytecode cache; predictions named first).
  Each of the 9 mutants was caught by its predicted test:
  utime-on-temp removed, encoding refusal off, pre-rename re-read off, mtime re-apply off, awaiting check off, put-back skipped,
  fsync removed, schema gate off, absent-title-as-0.

## Self-review
- No other key is touched: the title is set on the dict parsed from `expect`, and encode() is byte-equal to `expect` except the title line (test checks the byte splice).
- The station lock is not taken (library code). emcee imports no llama (test_no_llama_imports passes).
- Concern (minor): `retitle` imports `emcee.process` for `assignment_for` (as the brief specifies). That pulls in a heavy module at import, but it is harmless.

## Fix round 1 (Ruling R8; review minors 1, 2, 5)
Commit: 97e5febf emcee: retitle writer reports every OSError and keeps the manifest's mode

Changes (packages/emcee/src/emcee/retitle.py):
1. `_swap` now opens the temp (`"xb"`) BEFORE its cleanup try. If the open fails (e.g. FileExistsError on a collision), it raises without unlinking anything.
2. OSErrors are classified. `_swap` raises internal `_BeforeRename` and `_AfterRename` errors, and `write_title` maps them as follows:
   - manifest gone at the entry stat, or at the re-read before the rename → None (skipped; this was already the case at the re-read);
   - any other OSError before the rename (entry stat, open, fchmod/write/fsync, temp utime, re-read, replace) → TitleWriteFailed "...; the file is unchanged", with the temp unlinked;
   - stat/utime failing after the rename → TitleWriteFailed "...; manifest.json holds this write's bytes, its mtime unknown";
   - the verify read failing with a non-FNF error → TitleWriteFailed "...; what it holds is unknown";
   - put-back failing before its rename → "...putting the original back failed (...); it holds this write's bytes";
   - put-back failing after its rename → "...the original was put back, but restoring its mtime failed (...)".
   The ValueError contract check on `expect` now runs before the stat. It still writes nothing.
3. `os.fchmod(fd, stat.S_IMODE(st.st_mode))` runs on the open temp before the write and fsync, on both the write and the put-back path.

New tests (test_retitle_writer.py):
- test_write_temp_collision_never_deletes_the_other_file
- test_write_on_a_manifest_gone_before_the_first_stat_is_skipped
- test_write_oserrors_before_the_rename_leave_the_file_unchanged (entry stat, temp utime, fsync, replace, re-read)
- test_write_oserrors_after_the_rename_say_what_the_file_holds (mtime re-apply, stat after the rename, verify read)
- test_write_keeps_the_original_mode_under_another_umask (0o640 under umask 0o002; the put-back keeps 0o600)

Results:
- `./.venv/bin/pytest packages/emcee/tests/test_retitle_writer.py -q`: 23 passed.
- `./.venv/bin/pytest packages/emcee -q`: 1259 passed, 1 deselected.
- Mutation check (scratch copy, sentinel 20/23 failed, predictions named first). All 6 mutants were caught by the predicted test:
  fchmod removed, unlink on a failed open, entry-FNF→None removed, `_AfterRename` wrapping disabled, `_BeforeRename` mapping disabled, verify-read OSError mapping disabled.
