You are the implementer for Task 21 of the held-backlog Tier 1 run (llama repo): `llama fix --untitled` and triage's `[u]ntitled` — the operator route for a tape with no resolved titles (spec slice 7). Model: Sonnet.

## Read first
1. Common rules (binding, read in full): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r3/common.md
2. Your brief — read this first; it is your requirements, with the exact values to use verbatim, EXCEPT where the binding ruling below amends it: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-21-brief.md
3. The plan's "Global Constraints" (lines 24-43) of docs/superpowers/plans/2026-10-19-held-backlog-tier1.md (note: "Only Task 21 (operator-confirmed) writes overrides.json").
4. Spec (binding authority): docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md — "Slice 7 — Operator 'untitled' resolution" and its acceptance.
5. The existing code you extend: `fix`, `_resolve_prompt`, `_interactive_resolve`, `_edit_overrides`, `_redo_show`, `_clear_hold` in packages/llama/src/llama/cli.py, and the `--suggest-titles` path (its combination refusals are the model to follow). Test helpers `_cfg`, `_held_show`, `_stub_redo`, `tty` already exist in test_fix.py / test_triage.py / conftest — read them before writing tests.

## Binding ruling (pre-flight; amends the brief)
- `--untitled` ALSO refuses `--clear-set-breaks`, `--clear-encore` and `--clear-title` (any `--clear-*` that edits titles or structure — check the fix command's real option names), with the same `--untitled cannot be combined with {flag}` message; add them to the parametrized refusal test. Every refusal happens before the confirmation prompt and before anything is written.

## Context
- Pre-flight note: the spec's end-state acceptance (a real tape ends packaged) is met in these tests only with `_redo_show` stubbed, except `test_untitled_gather_makes_no_align_structure_call`, which runs the real `compute_gather`. Say so in your report; do not try to run a real redo.
- Worktree / cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1. BASE = HEAD when you start (Task 20's 23ac815 or a later fix commit). Full suite there: 3728 passed, 1 skipped, 8 deselected.
- Put every import the test snippets need at the top of each test file with the existing imports (not mid-file).
- ~/.llama is the operator's live library: never run `llama fix`/`triage` against it. Tests use tmp_path only.
- Mutation step (not listed in the plan for this task, but overrides.json is operator data): flip in a scratch copy per Global Constraints' recipe AND common.md's scratch rule (`MROOT=$(mktemp -d "$TMPDIR/mut-t21-impl-XXXXXX")`, echo it into your log, delete only that exact path): (a) overrides written before the confirmation; (b) the every-track-unresolved check counts `k < n` as allowed; (c) `_clear_hold` skipped when the gather redo returns None; (d) `[u]ntitled` offered when one track is resolved. Predicted test written to your log BEFORE each flip; caught only by the predicted or a named test; a survivor gets a test.

## Report contract
- Full report (what you changed, test commands + output lines, the mutation table `mutant -> predicted test -> caught by | SURVIVED`, deviations, concerns) to `$D/t21-impl/handback.md`, then touch `$D/t21-impl/done`. Return the same report as your final reply, but keep the reply short: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), commits, one-line test summary, concerns.
- If later resumed for a fix round R, append the fix report to the same handback.md, then touch `$D/t21-impl/done-r<R>`.
- `$D` = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to `$D/t21-impl/handback.md`, **then** touch `$D/t21-impl/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/t21-impl" && touch "$D/t21-impl/t21-impl.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/t21-impl/t21-impl.log"` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinels. Echo a progress line into the log during any long stretch of work that is not a teed command. A command that may run longer than ~4 minutes runs in the background, teed into the same log, and you poll it in chunks of at most 270 seconds (Bash `timeout` parameter 300000 ms).
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/t21-impl` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Multi-step work commits each coherent step rather than batching at the end. Commit only states where the change is wired up and the suite passes (state the test command in the commit message). **Never run `git stash` in any form** (not even `git stash list`). To set work aside, make a WIP commit. **Never `git clean -x`/`-X`.**
5. **Deliberate breakage only in a scratch copy.** Deliberate breakage (mutants and the like) only in a scratch copy (`git worktree add` or `git archive | tar -x`, or the plan's rsync recipe), run from a scratch or empty cwd, never in the live worktree.

You do not dispatch subagents. Never touch ~/.llama except reading.
