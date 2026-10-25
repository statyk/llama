"""Scheduler building blocks: estimates of a show's AAC frame count made from
the package scan alone, before any analysis (spec "Planning" -> "Exact timing")."""

from collections.abc import Callable
from pathlib import Path

from transmitter import aacenc, mp3info
from transmitter.grid import SAMPLE_RATE
from transmitter.station import Show

CLIP_FALLBACK_SECONDS = 120.0
UNVOICED_CLIP_ALLOWANCE_SECONDS = 240.0


def estimate_frames(show: Show, *, pause_samples: int, extra: int,
                    clip_seconds: Callable[[Path, int | None], float | None] = mp3info.mp3_seconds) -> int:
    """The AAC frame count render would produce, estimated from the manifest's
    total duration, each clip's own MP3 header and the join pauses."""
    seconds = float(show.meta.get("total_duration_sec") or 0.0)
    sizes = show.meta.get("sizes") or {}
    joins = 0
    prev = None
    for e in show.entries:
        if e.kind == "clip":
            secs = clip_seconds(show.dir / e.path, sizes.get(e.path))
            seconds += CLIP_FALLBACK_SECONDS if secs is None else secs
        if prev is not None and "clip" in (prev, e.kind):
            joins += 1
        prev = e.kind
    samples = round(seconds * SAMPLE_RATE) + pause_samples * joins
    return aacenc.frames_for(aacenc.pad_to_frame(samples), extra)
