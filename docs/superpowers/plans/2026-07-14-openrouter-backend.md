# OpenRouter Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `openrouter` LLM backend (complete + web-plugin research), per-backend `[llm.tiers]` config retargeting, and escalate-on-final-attempt provider ladders.

**Architecture:** A direct-`httpx` `OpenRouterProvider` implements the existing `LLMProvider` protocol against OpenRouter's OpenAI-compatible chat endpoint. Tier resolution merges a config overlay over shipped `TIER_MODELS` tables. `make_providers` switches from one provider per task to a per-attempt provider *ladder* whose final rung is one tier up; `run_json_task` accepts either a bare provider or a ladder.

**Tech Stack:** Python 3.11+, httpx (already a dependency), Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-07-14-openrouter-backend-design.md`

## Global Constraints

- No new dependencies — `httpx>=0.27` and `pydantic>=2.7` are already in `pyproject.toml`.
- All tests offline and deterministic (`pytest -q`); no live OpenRouter test in CI.
- The default backend stays `claude_cli`; OpenRouter is opt-in via config.
- API key comes from the `OPENROUTER_API_KEY` env var (or constructor arg); a missing key raises `LLMError` at provider construction.
- Shipped OpenRouter tier slugs (verified against the live catalog 2026-07-14): low `google/gemini-2.5-flash`, medium `anthropic/claude-sonnet-4.5`, high `anthropic/claude-opus-4.1`.
- Never commit audio files.
- Run all commands from the worktree root (`.claude/worktrees/openrouter-backend`); the venv is at the main checkout (`source /Users/shawn/projects/llama/.venv/bin/activate`) and the package is installed editable — but the worktree's `src` must be imported, so run pytest as `python -m pytest` from the worktree root with `PYTHONPATH=src` if imports resolve to the main checkout (verify with Task 1's first test run; if the plain `pytest -q` picks up the worktree source, drop the prefix).

---

### Task 1: OpenRouterProvider

**Files:**
- Create: `src/llama/llm/openrouter.py`
- Test: `tests/test_openrouter.py`

**Interfaces:**
- Consumes: `LLMError`, `LLMProvider` from `llama.llm.provider` (existing).
- Produces: `class OpenRouterProvider(model: str, api_key: str | None = None, timeout_s: int = 900, transport: httpx.BaseTransport | None = None)` with `.model` and `.api_key` attributes and methods `complete(prompt: str) -> str`, `research(brief: str) -> str`. Task 3 imports it in `llama/llm/__init__.py` and constructs it as `OpenRouterProvider(model=model)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openrouter.py`:

```python
import json

import httpx
import pytest

from llama.llm.openrouter import OpenRouterProvider
from llama.llm.provider import LLMError, LLMProvider


def ok_payload(text="hi"):
    return {"choices": [{"message": {"content": text}}]}


def make_provider(handler):
    return OpenRouterProvider(
        model="test/model", api_key="k", transport=httpx.MockTransport(handler)
    )


def test_complete_posts_model_and_prompt():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=ok_payload("hello"))

    p = make_provider(handler)
    assert p.complete("say hello") == "hello"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["body"]["model"] == "test/model"
    assert seen["body"]["messages"] == [{"role": "user", "content": "say hello"}]
    assert "plugins" not in seen["body"]
    assert seen["auth"] == "Bearer k"


def test_research_adds_web_plugin():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_payload("found"))

    assert make_provider(handler).research("dig") == "found"
    assert seen["body"]["plugins"] == [{"id": "web"}]


def test_missing_api_key_raises_at_construction(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(model="test/model")


def test_env_var_supplies_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    p = OpenRouterProvider(model="test/model")
    assert p.api_key == "from-env"


def test_non_200_raises():
    p = make_provider(lambda r: httpx.Response(429, text="rate limited"))
    with pytest.raises(LLMError, match="429"):
        p.complete("x")


def test_transport_error_raises():
    def handler(request):
        raise httpx.ConnectError("no route to host")

    with pytest.raises(LLMError, match="request failed"):
        make_provider(handler).complete("x")


def test_bad_json_raises():
    p = make_provider(lambda r: httpx.Response(200, text="not json"))
    with pytest.raises(LLMError, match="not JSON"):
        p.complete("x")


def test_missing_content_raises():
    p = make_provider(lambda r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(LLMError, match="missing content"):
        p.complete("x")


def test_non_string_content_raises():
    p = make_provider(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    )
    with pytest.raises(LLMError):
        p.complete("x")


def test_satisfies_protocol():
    p = make_provider(lambda r: httpx.Response(200, json=ok_payload()))
    assert isinstance(p, LLMProvider)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_openrouter.py -q`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'llama.llm.openrouter'`

- [ ] **Step 3: Write the implementation**

Create `src/llama/llm/openrouter.py`:

```python
import os

import httpx

from llama.llm.provider import LLMError

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter's web-search plugin: single-shot search grounding for research().
WEB_PLUGIN = [{"id": "web"}]


class OpenRouterProvider:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        timeout_s: int = 900,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise LLMError("OpenRouter API key missing: set OPENROUTER_API_KEY")
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def _chat(self, prompt: str, plugins: list[dict] | None = None) -> str:
        body: dict = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        if plugins:
            body["plugins"] = plugins
        try:
            resp = self._client.post(
                API_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"}
            )
        except httpx.HTTPError as e:
            raise LLMError(f"openrouter request failed: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"openrouter returned {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise LLMError(f"openrouter response was not JSON: {resp.text[:200]}") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"openrouter response missing content: {str(data)[:500]}") from e
        if not isinstance(content, str):
            raise LLMError(f"openrouter content is not a string: {str(data)[:500]}")
        return content

    def complete(self, prompt: str) -> str:
        return self._chat(prompt)

    def research(self, brief: str) -> str:
        return self._chat(brief, plugins=WEB_PLUGIN)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_openrouter.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/llama/llm/openrouter.py tests/test_openrouter.py
git commit -m "feat: OpenRouter provider with web-plugin research"
```

---

### Task 2: `[llm.tiers]` config section

**Files:**
- Modify: `src/llama/config.py`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `Config.tiers: dict[str, dict[Literal["low", "medium", "high"], str]]` (default `{}`), populated from TOML `[llm.tiers.<backend>]` tables. `"tiers"` becomes a reserved (non-task) key in the `[llm]` section. Task 3 reads `config.tiers.get(backend, {})`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_llm_tiers_lifted_from_llm_table(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[llm.tiers.openrouter]\nmedium = "deepseek/deepseek-chat-v3"\n'
        '[llm.tiers.claude_cli]\nhigh = "sonnet"\n'
        '[llm.synthesize]\ntier = "high"\n'
    )
    cfg = load_config(p)
    assert cfg.tiers == {
        "openrouter": {"medium": "deepseek/deepseek-chat-v3"},
        "claude_cli": {"high": "sonnet"},
    }
    # "tiers" is reserved: it must not appear as a task entry
    assert "tiers" not in cfg.llm
    assert cfg.llm_for("synthesize").tier == "high"


def test_llm_tiers_rejects_unknown_tier_key(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.tiers.openrouter]\nturbo = "some/model"\n')
    with pytest.raises(ValidationError):
        load_config(p)


def test_tiers_defaults_empty():
    assert Config().tiers == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: the three new tests FAIL. `Config` has no `tiers` attribute, so `test_tiers_defaults_empty` and `test_llm_tiers_lifted_from_llm_table` hit `AttributeError` (Pydantic *ignores* the unknown keys inside `[llm.tiers.*]` when validating them as an `LLMTaskConfig`, so loading itself succeeds), and `test_llm_tiers_rejects_unknown_tier_key` fails with `DID NOT RAISE`. The five existing tests still pass.

- [ ] **Step 3: Implement**

Replace the whole of `src/llama/config.py` with:

```python
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DEFAULT_ROOT = Path.home() / ".llama"

Tier = Literal["low", "medium", "high"]


class LLMTaskConfig(BaseModel):
    backend: str = "claude_cli"
    model: str | None = None
    tier: Tier | None = None


class Config(BaseModel):
    root: Path = DEFAULT_ROOT
    delivery_path: Path | None = None
    audio_format: Literal["mp3", "flac"] = "mp3"
    llm: dict[str, LLMTaskConfig] = Field(default_factory=dict)
    tiers: dict[str, dict[Tier, str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _lift_llm_tiers(cls, data):
        # TOML nests [llm.tiers.*] inside the llm table; "tiers" is a
        # reserved name there, not a task entry.
        if isinstance(data, dict) and isinstance(data.get("llm"), dict) and "tiers" in data["llm"]:
            llm = dict(data["llm"])
            data = {**data, "llm": llm, "tiers": llm.pop("tiers")}
        return data

    def llm_for(self, task: str) -> LLMTaskConfig:
        return self.llm.get(task) or self.llm.get("default") or LLMTaskConfig()


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_ROOT / "config.toml"
    if not path.exists():
        return Config()
    return Config.model_validate(tomllib.loads(path.read_text()))
```

(Only additions: the `Tier` alias, the `tiers` field, and the `_lift_llm_tiers` validator; `LLMTaskConfig.tier` now uses the alias. Everything else is verbatim the existing file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/llama/config.py tests/test_config.py
git commit -m "feat: per-backend [llm.tiers] config section"
```

---

### Task 3: Tier resolution with overlay + openrouter backend

**Files:**
- Modify: `src/llama/llm/__init__.py`
- Test: `tests/test_model_tiers.py` (append + one edit)

**Interfaces:**
- Consumes: `OpenRouterProvider` (Task 1), `Config.tiers` (Task 2).
- Produces: `TIER_MODELS["openrouter"]`; `_tier_table(config: Config, backend: str) -> dict[str, str]` (module-private merged table); `_construct(backend: str, model: str, task: str) -> LLMProvider`; `resolve_model` now raises `LLMError` (never `KeyError`) for a missing tier. `provider_for` signature unchanged. Task 4 uses `_tier_table` and `_construct`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model_tiers.py` (also add `from llama.llm.openrouter import OpenRouterProvider` beneath the existing imports):

```python
def test_openrouter_tier_table_matches_spec():
    assert TIER_MODELS["openrouter"] == {
        "low": "google/gemini-2.5-flash",
        "medium": "anthropic/claude-sonnet-4.5",
        "high": "anthropic/claude-opus-4.1",
    }


def test_openrouter_backend_resolves_and_constructs(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")})
    assert resolve_model(cfg, "interpret") == ("openrouter", "anthropic/claude-sonnet-4.5")
    assert resolve_model(cfg, "synthesize") == ("openrouter", "anthropic/claude-opus-4.1")
    p = provider_for(cfg, "interpret")
    assert isinstance(p, OpenRouterProvider)
    assert p.model == "anthropic/claude-sonnet-4.5"


def test_openrouter_without_key_fails_fast(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")})
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        provider_for(cfg, "interpret")


def test_config_tiers_overlay_beats_shipped_table():
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")},
                 tiers={"openrouter": {"medium": "deepseek/deepseek-chat-v3"}})
    assert resolve_model(cfg, "interpret") == ("openrouter", "deepseek/deepseek-chat-v3")
    # tiers the overlay doesn't touch still come from the shipped table
    assert resolve_model(cfg, "synthesize") == ("openrouter", "anthropic/claude-opus-4.1")


def test_overlay_applies_to_claude_cli_too():
    cfg = Config(tiers={"claude_cli": {"high": "sonnet"}})
    assert resolve_model(cfg, "synthesize") == ("claude_cli", "sonnet")


def test_missing_tier_raises_llmerror_not_keyerror():
    cfg = Config(llm={"default": LLMTaskConfig(backend="custom")},
                 tiers={"custom": {"low": "x/y"}})
    with pytest.raises(LLMError, match="tier"):
        resolve_model(cfg, "interpret")  # interpret needs medium; table only has low


def test_tiers_only_backend_fails_at_provider_construction():
    cfg = Config(llm={"default": LLMTaskConfig(backend="custom", tier="low")},
                 tiers={"custom": {"low": "x/y"}})
    assert resolve_model(cfg, "interpret") == ("custom", "x/y")
    with pytest.raises(LLMError, match="unknown LLM backend"):
        provider_for(cfg, "interpret")
```

Also edit the existing `test_tables_match_spec` so its `TIER_MODELS` assertion covers only the claude_cli entry (it already does — `TIER_MODELS["claude_cli"] == ...` — so no change is actually needed; verify and leave it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model_tiers.py -q`
Expected: the seven new tests FAIL (`TIER_MODELS` has no `"openrouter"` key; `resolve_model` raises "unknown LLM backend" for the overlay cases; the missing-tier case raises `KeyError`, which pytest reports as an error, not the expected `LLMError`). The seven existing tests still pass.

- [ ] **Step 3: Implement**

Replace the whole of `src/llama/llm/__init__.py` with:

```python
from llama.config import Config
from llama.llm.claude_cli import ClaudeCLIProvider
from llama.llm.openrouter import OpenRouterProvider
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
    "propose_artists": "medium",
}

# Backend -> tier -> model. claude_cli uses the CLI's stable aliases so the
# table carries no dated model ids. openrouter uses cross-vendor value picks
# (slugs verified against the live catalog 2026-07-14); retarget via
# [llm.tiers.openrouter] in config.
TIER_MODELS = {
    "claude_cli": {"low": "haiku", "medium": "sonnet", "high": "opus"},
    "openrouter": {
        "low": "google/gemini-2.5-flash",
        "medium": "anthropic/claude-sonnet-4.5",
        "high": "anthropic/claude-opus-4.1",
    },
}


def _tier_table(config: Config, backend: str) -> dict[str, str]:
    """Shipped tier table overlaid with the [llm.tiers.<backend>] config."""
    return TIER_MODELS.get(backend, {}) | config.tiers.get(backend, {})


def resolve_model(config: Config, task: str) -> tuple[str, str]:
    """Resolve (backend, model): explicit model > explicit tier > task default > medium."""
    cfg = config.llm_for(task)
    if cfg.model:
        return cfg.backend, cfg.model
    table = _tier_table(config, cfg.backend)
    if not table:
        raise LLMError(f"unknown LLM backend {cfg.backend!r} for task {task!r}")
    tier = cfg.tier or DEFAULT_TIERS.get(task, "medium")
    model = table.get(tier)
    if model is None:
        raise LLMError(f"backend {cfg.backend!r} has no model for tier {tier!r} (task {task!r})")
    return cfg.backend, model


def _construct(backend: str, model: str, task: str) -> LLMProvider:
    if backend == "claude_cli":
        return ClaudeCLIProvider(model=model)
    if backend == "openrouter":
        return OpenRouterProvider(model=model)
    raise LLMError(f"unknown LLM backend {backend!r} for task {task!r}")


def provider_for(config: Config, task: str) -> LLMProvider:
    backend, model = resolve_model(config, task)
    return _construct(backend, model, task)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_model_tiers.py tests/test_claude_cli.py -q`
Expected: all pass (14 in test_model_tiers, 5 in test_claude_cli)

- [ ] **Step 5: Commit**

```bash
git add src/llama/llm/__init__.py tests/test_model_tiers.py
git commit -m "feat: openrouter tier table, [llm.tiers] overlay, LLMError on missing tier"
```

---

### Task 4: Escalate-on-retry provider ladders

**Files:**
- Modify: `src/llama/llm/__init__.py` (append), `src/llama/llm/tasks.py`, `src/llama/pipeline.py:23-24`
- Test: `tests/test_model_tiers.py` (append), `tests/test_llm_tasks.py` (append)

**Interfaces:**
- Consumes: `_tier_table`, `_construct`, `provider_for`, `DEFAULT_TIERS` (Task 3); `FakeProvider` (existing).
- Produces: `provider_ladder(config: Config, task: str, attempts: int = 3) -> list[LLMProvider]`; `run_json_task` and `run_research_task` accept `LLMProvider | Sequence[LLMProvider]` as their first argument (bare provider behavior unchanged); `make_providers` returns `dict[str, list[LLMProvider]]`. Stage call sites are untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model_tiers.py` (add `provider_ladder` to the existing `from llama.llm import ...` line):

```python
def test_ladder_escalates_final_attempt(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")})
    ladder = provider_ladder(cfg, "interpret")  # medium task: final rung one tier up
    assert [p.model for p in ladder] == [
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-opus-4.1",
    ]


def test_ladder_high_tier_has_no_headroom():
    ladder = provider_ladder(Config(), "synthesize")
    assert [p.model for p in ladder] == ["opus", "opus", "opus"]


def test_ladder_model_pin_never_escalates():
    cfg = Config(llm={"interpret": LLMTaskConfig(model="claude-opus-4-8")})
    ladder = provider_ladder(cfg, "interpret")
    assert [p.model for p in ladder] == ["claude-opus-4-8"] * 3


def test_ladder_low_tier_escalates_to_medium():
    cfg = Config(llm={"default": LLMTaskConfig(backend="claude_cli", tier="low")},
                 tiers={"claude_cli": {"medium": "sonnet-cheap"}})
    # low escalates to medium, and the escalated rung honors the config overlay
    assert [p.model for p in provider_ladder(cfg, "interpret")] == [
        "haiku", "haiku", "sonnet-cheap"]
```

(The case of a backend whose table lacks even the *base* tier is already covered by `test_tiers_only_backend_fails_at_provider_construction` in Task 3; `provider_ladder` inherits that failure through `provider_for`.)

Append to `tests/test_llm_tasks.py`:

```python
def test_run_json_task_escalates_on_final_attempt(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    base = FakeProvider(completes=["bad", "still bad"])
    escalated = FakeProvider(completes=['{"value": 9}'])
    result = tasks.run_json_task([base, base, escalated], "interpret", Answer, q="x")
    assert result.value == 9
    assert len(base.calls) == 2
    assert len(escalated.calls) == 1
    assert "previous response was invalid" in escalated.calls[0][1]


def test_run_json_task_short_ladder_reuses_last_rung(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    only = FakeProvider(completes=["bad", "bad", '{"value": 3}'])
    assert tasks.run_json_task([only], "interpret", Answer, q="x").value == 3


def test_run_research_task_uses_first_rung(monkeypatch):
    use_template(monkeypatch, "Research {{topic}}")
    base = FakeProvider(researches=["# Findings"])
    escalated = FakeProvider()
    assert tasks.run_research_task([base, escalated], "deep_research", topic="x") == "# Findings"
    assert escalated.calls == []


def test_make_providers_builds_ladders():
    from llama.config import Config
    from llama.pipeline import make_providers
    providers = make_providers(Config())
    # interpret is a medium task: base, base, escalated-to-high
    assert [p.model for p in providers["interpret"]] == ["sonnet", "sonnet", "opus"]
    # synthesize is already high: no headroom
    assert [p.model for p in providers["synthesize"]] == ["opus", "opus", "opus"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model_tiers.py tests/test_llm_tasks.py -q`
Expected: new tests FAIL (`ImportError: cannot import name 'provider_ladder'`; `run_json_task` calls `.complete` on a list and hits `AttributeError`; `make_providers` values are single providers, not lists). All pre-existing tests still pass.

- [ ] **Step 3: Implement**

Append to `src/llama/llm/__init__.py`:

```python
# One step up per tier; high has no headroom.
ESCALATE = {"low": "medium", "medium": "high", "high": "high"}


def provider_ladder(config: Config, task: str, attempts: int = 3) -> list[LLMProvider]:
    """One provider per attempt: [base, ..., base, escalated].

    The final attempt runs one tier up on the same backend. Explicit model
    pins, high-tier tasks, and merged tables lacking the escalated tier
    never escalate (the ladder is all base rungs).
    """
    cfg = config.llm_for(task)
    base = provider_for(config, task)
    if attempts <= 1 or cfg.model:
        return [base] * max(attempts, 1)
    tier = cfg.tier or DEFAULT_TIERS.get(task, "medium")
    up = ESCALATE[tier]
    up_model = _tier_table(config, cfg.backend).get(up)
    if up == tier or up_model is None:
        return [base] * attempts
    return [base] * (attempts - 1) + [_construct(cfg.backend, up_model, task)]
```

In `src/llama/llm/tasks.py`, update the imports and the two task runners (leave `load_prompt`, `render`, `extract_json` untouched):

```python
from collections.abc import Sequence

from llama.llm.provider import LLMProvider, TaskFailed

ProviderOrLadder = LLMProvider | Sequence[LLMProvider]


def _as_ladder(provider: ProviderOrLadder) -> list[LLMProvider]:
    if isinstance(provider, (list, tuple)):
        if not provider:
            raise ValueError("empty provider ladder")
        return list(provider)
    return [provider]


def run_json_task(
    provider: ProviderOrLadder,
    task: str,
    schema: type[BaseModel],
    *,
    retries: int = 2,
    **inputs,
) -> BaseModel:
    ladder = _as_ladder(provider)
    prompt = render(load_prompt(task), **inputs)
    attempt_prompt = prompt
    raw = ""
    for attempt in range(retries + 1):
        raw = ladder[min(attempt, len(ladder) - 1)].complete(attempt_prompt)
        try:
            return schema.model_validate_json(extract_json(raw))
        except (ValidationError, ValueError) as err:
            attempt_prompt = (
                prompt
                + f"\n\nYour previous response was invalid: {err}\n"
                + "Respond with ONLY valid JSON matching the requested schema."
            )
    raise TaskFailed(f"LLM task {task!r} failed after {retries + 1} attempts", raw_output=raw)


def run_research_task(provider: ProviderOrLadder, task: str, **inputs) -> str:
    return _as_ladder(provider)[0].research(render(load_prompt(task), **inputs))
```

In `src/llama/pipeline.py`, change `make_providers` (lines 23–24) and its import (line 7):

```python
from llama.llm import provider_ladder
```

```python
def make_providers(config: Config) -> dict:
    return {key: provider_ladder(config, key) for key in TASK_KEYS}
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all pass. The pipeline/CLI tests monkeypatch `make_providers` with dicts of bare `FakeProvider`s — the `ProviderOrLadder` union keeps them green; if any fail, the union normalization in `_as_ladder` is wrong, not the tests.

- [ ] **Step 5: Commit**

```bash
git add src/llama/llm/__init__.py src/llama/llm/tasks.py src/llama/pipeline.py tests/test_model_tiers.py tests/test_llm_tasks.py
git commit -m "feat: escalate-on-final-attempt provider ladders"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md:12-25`, `CLAUDE.md` (LLM-layer bullets)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–4.
- Produces: user-facing docs only; no code.

- [ ] **Step 1: Update README config example**

Replace the config block at `README.md:18-25` with:

```
    [llm.default]
    backend = "claude_cli"           # requires the `claude` CLI on PATH
    # backend = "openrouter"         # HTTP alternative; set OPENROUTER_API_KEY
    # Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
    # gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
    # Defaults: medium for most tasks; high for deep_research and synthesize.
    # If a task's output fails validation twice, the final retry runs one
    # tier up (exact `model` pins never escalate).

    [llm.synthesize]
    # tier = "medium"                # example: cheaper synthesis
    # model = "claude-opus-4-8"      # example: exact pin, bypasses tiers

    [llm.tiers.openrouter]
    # medium = "deepseek/deepseek-chat-v3"  # retarget what a tier means per backend
```

- [ ] **Step 2: Update CLAUDE.md**

Two small edits, keeping surrounding text intact (the file is also being edited on main by a concurrent session — keep these edits minimal and expect a trivial merge):

1. In the "What this is" paragraph, replace the sentence
   `LLM model choice is tiered (low/medium/high -> haiku/sonnet/opus on the claude_cli backend): Sonnet by default, Opus for deep_research/synthesize, overridable per task via `[llm.<task>]` `tier` or `model` in config.`
   with
   `LLM model choice is tiered (low/medium/high; haiku/sonnet/opus on claude_cli, gemini-flash/sonnet-4.5/opus-4.1 on openrouter): medium by default, high for deep_research/synthesize, overridable per task via `[llm.<task>]` `tier`/`model` or per backend via `[llm.tiers.<backend>]`; a failed validation's final retry escalates one tier (pins never escalate).`

2. In the Architecture "LLM layer" bullet, replace
   `Dev backend shells out to headless `claude -p`; OpenRouter comes later; a `fake` backend serves tests.`
   with
   `Dev backend shells out to headless `claude -p`; `openrouter` is the HTTP alternative (opt-in, needs `OPENROUTER_API_KEY`, research via the web plugin); a `fake` backend serves tests.`

- [ ] **Step 3: Run the full suite one last time**

Run: `pytest -q`
Expected: all pass (docs-only change; this is the pre-merge gate).

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: OpenRouter backend, [llm.tiers], escalation semantics"
```
