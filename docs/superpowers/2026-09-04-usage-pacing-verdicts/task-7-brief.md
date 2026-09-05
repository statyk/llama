### Task 7: Pause and resume the show loop

The integration. `_execute` catches `RateLimited` at the show boundary and either sleeps and carries on, or checkpoints and exits 0.

**Files:**
- Modify: `packages/llama/src/llama/cli.py:155-278` (`_execute`), plus the `get`, `run approve` and `run resume` command signatures
- Modify: `packages/llama/tests/test_sessions.py` — its `test_a_run_that_lost_a_show_ends_incomplete_and_records_why` (line 261) is the end-to-end pattern to copy: `runner.invoke(cli.app, [...])` with `fake_providers`, `FakeIA`, and a `config.toml` written into `tmp_path`.

**Interfaces:**
- Consumes: `RateLimited` (Task 2), `parse_duration`/`format_delta`/`sleep_until` (Task 5), `mark_paused` (Task 6).
- Produces: `_execute(..., pace: PaceOptions | None = None)`; `PaceOptions` dataclass in `llama/pacing.py` with fields `enabled: bool`, `wait: bool`, `max_wait_s: float`, `unknown_reset_wait_s: float`, `reset_skew_s: float`, and the constructor `pace_options(config, wait: bool | None, max_wait: str | None) -> PaceOptions`.

- [ ] **Step 1: Add PaceOptions to pacing.py**

```python
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class PaceOptions:
    enabled: bool
    wait: bool
    max_wait_s: float
    unknown_reset_wait_s: float
    reset_skew_s: float


def pace_options(config, wait: bool | None = None,
                 max_wait: str | None = None) -> PaceOptions:
    """Config defaults with the CLI flags layered on top."""
    cfg = config.pacing
    return PaceOptions(
        enabled=cfg.enabled,
        wait=cfg.wait if wait is None else wait,
        max_wait_s=parse_duration(max_wait or cfg.max_wait),
        unknown_reset_wait_s=parse_duration(cfg.unknown_reset_wait),
        reset_skew_s=parse_duration(cfg.reset_skew),
    )


def resume_at(err, pace: PaceOptions) -> datetime:
    """When to come back after a refusal: the reset it named, else a default.

    The skew keeps us from racing the window's own clock.
    """
    when = getattr(err, "resets_at", None)
    if when is None:
        return _now() + timedelta(seconds=pace.unknown_reset_wait_s)
    return when + timedelta(seconds=pace.reset_skew_s)
```

- [ ] **Step 2: Write the failing test**

Append to `packages/llama/tests/test_sessions.py`, following the existing
end-to-end pattern (same `config.toml`, `fake_providers`, `FakeIA` and
`runner.invoke` as `test_a_run_that_lost_a_show_ends_incomplete_and_records_why`).
The fixture run processes one show, `GratefulDead/1973-06-10`.

```python
from datetime import datetime, timedelta, timezone

from herder.limits import RateLimited
from llama import pacing
from llama.sessions import STATE_PAUSED


class LimitedProvider:
    """Raises a usage limit for the first `times` calls, then defers to `then`."""

    def __init__(self, resets_at, times=1, then=None):
        self.resets_at, self.times, self.then = resets_at, times, then
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.times:
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=self.resets_at)
        return self.then.complete(prompt)

    def research(self, brief: str) -> str:
        return self.complete(brief)


def test_a_usage_limit_pauses_the_run_instead_of_failing_the_show(
        tmp_path: Path, monkeypatch):
    """A limit is not a show failure: nothing is wrong with the show, so it
    is left for the resume rather than recorded in failures[]."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    # 30h out, well past the 6h default cap, so it checkpoints rather than sleeps
    providers["brief"] = LimitedProvider(now + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "pausedrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.failures == []                    # NOT a failure
    assert info.resume_after.startswith("2026-09-05")
    assert info in attention_sessions(tmp_path)
    assert "run resume pausedrun" in result.output


def test_a_usage_limit_within_max_wait_sleeps_and_then_finishes(
        tmp_path: Path, monkeypatch):
    clock = {"now": datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    real_brief = providers["brief"]
    providers["brief"] = LimitedProvider(clock["now"] + timedelta(hours=2),
                                         times=1, then=real_brief)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "sleptrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE           # slept, retried, finished
    assert info.failures == []
    assert clock["now"] >= datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    # The three assertions above ALL hold if the interrupted show is silently
    # dropped from the queue instead of retried, which is exactly the bug this
    # test exists to catch. These two are what actually pin it: the show came
    # back round, and it packaged.
    assert providers["brief"].calls >= 2          # refused once, then retried
    assert info.outcome == "1 packaged"
    assert "packaged:" in result.output


def test_no_pacing_restores_the_old_failure_behaviour(tmp_path: Path, monkeypatch):
    """--no-pacing is the escape hatch: the limit is a per-show failure again."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    providers["brief"] = LimitedProvider(now + timedelta(hours=2), times=99)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "nopacing", "--no-pacing"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_INCOMPLETE
    assert [f["show"] for f in info.failures] == ["GratefulDead/1973-06-10"]
```

If `test_sessions.py` does not already import `pytest`, `STATE_COMPLETE` or
`attention_sessions`, add them to its existing import lines rather than
duplicating imports.

- [ ] **Step 3: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -q -k usage_limit`
Expected: FAIL — `_execute` has no `pace` parameter; the limit is caught by the
existing `except (TaskFailed, HerderError, IAError)` and recorded as a failure.

- [ ] **Step 4: Write minimal implementation**

In `packages/llama/src/llama/cli.py`, add imports:

```python
from herder.limits import RateLimited
from llama.pacing import PaceOptions, format_delta, pace_options, resume_at, sleep_until
from llama.sessions import STATE_PAUSED, mark_paused
```

Add the parameter to `_execute`'s signature:

```python
def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False,
             force_stage: str | None = None,
             full_rationale: bool = False, plan: bool = False,
             pace: PaceOptions | None = None) -> None:
```

and immediately after `providers = make_providers(config)` add:

```python
    pace = pace or pace_options(config)
    set_capture_dir(config.root / "llm-failures")
```

with `from herder.failures import set_capture_dir` added to the imports at the
top of `cli.py`. This is the one place capture is switched on: every provider
built by `make_providers` shares the module-level destination.

Replace the block from `packaged = held = 0` through the `mark_complete(ws, outcome)`
tail with:

```python
    setlistfm = make_client(config)
    packaged = held = 0
    failures: list[dict] = []          # {show, error} per show this run lost
    limited: RateLimited | None = None  # set when a usage window ran out

    def _process(entry):
        nonlocal packaged, held, limited
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force,
                               setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
                               force_stage=force_stage, profile=criteria.profile)
        except RateLimited as exc:
            # Not a failure: nothing is wrong with this show. Its finished
            # stages are on disk and a resume redoes only what is missing.
            if not pace.enabled:
                typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
                failures.append({"show": entry.candidate.performance_id, "error": str(exc)})
                return
            limited = exc
            return
        except (TaskFailed, HerderError, IAError) as exc:
            if isinstance(exc, TaskFailed) and exc.raw_output:
                failure_path = ws.show_ws(entry.candidate.performance_id).dir / "llm-failure.txt"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(exc.raw_output)
            typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
            failures.append({"show": entry.candidate.performance_id, "error": str(exc)})
            return
        if pkg:
            typer.echo(f"packaged: {pkg}")
            packaged += 1
        else:
            typer.echo(f"needs-review, skipped: {entry.candidate.performance_id}")
            held += 1

    def _outcome() -> str | None:
        parts = []
        if packaged:
            parts.append(f"{packaged} packaged")
        if held:
            parts.append(f"{held} held")
        if failures:
            parts.append(f"{len(failures)} failed")
        return ", ".join(parts) if parts else None

    pending = list(chosen)
    done_before_pause = -1                  # progress watermark; see the guard below
    while pending:
        deferred, unprocessed = [], []
        for idx, entry in enumerate(pending):
            lock_path = ws.show_ws(entry.candidate.performance_id).lock
            try:
                with file_lock(lock_path, blocking=False):
                    _process(entry)
            except Locked:
                deferred.append(entry)         # another run is building it
            # AFTER the call, not before: `pending[idx:]` must INCLUDE the show
            # that hit the limit. Checking at the top of the body instead starts
            # the slice one entry late and silently drops that show from the
            # run, which then reports `complete` having never processed it.
            if limited:
                unprocessed.extend(pending[idx:])
                break
        if limited:
            unprocessed.extend(deferred)
        else:
            for idx, entry in enumerate(deferred):   # come back and wait
                with file_lock(ws.show_ws(entry.candidate.performance_id).lock):
                    _process(entry)
                if limited:
                    unprocessed.extend(deferred[idx:])
                    break
        if not limited:
            break

        when = resume_at(limited, pace)
        wait_s = (when - _pacing._now()).total_seconds()
        reason = str(limited)
        scope = limited.scope
        # No-progress guard: if a whole pause cycle bought us nothing, sleeping
        # again would nap indefinitely against a backend that keeps refusing.
        # Checkpoint instead, and say WHY so it is not read as an ordinary
        # window pause.
        done_now = packaged + held + len(failures)
        stalled = done_now == done_before_pause
        done_before_pause = done_now
        typer.echo(f"paused after {packaged + held} shows: {reason}")
        if stalled:
            typer.echo("  no progress since last pause — checkpointing rather "
                       "than waiting again")
        if not stalled and pace.wait and wait_s <= pace.max_wait_s:
            typer.echo(f"  resumes {when.astimezone().strftime('%H:%M')} "
                       f"({format_delta(wait_s)})")
            try:
                sleep_until(when, echo=lambda m: typer.echo(m))
            except KeyboardInterrupt:
                mark_paused(ws, _outcome(), failures, when.isoformat(), scope, reason)
                typer.echo(f"\ninterrupted; resume with: llama run resume {ws.name}")
                return
            limited = None
            pending = unprocessed
            continue
        if wait_s > pace.max_wait_s:
            typer.echo(f"  resets in {format_delta(wait_s)} — exceeds "
                       f"--max-wait {format_delta(pace.max_wait_s)}")
        mark_paused(ws, _outcome(), failures, when.isoformat(), scope, reason)
        typer.echo(f"  {len(unprocessed)} shows left; resume with: "
                   f"llama run resume {ws.name}"
                   + (f" --max-wait {format_delta(wait_s)}"
                      if wait_s > pace.max_wait_s else ""))
        return

    outcome = _outcome()
    # A run that lost shows stays on the attention list (`run list` is
    # state != complete) until a `run resume` finishes cleanly -- otherwise a
    # usage limit or a dropped connection costs shows silently, and the only
    # record of why scrolls off the terminal.
    if failures:
        mark_incomplete(ws, outcome, failures)
    else:
        mark_complete(ws, outcome)
```

**Clock access must go through the module, never a rebound name.** Import it as:

```python
from llama import pacing as _pacing
```

and read the clock as `_pacing._now()`. A `from llama.pacing import _now` binds
the original function at import time and silently defeats
`monkeypatch.setattr(pacing, "_now", ...)`, which would make every test above
depend on the real wall clock.

- [ ] **Step 5: Wire the CLI flags**

Add to `get`, `run_approve` and `run_resume` the same three options:

```python
    wait: bool = typer.Option(None, "--wait/--no-wait",
                              help="On a usage-limit pause: sleep until the window "
                                   "resets (default), or checkpoint and exit"),
    max_wait: str = typer.Option(None, "--max-wait",
                                 help="Never sleep longer than this (default 6h); a "
                                      "longer wait checkpoints instead. e.g. 30h"),
    no_pacing: bool = typer.Option(False, "--no-pacing",
                                   help="Disable usage pacing: a limit fails the show "
                                        "as it did before"),
```

and in each body build the options before calling `_execute`:

```python
    pace = pace_options(config, wait=wait, max_wait=max_wait)
    if no_pacing:
        pace = replace(pace, enabled=False)
```

(`from dataclasses import replace`). Thread `pace=pace` through `_get_query`,
`_get_profile` and the two `run_*` calls into `_execute`. Validate `--max-wait`
eagerly so a typo fails before the run starts:

```python
    try:
        pace = pace_options(config, wait=wait, max_wait=max_wait)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests -q`
Expected: all pass.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/src/llama/pacing.py packages/llama/tests/
git commit -m "feat(llama): pause and resume a run when the usage window runs out"
```

---

