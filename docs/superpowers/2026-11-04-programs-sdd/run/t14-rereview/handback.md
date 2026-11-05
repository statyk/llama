### Finding Verdicts

- **T9-N1: the restore doc did copy-then-utime on the live file.** ADDRESSED. packages/emcee/CLAUDE.md, new section "Retitle hand restore" (diff +99..+176). It requires no emcee or llama process (`ps`) and no `.lma-station.lock`, or a `with station_lock(<station root>, command="hand restore")`. The snippet follows the same order as retitle.py:173-216 (`_replace`): a `.manifest.json.emcee-<hex>.tmp` in the package dir opened "xb", fchmod, write, flush, fsync, `os.utime(tmp)`, a re-read and compare of the live file, `os.replace`, then a re-check and re-apply of the mtime. It uses the real backup layout (`title-backups/<stamp>/<slug>.json` + `record.jsonl`) and the real record fields. It also checks that the backup's sha256 matches `before_sha256` before using it. Its encoding is `json.dumps(data, indent=2) + "\n"`, the same as retitle.py:48-49, and the title is set the way retitle.py:246 sets it (null for None).
- **T9-N2: the before-only outcomes, plus `title` in record.jsonl.** ADDRESSED.
  - Docs: the before-only cases (a), (b) and (c) are spelled out, and the snippet's branches implement them. Both failed put-back messages are mapped: "putting the original back failed" goes to (b), and "restoring its mtime failed" goes to (a), with the mtime re-applied. A record that predates the field raises KeyError at `before["title"]` before anything is written, and the doc says so.
  - Code: cli.py:1526-1536 (`_save_backup`) appends `"title": title` after the existing fields. The call site at cli.py:1598 passes `w.new`, and nothing else in the write path changed.
  - Test: test_retitle_cmd.py `test_backup_saved_before_each_write_with_sha` pins the values (including None) and the key order `[slug, before_sha256, mtime_ns, title]`. The fix report shows a RED run before the change and a GREEN run after it.
- **T13b: a stale lock file let cross pass vacuously.** ADDRESSED.
  - station_probe.py `cmd_cross` refuses with exit 2 when `os.path.lexists(path)` is true before the race. The message names the path, and the file is left untouched.
  - `acquired == 0` now exits 3 with a message naming the path and a possible stale file. This is checked after `double` and before `contended`.
  - Tests: `test_cross_refuses_to_start_over_an_existing_lock_file` and `test_cross_that_never_acquired_exits_3_naming_the_lock_file`.
  - The scripts/CLAUDE.md pass rule now reads "neither side exiting 1 or 2 and at least one exiting 0". That rule is sound: a side that exits 0 has contended, so the other side acquired at least once.
  - The only new import is `random` (stdlib). The fix report shows a py3.11 run with 17 passed.
- **T11a/T11i: the station_lock docstrings and emcee CLAUDE.md said every station write is an atomic rename.** ADDRESSED.
  - Both station_lock.py docstrings (emcee and llama, identical text) and emcee CLAUDE.md:37-45 now list the temp-plus-rename writers and name the two exceptions, with SIGTERM there acting as SIGKILL minus the stuck lock.
  - I checked the exceptions against the code. The overlay copy is llama cli.py:2667 `shutil.copytree(pkg, out, dirs_exist_ok=True)`. The replace path is cli.py:2536-2547: `.deliver-*` tmp, `out.rename(old)`, then `tmp.rename(out)`. The clear-mark claim matches station_mark.py:134 `os.replace`.
  - Docs only; no code changed.
- **T11g: "does not share this locking scheme".** ADDRESSED. packages/llama/CLAUDE.md:178 now reads "does not share this flock scheme".
- **T12b: the 118-col unmark docstring.** ADDRESSED. scripts/bulk_apply.py:1182-1183 is re-wrapped and the text is unchanged.

**The implementer's addition, cross pacing: judged sound.**
- `_race_loop(paced=True)` is passed only by `cmd_cross`. `_worker_main`, which `race` uses, still calls it with no `paced` argument, so `race` is unchanged.
- Pacing does not serialise the two sides. While one side holds the lock for 5 ms, the other retries after U(0, 5 ms) sleeps, so it makes on average about two create attempts inside every hold. Each `contended` count is one attempt that a broken O_EXCL would have turned into a `double`.
- It also adds free-file races near simultaneous creates, which the unpaced loop never exercised. In the unpaced loop the winner re-created at once, and the loser was locked out of every round (the implementer measured this in 3/3 runs).
- Check I ran: DROP_EXCL under paced two-sided cross. Three two-sided runs, n=50, `STATION_PROBE_TEST_DROP_EXCL=1`, run from a scratch dir against the live script, which was not modified. Results: `double 22/26`, `35/18`, `25/31`. A fourth run gave rc a=1, b=1, and no scratch files were left. Under cross, the DROP_EXCL path still detects doubles heavily.

### New Breakage in the Fix Diff

- **Minor:** scripts/test_station_probe.py has no test that pins paced cross detecting doubles. Only `race` is tested under DROP_EXCL (test_station_probe.py:27). I checked it by hand (above), but a future change to the pacing could make cross blind without turning anything red. A two-sided `cross` test under `STATION_PROBE_TEST_DROP_EXCL=1` that asserts at least one side has rc 1 and `double > 0` would close this. This does not block the fix round.
- **Minor:** the snippet in packages/emcee/CLAUDE.md swallows every OSError from `os.fchmod`. The writer (retitle.py:187-190) tolerates only `_FCHMOD_REFUSED`. This is harmless for a hand restore: the worst case is the server's default mode on the restored file.
- **Minor:** the snippet leaves its temp if the write or fsync raises (no try/unlink). The doc says this ("a killed run leaves at most a `.manifest.json.emcee-*.tmp`, which `emcee retitle --dry-run` lists"), so it is a known cost, not a defect.

None at Critical or Important.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. The cross-pacing addition preserves double detection, as measured above, and leaves `race` unchanged.
