"""transmitter's config (`~/.transmitter/config.toml`). Strict, like llama's
and emcee's: a typo'd key is an error, not a silently ignored knob."""

import math
import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from transmitter import grid
from transmitter.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".transmitter"


def default_root() -> Path:
    root = os.environ.get("TRANSMITTER_ROOT")
    return Path(root) if root else DEFAULT_ROOT


class _StrictModel(BaseModel):
    """Unknown keys are an error. Set on a shared base because pydantic does
    not propagate model_config to nested models."""
    model_config = ConfigDict(extra="forbid")


class StationConfig(_StrictModel):
    root: Path | None = None                       # NFS path on hugo; needs `.station-root`
    quiet_minutes: float = Field(default=10.0, ge=0)


class PlannerConfig(_StrictModel):
    seed: int = 0
    # A fresh run (first start, or after an outage longer than the lead) begins
    # this far ahead of now: long enough to analyse, encode and upload the
    # first show's opening batch before it airs.
    start_delay_minutes: float = Field(default=10.0, gt=0)


class RenderConfig(_StrictModel):
    ffmpeg: str = "ffmpeg"
    lead_hours: float = Field(default=24.0, gt=0)
    low_water_hours: float = Field(default=20.0, gt=0)
    music_target_lufs: float = -16.0
    speech_target_lufs: float = -16.0
    clip_pause_seconds: float = Field(default=0.75, ge=0)
    show_gap_seconds: float = Field(default=2.0, ge=0)

    @model_validator(mode="after")
    def _low_water_below_lead(self):
        if self.low_water_hours >= self.lead_hours:
            raise ValueError("render.low_water_hours must be below render.lead_hours")
        return self


# The smallest prune margin that cannot delete a segment a player may still
# request (spec "Clock"). The live playlist lists a window of k = 6 segments
# and keeps listing through a grace of up to 3 segments past `last`, so a
# segment can still be listed (6 + 3) * d = 92.16 s after it started; a CDN
# copy of live.m3u8 can be up to its max-age (5 s) staler; and a player sits
# behind the live edge and may stall or rebuffer before fetching what it was
# handed -- allow 120 s for that and for clock skew between hugo and the
# clock worker. 92.16 + 5 + 120 = 217.16 s, rounded up to whole minutes = 4.
# With a lookahead L (amendment A4, amended 2026-10-12) the window ends at
# cur + L, so a segment stays listed (window - L + grace) * d after it starts:
# the deployed 16 / 12 / 3 give 7 * d = 71.68 s, inside the 9 * d above
# (pinned by antenna's test/wrangler-config.test.ts), so the floor holds.
_LIVE_WINDOW_SEGMENTS = 6
_LIVE_GRACE_SEGMENTS = 3
_LIVE_PLAYLIST_MAX_AGE_S = 5
_PLAYER_LAG_ALLOWANCE_S = 120
PRUNE_MARGIN_FLOOR_MINUTES = float(math.ceil(
    ((_LIVE_WINDOW_SEGMENTS + _LIVE_GRACE_SEGMENTS) * grid.D_US / 1_000_000
     + _LIVE_PLAYLIST_MAX_AGE_S + _PLAYER_LAG_ALLOWANCE_S) / 60))


class PublishConfig(_StrictModel):
    account_id: str | None = None
    bucket: str | None = None
    endpoint_url: str | None = None
    batch_segments: int = Field(default=360, ge=1)
    # ~2x the expected daily count: 86400/10.24 = 8,438 segments, plus the
    # timeline/horizon/notes/page writes of each publish batch and prune's
    # horizon rewrites (at most one per prune_min_segments, ~141/day at 60)
    # ~= 8.9k/day.
    daily_put_budget: int = Field(default=17_500, ge=1)
    prune_margin_minutes: float = Field(default=10.0, ge=PRUNE_MARGIN_FLOOR_MINUTES)
    # prune (one horizon PUT + free deletes) only once this many are prunable
    prune_min_segments: int = Field(default=60, ge=1)
    guard_check_minutes: float = Field(default=15.0, ge=0)


class AlertsConfig(_StrictModel):
    """hugo's alert channels (spec "Alerts and operations"). Secrets come from
    the service's env file: SMTP_USERNAME, SMTP_PASSWORD, NTFY_TOKEN."""
    email_to: str | None = None
    email_from: str | None = None                  # default: SMTP_USERNAME
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    ntfy_url: str | None = None                    # https://ntfy.sh/<topic>
    repeat_hours: float = Field(default=6.0, gt=0)
    # Dead clock: the public live.m3u8, dated by its newest segment's start
    # minus its own hold-back (the segment airing when it was written), older
    # than this, twice in a row. At least 3 d (spec); the default allows the measured cron lags.
    dead_clock_seconds: float = Field(default=120.0, ge=31)
    # Dead guard: state/guard.json last evaluated longer ago than this. hugo
    # sees the evaluation time through a cache refreshed every [publish]
    # guard_check_minutes, and the guard evaluates every 15 minutes plus the
    # cron lag: at least guard_check_minutes + 16 (TransmitterConfig checks).
    guard_stale_minutes: float = Field(default=45.0, gt=0)


class AntennaConfig(_StrictModel):
    dir: Path | None = None            # the repo's antenna/ (templates/show.html)
    site_url: str | None = None        # public base URL, for Open Graph links
    station_name: str = "llama radio"


class InterstitialsConfig(_StrictModel):
    dir: Path | None = None            # absolute; default: <station root>/interstitials

    @field_validator("dir")
    @classmethod
    def _absolute(cls, v: Path | None) -> Path | None:
        if v is not None and not v.is_absolute():
            raise ValueError("interstitials.dir must be an absolute path (a relative one would "
                             "resolve against the service's cwd)")
        return v


class TransmitterConfig(_StrictModel):
    root: Path = Field(default_factory=default_root)
    station: StationConfig = Field(default_factory=StationConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    antenna: AntennaConfig = Field(default_factory=AntennaConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    interstitials: InterstitialsConfig = Field(default_factory=InterstitialsConfig)

    @model_validator(mode="after")
    def _guard_stale_outlasts_the_cache(self):
        floor = self.publish.guard_check_minutes + 16
        if self.alerts.guard_stale_minutes < floor:
            raise ValueError(f"alerts.guard_stale_minutes must be at least publish.guard_check_minutes + 16 ({floor:g}): "
                             "anything shorter alarms while the guard is healthy")
        return self


def load_config(path: Path | None = None) -> TransmitterConfig:
    path = path or default_root() / "config.toml"
    if not path.exists():
        return TransmitterConfig()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc
    try:
        return TransmitterConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


# Seeded by `transmitter config init`; kept equal to the defaults above by
# tests_transmitter/test_config.py::test_template_parses_to_the_defaults.
DEFAULT_CONFIG_TOML = """\
# transmitter config - seeded by `transmitter config init`.
# A value here REPLACES its built-in default; unknown keys are errors.

# workspace (plan, caches, rendered audio); default ~/.transmitter or $TRANSMITTER_ROOT
# root = "/home/station/.transmitter"

[station]
# the delivered-packages folder (NFS on hugo); must contain a `.station-root`
# marker file, or `plan` refuses (a down NFS mount is an empty directory)
# root = "/nfs/media/station"
# a package must be untouched this long before it may air
quiet_minutes = 10.0

[interstitials]
# station IDs (id-*.mp3) and schedule announcements (ann-<id>.mp3); transmitter
# only reads this folder. Default: <station root>/interstitials
# dir = "/nfs/media/station/interstitials"

[planner]
# seed of the fixed shuffled order
seed = 0
# a fresh run (first start, or after an outage longer than the lead) begins
# this far ahead of now
start_delay_minutes = 10.0

[render]
ffmpeg = "ffmpeg"
# keep this much audio published ahead of now; render again below low water
lead_hours = 24.0
low_water_hours = 20.0
# per-show music loudness ceiling (tracks only) and per-clip speech target;
# gain = min(target - I, -1 dBTP - TP)
music_target_lufs = -16.0
speech_target_lufs = -16.0
# pause between a DJ clip and a track; gap between shows
clip_pause_seconds = 0.75
show_gap_seconds = 2.0

[publish]
# R2 endpoint is https://<account_id>.r2.cloudflarestorage.com unless
# endpoint_url is set. Keys come from the environment:
# R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY.
# account_id = "..."
# bucket = "lma-radio"
# endpoint_url = "https://..."
# segments per publish batch (state/horizon.json advances once per batch)
batch_segments = 360
# own-write cap: publishing stops (and alerts) past this many PUTs per UTC day
daily_put_budget = 17500
# delete segments that started more than this long ago; at least 4 (below
# that a player may still request a deleted segment)
prune_margin_minutes = 10.0
# ...but only once this many are due (each prune rewrites state/horizon.json)
prune_min_segments = 60
# read state/guard.json at most this often
guard_check_minutes = 15.0

[antenna]
# the repo's antenna/ directory (the show-page template is templates/show.html)
# dir = "/home/station/llama/antenna"
# public base URL, for Open Graph links on show pages and the dead-clock
# check (which fetches <site_url>/live.m3u8 once a minute; unset = no check)
# site_url = "https://radio.example.org"
station_name = "llama radio"

[alerts]
# Email over SMTP with STARTTLS (credentials from the env file: SMTP_USERNAME,
# SMTP_PASSWORD -- for Gmail an App Password) and ntfy (NTFY_TOKEN, optional).
# With neither, alerts only reach the log (journald).
# email_to = "you@example.com"
# email_from = "station@example.com"      # default: SMTP_USERNAME
smtp_host = "smtp.gmail.com"
smtp_port = 587
# ntfy_url = "https://ntfy.sh/<your-topic>"
# re-send a still-firing alert at most this often
repeat_hours = 6.0
# the public live.m3u8 older than this (twice in a row): the clock is dead
dead_clock_seconds = 120.0
# state/guard.json not evaluated for this long: the guard is dead
# (at least [publish] guard_check_minutes + 16)
guard_stale_minutes = 45.0
"""
