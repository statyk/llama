import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_ROOT = Path.home() / ".llama"


class LLMTaskConfig(BaseModel):
    backend: str = "claude_cli"
    model: str | None = None


class Config(BaseModel):
    root: Path = DEFAULT_ROOT
    delivery_path: Path | None = None
    audio_format: str = "mp3"  # "mp3" | "flac"
    llm: dict[str, LLMTaskConfig] = Field(default_factory=dict)

    def llm_for(self, task: str) -> LLMTaskConfig:
        return self.llm.get(task) or self.llm.get("default") or LLMTaskConfig()


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_ROOT / "config.toml"
    if not path.exists():
        return Config()
    return Config.model_validate(tomllib.loads(path.read_text()))
