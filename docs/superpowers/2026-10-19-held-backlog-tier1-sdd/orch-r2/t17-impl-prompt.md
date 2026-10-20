You are the implementer for Task 17 of the held-backlog Tier 1 run (llama repo): slice 5a — the structure guard counts numbered sets only as set evidence, except when the canonical's encore was lost from the tape (unplaced-encore exception). Model: Sonnet.

## Read first
1. Common rules (binding, read in full): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r2/common.md
2. Your brief — read this first; it is your requirements, with the exact values to use verbatim: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-17-brief.md
3. Spec (binding authority) — "Slice 5 — 5a" (~line 772 onward): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md

## Context the brief cannot know
- Worktree / cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1, BASE e59a6d8 (suite 3677 passed, 1 skipped, 8 deselected). The `run_gather`/`compute_gather` split (Task 1) is in `packages/llama/src/llama/stages/gather.py`; find the `structure_guard(...)` call there.
- **Pre-flight finding B4 (binding ruling):** `packages/llama/tests/test_structure.py` ALREADY defines a helper `_tracks(n, dur)` with ~36 callers. The brief's new helper named `_tracks(*titles)` would shadow it and break ~30 existing tests. Name the new helper `_titled_tracks(*titles)` (and use that name in every new 5a test); leave the existing `_tracks` untouched. Check `_items` for the same collision before adding it (rename to `_encore_items` if a helper of that name exists).
- Ambiguity resolution: put the brief's mid-file `from llama.structure import encore_lost` with the file's top-level imports instead. `fuzzy_norm_title` and `title_components` already exist in structure.py — reuse them; `songs.normalize_song`, `DEFAULT_ALIASES` and `structure._STRUCTURE_PREFIX` are do-not-retune: call, never change.
- Mutation step: the brief's mutants (a)–(c), per Global Constraints' recipe AND common.md's scratch rule (`MROOT=$(mktemp -d "$TMPDIR/mut-t17-impl-XXXXXX")`, echo it into your log, delete only that exact path; if the delete is refused, leave it and say so). Predicted test written BEFORE each flip.

## Report contract
- Full report (what you changed, test commands + output lines, the mutation table `mutant -> predicted test -> caught by | SURVIVED`, any deviations, concerns) to `$D/t17-impl/handback.md`, then touch `$D/t17-impl/done`. Return the same report as your final reply, but keep the reply short: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), commits, one-line test summary, concerns.
- If later resumed for a fix round R, append the fix report to the same handback.md, then touch `$D/t17-impl/done-r<R>`.
- `$D` = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to `$D/t17-impl/handback.md`, **then** touch `$D/t17-impl/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/t17-impl" && touch "$D/t17-impl/t17-impl.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/t17-impl/t17-impl.log"` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinels. Echo a progress line into the log during any long stretch of work that is not a teed command. A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds (Bash `timeout` parameter 300000 ms).
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/t17-impl` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Multi-step work commits each coherent step rather than batching at the end. Commit only states where the change is wired up and the suite passes (state the test command in the commit message). **Never run `git stash` in any form** (not even `git stash list`). To set work aside, make a WIP commit. **Never `git clean -x`/`-X`.**
5. **Deliberate breakage only in a scratch copy.** Deliberate breakage (mutants and the like) only in a scratch copy (`git worktree add` or `git archive | tar -x`, or the plan's rsync recipe), run from a scratch or empty cwd, never in the live worktree.

You do not dispatch subagents. Never touch ~/.llama except reading.
