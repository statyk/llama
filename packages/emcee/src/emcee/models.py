"""emcee's own manifest-contract models.

emcee never imports llama, so it defines its own copies of the two manifest
blocks it owns -- shape-compatible with llama's `DJNotes`
and `DJAudio` (llama's copy carries the newer fields as optional) (packages/llama/src/llama/models.py). llama's
models.py keeps its own `DJNotes`/`DJAudio` too, solely as passthrough
documentation of a block it no longer writes (see the split-architecture
design spec, section 5); the two must be kept shape-compatible by hand if
either side changes.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ScriptNotes(BaseModel):
    """Scriptwriting output -- written to the package manifest's `dj_notes`
    block and rendered to `dj-notes.md`. `set_intros` is keyed by non-encore
    set label only ("1", "2", ...); the encore folds into `outro`."""

    context: str = ""  # one-line era/tour context
    set_intros: dict[str, str]  # combined lead-in per non-encore set
    outro: str
    mentioned_songs: list[str] = Field(default_factory=list)


class RephrasedSegment(BaseModel):
    """`rephrase` task output: one DJ segment with only the sentence a TTS
    content filter refused reworded; every other sentence verbatim."""

    text: str


class DJClips(BaseModel):
    """The clip paths `_synthesize_dj_audio` renders (package-relative,
    dj-audio/...). Everything `broadcast.m3u` assembly needs."""

    set_intros: dict[str, str]  # one lead-in clip per non-encore set
    outro: str


class TTSRecord(BaseModel):
    """How one package's clips were synthesized. `backend` comes from the
    TTS resolution; `model`/`voice` from the provider instance -- the same
    values the render-cache key uses, so one record per package is exact.
    `voice` is a preset name, or `clone:<sha256[:16]>` of the reference clip
    (voxtral) or of the clip plus its transcript (mlx_audio)."""

    backend: str
    model: str | None
    voice: str


class DJAudioBlock(DJClips):
    """The manifest's `dj_audio` block as emcee writes it.

    `profile`/`profile_source`/`tts` are required with no defaults, so a
    legacy block (which lacks them) round-tripped through this model fails
    loudly instead of writing `"profile": null` -- which would make the
    package pending. Legacy blocks are only ever updated as raw dicts."""

    # Id of the presenter that voiced this package; None = the house narrator.
    # Always serialized, so a house-voiced manifest carries `"presenter": null`
    # -- distinguishable from a legacy manifest that lacks the key entirely.
    presenter: str | None = None
    profile: str | None                                  # the effective profile voiced as
    profile_source: Literal["move", "artist", "llama"]  # where that profile came from
    tts: TTSRecord                                       # how its clips were synthesized
