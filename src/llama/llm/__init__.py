from llama.config import Config
from llama.llm.claude_cli import ClaudeCLIProvider
from llama.llm.provider import LLMError, LLMProvider


def provider_for(config: Config, task: str) -> LLMProvider:
    cfg = config.llm_for(task)
    if cfg.backend == "claude_cli":
        return ClaudeCLIProvider(model=cfg.model)
    raise LLMError(f"unknown LLM backend {cfg.backend!r} for task {task!r}")
