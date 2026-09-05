# Task 7 — spec-compliance verdict

**Spec verdict: ✅ PASS** (5 findings: 1 Important, 4 Minor; none blocking)

Reviewed against `docs/superpowers/specs/2026-09-04-usage-pacing-design.md`
("Integration", "Rendering a pause", "CLI and config", "Testing"), which is
binding above `task-7-brief.md`. Diff `42d90a4..980e02b`, 4 commits.

The failure mode that matters — a show silently skipped — is genuinely pinned,
and not merely by a green suite: `test_pace_loop.py` drives `_execute` with
three shows and a scripted `process_show`, and asserts the **exact list**
`seen == ["a", "b", "b", "c"]`. Neither `pending[idx + 1:]` nor a top-of-body
`if limited:` can satisfy that list (both yield `["a", "b", "c"]`), so the
constraint is pinned by construction and not only by the implementer's
mutation run. The companion assertion `info.outcome == "3 packaged"` closes the
"complete having skipped a show" case.

## Requirement-by-requirement

| # | Requirement (spec) | Where met | Note |
|---|---|---|---|
| 1 | `except RateLimited` **precedes** `except (TaskFailed, HerderError, IAError)` | `cli.py:263` / `cli.py:273` | Ordering is load-bearing (`RateLimited(HerderError)`, `limits.py:53`). Own arm, own comment saying why. Pinned end-to-end (`test_sessions.py::test_a_usage_limit_pauses_the_run_instead_of_failing_the_show`); implementer's M5 mutation KILLED. |
| 2 | A limit hit is **not** appended to `failures[]` | `cli.py:263-272` | On `pace.enabled` the arm sets `limited` and returns; no `failures.append`. Pinned by `info.failures == []` in three tests (`test_sessions.py`, `test_pace_loop.py::test_a_checkpoint_leaves_the_interrupted_show_for_the_resume`). |
| 3 | Render row 1: `wait` and `when - now <= max_wait` → sleep, then continue | `cli.py:343-355` | `if not stalled and pace.wait and wait_s <= pace.max_wait_s` → `sleep_until`, `limited = None`, `pending = unprocessed`, `continue`. Pinned by `test_a_usage_limit_within_max_wait_sleeps_and_then_finishes` (state COMPLETE, `brief.calls >= 2`, `outcome == "1 packaged"`). |
| 4 | Render row 2: cap exceeded **or** `--no-wait` → checkpoint and **exit 0** | `cli.py:356-363` | `mark_paused(...)` then `return` → exit 0. Both entry conditions pinned separately (`test_a_checkpoint_leaves_the_interrupted_show_for_the_resume`, `test_no_wait_checkpoints_even_inside_the_cap`). |
| 5 | Render row 3: same, but **no show has run yet** → refuse to start, **non-zero** exit | **MISSING** | See Finding 1. Not implemented, and the zero-shows-done case is pinned at exit 0 by test. |
| 6 | `max_wait` is the single mechanism governing whether a pause is waited out; no rule overrides `--wait` | `cli.py:343` | Held for the pacing rules (there are none in phase 1). The approved no-progress guard is a second gate — see Finding 3; a doc-drift issue, not a code fault. |
| 7 | Partially processed show abandoned, artifacts persist, resume redoes only what is missing | `cli.py:314`, `cli.py:317`, `cli.py:323` | The interrupted show is re-queued at the FRONT (`pending[idx:]`), the deferred (`Locked`) queue is merged in, and the deferred pass re-queues from `deferred[idx:]`. All three sites pinned by exact-list assertions. |
| 8 | `--wait/--no-wait`, `--max-wait`, `--no-pacing` on `get`, `run approve`, `run resume` | `cli.py:473`, `cli.py:610`, `cli.py:655` (via `_pace`, `cli.py:162-172`) | One shared helper, so the three cannot drift. `--batch N` and `--force` correctly absent (fixed rail / pre-flight refusal are phase 2). |
| 9 | `--max-wait` validated eagerly, before the run starts | `cli.py:162-172`; called before `_resolve_run` / `_get_query` / `_get_profile` | `ValueError` → `typer.echo(err)` + `typer.Exit(1)`. Pinned on all three commands by a parametrized test asserting `exit_code == 1`, `"not a duration"`, and `seen == []` (`_execute` never ran). |
| 10 | Ctrl-C during a pause is a clean checkpoint, not a traceback | `cli.py:348-352` | `except KeyboardInterrupt` → `mark_paused` + resume hint + `return` (exit 0). Pinned by `test_an_interrupt_during_the_wait_checkpoints_rather_than_losing_the_run`, which also asserts the recorded `resume_after`. |
| 11 | Reactive `PauseUntil` source: exception's `resets_at`, else `now + unknown_reset_wait`, then a re-probe | `pacing.py:resume_at` | Cache lookup is phase 2 and correctly absent. Re-probe = the retry after the sleep. Pinned (`test_a_limit_with_no_named_reset_waits_the_configured_default`). |
| 12 | `STATE_PAUSED` + `mark_paused(ws, outcome, failures, resume_after, scope, reason)` | `cli.py:349`, `cli.py:358` | Both call sites pass all six; `pause_scope`/`pause_reason` verified on disk by `test_a_pause_records_the_reset_time_and_the_scope`. |
| 13 | `_session_json` carries `resume_after` and `pause_reason`, null off a pause (in-flight ruling) | `cli.py:2312-2320` | Landed. Always-present keys; `test_run_list_json_carries_the_resume_time_of_a_paused_run` and `..._keys_are_present_and_null_off_a_pause`. `test_status_cmd.py`'s exact key-set assertion was updated, not weakened. `pause_scope` deliberately omitted — reasonable, `SessionInfo` does not carry it. |
| 14 | Clock read through the module, never a rebound name | `cli.py:29-30` (`from llama import pacing as _pacing`), used at `cli.py:329` | Comment records the trap. The by-name imports on `cli.py:30-31` are all pure functions whose internals read `pacing._now`/`pacing._sleep` at call time, so the monkeypatch still reaches them. M14 KILLED by 3 tests. |
| 15 | Raw capture switched on once per run | `cli.py:184` | `set_capture_dir(config.root / "llm-failures")` after `make_providers`. Pinned (`test_the_run_switches_on_raw_capture_for_every_provider`); M10 was a survivor closed by `980e02b`. |
| 16 | Tests offline/deterministic: no wall clock, no real `$HOME`, no real sleeping | `test_pace_loop.py::_clock`, `test_pacing.py`, `test_sessions.py` | `_now`/`_sleep` monkeypatched on the module; roots are `tmp_path`; `_clock`'s `sleep_budget` turns a non-terminating loop into a failing test rather than a hang. `Config()` (default root) is only ever read for `.pacing`, never for IO. |
| 17 | `RateLimited` in `_with_transport_retry`'s no-retry set | `herder/tasks.py:40` | Pre-existing (earlier task), confirmed still present. |
| 18 | `gather` re-raises `RateLimited` ahead of the broad clause | `stages/gather.py:993` | Pre-existing (earlier task), confirmed still present. |
| 19 | Scope: `PaceOptions`/`pace_options`/`resume_at` in `pacing.py`; `_execute` + three command signatures in `cli.py`; tests | whole diff | Confirmed — see "Scope creep". |

## Adjudication of the two departures

**1. `resume_at` declines a naive `resets_at` — JUSTIFIED.** Verified both
halves directly: `sleep_until(datetime(2026,9,4,11,10), …)` raises
`ValueError: sleep_until requires a timezone-aware datetime`, and the brief's
literal `resume_at` returns the naive value straight into it. The brief's code
therefore raises out of `_execute` at exactly the moment the pause path exists
to handle — the run dies with `error: …` and exit 1 via `main_cli`, no pause
marker, no resume hint. The checkpoint branch would be quietly wrong rather
than loud: `when.isoformat()` records a zoneless instant and
`when.astimezone()` silently reinterprets it as local. Coercing to UTC instead
would risk a multi-hour wake-time error, which is precisely what the spec's
"Sanity bound" paragraph says parsing must never be able to manufacture.
Declining to the known-safe `unknown_reset_wait` is the spec-consistent choice,
and it is unreachable from `herder.limits.parse_reset` (always UTC), so no real
signal is lost. Pinned by
`test_resume_at_declines_a_naive_reset_rather_than_guessing_its_zone`.

**2. `duration_arg` instead of `format_delta` for the hint — JUSTIFIED.**
Verified both ways: `format_delta(7200) == '2h 0m'`, and
`parse_duration('2h 0m')` raises `not a duration: '2h 0m'`. So the brief's hint
prints a copy-pasteable `llama run resume … --max-wait 2h 0m` that the shell
would split and the parser would reject — the operator's one documented escape
hatch from a capped pause would not run. The spec's own sample output
(`resume and wait it out: llama run resume dead-2026-09-04 --max-wait 30h`)
shows a *parseable* argument, so `duration_arg` serves the spec where
`format_delta` breaks it. Rounding **up** is right for the same reason: a
floored value can be shorter than the wait it was printed for and would
checkpoint again identically. `duration_arg(7200) == '2h'`,
`duration_arg(7250) == '2h1m'`. Round-trip pinned
(`test_duration_arg_round_trips_through_parse_duration`) and the loop-level
consequence pinned by
`test_the_resume_hint_prints_a_max_wait_the_shell_can_actually_take`.

## Findings

**Finding 1 — Important. Spec "Rendering a pause" row 3 is not implemented, and
the reachable analogue is pinned to the opposite behaviour.**
The spec's third row is *"Same, but no show has run yet → Refuse to start, exit
non-zero."* Nothing in `_execute` distinguishes zero-shows-done from
some-shows-done: `cli.py:356-363` checkpoints and returns (exit 0) either way,
and `test_sessions.py::test_a_usage_limit_pauses_the_run_instead_of_failing_the_show`
— a one-show run whose only show is refused, i.e. zero shows completed —
asserts `result.exit_code == 0`.
Adjudication: row 3's natural site is the **pre-flight** check (Integration
site 1), which depends on the percent rules and is explicitly phase 2, so its
absence is not a phase-1 implementation fault. But the phase-1-reachable
degenerate case does exist, the brief carried no version of this row, and
nothing in the repo records the deferral — so a phase-2 author reading the
table will find a shipped test asserting the opposite exit code with no note
saying why. **Action: an explicit ruling, not necessarily code.** Either
annotate the spec row as phase 2 alongside the pre-flight, or decide that a run
that packaged nothing should exit non-zero and change it. Do not leave it
undecided.

**Finding 2 — Minor. The prose pause line prints an unparseable value directly
after a flag name.** `cli.py:356-357` emits
`resets in 26h 12m — exceeds --max-wait 6h 0m` (the cap via `format_delta`),
one line above the copy-pasteable `--max-wait 26h13m`. `--max-wait 6h 0m` is
exactly the string `parse_duration` rejects and exactly the hazard
`duration_arg` was introduced to remove; an operator copying the first
occurrence they see gets the broken one. `test_the_resume_hint_prints_a_max_wait_the_shell_can_actually_take`
pins the bad form (`assert "exceeds --max-wait 1h 0m" in out`) as "prose,
unchanged". Suggest rendering the cap with `duration_arg` too, or rewording so
the flag name does not immediately precede a prose duration.

**Finding 3 — Minor (doc drift, not a code fault). The spec's "single
mechanism" sentence is now stale.** The spec states: *"`max_wait` … is the
**single** mechanism governing whether a pause is waited out. No rule overrides
`--wait`."* The approved no-progress guard (`cli.py:337-342`) is a second gate
that declines to wait even with `pace.wait` true and `wait_s` inside the cap.
This is amendment 3 and is not reported as a deviation; the code is right and
serves the spec's own goal of never idling indefinitely. But the guard is a
one-line deletion that a future reader holding the spec sentence would make in
good faith (M3 exists precisely because that deletion is tempting). **Action:
amend that sentence in the spec to carve out the guard**, so the constraint and
its rationale live in the same place.

**Finding 4 — Minor. Run-level stages are outside the pause machinery.** A
`RateLimited` from `interpret` (in `_get_query`, before `_execute`) or from
`search`/`winnow` (inside `_execute`, before the loop) propagates to
`main_cli`, prints `error: …` and exits 1 with no pause marker and no resume
hint — the whole run is lost. This matches the spec's phase-1 wording (the
reactive path is defined "at the show boundary") and is out of this task's file
scope, but it is a real hole against the goal "a long run survives window
exhaustion", and `winnow` is where the spec itself says the opening burst is
spent. The implementer filed it (report, Concern 1) with the right open
question: what `mark_paused` should record for a run with no shortlist yet.
Recommend a filed follow-up rather than in-task work.

**Finding 5 — Minor. `set_capture_dir` is a process-global set per `_execute`
call.** Correct for the CLI (one run per process), pinned by test, and flagged
by the implementer (Concern 2). Noted only so that a future in-process
multi-run caller does not inherit it silently.

## Scope creep

**None.** No usage-cache reader, no `UsageSnapshot` consumption, no EWMA or
`pacing-state.json`, no percent thresholds, no `decide()`, no fixed rail, no
`llama pacing` command, no `--batch`/`--force` flags. `PacingConfig`
(`config.py:98-116`) carries only the five phase-1 keys — no
`shows_per_batch`/`five_hour_threshold`/`trust_age` stubs. The one addition
beyond the brief's literal surface, `pacing.duration_arg`, is a phase-1
necessity (Finding/Departure 2), not a phase-2 down-payment.
`_redo_run_level`'s `_execute` call (`cli.py:2055`) is deliberately left on
`pace=None` → config defaults; the spec lists flags on `get`/`run approve`/
`run resume` only, so this is compliant.

## ⚠️ Cannot verify from diff

- **Full-suite count (1736 passed / 7 deselected, from 1703).** Not re-run per
  instruction; taken on the report's evidence. I ran the three pacing-related
  files directly: `test_pace_loop.py` + `test_sessions.py` + `test_pacing.py`
  → **64 passed in 0.72s**.
- **The 14 mutation results.** Deliberately not re-run: a concurrent reviewer
  (`t7qual`) is working the same tree, and mutating shared source would
  contaminate their suite. Mitigation: M1/M2/M4/M6 — the dropped-show family,
  the ones that matter — are verifiable by reading, because the tests assert
  exact ordered lists (`["a","b","b","c"]`, `["a","b","b"]`, `seen[0] == "b"`)
  that no off-by-one can satisfy. I accept the rest on the report's evidence.
- **Real-world behaviour of `when.astimezone().strftime('%H:%M')`** — local-zone
  rendering, not asserted by any test. Harmless (no clock read, display only).
- **Whether `parse_reset` can ever produce a naive datetime** — read as always
  UTC (`limits.py`), consistent with the implementer's claim; not exercised
  adversarially here.

## Tree state

`git status --porcelain` was **empty at start** and empty of anything of mine
at finish. **I made no edits and no commits.**

At finish it reported ` M packages/llama/src/llama/pacing.py` — a one-line
change I did not make and have deliberately **not** reverted:
`max_wait_s=parse_duration(max_wait or cfg.max_wait)` →
`parse_duration(cfg.max_wait)`, i.e. the `--max-wait` override dropped. That is
a live mutation-testing edit by the concurrent code-quality reviewer working
the same tree; reverting another agent's in-flight mutant would corrupt their
run. It is theirs to restore. My own targeted `pytest` run predates it and was
unaffected (it passed 64/64; that mutant would have failed
`test_pace_options_layers_the_flags_over_the_config` and
`test_get_passes_the_pacing_flags_through_to_the_loop`).

This is also why I declined to re-run the mutation table myself — see
"Cannot verify from diff".
The only writes were this file and the scratchpad log; the one command run
against the repo was a read-only `pytest` invocation via
`./.venv/bin/python -m pytest` (never the shebanged `.venv/bin/pytest`).
