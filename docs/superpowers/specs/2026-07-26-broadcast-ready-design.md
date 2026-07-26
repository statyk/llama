# Broadcast-ready — design

## Summary

Add a derived **broadcast-ready** property to shows: a boolean that answers
"is this show actually airable right now?" It is surfaced as a tag and a
filter on `llama status` and `llama show`, as a selector on `llama deliver`
and `llama redo`, and as a yes/no line (with reasons) on the single-show
`llama show <name>` detail view.

Broadcast-ready is **derived, never stored** — computed on demand from
artifacts on disk plus the show's hold state, exactly like the existing
`state` and `voiced` signals in `catalog.py`. There is no new pipeline stage,
no new persisted field, no schema change, and no migration.

## The predicate

A show is **broadcast-ready** iff **all** of the following hold:

1. **Packaged with complete audio.** `package/manifest.json` exists, and for
   **every** track in the manifest (`manifest.tracks[].filename`) the audio
   file exists on disk under `package/audio/`. This is a strict on-disk
   re-verification, not merely "the show reached the `packaged` state" — it
   catches a deleted or half-synced audio file.
2. **DJ script.** `dj-notes.json` exists (the synthesize stage's `scripted`
   artifact).
3. **DJ audio.** The manifest `dj_audio` block is present — identical to the
   existing `voiced is True` signal (`derive_voiced`).
4. **broadcast.m3u.** `package/broadcast.m3u` exists.
5. **Not held.** `show.needs_review` is false. A show held for review is never
   broadcast-ready regardless of which files exist.

### Consequences that fall out of the existing pipeline

- An **unvoiced show can never be broadcast-ready.** The `package` stage only
  writes `dj-audio/` and `broadcast.m3u` when voice is active
  (`package.py`: `broadcast.m3u` is written only when `dj_audio is not None`),
  so conditions 3 and 4 are unreachable without voice.
- In a normally produced package, condition 4 (broadcast.m3u) always
  accompanies condition 3 (dj_audio). We nonetheless check all four artifacts
  **explicitly** rather than inferring any from another, so a tampered or
  partially copied package reads correctly.

### Reasons (for the detail view)

When a show is **not** broadcast-ready, the readiness computation also returns
a list of human-readable reasons. Semantics:

- If there is no `package/manifest.json`, short-circuit and return exactly
  `["not packaged"]` (the manifest-dependent checks below cannot run).
- Otherwise, **accumulate every** failing condition among the following, in
  this order:
  - `held for review` — `show.needs_review` is true.
  - `no DJ script` — `dj-notes.json` missing.
  - `no DJ audio (unvoiced)` — manifest `dj_audio` block absent.
  - `no broadcast.m3u` — `package/broadcast.m3u` missing.
  - `N of M audio files missing` — one or more `manifest.tracks[].filename`
    absent under `package/audio/` (N = missing count, M = total tracks).

A broadcast-ready show reports `broadcast-ready: yes` and no reasons; a
non-ready show reports `broadcast-ready: no` with the accumulated reasons.

## Architecture

Mirror the existing `voiced` machinery in `src/llama/catalog.py`.

- **`broadcast_readiness(ws: ShowWorkspace) -> tuple[bool, list[str]]`** — new
  function alongside `derive_voiced`. Returns `(ready, reasons)`. `ready` is
  true iff `reasons` is empty. This is the single source of truth for the
  predicate.
- **`CatalogEntry.broadcast_ready: bool`** — new field, populated in
  `iter_shows` from `broadcast_readiness(ws)[0]`. (The reasons are not stored
  on the entry; the detail view recomputes them on demand for the one show it
  is printing.)
- **`select_shows(..., broadcast_ready: bool = False)`** — new keyword. When
  true, keep only entries with `broadcast_ready is True`. (Positive-only; see
  Decisions.)

### Surfaces

All four commands thread the same single new keyword.

| Surface | Change |
|---|---|
| `llama status` | Add `broadcast-ready` to the per-show `marks` list when ready; add a `--broadcast-ready` selector flag; add a `broadcast_ready` boolean to each object in `--json` output. |
| `llama show` (list/set form, `name is None`) | Add a `--broadcast-ready` selector flag. |
| `llama show <name>` (single-show detail, `_print_show_entry`) | Add a `broadcast-ready: yes` / `broadcast-ready: no` line after the existing needs-review block; when `no`, list the reasons (one per line, indented). |
| `llama deliver` | Add a `--broadcast-ready` selector flag (via `_batch_select` / `_has_selector`). |
| `llama redo` | Add a `--broadcast-ready` selector flag (via `_batch_select` / `_has_selector`). |

Plumbing touch points, all threading one new keyword through existing
tri-state/selector idioms:

- `select_shows` — `src/llama/catalog.py`.
- `_batch_select` and `_has_selector` — `src/llama/cli.py` (shared by
  `deliver` and `redo`).
- Flag definitions and the filter wiring on `status`, `show`, `deliver`,
  `redo` in `src/llama/cli.py`.
- `marks` construction in `status` and the `--json` dict in `status`.
- `_print_show_entry` in `src/llama/cli.py` for the detail line.

## Data flow

`iter_shows` walks `shows/`, and for each show already computes `state`,
`voiced`, `overrides`, etc. It additionally calls `broadcast_readiness(ws)` and
stores the boolean on the entry. Every command that lists or selects shows goes
through `iter_shows` + `select_shows`, so the new field and filter are
available everywhere for free. The single-show detail path
(`_print_show_entry`) recomputes `broadcast_readiness(ws)` to get both the
boolean and the reasons for the one show it renders.

## Error handling

No new failure modes. `broadcast_readiness` is a pure read over files that may
or may not exist; a missing artifact is simply a non-ready reason, never an
error. It never raises. It reads `manifest.json` (already read by
`derive_voiced`) and `show.json` (already read by `derive_state`); malformed
JSON is out of scope here (handled by existing `read_model`/`read_json`
behavior, same as every other derivation).

## Testing

Offline, deterministic, against the `fake` LLM backend, following existing test
patterns (e.g. `tests/` catalog/CLI tests).

**Unit — `broadcast_readiness`:**

- A fully broadcast-ready show fixture → `(True, [])`.
- Each of the five conditions broken individually, holding the others ready,
  → `(False, [reason])` with the expected reason string:
  - held (`needs_review = true`) → `held for review`.
  - unvoiced (no manifest `dj_audio`) → `no DJ audio (unvoiced)`.
  - `broadcast.m3u` deleted → `no broadcast.m3u`.
  - one `package/audio/` file deleted → `N of M audio files missing`.
  - `dj-notes.json` missing → `no DJ script`.
  - no package at all → `not packaged`.

**CLI:**

- `llama status --broadcast-ready` lists only ready shows; a non-ready show is
  excluded.
- `llama status` prints the `broadcast-ready` mark for a ready show and not for
  a non-ready one.
- `llama status --json` includes `broadcast_ready` with the correct value.
- `llama show <name>` detail prints `broadcast-ready: yes` for a ready show, and
  `broadcast-ready: no` plus the reasons for a non-ready one.
- `llama deliver --broadcast-ready` and `llama redo --broadcast-ready` select
  the ready set (via the shared batch-select path).

## Decisions (settled)

- **Held shows are never broadcast-ready** — condition 5. "Ready" means
  genuinely airable, not merely "the files happen to exist."
- **Strict on-disk audio re-verification** for condition 1 — verify each
  manifest track's file exists under `package/audio/`, rather than trusting the
  `packaged` state. Cheap at this scale (~10² shows, a few dozen stat calls
  each) and it is the robustness the feature exists to provide.
- **Positive-only filter.** `--broadcast-ready` selects ready shows on every
  surface; there is deliberately no `--not-broadcast-ready`. The negative case
  is served by the reasons line on `llama show <name>` and by existing
  `--packaged` triage. (Add the negative later only if a real need appears.)

## Out of scope / non-goals

- No new pipeline stage or persisted state; broadcast-ready stays derived.
- No `--not-broadcast-ready` inverse filter.
- No change to what the `package` stage emits.
- No migration or schema change.
- No new dependencies.
