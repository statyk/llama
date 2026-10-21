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

### Task 4: Failure records carry `kind` and `at`

**Implementer model: Sonnet** (two files, fully specified).

**Files:**
- Modify: `packages/llama/src/llama/sessions.py`, `packages/llama/src/llama/cli.py` (`_execute._process`'s two `failures.append` sites)
- Test: `packages/llama/tests/test_sessions.py`, existing assertions in `test_run_namespace.py`/`test_sessions.py`/`test_pace_loop.py` that compare whole failure dicts

**Interfaces:**
- Produces (in `sessions.py`):
  - `KIND_RATE_LIMITED = "rate-limited"`, `KIND_LLM = "llm"`, `KIND_TRANSPORT = "transport"`, `KIND_DOWNLOAD = "download"`, `KIND_ARCHIVE = "archive"`, `KIND_OTHER = "other"`.
  - `classify_failure(exc: BaseException) -> str` — first match in order: `RateLimited` → rate-limited; `TaskFailed` → llm; herder `ResearchNotSupported` → other; other `HerderError` → transport; `IADownloadError` → download; other `IAError` → archive; anything else → other.
  - `failure_record(show: str | None, exc: BaseException, *, kind: str | None = None, now: datetime | None = None) -> dict` → `{"show", "error", "kind": kind or classify_failure(exc), "at": <UTC ISO>}`; `error` is `str(exc)`, or the exception's class name when that is empty.
  - `failure_kind(record: dict) -> str` — the record's `kind` if present; else `download` when `error` starts with `download of `, else `other`.
- `_execute` uses `failure_record(pid, exc)` at both sites (the `--no-pacing` `RateLimited` site and the `(TaskFailed, HerderError, IAError)` site).

- [ ] **Step 1: Write failing tests** — `test_classify_failure_follows_the_order` (one parametrized case per class, including `RateLimited` beating `HerderError`, `TaskFailed` beating `HerderError`, `ResearchNotSupported` → other, `IADownloadError` beating `IAError`, `ValueError` → other); `test_failure_record_stamps_kind_and_utc_at` (also: an exception with an empty `str()` records its class name); `test_legacy_record_kind` (`{"error": "download of x failed after 3 attempts: …"}` → download; `{"error": "boom"}` → other; a record with `kind` keeps it); `test_execute_records_kind_for_a_failed_show` (via `test_pace_loop._drive`-style stub raising `IADownloadError` → the session's failure has `kind == "download"` and an `at`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**; update existing whole-dict failure assertions to compare `show`/`error` (they gain `kind`/`at`). **Step 4: Run** `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(sessions): failure records carry kind and at`.

---

