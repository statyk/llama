### Spec Compliance
- ✅ Spec compliant. Task 1 matches spec §1 (everything except the trickle switch) and the brief. Line numbers below are for `packages/llama/src/llama/ia_client.py` at 1517fa0 unless a test file is named.
  - The constants are exact: CONNECT 10.0, STALL 20.0, DEADLINE 60.0, SLEEP 1.0/4.0 (ia_client.py:24-31). The `TRICKLE_*` constants are not added yet. That is correct for this task: the brief scopes it as "everything except the trickle switch", and Task 2 uses them.
  - `IADownloadError(IAError)` exists. Its message starts `download of <filename> failed:` and lists every candidate URL with that URL's last error (download_file tail, around :298-299).
  - The `clock`/`sleep`/`rng` injectables are keyword-only. Existing parameters are unchanged, and so are `_get` and `_throttle`.
  - Candidates follow the spec. The redirect comes first. Then each `workable_servers` entry in order, or `d1`/`d2` only when that list is missing or empty. Duplicates are removed. With no `dir`, only the redirect is used. When `self.metadata` raises `IAError`/`ValueError`, or returns a non-dict, the result is the redirect alone with no size. `quote()` keeps `/` (`_download_candidates`, around :177-208).
  - Each attempt calls `_throttle()` and then `client.stream(..., timeout=Timeout(20, connect=10))`. There is no total-time bound (`_attempt`).
  - Classification is correct:
    - 5xx, 408 and 429 are retryable. Other non-2xx statuses are not.
    - Every `httpx.HTTPError` is retryable and deletes the `.part`. This covers TransportError, TooManyRedirects, DecodingError and a body dying mid-stream.
    - An md5 or size mismatch deletes the `.part` and is not retryable.
    - md5 is computed from the whole finished file read back from disk (`_file_md5`), after the write handle has closed.
  - The schedule is correct:
    - The first pass gives every candidate one attempt in order, with `rng.uniform(1, 4)` sleeps between them, and is never cut short.
    - `first_pass_end` is taken after the first pass.
    - Repeats cycle through the retryable candidates. The deadline is checked both before and after each pause, so no attempt starts past it. An attempt in flight is never interrupted.
    - `slot_wait` is subtracted (always 0 here).
    - Exhaustion deletes the `.part` (`finally`) and raises. `Retry-After` is ignored.
  - Download integrity, the strict surface, was checked exhaustively. `tmp.replace(dest)` is reached at only two sites, and both are gated on `_attempt(...).ok`. `ok=True` is returned only after the md5 check passes, or after the size check passes when there is no md5, or when neither is known ("as today", spec-sanctioned). Every failure path inside `_attempt` unlinks the `.part`: non-2xx, any httpx error, md5 mismatch, size mismatch. Any other exit from `download_file` (an OSError, KeyboardInterrupt, the exhaustion raise) passes through `finally: tmp.unlink(missing_ok=True)`. I found no path that renames an unverified or partial file when an md5 or size is known.
  - All 16 brief-listed tests are present with the brief's names and assertions. Review Focus 2 is covered by `test_unusable_metadata_degrades_to_redirect_only` (500 and non-JSON), `test_unusable_size_means_no_size_check` ("abc", None, absent, no entry, `files` not a list) and `test_duplicate_servers_are_tried_once`.
- ⚠️ Cannot verify from the diff:
  - The full-suite run the report quotes (3840 passed, 26 warnings). The report gives no baseline warning count, so I cannot confirm those 26 warnings existed before this change. The implementer ran `-W error` on test_ia_client.py (42 passed), and the only production caller (stages/package.py:52) is replaced by fakes in the tests, so this change is unlikely to be their source. I did not re-run the suite.
  - Whether the `slot_wait_s` hook is subtracted with the right sign. It is always 0 until Task 3 and cannot be tested here.

### Strengths
- One attempt lives in one method (`_attempt` returns a frozen `_Attempt` outcome). The schedule in `download_file` only classifies outcomes and never touches the stream. This is the right seam for Task 2 (Range/416/trickle) and Task 3 (`slot_wait_s`).
- Verifying the file read back from disk rather than a running hash is implemented as the brief requires, ready for stitched files in Task 2.
- The `finally` unlink is a belt-and-braces guarantee that no `.part` survives any exit. The implementer also found, through their own mutation M9, that this guarantee masks the per-attempt unlink. They pinned that unlink with the no-`.part`-at-next-request assertion in `test_mid_stream_failure_is_retryable` (test_ia_client.py, `server` handler).
- The tests use a fake clock in which `sleep` advances time and handlers can `advance`. They are fully deterministic, with `Random(0)`, MockTransport and no real sleeps.
- `test_deadline_counts_from_the_end_of_the_first_pass` covers the subtle rule that a 500 s first pass must not eat the 60 s repeat budget.
- The implementer's mutation sweep (M1-M9, with predictions recorded) is credible. I independently confirmed one of its cases (below).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The deadline's lower bound is not pinned.** `test_every_server_failing_raises_after_first_pass_and_deadline` (test_ia_client.py:~281-298) asserts only that the last attempt started *before* `first_pass_end + DOWNLOAD_DEADLINE_S`. It never asserts that repeats kept going until the deadline.
   - I checked this with a scratch-copy mutation (`git archive` into the scratchpad, `python -m pytest` with PYTHONPATH shadowing, `llama.__file__` verified inside the copy, `PYTHONDONTWRITEBYTECODE=1`, prediction logged first). With `expired()`'s `>= DOWNLOAD_DEADLINE_S` changed to `>= 10.0`, **all 42 tests pass**, as predicted.
   - Fix: one line at the end of that test, `assert clock.now >= first_pass_end + DOWNLOAD_DEADLINE_S`. It holds because the loop can only exit with every candidate retryable once `expired()` is true.
   - The control mutant passed as expected: removing the post-pause `if expired(): break` was caught by that test.
   - This is plan-literal: the brief's wording for the test asks only for the upper bound.
2. **A non-transport httpx error from the metadata fetch can escape `download_file`.** `_download_candidates` catches only `(IAError, ValueError)` around `self.metadata(identifier)`, which follows the brief literally. But `_get` (ia_client.py:100-124) catches only `httpx.TransportError`, so an uncached metadata fetch that raises `httpx.TooManyRedirects` or `DecodingError` would propagate out of `download_file`. That contradicts the brief's "No `httpx` exception ever escapes `download_file`".
   - In production this cannot be reached: `build_package` calls `ia.metadata(show.identifier)` (stages/package.py:41) before any `download_file`, so the same error would have surfaced there first and the metadata would be cached on success.
   - Fix: add `httpx.HTTPError` to that except tuple.
3. **Untested edge paths:** `DecodingError` (only TooManyRedirects stands in for "other HTTPError"), metadata that is valid JSON but not a dict, and an OSError raised mid-write being cleaned up by the `finally`. The code handles all three correctly by inspection.
4. **3xx is now non-retryable** (`_attempt`: a non-2xx status that is not 5xx/408/429). This was disclosed by the implementer. It is reachable only with a 3xx carrying no Location, since the sole production client has `follow_redirects=True` (cli.py:124 is the only construction). It is acceptable as a deterministic answer, and the old behaviour (retrying the same URL 3 times) failed the file anyway.
5. `test_sleeps_between_attempts_are_short_and_random` hard-codes `1.0 <= s <= 4.0` instead of importing `DOWNLOAD_SLEEP_MIN_S`/`MAX_S`. The test still passes if the constants are retuned within that range. This is cosmetic.
6. `self.rng = rng or random.Random()` relies on Random being truthy, which is fine. `rng if rng is not None else ...` would state the intent better. This is cosmetic.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation meets spec §1 and the brief, and the download-integrity surface holds on every path: nothing is renamed into place without the md5 or size check passing when one is known, and no `.part` survives any exit. The remaining findings are test-strength and edge-hardening polish. The most useful of them is a one-line lower-bound assertion on the deadline, which a scratch mutation showed is currently unpinned.
