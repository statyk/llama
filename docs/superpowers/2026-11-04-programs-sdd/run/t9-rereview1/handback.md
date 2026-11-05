### Finding Verdicts

- **1(a) Hand restore must say to reset mtime to `mtime_ns`**: ADDRESSED. packages/emcee/CLAUDE.md:142-144 says to set the mtime back with `os.utime(path, ns=(atime, mtime_ns))` and gives the reason (a `cp` gives a fresh mtime, so hugo drops the show for `quiet_minutes`). There is a residual, listed as Minor N1 below.
- **1(b) Doc must say what a before-only slug means and how to handle it**: ADDRESSED. CLAUDE.md:145-151 says what a before line with no after line means, says the restore rule leaves every such file alone, and gives a hand check (sha256 equal to `before_sha256` means the original; otherwise compare with the backup plus only the new title). The list of causes is incomplete and the action after each check is only implied. Both are listed as Minor N2 below; the procedure itself is safe in every case.
- **2 fsync the backup directories**: ADDRESSED. cli.py:1516-1523 adds `_fsync_dir`. It runs on:
  - the emcee root, when `title-backups/` is first created (cli.py:1541-1543);
  - `title-backups/` and the new run dir, after the run dir's mkdir (cli.py:1553-1554);
  - the run dir after each show's `<slug>.json` and its `before` record line (cli.py:1533).

  Fsyncing the run dir per show is right. A fsync of the empty run dir at mkdir time does nothing for entries created later, and `record.jsonl`'s entry first appears at show 1. The cost is one local fsync per show. Treating a failed dir fsync as a backup failure (cli.py:1593-1599: stop before writing that show) is also right: it fails closed while nothing about the show has changed. In that case a `before` line can exist for a slug that was never attempted. Its sha256 equals `before_sha256`, so the doc's hand check classifies it correctly as the original.

  Ordering check: the only `_fsync_dir` calls are inside `_save_backup`, which runs before `write_title`, and `_backup_run_dir`, which runs before the loop. Neither can run between `write_title` and the `after_sha256` append (cli.py:1601-1622). `_append_record` for the after line does no dir fsync, and needs none: the `record.jsonl` entry was already made durable by show 1's dir fsync. The record's meaning is unchanged.
- **3 Drift test must pin "re-read under the lock"**: ADDRESSED. test_retitle_cmd.py:302-345 wraps `Path.read_bytes`. For each manifest read after the plan, it records whether `sl._held` is set and the lock file names `command: emcee retitle`. The test's own snapshot reads are excluded, and it asserts `reread == [("a", True), ("b", True), ("c", True)]`. Two mutants would fail:
  - A re-read moved to between the ps check and `station_lock` records `held=False`.
  - A re-read moved before the ps check is never recorded, so the list is empty.

  The implementer reports that the move-before-lock mutant was caught. `sl._held` exists (station_lock.py:75).
- **4 Rename the misnamed `read_only_dir` test**: ADDRESSED. It is now `test_backup_failure_of_the_real_writer_on_an_existing_backup_file` (test_retitle_cmd.py:467), which matches its "xb" collision.

### New Breakage in the Fix Diff

- **Minor N1** (CLAUDE.md:141-144): the instructions describe a plain copy, then `os.utime` on the live file. That differs from how the writer itself avoids hugo trouble (retitle.py:13-16). The writer sets the mtime on a closed temp before the rename, because hugo's NFS attribute cache can show a post-rename mtime for up to a minute. Restoring hundreds of shows with copy-then-utime leaves two risks:
  - each show can still be dropped from a fill that lands in that cache window;
  - an in-place copy exposes a partially written manifest to a concurrent reader.

  Suggested wording: copy to a temp in the same directory, `os.utime` the temp, then `os.replace` onto `manifest.json`. Also restore with no emcee/llama running, or under the station lock. The doc currently says nothing about concurrency, and the sha256 precondition is only as good as the moment it is checked.
- **Minor N2** (CLAUDE.md:145-151): the list of before-only causes is incomplete.
  - It leaves out a failed put-back after a failed verify ("it holds this write's bytes", retitle.py:274-278). That case is a fourth "may hold this run's bytes" case, yet the doc says only "the last three" are.
  - It also leaves out: a failed re-read after the write (contents unknown), another writer after the write, a file gone after the write, a before-rename or stat failure, a dir fsync failure after the before line, and a non-`TitleWriteFailed` escape.

  Two more gaps:
  - The doc never states the final action. If the file matches backup-plus-new-title, restore it (and set its mtime); if it matches neither, leave it. The skipped-as-changed shows fall into the second branch.
  - `record.jsonl` does not carry the new title, and an after-rename failure prints no `<slug>: old -> new` line. The operator has to take the new title from the plan's `would write` line or from the config, and the doc does not say so.

  The hand check is safe as written, because anything that is neither the original nor this run's bytes is left alone. Suggested fix: replace the list with "any stop or skip at this slug" and spell out the three outcomes.
- **Minor N3** (cli.py:1541-1543): if `mkdir(parents=True)` also had to create the emcee root, the root's own parent entry is not fsynced. The emcee root normally already exists, so this is negligible.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Three Minor items (N1-N3) are for the controller's ledger. N1 is the one worth carrying into the restore doc before anyone uses it at scale.
