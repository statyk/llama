### Spec Compliance

**Compliant.** All brief interfaces exist and behave as specified:
- `errors.PlanLocked(TransmitterError)` (errors.py:71), `Workspace.plan_lock_path -> root/"plan.lock"` (workspace.py:108-110).
- `locks.plan_lock` (locks.py:20-32): creates `ws.root`, non-waiting `LOCK_EX|LOCK_NB`, raises `PlanLocked` with the exact brief message. Line-for-line mirror of `publish.publish_lock` (publish.py:173-185).
- Service wraps the plan and render step bodies separately (service.py:316-327); `_step` treats `PlanLocked` the same as `PublishLocked` (warning, skipped, returns False) (service.py:246).
- CLI `plan` and `render` take the lock around `plan_step` / `plan_step`+`render_step` (cli.py:162-176). Refusal propagates as a `TransmitterError`, and `main_cli` (cli.py:268-272) prints `error: …` and exits 1.
- `status` takes no lock. Recovery (`cut_for_recovery`) and the render skip path (`replan_from`) run inside `plan_step`/`render_step` (pipeline.py:163, 300), so the lock covers every place that drops rows. No plan.jsonl row semantics changed.

What the diff cannot show: none of material weight. The lock file is under `TRANSMITTER_ROOT` (local `~/.transmitter` on hugo, not the NFS station root), so flock semantics hold.

Named-risk checks:
1. **Lock ordering against `publish_lock`.** I grepped every `publish_lock`/`plan_lock` site. `publish_lock` is taken only in publish.py:279, publish.py:392 and fallback.py:104. `plan_lock` is taken only in the service plan/render closures and the CLI. Neither step calls into the other's critical section, so the two locks never nest and no ordering or deadlock risk exists. `fallback render` takes only `publish_lock`, as before.
2. **Callers of `plan_step`/`render_step`.** The only callers are service.py:318, 322 and cli.py:163, 175-176, all locked. `run --once` goes through `Runner.tick`, so it is covered. Nothing bypasses the lock or takes it twice. The CLI `render` holds one lock across both steps, so it never re-acquires (re-acquiring would self-refuse, because flock on a fresh fd from the same process conflicts).
3. **Can a held lock wedge filling or alert observation?** No. On a skip, `_step` returns False, so `plan`/`render` are not added to `ran`. `end_observation` then neither advances nor resets their gated counters, the same contract as `PublishLocked`. `filling` stays True and the next tick retries. Publish still runs, `_read_lead` still runs, and the watchdog is still pinged in `_step`'s `finally`. While an operator `transmitter render` holds the lock (possibly minutes of encoding), the service logs one warning per tick per step and retries. That is the designed behaviour.

### Strengths
- Exact reuse of the proven `publish_lock` shape (mkdir first, `O_CREAT` 0o644, `BlockingIOError` → typed error, fd closed in `finally`, which releases the lock).
- Separate locks per service step rather than one lock across plan+render, so a skip is attributed per step and matches the per-step `ran` accounting.
- The tests are real behavioural pins:
  - The service test asserts that both `plan step skipped` and `render step skipped` are logged, that plan.jsonl is byte-identical, that no `ALERT` was logged, and that publish still ran (via a spy). The `"ALERT" not in caplog.text` check is meaningful because alerts log at ERROR (alerts.py:348) and caplog captures WARNING and above.
  - The CLI test exercises both commands and asserts that plan.jsonl is not created, which also covers `render`'s inner `plan_step`.
  - `test_locks.py` pins refusal, release and root creation.
- Focused run of the 4 new tests: `4 passed in 1.92s`, with no warnings or noise. `transmitter.__file__` resolves inside the worktree.
- Python 3.11-safe (no new syntax), and there is no import cycle (`locks` → `workspace`, `errors`).

### Issues

#### Critical
None.

#### Important
None.

#### Minor
1. **service.py:227-231 and service.py:247: the docstring and comment are stale.**
   - What: `_step`'s docstring still says a step is skipped only "on PublishLocked". The except-arm comment says "An operator's manual publish/fallback overlaps this tick", but it now also catches an operator's `plan`/`render`.
   - Why: both mislead the next reader about which locks cause a skip.
   - Fix: name both errors in the docstring ("PublishLocked or PlanLocked"), and make the comment read "An operator's manual publish/fallback/plan/render overlaps this tick".
2. **test_cli.py:233-243: the CLI test checks the exception, not the `error: …` output.**
   - What: the brief asked for the message "on stderr" via `main_cli`. The test invokes `app` through CliRunner and asserts `result.exception` is `PlanLocked`.
   - Why: this proves the refusal propagates, but not the operator-visible output. That path is generic `main_cli` handling of any `TransmitterError` (cli.py:268-272), so the residual risk is very low. The implementer disclosed the choice.
   - Fix (optional): add one assertion that calls `main_cli` with a monkeypatched `sys.argv` and checks the captured stderr for `error: another transmitter plan or render holds the lock`.
3. **locks.py:20-32: duplicated code.**
   - What: `plan_lock` is a verbatim copy of `publish_lock`, differing only in the path and the error.
   - Why: two copies of the flock idiom can drift. The brief asked for a mirror, so this is acceptable as is.
   - Fix (optional): factor a private `_nonwaiting_flock(path, make_exc)` into `locks.py` and move `publish_lock` onto it later. It is not worth churning publish.py in this task.
4. **cli.py:158-176: `load_config`/`open_station` run before the lock.**
   - What: the brief says the commands take the lock "around their whole body", but the implementation takes it after `open_station`.
   - Why: `open_station` writes only the epoch, under its own `epoch.lock` (workspace.py:159), and never touches plan.jsonl, so nothing the plan lock protects is outside it. Noted only as a literal deviation; no change is needed.

### Assessment
**Task quality:** Approved
**Reasoning:** The lock covers every writer of plan.jsonl, including recovery and the render replan, in both the service and the CLI. It never nests with `publish_lock`, and a skip slots cleanly into the existing `PublishLocked` contract for gated alerts, filling and the watchdog. The tests pin the real behaviour on both surfaces. The remaining items are stale wording, one optional test strengthening and a cosmetic duplication.
