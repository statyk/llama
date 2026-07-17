# Workspace UX: canonical shows library, status view, name-addressed commands

**Date:** 2026-07-17
**Status:** approved

## Problem

Every show-level operation today takes a full filesystem path
(`llama show ~/.llama/runs/2026-07-16-countryish/shows/steepcanyonrangers-2002-07-07`),
there is no way to see what exists across runs — what's packaged, held for
review, or delivered — without walking directories by hand, and re-running
part of one show's pipeline means manually deleting artifacts chosen by
reading `workspace.py`. The daily workflow the CLI should serve is
show-centric triage ("what came in overnight, what's held, ship the good
ones"), but storage and addressing are run-centric.

## Decision summary

- **Shows move to a canonical top-level library**: `~/.llama/shows/<slug>/`,
  one directory per performance, keyed by `slugify(performance_id)`
  (`performance_id = collection/date[/early|late]`, so slugs are globally
  unique by construction). Runs keep only run-level artifacts and reference
  performances through their shortlist.
- **Show state is derived, never stored**: computed from which artifacts
  exist, `needs_review`, and the ledger.
- **All commands address shows and runs by name** through one shared
  resolver: exact match, else unique substring, else fail loud listing the
  candidates. Paths remain accepted (a path is an exact match).
- **New commands**: `llama status` (global triage table), `llama runs`
  (run listing), `llama redo <show> --from <stage>` (per-show pipeline
  tail re-run), `llama migrate` (one-time layout migration).
- Approach chosen over a scan-only resolver on the current nested layout:
  the restructure makes cross-run identity physical, deduplicates artifact
  spend across runs, and removes the slug-collision problem instead of
  handling it.

## Layout

```
~/.llama/
  shows/<slug>/            # canonical per-performance workspace
    selection.json         # (stage: select)
    show.json reviews.json # (stage: gather)
    research.md            # (stage: research)
    vetting.json           # (stage: vet)
    dj-notes.json dj-notes.md   # (stage: synthesize)
    package/               # (stage: package)
    provenance.json        # NEW — who caused this show to be processed
  runs/<name>/             # run-level only
    criteria.json candidates.json shortlist.json artists.json
  ledger.jsonl profiles/ cache/ config.toml
```

`RunWorkspace.show_ws(pid)` returns `ShowWorkspace(root / "shows" / slugify(pid))`.
Stage code is already `ShowWorkspace`-relative and does not change.

Re-shortlisting a performance in a later run now lands on the same
directory, so completed stages are skipped and prior spend (research,
package) is reused automatically.

### provenance.json

Written (overwritten) by `process_show` each time a show is processed:

```json
{
  "performance_id": "SteepCanyonRangers/2002-07-07",
  "run": "2026-07-16-countryish",
  "dossier": "<shortlist rationale + external reputation, as passed to research>",
  "candidate": { ...Candidate model dump... },
  "script": true,
  "processed_at": "2026-07-17T09:00:00Z"
}
```

Purpose: lets `redo` re-run pipeline stages standalone (candidate +
dossier without loading the originating run), and lets `status`/`show`
report run provenance without scanning every shortlist.

### Migration

`llama migrate [--dry-run]`, explicit and idempotent:

1. For each `runs/*/shows/<slug>`, move the directory to `shows/<slug>`.
2. Backfill `provenance.json` from the run's shortlist entry.
3. Collision (same slug under two runs — possible for never-selected
   shows): the directory with the most pipeline progress (deepest stage
   artifact) wins; the loser is left in place under the run with a printed
   warning. Nothing is ever deleted.
4. Remove now-empty `runs/*/shows/` directories.

Until migration runs, commands that touch shows detect the legacy layout
and exit with "run `llama migrate`" rather than operating on stale paths.

## State model

Derived per show, in this precedence order:

| state | derivation |
|---|---|
| `held` | `show.json` has `needs_review: true` |
| `delivered` | ledger contains a `delivered` entry for the performance |
| `packaged` | `package/manifest.json` exists |
| `scripted` | `dj-notes.json` exists |
| `vetted` | `vetting.json` exists |
| `researched` | `research.md` exists |
| `gathered` | `show.json` exists |
| `selected` | `selection.json` exists |

`held` carries the `review_flags` as its detail. States below `packaged`
describe in-flight or abandoned shows.

## Command surface

### New

- **`llama status`** — global triage table, no arguments. Order: `held`
  (with flags) first, then `packaged` (undelivered), then in-flight
  states, then the most recent few `delivered` (`--all` for everything).
  Columns: show slug, state, artist, date, run (from provenance), note
  (flags / package age). Filters: `--held`, `--packaged`, `--run <name>`,
  `--artist <substr>`. `--json` emits the underlying records for
  scripting.
- **`llama runs`** — one line per run: name, criteria summary, show
  counts by state.
- **`llama redo <show> --from <stage>`** — `--from` is required; stages
  are `select|gather|research|vet|synthesize|package`. Drops that stage's
  artifacts and everything downstream, then re-runs the show's pipeline
  tail using `provenance.json` (no run replay; other shows untouched).
  **`research.md` is preserved by default** — it is the expensive
  high-tier call and depends mostly on performance identity; the vet
  stage's grounding checks (songs, dates, set count) are the safety net
  if a structural fix leaves it slightly stale. `--with-research` also
  drops it; `--from research` names it explicitly. Script setting comes
  from `provenance.json` (recorded at process time), overridable with
  `--script/--no-script` — redo never needs the originating run directory
  to still exist.
- **`llama migrate [--dry-run]`** — as above.

### Changed

- **`llama show <name>`** — name-addressed; keeps state/flags/`--clear`,
  adds a stage table (artifact, present/missing, mtime age) and the
  package path.
- **`llama deliver <name>`** — name-addressed. The ledger entry's `run`
  field now comes from `provenance.json` (it was previously inferred from
  the show path, which the new layout no longer encodes).
- **`llama run <name>` / `llama review <name>`** — resolve run names via
  the resolver (`llama run countryish`).
- All output that mentions a show or run also prints its path, so manual
  filesystem drill-down stays easy.

### Name resolution

One resolver, shared: exact slug/name → unique substring match →
otherwise print all matches and exit 1. Non-TTY behavior is identical
(no interactive picker). An argument that is an existing path bypasses
resolution.

## Internals

- **`catalog.py`** (new) owns show/run discovery: `resolve_show(name)`,
  `resolve_run(name)`, `iter_shows()` yielding
  `(ShowWorkspace, state, flags, provenance)`, state derivation, and the
  legacy-layout detection. Scan-on-demand, no index file — at this scale
  (~10² shows) a walk is milliseconds. CLI commands consume the catalog;
  pipeline stages do not.
- **`ledger.record` idempotence**: skip appending when an entry with the
  same `(performance_id, status, run)` already exists. Ends duplicate
  `selected` lines on run replays; `status` reads the ledger and should
  see clean data.
- `process_show` writes `provenance.json` before the select stage runs.

## Error handling

- Resolver ambiguity/miss: list candidates (or "no match"), exit 1.
- `redo` on a show with no `provenance.json` (pre-migration artifact or
  hand-built dir): exit with a message naming the missing file and the
  migrate/backfill remedy.
- `migrate` collisions: warn and leave the loser in place (see above).
- Legacy layout detected by any show command: exit with "run
  `llama migrate`".

## Testing

Offline, per project convention (fake LLM provider, tmp_path workspaces):

- State derivation: artifact-combination matrix → expected state.
- Resolver: exact, unique substring, ambiguous, no match, path passthrough.
- Migration: fixture tree with two runs including one slug collision;
  idempotence (second run is a no-op); provenance backfill content.
- `redo`: drops the right artifacts per `--from`, preserves `research.md`
  by default, drops it with `--with-research`, re-runs the tail via fake
  provider, errors without provenance.
- Ledger idempotence: replay does not duplicate entries.
- CLI: typer-runner tests for `status` (ordering, filters, `--json`),
  `show`, `deliver`, `runs`, `redo`, `migrate --dry-run`.

## Documentation

- CLAUDE.md command list; `docs/station-brief.md` command surface;
  `--help` text for all new/changed commands.

## Out of scope

- Tab completion, interactive pickers, TUI dashboards.
- Any change to run-level pipeline semantics (search/winnow), profiles,
  or the ledger format beyond the idempotence guard.
- Persistent catalog/index files.
