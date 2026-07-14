# Model Tiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give llama's LLM layer a low/medium/high tier vocabulary with shipped defaults (Sonnet workhorse, Opus for deep_research/synthesize), so a concrete model is always chosen and the scheme ports to OpenRouter later.

**Architecture:** `LLMTaskConfig` gains an optional validated `tier`; `llama/llm/__init__.py` gains `DEFAULT_TIERS` (task→tier) and `TIER_MODELS` (backend→tier→model alias) plus a `resolve_model` step inside `provider_for`. Resolution precedence: explicit model > explicit tier > task default > medium.

**Tech Stack:** Existing project (Python ≥3.11, pydantic v2, pytest). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-14-model-tiers-design.md`.

## Global Constraints

- Tier values exactly `"low" | "medium" | "high"`; invalid strings must fail Pydantic validation at config load.
- claude_cli tier table exactly `{"low": "haiku", "medium": "sonnet", "high": "opus"}` (CLI aliases, no dated ids).
- `DEFAULT_TIERS`: `deep_research`/`synthesize` → `"high"`; `interpret`/`score_reviews`/`light_research`/`extract_setlist` → `"medium"`; unknown tasks fall back to `"medium"`.
- After this change `provider_for` always yields a provider with a concrete model (never None).
- All existing tests keep passing (`pytest -q`, currently 109 passed, 2 deselected). Tests offline; conventional commits.
- `[llm.tiers]` retargeting, OpenRouter backend, and auto-select are OUT of scope (deferred by the spec).

## File Structure

```
src/llama/config.py        # + tier field on LLMTaskConfig
src/llama/llm/__init__.py  # + DEFAULT_TIERS, TIER_MODELS, resolve_model; provider_for uses them
tests/test_config.py       # + tier validation tests
tests/test_model_tiers.py  # new: resolution-precedence tests
README.md, CLAUDE.md       # config example / architecture note updated (Task 2)
```

---

### Task 1: Tier field on LLMTaskConfig

**Files:**
- Modify: `src/llama/config.py` (LLMTaskConfig class)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: existing `LLMTaskConfig(backend: str = "claude_cli", model: str | None = None)`.
- Produces: `LLMTaskConfig.tier: Literal["low", "medium", "high"] | None = None` — Task 2's resolver reads `cfg.tier`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from llama.config import LLMTaskConfig


def test_tier_accepts_valid_values(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.synthesize]\ntier = "medium"\n')
    cfg = load_config(p)
    assert cfg.llm_for("synthesize").tier == "medium"
    assert LLMTaskConfig().tier is None


def test_tier_rejects_invalid_value(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.synthesize]\ntier = "turbo"\n')
    with pytest.raises(ValidationError):
        load_config(p)
```

(`Path` and `load_config` are already imported at the top of this test file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: 2 new tests FAIL (`tier` not a field / no ValidationError), 2 old pass

- [ ] **Step 3: Implement**

In `src/llama/config.py`, add to the imports:

```python
from typing import Literal
```

and change `LLMTaskConfig` to:

```python
class LLMTaskConfig(BaseModel):
    backend: str = "claude_cli"
    model: str | None = None
    tier: Literal["low", "medium", "high"] | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/llama/config.py tests/test_config.py
git commit -m "feat: add validated tier field to LLMTaskConfig"
```

---

### Task 2: Tier resolution in provider_for + docs

**Files:**
- Modify: `src/llama/llm/__init__.py` (full replacement below)
- Modify: `README.md` (config example), `CLAUDE.md` (LLM-layer bullet)
- Test: `tests/test_model_tiers.py` (new)

**Interfaces:**
- Consumes: `LLMTaskConfig.tier` from Task 1; existing `Config.llm_for(task)`, `ClaudeCLIProvider(model=...)`, `LLMError`.
- Produces: `DEFAULT_TIERS: dict[str, str]`, `TIER_MODELS: dict[str, dict[str, str]]`, `resolve_model(config: Config, task: str) -> tuple[str, str]` (returns `(backend, model)`), and `provider_for` now always passing a concrete model. `pipeline.make_providers` needs no change.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_model_tiers.py`:

```python
import pytest

from llama.config import Config, LLMTaskConfig
from llama.llm import DEFAULT_TIERS, TIER_MODELS, provider_for, resolve_model
from llama.llm.provider import LLMError


def test_out_of_box_defaults_are_concrete():
    cfg = Config()
    assert provider_for(cfg, "interpret").model == "sonnet"
    assert provider_for(cfg, "score_reviews").model == "sonnet"
    assert provider_for(cfg, "deep_research").model == "opus"
    assert provider_for(cfg, "synthesize").model == "opus"
    assert provider_for(cfg, "some_future_task").model == "sonnet"  # medium fallback


def test_explicit_tier_beats_task_default():
    cfg = Config(llm={"synthesize": LLMTaskConfig(tier="medium")})
    assert provider_for(cfg, "synthesize").model == "sonnet"
    cfg = Config(llm={"interpret": LLMTaskConfig(tier="low")})
    assert provider_for(cfg, "interpret").model == "haiku"


def test_explicit_model_beats_tier():
    cfg = Config(llm={"synthesize": LLMTaskConfig(tier="low", model="claude-opus-4-8")})
    assert provider_for(cfg, "synthesize").model == "claude-opus-4-8"


def test_default_entry_tier_floors_unpinned_tasks():
    cfg = Config(llm={"default": LLMTaskConfig(tier="low")})
    assert provider_for(cfg, "interpret").model == "haiku"
    # synthesize has no entry of its own, so the default entry's tier wins
    assert provider_for(cfg, "synthesize").model == "haiku"
    # ...but a task with its own entry ignores the default entry entirely
    cfg = Config(llm={"default": LLMTaskConfig(tier="low"),
                      "synthesize": LLMTaskConfig(tier="high")})
    assert provider_for(cfg, "synthesize").model == "opus"


def test_unknown_backend_still_raises():
    cfg = Config(llm={"default": LLMTaskConfig(backend="nope")})
    with pytest.raises(LLMError):
        provider_for(cfg, "interpret")


def test_resolve_model_returns_backend_and_model():
    assert resolve_model(Config(), "synthesize") == ("claude_cli", "opus")


def test_tables_match_spec():
    assert TIER_MODELS["claude_cli"] == {"low": "haiku", "medium": "sonnet", "high": "opus"}
    assert DEFAULT_TIERS == {
        "interpret": "medium", "score_reviews": "medium",
        "light_research": "medium", "extract_setlist": "medium",
        "deep_research": "high", "synthesize": "high",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model_tiers.py -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_TIERS'`

- [ ] **Step 3: Implement**

Replace the full contents of `src/llama/llm/__init__.py` with:

```python
from llama.config import Config
from llama.llm.claude_cli import ClaudeCLIProvider
from llama.llm.provider import LLMError, LLMProvider

# Task -> tier defaults. Sonnet is the workhorse; deep_research and synthesize
# are the two tasks whose quality is audible on air.
DEFAULT_TIERS = {
    "interpret": "medium",
    "score_reviews": "medium",
    "light_research": "medium",
    "extract_setlist": "medium",
    "deep_research": "high",
    "synthesize": "high",
}

# Backend -> tier -> model. claude_cli uses the CLI's stable aliases so the
# table carries no dated model ids.
TIER_MODELS = {
    "claude_cli": {"low": "haiku", "medium": "sonnet", "high": "opus"},
}


def resolve_model(config: Config, task: str) -> tuple[str, str]:
    """Resolve (backend, model): explicit model > explicit tier > task default > medium."""
    cfg = config.llm_for(task)
    if cfg.model:
        return cfg.backend, cfg.model
    table = TIER_MODELS.get(cfg.backend)
    if table is None:
        raise LLMError(f"unknown LLM backend {cfg.backend!r} for task {task!r}")
    tier = cfg.tier or DEFAULT_TIERS.get(task, "medium")
    return cfg.backend, table[tier]


def provider_for(config: Config, task: str) -> LLMProvider:
    backend, model = resolve_model(config, task)
    if backend == "claude_cli":
        return ClaudeCLIProvider(model=model)
    raise LLMError(f"unknown LLM backend {backend!r} for task {task!r}")
```

Note: the pre-existing test `test_provider_for_uses_task_config` (tests/test_claude_cli.py) pins explicit models and an unknown backend — both paths are preserved above (explicit model short-circuits before the table lookup, so unknown backend + explicit model still reaches `provider_for`'s own LLMError; unknown backend without a model raises in `resolve_model`). Either raise site satisfies the test's `pytest.raises(LLMError)`.

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `pytest tests/test_model_tiers.py -q`
Expected: 7 passed
Run: `pytest -q`
Expected: 118 passed, 2 deselected (109 prior + 2 config + 7 tier tests)

- [ ] **Step 5: Update docs**

In `README.md`, replace the config example's `[llm.default]` block with:

```toml
    [llm.default]
    backend = "claude_cli"           # requires the `claude` CLI on PATH
    # Model tiers: low=haiku, medium=sonnet, high=opus (claude_cli).
    # Defaults: sonnet for most tasks; opus for deep_research and synthesize.

    [llm.synthesize]
    # tier = "medium"                # example: cheaper synthesis
    # model = "claude-opus-4-8"      # example: exact pin, bypasses tiers
```

In `CLAUDE.md`, in the "What this is" section, append one sentence to the paragraph:

```markdown
LLM model choice is tiered (low/medium/high -> haiku/sonnet/opus on the
claude_cli backend): Sonnet by default, Opus for deep_research/synthesize,
overridable per task via `[llm.<task>]` `tier` or `model` in config.
```

- [ ] **Step 6: Commit**

```bash
git add src/llama/llm/__init__.py tests/test_model_tiers.py README.md CLAUDE.md
git commit -m "feat: resolve LLM models through low/medium/high tiers"
```

---

## Plan Self-Review Notes

- **Spec coverage:** tier field + validation (Task 1); DEFAULT_TIERS/TIER_MODELS/resolution precedence incl. default-entry semantics and always-concrete model (Task 2 tests 1–4, 6); unknown backend unchanged (test 5); tables pinned to spec (test 7); docs (Task 2 Step 5); deferred items excluded.
- **Placeholder scan:** clean.
- **Type consistency:** `resolve_model(config, task) -> tuple[str, str]` matches its single call site; `LLMTaskConfig.tier` name consistent across both tasks.
