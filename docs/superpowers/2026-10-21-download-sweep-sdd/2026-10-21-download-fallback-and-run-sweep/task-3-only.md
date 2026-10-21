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

