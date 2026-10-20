You are the implementer for Task 15 of the held-backlog Tier 1 run (llama repo): slice 4's deterministic vet fixes — 4c `normalize_date` range checks with a day-first fallback, 4b adjacent-day dates as context, 4d prompt wording. Model: Sonnet.

## Read first
1. Common rules (binding, read in full): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r2/common.md
2. Your brief — read this first; it is your requirements, with the exact values to use verbatim: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-15-brief.md
3. Spec (binding authority) — "Slice 4": the 4b, 4c, 4d bullets (~lines 727-766) and "New constants" (~line 981): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md

## Context the brief cannot know
- Worktree / cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1, BASE b9ae699 (suite 3621 passed, 1 skipped, 8 deselected).
- `grounding_flags` already returns a 3-tuple `(flags, adopted, notes)` (Task 3); `notes` is currently always `[]`. Task 15 keeps the 3-tuple and does not add notes.
- `raw_date_flags`: keep it as a local in `grounding_flags` exactly as the brief says (Task 16 will read it); it is unused in this task — a short comment saying Task 16 / 4a reads it is enough. Do not change the return signature.
- The 4b window's one-day constant is a spec "New constant": name it in code with a comment citing the spec section ("Slice 4 — 4b", "New constants").
- CARRIED from an earlier review (do it in this task): (a) `run_vet_research` writes `notes.json` AFTER `vetting.json`, but `vetting.json` is the stage's done-marker (`should_run` checks it). Reorder so `vetting.json` is written LAST (show.json, then notes.json, then vetting.json), with a one-line comment why; add a test that pins the order only if it is cheap and deterministic (e.g. mtimes are not reliable — prefer monkeypatching `write_artifact` to record the order). (b) `packages/llama/tests/test_stage_vet.py` has no `import pytest`; the brief's tests use `pytest.mark.parametrize` — add `import pytest` to the file's top imports (not mid-file).
- Ambiguity resolution: the brief's test block begins with `from llama.stages.vet_research import grounding_flags` mid-file; put that import with the file's other top imports instead (equivalent, cleaner).
- Mutation step: the brief's four mutants (a)–(d), per Global Constraints' recipe AND common.md's "Mutation scratch copies" rule (`MROOT=$(mktemp -d "$TMPDIR/mut-t15-impl-XXXXXX")`, echo it into your log, delete only that exact path). Write each predicted test BEFORE flipping.

## Report contract
- Full report (what you changed, test commands + output lines, the mutation table `mutant -> predicted test -> caught by | SURVIVED`, any deviations, concerns) to `$D/t15-impl/handback.md`, then touch `$D/t15-impl/done`. Return the same report as your final reply, but keep the reply short: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), commits, one-line test summary, concerns.
- If later resumed for a fix round R, append the fix report to the same handback.md, then touch `$D/t15-impl/done-r<R>`.
- `$D` = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to `$D/t15-impl/handback.md`, **then** touch `$D/t15-impl/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/t15-impl" && touch "$D/t15-impl/t15-impl.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/t15-impl/t15-impl.log"` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinels. Echo a progress line into the log during any long stretch of work that is not a teed command. A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds (Bash `timeout` parameter 300000 ms).
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/t15-impl` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Multi-step work commits each coherent step rather than batching at the end. Commit only states where the change is wired up and the suite passes (state the test command in the commit message). **Never run `git stash` in any form** (not even `git stash list`). To set work aside, make a WIP commit. **Never `git clean -x`/`-X`.**
5. **Deliberate breakage only in a scratch copy.** Deliberate breakage (mutants and the like) only in a scratch copy (`git worktree add` or `git archive | tar -x`, or the plan's rsync recipe), run from a scratch or empty cwd, never in the live worktree.

You do not dispatch subagents. Never touch ~/.llama except reading.
