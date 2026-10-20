You are re-reviewing one task's fix round. A previous review produced
findings; an implementer has attempted to fix them. Your job is to
verdict each finding and inspect the fix diff — nothing else.

## The Task

Read the task brief: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-22-brief.md

## The Findings Under Verification

The full previous review (every finding, with line refs) is at /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/t22-rev/handback.md — read it. Verdict each of its findings ADDRESSED / NOT ADDRESSED:
1. [Important] CLAUDE.md live per-show-cost reading (~3e-11, 'gate inert') — false and stale; replace with the durable statement.
2. [Important] length/shape: Architecture as ONE paragraph/bullet, one sentence per guard; the listed Commands cuts; target ~80-100 added CLAUDE.md lines.
3-14. [Minor x12] as listed in the review (the evidence-pointer minor was deliberately left: the evidence doc does not exist yet).
Also check that the cuts removed nothing load-bearing for a future agent: show.json last = commit marker, the per-show lock span, the -dirty refusal, resumability, the stop rules, notes.json never reaches the LLM, reapply never delivers, 5c.2 dropped/do-not-re-add — and that every statement still holds against the code (docs-only diff: verify any reworded claim against the code it describes).

## The Fix

Read the implementer's report (fix reports are appended at the end):
/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/t22-impl/handback.md

**Fix base:** e408703 (the head the previous review saw)
**Head:** 030caa7
**Diff file:** /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/review-e408703..030caa7.diff

Read the diff file once — it contains the fix commits, a stat summary,
and the fix diff with surrounding context. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat e408703..030caa7` and
`git diff e408703..030caa7`.

Your review is read-only on this checkout. Do not mutate the working
tree, the index, HEAD, or branch state in any way.

## You Do Not Dispatch Subagents

Do all of this review yourself. Never spawn a subagent to review part
of the diff, and never spawn another reviewer for a second opinion.
This process already provides every review seat the work gets; a
reviewer you spawn duplicates one of them at full cost, and its
verdict counts for nothing. If the diff feels too large for one
pass, review it in passes yourself and say so in your report.

## Scope

Your scope is the findings list and the fix diff. Verdict every finding.
Inspect the fix diff for new problems the fix itself introduced. Do NOT
re-review code the fix did not touch: if you notice an issue entirely
outside the fix diff, report it under Out-of-Scope Observations — it
does not block this task and does not extend the loop. A broad
whole-branch review happens after all tasks are complete.

## Tests

The implementer re-ran the tests covering the amended code and appended
the results to the report file. Treat the report as unverified claims:
confirm the fix report names the covering tests and shows their output,
and verify the claims against the diff. Do not re-run the suite to
confirm their report. Run a test only when reading the code raises a
specific doubt that no existing run answers — and then a focused test,
never a package-wide suite.

## Output Format

Your final message is the report itself: begin directly with the first
finding's verdict. Every line is a verdict, a finding with file:line,
or a check you ran — no preamble, no process narration.

### Finding Verdicts

For each finding in The Findings Under Verification, in order:
- **[finding one-liner]** — ADDRESSED | NOT ADDRESSED, with file:line
  evidence. "Attempted" is not addressed: the specific defect must no
  longer exist.

### New Breakage in the Fix Diff

Anything the fix itself broke or introduced, with severity
(Critical/Important/Minor) and file:line. "None" if clean.

### Out-of-Scope Observations

Issues you noticed entirely outside the fix diff. Non-blocking; the
controller ledgers these for the final review. "None" if none.

### Verdict

**Fix round:** [All findings addressed, no new Critical/Important
breakage | Findings remain open] — list the open ones.


## Delivery (binding)
Your task name is t22-rr1; $D = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1.
1. Report, then sentinel: write your full re-review to `$D/t22-rr1/handback.md`, THEN touch `$D/t22-rr1/done`; also return it as your final reply.
2. First action: `mkdir -p "$D/t22-rr1" && touch "$D/t22-rr1/t22-rr1.log"`; nothing else is written to that directory.
3. Check `$D/TAKEN_OVER` and `$D/taken-over/t22-rr1` before each write batch; if either exists, stop and write a final report.
4. You make no commits. Never run `git stash` in any form. Never `git clean -x`/`-X`.
5. Deliberate breakage only in a scratch copy under your own `mktemp -d "$TMPDIR/mut-t22-rr1-XXXXXX"`, never in the live worktree; delete only that exact path.
