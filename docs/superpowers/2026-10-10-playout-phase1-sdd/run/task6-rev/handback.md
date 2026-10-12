### Spec Compliance

**Compliant. Nothing is missing, extra or misunderstood.**

- `planner.py` matches the brief's Step 3 listing exactly: `shuffle_rank`, `choose_next`, `extend`, `next_start`, `replan_from`, `cut_for_recovery`, `current_run_start`, `publish_next`, `read_plan` and `write_plan`. Every signature matches the brief's Interfaces list.
- `test_planner.py` is the brief's 13 tests with one change: the unused `from transmitter.layout import PlanRow` is gone, as the orchestrator ruled. Every import in `planner.py` is used.
- `plan.jsonl` is written only through `write_plan`. That function validates the rows and then calls `workspace.atomic_write_text` (unique temp file, fsync, rename). `test_plan_file_round_trip` checks that no temp file is left behind.
- Spec "Phase 1 ... trivial planner: eligible packages in a fixed shuffled order, back to back with the inter-show gap" (spec line 293):
  - The rank is `sha256("{seed}:{slug}")`. It does not depend on the run or on which shows are in the set, and Python hash randomisation does not touch it.
  - Rows are placed at `prev.end_frame + gap_frames`.
- Spec "Frozen means rendered" (spec lines 283-287): `replan_from` keeps `rows[:index]` and restarts at the skipped row's own `start_frame`. It also carries over that row's `run_start` flag, so a skipped first row of a run stays aligned.
- Spec "Recovery after an outage longer than the lead" (spec line 355): `cut_for_recovery` cuts the row that spans the first unpublished segment, at `(published_last + 1) * 441`, and drops every later row. The cut is segment-aligned, so the plan never extends past what was published. The cut stays inside the show: rows starting at or after the boundary `break` first, so `start < cut <= start + frames` holds.
- Task 4 follow-ups (783a934). All four items are present:
  1. **Positive `validate_rows` tests.** Abutting rows are accepted, and so is a cut row followed by an aligned `run_start` row. Rejections are tested for `frames <= 0` and for both cut boundaries: `cut == start` and `cut == start + frames + 1`.
  2. **Pinned past-the-plan boundary.** `end_frame == 441` builds; `440` is refused with "past the end of the plan". The fake encode in that test is written with 440 frames, so the frame-count check cannot be what fires instead.
  3. **`FrameStore.__init__`** rejects a silent frame that is not exactly one ADTS frame (`layout.py:105-106`). Tested with two frames and with `b""`.
  4. **`_load`** maps any other `OSError` to `LayoutError`, with the path in the message (`layout.py:122-123`). Tested by putting a directory where the encode should be.

### Strengths

- The copy is faithful, and the cases the brief asked for are actually tested: the order is the seeded order, adding a package does not reshuffle the others, a newly eligible show airs exactly once and then falls in line, there is no back-to-back repeat unless only one show exists, `max_new` is honoured, skips go through `on_skip`, `PlanError` is raised only when planning is actually needed, and the recovery cut lands inside the spanning row.
- Failures cannot leave a partial plan. `extend` validates the whole plan before returning, and `write_plan` validates before its atomic write.
- `cut_for_recovery` and `replan_from` are pure functions over rows, which keeps the strict ordering and immutability decisions with the caller (Task 9's `plan_step`/`render_step`), where they belong.
- **Mutation check of the Task 4 follow-ups.** I ran four mutants in a scratch `git archive` copy, using `python -m pytest`, `PYTHONPATH` shadowing (confirmed with `transmitter.__file__`), `PYTHONDONTWRITEBYTECODE` and no cache provider. I wrote down the expected failing test before running each one.
  - m1, `validate_rows` overlap check `<` changed to `<=`: killed by `test_validate_rows_accepts_abutting_and_cut_then_aligned`, as predicted.
  - m2, `build_segment` past-the-plan check `>` changed to `>=`: killed by `test_build_segment_plan_end_boundary`, as predicted.
  - So the implementer's reasoning about which mutants these tests kill holds for both.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **Corrupt `plan.jsonl` raises raw `JSONDecodeError`/`TypeError`** (`planner.py`, `read_plan`; implementer concern 1).
   - **What I checked.** The plan's run loop does not catch only `TransmitterError`: `Runner._step` (plan lines ~6344-6357) catches `Exception`, logs it and alerts. So the service does not crash. `plan_step`, `render_step` and `publish_all` will each fail on every tick until an operator acts.
   - **Why this is not Important, unlike the earlier corrupt-cache defect.** That defect was Important because treating a corrupt cache as a miss was a safe automatic recovery, and the defect blocked it. Here no automatic recovery is safe. Treating a corrupt plan as empty would make `publish_next` return None and start a fresh run over segment keys that are already published and immutable. Failing loudly is the correct outcome.
   - **What is actually wrong is the message.** The alert reads "JSONDecodeError: Expecting value ..." with no file name, and `transmitter status`/`plan` would print a traceback rather than `error: ...`.
   - **Reachability is low.** The file is only ever written atomically with fsync.
   - **Fix.** Wrap the parse so that `ValueError`/`TypeError` become `PlanError(f"{path}: line {i}: {exc}")`.
2. **`cut_for_recovery`'s `start_frame >= boundary` branch is not pinned.**
   - **Evidence.** Mutant m3 (`>=` changed to `>`) survives all 28 layout and planner tests.
   - **Consequence if regressed.** A row starting exactly at the boundary would be kept with `cut_frame == start_frame`. `cut_for_recovery` does not validate its own output, so `write_plan` would then raise `LayoutError` on every recovery tick.
   - **The case is reachable.** Example: an earlier recovery's new run starts at segment S, the outage happens before any of S is published (`published_last == S-1`), and the boundary lands exactly on that `run_start` row. Mid-run rows also hit it about 1 time in 441.
   - **Fix.** Add one test row whose start equals the boundary.
   - Mutant m4 (`end_frame > boundary` changed to `>=`) also survives, but it is effectively equivalent: it gives `cut_frame == start + frames`, so `end_frame` is unchanged. Not worth pinning.
3. **A 0-frame row is not treated as a per-show skip** (`extend`; implementer concern 2).
   - **Behaviour.** `frames_of` returning 0 appends an invalid row, and the loop keeps going. A show of length 0 still advances `start` by `gap_frames`, so the loop ends when it reaches `until_frame`. Then the whole `extend` fails with `LayoutError`, instead of that one show being isolated.
   - **Not reachable in practice.** The plan's `planned_frames` returns `frames_for(padded_samples, extra)`, which is at least 1 for any show with audio, and negative counts cannot happen.
   - **Fix.** A `frames <= 0` check that raises `PlanError` inside the `try` would route it through `on_skip`.
4. **A persistently unmeasurable show is retried first on every `extend` call** (implementer concern 3).
   - **Why it is always first.** It is never planned, so its `last_seq` stays at -1, and least-recently-planned order puts it at the front every time.
   - **Cost.** Each call pays one failed `frames_of`. That is potentially a partial ffmpeg decode of a multi-hour show, unless analysis failures are cached. While the lead is filling, `plan_step` runs every tick with `max_new=1`, so this costs one wasted analysis and one log line per tick. Those log lines are not alerts.
   - **Impact.** This is CPU on hugo, not spend, and the skip itself works. Nothing wedges.
   - **Note for Task 9.** Consider a negative memo keyed on `show.key`. The plan's `render_step` already carries an `excluded` set for the replan path; `plan_step` has none.
5. **`PlanError("no eligible packages to plan")` is misleading when every eligible show was skipped as unmeasurable.** When the pool empties partway through, the rows already appended in that call are also discarded. Skipped shows are reported through `on_skip`, so the cause is visible. A different message for "all skipped" would help the operator.
6. **Missing test for skip-on-first-row.** Nothing asserts that `run_start` moves to the next row when the first chosen show is skipped. The code does it correctly: `mark` is only cleared after a row is appended.
7. **`FrameStore.__init__` raises `AdtsError` for non-ADTS bytes**, not `LayoutError`. Both are `TransmitterError` subclasses, so this is cosmetic.

### Assessment

**Task quality:** Approved

**Reasoning:** The planner is the brief's code verbatim. Its recovery-cut, re-plan and shuffle semantics match the spec, it only reaches `plan.jsonl` through validated atomic writes, and the Task 4 follow-ups do what was asked (two of them confirmed by mutation). None of the flagged concerns wedges the station where an automatic recovery would have been safe. The corrupt-plan case is a fail-loud situation that only needs a better error type and message, and the remaining items are coverage or defensive polish.
