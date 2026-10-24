You are reviewing an implementation plan before it is executed. You are a reviewer only: write no files except the three protocol files named at the end, make no git writes, and run nothing on remote hosts. Return your review as your final text reply.

## What to review
The plan under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45/review/plan-r1-frozen.md. The spec it implements is: /private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45/review/spec-final.md (final, settled after eight spec reviews; do not re-review the spec's design, but DO flag where the plan departs from it). Review exactly those two files; do not open other copies or git history.

## How the plan is used
It is executed by subagent-driven development. An implementer (Sonnet for mechanical tasks, Opus where marked) sees ONE task plus the spec and the code, then Opus spec-compliance and code-quality reviewers check the result against that task. The orchestrator runs the checkpoint tasks and stops for the operator at Checkpoints A, B and C.

## Context you may read (read-only)
- The code: worktree /Users/shawn/projects/llama/.claude/worktrees/junk-filter (code identical to main @ e37f670): packages/llama/src/llama/, packages/llama/tests/, scripts/, pytest config.
- The repo CLAUDE.md (especially the worktree-venv and copied-tree warnings, the junk filter, overrides, fix/redo units, deliver/purge, reapply, the replay harness).
- The evidence dir docs/superpowers/2026-10-23-junk-short-keep-evidence/ and the measurement scripts under ~/.llama-harness/piece45/ (read-only). Never write ~/.llama or /Volumes/media/lma-radio/.

## Stakes
About 4,000 shows, ~2,800 on air; one operator whose attention is scarce. Strict surfaces: (a) the overrides migration and every reader and writer of filename-valued overrides; (b) re-delivering voiced shows (`--replace-voiced` discards paid TTS voicing; only the 37 approved shows); (c) relaxing the junk filter must not admit spam or non-performance audio. Everything else is proportionate: an extra hold or a recoverable redo is Minor at most.

## What to look for
1. Fidelity: anything in the spec the plan omits, changes or adds (flag added mechanisms, and check each "plan reading" the plan marks).
2. Decomposition and order: task boundaries, dependencies, each task leaving every suite green and wired up; checkpoint placement.
3. Strict surfaces: whether the tasks that touch them test the right scenarios.
4. Interfaces: formats, options and exit codes defined once and used consistently.
5. Executability: whether an implementer seeing one task could carry it out without inventing anything, including whether its tests run where they will run (the worktree's own .venv; offline; no ~/.llama writes) and whether its file/function references match the real code.
6. Proportion and sprawl; idioms implementers will copy.

## Output format
Findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: task number plus a short exact quote
  - Problem / Evidence (file:line or quote) / Failure scenario / Suggested fix (one sentence)
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)` and one line: is the plan ready to execute?

## Protocol (D=/private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45, task=pr-1)
1. First action: `touch "$D/pr-1/pr-1.log"`; echo a progress line into it every ~10 minutes.
2. Write the review to `$D/pr-1/handback.md`, THEN touch `$D/pr-1/done`. Also return it as your final reply.
3. If `$D/TAKEN_OVER` or `$D/taken-over/pr-1` exists, stop and write what you have.
