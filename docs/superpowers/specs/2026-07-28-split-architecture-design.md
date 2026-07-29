# Split architecture: llama + persona tool + llm-core

**Date:** 2026-07-28
**Status:** Approved direction; decomposed into three sub-projects, each getting its
own spec → plan → implementation cycle. This document is the umbrella design and the
record of the decisions and their rationale.

## Motivation

llama today is one program doing two jobs: (1) finding, curating, researching, and
packaging concerts, and (2) giving them a voice — persona definitions, verbatim DJ
scriptwriting, and TTS. The second job exists only because the original consumer (a
friend's AI-DJ radio station, which has its own DJ-personality machinery) lacked the
bandwidth to ingest raw materials, so llama grew its own presentation layer.

Two futures now pull on the design:

- **Shawn's own archive-only station** (likely, no timeline): needs the persona/TTS
  piece, plus scheduling and streaming — functionality that must not accrete into
  llama.
- **Phish** via Phish.in (single source per show, no recording comparison, but still
  wanting research/reviews synthesis): a second *producer* of shows that needs
  llama's back half but almost none of its archive.org-specific front half.

The question was where to cut. The answer — reached after mapping the actual coupling
surface — is **not** the acquisition/presentation line as first imagined, but the
**show-package contract**, with `synthesize` reshaped from a verbatim persona script
into a neutral, vetted **briefing**.

## Why this line

The pipeline's feedback loops all live upstream of the package:

- `factual_guard` (`synthesize.py:77-108`) checks the DJ text against `Show.tracks`
  and writes `needs_review`/`review_flags` back into `show.json`.
- The triage/fix workflow is one human-attention queue spanning curation and script:
  `fix --set-venue` redoes from gather and the script regenerates automatically.
- `broadcast-ready` (`catalog.py:151-172`) is a conjunction over both halves.

Splitting *through* those loops (the original acquisition-vs-presentation idea) would
force cross-tool invalidation — the hardest problem in any pipeline system — or
duplicate the hold/triage machinery. Splitting *below* them, at the package, makes the
boundary one-way: llama owns every loop; downstream tools are pure consumers/filters
of a self-contained directory. The Unix model (small tools, stable data format) works
exactly where data flows one direction, and the package is already deliberately
self-contained (`_deliver_one` copies only `package/`; consumers never see the
workspace).

Reshaping the script into a briefing is what makes the line clean: the vetted,
grounded *content* work stays in llama (it depends on show data and the hold system);
the *personality* work — which is a station concern, not an acquisition concern —
moves out. This also restores the original product: the briefing **is** the "raw
materials + synthesized notes" deliverable the friend's station was always meant to
get.

## The two programs

### llama (keeps)

interpret → search → winnow → select-recording → gather → research → vet →
**brief** (renamed/reshaped `synthesize`) → package → deliver, plus status/show/
triage/fix/redo/rm/suppress and the run/profile/config namespaces. All holds, all
overrides, all quality gates.

The **brief** stage replaces the verbatim persona script with a thorough, neutral,
vetted briefing from which a human or downstream agent writes a script:

- `briefing.md` — prose: context, significance, research narrative, reviews
  sentiment.
- `briefing.json` — structured: per-set talking points, notable moments, review
  sentiment summary, cautions, and the **narration directive** (`full`/`vague`,
  sourced from `overrides.json` — with `vague`, the briefing asserts no set
  structure and names no songs, and downstream scriptwriters must do likewise).

The briefing is still LLM-generated (same `[llm]` task machinery, still a
high-tier task) and still guarded: a briefing that contradicts the setlist holds the
show, exactly as `factual_guard` does today — the guard's target changes from DJ
notes to briefing content. `fix --narration` and the accept-vague triage resolution
stay in llama (setlist-confidence is a curation concern).

llama **drops**: `tts/`, `speech_text.py`, `presenters.py`, `persona_style`, the
`voice` command, dj-audio synthesis and `broadcast.m3u` emission in `package.py`
(the music/voice fusion point at `package.py:253-319` reduces to its music half),
`Profile.presenter`/`Profile.title`/`Criteria.voice` and the voice fields of
`Provenance`, and the three voice legs of `broadcast_readiness`. llama's delivery
gate becomes **package-complete + not held**; `deliver --allow-unvoiced`
disappears because unvoiced is now the only thing llama ships.

### Persona tool (new; name TBD — Shawn to choose)

A package→package filter: reads a show package, writes DJ script + audio into it,
same format out. Owns everything personality- and speech-related:

- **Presenter definitions**: the `presenters/<id>.toml` format moves here unchanged
  (name/sex/character + `voice` XOR `voice_clone`, optional `bed`), along with the
  `presenter add/list/show/remove` CLI surface.
- **Scriptwriting**: an LLM task taking briefing + character → verbatim script
  (per-gap segments as today: combined set lead-ins + outro). Persona styling
  (opinions and paraphrased sentiment allowed, facts grounded, no attendance
  claims) moves here from `persona_style`.
- **Its own factual guard**: the script is checked against the manifest's
  `tracks`/`set_breaks` (the package carries the full setlist, so the check is
  self-contained) and against the briefing's narration directive. A failing script
  is this tool's failure to surface — llama's hold queue is not involved.
- **Speech layer**: `speech_text.py` normalization + pronunciation lexicon, the
  TTS `SpeechProvider` backends (voxtral/elevenlabs/fake), chunking, bed mixing,
  and the per-segment cache — moved wholesale, unchanged.
- **Outputs**: `dj-notes.md`, `package/dj-audio/`, `broadcast.m3u`, and the
  `dj_notes`/`dj_audio` manifest blocks (it rewrites `manifest.json` atomically).
  **broadcast-ready** — script + audio + broadcast.m3u complete — becomes this
  tool's gate and vocabulary, not llama's.
- **Its own config**: `[llm]` (shared lib semantics, own task registry with a
  scriptwrite task and guard task), `[tts]` (moved from llama's config), and
  presenter assignment (which presenter voices which packages — the concern that
  `Profile.presenter` used to carry).

It is an **LLM program**, not just an audio encoder — hence the shared library.

## The show-package contract (manifest v3)

The package directory is the public interface between the tools (and to the friend's
station, the future scheduler/streamer, and a possible mp3-flattener). Changes:

- Adds `briefing.md` + `briefing.json` (replacing `dj-notes.md` as llama's text
  deliverable); manifest gains a `briefing` block (pointer + narration directive +
  vetted flag).
- `dj_notes`/`dj_audio` manifest blocks remain, but are **written by the persona
  tool**, never by llama; they stay structurally separate from the music blocks
  (already true in v2).
- Version bumps to 3. **No back-compat shims, no migration** — solo user,
  established precedent (re-run `redo --from` as needed).

The exact schemas are sub-project 2's spec; this document fixes only the ownership
split and the requirement that the narration directive travels in the manifest.

## llm-core: the shared LLM library

Both tools need "render a prompt template, call a model, validate against a Pydantic
schema, retry with validation feedback, escalate a tier on the final attempt" — which
is exactly the current `src/llama/llm/` layer (~400 lines). It is extracted into a
third package rather than duplicated (drift) or replaced with Instructor/LiteLLM
(churn for nothing; ecosystem check 2026-07-28 confirmed those cover the same ground,
so the layer is also **not** worth publishing to PyPI — it stays internal).

The extraction de-llama-ifies exactly three tendrils:

1. `load_prompt` hardcodes the `llama.prompts` resource package (`llm/tasks.py:21`)
   → parameterize (loader argument or prompt text passed in); each tool owns its
   prompt files.
2. Tier resolution takes the whole `Config` (`llm/__init__.py:39-51`) → accept a
   small settings struct (backend/model/tier per task + tier tables) that each tool
   builds from its own `config.toml`. Task-name→tier defaults (`DEFAULT_TIERS`)
   stay per-tool — app vocabulary, not lib code.
3. `LLMError` subclasses `LlamaError` (`llm/provider.py:6`) → lib defines its own
   base; llama wraps.

What stays per-tool: task registries (prompt templates, output schemas, tier
defaults). What the lib owns: `LLMProvider` protocol, claude_cli/openrouter/fake
backends, `render`/`extract_json`, `run_json_task`/`run_research_task`, ladder +
escalation. TTS is **not** in this library and is **not** unified with it — after
the split TTS has exactly one consumer.

Noted improvement (fold into sub-project 1 or 2, not a blocker): the claude_cli
backend can adopt `claude -p --json-schema` for native schema-conformant output,
retiring extract-and-re-ask on that backend.

## Repo, packaging, license

- **Monorepo.** One repo, three Python packages (llama, persona tool, llm-core),
  separate CLI entry points, one test suite, one release/signing pipeline building
  both binaries. Rationale: while the contract and lib are young, most changes cut
  across packages; a monorepo keeps each an atomic commit with one test run.
  Extracting a repo later, once the boundary calcifies, is the cheap direction.
- **License: GPL-3.0-or-later across the board.** Shawn holds copyright and could
  license the new packages differently (GPL binds licensees, not the author), but
  there is no reason to; the vendored deadstream-derived `set_breaks.csv` pins
  llama itself to GPL regardless.

## What deliberately does not change

- The acquisition pipeline, holds/triage semantics, overrides model, ledger,
  locking, and workspace layout (minus the moved files).
- The presenter TOML format and the TTS provider layer — they move, not morph.
- The package as the delivery unit and the station-facing docs' promises about it
  (updated for v3 fields, not restructured).

## Future consumers (out of scope, enabled by this design)

Scheduler, streamer, and an mp3 flattener (automating the manual multi-hour-mp3
stitching) are separate programs consuming packages. A Phish.in fetcher is a thin
front-end feeding llama's research→brief→package back half via a source-adapter
seam at gather — designed when Phish becomes real, not now.

## Decomposition and build order

1. **Monorepo restructure + llm-core extraction.** Mechanical, low risk; llama's
   behavior unchanged; full suite green after. Includes the three de-coupling
   changes and (optionally) `--json-schema` adoption.
2. **Briefing + contract v3 in llama, additively.** New `brief` stage and briefing
   schemas; manifest v3 with the `briefing` block. The existing synthesize/voice
   path keeps working unchanged in this step, so voiced packages remain producible
   with no capability gap.
3. **Persona tool + the cut.** New package: scriptwriter + guard + presenter CLI +
   speech/TTS port. In the same sub-project, llama drops `synthesize`, `tts/`,
   `presenters.py`, `speech_text.py`, the voice CLI surface and `[tts]` config, and
   its gate semantics shrink to package-complete + not held (the "llama drops" list
   above describes this end state).

Ordering rationale: 1 is pure mechanics and unblocks everything; 2 changes the
contract while everything still lives in one package (cheapest place to change it)
and stays additive so nothing breaks; 3 builds the new tool against a settled
contract and performs the removal only once its replacement exists. Each
sub-project gets its own spec, plan, and subagent-driven implementation cycle.
