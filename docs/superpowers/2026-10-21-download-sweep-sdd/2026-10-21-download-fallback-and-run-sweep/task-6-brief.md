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

### Task 6: Run lock and `running` in readers

**Implementer model: Opus** (live-run detection strict surface; touches six commands).

**Files:**
- Modify: `packages/llama/src/llama/locks.py`, `packages/llama/src/llama/workspace.py` (`RunWorkspace.lock`), `packages/llama/src/llama/sessions.py` (`iter_sessions`, `STATE_RUNNING`), `packages/llama/src/llama/cli.py` (`_get_query`, `_get_profile`, `run_resume`, `run_approve`, `_redo_run_level`, `run_rm`, `_print_sessions`, `_session_json`, `_ATTENTION_LABELS`, `_NEXT_STEP`, `_by_run_rollup`, `status --by-run`)
- Test: `packages/llama/tests/test_run_lock.py` (new), adjustments in `test_run_namespace.py`

**Interfaces:**
- Produces:
  - `locks.RunMissing(Exception)`.
  - `locks.run_lock(run_dir: Path, *, blocking: bool) -> ContextManager[None]` — exclusive flock on `run_dir/.lock`; raises `RunMissing` if `run_dir` is not an existing directory, and never creates it (open `run_dir/.lock` with `O_CREAT` but no `mkdir`; a `FileNotFoundError` from the open is `RunMissing`); non-blocking + held → `Locked`. After acquiring (blocking or not) it verifies the locked fd is still the file at `run_dir/.lock`: `os.fstat(fd).st_ino == os.stat(run_dir / ".lock").st_ino` and the same `st_dev`; otherwise it releases and raises `RunMissing` (a `FileNotFoundError` from that `stat` is also `RunMissing`).
  - `locks.run_is_live(run_dir: Path) -> bool` — opens an **existing** `run_dir/.lock` `O_RDONLY` (no `O_CREAT`: a missing file or dir is "not live"), tries `LOCK_EX|LOCK_NB`, releases at once.
  - `RunWorkspace.lock = dir / ".lock"`.
  - `sessions.STATE_RUNNING = "running"`; `iter_sessions(root, *, probe_live: bool = True)` reports `running` for a live run regardless of its marker. `session_state()` never probes (it is called by `run rm` while holding the lock).
  - `cli._run_locked(ws: RunWorkspace) -> ContextManager[None]` — non-blocking `run_lock`; `Locked` → stderr `run <id> is in progress in another process`, `typer.Exit(1)`; `RunMissing` → stderr `run <id> no longer exists`, `typer.Exit(1)`.
- Wiring (spec §4), each lock taken once at command entry and held to exit:
  - `get` (both forms): the lock is taken right after the run dir exists, before `request.json` is written and before interpret; `claim_run_dir`'s fresh dir → `run_lock(blocking=True)`. `--name`: try `(runs / name).mkdir(parents=True, exist_ok=False)`; success → created → blocking lock; `FileExistsError` → existing → non-blocking `_run_locked` (refuses only a live run; an existing non-live dir is reused exactly as today). Only the decision mechanism changes; existing-name behaviour is unchanged.
  - `run resume <id>`: `_run_locked` before reading anything (Task 7 moves this into the helper).
  - `run approve`: `_run_locked` at entry, before the shortlist prints or any prompt.
  - `redo --run <id> --from search|winnow`: `_run_locked` in `_redo_run_level` before any read. The show-stage `--run` form is unchanged.
  - `run rm`: `_run_locked`, then the prompt, then `shutil.rmtree(ws.dir)` while holding the lock (Review Focus 4).
- Readers: `_ATTENTION_LABELS[STATE_RUNNING] = "running"`, `_NEXT_STEP[STATE_RUNNING] = "in progress"`; `_session_json`'s `next` is `None` for a running run (not `llama in progress <id>`). `_by_run_rollup`'s rows each gain `"running": bool` (`run_is_live`); the `status --by-run` text row appends `  [running]` when true.

- [ ] **Step 1: Write failing tests** (`test_run_lock.py`; a second holder is a real `fcntl.flock` on another fd, or a `subprocess` where a cross-process holder matters):
  - `test_run_lock_never_creates_a_missing_run_dir` — `RunMissing`, and `runs/<id>` still absent.
  - `test_run_is_live_does_not_create_the_lock_file`.
  - `test_resume_refuses_a_live_run`, `test_approve_refuses_a_live_run_before_prompting`, `test_redo_run_level_refuses_a_live_run`, `test_rm_refuses_a_live_run` — each exits 1 with `run <id> is in progress in another process`, and nothing under the run dir changed.
  - `test_get_takes_a_blocking_lock_on_its_fresh_dir` — monkeypatch `locks.run_lock` (as imported by `cli`) to record `blocking`; `get` query and profile forms record `True` and the lock is held when `_execute` is called (assert from a stubbed `_execute` that a non-blocking probe raises `Locked`).
  - `test_get_name_creates_and_locks_its_dir`, `test_get_name_existing_live_run_is_refused`.
  - `test_no_self_deadlock_get_to_execute` and `test_no_self_deadlock_resume_to_execute` — stub the stages, run the command end to end under `CliRunner`; it completes.
  - `test_run_list_reports_running` (text label `running`, NEXT `in progress`; `--json` `state == "running"`, `next is None`), `test_status_by_run_marks_running` (text `[running]`, JSON `running: true`).
  - `test_lock_on_a_replaced_lock_file_is_run_missing` (Review Focus 4) — a second fd holds the flock on `run_dir/.lock`; an acquirer in a thread blocks in `run_lock(run_dir, blocking=True)`; `run_dir/.lock` (or the whole dir) is deleted and recreated, then the holder releases → the acquirer raises `RunMissing` and holds no lock. Make the ordering deterministic (e.g. do the replacement inside a wrapped `flock` call on the acquirer's path), not with a timing sleep.
- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_run_lock.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `./.venv/bin/pytest -q` → PASS (adjust any existing test that asserted the exact rm/approve flow only where the lock changes it).
- [ ] **Step 5: Commit** `feat(runs): run lock on every command that works a run; readers report running`.

---

