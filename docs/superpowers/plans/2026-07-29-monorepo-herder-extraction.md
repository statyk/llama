# Monorepo Restructure + Herder Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the repo into a monorepo (`packages/llama/`, `packages/herder/`) and extract `src/llama/llm/` into the shared `herder` package, with zero behavior change.

**Architecture:** Three in-place de-couplings first (errors, prompts, settings) so the LLM layer stops referencing llama internals while every commit stays green; then a pure `git mv` restructure of llama; then the extraction, which at that point is a move + rename. Spec: `docs/superpowers/specs/2026-07-29-monorepo-herder-extraction-design.md`.

**Tech Stack:** Python ≥3.11, hatchling, pytest, pydantic v2, httpx. No new dependencies.

## Global Constraints

- License `GPL-3.0-or-later` on every package; `requires-python = ">=3.11"`.
- **No new third-party dependencies.** herder's deps are exactly `pydantic>=2.7`, `httpx>=0.27`.
- All file moves use `git mv` (history preservation).
- Full suite green after every task: `pytest -q` from the repo root (1027+ tests, offline).
- **No behavior change**: CLI output, stage semantics, tier-resolution semantics, and error rendering are identical before and after. Tests are updated only where they touch moved/renamed internals.
- herder never imports llama (guard test enforces).
- Commit after every task; messages follow the repo's `feat:`/`refactor:`/`docs:` convention.

---

### Task 1: De-couple errors — LLM layer gets its own exception base

The LLM layer's `LLMError` currently subclasses `llama.errors.LlamaError` (`src/llama/llm/provider.py:6`), and the CLI boundary relies on that. Make it independent; teach the boundary to catch both.

**Files:**
- Modify: `src/llama/llm/provider.py`
- Modify: `src/llama/cli.py` (main_cli, ~line 2362)
- Modify: `tests/test_errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `LLMError(Exception)` — independent base for the LLM layer (renamed to `HerderError` in Task 5). `TaskFailed`/`ResearchNotSupported` unchanged as its subclasses. `main_cli` catches `(LlamaError, LLMError)` identically.

- [ ] **Step 1: Update the taxonomy test to the new hierarchy (failing first)**

In `tests/test_errors.py`, replace the assertions that `LLMError`/`TaskFailed`/`ResearchNotSupported` subclass `LlamaError` with:

```python
import pytest

from llama.errors import LlamaError
from llama.llm.provider import LLMError, ResearchNotSupported, TaskFailed


def test_llm_errors_independent_of_llama_taxonomy():
    # The LLM layer is bound for extraction into the shared herder package:
    # its exceptions must not depend on llama's taxonomy.
    assert not issubclass(LLMError, LlamaError)
    assert issubclass(TaskFailed, LLMError)
    assert issubclass(ResearchNotSupported, LLMError)


def test_main_cli_renders_llm_error(monkeypatch, capsys):
    import pytest
    from llama import cli

    def boom():
        raise TaskFailed("model exploded")

    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as exc:
        cli.main_cli()
    assert exc.value.code == 1
    assert "error: model exploded" in capsys.readouterr().err
```

Keep any existing tests for `LlamaError`/`ArtistResolutionError`/`ConfigError` untouched.

- [ ] **Step 2: Run to verify the new tests fail**

Run: `pytest tests/test_errors.py -v`
Expected: `test_llm_errors_independent_of_llama_taxonomy` FAILS (`LLMError` *is* currently a `LlamaError`). The render test may pass already (via the `LlamaError` catch) — that's fine; it pins behavior for Step 3.

- [ ] **Step 3: Make the LLM error base independent**

`src/llama/llm/provider.py` — full new content:

```python
from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Base for LLM-layer failures.

    Deliberately independent of llama.errors: this module is bound for
    extraction into the shared `herder` package and must not import llama.
    The CLI boundary catches this alongside LlamaError.
    """


class ResearchNotSupported(LLMError):
    pass


class TaskFailed(LLMError):
    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...

    def research(self, brief: str) -> str: ...
```

In `src/llama/cli.py` `main_cli` (~line 2374), widen the boundary catch — change `except LlamaError as exc:` to:

```python
    except (LlamaError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in getattr(exc, "details", []):
            print(f"  {detail}", file=sys.stderr)
        raise SystemExit(1)
```

(`LLMError` is already imported at `cli.py:23`. `getattr` because `LLMError` has no `details`.)

- [ ] **Step 4: Full suite**

Run: `pytest -q`
Expected: all pass. (The explicit catch tuples at `cli.py:305`, `cli.py:1503`, and `stages/gather.py:222` already name `TaskFailed`/`LLMError` directly, so no other site depends on the old subclassing.)

- [ ] **Step 5: Commit**

```bash
git add src/llama/llm/provider.py src/llama/cli.py tests/test_errors.py
git commit -m "refactor: make LLM-layer errors independent of LlamaError"
```

---

### Task 2: De-couple prompts — task runners take the template; `load_prompt` moves to llama

`load_prompt` hardcodes the `llama.prompts` resource package inside the future-herder code (`src/llama/llm/tasks.py:20-21`). Move it to `llama/prompts/__init__.py` and make `run_json_task`/`run_research_task` take the template text as a required keyword.

**Files:**
- Modify: `src/llama/prompts/__init__.py` (currently empty)
- Modify: `src/llama/llm/tasks.py`
- Modify (call sites, add `template=load_prompt("<task>")` + import): `src/llama/artist_index.py:177`, `src/llama/stages/gather.py:158,218`, `src/llama/stages/interpret.py:9`, `src/llama/stages/synthesize.py:159`, `src/llama/stages/winnow.py:103,133`, `src/llama/stages/vet_research.py:163`, `src/llama/stages/research.py:15`
- Modify: `tests/test_llm_tasks.py`, `tests/test_prompts.py`, `tests/test_stage_synthesize.py`
- Test: `tests/test_llm_tasks.py`

**Interfaces:**
- Consumes: Task 1's `provider.py` (unchanged here).
- Produces:
  - `llama.prompts.load_prompt(name: str) -> str` — reads `llama/prompts/<name>.md`.
  - `run_json_task(provider, task: str, schema, *, template: str, retries: int = 2, **inputs)` — `task` is now used only in error messages.
  - `run_research_task(provider, task: str, *, template: str, required_sections=(), retries: int = 2, **inputs)`.

- [ ] **Step 1: Write the failing test**

In `tests/test_llm_tasks.py`, update every `run_json_task`/`run_research_task` call to pass an inline template instead of relying on a real prompt file, e.g. the basic case becomes:

```python
fake = FakeProvider(completes=['{"value": 42}'])
result = tasks.run_json_task(fake, "interpret", Answer, template="Q: {{q}}", q="six times seven")
```

and equivalently for the retry/escalation and research-task tests (`template="Research {{artist}}"`-style). Templates must contain a placeholder for every `**inputs` key the test passes (`render` raises on unfilled placeholders — that behavior is unchanged).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_llm_tasks.py -v`
Expected: FAIL — `run_json_task() got an unexpected keyword argument 'template'`.

- [ ] **Step 3: Implement**

`src/llama/prompts/__init__.py` — full new content:

```python
from importlib import resources


def load_prompt(name: str) -> str:
    return resources.files("llama.prompts").joinpath(f"{name}.md").read_text()
```

`src/llama/llm/tasks.py`: delete `load_prompt` and the `from importlib import resources` import; change both runner signatures/bodies:

```python
def run_json_task(
    provider: ProviderOrLadder,
    task: str,
    schema: type[BaseModel],
    *,
    template: str,
    retries: int = 2,
    **inputs,
) -> BaseModel:
    ladder = _as_ladder(provider)
    prompt = render(template, **inputs)
    ...
```

(only the `prompt = render(load_prompt(task), **inputs)` line changes, in both functions).

Update the nine call sites — pattern (example, `src/llama/stages/interpret.py`):

```python
from llama.prompts import load_prompt

criteria = run_json_task(provider, "interpret", Criteria,
                         template=load_prompt("interpret"), query=query)
```

Apply identically at each site, template name = the task-name string already present in the call: `find_artists` (artist_index.py:177), `extract_setlist` (gather.py:158), `align_structure` (gather.py:218), `synthesize` (synthesize.py:159), `score_reviews` (winnow.py:103), `vet_research` (vet_research.py:163), `deep_research` (research.py:15), `light_research` (winnow.py:133).

Update imports in `tests/test_prompts.py` and `tests/test_stage_synthesize.py`: `from llama.llm.tasks import load_prompt` → `from llama.prompts import load_prompt`.

- [ ] **Step 4: Full suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llama/prompts/__init__.py src/llama/llm/tasks.py src/llama/artist_index.py src/llama/stages/ tests/
git commit -m "refactor: task runners take template text; load_prompt moves to llama.prompts"
```

---

### Task 3: De-couple config — `LLMSettings` replaces `Config` in the LLM layer

`llm/__init__.py` imports llama's `Config` and reads `config.llm_for`/`config.tiers`. Give the layer its own settings type; llama's `Config` grows an adapter. `DEFAULT_TIERS` (task vocabulary) moves to llama.

**Files:**
- Modify: `src/llama/llm/__init__.py`
- Modify: `src/llama/config.py`
- Modify: `src/llama/cli.py:508`, `src/llama/pipeline.py:30`
- Modify: `tests/test_model_tiers.py`, `tests/test_config.py`
- Test: `tests/test_model_tiers.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: Task 1's error base.
- Produces (in `llama.llm`, extraction-bound):
  - `class TaskConfig(BaseModel)`: `backend: str = "claude_cli"`, `model: str | None = None`, `tier: str | None = None`.
  - `class LLMSettings(BaseModel)`: `tasks: dict[str, TaskConfig]` (per-task + optional `"default"` entry), `tiers: dict[str, dict[str, str]]` (backend overlays), `default_tiers: dict[str, str]` (task → tier); method `for_task(task: str) -> TaskConfig` (task entry > `"default"` > `TaskConfig()`).
  - `resolve_model(settings: LLMSettings, task: str) -> tuple[str, str]`, `provider_for(settings, task)`, `provider_ladder(settings, task, attempts=3)` — semantics byte-identical to today (explicit model > explicit tier > `default_tiers[task]` > `"medium"`; ladder escalates one tier on the final attempt; pins/high/missing-tier never escalate; same error messages).
- Produces (in `llama.config`):
  - `DEFAULT_TIERS` moved here verbatim (with its comment).
  - `class LLMTaskConfig(TaskConfig)` overriding `tier: Tier | None = None` (keeps TOML tier-typo validation).
  - `Config.llm_settings(self) -> LLMSettings` returning `LLMSettings(tasks=self.llm, tiers=self.tiers, default_tiers=DEFAULT_TIERS)`.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_model_tiers.py` to drive resolution through `LLMSettings` instead of `Config` — every existing behavioral case is preserved, only construction changes. Representative rewrites (carry ALL existing cases over in this style):

```python
from llama.llm import ESCALATE, TIER_MODELS, LLMSettings, TaskConfig, provider_ladder, resolve_model


def settings(**kw):
    return LLMSettings(default_tiers={"deep_research": "high", "vet_research": "low"}, **kw)


def test_task_default_tier_resolves():
    assert resolve_model(settings(), "deep_research") == ("claude_cli", "opus")


def test_unknown_task_defaults_to_medium():
    assert resolve_model(settings(), "interpret") == ("claude_cli", "sonnet")


def test_explicit_model_pin_wins():
    s = settings(tasks={"interpret": TaskConfig(model="claude-opus-4-8")})
    assert resolve_model(s, "interpret") == ("claude_cli", "claude-opus-4-8")


def test_tier_table_overlay():
    s = settings(tiers={"openrouter": {"medium": "deepseek/deepseek-chat-v3"}},
                 tasks={"default": TaskConfig(backend="openrouter")})
    assert resolve_model(s, "interpret") == ("openrouter", "deepseek/deepseek-chat-v3")
```

In `tests/test_config.py`, add the adapter + moved-vocabulary tests:

```python
from llama.config import DEFAULT_TIERS, Config


def test_llm_settings_adapter_carries_config_tables():
    config = Config.model_validate(
        {"llm": {"synthesize": {"tier": "medium"},
                 "tiers": {"openrouter": {"low": "x/y"}}}})
    s = config.llm_settings()
    assert s.tasks["synthesize"].tier == "medium"
    assert s.tiers == {"openrouter": {"low": "x/y"}}
    # pydantic copies dicts on validation — compare by value, not identity
    assert s.default_tiers == DEFAULT_TIERS


def test_default_tiers_vocabulary():
    assert DEFAULT_TIERS["deep_research"] == "high"
    assert DEFAULT_TIERS["synthesize"] == "high"
    assert DEFAULT_TIERS["vet_research"] == "low"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_model_tiers.py tests/test_config.py -v`
Expected: FAIL — `ImportError` (`LLMSettings`/`TaskConfig` don't exist; `DEFAULT_TIERS` not in `llama.config`).

- [ ] **Step 3: Implement**

`src/llama/llm/__init__.py`: remove `from llama.config import Config`; move `DEFAULT_TIERS` out (to config.py); add at the top:

```python
from pydantic import BaseModel, Field

from llama.llm.claude_cli import ClaudeCLIProvider
from llama.llm.openrouter import OpenRouterProvider
from llama.llm.provider import LLMError, LLMProvider


class TaskConfig(BaseModel):
    backend: str = "claude_cli"
    model: str | None = None
    tier: str | None = None


class LLMSettings(BaseModel):
    """Everything the LLM layer needs to pick a backend+model for a task.

    The consuming app builds this from its own config; the layer has no
    knowledge of any app's config format or task vocabulary."""

    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    tiers: dict[str, dict[str, str]] = Field(default_factory=dict)
    default_tiers: dict[str, str] = Field(default_factory=dict)

    def for_task(self, task: str) -> TaskConfig:
        return self.tasks.get(task) or self.tasks.get("default") or TaskConfig()
```

Then rewrite the resolution functions to take `settings: LLMSettings` instead of `config: Config`, preserving logic and messages exactly:

```python
def _tier_table(settings: LLMSettings, backend: str) -> dict[str, str]:
    """Shipped tier table overlaid with the app's per-backend overrides."""
    return TIER_MODELS.get(backend, {}) | settings.tiers.get(backend, {})


def resolve_model(settings: LLMSettings, task: str) -> tuple[str, str]:
    """Resolve (backend, model): explicit model > explicit tier > task default > medium."""
    cfg = settings.for_task(task)
    if cfg.model:
        return cfg.backend, cfg.model
    table = _tier_table(settings, cfg.backend)
    if not table:
        raise LLMError(f"unknown LLM backend {cfg.backend!r} for task {task!r}")
    tier = cfg.tier or settings.default_tiers.get(task, "medium")
    model = table.get(tier)
    if model is None:
        raise LLMError(f"backend {cfg.backend!r} has no model for tier {tier!r} (task {task!r})")
    return cfg.backend, model


def provider_for(settings: LLMSettings, task: str) -> LLMProvider:
    backend, model = resolve_model(settings, task)
    return _construct(backend, model, task)


def provider_ladder(settings: LLMSettings, task: str, attempts: int = 3) -> list[LLMProvider]:
    """One provider per attempt: [base, ..., base, escalated]. (docstring unchanged)"""
    cfg = settings.for_task(task)
    base = provider_for(settings, task)
    if attempts <= 1 or cfg.model:
        return [base] * max(attempts, 1)
    tier = cfg.tier or settings.default_tiers.get(task, "medium")
    up = ESCALATE[tier]
    up_model = _tier_table(settings, cfg.backend).get(up)
    if up == tier or up_model is None:
        return [base] * attempts
    return [base] * (attempts - 1) + [_construct(cfg.backend, up_model, task)]
```

(`TIER_MODELS`, `ESCALATE`, `_construct` stay verbatim. `ESCALATE[tier]` on an unknown custom tier would `KeyError` — today's tiers are constrained by llama's config validation, preserved below.)

`src/llama/config.py`:

```python
from llama.llm import LLMSettings, TaskConfig

# Task -> tier defaults. Sonnet is the workhorse; deep_research and synthesize
# are the two tasks whose quality is audible on air. (llama's task vocabulary —
# moved here from the LLM layer, which is app-agnostic.)
DEFAULT_TIERS = {
    "interpret": "medium",
    "score_reviews": "medium",
    "light_research": "medium",
    "extract_setlist": "medium",
    "deep_research": "high",
    "synthesize": "high",
    "find_artists": "medium",
    "align_structure": "medium",
    "vet_research": "low",
}


class LLMTaskConfig(TaskConfig):
    # Narrows the shared type so a config-file tier typo fails at parse time.
    tier: Tier | None = None
```

(delete the old standalone `LLMTaskConfig`; `Config.llm: dict[str, LLMTaskConfig]` stays as-is) and add to `Config`:

```python
    def llm_settings(self) -> LLMSettings:
        return LLMSettings(tasks=self.llm, tiers=self.tiers, default_tiers=DEFAULT_TIERS)
```

Call sites: `src/llama/cli.py:508` → `provider_ladder(config.llm_settings(), "find_artists")`; `src/llama/pipeline.py:30` → `provider_ladder(config.llm_settings(), key)` (hoist `settings = config.llm_settings()` above the dict comprehension and reuse it).

- [ ] **Step 4: Full suite**

Run: `pytest -q`
Expected: all pass. Check for import cycles: `python -c "import llama.config, llama.llm, llama.cli"` runs clean (the old `llm → config` import is gone; `config → llm` is the only direction left).

- [ ] **Step 5: Commit**

```bash
git add src/llama/llm/__init__.py src/llama/config.py src/llama/cli.py src/llama/pipeline.py tests/test_model_tiers.py tests/test_config.py
git commit -m "refactor: LLM layer takes LLMSettings; Config gains llm_settings() adapter"
```

---

### Task 4: Monorepo restructure — llama moves under `packages/llama/`

Pure relocation; no Python code changes except path anchors. After this task the repo root holds `packages/`, `packaging/`, `scripts/`, `docs/`, `pytest.ini`.

**Files:**
- Move: `src/` → `packages/llama/src/`, `tests/` → `packages/llama/tests/`, `pyproject.toml` → `packages/llama/pyproject.toml` (all via `git mv`)
- Create: `pytest.ini` (repo root)
- Modify: `packages/llama/pyproject.toml`, `.gitignore`, `packaging/llama.spec`, `packaging/build.py:27`, `scripts/refresh_jerrybase.py:` (VENDORED), `scripts/capture_fixture.py` (default output dir), `packages/llama/tests/test_packaging.py:13`, `packages/llama/tests/test_refresh_jerrybase.py:7`, `.github/workflows/release.yml:112`, `README.md:18,416,418`, `CLAUDE.md:15,16,67,128,151`

**Interfaces:**
- Consumes: nothing from prior tasks specifically.
- Produces: the `packages/` layout every later task assumes; root `pytest.ini` as the single pytest config; editable install command `pip install -e "packages/llama[dev]"`.

- [ ] **Step 1: Move**

```bash
mkdir -p packages/llama
git mv src packages/llama/src
git mv tests packages/llama/tests
git mv pyproject.toml packages/llama/pyproject.toml
```

- [ ] **Step 2: Root pytest config**

Create `pytest.ini` at the repo root:

```ini
[pytest]
testpaths = packages/llama/tests
markers = live: hits real network or LLM; deselected by default
addopts = -m 'not live'
```

Delete the `[tool.pytest.ini_options]` block from `packages/llama/pyproject.toml` (single source of truth at the root). The `[tool.hatch.build.targets.wheel] packages = ["src/llama"]` entry is relative to the pyproject file and needs no change.

- [ ] **Step 3: Fix path anchors**

- `.gitignore`: `src/llama/_version.py` → `packages/llama/src/llama/_version.py`.
- `packaging/llama.spec`: entry point `PROJECT_ROOT / "src" / "llama" / "__main__.py"` → `PROJECT_ROOT / "packages" / "llama" / "src" / "llama" / "__main__.py"`; `pathex=[str(PROJECT_ROOT / "src")]` → `pathex=[str(PROJECT_ROOT / "packages" / "llama" / "src")]`. (The `collect_data_files("llama.prompts")`/`("llama.data")` calls are package-name-based — leave them.)
- `packaging/build.py:27`: `VERSION_FILE = PROJECT_ROOT / "packages" / "llama" / "src" / "llama" / "_version.py"`.
- `scripts/refresh_jerrybase.py`: `VENDORED = Path(__file__).resolve().parent.parent / "packages" / "llama" / "src" / "llama" / "data" / "set_breaks.csv"`.
- `scripts/capture_fixture.py`: its output dir default is cwd-relative; re-anchor it to `Path(__file__).resolve().parent.parent / "packages" / "llama" / "tests" / "fixtures"` so `python scripts/capture_fixture.py <id>` works from the repo root as documented.
- `packages/llama/tests/test_packaging.py:13`: `ROOT = Path(__file__).resolve().parent.parent` → `ROOT = Path(__file__).resolve().parents[3]` (tests/ is now three levels below the repo root).
- `packages/llama/tests/test_refresh_jerrybase.py:7`: `parent.parent` → `parents[3]`.

- [ ] **Step 4: CI + docs**

- `.github/workflows/release.yml:112`: `pip install -e ".[dev]"` → `pip install -e "packages/llama[dev]"`.
- `README.md:18`: same install-command change. `README.md:416,418`: `src/llama/data/...` → `packages/llama/src/llama/data/...`.
- `CLAUDE.md:15`: setup command; `:16`: single-test example path becomes `pytest packages/llama/tests/test_setlist.py::test_parses_sets_segues_and_confidence -q`; `:67,128,151`: `src/llama/...` → `packages/llama/src/llama/...`.
- Leave historical docs (`docs/ux-review.md`, dated specs/plans) untouched — they describe past snapshots.

- [ ] **Step 5: Reinstall editable + full suite**

```bash
pip install -e "packages/llama[dev]"
pytest -q
```

Expected: all pass. Also: `llama --help` prints the command tree.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move llama into packages/llama (monorepo layout)"
```

---

### Task 5: Extract herder

Move `packages/llama/src/llama/llm/` to `packages/herder/src/herder/`, rename `LLMError` → `HerderError`, rewrite imports, split tests, add the guard test.

**Files:**
- Move (git mv): `llm/provider.py` → `packages/herder/src/herder/provider.py`; `llm/claude_cli.py` → `herder/claude_cli.py`; `llm/openrouter.py` → `herder/openrouter.py`; `llm/fake.py` → `herder/fake.py`; `llm/tasks.py` → `herder/tasks.py`; `llm/__init__.py` → `packages/herder/src/herder/resolve.py`
- Move (git mv): `packages/llama/tests/{test_llm_tasks.py,test_model_tiers.py,test_claude_cli.py,test_openrouter.py}` → `packages/herder/tests/`
- Create: `packages/herder/pyproject.toml`, `packages/herder/src/herder/__init__.py`, `packages/herder/tests/test_no_llama_imports.py`
- Modify: every `llama.llm` import site (listed in Step 3), `pytest.ini`, `packages/llama/pyproject.toml`, `packaging/llama.spec`, `.github/workflows/release.yml:112`, `README.md`, `CLAUDE.md`
- Test: whole suite + the new guard test

**Interfaces:**
- Consumes: Tasks 1–4 (independent errors, template-passing runners, `LLMSettings`, `packages/` layout).
- Produces: importable `herder` package — public API via `herder/__init__.py`: `HerderError`, `TaskFailed`, `ResearchNotSupported`, `LLMProvider`, `TaskConfig`, `LLMSettings`, `TIER_MODELS`, `ESCALATE`, `resolve_model`, `provider_for`, `provider_ladder`, `render`, `extract_json`, `run_json_task`, `run_research_task`, `FakeProvider` (from `herder.fake`). Distribution name `llama-herder`, module `herder`.

- [ ] **Step 1: Move the files**

```bash
mkdir -p packages/herder/src/herder packages/herder/tests
git mv packages/llama/src/llama/llm/provider.py   packages/herder/src/herder/provider.py
git mv packages/llama/src/llama/llm/claude_cli.py packages/herder/src/herder/claude_cli.py
git mv packages/llama/src/llama/llm/openrouter.py packages/herder/src/herder/openrouter.py
git mv packages/llama/src/llama/llm/fake.py       packages/herder/src/herder/fake.py
git mv packages/llama/src/llama/llm/tasks.py      packages/herder/src/herder/tasks.py
git mv packages/llama/src/llama/llm/__init__.py   packages/herder/src/herder/resolve.py
rmdir packages/llama/src/llama/llm
git mv packages/llama/tests/test_llm_tasks.py   packages/herder/tests/test_llm_tasks.py
git mv packages/llama/tests/test_model_tiers.py packages/herder/tests/test_model_tiers.py
git mv packages/llama/tests/test_claude_cli.py  packages/herder/tests/test_claude_cli.py
git mv packages/llama/tests/test_openrouter.py  packages/herder/tests/test_openrouter.py
```

- [ ] **Step 2: Package metadata + public API**

`packages/herder/pyproject.toml` — full content:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llama-herder"
version = "0.1.0"
description = "Shared LLM task layer: tiered providers, schema-validated tasks, retry escalation"
license = "GPL-3.0-or-later"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "httpx>=0.27",
]

[tool.hatch.build.targets.wheel]
packages = ["src/herder"]
```

`packages/herder/src/herder/__init__.py` — full content:

```python
from herder.fake import FakeProvider
from herder.provider import HerderError, LLMProvider, ResearchNotSupported, TaskFailed
from herder.resolve import (
    ESCALATE,
    TIER_MODELS,
    LLMSettings,
    TaskConfig,
    provider_for,
    provider_ladder,
    resolve_model,
)
from herder.tasks import extract_json, render, run_json_task, run_research_task
```

Add `llama-herder` to `packages/llama/pyproject.toml` `dependencies` (satisfied by the joint editable install; neither package is published).

- [ ] **Step 3: Rename + rewrite imports**

Within `packages/herder/src/herder/`: replace every `from llama.llm.` import prefix with `from herder.` (`provider.py` has none; `claude_cli.py:6`, `openrouter.py:5`, `tasks.py:7`, `resolve.py:2-4` do — and `resolve.py`'s backend imports become `from herder.claude_cli import ...` etc.). Rename class `LLMError` → `HerderError` everywhere in herder (definition in `provider.py`, raises in `resolve.py`, `claude_cli.py`, `openrouter.py`).

Within `packages/llama/` (src + tests) apply this mapping:

| Old | New |
|---|---|
| `from llama.llm import provider_ladder` (cli.py:22, pipeline.py:7) | `from herder import provider_ladder` |
| `from llama.llm.provider import LLMError, TaskFailed` (cli.py:23) | `from herder import HerderError, TaskFailed` |
| `from llama.llm.tasks import run_json_task[, run_research_task]` (artist_index.py:17, stages/gather.py:10, winnow.py:5, interpret.py:1, vet_research.py:3, research.py:1, synthesize.py:3) | `from herder import run_json_task[, run_research_task]` |
| `from llama.llm.provider import LLMError, TaskFailed` (stages/gather.py:9) | `from herder import HerderError, TaskFailed` |
| `from llama.llm import LLMSettings, TaskConfig` (config.py, from Task 3) | `from herder import LLMSettings, TaskConfig` |
| `from llama.llm.fake import FakeProvider` (18 test files) | `from herder import FakeProvider` |
| `__import__("llama.llm.fake", fromlist=["FakeProvider"])` (tests/test_get_cmd.py:336) | `__import__("herder.fake", fromlist=["FakeProvider"])` |
| `from llama.llm import tasks` (herder tests) | `from herder import tasks` |
| every `except (...) `/`isinstance` naming `LLMError` (cli.py:305,1503 + main_cli boundary, stages/gather.py:222, tests/test_errors.py) | `HerderError` |

`packages/llama/tests/test_errors.py`: update imports to `from herder import HerderError, ResearchNotSupported, TaskFailed` and rename in assertions (the independence + boundary tests from Task 1 otherwise stand).

- [ ] **Step 4: Guard test**

`packages/herder/tests/test_no_llama_imports.py` — full content:

```python
"""herder is the shared layer: it must never depend on any consuming app."""

import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(?:from|import)\s+llama\b", re.M)


def test_herder_never_imports_llama():
    src = Path(__file__).resolve().parents[1] / "src"
    offenders = [str(p) for p in sorted(src.rglob("*.py")) if FORBIDDEN.search(p.read_text())]
    assert offenders == []
```

- [ ] **Step 5: Wire up root config, CI, packaging, docs**

- `pytest.ini`: `testpaths = packages/herder/tests packages/llama/tests`.
- `.github/workflows/release.yml:112`: `pip install -e "packages/llama[dev]"` → `pip install -e packages/herder -e "packages/llama[dev]"`.
- `packaging/llama.spec`: `pathex` gains `str(PROJECT_ROOT / "packages" / "herder" / "src")` (robust against editable-install import hooks at freeze time).
- `README.md:18` and `CLAUDE.md:15`: install command → `pip install -e packages/herder -e "packages/llama[dev]"`.
- `CLAUDE.md` architecture section: change the LLM-layer sentence to note it lives in the shared `herder` package (`packages/herder/`), used by llama and (later) the persona tool; task registries/prompts stay per-app.

- [ ] **Step 6: Reinstall + full suite**

```bash
pip install -e packages/herder -e "packages/llama[dev]"
pytest -q
```

Expected: all pass, including the guard test. Then:

```bash
grep -rn "llama\.llm" packages/ && echo "STALE IMPORTS" || echo OK
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: extract shared herder package (LLM task layer)"
```

---

### Task 6: End-to-end verification

**Files:** none created; verification only (plus any fixes it forces).

**Interfaces:** consumes the finished layout.

- [ ] **Step 1: Fresh-venv install per the new README**

```bash
python3 -m venv /tmp/llama-fresh-venv
/tmp/llama-fresh-venv/bin/pip install -q -e packages/herder -e "packages/llama[dev]"
/tmp/llama-fresh-venv/bin/llama --help
/tmp/llama-fresh-venv/bin/llama pipeline
/tmp/llama-fresh-venv/bin/pytest -q
```

Expected: help tree renders, `pipeline` prints the stage/state teaching output, suite passes. Remove the venv afterwards. (The spec's "offline `llama get` smoke against the fake backend" is covered by the suite's `test_get_cmd.py` — there is no `fake` backend string at the CLI level, only test-injected `FakeProvider`, so the suite IS the smoke.)

- [ ] **Step 2: PyInstaller dry-run check**

```bash
python packaging/build.py --version 0.0.0-smoke --dry-run
```

Expected: exits 0 (path re-anchors in `llama.spec`/`build.py` resolve; no build performed).

- [ ] **Step 3: Confirm history followed the moves**

```bash
git log --follow --oneline -- packages/herder/src/herder/tasks.py | tail -3
```

Expected: shows commits from before the extraction (history preserved through both moves).

- [ ] **Step 4: Commit any verification fixes; otherwise nothing to commit**

```bash
git status --short
```

Expected: clean.
