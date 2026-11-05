### Spec Compliance

- ✅ Spec compliant. I checked the brief's Task 9 interface and the spec's "The title backfill" and "The station lock" sections against cli.py, retitle.py, CLAUDE.md and the tests. The order is plan (cli.py diff 345-346); `--dry-run` / nothing-to-write exit (348-351); confirm with the no-TTY refusal (353-359); `ps` check (364-374); `station_lock(root, command="emcee retitle")` around the whole write phase (376-379); R2 re-read of every `plan.writes` before anything is written or the backup dir is created (255-266); backup dir (269-276); per show, a durable backup plus record, then `write_title`, then the after line (280-311). Every listed file has its hunk. `_COMMAND_ORDER` has `"retitle"` before `"lock"` (163), and test_cli_boundary.py:551 matches.
- ⚠️ Cannot verify from the diff: that `station_lock`'s SIGTERM/SIGHUP handler is installed for this command and releases on `typer.Exit` (Task 5 code). The tests show the lock is gone after Exit(1) paths (test_retitle_cmd.py:895, 954, 1003). That `plan_retitle` classifies awaiting, refused and unchanged correctly is Task 8 code, reached here only through the command tests.

### Named-risk checks (one focused check each)

- **Lock never held during `Proceed?`; ps before the lock.** Holds. `typer.confirm` (cli.py diff 357) and `other_tool_processes` (365) both come before the `with station_lock` at 377. No lock is taken anywhere earlier in `retitle_cmd`. Pinned by test_retitle_cmd.py:747-764 (lock file absent and `sl._held is None` inside confirm) and 829-846 (patched `station_lock` never called on the ps refusal).
- **Exit code.** I went through every listed case. Refused: `failed = bool(plan.refused)` (347) feeds the dry run (351), the decline (359) and the end of the run (386-387). Skipped-as-changed: `return not skipped` (316) gives `failed` (379). Drift (266), ps (369, 374), held lock (385), backup (275, 288), write/verify (297), after-record failure (311) and no-TTY (356) each raise Exit(1). Awaiting, unchanged and unvoiced never touch `failed`. Correct in every case. Not listed in the brief: declining exits 0, or 1 if anything was refused. That is consistent with the rule.
- **Printed copy.** Every brief string matches exactly: `would write`, `skip … awaiting fix from llama`, `refused`, the summary, `nothing to write`, the confirm error, the ps refusal, the drift refusal, `backup failed (<err>); stopping before writing it`, `not attempted:`, `<slug>: <old> -> <new>`, `skip <slug>: changed since the plan` and `error: <TitleWriteFailed>`. Lines beyond the brief: `stray temp:`, `backups: <dir>`, `<n> written`, and `changed since the plan: …` on stderr. The report does not mention `<n> written`; see Minor.
- **record.jsonl misleading a hand restore.** Lines are keyed by slug. There is one run dir per run (the `-n` suffix) and one `<slug>.json` per slug (`"xb"`), so a before line and an after line cannot belong to different files. The cases without an after line are: skip-as-changed (file is the other writer's), verify failure with put-back (file is the original), the `_AfterRename` failure, an after-append failure, and a SIGTERM between the rename and the append. In the last three the file holds this run's bytes. The sha-equals-`after_sha256` rule leaves all of them in place, which is the safe direction. Because `_save_backup` completes before `write_title` (283 before 290), a signal can never leave a written show with no backup. The after hash is of `out`, and `write_title` returns `new` only after `after_raw == new` and the verify pass (retitle.py `write_title`, outside the diff, checked). So the record is never wrong. It is incomplete in the three cases above; see Minor 1.
- **R9 fchmod tolerance.** It is limited to `_FCHMOD_REFUSED = {EPERM, ENOTSUP, EOPNOTSUPP, EINVAL}` (retitle.py diff 434, 474-478). Any other errno re-raises into the `BaseException` handler and becomes `_BeforeRename`. Pinned by test_retitle_writer.py:1235-1262 (all four tolerated; EACCES and EIO fatal, file and mtime unchanged).
- **ps self/ancestor exclusion (procs.py, outside the diff).** `tool_lines` walks ppid from `os.getpid()` and skips self plus every ancestor. That covers `uv run emcee …` (uv is an ancestor and does not match a tool anyway), a `bash -c` / `zsh -lc` wrapper or a forked pipeline subshell (an ancestor), and a PyInstaller-style signed binary whose bootloader parent shows the same command line (an ancestor). A sibling in a pipeline (`| tee`) does not match. If ps omits our own pid, the ancestors are not skipped and the parent shell matches. That is a false refusal, which fails closed. `ps` failing (FileNotFoundError, CalledProcessError) is caught at cli.py diff 366 and refused. Correct.

### Beyond-brief choices, judged

- **ps unavailable refuses (366-369).** Right: fail closed on the only guard against lock-blind tools.
- **Backup dir `-n` suffix (231-244).** Right. It keeps `"xb"` and the per-slug record unambiguous across same-second runs (pinned at test_retitle_cmd.py:1137).
- **An `after_sha256` append failure stops the run (304-311).** Right. Each later show would otherwise be unrestorable by the documented rule.
- **`backups:` line (276).** Fine and useful. It prints only after the drift check passes.
- **No dir fsync, no F_FULLFSYNC.** Acceptable for R6: `os._exit` keeps kernel buffers. Against power loss, a lost backup costs only a title-only diff. The original's absent-vs-null `title` cannot be told apart afterwards, but they are the same title by spec. A one-time `os.fsync` of the run dir's fd (and of `title-backups/` on first creation) is cheap; see Minor 3.

### Strengths

- The ordering is exact, and each step is pinned by a test that observes the state at the moment it matters. Confirm asserts no lock (747). `write_title` and `_save_backup` see one identical lock body (782-809, `len(set(raws)) == 1`). The ps refusal never calls `station_lock` (836-844). The drift snapshot is taken at the lock (866-895).
- Backups are durable before every write, and `"xb"` makes a collision a hard stop rather than an overwrite. The real-writer collision test is at 957-975.
- `write_title` escapes are all fatal (290-297), including non-`TitleWriteFailed`, per the carried ruling. The `not attempted` lists are precise, `(none)` for the last show included.
- The R9 unlink fix keeps the original cause and never replaces a KeyboardInterrupt (retitle.py diff 491-499; tests 1280-1329).
- The CLAUDE.md entry covers everything Step 5 lists: 136, unmark, snapshot restore, encoding, mtime and `quiet_minutes` 10, lock and ps, the backup path, the hand-restore rule and the agent rule.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **packages/emcee/CLAUDE.md diff 94-96 (hand restore). Two gaps.**
   - (a) The doc does not say to restore the mtime from the record's `mtime_ns`. A plain `cp` of hundreds of backups gives every restored manifest a fresh mtime, and hugo then drops those planned shows for `quiet_minutes`. That is the very hazard the writer was built to avoid, and `mtime_ns` is recorded for exactly this. Add "and set its mtime back to `mtime_ns` (`os.utime`)".
   - (b) The doc does not say what a slug with a before line and no after line means: an `_AfterRename` failure, an after-append failure, or a kill between the rename and the append. Each leaves this run's bytes in place. The rule correctly leaves such a file alone, but the doc should say so.
2. **retitle.py diff 496.** The "temp was left" `add_note` goes on the OSError, but the `TitleWriteFailed` message only formats `str(exc.__cause__)`, which drops notes. The operator therefore never sees that a temp was left. The next plan's `stray temp:` line does surface it. Fold the note into the message, or accept the gap.
3. **cli.py diff 211-244.** Fsync the new run dir once after `mkdir`, and `title-backups/` when it is created. This makes the backup entries and `record.jsonl` durable against power loss, not just against `os._exit`. Cheap; optional.
4. **cli.py diff 313.** `<n> written` is extra copy. The brief does not list it and the implementer did not report it. It is harmless, but should be noted for the controller. `nothing written` goes to stdout on decline (358) and to stderr on a held lock (384). That is an inconsistent stream, trivial.
5. **cli.py diff 190-194, `_stray_temps`.** This adds a readdir of every package directory on the SMB share (2,786) to every plan, dry run included. Not requested by the brief. It is probably acceptable next to `plan_retitle`'s per-manifest reads, but worth timing at go-live.
6. **test_retitle_cmd.py:957.** The name says "read_only_dir", but the test makes an `"xb"` collision. Rename it.
7. **test_retitle_cmd.py:866-895.** A mutant that moves the R2 re-read before `station_lock` (after the ps check) would still pass, because the change is injected in the ps hook. Injecting the change inside the patched `lock()` just before `real_lock` would not catch that mutant either. Asserting `sl._held is not None` at re-read time (for example, by wrapping `Path.read_bytes` for the planned manifests) would pin "under the lock".
8. **Ctrl-C during the write phase** propagates as KeyboardInterrupt. The lock is released and `_swap` cleans its temp, but no `not attempted:` list is printed. Acceptable, but undocumented.

### Assessment

**Task quality:** Approved

**Reasoning:** Every spec and brief ordering constraint (confirm, then ps, then lock, then whole-run drift refusal, then a durable backup before each write) is implemented exactly and pinned by tests that observe state at the critical moment. The R9 fixes are scoped precisely to the ruled errnos and messages. The remaining items are documentation completeness for hand restores and small durability or polish points, none of which can corrupt or lose a station manifest.
