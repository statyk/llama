You are reviewing an implementation plan before it is executed. You are a reviewer only: do not
edit, create or delete any file anywhere, do not commit, and do not run llama or any command
that writes. Read-only shell commands and read-only Python importing the repo code from
/Users/shawn/projects/llama/.venv/bin/python are fine. Return your review as your final text reply.

## What to review
The plan: /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/plan-r1.md. The spec it implements: /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/spec-final.md. Review exactly those files;
do not open other copies or git history of them.

## How the plan is used
A peer orchestrator runs subagent-driven development: an implementer subagent sees ONE task
(plus the spec, the plan's Global Constraints and the code), then a spec-compliance reviewer and
a code-quality reviewer check the result against that task. Checkpoints report to the operator.

## Context you may read (read-only)
/Users/shawn/projects/llama (CLAUDE.md; packages/llama/src/llama/setlist.py, structure.py,
jerrybase.py, stages/gather.py, replay.py, reapply.py, models.py, cli.py; packages/llama/tests/
test_stage_gather.py, test_replay.py, test_reapply.py, test_setlist.py; scripts/replay_holds.py,
scripts/test_replay_holds.py); docs/superpowers/2026-10-22-taper-set-markers-evidence/;
~/.llama-harness/t3/ (verdicts, bundles); ~/.llama/cache and ~/.llama/shows (read-only).

## Stakes
llama feeds an automated radio station; set structure is spoken on air. Strict surfaces: a hold
this change clears; silent structure changes on shipped shows; the stored-llm needs-LLM
relaxation in replay.py (reapply shares it); any change to titles or parse_setlist's output.
Elsewhere, report only defects plausible on this library (~3,800 LMA shows, heavy Grateful Dead
family); a defect whose worst case is a show staying held as today is Minor at most.

## What to look for
1. Fidelity: anything in the spec the plan omits, changes or adds (flag added mechanisms).
2. Decomposition and order: task boundaries, dependencies, each task leaving every suite green
   and wired up; checkpoint placement (the spec requires a yield gate before building).
3. Strict surfaces: whether the tasks that touch them test the right scenarios.
4. Interfaces: names, types, formats and options defined once and used consistently.
5. Executability: whether an implementer seeing one task could carry it out without inventing
   anything, including whether its tests can run offline where they will run.
6. Proportion and sprawl; idioms implementers will copy.

## Output format
Findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: task and step, short exact quote
  - Problem / Evidence (file:line or quote) / Failure scenario / Suggested fix (one sentence)
End with: TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)
