"""`<TRANSMITTER_ROOT>/announce.toml`: the concert-announcement settings. Strict
(a typo'd key is an error) and off by default. Loading never raises: an invalid
file means "off" plus one `announce-config` alert."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from transmitter import alerts
from transmitter.workspace import Workspace

DEFAULT_ID_TEXT = "You're listening to LMA Radio. Live concert tapes from the Live Music Archive."


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Gaps(_Strict):
    """Seconds of silence around the spoken pieces and the bed."""
    after_id: float = Field(default=0.4, ge=0, le=2.0)
    after_comma: float = Field(default=0.15, ge=0, le=2.0)
    after_period: float = Field(default=0.3, ge=0, le=2.0)
    within: float = Field(default=0.05, ge=0, le=2.0)
    bed_lead_in: float = Field(default=0.5, ge=0, le=2.0)
    bed_tail: float = Field(default=1.0, ge=0, le=2.0)


class AnnounceSettings(_Strict):
    enabled: bool = False
    id_text: str = Field(default=DEFAULT_ID_TEXT, min_length=1)
    bed: Path | None = None
    bed_under_db: float = Field(default=20.0, ge=0, le=60)
    gaps: Gaps = Field(default_factory=Gaps)

    @field_validator("id_text")
    @classmethod
    def _single_line(cls, v: str) -> str:
        if "\n" in v or "\r" in v:
            raise ValueError("id_text must be a single line")
        return v

    @field_validator("bed")
    @classmethod
    def _absolute(cls, v: Path | None) -> Path | None:
        if v is not None and not v.is_absolute():
            raise ValueError("bed must be an absolute path")
        return v

    @model_validator(mode="after")
    def _bed_required(self) -> "AnnounceSettings":
        if self.enabled and self.bed is None:
            raise ValueError("bed is required when enabled = true")
        return self


@dataclass(frozen=True)
class LoadedSettings:
    settings: AnnounceSettings
    source: Literal["file", "missing", "invalid"]
    problem: str | None


def _describe(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "bed"
        if not err["loc"] and "bed" in err["msg"]:
            loc = "bed"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def load_settings(ws: Workspace, *, alert: bool) -> LoadedSettings:
    """The settings, or defaults (off) when the file is missing or invalid.
    Never raises; alerts at most once per call, only for an invalid file."""
    path = ws.announce_path
    problem: str
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
        return LoadedSettings(AnnounceSettings.model_validate(data), "file", None)
    except FileNotFoundError:
        return LoadedSettings(AnnounceSettings(), "missing", None)
    except UnicodeDecodeError as e:
        problem = f"not valid UTF-8 ({e})"
    except tomllib.TOMLDecodeError as e:
        problem = f"not valid TOML ({e})"
    except ValidationError as e:
        problem = _describe(e)
    except OSError as e:
        problem = f"cannot be read ({e})"
    if alert:
        alerts.alert("announce-config", f"{path} is invalid, announcements are off: {problem}")
    return LoadedSettings(AnnounceSettings(), "invalid", problem)
