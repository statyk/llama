import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from herder import LLMSettings, TaskConfig

from emcee.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".emcee"

Tier = Literal["low", "medium", "high"]

# emcee's task vocabulary is much narrower than llama's -- it only ever
# scripts, never researches or curates.
TASK_KEYS = ["scriptwrite"]

# Task -> tier defaults. scriptwrite quality is audible on air, so it
# defaults to high (mirrors llama's config.py DEFAULT_TIERS pattern).
DEFAULT_TIERS = {
    "scriptwrite": "high",
}


def default_root() -> Path:
    """Resolve the emcee workspace root: `EMCEE_ROOT` env override, else
    `~/.emcee`. Used as `EmceeConfig.root`'s default (evaluated fresh at
    every construction, so a test that sets `EMCEE_ROOT` after import still
    gets the right root) and as `load_config`'s default search location."""
    root = os.environ.get("EMCEE_ROOT")
    return Path(root) if root else DEFAULT_ROOT


class LLMTaskConfig(TaskConfig):
    # Narrows the shared type so a config-file tier typo fails at parse time.
    tier: Tier | None = None


class StationConfig(BaseModel):
    root: Path | None = None   # the delivered-packages folder; required by run/status


class TTSConfig(BaseModel):
    """Spoken DJ patter (text-to-speech of the DJ script)."""
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


class Assignment(BaseModel):
    presenter: str
    title: str | None = None


class AssignConfig(BaseModel):
    default: str | None = None                          # station-default presenter id
    profiles: dict[str, Assignment] = Field(default_factory=dict)


class EmceeConfig(BaseModel):
    root: Path = Field(default_factory=default_root)
    station: StationConfig = Field(default_factory=StationConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    assign: AssignConfig = Field(default_factory=AssignConfig)
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

    def llm_settings(self) -> LLMSettings:
        return LLMSettings(tasks=self.llm, tiers=self.tiers, default_tiers=DEFAULT_TIERS)


def load_config(path: Path | None = None) -> EmceeConfig:
    path = path or default_root() / "config.toml"
    if not path.exists():
        return EmceeConfig()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc
    try:
        return EmceeConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


# Seeded by `emcee config init`. Kept in sync with the defaults above by
# tests/test_config.py::test_default_config_template_matches_defaults.
DEFAULT_CONFIG_TOML = """\
# emcee config - seeded by `emcee config init` with the baked-in defaults.
#
# IMPORTANT: a value here REPLACES its built-in default; nothing merges.
# The defaults are written out below so additive edits keep them.


# workspace root; default ~/.emcee
# root = "/path/to/workdir"


# the delivered-packages folder llama writes into; required by
# `emcee run`/`emcee status`
# [station]
# root = "/station/inbox"


[llm.scriptwrite]
# requires the `claude` CLI on PATH
backend = "claude_cli"

# HTTP alternative; set OPENROUTER_API_KEY
# backend = "openrouter"

# Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
# gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
# Default: high (scriptwrite quality is audible on air).
# A failed validation's final retry escalates one tier (pins never escalate).
# tier = "medium"
# example: exact pin, bypasses tiers
# model = "claude-opus-4-8"


# [llm.tiers.openrouter]
# retarget what a tier means per backend
# medium = "deepseek/deepseek-chat-v3"


# spoken DJ patter: per-segment MP3 clips of the DJ script land in
# package/dj-audio/ (one set<key>-intro per non-encore set, then 99-outro),
# tied together by the manifest's dj_audio block.
# [tts]
# hosted Mistral Voxtral TTS (default); or "elevenlabs"; or "fake" for tests
# backend = "voxtral"

# the HOUSE voice: voxtral preset name (or elevenlabs voice_id), used when
# a profile has no presenter assignment
# voice = "..."

# path to a 3-25s reference WAV; when set, voxtral clones that voice
# (ignores `voice`)
# voice_clone = "..."

# per-backend default when unset
# (voxtral-mini-tts-2603 / eleven_multilingual_v2)
# model = "..."

# MISTRAL_API_KEY / ELEVENLABS_API_KEY env (env wins)
# api_key = "..."

# Assignment is keyed by the llama profile name stamped in the manifest as
# source.profile (see [assign] below) -- not by anything in this section.

# synthesize each segment sentence-by-sentence and concatenate (single MP3
# encode at the end) instead of one TTS call per whole segment; noticeably
# better prosody/pacing on longer DJ patter at the cost of more provider
# round-trips per segment. Requires the `lameenc` dependency (installed by
# default). Default false.
# chunk = true

# bed music (instrumental) played UNDER the DJ voice on voiced shows; must be
# a 24kHz mono 16-bit WAV. Per-presenter override via the presenter's `bed`.
# emcee never converts audio; prepare the file once with an external tool, e.g.
# `ffmpeg -i in.mp3 -ac 1 -ar 24000 -c:a pcm_s16le bed.wav` (or sox). A wrong
# format or missing file hard-fails that show's package.
# bed = "/path/to/bed.wav"
# bed loudness under the voice, in dB (negative = quieter); default -20
# bed_gain_db = -20.0
# because mixing needs PCM, bed-active clips are re-encoded to MP3 (24kHz
# mono, ~64 kbps via lameenc) rather than shipping the provider's native
# MP3 like unbedded clips do - a small, expected bitrate difference.


# Which presenter voices which llama profile's shows, and what this station
# calls that segment on air. `[assign] default` names the presenter used for
# a profile with no entry of its own below; each [assign.profiles.<name>]
# table is keyed by the llama profile name stamped into the manifest as
# source.profile, and names a presenter (presenters/<id>.toml) plus an
# optional on-air show title.
# [assign]
# default = "waldo"

# [assign.profiles.prime-dead]
# presenter = "waldo"
# title = "The Primal Dead Hour"
"""
