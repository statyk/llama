# Bulk apply (held-backlog pieces 1-4): SDD record

Spec `docs/superpowers/specs/2026-10-25-bulk-apply-design.md`, plan `docs/superpowers/plans/2026-10-26-bulk-apply.md`.
Built 2026-10-26/27 on branch `bulk-apply` (3a2c1352..65d13e35, 39 commits) by four successive Opus peer
orchestrators (`orch`, `orch-r1`, `orch-r2`, `orch-r3`), Sonnet/Opus implementers and Opus reviewers.

- `orch*/ledger.md`: each orchestrator's ledger (dispatches, rulings, deferred minors, HANDOFF sections).
- `checkpoints/`: Checkpoint A (backfill dry run) and A2 (after Shawn's rulings, T14b/T14c); B (marking dry run),
  the B-90 addendum (newly held, no visible change) and B2 (after the fifth trigger, T15c); C (finish report,
  release note, open minors).
- `verdicts/<task>.md`: every child's hand-back (implementers and reviewers), named by task; `final-review.md`
  is the whole-branch review, `finalfix-rereview.md` its re-review.
- `briefs/`: the task briefs the orchestrators wrote.

Parent-directed additions beyond the plan: T4b, T9b, T13b, T14b, T14c, T15b, T15c, the RF sweep, and
`CAMPAIGN_MIN_VERSION = "2.20.0"` (2.19.0 had already shipped).
