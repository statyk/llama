# Task 16 fix round 1: re-review (928b784b..c225ca33)

## Finding 1, unmounted or unconfigured station listed as unvoiced: ADDRESSED
- scripts/bulk_apply.py:1367-1371: `cmd_lists` now refuses `no delivery_path in config` and `station root X is not mounted or not a directory` (GateRefused, exit 2). The check sits at the top of the function, before the pin, the `--out` check, the arm read and `select_wave`. So it covers every path that reads voicing: the list write, `--counts` (1404) and `--famous` (1423, which only runs after the list write). The wording matches `cmd_mark` (1136-1139).
- Flaky mount: `Path.is_dir()` on Python 3.14.7 (the venv) is `os.path.isdir`, which turns every OSError into False. EIO, ENOTCONN or ETIMEDOUT on the root therefore refuses and cannot pass. Per show, `_voiced` goes through `_station_copy_problem` (796-809). There only ENOENT counts as "no station copy"; any other stat error is reported in `problems` and the show is dropped from the list (`voiced is None`, 1402). A mount that flaps mid-run therefore does not turn a show into "unvoiced" unless the error is ENOENT.
- Test: scripts/test_bulk_apply_lists.py `test_lists_refuse_a_missing_station_root_or_delivery_path`. It checks the station root missing for both the list (exit 2, no file, message) and `--counts` (exit 2, empty stdout), and the same for `delivery_path` unset. I verified it with a mutant in a scratch copy (git archive c225ca33; PYTHONPATH shadowing; llama.__file__ and bulk_apply.__file__ proven inside the copy; PYTHONDONTWRITEBYTECODE=1). With the is_dir check removed, the predicted assertion went red: `assert 0 == 2` on the first `lists --out`.

## Finding 2, famous packet test never tested the after side: ADDRESSED
- scripts/test_bulk_apply_lists.py `test_famous_shows_go_to_a_packet`: the test now gives the famous arm row titles `["Song 1","Renamed"]`, sets `["1","2"]` and segues `[False,True]`. It asserts that line 1 (unchanged) is not starred, that line 2 is starred, and the exact substrings `set 1->2`, `title Song 2->Renamed` and `segue -->>`.
- The implementer's `_row_side -> []` mutant goes red on `assert not one.startswith("*")`. I also ran my own mutant in the scratch copy: `_famous_packet` rendering the stored side on both sides. It went red as predicted on `assert two.startswith("*")`, with output `'    2  set 1->1  title Song 2->Song 2  segue -->-'`.
- The live worktree ran `scripts/test_bulk_apply_lists.py`: 12 passed.

## New breakage in the fix diff
None (no Critical, no Important, no Minor).

## Deferred minors (out of scope)
- A mount point that stays behind as an empty local directory when the share is unmounted (a Linux-style `/mnt/x`, or a stale `/Volumes/x`) passes `is_dir()`. Every show then reads ENOENT and counts as "no station copy", i.e. unvoiced. `cmd_mark` has the same gap, so the fix matches the finding's "as mark does" bar. A future fix would be a sentinel or non-empty check on the station root, shared by mark, lists and wave-check.
- `cmd_wave_check` (1435) also checks `os.access(R_OK)`; lists and mark do not. This has no practical effect: a station root that can be traversed but not read still stats each child correctly, and one that cannot be traversed gives EACCES per show, which is reported and not counted as "no copy". It is a consistency nit only.

Verdict: all findings addressed
