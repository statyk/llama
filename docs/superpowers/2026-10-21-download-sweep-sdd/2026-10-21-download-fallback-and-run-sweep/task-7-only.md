### Task 7: The sweep — `llama run resume --all`

**Implementer model: Opus** (LLM-spend strict surface; extraction of `run_resume` and isolation semantics).

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`run_resume`, new helper and sweep, `_execute`'s no-matching-artists return, `_print_sessions`), `packages/llama/src/llama/sessions.py` (eligibility)
- Test: `packages/llama/tests/test_sweep.py` (new)

**Interfaces:**
- Consumes: `failure_kind`, `failure_record`, `KIND_*` (Task 4); `sessions.read_request`; `run_lock`, `RunMissing`, `Locked`, `STATE_RUNNING`, `iter_sessions(probe_live=True)` (Task 6).
- Produces:
  - `sessions.sweep_verdict(info: SessionInfo, run_dir: Path, now: datetime) -> str | None` — `None` = eligible; else the skip reason: `running`; `paused until HH:MM` (local time of `resume_after`, for a `paused` run whose `resume_after` is in the future); `awaiting approval`; `needs attention`, which is any of:
    - a `paused` or `incomplete` run with any failure whose `failure_kind` is not `download`/`archive` (the same test for both states);
    - a run with neither `criteria.json` nor `request.json`;
    - a run with no `session.json` whose `request.json` has `auto: false`.

    Eligible: `paused` with `resume_after` past or absent, and `incomplete`, each when every failure (if any) is `download` or `archive`; a marker-less run qualifies only with `auto: true` or no `auto` key. It reads `run_dir/session.json` existence and `request.json` via `sessions.read_request`. `complete` runs never reach it (`attention_sessions`).
  - `cli._resume_run(config, ia, ledger, ws: RunWorkspace, *, auto: bool, full_rationale: bool, pace: PaceOptions, record_crash: bool) -> None` — takes `run_lock(ws.dir, blocking=False)` itself (raising `Locked`/`RunMissing` to the caller), then runs today's `run_resume` body. With `record_crash=True`, any `Exception` (including `typer.Exit` with a non-zero code) is caught, `mark_incomplete(ws, outcome=None, failures=[failure_record(None, exc, kind=KIND_OTHER)])` is written while the lock is still held, and the exception is re-raised. The failure's `error` is `exit <code>` for a `typer.Exit`, else per `failure_record` (Task 4). `typer.Exit(0)` is not a crash. `KeyboardInterrupt` is never caught.
  - `run_resume(session: str | None = Argument(None), all_runs: bool = Option(False, "--all", help=...), ...)`: exactly one of `session`/`--all` (else stderr error, exit 1); `--all` with `--interactive` → error, exit 1. The single-session form calls `_resume_run(..., record_crash=False)` and converts `Locked`/`RunMissing` exactly like `_run_locked` (Task 6).
- Sweep (spec §6): `--wait/--no-wait` defaults to `--no-wait` when unspecified (`wait=None` → `False`); `--max-wait` and `--no-pacing` pass through. List `attention_sessions(config.root)`, compute `sweep_verdict` for each, print one line per skipped run (`skip <id>: <reason>`), then resume the eligible ones oldest `updated_at` first, one at a time, in-process, `auto=True`, each under a `== <id>` header. Per-run result: `Locked` → `running` (no marker); `RunMissing` → `gone` (no marker, not an error); a caught exception → `error: <message>`; otherwise the run's `session_state` after the resume. After each resume, if that state is `paused`: stop, print the eligible ids not reached, go to the summary. Summary: one line per resumed run with its result. Exit 0 when every resumed run ended `complete` or nothing was eligible (print `nothing to resume`); else exit 1 (`incomplete`, `paused`, `error`, or any other state such as `awaiting-approval`; `running` and `gone` do not by themselves make it 1).
  - `_execute`: the `no matching artists found` return writes `mark_complete(ws, "no matching artists found")` first.
  - `_print_sessions` prints `(run)` for a failure whose `show` is `None`.

- [ ] **Step 1: Write failing tests** (`test_sweep.py`; stub `_execute` or `process_show` as `test_pace_loop`/`test_run_namespace` do; build runs with `mark_*` and `failure_record`):
  - `test_eligibility_per_state_and_kind` — parametrized over: paused past / paused absent / paused future (`paused until HH:MM`) / `paused-past-with-transport` (needs attention) / `paused-past-with-download` (eligible) / awaiting / incomplete no failures / incomplete all `download`+`archive` / incomplete with one each of `transport`, `llm`, `rate-limited`, `other` (needs attention) / legacy `download of …` record (eligible) / legacy `boom` record (needs attention) / no criteria and no request (needs attention) / `no-marker-auto-false` (needs attention) / `no-marker-auto-true` (eligible) / `no-marker-no-auto-key` (eligible).
  - `test_live_runs_are_skipped_as_running` (a real flock held on the run's `.lock`).
  - `test_oldest_first_and_summary` — three eligible runs resumed in `updated_at` order; summary lists all three.
  - `test_stops_on_a_pause` — the second run's stub writes `mark_paused`; the third is listed as not reached and not resumed; exit 1.
  - `test_one_run_raising_does_not_stop_the_others_and_writes_a_marker` — the first run's stub raises `RuntimeError("boom")`; the second still runs; the first's `session.json` is `incomplete` with one failure `{"kind": "other", "error": "boom"}`; the summary says `error: boom`; exit 1; a second sweep skips it as `needs attention`; `run list` prints that failure under `(run)`.
  - `test_crash_marker_for_typer_exit_reads_exit_code` — the first run's stub raises `typer.Exit(1)` → its failure's `error` is `exit 1` and the summary says `error: exit 1`.
  - `test_keyboard_interrupt_stops_the_sweep` — `KeyboardInterrupt` propagates; no marker written.
  - `test_run_that_turned_live_reports_running` — monkeypatch the helper's lock to raise `Locked` → result `running`, no marker.
  - `test_a_run_removed_before_its_turn_is_reported_gone` (Review Focus 5).
  - `test_no_wait_is_the_default_for_the_sweep` — capture the `PaceOptions` reaching `_execute`: `wait is False`; `--wait` passes `True`; `--max-wait 30m` and `--no-pacing` pass through.
  - `test_exit_codes` — all complete → 0; nothing eligible → 0 and `nothing to resume`; one ends `awaiting-approval` → 1.
  - `test_session_and_all_are_exclusive`, `test_all_rejects_interactive`.
  - `test_single_resume_still_refuses_a_live_run_and_records_no_crash_marker`.
  - `test_no_matching_artists_marks_the_run_complete` — `run_discover` stub returns `[]` → state `complete`, outcome `no matching artists found`.
- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_sweep.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(runs): llama run resume --all sweeps resumable runs in one pass`.

---

