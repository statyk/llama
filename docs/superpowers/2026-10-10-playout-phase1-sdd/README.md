# Playout phase 1: SDD record

This is the subagent-driven-development record for `docs/superpowers/plans/2026-10-10-playout-phase1.md` (19 tasks). It was copied out of the build worktree's gitignored `.superpowers/sdd/` before that worktree was removed. The branch was merged to `main` at `43a6b41`.

- **`run/`** holds one directory per dispatch:
  - `taskN-impl`, `-rev`, `-fix`, `-rerev`;
  - `final-review` (Fable), and `final-fix1`/`final-fix2` with `final-rerev1`/`final-rerev2` (Opus);
  - each one's `handback.md`, plus logs and `done`/`dispatched` sentinels.
  - The orchestrator ledgers are in `orch/`, `orch-r1/` and `orch-r2/`. The build relayed twice, at Task 9 and at Task 17.
  - The verdicts the merge was ratified on have these SHA-256 hashes:
    - `final-review/handback.md`: `79bd2801…`
    - `final-rerev2/handback.md`: `69e75994…`
- **`constraints.md`** and **`final-review-deferred.md`** are the run's standing constraints and the deferred minor findings.
- **`spike-out/`** is the container spike's page and metadata. Its audio is omitted, because audio is never committed.
- **The per-review diffs are omitted.** Every reviewed range is a pair of commits on the merged branch, so `git diff <a>..<b>` regenerates any of them.

Results from running it on the live station are in `../2026-10-11-playout-phase1-verification.md`.
