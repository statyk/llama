You are reviewing a design spec before it is turned into an implementation plan. You are a reviewer only: do not edit, create or delete any file anywhere (except the three protocol files named at the end), do not commit, and do not run anything on remote hosts. Return your review as your final text reply.

## What to review
The draft under review is: /private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45/review/spec-r1-frozen.md. Review exactly that file. Do not open any other copy of this spec (the worktree copy, docs/superpowers/specs/2026-10-23-junk-short-keep-design.md) or any git history of it.

## Context you may read (read-only)
- The code it changes: the worktree /Users/shawn/projects/llama/.claude/worktrees/junk-filter (code identical to main @ e37f670; nobody is editing it). Key modules: packages/llama/src/llama/junk.py, stages/gather.py, structure.py, titles.py, workspace.py (overrides), cli.py (fix/triage/redo/deliver/reapply), reapply.py, replay.py, catalog.py (purge), models.py.
- Project rules and invariants: the repo CLAUDE.md (read the junk-filter, overrides, fix/redo, reapply, deliver/purge and title-hygiene sections).
- Evidence: docs/superpowers/2026-10-23-junk-short-keep-evidence/ in the worktree; measurement scripts and outputs under ~/.llama-harness/piece45/spec/ and ~/.llama-harness/piece45/ (read-only).
- The library ~/.llama/shows/ may be READ (never written) to check a claim about real data.

## Stakes (read before reviewing)
About 4,000 shows; ~2,800 delivered and on air at listen.lma-radio.com; one operator whose attention is the scarce resource. Operator rule: omitting real show content is worse than including a little that does not belong; tape notes presumed correct.
- Strict surfaces -- report exhaustively: (a) the positional-overrides migration that rewrites hand-authored overrides.json (and every command that reads or writes those keys after it, including version skew between binaries); (b) re-delivering voiced shows (`deliver --replace-voiced` discards paid TTS voicing, irreversible; only the 37 approved shows may be touched); (c) relaxing the junk filter must not admit spam or non-performance audio (the filename-convention arm must stay the spam guard).
- Everywhere else -- report only defects plausible on this library and this single-operator macOS setup. A defect whose worst case is an extra hold, a recoverable `redo`, or a short spoken clip airing is Minor at most. For a rare case, propose a documented limitation rather than a new mechanism. Where the spec is over-built for these stakes, a removal is a valid finding.
## What to look for (STRICT-SURFACE review only)
Report every defect on the three strict surfaces, and nothing else. Work through this scenario checklist for each surface it applies to:
- Interrupted operation mid-way (SIGKILL / Ctrl-C during the migration, during a re-key inside fix, during a redo or deliver).
- Confirm-then-act with state changing in between (dry run, then apply after a `fix`/`triage`/`redo` changed show.json or overrides.json).
- Durability of the undo copy before the original changes; the undo path itself failing or being run twice; undo after later edits.
- Interactive vs batch parity (fix vs triage vs reapply vs redo vs the migration script).
- Two writers at once (the per-show lock; a `llama get` reusing the show; triage open in another terminal).
- Version skew: an older installed binary (v2.17.0) reading migrated keys, or a newer binary reading legacy keys -- silent drop of operator overrides is the worst case.
- Legacy shows: no show.json, partial show.json, a stale .txn/, operator-excluded rows, overrides referencing excluded or included files, duplicate filenames across discs.
- Re-voice scope: can any path re-deliver a voiced show outside the approved 37, or discard voicing without --replace-voiced?
- Filter relaxation: can any spam/promo/non-performance file reach a package by a path the spec leaves open (tags that lie, untagged files, sibling/format recovery, include/exclude interplay)?
## Output format
First line: `Foundation: SOUND | UNVERIFIED | PROBLEM -- <one sentence>`. PROBLEM means a premise the design rests on is contradicted by evidence you can cite and the design misses its goal because of it; this line is not subject to the stakes guidance on severity.

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

## Protocol (D=/private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45, task=rv-s1)
1. First action: `touch "$D/rv-s1/rv-s1.log"` (the dir exists). Echo a progress line into that log every ~10 minutes of reading.
2. When done, write your full review to `$D/rv-s1/handback.md`, THEN touch `$D/rv-s1/done`. Also return the full review as your final reply.
3. If `$D/TAKEN_OVER` or `$D/taken-over/rv-s1` exists, stop and write what you have.
4. Never `git stash`, `git clean`, or any git write.
