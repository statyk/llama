# Task 2 handback: trickle switch with Range continuation

Status: DONE_WITH_CONCERNS (one deliberate interpretation, flagged below for review)

Commits (branch download-sweep):
- 6c19958 feat(ia): trickle switch with Range continuation and whole-file integrity
- be153c2 test(ia): pin the sliding trickle window and a transport error keeping the .part
- 5300f01 test(ia): pin the 200 rewrite and both halves of the post-abandonment attempt

Final: `./.venv/bin/pytest -q` -> 3861 passed, 1 skipped, 8 deselected (baseline 3840 + 21 new test cases).

## What was implemented (packages/llama/src/llama/ia_client.py)
- Constants `TRICKLE_FLOOR_BPS = 10_000`, `TRICKLE_WINDOW_S = 30.0` (module level, verbatim).
- `_TrickleMonitor`, one per request (including the re-issued no-Range request): samples
  (arrival time, cumulative bytes) per chunk; the window opens at the first body byte; at a chunk
  with `t - first_byte_t >= TRICKLE_WINDOW_S`, b0 = the latest sample at or before `t - W`;
  trickling iff `total - b0 < FLOOR * W`. Samples are pruned with a deque (cutoff only grows).
- `_attempt(..., may_abandon)`: still one attempt in one method.
  - `offset = tmp.stat().st_size` (0 when absent); `offset > 0` sends `Range: bytes=<offset>-`.
  - 416 with Range -> discard .part, retryable, attempt ends.
  - other non-2xx -> classified as in Task 1, .part untouched (Task 1's unlink here removed).
  - 206 without Range -> retryable error, .part discarded.
  - 206 whose Content-Range (strict `bytes N-M/T` fullmatch) does not start at offset, or whose
    total differs from a known size (`*` counts as differing) -> discard, re-issue same URL without
    Range in the same attempt (bounded: the re-issue has offset 0, so it cannot loop).
  - matching 206 -> append ("ab"); 200 (any non-206 2xx) -> "wb" from byte 0.
  - per chunk: write, then trickle check; abandon iff monitor trips AND `f.tell() < size` (when
    size known) AND `may_abandon()`. Abandonment returns `_Attempt(..., retryable=True,
    trickled=True)`; the .part is kept only when md5 is given, else deleted.
  - transport/httpx errors discard the .part only if this attempt wrote to it (`wrote` flag; "wb"
    truncation counts as writing). A 206 append dying before its first byte keeps the .part (nothing
    written).
  - integrity check unchanged: md5 (or size) over the whole finished .part read from disk.
- `download_file`:
  - deletes any pre-existing .part before the first attempt (Review Focus 1).
  - `abandoned` set; `may_abandon(url)` = url not abandoned AND some other candidate neither
    abandoned nor known non-retryable (`retryable.get(d, True)`) AND (in first pass OR not expired()).
  - slot_wait accumulation moved into `attempt()` (reset to 0 at first-pass end, as before).
- Carried-over item 2: `_download_candidates` also catches `httpx.HTTPError` from `metadata()`.

## Interpretation to review (the concern)
**The attempt an abandonment promises always starts.** Condition 3 ("another attempt will actually
start", evaluated as clock-now vs deadline at abandonment time) is not sufficient on its own: the
schedule then pauses 1-4 s and re-checks the deadline, so an abandonment at deadline-0.5 s would be
followed by NO attempt and the file would fail with a .part that a slow transfer would have
finished. I added an `owed` flag: after a trickle abandonment the next repeat attempt skips both
deadline checks (loop top and post-pause). Termination still holds: each candidate is abandoned at
most once, so there are at most len(candidates) owed attempts. This is a narrow exception to spec §1
"The deadline is checked before starting an attempt"; documented in the `download_file` docstring.
Pinned by `test_abandonment_just_before_the_deadline_still_gets_its_next_attempt` (both halves
mutation-caught). If the reviewer prefers the literal reading, delete `owed` (3 lines) and that test.

## Smaller judgment calls (not conflicts)
- "md5 known" means the `md5` argument of `download_file` (Task 1's convention), not the metadata md5.
- Condition 4 is `f.tell() < size`; a .part already over `size` is unreachable (abandonment only
  keeps a .part < size) and would run to completion and fail integrity.
- A 416 to a request WITHOUT Range stays a plain non-retryable 4xx (only a ranged 416 is special).
- `_throttle()` now runs before each request, including the in-attempt re-issue.
- Brief's `test_each_candidate_abandoned_at_most_once` as specified is actually blocked by
  condition 2 (no other candidate), not condition 1; I added
  `test_an_abandoned_candidate_is_not_abandoned_again` (3 candidates) where ONLY condition 1 prevents
  the second abandonment.

## Tests added (packages/llama/tests/test_ia_client.py)
All 14 named in the brief, plus: `test_metadata_http_error_means_redirect_only` (carried item 2),
`test_an_abandoned_candidate_is_not_abandoned_again`, `test_full_part_is_never_abandoned`
(condition 4), `test_abandonment_just_before_the_deadline_still_gets_its_next_attempt`,
`test_a_transfer_that_slows_to_a_trickle_is_abandoned` (sliding vs cumulative window),
`test_wrong_content_range_restarts_from_zero` parametrized wrong-start / wrong-total,
`test_a_status_error_keeps_the_continuation_part` parametrized status / connect-error.
Carried item 1: `test_every_server_failing_raises_after_first_pass_and_deadline` now asserts
`clock.now >= first_pass_end + DOWNLOAD_DEADLINE_S` (the 10.0 mutant is now caught).
Helpers: `stream()` (lazy generator body advancing the fake clock per chunk), `serve()` (honours
Range with 206 + Content-Range, records Range headers), `SlowToClose` (a body whose close takes 1 s).

## TDD evidence
RED (constants only added so the module imports):
`./.venv/bin/pytest packages/llama/tests/test_ia_client.py -q`
-> 14 failed, 47 passed: metadata_http_error, trickle_switches, range_answered_200,
wrong_content_range[wrong-start], [wrong-total], stitched_bad_md5, last_non_abandoned,
each_candidate_abandoned_at_most_once, an_abandoned_candidate_is_not_abandoned_again,
abandonment_just_before_the_deadline, no_md5_trickle, 206_to_a_plain_request, 416, status_error_keeps.
The 5 that passed at RED (slow_but_above_floor, single_candidate, full_part, no_abandonment_after_
deadline, stale_part) are properties Task 1's no-switch code already had; mutation pins each.
GREEN: same command -> 61 passed (then 63 after the two extra tests); full suite 3861 passed, 1 skipped.

## Mutation check (scratch `git archive` copy, PYTHONPATH-shadowed, sentinel-verified, no bytecode)
26 meaningful mutants, each with its predicted red test named first; all CAUGHT by the predicted test
after fixes: conditions 1/2 (two variants)/3/4, both owed halves, no-md5 keeps part, Content-Range
start and total, 416 branch and 416-keeps-part, 206-to-plain accepted, stale part kept, status error
discards part, transport error always/never discards, check-before-write, window opens late,
cumulative-not-sliding, floor comparison flipped, 200 appends, metadata httpx error, deadline 10 s,
trickle not retryable, no abandoned bookkeeping.
First run had 2 survivors -> fixed by test tightening (commit 5300f01): "200 appends" (test lacked
`seen == [REDIRECT, SERVER]`; md5 failure + redirect retry masked it) and "owed loop-top" (unreachable
without time passing between abandonment and loop check; now the response close advances the clock).
Seed robustness: the test file passes under rng seeds 1-30 (scratch sweep), 0 failures.

## Self-review findings (fixed before commit)
- FP drift: a stream starting at a non-integer clock can close its window one chunk late; two tests
  that assumed an exact boundary there were made drift-tolerant (arrival-derived offsets; 0.1 s chunks).
- Replaced an `assert` in `expired()` with an explicit `in_first_pass` flag.

Files changed: packages/llama/src/llama/ia_client.py, packages/llama/tests/test_ia_client.py.
