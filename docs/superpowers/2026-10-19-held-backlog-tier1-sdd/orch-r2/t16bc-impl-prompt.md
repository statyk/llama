You are the implementer for Tasks 16b and 16c of the held-backlog Tier 1 run (llama repo): two small operator-decided fixes from Checkpoint E — 16b: an asserted day-00 date ("1991-09-00") is a "day unknown" assertion and must still raise the wrong-date flag against a specific show date (vet_research.py); 16c: a harness compare bug (scripts/replay_holds.py). One commit each, 16b first. Model: Sonnet.

## Read first
1. Common rules (binding, read in full): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r2/common.md
2. Your brief — read this first; it is your requirements, with the exact values to use verbatim: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-16bc-brief.md
3. Current code: packages/llama/src/llama/stages/vet_research.py (`normalize_date`, `_valid_ymd`, `_date_flags`, `grounding_flags`, `right_show_gate` — Tasks 15/16 just landed them) and scripts/replay_holds.py (compare's closest-calls section ~lines 490-515).

## Context
- Worktree / cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1, BASE 3928398 (suite 3657 passed, 1 skipped, 8 deselected).
- `normalize_date`'s contract and every existing test stay unchanged. Factor its regex branches so `day_unknown_date` shares them instead of duplicating the patterns; keep `normalize_date`'s outputs byte-identical (the existing tests are the proof).
- `scripts` is in pytest testpaths; run its tests as `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q`.
- Mutation step for 16b only (16c is a harness fix): the brief's mutants (a)–(d), per Global Constraints' recipe AND common.md's scratch rule (`MROOT=$(mktemp -d "$TMPDIR/mut-t16bc-impl-XXXXXX")`, echo it into your log, delete only that exact path; if the delete is refused, leave it and say so). Predicted test written BEFORE each flip; caught only by the predicted or a named test.

## Report contract
- Full report (changes per task, test commands + output lines, the mutation table `mutant -> predicted test -> caught by | SURVIVED`, deviations, concerns) to `$D/t16bc-impl/handback.md`, then touch `$D/t16bc-impl/done`. Return the same report as your final reply, but keep the reply short: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), commits, one-line test summary, concerns.
- If later resumed for a fix round R, append the fix report to the same handback.md, then touch `$D/t16bc-impl/done-r<R>`.
- `$D` = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to `$D/t16bc-impl/handback.md`, **then** touch `$D/t16bc-impl/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/t16bc-impl" && touch "$D/t16bc-impl/t16bc-impl.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/t16bc-impl/t16bc-impl.log"` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinels. Echo a progress line into the log during any long stretch of work that is not a teed command. A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds (Bash `timeout` parameter 300000 ms).
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/t16bc-impl` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Multi-step work commits each coherent step rather than batching at the end. Commit only states where the change is wired up and the suite passes (state the test command in the commit message). **Never run `git stash` in any form** (not even `git stash list`). To set work aside, make a WIP commit. **Never `git clean -x`/`-X`.**
5. **Deliberate breakage only in a scratch copy.** Deliberate breakage (mutants and the like) only in a scratch copy (`git worktree add` or `git archive | tar -x`, or the plan's rsync recipe), run from a scratch or empty cwd, never in the live worktree.

You do not dispatch subagents. Never touch ~/.llama except reading.
