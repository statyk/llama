"""Central exception taxonomy.

`TransmitterError` is the base for expected, operator-actionable failures:
the CLI boundary prints `error: <message>` (plus indented `details`) and
exits 1. Anything else is a bug and surfaces as a traceback. This module
imports nothing from the package, to stay import-cycle-free.
"""


class TransmitterError(Exception):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class ConfigError(TransmitterError):
    """config.toml could not be parsed or failed validation."""


class AdtsError(TransmitterError):
    """Bytes that should be an ADTS frame sequence are not."""


class EncodeError(TransmitterError):
    """ffmpeg's AAC encode failed."""


class DecodeError(TransmitterError):
    """ffmpeg could not decode a package's audio file."""


class AnalysisError(TransmitterError):
    """A show's durations/loudness could not be measured."""


class StationRootError(TransmitterError):
    """The station root is unset, missing, or lacks its `.station-root` marker."""


class PlanError(TransmitterError):
    """The plan cannot be extended (e.g. nothing eligible)."""


class LayoutError(TransmitterError):
    """The plan's frame layout is inconsistent with what is on disk."""


class RenderError(TransmitterError):
    """A show could not be rendered (the show is skipped and re-planned)."""


class AnalysisStale(RenderError):
    """A file decoded to a different sample count than its cached analysis says
    (the package changed, or the decoder did). The engine drops the cached
    analysis so the next attempt re-measures."""


class FrameCountDrift(RenderError):
    """The encoder produced a different frame count than planned. Fatal: it
    means the frame-count model is wrong on this ffmpeg, not that one show is bad."""


class PublishError(TransmitterError):
    """An upload/delete against R2 failed after retries."""


class PublishLocked(TransmitterError):
    """Another publish or prune holds the local lock."""


class PutBudgetExceeded(TransmitterError):
    """The local daily PUT budget is spent; publishing stops until tomorrow (UTC)."""


class CloudStateError(TransmitterError):
    """An operator command could not read or write the station's cloud state
    (state/offair.json, state/budget.json, state/guard.json)."""


class CloudDocumentError(CloudStateError):
    """The object was read but is not a JSON object (a corrupt or hand-edited
    document), as against an access or transport failure."""
