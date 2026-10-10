"""Per-show analysis (spec: "Durations and loudness come from one decode pass
per show ... cached keyed by the show's file set"): decoded sample counts per
file, integrated loudness + true peak over the tracks only, and per-clip
loudness for DJ clips (their own speech target). Rendering decodes again with
the same decoder and must reproduce these sample counts exactly."""

from dataclasses import asdict, dataclass
from pathlib import Path

from transmitter.audio import LoudnessMeter, iter_decode
from transmitter.errors import AnalysisError
from transmitter.station import Show
from transmitter.workspace import read_json, write_json

ANALYSIS_VERSION = 1
TRUE_PEAK_CEILING_DB = -1.0


@dataclass(frozen=True)
class FileAnalysis:
    path: str
    kind: str
    title: str
    samples: int
    i_lufs: float | None = None      # clips only
    tp_dbfs: float | None = None     # clips only


@dataclass(frozen=True)
class ShowAnalysis:
    key: str
    slug: str
    files: tuple[FileAnalysis, ...]
    tracks_i_lufs: float | None
    tracks_tp_dbfs: float | None
    meta: dict

    def to_json(self) -> dict:
        data = asdict(self)
        data["files"] = [asdict(f) for f in self.files]
        data["version"] = ANALYSIS_VERSION
        return data

    @classmethod
    def from_json(cls, data: dict) -> "ShowAnalysis":
        return cls(key=data["key"], slug=data["slug"],
                   files=tuple(FileAnalysis(**f) for f in data["files"]),
                   tracks_i_lufs=data["tracks_i_lufs"], tracks_tp_dbfs=data["tracks_tp_dbfs"],
                   meta=dict(data["meta"]))


def gain_db(target: float, i_lufs: float | None, tp_dbfs: float | None,
            ceiling: float = TRUE_PEAK_CEILING_DB) -> float:
    """min(target - I, ceiling - TP). The target is a ceiling, so quiet,
    dynamic tapes are not pushed into a limiter; unmeasurable audio (I below
    the gate) is left at unity gain."""
    if i_lufs is None:
        return 0.0
    gain = target - i_lufs
    if tp_dbfs is not None:
        gain = min(gain, ceiling - tp_dbfs)
    return gain


def analyze_show(show: Show, ffmpeg: str = "ffmpeg") -> ShowAnalysis:
    tracks = LoudnessMeter(ffmpeg)
    files: list[FileAnalysis] = []
    try:
        for entry in show.entries:
            clip_meter = LoudnessMeter(ffmpeg) if entry.kind == "clip" else None
            meter = clip_meter or tracks
            n = 0
            try:
                for pcm in iter_decode(show.dir / entry.path, ffmpeg):
                    meter.write(pcm)
                    n += len(pcm)
            except BaseException:
                if clip_meter is not None:
                    clip_meter.abort()
                raise
            if n == 0:
                raise AnalysisError(f"{show.slug}: {entry.path} decoded to no audio")
            loud = clip_meter.finish() if clip_meter is not None else None
            files.append(FileAnalysis(entry.path, entry.kind, entry.title, n,
                                      loud.i_lufs if loud else None, loud.tp_dbfs if loud else None))
        t = tracks.finish()
    except BaseException:
        tracks.abort()
        raise
    return ShowAnalysis(key=show.key, slug=show.slug, files=tuple(files),
                        tracks_i_lufs=t.i_lufs, tracks_tp_dbfs=t.tp_dbfs, meta=dict(show.meta))


def load_cached(cache_dir: Path, key: str) -> ShowAnalysis | None:
    data = read_json(Path(cache_dir) / f"{key}.json")
    if not data or data.get("version") != ANALYSIS_VERSION or data.get("key") != key:
        return None
    return ShowAnalysis.from_json(data)


def load_or_analyze(cache_dir: Path, show: Show, ffmpeg: str = "ffmpeg") -> ShowAnalysis:
    cached = load_cached(cache_dir, show.key)
    if cached is not None:
        return cached
    result = analyze_show(show, ffmpeg)
    write_json(Path(cache_dir) / f"{show.key}.json", result.to_json())
    return result
