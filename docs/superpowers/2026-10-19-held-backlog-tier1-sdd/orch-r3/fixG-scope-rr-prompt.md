You are re-reviewing one task's fix round. A previous review produced
findings; an implementer has attempted to fix them. Your job is to
verdict each finding and inspect the fix diff — nothing else.

## The Task

Read the task brief: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r3/fixG-scope-brief.md

## The Findings Under Verification

From the FINAL whole-branch review (/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/final-rev/handback.md, section I1):
1. [Important] brief.py `_SCOPE_AFTER = r"^\s*(?:each|every|a|per)\s+(?:night|day|weekend|tour)\b"`: `\s*` matches the `\n` field boundary `_guard_prose` uses, so a set-count/ordinal claim ending one briefing field is suppressed as scoped when the next field starts "A night…"/"Each night…". Probe: `_claim_counts("The band played two sets\nA night to remember")` → no claim; with a period → {2}. Fix asked: `^[^\S\n]*` + one test; mirror of the Task 14 r1 negation-window fix. This guard checks ~128 FRESH briefings about to be generated unread against the live library, so it is strict.
Also judge: does the inner `\s+` (between the scope word and night/day/…) leave any realistic cross-field hole, and does any OTHER 3c window in brief.py still cross the field boundary?

## The Fix

Read the implementer's report (fix reports are appended at the end):
/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/fixG-scope/handback.md

**Fix base:** 030caa7 (the head the previous review saw)
**Head:** 4cd1ebc
**Diff file:** /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/review-030caa7..4cd1ebc.diff

Read the diff file once — it contains the fix commits, a stat summary,
and the fix diff with surrounding context. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat 030caa7..4cd1ebc` and
`git diff 030caa7..4cd1ebc`.

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
Your task name is fixG-scope-rr; $D = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1.
1. Report, then sentinel: write your full re-review to `$D/fixG-scope-rr/handback.md`, THEN touch `$D/fixG-scope-rr/done`; also return it as your final reply.
2. First action: `mkdir -p "$D/fixG-scope-rr" && touch "$D/fixG-scope-rr/fixG-scope-rr.log"`; nothing else is written to that directory.
3. Check `$D/TAKEN_OVER` and `$D/taken-over/fixG-scope-rr` before each write batch; if either exists, stop and write a final report.
4. You make no commits. Never run `git stash` in any form. Never `git clean -x`/`-X`.
5. Deliberate breakage only in a scratch copy under your own `mktemp -d "$TMPDIR/mut-fixG-scope-rr-XXXXXX"`, never in the live worktree; delete only that exact path.
