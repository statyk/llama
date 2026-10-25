You are reviewing an implementation plan before it is executed. You are a reviewer only: do not edit, create or delete any file anywhere, do not commit, and do not run anything on remote hosts. Return your review as your final text reply.

## What to review
The plan under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/a95b18a2-b25c-4e0c-98eb-cde44eaf5953/scratchpad/specreview/plan-frozen.md. Review exactly that file; do not open any other copy of it or git history.

## How the plan is used
Subagent-driven development: an implementer subagent sees ONE task (plus the spec and the code), implements it test-first, and then a spec-compliance reviewer and a code-quality reviewer check the result against that task. Tasks run in order on branch playout-scheduler in the worktree /Users/shawn/projects/llama/.claude/worktrees/scheduler.

## Context you may read (read-only)
- The approved spec it implements: /Users/shawn/projects/llama/.claude/worktrees/scheduler/docs/superpowers/specs/2026-10-25-scheduler-design.md (and its parent /Users/shawn/projects/llama/.claude/worktrees/scheduler/docs/superpowers/specs/2026-10-09-playout-design.md).
- The code it changes: /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/src/transmitter/ and tests /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/tests_transmitter/ (helpers.py has make_station, FakeEngine, build_package, NOW/E); /Users/shawn/projects/llama/.claude/worktrees/scheduler/antenna/public/ and /Users/shawn/projects/llama/.claude/worktrees/scheduler/antenna/test/.
- Project conventions: /Users/shawn/projects/llama/.claude/worktrees/scheduler/CLAUDE.md (transmitter and antenna paragraphs; the worktree-venv and copied-tree warnings in Commands).

## Stakes (read before reviewing)
The risk is on-air continuity and the listening experience, not money or data. Strict surfaces (irreversible once wrong): (1) a persisted plan.jsonl row never changes (append-only; only phase 1's replan_from skip path and cut_for_recovery drop rows) because rendered segments may already be published under immutable, year-cached keys; (2) never cut a show mid-song and never leave silence beyond the configured gaps; (3) never list a segment that does not exist. Common setup: one transmitter service on hugo (Debian 12, Python 3.11) reading a few hundred to a few thousand packages over NFS, ~24 h lead, clock edits weekly-ish. Elsewhere, a defect whose worst case is a badly chosen show, a late block, a dropped announcement or a misleading status line is Minor at most. Where the plan is over-built for these stakes, a removal is a valid finding.

## What to look for
1. Fidelity: anything in the spec the plan omits, changes or adds (flag added mechanisms).
2. Decomposition and order: task boundaries, dependencies, each task leaving every suite green and wired up; checkpoint placement.
3. Strict surfaces: whether the tasks that touch them test the right scenarios.
4. Interfaces: formats, options and exit codes defined once and used consistently across tasks (names, signatures, field names).
5. Executability: whether an implementer seeing one task could carry it out without inventing anything — including whether its tests run where they will run (macOS dev box with/without ffmpeg; hugo's Python 3.11).
6. Proportion and sprawl; idioms implementers will copy.

## Output format
Findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: task and step, with a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, or the conflicting quote
  - Failure scenario: what goes wrong for the implementer or on air
  - Suggested fix: one sentence
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
