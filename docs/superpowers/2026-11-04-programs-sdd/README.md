# Programs and lineup SDD record

Copied from the worktree's gitignored `.superpowers/sdd/programs/` before the worktree was removed (2026-11-04).

- `run/orch/`: the first peer orchestrator (`programs-lineup`, Tasks 1-11 plus t5b): ledger with rulings R1-R12 and its HANDOFF section.
- `run/orch-r1/`: the successor (`programs-lineup-r1`, Tasks 12-14): ledger with rulings R13-R16, final carry-overs, the py3.11 gate log and final verification.
- `run/<task>/`: one directory per dispatch, each with its log, `handback.md` and sentinel files. The final whole-branch review is `t14-final-review/handback.md` (sha256 a644678eb3dd7689fd40a231e6da37665f36948f328483821281b64d26337ad5); its fix-wave re-review is `t14-rereview/handback.md` (be7d55df37cf290c099adc5d4eb7e476cbc542efe747a9e49b55713c46f6081f).

Spec `docs/superpowers/specs/2026-11-04-programs-and-lineup-design.md`. Plan `docs/superpowers/plans/2026-11-04-programs-and-lineup.md`. Go-live record `docs/superpowers/2026-11-04-programs-go-live.md`.
