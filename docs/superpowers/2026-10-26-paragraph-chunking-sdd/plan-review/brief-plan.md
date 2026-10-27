You are reviewing an implementation plan before it is executed. You are a reviewer only: do not
edit, create or delete any file anywhere, do not commit, do not create a venv or pip install, make no
TTS or LLM API calls (no network). Return your review as your final text reply.

## What to review
The plan under review:
/Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/docs/superpowers/2026-10-26-paragraph-chunking-sdd/plan-review/plan-frozen.md
Review exactly that file; do not open other copies of it or git history.
It implements the approved spec (read it in full first):
/Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md

How the plan is used: a peer orchestrator dispatches one implementer subagent per task (usually
Sonnet). The implementer sees ONLY its own task (plus the spec and the code), writes the tests and
code, commits, and runs the task's mutation checks; then Opus reviewers check the result against the
task (spec compliance, code quality). So every task must be executable on its own without inventing
anything, and every task must leave the whole suite green.

## Context you may read (read-only)
- The emcee code and tests it changes:
  /Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/packages/emcee/ (src/emcee/audio.py,
  process.py, scriptwrite.py, config.py, cli.py, prompts/, tts/ incl. loudness.py, quality.py, fake.py;
  tests/ incl. test_audio.py, test_process.py, test_config.py, test_scriptwrite.py, test_say_cmd.py,
  helpers.py), and herder's fake provider (packages/herder/src/herder/fake.py).
- The repo conventions: /Users/shawn/projects/llama/CLAUDE.md (emcee bullets; worktree venv rule).
- The harness reference for room tone and packing: /Users/shawn/.llama-harness/tts-experiments/
  (noise_test.py room_tone(), sweep_test.py pack()). Read only.
You may evaluate small pure-Python snippets mentally or with `python3 -c` (no installs) to check that
a test's literal expectations agree with the algorithm the plan states; do not import emcee.

## Stakes (read before reviewing)
This changes how every DJ clip is rendered, on air, for every presenter, on a single-operator
home radio station (one Mac running emcee; presenters on hosted Voxtral (metered per character)
and on local mlx_audio Qwen3-TTS (free)). Nothing here deletes, migrates or overwrites user data,
and readiness is untouched, so no broadcast-ready package changes state. The real costs are
on-air quality and paid TTS (every clip whose cache key changes re-renders when its package is
next voiced). An operator listening check gates release.
- Strict surfaces — report exhaustively: (1) the content-filter recovery path (`_locate_block`,
  `SpeechBlocked` handling in `render_speech_mp3`/`_chunked_pcm`, the `rephrase` repair loop in
  `process.py`, `rephrase_problems`): it must keep finding and rewording the one blocked
  sentence; a regression can make a blocked show unvoiceable. (2) the render-cache key: it must
  change whenever the rendered audio would change, and must not change otherwise; a stale hit
  ships old audio for new text.
- Everywhere else — report only defects plausible on the common setups (Voxtral, mlx_audio
  Qwen, with or without a bed, `[tts] chunk = true` default, `emcee run`/`emcee voice`/`emcee
  say`). A defect whose worst case is a clip that sounds slightly worse until re-voiced, or a
  modest one-time re-render spend, is Minor at most. For a rare setup, propose a documented
  limitation rather than a new mechanism. Where the spec is over-built for these stakes, a
  removal is a valid finding.

## What to look for
1. Fidelity: anything in the spec the plan omits, changes or adds (flag added mechanisms).
2. Decomposition and order: task boundaries, dependencies, each task leaving every suite green and
   wired up; checkpoint placement.
3. Strict surfaces: whether the tasks that touch them (Tasks 4-6) test the right scenarios.
4. Interfaces: names, signatures, formats defined once and used consistently across tasks.
5. Executability: whether an implementer seeing one task could carry it out without inventing
   anything — including whether its tests' literal expectations are actually right for the stated
   algorithm, and whether its commands run where they will run (this worktree, its own .venv).
6. Proportion and sprawl; idioms implementers will copy.
Anything unclear is a finding.

## Output format
Findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: task/step plus a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, spec quote, or your computation
  - Failure scenario: what the implementer or the shipped code does wrong
  - Suggested fix: one sentence
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
