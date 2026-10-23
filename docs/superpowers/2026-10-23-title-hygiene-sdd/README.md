# Title hygiene: SDD record

Record of the subagent-driven build of "piece 3: title hygiene" (branch held-backlog-title-hygiene). Spec: docs/superpowers/specs/2026-10-22-title-hygiene-design.md. Plan: docs/superpowers/plans/2026-10-23-title-hygiene.md. Acceptance write-up (with the (d) table of added holds): docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md.

The cycle was run by four successive peer orchestrator sessions, whose parent was llama-db: orch (f6d9aa57), orch-r1 (24bca8e3), orch-r2 (3400e369) and orch-r3 (7d23a593). Each dispatched the implementer, reviewer, fix and measurement subagents named below. Review mode was Fable: the final branch review (`verdicts/final-rev.md`) was a Fable reviewer; every other reviewer was Opus, except the Checkpoint B hand-check checkers (`cpb-k01` to `cpb-k13`, `u4check`), which were Sonnet, and the spec/plan reviews, which also had a Fable seat. Implementers were Sonnet or Opus per task (see the ledgers).

Contents:

- `orch/`, `orch-r1/`, `orch-r2/`, `orch-r3/`: each orchestrator's `ledger.md`, copied byte for byte. orch-r3's ledger was still being written when this record was committed (it was copied as it stood at Task 22); the orchestrator re-syncs it at the finish, so the final ledger is the one in the finish commit, not necessarily this copy.
- `orch-r1/checkpoint-a-rulings.md`, `orch-r1/checkpoint-a.md`: the Checkpoint A packet and the operator's rulings (relayed by llama-db), including the R16 clarification.
- `orch-r2/checkpoint-b-rulings.md`, `orch-r2/checkpoint-b.md`: the Checkpoint B packet and the operator's rulings; `orch-r2/final-review-minors.md` is the final review's minor findings and their disposition.
- `verdicts/<task>.md`: the `handback.md` report of every subagent task dir under the run's `.superpowers/sdd/title-hygiene/` that has one, copied unedited: implementers (`t*`), reviewers (`*-rev`, `*-rr*`), fixes (`t6fix`, `t15b`, `fixwave`), the Checkpoint pre-screens (`prescreen`, `cpb-prescreen`), the Checkpoint B hand-check checkers (`cpb-k01` to `cpb-k13`), the acceptance runs (`accept-*`), `kg-why` (why kinggizzardandthelizardwizard-2022-10-22 gains a hold), `u4check`, `t21arms*` and the final branch review `final-rev`. Every task dir had a `handback.md`; none is missing.
- `mutation.md`: the mutation record (written earlier, left as committed).

Not committed here:

- Harness outputs (arms, compare directories, gate dumps, hand-check row files, packets) live under `~/.llama-harness/piece3/` and are not committed. The acceptance write-up names the paths and sha256 of the ones it relies on.
- The briefs, scripts, diffs and per-task logs of the run stay in the worktree's git-ignored `.superpowers/sdd/title-hygiene/`.

## Dropped from the record

Rule carried over from the piece 2 record (it cost a history rewrite there): copied or mutated source trees are never committed. This record copies no source tree at all. Size policy: only files of 256 KB or less; no file exceeded it, so none was skipped. 88 files (including `mutation.md`), 764,936 bytes, before this README was added.
