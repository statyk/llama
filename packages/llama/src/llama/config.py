import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from herder import LLMSettings, TaskConfig
from llama.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".llama"


class _StrictModel(BaseModel):
    """Unknown keys are an error, not a silent drop.

    config.toml is the one file this design expects a human to hand-edit, so a
    typo'd knob must fail loudly rather than leave the default in place. Set on
    a shared base because pydantic does not propagate model_config to nested
    models -- on Config alone, every section below it stays permissive.
    """
    model_config = ConfigDict(extra="forbid")


Tier = Literal["low", "medium", "high"]

# Task -> tier defaults. Sonnet is the workhorse; deep_research and brief are
# the two tasks whose quality is audible on air. (llama's task vocabulary —
# moved here from the LLM layer, which is app-agnostic.)
#
# `interpret` is high for leverage, not for quality-on-air: it is one small call
# (a one-line query in, a small JSON object out) against the ~25 a full run
# makes, several of which carry review bodies or run web search — so it is a
# rounding error on spend. But it is stage one, and every later stage only ever
# sees the Criteria it produced. A field it drops is not recoverable downstream:
# a required song left out of `setlist_constraints` cannot be filtered on later,
# and the run ships the wrong show without ever knowing it.
DEFAULT_TIERS = {
    "interpret": "high",
    "score_reviews": "medium",
    "light_research": "medium",
    "extract_setlist": "medium",
    "deep_research": "high",
    "brief": "high",
    "find_artists": "medium",
    "align_structure": "medium",
    "vet_research": "low",
}


class LLMTaskConfig(_StrictModel, TaskConfig):
    # Narrows the shared type so a config-file tier typo fails at parse time.
    tier: Tier | None = None


class SetlistFMConfig(_StrictModel):
    api_key: str | None = None


class JerrybaseConfig(_StrictModel):
    # Vendored, offline, no key - so on by default (unlike setlist.fm). No
    # thresholds: anchoring either resolves every set closer or declines
    # entirely, and when it resolves it wins over the aligned breaks.
    enabled: bool = True


class StructureConfig(_StrictModel):
    guard_min_minutes: int = 150
    align_coverage_threshold: float = 0.8


class LineageEra(_StrictModel):
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


class SelectionConfig(_StrictModel):
    tapers: dict[str, dict[str, float]] = Field(default_factory=_default_tapers)
    lineage_eras: list[LineageEra] = Field(default_factory=_default_lineage_eras)


class WinnowConfig(_StrictModel):
    # Review-fetch budget: when more candidates survive the mechanical gate,
    # winnow samples this many evenly across years instead of scoring all.
    max_metadata_fetch: int = 40


class ArtistsConfig(_StrictModel):
    min_recordings: int = 25
    min_downloads: int = 50000
    # LLM artist-match budget for find/profile discovery; matches the
    # `llama artists` default so test-driving a query previews the same slate.
    max_matched: int = 20


class PacingConfig(_StrictModel):
    """Pacing a run against a usage window (see llama/pacing.py).

    Covers both halves: waiting out a window the backend has already
    refused on, and the ceilings that stop the run at a show boundary
    BEFORE it is exhausted.

    Durations are strings so the config reads in the units a human thinks
    in; they are validated at load time rather than at the point of use, so
    a typo fails `llama get` immediately instead of four shows in.
    """
    enabled: bool = True
    wait: bool = True
    max_wait: str = "6h"
    unknown_reset_wait: str = "1h"
    reset_skew: str = "2m"

    # The proactive gate's whole policy surface for each window. A run pauses
    # when the meter PLUS the projected next show would cross the ceiling.
    # 90 is "careful": it stops before the wall without leaving much unused.
    # Set lower (e.g. 70) to be "polite" and reserve headroom for interactive
    # work; there is deliberately no second `reserve` knob, which would be a
    # subtraction the reader has to perform.
    five_hour_ceiling: float = 90
    seven_day_ceiling: float = 90

    @field_validator("max_wait", "unknown_reset_wait", "reset_skew")
    @classmethod
    def _durations_parse(cls, v: str) -> str:
        from llama.pacing import parse_duration
        parse_duration(v)
        return v


class Config(_StrictModel):
    root: Path = DEFAULT_ROOT
    delivery_path: Path | None = None
    audio_format: Literal["mp3", "flac"] = "mp3"
    llm: dict[str, LLMTaskConfig] = Field(default_factory=dict)
    setlistfm: SetlistFMConfig = Field(default_factory=SetlistFMConfig)
    jerrybase: JerrybaseConfig = Field(default_factory=JerrybaseConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    artists: ArtistsConfig = Field(default_factory=ArtistsConfig)
    winnow: WinnowConfig = Field(default_factory=WinnowConfig)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
    pacing: PacingConfig = Field(default_factory=PacingConfig)
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
# gemini-2.5-flash / claude-sonnet-5 / claude-opus-5 on openrouter.
# Defaults: medium for most tasks; high for interpret, deep_research and brief;
# low for vet_research.
# A failed validation's final retry escalates one tier (pins never escalate).


# [llm.deep_research]
# pin research to the claude CLI when the default backend is openrouter: its
# agentic multi-step research is stronger, and quality is audible on air
# backend = "claude_cli"


# [llm.brief]
# example: cheaper briefing
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


[jerrybase]
# vendored offline set-structure evidence (break anchoring +
# set-count/venue/multi-event tripwires); set false to ignore the dataset
# entirely
enabled = true


[winnow]
# review-fetch budget: when more survivors than this, the best-evidenced are
# sampled for scoring
max_metadata_fetch = 40


[pacing]
# When the backend refuses because a usage window is exhausted, wait it out
# instead of failing every remaining show. Set enabled = false to restore the
# old behaviour (the run fails the show and moves on).
enabled = true

# Sleep through the wait (true) or checkpoint the session and exit 0 (false).
# Either way the run resumes with `llama run resume <name>`; stages skip work
# already done, so resuming costs nothing for shows already packaged.
wait = true

# Never sleep longer than this. A wait beyond it checkpoints instead - which
# is what keeps a 7-day window from parking the process for days. Raise it
# (e.g. --max-wait 30h) to deliberately wait out a weekly reset.
max_wait = "6h"

# How long to wait when the refusal names no reset time.
unknown_reset_wait = "1h"

# Added to the reset instant before resuming, so we do not race the window.
reset_skew = "2m"

# Pause when a meter plus the projected next show would cross these. 90 is
# careful - it stops before the wall. Lower them (e.g. 70) to reserve
# headroom for your own interactive sessions; the meter is account-wide.
five_hour_ceiling = 90
seven_day_ceiling = 90


[artists]
# hide artists below these floors from the index
min_recordings = 25
min_downloads = 50000

# LLM artist-match budget for artist-less queries
max_matched = 20


[structure]
# hold single-set shows longer than this for review
guard_min_minutes = 150

# below this share of song-like tracks matched, fall back to LLM realignment
# and then to a review flag. Does NOT gate jerrybase break anchoring, which
# runs on its own evidence whenever the dataset covers the show.
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
