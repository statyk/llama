# Implementer instructions (common to every implementer in this run)

Worktree (cwd for everything): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes (branch held-backlog-small-fixes-impl). Its own .venv resolves llama inside this worktree.
- Read your task brief first (named in your dispatch): it is your requirements, with exact values and test code to use verbatim.
- Read the binding global constraints: .superpowers/sdd/2026-10-21-held-backlog-small-fixes/global-constraints.md
- Read the spec slice your dispatch names in docs/superpowers/specs/2026-10-21-held-backlog-small-fixes-design.md (the spec is the authority over the plan). Do not read the whole plan file.
- Every test command is `./.venv/bin/python -m pytest ...` from the worktree root. Never a bare `pytest`, never `.venv/bin/pytest` from a copy.
- Test snippets in the brief name helpers from the existing test files; check each file's imports and fixtures, add what is missing; if a helper's real signature differs from the snippet, adapt minimally and say so in your report.
- If any EXISTING test changes outcome, or the brief contradicts the code in a way that needs a design decision, stop and report NEEDS_CONTEXT with specifics rather than edit the test or guess.
- Never write to ~/.llama. Never run deliver/rm/fix/redo/reapply against the live library.

## Your job
1. TDD: write the brief's tests, run them and see them fail (record the RED output), implement, see them pass. 2. Full suite once before committing. 3. Commit per the brief (plus the test line and the trailer from global-constraints.md). 4. Self-review your diff (completeness, names, YAGNI, existing patterns, tests verify behaviour, pristine output). 5. Report.
You do not dispatch subagents — not helpers, never a reviewer. Review is the controller's job after you report.
If your work is resumed with review findings: fix them, re-run the covering tests, append a fix report (what changed, covering tests, the literal command, output) to handback.md, touch `done` again, and reply with the short contract.

## Mandates (verbatim, binding). $D = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes/.superpowers/sdd/small-fixes ; <task> is named in your dispatch.
1. **Report, then sentinel.** Write the full report to `$D/<task>/handback.md`, **then** touch `$D/<task>/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/<task>" && touch "$D/<task>/<task>.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/<task>/<task>.log"` for every long-running command. Nothing else may be written to this directory. Echo a progress line into the log during any long stretch of work that is not a teed command. **A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds** (each chunk a Bash call with the tool's `timeout` parameter set to 300000 ms), testing for the command's exit (for example a `"$D/<task>/<cmd>.rc"` file written by `cmd; echo $? > …rc`). (The full suite takes ~75 s and may run in the foreground.)
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/<task>` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Multi-step work commits each coherent step rather than batching at the end. **Commit only states where the change is wired up and the suite passes** (state the test command in the commit message — a green claim without its command is unauditable). **Never run `git stash` in any form.** The stash stack is shared by every worktree; to set work aside, make a WIP commit. **Never `git clean -x`/`-X`:** it deletes ignored files, and `$D` is one.
5. **Deliberate breakage only in a scratch copy.** Deliberate breakage (mutants and the like) only in a scratch copy (`git worktree add` or `git archive | tar -x`), run from a scratch or empty cwd, never in the live worktree.

## Report format
handback.md: what you implemented; tests and results; TDD evidence (RED: literal command + relevant failing output + why expected; GREEN: literal command + passing output); files changed; self-review findings; concerns.
Final reply (under 15 lines): Status (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT); commits (short SHA + subject); one-line test summary with the full-suite count; concerns; the handback path. If BLOCKED/NEEDS_CONTEXT, put the specifics in the reply.
