> **Superseded 2026-10-26 (10:24 build finish; e6c0ba33 M4).** The build ran and finished
> (see `README.md` here for the record); the operator's listening check passed on the
> chunking; then merged to main for release v2.19.0. The text below is the pre-build handoff, kept as
> written.

# Handoff: paragraph-aware chunking (emcee), 2026-10-26 (updated 09:00)

**Where:** branch `emcee-paragraph-chunking`, worktree
`.claude/worktrees/emcee-paragraph-chunking` (cut from `main` @ `6fe245b5`), head `a25b334c`,
clean. Nothing is merged or pushed. **There is no `.venv` in the worktree yet**: the plan's
Task 0 creates it. Never run a bare `pytest` here (CLAUDE.md, worktree rule).

## State: spec and plan reviewed; build not started

- **Spec:** `docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md` (`b41863d4`). It went
  through two review rounds, six Opus reviews in all. All of them returned Foundation SOUND, with
  no Critical findings and no escalations. Review record: `spec-review/` here, with the frozen
  copies, per-reviewer summaries, `r1-decisions.md` and `r2-decisions.md`. Review mode: **Opus**.
- **Plan:** `docs/superpowers/plans/2026-10-26-paragraph-chunking.md` (`a25b334c`). It has 8 tasks
  plus Task 0, the worktree venv. Two blind Opus reviewers found 0 Critical issues. Both raised the
  same 2 Important issues (a Task 3 fixture with no floor-only frames, and a Task 2 newline rule
  left unpinned), and both are fixed. No task was reshaped, so there was no second round. Record:
  `plan-review/` here.
- The tasks, in order:
  1. abbreviation pre-pass in `_split_sentences`
  2. `plan_chunks` packer
  3. `tts/room_tone.py`
  4. one required `chunking: Chunking | None` argument plus the `[tts] chunk_chars`/`room_tone`
     config (no behaviour change)
  5. packed chunks, room tone and the chunk-digest cache key
  6. in-chunk content-filter narrowing and fallback (**strict surface**)
  7. scriptwrite/rephrase prompts plus literal `\n` unescape
  8. docs (the root `README.md`, `CLAUDE.md`, help text and docstrings)

## Next, in order

1. **Build via SDD.** The run has more than 3-4 tasks, so per `~/.claude/CLAUDE.md` launch an
   **Opus peer orchestrator** (the `sdd-delegation` skill: read `parent.md`, brief from
   `peer-brief.md`, launch with `~/.claude/sdd-peer-launch.sh`). Suggested models: Sonnet
   implementers for every task, and Opus spec-compliance and code-quality reviewers. Task 6 is the
   strict surface, so its Opus reviewers must get the spec's Stakes paragraph. Implementers run each
   task's mutation checks per the plan's Global Constraints (`PYTHONDONTWRITEBYTECODE=1`, the whole
   `packages/emcee` suite, restore with `git checkout -- <file>`). The final whole-branch review is
   Opus. Merge/push stay with the root. Do the `usage-pacing` fleet check first: the 7-day meter
   read 67% at 02:26 on 10-26, with the reset on Oct 31 at 06:59. The bulk-apply build in
   [[llama-held-backlog]] is deliberately held until after that reset; this build is smaller, but
   the operator decides whether it runs before the reset.
2. **Acceptance listening check** (the operator; Voxtral is metered): one Kurt (Qwen) and one Phil
   (Voxtral) segment voiced end to end with a real scriptwriter run, with the bed, compared with
   today's rendering. At no extra spend, also check:
   - the notes contain paragraph breaks
   - there are no invalid-JSON retries
   - Kurt's log shows no "quality check failed" lines
   - the mlx server's memory peak
   - optionally, an offline room-tone listen on a Jimmy render
3. Release (llama/emcee release mechanics) only after the listening check.

## Operator-side, independent of the build

- Kurt already points at the un-evened `~/.emcee/samples/kurt1.wav` (done; checked 2026-10-26).
- `live,Lyve,` is in `~/.emcee/pronunciations.csv` (done). **Open:** the lexicon matches whole
  words case-insensitively, so it also respells the verb ("what I live for" becomes Lyve). A phrase
  entry such as `Live from the Basement` would be narrower; the operator's call.

**Also on `main`, unreleased:** `6223b31` (emcee status TTS view, faster scan,
`scripts/backfill_tts_record.py`) and `9b60906` (the scriptwrite prompt bans present-anchored
time). Both reach the installed `emcee` only with a release.

**Evidence and tools:** `~/.llama-harness/tts-experiments/` (see the spec's Evidence section);
project memory `llama-qwen-tts-tuning`.
