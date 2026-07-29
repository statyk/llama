# Briefing + manifest v3 (split sub-project 2)

**Date:** 2026-07-29
**Status:** Approved design for sub-project 2 of the split architecture
(`docs/superpowers/specs/2026-07-28-split-architecture-design.md`). Additive: the
existing synthesize/voice path is byte-for-byte untouched; nothing voiced today loses
that capability.

## Goal

Add the neutral, vetted **briefing** to llama as a new default-on pipeline stage, and
bump the show-package contract to **manifest v3** with a `briefing` block. After this
sub-project every packaged show carries `briefing.md` + `briefing.json` alongside the
existing DJ-notes outputs, so downstream consumers (the friend's station now, the
persona tool in sub-project 3) can consume briefings from real packages while the old
script path keeps working unchanged.

## Decisions (settled here or in the umbrella; don't relitigate)

- **Default-on.** The brief stage runs on every show — no flag, no config gate. The
  transition-period cost (one extra high-tier LLM call per show while synthesize
  also runs) was accepted explicitly.
- **Additive.** `stages/synthesize.py`, TTS, presenters, `broadcast_readiness`, and
  the deliver gate are not modified. Synthesize is **not** rewired to consume the
  briefing — that is the persona tool's job in sub-project 3.
- **Placement: `brief` runs between `vet` and `synthesize`** — matching the
  sub-project 3 end state (`vet → brief → package`), so the eventual cut is a pure
  deletion. Consequence via the existing drop-downstream redo machinery:
  `redo --from brief` regenerates the script and package too. Accepted as a
  transition cost.
- **A contradicting briefing holds the show**, with the same retry-once-then-hold
  semantics as `factual_guard` (umbrella decision).
- **Manifest v3, no migration, no back-compat** — established precedent (solo user;
  old packages regenerate via `redo`).
- The briefing is **always neutral**: no presenter, no `{{style}}` slot. Persona
  styling stays a synthesize/persona-tool concern.

## 1. Stage and task wiring

New show-level stage **`brief`**:

- `SHOW_STAGE_ORDER` (`workspace.py:88`) becomes
  `["select", "gather", "research", "vet", "brief", "synthesize", "package"]`.
- `show_stage_artifacts()` (`workspace.py:91-99`) gains
  `"brief": [briefing.json, briefing.md]`; `ShowWorkspace` gains `briefing_json` /
  `briefing_md` path properties. Artifacts are written only on success, like every
  stage.
- `VALID_STAGES` (`cli.py:48`) gains `"brief"`. `redo --from brief`, batch
  selectors, and `fix` cascades work through the existing machinery with no new
  code paths (drop artifacts → `process_show` re-derives).
- `process_show` (`pipeline.py:86-127`) calls the new stage between vet and
  synthesize, guarded by the same `should_run()` idiom. **Self-healing:** any
  pre-existing show redone from any stage at or before `package` finds
  `briefing.json` missing and generates it en route — old shows pick up briefings
  (and v3 manifests) on their next redo with no migration step.
- `_PIPELINE_FLOW` / the `llama pipeline` teaching command (`cli.py:1052`,
  `1078-1114`) and `llama show` stage displays gain the new stage.

Tenth LLM task **`brief`**:

- `TASK_KEYS` (`pipeline.py:24-26`) gains `"brief"`; `DEFAULT_TIERS`
  (`config.py:17-27`) gains `"brief": "high"`. Per-task overrides
  (`[llm.brief] tier/model`) work automatically via `Config.llm_settings()`; the
  final-retry tier escalation applies as with every task.
- New prompt template `packages/llama/src/llama/prompts/brief.md`, loaded with
  `load_prompt("brief")`. Inputs (prompt slots):
  - `{{show_json}}` — full `Show` dump (post-vet, so corrected dates/venues are in).
  - `{{research_md}}` — `research.md` content ("(no research available)" if empty).
  - `{{reviews_digest}}` — same `reviews_digest()` used by synthesize.
  - `{{vetting}}` — a compact rendering of `vetting.json` (flags, notes,
    research_vetted) so `cautions` are grounded in the vet stage's findings rather
    than hallucinated. This is a deliberate difference from synthesize, which never
    reads vetting.
  - `{{narration_note}}` — same `full`/`vague` mechanism as synthesize
    (`synthesize.py:20-25`), reading `read_overrides(show_ws).narration`.
- The prompt instructs: neutral, factual register; thorough enough that a
  scriptwriter who has never heard of the show can work from it alone; opinions
  only as *attributed sentiment* ("reviewers describe…"), never the briefing's own;
  under `vague`, assert no set structure and name no songs.

## 2. Briefing schemas

New Pydantic model in `models.py`:

```python
class Briefing(BaseModel):
    context: str                      # era/tour/venue context prose
    significance: str                 # why this show is worth airing
    per_set: dict[str, list[str]]     # set label (as in Show.tracks) → talking points
    notable_moments: list[str]        # specific highlights, grounded in research/reviews
    review_sentiment: str             # summary of reception
    non_attendee_sentiment: bool      # True iff sentiment includes non-attendee voices
    cautions: list[str]               # caveats for the scriptwriter (thin research, corrected date, …)
    narration: Literal["full", "vague"] = "full"
    mentioned_songs: list[str] = Field(default_factory=list)  # guard input, as DJNotes
```

- `narration` is **stamped deterministically** after LLM parse from
  `overrides.json` — the model's opinion of it is overwritten, never trusted.
- `per_set` keys use the same set-label vocabulary as `Show.tracks` (including the
  encore label if present); the guard validates them against the real structure.
- `briefing.md` is **rendered deterministically** from the model (a
  `render_briefing_md()` sibling of `render_notes_md`, `synthesize.py:116-125`):
  headed sections for context/significance, one section per set with its talking
  points, notable moments, reception, and cautions. The two artifacts can never
  disagree because one is a pure function of the other.
- Under `vague`: `per_set = {}`, `mentioned_songs = []`, no songs or set counts
  anywhere in prose — enforced by prompt *and* guard (below), which is stricter
  than the script path's prompt-only enforcement.

## 3. The briefing guard

`briefing_guard(briefing: Briefing, show: Show) -> list[str]` in the new
`stages/brief.py`, reusing the `factual_guard` checks (`synthesize.py:78-109`)
generalized to briefing fields:

1. Every `mentioned_songs` entry must normalize to a known track title.
2. Every `per_set` key must be a set present in `show.tracks`.
3. Free-text set-count claims in `context` / `significance` / `notable_moments` /
   `review_sentiment` prose must match the real structure (same
   `_SET_COUNT_CLAIM` / `_ORDINAL_SET` regexes; extract them to module scope or a
   shared helper so both guards use one implementation).
4. **Vague-mode checks (new, deterministic):** when `narration == "vague"`,
   non-empty `per_set` or `mentioned_songs` is itself a guard failure.

Failure handling mirrors `run_synthesize` (`synthesize.py:158-174`): retry once
with the problems as feedback; if problems remain, append them to
`show.review_flags`, set `needs_review = True`, and still write the briefing
artifacts. The hold is an ordinary flag — triage/fix/accept-vague/overrule work on
it with zero new verbs. `fix --narration vague` already redoes from synthesize;
its redo point moves to `brief` so the briefing regenerates too.

Unlike `factual_guard`, there is no per-set-intro completeness check (a briefing
may legitimately have little to say about a set) — but an **empty `per_set` under
`full` narration** is flagged (it means the LLM ignored the structure).

## 4. Manifest v3

In `models.py`:

- `Manifest.schema_version` default flips **2 → 3** (`models.py:247`).
- New block model and required field:

```python
class ManifestBriefing(BaseModel):
    file: str = "briefing.md"
    json_file: str = Field("briefing.json", serialization_alias="json")
    narration: Literal["full", "vague"]
    vetted: bool                      # == research_vetted at package time

class Manifest(BaseModel):
    schema_version: int = 3
    ...
    briefing: ManifestBriefing        # required — llama-written, every v3 package
    dj_notes: DJNotes | None = None   # unchanged; persona-tool-owned after SP3
    dj_audio: DJAudio | None = None   # unchanged
```

(The serialized key is `"json"`; the Python attribute avoids shadowing
`BaseModel.json`.)

In `package.py` / `manifest.py`:

- `run_package` (`package.py:250-326`) copies `briefing.md` + `briefing.json` into
  `package/` alongside the existing files and **hard-fails** if they are missing —
  brief is a mandatory upstream stage, so absence means a broken workspace, not an
  option.
- `build_manifest` (`manifest.py`) gains the briefing parameters and emits the
  block. `playlist.m3u`, `broadcast.m3u`, dj-audio synthesis, and the
  music/voice fusion (`package.py:301-313`) are untouched.
- `deliver` copies `package/` wholesale (`_deliver_one`), so briefings travel with
  no changes.

**Not** in v3: no changes to `tracks`, `set_breaks`, `research`, `reviews`,
`research_vetted`, or the `show`/`source` dicts. The version bump signals the new
required block, nothing else.

## 5. Status / catalog surface

- `_STAGES` (`catalog.py:48-54`) gains `("briefing_json", 5, "briefed")` between
  vetted and scripted (the `scripted` entry renumbers; `packaged`/`held`/
  `delivered` are special-cased ahead of the loop and don't move). `derive_state`
  and the `--state` enum pick it up; `llama status --state briefed` and the state
  column work with no other changes.
- `broadcast_readiness` (`catalog.py:149-173`) and `deliver_refusals` are
  **unchanged** — briefing presence is guaranteed by the packaged state itself in
  v3, so it adds no readiness leg.
- `llama show <name>` lists the briefing artifacts in its files section and shows
  `narration` as today (it already surfaces overrides).

## 6. Testing

Offline, fake-backend, mirroring the synthesize test suite:

- **Stage:** brief runs between vet and synthesize; artifacts written on success
  only; `redo --from brief` drops briefing + dj-notes + package and regenerates
  all three; a pre-v3 show workspace (no `briefing.json`) redone `--from package`
  self-heals the briefing.
- **Schema/render:** `Briefing` round-trips; `render_briefing_md` is
  deterministic and section-complete; `narration` stamp overwrites the LLM value.
- **Guard:** each check fires (unknown song, bogus set key, wrong set-count claim,
  vague-mode violations, empty-per_set-under-full); retry-with-feedback path;
  unresolved problems hold the show with the exact flag strings; artifacts still
  written when held.
- **Manifest:** v3 emitted with correct `briefing` block (narration + vetted
  propagation, serialized `json` key); package hard-fails without briefing files;
  dj_notes/dj_audio/broadcast.m3u behavior byte-identical to the v2 tests
  (assert against existing fixtures).
- **Catalog:** `briefed` state derived correctly; ordering vs `scripted`;
  `--state briefed` filter.
- **Config:** `[llm.brief]` tier/model override resolves; default tier is high.

## 7. Documentation

- `docs/station-brief.md`: package-format section rewritten for
  `schema_version 3` — annotated manifest example gains the `briefing` block; the
  package-directory tree gains `briefing.md`/`briefing.json`; the briefing is
  documented as **the** text deliverable for scriptwriting, with `dj_notes`
  described as the legacy in-house script (persona-tool-owned after sub-project
  3); the "schema_version is bumped on breaking changes" question is answered by
  example.
- `README.md`: "Package format (v2)" → "(v3)" with the new block; downstream
  synthesis contract section points scriptwriters at the briefing first.
- `docs/workflow.md`: workspace tree, stage table (new `brief` row), and the
  synthesize row noting it is transitional.
- `llama config init` comment block: mention `[llm.brief]` override alongside the
  other task overrides.

## Out of scope (sub-project 3)

- The persona tool package, scriptwriter, its guard, presenter/TTS moves.
- Dropping synthesize/voice from llama; rewiring anything to *consume* the
  briefing; gate-semantics changes; removing `--allow-unvoiced`.
- Any migration/back-compat for v2 packages or pre-brief workspaces beyond the
  self-healing redo behavior described above.
