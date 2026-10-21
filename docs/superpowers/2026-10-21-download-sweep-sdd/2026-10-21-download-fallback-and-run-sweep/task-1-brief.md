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

