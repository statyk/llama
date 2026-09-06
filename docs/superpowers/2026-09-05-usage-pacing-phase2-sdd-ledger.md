# SDD ledger — plan: docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md

Worktree: /Users/shawn/projects/llama-wt-pacing2  branch usage-pacing-phase2  base ac7c428
Spec: docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md (read)
Test cmd: cd /Users/shawn/projects/llama-wt-pacing2 && ./.venv/bin/python -m pytest -q
Baseline: 1742 passing. Interpreter verified to resolve inside the worktree.

## STATUS: COMPLETE (2026-09-06). Read this before anything below it.

Tasks 1-9 all landed and all reviewed. The whole-branch review is done: spec PASS (qualified) and
quality APPROVED, one Critical and four Importants raised and all fixed in a single fix wave, whose
scoped re-review verdicted every finding ADDRESSED with no new breakage. All 61 deferred minors were
triaged (4 fixed, 53 left with named reasons, 4 already closed on-branch).

  branch usage-pacing-phase2, HEAD b628cb2, base ac7c428, 37 commits, tree clean
  suite 1860 passed, 7 deselected (base was 1742)
  test cmd: cd /Users/shawn/projects/llama-wt-pacing2 && ./.venv/bin/python -m pytest -q

NOT merged, NOT pushed, NOT tagged; the worktree still exists. Integration is the root session's call.

DELIBERATELY NOT BUILT -- this is the complete handoff list:
  1. T6b -- checkpoint a RateLimited during run_interpret. Filed, UNBUILT. Covering it is a
     resumability design (the raw query must be persisted at run-claim time), not a catch, because
     run_interpret writes criteria.json only on success and `run resume` refuses a session without one.
  2. T7b -- let the two run-level pause sites honour --wait instead of always checkpointing. Filed,
     UNBUILT. Operator consequence, documented: `llama get --wait` shortly before a reset exits having
     done nothing and needs a manual `llama run resume`.
  3. Rendering the per_model meter in `llama pacing` (ruling R29; the spec was corrected to say two
     meters rather than three, so spec and code agree).
  4. The two counters the spec named on `Progress` (R29/R31; the spec sentence is now marked
     filed-and-unbuilt rather than left promising them).
  5. The spec's "resume costs nothing" test with a call-counting provider (R29/R31; same treatment).

ALSO DELIBERATELY NOT DONE, so nothing here is a surprise later:
  - 53 of the 61 deferred minors, each left with a named reason in the final quality review's triage,
    plus the 6 residual minors from the final re-review adjudicated as R32 at the end of this file.
  - Three commit messages carry numeric claims that do not reproduce (cbaad44, ea14004, daa0c97).
    Report-only by ruling: history was not rewritten under live review. Three of thirty-two is a
    measured rate, not an anecdote. Details at the end of this file.
  - openrouter pacing, which is an explicit non-goal of the spec. openrouter.py is untouched on this
    branch, verified by `git log origin/main..HEAD -- openrouter.py` returning empty.

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

=== RUN 1 PAUSED HERE, at a clean boundary, per the parent's instruction, with Tasks 8 and 9 not
    yet started. A fresh orchestrator resumed the plan and carried it to completion; RUN 2 begins
    immediately below and Tasks 8, 9 and the whole-branch review all landed. See the STATUS block
    at the top of this file for the finished state. ===

=== RUN 2 (fresh orchestrator, 2026-09-06 03:2x EDT). Meter at start: 5h 2%, weekly 21%. ===

## Pre-flight for Tasks 8-9 (re-verified against HEAD 6f7c126, not inherited)

| check | finding |
|---|---|
| T8 snippet calls `_meter(config)` | STALE: cli.py:203 signature is `_meter(config, pace)` (T7 deviation (a)) -> R15 |
| T8 needs `reading` for `_pacing_line` | cli.py:234 passes `_meter(...)` inline to decide, unbound -> R16 |
| T8 uses `Proceed` | NOT in cli.py's import list (cli.py:31-33); must be added alongside `shows_that_fit` |
| T8 `def pacing()` shadowing | safe: cli.py imports the module as `_pacing` (line 28) and `pacing_state`; no bare `pacing` name in the file |
| T8 test monkeypatches `cli_mod.read_usage` | works: cli.py:16 imports the name, `_meter` calls the module global at :218 |
| T8 test default backend | DEFAULT_CONFIG_TOML sets `backend = "claude_cli"` (config.py:200), so `_meter`'s backend gate passes |
| T8 autouse fixture | conftest.py:26 `_no_live_usage_meter` patches `cli.read_usage` -> None; a test-level patch runs after and wins |
| T8 spec sample line vs plan formatter | DIVERGE: spec:~"`~6 of 13 fit`" vs plan's `~6 fit` + separate suffix -> R17 |
| T9 mutation targets | ALL FOUR present: pacing_state.py:54 `b.resets_at != a.resets_at`; usage.py:67 `or STALE_MARKER in text`; usage.py:31 SEVEN_DAY_MAX_AHEAD_S; test_pace_loop.py:464 test_run_level_ratelimited_is_caught_before_herdererror |
| T9 named tests | ALL present: test_usage.py:23/40/60, test_limits.py:195, test_pacing_state.py:30 |
| T9 Step 6 baseline "1742" | STALE: actual baseline is 1828 passed, 7 deselected -> R18 |

Ruling R15 (Task 8): `llama pacing` and `_execute` call `_meter(config, pace)`. The brief's snippet
  predates Task 7's `pace.enabled` gate (cli.py:203-218). Cost if wrong: TypeError on first call, caught
  by any test that reaches it.
Ruling R16 (Task 8): `_execute` binds the pre-flight read to `reading` and REUSES it for the forecast
  line; it does not call `_meter` a second time. Two reads would spend a second subprocess at run start
  and could print a line inconsistent with the verdict just computed from the first.
  Cost if wrong: one redundant subprocess and a possible skew between line and verdict.
Ruling R17 (Task 8): the rendered shape follows the PLAN's `_pacing_line` + `_execute` suffix, not the
  spec's illustrative `~6 of 13 fit before 17:19`. `llama pacing` has no `count`, so "of 13" is not
  available in the shared formatter, and a formatter rendering differently per caller is worse than one
  that does not. The spec line is prose illustration; the plan carries the executable statement.
  Cost if wrong: cosmetic — the run-start line words the same fact differently from one spec example.
Ruling R18 (Task 9): Step 6's expected baseline is 1828 passed / 7 deselected, not the plan's stale 1742.
  Cost if wrong: none; a wrong number would be caught by the run itself.
RUN-2 NOTE: my agentId is ae1a6b246987e7c1a (supplied by the parent; a subagent cannot read its own).
  Every child dispatch from t8-onward carries it as the upward address, with an explicit instruction NOT to
  address a role name — `sdd-orchestrator` is a subagent TYPE, and last run's children fell back to the
  session root because of it. Task 8's implementer was dispatched before I had it and reports to disk only.
RUN-2 NOTE (Task 9 method, from the parent): for each of the four mutations, NAME the expected red test
  BEFORE running, then confirm the failure count matches that expectation rather than merely being non-zero.
  Last run produced a mutant that failed 12 tests for the wrong reason and would have scored CAUGHT under
  "any failure = caught". Red is not evidence until it is red for the claimed reason.
Task 8: implementer Opus (a6ac202d) -> DONE_WITH_CONCERNS, commits ea14004..a42c051, 1835 passed
  (baseline 1828 + 5 brief tests + 2 the implementer added). Orchestrator suite run at a42c051:
  1835 passed, 7 deselected; interpreter re-verified inside the worktree.
  R15/R16/R17 applied as ruled. Its own 5-mutation sweep, all killed, control proven non-vacuous
  (91/48 passed restored, every mutation moved the number). Notable: mutating _execute to call _meter
  a SECOND time breaks two PRE-EXISTING Task 6 read-order tests -- R16's single-read constraint is
  enforced by the suite, not merely by a comment.
Task 8: three UNAUTHORIZED deviations, sent to both reviewers to judge freshly (not pre-judged by me):
  (a) rich_help_panel="Watch" + short_help + a _COMMAND_ORDER entry (no test covers command order);
  (b) `from conftest import cli_invoke` in test_cli_commands.py (repo pattern per test_triage.py:14),
      which kept the brief's test bodies verbatim;
  (c) two extra tests in test_pace_loop.py plus a `choose=` parameter on its _drive helper -- the brief's
      five tests cover `llama pacing`, which has NO `count` and therefore cannot reach the shortfall
      clause at all, so that branch of _execute shipped uncovered.
Task 8 CONCERN raised for review (the DONE_WITH_CONCERNS): `_meter` returns None for THREE reasons --
  a failed read, a non-claude_cli backend, and --no-pacing -- and _execute now prints the same
  brief-mandated "usage read unavailable - pacing on limit errors only" for all three. The implementer
  argues the second half is false under --no-pacing (pace.enabled False, so RateLimited re-raises) and
  under openrouter (phase 1 recognizes no openrouter response as a window exhaustion). It declined to
  change a brief-mandated string and offered three candidate fixes. BOTH reviewers asked to verify the
  factual claim against source themselves and rule; I did not pre-judge it.
Task 8: minor (deferred, self-reported by the implementer): commit ea14004's message says "(16 passed)"
  where the actual result was 13 passed. The COMMAND named in the message is exact and reproduces.
  Not amended -- the dispatch forbids amending existing commits.
Task 8: one line citation I supplied had drifted -- _no_live_usage_meter's `def` is conftest.py:28, not
  :26 (the decorator is at :27). Every other citation I handed it was exact.
Task 8: spec reviewer Opus (acdbeb26) + quality reviewer Opus (a4c329f6) dispatched in parallel,
  independent inputs (brief + global constraints + implementer report + review package only; NO ledger,
  so neither sees the other's verdict). Both under the isolation mandate: no worktree writes, no suite
  runs there, git-archive snapshot + proven PYTHONPATH shadowing + planted sentinel required.
  Both carry the "name the expected red test BEFORE running" scoring rule.
Task 8: spec reviewer Opus -> Spec PASS. All 12 brief requirements delivered; R15/R16/R17 applied
  correctly; openrouter.py untouched; no --batch/--force/trust_age; no new except blocks so the
  RateLimited-before-HerderError ordering is unchanged. Proved shadowing before trusting anything:
  a planted `raise` in the snapshot's _pacing_line moved 91 passed -> 38 failed/53 passed. It also
  independently reproduced the brief's RED prediction at 6f7c126 with a42c051's test files
  (5 failed, 38 deselected). Did NOT verify the full-suite count -- reserved to me by the isolation rule.
Task 8: spec reviewer INDEPENDENTLY converged on the implementer's concern and found it WORSE than
  reported. Verified, not taken on trust: _meter (cli.py:216) has three None paths, all printing the
  identical string (probes with pytest.fail installed as read_usage prove the gate paths never read the
  meter); under --no-pacing the two handlers differ -- cli.py:340 re-raises, cli.py:393 echoes FAILED and
  records a loss -- but neither paces; classify() has exactly two call sites, both in claude_cli.py, so
  openrouter can never produce a RateLimited. THE HALF THE IMPLEMENTER MISSED: `llama pacing` ITSELF
  misprints on both gate paths and then returns with NO verdict -- an operator with
  `[pacing] enabled = false` is told their meter is broken by the one command that exists to answer that.
Ruling R19 (Task 8, ISSUED BY THE PARENT, not by me): the message is FIXED, three-way by cause, because
  the brief was wrong. (a) read failed on claude_cli with pacing enabled -> keep the existing string
  EXACTLY; the reactive backstop really is still live. (b) --no-pacing -> print NOTHING; the operator
  turned the feature off and the line is both false and noise. (c) non-claude_cli backend -> print
  NOTHING; that is the normal steady state for fake/openrouter, and warning once per run would train the
  operator to ignore the line that matters. _execute holds both `config` and `pace`, so distinguishing
  costs nothing. EXPLICITLY FORBIDDEN: making _meter return a reason enum -- the caller already knows
  which case it is, the information was never lost, only discarded at the print site.
  Cost if wrong: an operator reading the line at 3am after a run did nothing is pointed at the wrong
  explanation two-thirds of the time -- which is the defect being fixed, so the cost of NOT fixing is
  the known one.
Ruling R20 (Task 8, mine, extending R19 to the site the parent's ruling did not name): in `llama pacing`
  the two gate cases must NAME THE REAL REASON, not print nothing. R19's "print nothing" reasoning is
  that an unsolicited run-start line is noise; `llama pacing` is the opposite -- a read-only command
  whose entire job is to answer "what is my pacing situation", invoked deliberately. Printing nothing
  there, or the current false string, makes the one command that exists to answer the question refuse to.
  The spec reviewer found this half independently. Cost if wrong: one extra sentence on a read-only
  command; no behavioural surface.
Ruling R21 (Task 8, ISSUED BY THE PARENT): all three unauthorized deviations APPROVED, and one is
  reclassified as not a deviation at all. `from conftest import cli_invoke` is HOUSE STYLE --
  test_cli.py, test_cli_commands.py, test_fix.py, test_show_cmd.py and test_triage.py all do exactly
  this; the plan's fully-qualified form was the outlier. rich_help_panel/_COMMAND_ORDER approved: a new
  command that does not appear in the right help section is half-shipped. The two extra test_pace_loop.py
  tests and the `choose=` param approved and NOT scope creep.
MEASURED INSTANCE (parent's request, second of its kind on this branch): the brief's own five tests
  CANNOT REACH the shortfall clause the brief itself specifies -- `llama pacing` has no `count`, so that
  branch of _execute would have shipped unpinned without the implementer's two extras. This is the same
  finding as Task 5's rollover guard, where the brief's seven tests did not pin the guard the task called
  load-bearing. Two independent instances: a brief's test list is not evidence its own claims are pinned.
VERIFIED-BY-MUTATION NOTE (parent's request): R16's single-read constraint is enforced by TWO PRE-EXISTING
  Task 6 read-order tests, established by mutation (making _execute call _meter a second time turns them
  red), not by reading the code or trusting the comment.
Task 8: minor (deferred): spec asks for "the three meters"; only two render -- per_model is never
  displayed. Brief/spec gap, not an implementation error.
Task 8: minor (deferred): the unavailable line has no `pacing:` prefix while every other return does.
Task 8: minor (deferred): the shortfall clause can name "the reset" on a line carrying no reset time
  when resets_at is None.
Task 8: minor (deferred): astimezone() is machine-local -- CORRECT for an operator-facing line; flagged
  only so nobody later "fixes" it to UTC and prints a reset in a zone the operator does not live in.
Task 8: minor (deferred): CLAUDE.md's new clause omits the verdict line.
FINAL-REVIEW SCOPE ADDITION (parent's instruction): sweep EVERY commit message on the branch for numeric
  claims and confirm each reproduces. Two known already -- cbaad44's subject overstates what landed, and
  ea14004's "(16 passed)" against an actual 13. Two is a pattern, and commit messages are the durable
  record this will be read from in six months. The ea14004 minor STAYS PARKED (not amended): the command
  it names is exact and reproduces in seconds, and rewriting history under live reviewers is worse.
Task 8: quality reviewer Opus -> CHANGES REQUESTED. 35 mutants on a git-archive snapshot, 21 CAUGHT,
  14 SURVIVED, 0 EQUIVALENT. BOTH harness outcomes proven before any result was believed: a planted
  `raise` in the SNAPSHOT's pacing.py gave 40 failed/51 passed (restore -> 91 passed), and a benign
  no-op mutant through the same driver gave 91 passed. Every kill had its expected red test NAMED BEFORE
  running and all 35 matched; the one kill that could plausibly have fired for an unrelated reason (the
  R16 double-read mutant) it opened and read to confirm the assertion was the read-counter. Its mutation
  driver hard-fails with PATCH-ANCHOR-COUNT unless the anchor matches exactly once, so no mutant was
  silently a no-op -- the exact failure that scored a phantom 24/24 on Task 4. Worktree never touched;
  snapshot diff-identical to `git show a42c051:<path>` for all five files afterwards.
Task 8: quality reviewer confirmed _no_live_usage_meter BY EXPERIMENT, not by reading: a BaseException
  tripwire in herder.usage.read_usage on the real-subprocess path gave 1368 passed with the fixture
  intact and 54 failed with it neutered. Not weakened, and 54 tests depend on it.
Task 8: all ten line citations printed and verified; zero drift in the implementer's report.
Task 8: fix round 1/5 dispatched (resumed implementer a6ac202d, Opus) -- F1 R19+R20 (the three-way
  message, via an extracted _meter_applies predicate, no reason enum); F2 the `resets_at is not None`
  arm unpinned while Meter(pct, None) is production-reachable via four parse_reset branches (dropping it
  is an AttributeError at run start); F3 `not per_show_delta` vs `is None` unpinned while observe()
  genuinely emits 0.0; F4 llama pacing's ENTIRE SECOND HALF untested (verdict echo deleted / early return
  removed / branches inverted / persisted state ignored -- green all four times, and with the early
  return gone the unavailable path prints "unavailable" AND THEN "would proceed" while the brief's
  assertion is still satisfied); F5 --config honouring unpinned (load_config(None) survives) despite
  _cfg_file's docstring claiming that isolation and "no real $HOME" being a global constraint;
  F6 the `fits < count` boundary unpinned (`<=` survives, emitting "the remaining 0 pause until the
  reset"; `>` IS caught, so direction is pinned and only the boundary is not). Minors not in the loop.
Task 8: ESCALATED TO THE PARENT, excluded from round 1 -- F-I1: shows_that_fit measures ONLY five_hour
  against five_hour_ceiling and _pacing_line names five_hour.resets_at, but decide() checks seven_day
  FIRST and both ceilings default to 90. Measured through the real formatter:
  `pacing: 5h 20% · weekly 84% · est 4.0%/show · ~17 fit before 06:00` where weekly headroom is ONE show
  and the binding reset is three days out; the gate proceeds at 84+4<=90 so the line prints, with
  `weekly 84%` next to the forecast contradicting it. This is a scope question about what phase 2's
  forecast is defined over, not a defect in the implementation of the brief. Implementer told to leave
  shows_that_fit's signature and both call sites untouched pending the ruling.
Ruling R22 (Task 8, mine): the missing `pacing: ` prefix on the unavailable line stays a DEFERRED MINOR
  this round, though both reviewers want it. R19 says keep that sentence EXACTLY, and I read that
  literally rather than smuggling a reword into a round the plan's author scoped. Flagged upward for a
  one-line overrule. Cost if wrong: one run-start line lacks the marker identifying it as pacing output.
Task 8: fix round 1/5 (6 addressed, 0 open — F1 R19+R20 message, F2 resets_at arm, F3 zero-delta guard,
  F4 llama pacing's second half, F5 --config honouring, F6 fits<count boundary; commits daa0c97..df23158).
  Orchestrator suite run at df23158: 1848 passed, 7 deselected (1835 + 13), interpreter re-verified.
  F2-F6 needed NO source change — every one of those guards was already correct and simply unpinned,
  which is the branch's recurring finding in its purest form. F1 landed as _meter_applies(config, pace),
  the predicate _meter already computed, with no reason enum per R19's prohibition; the failed-read
  sentence is byte-for-byte unchanged; the two "print nothing" tests also assert read_usage is never
  called, so they pin that the gate still saves the subprocess as well as the line.
Task 8: fix round 1 mutation discipline — 11 mutants, expectation ECHOED INTO THE LOG BEFORE each run,
  harness control proven both ways (104 passed restored, every mutant moved it). Ten of eleven matched
  their predicted RED set exactly.
Task 8 METHODOLOGY NOTE (the parent asked that the "name the expected red test BEFORE running" rule be
  recorded as applied and working — it produced findings rather than reassurance): the implementer
  reported M8 as a PREDICTION MISS rather than rounding it to CAUGHT. Inverting the Proceed/pause
  branches failed 4 tests, not the 2 predicted: both predicted tests did fail, but the inversion makes
  the Proceed path evaluate `verdict.reason` on a Proceed dataclass, raising AttributeError and taking
  exit_code non-zero, so every test asserting exit_code == 0 on a proceeding path failed too — including
  one of the brief's own. The mutant is genuinely caught; the model of the blast radius was incomplete.
  Under "any failure = caught" this would have been logged as a clean 2/2 and the incomplete model would
  have survived unexamined.
Ruling R23 (Task 8, ISSUED BY THE PARENT, overturning my R22 deferral): ADD the `pacing: ` prefix to the
  unavailable line. "My intent in R19 was about the sentence's CLAIM — do not assert the reactive
  backstop is live when it is not — never about forbidding a prefix." The parent explicitly endorsed the
  deferral as correct discipline while overruling its outcome. Cost if wrong: none; the sentence's claim
  is untouched.
Ruling R24 (Task 8, ISSUED BY THE PARENT, resolving the F-I1 escalation): FIX IT, in phase 2, as fix
  round 2. "The forecast is not deliberately a session-window instrument — my spec was imprecise and you
  found where. My spec says `llama pacing` reports 'how many shows fit before the reset.' The singular
  'the reset' is the bug." Scope, quoted and bounded: "shows_that_fit computed for both windows, take the
  min, and render the reset of whichever binds. Do NOT add a burn-rate or time-to-exhaustion notion — the
  binding-window concept is enough. Name the bound window in the output when it is the weekly one, since
  'before Sep 9 07:00' without a label reads like a bug rather than a weekly ceiling."
  The parent separately ratified the HANDLING: excluding it from round 1 and freezing shows_that_fit's
  signature was "the right call, not excessive caution — a scope question that changes a public signature
  does not belong inside a fix round scoped to something else."
  Cost if wrong: the forecast would keep contradicting the gate it forecasts whenever the weekly binds —
  an operator reads "~17 fit", starts 13 shows, and gets one show and a pause to a reset three days out.
PARENT-CONFIRMED REACHABILITY (round 1's F2): the real `/usage` output prints `Current week (Fable): 0%
  used` with NO reset clause at all, and parse_reset returns None for an absent, unparseable or
  out-of-bound value. Meter(pct, None) is not a theoretical shape — it is what the live meter produces
  today, one AttributeError at run start away before round 1 pinned it.
Task 8: fix round 2/5 dispatched (resumed a6ac202d, Opus) — G1 the binding-window forecast per R24,
  G2 the `pacing: ` prefix per R23. Three fall-out items called out explicitly so they are handled rather
  than discovered: the two ceilings are independent config fields and must not share one value; the
  current `%H:%M` format renders a three-day-out weekly reset as "07:00", which reads as this morning and
  is worse than the wrong count; and round 1's newly-pinned `resets_at is not None` guard must now follow
  the BINDING window rather than five_hour unconditionally. Signature guidance: prefer adding over
  changing, and if shows_that_fit's brief-pinned signature must change, say so and update its three tests
  deliberately rather than incidentally.
Task 8: fix round 2/5 (2 addressed, 0 open — G1 binding-window forecast, G2 the family prefix;
  commits 2df1de9..3693e45). Orchestrator suite run at 3693e45: 1859 passed, 7 deselected (1848 + 11).
  The reported line now reads `pacing: 5h 20% · weekly 84% · est 4.0%/show · ~1 fit before the weekly
  reset, Sep 8 16:00` where it read `~17 fit before 06:00`. New `binding_forecast(reading, delta, opts)
  -> Forecast | None` calls shows_that_fit once per window against its OWN ceiling, takes the smaller
  count, and carries the BINDING window's own resets_at. Ties go to the weekly window because that is
  where decide pauses. No burn-rate or time-to-exhaustion notion added, per R24's boundary.
Task 8 DECLARED SIGNATURE CHANGE (authorized in advance only if declared with a reason, which it was):
  `shows_that_fit(reading, delta, ceiling)` -> `shows_that_fit(meter, delta, ceiling)`. Reason given:
  "the old shape had `reading.five_hour` IN ITS BODY, which made 'forecast the wrong window' the easiest
  thing a caller could write — and it got written, which is why this round exists. Adding a second
  function beside it would have left that trap loaded." cli.py can no longer express the old bug because
  it no longer has a per-window entry point.
Task 8 FINDING, sent to the re-reviewer to verify MECHANICALLY rather than accept: the implementer
  reports that TWO of the brief-pinned shows_that_fit tests -- test_shows_that_fit_is_unknown_without_an
  _estimate and its own round-1 test_shows_that_fit_treats_a_zero_estimate_as_no_estimate -- WOULD
  OTHERWISE HAVE PASSED ACCIDENTALLY, because a UsageReading is not None so the `not per_show_delta` arm
  short-circuited before the reading was ever inspected. If true this is a third instance of the
  branch's standing theme, and it was caught only because the signature change forced each call site to
  be re-read.
Task 8: fix round 2 mutation discipline — 7 mutants, 7/7 MATCH, expectations written to a file and
  diffed MECHANICALLY against the actual failed set, printing MATCH/MISMATCH, so "close enough" was not
  available to the implementer. N3 (min -> max) enumerated all 13 affected tests up front by working
  through each test's DATA rather than by which tests are "about" the forecast -- the method round 1's
  M8 taught it -- and the three tests that surprised it on paper were in the predicted set because of it.
Ruling R25 (Task 8, mine): fix rounds 1 and 2 get a SINGLE scoped re-review over a42c051..3693e45 rather
  than one each. Round 2 was NOT triggered by a round-1 re-review failure — it was a new finding the
  parent ruled on (R24) while round 1 was in flight — so two re-reviews over adjacent ranges would read
  the same files twice and the second would subsume the first. Cost if wrong: round 1's fixes get their
  verdict slightly later, from a reviewer that also sees round 2's changes layered on top.
Task 8: scoped re-review Opus (a94463de) dispatched over a42c051..3693e45 (4 commits), under the same
  snapshot isolation and pre-named-expectation rules. Asked to scrutinize three things harder than the
  rest: the declared signature change and whether the three brief tests still test what they were written
  to test; the accidental-pass claim, verified mechanically; and the tie-break, checked against decide()'s
  actual ordering rather than the report. Also told to SPOT-CHECK the implementer's mutation tables --
  a mutation table is exactly the artifact that was fabricated earlier on this branch.
FINAL-REVIEW SCOPE ADDITION #2 (parent's instruction, and they judge it the most valuable thing the final
  review can do). The "would have passed accidentally" finding is the THIRD measured instance on this
  branch of one defect class: (1) T5 -- the brief's rollover fixture used 90->2, a negative delta the
  negative-guard already catches, so the rollover guard the task calls load-bearing was pinned by nothing
  in the brief's own tests; (2) T8 round 2 -- two brief-pinned tests passed because a UsageReading is not
  None and the `not per_show_delta` arm short-circuited before the wrong-window path was reached;
  (3) across the run -- F2-F6 and most of T1-T3's findings were guards that were CORRECT and simply
  UNPINNED. The parent's framing: "The pattern is not 'tests are missing.' It is TESTS THAT ARE GREEN FOR
  A REASON OTHER THAN THE ONE THEIR NAME CLAIMS, which is strictly worse than a missing test because it
  advertises coverage that does not exist. My plan produced them repeatedly."
  NAMED DELIVERABLE for the final review: for each test THE PLAN ITSELF SPECIFIED, confirm it fails when
  the behaviour it names is broken. NOT a fresh mutation sweep of the source -- that has been done
  per-task and thoroughly. This is narrower and different: take the brief-pinned tests specifically,
  break the thing each one CLAIMS to check, and confirm that test goes red. Any that stay green are the
  same class as the three above, and they are the ones nobody has looked at, "because every sweep so far
  started from the source rather than from the test's own claim."
FINAL-REVIEW SCOPE, consolidated -- three named deliverables plus the triage:
  (i)   triage the ~46 deferred minors (list extracted to $D/briefs/deferred-minors.md); fix or park each
        with a NAMED reason. A count of rulings is not a ruling.
  (ii)  sweep EVERY commit message on the branch for numeric claims and confirm each reproduces.
        Two known already: cbaad44's subject overstates what landed, ea14004's "(16 passed)" was 13.
  (iii) the brief-pinned-test audit above: break what each plan-specified test NAMES, confirm it reddens.
Task 8: scoped re-review Opus (a94463de) -> ALL EIGHT findings ADDRESSED (F1-F6, G1, G2), NO new
  Critical/Important breakage. 18 mutations, 18/18 EXACT expected-set matches, every expectation named
  before running. Harness proven both ways (115 passed control; a planted raise in the SNAPSHOT's
  binding_forecast gave 51 failed; full snapshot suite 1859 passed/7 deselected, matching my independent
  worktree run). Test arithmetic reconciles: 24 added, 0 lost, 1835 -> 1859. Worktree never modified.
Task 8: the re-reviewer added two mutants of its own that the implementer had not run, and the better one
  is R17 -- a DIRECT REVERT of the G1 fix (drop the seven_day candidate, restoring the five-hour-only
  forecast) reddens 8 tests. So the fix is pinned against being UNDONE, not merely against being
  perturbed. That is a stronger property than any perturbation mutant establishes and is worth copying.
Task 8: re-reviewer SPOT-CHECKED both of the implementer's mutation tables by independent execution and
  found NO fabricated or rounded row. Round 1's M8 self-reported miss is real and correctly described.
  Round 2's N3 thirteen-name enumeration -- the row most susceptible to hand-waving -- is exactly right;
  the re-reviewer derived the same 13 names independently from each test's data before running. One
  benign divergence explained: its R5 gives 2 red where M5 predicted 1, because the second test did not
  exist in round 1.
Task 8 (a) SIGNATURE CHANGE RATIFIED, with decisive evidence the implementer did not have: the BRIEF'S
  OWN _pacing_line sketch (task-8-brief.md:102-105) is where the G1 bug came from -- it calls
  shows_that_fit(reading, ..., five_hour_ceiling) and renders reading.five_hour.resets_at. So "the pinned
  shape made the wrong-window call the obvious one" is DEMONSTRATED, not rationalized after the fact.
  The three brief tests were not weakened; coverage is UP -- the old guard's `reading.five_hour is None`
  arm had NO test at a42c051, its successor has two.
Task 8 (b) THE ACCIDENTAL-PASS CLAIM VERIFIED MECHANICALLY, not accepted: reverting all four call sites
  to whole UsageReadings leaves EXACTLY the two named tests green while the other two die with
  `AttributeError: 'UsageReading' object has no attribute 'percent'`. Claim accurate, and self-reported
  by the implementer rather than found in review.
Task 8 (c) TIE-BREAK CORRECT against decide()'s actual code, not the report: pacing.py:226 evaluates
  _pause(reading.seven_day, ...) first and short-circuits; min returns the first minimal element and the
  seven_day candidate is listed first. Pinned by R13.
Task 8: minor (deferred, NEW from the re-review): a five_hour=None reading is UNREACHABLE in production --
  parse_usage_text returns None outright when the session line is missing (_SESSION_RE is mandatory) --
  so _pacing_line's `reading.five_hour is None` arm and test_a_window_with_no_meter_does_not_compete's
  only_weekly half are defensive-only, AND mutually inconsistent: binding_forecast would forecast a
  weekly-only reading that _pacing_line short-circuits past before ever calling it.
Task 8: minor (deferred, NEW): binding_forecast is computed twice on the _execute path (inside
  _pacing_line and again beside it). Pure and cheap, but threadable from one call.
Task 8: minor (deferred, NEW): docs drift on G2 -- the plan (:1496) and spec (:405) still show the
  unavailable sentence WITHOUT the `pacing: ` prefix the code now carries.
Task 8: minor (deferred, NEW): a 5-hour reset crossing midnight renders as a bare `02:00` with no date.
  Implementer flagged it as an accepted edge; re-reviewer agreed (it reads as "tonight"). Recorded so it
  is not rediscovered.
Task 8: minor (deferred, NEW): the load_config(None) mutant's kill is mildly environment-coupled -- it
  depends on the operator having a real ~/.llama/config.toml. Two of its three killers are
  config-content tests so the kill is robust in practice.
Task 8: COMPLETE (commits 6f7c126..3693e45, review clean; 2 fix rounds, 8 findings all addressed).
  Orchestrator suite run: 1859 passed, 7 deselected.
Task 9: implementer Sonnet (a57a3989) dispatched. Baseline corrected to 1859 per R18. Carries: R4's
  correction to mutation 1's red set; the Task 5 finding that the brief's own rollover fixture does not
  pin the guard mutation 2 targets (two Task-5 tests do); the GENUINE-REORDER-NOT-DELETION requirement on
  mutation 4 with both measured traps (the 4-space arm is a substring of the loop's 8-space arm; the
  deletion form gives 12 failures and scores CAUGHT while proving nothing); prove-both-outcomes; prove
  each mutation applied via git diff; and the instruction to treat the four as a FLOOR, not a ceiling,
  since every per-task sweep on this branch already exceeded what Task 9 specifies.
Task 9: implementer Sonnet (a57a3989) -> DONE. NO MUTATION SURVIVED, so no production or test change and
  NO COMMIT. Tree byte-identical to 3693e45, verified by me: `git diff 3693e45 --stat` empty,
  `git status --porcelain` empty, HEAD 3693e45, suite 1859 passed / 7 deselected before and after.
  Six mutations, not the brief's four -- it took "floor, not ceiling" literally and added
  FIVE_HOUR_MAX_AHEAD_S and the PER-SHOW RateLimited/HerderError ordering.
Task 9 FINDING 1 (mismatch reported AS a mismatch, not rounded): mutation 1's actual failing set is a
  SUPERSET of the corrected two -- test_per_model_meter_parses_percent_reset_and_strips_whitespace also
  fails, because parse_reset is called with SEVEN_DAY_MAX_AHEAD_S again at usage.py:83 for the per_model
  dict. R4's correction held on its other half: test_parse_reset_bound_is_per_call_not_global correctly
  did NOT fail. Benign broadening; the constraint is pinned by three tests, not two.
Task 9 FINDING 2 -- THE IMPORTANT ONE, and it is the THIRD measured instance of the parent's named defect
  class, found independently by a Sonnet implementer that was only warned the possibility existed:
  THE BRIEF'S OWN NAMED TEST FOR MUTATION 2 DOES NOT PIN THE GUARD IT IS CREDITED WITH.
  `test_a_window_rollover_contributes_nothing` stays GREEN under the mutation, because its fixture goes
  90% -> 2% -- a NEGATIVE delta that the separate `if delta < 0: return state` guard catches
  independently, regardless of the resets_at check. The actual pin is
  `test_a_rollover_with_a_positive_delta_still_contributes_nothing` (10% -> 14%, positive delta,
  rollover), added during Task 5, whose own docstring says exactly this: the case "must not slip past it
  just because the negative-delta guard alone would have let it through."
  The CONSTRAINT is fine -- it is pinned, by the correctly-designed test. What is wrong is the PLAN'S
  DOCUMENTATION of which test does the pinning. This is direct corroboration of the parent's
  final-review deliverable (iii) and evidence that the audit will find more.
Task 9 FINDING 3 (self-caught, and it is the exact trap that cost this branch a false CAUGHT on Task 7):
  mutation 4 took TWO attempts. The first synthetic `except HerderError` arm echoed and returned
  UNCONDITIONALLY, producing 7 failures of which 2 were collateral behaviour changes unrelated to
  ordering. Redone with a bare `except HerderError as exc: raise`, which adds no behaviour of its own and
  isolates the pure ordering effect: exactly the 5 predicted tests, and the two "expected green" tests
  stayed green. The implementer reported the first attempt in full rather than quietly discarding it.
Task 9: additional mutation B (per-show RateLimited/HerderError ordering, a genuine swap of two
  PRE-EXISTING arms, anchored on full arm bodies so the 4-space/8-space substring collision could not
  fire) reddens 16 of 58 tests in test_pace_loop.py -- the most heavily pinned constraint found on the
  pass -- while test_pacing_disabled_records_the_limit_as_a_show_failure correctly stayed green.
Ruling R26 (Task 9, mine): Task 9 gets ONE Opus verification reviewer (aa0579ad) rather than the usual
  separate spec + quality pair. Task 9 produced NO DIFF, so there is no code to critique; spec compliance
  for a no-diff task reduces to "did the mutations run as specified and are the reported results honest",
  which is the SAME evidence a quality review would need. Two agents would read the same report and
  re-run the same six mutations. Review is NOT skipped -- the reviewer independently re-derives every
  expected red set before reading the report's claims, and is told a mutation table is exactly the
  artifact that was fabricated earlier on this branch. It is additionally asked to adjudicate the three
  named claims, above all FINDING 2. Cost if wrong: one reviewer's worth of independent judgement on a
  task with no code changes, on a branch that still faces two independent whole-branch reviewers.
LEDGER CORRECTION (issued by the parent, correcting MY count in the Task 9 FINDING 2 entry above):
  mutation 2's finding is NOT instance three. It is INSTANCE ONE, INDEPENDENTLY RE-DERIVED. The Task 5
  boundary already reported exactly this -- "the brief's rollover fixture uses 90->2, a negative delta
  the negative-guard already catches" -- and the parent has confirmed the fixture on disk at
  test_pacing_state.py:30-35: `ps.observe(_r(90), _r(2, OTHER_RESET), seeded)`.
  Read the earlier entry with this correction applied. The measured instance count of the defect class
  stands at THREE, not four. Inflating it would make the defect look more widespread than measured, and
  this ledger is the durable record.
  IT IS KEPT ANYWAY, and the parent judges the re-derivation worth more than a fourth instance would
  have been: two agents, different methods, different tasks, NO SHARED CONTEXT. The T5 implementer found
  it by running the brief's tests ALONE against mutants; a Sonnet implementer on Task 9 found it by
  flipping the brief's own named mutation and noticing the named test stayed green. Independent
  confirmation by a different route is what turns a plausible finding into a settled one.
PROCESS RESULT WORTH KEEPING: mutation 4's first attempt is the same trap that cost Task 7 a false
  CAUGHT last night -- and it was self-caught this time BY A CHEAPER MODEL, because the method was
  written into the dispatch prompt. The transferable claim is that the pre-named-expected-red-set rule
  is a prompt-level control, not a capability-level one.
Task 9: verification reviewer Opus (aa0579ad) -> MUTATION-REPORT VERDICT: **VERIFIED**. SPEC-COMPLIANCE:
  **PASS**. It re-ran all six mutations independently on its own git-archive snapshot with its own
  expected red sets written BEFORE reading the report's claims, and EVERY numeric claim and every named
  test in $D/t9/report.md reproduced exactly. No fabricated result, no rounded-to-CAUGHT mutant, no
  unreproducible claim. It ran every mutation against the WHOLE SUITE, which the implementer had not.
  Harness proven both ways; snapshot shadowing proven by planted sentinels citing the SNAPSHOT path; and
  it checked the venv's .pth mechanism (plain path-append, not a MetaPathFinder) rather than assuming
  PYTHONPATH would shadow. Final control after all seven mutations reverted: 1859 passed, snapshot
  git status empty. Worktree read-only throughout.
Task 9 (A) ADJUDICATED — HOLDS, with a correction that sharpens it: the third test IS independently
  sensitive (SEVEN_DAY_MAX_AHEAD_S has a SECOND call site at usage.py:83 inside the per_model
  comprehension, and that test's fixture carries a reset ~6.6 days out). But the failing set is NOT "a
  superset of the brief's named two" -- ONE OF THE BRIEF'S TWO NEVER FAILS. test_limits.py does not even
  import herder.usage, so test_parse_reset_bound_is_per_call_not_global is STRUCTURALLY INCAPABLE of
  seeing the mutation. The real finding is a DEFECT IN THE BRIEF: its Step 1 names a test that cannot
  fail under the mutation it prescribes, and omits two that do.
Task 9 (B) ADJUDICATED — HOLDS, FIRST-CLASS FINDING, confirmed twice (by the mutation run and by calling
  observe() directly with both fixtures under the mutation). The guard is pinned by EXACTLY ONE test and
  it is not the one the brief credits. Does NOT pin it: test_a_window_rollover_contributes_nothing
  (pacing_state.py test lines 30-35, delta -88, falls through to the separate `if delta < 0` at
  pacing_state.py:57), test_a_negative_delta_contributes_nothing, and
  test_a_failed_reading_at_either_end_contributes_nothing. DOES pin it:
  test_a_rollover_with_a_positive_delta_still_contributes_nothing (lines 50-55, delta +4). No other test
  in the file varies resets_at at all.
Task 9 (B) SUB-FINDING, new, the reviewer's own (minor, for triage): THE SOLE PIN IS THINNER THAN IT
  LOOKS. Under the mutation it yields PacingState(4.0, 4) against a seeded PacingState(4.0, 3) -- the
  per_show_delta field is NUMERICALLY IDENTICAL, because the fixture's delta (4.0) happens to equal the
  seeded estimate (4.0). The test fails ONLY on the `samples` field, via dataclass equality. Any refactor
  comparing out.per_show_delta instead of the whole state, or ceasing to increment samples on a fold,
  would SILENTLY UNPIN the guard. Choosing a fixture delta different from the seed (e.g. 10 -> 20) makes
  the pin robust.
Task 9 (C) ADJUDICATED — HOLDS IN FULL, both forms reproduced (Form B swallowing: 7 failed; Form A bare
  raise: 5 failed). The two extras are proven to be BODY effects rather than ordering effects by direct
  evidence, not inference: both fail with `DID NOT RAISE`, and the decisive one raises a PLAIN HerderError
  and never a RateLimited, so arm order cannot affect it at all -- under Form A, with identical ordering,
  it passes. NOTE FOR THE RECORD: Form B is CLOSER TO THE BRIEF'S LITERAL INSTRUCTION ("catching and
  reporting as a stage failure"), so THE BRIEF AS WRITTEN PRESCRIBES THE TRAP; departing from it was the
  right call.
Task 9: the reviewer ran a SEVENTH mutation of its own on the record-placement ordering at cli.py:505-509
  (whose comment claims to be load-bearing) -- hoisting the pacing_state.record block above the
  `if limited: ... break` -- and it IS pinned: 1 failed, exactly test_a_rate_limited_show_is_not_a_boundary.
  So its "additional A was near-token" note is about mutation SELECTION, not a hole in the branch.
Ruling R27 (Task 9, mine): the verification review's two Importants are PARKED WITH RULINGS, not entered
  into a fix round. I-1 (the report contains no raw tool output anywhere -- every result is prose, so the
  artifact is not self-verifying) and I-2 (no mutation was run against the full suite, which under-reports
  mutation 6's radius as 16 when it is 18: test_sessions.py's two phase-1 pause tests also break).
  NEITHER IS A CODE OR TEST DEFECT -- both are findings about the REPORT's evidentiary form, and the
  reviewer states plainly that everything reproduced and there is no correctness consequence. The
  verification reviewer independently reproduced every mutation on its own snapshot with its own
  pre-written expectations and full-suite scope, which SUPERSEDES the missing raw output rather than
  merely substituting for it; re-running the implementer to paste terminal output it already produced
  would add ceremony and no information. I-2's one substantive consequence is a NUMBER, now measured and
  corrected here: mutation 6's true blast radius is 18, not 16. I-2's general risk (a narrow run missing
  the only test that would have caught a mutation, which reads as a survivor when it is not) is real and
  goes to the final review as a method note; the reviewer confirmed the full-suite set equals the in-file
  set for mutations 1, 3, 4A, 4B and 5, so only 6 was affected.
  Cost if wrong: the Task 9 report stays a prose artifact, and anyone re-auditing must rely on the
  VERIFIER's reproduction rather than the implementer's -- which is the stronger of the two anyway.
MY OWN ERROR, self-reported: the Task 9 report attributes its no-commit contingency to "the brief's own
  final contingency". That sentence is NOT in $D/briefs/task-9-brief.md -- it is MY dispatch prompt's
  wording, which the implementer quoted and misattributed. The brief's Step 6 in fact carries an
  UNCONDITIONAL `git add -A && git commit` block with no stated contingency. Not fabrication by the
  implementer; a citation error originating in my dispatch.
Task 9: minor (deferred): the Task 9 report's Concern #4 provenance claim ("mostly from Tasks 5-8's own
  mutation sweeps") is unevidenced.
Task 9: minor (deferred): additional mutation A (FIVE_HOUR_MAX_AHEAD_S) is a NEAR-TOKEN extension -- the
  catching test's own docstring names that exact mutation, so the outcome was knowable by reading.
  Additional B is a real extension.
Task 9: minor (deferred): PLAN/BRIEF DOC CORRECTIONS, three in Task 9's text alone -- Step 1 names a
  structurally-incapable test and omits two real ones; Step 2 names a test that does not pin the guard;
  Step 4's wording prescribes the swallowing arm that produced the false 7.
Task 9: COMPLETE (no commits, tree unchanged at 3693e45, review VERIFIED + spec PASS, 2 parked under R27).
FINAL REVIEW dispatched (both Opus, in parallel, independent of each other's verdicts; neither is given
  this ledger). Whole-branch package: review-ac7c428..3693e45.diff, 32 commits, 513786 bytes -- both told
  it will TRUNCATE a single Read and to chunk it.
  final-spec (acb870b2): whole-branch spec compliance + deliverable (ii) the exhaustive commit-message
    numeric sweep + deliverable on documentation accuracy (the unprefixed G2 sentence in spec and plan,
    the "three meters" claim against two rendered, Task 9's brief being wrong in three places, and
    whether T6's spliced `### Known gap` heading was ever fixed). Told to prove its sweep method can
    return a failure by running it against ea14004, whose claim is known wrong -- a sweep that finds only
    the two already-known failures has probably not looked hard enough.
  final-quality (a86c718c): deliverable (iii) THE BRIEF-PINNED-TEST AUDIT as the priority, with all three
    measured instances quoted as the reason it exists and the explicit instruction that this runs in the
    OPPOSITE DIRECTION from every sweep so far -- start from the test's own claim, not from the source,
    which is why the three instances were invisible to sweeps that started from the code. Full
    enumeration required, including the tests that pass the audit; a partial list is not the deliverable.
    Plus deliverable (i) the triage of all 61 deferred minors, each with fix-before-merge-or-leave and a
    NAMED reason ("a count is not a triage"), plus a general quality pass with the three unswept leads the
    Task 9 verifier named (_meter_applies's backend gate, the two config ceilings, and the
    `ran and reading_before is not None` condition).
  Both carry: full-suite mutation scope (I-2's lesson), pre-named expected red sets, prove-both-outcomes,
  prove-the-mutation-applied, and verify-every-line-citation.
Ruling R28 (ISSUED BY THE PARENT, on Task 9's finding (B) sub-finding): FIX THE FIXTURE IN THE FINAL
  REVIEW'S FIX WAVE, do not merely note it. The parent checked the arithmetic and judges it worse than
  "thin" -- "it is the exact class we have been chasing all night, one refactor away from being live."
  Mechanism, quoted: "test_a_rollover_with_a_positive_delta_still_contributes_nothing seeds
  PacingState(4.0, 3) and observes 10 -> 14. That delta is 4.0, and the EWMA of 4.0 against a seeded 4.0
  is 4.0 -- so under the mutation the result is PacingState(4.0, 4) and the test fails ONLY on the
  `samples` field. Anyone who later asserts on per_show_delta alone, or compares with a tolerance,
  silently unpins the resets_at guard entirely, and nothing goes red to say so."
  THE FIX, prescribed exactly: change the observed delta so it differs from the seed. 10 -> 20 gives an
  EWMA of 6.4 against a seeded 4.0, so the assertion fails on BOTH fields and the pin survives any
  reasonable refactor of the comparison. KEEP THE TEST'S NAME AND COMMENT -- they are accurate; only the
  data was chosen badly, "and it was chosen badly by me." The fix wave must confirm the mutation
  (deleting `or b.resets_at != a.resets_at` at pacing_state.py:54) STILL REDDENS the test afterwards.
  The parent's framing: "This is deliverable (iii) doing its job before it has finished: the test's CLAIM
  was true, its DATA did not support the claim, and no source-first sweep would ever have found it."
  Cost if wrong: one fixture constant changes and the test still passes; the downside is bounded to a
  test-data edit on a test whose name and intent are unchanged.
CARRY INTO THE FINAL REPORT, not merely the ledger (parent's instruction), item 1: the Task 9 verifier's
  sentence on (C), VERBATIM -- "Form B is closer to the brief's literal wording ('catching and reporting
  as a stage failure') -- the brief prescribes the trap; departing from it was correct." The parent's
  reason: "Across this run my briefs have prescribed a trap at least FOUR times: the five-hour-only
  forecast, the `_pace` exception rewrite, the substring anchor, and now mutation 4's form. An
  implementer departing from a brief and being right is the outcome the two-reviewer structure exists to
  produce, and the record should say so plainly rather than reading as though the plan was followed."
CARRY INTO THE FINAL REPORT, item 2: my own citation error (attributing my dispatch wording to the
  brief), self-reported and correctly attributed. It changed nothing.
TRIAGE DISCIPLINE (parent's instruction, given the count came out at 61 not 46): do NOT let the count
  push toward batch-waiving. Every parked minor still needs its OWN named reason, and "low value" is not
  a reason. If the triage runs long, report at the halfway point rather than going quiet.
FINAL REVIEW RESULTS.
final-spec Opus (acb870b2) -> **Spec PASS (qualified)**. Architecture, Policy, all four Integration touch
  points and CLI/config delivered; all six global constraints hold (openrouter.py diffstat EMPTY, no
  --batch/--force/trust_age, herder imports nothing from llama); T6b and T7b properly filed as UNBUILT
  with nothing half-implemented. IT RE-RAN ALL FOUR SPEC-MANDATED MUTATIONS ITSELF; every one goes red.
final-spec CRITICAL: `CLAUDE.md:275-290` STILL SAYS THE FEATURE DOES NOT EXIST -- "not caught anywhere",
  "no such gate", "fails the run outright". False as of this branch. The branch DID edit CLAUDE.md (it
  added the `llama pacing` clause) and left that paragraph standing. "It's the first thing every future
  session reads; it's the one thing I'd block merge on."
final-spec IMPORTANT: the weekly reset bound's REJECT direction is unpinned -- widening
  SEVEN_DAY_MAX_AHEAD_S 7.5d -> 30d leaves all 1859 green. That is the direction that MANUFACTURES A LONG
  SLEEP from a bogus reset, and the session bound's equivalent IS pinned. Independently measured by the
  quality reviewer too (its triage entry #20: identities pinned, magnitudes not).
final-spec deliverable (ii), the commit sweep, ALL 32: method proved first by running the harness against
  ea14004 (known wrong) and by a planted EWMA_ALPHA sentinel. **29 of 32 reproduce exactly.** Three fail:
  cbaad44 (known), ea14004 (known, 13 not 16), and a NEW one -- **daa0c97 claims 1848 where the tree at
  that commit gives 1835**; it is code-only (+47/-8 in cli.py, no tests), its own body says "covering
  tests land in the next commit", and it quotes its SUCCESSOR's count. All private-copy mutation tallies
  were named as unverifiable rather than assumed.
final-spec deliverable (iii), docs: all four reported items confirmed. The `### Known gap` heading splice
  was real (introduced a3d8cdc) AND IS FIXED. Task 9's brief is wrong in exactly the three places
  described -- and Step 4 is wrong twice over: under the MINIMAL mutation its named test stays green, and
  the ordering is actually pinned by test_an_ordinary_stage_failure_is_not_turned_into_a_pause. PLAN
  RULING R4, WRITTEN TO FIX STEP 1, HAS ITSELF GONE STALE BY ONE TEST.
final-spec, unasked-for and correct: the `### Known gap` citations were exact at a3d8cdc and are ALL
  WRONG at HEAD, because 0ca7e1a inserted ~167 lines above them. cli.py:440->607, :2556->2760,
  :708-710->875-877, :1186->1353; T7b's cli.py:422 was NEVER right. The ledger offers a THIRD number
  (1177) for the symbol now at 1353. Recommends symbol names over line numbers.
final-quality Opus (a86c718c) -> **APPROVED**, no Critical, 3 Important, none blocking.
final-quality deliverable (iii) THE BRIEF-PINNED-TEST AUDIT: **38 of 39 PASS.** All 39 brief-supplied
  tests enumerated (T1:5 T2:6 T3:3 T4:7 T5:7 T6:2 T7:4 T8:5), all present under their brief names, all
  verbatim except shows_that_fit's three (whose args changed with the Task 8 fix). Each broken at exactly
  the thing its name claims, each run against the FULL suite, predictions written before each batch.
  **NO NEW INSTANCE of the class was found** across the other 38, plus four extra conjunct probes all
  CAUGHT. The single failure is D1-A -- an independent THIRD derivation of the known Task 5 defect.
final-quality D1-A, and it goes further than either earlier derivation: it predicted that relaxing the
  NEGATIVE guard would also redden test_a_window_rollover_contributes_nothing, exposing the
  overdetermination from the other side. **THE PREDICTION WAS REFUTED AND IS RECORDED AS SUCH** -- with
  the rollover guard still present the test short-circuits there. So that test is green under EITHER
  guard alone and pinned by NEITHER specifically. "That is precisely the pathology."
final-quality deliverable (i), ALL 61 TRIAGED: 4 FIX (all docs/comments), 53 LEAVE, 4 CLOSED as already
  fixed on-branch (#12, #41 -- including the "FLAG AT MERGE" spec splice, verified fixed -- #45, #50).
  Seven re-graded. Only #43 changed materially: it PROVED with two probes that BOTH halves of
  `if ran and reading_before is not None:` are pinned, contrary to this ledger's "unpinned" note.
  #47 (the ungated deferred second pass) re-graded Important-adjacent but LEAVE, named the strongest
  phase-3 candidate.
final-quality D3-A (Important): the Tasks 8-9 verdicts and this ledger's second half ARE NOT COMMITTED,
  and .gitignore:6 ignores .superpowers/ -- the in-repo copy literally still says "Tasks 8 and 9 NOT
  started". Must be committed before the worktree is removed. Same hazard 6f7c126 was created to close.
final-quality D3-B (Important): five cli.py:NNN citations, ONE IN SHIPPED SOURCE (pacing_state.py:4 says
  389/426; actual 486/523) and four in the spec. Traced, not assumed.
final-quality minors: `raising=False` on the offline-meter guard can silently lapse; _meter_applies keys
  only on llm_for("default"); the two new ceilings have no range validation.
final-quality HARNESS SELF-REPORT, worth keeping: **its v1 harness scored a CRASHING control as
  SURVIVED** -- no summary line, no failing names, "found nothing" indistinguishable from "never looked".
  Caught by its own controls before a single real result was recorded. Fixed by requiring, for a SURVIVED
  verdict, exit 0 AND a summary line reading exactly `1859 passed`; anything else is HARNESS-ERROR. It
  also found `-rf -rE` silently override each other (fixed to `-rfE`). This is the fifth instance on this
  branch of the empty-result failure mode, and the first caught by a control designed for it.
Ruling R29 (mine): three spec-promised items are PARKED, not built in the fix wave -- rendering the
  per_model meter in `llama pacing`, the two counters the spec names on `Progress`, and the spec's
  "resume costs nothing" test with a call-counting provider. Each ADDS NEW SURFACE rather than correcting
  something wrong, and adding features during a final fix wave is how a review-clean branch acquires
  unreviewed code. The spec reviewer graded none of them blocking and still returned PASS. They go to the
  parent as named follow-ups. Cost if wrong: three spec-promised niceties land in a later phase; none
  affects the correctness of what shipped. The spec text is corrected to say TWO meters rather than
  three, so spec and code agree.
FINAL FIX WAVE dispatched (acf7392c, Opus) -- ONE wave, all findings together: F1 the CRITICAL CLAUDE.md
  paragraph; F2 the weekly bound's reject direction; F3a AND F3b both rollover fixtures (R28's 10->20 and
  D1-A's 90->92, two different tests with two different defects, both prescribed, neither test deleted);
  F4 the stale citations including the one in shipped source, with symbol names preferred over line
  numbers; F5 the four FIX minors plus R4's own staleness plus the "three meters" spec claim.
  Commit messages are REPORT-ONLY, no amend. R29's three items named as out of scope.
Ruling R30 (ISSUED BY THE PARENT, refining F1 mid-flight; sent to the running fix wave acf7392c):
  the CLAUDE.md paragraph carries THREE claims with THREE different truth values, and a careless
  correction destroys real information.
  (1) BOUNDARY (a), openrouter -- STILL TRUE, KEEP VERBATIM. openrouter.py:37 still raises a plain
      HerderError, a 429 is still retried three times and still fails the show. Phase 2 deliberately did
      not touch it (explicit non-goal). Deleting (a) as collateral of "phase 2 built this now" is wrong.
  (2) BOUNDARY (b)'s CORE CLAIM -- NOW FALSE, REWRITE. "not caught anywhere", "exit 1, no checkpoint,
      no paused state, no resume_after" are all false for run_discover/run_search/run_winnow since T6;
      "phase 1 has no such gate, so a limit hit during those stages fails the run outright" is false
      since T7.
  (3) THE REMAINING GAP MUST SURVIVE THE REWRITE. run_interpret is still uncovered -- that is T6b.
      Parent's warning verbatim: "If the fix wave rewrites (b) into 'phase 2 covers the run-level stages'
      and stops there, we lose the one part of the old paragraph that is still accurate, in the file
      every future session reads first."
  (4) FIX THE CONFLATION: the old text writes "`interpret` (`run_discover`)" as though they were one
      stage. THAT PARENTHETICAL IS THE ORIGIN OF THE ENTIRE T6b CONFUSION -- it is what made the spec's
      Problem section name `interpret` when its Integration section only ever covered `discover`. Must
      not be carried forward.
  Cost if wrong: the file every future session reads first either keeps a false claim or loses a true
  one; both are the defect this finding is about.
Ruling R31 (PARENT'S CONDITION ON MY R29): parking the three unbuilt items stands, but EVERY SPEC
  SENTENCE THAT PROMISES SOMETHING UNBUILT MUST BE CORRECTED OR EXPLICITLY MARKED AS FILED. I had done
  this for per_model (three meters -> two); the same is now required for Progress's two counters and the
  "resume costs nothing" test, in the style the spec already uses for T6b and T7b. Parent's reason:
  "A spec that ships promising what the code does not do is the same defect as the CLAUDE.md paragraph,
  one document over." Sent to the fix wave as an addition to F5.
  Cost if wrong: the spec ships describing capability the code does not have.
RECORD, per the parent: daa0c97's 1848-vs-1835 is a FORWARD REFERENCE, not a fabrication -- its body
  says the covering tests land in the next commit. And three non-reproducing messages out of thirty-two
  is now a MEASURED RATE rather than an anecdote.
CARRY INTO THE FINAL REPORT, item 3 (parent): deliverable (iii)'s one failure is BETTER than a new
  instance would have been. "A prediction that survives is weak evidence; a prediction that fails and
  gets written down is how you learn the test is pinned by neither guard specifically."
FINAL FIX WAVE (acf7392c, Opus) -> COMPLETE. All of F1-F5 fixed, 5 commits 39700a4..b628cb2, nothing
  merged/pushed/amended. Orchestrator suite run at b628cb2: 1860 passed, 7 deselected (1859 + 1 = F2's
  new test, no tests lost); interpreter re-verified inside the worktree.
  Commits: 39700a4 tests | d883885 source docstrings | 9818508 CLAUDE.md | 3024bae spec+plan citations
  and Task 9 | b628cb2 F1 refinement + the spec's unbuilt promises.
F1: CLAUDE.md rewritten in two parts -- a lead paragraph describing what SHIPS (both halves, the
  zero-token meter via herder.usage, the EWMA in pacing-state.json, decide()'s Proceed/PauseUntil, both
  gate sites, `llama pacing`, --no-pacing opting out of both) and then THREE boundaries that remain, not
  two: (a) claude_cli-specific, substance KEPT and re-verified by reading openrouter.py AND by confirming
  `git log origin/main..HEAD -- openrouter.py` is EMPTY, so "deliberately untouched" is true of the
  branch and not merely of intent; (b) three stages not four, with T6b's surviving gap and WHY covering
  it is a resumability design rather than a catch, bounded by the note that --profile never calls
  run_interpret; (c) the run-level sites checkpoint but never sleep, T7b, with the operator consequence
  stated. Per R30 it also names the `interpret (run_discover)` conflation EXPLICITLY as the inherited
  phrasing that caused the muddle, and notes _PIPELINE_RUN_STAGES is a THIRD triple excluding discover.
  Every claim re-read against source first, with the regions cited.
F2/F3 MUTATION EVIDENCE, expected set named before each run, FULL suite, harness proven both ways
  (control: exit 0 AND the summary line `1860 passed`):
  - widen SEVEN_DAY_MAX_AHEAD_S -> 30d: expected exactly the new reject-direction test; actual exactly
    that one (1 failed, 1859 passed). CAUGHT.
  - delete the rollover clause: expected BOTH rollover tests; actual exactly those two (2 failed, 1858
    passed). CAUGHT. Neither test deleted. Both fixtures now diverge on BOTH fields under the mutant
    (3.2 and 6.4 against a seeded 4.0), which is the property R28 and D1-A were each asking for.
F4: 8 citations re-derived, most REPLACED BY SYMBOLS rather than renumbered (cli._get_query,
  cli.profile_add, the ws.criteria.exists() guard in cli.run_resume, module-level _PIPELINE_RUN_STAGES,
  _execute's isinstance(verdict, PauseUntil) branch, _execute's except RateLimited arm). T7b's cli.py:422
  -- never correct -- re-derived as the deferred second pass's blocking file_lock, IDENTIFIED BY THE
  ABSENT `blocking=False` that distinguishes it from the first pass.
F5: all four FIX minors plus the two added mid-wave by R31 (the spec's Progress counters and the
  "resume costs nothing" test, now MARKED filed-and-unbuilt, not built).
FIX WAVE METHOD FINDING, self-reported and worth keeping: ITS OWN predicted red set for the plan's Step-4
  mutant was wrong -- it named 4 and measured 7, and the three extras were exactly the "failures
  unrelated to ordering" the finding warns about. That drove the corrected prescription (a bare `raise`
  above the arm -> exactly 5 red, ordering-isolated). A "non-zero failures" check would have scored the
  bad mutant CAUGHT. Third agent on this branch to make and report this class of prediction error.
FINAL SCOPED RE-REVIEW dispatched (a68296f5, Opus) over 3693e45..b628cb2. Told F1 needs the most care
  because three of its four parts are about NOT DESTROYING information, and that a newly written wrong
  claim in CLAUDE.md is WORSE than the stale one it replaced -- grade it against source, not on tone.
  Also: verify every replacement citation RESOLVES (a re-cited-but-still-wrong reference is the same
  defect), confirm the marked-not-built items were not built, and spot-check the fix wave's self-reported
  prediction error. NO SECOND FIX WAVE -- anything left open I adjudicate.
FINAL SCOPED RE-REVIEW (a68296f5, Opus) over 3693e45..b628cb2 -> **ALL FIVE ADDRESSED, NO NEW
  CRITICAL/IMPORTANT BREAKAGE.** It checked ~20 individual claims in the new CLAUDE.md text against
  source rather than grading the rewrite on tone, and confirmed all four required parts of R30 present:
  (i) the openrouter boundary kept and still true (openrouter.py:37 verbatim bare HerderError);
  (ii) boundary (b) rewritten as false-since-T6/T7, matching cli.py:381-397; (iii) the run_interpret gap
  SURVIVING loudly as T6b-UNBUILT with its unresumability reason; (iv) the `interpret (run_discover)`
  conflation called out explicitly by name. NO NEWLY-WRITTEN CLAIM IS FALSE.
  F2: MUT-A full suite, 1 failed / 1859 passed, exactly the predicted test.
  F3: MUT-B full suite, 2 failed / 1858 passed, failing set EXACTLY those two -- and it verified BOTH
  required properties independently: both new deltas are POSITIVE (so the negative-delta guard cannot
  cover for the deleted clause) and both DIFFER from the seeded 4.0 (so per_show_delta moves, not only
  samples). That is F3a's condition and F3b's condition, each checked.
  F4: 15 changed citations plus 5 deliberately-kept ones, all verified to RESOLVE at b628cb2.
  NO LINE-NUMBER CITATION INTO cli.py REMAINS. T7b's never-correct cli.py:422 was genuinely re-derived,
  not shifted.
  F5: all six done and NOTHING BUILT -- Progress still carries only per_show_delta (pacing.py:178-183),
  no call-counting test exists anywhere in packages/llama/tests/, per_model appears in packages/llama/
  only as a test constructor kwarg and is never rendered.
  NO BREAKAGE: the only shipped-source file the diff touches is pacing_state.py, and an AST comparison
  WITH DOCSTRINGS STRIPPED between 3693e45 and b628cb2 returns IDENTICAL -- a stronger check than reading
  the diff. Everything else is docs, two test fixtures and one new test.
FINAL RE-REVIEW CORRECTION to the fix wave's self-report, and it CUTS AGAINST the fix wave's own
  confession rather than for it: of the three tests beyond its 4-test prediction, only TWO are
  body-related -- the third was an UNPREDICTED ORDERING FAILURE. The wave's numbered list says "2 of them
  unrelated to ordering" correctly; only its looser prose method note says "three extras". Substance
  stands; the prose overstated its own error.
Ruling R32 (mine, adjudicating the final re-review's six residual minors; there is no second fix wave, so
  these are parked with reasons rather than fixed):
  (1) CLAUDE.md's "written nothing" during interpret is imprecise -- claim_run_dir (cli.py:600,
      workspace.py:129-138) has already mkdir'd the run directory, so an empty run dir IS left behind;
      "written no artifacts" would be exact. PARK. It is a two-word correction in the very file the
      Critical was about, so I am flagging it upward explicitly rather than burying it -- but reopening a
      closed review loop for a two-word docs edit would put unreviewed text into that file, which is the
      failure mode the loop exists to prevent. Cheapest of the six to take in a later pass.
  (2) CLAUDE.md's one-clause T6b sentence omits run_interpret's SECOND call site, profile_add
      (cli.py:2760). PARK, same reasoning; the spec and plan both name it, so the complete record exists
      and only CLAUDE.md's condensed version is partial. Flagged upward with (1) as a pair.
  (3) Plan Step 3 still prescribes a file-scoped pytest run, contradicting the full-suite instruction the
      fix wave added at Steps 1, 2 and 4. PARK: an internal inconsistency in a plan whose execution is
      finished, affecting nobody who is not re-running Task 9 from scratch.
  (4) Plan Step 6 still cites the 1742 phase-1 baseline where the branch is at 1860. PARK: same class,
      and the STATUS block at the top of this ledger now carries the correct number where a reader will
      actually look.
  (5) Step 1b's measurement lacks the date stamp Step 2 and R4 carry. PARK: cosmetic consistency only,
      and the reviewer confirmed both numbers reproduce.
  (6) test_a_window_rollover_contributes_nothing's comment was written for the old negative fixture. The
      reviewer verified it REMAINS TRUE of the new 90 -> 92 fixture (delta 2.0 < seed 4.0 still drags the
      estimate downward), so it is a note rather than a defect. PARK.
  Cost if wrong: two small inaccuracies persist in CLAUDE.md ((1) and (2)) and four in a finished plan
  file. None affects code, tests or behaviour; all six are one-line edits available at any time.
THE MOST TRANSFERABLE RESULT OF THIS RUN, stated as a measured rate rather than an anecdote (the parent
  asked that this be recorded prominently): FOUR independent agents on this branch -- a Task 7
  implementer, a Task 9 implementer, the final fix wave, and by its own account one reviewer's first
  harness -- each made a mutation-scoring error that "any failure = caught" would have scored as a clean
  CAUGHT, and each caught it only because the dispatch prompt required naming the expected red test
  BEFORE running. Three of the four self-reported the error rather than rounding it away. The control is
  PROMPT-LEVEL, not capability-level: a Sonnet implementer caught the exact trap that had cost an Opus
  implementer a false CAUGHT the night before, because the method was written into its instructions.
  Companion rate: 3 of 32 commit messages carry numeric claims that do not reproduce.
