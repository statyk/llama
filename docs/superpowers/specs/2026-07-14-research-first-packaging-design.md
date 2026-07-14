# Research-first packaging: vetted research by default, script opt-in

**Date:** 2026-07-14
**Status:** Approved

## Problem

The package's only editorial artifact today is the verbatim DJ script
(`dj-notes.md` + `Manifest.dj_notes`), produced by the high-tier `synthesize`
touchpoint. Deployments whose downstream DJ (human or LLM) writes its own
patter pay for a script they discard, while the richer artifact — the
`deep_research` output — never leaves the run directory. Worse, research is
the pipeline's only LLM artifact with **zero validation**: `run_research_task`
writes free text straight to disk. Its only safety net is indirect — bad
research *sometimes* leaks wrong songs into the script and trips
`factual_guard`. If research is to ship, it must be vetted directly.

## Decision summary

1. **Research ships in every package, and is always vetted** by a new
   low-tier grounding check. Vet failure marks the show `needs-review`
   (packaging is skipped, per the existing pre-package flag pattern).
2. **Script generation becomes opt-in** (`--script` / profile `script`,
   default off). When enabled, synthesize + `factual_guard` run unchanged.
3. **The package also carries the listener-review digest** (same top-5 ×
   800-char digest synthesize consumes), so a downstream synthesizer has the
   same three inputs our synthesize stage gets: show data, research, reviews.
4. **Manifest bumps to `schema_version: 2`**: `dj_notes` optional, artifact
   pointers added, `show.context` sourced from the vetting call.

## Components

### 1. `vet_research` touchpoint (ninth LLM touchpoint)

- Prompt: `src/llama/prompts/vet_research.md`. Input: the research markdown
  only (no show data in the prompt). Output (JSON, new `ResearchVetting`
  Pydantic model in `models.py`):
  - `asserted_songs: list[str]` — titles the document asserts were performed
    **at this show**. Songs mentioned as context (other nights, studio
    versions, tour statistics) are excluded — the prompt must make this
    distinction explicit.
  - `asserted_dates: list[str]` — dates the document asserts **this
    performance** took place on (any format; normalized in Python).
    Neighboring-show dates mentioned as tour context are excluded.
  - `context: str` — one line placing the show in its era/tour, for the
    manifest header.
- Tier: `DEFAULT_TIERS["vet_research"] = "low"` (haiku on claude_cli,
  gemini-flash on openrouter). Added to `TASK_KEYS` in `pipeline.py`;
  per-task override via `[llm.vet_research]` and the escalation ladder
  (final retry one tier up) work through existing machinery.
- Why LLM extraction and not regex: distinguishing "this show happened on
  June 10" from "two nights after the 6/8 Nassau show" is semantic. A date
  regex over the whole document would flag legitimate tour context. Same for
  songs: `## Context` sections legitimately name songs from other shows.

### 2. Deterministic grounding check (Python, zero tokens)

In `stages/vet_research.py`:

- Every entry in `asserted_songs` must match a `show.tracks` title via the
  existing `normalize_song`. Failures append
  `research asserts unknown song: <title>` to `show.review_flags`.
- Every entry in `asserted_dates`, normalized to `YYYY-MM-DD` (deterministic
  date parsing of common formats; unparseable assertions are flagged as
  unparseable rather than silently dropped), must equal `show.date`.
  Failures append `research asserts wrong date: <date>`.
- Any flag sets `show.needs_review = True` and rewrites `show.json`
  (same pattern as `factual_guard` / package duration checks).

### 3. New pipeline stage: `vet`

- Runs in `process_show` immediately after research. Artifact:
  `vetting.json` (the `ResearchVetting` payload plus the computed flags) at
  `ShowWorkspace.vetting`.
- Registered in `VALID_STAGES` and `_show_stage_artifacts`
  (`"vet": [show_ws.vetting]`), so `llama run --stage vet --force` re-vets a
  cached `research.md` without re-running the expensive opus+web-search
  research call.
- Skip-if-exists semantics identical to other stages (`should_run`).
- Failure handling: the existing post-synthesize `needs_review` check in
  `process_show` (pipeline.py) already halts before packaging; vet flags ride
  the same check. No new gating machinery. `--auto` runs skip flagged shows;
  `llama deliver` refuses them without `--force`. A vet failure therefore
  means **no package is built** until a human clears or re-runs research.

### 4. Optional script generation

- `Profile` gains `script: bool = False`. `llama find` and `llama run` gain
  `--script/--no-script` (typer bool option, default off). `profile run`
  passes the profile's setting.
- `process_show` gains `script: bool = False`. When off, `run_synthesize` is
  not called at all (no opus call, no `dj-notes.*` artifacts) and `notes` is
  `None` through packaging. When on, synthesize and `factual_guard` run
  exactly as today.
- `llama run --stage synthesize` implies script generation for that replay
  (forcing the stage is an explicit request for a script).
- `manifest.show.context` comes from `vetting.context` in **both** modes —
  one source of truth; `DJNotes.context` is no longer read by packaging.

### 5. Package layout and Manifest v2

Package directory gains, unconditionally:

- `research.md` — copied from the run dir (only reached when vetting passed,
  since vet failure halts before packaging).
- `reviews.md` — the reviews digest (top 5 reviews, 800 chars each). The
  digest helper moves out of `stages/synthesize.py` into `util.py` so
  synthesize and package render the identical digest.

`dj-notes.md` is copied only when a script was generated (existing
conditional in `run_package` already handles absence).

`Manifest` changes (`models.py`), `schema_version` 1 → 2:

- `dj_notes: DJNotes | None = None`
- `SetBreak.note_index: int | None = None` — breaks always mark *where*
  (`after_track`); note indices exist only when a script does.
- New fields: `research: str | None` and `reviews: str | None` — relative
  paths within the package (`"research.md"`, `"reviews.md"`);
  `research_vetted: bool = True` (always true in practice; present so
  downstream can assert on it).
- `run_package` / `build_manifest` accept `notes: DJNotes | None` and the
  vetting context.

### 6. Package contract documentation

README (or `docs/`) gains a package-format section covering v2 and the
**downstream synthesis contract**: whoever generates spoken copy from the
package must guard it against the manifest —

- every song mentioned must match a manifest track title,
- set intros must cover exactly the manifest's sets,
- one break note per `set_breaks` entry.

These are `factual_guard`'s rules, restated as the consumer's obligation
when synthesis happens downstream.

## Cost effect (per show, default mode)

Removed: one high-tier synthesize call (~5–10K in / ~1K out, opus).
Added: one low-tier vet call (~1.5–3.5K in / ~300 out, haiku).
`deep_research` (opus + web search) is unchanged and remains the dominant
cost. On `claude_cli` these are Max-plan headroom, not dollars.

## Testing (all offline, fake backend)

- Vet: pass; fail on unknown song; fail on wrong date; tour-context research
  mentioning neighboring dates/songs is **not** flagged (prompt-contract
  fixture); unparseable asserted date flags rather than passes.
- Stage mechanics: `vetting.json` written; skip-if-exists; `--stage vet
  --force` re-vets cached research without touching `research.md`.
- Script off: synthesize never called (fake provider call log), no
  `dj-notes.*`, package has `research.md` + `reviews.md`, manifest v2 has
  `dj_notes=None`, `note_index=None`, pointers set, context from vetting.
- Script on: factual_guard unchanged; `dj-notes.md` in package; manifest
  carries both script and research.
- Manifest v2 round-trip; digest helper shared (synthesize input ==
  packaged `reviews.md`).
- Prompt template render test for `vet_research` alongside the existing
  eight.
- CLI: `--script` flag plumbed through `find`/`run`; profile `script`
  round-trips through TOML save/load.

## Out of scope

- Prose-level fact-checking of research (anecdotes, rankings, citations) —
  would need a second research-capability call and rival synthesize cost.
- Auto-retrying research on vet failure.
- TTS or any downstream synthesis implementation.
- Migration of already-delivered v1 packages.
