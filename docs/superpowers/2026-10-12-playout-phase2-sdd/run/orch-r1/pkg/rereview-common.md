# Scoped re-review instructions (read in full)

You are re-reviewing one task's fix round. A previous review produced findings; an implementer attempted to fix
them. Verdict each finding and inspect the fix diff — nothing else. Read-only on the worktree (no changes to the
working tree, index, HEAD or branches). You do not dispatch subagents.

- Read the brief, the findings list in your dispatch, the implementer's report (fix reports appended at the
  end), and the fix diff file once.
- Scope: the findings and the fix diff. Issues outside the fix diff go under Out-of-Scope Observations; they do
  not block.
- Tests: confirm the fix report names the covering tests, the command and the output, and verify claims against
  the diff. Do not re-run the suite. A focused test only for a specific doubt. Mutants only in a scratch copy
  (`git archive HEAD <path> | tar -x -C <scratch>`), run from the scratch dir, naming the expected red test first.

## Output (final message AND handback.md), begin directly with the verdict line
VERDICT: ALL ADDRESSED | OPEN FINDINGS
### Finding verdicts (one per finding, in order: ADDRESSED | NOT ADDRESSED — evidence file:line)
### New breakage in the fix diff (Critical/Important/Minor, file:line) or "none"
### Out-of-scope observations
### Checks run
