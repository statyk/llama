import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from herder import LLMSettings, TaskConfig
from llama.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".llama"

Tier = Literal["low", "medium", "high"]

# Task -> tier defaults. Sonnet is the workhorse; deep_research and synthesize
# are the two tasks whose quality is audible on air. (llama's task vocabulary —
# moved here from the LLM layer, which is app-agnostic.)
DEFAULT_TIERS = {
    "interpret": "medium",
    "score_reviews": "medium",
    "light_research": "medium",
    "extract_setlist": "medium",
    "deep_research": "high",
    "synthesize": "high",
    "find_artists": "medium",
    "align_structure": "medium",
    "vet_research": "low",
}


class LLMTaskConfig(TaskConfig):
    # Narrows the shared type so a config-file tier typo fails at parse time.
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
    bed: str | None = None              # path to a 24kHz mono 16-bit WAV played
                                         # under the DJ voice; None = no bed
    bed_gain_db: float = -20.0          # bed loudness under the voice (station-level)


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

    def llm_settings(self) -> LLMSettings:
        return LLMSettings(tasks=self.llm, tiers=self.tiers, default_tiers=DEFAULT_TIERS)


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


# workspace root; default ~/.llama
# root = "/path/to/workdir"

# target for `llama deliver`
# delivery_path = "/station/inbox"

# or "flac"
audio_format = "mp3"


[llm.default]
# requires the `claude` CLI on PATH
backend = "claude_cli"

# HTTP alternative; set OPENROUTER_API_KEY
# backend = "openrouter"

# Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
# gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
# Defaults: medium for most tasks; high for deep_research and synthesize;
# low for vet_research.
# A failed validation's final retry escalates one tier (pins never escalate).


# [llm.deep_research]
# pin research to the claude CLI when the default backend is openrouter: its
# agentic multi-step research is stronger, and quality is audible on air
# backend = "claude_cli"


# [llm.synthesize]
# example: cheaper synthesis
# tier = "medium"
# example: exact pin, bypasses tiers
# model = "claude-opus-4-8"


# [llm.tiers.openrouter]
# retarget what a tier means per backend
# medium = "deepseek/deepseek-chat-v3"


# [setlistfm]
# or SETLISTFM_API_KEY env var; without a key, set-structure recovery is
# LMA-descriptions only
# api_key = "..."


# spoken DJ patter: per-segment MP3 clips of the DJ script land in
# package/dj-audio/ (one set<key>-intro per non-encore set, then 99-outro),
# tied together by the manifest's dj_audio block. Enabling voice forces the
# DJ script on even against --no-script (nothing to voice otherwise).
# [tts]
# default false; a profile with a presenter is voiced even when this is off
# enabled = true

# hosted Mistral Voxtral TTS (default); or "elevenlabs"; or "fake" for tests
# backend = "voxtral"

# the HOUSE voice: voxtral preset name (or elevenlabs voice_id), used when
# no presenter
# voice = "..."

# path to a 3-25s reference WAV; when set, voxtral clones that voice
# (ignores `voice`)
# voice_clone = "..."

# per-backend default when unset
# (voxtral-mini-tts-2603 / eleven_multilingual_v2)
# model = "..."

# MISTRAL_API_KEY / ELEVENLABS_API_KEY env (env wins)
# api_key = "..."

# Hosts live in presenters/<id>.toml (name / sex / voice XOR voice_clone /
# character / bed); a profile picks one via `presenter = "<id>"` and names its
# radio show via `title = "..."`.

# synthesize each segment sentence-by-sentence and concatenate (single MP3
# encode at the end) instead of one TTS call per whole segment; noticeably
# better prosody/pacing on longer DJ patter at the cost of more provider
# round-trips per segment. Requires the `lameenc` dependency (installed by
# default). Default false.
# chunk = true

# bed music (instrumental) played UNDER the DJ voice on voiced shows; must be
# a 24kHz mono 16-bit WAV. Per-presenter override via the presenter's `bed`.
# llama never converts audio; prepare the file once with an external tool, e.g.
# `ffmpeg -i in.mp3 -ac 1 -ar 24000 -c:a pcm_s16le bed.wav` (or sox). A wrong
# format or missing file hard-fails that show's package.
# bed = "/path/to/bed.wav"
# bed loudness under the voice, in dB (negative = quieter); default -20
# bed_gain_db = -20.0
# because mixing needs PCM, bed-active clips are re-encoded to MP3 (24kHz
# mono, ~64 kbps via lameenc) rather than shipping the provider's native
# MP3 like unbedded clips do - a small, expected bitrate difference.


[jerrybase]
# vendored offline set-structure evidence (break anchoring +
# set-count/venue/multi-event tripwires); set false to ignore the dataset
# entirely
enabled = true


[winnow]
# review-fetch budget: when more survivors than this, the best-evidenced are
# sampled for scoring
max_metadata_fetch = 40


[artists]
# hide artists below these floors from the index
min_recordings = 25
min_downloads = 50000

# LLM artist-match budget for artist-less queries
max_matched = 20


[structure]
# hold single-set shows longer than this for review
guard_min_minutes = 150

align_coverage_threshold = 0.8


# Recording selection. Taper bonuses match identifier substrings; among
# revisions by the same taper the newest gets the full bonus, the rest half.
[selection.tapers.GratefulDead]
# Charlie Miller: community gold standard
miller = 2.0
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
# early-80s boards are rough: MTX > AUD > SBD
collection = "GratefulDead"
date_from = "1980-01-01"
date_to = "1987-12-31"
scores = { matrix = 3.0, aud = 2.0, sbd = 1.0 }
"""
