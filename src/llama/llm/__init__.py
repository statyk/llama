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
    "propose_artists": "medium",
    "align_structure": "medium",
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
