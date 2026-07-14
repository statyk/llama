# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Design phase — no code exists yet. The approved design spec is
`docs/superpowers/specs/2026-07-14-llama-design.md`; read it before doing any
work here. Next step in the workflow is an implementation plan
(superpowers:writing-plans), then implementation.

## What this is

`llama` — a Python CLI that finds concerts on archive.org's Live Music Archive
(LMA), winnows them for quality, researches the specific performance online,
and emits a self-contained "show package" (verified audio, m3u, manifest with
track titles/set breaks, LLM-written DJ notes) for an automated in-house radio
station. Usage tilts heavily toward Grateful Dead shows (two sets + encore).

## Architecture (from the spec — the short version)

- **Staged pipeline over an on-disk workspace** (default `~/.llama/`):
  interpret → search (wide net) → winnow (quality gate + optional human gate)
  → select-recording → gather → research → synthesize → package. Every stage
  reads/writes plain files in a per-run directory; stages write outputs only on
  success and are individually re-runnable with `--force`.
- **Two modes:** one-off queries, and standing criteria profiles for recurring
  segments with a `ledger.jsonl` dedup history keyed by performance identity
  (artist + date + venue), not archive.org item id.
- **LLM layer:** provider abstraction with two capabilities — `complete`
  (schema-validated, no tools) and `research` (needs web search). Dev backend
  shells out to headless `claude -p`; OpenRouter comes later; a `fake` backend
  serves tests. Six named touchpoints, each with a prompt template file under
  `prompts/` and a Pydantic output schema. LLM calls live only at stage
  boundaries — everything else is deterministic.
- **Quality philosophy:** the LMA is a completist archive. Winnowing demands
  evidence a show is well received by people who were *not* there (LMA reviews
  are heavily attendance-biased). Suspicious output (unresolved track titles,
  duration mismatches, low-confidence setlist parse, DJ notes contradicting
  the setlist) marks a show `needs-review` rather than shipping; `--auto` runs
  skip such shows.

## Domain gotchas

- archive.org items contain junk: `gd73-06-10.sbd.hollister.174.sbeok.shnf`
  (sample m3u in repo root) includes a spam file `FOLLOW-ME @BYPIKENO.mp3`
  that would play on air if file lists were trusted. Filter to originals (or
  derivatives of originals) matching the item's dominant filename convention
  with plausible durations.
- Track filenames (`gd73-06-10d1t04.mp3`) don't carry song titles; disc/track
  numbering doesn't map to sets. Titles resolve via cascade: embedded tags →
  setlist parsed from the item description → sibling recordings of the same
  performance. Never guess — flag unresolved.
- Setlists in descriptions are convention, not schema; the parser must be
  defensive and report confidence, with an LLM extraction fallback.
- Multiple recordings of the same performance are the norm; show-level merit
  (winnow) and recording-level quality (select-recording) are deliberately
  separate decisions.

## Conventions

- Audio files (`*.mp3`, `*.flac`, `*.shn`) are gitignored; never commit audio.
- Test fixtures are captured real archive.org API responses (gd73-06-10 is the
  canonical one). Pipeline tests use the `fake` LLM backend and run offline;
  the only live end-to-end test is manual/opt-in.
