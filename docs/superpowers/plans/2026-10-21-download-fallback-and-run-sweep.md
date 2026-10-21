# Download fallback, archive.org courtesy, and the run sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audio downloads survive broken archive.org copies (server fallback, bounded retry, trickle switch with Range continuation), at most 8 run concurrently per workspace, every run-working command holds a run lock so liveness is known, pacing samples stay honest, and `llama run resume --all` replaces the operator's hand loop.

**Architecture:** `IAClient.download_file` becomes a candidate-URL scheduler (redirect URL, then the item's listed servers) with its own short timeouts, an injectable clock/sleep/RNG, a throughput monitor that can hand a partial `.part` to the next candidate via `Range`, and a whole-file integrity check; a new `DownloadSlots` flock pool caps concurrency. Runs gain an exclusive flock (`runs/<id>/.lock`) taken once at command entry by every command that works a run, probed non-blockingly by readers to report `running`. The sweep is one pass over `iter_sessions` that resumes eligible runs through a helper extracted from `run_resume`.

**Tech Stack:** Python 3.11+, httpx (`MockTransport` in tests), typer, pydantic, `fcntl.flock`.

**Spec:** `docs/superpowers/specs/2026-10-21-download-retry-and-run-sweep-design.md` (read it with this plan; section numbers below are the spec's).

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

### Task 1: Server fallback, download timeouts, classification and schedule

**Implementer model: Opus** (download-integrity strict surface; scheduling judgment).

**Files:**
- Modify: `packages/llama/src/llama/ia_client.py` (`download_file`, new helpers, constants, `IADownloadError`, `IAClient.__init__`)
- Test: `packages/llama/tests/test_ia_client.py`

**Interfaces:**
- Produces:
  - `class IADownloadError(IAError)` — message starts `download of <filename> failed:` and names every URL tried with its last error.
  - `IAClient.__init__(..., *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, rng: random.Random | None = None)` — new keyword-only injectables; existing parameters unchanged. (Task 3 adds `slots`.)
  - `IAClient._download_candidates(identifier: str, filename: str) -> tuple[list[str], int | None]` — candidate URLs in order, plus the metadata `size` of `filename` (`None` when absent or non-numeric).
  - `IAClient.download_file(identifier, filename, dest, md5=None) -> Path` — signature unchanged.
  - Internally, one attempt is a method `_attempt(url, tmp, ...)` returning an outcome the schedule can classify (`ok`, or an error with `retryable: bool`). Task 2 extends this method; keep the transfer loop in one place.

**Behavior to implement (spec §1, everything except the trickle switch):**
- Candidates: (1) `DOWNLOAD_URL` as today; (2) `https://<server><dir>/<quote(filename)>` for each server in `workable_servers` in order, de-duplicated; only when `workable_servers` is missing or empty, `d1` then `d2`, de-duplicated. No server or no `dir` → redirect only. Metadata comes from `self.metadata(identifier)`; if that raises `IAError` or `ValueError` (non-JSON), use redirect only with no size.
- `quote(filename)` keeps `/` (same rule as `DOWNLOAD_URL`).
- Each attempt: `self._throttle()`, then `self.client.stream("GET", url, timeout=httpx.Timeout(DOWNLOAD_STALL_TIMEOUT_S, connect=DOWNLOAD_CONNECT_TIMEOUT_S))`. No total-time bound.
- Classification:
  - 5xx, 429, 408 and every `httpx.TransportError` (incl. timeouts and a body stream dying mid-transfer) → retryable.
  - Any other `httpx.HTTPError` (e.g. `TooManyRedirects`, `DecodingError`) → that attempt fails, retryable. No `httpx` exception ever escapes `download_file`.
  - Other 4xx → moves on, not retryable.
  - md5 mismatch → moves on, `.part` deleted, not repeated (that copy is not retried). Each copy is checked at most once per `download_file` call; the others are still tried.
  - No md5 and a known `size` → byte count must equal `size` before rename; a mismatch is handled like an md5 mismatch.
  - Neither → rename as today.
- md5 is computed by reading the finished `.part` back from disk (whole file), not from a running hash — Task 2 relies on this to verify stitched files.
- Schedule: first pass = one attempt per candidate in order, never cut short; `self.sleep(self.rng.uniform(DOWNLOAD_SLEEP_MIN_S, DOWNLOAD_SLEEP_MAX_S))` between attempts. Then repeat passes cycle the candidates whose last error was retryable, until `DOWNLOAD_DEADLINE_S` of attempts+sleeps measured on `self.clock` from the end of the first pass. The deadline is checked before starting an attempt; an attempt in flight finishes. Slot wait reported by attempts started after the first pass (Task 3; 0 here) is subtracted from the elapsed time. Exhausted (deadline, or no retryable candidate) → delete any `.part`, raise `IADownloadError`. `Retry-After` is ignored.
- A failed attempt deletes the `.part` (Task 2 refines this for trickle continuation).

- [ ] **Step 1: Update the test helper and write failing tests**

`make_client` gains a fake clock where `sleep` advances time, passed as `clock=`/`sleep=`/`rng=random.Random(0)`, and a `metadata` dict served at `https://archive.org/metadata/<id>`. Existing download tests keep passing through it (their handler must now also answer the metadata URL, or the metadata must be absent → redirect-only).

Tests (all in `test_ia_client.py`):
- `test_500_on_redirect_falls_back_to_listed_server` — metadata `{"dir": "/9/items/x", "workable_servers": ["ia800903.us.archive.org"], "files": [{"name": "t.mp3", "md5": <md5>, "size": "<n>"}]}`; redirect 500, `https://ia800903.us.archive.org/9/items/x/t.mp3` 200 → file written, URLs requested in exactly that order.
- `test_every_server_failing_raises_after_first_pass_and_deadline` — all 500; raises `IADownloadError` whose message starts `download of t.mp3 failed` and names both URLs; fake clock shows the last attempt started before `first_pass_end + DOWNLOAD_DEADLINE_S`; no `.part`, no dest.
- `test_hanging_redirect_does_not_starve_listed_servers` — redirect handler advances the clock 500 s then raises `httpx.ReadTimeout`; the listed server still gets its first-pass attempt and succeeds.
- `test_4xx_moves_on_then_succeeds` — redirect 404, server 200 → success.
- `test_all_4xx_fails_after_one_pass` — both 404 → `IADownloadError`, each URL requested exactly once.
- `test_md5_mismatch_on_one_server_then_success` — redirect serves wrong bytes, server right bytes → success, dest md5 correct.
- `test_md5_mismatch_copy_is_checked_once` — two candidates both serving wrong bytes → `IADownloadError` after exactly one request to each (no repeat attempts).
- `test_too_many_redirects_is_caught` — the redirect handler raises `httpx.TooManyRedirects` (constructed with `request=`), the server succeeds → success; a lone such candidate ends in `IADownloadError`.
- `test_size_check_when_no_md5` — no md5, `size` "10"; redirect returns 9 bytes, server 10 → dest is the 10-byte body; a lone 9-byte candidate → `IADownloadError`.
- `test_mid_stream_failure_is_retryable` — a body generator that yields some bytes then raises `httpx.ReadError`; next candidate succeeds; no `.part` left.
- `test_missing_server_fields_mean_redirect_only` — metadata with no `dir` → only the redirect URL is requested.
- `test_d1_d2_used_only_when_workable_servers_empty` — `workable_servers: []`, `d1`, `d2` (equal to each other) → candidates `[redirect, d1-url]`; with a non-empty `workable_servers` lacking `d1`, `d1` is not tried.
- `test_listed_server_url_quotes_but_keeps_slash` — filename `"set 2/t 06.mp3"` → server path `/9/items/x/set%202/t%2006.mp3`.
- `test_unusable_metadata_degrades_to_redirect_only` (Review Focus 2) — metadata URL returns 500s / non-JSON; `size: "abc"` → no size check; download still succeeds from the redirect.
- `test_duplicate_servers_are_tried_once` (Review Focus 2).
- `test_download_uses_short_timeouts` — a handler that records `request.extensions["timeout"]`: `connect == DOWNLOAD_CONNECT_TIMEOUT_S`, `read == DOWNLOAD_STALL_TIMEOUT_S`.

- [ ] **Step 2: Run them, verify they fail** — `./.venv/bin/pytest packages/llama/tests/test_ia_client.py -q` → new tests FAIL.
- [ ] **Step 3: Implement** per the behavior above.
- [ ] **Step 4: Run** `./.venv/bin/pytest packages/llama/tests/test_ia_client.py packages/llama/tests/test_stage_package.py -q` → PASS; then the full suite `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(ia): download fallback to listed servers, short timeouts, bounded schedule` (message states the test command).

---

### Task 2: Trickle switch with Range continuation

**Implementer model: Opus** (download-integrity strict surface; the stitching and termination rules).

**Files:**
- Modify: `packages/llama/src/llama/ia_client.py`
- Test: `packages/llama/tests/test_ia_client.py`

**Interfaces:**
- Consumes: Task 1's schedule, `_attempt`, whole-file md5-from-disk, injected `clock`.
- Produces: nothing new outside `ia_client.py`.

**Behavior (spec §1 "Trickle switch"):**
- **Monitor**, per request, restarted for each request (including the re-issued no-Range request below): the window starts at the first body byte (the stall timeout covers the wait before it). At each chunk arrival at time `t` with `t - first_byte_t >= TRICKLE_WINDOW_S`: let `b0` be the request's cumulative byte count at the latest sample taken at or before `t - TRICKLE_WINDOW_S`; the transfer is trickling iff `total - b0 < TRICKLE_FLOOR_BPS * TRICKLE_WINDOW_S`.
- **Order per chunk:** write the chunk to the `.part`, then run the trickle check.
- **May abandon** a candidate `c` iff all of these hold:
  - `c` has not been trickle-abandoned during this `download_file` call;
  - some other candidate `d` is neither trickle-abandoned nor known non-retryable (i.e. `d` is untried or its last error was retryable);
  - another attempt will actually start: the first pass is not finished, or the deadline has not passed (`clock` now vs the deadline);
  - the `.part` does not already hold the known `size` bytes.

  Otherwise the transfer runs to completion however slow, as long as it is not stalled. A trickle abandonment is a retryable error for `c` (it stays in the repeat cycle, but can never be abandoned again).
- **The `.part` across attempts:** `offset` is always `tmp.stat().st_size` (0 when the `.part` is absent), never a separate counter. After a trickle abandonment the `.part` is kept **only when an md5 is known** for the file; with no md5 the abandonment still happens but discards the `.part`, so the next attempt starts at byte 0. An attempt that writes nothing to the `.part` (a status error, a connect failure) leaves it untouched. Any other failure of an attempt that wrote to the `.part`, any integrity failure, and the cases below discard it.
- **Continuation request:** when `offset > 0`, send `Range: bytes=<offset>-`. Then:
  - `206` with `Content-Range` starting `bytes <offset>-` (and, when `size` is known, total `/<size>`) → append to the `.part`;
  - `200` → truncate the `.part` and write this body from byte 0;
  - `206` whose `Content-Range` does not start at `offset`, or whose total differs from a known `size` → close it, discard the `.part`, and re-issue the same URL without `Range` in the same attempt (from byte 0);
  - `416` → discard the `.part`, retryable; the attempt ends and the schedule moves on rather than restarting in the same attempt (Review Focus 3);
  - any other status → classified as in Task 1, `.part` kept (nothing was written to invalidate it).

  These are the two readings of spec §1's "any other answer": a status error that wrote nothing keeps the `.part`, and a `416` discards it and moves on.
- **A `206` to a request sent without `Range`** → an error, retryable, `.part` discarded.
- **Integrity unchanged:** the md5 (or size) check runs over the whole finished `.part` read back from disk; a failure deletes it, that copy is not retried (Task 1), and the next attempt starts at byte 0.
- **Fresh start:** `download_file` deletes any pre-existing `.part` before its first attempt (Review Focus 1).

- [ ] **Step 1: Write failing tests.** Streams are generator bodies whose `yield` advances the fake clock (e.g. 1,000 bytes per simulated second = trickle; 100,000 bytes/s = healthy). Handlers inspect `request.headers.get("range")` and count requests per URL. Metadata carries an md5 unless a test says otherwise.
  - `test_slow_but_above_floor_transfer_finishes` — two candidates: the redirect at 2 × floor for 120 simulated s, plus a healthy server → completes from the redirect; the server is never requested.
  - `test_trickle_switches_and_continues_from_offset` — redirect trickles at 1,000 B/s; server answers `Range: bytes=<k>-` with `206` + `Content-Range: bytes k-(n-1)/n` and the rest → dest equals the full body, md5 passes, the server saw exactly `bytes=<k>-` where `k` is the `.part` size at abandonment (including the triggering chunk), and the redirect was abandoned at the first chunk with `t - first_byte >= TRICKLE_WINDOW_S`.
  - `test_range_answered_200_restarts_from_zero` — server ignores Range with `200` + full body → dest equals body.
  - `test_wrong_content_range_restarts_from_zero` — server answers the Range with `206` + `Content-Range: bytes 0-…` → the next request to it carries no Range; dest equals body.
  - `test_stitched_file_with_bad_md5_is_deleted_and_refetched_from_zero` — candidates redirect (trickles, abandoned at k), S1 (continues from k with corrupt bytes), S2 (healthy) → md5 fails on the stitched file, `.part` deleted, S1 requested once, S2's request carries no Range and succeeds; dest correct.
  - `test_last_non_abandoned_candidate_is_never_abandoned` — candidates redirect (trickling at 1,000 B/s), S1 answering 404, S2 trickling at 1,000 B/s → redirect abandoned once; S1 requested once; S2 requested exactly once, with `Range`, and run to completion (never abandoned, because no other candidate could still be attempted); dest correct.
  - `test_single_candidate_trickle_completes_in_one_request` — redirect-only, trickling → exactly one request, no `Range` header ever sent, completes.
  - `test_each_candidate_abandoned_at_most_once` — both candidates trickle: redirect abandoned once, server then runs to completion (never abandoned), dest correct; the server got exactly one request and the redirect at most two.
  - `test_no_abandonment_after_the_deadline` — redirect `500` and server `500` in the first pass; in the repeat phase the redirect starts trickling just before the deadline → it is not abandoned past the deadline and completes.
  - `test_no_md5_trickle_restarts_from_zero` — metadata with `size` and no md5; redirect trickles and is abandoned; the server's request carries no `Range`; dest correct.
  - `test_206_to_a_plain_request_is_rejected` — a candidate answers a request sent without `Range` with `206` → that attempt fails retryably, no `.part` kept, the next candidate succeeds; dest correct.
  - `test_416_discards_the_part_and_restarts_from_zero` (Review Focus 3).
  - `test_stale_part_from_a_previous_process_is_not_continued` (Review Focus 1) — pre-create `dest.part` with junk; the first request carries no Range; dest correct.
  - `test_a_status_error_keeps_the_continuation_part` — redirect trickles (abandoned at k), server A `500`, server B `206` from k → B saw `bytes=<k>-`.
- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_ia_client.py -q` → new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** that file, then `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(ia): trickle switch with Range continuation and whole-file integrity`.

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

### Task 5: Honest pacing samples

**Implementer model: Sonnet** (one wrapper plus one condition, and the test-harness change specified below).

**Files:**
- Modify: `packages/llama/src/llama/pipeline.py`, `packages/llama/src/llama/cli.py:_execute` (first-pass loop only)
- Test: `packages/llama/tests/test_pace_loop.py`

**Interfaces:**
- Produces: `pipeline.count_llm_calls(providers: Mapping) -> tuple[Mapping, Callable[[], int]]` — returns a mapping that answers every key the original answers (including a `defaultdict`'s missing keys, lazily) with the value wrapped: a list (ladder) → list of wrappers, a single provider → wrapper, `None` → `None`. A wrapper's `complete`/`research` increment the shared counter **before** delegating (a call that raises still counts). The callable returns the count so far.
- `_execute`: `providers, llm_calls = count_llm_calls(make_providers(config))`. In the first-pass loop, take `calls_before = llm_calls()` right before `_process(entry)`; the boundary is recorded only if `ran and reading_before is not None and llm_calls() > calls_before` (spec §5); the after-show meter read sits inside that condition, so an LLM-free show takes none. The deferred pass is unchanged (records nothing).

- **Test harness change (`test_pace_loop._drive`):** its `make_providers` stub returns `collections.defaultdict(lambda: [FakeProvider(completes=["x"] * 50)])` (`herder.fake.FakeProvider`). `_drive` gains a keyword `llm: bool | Callable[[str], bool] = True`: its `_process_show` stub calls `providers["brief"][0].complete("x")` on the providers argument it receives (the counted wrapper) before `process(pid)` whenever `llm` is `True` or `llm(pid)` is true. The default keeps every existing test's behaviour: each show "called an LLM", so recorded boundaries and meter-read order are unchanged. The new download-only tests pass `llm=False`. For an LLM-free show the second meter read is skipped, which shifts scripted meter-read sequences; that is why the default is `llm=True`. Do not change existing assertions.

- [ ] **Step 1: Write failing tests** — `test_a_show_that_called_the_llm_records_a_boundary` (default `llm=True`); `test_a_download_only_resume_records_no_boundary` (`llm=False`; stub returns a package path → `pacing-state.json` unchanged); `test_an_already_packaged_show_records_no_boundary` (`llm=False`); `test_count_llm_calls_wraps_defaultdict_and_ladders` (unit test of the wrapper, including a raising fake counted once).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**, including the `_drive` change above; existing tests are not edited.
- [ ] **Step 4: Run** `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `fix(pacing): record a show boundary only when the show called an LLM`.

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

### Task 7: The sweep — `llama run resume --all`

**Implementer model: Opus** (LLM-spend strict surface; extraction of `run_resume` and isolation semantics).

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`run_resume`, new helper and sweep, `_execute`'s no-matching-artists return, `_print_sessions`), `packages/llama/src/llama/sessions.py` (eligibility)
- Test: `packages/llama/tests/test_sweep.py` (new)

**Interfaces:**
- Consumes: `failure_kind`, `failure_record`, `KIND_*` (Task 4); `sessions.read_request`; `run_lock`, `RunMissing`, `Locked`, `STATE_RUNNING`, `iter_sessions(probe_live=True)` (Task 6).
- Produces:
  - `sessions.sweep_verdict(info: SessionInfo, run_dir: Path, now: datetime) -> str | None` — `None` = eligible; else the skip reason: `running`; `paused until HH:MM` (local time of `resume_after`, for a `paused` run whose `resume_after` is in the future); `awaiting approval`; `needs attention`, which is any of:
    - a `paused` or `incomplete` run with any failure whose `failure_kind` is not `download`/`archive` (the same test for both states);
    - a run with neither `criteria.json` nor `request.json`;
    - a run with no `session.json` whose `request.json` has `auto: false`.

    Eligible: `paused` with `resume_after` past or absent, and `incomplete`, each when every failure (if any) is `download` or `archive`; a marker-less run qualifies only with `auto: true` or no `auto` key. It reads `run_dir/session.json` existence and `request.json` via `sessions.read_request`. `complete` runs never reach it (`attention_sessions`).
  - `cli._resume_run(config, ia, ledger, ws: RunWorkspace, *, auto: bool, full_rationale: bool, pace: PaceOptions, record_crash: bool) -> None` — takes `run_lock(ws.dir, blocking=False)` itself (raising `Locked`/`RunMissing` to the caller), then runs today's `run_resume` body. With `record_crash=True`, any `Exception` (including `typer.Exit` with a non-zero code) is caught, `mark_incomplete(ws, outcome=None, failures=[failure_record(None, exc, kind=KIND_OTHER)])` is written while the lock is still held, and the exception is re-raised. The failure's `error` is `exit <code>` for a `typer.Exit`, else per `failure_record` (Task 4). `typer.Exit(0)` is not a crash. `KeyboardInterrupt` is never caught.
  - `run_resume(session: str | None = Argument(None), all_runs: bool = Option(False, "--all", help=...), ...)`: exactly one of `session`/`--all` (else stderr error, exit 1); `--all` with `--interactive` → error, exit 1. The single-session form calls `_resume_run(..., record_crash=False)` and converts `Locked`/`RunMissing` exactly like `_run_locked` (Task 6).
- Sweep (spec §6): `--wait/--no-wait` defaults to `--no-wait` when unspecified (`wait=None` → `False`); `--max-wait` and `--no-pacing` pass through. List `attention_sessions(config.root)`, compute `sweep_verdict` for each, print one line per skipped run (`skip <id>: <reason>`), then resume the eligible ones oldest `updated_at` first, one at a time, in-process, `auto=True`, each under a `== <id>` header. Per-run result: `Locked` → `running` (no marker); `RunMissing` → `gone` (no marker, not an error); a caught exception → `error: <message>`; otherwise the run's `session_state` after the resume. After each resume, if that state is `paused`: stop, print the eligible ids not reached, go to the summary. Summary: one line per resumed run with its result. Exit 0 when every resumed run ended `complete` or nothing was eligible (print `nothing to resume`); else exit 1 (`incomplete`, `paused`, `error`, or any other state such as `awaiting-approval`; `running` and `gone` do not by themselves make it 1).
  - `_execute`: the `no matching artists found` return writes `mark_complete(ws, "no matching artists found")` first.
  - `_print_sessions` prints `(run)` for a failure whose `show` is `None`.

- [ ] **Step 1: Write failing tests** (`test_sweep.py`; stub `_execute` or `process_show` as `test_pace_loop`/`test_run_namespace` do; build runs with `mark_*` and `failure_record`):
  - `test_eligibility_per_state_and_kind` — parametrized over: paused past / paused absent / paused future (`paused until HH:MM`) / `paused-past-with-transport` (needs attention) / `paused-past-with-download` (eligible) / awaiting / incomplete no failures / incomplete all `download`+`archive` / incomplete with one each of `transport`, `llm`, `rate-limited`, `other` (needs attention) / legacy `download of …` record (eligible) / legacy `boom` record (needs attention) / no criteria and no request (needs attention) / `no-marker-auto-false` (needs attention) / `no-marker-auto-true` (eligible) / `no-marker-no-auto-key` (eligible).
  - `test_live_runs_are_skipped_as_running` (a real flock held on the run's `.lock`).
  - `test_oldest_first_and_summary` — three eligible runs resumed in `updated_at` order; summary lists all three.
  - `test_stops_on_a_pause` — the second run's stub writes `mark_paused`; the third is listed as not reached and not resumed; exit 1.
  - `test_one_run_raising_does_not_stop_the_others_and_writes_a_marker` — the first run's stub raises `RuntimeError("boom")`; the second still runs; the first's `session.json` is `incomplete` with one failure `{"kind": "other", "error": "boom"}`; the summary says `error: boom`; exit 1; a second sweep skips it as `needs attention`; `run list` prints that failure under `(run)`.
  - `test_crash_marker_for_typer_exit_reads_exit_code` — the first run's stub raises `typer.Exit(1)` → its failure's `error` is `exit 1` and the summary says `error: exit 1`.
  - `test_keyboard_interrupt_stops_the_sweep` — `KeyboardInterrupt` propagates; no marker written.
  - `test_run_that_turned_live_reports_running` — monkeypatch the helper's lock to raise `Locked` → result `running`, no marker.
  - `test_a_run_removed_before_its_turn_is_reported_gone` (Review Focus 5).
  - `test_no_wait_is_the_default_for_the_sweep` — capture the `PaceOptions` reaching `_execute`: `wait is False`; `--wait` passes `True`; `--max-wait 30m` and `--no-pacing` pass through.
  - `test_exit_codes` — all complete → 0; nothing eligible → 0 and `nothing to resume`; one ends `awaiting-approval` → 1.
  - `test_session_and_all_are_exclusive`, `test_all_rejects_interactive`.
  - `test_single_resume_still_refuses_a_live_run_and_records_no_crash_marker`.
  - `test_no_matching_artists_marks_the_run_complete` — `run_discover` stub returns `[]` → state `complete`, outcome `no matching artists found`.
- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_sweep.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(runs): llama run resume --all sweeps resumable runs in one pass`.

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
