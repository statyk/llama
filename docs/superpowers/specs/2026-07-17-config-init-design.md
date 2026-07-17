# Config seeding: `llama config init` + replace-semantics documentation

**Date:** 2026-07-17
**Status:** approved

## Problem

Config defaults are per-field pydantic `default_factory`s, which only apply
when the key is absent from the TOML. Supplying any value for a field
replaces that field's default wholesale — there is no merging. Two places
this bites hard:

- Adding `[selection.tapers.<AnyBand>]` replaces the entire tapers dict,
  silently dropping the built-in GratefulDead miller/seamons bonuses.
- Writing any `[[selection.lineage_eras]]` block replaces the entire
  default list, silently dropping the built-in early-80s GD era.

A related trap one level down: a matching era's `scores` map replaces the
whole lineage score table for that show — a lineage class omitted from
`scores` gets 0.0, not the global base value.

None of this is documented, and there is no way to obtain a config file
that states the defaults explicitly so they survive additive edits.

## Decision

Keep replace semantics (what you write is exactly what runs; merge
semantics would make defaults invisible and offer no way to remove one).
Instead:

1. **`llama config init`** seeds a fully-commented config file containing
   the baked-in defaults, so "add a taper" becomes "edit the seeded list."
2. **Document the replace rule** in the README, the operator's guide, and
   inside the seeded template itself, at the point where it bites.

## Design

### Template

- Module-level string constant `DEFAULT_CONFIG_TOML` in `llama/config.py`.
  A string constant, not a packaged data file: no wheel package-data or
  PyInstaller spec changes.
- Content mirrors the README config example, fully commented.
  - **Commented out** (no active default to state, or computed at runtime):
    `root`, `delivery_path`, `[setlistfm] api_key`, per-task LLM sections
    (`[llm.deep_research]`, `[llm.synthesize]`, `[llm.tiers.*]`).
  - **Uncommented with real default values:** `audio_format`,
    `[llm.default] backend`, `[winnow] max_metadata_fetch`,
    `[artists] min_recordings/min_downloads/max_matched`,
    `[structure] guard_min_minutes/align_coverage_threshold`,
    `[selection.tapers.GratefulDead]`, and the built-in GratefulDead
    `[[selection.lineage_eras]]` block.
- Comments explain, in place:
  - Above the `[selection]` tables: overriding a field replaces its whole
    value — restate defaults you want to keep.
  - Next to `scores`: the map replaces the whole lineage table
    (`sbd`/`matrix`/`aud`/`unknown`); an omitted class scores 0.0.
  - Multiple `[[selection.lineage_eras]]` blocks are allowed; first
    matching (collection + inclusive date window) wins.

### Sync guarantee

Test: `Config.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML)) ==
Config()`. The seeded file, untouched, must produce exactly the baked-in
defaults; a future default change that forgets the template fails the
suite. (Commented-out keys are invisible to the parser, so they cannot
drift the comparison; their continued accuracy is prose, reviewed like
any doc.)

### CLI

New `config` subapp (pattern-matching `profile`/`ledger`):

```
llama config init [--stdout] [--config PATH]
```

- Target: `--config` if given, else `~/.llama/config.toml` (the same
  option other commands use to point at the config file).
- Target exists → error message and exit 1. No overwrite flag: a config
  file is hand-edited state; delete it yourself if you mean it.
- Otherwise: create parent dirs, write the template, print the path and a
  one-line reminder that edits replace defaults rather than merging.
- `--stdout`: print the template and exit; no file checks, no writes.

### Documentation

- **README**: Setup section points at `llama config init` for seeding; a
  short warning paragraph after the config example states the replace
  rule (tapers dict, lineage_eras list, era `scores` table) and the
  omitted-class-scores-zero gotcha.
- **docs/workflow.md**: command-reference entry for `llama config init`.
- **CLAUDE.md**: add `llama config init` to the command list.

## Testing

Offline, per project convention:

- Template/defaults sync test (above).
- CLI (typer runner): writes a parseable file at the default location
  (tmp root via `--config`); refuses with exit 1 when the target exists;
  `--stdout` prints the template and writes nothing; written file content
  equals `DEFAULT_CONFIG_TOML`.

## Out of scope

- Merge semantics or any change to config parsing.
- `config show` / other `config` subcommands (the subapp leaves room).
- Workspace initialization beyond the config file.
