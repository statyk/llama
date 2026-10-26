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

## What to look for (strict-surface review)
Review ONLY the two strict surfaces, and report every defect on them, nothing else. Read the
current code paths end to end first (`render_speech_mp3`, `_chunked_pcm`, `_locate_block`,
`SpeechBlocked` and its fields, `process.process_package`'s repair loop, `_repair`,
`rephrase_problems`, `rephrase_segment`, the rephrase prompt, `_synthesize_dj_audio` and its key,
the `rendered` set, `--force`/`--fresh`), then check the design against scenarios such as:
- Content filter: a block on a packed chunk of 1, 2 and N sentences; a chunk whose sentences
  each pass alone (cross-sentence trigger) — does the fallback really avoid it, and what if the
  per-sentence fallback is itself blocked; a block whose trigger is a band/song name a rephrase
  cannot remove ("Cracker"); a block on the narrowing calls themselves; a sentence that
  `_split_sentences` and the packer disagree about (abbreviation rule, newlines, paragraph
  collapse); the rephrased segment's sentence count or paragraph breaks changing, and
  `rephrase_problems` comparing sentence lists after the abbreviation change; how the error
  identifies the segment and sentence back to `_repair`; repeated blocks across MAX_REPHRASES;
  `emcee say` (no repair) and `chunk = false` parity; mlx_audio (which may never block) vs
  Voxtral; bed vs no bed (`fmt` wav vs mp3 in `_locate_block`).
- Cache key: every input that changes the rendered bytes (text incl. paragraph breaks vs the
  collapsed text, chunk_chars, room_tone on/off, room-tone algorithm version, packer version,
  abbreviation-rule change to sentence boundaries, the per-chunk fallback after a block, bed,
  loudness, voice/model, lexicon) — is each in the key, or provably unable to change the
  audio; anything in the key that does not change the audio (needless paid re-renders);
  the unchunked path staying byte-identical in key; the per-chunk fallback producing different
  audio for the same key on a later run (deterministic?); `emcee say` (does it cache?);
  `rendered`/`--force` interaction after a repair; room tone's seed and determinism across
  runs; a mid-run crash leaving a cached clip under a key that would later be reused wrongly.
Anything you find unclear on these surfaces is a finding.

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
