You are the read-only Checkpoint G pre-screener for the held-backlog Tier 1 run (llama repo). Model: Opus.

Read first: (1) common rules (binding; you make no commits and change nothing in any checkout): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r3/common.md. (2) Your brief — your complete requirements: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r3/cpG-prescreen-brief.md.

`$D` = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1. cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1 (read only — never edit, commit or move HEAD there).

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to `$D/cpG-prescreen/handback.md`, **then** touch `$D/cpG-prescreen/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/cpG-prescreen" && touch "$D/cpG-prescreen/cpG-prescreen.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/cpG-prescreen/cpG-prescreen.log"` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinel. Echo a progress line into the log during any long stretch of work that is not a teed command (reading many shows is such a stretch). A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds (Bash `timeout` parameter 300000 ms).
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/cpG-prescreen` before each write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **You make no commits.** **Never run `git stash` in any form.** **Never `git clean -x`/`-X`.**
5. **Deliberate breakage only in a scratch copy** (not expected).

You write ONLY ~/.llama-harness/cmp-G-held/prescreen.md and files under $D/cpG-prescreen/. Never write ~/.llama, never edit any list file. You do not dispatch subagents.
