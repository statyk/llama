# Metronome spec review record (2026-10-14)

Spec: `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`. Review mode: Fable.

- Round 1 (draft `13b1a5e`): 4 blind reviewers on a frozen copy. Breadth: Opus (13 findings), Fable (15). Strict, spend surface: Opus (11), Fable (11). Foundation: 3 SOUND, 1 UNVERIFIED (unmeasured DO meters), 0 PROBLEM. No Critical findings.
  Triage: `decisions-r1.md`. Running list: `known-findings-r1.md`. Editor: Opus. The revision `309965c` grew the spec from 366 to 535 lines.
- Premise checks the author ran between rounds against the account, read-only: the DO datasets accept 32-day ranges; their lag is under 1 min; an empty range returns `[]`; `durableObjectsStorageGroups` returns no rows; the probe's minimum lateness is 0 ms, so there was no early delivery; hugo already alerts on a stale guard.json (`guard_stale_minutes`).
- Round 2, informed: Opus (12 findings) and Fable (13). Both SOUND, no Critical. Two circuit-breakers tripped: a self-inflicted share over 40%, and two strikes on lease handling. So there was no round 3. The lease rule was replaced by the simplest stated rule, checked against a fixed scenario list (`decisions-r2.md` R1). Revision `baa015d`: 533 lines.
- Reviewer prompts: `prompt-breadth.md`, `prompt-strict.md`, `prompt-r2.md` (their paths point at a session scratchpad copy of the frozen spec). `do-research-sonnet.md` is the delegated Sonnet web research; its quotes are extracts from a summarizing fetch.
