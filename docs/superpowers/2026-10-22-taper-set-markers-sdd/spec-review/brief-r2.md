You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, do not run
llama or any command that writes, and do not run anything on remote hosts. Read-only shell
commands (grep, sed -n, cat, git show/log on main) and read-only Python that imports the
repo's code from /Users/shawn/projects/llama/.venv/bin/python are fine. Return your review as
your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/spec-r2.md. Review exactly that file. Do not open any other copy
of this spec (in particular not docs/superpowers/specs/2026-10-22-taper-set-markers-design.md
in the repo) or its git history.

## Context you may read (read-only)
- The code it changes, at /Users/shawn/projects/llama (branch checked out has only doc changes
  on top of main @ a26c4d1): packages/llama/src/llama/setlist.py, structure.py, jerrybase.py,
  stages/gather.py, titles.py, replay.py, reapply.py, models.py; scripts/replay_holds.py.
- Project conventions and invariants: /Users/shawn/projects/llama/CLAUDE.md.
- The evidence: docs/superpowers/2026-10-22-taper-set-markers-evidence/ (classified.jsonl,
  sort1.json), docs/superpowers/2026-10-21-held-backlog-adjudication/; the verdicts and
  evidence bundles in ~/.llama-harness/t3/verdicts/ and ~/.llama-harness/t3/bundles/;
  cached archive.org item metadata in ~/.llama/cache/md_<identifier>.json; the show library
  ~/.llama/shows/<slug>/ (show.json, overrides.json, notes.json).
- The previous piece's spec for style and precedent:
  docs/superpowers/specs/2026-10-21-held-backlog-small-fixes-design.md.

## Stakes (read before reviewing)
llama feeds an automated radio station. Set structure reaches air twice: the briefing (and
from it emcee's DJ script) says what opened the second set and what the encore was, and the
manifest's set labels group the tracks. A wrong break is spoken as fact. The operator's
standing rule: the archive description is ground truth unless clearly contradicted; repeat
the tape's error rather than mis-correct the tape. The operator's attention is the scarce
resource.
- Strict surfaces — report exhaustively: (1) a hold this change clears, since a cleared show
  ships with no human look; (2) silent changes to the structure of shows that already shipped
  (packaged, delivered, voiced); (3) the relaxation of the needs-LLM rule in replay.py, which
  reapply shares; (4) any change to titles or other rungs' inputs caused by the parser change.
- Everywhere else — report only defects plausible on this library (about 3,800 shows, LMA
  tapes, heavy Grateful Dead family, many jam bands). A defect whose worst case is a show
  staying held as it is today is Minor at most. For a rare case, propose a documented
  limitation rather than a new mechanism. Where the spec is over-built for these stakes, a
  removal is a valid finding.

## Already found
The issues found in round 1 (four reviews), and how the spec now handles each: /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/known-findings-r1.md.
Read it first. Do not report those issues again, unless the spec's current handling is itself
wrong, incomplete or introduces a new problem — then say precisely what is wrong with it.
## What to look for
1. Interfaces: trace every output to its consumer; flag misreadings and anything undefined
   an implementer would have to invent.
2. Idioms implementers will copy that undermine the goals.
3. Safety: anything weakening the strict surfaces.
4. Consistency and ambiguity; claims about existing code (check them against the code).
5. Fitness for the target environment.
6. Design: right approach? missing, over-built, or likely to sprawl?
7. Premises: the claims the design rests on — the diagnosis of the cause, the environment,
   scale and where the bottleneck is, how existing code behaves, what the requester needs.
   Check each against the evidence you can read.
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
