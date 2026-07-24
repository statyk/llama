import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from llama.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".llama"

Tier = Literal["low", "medium", "high"]


class LLMTaskConfig(BaseModel):
    backend: str = "claude_cli"
    model: str | None = None
    tier: Tier | None = None


class SetlistFMConfig(BaseModel):
    api_key: str | None = None


class TTSConfig(BaseModel):
    """Spoken DJ patter (text-to-speech of the DJ script). Opt-in."""
    enabled: bool = False               # nothing calls a TTS API unless voice is active
    backend: str = "voxtral"            # or "elevenlabs" / "fake"
    voice: str | None = None            # voxtral preset name / elevenlabs voice_id
    voice_clone: str | None = None      # path to a reference WAV; when set, voxtral clones it
    model: str | None = None            # per-backend default when unset
    api_key: str | None = None          # MISTRAL_API_KEY / ELEVENLABS_API_KEY env wins
    chunk: bool = False                 # synthesize each DJ-notes segment sentence-by-
                                         # sentence and concatenate, instead of one call
                                         # per segment (better prosody; needs lameenc)


class JerrybaseConfig(BaseModel):
    # Vendored, offline, no key - so on by default (unlike setlist.fm). No
    # thresholds: break anchoring is all-or-nothing by design.
    enabled: bool = True


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
    tts: TTSConfig = Field(default_factory=TTSConfig)
    jerrybase: JerrybaseConfig = Field(default_factory=JerrybaseConfig)
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
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


# Seeded by `llama config init`. Kept in sync with the defaults above by
# tests/test_config.py::test_default_config_template_matches_defaults.
DEFAULT_CONFIG_TOML = """\
# llama config - seeded by `llama config init` with the baked-in defaults.
#
# IMPORTANT: a value here REPLACES its built-in default; nothing merges.
# Any [selection.tapers.*] table replaces the entire taper set, and any
# [[selection.lineage_eras]] block replaces the entire built-in era list.
# The defaults are written out below so additive edits keep them.

# root = "/path/to/workdir"        # workspace root; default ~/.llama
# delivery_path = "/station/inbox" # target for `llama deliver`
audio_format = "mp3"               # or "flac"

[llm.default]
backend = "claude_cli"             # requires the `claude` CLI on PATH
# backend = "openrouter"           # HTTP alternative; set OPENROUTER_API_KEY
# Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
# gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
# Defaults: medium for most tasks; high for deep_research and synthesize;
# low for vet_research.
# A failed validation's final retry escalates one tier (pins never escalate).

# [llm.deep_research]
# backend = "claude_cli"   # pin research to the claude CLI when the default
#                          # backend is openrouter: its agentic multi-step
#                          # research is stronger, and quality is audible on air

# [llm.synthesize]
# tier = "medium"            # example: cheaper synthesis
# model = "claude-opus-4-8"  # example: exact pin, bypasses tiers

# [llm.tiers.openrouter]
# medium = "deepseek/deepseek-chat-v3"  # retarget what a tier means per backend

# [setlistfm]
# api_key = "..."          # or SETLISTFM_API_KEY env var; without a key,
#                          # set-structure recovery is LMA-descriptions only

# [tts]                      # spoken DJ patter: per-segment MP3 clips of the
#                            # DJ script land in package/dj-audio/ (00-intro,
#                            # set<key>-intro, break<N>, 99-outro), tied
#                            # together by the manifest's dj_audio block.
#                            # Enabling voice forces the DJ script on even
#                            # against --no-script (nothing to voice otherwise).
# enabled = true             # default false; a profile with its own `voice`
#                            # is voiced even when this is off
# backend = "voxtral"        # hosted Mistral Voxtral TTS (default); or
#                            # "elevenlabs"; or "fake" for tests
# voice = "..."              # voxtral preset name (or elevenlabs voice_id); a
#                            # profile can set its own `voice` to override this
# voice_clone = "..."        # path to a 3-25s reference WAV; when set, voxtral
#                            # clones that voice (ignores `voice`)
# model = "..."              # per-backend default when unset
#                            # (voxtral-mini-tts-2603 / eleven_multilingual_v2)
# api_key = "..."            # MISTRAL_API_KEY / ELEVENLABS_API_KEY env (env wins)
# chunk = true               # synthesize each segment sentence-by-sentence and
#                            # concatenate (single MP3 encode at the end)
#                            # instead of one TTS call per whole segment;
#                            # noticeably better prosody/pacing on longer DJ
#                            # patter at the cost of more provider round-trips
#                            # per segment. Requires the `lameenc` dependency
#                            # (installed by default). Default false.

[jerrybase]
enabled = true             # vendored offline set-structure evidence (break
                           # anchoring + set-count/venue/multi-event tripwires);
                           # set false to ignore the dataset entirely

[winnow]
max_metadata_fetch = 40    # review-fetch budget: when more survivors than
                           # this, the best-evidenced are sampled for scoring

[artists]
min_recordings = 25        # hide artists below these floors from the index
min_downloads = 50000
max_matched = 20           # LLM artist-match budget for artist-less queries

[structure]
guard_min_minutes = 150    # hold single-set shows longer than this for review
align_coverage_threshold = 0.8

# Recording selection. Taper bonuses match identifier substrings; among
# revisions by the same taper the newest gets the full bonus, the rest half.
[selection.tapers.GratefulDead]
miller = 2.0               # Charlie Miller: community gold standard
seamons = 1.0

# Era overrides for lineage scoring. Multiple [[selection.lineage_eras]]
# blocks are allowed; the first whose collection and (inclusive) date window
# match a show wins. `scores` replaces the ENTIRE lineage table (global
# base: sbd 3.0, matrix 2.5, aud 1.0, unknown 0.0) - an omitted class
# scores 0.0, so spell out every class you care about.
# Deleting a table/block here restores its built-in default (absence =
# default); to truly clear one, set it empty, e.g. lineage_eras = []
# under [selection].
[[selection.lineage_eras]]
collection = "GratefulDead"   # early-80s boards are rough: MTX > AUD > SBD
date_from = "1980-01-01"
date_to = "1987-12-31"
scores = { matrix = 3.0, aud = 2.0, sbd = 1.0 }
"""
