"""Plan and render steps over the workspace (spec "Lead", "Frozen means
rendered", "Recovery after an outage longer than the lead").

plan_step extends plan.jsonl until it covers now + lead (or starts a fresh
run after an outage); render_step writes segment files
render/seg/<epoch_id>/<N>.aac in ascending N from the next unpublished
segment to now + lead, encoding each show the first time a segment needs it.
Before encoding, a show is re-validated against the current station scan;
a failing or no-longer-eligible show is skipped at its boundary and the plan
re-extended from there; a re-voiced show, or one whose frame count changed
with the config or encoder, is re-planned in place (excluded only if it
mismatches again in the same call). Encoded shows are frozen: their segments are built from the
encode regardless of later package changes.
"""

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from transmitter import aacenc, analysis as analysis_mod, grid, render, station
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import FrameCountDrift, LayoutError, TransmitterError
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import FrameStore, PlanRow, rows_overlapping
from transmitter.planner import (cut_for_recovery, extend, next_start, publish_next, read_plan,
                                 replan_from, write_plan)
from transmitter.state import load_publish_state
from transmitter.station import Ineligible, Show
from transmitter.workspace import Epoch, Workspace, atomic_write_bytes


class Engine(Protocol):
    def analyze(self, show: Show) -> ShowAnalysis: ...
    def extra_frames(self) -> int: ...
    def silent_frame(self) -> bytes: ...
    def encode_show(self, show: Show, analysis: ShowAnalysis, out_path: Path) -> int: ...


class FfmpegEngine:
    def __init__(self, ws: Workspace, cfg: TransmitterConfig):
        self.ws = ws
        self.settings = render.RenderSettings.from_config(cfg.render)

    def analyze(self, show: Show) -> ShowAnalysis:
        return analysis_mod.load_or_analyze(self.ws.cache_dir, show, self.settings.ffmpeg)

    def extra_frames(self) -> int:
        return aacenc.extra_frames(self.settings.ffmpeg)

    def silent_frame(self) -> bytes:
        return aacenc.silent_frame(self.settings.ffmpeg)

    def encode_show(self, show: Show, analysis: ShowAnalysis, out_path: Path) -> int:
        return render.render_show(show, analysis, out_path, settings=self.settings,
                                  extra=self.extra_frames())


Scanner = Callable[[float], tuple[list[Show], list[Ineligible]]]


@dataclass
class Station:
    ws: Workspace
    cfg: TransmitterConfig
    epoch: Epoch
    engine: Engine
    scan: Scanner | None = None
    log: Callable[[str], None] = print

    def scan_now(self, now_us: int) -> list[Show]:
        """Eligible shows; raises StationRootError when the root is unusable."""
        if self.scan is not None:
            return self.scan(now_us / 1e6)[0]
        return station.scan(self.cfg.station.root, now_s=now_us / 1e6,
                            quiet_s=self.cfg.station.quiet_minutes * 60)[0]

    @property
    def gap_frames(self) -> int:
        return grid.gap_frames(self.cfg.render.show_gap_seconds)

    @property
    def pause_samples(self) -> int:
        return grid.samples_for_seconds(self.cfg.render.clip_pause_seconds)

    @property
    def lead_us(self) -> int:
        return int(self.cfg.render.lead_hours * 3600 * 1_000_000)

    @property
    def start_margin_segments(self) -> int:
        return math.ceil(self.cfg.planner.start_delay_minutes * 60 * 1_000_000 / grid.D_US)

    def until_frame(self, now_us: int) -> int:
        return (self.epoch.index_at(now_us + self.lead_us) + 2) * SEGMENT_FRAMES

    def frames_of(self, show: Show) -> int:
        return self.planned_frames(self.engine.analyze(show))

    def planned_frames(self, analysis: ShowAnalysis) -> int:
        """The frame count the current config and encoder give this analysis."""
        return render.planned_frames(analysis, self.pause_samples, self.engine.extra_frames())

    def extend(self, rows: list[PlanRow], shows: list[Show], now_us: int, *, start_frame: int,
               run_start: bool, max_new: int | None = None) -> list[PlanRow]:
        return extend(rows, shows, frames_of=self.frames_of, seed=self.cfg.planner.seed,
                      gap_frames=self.gap_frames, until_frame=self.until_frame(now_us),
                      start_frame=start_frame, run_start=run_start, max_new=max_new,
                      on_skip=lambda s, e: self.log(f"skipping {s.slug}: {e}"))


def _drop_unpublished_segments(st: Station, last: int | None) -> None:
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    if not seg_dir.is_dir():
        return
    floor = -1 if last is None else last
    for p in seg_dir.glob("*.aac"):
        if p.stem.isdigit() and int(p.stem) > floor:
            p.unlink(missing_ok=True)


def plan_step(st: Station, now_us: int, *, max_new: int | None = None) -> list[PlanRow]:
    shows = st.scan_now(now_us)              # StationRootError: refuse, plan untouched
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    # The highest segment R2 may list: local `last`, or above it when a crash
    # fell between a horizon PUT and the save recording it. Keys at or below
    # it are immutable and CDN-cached, so nothing there is dropped or re-planned.
    listed = pub.listed_bound()
    now_n = st.epoch.index_at(now_us)
    fresh = (now_n + st.start_margin_segments) * SEGMENT_FRAMES
    nxt = publish_next(rows, pub.last)
    recovery = None
    if nxt is None or nxt <= now_n:
        # Published keys are immutable, so a new run never starts under one --
        # that would air a new show from its middle right after old-plan audio.
        if listed is not None:
            fresh = max(fresh, (listed + 1) * SEGMENT_FRAMES)
    if nxt is None:
        # No plan: a first start, or plan.jsonl was lost.
        start, run_start = fresh, True
    elif nxt <= now_n:
        # The next segment to publish is already due: the outage outlasted the
        # lead and listeners are already off the live edge. Start a fresh run.
        rows = cut_for_recovery(rows, listed)
        recovery = f"recovery: segment {nxt} was due at index {now_n}; new run at segment " \
                   f"{fresh // SEGMENT_FRAMES}"
        start, run_start = fresh, True
    else:
        if rows[-1].end_frame >= st.until_frame(now_us):
            return rows
        start, run_start = next_start(rows, st.gap_frames), False
    # Extend before touching anything: a PlanError (e.g. every package
    # momentarily changing) must leave both the plan and the segments as they were.
    rows = st.extend(rows, shows, now_us, start_frame=start, run_start=run_start, max_new=max_new)
    if run_start:
        # A new run renumbers everything after the last published segment. Drop
        # the old plan's unpublished files BEFORE the new plan lands, so a crash
        # in between can never leave stale audio under the new run's indices.
        _drop_unpublished_segments(st, listed)
    write_plan(st.ws.plan_path, rows)
    if recovery is not None:
        st.log(recovery)
    return rows


@dataclass
class RenderReport:
    written: list[int] = field(default_factory=list)
    replanned: list[str] = field(default_factory=list)
    covered: bool = True


TMP_MAX_AGE_S = 3600


def _gc_encodes(st: Station, rows: list[PlanRow], next_n: int) -> None:
    """Drop encodes no remaining segment needs, and temp files a crashed
    encode left behind (older than an hour, so never one still being written)."""
    keep = {r.key for r in rows if r.end_frame > next_n * SEGMENT_FRAMES}
    if not st.ws.shows_dir.is_dir():
        return
    for p in st.ws.shows_dir.glob("*.aac"):
        if p.stem not in keep:
            p.unlink(missing_ok=True)
    stale = time.time() - TMP_MAX_AGE_S
    for p in st.ws.shows_dir.glob(".*.tmp"):
        try:
            if p.stat().st_mtime < stale:
                p.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def render_step(st: Station, now_us: int, *, limit: int | None = None) -> RenderReport:
    report = RenderReport()
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    n = publish_next(rows, pub.last)
    if n is None:
        return report
    now_n = st.epoch.index_at(now_us)
    if n <= now_n:
        # Already due: plan_step must start a new run first (recovery). Rendering
        # the old plan now would only produce past segments for publish to upload.
        report.covered = False
        st.log(f"recovery pending: segment {n} was due at index {now_n}; not rendering "
               "until the plan starts a new run")
        return report
    target = st.epoch.index_at(now_us + st.lead_us)
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    store = FrameStore(st.ws.shows_dir, st.engine.silent_frame())
    shows: dict[str, Show] | None = None
    excluded: set[str] = set()
    # Slugs re-planned in place this call: a second mismatch excludes them, so
    # a measurement that never settles cannot loop forever.
    mismatched: set[str] = set()
    while n <= target and (limit is None or len(report.written) < limit):
        path = seg_dir / f"{n}.aac"
        if path.exists():
            n += 1
            continue
        if not rows or (n + 1) * SEGMENT_FRAMES > rows[-1].end_frame:
            report.covered = False
            break
        replanned = False
        for r in rows_overlapping(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES):
            if store.has(r.key):
                continue
            if r.start_frame < n * SEGMENT_FRAMES:
                # Its earlier segments are already rendered (frozen); a re-plan
                # here would cut the show mid-air. Alert and let the operator act.
                raise LayoutError(f"{r.slug} is already on air (from frame {r.start_frame}) but its "
                                  f"encode {r.key} is missing; refusing to re-plan into a mid-show cut")
            if shows is None:
                shows = {s.slug: s for s in st.scan_now(now_us)}
            show = shows.get(r.slug)
            reason = None
            exclude = True
            if show is None:
                reason = "no longer eligible"
            elif show.key != r.key:
                reason = "package changed"
                exclude = r.slug in mismatched
            else:
                try:
                    analysis = st.engine.analyze(show)
                    planned = st.planned_frames(analysis)
                    if planned != r.frames:
                        # A config or encoder change since planning (clip pause,
                        # extra_frames): re-plan after the frontier, never encode
                        # against the stale count.
                        reason = (f"planned frame count changed: {planned} now, {r.frames} in the "
                                  "plan (config or encoder change)")
                        exclude = r.slug in mismatched
                    else:
                        frames = st.engine.encode_show(show, analysis, store.path(r.key))
                        if frames != r.frames:
                            store.path(r.key).unlink(missing_ok=True)
                            raise FrameCountDrift(f"{r.slug}: encoded {frames} frames, plan says "
                                                  f"{r.frames}")
                except FrameCountDrift:
                    raise
                except TransmitterError as exc:
                    reason = f"render failed: {exc}"
            if reason is not None:
                # A re-voice or a frame-count model change re-plans the show in
                # place (re-measured under the current key and model); excluding
                # it would wedge a station with nothing else eligible.
                if exclude:
                    excluded.add(r.slug)
                else:
                    mismatched.add(r.slug)
                kept, start, run_start = replan_from(rows, rows.index(r))
                pool = [s for s in shows.values() if s.slug not in excluded]
                rows = st.extend(kept, pool, now_us, start_frame=start, run_start=run_start)
                write_plan(st.ws.plan_path, rows)
                st.log(f"plan-changed: skipped {r.slug} at frame {r.start_frame} ({reason})")
                report.replanned.append(r.slug)
                replanned = True
                break
        if replanned:
            continue
        atomic_write_bytes(path, store.build_segment(n, rows))
        report.written.append(n)
        n += 1
    _gc_encodes(st, rows, n)
    return report
