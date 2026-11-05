You are re-reviewing one task's fix round. A previous review produced
findings; an implementer has attempted to fix them. Your job is to
verdict each finding and inspect the fix diff — nothing else.

## The Task

Read the task brief: /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/2026-11-04-programs-and-lineup/task-9-brief.md (retitle) and /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/2026-11-04-programs-and-lineup/task-13-brief.md (probe); the findings below are from the final review, not a single task

## The Findings Under Verification

From the final whole-branch review (full text: /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/programs/t14-final-review/handback.md — read its triage rows for these IDs):
- T9-N1 (MUST-FIX): packages/emcee/CLAUDE.md hand-restore runbook copied the backup over the live file then fixed mtime. Required: temp in the package dir + fsync + utime + os.replace + re-check/re-apply mtime; only with no emcee/llama running or under the station lock; a correct pasteable Python snippet matching the real backup layout and record.jsonl fields.
- T9-N2 (MUST-FIX): spell out the three outcomes for a slug with a before line and no after line (file == original: nothing; file == this run's unrecorded write; foreign write: leave) plus the failed put-back case; record.jsonl's before line gains "title": <new title> so case (b) is checkable, with a test; no other write-path change; other record fields and order kept.
- T13b (SHOULD-FIX): station_probe cross passed vacuously with a stale .lock-race-<tag> (acquired 0, contended N, rc 0). Required: exit 3 when acquired == 0 with a message naming the possibly stale lock; refuse to start when the lock file pre-exists; tests; scripts/CLAUDE.md pass rule updated; py3.11/stdlib.
- T11a/T11i (SHOULD-FIX): station_lock docstrings (emcee + llama, ~:24-27) and emcee CLAUDE.md:44-45 claimed every station write is an atomic rename; must name the exceptions (llama deliver overlay copytree; replace path's two renames). Docs only.
- T11g (SHOULD-FIX): llama CLAUDE.md ~:178 "does not share this locking scheme" -> the flock scheme.
- T12b (SHOULD-FIX): wrap the 118-col unmark docstring at scripts/bulk_apply.py:1182.
Also judge on its merits: the implementer ADDED pacing to cross (_race_loop(paced=True): random sleep up to HOLD_SECONDS after a refused create, up to 2x after a release) because without it the loser side got acquired 0 in 3/3 real two-sided runs, which the new exit-3 rule would fail. Does pacing preserve the probe's ability to detect a double acquisition across hosts (does it still produce real contention/overlap, or does it serialise the sides so that a broken O_EXCL would go unseen)? Is the DROP_EXCL path still detecting doubles under cross? race must be unchanged.
Strict surface: emcee retitle's record.jsonl is an operator restore record for live-share manifest writes.


## The Fix

Read the implementer's report (fix reports are appended at the end):
/Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/programs/t14-fix/handback.md

**Fix base:** 33198e55 (the head the previous review saw)
**Head:** 434c2637
**Diff file:** /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/2026-11-04-programs-and-lineup/review-33198e55..434c2637.diff

Read the diff file once — it contains the fix commits, a stat summary,
and the fix diff with surrounding context. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat 33198e55..434c2637` and
`git diff 33198e55..434c2637`.

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
