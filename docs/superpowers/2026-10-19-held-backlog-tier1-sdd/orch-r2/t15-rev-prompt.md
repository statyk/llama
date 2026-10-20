You are reviewing one task's implementation: first whether it matches its
requirements, then whether it is well-built. This is a task-scoped gate,
not a merge review — a broad whole-branch review happens separately after
all tasks are complete.

## What Was Requested

Read the task brief: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/task-15-brief.md

Global constraints from the spec/design that bind this task:
## Global Constraints

- **Do-not-retune constants stay byte-identical** (spec "Stakes"): `is_real_title`, `title_fraction`, `_TRACK_NUM_PREFIX`, `songs.normalize_song`, `DEFAULT_ALIASES`, `GD_SHORTHAND`'s family gate, `gather._RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, the tail-guard constants, the junk-duration constants, `align_coverage_threshold`, `_ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`, `structure._STRUCTURE_PREFIX`, `_FOOTNOTE_TAIL`. Every task's code-quality review greps the diff for them.
- **Narrow beside, never loosen in place** (ruling 2): a slice that needs more than a protected predicate gives adds a new predicate next to it with its own name and its own tests.
- **Corroboration is cross-source** (ruling 3): the parse vocabulary used by 2a and 2b excludes the selected recording's own description (`SourcedParse.source == "chosen"`) and every sibling parse whose whitespace-normalised description equals it (a pasted copy has the same author), and is built in exactly one place (`build_canonical`, Task 8).
- **Notes never reach the LLM** (ruling 6): every note added by this plan is appended to `GatherResult.notes` / `VetOutcome.notes` and lands in `notes.json`. Nothing new is appended to `StructureInfo.conflicts`, `Show.review_flags` (other than the flags the spec names), or `VettingResult`.
- **A real tag, a `sibling-format` title or an `override` is never overwritten** by any automatic pass. 2b may demote a `tags`/`sibling-format` placeholder to `unresolved` (title = filename) and never to other text. Only Task 21 (operator-confirmed) writes `overrides.json`.
- **Nothing here rewrites a package or a delivered show silently** (ruling 4). The harness reports; `reapply` changes only shows that are held, under the per-show lock, with `show.json` written last.
- **Tier 1 is LLM-free by scope** (ruling 5): the needs-LLM verdict is computed by `llama.replay.compute_legs` and turned into an outcome by `llama.replay.classify`, both used by the harness and `reapply` (which maps `classify`'s outcome). No other code decides it.
- New constants are fixed a priori (spec "New constants") and named in code with a comment citing the spec section; none is retuned after a harness run except `RIGHT_SHOW_MIN_TAPE_FRACTION` at Checkpoint E, before 4a ships.
- Message and note texts are verbatim from the "Contracts" section below; `compare` parses them.
- Tests are offline and deterministic; never commit audio; fixtures are captured real items slimmed by `capture_fixture.py`.
- Each task ends with the full suite green: `./.venv/bin/python -m pytest -q` from the worktree root.
- Commits: one per task as shown; end each commit message with the attribution trailer the orchestrating session specifies.
- **Mutation step** (spec "Testing"; required on every task that touches a strict predicate: Tasks 4, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19). After the full suite is green and before the commit, flip each mutant the task lists, one at a time, by this recipe:
  1. Write down the predicted red test (file::name) for the mutant BEFORE flipping it.
  2. Fresh copy per mutant, outside the worktree (`W` = the worktree root): `M=$(mktemp -d "$TMPDIR/mut-XXXX"); rsync -a --exclude .venv --exclude .git "$W/" "$M/tree/"`; apply the mutant in `$M/tree` only.
  3. Run with the worktree's interpreter, the copy shadowing the editable install, and a bytecode cache private to this mutant: `cd "$M/tree" && PYTHONPATH="$M/tree/packages/llama/src:$M/tree/packages/herder/src" PYTHONPYCACHEPREFIX="$M/pyc" "$W/.venv/bin/python" -m pytest <files> -q`. Never `.venv/bin/pytest` (CLAUDE.md: its shebang tests the worktree, not the copy).
  4. Prove the shadowing once per mutant: the same command line with `-c "import llama; print(llama.__file__)"` instead of `-m pytest ...` must print a path under `$M/tree`.
  5. Record `mutant → predicted test → caught by (test id) | SURVIVED` in the implementer's report; the orchestrator copies the table into the SDD ledger. A survivor gets a test (or a written reason it is equivalent) before the commit. A mutant counts as caught only by the predicted test or a named other test, never by "some failure".


Spec (binding authority): /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md — "Slice 4": the 4b, 4c, 4d bullets (~lines 727-766), "New constants" (~line 981), and the 4a text that reads the date flags BEFORE 4b (~lines 705-715; Task 16 will consume `raw_date_flags`).
Orchestrator-added scope for this task (not in the brief, carried from an earlier review): run_vet_research must write vetting.json (the stage done-marker checked by should_run) LAST — after show.json and notes.json — and test_stage_vet.py gains a top-level `import pytest`.
The implementer reports mutant (c) "window runs before placeholder adoption" as SURVIVED-equivalent; judge that equivalence argument yourself.

## What the Implementer Claims They Built

Read the implementer's report: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/t15-impl/handback.md

## Diff Under Review

**Base:** b9ae699
**Head:** ab6f708
**Diff file:** /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/2026-10-19-held-backlog-tier1/review-b9ae699..ab6f708.diff

Read the diff file once — it contains the commit list, a stat summary,
and the full diff with surrounding context, and it is your view of the
change. The diff's context lines ARE the changed files: do not Read a
changed file separately unless a hunk you must judge is cut off
mid-function — and say so in your report. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat b9ae699..ab6f708` and `git diff b9ae699..ab6f708`.
Do not crawl the broader codebase. Inspect code outside the diff only
to evaluate a concrete risk you can name — one focused check per named
risk, and name both the risk and what you checked in your report.
Cross-cutting changes are legitimate named risks: if the diff changes
lock ordering, a function or API contract, or shared mutable state,
checking the call sites is the right method.

Your review is read-only on this checkout. Do not mutate the working
tree, the index, HEAD, or branch state in any way.

## You Do Not Dispatch Subagents

Do all of this review yourself. Never spawn a subagent to review part
of the diff, and never spawn another reviewer for a second opinion.
This process already provides every review seat the work gets; a
reviewer you spawn duplicates one of them at full cost, and its
verdict counts for nothing. If the diff feels too large for one
pass, review it in passes yourself and say so in your report.

## Do Not Trust the Report

Treat the implementer's report as unverified claims about the code. It
may be incomplete, inaccurate, or optimistic. Verify the claims against
the diff. Design rationales in the report are claims too: "left it per
YAGNI," "kept it simple deliberately," or any other justification is the
implementer grading their own work. Judge the code on its merits — a
stated rationale never downgrades a finding's severity.

## Tests

The implementer already ran the tests and reported results with TDD
evidence for exactly this code. Do not re-run the suite to confirm their
report. Run a test only when reading the code raises a specific doubt
that no existing run answers — and then a focused test, never a
package-wide suite, race detector run, or repeated/high-count loop. If
heavy validation seems warranted, recommend it in your report instead of
running it. If you cannot run commands in this environment, name the
test you would run.

Warnings or other noise in the implementer's reported test output are
findings — test output should be pristine.

Evidence you cannot see is not evidence that doesn't exist. If the
report or its test evidence looks truncated, or you cannot locate the
results it claims, re-read the file at its stated path — and if it is
genuinely missing or garbled, report that as a gap for the controller.
Re-running the suite to regenerate what you failed to read is not
verification; illegibility of the evidence is not invalidation of it.

## Part 1: Spec Compliance

Compare the diff against What Was Requested:

- **Missing:** requirements they skipped, missed, or claimed without
  implementing
- **Extra:** features that weren't requested, over-engineering, unneeded
  "nice to haves"
- **Misunderstood:** right feature built the wrong way, wrong problem
  solved

If the brief lists several files each with its own change (a batched
dispatch), check the diff against that list file by file: every listed
file must have its corresponding hunk. A listed file the diff never
touches is a Missing finding, no matter how clean the rest of the
batch looks.

If a requirement cannot be verified from this diff alone (it lives in
unchanged code or spans tasks), report it as a ⚠️ item instead of
broadening your search.

## Part 2: Code Quality

**Code quality:**
- Clean separation of concerns?
- Proper error handling?
- DRY without premature abstraction?
- Edge cases handled?

**Tests:**
- Do the new and changed tests verify real behavior, not mocks?
- Are the task's edge cases covered?

**Structure:**
- Does each file have one clear responsibility with a well-defined interface?
- Are units decomposed so they can be understood and tested independently?
- Is the implementation following the file structure from the plan?
- Did this change create new files that are already large, or
  significantly grow existing files? (Don't flag pre-existing file
  sizes — focus on what this change contributed.)

Your report should point at evidence: file:line references for every
finding and for any check you would otherwise answer with a bare
"yes." A tight report that cites lines gives the controller everything
it needs.

Your final message is the report itself: begin directly with the
spec-compliance verdict. Every line is a verdict, a finding with
file:line, or a check you ran — no preamble, no process narration,
no closing summary.

## Calibration

Categorize issues by actual severity. Not everything is Critical.
Important means this task cannot be trusted until it is fixed: incorrect
or fragile behavior, a missed requirement, or maintainability damage you
would block a merge over — verbatim duplication of a logic block,
swallowed errors, tests that assert nothing. "Coverage could be broader"
and polish suggestions are Minor.
If the plan or brief explicitly mandates something this rubric calls a
defect (a test that asserts nothing, verbatim duplication of a logic
block), that IS a finding — report it as Important, labeled
plan-mandated. The plan's authorship does not grade its own work; the
human decides.
Acknowledge what was done well before listing issues — accurate praise
helps the implementer trust the rest of the feedback.

## Output Format

### Spec Compliance

- ✅ Spec compliant | ❌ Issues found: [what's missing/extra/misunderstood,
  with file:line references]
- ⚠️ Cannot verify from diff: [requirements you could not verify from the
  diff alone, and what the controller should check — report alongside the
  ✅/❌ verdict for everything you could verify]

### Strengths
[What's well done? Be specific.]

### Issues

#### Critical (Must Fix)
#### Important (Should Fix)
#### Minor (Nice to Have)

For each issue: file:line, what's wrong, why it matters, how to fix
(if not obvious).

### Assessment

**Task quality:** [Approved | Needs fixes]

**Reasoning:** [1-2 sentence technical assessment]


## Delivery (binding)
Your task name is t15-rev; $D = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1.
1. Report, then sentinel: write your full review to `$D/t15-rev/handback.md`, THEN touch `$D/t15-rev/done`; also return the full review as your final reply.
2. First action: `mkdir -p "$D/t15-rev" && touch "$D/t15-rev/t15-rev.log"`; tee any long command into that log; nothing else is written to that directory.
3. Check `$D/TAKEN_OVER` and `$D/taken-over/t15-rev` before each write batch; if either exists, stop and write a final report.
4. You make no commits. Never run `git stash` in any form. Never `git clean -x`/`-X`.
5. Deliberate breakage (if you mutate to test a doubt) only in a scratch copy under your own `mktemp -d "$TMPDIR/mut-t15-rev-XXXXXX"`, run with `PYTHONPATH` shadowing per the Global Constraints recipe, never in the live worktree; delete only that exact path.
