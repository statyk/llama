You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, do not run
llama or any command that writes, and do not run anything on remote hosts. Read-only shell
commands (grep, sed -n, cat, git show/log on main) and read-only Python that imports the
repo's code from /Users/shawn/projects/llama/.venv/bin/python are fine. Return your review as
your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/09655149-3733-4f18-90cf-0f06e280493e/scratchpad/review/spec-r1.md. Review exactly that file. Do not open any other copy
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
## What to look for — strict surfaces only
Report every defect on the four strict surfaces, and nothing else. Work through these
scenarios against the spec and the real code:
- A real song title, or prose, read as one of the new marker forms (`I`, `II`, `1:`, `E.`,
  `S1`, `[1]`, `(E)Song`, a trailing `enc`, `Disc 2 - Set 2`, set labels in track tags), on a
  show that then clears or changes shape. Include titles like "J", "Untitled #12", "E.M.D.",
  "I Know You Rider", "II B.S.", "1:00 AM", numbered tracklists.
- A taper boundary "placed" when the tape does not really pin it (merged tracks, repeated
  songs, a reprise, a song in both sets, tautological title sources, a partial tape, an
  encore song played earlier in the show), and the show clears.
- The merge of taper-owned and fallback parts producing a structure nobody asserted.
- A flag suppressed (jerrybase set count, closer tripwire, low-confidence alignment, guard
  checks) on a show where the suppressed flag was the only thing catching a real error.
- The stored-`llm` relaxation in replay/reapply: a show reapplied offline whose shipped output
  still depends on the stored LLM alignment or on anything the replay cannot reproduce; the
  harness and reapply disagreeing; the Tier 1 needs-LLM pin.
- A shipped show whose structure changes but does not appear in the report the spec promises
  (including shows with operator overrides, stored-llm shows, shows the harness skips).
- The parser change altering canonical items, set labels or `corroboration` inputs that other
  rungs read (setlist-gap, accept_short_tags, sibling-align, suggest-titles, vet/brief
  matchers), shifting titles silently.
- Interaction with `llama fix`/`redo`/`triage`/`reapply` and operator overrides; a stale
  briefing shipping with new structure.
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
