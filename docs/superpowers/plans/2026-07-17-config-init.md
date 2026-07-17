# Config Init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `llama config init` to seed a fully-commented config.toml of the baked-in defaults, and document that config values replace defaults rather than merging.

**Architecture:** A `DEFAULT_CONFIG_TOML` string constant in `llama/config.py` (no packaged data files, so the wheel and PyInstaller binary need no changes), kept honest by a test asserting it parses back to the built-in defaults. A new `config` typer subapp in `cli.py` (same pattern as `profile`/`ledger`) with one `init` command. Docs updates in README, the operator's guide, and CLAUDE.md.

**Tech Stack:** Python 3.11+ (`tomllib` in stdlib), pydantic v2 models, typer CLI, pytest with `typer.testing.CliRunner`.

**Spec:** `docs/superpowers/specs/2026-07-17-config-init-design.md`

## Global Constraints

- All tests offline and deterministic (`pytest -q` must pass with no network).
- Never commit audio files.
- Commit messages end with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF`
- The seeded template must state every built-in default it claims to state with the *exact* values from `config.py` — the sync test in Task 1 is the enforcement.

**Spec deviation, agreed at plan time:** the spec words the sync test as `parsed == Config()`. `Config().llm` defaults to `{}` while the template states `[llm.default] backend = "claude_cli"` explicitly, so strict equality is impossible with `[llm.default]` uncommented (which the spec also requires). The test therefore compares all fields *except* `llm` for exact equality, then asserts the template's `llm` section is exactly `{"default": ...}` and behaviorally identical to the built-in fallback via `llm_for`. This preserves the guarantee the spec is after: the seeded file, untouched, runs identically to no config file.

---

### Task 1: `DEFAULT_CONFIG_TOML` template + sync test

**Files:**
- Modify: `src/llama/config.py` (append constant at end of file, after `load_config`)
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: `Config`, existing defaults in `src/llama/config.py`.
- Produces: `llama.config.DEFAULT_CONFIG_TOML: str` — module-level constant; Task 2's CLI command and tests import it by this exact name.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py` (the file already imports `Config` from `llama.config`; add the `tomllib` and `DEFAULT_CONFIG_TOML` imports if not present):

```python
import tomllib

from llama.config import DEFAULT_CONFIG_TOML


def test_default_config_template_matches_defaults():
    # The seeded file, untouched, must behave exactly like no config file.
    parsed = Config.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    default = Config()
    assert parsed.model_dump(exclude={"llm"}) == default.model_dump(exclude={"llm"})
    # [llm.default] is written out for editability; it must be exactly the
    # built-in fallback, and the only llm entry present.
    assert set(parsed.llm) == {"default"}
    assert parsed.llm_for("interpret") == default.llm_for("interpret")


def test_default_config_template_states_selection_defaults():
    # The whole point: the GD tuning is explicit, so additive edits keep it.
    data = tomllib.loads(DEFAULT_CONFIG_TOML)
    assert data["selection"]["tapers"]["GratefulDead"] == {"miller": 2.0, "seamons": 1.0}
    assert data["selection"]["lineage_eras"] == [{
        "collection": "GratefulDead",
        "date_from": "1980-01-01",
        "date_to": "1987-12-31",
        "scores": {"matrix": 3.0, "aud": 2.0, "sbd": 1.0},
    }]
```

Note: `tests/test_config.py` imports at its top may differ — put the two new import lines with the existing imports at the top of the file, not inside functions.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: FAIL / ERROR with `ImportError: cannot import name 'DEFAULT_CONFIG_TOML'`

- [ ] **Step 3: Add the constant**

Append to `src/llama/config.py` (after `load_config`):

```python
# Seeded by `llama config init`. Kept in sync with the defaults above by
# tests/test_config.py::test_default_config_template_matches_defaults.
DEFAULT_CONFIG_TOML = """\
# llama config - seeded by `llama config init` with the baked-in defaults.
#
# IMPORTANT: a value here REPLACES its built-in default; nothing merges.
# Any [selection.tapers.*] table replaces the entire taper set, and any
# [[selection.lineage_eras]] block replaces the entire built-in era list.
# The defaults are written out below so additive edits keep them.

# root = "/path/to/workdir"        # workspace root; default ~/.llama
# delivery_path = "/station/inbox" # target for `llama deliver`
audio_format = "mp3"               # or "flac"

[llm.default]
backend = "claude_cli"             # requires the `claude` CLI on PATH
# backend = "openrouter"           # HTTP alternative; set OPENROUTER_API_KEY
# Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
# gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
# Defaults: medium for most tasks; high for deep_research and synthesize.
# A failed validation's final retry escalates one tier (pins never escalate).

# [llm.deep_research]
# backend = "claude_cli"   # pin research to the claude CLI when the default
#                          # backend is openrouter: its agentic multi-step
#                          # research is stronger, and quality is audible on air

# [llm.synthesize]
# tier = "medium"            # example: cheaper synthesis
# model = "claude-opus-4-8"  # example: exact pin, bypasses tiers

# [llm.tiers.openrouter]
# medium = "deepseek/deepseek-chat-v3"  # retarget what a tier means per backend

# [setlistfm]
# api_key = "..."          # or SETLISTFM_API_KEY env var; without a key,
#                          # set-structure recovery is LMA-descriptions only

[winnow]
max_metadata_fetch = 40    # review-fetch budget: when more survivors than
                           # this, the best-evidenced are sampled for scoring

[artists]
min_recordings = 25        # hide artists below these floors from the index
min_downloads = 50000
max_matched = 20           # LLM artist-match budget for artist-less queries

[structure]
guard_min_minutes = 150    # hold single-set shows longer than this for review
align_coverage_threshold = 0.8

# Recording selection. Taper bonuses match identifier substrings; among
# revisions by the same taper the newest gets the full bonus, the rest half.
[selection.tapers.GratefulDead]
miller = 2.0               # Charlie Miller: community gold standard
seamons = 1.0

# Era overrides for lineage scoring. Multiple [[selection.lineage_eras]]
# blocks are allowed; the first whose collection and (inclusive) date window
# match a show wins. `scores` replaces the ENTIRE lineage table (global
# base: sbd 3.0, matrix 2.5, aud 1.0, unknown 0.0) - an omitted class
# scores 0.0, so spell out every class you care about.
[[selection.lineage_eras]]
collection = "GratefulDead"   # early-80s boards are rough: MTX > AUD > SBD
date_from = "1980-01-01"
date_to = "1987-12-31"
scores = { matrix = 3.0, aud = 2.0, sbd = 1.0 }
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: all PASS

- [ ] **Step 5: Run the full offline suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/llama/config.py tests/test_config.py
git commit -m "feat: DEFAULT_CONFIG_TOML template, sync-tested against defaults

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF"
```

---

### Task 2: `llama config init` command

**Files:**
- Modify: `src/llama/cli.py` (subapp registration near line 35-38 where `profile_app`/`ledger_app` are declared; command function after the `runs` command, before `@profile_app.command("add")`)
- Test: `tests/test_cli_commands.py` (append)

**Interfaces:**
- Consumes: `llama.config.DEFAULT_CONFIG_TOML` and `llama.config.DEFAULT_ROOT` (both exist; Task 1 added the former).
- Produces: `llama config init [--stdout] [--config PATH]` CLI command. Task 3 documents it under this exact name and flag set.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_commands.py` (module already has `runner = CliRunner()`, `import llama.cli as cli`, and `from pathlib import Path`; add the new import line at the top with the existing imports):

```python
import tomllib

from llama.config import DEFAULT_CONFIG_TOML


def test_config_init_writes_template(tmp_path: Path):
    target = tmp_path / "config.toml"
    result = runner.invoke(cli.app, ["config", "init", "--config", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_text() == DEFAULT_CONFIG_TOML
    tomllib.loads(target.read_text())        # parseable
    assert str(target) in result.output
    assert "replace" in result.output        # the no-merge reminder


def test_config_init_refuses_existing(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text('audio_format = "flac"\n')
    result = runner.invoke(cli.app, ["config", "init", "--config", str(target)])
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert target.read_text() == 'audio_format = "flac"\n'   # untouched


def test_config_init_defaults_to_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_ROOT", tmp_path)
    result = runner.invoke(cli.app, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "config.toml").read_text() == DEFAULT_CONFIG_TOML


def test_config_init_stdout_prints_and_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_ROOT", tmp_path)
    result = runner.invoke(cli.app, ["config", "init", "--stdout"])
    assert result.exit_code == 0, result.output
    assert "[[selection.lineage_eras]]" in result.output
    assert not (tmp_path / "config.toml").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -q -k config_init`
Expected: 4 FAIL — typer exits 2 with "No such command 'config'" (visible in `result.output`), so the exit-code asserts fail.

- [ ] **Step 3: Implement the command**

In `src/llama/cli.py`:

(a) Extend the existing config import (currently `from llama.config import Config, load_config`):

```python
from llama.config import DEFAULT_CONFIG_TOML, DEFAULT_ROOT, Config, load_config
```

(b) Register the subapp next to the existing ones (after `ledger_app = typer.Typer(...)` / `app.add_typer(ledger_app, name="ledger")`):

```python
config_app = typer.Typer(help="Config file utilities")
app.add_typer(config_app, name="config")
```

(c) Add the command after the `runs` command, before `@profile_app.command("add")`:

```python
@config_app.command("init")
def config_init(
    stdout: bool = typer.Option(False, "--stdout",
                                help="Print the default config instead of writing a file"),
    config_path: Path = typer.Option(None, "--config",
                                     help="Target file (default ~/.llama/config.toml)"),
):
    """Seed a config file with the baked-in defaults, fully commented."""
    if stdout:
        typer.echo(DEFAULT_CONFIG_TOML, nl=False)
        return
    target = config_path or DEFAULT_ROOT / "config.toml"
    if target.exists():
        typer.echo(f"{target} already exists - not overwriting "
                   "(delete it first if you mean to reseed)", err=True)
        raise typer.Exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML)
    typer.echo(f"wrote {target}")
    typer.echo("note: config values replace built-in defaults (no merging); "
               "the defaults are written out so additive edits keep them")
```

Deliberately no `_setup()` call: the command must work with no workspace and must not load the config it is about to create.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -q -k config_init`
Expected: 4 PASS

- [ ] **Step 5: Run the full offline suite**

Run: `pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: llama config init - seed a commented config of the defaults

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF"
```

---

### Task 3: Documentation (README, workflow.md, CLAUDE.md)

**Files:**
- Modify: `README.md` (Setup section, ~line 14; end of config example, before `## Use`)
- Modify: `docs/workflow.md` (command reference, after the `llama migrate` entry ~line 331, before `### llama artists`)
- Modify: `CLAUDE.md` (Commands section, the `Run:` bullet)

**Interfaces:**
- Consumes: the `llama config init [--stdout] [--config PATH]` surface from Task 2.
- Produces: docs only.

- [ ] **Step 1: README — point Setup at the seeder**

Change the line `Optional config at `~/.llama/config.toml`:` to:

```markdown
Optional config at `~/.llama/config.toml` — seed a fully-commented copy of
these defaults with `llama config init` (`--stdout` to print instead):
```

- [ ] **Step 2: README — replace-semantics warning after the config example**

Insert immediately after the config example block (after the
`[llm.tiers.openrouter]` lines, before `## Use`):

```markdown
Config values **replace** built-in defaults — nothing merges. Adding any
`[selection.tapers.<Band>]` table replaces the whole taper set (the
GratefulDead bonuses vanish unless restated), and any
`[[selection.lineage_eras]]` block replaces the built-in era list. One
level down, an era's `scores` map replaces the whole lineage table: an
omitted class (`sbd`/`matrix`/`aud`/`unknown`) scores 0.0, not its global
value. `llama config init` writes all defaults out explicitly so additive
edits keep them.
```

- [ ] **Step 3: workflow.md — command reference entry**

Insert after the `### llama migrate [--dry-run]` entry and before
`### llama artists`:

```markdown
### `llama config init [--stdout] [--config PATH]`
Seed `~/.llama/config.toml` (or `--config PATH`) with the baked-in
defaults as a fully-commented TOML file. Refuses to overwrite an existing
file; `--stdout` prints the template instead. Exists because config
values **replace** defaults rather than merging: any
`[selection.tapers.*]` or `[[selection.lineage_eras]]` you add replaces
the built-in GD tuning unless the defaults are restated — which the
seeded file does for you.
```

- [ ] **Step 4: CLAUDE.md — command list**

In the Commands section `Run:` bullet, after
`` One-time after upgrading: `llama migrate` moves nested show dirs to `~/.llama/shows/`. ``
append the sentence:

```markdown
  `llama config init` seeds a commented config of the baked-in defaults
  (config values replace defaults; nothing merges).
```

- [ ] **Step 5: Verify docs claims against the implementation**

Run: `llama config init --stdout | head -5` (in the venv) and confirm the output starts with `# llama config`; run `pytest -q` once more.
Expected: template prints; suite passes.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/workflow.md CLAUDE.md
git commit -m "docs: document config replace semantics and llama config init

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF"
```
