You are reviewing a design spec before it is turned into an implementation plan. You are a reviewer only: do not edit, create or delete any file anywhere, do not commit, and do not run anything on remote hosts. Return your review as your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/a95b18a2-b25c-4e0c-98eb-cde44eaf5953/scratchpad/specreview/r2-frozen.md. Review exactly that file. Do not open any other copy of this spec (in particular not the one under docs/superpowers/specs/2026-10-25-*) or any git history.

## Already found
The issues found in an earlier round, and how the spec now handles each: /private/tmp/claude-501/-Users-shawn-projects-llama/a95b18a2-b25c-4e0c-98eb-cde44eaf5953/scratchpad/specreview/known-r1.md. Read it first. Do not report those issues again, unless the spec's current handling is itself wrong, incomplete or introduces a new problem — then say precisely what is wrong with it. Pay particular attention to the new text (the frontier, the gap layout, exact timing, announcements' next/later templates, the bend rule, interstitial re-validation and timeline handling, aired.jsonl gating, the clock read per step).

## Context you may read (read-only)
- The code it changes: /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/src/transmitter/ (planner.py, pipeline.py, layout.py, station.py, site.py, service.py, config.py, analysis.py, render.py, publish.py, state.py, workspace.py, grid.py) and its tests in /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/tests_transmitter/.
- The player's timeline reader: /Users/shawn/projects/llama/.claude/worktrees/scheduler/antenna/public/nowplaying.js and player.js.
- The design it builds on: /Users/shawn/projects/llama/.claude/worktrees/scheduler/docs/superpowers/specs/2026-10-09-playout-design.md (the umbrella; phase 3 = "Scheduler (phase 3)").
- Project conventions: /Users/shawn/projects/llama/.claude/worktrees/scheduler/CLAUDE.md (long; the transmitter and antenna paragraphs are the relevant parts).
- The umbrella's naive-filler simulation: /Users/shawn/projects/llama/.claude/worktrees/scheduler/docs/superpowers/2026-10-10-playout-review/feasibility-sim.py.
- emcee's scan (to check the interstitials-folder claim): /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/emcee/src/emcee/station.py; llama's deliver lives under /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/llama/src/llama/.

## Stakes (read before reviewing)
The risk is on-air continuity and the listening experience, not money or data. The scheduler only chooses what plays and when; it adds no R2 writes beyond phase 1's (segment count is fixed by wall-clock time; timeline.json still written once per publish batch). It reads the station root and a new interstitials folder and writes only transmitter's own workspace.
- Strict surfaces (irreversible once wrong): (1) the frozen prefix -- a rendered segment may already be published, published keys are immutable and cached for a year, so a plan row whose audio is rendered must never change; (2) never cut a show mid-song and never leave silence; (3) never list a segment that does not exist (owned by render/publish; the scheduler must not hand them an unrenderable plan).
- Common setup: one transmitter service on hugo (Debian 12, Python 3.11) reading a station root of a few hundred to a few thousand packages over NFS; ~24 h lead; the operator edits the clock occasionally (weekly-ish) and re-voices or pulls a show rarely. A defect whose worst case is a badly chosen show, a block starting late, a dropped announcement or a status line that misleads is Minor at most -- the next re-plan corrects it within one lead. For a rare setup, propose a documented limitation rather than a new mechanism. Where the spec is over-built for these stakes, a removal is a valid finding.

## What to look for
1. Interfaces: trace every output to its consumer; flag misreadings and anything undefined an implementer would have to invent.
2. Idioms implementers will copy that undermine the goals.
3. Safety: anything weakening the strict surfaces.
4. Consistency and ambiguity; claims about existing code (check them against the code).
5. Fitness for the target environment.
6. Design: right approach? missing, over-built, or likely to sprawl?
7. Premises: the claims the design rests on — the diagnosis of the cause, the environment, scale and where the bottleneck is, how existing code behaves, what the requester needs. Check each against the evidence you can read.
Anything you find unclear is a finding.

## Output format
First line: `Foundation: SOUND | UNVERIFIED | PROBLEM — <one sentence>`. PROBLEM means a premise the design rests on is contradicted by evidence you can cite and the design misses its goal because of it; this line is not subject to the stakes guidance on severity.

Then findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: section heading plus a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, or the conflicting quote
  - Failure scenario: concrete inputs or situation, and what goes wrong
  - Setup and likelihood: the setup it needs and how likely it is
  - Suggested fix: one sentence, and roughly what it adds or removes
Then `### Unverified premises`: each claim the design depends on that the evidence here cannot confirm, with the cheapest test that would settle it (or `none`).
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
