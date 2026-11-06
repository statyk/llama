# Adjudicator: handoff to the implementation session

Written 2026-11-06 by the spec/plan session (Opus). Start implementation **after the Nov 7 06:00
weekly reset** (weekly meter was 92% at hand-off).

## What exists
- Spec (approved by Shawn 2026-11-06): `docs/superpowers/specs/2026-11-06-adjudicator-design.md`
  (commit `9174f72b`). Review mode: **Opus**. Two Opus spec-review rounds (2 breadth + 2 strict, then 2
  informed), then a simplification pass on the circuit-breaker (evidence-check mechanism drew findings
  two rounds running; spec growth >50%). Decision lists in `review/decisions-r1.md`, `decisions-r2.md`.
- Plan (approved by Shawn 2026-11-06): `docs/superpowers/plans/2026-11-06-adjudicator.md` (commit
  `1bfedd0c`), 11 tasks. Two blind Opus plan reviews applied (`review/plan-decisions-r1.md`); no second
  plan round (no finding reshaped tasks).
- Branch `adjudicator` (main checkout is on it; only the two docs commits above `main` @ `6b558cb7`).
  Not pushed. Suite on the branch: 6905 passed, 1 skipped (`./.venv/bin/pytest -q`, 2026-11-06).

## Execution (Shawn chose subagent-driven)
- Per `~/.claude/CLAUDE.md`: launch a **peer orchestrator on Opus** (`sdd-delegation` skill,
  `parent.md`), fallback `sdd-orchestrator` subagent. Worktree `.claude/worktrees/adjudicator-impl`
  cut from `adjudicator`, with its **own `.venv`** (repo CLAUDE.md: root venv imports the main
  checkout). Arm the keepalive tick; peer reports at task boundaries with the meter and every dispatch's
  model listed.
- Implementer models per the plan's task list (Sonnet for 1, 2, 3, 8, 10, 11; Opus for 4, 5, 6, 7, 9);
  spec-compliance and code-quality reviewers on Opus; final branch reviewer Opus (review mode Opus).
- **Checkpoint A** (after Task 7, core done): operator boundary report before CLI wiring.
- **Checkpoint B** (after Task 11): the pilot (`scripts/adjudicate_pilot.py`, 30 held shows, Opus vs
  Sonnet, exact model pins) runs from the worktree against `~/.llama` **only on Shawn's go** — it
  performs trial applies (apply then restore). Then the acceptance bar (zero wrong auto-applied >60 s
  track-list edits, title fills/replacements, structure edits or switches; Shawn spot-checks the
  strict-surface ones, expected under a dozen), Shawn's model decision, any propose-only demotions — all
  before merge/release/install. Implementers never run the pilot.
- Never push/merge/tag/release without Shawn. The feature is default-on once installed, so nothing is
  installed before Checkpoint B passes.

## Open sign-offs for Shawn (raise at Checkpoint A or B, not blocking)
1. `run approve` also triggers adjudication (beyond the spec's get / redo / run resume list).
2. The long-track evidence rule is stricter than the spec: the quote must contain the filename stem as
   a whole token; a bare track number never counts.
3. Author's calls in the spec Shawn may retune after the pilot: 60 s short/long line, 120 s cumulative
   cap, sibling duration match max(2 s, 1 %), recording-switch bar, structure edits need taper-side
   markers, city edits and catch-all `other` research flags always propose-only.

## Context the implementation session will want
- Shawn's class rulings are in the spec ("Operator class rulings") and in memory
  `llama-adjudicator.md`.
- Measured premise: of 347 held shows, 316 already had 2026-10-21 prototype verdicts and 254 were
  escalated; the class rulings, not re-judging, are what make the backlog sweep reach "dozens".
- The 2026-11-06 library waves (`~/.llama-harness/bulk/library-waves/`) stopped after L02 (49/50;
  `furthur-2010-07-05` hit an archive.org HTTP 500). L03-L07 are not run yet; that is a separate thread
  from this feature and shares the meter.
- Prototype being ported: `~/.llama-harness/t3/` (`adjudicator-brief-v2.md`, `tools/build_bundles.py`,
  `tools/daemon.py`).
