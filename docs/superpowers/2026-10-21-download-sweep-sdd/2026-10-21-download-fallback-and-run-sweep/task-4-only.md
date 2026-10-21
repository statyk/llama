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

