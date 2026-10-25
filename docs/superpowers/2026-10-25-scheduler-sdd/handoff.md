# Scheduler SDD handoff (2026-10-25)

Start here in a fresh session. Everything below is committed on branch
`playout-scheduler`, worktree `/Users/shawn/projects/llama/.claude/worktrees/scheduler`.

- **Spec (approved 2026-10-25):** `docs/superpowers/specs/2026-10-25-scheduler-design.md`
  (review mode **Fable**; stakes paragraph confirmed; two spec review rounds).
- **Plan (approved 2026-10-25):** `docs/superpowers/plans/2026-10-25-scheduler.md`, 14 tasks
  (reviewed by Opus + Fable, 46 decisions applied).
- **Review record:** `docs/superpowers/2026-10-25-scheduler-spec-review/` (briefs, findings,
  decisions, including the operator rulings).

## How to run it

- Per `~/.claude/CLAUDE.md`: launch a **peer orchestrator on Opus** via the `sdd-delegation`
  skill (`parent.md`, `peer-brief.md`), in this worktree. Implementers on Sonnet unless the plan's
  task header says Opus (Tasks 8, 9, 11); spec-compliance and code-quality reviewers on Opus;
  final branch reviewer per review mode **Fable** (the spec's review mode overrides "never
  silently upgrade" for that review only).
- The worktree has **no `.venv` yet**: the first task creates one per the repo CLAUDE.md setup
  line and runs tests as `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`.
- Arm the 30-min keepalive in the parent session (peer-run parent rules).
- Usage: the 5x plan's 5 h window burned ~40 points on one Opus+Fable review pair on 2026-10-25;
  do the usage-pacing fit check before every fleet and have the peer report the meter at boundaries.

## Stops for the operator (the peer stops and reports)

1. **After Task 1:** the tolerant plan-row reader (+ timeline skip of non-show rows) is ready to
   deploy to hugo on its own, before the scheduler. Deployment is the operator's.
2. **After Task 3:** the operator runs `packages/transmitter/scripts/probe_estimates.py` on hugo
   (and `--time-one` on a long package). Escalate before Task 11 if median |error| > 15 s or
   max > 2 min. Tasks 4-9 may proceed meanwhile.
3. **After Task 10 (measurement):** if the scheduler's share of block starts outside the window
   exceeds the like-for-like naive baseline, stop and bring the numbers before Task 11.
4. Finish: merge/push/tag are the root's, after the operator's choice.

## Operator rulings recorded during design (binding)

- Announcements are a promise kept where possible, not a guarantee (broken = logged, not alerted).
- Announcements name their time zones; default Eastern and Pacific (`[announce] zones`).
- When every own-profile show is too long to land the next block on time, the block still plays
  its own profile and the next block starts late (a miss), rather than filling with other profiles.
- Partial sets, alternate DJ intros, concert-specific announcements and transmitter invoking
  `emcee say` are future work; the design must not make them harder.
