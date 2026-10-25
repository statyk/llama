"""Scheduler building blocks: estimates of a show's AAC frame count made from
the package scan alone, before any analysis (spec "Planning" -> "Exact timing")."""

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from transmitter import aacenc, analysis, mp3info, render, station
from transmitter.errors import TransmitterError
from transmitter.grid import SAMPLE_RATE
from transmitter.station import Entry, Show

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


def _safe_mp3_seconds(path: Path, size: int | None) -> float | None:
    """mp3_seconds, but a clip that vanished or went stale mid-scan counts as unknown."""
    try:
        return mp3info.mp3_seconds(path, size)
    except OSError:
        return None


def _date_parts(value) -> tuple[int | None, str | None]:
    if not isinstance(value, str) or len(value) < 10:
        return None, None
    y, m, d = value[0:4], value[5:7], value[8:10]
    if value[4] != "-" or value[7] != "-" or not (y + m + d).isdigit():
        return None, None
    return int(y), f"{m}-{d}"


@dataclass(frozen=True)
class Piece:
    kind: Literal["show", "interstitial"]
    show: Show
    dir: str
    frames: int
    exact: bool

    @property
    def slug(self) -> str:
        return self.show.slug

    @property
    def key(self) -> str:
        return self.show.key

    @property
    def package(self) -> str | None:
        return self.show.slug if self.kind == "show" else None

    @property
    def artist(self) -> str | None:
        return self.show.meta.get("artist")

    @property
    def date(self) -> str | None:
        y, md = _date_parts(self.show.meta.get("date"))
        return None if y is None else f"{y:04d}-{md}"

    @property
    def year(self) -> int | None:
        return _date_parts(self.show.meta.get("date"))[0]

    @property
    def month_day(self) -> str | None:
        return _date_parts(self.show.meta.get("date"))[1]

    @property
    def profile(self) -> str | None:
        return self.show.meta.get("voiced_profile")

    @property
    def role(self) -> str | None:
        return "show" if self.kind == "show" else self.show.meta.get("role")

    @property
    def ann_id(self) -> str | None:
        return self.show.meta.get("ann_id")


class LengthCache:
    """Per-key piece lengths: exact (a cached analysis, or learned this process)
    else estimated. `cache_dir=None` never looks at the analysis cache."""

    def __init__(self, cache_dir: Path | None, pause_samples: int, extra: int):
        self.cache_dir = None if cache_dir is None else Path(cache_dir)
        self.pause_samples = pause_samples
        self.extra = extra
        self._exact: dict[str, int] = {}
        self._estimated: dict[str, int] = {}

    def mark_exact(self, key: str, frames: int) -> None:
        self._exact[key] = frames

    def forget(self, key: str) -> None:
        """Drop what this process learned for `key`, so the next `length`
        re-reads the analysis cache (else estimates)."""
        self._exact.pop(key, None)

    def length(self, show: Show) -> tuple[int, bool]:
        key = show.key
        if key in self._exact:
            return self._exact[key], True
        if self.cache_dir is not None:
            cached = analysis.load_cached(self.cache_dir, key)
            if cached is not None:
                frames = render.planned_frames(cached, self.pause_samples, self.extra)
                self._exact[key] = frames
                return frames, True
        if key not in self._estimated:
            self._estimated[key] = estimate_frames(
                show, pause_samples=self.pause_samples, extra=self.extra,
                clip_seconds=_safe_mp3_seconds)
        return self._estimated[key], False


def build_pool(shows: Sequence[Show], clips: Sequence[Show], *, lengths: LengthCache, clip_dir: str,
               analyze_clip: Callable[[Show], int] | None = None,
               read_only: bool = False) -> tuple[list[Piece], list[tuple[Show, TransmitterError]]]:
    if analyze_clip is None and not read_only:
        raise ValueError("build_pool needs analyze_clip unless read_only=True")
    pieces: list[Piece] = []
    dropped: list[tuple[Show, TransmitterError]] = []
    for show in shows:
        frames, exact = lengths.length(show)
        pieces.append(Piece("show", show, show.dir.name, frames, exact))
    for clip in clips:
        frames, exact = lengths.length(clip)
        if not exact and not read_only:
            try:
                frames = analyze_clip(clip)
            except TransmitterError as exc:
                dropped.append((clip, exc))
                continue
            lengths.mark_exact(clip.key, frames)
            exact = True
        pieces.append(Piece("interstitial", clip, clip_dir, frames, exact))
    return pieces, dropped


def _manifest_show(pkg: Path, manifest: dict, manifest_path: Path) -> Show:
    st = manifest_path.stat()
    key = "m-" + hashlib.sha256(f"{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:20]
    entries: list[Entry] = []
    dj_audio = manifest.get("dj_audio")
    clips = station._clips(dj_audio) if isinstance(dj_audio, dict) else {}
    intros = dj_audio.get("set_intros") if isinstance(dj_audio, dict) else None
    outro = dj_audio.get("outro") if isinstance(dj_audio, dict) else None
    if isinstance(intros, dict):
        entries += [Entry(p, "clip", clips[p]) for p in intros.values() if p in clips]
    tracks = manifest.get("tracks") or []
    for t in tracks:
        fn = t.get("filename") if isinstance(t, dict) else None
        if isinstance(fn, str) and fn:
            entries.append(Entry(f"audio/{fn}", "track", t.get("title") or fn))
    if isinstance(outro, str) and outro in clips:
        entries.append(Entry(outro, "clip", clips[outro]))
    total = manifest.get("total_duration_sec")
    if not (isinstance(total, (int, float)) and not isinstance(total, bool)
            and math.isfinite(total) and total >= 0):
        total = sum(t["duration_sec"] for t in tracks
                    if isinstance(t, dict) and isinstance(t.get("duration_sec"), (int, float))
                    and not isinstance(t.get("duration_sec"), bool) and math.isfinite(t["duration_sec"]))
    show_meta = manifest.get("show") or {}
    source = manifest.get("source") or {}
    meta = {k: show_meta.get(k) for k in ("artist", "date", "venue", "city")}
    dj_profile = (dj_audio or {}).get("profile") if isinstance(dj_audio, dict) else None
    meta.update(profile=source.get("profile"), url=source.get("url"), lineage=source.get("lineage"),
                total_duration_sec=float(total),
                voiced_profile=dj_profile if isinstance(dj_profile, str) and dj_profile
                else source.get("profile"),
                sizes={})
    return Show(pkg.name, pkg, tuple(entries), key, meta)


def scan_delivered(root: Path, *, now_s: float, quiet_s: float, pause_samples: int,
                   extra: int) -> list[Piece]:
    """Every readable v3+ package, voiced or not, for `--library delivered`
    rehearsal. Read-only: never decodes, never writes."""
    root = station.require_root(root)
    try:
        dirs = sorted(root.iterdir())
    except OSError as exc:
        raise station.StationRootError(f"station root {root} cannot be listed: {exc}") from exc
    out: list[Piece] = []
    for pkg in dirs:
        if pkg.name.startswith("."):
            continue
        try:
            if not pkg.is_dir():
                continue
            manifest_path = pkg / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            version = manifest.get("schema_version") if isinstance(manifest, dict) else None
            if not isinstance(version, int) or isinstance(version, bool) or version < 3:
                continue
            got = station.evaluate(pkg, now_s=now_s, quiet_s=quiet_s)
            if isinstance(got, Show):
                frames = estimate_frames(got, pause_samples=pause_samples, extra=extra,
                                         clip_seconds=_safe_mp3_seconds)
                out.append(Piece("show", got, pkg.name, frames, False))
                continue
            show = _manifest_show(pkg, manifest, manifest_path)
        except (OSError, ValueError):
            continue
        seconds = show.meta["total_duration_sec"] + UNVOICED_CLIP_ALLOWANCE_SECONDS
        frames = aacenc.frames_for(aacenc.pad_to_frame(round(seconds * SAMPLE_RATE)), extra)
        out.append(Piece("show", show, pkg.name, frames, False))
    return out
