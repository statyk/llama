You are re-reviewing one task's fix round. A previous review produced
findings; an implementer has attempted to fix them. Your job is to
verdict each finding and inspect the fix diff — nothing else.

## The Task

Read the task brief: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-16-brief.md

## The Findings Under Verification

1. [Important] No test makes the tape-fraction clause the only reason right_show_gate declines: the brief's `(8, 0, 3, ["1973-06-10"], False)  # below 0.5` row also fails RIGHT_SHOW_MIN_ASSERTED = 4, so deleting `and len(asserted) >= RIGHT_SHOW_MIN_TAPE_FRACTION * len(resolved)` survived (reviewer-verified, 69 passed). Orchestrator ruling: ADD a row where only the fraction fails (e.g. (10, 0, 4, ...)), keep the brief's row with a corrected comment, and show mutants f1 (delete the clause) and f2 (numerator len(asserted)) caught by the new row.
2. [Minor, folded in by orchestrator] packages/llama/src/llama/stages/brief.py `_guard_prose` docstring is non-raw and contains `\s+`, emitting `SyntaxWarning: "\s" is an invalid escape sequence` on a fresh compile; make it a raw string, wording unchanged.

## The Fix

Read the implementer's report (fix reports are appended at the end):
/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/t16-impl/handback.md

**Fix base:** f0d7b9a (the head the previous review saw)
**Head:** 3928398
**Diff file:** /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/review-f0d7b9a..3928398.diff

Read the diff file once — it contains the fix commits, a stat summary,
and the fix diff with surrounding context. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat f0d7b9a..3928398` and
`git diff f0d7b9a..3928398`.

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
Your task name is t16-rr1; $D = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1.
1. Report, then sentinel: write your full re-review to `$D/t16-rr1/handback.md`, THEN touch `$D/t16-rr1/done`; also return it as your final reply.
2. First action: `mkdir -p "$D/t16-rr1" && touch "$D/t16-rr1/t16-rr1.log"`; nothing else is written to that directory.
3. Check `$D/TAKEN_OVER` and `$D/taken-over/t16-rr1` before each write batch; if either exists, stop and write a final report.
4. You make no commits. Never run `git stash` in any form. Never `git clean -x`/`-X`.
5. Deliberate breakage only in a scratch copy under your own `mktemp -d "$TMPDIR/mut-t16-rr1-XXXXXX"`, never in the live worktree; delete only that exact path.
