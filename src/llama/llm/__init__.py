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
    "align_structure": "medium",
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
