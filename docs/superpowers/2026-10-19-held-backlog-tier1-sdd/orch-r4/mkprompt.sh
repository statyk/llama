#!/bin/bash
# usage: mkprompt.sh <task> <model> <role-line> <brief-path>  -> writes $O/<task>-prompt.md
T=$1; M=$2; ROLE=$3; B=$4
D=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1; O=$D/orch-r4
cat > $O/$T-prompt.md <<P
$ROLE Model: $M.

## Read first
1. Common rules (binding, read in full): $O/common.md
2. Your brief (your requirements; values in it are verbatim): $B

## Context
- Worktree / cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1. Read HEAD yourself (\`git log -1\`); suite at 4cd1ebc: 3762 passed, 1 skipped, 8 deselected.
- \`scripts\` is in pytest testpaths.

## Report contract
- Full report (what you changed, test commands + output lines, the mutation table \`mutant -> predicted test -> caught by | SURVIVED\` when your brief lists mutants, deviations, concerns) to \`\$D/$T/handback.md\`, then touch \`\$D/$T/done\`. Return the same report as your final reply, but keep the reply short: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), commits, one-line test summary, concerns.
- If later resumed for a fix round R, append the fix report to the same handback.md, then touch \`\$D/$T/done-r<R>\`.
- \`\$D\` = $D

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to \`\$D/$T/handback.md\`, **then** touch \`\$D/$T/done\`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** \`mkdir -p "\$D/$T" && touch "\$D/$T/$T.log"\` as your **first action**, before any work, then \`cmd 2>&1 | tee -a "\$D/$T/$T.log"\` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinels. Echo a progress line into the log during any long stretch of work that is not a teed command. A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds (Bash \`timeout\` parameter 300000 ms).
3. **Check \`\$D/TAKEN_OVER\` and \`\$D/taken-over/$T\` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Multi-step work commits each coherent step rather than batching at the end. Commit only states where the change is wired up and the suite passes (state the test command in the commit message). **Never run \`git stash\` in any form** (not even \`git stash list\`). To set work aside, make a WIP commit. **Never \`git clean -x\`/\`-X\`.**
5. **Deliberate breakage only in a scratch copy.** Deliberate breakage (mutants and the like) only in a scratch copy (\`git worktree add\` or \`git archive | tar -x\`, or the plan's rsync recipe), run from a scratch or empty cwd, never in the live worktree.

You do not dispatch subagents. Never touch ~/.llama except reading.
P
echo $O/$T-prompt.md
