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


class SetlistFMConfig(BaseModel):
    api_key: str | None = None


class StructureConfig(BaseModel):
    guard_min_minutes: int = 100
    guard_min_tracks: int = 16
    align_coverage_threshold: float = 0.8


class Config(BaseModel):
    root: Path = DEFAULT_ROOT
    delivery_path: Path | None = None
    audio_format: Literal["mp3", "flac"] = "mp3"
    llm: dict[str, LLMTaskConfig] = Field(default_factory=dict)
    setlistfm: SetlistFMConfig = Field(default_factory=SetlistFMConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
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
