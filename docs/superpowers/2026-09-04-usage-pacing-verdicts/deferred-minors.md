## Deferred minors awaiting final triage
Task 1: minor (deferred): capture filename uniqueness rests on `time.monotonic_ns() % 1_000_000` — implementer flagged it as a concern; kept verbatim per the brief.
Task 1: minor (deferred): filename collision (~1e-6, same second + same pid) silently overwrites the earlier capture.
Task 1: minor (deferred): capture stamp is unmarked local time and appears only in the filename, not the body.
Task 1: minor (deferred): test_each_capture_gets_its_own_file pins the uniquifier only probabilistically (passes without it when calls straddle a second boundary).
Task 1: minor (deferred): `proc` parameter unannotated, its duck type undocumented.
Task 2: minor (deferred): no hour range guard — `25:10am` silently becomes 1:10am while `11:75am` is rejected.
Task 2: minor (deferred): a naive injected `now` reads as machine-local, making a supposedly deterministic function host-dependent.
Task 2: minor (deferred): nonexistent (spring-forward) wall times resolve 1h late; the ambiguous fall-back case is correct only by `fold=0` accident, undocumented.
Task 2: minor (deferred): exact-equality rollover returns `now` rather than `None` — now pinned, but the choice is undocumented.
Task 2: minor (deferred): `re.Pattern` should be `re.Pattern[str]`; `now = now or ...` where `is None` is meant; generic top-level `herder.classify` export.
- Batch: minor (deferred): `_run`'s TimeoutExpired branch is uncaptured, though TimeoutExpired duck-types with .stdout/.stderr/.returncode so capture_failure(cmd, e) would work; a 900s hang is otherwise undiagnosable.
- Batch: minor (deferred): the three raise sites in `_run` are near-identical; a `_fail(cmd, proc, message) -> NoReturn` helper would have structurally prevented both gaps this review found.
- Batch: minor (deferred): gather.py imports RateLimited from herder.limits while the line above imports from herder, which re-exports it. Cosmetic; herder-internal modules MUST use the submodule (circular import), gather.py need not.
- Batch: minor (deferred): continuation indent at test_stage_gather.py:288. No linter configured.
- Batch: minor (deferred): the spec's own audit note misidentifies cli.py:2505 as belonging to fix/triage; it is main_cli, the global boundary that wraps _execute too. Harmless today (prints `error:`, exits 1, persists nothing) but TASK 7 MUST NOT TRUST THAT LINE VERBATIM — carry this into Task 7's dispatch.
- Batch: minor (deferred): cli.py:1902 (the batch `redo` loop) still burns one limit hit per show. Outside _execute, so outside phase 1's guarantee; real residual for the backlog.

## Also filed, not minors — follow-ups deliberately out of phase 1
- A RateLimited from `interpret`/`search`/`winnow` still loses the run: exit 1, no checkpoint, no paused state. Identical to pre-change behaviour. The fix is the phase-2 pre-flight gate. NOW DOCUMENTED in the spec and CLAUDE.md rather than implied.
- `openrouter.py:37` raises a plain HerderError on any non-200, so an HTTP 429 there is still retried 3x and then fails the show. Phase 1's guarantee is claude_cli-specific. NOW DOCUMENTED.
- `cli.py:1902` (the batch `redo` loop) still burns one limit hit per show; outside `_execute`, so outside phase 1's scope.
- A `_checkpoint(when, scope, reason)` closure would stop the two `mark_paused` call sites drifting; the second site is exactly what a mutation found unpinned. Filed as a refactor, deliberately not done at a window's end.
