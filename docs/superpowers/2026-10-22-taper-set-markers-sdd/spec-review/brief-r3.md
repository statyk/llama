You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, do not run
llama or any command that writes, and do not run anything on remote hosts. Read-only shell
commands (grep, sed -n, cat, git show/log on main) and read-only Python that imports the
repo's code from /Users/shawn/projects/llama/.venv/bin/python are fine. Return your review as
your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/spec-r3.md. Review exactly that file. Do not open any other copy
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

## What to look for — scenario check of a simplified rule
Earlier review rounds drove a redesign: the spec now uses a whole-structure rule (the taper
owns the whole structure or nothing; worded markers only). Do NOT do a general review. Work
through every scenario in /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/scenarios-r3.md against the spec and the real code, and for
each one state: what the spec says happens (cite the section), whether that outcome is safe
(today's behaviour, or exactly the taper's own written structure; never a structure nobody
asserted; never a newly cleared wrong show), and whether the spec leaves the outcome
undefined. Then add any scenario of the same kind you find where the simplified rule ships a
wrong structure or clears a wrong hold. Check claims against the code and, where cheap, real
cached descriptions (~/.llama/cache/md_*.json) and library shows (~/.llama/shows/).

## Output format
First line: `Foundation: SOUND | UNVERIFIED | PROBLEM — <one sentence>`.
Then one line per scenario: `<n>. SAFE | UNSAFE | UNDEFINED — <outcome, section cited>`.
Then findings for every UNSAFE/UNDEFINED and every added scenario, most severe first, in this form:
- **[Critical|Important|Minor] Short title** / Where / Problem / Evidence / Failure scenario / Suggested fix (one sentence)
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
