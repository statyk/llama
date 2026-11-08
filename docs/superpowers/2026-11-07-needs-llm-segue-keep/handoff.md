# Needs-LLM segue keep: handoff to the next session

Written 2026-11-07 by the adjudicator implementation session (Opus). Shawn chose this as the next job
(option 2 of three) and HELD the v2.23.0 release so it ships together with the adjudicator.

## The problem
- The campaign's **needs-LLM** class cannot be re-derived without gather's LLM touchpoints
  (`replay.legs`). It's 621 shows still awaiting fix: 332 station copies (20 voiced) and 289 library-only.
- On 2026-10-27 Shawn HELD them out of the waves because re-running `align_structure` churns segues
  both ways. The trial was 37 shows, of which 17 changed: 19 segues added, 17 dropped. One example:
  deadandcompany-2015-10-31 lost China Cat > Rider, even though a sibling description has the segue.
- Evidence: `~/.llama-harness/bulk/trial-report.txt` and `~/.llama-harness/bulk-apply/handoff-campaign.md`
  (the "Update 2026-10-27 late" section). The arm classification is `~/.llama-harness/bulk/arm-2.json`.
- The campaign handoff said "decide with the adjudicator". But the approved adjudicator spec
  (`docs/superpowers/specs/2026-11-06-adjudicator-design.md`, Non-goals) puts needs-LLM reprocessing
  OUT of scope, and the adjudicator refuses stale shows. Nothing settles them today.

## The chosen direction (Shawn, 2026-11-07: option 2)
When gather's LLM branch re-runs on a show, KEEP the segues the stored `show.json` already had for
tracks that didn't change. That was the campaign's candidate fix ("keep stored segues under the
LLM branch"). Two other options were rejected: (1) accept the churn and reprocess now, and (3) leave them held.

Sizing (told to Shawn): roughly a tenth of the adjudicator job. It's a short spec with one or two
rulings, a plan of 2-4 tasks (small enough to run without a peer orchestrator), and a measurement pass.

## Open design questions for the spec
1. **What is an "unchanged track"?** Reprocessing adds short tracks (the piece-4 short-keep rule), so
   a new track can land between the two songs of a stored segue. Decide whether the segue survives,
   moves, or drops. This ruling settles most edge cases.
2. **Donor segues** (taking a segue from a sibling recording's description, as in the China Cat case)
   is a second rung, about as large again. Scope it OUT unless the measurement shows that keeping
   stored segues isn't enough.
3. **Adds versus drops.** Does the rule keep only stored segues (blocking drops), or also block LLM-added
   segues? Segues are a LOOSE surface in Shawn's rulings ("an occasional miss is acceptable"), and the
   10-22 D1 precedent accepted segue loss on weakly aligned shows. Voiced shows: a segue change on a
   voiced show can mean a re-voice, so the 20 voiced needs-LLM shows deserve a note.
4. **Measurement cost.** Proving the fix means re-running gather's LLM step on a sample. The 10-27
   trial used 37 shows (`needs-LLM 0.21/0.22` meter points per show at the 5h window), and a sample that size is
   enough. Reprocessing all 621 is campaign work, after release.

## State of the repo
- Local `main` is at `8ce1f47e`: the adjudicator plus all its pre-release fixes. Suite 7638 passed,
  root-verified. NOT pushed, NOT tagged; origin/main is 85de0f6b. The release (v2.23.0) is
  HELD until this fix lands.
- Worktree `.claude/worktrees/adjudicator-impl` (branch `adjudicator-impl`, same commit, its own `.venv`)
  can be removed. Its git-ignored reports dir is archived in
  `docs/superpowers/2026-11-06-adjudicator-sdd/record/`. Cut this job's worktree fresh from `main`.
- The main checkout is on branch `adjudicator` with Shawn's uncommitted `scripts/listeners.py` changes.
  Leave them alone.
- After release: Shawn installs 2.23.0, and then we re-pin the `llama-waves` campaign together. Note: `llama
  reapply` never calls the adjudicator, so re-pinning doesn't start Opus calls in the campaign.

## Process
Per `~/.claude/CLAUDE.md`: brainstorm, then a spec with the review mode and a stakes paragraph, then
`spec-review`, plan, plan review, and SDD. Spec and plan on at least Opus.
