# Task 7 — SCOPED RE-REVIEW of fix round 1

**Verdict: all three Importants ADDRESSED. No new Critical or Important
breakage from the fix diff. Approve.**

## Harness

Private copy `$D/work/t7-rereview/copy`, `PYTHONPATH`-shadowed onto the
worktree's venv interpreter (`.venv/bin/python -m pytest`, never the console
script). Shadowing proved by planting `_T7RR_SENTINEL` in the copy's `cli.py`
and reading it back through `llama.cli` (`SENTINEL: planted`), then restoring.
Green baseline asserted **1828 passed, 7 deselected**; every run's summary line
required to match `passed|failed|error`. `python -B -p no:cacheprovider`,
`PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared per run, `stdin=/dev/null`.
Every anchor asserted `count == 1` before applying; the N3 swap additionally
asserted `len(out) == len(src)` so nothing could be removed by accident.
Re-sync + `diff -r` byte-identity before and after every mutation — the copy is
byte-identical to the worktree now, the worktree is untouched (`git status`
empty, HEAD `61a314e`), and I made no commits. `$D/TAKEN_OVER` and
`$D/taken-over/t7-rereview` checked before each write batch; neither exists.
Log: `$D/t7-rereview/t7-rereview.log`.

## The three findings

- **I1 — ADDRESSED.** `test_a_previous_runs_estimate_reaches_the_preflight_gate`
  kills both survivors, each alone.
  N1 `Progress(state.per_show_delta)` → `Progress(None)`: **1 failed, 1827
  passed**, the one failure being that test.
  N2 `state = pacing_state.read_state(config.root)` → `PacingState()`:
  **1 failed, 1827 passed**, same single test. A previous run's
  `pacing-state.json` is now pinned as reaching the pre-flight gate.
- **I2 — ADDRESSED.** N3 as a **true reordering** (see below): **1 failed, 1827
  passed**, the one failure `test_a_rate_limited_show_is_not_a_boundary`.
- **I3 — ADDRESSED.** Guard is `if ran and reading_before is not None:`.
  N12 (drop the `reading_before is not None` arm): **2 failed, 1826 passed** —
  `test_gate_is_skipped_entirely_on_a_non_claude_cli_backend` and
  `test_no_pacing_never_reads_the_meter`, exactly the two extended assertions.

## The N3 wrong-reason episode — verified, and the implementer is right

I reproduced both mutants on the same copy, same harness.

- **True reorder** (`LIMITED + RECORD` → `RECORD + LIMITED`, a pure text swap;
  ordered pair asserted unique, byte length asserted unchanged so neither half
  could be dropped): **1 failed, 1827 passed**, and the single failure is
  `test_pace_loop.py::test_a_rate_limited_show_is_not_a_boundary`.
- **The first attempt** (delete the `if limited:` block outright): **12 failed,
  1816 passed** — `test_the_show_that_hit_the_limit_is_retried_not_dropped`,
  three checkpoint tests, the no-progress-guard tests, the two
  progress-between-pauses tests, `test_a_limit_mid_pass_keeps_the_shows_another_run_had_locked`,
  `test_no_wait_checkpoints_even_inside_the_cap`,
  `test_sessions.py::test_a_usage_limit_within_max_wait_sleeps_and_then_finishes`
  — **and, among them, `test_a_rate_limited_show_is_not_a_boundary`.**

That last inclusion is the whole point: in a bulk sweep scored on "did any test
fail", the deletion mutant would have been recorded as N3 CAUGHT with the new
test in the failure list, while proving nothing about the *ordering*. It was
killed by the queue-arithmetic tests that already existed at `b67b2a1`. The
implementer's numbers are exact (12, then 1) and the correction was the right
one. This is the strongest methodological moment in the round and it survives
independent reproduction.

## Documentation checks

1. **Sleep-scope paragraph — CORRECT and accurate.** The spec now states the
   "sleep if it fits under `max_wait`" sentence "describes touch points 3 and 4
   only", names **both** run-level sites (pre-flight gate, and the reactive
   catch around the three run-level stages) as deliberately checkpointing
   without sleeping, and gives the mechanism. Verified against code, not taken
   on trust: `_checkpoint_pause` (`cli.py:176-201`) has no sleep branch and
   says so in its own docstring; both run-level sites call it (`cli.py:239`,
   `cli.py:300`); the only `sleep_until` is the show loop's
   (`cli.py:460-467`), gated on `pace.wait and wait_s <= pace.max_wait_s`.
   The `--wait` sentence is present and reads: `llama get --wait` started
   twenty minutes before a reset "now exits immediately having done nothing,
   and an unattended invocation needs a manual `llama run resume`." Accurate.
   One honest nuance, not a correction: the phase-1 comparison holds for the
   window states where the run-level stages would still have succeeded — with a
   fully exhausted window phase 1 would have exited 1 at search/winnow, not
   slept. The sentence is about the class the gate newly intercepts, which is
   the right class to describe.
2. **T7b filed UNBUILT and not built — CONFIRMED.** Plan line 1369, "Status:
   UNBUILT. Do not implement as part of phase 2." Scoped to **both** sites
   together with the stated reason (doing one replaces a symmetry with a worse
   asymmetry), notes it is not a flag lookup (re-decide after the nap, the
   no-progress guard, a new shared pause renderer), and folds in the ungated
   deferred pass **and** its blocking lock (`cli.py:429`) making the last gate
   reading stale by the whole wait. Code-side: the entire `cli.py` change in
   `b67b2a1..61a314e` is one condition and eight comment lines — no sleep
   behaviour changed anywhere, and `pacing.py`/`pacing_state.py` are untouched
   by this range.
3. **Task 6's structural regression — REPAIRED.** All three bullets of "Three
   things are left undone" now sit together, bullet 3 ("There is no way to plan
   a run against the window") reads under the list, and
   `### Known gap: run_interpret is not covered` follows the complete list. The
   section's prose is otherwise unchanged (the diff is a pure move).
4. **Deferred Minors NOT fixed opportunistically — CONFIRMED, all four.**
   `if ran and reading_before is not None:` carries no `failures`/`held` clause,
   so held and failed shows are still folded while `Locked` is excluded, and the
   comment was not extended to justify that asymmetry (Minor 1 stands).
   Two `_meter` calls per boundary remain (`cli.py:387` and `cli.py:424-425`),
   so the 2N+1 read count is unchanged. `pacing_state.py:3-5` still describes
   the before-N/before-N+1 protocol. `test_a_preflight_pause_exits_zero_like_every_other_pause`
   still asserts only `state == STATE_PAUSED` and checks no exit code. Nothing
   was smuggled in.

## Count sanity check

Independently reproduced rather than accepted: the tree at `b67b2a1`
(`git archive` into a second copy, same shadowing) runs **1826 passed, 7
deselected**; the tree at `61a314e` runs **1828 passed, 7 deselected**. The fix
diff adds exactly two `def test_` functions. 1826 → 1828 matches a 2-test
addition with no test lost or renamed. (Your own suite run is still the
authority; this is the sanity check you asked for.)

## New breakage from the fix diff

**None at Critical or Important.** The guard is behaviourally invisible except
on the paths it was written for: when `reading_before is None`, `record` would
have called `observe(None, after, state)`, which declines to fold on a failed
reading, so the only thing lost is the write, the `mkdir` and the lock — which
is the finding. Two observations, neither rising to Important:

- **Observation A (new, from the fix).** Skipping `record` also skips the
  `state = ...` reassignment, so on a no-reading run `state` stays as
  `read_state` left it at run start instead of being refreshed from disk each
  show. Harmless today: on a no-reading run `_meter` is `None`, so `decide`
  never consults `state.per_show_delta`. Worth a line in the comment only if
  someone later makes the gate consult state without a reading.
- **Observation B (pre-existing, unchanged by the fix).** The guard tests
  `reading_before` only. If the *before* read succeeds and the *after* read
  fails, `record` still writes and locks while folding nothing — the same cost
  the finding objects to, on a rarer path. The reviewer proposed exactly this
  one-line form and the implementer took it; tightening to
  `reading_before is not None and (after is not None)` would need the after
  reading hoisted out of the call, which is more churn than the case earns.

## Deferred minors (unchanged, listed for the ledger)

M1 held/failed folded while `Locked` is excluded, unpinned and unexplained in
the comment; M2 the 2N+1 meter reads; M3 `pacing_state.py`'s docstring; M4
`test_a_preflight_pause_exits_zero...` not earning its name; M5 the conftest
fixture stubbing the name rather than the transport. All were deferred
deliberately and none regressed.

## The unruled item — recommendation, not a fix

`pacing_state.py`'s module docstring (before-N minus before-N+1) versus its only
caller (before/after around one show). **It is a real defect worth a follow-up,
at Minor severity, doc-only.** Two reasons it is more than imprecision. First,
it does not merely differ from the caller — it *advocates* a protocol, and the
sentence "available for free because the meter read costs nothing" is the exact
false premise Minor 2 would rely on: each read is a `claude -p` subprocess, so
the before/before scheme's appeal is that it halves them, not that they are
free. Second, the before/before scheme cannot express, without extra
bookkeeping, the two exclusions this design now depends on and pins: a `Locked`
show and a `RateLimited` show must contribute **no** boundary, and under
before/before their zero silently lands inside the *next* show's delta — an
under-estimate, the direction both `cli.py` comments call walking into the wall.
So the docstring quietly points a future editor at a change that would undo
`test_a_deferred_show_is_not_a_boundary` and the new
`test_a_rate_limited_show_is_not_a_boundary`. Recommendation: file it as a
one-paragraph docstring correction against the Task 4/5 file, recording that
before/after is deliberate and why; do **not** let it ride as part of Minor 2's
read-halving, which needs its own argument about the excluded boundaries.
Correctly out of scope for this task, which was not asked to edit that file.

## Tool refusals

None. No tool refused me at any point in this round.
