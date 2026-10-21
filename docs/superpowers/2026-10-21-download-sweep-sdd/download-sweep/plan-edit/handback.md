# plan-edit handback

All decisions are applied. Nothing is committed, and only the plan and the spec were edited.

**Line counts:**
- Plan: 312 → 351.
- Spec: 350 → 373.

## Where each decision went

**S1 (paused runs with failures)**
- Spec §6 "Eligible": paused runs also need every failure (if any) to be `download`/`archive`.
- Spec §6 "needs attention": now covers "an incomplete or paused run …", with the re-paid-once-per-window reason.
- Spec testing expectations: eligibility bullet updated.
- Plan Task 7 `sweep_verdict`: the failure-kind test applies to `paused` and `incomplete` alike.
- Plan Task 7 parametrized cases: added `paused-past-with-transport` (needs attention) and `paused-past-with-download` (eligible).

**S2 (marker-less runs)**
- Spec §6: a paragraph after "Eligible" says a marker-less run reads as `incomplete`, and is eligible with `auto: true` or no `auto` key.
- Spec §6 "needs attention": new bullet for a marker-less run with `auto: false`.
- Plan Task 7 `sweep_verdict`: added that clause, and it now reads `session.json` existence and `request.json` via `sessions.read_request`.
- Plan Task 7 Consumes: added `sessions.read_request`.
- Plan Task 7 cases: added `no-marker-auto-false`, `no-marker-auto-true` and `no-marker-no-auto-key` (see gaps).

**S3 (each copy checked once)**
- Spec §1 Classification: an md5 mismatch moves on and that copy is not tried again in the repeat attempts. A size mismatch is "handled like an md5 mismatch".
- Spec §1: new limitation paragraph (a file whose every copy fails is swept every pass, exit 1, cleared by hand).
- Spec testing expectations: the md5 bullet adds "each copy checked at most once".
- Plan Task 1: classification is now a list. The md5 line reads "moves on, `.part` deleted, not repeated (that copy is not retried)", and the size mismatch is handled like it.
- Plan Task 1: added `test_md5_mismatch_copy_is_checked_once`. `test_md5_mismatch_on_one_server_then_success` is unchanged.
- Plan Task 2 "Integrity unchanged": adds "that copy is not retried".
- Plan Task 2: `test_stitched_file_with_bad_md5_is_deleted_and_refetched_from_zero` is re-specified (see gaps).

**S4 (inode check and the husk window)**
- Spec §4 Rules:
  - New rule "The locked file must still be the run's lock file" (same inode and device; otherwise release and treat as missing).
  - The "Missing run dir" rule was reworded (see contradictions).
- Spec §4 "Known remaining windows":
  - Added the husk bullet ("directory not empty", a `.lock`-only dir, shown as needs attention, a second `run rm` removes it).
  - "Neither can produce two workers." is replaced by the corrected paragraph.
- Spec testing expectations: run-lock bullet updated.
- Plan Task 6:
  - `run_lock` interface carries the `fstat`/`stat` `st_ino` + `st_dev` check, and the `FileNotFoundError` → `RunMissing` rule.
  - Added the test `test_lock_on_a_replaced_lock_file_is_run_missing`.
- Plan mutation table: added the row "Drop the inode check".

**P1 (tombstone removed)**
- Task 6 `run rm` is now `_run_locked`, the prompt, then `shutil.rmtree(ws.dir)` while holding the lock.
- Review Focus 4 is rewritten (see contradictions).
- `test_run_rm_leaves_no_husk_and_readers_skip_the_tombstone` is deleted.

**P2 (Task 2 tests re-pinned with request counts)**
- `test_last_non_abandoned_candidate_is_never_abandoned`: redirect / S1 404 / S2 trickle, with request counts.
- `test_single_candidate_trickle_completes_in_one_request`: added.
- `test_each_candidate_abandoned_at_most_once`: adds the server-1 / redirect-at-most-2 request counts.
- `test_slow_but_above_floor_transfer_finishes`: now two candidates, and the server is never requested.
- Mutation table: added "Drop the floor comparison / floor × 100". The "last non-abandoned" row already pointed at the right test.

**P3 (other httpx errors)**
- Task 1 classification: "any other `httpx.HTTPError` … retryable; no `httpx` exception ever escapes".
- Task 1: added `test_too_many_redirects_is_caught`.

**P4 (when abandonment is allowed)**
- Task 2 "May abandon" is now a four-clause list, adding the deadline clause and the full-`size` clause.
- Task 2: added `test_no_abandonment_after_the_deadline`.

**P5 (continuation integrity)**
- Task 2 `.part` bullet: a continuation is kept only when an md5 is known.
- Task 2 continuation list:
  - A `Content-Range` total that differs from `size` is treated like a wrong start.
  - New bullet: a `206` answering a request sent without `Range` is an error.
- Tests added: `test_no_md5_trickle_restarts_from_zero` and `test_206_to_a_plain_request_is_rejected`.

**P6 (transfer mechanics)**
- New Task 2 bullet "Order per chunk" (write, then check).
- `offset` is always `tmp.stat().st_size`.
- The monitor restarts per request, including the re-issued no-Range request.
- `k` is defined in `test_trickle_switches_and_continues_from_offset`.

**P7 (the two readings of "any other answer")**
- Task 2 continuation list: the 416 bullet says the attempt ends and the schedule moves on.
- A sentence after the list names the two readings of spec §1's "any other answer".
- Review Focus 3's rationale is replaced with the decision's wording.

**P8 (`slots` replaces `slots_dir`)**
- Task 3 interface: `slots: DownloadSlots | None = None`.
- `_setup` builds `DownloadSlots(config.root / ".download-slots")`, and tests share the fake clock or use a stub.
- The Task 3 Files entry is now "construct the `DownloadSlots`".
- The deadline sentence is in Task 3, and Task 1's schedule bullet was changed to match ("slot wait reported by attempts started after the first pass").
- Task 1's forward note now says "Task 3 adds `slots`".

**P9 (`_drive` harness change)**
- New "Test harness change" bullet in Task 5: the `defaultdict` of `herder.fake.FakeProvider` ladders, the `llm=` keyword, the default `True`, and the meter-read note.
- Task 5's new tests name `llm=True`/`llm=False`.
- The old instruction to edit existing boundary tests is removed ("existing tests are not edited").
- Task 5's implementer-model note was updated to match.

**P10 (crash-marker text)**
- Task 4 `failure_record`: `error` is `str(exc)`, or the class name when that is empty. `test_failure_record_stamps_kind_and_utc_at` covers it.
- Task 7 `_resume_run`: `error` is `exit <code>` for a `typer.Exit`.
- Task 7: `_print_sessions` prints `(run)`, and `_print_sessions` is added to Task 7's Files.
- Tests: added `test_crash_marker_for_typer_exit_reads_exit_code`, and a `(run)` assertion on `test_one_run_raising_does_not_stop_the_others_and_writes_a_marker`.

**P11 (`get --name` decision mechanism)**
- Task 6 `get --name` wiring: try `mkdir(exist_ok=False)`; `FileExistsError` means an existing dir and takes `_run_locked`.
- An existing non-live dir is reused as today. Both tests are kept.

**P12 (doc limitations)**
- Task 8 Step 1 gains a five-item "Known limitations" list, covering (i)–(v).
- Task 8's architecture text says "`run rm` holds it through `rmtree`, the inode check after acquiring".

**P13 (consistency)**
- Review Focus 4 now names the inode-check scenario and its test.
- Review Focus 3 was corrected.
- Mutation-table rows were added as listed above.
- Global Constraints needed no change.

## Removed
- The rename-then-rmtree tombstone: from Task 6 wiring, from Review Focus 4, and from Task 8 (it was "`run rm` rename-then-rmtree").
- Every `.removing-` mention.
- The test `test_run_rm_leaves_no_husk_and_readers_skip_the_tombstone`.
- Dot-dir skipping in `iter_sessions` (interface text), `_by_run_rollup` (Readers bullet) and `catalog.resolve_run`, with `catalog.py` dropped from Task 6's Files.
- Every `slots_dir`.
- In Task 5, "existing boundary tests … are updated so their stub makes one provider call".

A grep of both files for `removing|tombstone|dot dir|slots_dir|catalog|resolve_run|rename-then` now returns nothing. The spec still has one unrelated use of "husk" in `get`'s blocking-lock rationale, which remains true.

## Not applied cleanly
- **P11 against the spec's wording.** Spec §4 still says the `--name <new>` dir "is created (`exist_ok`) before locking". The plan now decides by `exist_ok=False` plus `FileExistsError`. The behaviour is the same and only the mechanism differs. I did not edit the spec, because P11 is a plan-local item.
- **Plan narrower than spec §1 (P5).** The spec's "Continue, don't restart" has no md5 condition and no `Content-Range` total check. P4's two extra abandonment clauses are likewise not in the spec. These are refinements, but the spec was not edited for them because they are P items. Edit the spec if it should match.
- **Spec "Known remaining windows", first bullet.** It still says "Nothing guards this window" about `get`'s create-then-lock gap. The new paragraph below it explains that the inode check keeps that gap from producing two workers, so the two read together. I left the sentence as written.

## Gaps filled
- **`test_stitched_file_with_bad_md5_is_deleted_and_refetched_from_zero`.** Under S3, the copy that served the corrupt continuation is not retried. The redirect, having been trickle-abandoned, would only trickle again. So the test now uses three candidates: redirect (trickles), S1 (corrupt continuation, requested once), and S2 (healthy, no `Range`).
- **Test order in `test_lock_on_a_replaced_lock_file_is_run_missing`.** As worded, a thread blocking behind a holder has a race: it may open the new file after the replacement and the test would pass vacuously or flake. I added "Make the ordering deterministic (e.g. do the replacement inside a wrapped `flock` call on the acquirer's path), not with a timing sleep", per the Global Constraints' "no timing sleeps for correctness".
- **Extra test case `no-marker-no-auto-key` (eligible).** S2's text states this outcome, but the decision listed only two cases.
- **Extra mutation row.** "Keep an md5-mismatched copy in the repeat cycle" → `test_md5_mismatch_copy_is_checked_once`. The table had no md5-retry row to update, and S3 adds a new load-bearing line.
- **Test-wide md5 default.** Task 2's test preamble now says "Metadata carries an md5 unless a test says otherwise", because continuation now depends on an md5 being known.
- **Typer exit text.** `typer.Exit`'s `str()` is empty (click's `Exit` does not pass args), so `exit <code>` is set in `_resume_run`, not in `failure_record`. `sessions.py` stays free of typer. No new interface parameter was needed.
- **The meter read in Task 5.** I checked `cli.py:637-652`: the after-show `_meter` call sits inside the boundary condition. The `_execute` bullet now says an LLM-free show takes no second read, which matches P9's note.

## Contradictions resolved
- **P1 against P13 on Review Focus 4.** P1 said to replace it with the husk limitation; P13 said to name the inode scenario. Item 4 now does both: the inode scenario with its test, and the husk race as a documented limitation whose only test is `test_rm_refuses_a_live_run`.
- **Spec §4's "Missing run dir" rule.** It said the refusal means "a lock attempt racing `rm` can't leave a husk", which S4's new husk window contradicts. It now reads: "… can't recreate the run (one narrow window remains, below)".
- **Removed history wording.** The S4 phrase "No tombstone, no retry" was not written into the spec, since naming a removed design is history.
