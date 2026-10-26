import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator, model_validator

from herder import LLMSettings, TaskConfig

from emcee.artists import normalize_artist
from emcee.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".emcee"


class _StrictModel(BaseModel):
    """Unknown keys are an error, not a silent drop.

    config.toml is the one file this design expects a human to hand-edit, so
    a typo'd knob must fail loudly rather than leave the default in place.
    Set on a shared base because pydantic does not propagate model_config to
    nested models -- on EmceeConfig alone, every section below it stays
    permissive. emcee's own base, not llama's `_StrictModel` -- emcee never
    imports llama (enforced by test_no_llama_imports.py).
    """
    model_config = ConfigDict(extra="forbid")


Tier = Literal["low", "medium", "high"]

# emcee's task vocabulary is much narrower than llama's -- it only ever
# scripts, never researches or curates.
TASK_KEYS = ["scriptwrite", "rephrase"]

# Task -> tier defaults. scriptwrite quality is audible on air, so it
# defaults to high (mirrors llama's config.py DEFAULT_TIERS pattern).
# rephrase rewords one sentence a TTS content filter refused -- small, so medium.
DEFAULT_TIERS = {
    "scriptwrite": "high",
    "rephrase": "medium",
}


def default_root() -> Path:
    """Resolve the emcee workspace root: `EMCEE_ROOT` env override, else
    `~/.emcee`. Used as `EmceeConfig.root`'s default (evaluated fresh at
    every construction, so a test that sets `EMCEE_ROOT` after import still
    gets the right root) and as `load_config`'s default search location."""
    root = os.environ.get("EMCEE_ROOT")
    return Path(root) if root else DEFAULT_ROOT


class LLMTaskConfig(_StrictModel, TaskConfig):
    # Narrows the shared type so a config-file tier typo fails at parse time.
    tier: Tier | None = None


class StationConfig(_StrictModel):
    root: Path | None = None   # the delivered-packages folder; required by run/status


# Hosted TTS backends: each has an API key and a model, configured in its own
# [tts.<backend>] table wherever it voices (house or pin).
HOSTED_BACKENDS = ("voxtral", "elevenlabs")


class HostedTTSConfig(_StrictModel):
    """[tts.voxtral] / [tts.elevenlabs]: applies wherever that backend voices
    (as [tts] backend or as a presenter pin). The provider's env var
    (MISTRAL_API_KEY / ELEVENLABS_API_KEY) still wins over api_key."""
    api_key: str | None = None
    model: str | None = None


class MlxAudioConfig(_StrictModel):
    """[tts.mlx_audio]: the local mlx-audio server. `model` has no default; it
    is required only when something resolves to mlx_audio (checked at
    resolution), so a table holding only stt_model is valid."""
    url: str = "http://127.0.0.1:8000"
    model: str | None = None
    timeout_s: float = 600                 # per sentence request
    stt_model: str | None = None           # speech-to-text model on the same server


VerifyBackend = Literal["mlx_audio", "voxtral", "elevenlabs"]


class VerifyConfig(_StrictModel):
    """[tts.verify]: transcript verification of newly synthesized audio."""
    backends: list[VerifyBackend] = Field(default_factory=list)   # default off


@dataclass(frozen=True)
class Chunking:
    """How a chunked render packs and finishes a segment (spec 2026-10-26)."""
    ceiling: int
    room_tone: bool


class TTSConfig(_StrictModel):
    """Spoken DJ patter (text-to-speech of the DJ script).

    `backend` is the HOUSE voice and every unpinned presenter's backend --
    except that an unpinned presenter never inherits mlx_audio (resolution
    rejects it), so changing the house voice never moves a presenter."""
    backend: str = "voxtral"            # or "elevenlabs" / "mlx_audio" / "fake"
    voice: str | None = None            # voxtral preset name / elevenlabs voice_id
    voice_clone: str | None = None      # path to a reference clip; when set, the house voice clones it
    voice_clone_text: str | None = None  # transcript of voice_clone (required on mlx_audio)
    model: str | None = None            # legacy: the HOUSE hosted backend's model
    api_key: str | None = None          # legacy: the HOUSE hosted backend's key (env wins)
    chunk: bool = True                  # synthesize each DJ-notes segment in chunks
                                         # and concatenate, instead of one call
                                         # per segment (better prosody, loudness-normalized;
                                         # needs lameenc). false = one call per segment
    chunk_chars: StrictInt = Field(default=250, ge=50, le=1000)  # packing ceiling, characters
    room_tone: bool = True              # fill exact-silence gaps in chunked clips
    bed: str | None = None              # path to a 24kHz mono 16-bit WAV played
                                         # under the DJ voice; None = no bed
    bed_gain_db: float = -20.0          # bed loudness under the voice (station-level)
    voxtral: HostedTTSConfig = Field(default_factory=HostedTTSConfig)
    elevenlabs: HostedTTSConfig = Field(default_factory=HostedTTSConfig)
    mlx_audio: MlxAudioConfig = Field(default_factory=MlxAudioConfig)
    verify: VerifyConfig = Field(default_factory=VerifyConfig)

    def chunking(self, *, enabled: bool) -> Chunking | None:
        """The chunking settings when chunked rendering is on, else None."""
        return Chunking(self.chunk_chars, self.room_tone) if enabled else None

    @model_validator(mode="after")
    def _check_keys_and_verify(self):
        if self.backend == "mlx_audio":
            if self.api_key is not None:
                raise ValueError(
                    "[tts] api_key is not valid when [tts] backend is mlx_audio (it needs "
                    "no key); put a hosted backend's key in [tts.voxtral] or "
                    "[tts.elevenlabs] api_key")
            if self.model is not None:
                raise ValueError("[tts] model is not valid when [tts] backend is mlx_audio; "
                                 "set [tts.mlx_audio] model")
        elif self.backend in HOSTED_BACKENDS:
            sub = getattr(self, self.backend)
            for key in ("api_key", "model"):
                if getattr(self, key) is not None and getattr(sub, key) is not None:
                    raise ValueError(
                        f"[tts] {key} and [tts.{self.backend}] {key} are both set; they "
                        "mean the same setting, keep one")
        if self.verify.backends and not self.mlx_audio.stt_model:
            raise ValueError("[tts.verify] backends needs [tts.mlx_audio] stt_model (the "
                             "speech-to-text model verification transcribes with)")
        return self


class Assignment(_StrictModel):
    presenter: str
    title: str | None = None


class ArtistRule(_StrictModel):
    """One `[assign.artists]` rule: voice this artist's shows as `profile`,
    whatever profile llama delivered them under -- or, with `from`, only
    when llama's profile is one of those listed."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    profile: str
    from_: list[str] | None = Field(default=None, alias="from")


class AssignConfig(_StrictModel):
    default: str | None = None                          # station-default presenter id
    profiles: dict[str, Assignment] = Field(default_factory=dict)
    artists: dict[str, ArtistRule] = Field(default_factory=dict)

    @field_validator("artists", mode="before")
    @classmethod
    def _artist_shorthand(cls, value):
        # `"Artist" = "profile"` is shorthand for `{ profile = "profile" }`.
        if isinstance(value, dict):
            return {key: {"profile": rule} if isinstance(rule, str) else rule
                    for key, rule in value.items()}
        return value

    @model_validator(mode="after")
    def _check_artists(self):
        """A rule naming a profile with no [assign.profiles] entry would
        silently route shows to the default presenter; two keys normalizing
        alike would make the winner depend on file order; an empty key or
        an empty `from` can never match; an empty [assign.profiles] name
        reads back from a voiced manifest as "no profile", so its packages
        would be re-voiced on every run. All are load errors."""
        if "" in self.profiles:
            raise ValueError('[assign.profiles.""]: profile names must be non-empty')
        seen: dict[str, str] = {}
        for key, rule in self.artists.items():
            norm = normalize_artist(key)
            if not norm:
                raise ValueError(f'[assign.artists] "{key}" normalizes to an empty artist name')
            if norm in seen:
                raise ValueError(f'[assign.artists] "{seen[norm]}" and "{key}" name the same '
                                 f'artist (both normalize to "{norm}"); keep one')
            seen[norm] = key
            if rule.from_ is not None and not rule.from_:
                raise ValueError(f'[assign.artists] "{key}": from = [] can never match; '
                                 "remove it to match every delivered profile")
            if rule.profile not in self.profiles:
                raise ValueError(f'[assign.artists] "{key}" targets profile "{rule.profile}", '
                                 f"which has no [assign.profiles.{rule.profile}] entry "
                                 "(add the entry first)")
        return self


class EmceeConfig(_StrictModel):
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
# gemini-2.5-flash / claude-sonnet-5 / claude-opus-5 on openrouter.
# Default: high (scriptwrite quality is audible on air).
# A failed validation's final retry escalates one tier (pins never escalate).
# tier = "medium"
# example: exact pin, bypasses tiers
# model = "claude-opus-4-8"

[llm.rephrase]
# rewords a DJ-script sentence the TTS content filter refused (rare).
# An unset task falls back to [llm.default], else claude_cli -- so if you
# change scriptwrite's backend above, change this one too.
backend = "claude_cli"
# Default: medium.
# tier = "low"


# [llm.tiers.openrouter]
# retarget what a tier means per backend
# medium = "deepseek/deepseek-chat-v3"


# spoken DJ patter: per-segment MP3 clips of the DJ script land in
# package/dj-audio/ (one set<key>-intro per non-encore set, then 99-outro),
# tied together by the manifest's dj_audio block.
# [tts]
# hosted Mistral Voxtral TTS (default); or "elevenlabs"; or "mlx_audio" (local,
# see [tts.mlx_audio] below); or "fake" for tests
# backend = "voxtral"

# the HOUSE voice: voxtral preset name (or elevenlabs voice_id), used when
# a profile has no presenter assignment
# voice = "..."

# path to a 3-25s reference WAV; when set, the house voice clones it
# (ignores `voice`)
# voice_clone = "..."

# word-for-word transcript of voice_clone; required when the house voice is
# on mlx_audio, ignored by voxtral
# voice_clone_text = "..."

# legacy spellings of the HOUSE hosted backend's model and key (valid only
# while backend is voxtral/elevenlabs; the same key in [tts.<backend>] too is
# an error). Per-backend default model when unset
# (voxtral-mini-tts-2603 / eleven_multilingual_v2)
# model = "..."

# MISTRAL_API_KEY / ELEVENLABS_API_KEY env (env wins)
# api_key = "..."

# Per-backend tables. A hosted backend's table applies wherever it voices:
# as [tts] backend or as a presenter's `tts` pin.
# [tts.voxtral]
# api_key = "..."            # MISTRAL_API_KEY env wins
# model = "voxtral-mini-tts-2603"

# [tts.elevenlabs]
# api_key = "..."            # ELEVENLABS_API_KEY env wins
# model = "eleven_multilingual_v2"

# Local TTS through mlx-audio's server on this Mac (see the README runbook).
# A presenter opts in with tts = "mlx_audio"; the house voice only with
# [tts] backend = "mlx_audio" -- and then every presenter must pin `tts`.
# [tts.mlx_audio]
# url = "http://127.0.0.1:8000"
# model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
# timeout_s = 600            # seconds per sentence request
# stt_model = "mlx-community/whisper-large-v3-turbo-asr-fp16"  # speech-to-text model on the same server

# Transcript verification: transcribe each newly synthesized clip on the
# mlx-audio server and re-synthesize once on a gross mismatch; a second
# failure fails the package. Needs [tts.mlx_audio] stt_model. Default off.
# [tts.verify]
# backends = ["mlx_audio"]

# Assignment is keyed by the llama profile name stamped in the manifest as
# source.profile (see [assign] below) -- not by anything in this section.

# synthesize each segment in chunks and concatenate (single MP3
# encode at the end) instead of one TTS call per whole segment; noticeably
# better prosody/pacing on longer DJ patter at the cost of more provider
# round-trips per segment. Chunked clips are loudness-normalized per chunk;
# unchunked clips without a bed ship the provider's own MP3 un-normalized.
# Requires the `lameenc` dependency (installed by default). Default true.
# chunk = false
# the packing ceiling in characters, 50-1000, one value for every backend;
# chunks follow the script's paragraphs and never end inside a sentence.
# chunk_chars = 250
# fill exact-silence gaps in chunked clips with the clip's own quietest sound;
# set false to turn it off.
# room_tone = true

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
#
# Artist rules: voice every show by an artist as another profile, whatever
# profile llama delivered it under (or only from the profiles in `from`).
# Names match loosely (case, "&"/"and", apostrophes, one trailing [...], a
# leading "The"). A rule's profile needs its own [assign.profiles.<name>]
# entry: add that first, or every emcee command refuses to start.
# [assign.artists]
# "Tedeschi Trucks Band" = "southern"
# "JJ Grey and MOFRO" = { profile = "southern", from = ["funk"] }
"""
