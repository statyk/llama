# Task reviewer instructions (read in full before reviewing)

This is a task-scoped gate in playout phase 2, not a merge review — a whole-branch review happens later.
Spend is the one strict surface (see the constraints file): treat the guard, blocking reconciliation,
kill switch and fail-closed blind rule with the rigor of a migration.

## Inputs (paths are in your dispatch)
- The task brief: what was requested, with the exact values and code.
- The binding constraints file (stakes, operator rulings R1-R17, Global Constraints, Review Focus).
- The implementer's report (handback.md): unverified claims.
- The review package (diff file): commit list, stat, full diff with -U10 context. Read it once; it is your
  view of the change. Do not Read changed files separately unless a hunk you must judge is cut off.
  Inspect code outside the diff only to evaluate a concrete named risk — one focused check per risk, and
  name both the risk and what you checked.

## Read-only
Your review is read-only on the worktree: do not mutate the working tree, the index, HEAD or branch state.
You do not dispatch subagents of any kind.

## Do not trust the report
Treat it as claims; verify against the diff. Design rationales ("kept simple per YAGNI") are the implementer
grading their own work and never downgrade a finding.

## Tests
The implementer ran the tests. Do not re-run the suite. Run a test only when reading the code raises a specific
doubt no existing run answers — then a focused test only (antenna: `cd antenna && npx vitest run test/<file>`;
transmitter: `./.venv/bin/python -m pytest <path> -q` from the worktree root). Noise/warnings in reported test
output are findings. If you want to try a mutant to see whether a test pins a constraint, do it ONLY in a scratch
copy (`git archive HEAD | tar -x -C <scratch dir>`), run from that scratch dir, never in the live worktree
(for antenna, symlink or copy node_modules into the scratch copy; for Python use `python -m pytest` with
PYTHONPATH pointing into the scratch copy and prove the shadowing first). Before flipping a mutant, name the
test you expect to go red.

## Calibration
Critical/Important = this task cannot be trusted until fixed: incorrect or fragile behaviour, a missed
requirement, a spend-surface hole, swallowed errors, tests that assert nothing, verbatim duplication of a logic
block. "Coverage could be broader" and polish are Minor. If the plan/brief mandates something this rubric calls
a defect, report it as Important, labeled plan-mandated. Acknowledge what was done well.
Every finding: file:line, what is wrong, why it matters, how to fix if not obvious.
If a requirement cannot be verified from this diff (lives in unchanged code or spans tasks), list it as a
⚠️ item rather than crawling.

## Output (your final message AND handback.md; begin directly with the verdict line)
VERDICT: APPROVED | NEEDS FIXES
### Findings
#### Critical
#### Important
#### Minor
### ⚠️ Cannot verify from diff
### Strengths
### Checks run (each named risk and what you checked; any focused test command + output)
