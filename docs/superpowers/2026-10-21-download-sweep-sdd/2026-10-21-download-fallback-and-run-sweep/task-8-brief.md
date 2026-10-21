# Plan context (applies to every task)

## Global Constraints

- Review mode: **Opus** (task reviewers and the final branch reviewer).
- Strict surfaces (spec "Stakes"): **download integrity** — no truncated or corrupt file is ever renamed into place, from any server; **live-run detection** — a wrong "not live" verdict starts a second worker; **LLM spend** — the pacing gate applies to every show the sweep processes, its learned cost stays honest, the sweep never loops spend on a run that fails the same way every time.
- Tests are offline and deterministic: httpx `MockTransport`, injected clock, sleep and RNG. No network, no timing sleeps for correctness. Never touch `~/.llama` or the station root; use `tmp_path`.
- Run the suite from the worktree as `./.venv/bin/pytest -q` (the worktree has its own `.venv`; `./.venv/bin/python -c "import llama; print(llama.__file__)"` must resolve inside the worktree).
- Persisted artifacts stay permissive: a `session.json` failure record may lack `kind`/`at` (legacy) and readers must cope. `config.toml` gains nothing (`DOWNLOAD_SLOTS` and all download constants are module constants, not config).
- emcee and transmitter are untouched.
- Download constants (module level in `llama/ia_client.py`): `DOWNLOAD_CONNECT_TIMEOUT_S = 10.0`, `DOWNLOAD_STALL_TIMEOUT_S = 20.0`, `DOWNLOAD_DEADLINE_S = 60.0`, `DOWNLOAD_SLEEP_MIN_S = 1.0`, `DOWNLOAD_SLEEP_MAX_S = 4.0`, `TRICKLE_FLOOR_BPS = 10_000`, `TRICKLE_WINDOW_S = 30.0`. Slot constants (in `llama/download_slots.py`): `DOWNLOAD_SLOTS = 8`, `SLOT_POLL_MIN_S = 0.5`, `SLOT_POLL_MAX_S = 1.0`.
- `max_retries` and `backoff_s` keep serving `IAClient._get` unchanged; `_get` keeps the client's own timeout settings.
- Error text for an exhausted download keeps the `download of <filename>` prefix (the legacy-record rule in §3 and the operator's greps depend on it).
- Lock order: run ⊃ show ⊃ ledger. `process_show` stays lock-free. The run lock is never taken inside `_execute`.
- Exact output lines quoted by the spec are copy: `waiting for a download slot`, `run <id> is in progress in another process`, `nothing to resume`.

## Review Focus

Failure modes the spec implies but does not list as tests; each has a test in the named task.

1. **A stale `.part` left by a killed earlier process** must never be continued with `Range` — a fresh `download_file` call starts from byte 0 (Task 2, `test_stale_part_from_a_previous_process_is_not_continued`).
2. **Unusable metadata** — the metadata fetch fails or returns non-JSON, `files` lacks the entry, `size` is non-numeric, `workable_servers` holds duplicates — degrades to fewer candidates / no size check, never a crash (Task 1, `test_unusable_metadata_degrades_to_redirect_only`, `test_duplicate_servers_are_tried_once`).
3. **A `Range` request answered 416** (the next copy is shorter than the bytes already held) discards the `.part` and is retryable. Without that, a `416` is a non-retryable 4xx with the `.part` kept, so every candidate would answer `416` and the file would fail after one pass although a fresh download would succeed (Task 2, `test_416_discards_the_part_and_restarts_from_zero`).
4. **`run rm` racing a lock attempt** — a fresh `get` whose dir is removed and recreated under it must not end up working an unlocked dir: the run lock checks that the locked fd is still `run_dir/.lock` (Task 6, `test_lock_on_a_replaced_lock_file_is_run_missing`). The other race, a lock attempt recreating `.lock` inside `rm`'s `rmtree` so `rm` fails and leaves a `.lock`-only dir, is a documented limitation (spec §4); its only test is that `run rm` refuses a live run (`test_rm_refuses_a_live_run`).
5. **A run removed between the sweep's listing and its turn** is reported `gone` and does not count as an error or get a marker (Task 7, `test_a_run_removed_before_its_turn_is_reported_gone`).

---

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
