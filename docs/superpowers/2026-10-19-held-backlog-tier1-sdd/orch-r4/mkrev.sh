#!/bin/bash
# usage: mkrev.sh <rev-task> <impl-brief> <base-sha> <head-sha>  -> writes $O/<rev-task>-brief.md and prompt
T=$1; B=$2; BASE=$3; HEAD=$4
D=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1; O=$D/orch-r4; W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1
git -C $W diff $BASE..$HEAD > $O/$T-$BASE..$HEAD.diff
cat > $O/$T-brief.md <<P
# $T — combined spec-compliance + code-quality review (READ-ONLY)

You review commits $BASE..$HEAD on branch held-backlog-tier1 (worktree $W). You change NO files in the worktree and make NO commits. **Another implementer may be committing in the worktree while you work: never read source or run tests in the live worktree.** First take a snapshot: \`S=\$(mktemp -d "\$TMPDIR/$T-snap-XXXXXX"); git -C $W archive $HEAD | tar -x -C "\$S"\`, echo \$S into your log, and read/run everything there, using the worktree's interpreter with PYTHONPATH shadowing (\`cd "\$S" && PYTHONPATH="\$S/packages/llama/src:\$S/packages/herder/src" PYTHONPYCACHEPREFIX="\$S/.pyc" $W/.venv/bin/python -m pytest -q -p no:cacheprovider\`; prove the shadowing once with \`-c 'import llama; print(llama.__file__)'\`). Mutants go in further copies of \$S. Remove only your own \$S at the end.

- The implementer's requirements: $B (this is the spec you check compliance against).
- The diff: $O/$T-$BASE..$HEAD.diff (also \`git -C $W diff $BASE..$HEAD\`). The implementer's report is in the matching \`$D/<impl-task>/handback.md\` — read it AFTER forming your own view of the diff, and treat its claims as claims to verify, not facts.
- Binding project constraints: the plan's "Global Constraints" (docs/superpowers/plans/2026-10-19-held-backlog-tier1.md lines 24-43) and the project CLAUDE.md. The data is the operator's live library: briefing_guard and title/structure code are the STRICT surface — a change that silently loosens a guard (fewer holds) is Critical/Important unless the brief asked for exactly that loosening.

## Check
1. **Spec compliance**: every required item of the brief is done, nothing extra was changed, verbatim values are verbatim. List each brief item ✅/❌ with file:line.
2. **Code quality**: correctness, edge cases, idiom matching the surrounding code, comment density, test quality (do the tests test behaviour and would they fail on the bug?). Grep the diff for every do-not-retune name in Global Constraints — none may move.
3. **Mutation spot-check**: re-run at least ONE of the implementer's claimed mutants yourself per the plan's recipe (predicted test written before the flip; PYTHONPATH shadowing proven; private PYTHONPYCACHEPREFIX) and confirm the claimed catch. Name any mutant the brief should have listed and didn't, and run it if cheap.
4. Run the full suite once in your snapshot (command above) and report the exact count line.

## Verdict format (handback.md)
First line: \`VERDICT: APPROVED\` or \`VERDICT: CHANGES REQUIRED\`. Then: spec table; findings as Critical / Important / Minor, each with file:line, the failure scenario, and a concrete fix; mutation spot-check table; suite line. Be concise.
P
$O/mkprompt.sh $T opus "You are an independent REVIEWER (spec compliance + code quality) for a post-apply fix-wave task of the held-backlog Tier 1 run (llama repo). You change no files in the worktree and make no commits." $O/$T-brief.md
