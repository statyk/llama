"""emcee's own manifest-contract models.

emcee never imports llama, so it defines its own copies of the two manifest
blocks it owns -- shape-identical to llama's `DJNotes`
(packages/llama/src/llama/models.py:206) and `DJAudio` (:252). llama's
models.py keeps its own `DJNotes`/`DJAudio` too, solely as passthrough
documentation of a block it no longer writes (see the split-architecture
design spec, section 5); the two must be kept shape-compatible by hand if
either side changes.
"""

from pydantic import BaseModel, Field


class ScriptNotes(BaseModel):
    """Scriptwriting output -- written to the package manifest's `dj_notes`
    block and rendered to `dj-notes.md`. `set_intros` is keyed by non-encore
    set label only ("1", "2", ...); the encore folds into `outro`."""

    context: str = ""  # one-line era/tour context
    set_intros: dict[str, str]  # combined lead-in per non-encore set
    outro: str
    mentioned_songs: list[str] = Field(default_factory=list)


class DJAudioBlock(BaseModel):
    """Per-segment spoken DJ clips, as package-relative paths (dj-audio/...).
    Written to the package manifest's `dj_audio` block."""

    set_intros: dict[str, str]  # one lead-in clip per non-encore set
    outro: str
