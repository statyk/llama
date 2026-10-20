# Common rules for every tier1 child (read in full)

Worktree (your cwd, the ONLY checkout you touch): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1.
Plan: docs/superpowers/plans/2026-10-19-held-backlog-tier1.md — read only your task brief, the plan's "Global Constraints" (lines 24-43) and "Contracts" (lines 57-120) sections. Spec (binding authority): docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md — read the section your task names.

## Tests
- Always: `./.venv/bin/python -m pytest <files> -q` from the worktree root. Never bare `pytest`, never `.venv/bin/pytest`.
- Full suite before each commit: `./.venv/bin/python -m pytest -q` (~60 s; it may run longer than 4 min only if you add slow tests — then background it). Tee it into your log.
- Confirm once: `./.venv/bin/python -c "import llama; print(llama.__file__)"` prints a path inside the worktree.
- Mutation step (when your task lists mutants): follow Global Constraints' recipe exactly (fresh rsync copy under $TMPDIR, PYTHONPATH shadowing, PYTHONPYCACHEPREFIX per mutant, prove shadowing with -c "import llama; print(llama.__file__)", predicted test written BEFORE flipping). Record the table `mutant -> predicted test -> caught by | SURVIVED` in your handback.

## Hard limits
- ~/.llama is the operator's LIVE library: READ-ONLY. Never run llama get/redo/fix/triage/deliver/reapply/rm against it. Reading ~/.llama/cache/md_<id>.json to cut fixtures is fine.
- Do-not-retune constants stay byte-identical (Global Constraints list).
- Never merge, push, switch branches, tag, or touch another checkout. Never `git stash`. Never `git clean -x`/`-X`.
- You do not dispatch subagents.

## Commits
End every commit message with these two lines (after a blank line):
Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RPSTWKMnYuyZnHLrWrcssY
(If you are not Opus, use your own model name in Co-Authored-By.) State the test command and result in the message body.

## Mutation scratch copies (binding, added 2026-10-19 after an escape)
Create every mutation copy under your OWN uniquely named directory: `MROOT=$(mktemp -d "$TMPDIR/mut-<your-task>-XXXXXX")`, and echo `$MROOT` into your log. Per-mutant copies go inside `$MROOT`. Clean up ONLY that exact path (`rm -rf "$MROOT"`), never a glob over `$TMPDIR` or any shared directory.
