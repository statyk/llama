# Final whole-branch review: download-sweep (1609a28..3f48bc0), reviewer on Opus

## What I checked
- **Read:** the spec (Stakes first), the plan (Global Constraints, Review Focus, Mutation pins), the deferred/rulings file, and the full branch diff. I read these whole in their final state: `ia_client.py`, `download_slots.py` and `locks.py`; the diffs of `sessions.py`, `pipeline.py` and `workspace.py`; and the cli.py diff, plus all of `_execute`, `_resume_locked` and `_sweep_runs`.
- **Code outside the diff, each for a named risk:**
  - `stages/package.py`: download error wrapping and the rename gate.
  - `pipeline.process_show`: whether every LLM call goes through the counted provider map.
  - `herder/tasks.py`: tasks call `.complete`/`.research` by attribute, so the wrapper counts them, and there are no isinstance checks on providers.
  - `choose_entries` and every `human_gate` use: the sweep bypass described below.
  - `_render_pause` and `_preflight_gate`: what a pause writes to the marker.
  - Every non-blocking lock site: whether a `Locked` or `RunMissing` can be raised from inside a body.
  - `_humanize_age`: malformed `updated_at`.
- **Suite:** `./.venv/bin/pytest -q` from the worktree ran 3934 passed, 1 skipped, 8 deselected, rc 0. `llama.__file__` resolves inside the worktree. The output is in final-rev.log.
- **Mutation:** 10 mutants, each in its own `git archive` scratch copy. I ran `.venv/bin/python -m pytest` with `PYTHONPATH` shadowing, proven by a `SENTINEL_PLANTED` constant in the copy's `locks.py`, with `PYTHONDONTWRITEBYTECODE=1`. I named the predicted red test before each run; predictions and results are in final-rev.log. Results:
  - M2 (drop the inode check), M3 (`_continues` always True), M4 (skip md5 on a stitched 206), M5 (`transport` sweepable), M6 (no-md5 trickle keeps the `.part`), M7 (abandon the last candidate), M8 (no crash marker), M9 (deadline 60 s → 10 s) and M10 (a chunk write does not set `wrote`) are each caught by the predicted test.
  - **M1 (per-show `calls_before` replaced by a run-level baseline, `llm_calls() > 0`) SURVIVES all 271 focused tests, as predicted.** This is Important #1.

## Strengths
- **Download integrity holds on every path I traced.** `tmp.replace(dest)` is reached only on `_Attempt(True)`, which comes only after the whole-file check: md5 read back from disk, else size, else (neither known) as today per the spec. Each failure path discards the `.part`:
  - a trickle without md5;
  - an httpx error after `wrote`;
  - a mismatched 206;
  - a 206 to a plain request;
  - a 416;
  - an integrity failure;
  - `finally` on any other exit, including KeyboardInterrupt and OSError.

  A stale `.part` is unlinked before the first attempt. `wrote` treats a `"wb"` truncate as a write, which matters for a 200 after a kept `.part`. Append-mode `f.tell()` is correct because CPython seeks to the end on open.
- **The schedule terminates and matches the spec, including the owed-attempt ruling.** `may_abandon` requires another non-abandoned, retryable-or-untried candidate, so the last one is never abandoned. The owed attempt cannot itself be abandoned, because `expired()` is already true for it. Slot wait is subtracted only after the first pass.
- **Lock design is sound.**
  - Lock order holds: run, then show, then ledger.
  - Slot locks are taken only inside `_attempt`, which runs within the show lock and waits on nothing but the network, so they cannot form a cycle.
  - `os.open` fds are non-inheritable (PEP 446), so a `claude -p` or ffmpeg child can't keep a run "live" after llama dies.
  - `run_is_live` lets unexpected errors propagate rather than read "not live", which is the right bias for this strict surface.
  - Nothing that holds a run lock calls `iter_sessions`, so no process can probe itself as running.
- **Download failures land in the right kind.** `IADownloadError` reaches `_process`'s `(TaskFailed, HerderError, IAError)` arm unwrapped (package.py:52 → process_show has no wrapping) and is recorded as `download`. A metadata `_get` failure is recorded as `archive`. Any uncaught exception in a swept run becomes a `kind: other` crash marker written under the lock, so a run that fails the same way is re-paid at most once by the sweep.
- **Every `_execute` early return now writes a marker,** including the new `no matching artists found` → complete. So `session_state` after a resume is meaningful, and stop-on-pause works.
- **Folded rulings landed:**
  - T1's metadata httpx error is caught (ia_client.py:222).
  - The T1 deadline pin and the T2 mid-append discard are pinned (M9 and M10 are caught).
  - The T4 comment and `startswith("download of ")` assertion are in place.
  - The T6 "or running" docstring is in place.
- **Docs are thorough.** CLAUDE.md now carries the run lock, the cap, the fallback, the failure kinds and the rollout caveat, with the known limitations in the plan's wording.

## Issues

### Critical (Must Fix)
None.

### Important (Should Fix)

1. **Test gap on the LLM-spend strict surface: the per-show `calls_before` baseline is unpinned.**
   - **Where:** `packages/llama/tests/test_pace_loop.py`, against `packages/llama/src/llama/cli.py:632/646`.
   - **What:** mutant M1 replaces `llm_calls() > calls_before` with `llm_calls() > 0` and survives the whole focused suite. Every no-boundary test drives one show, so a run-level baseline is indistinguishable from a per-show one.
   - **Why it matters:** if that regression happened, every LLM-free show after the first LLM show in a run (a mixed resume, the sweep's population) would fold a near-zero delta into the EWMA. That is exactly what spec §5 / Goal 6 exist to prevent.
   - **Fix:** add the orchestrator's mixed-run test: `_drive(..., ["a", "b"], llm=lambda p: p == "a")` gives exactly one boundary, and the `b`-first order also gives one. Also drop or un-vacuum the `pacing-state.json`-absent assertions: `record` is monkeypatched, so the file can never exist.

2. **Spec-level, for the operator: the sweep makes decisions a human was meant to make.**
   - **(a) `--human-gate` profiles.** `_resume_locked` always passes `human_gate=False` (`cli.py:1278`). That is pre-existing for a manual `run resume`. The sweep now makes it unattended.
     - **How it happens:** a `get --profile <gated> --auto` run that pauses or dies before `choose_entries` is eligible (paused with no failures, or marker-less with `auto: true`). It pauses at `_execute`'s pre-flight gate, or in the run-level RateLimited catch in discover/search/winnow past `--max-wait`, for example on a multi-day 7-day-window pause, or it is killed.
     - **Effect:** the sweep processes the top picks with no approval. That spends LLM tokens and adds shows the profile said a human must pick.
   - **(b) Interactive runs that paused before their prompts.** A paused `auto: false` run with a marker, paused before its artist-prune or rank prompts, is eligible and resumed with `--auto`. The spec's own reason for excluding the marker-less `auto: false` case ("the sweep would otherwise process it with --auto") applies equally here.
   - **Spec status:** the spec is silent on (a) and inconsistent on (b). A reasonable operator would not expect an unattended sweep to bypass a configured human gate.
   - **Fix options (operator's call):** persist `human_gate` in `request.json` (for older runs, re-load the profile by name) and pass it through `_resume_locked`. Or have `sweep_verdict` return `needs attention` for a gated profile with no recorded approvals, and for any `auto: false` request whose run has no shortlist decision yet. Escalate rather than fix silently, since (a) changes manual `run resume` semantics too.

### Minor (Nice to Have)

1. **A pause erases a needs-attention run's failures.** `_render_pause` defaults `failures=None` (`cli.py` `_preflight_gate` and the run-level catch), so a pre-flight or run-level pause rewrites the marker with `failures: []`.
   - **Effect:** a needs-attention run (for example one with an `llm` failure) that the operator resumes by hand into a pre-flight pause becomes sweep-eligible after the reset. The sweep then re-pays the failing show once before it lands back in needs attention.
   - Bounded to one re-spend per such manual resume, and the marker semantics are pre-existing. The spec's "a paused marker carries the failures already taken" only covers this invocation's failures.
   - **Fix (optional):** carry forward non-sweepable failures from the old marker when pausing.
2. **A lock attempt bumps a marker-less run's apparent age.** `run_lock`'s `O_CREAT` on a pre-v2.14 run dir creates `.lock`, which bumps the dir mtime. A marker-less run takes its `updated_at` from that mtime, so its age and sweep order shift after any lock attempt. Cosmetic.
3. **Latent: a `Locked`/`RunMissing` raised inside `_resume_run`'s body would be reported as a lock refusal.** `cli.py:1219-1226` would then label it "running" in the sweep or "in progress in another process" for a single resume. It is unreachable today: the only non-blocking lock in the body is `cli.py:634`, caught locally, and `run_lock` is never re-entered. Even if reached, the crash marker still stops any spend loop. Hardening is optional; see the triage below.

## Deferred-minor triage

**Predecessor ledger (Tasks 1-3):**
- **Ruling: one combined Opus reviewer per task.** Accept (process, not code); this review is the final Opus seat.
- **Ruling: ledger/brief/handback paths.** Accept (paths only).
- **T1 deadline lower bound unpinned.** Resolved by the fold: M9 (60 → 10 s) is caught by `test_every_server_failing_raises_after_first_pass_and_deadline` and two others.
- **T1 metadata httpx non-transport error can escape.** Resolved: `_download_candidates` catches `httpx.HTTPError` (ia_client.py:222).
- **T1 DecodingError, non-dict metadata, mid-write OSError untested; 3xx non-retryable; hard-coded 1.0..4.0; rng "or" idiom.** Defer. The code paths are correct on reading; an OSError fails the show as `other`, which is conservative for the sweep. No strict-surface effect.
- **Ruling: the "owed" attempt after an abandonment skips the deadline.** Accept. The code matches the amended §1 (ia_client.py:427-436), and the owed attempt is not abandonable because `expired()` is true.
- **T2 transport error mid-append discard unpinned.** Resolved by the fold: M10 is caught by `test_transport_error_mid_continuation_discards_the_part`.
- **T2 stitched md5 failure blames only the finisher.** Defer. Liveness only; integrity is intact, and the file fails as `download` and is retried next sweep pass.
- **T2 `_continues` does not check range end M == size-1.** Defer. Continuation exists only under an md5, which catches a short append.
- **T2 no test for a `*` total with size known; condition 4 tested on the first request only.** Defer. Test polish; `_continues` rejects `*` when size is known on reading.
- **T3 bundle:**
  - `_setup` slots wiring unpinned: defer. Not a strict surface; a one-line test is worth adding if a fix wave runs anyway.
  - Duplicated `_attempt` branches: defer, cosmetic.
  - `_throttle` sleeps inside the slot: defer, 0.5 s.
  - Non-FIFO polling: defer, documented.
  - A long slot wait disables trickle abandonment: defer, liveness only.
  - The cap test fails only after its 30 s guard: defer, test ergonomics.
- **T3 `os.close` on the non-BlockingIOError path unpinned.** Defer. An fd leak only on ENOLCK, and the error propagates.

**orch-r1 ledger (Tasks 4-8):**
- **T4 naive caller `now`; `--no-pacing` RateLimited site untested for kind; mid-module import.** Defer. No caller passes `now`, the site uses the same `failure_record` call that is unit-tested, and the import is style.
- **Ruling: fold the T4 stale comment and the `startswith` assertion into T5.** Landed (cli.py:567; test_pace_loop asserts `startswith("download of ")`).
- **T5 vacuous `pacing-state.json` assertions; replace the already-packaged test with a mixed run (RECOMMEND FIX).** **Fix before merge.** Confirmed by mutation: M1 survives (Important #1).
- **T5 `_CountedProviders.get`/`__contains__` via `__getitem__`; `__getattr__` recursion without `__init__`.** Defer. Production providers is a plain dict of every TASK_KEY, and nothing copies or pickles the wrapper.
- **T6 a running row prints the previous attempt's outcome and failures.** Defer. The spec is silent and the effect is cosmetic. A `last attempt:` prefix is a nice follow-up.
- **T6 `RunWorkspace.lock` unused; extra `blocking=` kwarg; `--name` on a regular file prints "no longer exists".** Defer. Cosmetic, and the misleading message for a non-dir name is harmless.
- **Ruling: fold the T6 `run list` docstring into T7.** Landed.
- **T7 (RECOMMEND FIX):**
  - **(1) body-raised `Locked`/`RunMissing` read as a lock refusal.** Defer. I verified it is unreachable today: the only body non-blocking lock is `cli.py:634`, caught locally. Even if reached, the effect is a mislabeled summary or exit code, not a second worker or a spend loop, because the crash marker is still written. Cheap hardening if a fix wave runs anyway: acquire, then `try` the body, and map body exceptions to `error:`.
  - **(2) a malformed `updated_at` crashes the sweep.** Defer. `run list` already crashes on the same input via `_humanize_age` (`cli.py:1029`), and llama itself always writes isoformat, so only a hand-corrupted marker triggers it. If fixed, fix both readers together.
  - **(4) the turned-live test stubs `run_lock`.** Defer. Pinned piecewise: the stub test fails if the `try` moved around the acquire (a marker would be written), and the real non-blocking `Locked` is pinned by test_run_lock and `test_live_runs_are_skipped_as_running`.
- **T7 untested interpretations (unparseable `resume_after`, malformed failures → needs attention); annotation `str | None`; terse exit-only crash marker.** Defer. Both interpretations are the conservative direction (no resume).
- **T8 doc nits** (README:152 "crash", CLAUDE.md:94 criteria-without-request, :910 "marked not workable", :921 total check, :457 "--json"). Defer; none misleads an operator into a harmful action. Fold them in if the Important #1 fix wave touches docs anyway.

## Declined to judge
- **Whether `archive`-kind failures should be sweep-eligible.** It is a spec ruling. I checked only that no traced path pays an LLM call before a persistent IAError on every pass (gather's IAError sites are caught locally, and package runs after brief has persisted).
- **Pre-existing `ValueError`/`JSONDecodeError` from `ia.metadata()` in `build_package` escaping `_process` uncaught.** It is outside this branch's diff. Under the sweep it becomes a crash marker, which is conservative.
- **The `run rm` `.lock` husk race and the fresh-`get` mkdir-to-lock window.** Operator ruling plus documented limitations.
- **`get --name` existing-name reuse.** Operator ruling.
- **Parallel processing within a run, refreshing stale metadata, `_get` retry changes.** Spec non-goals.
- **Process kills (SIGKILL/OOM) looping a run through the sweep.** No marker can be written by a killed process. That is inherent to the design and outside the spec.

## Recommendations
- Land Important #1 (one test, about 10 lines) before merge.
- Put Important #2 to the operator as a spec decision. It is pre-existing for manual `run resume`, but the sweep runs it unattended. If accepted, it is a small change in `request.json`, `_resume_locked` and `sweep_verdict`, with tests for a gated paused run and a paused `auto: false` run.
- Optional in the same wave: the `_setup` wiring pin, and the T7(1) acquire/body split.

## Assessment
**Ready to merge?** With fixes.

**Reasoning:** no strict-surface violation found in code. Integrity, liveness and lock order hold, and the mutation pins are all caught. One strict-surface test gap (M1) should be closed before merge, and the human-gate bypass needs an operator ruling: fix now or explicitly accept as known.
