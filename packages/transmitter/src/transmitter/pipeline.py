"""Plan and render steps over the workspace (spec "Lead", "Frozen means
rendered", "Recovery after an outage longer than the lead"; scheduler spec
"Planning", "Re-validation").

plan_step extends plan.jsonl until it covers now + lead (or starts a fresh
run after an outage). The scheduler (`scheduler.project`) chooses each
appended row from the end of the persisted plan, on the live clock
(`Station.clock`), the piece pool (`Station.scan_pieces`: eligible packages
and the interstitials folder) and the rotation history; rows are only ever
appended, and every written row carries an exact frame count (`Station.extend`).

render_step writes segment files render/seg/<epoch_id>/<N>.aac in ascending
N from the next unpublished segment to now + lead, encoding each piece (a
show or an interstitial clip) the first time a segment needs it. Before
encoding, a piece is re-validated against the current scan; a failing,
vanished or unknown-kind piece is skipped at its boundary and the plan
re-extended from there; a re-voiced show, or one whose frame count changed
with the config or encoder, is re-planned in place (excluded only if it
mismatches again in the same call). One call re-plans at most
`len(clip pool) + rows in the lead + 10` times. Encoded pieces are frozen:
their segments are built from the encode regardless of later package
changes. A piece already on air whose encode was lost is re-encoded when its
files are unchanged, and refused (LayoutError) otherwise -- never re-planned
into a mid-show cut.
"""

import dataclasses
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from transmitter import aacenc, alerts, analysis as analysis_mod, clock as clock_mod, grid, history
from transmitter import interstitials, render, station
from transmitter.analysis import ShowAnalysis
from transmitter.clock import ClockConfig
from transmitter.config import TransmitterConfig
from transmitter.errors import AnalysisStale, FrameCountDrift, LayoutError, PlanError, TransmitterError
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import FrameStore, PlanRow, rows_overlapping, validate_rows
from transmitter.pieces import LengthCache, Piece, build_pool
from transmitter.planner import cut_for_recovery, next_start, publish_next, read_plan, replan_from, write_plan
from transmitter.scheduler import SchedulerInput, project, to_row
from transmitter.state import load_publish_state
from transmitter.station import Ineligible, Show
from transmitter.workspace import Epoch, Workspace, atomic_write_bytes

KINDS = ("show", "interstitial")
ANNOUNCEMENT_ROLES = ("next", "later")
CLOCK_PROBLEM_MAX = 300


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
        try:
            return render.render_show(show, analysis, out_path, settings=self.settings,
                                      extra=self.extra_frames())
        except AnalysisStale:
            analysis_mod.drop_cached(self.ws.cache_dir, analysis.key)
            raise


Scanner = Callable[[float], tuple[list[Show], list[Ineligible]]]


@dataclass
class Station:
    ws: Workspace
    cfg: TransmitterConfig
    epoch: Epoch
    engine: Engine
    scan: Scanner | None = None
    log: Callable[[str], None] = print
    notify: Callable[[str], object] | None = None   # the service's sd_notify; fed during long plan steps
    lengths: LengthCache | None = None              # piece lengths; see length_cache()

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
        try:
            analysis = self.engine.analyze(show)
        finally:
            if self.notify is not None:
                self.notify("WATCHDOG=1")   # a plan over many unanalysed shows must not outlast WatchdogSec
        return self.planned_frames(analysis)

    def planned_frames(self, analysis: ShowAnalysis) -> int:
        """The frame count the current config and encoder give this analysis."""
        return render.planned_frames(analysis, self.pause_samples, self.engine.extra_frames())

    def length_cache(self) -> LengthCache:
        """`lengths`, (re)built from exactly the inputs `planned_frames` uses
        (the analysis cache, `pause_samples`, the encoder's extra frames), so
        an "exact" length always agrees with what render will encode. A
        config or encoder change since it was built rebuilds it."""
        pause, extra = self.pause_samples, self.engine.extra_frames()
        lc = self.lengths
        if lc is None or lc.pause_samples != pause or lc.extra != extra \
                or lc.cache_dir != Path(self.ws.cache_dir):
            lc = self.lengths = LengthCache(self.ws.cache_dir, pause, extra)
        return lc

    def scan_pieces(self, now_us: int, *, read_only: bool = False) -> list[Piece]:
        """The piece pool: eligible packages (estimated unless their analysis
        is cached or learned) and the interstitials folder's clips (analysed
        exactly unless `read_only`). Raises StationRootError like `scan_now`."""
        shows = self.scan_now(now_us)
        folder = interstitials.folder(self.cfg)
        clips = interstitials.scan(folder, now_s=now_us / 1e6, quiet_s=self.cfg.station.quiet_minutes * 60)
        clip_dir = interstitials.row_dir(self.cfg, folder) if folder is not None else ""
        pool, dropped = build_pool(shows, clips, lengths=self.length_cache(), clip_dir=clip_dir,
                                   analyze_clip=None if read_only else self.frames_of, read_only=read_only)
        for clip, exc in dropped:
            self.log(f"skipping {clip.slug}: {exc}")
        return pool

    def clock(self) -> ClockConfig:
        """The live clock (saving the last-good copy). An invalid clock.toml is
        alerted and planning goes on with the last good copy, else the
        implicit clock; a valid one (or none) resolves the alert."""
        lc = clock_mod.live_clock(self.ws)
        if lc.problem:
            alerts.alert("clock", f"{condense_clock_problem(lc.problem)}; planning with the {lc.source} clock")
        else:
            alerts.resolve("clock")
        return lc.clock

    def _ping(self) -> None:
        if self.notify is not None:
            self.notify("WATCHDOG=1")

    def extend(self, rows: list[PlanRow], pool: list[Piece], now_us: int, *, start_frame: int,
               run_start: bool, max_new: int | None = None) -> list[PlanRow]:
        """Append scheduler rows from `start_frame` until the plan covers
        `until_frame(now_us)` (at most `max_new`); never changes a row of
        `rows`. Per row (spec "Exact timing"): run the scheduler on the
        best-known lengths; analyse its pick when estimated; run it once more
        with the exact count; append run 2's pick when analysed, else run 1's
        analysed pick. A pick that cannot be measured is skipped for the rest
        of the call. Every written row carries an exact frame count."""
        clock = self.clock()
        lengths = self.length_cache()
        aired = history.load_aired(self.ws)
        pool = list(pool)
        meta = {p.package: (p.artist, p.date) for p in pool if p.kind == "show"}

        def meta_of(package: str) -> tuple[str | None, str | None]:
            return meta.get(package, (None, None))

        until = self.until_frame(now_us)
        out = list(rows)
        appended: list[PlanRow] = []
        next_seq = max((r.seq for r in out), default=-1) + 1
        start, mark = start_frame, run_start
        while (not out or out[-1].end_frame < until) and (max_new is None or len(appended) < max_new):
            # every persisted row (and each row appended so far) is history; the
            # projection adds only what it projects
            rec = history.recency(aired, out, self.epoch, clock.timezone, meta_of)
            inp = SchedulerInput(rows=tuple(out), start_frame=start, run_start=mark, pool=tuple(pool),
                                 clock=clock, rec=rec, epoch_us=self.epoch.epoch_us,
                                 gap_frames=self.gap_frames, seed=self.cfg.planner.seed)
            run1 = project(inp, ahead=1)[0]     # piece [0] does not depend on `ahead`
            self._ping()
            chosen = run1
            if not run1.piece.exact:
                piece = run1.piece
                frames, exact = lengths.length(piece.show)     # learned earlier in this process?
                if not exact:
                    try:
                        frames = self.frames_of(piece.show)
                        if frames <= 0:
                            raise PlanError(f"{piece.slug} measures {frames} frames")
                    except TransmitterError as exc:
                        self.log(f"skipping {piece.slug}: {exc}")
                        pool = [p for p in pool if (p.kind, p.slug) != (piece.kind, piece.slug)]
                        continue
                    lengths.mark_exact(piece.key, frames)
                measured = dataclasses.replace(piece, frames=frames, exact=True)
                pool = [measured if (p.kind, p.slug) == (piece.kind, piece.slug) else p for p in pool]
                run2 = project(dataclasses.replace(inp, pool=tuple(pool)), ahead=1)[0]
                self._ping()
                chosen = run2 if run2.piece.exact else dataclasses.replace(run1, piece=measured)
            row = to_row(chosen, next_seq)
            # The first row goes at the caller's start, never prev.end + gap: on the
            # render skip path `replan_from` hands back the dropped row's own start,
            # laid with the gap of its day; after a show_gap_seconds change, prev.end
            # + the new gap could fall inside an already-written segment (a cut).
            # plan_step checks its own start against the gap before calling.
            expected = start if not appended else appended[-1].end_frame + self.gap_frames
            if row.start_frame != expected or row.run_start != mark:
                raise LayoutError(f"scheduler laid row {row.seq} ({row.slug}) at frame {row.start_frame} "
                                  f"(run_start={row.run_start}); the gap layout puts it at {expected}")
            if _announcement_broken(row, out):
                row = dataclasses.replace(row, announcement_broken=True)
                self.log(f"announcement-broken: {row.block} {row.nominal_start}")
            out.append(row)
            appended.append(row)
            next_seq += 1
            start, mark = row.end_frame + self.gap_frames, False
        validate_rows(out)
        return out


def condense_clock_problem(problem: str) -> str:
    """`live_clock`'s problem on one readable line: pydantic's multi-line
    message without its errors.pydantic.dev links and `[type=...]` tails."""
    parts = []
    for line in problem.splitlines():
        line = line.strip()
        if not line or line.startswith("For further information"):
            continue
        cut = line.find(" [type=")
        parts.append(line[:cut] if cut >= 0 else line)
    text = "; ".join(parts)
    return text if len(text) <= CLOCK_PROBLEM_MAX else text[:CLOCK_PROBLEM_MAX - 3] + "..."


def _announcement_broken(row: PlanRow, persisted: list[PlanRow]) -> bool:
    """A block's first show row breaks the promise of every persisted
    announcement naming its occurrence when it starts outside its window or
    degraded to open time (spec "A promise kept where possible")."""
    if row.kind != "show" or row.miss is None or not (row.miss or row.degraded):
        return False
    occ = (row.block, row.nominal_start)
    return any(r.kind == "interstitial" and r.role in ANNOUNCEMENT_ROLES and occ in r.names
               for r in persisted)


def _drop_unpublished_segments(st: Station, last: int | None) -> None:
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    if not seg_dir.is_dir():
        return
    floor = -1 if last is None else last
    for p in seg_dir.glob("*.aac"):
        if p.stem.isdigit() and int(p.stem) > floor:
            p.unlink(missing_ok=True)


def plan_step(st: Station, now_us: int, *, max_new: int | None = None) -> list[PlanRow]:
    pool = st.scan_pieces(now_us)            # StationRootError: refuse, plan untouched
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    # The highest segment R2 may list: local `last`, or above it when a crash
    # fell between a horizon PUT and the save recording it. Keys at or below
    # it are immutable and CDN-cached, so nothing there is dropped or re-planned.
    listed = pub.listed_bound()
    now_n = st.epoch.index_at(now_us)
    fresh = (now_n + st.start_margin_segments) * SEGMENT_FRAMES
    nxt = publish_next(rows, pub.last)
    # The first segment R2 cannot already list. Recovery is decided on it, not
    # on `nxt`: while R2 may list past now, listeners are on audio already up,
    # and a recovery would cut the show on air at the mark (or leave dead air).
    due = publish_next(rows, listed)
    recovery = None
    if nxt is None or due <= now_n:
        # Published keys are immutable, so a new run never starts under one --
        # that would air a new show from its middle right after old-plan audio.
        if listed is not None:
            fresh = max(fresh, (listed + 1) * SEGMENT_FRAMES)
    if nxt is None:
        # No plan: a first start, or plan.jsonl was lost.
        start, run_start = fresh, True
    elif due <= now_n:
        # The next segment to publish is already due: the outage outlasted the
        # lead and listeners are already off the live edge. Start a fresh run.
        rows = cut_for_recovery(rows, listed)
        recovery = f"recovery: segment {due} was due at index {now_n}; new run at segment " \
                   f"{fresh // SEGMENT_FRAMES}"
        start, run_start = fresh, True
    else:
        if rows[-1].end_frame >= st.until_frame(now_us):
            return rows
        start, run_start = next_start(rows, st.gap_frames), False
    # Extend before touching anything: a PlanError (e.g. every package
    # momentarily changing) must leave both the plan and the segments as they were.
    rows = st.extend(rows, pool, now_us, start_frame=start, run_start=run_start, max_new=max_new)
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


def render_step(st: Station, now_us: int, *, limit: int | None = None,
                notify: Callable[[str], object] | None = None) -> RenderReport:
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
    pieces: dict[tuple[str, str], Piece] | None = None     # the scan, keyed (kind, slug)
    excluded: set[tuple[str, str]] = set()
    # Pieces re-planned in place this call: a second mismatch excludes them, so
    # a measurement that never settles cannot loop forever.
    mismatched: set[tuple[str, str]] = set()
    # A re-plan writes no segment, so the call's re-plans are capped (spec
    # "Re-validation": above the clip pool plus the rows in the lead).
    cap: int | None = None
    replans = 0
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
            # Its earlier segments are already rendered (frozen): its encode was
            # lost (render/shows cleaned or not restored). An unchanged piece
            # re-encodes to the planned frame count -- the FrameCountDrift check
            # below proves it -- so it carries on. Anything that would re-plan
            # it instead cuts it mid-air: refuse (see `reason` below).
            on_air = r.start_frame < n * SEGMENT_FRAMES
            if pieces is None:
                pool = st.scan_pieces(now_us)
                pieces = {(p.kind, p.slug): p for p in pool}
                cap = (sum(p.kind == "interstitial" for p in pool)
                       + len(rows_overlapping(rows, n * SEGMENT_FRAMES, (target + 1) * SEGMENT_FRAMES)) + 10)
            ident = (r.kind, r.slug)
            piece = pieces.get(ident)
            what = "package" if r.kind == "show" else "clip"
            reason = None
            exclude = True
            if r.kind not in KINDS:
                reason = f"unknown kind {r.kind!r}"
            elif piece is None:
                reason = "no longer eligible" if r.kind == "show" else \
                    "no longer in the interstitials folder (or inside its quiet period)"
            elif piece.key != r.key:
                reason = f"{what} changed"
                # a re-voiced show is re-planned in place; a changed clip fails
                # re-validation and leaves the pool for the rest of the call
                exclude = ident in mismatched or r.kind != "show"
            else:
                try:
                    analysis = st.engine.analyze(piece.show)
                    if notify is not None:
                        notify("WATCHDOG=1")    # a cold analysis can take minutes
                    planned = st.planned_frames(analysis)
                    if planned != r.frames:
                        # A config or encoder change since planning (clip pause,
                        # extra_frames): re-plan after the frontier, never encode
                        # against the stale count. The re-plan measures it afresh.
                        reason = (f"planned frame count changed: {planned} now, {r.frames} in the "
                                  "plan (config or encoder change)")
                        exclude = ident in mismatched
                        lengths = st.length_cache()
                        lengths.forget(piece.key)
                        frames, exact = lengths.length(piece.show)
                        pieces[ident] = dataclasses.replace(piece, frames=frames, exact=exact)
                    else:
                        frames = st.engine.encode_show(piece.show, analysis, store.path(r.key))
                        if notify is not None:
                            notify("WATCHDOG=1")    # a step can encode several pieces
                        if frames != r.frames:
                            store.path(r.key).unlink(missing_ok=True)
                            raise FrameCountDrift(f"{r.slug}: encoded {frames} frames, plan says "
                                                  f"{r.frames}")
                except FrameCountDrift:
                    raise
                except TransmitterError as exc:
                    reason = f"render failed: {exc}"
            if reason is not None and on_air:
                raise LayoutError(f"{r.slug} is already on air (from frame {r.start_frame}) but its "
                                  f"encode {r.key} is missing and cannot be re-made ({reason}); "
                                  "refusing to re-plan into a mid-show cut")
            if reason is not None:
                if replans >= cap:
                    raise PlanError(f"render re-planned {replans} times in one call; stopping")
                replans += 1
                # A re-voice or a frame-count model change re-plans the piece in
                # place (re-measured under the current key and model); excluding
                # it would wedge a station with nothing else eligible.
                if exclude:
                    excluded.add(ident)
                else:
                    mismatched.add(ident)
                kept, start, run_start = replan_from(rows, rows.index(r))
                pool = [p for key, p in pieces.items() if key not in excluded]
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
