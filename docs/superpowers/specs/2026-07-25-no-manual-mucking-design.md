# Operate without hand-editing ~/.llama: track view, metadata overrides, presenter & profile commands

**Status:** approved design, pre-plan
**Date:** 2026-07-25
**Goal:** Close the remaining cases where an operator must open a file under
`~/.llama/` by hand. Four independent parts under one theme. No backward
compatibility required.

## Motivation

The show-management tooling (shipped 2026-07-25) made held-show *resolution*
app-driven via `overrides.json`, but real use surfaced gaps:

- To exclude junk tracks (e.g. gd 1972-08-27's between-set stage
  announcements) you must know their **source filenames**, which the app never
  shows outside the interactive picker — so you `ls ~/.llama/shows/.../` or
  read `show.json`.
- Other legitimate corrections — a mangled **venue** (`"Austin,TX"`), an
  **unresolved/wrong track title**, a **bad set-break** alignment, a wrong
  **date** — have no override at all, so you hand-edit `show.json` (which a
  re-gather then overwrites).
- **Presenters** are created only by hand-writing `presenters/<id>.toml`.
- A profile's **pinned artist roster** can only be changed by editing
  `profiles/<name>.toml`.

`config.toml` is deliberately out of scope: it is ordinary configuration,
bootstrapped by `llama config init`, and hand-editing it is expected.

## Background anchors (verified)

- `Overrides` model (`src/llama/models.py:188`): today `exclude: list[str]`,
  `narration: str="full"`. `ShowWorkspace.overrides` +
  `workspace.read_overrides` return defaults when absent.
- `run_gather` (`src/llama/stages/gather.py`): reads overrides for `exclude`
  after `filter_files` (:119); `tracks = resolve_titles(...)` (:149); per-track
  `set`/`segue` + `breaks = set_breaks(tracks)` (:192-194); venue/city
  enrichment + flags computed (:225-260); `Show(...)` constructed (:263+) with
  `date=candidate.date`, `venue`, `city`, `venue_source`, `set_breaks=breaks`.
  Flag strings: `"unresolved track titles"` (:238), `"low-confidence structure
  alignment"` (:190), `"venue mismatch: ..."`.
- `show` command (`src/llama/cli.py:604`): single-show + set form; resolution
  flags `--exclude/--include/--vague/--full/--clear/--apply`; helpers
  `_edit_overrides`, `_clear_hold`, `_print_show_entry`, `_pick_excludes`
  (already prints a numbered track list in the interactive picker),
  `_redo_show`.
- `Presenter` model + `save_presenter(root, presenter)` /`load_presenter`
  (`src/llama/presenters.py`): fields `id,name,sex,voice?,voice_clone?,
  character,bed?`; validator requires exactly one of voice/voice_clone.
  `save_presenter` already exists and is currently unused by any CLI command.
- `profile_add` (`src/llama/cli.py:1031`) pins artists via
  `resolve_artists(load_or_build(ia, cache), names)` → `Criteria.artists`
  (`list[str]` of identifiers); `save_profile`/`load_profile`
  (`src/llama/profiles.py`); `Profile.criteria.artists`.

## Part A — See tracks, exclude by number

### `llama show <s> --tracks`

A new flag on `show` that prints the numbered track list (in addition to the
normal inspection, when `show.json` exists):

```
tracks:
   1. set 1   Bertha                       tags       gd72-08-27d1t01.mp3   6:58
   ...
   9. set 1   (unknown)                    unresolved gd72-08-27d2t01.mp3   1:12
```

Columns: track number (`Track.index`), `set`, `title` (or `(unknown)` when
`title_source == "unresolved"`), `title_source`, `filename`, `M:SS` duration.
The interactive picker (`_pick_excludes`) is refactored to render the same
listing (one formatter, `_format_tracks(show)`), so viewing and picking match.

`--tracks` composes with pure inspection (`llama show <s> --tracks`) and is a
no-op annotation on action invocations (it does not change what an action
prints).

### `--exclude` / `--include` accept track numbers

Both options already accept repeatable values; extend each value to be either a
**track number** or a **filename**, and to accept comma-separated groups
(`--exclude 9,10` ≡ `--exclude 9 --exclude 10`). Resolution happens in the
`show` command before writing overrides:

- A token that is all digits is a track number → resolved to that track's
  `filename` via `show.json` (error if out of range).
- Any other token is treated as a filename verbatim (today's behavior).

`overrides.exclude` continues to store **filenames** (recording-specific,
stable, matched by gather). Requires `show.json` to resolve numbers; if absent,
error `"--exclude by number needs show.json; reference the file by name"`.

## Part B — show-metadata overrides

`overrides.json` grows four optional fields (all default to "no override", so
absent/old files are unchanged):

```python
class Overrides(BaseModel):
    exclude: list[str] = []
    narration: str = "full"
    venue: str | None = None
    city: str | None = None
    date: str | None = None                       # YYYY-MM-DD
    titles: dict[int, str] = {}                   # track number -> forced title
    set_breaks: list[int] | None = None           # track numbers a break falls after
```

(`titles` keys are ints in the model; JSON object keys are strings — the reader
coerces, matching how the field is authored by the CLI.)

### gather consumes them (all route to `redo --from gather`)

Applied inside `run_gather`, at the natural points, so the existing flag checks
see corrected data and don't fire:

- **titles** — after `resolve_titles(...)` (:149): for each `{n: title}`, set
  `tracks[n-1].title = title`, `tracks[n-1].title_source = "override"`. The
  later `"unresolved track titles"` check (:238) then only fires for tracks
  *still* unresolved, so filling every gap self-clears the hold.
- **set_breaks** — when set, bypass the deterministic/LLM alignment block
  entirely: build per-track `set` labels directly from the override (tracks
  `1..b1` → set `"1"`, `b1+1..b2` → `"2"`, …) and set `breaks = overrides.
  set_breaks`. This means the `"low-confidence structure alignment"` /
  multi-set-vs-flat flags are never appended (the operator has defined the
  structure), and `structure_guard` runs against the override. `StructureInfo.
  alignment = "override"`. (v1: numbered sets only — no `encore` designation.)
- **venue / city** — at Show construction: when `overrides.venue` is set, use
  it, set `venue_source = "override"`, and skip jerrybase venue enrichment and
  the `"venue mismatch"` flag (the operator's value wins, uncontested).
  `overrides.city` overrides `city` likewise.
- **date** — when set, `Show.date = overrides.date`, `date_source =
  "override"`, `item_date = candidate.date` (original preserved), performance
  identity (`performance_id`) unchanged. Cross-stage: `vet`'s existing
  date-adoption (which replaces a `YYYY-01-01` placeholder with a unanimous
  research date) must **skip a show whose `date_source == "override"`**, so a
  `redo --from gather` (which re-runs research/vet) can't clobber the manual
  date. This is the one change outside gather/show for Part B.

A track-number in `titles`/`set_breaks` that is out of range is a gather-time
`LlamaError` (loud, not silent), consistent with exclude's no-match warning
being tolerant but index refs being exact.

### `show` command flags

All write `overrides.json` via `_edit_overrides` (extended) and print
`next: llama redo <s> --from gather` (or run it with `--apply`); none clears
the hold directly — a clean re-gather self-clears whatever flag the correction
resolves (same model as `--exclude`):

- `--set-venue TEXT`, `--set-city TEXT`, `--set-date YYYY-MM-DD`
- `--title N=TITLE` (repeatable; `N` is a track number) → `overrides.titles`
- `--clear-title N` (repeatable) removes an entry from `overrides.titles`
- `--set-breaks "9,17"` (comma list of track numbers) → `overrides.set_breaks`;
  `--clear-set-breaks` removes the override
- The confirmation line names what changed (e.g.
  `<slug>: title 9 = "Playin' in the Band"`), matching Part-A/existing
  concise-confirmation style (no stale inspection dump).

These compose with `--exclude`/`--vague`/etc. in one invocation; the printed
next stage is the earliest affected (`gather` for any metadata/exclude edit,
else `synthesize` for narration, else `package`).

## Part C — `llama presenter` commands

A new `presenter` sub-app (help panel "Discover & process"), wrapping the
existing `save_presenter`/`load_presenter`:

- `presenter add <id> --name TEXT --sex TEXT (--voice TEXT | --voice-clone
  PATH) (--character TEXT | --character-file PATH) [--bed PATH] [--force]`
  — builds and validates a `Presenter` (the model's voice-XOR-clone validator
  is reused; a bad combo fails loudly), then `save_presenter`. Refuses to
  overwrite an existing `presenters/<id>.toml` unless `--force`. `--character`
  and `--character-file` are mutually exclusive and one is required;
  `--character-file` reads the file's text as the persona. Prints
  `saved: <path>`.
- `presenter list` — one line per `presenters/*.toml`: id, name, sex, and
  voice or `clone:<path>`; `(invalid: <reason>)` for a file that fails to load
  rather than aborting the listing.
- `presenter show <id>` — the resolved fields, with the full character text.

No `presenter remove` (deleting a file is `rm`; out of scope, and profiles may
reference it). Editing an existing presenter is `presenter add --force` (or the
TOML is still hand-editable — character edits stay "live").

## Part D — `llama profile artists <name>`

- `profile artists <name>` (no `--set`) prints the profile's current pinned
  roster from `Criteria.artists` (or "no pinned roster (uses the LLM matcher)"
  when empty).
- `profile artists <name> --set "A, B, C"` re-validates the names against the
  artist index (`resolve_artists(load_or_build(...), names)`, exactly as
  `profile add --artists` does — typos/ambiguity fail immediately), rewrites
  `Criteria.artists`, and `save_profile`. Prints the pinned result. `--set ""`
  clears the roster (reverts to the LLM matcher).

## Non-goals

- No `config.toml` editor (ordinary config; `config init` bootstraps it).
- No `presenter remove` / no `profile remove-artist` granular ops (re-set the
  whole list; delete a presenter file by hand).
- `--set-breaks` does not designate an `encore` set in v1 (numbered sets only).
- No migration: all new `overrides.json` fields are additive and optional.
- Overrides remain recording-specific by filename (exclude) / track-number
  (titles, set_breaks); switching recordings (`redo --from select`) may strand
  number/-file refs — gather errors loudly on an out-of-range number and warns
  on a no-match filename, so this surfaces rather than silently misapplying.

## Testing (offline, deterministic, fake backend + gd73 fixture)

- **Overrides model:** new fields round-trip; string JSON keys for `titles`
  coerce to int; absent file → all-default.
- **show --tracks:** renders the numbered list with the shared formatter;
  `(unknown)` for unresolved; `--tracks` on a show without `show.json` errors
  like the rest of `show`.
- **exclude by number:** `--exclude 6` resolves to track 6's filename in
  `overrides.exclude`; comma + repeated forms; out-of-range → error; a
  filename token still works; no `show.json` → error.
- **gather metadata overrides:** titles fill unresolved slots
  (`title_source="override"`) and drop the `"unresolved track titles"` flag;
  `set_breaks` override sets numbered sets + `StructureInfo.alignment=
  "override"` and suppresses the alignment flag; venue/city/date overrides land
  on `Show` with the right `*_source`, `item_date` preserved, and no
  venue-mismatch flag; out-of-range title/break index → `LlamaError`.
- **show metadata flags:** each writes the right `overrides.json` field, prints
  a concise confirmation + `--from gather`, does not clear the hold; `--apply`
  runs the redo; `--clear-title`/`--clear-set-breaks` remove entries.
- **presenter commands:** `add` writes a valid TOML (voice XOR clone enforced;
  `--character-file` read); refuses overwrite without `--force`;
  `--character`+`--character-file` together errors; `list` includes an invalid
  file's marker without aborting; `show` prints the character.
- **profile artists:** `--set` re-validates (bad name fails) and rewrites
  `Criteria.artists`; no-arg prints the roster; `--set ""` clears it.
- **help:** the `presenter` group appears in the "Discover & process" panel.
