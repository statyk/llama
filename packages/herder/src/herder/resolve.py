from pydantic import BaseModel, Field

from herder.claude_cli import ClaudeCLIProvider
from herder.openrouter import OpenRouterProvider
from herder.provider import HerderError, LLMProvider


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


# Backend -> tier -> model. claude_cli uses the CLI's stable aliases so the
# table carries no dated model ids and floats forward on its own; openrouter
# has no aliases, so its slugs are pinned and go stale - re-check them against
# the live catalog when a generation ships (slugs verified 2026-08-06).
# Retarget either backend via [llm.tiers.<backend>] in config.
TIER_MODELS = {
    "claude_cli": {"low": "haiku", "medium": "sonnet", "high": "opus"},
    "openrouter": {
        "low": "google/gemini-2.5-flash",
        "medium": "anthropic/claude-sonnet-5",
        "high": "anthropic/claude-opus-5",
    },
}


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
        raise HerderError(f"unknown LLM backend {cfg.backend!r} for task {task!r}")
    tier = cfg.tier or settings.default_tiers.get(task, "medium")
    model = table.get(tier)
    if model is None:
        raise HerderError(f"backend {cfg.backend!r} has no model for tier {tier!r} (task {task!r})")
    return cfg.backend, model


def _construct(backend: str, model: str, task: str) -> LLMProvider:
    if backend == "claude_cli":
        return ClaudeCLIProvider(model=model)
    if backend == "openrouter":
        return OpenRouterProvider(model=model)
    raise HerderError(f"unknown LLM backend {backend!r} for task {task!r}")


def provider_for(settings: LLMSettings, task: str) -> LLMProvider:
    backend, model = resolve_model(settings, task)
    return _construct(backend, model, task)


# One step up per tier; high has no headroom.
ESCALATE = {"low": "medium", "medium": "high", "high": "high"}


def provider_ladder(settings: LLMSettings, task: str, attempts: int = 3) -> list[LLMProvider]:
    """One provider per attempt: [base, ..., base, escalated].

    The final attempt runs one tier up on the same backend. Explicit model
    pins, high-tier tasks, and merged tables lacking the escalated tier
    never escalate (the ladder is all base rungs).
    """
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
