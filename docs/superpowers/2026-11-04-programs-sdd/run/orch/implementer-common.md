# Implementer instructions (common to every task)

- Worktree: /Users/shawn/projects/llama/.claude/worktrees/programs, branch programs-lineup. Read the root CLAUDE.md and the CLAUDE.md of every component you touch BEFORE running anything.
- Python tests: `./.venv/bin/pytest` only (never bare pytest). Antenna: `cd antenna && npm test` (plus `npm run smoke`, `npm run typecheck` for page tasks).
- emcee, transmitter and llama never import each other; only scripts/ may import both. Never commit audio. Nothing writes outside the worktree and tmp; tests use tmp_path. Never touch /Volumes/media/lma-radio or hugo; never ssh.
- transmitter stays Python 3.11-compatible (the venv is 3.14: avoid newer syntax/stdlib). Run `packages/transmitter/scripts/test-in-debian12.sh` for transmitter changes if Docker is running; otherwise say so.
- Do not read the whole plan file. The spec (docs/superpowers/specs/2026-11-04-programs-and-lineup-design.md) is the authority if your brief is ambiguous.

## Before you begin / while working
If anything about requirements, approach or assumptions is unclear, stop and report NEEDS_CONTEXT with the specific question. Do not guess. STOP and report BLOCKED when the task requires architectural decisions with several valid approaches, restructuring the plan did not anticipate, or you are reading file after file without progress. Bad work is worse than no work.

## Your job
1. Implement exactly what the task specifies (TDD: write the failing tests first, run them, record the RED output).
2. Verify: focused tests while iterating; the task's full-suite command once before committing.
3. Commit (each commit message ends with the two attribution lines below).
4. Self-review your own diff: completeness against the brief, clear names, YAGNI, tests verify behaviour (not mocks), test output pristine (no new warnings). Fix what you find.
5. Report.

Attribution lines for every commit:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JHQ1oUGVawvoAVh2RYsRXd

## You do not dispatch subagents
Do all the work yourself. Never spawn a subagent, and above all never a reviewer. The controller schedules review after you report.

## Code organization
Follow the plan's file structure. Follow established patterns. If a file grows beyond the plan's intent, report DONE_WITH_CONCERNS rather than splitting on your own.

## After review findings
You may be resumed with findings. Fix them, re-run the covering tests, and APPEND a fix report to your handback.md: what you changed, the covering tests, the command, and the output. Then reply with the same short contract.

## Report
Full report in your handback.md: what you implemented, tests and results, TDD evidence (RED: command + failing output + why expected; GREEN: command + passing output), files changed, self-review findings, concerns. Then reply with ONLY (under 15 lines): Status (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT), commits (short SHA + subject), one-line test summary, concerns, report path. On BLOCKED/NEEDS_CONTEXT put the specifics in the final message itself.
