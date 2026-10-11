"""Per-show encode (spec "Per-show encode, frame-count segmentation", "Joins",
"Loudness").

A show's whole broadcast.m3u is decoded gaplessly, gained (tracks by the
show's track-set gain, each DJ clip by its own speech gain), joined (no
silence track->track; `clip_pause` around clips), padded to a whole frame and
encoded once. The encoder's output -- priming and flush frames included -- is
the show's frame count; it must equal `planned_frames`, which the planner used
to place the next show."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts
from transmitter.analysis import FileAnalysis, ShowAnalysis, gain_db
from transmitter.audio import iter_decode
from transmitter.config import RenderConfig
from transmitter.errors import AnalysisStale, FrameCountDrift, RenderError
from transmitter.grid import samples_for_seconds
from transmitter.station import Show


@dataclass(frozen=True)
class FileSpan:
    path: str
    kind: str
    title: str
    start_sample: int     # within the show, before encoder priming
    samples: int


@dataclass(frozen=True)
class ShowLayout:
    spans: tuple[FileSpan, ...]
    content_samples: int
    padded_samples: int


def show_layout(analysis: ShowAnalysis, pause_samples: int) -> ShowLayout:
    spans: list[FileSpan] = []
    pos = 0
    prev: str | None = None
    for f in analysis.files:
        if prev is not None and "clip" in (prev, f.kind):
            pos += pause_samples
        spans.append(FileSpan(f.path, f.kind, f.title, pos, f.samples))
        pos += f.samples
        prev = f.kind
    return ShowLayout(tuple(spans), pos, aacenc.pad_to_frame(pos))


def planned_frames(analysis: ShowAnalysis, pause_samples: int, extra: int) -> int:
    return aacenc.frames_for(show_layout(analysis, pause_samples).padded_samples, extra)


@dataclass(frozen=True)
class RenderSettings:
    ffmpeg: str
    music_target_lufs: float
    speech_target_lufs: float
    clip_pause_samples: int

    @classmethod
    def from_config(cls, cfg: RenderConfig) -> "RenderSettings":
        return cls(cfg.ffmpeg, cfg.music_target_lufs, cfg.speech_target_lufs,
                   samples_for_seconds(cfg.clip_pause_seconds))


def file_gain(f: FileAnalysis, analysis: ShowAnalysis, settings: RenderSettings) -> float:
    if f.kind == "clip":
        db = gain_db(settings.speech_target_lufs, f.i_lufs, f.tp_dbfs)
    else:
        db = gain_db(settings.music_target_lufs, analysis.tracks_i_lufs, analysis.tracks_tp_dbfs)
    return 10.0 ** (db / 20.0)


def render_show(show: Show, analysis: ShowAnalysis, out_path: Path, *,
                settings: RenderSettings, extra: int) -> int:
    if analysis.key != show.key or [f.path for f in analysis.files] != [e.path for e in show.entries]:
        raise RenderError(f"{show.slug}: analysis does not match the package's current file set")
    layout = show_layout(analysis, settings.clip_pause_samples)
    expected = aacenc.frames_for(layout.padded_samples, extra)
    enc = aacenc.AacFileEncoder(out_path, settings.ffmpeg)
    try:
        pos = 0
        for span, f in zip(layout.spans, analysis.files):
            enc.write_silence(span.start_sample - pos)
            gain = file_gain(f, analysis, settings)
            n = 0
            for pcm in iter_decode(show.dir / span.path, settings.ffmpeg):
                # The gain rule already bounds true peak at -1 dBTP; the clamp is
                # the safety limiter the spec calls for, and normally never acts.
                enc.write(np.clip(pcm * gain, -1.0, 1.0))
                n += len(pcm)
            if n != span.samples:
                raise AnalysisStale(f"{show.slug}: {span.path} decoded to {n} samples but was "
                                    f"analysed at {span.samples} -- the package changed (or the "
                                    "decoder did); its cached analysis is dropped")
            pos = span.start_sample + n
        enc.write_silence(layout.padded_samples - pos)
        enc.close()
    except BaseException:
        enc.abort()
        raise
    # close() has already renamed the encode into place. Until its frame count
    # is verified it must not survive any failure there, or FrameStore would
    # treat an unverified encode as rendered and the station would wedge on it.
    try:
        frames = len(adts.frame_offsets(Path(out_path).read_bytes())) - 1
        if frames != expected:
            raise FrameCountDrift(f"{show.slug}: encoder produced {frames} frames, expected {expected} "
                                  f"({layout.padded_samples} padded samples + {extra}); the frame-count "
                                  "model does not hold on this ffmpeg")
    except BaseException:
        Path(out_path).unlink(missing_ok=True)
        raise
    return frames
