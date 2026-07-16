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
    guard_min_minutes: int = 150
    align_coverage_threshold: float = 0.8


class LineageEra(BaseModel):
    """Replace the global lineage base scores for one collection + date window."""
    collection: str
    date_from: str  # YYYY-MM-DD, inclusive
    date_to: str
    scores: dict[str, float]  # keys: sbd / matrix / aud / unknown


def _default_tapers() -> dict[str, dict[str, float]]:
    # Charlie Miller's transfers are the community gold standard; Seamons next.
    return {"GratefulDead": {"miller": 2.0, "seamons": 1.0}}


def _default_lineage_eras() -> list[LineageEra]:
    # Early-80s GD soundboards are often poor; matrixes and audience tapes shine.
    return [LineageEra(collection="GratefulDead",
                       date_from="1980-01-01", date_to="1987-12-31",
                       scores={"matrix": 3.0, "aud": 2.0, "sbd": 1.0})]


class SelectionConfig(BaseModel):
    tapers: dict[str, dict[str, float]] = Field(default_factory=_default_tapers)
    lineage_eras: list[LineageEra] = Field(default_factory=_default_lineage_eras)


class WinnowConfig(BaseModel):
    # Review-fetch budget: when more candidates survive the mechanical gate,
    # winnow samples this many evenly across years instead of scoring all.
    max_metadata_fetch: int = 40


class ArtistsConfig(BaseModel):
    min_recordings: int = 25
    min_downloads: int = 50000
    # LLM artist-match budget for find/profile discovery; matches the
    # `llama artists` default so test-driving a query previews the same slate.
    max_matched: int = 20


class Config(BaseModel):
    root: Path = DEFAULT_ROOT
    delivery_path: Path | None = None
    audio_format: Literal["mp3", "flac"] = "mp3"
    llm: dict[str, LLMTaskConfig] = Field(default_factory=dict)
    setlistfm: SetlistFMConfig = Field(default_factory=SetlistFMConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    artists: ArtistsConfig = Field(default_factory=ArtistsConfig)
    winnow: WinnowConfig = Field(default_factory=WinnowConfig)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
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
