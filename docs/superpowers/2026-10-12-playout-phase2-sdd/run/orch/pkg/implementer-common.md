# Implementer rules (read in full before starting)

## Where
Work only in the worktree /Users/shawn/projects/llama/.claude/worktrees/playout-phase2 (branch playout-phase2;
never switch branches, merge, push or tag).
- antenna: `cd antenna && npm test && npx tsc --noEmit`. node_modules is installed — do not run npm install/ci.
- transmitter: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` from the worktree root,
  then on Python 3.11: `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`, then the
  Debian-12 gate `packages/transmitter/scripts/test-in-debian12.sh` (Docker is running; run it in the
  background teed into your log — it takes a minute or two). Never run a `.venv/bin/*` console script.

## Hard rules
- This repo is PUBLIC: no account ID, zone ID, token, key or email address (except alerts@lma-radio.com) in any
  committed file.
- No `wrangler deploy`, `wrangler secret put`, `deploy:assets`, `--dry-run`, or anything touching the real
  Cloudflare account, R2, ntfy or SMTP. No test may reach the network.
- Do not touch `~/lma-radio-ops/` or `~/.transmitter/`.
- Commit by explicit paths (`git add <files>`), never `git add -A` / `git add .`.
- End each commit message with the co-author trailer for your model, e.g.
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` or `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- You do not dispatch subagents of any kind (no helpers, no reviewers). Review is scheduled by the orchestrator.
- The brief's code is the plan's; implement it as written unless it is wrong. If it contradicts the code you
  find, or a test it specifies cannot pass as written, stop and report NEEDS_CONTEXT or BLOCKED with specifics
  (or, if the fix is small and obvious, make it and list it under "Deviations" in your report with the reason).
- While iterating, run the focused test; run the full antenna suite (or transmitter suite) once before committing.

## Report (handback.md) and final reply
What you implemented; files changed; Deviations from the brief (each with the reason); tests with exact commands
and output (TDD evidence: RED command + failing output, GREEN command + passing output, where the brief's steps
call for it); final suite counts; self-review findings; concerns.
Final reply: Status (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT), commits (short SHA + subject),
one-line test summary, concerns, then the full report.

## After review findings
If resumed with findings: fix them, re-run the tests covering the amended code, APPEND a fix report to the same
handback.md (what changed, covering tests, command, output), commit, then touch the sentinel named in the
resume message, and reply with the same short contract.
