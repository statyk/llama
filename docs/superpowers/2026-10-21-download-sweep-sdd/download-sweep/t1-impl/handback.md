# Task 1 handback: server fallback, download timeouts, classification and schedule

**Status: DONE**
**Commit:** `1517fa0 feat(ia): download fallback to listed servers, short timeouts, bounded schedule` (branch download-sweep)

## What was implemented (packages/llama/src/llama/ia_client.py)
- Module constants `DOWNLOAD_CONNECT_TIMEOUT_S = 10.0`, `DOWNLOAD_STALL_TIMEOUT_S = 20.0`, `DOWNLOAD_DEADLINE_S = 60.0`, `DOWNLOAD_SLEEP_MIN_S = 1.0`, `DOWNLOAD_SLEEP_MAX_S = 4.0`; private `_DOWNLOAD_TIMEOUT = httpx.Timeout(STALL, connect=CONNECT)`, `_RETRYABLE_STATUS = {408, 429}`. The trickle constants are NOT added (they belong to Task 2, which uses them).
- `class IADownloadError(IAError)`. Message: `download of <filename> failed: <url> -> <last error>; <url> -> <last error> (<N> attempts)`, naming every candidate URL in order.
- `IAClient.__init__` gains keyword-only `clock=time.monotonic`, `sleep=time.sleep`, `rng=None` (→ `random.Random()`), stored as `self.clock/self.sleep/self.rng`. Existing parameters unchanged; `_get` and `_throttle` unchanged.
- `_download_candidates(identifier, filename) -> (urls, size)`: redirect URL first; then `https://<server><dir>/<quote(filename)>` for `workable_servers` in order, or — only when that is missing/empty — `d1`, `d2`; de-duplicated; non-string/empty servers skipped; no usable `dir` → redirect only. `self.metadata` raising `IAError`/`ValueError`, or returning a non-dict → redirect only, size None. `size` = `int(entry["size"])` for the matching `files` entry, None when absent/non-numeric/`files` not a list.
- `_attempt(url, tmp, *, md5, size) -> _Attempt(ok, error, retryable, slot_wait_s=0.0)`: `_throttle()`, `client.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT)`, non-2xx → `HTTP <n>` (retryable iff >=500 or 408/429); body written to `tmp`; any `httpx.HTTPError` (transport, TooManyRedirects, DecodingError, mid-stream death) → retryable, `.part` deleted. Then verification over the whole file read back from disk: md5 (`_file_md5`, 1 MiB blocks) or, with no md5 and a known size, the byte count; mismatch → `.part` deleted, not retryable. The transfer loop lives only here (for Task 2). `slot_wait_s` is the Task 3 hook (always 0 now).
- `download_file` (signature unchanged): first pass = one attempt per candidate in order, `_pause()` (= `self.sleep(self.rng.uniform(1.0, 4.0))`) between attempts, never cut short. Then `first_pass_end = self.clock()`; loop while any candidate's last error was retryable and the deadline (`clock - first_pass_end - slot_wait >= 60`) has not passed: pause, re-check the deadline, attempt the next retryable candidate (itertools.cycle over candidates in order), accumulating `slot_wait_s` from repeat attempts. An in-flight attempt is never interrupted. Success → `tmp.replace(dest)`. A `finally` unlinks any `.part` on every exit (exhaustion, or an unexpected exception such as an OSError). `Retry-After` ignored.

## Tests (packages/llama/tests/test_ia_client.py)
`make_client` gained a `FakeClock` (sleep advances it; handlers may `advance`), `rng=random.Random(0)`, and an optional `metadata` dict served at `/metadata/<id>` (otherwise the metadata request reaches the handler; the pre-existing download tests' handlers answer it with non-JSON → redirect-only, which they pass through unchanged).
All brief-listed tests are present: `test_500_on_redirect_falls_back_to_listed_server`, `test_every_server_failing_raises_after_first_pass_and_deadline`, `test_hanging_redirect_does_not_starve_listed_servers`, `test_4xx_moves_on_then_succeeds`, `test_all_4xx_fails_after_one_pass`, `test_md5_mismatch_on_one_server_then_success`, `test_md5_mismatch_copy_is_checked_once`, `test_too_many_redirects_is_caught`, `test_size_check_when_no_md5`, `test_mid_stream_failure_is_retryable`, `test_missing_server_fields_mean_redirect_only`, `test_d1_d2_used_only_when_workable_servers_empty`, `test_listed_server_url_quotes_but_keeps_slash`, `test_unusable_metadata_degrades_to_redirect_only` (500s, non-JSON), `test_duplicate_servers_are_tried_once`, `test_download_uses_short_timeouts`.
Added beyond the list: `test_408_429_and_5xx_are_retried` (param 408/429/503), `test_md5_mismatch_copy_is_skipped_by_repeat_attempts` (a bad copy is skipped while another retryable one is repeated), `test_deadline_counts_from_the_end_of_the_first_pass` (a 500 s first pass must not consume the repeat budget), `test_unusable_size_means_no_size_check` (param: "abc", None, absent, no entry, files not a list — covers Review Focus 2's size/entry cases), `test_sleeps_between_attempts_are_short_and_random`, `test_download_error_is_an_ia_error`. `test_mid_stream_failure_is_retryable` also asserts the next candidate starts with no `.part` on disk.

## TDD evidence
RED (after adding only the constants, the `IADownloadError` class and the `__init__` injectables, so the failures are behavioral, not import errors; before that the module failed at import on `DOWNLOAD_CONNECT_TIMEOUT_S`):
`./.venv/bin/pytest packages/llama/tests/test_ia_client.py -q` → `27 failed, 14 passed` (every new behavior test failed, e.g. `IAError: download of t.mp3 failed after 3 attempts: Server error '500 Internal Server Error' for url 'https://archive.org/download/x/t.mp3'`; the 14 passes were the 13 pre-existing tests + `test_download_error_is_an_ia_error`).
GREEN: `./.venv/bin/pytest packages/llama/tests/test_ia_client.py -q` → `41 passed`; after the two added tests, `./.venv/bin/pytest packages/llama/tests/test_ia_client.py packages/llama/tests/test_stage_package.py -q` → `54 passed`; with `-W error` on test_ia_client → `42 passed` (no warnings from these tests).
Full suite: `./.venv/bin/pytest -q` → `3840 passed, 1 skipped, 8 deselected, 26 warnings in 107.37s` (baseline 3811 passed, 1 skipped; +29 new test cases). After that run I reordered one import line (`itertools` before `json`) and re-ran `test_ia_client.py test_stage_package.py test_replay.py` → `138 passed`.

## Mutation check (scratch copy under the scratchpad, `python -m pytest` with PYTHONPATH shadowing verified via `llama.__file__`, PYTHONDONTWRITEBYTECODE=1; predictions named before each run)
M1 deadline from call start → caught by test_deadline_counts_from_the_end_of_the_first_pass (as predicted). M2 md5 mismatch retryable → caught by md5_copy_is_checked_once + md5_..._skipped_by_repeat_attempts. M3 d1/d2 always appended → d1_d2 test. M4 4xx retryable → all_4xx + duplicate_servers. M5 size check removed → size_check_when_no_md5. M6 no download timeout → short_timeouts. M7 no dedupe → duplicate_servers + d1_d2. M8 408/429 not retryable → 408_429 params. M9 no `.part` delete after a transport error → initially SURVIVED (masked by `wb` truncation and the `finally`); pinned by the new no-`.part`-at-next-request assertion, now caught. All predictions matched.

## Files changed
- packages/llama/src/llama/ia_client.py
- packages/llama/tests/test_ia_client.py

## Self-review findings / judgment calls for the reviewer
1. **3xx responses** (only reachable if redirect-following fails without raising, e.g. a 3xx with no Location) are classified as not retryable, like other non-success, non-5xx/408/429 statuses. The old code retried them (raise_for_status raised). The spec does not classify 3xx; I treated it as a deterministic answer. Easy to flip if the reviewer prefers retryable.
2. **Any 2xx is accepted** as a body (as before: raise_for_status accepted all 2xx). Task 2 will distinguish 206 for Range.
3. **`workable_servers` non-empty but all junk** (non-strings) → uses that list (yielding no servers), not d1/d2 — faithful to "only when missing or empty".
4. **md5 comparison stays case-sensitive**, as before.
5. `_throttle` still uses real `time.monotonic/time.sleep` (unchanged, since `_get` shares it); tests pass `rate_limit_s=0`. In production throttle time counts toward the deadline on the real clock, which is harmless.
6. A metadata fetch that is not cached and fails costs `_get`'s own retries (1 s + 2 s backoff) before degrading to redirect-only. In production `build_package` has already fetched and cached it.
7. md5 mismatch error text changed from `md5 mismatch downloading <file>` to `md5 mismatch (got X, expected Y)` inside the IADownloadError message; the message still starts `download of <file> failed:`. No caller matched the old text (grep).
8. No conflict found between the brief and spec §1.

## Concerns
None blocking.
