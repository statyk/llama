You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, do not deploy,
do not call any Cloudflare API, and do not run anything on remote hosts. Return your review as
your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/spec-r1.md. Review exactly that file. Do not open any
other copy of this spec (in particular not docs/superpowers/specs/2026-10-14-antenna-metronome-design.md)
or any git history.

## Context you may read (read-only)
- The code it changes: /Users/shawn/projects/llama/antenna/ (src/*.ts, test/*.ts, wrangler.jsonc).
  clock.ts (runClock), playlist.ts, guard.ts, latch.ts, meter.ts, pricing.ts, alerts.ts, index.ts matter most.
- The design it builds on: /Users/shawn/projects/llama/docs/superpowers/specs/2026-10-09-playout-design.md
  (sections "antenna", "Spend budget", "Cost guard", "Alerts and operations").
- Project conventions: /Users/shawn/projects/llama/CLAUDE.md (the antenna and transmitter paragraphs).
- The throwaway probe the measurements came from: /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/probe-src/index.ts.
- Delegated web research on Durable Object pricing/semantics (Sonnet; quotes are extracts from a
  summarizing fetch, not verbatim): /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/do-facts.md. Treat its claims as unverified unless
  the spec states it measured them.

## Stakes (read before reviewing)
What is at risk is money and on-air continuity, not data. Nothing here touches the station
root or llama/emcee state; antenna writes only its own R2 bucket and its own Durable Object
storage. A single operator runs a non-commercial internet radio station; the budget is $15/month
including the $5 Workers Paid base, and the station shuts down on overrun.
Strict surface: SPEND. Cloudflare has no spending cap. The design adds a new billed product
(Durable Objects) and a new writer of a billed R2 object. A runaway alarm chain, an unpriced
meter, a PUT bound that trusts its inputs, or anything that lets the station keep spending when
the cost guard cannot see it, is an uncapped bill. Fail-closed must survive: an unknown verdict
is never treated as unblocked.
The goal is continuity: no playlist freeze over ~45 s (iOS drops audio at ~60-75 s of playlist
staleness, measured).
- Report ONLY defects on the strict surface (spend, including fail-closed), exhaustively.
  Ignore continuity-only, style, and documentation issues unless they create a spend defect.

## What to look for (strict surface: spend and fail-closed)
Work through each scenario below against the spec AND the existing code, and report every
defect you find on the spend surface:
1. A runaway: any path where the alarm chain re-arms faster than once per boundary, re-arms
   forever without cron, or PUTs more than the stated bounds (bugs in inputs: a lease with a huge
   validUntil, a horizon with a strange epoch or d, a clock that jumps, a duplicate/retried alarm,
   an exception at every step of alarm()).
2. Two writers at once: DO + cron fallback, DO + a stale DO instance across a deploy, two cron
   invocations renewing concurrently; what bounds total Class A per minute in each case.
3. Out-of-order or interleaved operations: leases arriving out of order; renew() interleaving
   with alarm() at an await point inside the DO (input/output gates); a blocked lease followed by
   an older unblocked one; hold vs play ties.
4. Interrupted operations: DO evicted/restarted mid-alarm, storage write failing after the PUT,
   a deploy while an alarm is pending, the RPC timing out after the DO already applied the lease.
5. The cost guard: can any DO meter go unpriced, priced at zero, or lag so that a runaway is
   invisible for longer than the guard's existing tolerances? Is a missing/partial dataset a failed
   reading? Do the new meters' allowances and units match the evidence?
6. Fail-closed: every path where the station could keep writing (or keep the DO billing) while the
   guard's verdict is unknown, tripped, or cron is dead; the 15-minute lease's exact bound; the
   rollback switch (METRONOME=off) when stop() fails.
7. The rollback/undo path itself failing: teardown of the DO class, the probe teardown, deploy
   ordering.
8. Premises on the strict surface: is anything the design's spend safety depends on unmeasured?

## Output format
First line: `Foundation: SOUND | UNVERIFIED | PROBLEM — <one sentence>`. PROBLEM means a premise
the design rests on is contradicted by evidence you can cite and the design misses its goal
because of it; this line is not subject to the stakes guidance on severity.

Then findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: section heading plus a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, or the conflicting quote
  - Failure scenario: concrete inputs or situation, and what goes wrong
  - Setup and likelihood: the setup it needs and how likely it is
  - Suggested fix: one sentence, and roughly what it adds or removes
Then `### Unverified premises`: each claim the design depends on that the evidence here cannot
confirm, with the cheapest test that would settle it (or `none`).
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
