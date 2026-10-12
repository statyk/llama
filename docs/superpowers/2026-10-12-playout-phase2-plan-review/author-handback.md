# Phase 2 plan: handback

Plan: /Users/shawn/projects/llama/docs/superpowers/plans/2026-10-11-playout-phase2.md (7,517 lines, not committed).
Code and tests are copied from a scratch build that passed: antenna 132 tests (tsc clean), transmitter 357 tests on 3.14 and 3.11; Task 1's in-between state and Task 19's variant were run separately.

## Tasks and model hints
| Tasks | What | Model |
|---|---|---|
| T0 | worktree, .venv/.venv311, npm ci | sonnet |
| T1 | storage seam, test support, billing period | sonnet |
| T2–T8 | **spend/blocking path**: pricing, GraphQL meter, latch, WAF kill switch, guardStep, index.html pages, clock wiring | opus |
| T8 end | review gate: report to parent before T9 | — |
| T9, T10 | cloud alerts; deploy script with pinned send_email | sonnet |
| T11, T12 | discontinuity numbering, antenna and transmitter (A1) | opus |
| T13 | player detects kill switch mid-play (A2) | sonnet |
| T14 | `offair` / `budget` commands | opus |
| T15–T18 | hugo alerts, dead-clock monitor, systemd unit + watchdog, status | sonnet |
| T19 | **conditional** lookahead (A4); starts with a **HUMAN CHECKPOINT** | opus |
| T20 | runbook + phase-2 checklist; **HUMAN CHECKPOINT** where the operator deploys and verifies | sonnet |
| T21 | CLAUDE.md + spec notes for the approved amendments | sonnet |

## Proposed spec amendments (in the plan header, for the operator to approve)
- **A1:** `horizon.json` gains an integer `disc`, which keeps the discontinuity sequence from ever going down (fixes the VLC hang). I tested the algorithm by simulation. A version computed from the segment number alone is impossible; the plan explains why. Deploy order: transmitter first, then antenna.
- **A2:** the player probes the playlist after 15 s of stalled playback; two 403-or-ENDLIST answers in a row show the off-air notice.
- **A3:** the deploy script generates a git-ignored config that pins `send_email` to the address in `.env`.
- **A4:** the lookahead is conditional: it ships only if more than 5 cron fires in the 24 h capture lag over 25 s.
- **A5:** free-plan facts. The guard creates no rules; the kill switch is found by its description; analytics reads leave 5 minutes for GraphQL lag.

## Open questions for the operator
1. Approve or reject A1–A5 and rulings R1–R17. Most worth a look: R2 (unreadable state: write nothing that minute), R3 (when a raise clears a spend trip), R5 ($100 cap on `--raise-to`), R12 (anniversary day as a Worker secret), R13 (extra alert types), R15 (unit runs as your user, 45-min watchdog).
2. The 24 h cron-lag summary, which decides whether Task 19 runs.
3. The alert sender `ALERT_EMAIL_FROM` must be an address on the zone's domain; please confirm which.
4. Lead-floor alert at 16 h, dead-clock alert at 120 s twice in a row, repeats every 6 h: OK?

## Unconfirmed in docs; the T20 checklist verifies them live
- R2 GraphQL `actionType` strings (unknown ones priced as Class A and listed in `guard.json`); whether a Rulesets PATCH needs the whole rule (the plan resends it); the WAF token permission (planned Zone · WAF · Edit); `EmailMessage` with a hand-built MIME message (docs use `mimetext`).
- The billing API could supply the anniversary day; rejected because it needs a billing-read token.
