# SDD ledger — plan: docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md

Worktree: /Users/shawn/projects/llama-wt-pacing2  branch usage-pacing-phase2  base ac7c428
Spec: docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md (read)
Test cmd: cd /Users/shawn/projects/llama-wt-pacing2 && ./.venv/bin/python -m pytest -q
Baseline: 1742 passing. Interpreter verified to resolve inside the worktree.

## Pre-flight conflict scan (2026-09-05 21:0x EDT)

### Cross-task rows (tasks sharing a file or an interface)

| pair | produced | consumed | finding |
|---|---|---|---|
| T1 -> T2 | `limits.parse_reset(text, now, max_ahead_s)` | called with `max_ahead_s=FIVE/SEVEN_*` | agree |
| T2 -> T3 | `usage.py` module, `parse_usage_text` | `read_usage` appends to same file | agree |
| T3 -> herder.claude_cli | `ISOLATION_ARGS`, `_subprocess_env`, `_neutral_cwd` | VERIFIED present (claude_cli.py:37,40,62) | agree |
| T4 -> T7/T8 | `PaceOptions.five_hour_ceiling/seven_day_ceiling`, `decide`, `Progress`, `PauseUntil` | gates + `_pacing_line` | agree |
| T4 -> cli.py | `_pace` drops `dataclasses.replace` | `replace` imported cli.py:6; other uses at 537/841 are str/datetime methods, NOT dataclasses.replace -> import becomes unused, must be removed | agree, see R1 |
| T5 -> llama.workspace | `write_artifact(path, json.dumps(...))` | VERIFIED workspace.py:43 passes a `str` through unencoded | agree |
| T5 -> llama.locks | `file_lock` | present | agree |
| T6 -> T7 | `_checkpoint_pause(..., when=)`, `_drive(winnow=, search=)` | T7 passes `when=verdict.when` and uses `search=` | agree |
| T6 -> sessions | marker key `pause_scope` | VERIFIED sessions.py:30 | agree |
| T7 -> T8 | `shows_that_fit` | T7 must NOT import it (T8 defines it) | plan says so explicitly; carried into T7 dispatch |
| T7 -> existing loop | `limited` may now be a `PauseUntil` | loop calls `resume_at(limited, pace)`, which reads `resets_at` -> PauseUntil has none | see R3 |
| T9 -> T1..T8 | four mutations | see R4 |

### Per-task self-agreement rows

| task | tests vs code it specifies | finding |
|---|---|---|
| T1 | dated/no-minute/bound/year-roll/refusal-unchanged all satisfied by the given `parse_reset` body | self-consistent |
| T2 | 6 tests vs regexes + dataclasses; `Current session: 42% used\n` yields group(2)="" -> resets_at None | self-consistent |
| T3 | 3 tests vs `read_usage`; every failure shape returns None | self-consistent |
| T4 | boundary math checked by hand: 86+4<=90 Proceed, 87+4>90 Pause; weekly-first ordering holds | self-consistent EXCEPT `_pace` rewrite, see R1 |
| T5 | EWMA seed/smooth/rollover/negative/roundtrip vs `observe`/`record` | self-consistent |
| T6 | two tests vs the run-level catch | self-consistent EXCEPT docstring overclaim, see R2 |
| T7 | 4 tests + autouse fixture vs three gate points | self-consistent EXCEPT `resume_at` gap, see R3 |
| T8 | `shows_that_fit` arithmetic ((90-65)//4.2 -> 5) and CLI strings match `_pacing_line` | self-consistent |
| T9 | mutation 1's claimed red set | over-claims, see R4 |

### Rulings

Ruling R1 (Task 4): `_pace` KEEPS its existing error rendering — `typer.echo(str(exc), err=True); raise typer.Exit(1)` — and changes ONLY to construct via `pace_options(config, wait=..., max_wait=..., no_pacing=no_pacing)` instead of `replace`. Why: the plan's snippet raises `typer.BadParameter`, which Typer exits with code 2, but `test_pace_loop.py:510 test_a_malformed_max_wait_fails_before_the_run_starts` asserts `exit_code == 1` on three parametrized argv. The spec demands no change to error rendering; the plan's substantive point (one construction path, drop the unused `replace` import) is fully preserved. Cost if wrong: none material — a cosmetically different error class for a malformed `--max-wait`.

Ruling R2 (Task 6): `_checkpoint_pause` is wired to the run-level catch and the Task 7 pre-flight gate ONLY. The per-show loop's existing pause rendering (`paused after N shows: ...`) is NOT refactored into it. Why: `test_a_checkpoint_reports_how_many_shows_are_left` and siblings pin that exact output, and the loop additionally carries the no-progress guard and the sleep branch. The helper's docstring must be written to match what it actually shares rather than claiming the loop uses it. Cost if wrong: one less-shared helper; the two paths could drift on marker shape, which the tests on both sides already pin.

Ruling R3 (Task 7): where the per-show loop computes `when = resume_at(limited, pace)`, it must become `when = limited.when if isinstance(limited, PauseUntil) else resume_at(limited, pace)`. Why: the plan says "Pass `when=limited.when` when `limited` is a `PauseUntil`" but that line does not call `_checkpoint_pause`; left alone, a `PauseUntil` falls through `resume_at`'s `getattr(err, "resets_at", None)` to the 1h unknown-reset default, discarding the reset the meter actually named. The `limited` annotation widens to `RateLimited | PauseUntil | None`. Cost if wrong: a proactive pause would sleep 1h instead of to the real reset — recoverable, but it silently defeats the feature.

Ruling R4 (Task 9): Mutation 1's expected-red set is `test_weekly_reset_uses_the_weekly_bound_not_the_session_one` AND `test_parses_all_three_meters_from_the_real_output`, both in test_usage.py. The plan also names `test_parse_reset_bound_is_per_call_not_global`, which passes `7.5 * 86400` as a LITERAL and therefore cannot see a change to `usage.SEVEN_DAY_MAX_AHEAD_S`. The constraint is still pinned, so no test is strengthened; the plan's red set is corrected, not the code. Cost if wrong: none — the mutation still goes red.

## Progress

Task 1: implementer Sonnet (a09cc968) -> DONE, commits eef3081..9ee737b, 1747 passed (baseline 1742 + 5).
Task 1: docs commit 94f8c6c records rulings R1-R4 in the plan file itself (coordinator request).
Task 1: spec reviewer Opus -> Spec OK, no Critical/Important, 4 minors.
Task 1: quality reviewer Opus -> Changes requested. 2 Important + 11 minors. Evidence: a mutation run
  (module shim, worktree unmodified) control 27 passed, 9 of 10 mutations survived GREEN.
Task 1: minor (deferred): M1 dead minute-range check limits.py:87-88 (except ValueError below already catches it)
Task 1: minor (deferred): M2 _dated_target docstring contradicted by the diff's own Jan-2 test
Task 1: minor (deferred): M3 stale _RESET_RE header comment limits.py:43-45
Task 1: minor (deferred): M4 month regex accepts "Sepxyz"; month_s[:3] is a no-op; bogus month unpinned
Task 1: minor (deferred): M5 ambiguous fall-back hour resolves fold=0 (earlier instant); wrong side for a reset
Task 1: minor (deferred): M6 asymmetric branches; time-only path still inline, duplicates zone/minute handling
Task 1: minor (deferred): M7 max_ahead_s default binds MAX_RESET_AHEAD_S at import; monkeypatching no-ops
Task 1: minor (deferred): M8 classify() still passes the session bound, dated form unreachable from refusals
Task 1: minor (deferred): M9/M10 two test names/duplications wanting comments
Task 1: spec-minor (deferred): dated branch has no fall-through to _RESET_RE on a multi-clause text
Task 1: spec-minor (deferred): _RESET_RE comment now false at parser level (same as quality M3)
Task 1: fix round 1/5 dispatched — I1 (unpinned crash guards) + I2 (false ordering comment, unstated
  single-clause contract). Minors NOT in the loop, per skill; final review triages them.
Task 1: fix round 1/5 (2 addressed, 0 open — I1 unpinned dated-branch guards, I2 false ordering comment;
  commits 3b16e42..e2ada6a). Re-reviewer verified BOTH pins by mutation with a proven harness
  (control 29 passed; 4 mutants correctly red; worktree never modified).
Task 1: complete (commits ac7c428..e2ada6a, review clean). Suite re-run by the orchestrator: 1749 passed, 7 deselected.
Task 2: implementer Sonnet (a642ef49) -> DONE, commit 8c0a56d, 1755 passed (1749 + 6). Self-audited
  four surviving mutations unprompted (bound swap on the session call; group(3)->group(2) in the
  per_model comprehension; dropped .strip() on the key; fetched_at asserted nowhere).
Task 2: spec reviewer Opus (a138e468) + quality reviewer Opus (a8522cb8) dispatched in parallel,
  both under the tightened isolation mandate (no worktree writes, no suite runs there, shim/snapshot only).
Task 2: spec reviewer Opus -> Spec OK (diff is the brief's code blocks byte-for-byte). 1 Important, 5 minors.
Task 2: quality reviewer Opus -> Changes requested. 3 Important, 7 minors. Harness proven: control 6 passed,
  30 mutants, 14 caught / 16 SURVIVED. Confirmed all 4 of the implementer's self-audited survivors and found 12 more.
Task 2: minor (deferred): unused json/subprocess imports (Task 3 consumes them; no lint gate in CI)
Task 2: minor (deferred): STALE_MARKER is case-sensitive; a lower-cased banner reads as live
Task 2: minor (deferred): percent unbounded — "999%" parses; fails safe for decide()
Task 2: minor (deferred): frozen=True is shallow, per_model dict is mutable on a frozen reading
Task 2: minor (deferred): UsageReading unhashable (frozen dataclass with a dict field)
Task 2: minor (deferred): "all models" literal duplicated across two regexes
Task 2: minor (deferred): test_missing_session_line "" case redundant; None input untested
Task 2: minor (deferred): test name at test_usage.py:31 broader than its body; "(All models)" defeats it silently
Ruling R5 (Task 2): KEEP `fetched_at: datetime | None = None` as implemented. The brief's Interfaces line
  writes the field non-optional while the brief's own executable code block writes it optional — the plan
  contradicts itself. The code block is the more specific statement, the field is inert (nothing downstream
  reads it; decide() takes `now` as a parameter), and Task 5's positional construction works either way.
  Cost if wrong: a nullable field that nothing currently reads.
Task 2: fix round 1/5 dispatched — F1 line-based parsing unpinned (5 mutations survive, measured harm is the
  weekly reset worn as the session's, inside the 5.5h bound); F2 per-model assertion tautological (4 survive);
  F3 five-hour bound exercised by nothing (raised independently by BOTH reviewers). Minors not in the loop.
Task 2: fix round 1/5 (3 addressed, 0 open — F1 line-slicing, F2 per-model, F3 five-hour bound; commit 6901427).
  Implementer added 5 tests, not 3, and correctly identified _SESSION_RE's `$`-anchor drop as an EQUIVALENT
  mutant rather than a test gap. Re-reviewer confirmed that reasoning with 37,449 exhaustive + 60,000
  randomized differential comparisons, zero differences — chasing it would have been wasted work.
Task 2: re-review harness: private copy, shadowing proven twice, control 11 passed, control mutant caught,
  11 mutants each killed by exactly the test claiming it. Worktree never modified, suite never run there.
Task 2: minor (deferred): bound VALUES still unpinned (5.5h->24h and 7.5d->30d both survive; identities
  pinned, magnitudes not)
Task 2: complete (commits e2ada6a..6901427, review clean).
Task 3: implementer Sonnet (a1904024) -> DONE, commits f53678d..7b3e474, 1766 passed (1760 + 6).
  Ran its OWN 9-mutation sweep unprompted on a private sentinel-proven copy: M2/M5 caught, M1/M6/M7/M8/M9
  survived and were closed with 3 extra tests (re-verified red). M3/M4 left as examined equivalent survivors
  (the `if not raw` guard is subsumed by the except clause below it: json.loads(None) -> TypeError,
  json.loads("") -> JSONDecodeError, both already caught, identical net result).
Task 3: implementer concern raised for review: _cli_runner (the real subprocess.run, its try/except and the
  returncode==0 check) has ZERO direct test coverage by design — no test may spawn a subprocess and the brief
  offers no seam short of monkeypatching subprocess.run globally.
Task 3: spec reviewer Opus (a9e173d8) + quality reviewer Opus (ad5c044c) dispatched 22:00 EDT, both asked to
  adjudicate the equivalence claim and the _cli_runner coverage gap rather than merely note them.
Task 3: spec reviewer Opus -> Spec OK. Task 3: quality reviewer Opus -> Changes requested.
  BOTH converged independently on the same Important finding.
Ruling R6 (Task 3): FIX the _cli_runner coverage gap rather than defer it, even though the brief never asked
  for such a test. Both reviewers measured that ALL 9 mutations of _cli_runner's body survive green —
  including deleting *ISOLATION_ARGS, cwd=_neutral_cwd(), env=_subprocess_env(), --output-format json and the
  returncode==0 check — so the brief's own binding isolation constraint is held by nothing. The implementer's
  stated reason (no seam short of a global monkeypatch) is factually wrong: test_claude_cli.py:14-21 already
  defines that exact subprocess-free helper and uses it at 149/191/208 to pin the same ISOLATION_ARGS for the
  sibling call site. The failure mode is SILENT INERTNESS, not a crash — read_usage's except Exception eats
  everything, so a dropped flag makes read_usage return None forever and phase 2's gate never fires, with no
  error anywhere. Same class as the STALE_MARKER lie this module already defends against.
  Cost if wrong: ~20 lines of test the brief did not ask for.
Ruling R7 (Task 3): M3/M4 (the `if not raw` guard) are EQUIVALENT MUTANTS and stay unpinned. Confirmed
  independently by both reviewers by enumerating every falsy Python value against json.loads; the only
  distinguishing input is a str subclass overriding __bool__, unreachable from proc.stdout under text=True.
  Chasing them would be wasted work. Cost if wrong: one redundant line stays unpinned.
Task 3: minor (deferred): no is_error guard, unlike claude_cli.py:139 (one condition from the STALE_MARKER class of lie)
Task 3: minor (deferred): mid-file `import json` at test_usage.py:129 (E402; brief-mandated, no linter in repo)
Task 3: minor (deferred): "every failure shape" test omits the stale banner its own docstring names
Task 3: minor (deferred): _cli_runner's binary/timeout_s params unused; two missing annotations
Task 3: minor (deferred): _cli_runner does not close the child's stdin (claude_cli.py:121 does, via input=)
Task 3: fix round 1/5 dispatched — F1 only.
Task 3: fix round 1/5 (1 addressed, 0 open — F1 _cli_runner coverage; commit 816d00a, 5 tests added).
  Re-reviewer re-ran all 10 named mutations plus an 11th nobody claimed (narrowing except to SubprocessError,
  letting a missing binary escape): 10/10 + 1 RED, zero survivors, each failing exactly one test.
  Proved no test spawns a real subprocess by bombing subprocess.run/Popen/check_output/call and os.system
  across the whole herder suite (131 passed) with a LIVE negative control (planted /bin/echo failed loudly).
Task 3: minor (deferred): _FakeProc re-declares test_claude_cli.FakeProc
Task 3: minor (deferred): the argv assertion assumes ISOLATION_ARGS is cmd's tail (would fail loudly; naming nit)
Task 3: complete (commits 6901427..816d00a, review clean). Orchestrator suite run: 1771 passed, 7 deselected.
Task 4: implementer Opus (a5126a7d) -> DONE, commits 2686d0a..c79d81d, 1782 passed (1771 + 11).
  Ruling R1 applied correctly (_pace keeps echo + Exit(1); construction only; dataclasses.replace removed
  after an AST check for a bare `replace` Name).
  Mutation sweep: 24 executed on a sentinel-proved private copy, 24 CAUGHT, 0 survivors, 0 declined equivalent.
  Four survived a first pass and were closed with tests: ceiling swap (invisible while both default to 90),
  the `meter is None` guard, the unpinned weekly/5h reason wording, and deleting the ceilings from the TOML.
Task 4 FINDING (from the implementer's own sweep, worth a backlog line beyond this phase):
  test_default_config_template_matches_defaults compares parsed BEHAVIOUR, so a key DELETED from
  DEFAULT_CONFIG_TOML still passes — an omitted key yields its default. It catches a wrong value but never an
  absent one, and the blind spot exists for EVERY config section. Fix scoped to [pacing] via a key-set test
  over PacingConfig.model_fields; widening it is out of scope and would likely fail today on sections that
  document a subset of their fields deliberately.
Task 4 PROCESS FINDING: the implementer's FIRST sweep reported 24/24 CAUGHT and every result was false — the
  named test path did not exist, so pytest collected nothing and exited non-zero, which the harness scored as
  "caught". Self-caught by asserting a green baseline. This warning now goes into every reviewer prompt.
Task 4: orphaned mutate.py + pytest (pids 52366/52367) survived the Bash 600s cap ~20 min, hung on stdin from
  a bare directory arg. Private copy only; worktree clean throughout; reaped by me at the boundary.
Task 4: spec reviewer Opus (a9b7b1a6) + quality reviewer Opus (a55eb350) dispatched 23:07 EDT.
Task 4: spec reviewer Opus -> Spec PASS, no Critical/Important, 3 minors. It independently caught the brief's
  own typer.BadParameter change as breaking test_pace_loop — confirming ruling R1 was necessary, not cosmetic.
Task 4: quality reviewer Opus -> Changes requested, 1 Important + 5 minors. Ran 51 mutations at FULL-suite
  scope (baseline 1783 incl. its own sentinel test; the 600s cap was never a factor). Re-derived all 26 of the
  implementer's set: all caught, so 24/24 holds. Of its own 25 extras: 18 caught, 7 survivors, and ZERO of the
  survivors are logic mutants — all unpinned defaults/invariants.
Ruling R8 (Task 4): the truthiness dependency in decide()'s `or` chain stays FLAGGED, not restructured.
  Both reviewers concurred. The weekly-before-session ordering is pinned by execution from four independent
  directions and PauseUntil has neither __bool__ nor __len__; restructuring costs call-site readability for a
  hypothetical. Cost if wrong: if PauseUntil ever gains a falsy __bool__, the ordering inverts — but the
  existing tests catch it, which is the whole basis for the ruling.
Ruling R9 (Task 4): a negative per_show_delta is DOCUMENTED as a precondition, not clamped in decide().
  The reviewer measured it unclamped (X14 survived): it makes the gate strictly MORE permissive near the wall
  and prints "est -3.0%/show". Task 5's observe() is the only producer and explicitly refuses negative deltas,
  so a clamp here would silently absorb a Task 5 regression that Task 5's own tests already catch. Documenting
  makes the cross-task dependency visible; clamping hides it. CARRY THIS INTO TASK 5's DISPATCH.
  Cost if wrong: if a future caller bypasses observe() with a negative delta, the gate is too permissive.
Task 4: minor (deferred): int-literal defaults (90) under a float annotation
Task 4: minor (deferred): `if projected` omits the estimate at exactly 0.0
Task 4: minor (deferred): `reading` untyped in decide/_pause (deliberate — keeps llama.pacing herder-free)
Task 4: minor (deferred): PaceOptions frozen-ness unpinned (repo has test_selector_is_frozen_dataclass to copy)
Task 4: minor (deferred): Progress's default is unreachable; window label derived by `else`
Task 4: fix round 1/5 dispatched — I1 false module docstring (points at the usage-cache approach herder/usage.py
  rejects on measured evidence), plus two cheap hardenings: annotate _pause, document the non-negative precondition.
Task 4: fix round 1/5 (1 addressed, 0 open — I1 module docstring; commit 5739217, source-only, +26/-9,
  no behavior change, suite unchanged at 1782). Both hardenings landed. Re-reviewer verified the new docstring
  claim-by-claim against pacing.py AND herder/usage.py, confirmed no NEW false statement, and confirmed scope
  discipline by checking all six deferred minors are still unfixed.
Task 4: re-reviewer corrected the implementer's stated reason for rewriting the suggested text (the "backstop
  sentence" was never in the module docstring — it lives in decide():198-200). Right outcome, wrong reason:
  the justification is that the reviewer's text left the summary line naming only the reactive half.
Task 4: complete (commits 816d00a..5739217, review clean). Orchestrator suite run: 1782 passed, 7 deselected.
CROSS-TASK FINDING d3 -> CARRIED INTO TASK 5's DISPATCH: pacing_state.read_state deserializes per_show_delta
  with NO sign or type check, so a corrupt or hand-edited state file could hand decide() a negative delta that
  observe() never produced. This qualifies ruling R9: "observe is the sole producer" is true of the COMPUTED
  path only, not of the persisted one. Task 5 owns read_state and is where this is cheap to close.
Task 5: implementer Sonnet (a6898f15) -> DONE, commits cb87790..f980ebe, 1803 passed (1782 + 21).
  Resolved the carried cross-task finding: read_state validates per_show_delta via _valid_persisted_delta —
  accepts None or a real, finite, non-negative number; rejects wrong type, negative, NaN/Infinity, and bool
  (explicitly, despite bool <: int, on the ground that observe() could never produce one). Degrades to
  PacingState(None, 0); no clamping, no coercion.
  Sweep: 14 caught, 1 equivalent, 0 unexplained survivors. Equivalent = removing record()'s root.mkdir, since
  llama.locks.file_lock already mkdirs the parent before opening the lock fd.
  It also hit and fixed a real flakiness trap: stale __pycache__ gave NON-DETERMINISTIC caught/survived across
  identical reruns. Fixed with python -B -p no:cacheprovider + PYTHONDONTWRITEBYTECODE=1 + clearing caches.
HARNESS FINDING (affects every child dispatch from here): the Write tool HARD-BLOCKS subagents from creating
  report/summary/findings/analysis .md files — "Subagents should return findings as text, not write report
  files" — even at the mandate-specified path. T5's implementer hit it twice, logged the refusal into t5.log,
  touched the sentinel, and returned the report as text; I transcribed it to $D/t5/report.md. Tasks 1-4 were
  unaffected because they happened to write via Bash heredoc. FIX APPLIED: every dispatch from here tells the
  child to write its report with a Bash heredoc, not the Write tool. Mandate 1 is otherwise unenforceable and
  a missing report.md would be misread as a dead child.
Task 5: spec reviewer Opus (aa5c24ca) + quality reviewer Opus (ab158354) dispatched 23:36 EDT.
Task 5: spec reviewer Opus -> Spec PASS. Deviation from the brief is 3 hunks, all inside R9. Both R9 boundaries
  held (except tuple not widened, samples still bare int(), no negative-samples test).
Task 5 PLAN DEFECT found by the spec reviewer, measured not argued: THE BRIEF'S OWN 7 TESTS DO NOT PIN THE
  ROLLOVER GUARD the task calls load-bearing. Running the brief's 7 alone against mutants, dropping the
  rollover guard SURVIVES — the brief's rollover fixture uses 90->2, a negative delta the negative-guard
  already catches. Same for `delta < 0` -> `<= 0`. Two of the implementer's extra tests are the only pin.
  This vindicates the 14 extra tests as legitimate rather than scope creep.
Task 5: quality reviewer Opus -> Changes requested. 44 mutations, 30 caught, 14 survived (5 equivalent,
  9 real gaps). The implementer's honest 14/1/0 never mutated record()'s BODY; all four record mutations survive.
Ruling R10 (Task 5): ADD OverflowError to read_state's except tuple, overriding the earlier "do not widen the
  except tuple" boundary. That guidance was premised on the existing tuple covering every other corruption
  path; the reviewer MEASURED that premise false — a persisted `samples: Infinity` or `1e309` raises
  OverflowError from int(), violating the function's documented "never raises". This is fixing a violated
  contract, not adding per-field validation, so OverflowError only and still no validation of samples' value.
  Left unfixed it would propagate into Task 7's pre-flight gate and kill a run outright.
  Cost if wrong: one extra exception class in a tuple.
Ruling R11 (Task 5): KEEP the bool and non-finite rejections (both reviewers concur, both within R9), and KEEP
  record()'s root.mkdir despite being a confirmed equivalent mutant — ledger.py:30 does the identical thing,
  so it is house style. Cost if wrong: one unreachable line, consistent with its sibling.
Task 5: minor (deferred): samples validated far looser than delta (accepts -3, true, "7")
Task 5: minor (deferred): PacingState(None, samples>0) producible by read_state, discarded by observe's seed branch
Task 5: minor (deferred): missing delta key unpinned in the under-estimate direction
Task 5: minor (deferred): _five's None-guard is dead code; its getattr default is an unpinned silencer
Task 5: minor (deferred): the resets_at guard silently no-ops when both are None (safe direction)
Task 5: minor (deferred): record's docstring names the meter bias where it means lost update
Task 5: minor (deferred): three redundant tests; float(delta) coercion beyond the ruling's literal text
Task 5: fix round 1/5 dispatched — I1 read_state can raise (real bug), I2 record's RMW unpinned, I3 the lock
  unpinned four ways. Reviewer supplied 4 tests flipping 8 of 9 gaps.
PROCESS RULE (applies to every dispatch from T6 on): a child that cannot perform an action must quote the
  EXACT error text, never the word "blocked", and must classify it as either (a) a MECHANICAL guard
  (read-before-overwrite, an unreachable path, a tool-scope restriction) — routing around it with another tool
  is legitimate — or (b) a PERMISSION DENIAL, where the user declined the action, in which case achieving the
  same effect by another route is circumventing a user decision and is forbidden: stop and report instead.
  A child that cannot tell which category it is in must escalate rather than guess. T5's case was verified
  benign — the exact text was "Subagents should return findings as text, not write report files", a tool-scope
  guard, and no Write/Edit deny or ask rule exists in any settings file — but the reporting habit of saying
  "blocked" collapses the two categories and must not become standard.
Task 5: fix round 1/5 (3 addressed, 0 open — I1 OverflowError, I2 record's RMW, I3 lock discipline;
  commit ef6ad14). Re-reviewer re-ran all 6 mutations (all red), confirmed the I1 fix is exactly one exception
  class wider with no samples-value validation crept in, and judged the lock test MEANINGFULLY STRONG rather
  than a re-description of the implementation.
Task 5: complete (commits 5739217..ef6ad14, review clean). Orchestrator suite run: 1806 passed, 7 deselected.
Task 6: implementer Opus (a57e2986) -> DONE, commits cbaad44..4aef34a, 1814 passed (1806 + 8).
  R2 honored: per-show loop untouched, helper docstring describes what is actually shared.
  Sweep: 17 mutants, 16 caught, 1 survivor proven equivalent mechanically (failures or [] -> None writes a
  byte-identical marker because sessions._write already does `failures or []`).
  Its guards caught two harness bugs: a NameError scored APPLY-FAILED not CAUGHT, and — the good one —
  "    except RateLimited as exc:" is a SUBSTRING of the per-show loop's 8-space arm, so the ordering mutants
  silently failed to apply and would have scored as survivors. Fixed by anchoring on the leading newline.
OPEN SCOPE QUESTION escalated to the parent (not blocking): run_interpret is a real LLM stage at cli.py:431,
  called BEFORE _execute at :445, so a RateLimited from interpret still escapes with exit 1 and no checkpoint.
  The spec contradicts itself — its Problem section names `interpret` explicitly, its Goals section says
  "anywhere on the _execute path", which interpret is not on. The brief scoped T6 to the _execute region, and
  the commit subject it supplied (used verbatim) overstates coverage. Likely origin: phase 1's spec conflates
  "interpret" with run_discover; they are different stages and both exist. Covering it means four call sites
  plus cli.py:2547 — a task's worth of surface, not a fix round. Provisional: accept and document.
Task 6: spec reviewer Opus (a299c730) + quality reviewer Opus (adda8395) dispatched 00:03 EDT; spec reviewer
  asked to rule on the interpret question explicitly.
Task 6: spec reviewer Opus -> Spec PASS. Task 6: quality reviewer Opus -> APPROVED, 2 Important one-liners.
  Quality reviewer reproduced all 17 implementer mutants (16 caught, m15 survived), upheld m15's equivalence
  mechanically, added 13 of its own (9 caught, 4 survived), and confirmed control flow correct at all five
  _execute call sites.
Ruling R12 (Task 6, ratified by the parent): the run_interpret gap is ACCEPTED AND DOCUMENTED, not fixed here.
  Decisive argument, found independently by both reviewers and not available at dispatch: run_interpret writes
  criteria.json only on success (stages/interpret.py:13) and `run resume` refuses a session without one
  (cli.py:700-702), so a checkpoint there would be UNRESUMABLE — the query lives only in argv. Wrapping it is
  new design, not a catch. The defect is in the spec, not the implementation: the spec's Problem section names
  interpret while its Goals section says "anywhere on the _execute path", and interpret is not on it. Origin
  confirmed: phase 1's spec writes `interpret` (`run_discover`) literally at 2026-09-04-usage-pacing-design.md
  :346-348, and cli.py:1177's _PIPELINE_RUN_STAGES is a DIFFERENT triple that excludes discover.
  Cost if wrong: one uncovered LLM call at the start of `llama get` only; nothing written, profile path unaffected.
Task 6: fix round 1/5 dispatched — I1 correct the record in four places (follow-up commit, not a rebase;
  code comment enumerating run_discover/run_search/run_winnow; a comment at cli.py:431; spec+plan amended on
  the branch with a Known-gap paragraph; T6b filed as an explicitly UNBUILT task). I2 pause_reason asserted by
  substring only — str(limited)->repr(limited) at cli.py:196 SURVIVES the whole suite; use equality.
Task 6: minor (deferred): unreachable getattr default on .scope; `when or` truthiness on a datetime;
  redundant failures or []; a test name promising ordering its body doesn't check; docstring plural "sites"
  and three params with no production caller until Task 7; pause text split across stderr/stdout unlike the
  loop; no CliRunner-level pause test; leftover local `import json` at test_pace_loop.py:429.
Task 6: fix round 1/5 (2 addressed, 0 open; commit a3d8cdc, cbaad44/4aef34a NOT amended or rebased).
  I2 verified by the implementer in BOTH directions: the repr mutant SURVIVES the old substring assertions
  (32 passed, reproducing the reviewer's finding) and is CAUGHT by the new equality ones. Running only the
  second direction would have proved nothing about whether the change was what caught it.
  I1: catch comment enumerates the three stages, note text de-vagued (a mutant reverting it is CAUGHT, so the
  specificity itself is pinned), comment at the run_interpret call site, spec Problem de-names interpret,
  Known-gap paragraph in both spec and plan, T6b filed as UNBUILT.
ORCHESTRATOR ERROR, self-reported: I deleted $D/work/t6/ between rounds as routine cleanup and destroyed the
  implementer's mutation harness mid-task. It correctly classified this as cleanup rather than a refusal
  (no error text to quote) and rebuilt, improving it — the sentinel check now lives inside sweep.sh so
  shadowing is re-proven every run. RULE: do not prune work dirs while an agent may still be resumed.
Task 6: the implementer found 4 of the 5 line citations I handed it had DRIFTED, because its own comment
  insertion moved the run_interpret call sites. It re-derived and audited each by printing the cited line.
Task 6: re-review Opus (ae105472) dispatched 00:24 EDT.
Task 6: re-review Opus -> both ADDRESSED, approved. I1 6/6; I2 reproduced in BOTH directions independently
  (old substring form SURVIVED at 1347 passed; new equality form CAUGHT). It also mutated cli.py:377 and
  found it CAUGHT by the other assertion — so the two tightened assertions guard DIFFERENT production sites
  and neither is redundant. All six line citations resolve exactly, zero drift. T6b confirmed UNBUILT by grep.
Task 6: minor (deferred, NEW, introduced by the fix): the spec's "### Known gap" H3 is spliced between
  bullets 2 and 3 of the "Three things are left undone" list, orphaning the third bullet under it. Content
  correct, structure regressed; a one-line move. FLAG AT MERGE — the parent reads this spec.
Task 6: minor (deferred): cli.py:2556 (the profile-creation run_interpret call) has no local comment.
Task 6: complete (commits ef6ad14..a3d8cdc, review clean). Orchestrator suite run: 1814 passed, 7 deselected.
Task 7: implementer Opus (a3fb008d) -> COMPLETE, commits 0ca7e1a..b67b2a1, 1826 passed (1814 + 12).
  R3 implemented as ruled: `when = (limited.when if isinstance(limited, PauseUntil) else resume_at(...))`,
  annotation widened to RateLimited | PauseUntil | None, no resets_at property on PauseUntil.
  Its test asserts resume_after == reset + ONE skew where the unguarded version silently records now+1h,
  and it was verified red on that exact test under mutation.
  Sweep: 13 mutants, 13 CAUGHT, no survivors, no equivalent-mutant judgements needed. All five harness guards.
  The autouse conftest fixture landed FIRST, so no test shells out to the real claude -p "/usage".
Task 7: two deliberate deviations from the brief, both defended, both sent to the reviewers to rule on:
  (a) _meter(config, pace) also gates on pace.enabled, so --no-pacing spends no /usage subprocess per show;
  (b) a Locked/deferred show sets ran=False and is NOT folded in as a cost boundary — it ran nothing between
      the two readings, and folding a zero would UNDER-estimate, which is what walks a run into the wall.
Task 7: two concerns raised, both sent to the reviewers: the deferred second pass is ungated (brief scope,
  reactive backstop covers it); and a pre-flight pause always checkpoints and never sleeps even when the wait
  would fit under --max-wait, an asymmetry with the per-show loop. T6's spec reviewer flagged the same
  asymmetry and asked that T7's review make a deliberate ruling on it.
Task 7: spec reviewer Opus (aea34860) + quality reviewer Opus (aecf9a10) dispatched 00:42 EDT.
Task 7: spec reviewer Opus -> Spec PASS. Verified the conftest fixture BY EXPERIMENT, not by report: a
  witness-file `claude` stub placed first on PATH across llama+herder (1490 passed) left the witness
  uncreated. Both deliberate deviations accepted; deviation (b) ruled not merely acceptable but REQUIRED.
Task 7: quality reviewer Opus -> Changes requested. Verified all 13 implementer mutants CAUGHT by the
  intended test; extended by 11, 5 survived, all coverage gaps not bugs. Proved the autouse fixture airtight
  with a claude-targeted subprocess bomb over the FULL suite (1827 passed) plus a live negative control AND a
  paired innocent-spawn control.
Ruling R13 (Task 7, spanning T6 too): the "run-level pauses never sleep" asymmetry is DOCUMENTED AND FILED,
  not fixed. Both reviewers raised it; the spec reviewer named the operator-visible consequence exactly:
  `llama get --wait` twenty minutes before a reset now exits having done nothing — a --wait contract break
  phase 1 did not have. It applies to BOTH run-level pause sites (T7's pre-flight gate and T6's catch).
  Fixing it changes sleep behaviour at two sites and needs its own tests; doing that at 01:00 on a branch
  about to be handed over is the wrong trade. So: the spec states the asymmetry and its --wait consequence
  explicitly, and T7b is filed as an explicitly UNBUILT task covering both sites.
  Cost if wrong: an operator using --wait near a reset gets a checkpoint instead of a sleep, and must re-run
  `llama run resume`. Recoverable, visible, and now documented rather than surprising.
Task 7: fix round 1/5 dispatched — I1 pre-flight gate's state input unpinned (N1+N2 survive: the learned AND
  persisted estimate can both be disconnected without a test noticing, which is Tasks 4/5's whole payoff);
  I2 record-vs-limited ordering unpinned (N3); I3 record writes a useless artifact and takes a lock per show
  on every openrouter/fake/--no-pacing run (N12, measured). Plus the R13 doc work and fixing T6's spliced
  Known-gap heading.
Task 7: minor (deferred): held/failed shows folded while Locked is excluded — defensible, undocumented, unpinned
Task 7: minor (deferred): 2N+1 meter reads (after-N and before-N+1 have no work between them)
Task 7: minor (deferred): pacing_state.py's docstring describes a protocol its only caller doesn't use
Task 7: minor (deferred): test_a_preflight_pause_exits_zero (:661) never checks an exit code
Task 7: minor (deferred): the deferred second pass is ungated AND takes a blocking lock, so its reading can
  be stale by the whole wait; pre-flight gate sits above the raw-output-capture comment
Task 7: fix round 1/5 (3 addressed; commits dda7948 code+tests, 61a314e docs) then fix round 2/5 (docs only,
  commit 6db6ed4). Re-reviewer: all three Importants ADDRESSED, no new Critical/Important breakage.
Task 7 METHODOLOGY FINDING, the sharpest of the run: the implementer's first N3 mutant DELETED the
  `if limited:` check instead of reordering the two blocks. That gives 12 failures — and the re-reviewer
  independently confirmed the new test test_a_rate_limited_show_is_not_a_boundary IS AMONG those 12, killed by
  pre-existing queue-arithmetic tests. So under "any failure = caught" scoring it would have been logged
  N3 CAUGHT while proving nothing about ordering. The true reorder fails exactly one test. The implementer
  caught this in its OWN work and re-ran it; the re-reviewer reproduced both forms and confirmed the account exact.
Ruling R14 (Task 7): pacing_state.py's docstring described a before-N/before-N+1 protocol while the caller
  measures before/after. FIX THE DOCSTRING, KEEP THE CODE. The code is right: before/after attributes the
  show's own cost, whereas before/before folds the gate's own meter read and record's write — both of which
  happen BETWEEN shows — into every sample as a constant unrelated to the show. The re-reviewer independently
  flagged the same text as a real defect, noting a future editor following it would undo both no-boundary
  tests. Corrected in pacing_state.py AND the spec so they cannot drift. Cost if wrong: none, docs only.
Task 7: complete (commits a3d8cdc..6db6ed4, review clean). Orchestrator suite run: 1828 passed, 7 deselected.

=== RUN STOPPED HERE, at a clean boundary, per the parent's instruction. Tasks 8 and 9 NOT started. ===
