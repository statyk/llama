# Rules for every implementer on this run

Work from /Users/shawn/projects/llama/.claude/worktrees/player, branch playout-player. Stay in this worktree. Do not merge, push or switch branches. Nothing touches production: no real `deploy-assets` (only `--dry-run`), no `wrangler r2`, no `wrangler deploy`, nothing on hugo, no secrets. Python tests run as `./.venv/bin/pytest`, never bare `pytest`.

Implement exactly what the brief specifies; run the focused test while iterating and the full suite for what you touched once before committing. Commit messages as the brief gives, the body stating the test command, ending with:

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JHQ1oT2moZYY5Gr3o1EFWi

You do not dispatch subagents. Do all the work yourself; never spawn a subagent, and never a reviewer. Review is scheduled after you report. Self-review means reading your own diff for completeness, quality, discipline (YAGNI, nothing beyond the brief) and tests that verify behaviour. Fix what you find before reporting.

If something is unclear, stop and report NEEDS_CONTEXT or BLOCKED rather than guess, with the specifics in your final message. Use DONE_WITH_CONCERNS for doubts about correctness. Bad work is worse than no work; escalating is never penalised. A file growing beyond the plan's intent is a concern to report, not a reason to split it on your own.

If you are resumed with review findings: fix them, re-run the covering tests, append a fix report to your handback (what changed, tests, command, output), and reply in the same short form.

Report: handback.md holds what you implemented; tests and results; TDD evidence where the brief is test-first (RED: command, failing output; GREEN: command, passing output); files changed; self-review findings; concerns. Your final reply starts with, in under 15 lines: Status (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT), commits (short SHA + subject), one-line test summary, concerns, handback path; then the full report text.
