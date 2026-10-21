### Spec Compliance
- ✅ Spec compliant with one disclosed interpretation that deviates from the literal spec text. I judge it the correct reading, but it needs a ruling recorded in the spec (see Minor 1). Every brief item is present: monitor, per-chunk order, the four abandonment conditions, the `.part` rules, the Range/206/200/416 handling, the 206 to a plain request, unchanged integrity, the fresh start, all 14 named tests, and both carried-over items.
- ⚠️ Cannot verify from diff:
  - Whether Task 1's callers of `download_file` always pass `md5` when the metadata has one. "md5 known" here means the `md5` argument (`ia_client.py:230`, `if not md5`), not the metadata md5. If a caller passes `md5=None` while the metadata has one, continuation is disabled (safe) and the size check applies. This is Task 1's convention; I did not crawl `build_package`.
  - Task 3 interaction (named risk, not a defect now). `expired()` (`ia_client.py:287-288`) subtracts only the slot waits of finished attempts. A condition-3 check made mid-attempt will therefore count the in-flight attempt's slot wait as elapsed. That errs conservative (fewer abandonments), but Task 3 should know.

#### Strict surface: download integrity (exhaustive)
**What can be renamed into place.** `tmp.replace(dest)` runs only after `attempt(url).ok` (`ia_client.py:321-323`, `344-346`). `ok` is returned only after the whole-file check: md5 read back from disk (`236-240`), or the size check (`241-245`). The `finally` (`348`) removes the `.part` on every other exit, including non-httpx exceptions such as an `OSError`. With neither md5 nor size the file is renamed unchecked, which the spec says is "as today".

**Stitching.**
- Continuation happens only with a kept `.part`, and a kept `.part` exists only after a trickle abandonment under an md5 (`227-233`). Without an md5 the abandonment discards the `.part`, so no stitched file is ever checked by size alone. ✅
- `offset` is `tmp.stat().st_size` (`171`), never a counter. ✅
- The `Content-Range` check (`248-255`) is a strict `fullmatch`: the start must equal `offset`, and when `size` is known the total must equal it, with `*` counting as mismatched. ✅
- Append mode (`"ab"`) puts the file position at the end of the file, so `f.tell()` in condition 4 counts the whole file. ✅
- A 206 whose range ends early, or a short chunked body, appends short. The md5 check catches it and deletes the `.part`. No integrity breach (see Minor 3 for the liveness cost).

**Which `.part` survives which failure.**

| Failure | Effect on the `.part` | Where |
|---|---|---|
| Status error | untouched | `194-196` |
| Connect error, or a transport error before the first byte of a 206 append | untouched (`wrote` is False) | `223-225` |
| Transport error after this attempt wrote, including a `"wb"` truncation | discarded | `208`, `211`, `223-224` |
| Trickle abandonment with md5 | kept | `227-233` |
| Trickle abandonment without md5 | discarded | `227-233` |
| Ranged 416 | discarded, retryable, attempt ends | `190-193` |
| 206 to a plain request | discarded, retryable | `197-200` |
| Mismatched 206 | discarded, re-issued without Range in the same attempt; bounded, because the re-issue has offset 0 and cannot reach `continue` again | `201-205` |
| Integrity failure | deleted | `239`, `244` |
| Stale `.part` from a killed process | deleted before the first attempt | `316` |

All of this matches the brief.

**Termination.**
- Condition 1, each candidate abandoned at most once: `292`.
- Condition 2, the last candidate not abandoned and still retryable is never abandoned: `294-296`, using `retryable.get(d, True)`, so an untried candidate counts.
- Condition 3: `297`.
- Condition 4: `213`.
- Abandonments are therefore at most `len(candidates) - 1`.
- After the deadline, condition 3 is false in the repeat phase. A post-deadline attempt (the "owed" one) can therefore never be abandoned: it runs to completion or fails. If it fails, `owed` resets (`343`) and the loop exits on `expired()`. So at most one owed attempt runs past the deadline.
- The ring never re-picks the just-abandoned URL, because condition 2 guaranteed another retryable candidate exists.
- If the abandoned candidate was the last one of the first pass, the repeat loop starts from a fresh `first_pass_end` with that candidate retryable (`325-335`), so the promised attempt does start.
- I confirmed by mutation that conditions 3 and `owed` are load-bearing (see below).

### Strengths
- One attempt stays one method. The in-attempt re-issue loop is bounded by construction (offset 0 cannot reach `continue`). `_throttle` runs per request inside `_attempt` (`185`), so Task 3's slot acquire can wrap `self._attempt(...)` at `305` cleanly.
- `_TrickleMonitor` (`80-105`) is small and correct:
  - The window opens at the first byte.
  - `b0` is the latest sample at or before the cutoff. The invariant holds because the first sample is at or before the cutoff once the window is open, and the pruning pops only while `samples[1]` is at or before the cutoff.
  - The sliding window is pinned separately from a cumulative one by `test_a_transfer_that_slows_to_a_trickle_is_abandoned` (`test_ia_client.py:852-884`).
- The `wrote` flag (`172`, `208`, `211`) implements "an attempt that writes nothing leaves the `.part` untouched" precisely. It is pinned for both status and connect failures (`test_ia_client.py:835-849`).
- The tests are strong. They use exact Range-header sequences (`ranges == [f"bytes={K}-"]`). The write-then-check order is pinned through `K` including the triggering chunk (`test_ia_client.py:508`). `test_an_abandoned_candidate_is_not_abandoned_again` (`625-649`) correctly isolates condition 1, which the brief's own test cannot (the implementer spotted that). `test_416…` (`785-815`) pins both "retryable" and "ends the attempt" through the `seen` sequence.
- Carried item 1: `test_ia_client.py:391` pins the deadline's lower bound.
- Carried item 2: `ia_client.py:128` catches `httpx.HTTPError`. Mutant B (revert the catch) went red on `test_metadata_http_error_means_redirect_only` as predicted.
- Mutants I ran myself in a scratch `git archive` copy (PYTHONPATH-shadowed, `llama.__file__` verified inside the scratch tree, `PYTHONDONTWRITEBYTECODE`, `-p no:cacheprovider`). Each had its predicted red test named first:
  - **B**, metadata catch reverted: CAUGHT by the predicted test.
  - **C**, `owed` never set: CAUGHT by `test_abandonment_just_before_the_deadline_still_gets_its_next_attempt`. The failure is exactly the stranded-file case: "trickling below… ; HTTP 500 (11 attempts)".
  - **D**, condition 3 removed: CAUGHT by `test_no_abandonment_after_the_deadline`.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The `owed` exception is a deviation from spec text and needs a recorded ruling.** It is at `ia_client.py:331`, `335`, `338` and `343`, and in the docstring at `272-275`. Spec §1 says "The deadline is checked before starting an attempt". The owed attempt skips that check.
   - I agree with the deviation on the merits. The literal reading breaks the spec's own sentence "an abandonment is allowed only while another attempt will still start": condition 3 is evaluated at abandonment time, and the 1-4 s pause plus the response close can cross the deadline. Mutant C demonstrates the resulting failure: the file fails while holding a `.part` that a slow transfer would have finished.
   - It is bounded: at most one post-deadline attempt, which cannot itself be abandoned. In effect it is the interrupted in-flight attempt, which the spec already lets finish.
   - Action: amend spec §1's deadline sentence (for example "…except the attempt an abandonment promised") so the binding text and the code agree. Do not delete `owed`.
2. **A transport error mid-append (206, `"ab"`) discarding the `.part` is unpinned.** I ran mutant A: `wrote = True` at `ia_client.py:211` changed to `wrote = wrote`, so only a `"wb"` open marks the attempt as having written. The whole `test_ia_client.py` suite stayed green (63 passed). No integrity exposure, because the md5 still guards any stitched result. But the brief's "any other failure of an attempt that wrote to the `.part` … discard it" has no test on the append path. Fix: add a test where a 206 continuation's body dies after one chunk, and assert the next candidate's request carries no Range.
3. **A stitched md5 failure blames only the finishing candidate** (`ia_client.py:236-240`; `retryable[url] = False` at `311`). If the corrupt bytes came from the abandoned prefix candidate, that candidate stays retryable (from its abandonment), while the possibly good finisher is excluded for the rest of the call. Example with two candidates and a corrupt redirect: the stitch fails, S1 is excluded, the redirect restarts from 0, fails md5 again, and the file fails although S1 alone would have succeeded. Integrity holds; the cost is liveness (a later sweep retries). This is plan-mandated: the brief's `test_stitched_file_with_bad_md5…` asserts S1 is requested once. Worth a spec note: either "a stitched mismatch excludes the finisher" as a ruling, or keep the finisher retryable since its own copy was never checked whole.
4. **`_continues` does not check the range end** (`ia_client.py:252-255`). A 206 `bytes K-M/size` with `M < size-1` is a legal partial answer. It is appended, fails the md5, and per item 3 permanently excludes that server. Optionally require `int(m[2]) == size - 1` when `size` is known and treat anything else as mismatched (re-issue from 0).
5. **Coverage gaps (no observed defect):**
   - No test for a `*` total in `Content-Range` while `size` is known (`ia_client.py:255`).
   - Condition 4 is exercised only on a first request (`"wb"`, `test_ia_client.py:652-664`), not on an append that completes the file exactly.

### Assessment
**Task quality:** Approved
**Reasoning:** No integrity path renames an unverified stitched or truncated file. Every `.part` disposition matches the brief, and termination is bounded and pinned by tests that go red under the relevant mutants. What remains is a spec-text ruling for the justified `owed` exception, one unpinned discard path on appends, and plan-level blame semantics for stitched mismatches.
