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
from transmitter import announce_config, concert, interstitials, piecelist, promises, render, station
from transmitter import assemble as assemble_mod
from transmitter.analysis import ShowAnalysis
from transmitter.announce_config import AnnounceSettings
from transmitter.clock import ClockConfig
from transmitter.concert import BreakContent, ConcertInput
from transmitter.config import TransmitterConfig
from transmitter.errors import (AnalysisStale, FrameCountDrift, LayoutError, PieceUndecodable, PlanError,
                                TransmitterError)
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import CONCERT_ROLE, FrameStore, PlanRow, rows_overlapping, validate_rows
from transmitter.pieces import LengthCache, Piece, build_pool
from transmitter.planner import cut_for_recovery, next_start, publish_next, read_plan, replan_from, write_plan
from transmitter.scheduler import PLACEHOLDER_SLUG, PlannedPiece, SchedulerInput, project, to_row
from transmitter.state import load_publish_state
from transmitter.station import Ineligible, Show
from transmitter.workspace import Epoch, Workspace, atomic_write_bytes

KINDS = ("show", "interstitial")
ANNOUNCEMENT_ROLES = ("next", "later", CONCERT_ROLE)
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
    # builds a concert break's clip; None: a call-scoped `assemble.Assembler` over the pieces folder
    assemble: Callable[[BreakContent, AnnounceSettings], Show] | None = None

    def scan_all(self, now_us: int) -> tuple[list[Show], list[Ineligible]]:
        """Eligible shows and the ineligible packages; raises StationRootError
        when the root is unusable."""
        if self.scan is not None:
            return self.scan(now_us / 1e6)
        return station.scan(self.cfg.station.root, now_s=now_us / 1e6,
                            quiet_s=self.cfg.station.quiet_minutes * 60)

    def scan_now(self, now_us: int) -> list[Show]:
        """Eligible shows; raises StationRootError when the root is unusable."""
        return self.scan_all(now_us)[0]

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

    def scan_pieces(self, now_us: int, *, read_only: bool = False,
                    shows: list[Show] | None = None) -> list[Piece]:
        """The piece pool: eligible packages (estimated unless their analysis
        is cached or learned) and the interstitials folder's clips (analysed
        exactly unless `read_only`). Raises StationRootError like `scan_now`;
        `shows` (a scan the caller already made) skips the rescan."""
        if shows is None:
            shows = self.scan_now(now_us)
        folder = interstitials.folder(self.cfg)
        clips = interstitials.scan(folder, now_s=now_us / 1e6, quiet_s=self.cfg.station.quiet_minutes * 60)
        clip_dir = interstitials.row_dir(self.cfg, folder) if folder is not None else ""
        pool, dropped = build_pool(shows, clips, lengths=self.length_cache(), clip_dir=clip_dir,
                                   analyze_clip=None if read_only else self.frames_of, read_only=read_only)
        for clip, exc in dropped:
            self.log(f"skipping {clip.slug}: {exc}")
        return pool + self.concert_pieces()

    def concert_pieces(self) -> list[Piece]:
        """The assembled concert clips in the workspace clip folder as interstitial
        pieces (`dir` the folder). Lengths come from the length cache (exact once
        analysed, else estimated); nothing is analysed here, since the scheduler
        never picks a concert clip from the pool (render re-analyses what it
        encodes). Never raises: any failure is no clips."""
        try:
            lengths = self.length_cache()
            out: list[Piece] = []
            for show in assemble_mod.scan_clips(self.ws.concert_dir):
                try:
                    frames, exact = lengths.length(show)
                except Exception:
                    continue
                out.append(Piece("interstitial", show, str(self.ws.concert_dir), frames, exact))
            return out
        except Exception as exc:
            try:
                self.log(f"concert clips unreadable: {type(exc).__name__}: {exc}")
            except Exception:
                pass
            return []

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
               run_start: bool, max_new: int | None = None,
               no_assembly_at: frozenset[int] = frozenset()) -> list[PlanRow]:
        """Append scheduler rows from `start_frame` until the plan covers
        `until_frame(now_us)` (at most `max_new`); never changes a row of
        `rows`. Per row (spec "Exact timing"): run the scheduler on the
        best-known lengths; analyse its pick when estimated; run it once more
        with the exact count; append run 2's pick when analysed, else run 1's
        analysed pick. A pick that cannot be measured is skipped for the rest
        of the call. Every written row carries an exact frame count.

        A concert break (spec "Assembly") is planned in two passes: pass 1's
        content is assembled into a clip and measured, the shows it names are
        measured, and pass 2 re-runs with those exact lengths and the clip; the
        row is appended with pass 1's wording when pass 2 proposes a break of the
        same shape, else that boundary is planned at the last rung (today's
        logic), as it is on any assembly failure. `no_assembly_at` (start
        frames) are planned at the last rung from the start. Nothing of the
        feature raises out of here (`_ConcertCall`); a `PlanError` propagates as today."""
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
        conc = _ConcertCall(self, now_us, no_assembly_at)
        while (not out or out[-1].end_frame < until) and (max_new is None or len(appended) < max_new):
            # every persisted row (and each row appended so far) is history; the
            # projection adds only what it projects
            rec = history.recency(aired, out, self.epoch, clock.timezone, meta_of)
            inp = conc.prepare(SchedulerInput(rows=tuple(out), start_frame=start, run_start=mark,
                                              pool=tuple(pool), clock=clock, rec=rec,
                                              epoch_us=self.epoch.epoch_us, gap_frames=self.gap_frames,
                                              seed=self.cfg.planner.seed))
            run1 = conc.project(inp)            # piece [0] does not depend on `ahead`
            if run1 is None:
                continue                        # the guard fell back: this row again, as today
            self._ping()
            chosen: PlannedPiece | None = run1
            if run1.concert is not None:        # before the measuring below: the placeholder is not exact
                chosen, pool = conc.plan_break(run1, inp, pool, lengths)
            elif not run1.piece.exact:
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
                run2 = conc.project(dataclasses.replace(inp, pool=tuple(pool)))
                if run2 is None:
                    continue
                self._ping()
                chosen = run2 if run2.piece.exact and run2.concert is None else \
                    dataclasses.replace(run1, piece=measured)
            if chosen is None:
                continue                        # re-proposed: a piece absent, or this boundary at the last rung
            if chosen.piece.slug == PLACEHOLDER_SLUG:     # never written; unreachable
                conc.no_asm.add(start)
                continue
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
            if _promise_broken(out, row):
                row = dataclasses.replace(row, announcement_broken=True)
                _report(self, "announce-promise", f"promise-broken: {row.slug} at {row.block} {row.nominal_start}")
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


def _promise_broken(out: list[PlanRow], row: PlanRow) -> bool:
    """`row` is the show row placed at a concert break's first mismatched slot
    (spec "A void promise is never fatal"). Never raises."""
    try:
        return row.kind == "show" and bool(promises.first_mismatch(out, row))
    except Exception:
        return False


def _report(st: "Station", code: str, message: str) -> None:
    """Log and alert, never raising (the feature's failures must not stop planning)."""
    for report in (lambda: st.log(message), lambda: alerts.alert(code, message)):
        try:
            report()
        except Exception:
            pass


def concert_input(st: "Station", now_us: int, *, read_only: bool,
                  no_assembly_at: frozenset[int] = frozenset()) -> tuple[ConcertInput | None, AnnounceSettings]:
    """The scheduler's concert input and the settings: None unless `announce.toml`
    switches announcements on and the pieces folder exists (transmitter never
    creates it). `read_only` loads the settings without alerting. `present` is
    the voiced pieces past the station's quiet period; `typical_frames` the
    assumed assembled length (`concert.ASSEMBLED_TYPICAL_SECONDS`). Never raises."""
    settings = AnnounceSettings()
    try:
        settings = announce_config.load_settings(st.ws, alert=not read_only).settings
        if not settings.enabled:
            return None, settings
        folder = piecelist.pieces_folder(st.cfg)
        if folder is None or not folder.is_dir():
            return None, settings
        present = piecelist.present_ids(folder, now_s=now_us / 1e6, quiet_s=st.cfg.station.quiet_minutes * 60)
        samples = aacenc.pad_to_frame(grid.samples_for_seconds(concert.ASSEMBLED_TYPICAL_SECONDS))
        typical = aacenc.frames_for(samples, st.engine.extra_frames())
        return ConcertInput(present=present, id_text=settings.id_text, typical_frames=typical,
                            no_assembly_at=frozenset(no_assembly_at)), settings
    except Exception as exc:
        message = f"concert breaks unavailable: {type(exc).__name__}: {exc}; planning without them"
        if read_only:
            try:
                st.log(message)
            except Exception:
                pass
        else:
            _report(st, "announce-assembly", message)
        return None, settings


class _ConcertCall:
    """One `extend` call's concert-break state (spec "Assembly", "Fallback ladder").

    `present` shrinks when a piece turns out undecodable and `no_asm` (start
    frames planned at the last rung) grows on every other failure, so each
    re-proposal of a row makes progress and the loop ends. The guard: an
    exception other than `PlanError` out of a projection that had concert input
    or live promises is logged, alerted and the row re-run with neither, for the
    rest of the call (`off`); with `off` set a projection is today's and its
    exceptions propagate as today."""

    def __init__(self, st: "Station", now_us: int, no_assembly_at: frozenset[int]):
        self.st = st
        self.ci, self.settings = concert_input(st, now_us, read_only=False, no_assembly_at=no_assembly_at)
        self.present = set(self.ci.present) if self.ci is not None else set()
        self.no_asm = set(no_assembly_at)
        self.off = False
        self.live = False
        self.built: dict[tuple[int, BreakContent], Piece] = {}
        self._assembler: assemble_mod.Assembler | None = None    # call-scoped: its decode cache is unbounded

    def _degrade(self, code: str, what: str, exc: BaseException) -> None:
        self.off, self.live = True, False
        _report(self.st, code, f"{what}: {type(exc).__name__}: {exc}; planning this step without concert "
                               "breaks or promises")

    def prepare(self, base: SchedulerInput) -> SchedulerInput:
        """`base` with this row's concert input, or with neither concert breaks
        nor promises once the guard has fallen back."""
        if not self.off:
            try:
                self.live = bool(promises.remaining(
                    base.rows, pool_slugs=frozenset(p.slug for p in base.pool if p.kind == "show"),
                    clock=base.clock, run_start=base.run_start))
            except Exception as exc:
                self._degrade("announce-promise", "live promises unreadable", exc)
        if self.off:
            return dataclasses.replace(base, concert=None, promises=False)
        if self.ci is None:
            return base
        return dataclasses.replace(base, concert=dataclasses.replace(
            self.ci, present=frozenset(self.present), no_assembly_at=frozenset(self.no_asm)))

    def project(self, inp: SchedulerInput) -> PlannedPiece | None:
        """Piece [0] of `project(inp)`, or None when the guard fell back (re-run the row)."""
        if inp.concert is None and not (inp.promises and self.live):
            return project(inp, ahead=1)[0]
        try:
            return project(inp, ahead=1)[0]
        except PlanError:
            raise
        except Exception as exc:
            if inp.concert is not None:
                self._degrade("announce-assembly", "the concert-break projection failed", exc)
            else:
                self._degrade("announce-promise", "the live-promise projection failed", exc)
            return None

    def _assemble(self, content: BreakContent) -> Show:
        if self.st.assemble is not None:
            return self.st.assemble(content, self.settings)
        if self._assembler is None:
            folder = piecelist.pieces_folder(self.st.cfg)
            if folder is None:
                raise TransmitterError("no interstitials folder")
            self._assembler = assemble_mod.Assembler(pieces=folder, out_dir=self.st.ws.concert_dir,
                                                     settings=self.settings, ffmpeg=self.st.cfg.render.ffmpeg)
        return self._assembler.build(content)

    def _clip(self, content: BreakContent, start: int, lengths: LengthCache) -> Piece | None:
        """The assembled, measured clip for `content` at `start` (at most one
        assembly per (start, content) per call), or None after recording the
        failure: an undecodable piece leaves `present`, anything else puts
        `start` in `no_asm`."""
        clip = self.built.get((start, content))
        if clip is not None:
            return clip
        try:
            show = self._assemble(content)
            frames = self.st.frames_of(show)
            if frames <= 0:
                raise TransmitterError(f"{show.slug} measures {frames} frames")
        except PieceUndecodable as exc:
            if exc.piece_id not in self.present:   # not one we offered: no progress to make by re-proposing
                self.no_asm.add(start)
                _report(self.st, "announce-assembly", f"concert break at frame {start}: {exc}; planned at the "
                                                      "last rung")
                return None
            self.present.discard(exc.piece_id)
            _report(self.st, "announce-assembly", f"concert break at frame {start}: piece {exc.piece_id} "
                                                  f"undecodable ({exc}); treated as absent for this step")
            return None
        except Exception as exc:
            self.no_asm.add(start)
            _report(self.st, "announce-assembly", f"concert break at frame {start} cannot be assembled: "
                                                  f"{type(exc).__name__}: {exc}; planned at the last rung")
            return None
        lengths.mark_exact(show.key, frames)
        clip = self.built[(start, content)] = Piece("interstitial", show, str(self.st.ws.concert_dir), frames, True)
        return clip

    def plan_break(self, run1: PlannedPiece, inp: SchedulerInput, pool: list[Piece],
                   lengths: LengthCache) -> tuple[PlannedPiece | None, list[Piece]]:
        """Pass 1's break `run1` assembled, its named shows measured and pass 2
        run: (the row's piece, the pool), or (None, the pool) to re-propose."""
        content = run1.concert
        start = run1.start_frame
        if content is None or inp.concert is None:     # unreachable: a break needs concert input
            self._degrade("announce-assembly", "a concert break without concert input",
                          TransmitterError(f"at frame {start}"))
            return None, pool
        clip = self._clip(content, start, lengths)
        if clip is None:
            return None, pool
        for slug in content.named:                 # exact before pass 2 (the watchdog fed after each)
            piece = next((p for p in pool if p.kind == "show" and p.slug == slug), None)
            if piece is None or piece.exact:
                continue
            frames, exact = lengths.length(piece.show)
            if not exact:
                try:
                    frames = self.st.frames_of(piece.show)
                    if frames <= 0:
                        raise PlanError(f"{slug} measures {frames} frames")
                except Exception as exc:           # today's skip; this boundary at the last rung
                    self.st.log(f"skipping {slug}: {exc}")
                    self.no_asm.add(start)
                    return None, [p for p in pool if (p.kind, p.slug) != ("show", slug)]
                lengths.mark_exact(piece.key, frames)
            measured = dataclasses.replace(piece, frames=frames, exact=True)
            pool = [measured if (p.kind, p.slug) == ("show", slug) else p for p in pool]
        run2 = self.project(dataclasses.replace(inp, pool=tuple(pool),
                                                concert=dataclasses.replace(inp.concert, first_break=clip)))
        if run2 is None:
            return None, pool
        self.st._ping()
        if run2.concert is not None and run2.start_frame == start and run2.piece.key == clip.key \
                and run2.concert.same_shape(content):
            # pass 1's wording stands (a different Y bucket alone is no difference)
            return dataclasses.replace(run2, piece=clip, concert=content, names=content.names), pool
        self.no_asm.add(start)
        return None, pool


def _drop_unpublished_segments(st: Station, last: int | None) -> None:
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    if not seg_dir.is_dir():
        return
    floor = -1 if last is None else last
    for p in seg_dir.glob("*.aac"):
        if p.stem.isdigit() and int(p.stem) > floor:
            p.unlink(missing_ok=True)


def write_piece_list(st: Station, now_us: int, shows: list[Show], ineligible: list[Ineligible]) -> None:
    """Derive the needed announcement pieces, keep the list in the workspace and
    write each missing text into `<interstitials>/pieces` (never creating it:
    while it is missing the feature is dormant). Never raises: any failure is
    logged and alerted (`announce-pieces`) and planning goes on."""
    try:
        settings = announce_config.load_settings(st.ws, alert=True).settings
        artists = []
        for value in [s.meta.get("artist") for s in shows] + [i.artist for i in ineligible]:
            try:
                if isinstance(value, str):
                    value.encode("utf-8")       # a lone surrogate would poison the whole list
                    artists.append(value)
            except UnicodeError:
                continue
        clock = clock_mod.live_clock(st.ws, save=False).clock
        needed = concert.needed_pieces(clock, artists, settings.id_text, now_us)
        piecelist.save_needed(st.ws, needed, now_us=now_us)
        folder = piecelist.pieces_folder(st.cfg)
        if folder is None or not folder.is_dir():
            return
        written, remaining = piecelist.write_texts(folder, needed, now_s=now_us / 1e6)
        if written or remaining:
            st.log(f"piece list: wrote {written} text(s), {remaining} left for the next step")
    except Exception as exc:
        for report in (lambda: st.log(f"piece list: {type(exc).__name__}: {exc}"),
                       lambda: alerts.alert("announce-pieces", "cannot write the needed announcement "
                                            f"pieces: {type(exc).__name__}: {exc}")):
            try:
                report()
            except Exception:
                pass


def plan_step(st: Station, now_us: int, *, max_new: int | None = None) -> list[PlanRow]:
    shows, ineligible = st.scan_all(now_us)   # StationRootError: refuse, plan untouched
    write_piece_list(st, now_us, shows, ineligible)   # before the early return below; never raises
    pool = st.scan_pieces(now_us, shows=shows)
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
