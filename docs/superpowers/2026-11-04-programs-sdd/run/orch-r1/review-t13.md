You are reviewing one task's implementation: first whether it matches its
requirements, then whether it is well-built. This is a task-scoped gate,
not a merge review — a broad whole-branch review happens separately after
all tasks are complete.

## What Was Requested

Read the task brief: /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/2026-11-04-programs-and-lineup/task-13-brief.md

Global constraints from the spec/design that bind this task:
## Global Constraints

- `emcee`, `transmitter` and `llama` never import each other. The new `dj_audio.title` field and the station lock file are part of the on-disk contract. Only `scripts/` may import both emcee and llama.
- transmitter stays Python 3.11-compatible (hugo: Debian 12). Gate: `packages/transmitter/scripts/test-in-debian12.sh` when Docker runs. If it doesn't, say so in the report.
- `timeline.json` keeps every existing field and its meaning; additions only. A show's notes and page go up before any timeline that lists it.
- The title is read from the manifest at publish time, never from cached `ShowAnalysis.meta`.
- Page text reaches the DOM through `textContent` only, and the server escapes it in `show.html`. Nothing parses markup.
- `antenna/public/player.js`, `nowplaying.js` and `style.css` stay byte-for-byte unchanged. `antenna/src/` changes only through `npm run pages`. No new client-side settings. Keep the existing look (`assets/radio.css`).
- Exact copy: `LMA RADIO PRESENTS` (the fallback when there is no title); section heading `The weekly lineup`; block span `7:00a – 9:56a` (an en dash with a space either side; the start alone when the end is unknown). The first lineup tab is labelled `Today`, the rest by short weekday (`Thu`).
- A block's displayed title is its clock `title`, else its `name`, everywhere, including a block no longer in the clock. A block is a **variety** block when it lists no profiles or more than one.
- Occurrence identity is the pair (`block`, `nominal_start`), with `nominal_start` formatted by `grid.us_to_iso` (as in plan rows) on every side.
- Station manifest writes are raw-dict read-modify-writes. They preserve every key they don't own (including `awaiting_fix`) and refuse rather than reformat. The encoding is `json.dumps(m, indent=2) + "\n"`, with `ensure_ascii` left at its default.
- hugo's `quiet_minutes` is 10. A rewritten manifest must keep its original mtime. The writer and the go-live probe use one order: write the temp file, flush, fsync, close, then `os.utime`, then rename, then re-check the mtime and re-apply it if it differs.
- **Lock contract** (both tools): the file is `<delivered folder>/.lma-station.lock`, where the delivered folder is the package directory's absolute parent (`Path(".").parent` is `.`). Contents are UTF-8: line 1 is `lma-station-lock 1 <32 lowercase hex token>`, then `tool: <emcee|llama>`, `command: <text>`, `host: <hostname>`, `pid: <n>` and `started: <ISO-8601 local time with offset>`, each on its own line, with a trailing newline. It is created with `O_CREAT|O_EXCL|O_WRONLY`, mode 0644, written, then fsynced. Empty or unparseable contents count as held. A tool releases only on its own token. A lock is never broken automatically and never expires. No tool parses the holder text.
- No tool holds the station lock while waiting on an operator prompt. Only command entry points (and `bulk_apply`'s per-show step) acquire it. It is not re-entrant: a second acquire in one process raises `StationLockReentry`, a bug.
- Every station write keeps the operator gate. An agent runs the dry run, shows it, and passes `--yes` only after Shawn approves, in a separate tool call.
- Worktree: `<repo>/.claude/worktrees/programs`, branch `programs-lineup`, with its own `.venv`. Python tests run as `./.venv/bin/pytest` there, never a bare `pytest`. Antenna: `cd antenna && npm test` (plus `npm run smoke` for page tasks). Every task leaves every suite green. Every commit ends with the session's attribution lines.

## Review Focus

1. **A program or block title with markup, an ampersand or great length** (`Gravel & Steel`, `<b>Late</b> "Night"`, a 60-character title): it shows as literal text on the ticket, the panel and `show/<slug>.html`, and wraps at 320 px with no sideways scroll. Pinned in Task 1 (`test_show_page_escapes_program_title`) and Task 4 (the hostile and 320 px smoke scenarios).
2. **A listener in another zone, and the lineup on a daylight-saving day:** a block near midnight moves to the neighbouring tab for a listener west of the clock's zone, no tab is skipped or repeated on the spring-forward or fall-back day, and no block appears twice. Pinned in Task 3 (`lineupDays` DST and zone tests).
3. **A lock left by a killed process (SIGKILL, power loss):** every writer refuses and names the holder plus `emcee lock show` and `emcee lock clear`. Nothing breaks the lock until the operator runs `emcee lock clear` and confirms. Pinned in Task 5 (`test_lock_clear_*`) and Task 10 (`test_refusal_names_holder_and_emcee_commands`).
4. **A voiced manifest not in emcee's exact encoding** (non-ASCII written with `ensure_ascii=False`, no trailing newline, duplicate keys, a float written as `1.50`, `dj_audio` not an object): the backfill refuses it, lists it, and leaves the file byte-identical, mtime included. Pinned in Task 8 (`test_plan_refuses_foreign_encodings`).
5. **The page against an old or partial transmitter** (no `program`, no `blocks`, a 404 or malformed lineup object): tickets read `LMA RADIO PRESENTS`, Coming up is flat with no headings, the lineup section is hidden, and the console is clean. The reverse mix matters too during rollout: new assets with the old `index.html` still play and show tickets. Pinned in Task 3 (helpers on missing data) and Task 4 (smoke, including `new assets with the old index.html`).

## Task-specific lens
- station_probe.py is the go-live probe (plan Task 19 runs it on the SMB share and on hugo). It must be stdlib-only and Python 3.11-compatible; scripts/test_station_probe.py must ALSO be 3.11-compatible and import only stdlib + pytest (a later gate runs it in a 3.11 venv with no llama/emcee).
- Its mtime --replace order must match the Global Constraints' writer order exactly (temp, flush, fsync, close, os.utime, rename, re-check + re-apply). A probe whose order differs from the real writer proves nothing about it.
- A probe that cannot fail is worthless: check that `double` is counted only from a token re-read, that the DROP_EXCL test switch actually removes O_EXCL in spawned workers, and that the probe's exit code tracks `double 0`.
- The implementer added an unbriefed 6th test (cross) and reports a py3.11 run with only pytest installed; verify on their merits.


## What the Implementer Claims They Built

Read the implementer's report: /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/programs/t13-impl/handback.md

## Diff Under Review

**Base:** f0b480ce
**Head:** ba83a992
**Diff file:** /Users/shawn/projects/llama/.claude/worktrees/programs/.superpowers/sdd/2026-11-04-programs-and-lineup/review-f0b480ce..ba83a992.diff

Read the diff file once — it contains the commit list, a stat summary,
and the full diff with surrounding context, and it is your view of the
change. The diff's context lines ARE the changed files: do not Read a
changed file separately unless a hunk you must judge is cut off
mid-function — and say so in your report. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat f0b480ce..ba83a992` and `git diff f0b480ce..ba83a992`.
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
