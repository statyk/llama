"""Wiring for the CLI and the service loop (spec "transmitter -- state and
commands", "Lead"). `run` ticks once a minute: below the low-water mark it
starts filling -- each tick plans at most one more show and renders at most
one publish batch, then publishes -- until the published lead is back at
`lead_hours`; publishing and pruning run every tick. An error in any step is
logged with its traceback and alerted, and the loop goes on; a frame-count
drift halts filling (publishing goes on) until transmitter is restarted."""

import logging
import time
from pathlib import Path
from typing import Callable

from transmitter import alerts, analysis, grid, pipeline, publish, r2, station
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import ConfigError, FrameCountDrift, PublishLocked
from transmitter.layout import PlanRow
from transmitter.planner import read_plan
from transmitter.state import load_fallback_version, load_publish_state
from transmitter.workspace import Workspace, load_epoch, load_or_create_epoch

log = logging.getLogger("transmitter")
MAX_BATCHES = 100


def now_us() -> int:
    return time.time_ns() // 1000


def make_engine(ws: Workspace, cfg: TransmitterConfig) -> pipeline.Engine:
    return pipeline.FfmpegEngine(ws, cfg)


def make_client(cfg: TransmitterConfig):
    return r2.make_client(cfg.publish)


def open_station(cfg: TransmitterConfig, t_us: int) -> pipeline.Station:
    ws = Workspace(cfg.root)
    return pipeline.Station(ws=ws, cfg=cfg, epoch=load_or_create_epoch(ws, t_us),
                            engine=make_engine(ws, cfg), log=log.info)


def load_template(cfg: TransmitterConfig) -> str:
    if cfg.antenna.dir is None:
        raise ConfigError("set [antenna] dir to the repo's antenna/ directory "
                          "(show pages are rendered from antenna/templates/show.html)")
    path = Path(cfg.antenna.dir) / "templates" / "show.html"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read the show-page template {path}: {exc}") from exc


def row_analysis(st: pipeline.Station, row: PlanRow) -> ShowAnalysis | None:
    """A planned row's analysis for the timeline: the cache if it still holds
    the row's key, else the engine's analyze (which re-caches) on the package,
    when the package still has the file set the row was planned from."""
    cached = analysis.load_cached(st.ws.cache_dir, row.key)
    if cached is not None:
        return cached
    root = st.cfg.station.root
    if root is None:
        return None
    show = station.evaluate(Path(root) / row.dir, now_s=time.time(), quiet_s=0)
    if not isinstance(show, station.Show) or show.key != row.key:
        return None
    return st.engine.analyze(show)


def open_publisher(st: pipeline.Station) -> publish.Publisher:
    cfg = st.cfg
    if not cfg.publish.bucket:
        raise ConfigError("set [publish] bucket in transmitter's config.toml")
    budget = publish.PutBudget(st.ws.puts_path, cfg.publish.daily_put_budget)
    uploader = publish.Uploader(make_client(cfg), cfg.publish.bucket, budget)
    return publish.Publisher(ws=st.ws, cfg=cfg, epoch=st.epoch, uploader=uploader,
                             template=load_template(cfg),
                             analysis_for=lambda row: row_analysis(st, row), log=log.info)


HELD_MARKER = "horizon held"
HELD_ALERT_AFTER = 3     # consecutive publish_all calls with a held horizon before alerting


class HeldTracker:
    """Counts consecutive publish_all calls that ended with a held horizon. A
    hold that never clears re-PUTs the same partial batch every tick, which
    spends the PUT budget, so a persistent one escalates from a warning."""

    def __init__(self) -> None:
        self.count = 0

    def observe(self, held: bool) -> None:
        self.count = self.count + 1 if held else 0
        if self.count == HELD_ALERT_AFTER:
            alerts.alert("horizon-held", f"the horizon has been held for {self.count} consecutive publish "
                                         "passes (each re-sends the same batch, spending PUT budget); "
                                         "check publish state vs R2's state/horizon.json")


def _report_stop(step: str, stopped: str | None, error: str | None, held: bool = False) -> None:
    """Surface one publish/prune report. A put-budget stop is an alert (spend is
    the strict surface); a guard stop is routine; a high-water stop or a held
    horizon is a deliberate deferral (a recovering state), logged as a WARNING;
    any other error is an alert."""
    if stopped == "put-budget":
        alerts.alert("put-budget", error or f"daily PUT budget exceeded; {step} stopped")
        return
    if stopped == "guard":
        log.info("%s paused: state/guard.json says tripped (or is unreadable)", step)
    elif stopped == "high-water":
        log.warning("%s deferred: high-water mark is above last (publish reconciles the horizon first)", step)
    elif stopped:
        alerts.alert(step, f"stopped: {stopped}" + (f": {error}" if error else ""))
        return
    if not error:
        return
    parts = error.split("; ")
    if held:
        for part in parts:
            if part.startswith(HELD_MARKER):
                log.warning("%s: %s", step, part)
        parts = [part for part in parts if not part.startswith(HELD_MARKER)]
    if parts:
        alerts.alert(step, "; ".join(parts))


def publish_all(p: publish.Publisher, t_us: int, held: HeldTracker | None = None
                ) -> tuple[list[publish.PublishReport], publish.PruneReport]:
    reports = []
    for _ in range(MAX_BATCHES):
        r = publish.publish_batch(p, t_us)
        reports.append(r)
        _report_stop("publish", r.stopped, r.error, r.held)
        if not r.uploaded or r.stopped or r.error:
            break
    if held is not None:
        held.observe(any(r.held for r in reports))
    pr = publish.prune(p, t_us)
    _report_stop("prune", pr.stopped, pr.error)
    return reports, pr


class Runner:
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.filling = False
        self.held = HeldTracker()
        self.halted = False          # latched by a frame-count drift; cleared by a restart

    def lead_us(self, t_us: int) -> int | None:
        last = load_publish_state(self.st.ws).last
        return None if last is None else self.st.epoch.start_us(last + 1) - t_us

    def _step(self, name: str, fn: Callable[[], object]) -> None:
        """Run one step; no error ends the loop (the next tick retries)."""
        try:
            fn()
        except FrameCountDrift as exc:
            # The encoder no longer matches the frame-count model: stop filling
            # rather than render more of a timeline that may be wrong.
            self.halted, self.filling = True, False
            log.error("%s step: frame-count drift; filling halted", name, exc_info=True)
            alerts.alert("frame-count-drift", f"{exc}; filling halted (publishing continues) "
                                              "until transmitter is restarted")
        except PublishLocked as exc:
            # An operator's manual publish/fallback overlaps this tick; the next one retries.
            log.warning("%s step skipped: %s", name, exc)
        except Exception as exc:
            log.exception("%s step failed", name)
            alerts.alert(name, f"{type(exc).__name__}: {exc}")

    def tick(self, t_us: int) -> None:
        low_water_us = int(self.st.cfg.render.low_water_hours * 3600 * 1_000_000)
        lead = self.lead_us(t_us)
        if not self.halted and (lead is None or lead < low_water_us):
            self.filling = True
        if self.filling:
            self._step("plan", lambda: pipeline.plan_step(self.st, t_us, max_new=1))
            self._step("render", lambda: pipeline.render_step(
                self.st, t_us, limit=self.st.cfg.publish.batch_segments))
        self._step("publish", lambda: publish_all(self.p, t_us, self.held))
        lead = self.lead_us(t_us)
        if lead is not None and lead >= self.st.lead_us - grid.D_US:
            self.filling = False

    def run(self, max_ticks: int | None = None) -> None:
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            started = time.monotonic()
            self.tick(self.clock())
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            self.sleep(max(0.0, self.tick_s - (time.monotonic() - started)))


def status_lines(cfg: TransmitterConfig, t_us: int) -> list[str]:
    ws = Workspace(cfg.root)
    epoch = load_epoch(ws)
    if epoch is None:
        return ["no epoch yet - run `transmitter plan` (or `transmitter run`) first"]
    rows = read_plan(ws.plan_path)
    pub = load_publish_state(ws)
    fb = load_fallback_version(ws)
    lines = [f"epoch      {epoch.epoch_id} ({epoch.iso})"]
    if rows:
        end_us = epoch.epoch_us + grid.frame_to_us(rows[-1].end_frame)
        lines.append(f"plan       {len(rows)} rows through {grid.us_to_iso(end_us)}")
        now_frame = (t_us - epoch.epoch_us) * grid.SAMPLE_RATE // (grid.FRAME_SAMPLES * 1_000_000)
        on = next((r for r in rows if r.start_frame <= now_frame < r.end_frame), None)
        lines.append(f"on air     {on.slug}" if on else "on air     (between shows, or not started)")
    else:
        lines.append("plan       empty")
    if pub.last is None:
        lines.append("published  nothing yet")
    else:
        lead_h = (epoch.start_us(pub.last + 1) - t_us) / 3_600_000_000
        lines.append(f"published  segments {pub.first}..{pub.last}; lead {lead_h:.1f} h")
    lines.append(f"fallback   {fb}" if fb else "fallback   none (run `transmitter fallback render`)")
    return lines
