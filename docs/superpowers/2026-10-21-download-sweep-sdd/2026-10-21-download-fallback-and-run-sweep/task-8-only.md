### Task 8: Documentation

**Implementer model: Sonnet** (prose in two files).

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1:** `CLAUDE.md` "Commands" llama bullet: `llama run resume --all` (eligibility, `--no-wait` default, stop-on-pause, exit codes, the crash marker; the operator loop `while true; do llama run resume --all; sleep 600; done`); `run list`'s `running` state. "Architecture" parallel-safe bullet: the run lock (which commands, held once at entry, never inside `_execute`, readers probe without creating, lock order run ⊃ show ⊃ ledger, `run rm` holds it through `rmtree`, the inode check after acquiring) and the download cap (`<root>/.download-slots/0..7.lock`). "Domain gotchas": the download fallback (redirect then `workable_servers`/`d1`/`d2`, per-connection throttling, the trickle switch, whole-file integrity, `IADownloadError`), and the failure-record `kind`s. Honest pacing: one sentence where the pacing EWMA is described. The rollout caveat: a pre-v2.14 run holds no lock, so don't sweep while one is going. Known limitations, one line each:
  - the download cap is not FIFO: with more than 8 downloading processes a waiter may wait until a holder's show finishes downloading;
  - the last non-abandoned candidate is never abandoned, so a server dribbling just above the stall timeout holds its slot until it finishes;
  - a file whose every copy fails the integrity check (a removed or darked item, or a stale cached md5) fails as `download` on every sweep pass, so the sweep keeps listing it and exits 1 until it is cleared by hand;
  - a lock attempt landing inside `run rm`'s `rmtree` recreates `.lock`, so `rm` fails and leaves a `.lock`-only dir, listed as needs attention; a second `run rm` removes it;
  - none of the remaining lock windows can produce two workers: the inode check stops a fresh `get` whose dir was removed under it from working an unlocked dir.
- [ ] **Step 2:** `README.md` session commands block (around line 143-150): add `llama run resume --all` and the `running` state.
- [ ] **Step 3:** `./.venv/bin/pytest -q` → PASS (docs-only; confirms nothing else moved).
- [ ] **Step 4: Commit** `docs: download fallback, run lock, run resume --all`.

---

## Mutation pins (for the task reviewers and the final review)

Run in a scratch copy only (`git archive HEAD | tar -x -C <scratch>`), with `<scratch-venv-or-worktree-venv>/bin/python -m pytest` and `PYTHONPATH` shadowing proven by a planted sentinel; name the predicted red test before flipping each mutant.

| Mutant | Predicted red test |
|---|---|
| Skip the md5 check when the `.part` came from more than one server | `test_stitched_file_with_bad_md5_is_deleted_and_refetched_from_zero` |
| Append to `.part` on a `206` without checking `Content-Range` start | `test_wrong_content_range_restarts_from_zero` |
| Allow abandoning the last non-abandoned candidate | `test_last_non_abandoned_candidate_is_never_abandoned` |
| Drop the floor comparison / floor × 100 | `test_slow_but_above_floor_transfer_finishes` |
| Keep an md5-mismatched copy in the repeat cycle | `test_md5_mismatch_copy_is_checked_once` |
| Cut the first pass short at the deadline | `test_hanging_redirect_does_not_starve_listed_servers` |
| Count slot wait toward the deadline | `test_slot_wait_does_not_count_toward_deadline` |
| `run_is_live` opens with `O_CREAT` | `test_run_is_live_does_not_create_the_lock_file` |
| `run_lock` calls `mkdir(parents=True)` | `test_run_lock_never_creates_a_missing_run_dir` |
| Drop the inode check | `test_lock_on_a_replaced_lock_file_is_run_missing` |
| Record a boundary on `ran` alone (drop the LLM-call condition) | `test_a_download_only_resume_records_no_boundary` |
| Treat `transport` as eligible | `test_eligibility_per_state_and_kind[transport]` |
| Sweep default `wait=True` | `test_no_wait_is_the_default_for_the_sweep` |
