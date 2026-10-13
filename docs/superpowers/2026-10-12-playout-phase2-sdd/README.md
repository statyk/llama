# Playout phase 2: SDD record

This is the subagent-driven-development record for
`docs/superpowers/plans/2026-10-11-playout-phase2.md`. It was copied out of the
build worktrees' gitignored `.superpowers/sdd/` before they were removed. The
branches were merged to `main` at `0834d08` (Tasks 0–17 plus the final wave) and
`9fe7d32` (the amended Task 18).

- **`run/`** holds one directory per dispatch:
  - `tN-impl`, `-rev-spec`, `-rev-qual`, `-rerevN`;
  - `final-review` (Fable), with `final-fix` and `final-rerev` (Opus);
  - each one's `handback.md`, plus logs and `done`/`dispatched` sentinels.
  - The orchestrator ledgers are in `orch/`, `orch-r1/` and `orch-r2/`. Each holds a
    `ledger.md` with every `Ruling:` line and a `HANDOFF` or `FINAL` section, plus
    `pkg/`, the task briefs and shared reviewer/implementer instructions. The build
    relayed twice: at the review gate after Task 8, and after Task 14.
  - `orch/gate8-report.md` is the Task 8 gate report the parent ratified.
- **`t18/`** is the amended Task 18 (playlist hold-back plus lookahead):
  - `brief.md` and `fix1-brief.md`;
  - the implementer, spec and quality reviews;
  - the fix round and its re-review.

  The parent session ran it inline, after the iPhone measurements recorded in the
  plan's amendment A4.
- **`t19/`** is the phase-2 wrap: Task 19's docs and the F9 offair-parse fix. It holds
  the brief, the implementer's handback and the Opus review. It was merged at `8a2e4e9`.
- **The verdicts the merges were ratified on** have these SHA-256 hashes:

  | Verdict | SHA-256 |
  |---|---|
  | `run/final-review/handback.md` | `79e05969…` |
  | `run/final-rerev/handback.md` | `cc1b7208…` |
  | `t18/t18-rev-spec/handback.md` | `2bd28de1…` |
  | `t18/t18-rev-qual/handback.md` | `dcc1d0b7…` |
  | `t18/t18-rerev1/handback.md` | `af9687da…` |

- **The per-review diffs are omitted.** Every reviewed range is a pair of commits
  on the merged branches, so `git diff <a>..<b>` regenerates any of them.

The plan review record is `../2026-10-12-playout-phase2-plan-review/`. The phase-1
cron-lag measurements that drove Task 18 are in
`../2026-10-11-playout-phase1-verification.md`.
