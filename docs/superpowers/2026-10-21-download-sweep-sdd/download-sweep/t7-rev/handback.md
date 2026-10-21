### Spec Compliance
- ✅ Spec compliant. Every item in brief Task 7 and spec §6 is present and matches:
  - **Eligibility and skip reasons** (`sessions.py:433-470`): `running`, `awaiting approval`, `paused until HH:MM` (local time), and `needs attention`. Needs attention covers four cases:
    - any non-download/archive failure, with the same test for `paused` and `incomplete`;
    - neither criteria nor request;
    - a marker-less run whose request has `auto` other than `True`;
    - legacy records, through `failure_kind`.
  - **Order** is oldest `updated_at` first, compared as datetimes (`cli.py:330`).
  - **Results:**
    - `Locked` gives `running` and `RunMissing` gives `gone`. Neither writes a marker and neither counts toward exit 1 (`cli.py:339-342`, `:355`).
    - An exception gives `error: <msg>`; otherwise the run's `session_state`.
  - **Pause:** a run that ends paused stops the sweep, which then prints `not reached:` for each remaining eligible run (`:347-351`).
  - **Summary and exit:** the summary follows. Exit is 0 only when every result is complete, running or gone, or with `nothing to resume` (`:327-329`, `:352-356`).
  - **`--wait`** defaults to False for the sweep, and `--max-wait` and `--no-pacing` pass through (`:167`).
  - **Argument checks:** giving both or neither of session/`--all` is refused (`:156-158`), and so is `--all --interactive` (`:159-162`).
  - **No matching artists:** that return now writes `mark_complete` (`:61`).
  - **`(run)` label** is printed (`:84-87`).
  - **Crash marker:** written inside the lock scope, not for `Exit(0)`, and never for `KeyboardInterrupt` (`:227-234`).
  - **`run list` docstring** cleanup is folded in.
- ⚠️ Cannot verify from this diff: that `run_lock`'s context manager releases on every exit path, and that it refuses to create a missing dir. Both are Task 6 code. The `gone` test (`test_sweep.py:786-803`, which asserts `not r2.dir.exists()`) is indirect evidence for the second.

### Strengths
- **The extraction is faithful.** I compared the removed body (diff lines 172-325) against `_resume_locked` (`cli.py:237-288`) line by line:
  - It is a pure dedent.
  - Both request reads stay as raw `json.loads` (`:258`, `:270`), so the deliberate loud-failure asymmetry against `read_request` is kept.
  - The only removal is one comment, whose point moved into `_resume_run`'s docstring.
- **Named risks I checked, with what I checked:**
  - *Every path out of `_resume_run` releases the lock.* Lock, marker and re-raise are all inside one `with run_lock(...)` (`cli.py:227-234`).
  - *The crash marker is never written for `Exit(0)` or `KeyboardInterrupt`.* `_is_crash` (`:212`) handles `Exit(0)`. `except Exception` handles `KeyboardInterrupt`, and `test_sweep.py:755` pins it.
  - *The sweep can't re-resume a run in the same pass.* The eligible list is computed once and walked once (`:294-351`).
  - *Pacing reaches every swept run.* `pace` flows `_sweep_runs` → `_resume_run` → `_resume_locked` → both `_preflight_gate` (`:250`) and `_execute` (`:288`). `test_no_wait_is_the_default_for_the_sweep` pins all four combinations, and also asserts that the config default is `True`, so the `False` result is not a coincidence.
  - *No unmarked early return in `_execute` can loop spend.* I listed `_execute`'s returns:
    - every one writes a marker: complete, awaiting, or paused via `_render_pause`, which calls `mark_paused` at its lines 55/62;
    - the `no selections` return is interactive-only;
    - the `no matching artists` return was the only unmarked one, and this task fixed it.
- **DRY:** `_lock_refusal` (`cli.py:394-400`) now holds both refusal messages for `_run_locked` and the single-form resume. `_crash_record` serves both the marker and the summary text.
- **Tests:**
  - Liveness uses a real `fcntl.flock` on a separate fd (`test_sweep.py:562-571`).
  - The `gone` case uses a real `rmtree` between the listing and the run's turn, with no sleeps.
  - Both the crash-marker test and the paused test assert the second pass's verdict, not only the first pass.
  - `test_single_resume_still_refuses_a_live_run_and_records_no_crash_marker` pins that `record_crash=False` writes nothing and that the `RuntimeError` propagates unconverted.
- **The implementer's interpretations are all sound:**
  - checking needs-attention before paused-until gives a stable reason for a run that waiting will not fix;
  - an unparseable `resume_after` reads as needs attention, since the spec allows only past or absent;
  - `auto` is read strictly;
  - malformed failure lists read as needs attention instead of crashing the sweep.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **A `Locked`/`RunMissing` raised by the resume body is read as a lock refusal** (`cli.py:196-200`, `cli.py:336-342`). The implementer raised this concern; I confirm it is real but latent.
   - **What goes wrong:**
     - In the sweep, the body's `Locked` first writes a crash marker (`_is_crash` is true at `:232`), and then the sweep reports the run `running`, which does not count toward exit 1. The result is a hidden crash with exit 0.
     - In the single form it prints "in progress in another process".
   - **Why it is latent today:** I grepped `llama/src` for `blocking=False` and for where `Locked` is raised. The only non-blocking lock in the body is the show lock at `cli.py:634`, and `_execute` catches its `Locked`. `Locked`/`RunMissing` are raised only in `locks.py`.
   - **Fix:** catch acquisition separately in `_resume_run`, for example `stack = ExitStack(); stack.enter_context(run_lock(...))` outside the body's try, and wrap a body-raised `Locked`/`RunMissing` as an ordinary error. That keeps "the helper's acquire decides `running`" literally true (spec §6).
2. **One malformed `updated_at` crashes the whole sweep** (`cli.py:330`, `:359-361`). `_instant` calls `datetime.fromisoformat` on `SessionInfo.updated_at`, which is the marker's raw value when present (`sessions.py:180-182`). A hand-damaged marker would raise `ValueError` before any run is resumed. That breaks the "one bad file can't blind the sweep" principle that `read_request` follows, and persisted artifacts are meant to stay permissive.
   - **Fix:** fall back to the dir mtime, or to the epoch, on `ValueError`/`TypeError`.
3. **Two of the implementer's own interpretations have no test:**
   - an unparseable `resume_after` → `needs attention` (`sessions.py:462-465`);
   - a non-list `failures` or a non-dict record → `needs attention` (`sessions.py:450-453`).

   Both are cheap parametrized cases in `ELIGIBILITY`.
4. **The "turned live" test stubs the lock instead of holding one** (`test_sweep.py:768-783`). It monkeypatches `cli.run_lock` to raise. The `gone` test's pattern would give a real flock instead: have r1's stub action open and `flock` r2's `.lock` on its own fd. That exercises the real non-blocking acquire between the listing and the run's turn, which is exactly the live-run strict surface.
5. **The `session` type annotation is wrong** (`cli.py:127`). It reads `session: str = typer.Argument(None, ...)` and should be `str | None`. Cosmetic.
6. **The exit-only crash marker is terse.** A `typer.Exit(1)` marker records only `exit 1`, as the brief specifies, so the real reason exists only in that run's stderr section. This is acceptable as specified; a later task could consider capturing the last `error:` line.

### Assessment
**Task quality:** Approved
**Reasoning:** Every §6 requirement is implemented and tested. The extraction preserves single-run behaviour exactly, including the loud request reads, and the strict surfaces hold: the lock-held crash marker, the pacing passthrough, and the no-loop eligibility. The remaining items are latent or robustness and coverage polish.
