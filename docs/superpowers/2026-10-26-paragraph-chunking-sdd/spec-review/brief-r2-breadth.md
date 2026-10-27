You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, and do not run
anything on remote hosts, and make no TTS or LLM API calls (no network). Return your review as
your final text reply.

## What to review
The draft under review is:
/Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/docs/superpowers/2026-10-26-paragraph-chunking-sdd/spec-review/r2-frozen.md
Review exactly that file. Do not open any other copy of this spec (including
docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md) or any git history.

## Already found
The issues found in the earlier round, and how the spec now handles each:
/Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/docs/superpowers/2026-10-26-paragraph-chunking-sdd/spec-review/r1-decisions.md
Read it first. Do not report those issues again, unless the spec's current handling is itself
wrong, incomplete or introduces a new problem — then say precisely what is wrong with it.
Focus on regressions and new problems introduced by the revision, and on anything still missed.

## Context you may read (read-only)
- The emcee code it changes, in the worktree
  /Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/packages/emcee/:
  `src/emcee/audio.py` (`_split_sentences`, `_chunked_pcm`, `_locate_block`,
  `render_speech_mp3`, `_synthesize_dj_audio` and its cache key), `src/emcee/process.py`
  (`process_package`, `_repair`), `src/emcee/scriptwrite.py` (`rephrase_problems`,
  `rephrase_segment`), `src/emcee/prompts/scriptwrite.md`, `src/emcee/prompts/rephrase.md`,
  `src/emcee/config.py` (`[tts]` model, strict base), `src/emcee/cli.py` (`emcee say`),
  `src/emcee/speech_text.py`, `src/emcee/tts/` (providers, `loudness.py`, `bed.py`,
  `mlx_audio.py`, `quality.py`, `calibration.py`), and `tests/`.
- Project conventions: /Users/shawn/projects/llama/CLAUDE.md (the emcee bullets).
- The throwaway experiment harness the spec cites as evidence:
  /Users/shawn/.llama-harness/tts-experiments/ (`noise_test.py`'s `room_tone()`, `para_test.py`,
  `sweep_test.py`, logs). Read only; do not run anything that synthesizes audio.
You may run the existing offline test suite read-only if it helps:
`cd <worktree> && python -m pytest packages/emcee -q` only if a `.venv` exists in the worktree
(do not create one, do not pip install).

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
