You are reviewing a design spec before it is turned into an implementation plan. You are a
reviewer only: do not edit, create or delete any file anywhere, do not commit, and do not run
anything on remote hosts, and make no TTS or LLM API calls (no network). Return your review as
your final text reply.

## What to review
The draft under review is:
/Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking/docs/superpowers/2026-10-26-paragraph-chunking-sdd/spec-review/r1-frozen.md
Review exactly that file. Do not open any other copy of this spec (including
docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md) or any git history.

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
