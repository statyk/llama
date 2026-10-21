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

### Task 3: Download cap (8 slots per workspace)

**Implementer model: Sonnet** (one new module plus a narrow wiring change; the tests are specified below).

**Files:**
- Create: `packages/llama/src/llama/download_slots.py`
- Modify: `packages/llama/src/llama/ia_client.py` (acquire around each attempt), `packages/llama/src/llama/cli.py:_setup` (construct the `DownloadSlots`)
- Test: `packages/llama/tests/test_download_slots.py`, `packages/llama/tests/test_ia_client.py`

**Interfaces:**
- Produces:
  - `DOWNLOAD_SLOTS = 8`, `SLOT_POLL_MIN_S = 0.5`, `SLOT_POLL_MAX_S = 1.0`.
  - `class DownloadSlots: __init__(self, dir: Path, n: int = DOWNLOAD_SLOTS, *, sleep=time.sleep, clock=time.monotonic, rng: random.Random | None = None)`.
  - `DownloadSlots.acquire(self, *, on_wait: Callable[[], None] | None = None) -> ContextManager[float]` — yields the seconds spent waiting (measured on `clock`). Polls `dir/0.lock .. dir/{n-1}.lock` with non-blocking `flock`, in order; if all are held, calls `on_wait` (first poll miss only) and `sleep(rng.uniform(SLOT_POLL_MIN_S, SLOT_POLL_MAX_S))`, then polls again. Never blocks on one slot. Creates `dir` if missing. Releases on exit and on process death (flock).
  - `IAClient.__init__(..., slots: DownloadSlots | None = None)` — `None` means no cap. `_setup` passes `DownloadSlots(config.root / ".download-slots")` (production: real clock, sleep, RNG). Tests pass a `DownloadSlots` sharing the `IAClient`'s fake clock, or a stub with the same `acquire` contract.
- In `download_file`: the slot is held for one attempt's request+transfer and released before any sleep; `detail("waiting for a download slot")` prints at most once per `download_file` call (via `on_wait`). Only slot waits after the first pass ends affect the deadline: it is measured from the end of the first pass, minus the yielded wait seconds of attempts started after that point (Task 1).

- [ ] **Step 1: Write failing tests**
  - `test_never_more_than_n_holders` — 12 threads, `n=8`, a shared counter incremented/decremented inside the `with` under a `threading.Lock`, recording the max. Holders block inside the `with` on a `threading.Event go`; the injected `sleep` records a poll then blocks on `go`. The main thread waits (a `threading.Condition` with a generous failure-guard timeout, not a correctness sleep) until 8 are holding and 4 have polled, asserts `held == 8`, sets `go`, joins → `max_held == 8`, 12 acquisitions total.
  - `test_a_dead_holder_frees_its_slot` — a `subprocess` (`sys.executable -c ...`) opens and flocks all 8 slot files, prints `held`, then reads stdin. The parent reads `held`, asserts `acquire` with a `sleep` that raises a sentinel exception does raise it (would wait), then `kill()` + `wait()` the child and asserts the same `acquire` succeeds without calling `sleep`.
  - `test_on_wait_called_once_per_acquire` — all slots held by a second `DownloadSlots` in the same process; the injected `sleep` releases them after 3 polls → `on_wait` called exactly once.
  - In `test_ia_client.py`: `test_slot_released_before_sleep_between_attempts` — a 1-slot `DownloadSlots`, redirect 500 then server 200; the injected `sleep` asserts the slot is free (a non-blocking flock on `0.lock` succeeds) when called.
  - `test_slot_wait_does_not_count_toward_deadline` — a `DownloadSlots` stub whose acquire advances the fake clock by 500 s and yields 500.0; all candidates fail → the number of repeat attempts equals that of a run with zero wait.
- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_download_slots.py packages/llama/tests/test_ia_client.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** those files, then `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(ia): cap concurrent audio downloads at 8 per workspace`.

---

