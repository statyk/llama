# Show-management tooling: overrides, resolutions, voiced-state, bulk ops

**Status:** approved design, pre-plan
**Date:** 2026-07-25
**Scope:** on-disk show management — resolving held shows, a durable
per-show overrides input, a "voiced" dimension in the triage view, bulk
operations over filtered show sets, and a `--help` reordering. No backward
compatibility is required (single operator, purge-and-rerun is acceptable).

## Motivation

Day-to-day operation is show-centric, but the tooling for *acting on shows
already on disk* is thin. Two real cases motivate the work:

- **gratefuldead-1972-08-27** — a famous, well-documented show, held only
  because between-set stage-announcement tracks exist on the tape that no
  setlist names, so structure alignment is shaky. The fix is real metadata
  cleanup: drop those tracks and re-derive. Today that means hand-editing
  `show.json` (delete track objects, renumber `index`, fix `set_breaks`,
  clear `needs_review`) — fiddly and error-prone.
- **delmccouryband-2003-04-19** — a good show with an *irreducibly* unknown
  setlist: the two LMA copies have incomplete, mutually conflicting
  tracklists. The data cannot be corrected. The right outcome is to ship it
  with a script that stays general — names no songs it can't confirm, asserts
  no set structure, says nothing false.

These are two of **three ways to resolve a held show**, only the third of
which exists today:

| Resolution | Meaning | Mechanism |
|---|---|---|
| **Correct** | fix the underlying data, re-derive | overrides `exclude` + `redo --from gather` (flag self-clears) |
| **Accept-as-vague** | data is irreducibly uncertain; narrate around it | overrides `narration=vague` + `redo --from synthesize` |
| **Overrule** | the flag is a false alarm; ship as-is | `show --clear` (unchanged) |

## Background: how state and re-runs already work (grounding)

- Show state is **derived, never stored**: `catalog.derive_state`
  (`src/llama/catalog.py:56`) reads which artifacts exist plus the ledger.
  Precedence: `held > delivered > packaged > scripted > vetted > researched
  > gathered > selected`. `held` beats `packaged`/`delivered` — a show can be
  both packaged and held, and reports as held.
- Stages **skip work whose output exists**. `run_gather` returns the existing
  `show.json` untouched unless forced (`gather.py:111`); `run_package` returns
  early if `manifest.json` exists (`package.py:251`). `redo --from <stage>`
  drops that stage's artifacts *and everything downstream*
  (`workspace.drop_stage_artifacts`) then re-runs the tail via
  `process_show`, so earlier artifacts (including a hand-edited `show.json`)
  are reused.
- `process_show` re-reads `show.json` after vet, after synthesize, and after
  package, and **halts if `needs_review` is true** (`pipeline.py:99-126`).
  This is why any resolution must end with the hold cleared — either
  self-cleared by a clean re-gather, or explicitly by the resolution flag.
- `build_manifest` trusts `show.set_breaks` and the track list verbatim
  (`manifest.py:19`); `run_package` downloads exactly the files in
  `show.tracks` (`package.py:262`). So a corrected `show.json` fully
  determines the package.

## Part 1 — The overrides primitive

### `shows/<slug>/overrides.json`

A new, **hand-authored, durable** per-show file — the single home for
operator inputs that must survive re-derivation. `show.json` stays purely
derived and safe to regenerate.

Model (new `Overrides` in `src/llama/models.py`):

```python
class Overrides(BaseModel):
    exclude: list[str] = Field(default_factory=list)   # source filenames to drop
    narration: str = "full"                            # "full" | "vague"
```

- `ShowWorkspace` gains `self.overrides = dir / "overrides.json"`
  (`src/llama/workspace.py`).
- A read helper returns `Overrides()` (defaults) when the file is absent, so
  every consumer has a total function. Absent file ≡ no overrides.
- `overrides.exclude` names **source filenames** (matching `Track.filename` /
  the archive item's file names), which is what gather works from. Excludes
  are therefore recording-specific: after `redo --from select` picks a
  different recording, stale entries simply match nothing (see gather's
  no-match warning below). This is acceptable and documented, not a bug.

### gather honors `exclude`

In `run_gather`, immediately after `filter_files(...)` produces `kept`
(`gather.py:119`), drop any file whose name is in `overrides.exclude` from
`kept` before setlist ranking, title resolution, and alignment. Excluded
files are appended to the `excluded` record with reason `"operator-excluded"`
so `show.json`'s `excluded_files` still documents them.

Because the drop happens before `len(kept)` is used for setlist ranking and
alignment, structure re-derives clean and contiguously indexed — no manual
renumbering. When the well-documented show now aligns, `flags` comes back
empty and gather writes `needs_review=False` on its own
(`gather.py:267`) — **the hold self-clears**.

If an `exclude` entry matches no kept file, gather logs a warning (`warning:
overrides.exclude entry 'X' matched no file`) and continues — guards against
typos and stale recording-specific entries; never a hard failure.

### synthesize honors `narration`

`run_synthesize` reads `overrides.narration`. When `"vague"`, it passes a
non-empty `narration_note` into the prompt inputs; when `"full"` (or absent)
the note is empty and behavior is byte-for-byte unchanged.

- Add a `{{narration_note}}` slot to `src/llama/prompts/synthesize.md`
  (placed after the three hard spoken-delivery rules, before `Show data`).
  The empty-string fill must leave the rendered prompt identical to today for
  the `full` case — update/extend the golden prompt test accordingly.
- The vague note instructs: *the setlist for this show is uncertain and
  incomplete — do not name specific songs, do not assert a set count or set
  structure, and state nothing as fact that the show data does not confirm;
  speak to the band, the era, the venue, the performance, and its
  reputation.*
- `factual_guard` is **unchanged**: it forbids naming songs absent from the
  track list but never *requires* naming any, so a song-free script with an
  empty `mentioned_songs` passes. The per-set `set_intros` scaffolding is
  still produced (one generic lead-in per non-encore set) — vague affects
  *content*, not the segment structure.
- `narration` is orthogonal to presenter: it composes with both
  `NEUTRAL_STYLE` and `persona_style` (a hosted show can still be vague).

### `llama show` resolution flags

`llama show <show>` grows three write-then-print flags. Each updates
`overrides.json` and/or `show.json` and prints the exact next `redo` command;
**none fires the redo** (mirrors today's `--clear`, keeping the operator in
control of paid/LLM re-runs).

| Flag | Effect | Clears hold? | Prints next step |
|---|---|---|---|
| `--exclude FILE...` | append files to `overrides.exclude` | no — re-gather decides | `llama redo <show> --from gather` |
| `--include FILE...` | remove files from `overrides.exclude` | no | `llama redo <show> --from gather` |
| `--vague` | set `overrides.narration="vague"` **and** clear `needs_review`/`review_flags` | yes (operator judgment to ship vaguely) | `llama redo <show> --from synthesize` |
| `--full` | set `overrides.narration="full"` | no | `llama redo <show> --from synthesize` |
| `--clear` *(unchanged)* | clear `needs_review`/`review_flags` | yes | `llama redo <show> --from package` |

Rationale for the hold-clearing asymmetry:

- `--exclude` does **not** pre-clear: correctness is decided by the
  re-gather, which self-clears only if the structure actually comes out
  clean. If it doesn't, the show stays correctly held.
- `--vague` **does** clear: accepting irreducible uncertainty is the
  operator's judgment call, exactly like `--clear`, but additionally records
  *why* (narration guidance) so the next re-script honors it.

`--exclude` and `--vague`/`--clear` may be combined in one invocation
(e.g. exclude some tracks *and* accept the rest as vague); the printed next
step is the earliest applicable stage (`gather` if any exclude changed, else
`synthesize` for narration, else `package`).

`llama show` output gains an **Overrides** line showing the current
`exclude` list and `narration` when non-default, so the authored state is
always visible alongside the derived stage table.

## Part 2 — The "voiced" dimension in `status`

"Voiced" is orthogonal to the lifecycle ladder (a packaged or delivered show
may or may not carry DJ audio), so it is an **annotation**, not a new state.

- Derivation (add to `catalog.CatalogEntry` as `voiced: bool | None`):
  voicing is only meaningful once a package exists. For a show with
  `package/manifest.json`, `voiced` is `True` iff the manifest's `dj_audio`
  block is non-null (authoritative; falls back to a non-empty
  `package/dj-audio/` directory), else `False`. For a pre-package show,
  `voiced` is `None` (not applicable).
- `--voiced` matches `voiced is True`; `--unvoiced` matches `voiced is False`.
  Both therefore **imply a package exists** — pre-package shows (`voiced is
  None`) match neither, so `llama redo --unvoiced --from package --voice`
  targets exactly the packaged-but-silent shows with no surprise pre-package
  work. This is a pure predicate that composes (AND) with the other
  selectors; no implicit `--packaged` pairing is needed.
- The plain-text listing shows a `voiced` marker and any active override
  (`vague`, `Nx` excluded) inline under/next to the row.
- `--json` records gain `voiced: bool | null` (null = pre-package) and
  `overrides: {exclude, narration}`.

## Part 3 — Shared selectors and bulk operations

### Selector vocabulary (shared)

A single filter vocabulary is reused by `status`, `triage`, and the batch
forms of `redo`/`deliver`, so selection is learned once:

- `--held`, `--packaged`, `--voiced`, `--unvoiced`
- `--state NAME` (any derived state: `selected|gathered|researched|vetted|
  scripted|packaged|delivered|held`)
- `--artist SUBSTR`, `--run NAME`

Multiple selectors combine with **AND**. Selection is implemented once in
`catalog` (a `select_shows(entries, **filters)` helper) and shared, rather
than re-filtered per command as `status` does today (`cli.py:660-667`); the
existing `status` filters move onto it.

### 3a. `llama triage [selectors]` — interactive walkthrough (new)

The interactive form of the three-resolutions model. Defaults to `--held`;
selectors narrow the set (e.g. `triage --held --artist grateful`).

For each show in turn it prints identity, derived state, the review flags,
and the **numbered track list**, then prompts:

```
[1/4] gratefuldead-1972-08-27   held
  - low-confidence structure alignment
   1. Set 1  Bertha                     gd72-08-27d1t01.mp3
   ...
   9. Set 1  (crowd/announcement)       gd72-08-27d1t09.mp3
  [e]xclude tracks  [v]ague  [c]lear  [s]kip  [q]uit ?
```

- **[e]xclude** — pick tracks by index (the walkthrough is the nicest home
  for a picker; the operator never types filenames), writes
  `overrides.exclude`, and runs `redo --from gather`.
- **[v]ague** — writes `overrides.narration=vague`, clears the hold, runs
  `redo --from synthesize`.
- **[c]lear** — clears the hold, runs `redo --from package`.
- **[s]kip** / **[q]uit** — next show / stop.

Unlike the `show` flags (print-next-step), `triage` **runs** the chosen
resolution inline — the per-show prompt *is* the confirmation, and running
each fix in the loop is the entire point of a walkthrough. The result
(re-packaged / still-held / failed) is printed before advancing.

### 3b. Batch `redo` / `deliver` via selectors

`redo` and `deliver` accept selectors *instead of* a single-show positional
argument, so any action batches without a new verb (no `llama voice` — batch
voicing is `redo --unvoiced --from package --voice`):

```
llama redo --unvoiced --from package --voice     # voice every unvoiced packaged show
llama deliver --packaged                          # deliver everything ready
```

Semantics:

- Exactly one of {positional `<show>`, ≥1 selector} is required; mixing them
  is an error.
- The batch prints a **plan** (the resolved show list + the action) and
  prompts `Proceed? [y/N]`; `--yes` skips the prompt for scripting/cron.
- **Held shows are excluded** from batch actions unless `--held` is explicitly
  among the selectors — held shows aren't ready to act on. (Resolving held
  shows is `triage`'s job.)
- Per-show failures don't abort the batch: each is reported (`FAILED
  <show>: …`) and the sweep continues, matching `run`'s per-show failure
  isolation.

## Part 4 — `--help` reordering

Commands are currently listed in definition order (Typer default). Group them
into labeled panels via `rich_help_panel` on each command/sub-app:

- **Discover & process:** `find`, `artists`, `profile`, `run`, `review`
- **Inspect & triage:** `status`, `runs`, `show`, `triage`
- **Act on shows:** `redo`, `deliver`
- **Housekeeping:** `ledger`, `config`, `version`

Purely presentational; no behavior change.

## Non-goals

- No graduated narration levels (per-set, "titles-uncertain-but-structure-
  known"). `narration` is binary `full|vague`; revisit only if a real show
  needs the middle ground.
- No auto-detecting overrides changes to pick a redo stage (the rejected
  "smart redo"); the operator runs the printed `redo`.
- No `--force`-through-processing for held shows; the hold still gates.
- No new bulk verb beyond `triage`; batch actions ride existing verbs.
- No migration or legacy handling: overrides.json is purely additive; a show
  without one behaves exactly as today.

## Testing

Offline, deterministic, `fake` backend, against the gd73-06-10 fixture and
synthetic shows:

- **Overrides model + workspace:** absent file → defaults; round-trip.
- **gather exclude:** given `overrides.exclude`, the named file is dropped
  from `kept`, structure re-derives with contiguous indices, and a
  previously-flagged synthetic show comes back `needs_review=False`; a
  non-matching exclude entry logs a warning and is a no-op.
- **synthesize narration:** `full` renders the prompt byte-for-byte as today
  (golden test); `vague` injects the note and a song-free `DJNotes` passes
  `factual_guard`.
- **show flags:** `--exclude/--include` edit `overrides.json` and print the
  gather next-step without clearing the hold; `--vague` sets narration and
  clears the hold and prints the synthesize next-step; `--full` resets;
  `--clear` unchanged.
- **catalog voiced + select_shows:** `voiced` derivation from manifest
  `dj_audio`; each selector and their AND-combination.
- **status:** `--voiced/--unvoiced/--state` filters; voiced/override
  annotations in text and `--json`.
- **triage:** scripted stdin drives exclude/vague/clear/skip/quit; asserts
  the right overrides written and the right stage re-run (via a stubbed
  `process_show`).
- **batch redo/deliver:** selector resolves the expected set, held excluded
  unless `--held`, plan+confirm honored, `--yes` skips, per-show failure
  isolation.
- **help panels:** each command advertises its `rich_help_panel`.
