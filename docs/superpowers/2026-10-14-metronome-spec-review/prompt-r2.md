You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, do not deploy,
do not call any Cloudflare API, and do not run anything on remote hosts. Return your review as
your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/spec-r2.md. Review exactly that file. Do not open any
other copy of this spec (in particular not docs/superpowers/specs/2026-10-14-antenna-metronome-design.md)
or any git history.

## Already found
The issues found in the previous round, and how the spec now handles each: /private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/review/known-findings-r1.md.
Read it first. Do not report those issues again, unless the spec's current handling is itself
wrong, incomplete or introduces a new problem — then say precisely what is wrong with it.
Pay particular attention to regressions introduced by the revision, and to over-building: the spec
grew from 366 to 535 lines in one revision, so a removal or a simpler rule is a valid finding.

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
- Strict surfaces — report exhaustively: spend (PUT bounds, alarm chain bounds, the guard's
  pricing of the new meters, fail-closed behaviour, the rollback switch).
- Everywhere else — report only defects plausible on this deployment (one Worker, one DO
  instance, Cloudflare cron that fires 0-143 s late, overlapping cron invocations ~1 in 3 on bad
  days, a handful of listeners on iOS Safari / Chrome+hls.js / VLC). A defect whose worst case is
  a brief audible drop or one extra alert is Minor at most. For a rare setup, propose a documented
  limitation rather than a new mechanism. Where the spec is over-built for these stakes, a
  removal is a valid finding.

## What to look for
1. Interfaces: trace every output to its consumer (lease → DO, renew status → cron's fallback
   decision, DO alerts → channels, new meters → evaluateSpend); flag misreadings and anything
   undefined an implementer would have to invent.
2. Idioms implementers will copy that undermine the goals.
3. Safety: anything weakening the strict surface.
4. Consistency and ambiguity; claims about existing code (check them against the code).
5. Fitness for the target environment (Cloudflare Workers + Durable Objects runtime semantics).
6. Design: right approach? missing, over-built, or likely to sprawl?
7. Premises: the claims the design rests on — the diagnosis of the cause, the probe's
   measurements and what they do and do not show, how existing code behaves, what the operator
   needs. Check each against the evidence you can read.
Anything you find unclear is a finding.

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
