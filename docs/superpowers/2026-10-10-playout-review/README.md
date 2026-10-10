# Playout spec + plan review record (2026-10-09/10)

Provenance for `docs/superpowers/specs/2026-10-09-playout-design.md` and
`docs/superpowers/plans/2026-10-10-playout-phase1.md`. Review mode: Fable.

- `platform-research.md` — sourced Cloudflare/R2/Oracle/AzuraCast/Liquidsoap/HLS facts (Sonnet research, 2026-10-09).
- `feasibility-sim.py` — the schedule-feasibility simulation behind the spec's table (NOTE: it counts all delivered packages, voiced or not; only 129 were ready).
- `known-findings-r1.md` — spec round 1 (4 reviewers: Opus+Fable breadth, Opus+Fable strict-spend) findings and how the spec handles each. Two strict reviewers returned Foundation: PROBLEM (Workers run before the cache, so cached Worker responses are billed; no spend cap) — the operator approved the static-listener-path redesign.
- `decisions-r1.md`, `decisions-r2.md` — spec revision decision lists applied by an Opus editor. Round 2 hit the two-strike rule on the guard (replaced by the two-flag latch model, checked against 8 scenarios) and the >50% spec-growth breaker (396→595 lines), so no round 3.
- `plan-decisions-r1.md` — plan review (Opus + Fable, both READY WITH FIXES; both executed the plan's code in scratch trees) decisions applied by an Opus editor (192 transmitter + 20 antenna tests passing in scratch, mutation-checked).
