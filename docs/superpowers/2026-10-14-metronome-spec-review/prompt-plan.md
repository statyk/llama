You are reviewing an implementation plan before it is executed. You are a reviewer only: do not edit, create or delete any file anywhere, do not commit, do not deploy, do not call any Cloudflare API, and do not run anything on remote hosts. You MAY run read-only commands and the test suite inside the scratch copy named below. Return your review as your final text reply.

## How the plan is used
Execution is subagent-driven: an implementer sees ONE task (plus the spec and the code), implements it in a git worktree, and then an Opus spec-compliance reviewer and an Opus code-quality reviewer check the result against that task. A final whole-branch review runs on Fable. So every task must be executable without inventing anything, and its tests must run where they will run.

## What to review
The plan under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/plan-r1.md. Review exactly that file; do not open any other copy of it or git history of it.
It implements this approved spec (read it first): /Users/shawn/projects/llama/docs/superpowers/specs/2026-10-14-antenna-metronome-design.md
Why the spec says what it says (settled decisions; do not re-open the design): /Users/shawn/projects/llama/docs/superpowers/2026-10-14-metronome-spec-review/ (decisions-r1.md, decisions-r2.md).

## Context you may read (read-only)
- The code it changes: /Users/shawn/projects/llama/antenna/ (src/, test/, wrangler.jsonc, package.json, vitest config).
- The plan writer ran Tasks 1-7's code in a scratch copy with one git commit per task: /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/../ant (cd there; `git log --oneline`, `git show <sha>`; you may run `npm test` / `npm run typecheck` there, read-only otherwise). Use it to check whether the plan's code actually compiles and passes as written, but review the PLAN TEXT: an implementer will only see the plan.
- Project conventions: /Users/shawn/projects/llama/CLAUDE.md (antenna paragraph).

## Stakes (read before reviewing)
What is at risk is money and on-air continuity, not data. A single operator runs a non-commercial internet radio station; budget $15/month incl. the $5 Workers Paid base. Strict surface: SPEND (Cloudflare has no spending cap). The plan adds a Durable Object and a second writer of a billed R2 object; a runaway alarm chain, an unpriced meter, a PUT bound that trusts its inputs, or a path where the station keeps spending while the cost guard cannot see it is an uncapped bill. Fail-closed must survive: an unknown verdict is never treated as unblocked. Report exhaustively on the strict surface; elsewhere report only defects plausible on this deployment; a removal is a valid finding.

## What to look for
1. Fidelity: anything in the spec the plan omits, changes or adds (flag added mechanisms).
2. Decomposition and order: task boundaries, dependencies, each task leaving every suite green and wired up; checkpoint placement.
3. Strict surfaces: whether the tasks that touch them test the right scenarios.
4. Interfaces: formats, options and names defined once and used consistently across tasks.
5. Executability: whether an implementer seeing one task could carry it out without inventing anything — including whether its tests run where they will run (vitest in the Workers runtime via @cloudflare/vitest-plugin).
6. Proportion and sprawl; idioms implementers will copy.

## Output format
Findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: task and step, plus a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, or the conflicting quote
  - Failure scenario: what goes wrong when an implementer follows the plan
  - Suggested fix: one sentence
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
