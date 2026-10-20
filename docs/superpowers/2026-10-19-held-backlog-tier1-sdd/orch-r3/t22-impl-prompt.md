You are the implementer for Task 22 of the held-backlog Tier 1 run (llama repo): the docs task — CLAUDE.md and README.md for the Tier 1 guards, the replay harness, `llama reapply` and `fix --untitled`. Docs only; no code change. Model: Sonnet.

## Read first
1. Common rules (binding): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r3/common.md — the commit trailer and hard limits apply; the test rules apply only as "full suite still green".
2. Your brief — your requirements: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-22-brief.md
3. Spec (binding authority) for what each guard does: docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md. The plan's "Recorded at Checkpoint B/C/D/E/F" blocks in docs/superpowers/plans/2026-10-19-held-backlog-tier1.md record what the operator changed at each checkpoint — the docs must describe the SHIPPED behaviour, i.e. the spec as amended by those blocks. In particular: **5c.2 (numbered-set anchoring when only the encore closer is missing) was DROPPED at Checkpoint F** — do not document it; 5c is 5c.1 (filler-tail closers become an operator note) + 5c.3 (leading-parenthetical fold as a fallback tier). Checkpoint C narrowed slice 1 (V + S); Checkpoint E added the day-00 rule (Task 16b) and kept RIGHT_SHOW_MIN_TAPE_FRACTION at 0.5.
4. The code itself is the final word on names, flags and messages: read `scripts/replay_holds.py` (`run`/`compare`, their flags and output files), `packages/llama/src/llama/reapply.py` and the `reapply`/`fix`/`triage` commands in `packages/llama/src/llama/cli.py` before describing them. Get every flag and file name from the code, never from memory.

## What to write
- CLAUDE.md, in the existing style (dense, factual, measured; bold for load-bearing rules; it is read by future agents): under Commands — `llama reapply <show>...` and `--from-list <list> [--dry-run]` (what it reads, the per-show lock, show.json last, the batch dir `<root>/reapply/<hash>/` and resumability, the pacing gate and stop rules, the sha/config + `-dirty` refusal, llm-failures capture, never delivers — prints `re-deliver with: llama deliver` on a delivered show that cleared); `fix --untitled` / triage `[u]` with eotoband-2007-10-09's route as the brief names it; `scripts/replay_holds.py run|compare` (read-only, `~/.llama-harness`-style `--out`, the list files compare writes and what `predicted_list.json` is tied to); `notes.json` (operator notes; never reach the LLM). Under Architecture: ONE paragraph on the Tier 1 guards, one sentence per slice item as the brief says (1a–1d, 2a–2c, 3a–3c, 4a–4c, 5a, 5c.1, 5c.3), each naming its predicate and the spec. Keep the do-not-retune style: name any new constant the spec fixed.
- README.md: operator-facing — the harness, `reapply` (dry run first; the pilot/waves procedure in one short paragraph), `--untitled`.
- Do not rewrite unrelated sections. Do not touch any file other than CLAUDE.md and README.md.

## Context
- Worktree / cwd: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, branch held-backlog-tier1. BASE = HEAD when you start.
- Run `./.venv/bin/python -m pytest -q` once after editing (no code changed, so it must match the BASE count) and state the result in the commit message. One commit: `docs: Tier 1 held-backlog guards, replay harness, reapply, --untitled`.

## Report contract
Full report (what you wrote where, the facts you took from code and from which file/function, the test result) to `$D/t22-impl/handback.md`, then touch `$D/t22-impl/done`. Return the same report as your final reply, kept short: status, commit, concerns. If later resumed for a fix round R, append to the same handback.md, then touch `$D/t22-impl/done-r<R>`. `$D` = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1

## Mandates (verbatim, binding)
1. **Report, then sentinel.** Write the full report to `$D/t22-impl/handback.md`, **then** touch `$D/t22-impl/done`. Sentinel last: its existence must guarantee the report is complete. A report file without a sentinel is usable evidence but not a completion claim — treat it as partial. Also return the full report as your final reply: the file is the manager's mid-turn copy, not a substitute for the text.
2. **Open your log first, then tee into it.** `mkdir -p "$D/t22-impl" && touch "$D/t22-impl/t22-impl.log"` as your **first action**, before any work, then `cmd 2>&1 | tee -a "$D/t22-impl/t22-impl.log"` for every long-running command. Nothing else may be written to this directory except handback.md and the sentinels. Echo a progress line into the log during any long stretch of work that is not a teed command.
3. **Check `$D/TAKEN_OVER` and `$D/taken-over/t22-impl` before each commit or write batch.** If either exists, stop immediately and write a final report of where you stopped.
4. **Commit incrementally.** Commit only coherent states (state the test command in the commit message). **Never run `git stash` in any form.** **Never `git clean -x`/`-X`.**
5. **Deliberate breakage only in a scratch copy** (not expected for this task).

You do not dispatch subagents. Never touch ~/.llama.
