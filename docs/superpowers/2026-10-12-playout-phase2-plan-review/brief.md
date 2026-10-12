You are reviewing an implementation PLAN before it is executed. You are a reviewer only: do not edit, create or delete any file anywhere, do not commit, do not run anything against Cloudflare or any remote host, and do not run git (it is broken on this machine). Return your review as your final text reply. Never name a file REPORT*/SUMMARY*/FINDINGS*/ANALYSIS*.

## What to review
The plan under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/4da97ce3-033f-41ac-8393-7961aaf833f2/scratchpad/plan-review/plan-frozen.md (playout phase 2: cost guard + operations, ~7,500 lines, 22 tasks T0–T21). Review exactly that file. Do not open any other copy of the plan (in particular not docs/superpowers/plans/2026-10-11-playout-phase2.md) and do not read the scratch prototype under .../scratchpad/proto/.

How the plan is used: execution is subagent-driven. An implementer sees ONE task (plus the spec and the code), implements it TDD-style in a worktree, then Opus reviewers check the result against that task. So every task must be executable on its own without inventing anything, and must leave every suite green.

## Context you may read (read-only)
- The spec: /Users/shawn/projects/llama/docs/superpowers/specs/2026-10-09-playout-design.md (phase 2 = "Cost guard (phase 2)", "Alerts and operations (phase 2)", Phases item 2; Stakes governs).
- The as-built phase-1 code the plan extends: /Users/shawn/projects/llama/packages/transmitter/ (src + tests_transmitter/) and /Users/shawn/projects/llama/antenna/ (src, public, scripts, test, wrangler.jsonc, vitest config, package.json).
- /Users/shawn/projects/llama/CLAUDE.md (transmitter/antenna paragraphs describe as-built behaviour and conventions).
- /Users/shawn/projects/llama/docs/playout-setup.md (runbook) and /Users/shawn/projects/llama/docs/superpowers/2026-10-11-playout-phase1-verification.md (live measurements: cron lag, GraphQL lags, player behaviour, Free-plan rule limits).
- The phase-1 plan for format conventions: /Users/shawn/projects/llama/docs/superpowers/plans/2026-10-10-playout-phase1.md.

## Stakes (read before reviewing)
What is at risk is money and on-air continuity, not data. transmitter only reads the station root; transmitter and antenna write only their own state and their own R2 bucket. A bug elsewhere costs dead air, a glitch, a bad schedule, or a re-render.
One strict surface: spend. The operator's ceiling is "a few tens of dollars a month" (configured: monthly_budget_usd = 15 including the $5 Workers Paid base; alerts at 50%/80%, trip at actual >= 90% or projected >= 100%). Cloudflare has no account spending cap, so the design enforces it: every listener path is a cache-served static object, the clock's ENDLIST playlist stops players, the WAF kill switch blocks the hostname, and the cost guard fails closed when it cannot read usage. A defect there can run up an uncapped bill silently; treat those paths with the rigor of a migration. Secondary but real: the station must never list a segment that does not exist, and must never cut a performance mid-song.
Also strict (security): this repo is PUBLIC. No account ID, API token, R2 key, email address or other account detail may appear in any committed file (code, config templates, tests, docs, generated config that is not git-ignored).
- Strict surfaces — report exhaustively: the guard (metering, pricing, projection, the tripped latch and its set/clear rules, blind rule, state files), blocking reconciliation (ENDLIST/off-air page/kill-switch WAF rule, level-triggered, API-failure handling), anything that could raise per-request or per-write billing (new writes per invocation, new listener-path objects, new Worker routes), the operator commands that change budget/offair state, and secret handling.
- Everywhere else — report only defects plausible on the real setup (one Free zone, Workers Paid, hugo = Debian 12/Python 3.11, macOS dev host, ~1–10 listeners). A defect whose worst case is a missed or duplicate alert, a cosmetic player glitch, or a re-render is Minor at most. For a rare setup, propose a documented limitation rather than a new mechanism. Where the plan is over-built for these stakes, a removal is a valid finding.

## What to look for
1. Fidelity: anything in the spec the plan omits, changes or adds (flag added mechanisms). The plan opens with proposed spec amendments A1–A5 and rulings R1–R17: judge each on its merits (sound? necessary? simpler alternative?).
2. Decomposition and order: task boundaries, dependencies, each task leaving every suite green and wired up; checkpoint placement (incl. the review gate after T8 and the human checkpoints in T19/T20).
3. Strict surfaces: whether the tasks that touch them test the right scenarios — e.g. GraphQL failure/partial/odd data, analytics lag at period boundaries, latch set/clear sequences over many invocations, WAF API failure and recovery, two invocations overlapping, state-file corruption or absence, clock reading its state failing, raise-to and new-period interactions, unknown R2 action types.
4. Interfaces: formats, options and exit codes defined once and used consistently (state/guard.json, state/budget.json, state/offair.json, state/alerts.json, horizon.json `disc`, config keys, CLI commands, the TS/Python shared vectors).
5. Executability: whether an implementer seeing one task could carry it out without inventing anything — including whether its tests run where they will run (macOS dev host; hugo Debian 12 Python 3.11; the Workers vitest pool), and whether test code in the plan matches the real code's names and signatures.
6. Proportion and sprawl; idioms implementers will copy.
7. Premises: the claims the plan rests on (Cloudflare API behaviour, GraphQL dataset/field names, Rulesets API semantics, Email Routing send_email, pricing/allowances, cron behaviour, how the existing code behaves). Check each against the evidence you can read.
Anything you find unclear is a finding.

## Output format
First line: `Foundation: SOUND | UNVERIFIED | PROBLEM — <one sentence>`. PROBLEM means a premise the plan rests on is contradicted by evidence you can cite and the plan misses its goal because of it; this line is not subject to the stakes guidance on severity.

Then findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: task number/section plus a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, or the conflicting quote
  - Failure scenario: concrete inputs or situation, and what goes wrong
  - Setup and likelihood: the setup it needs and how likely it is
  - Suggested fix: one sentence, and roughly what it adds or removes
Then `### Unverified premises`: each claim the plan depends on that the evidence here cannot confirm, with the cheapest test that would settle it (or `none`).
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
