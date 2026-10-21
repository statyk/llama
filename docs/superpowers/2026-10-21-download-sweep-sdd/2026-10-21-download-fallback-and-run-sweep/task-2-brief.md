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

