# Task 7 — CODE-QUALITY review

**Verdict: Changes requested.** Small and scoped: three missing tests and one
six-word guard. The shipped code is correct on every path I could probe — I
found no behavioural defect. Every one of the implementer's 13 mutants is
independently confirmed CAUGHT, by the intended test. The gaps below are
things the suite does not pin, not things the code gets wrong.

## Harness (all five guards in force)

Private copy at `$D/work/t7-quality/copy`, `PYTHONPATH`-shadowed onto the
worktree's venv interpreter (`.venv/bin/python -m pytest`, never the console
script). Shadowing proved first with a planted `_T7Q_SENTINEL` read back
through `llama.cli.__file__` / `herder.usage.__file__`. **Green baseline
asserted: `1490 passed, 7 deselected`**, and every run's summary line required
to match `passed|failed|error` (a collection failure raises, it does not score
as "caught"). Every anchor asserted `count == 1` before applying. `python -B`,
`-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared per
run, `stdin=/dev/null`. Re-sync + `diff -r` byte-identity before **and** after
every mutation; the copy is byte-identical to the worktree now, and the
worktree is untouched (`git status` empty, HEAD `b67b2a1`). No commits made.
Full log: `$D/t7-quality/t7-quality.log`.

## The 13, verified

M1–M13 all CAUGHT, each by the test the report names (M1 →
`..._not_the_unknown_default`; M4 → 8 tests; M8 → 4; M12 → 3). The claim
stands as written.

## The autouse fixture — proved, not assumed

Two bomb runs over the copy:

1. **Broad bomb** (`subprocess.run/Popen/check_output/call/check_call`,
   `os.system/popen/posix_spawn/exec*/fork`, raising a `BaseException` so
   nothing swallows it). Two live negative controls both fired. Six real
   spawns, all pre-existing multiprocessing lock-race tests
   (`test_locks`, `test_concurrency`, `test_ledger_concurrency`,
   `test_atomic_write`, `test_sessions`) — none `claude`.
2. **`claude`-targeted bomb** over the **entire** suite (llama + herder +
   emcee + scripts): `1827 passed`, and the only failure was my own negative
   control `subprocess.run(["claude","-p","/usage"])`. The paired
   innocent-spawn control passed, so the bomb discriminates.

Conclusion: no test in the repo can spawn the real CLI. `read_usage` has
exactly one non-test caller (`cli.py:218`), so stubbing the name in `llama.cli`
is sufficient today — see Minor 4 for the one thing that makes it fragile.

## Findings

### Important 1 — the pre-flight gate's whole state input is unpinned (survivors N1 + N2)

`cli.py:233-235`. Two mutants survive the full suite:

- `Progress(state.per_show_delta)` → `Progress(None)` — the pre-flight gate
  ignoring the learned cost entirely. **SURVIVED, 1490 passed.**
- `state = pacing_state.read_state(config.root)` → `state = pacing_state.PacingState()`
  — the persisted estimate never loaded at all. **SURVIVED, 1490 passed.**

N4 (the same mutation at the *per-show* gate, `cli.py:390-391`) is caught, so
only the within-run learned value is covered. Nothing anywhere proves that a
`pacing-state.json` written by a *previous* run reaches any gate — which is
the entire payoff of Tasks 4 and 5. The behaviour is right: I wrote the probe
and it pauses correctly ("paused: 5h window at 85%, est 12.0%/show", never
entered the burst). It just is not pinned.

Suggested change — add to `test_pace_loop.py`:

```python
def test_a_previous_runs_estimate_reaches_the_preflight_gate(tmp_path, monkeypatch):
    """The cross-run payoff: 85% is under the 90 ceiling, but a show that a
    PREVIOUS run measured at 12% is not, so the burst never starts."""
    _clock(monkeypatch, sleep_budget=0)
    (tmp_path / "pacing-state.json").write_text(
        json.dumps({"per_show_delta": 12.0, "samples": 2}))
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=85))
    searched = []
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      search=lambda *a, **k: searched.append(1))
    assert searched == [] and seen == []
    assert json.loads(ws.session.read_text())["pause_reason"] == \
        "5h window at 85%, est 12.0%/show"
```

That one test kills both survivors.

### Important 2 — the record-vs-`limited` ordering is unpinned (survivor N3)

`cli.py:408-418`. Moving the `if ran:` record block **above** the
`if limited:` check — so a show that hit a `RateLimited` part-way is folded in
as a completed boundary — **SURVIVED, 1490 passed.** It survives because every
reactive test runs with the conftest stub returning `None`, so `record` is a
no-op there and the ordering can never matter.

The current ordering is correct, and for exactly the reason the code gives for
excluding `Locked`: a refused show did partial work, so its delta is an
under-estimate, the direction that walks into the wall. It deserves the same
one-line test the `Locked` case got. My probe (green today) is:

```python
def test_a_rate_limited_show_is_not_a_boundary(tmp_path, monkeypatch):
    """It did partial work, so its delta is an under-estimate -- the same
    reason a deferred show is not a boundary."""
    ...  # read_usage climbing 10 -> 10 -> 14, process_show raising RateLimited
    assert pacing_state.read_state(tmp_path).samples == 0
```

### Important 3 — `record` writes a useless artifact and takes a lock on every non-pacing run (survivor N12)

`cli.py:411-418`. When `_meter` returns `None` — every `openrouter`/`fake`
backend, and every `--no-pacing` run — `record(root, None, None)` still does
`root.mkdir` + `file_lock` + `write_artifact` once per show. Measured, not
inferred: on a fake-backend two-show run the workspace ends up with

```
pacing-state.json  ->  {"per_show_delta": null, "samples": 0}
```

and a lock acquisition per show. That is a new file in every emcee-only /
openrouter user's workspace, plus per-show lock IO the feature never reads.
Guarding it is behaviourally invisible to the suite (N12 **SURVIVED**), so it
is a safe change:

```python
            if ran and reading_before is not None:
```

with the reason in the existing comment ("nothing to fold when there is no
window to read"). Please also pin it — `assert not (tmp_path /
"pacing-state.json").exists()` on the fake-backend and `--no-pacing` tests,
which currently assert only `seen == ["a"]`.

### Minor 1 — held/failed shows are folded, `Locked` is not, and neither is pinned (survivor N13)

`cli.py:411`. `if ran and not failures and held == 0:` **SURVIVED**, so nothing
pins that a held or failed show *is* a boundary. The asymmetry with the
deliberate `Locked` exclusion is defensible — a failed show really did burn
window, a deferred one really did not — but a show that fails in its first
stage folds a near-zero delta and, at `EWMA_ALPHA = 0.4`, drags the estimate
40% toward zero in one step. That is the same under-estimate the `Locked`
comment calls "the direction that walks into the wall", so the reasoning
should be recorded where it can be argued with: extend the comment at
`cli.py:412-416` to say why a *failed* show is still a boundary, and pin the
held case with one assertion.

### Minor 2 — two meter reads per boundary with nothing between them

`cli.py:389` and `cli.py:417-418`. The "after show N" read and the "before
show N+1" read are separated by only the `record` call — no work at all. A run
therefore spends `2N + 1` `claude -p "/usage"` subprocesses (pinned as exactly
5 reads for 2 shows by `test_the_learned_cost_folds_each_shows_own_before_and_after`)
where `N + 1` carry the same information. Carrying the last "after" reading
forward as the next iteration's `reading_before` — re-reading only after a
sleep, a deferred show, or on the first iteration — halves it.

Whether or not you make that change, `pacing_state.py:3-5` now describes a
protocol the caller does not use: *"The reading taken before show N+1 minus the
reading taken before show N is exactly show N's cost… available for free
because the meter read costs nothing."* The caller measures before/after
instead. Fix one to match the other; a module docstring describing a different
protocol than its only caller is the kind of thing that gets believed later.

### Minor 3 — `test_a_preflight_pause_exits_zero_like_every_other_pause` (`test_pace_loop.py:661`)

The name promises an exit code; the body asserts only
`state == STATE_PAUSED`, and `_drive` calls `_execute` directly, so no exit
code exists to check. It is a strict subset of
`test_preflight_gate_pauses_before_any_stage_runs` (:613). It is brief-verbatim
and it does fail under N7, so it is not dead weight — but either make it earn
its name via the `CliRunner` already in the file (`result.exit_code == 0`), or
fold it into :613 with a comment.

### Minor 4 — the fixture stubs the *name*, not the function

`conftest.py:28-38` patches `llama.cli.read_usage`. That is airtight today
(one caller) and correct per the brief. It stops being airtight the moment a
second module imports `read_usage` — Task 8's `llama pacing` command is the
obvious candidate. Consider `monkeypatch.setattr("herder.usage._cli_runner", ...)`
as a belt-and-braces second line in the same fixture, or a note in the
docstring that a new importer needs a new stub.

## The two deliberate deviations — both adjudicated correct

1. **`_meter(config, pace)` also gating on `pace.enabled`.** Correct.
   `decide` short-circuits on `not opts.enabled`, so under `--no-pacing` the
   brief's signature would spend a subprocess per show on an answer nothing
   reads. Properly pinned: M3 (drop the `pace.enabled` arm) is caught by
   `test_no_pacing_never_reads_the_meter`, M2 (drop the backend arm) by
   `test_gate_is_skipped_entirely_on_a_non_claude_cli_backend`. The one
   side effect is Important 3 above — the gate is skipped but `record` is not.
2. **A `Locked`/deferred show is not a boundary.** Correct, and the stated
   reason is the right one. Pinned twice over: M10 (`if ran:` → `if True:`) and
   M11 (drop `ran = False`) are both caught by
   `test_a_deferred_show_is_not_a_boundary`.

## Things I checked and found clean

- **`reset_skew` applied exactly once on every path.** Pre-flight passes
  `when=verdict.when` (:236-241, skewed once inside `pacing._pause`); the show
  loop keeps `limited.when` verbatim (:436-437); `RateLimited` goes through
  `resume_at` (skew once); a meter with no `resets_at` gets
  `now + unknown_reset_wait_s` and no skew, which is right. Never twice, never
  zero. M1 and M13 pin the two ends.
- **A `PauseUntil` and a `RateLimited` cannot be live in the same iteration.**
  The gate `break`s before `_process` can run, and the sleep branch resets
  `limited = None` (:445) before `continue`.
- **Queue arithmetic.** `pending[idx:]` (gate, :394) is right and pinned (M7,
  N10); `unprocessed.extend(deferred)` on a proactive pause (:419-420) is
  shared with the reactive path and unchanged.
- **The no-progress guard covers a proactive pause loop.** A gate that keeps
  pausing without progress checkpoints on the second cycle rather than napping
  forever; `_clock`'s sleep budget would catch a regression.
- **First show / no `before` / rollover / corrupt state** are all handled one
  layer down by `pacing_state.observe`/`read_state` (Task 4), and `decide`'s
  non-negative precondition holds for every `PacingState` `read_state` can
  return. Nothing in Task 7 can violate it.
- No duplication with the run-level `except RateLimited` (:255-274 — different
  site, different note, both needed), no dead parameters, no misleading
  comments other than Minor 2's docstring, no YAGNI.

## The implementer's own two concerns

Both real, both brief-scoped, neither blocking. **(1) the deferred pass is
ungated** (:422-427) — shows another run held the lock on are processed with no
gate and no boundary, and after a *blocking* acquire the last reading may be
very stale; the reactive backstop covers it at one refused show. **(2) a
pre-flight pause never sleeps even under `--wait`** — `llama get --wait`
started twenty minutes before a reset checkpoints where the show loop would
have waited. I would close (2) in Task 8 if the queue arithmetic allows;
(1) is genuinely a scope call for the orchestrator.

## No tool refused me at any point.
