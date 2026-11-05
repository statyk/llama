# t14-fix: final-review fix wave (ruling R16)

Status: DONE_WITH_CONCERNS (one concern: T13b needed a pacing change to cross's race loop, see below)

Commits (on programs-lineup, from 33198e55):
- b8cecddf emcee: retitle records the target title on each backup's before line
- ac65114f scripts: station_probe cross refuses a pre-existing lock file and exits 3 when it never acquired
- 434c2637 docs: retitle hand-restore runbook, station-write atomicity exceptions, probe pass rule

## T9-N2 (MUST-FIX): code part
- packages/emcee/src/emcee/cli.py:1526-1536 `_save_backup(run_dir, slug, raw, mtime_ns, title)`. The before line is now `{"slug", "before_sha256", "mtime_ns", "title"}`: the existing fields keep their order and `title` is appended. It holds `w.new`, which is null for a profile with no title. Call site: cli.py:1598 `_save_backup(run_dir, w.slug, w.raw, mtime_ns, w.new)`. Nothing else in the write path changed.
- Test: packages/emcee/tests/test_retitle_cmd.py `test_backup_saved_before_each_write_with_sha` now expects `title` ("Dead Hour", "Dead Hour", None) and pins the key order `["slug","before_sha256","mtime_ns","title"]`. The three `_save_backup` wrappers in the tests now pass through `*rest`.
- RED: `./.venv/bin/pytest packages/emcee/tests/test_retitle_cmd.py -q -k backup` gave `1 failed, 4 passed` (`At index 0 diff: {... 'mtime_ns': 1700000000123456789} != {... 'title': 'Dead Hour'}`). This was expected: the field did not exist yet.
- GREEN: `./.venv/bin/pytest packages/emcee/tests/test_retitle_cmd.py packages/emcee/tests/test_retitle_writer.py -q` gave `59 passed`.

## T9-N1 + T9-N2 (MUST-FIX): docs
- packages/emcee/CLAUDE.md: the inline "Hand restore" text in the retitle bullet now points to a new `## Retitle hand restore` section (about :156-233, just before `## Architecture`). The record description at :137 now lists `title`.
- The section covers:
  - The writer's order: a temp file in the package dir, flush, fsync, `os.utime` from the record's `mtime_ns`, `os.replace`, then re-check and re-apply the mtime. It also says why `cp` is wrong.
  - When to run it: only with no emcee or llama process running (ps also covers the lock-ignoring backfill scripts and the campaign llama) and no `.lma-station.lock`, or inside `station_lock(<station root>, command="hand restore")` from emcee's venv.
  - The outcomes. For an after line: restore only if the file's sha256 equals `after_sha256`. For a before-only slug: (a) sha256 equals `before_sha256`, so it is the original and there is nothing to do, though the mtime is re-applied if it is off; (b) the bytes equal the backup with only `dj_audio.title` set to the record's `title`, in emcee's encoding, so it is this run's unrecorded write and is restored; (c) anything else is a foreign write and is left alone.
  - The failed put-back cases: "putting the original back failed" is (b), and "restoring its mtime failed" is (a).
  - Old records with no `title` key: the snippet stops with a KeyError and writes nothing.
- The snippet is pasteable stdlib Python, 37 lines, and Python 3.11 parses it. It applies these rules, uses the `.manifest.json.emcee-<hex>.tmp` temp name (so the next dry run's `stray temp:` lists a leftover), keeps the permission bits with fchmod (an SMB refusal is tolerated), and re-reads the file just before the rename.
- I checked it against the real layout: `title-backups/<stamp>/<slug>.json` plus `record.jsonl`, produced by a real `emcee retitle --yes` through CliRunner. The scratch test (outside the repo) extracts the snippet from the CLAUDE.md fence and covers four cases:
  - after-line restore: bytes and mtime back to the original, no temp left, and a second run says "original";
  - case (b): the after line was dropped, and the file is restored;
  - case (c): a foreign title is left byte-identical;
  - case (a) with a fresh mtime: the mtime is re-applied.
  - Result: `4 passed`.

## T13b (SHOULD-FIX): station_probe cross
- scripts/station_probe.py `cmd_cross`:
  - It refuses before racing when `.lock-race-<tag>` already exists. The message is `refusing: the lock file <path> already exists before the start (...)`, exit 2, and the file is left untouched.
  - After the race, `acquired == 0` exits 3: `this side never acquired the lock file <path>, so it proves nothing: a stale lock file may be present ...`. This is checked after `double`, before `contended == 0`.
  - The module docstring is updated.
- **Concern (scope):** I measured that the old unpaced loop could never satisfy the new rule. Three of three real two-sided runs gave the loser `acquired 0 contended 50` (exit 0 before this change) and the winner `contended 0` (exit 3), because the loser spun through all 50 rounds during the winner's first 5 ms hold. With acquired==0 exiting 3, every real run would have failed, the existing two-sided test included.
  - So `_race_loop` gained `paced=False`. Only cross passes True. It sleeps `random.uniform(0, HOLD_SECONDS)` after a refused create and `uniform(0, 2*HOLD_SECONDS)` after a release. `race` is unchanged.
  - Measured: 20 of 20 local two-sided runs exited 0 on both sides, each side acquiring 15-28 of 50.
  - It also means the old probe never actually tested repeated contended creates, only round 1. Revert or adjust if the controller prefers another remedy.
  - Go-live note: over SMB/NFS the per-op latency is larger than the pause, which should only increase interleaving. Untested cross-host.
- Tests in scripts/test_station_probe.py:
  - `test_cross_refuses_to_start_over_an_existing_lock_file` (exit 2, path named, empty stdout, stale file unchanged);
  - `test_cross_that_never_acquired_exits_3_naming_the_lock_file` (the lock appears after the start check, in-process: rc 3, `acquired 0 contended 5`, message names the path and "stale", the file is left);
  - `test_cross_both_sides_acquire_and_contend` (both sides exit 0, neither has acquired 0 or contended 0).
- RED: `./.venv/bin/pytest scripts/test_station_probe.py -q` gave `3 failed, 14 passed`. The reasons: rc 0 with `acquired 0 contended 5` (refusal and exit 3 both missing), and `[0, 3] == [0, 0]` for the two-sided test (unpaced).
- GREEN: the same command gave `17 passed`, three runs in a row.
- py3.11: `PYTHONDONTWRITEBYTECODE=1 /tmp/programs-py311/bin/python -m pytest scripts/test_station_probe.py -q -p no:cacheprovider` gave `17 passed`. The probe is still stdlib-only (adds `random`), and the test file is still stdlib plus pytest.
- scripts/CLAUDE.md (station_probe bullet): describes the refusal (exit 2), the pacing, and the new exit-3 cases. Pass rule: a side's 0 means it both acquired and was refused with `double 0`. A go-live pass is neither side exiting 1 or 2 and at least one exiting 0 (normally both).

## T11a/T11i (SHOULD-FIX, docs only)
- packages/emcee/src/emcee/station_lock.py and packages/llama/src/llama/station_lock.py module docstrings (about :20-33, identical text):
  - The temp-plus-rename writes are named: emcee's manifest and clips, retitle, clear-mark, and bulk_apply mark and unmark.
  - The two exceptions are named, with SIGTERM there behaving like SIGKILL minus the stuck lock. The first is deliver's overlay `shutil.copytree(..., dirs_exist_ok=True)` into the live package, which can leave a truncated manifest or audio. The second is the replace path's two renames: an exit between them leaves no package, only `.<slug>.old-*`/`.<slug>.deliver-*`.
- packages/emcee/CLAUDE.md:43-50 carries the same correction.
- No code changed. I verified it against llama cli.py:2528-2549 and :2667.

## T11g (SHOULD-FIX)
- packages/llama/CLAUDE.md:178: "**`emcee` does not share this flock scheme**".

## T12b (SHOULD-FIX)
- scripts/bulk_apply.py:1182-1183: the unmark docstring line is re-wrapped. The only lines in the file over 100 columns now are the pre-existing :1778 and :1983 (T12c, LEAVE).

## Suites
- `./.venv/bin/pytest -q`, run on the code state before the code commits: 6889 passed, 1 skipped, 8 deselected, 26 warnings (the baseline).
- The same command on the final state: 6889 passed, 1 skipped, 26 warnings.
- `cd antenna && npm test`: 545 passed.
- Nothing under packages/transmitter changed, so the transmitter py3.11 run was not needed.
- Not in scope and untouched: T4b and every LEAVE or NOT-OURS item.

## Self-review
- The record change adds a field without reordering. `write_title` and the rest of the write path are untouched.
- The snippet was checked against the real writer's output, not by reading.
- The pacing change is flagged above as the one step beyond the literal brief.
