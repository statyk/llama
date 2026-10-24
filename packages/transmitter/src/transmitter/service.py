"""Wiring for the CLI and the service loop (spec "transmitter -- state and
commands", "Lead"). `run` ticks once a minute: below the low-water mark it
starts filling -- each tick plans at most one more show and renders at most
one publish batch, then publishes -- until the published lead is back at
`lead_hours`; publishing and pruning run every tick. An error in any step is
logged with its traceback and alerted, and the loop goes on; a frame-count
drift halts filling (publishing goes on) until transmitter is restarted."""

import logging
import math
import time
from pathlib import Path
from typing import Callable

from transmitter import alerts, analysis, cloudstate, grid, pipeline, publish, r2, sdnotify, station
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.deadclock import DeadClockMonitor
from transmitter.errors import CloudDocumentError, ConfigError, FrameCountDrift, PublishLocked, StationRootError, TransmitterError
from transmitter.layout import PlanRow
from transmitter.planner import read_plan
from transmitter.state import load_fallback_version, load_publish_state
from transmitter.workspace import Workspace, load_epoch, load_or_create_epoch, read_json

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
    when the package still has the file set the row was planned from.

    The fallback evaluates the package against the real clock (`time.time()`,
    not the tick's time) with `quiet_s=0`, and runs inside `_publish_site`, so
    when `cache/<key>.json` is missing it can run a full ffmpeg analysis while
    the publish flock is held, lengthening that one publish tick by minutes.
    A lost `cache/` can make this recompute long enough to meet WatchdogSec
    (it is not followed by a watchdog ping). Acceptable: the cache is never garbage-collected, so this is reachable only
    after an operator deleted `cache/` (or a decode mismatch dropped an entry)."""
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


def publish_all(p: publish.Publisher, t_us: int, held: HeldTracker | None = None,
                notify: Callable[[str], object] | None = None
                ) -> tuple[list[publish.PublishReport], publish.PruneReport]:
    reports = []
    for _ in range(MAX_BATCHES):
        r = publish.publish_batch(p, t_us)
        reports.append(r)
        if notify is not None:
            notify("WATCHDOG=1")    # a catch-up is many batches: one step must not outlast WatchdogSec
        _report_stop("publish", r.stopped, r.error, r.held)
        if not r.uploaded or r.stopped or r.error:
            break
    if held is not None:
        held.observe(any(r.held for r in reports))
    pr = publish.prune(p, t_us, notify)
    _report_stop("prune", pr.stopped, pr.error)
    return reports, pr


def open_monitor(st: pipeline.Station) -> DeadClockMonitor | None:
    """The dead-clock check, when [antenna] site_url says where live.m3u8 is."""
    url = st.cfg.antenna.site_url
    if not url:
        log.warning("[antenna] site_url is not set: the dead-clock check is off")
        return None
    a = st.cfg.alerts
    # An unexpected 403 must outlast the guard cache (refreshed every
    # guard_check_minutes) before it alarms.
    return DeadClockMonitor(url.rstrip("/") + "/live.m3u8", st.epoch.epoch_us, a.dead_clock_seconds,
                            a.guard_stale_minutes * 60, math.ceil(st.cfg.publish.guard_check_minutes) + 2)


class Runner:
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0,
                 monitor: DeadClockMonitor | None = None, notify: Callable[[str], object] = sdnotify.notify):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.monitor, self.notify = monitor, notify
        self.filling = False
        self.held = HeldTracker()
        self.halted = False          # latched by a frame-count drift; cleared by a restart

    def lead_us(self, t_us: int) -> int | None:
        last = load_publish_state(self.st.ws).last
        return None if last is None else self.st.epoch.start_us(last + 1) - t_us

    def _step(self, name: str, fn: Callable[[], object], *, resolves: tuple[str, ...] = ()) -> bool:
        """Run one step; no error ends the loop (the next tick retries). A step
        that succeeds resolves `resolves`; every step ends with a watchdog ping.
        True when the step observed (ran), i.e. unless it was skipped on
        PublishLocked: a skipped step neither advances nor resets the 3-
        consecutive gate of the codes it declares (alerts.STEP_CODES)."""
        try:
            fn()
            for code in resolves:
                alerts.resolve(code)
        except StationRootError as exc:
            log.error("%s step: %s", name, exc)
            alerts.alert("station-root", f"{type(exc).__name__}: {exc}")
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
            return False
        except Exception as exc:
            log.exception("%s step failed", name)
            alerts.alert(name, f"{type(exc).__name__}: {exc}")
        finally:
            self.notify("WATCHDOG=1")
        return True

    def _read_lead(self, t_us: int) -> tuple[bool, int | None]:
        """(readable, lead). An unreadable publish.json is alerted, not raised:
        raising here (outside `_step`) would crash-loop the service."""
        try:
            return True, self.lead_us(t_us)
        except Exception as exc:
            log.error("publish state unreadable", exc_info=True)
            alerts.alert("publish-state", f"cannot read {self.st.ws.publish_state_path} "
                                          f"({type(exc).__name__}: {exc}); this tick plans, renders and "
                                          "publishes nothing until it is repaired")
            return False, None

    def tick(self, t_us: int) -> None:
        """One tick is one observation of the tick's gated alert codes: the
        steps that ran are declared to the Dispatcher at the end, on every
        path (alerts.end_observation)."""
        ran: set[str] = set()
        try:
            self._tick(t_us, ran)
        finally:
            alerts.end_observation(alerts.TICK, ran)

    def _tick(self, t_us: int, ran: set[str]) -> None:
        low_water_us = int(self.st.cfg.render.low_water_hours * 3600 * 1_000_000)
        ok, lead = self._read_lead(t_us)
        ran.add("lead")
        if not ok:
            # Fail closed: publish.json mirrors what R2 lists; without it no step
            # can know what is safe to plan, render, upload or prune. This is a
            # designed, alerted state, not a hang: keep the watchdog fed.
            self.notify("WATCHDOG=1")
            return
        if not self.halted and (lead is None or lead < low_water_us):
            self.filling = True
        if self.filling:
            if self._step("plan", lambda: pipeline.plan_step(self.st, t_us, max_new=1),
                          resolves=("plan", "station-root")):
                ran.add("plan")
            if self._step("render", lambda: pipeline.render_step(
                    self.st, t_us, limit=self.st.cfg.publish.batch_segments, notify=self.notify),
                    resolves=("render",)):
                ran.add("render")
        if self._step("publish", lambda: publish_all(self.p, t_us, self.held, self.notify)):
            ran.add("publish")
        if self.monitor is not None:
            monitor = self.monitor
            # "dead-clock-check", not "dead-clock": a monitor that RAISES must fire an event code, never the
            # level code that means "the clock is dead" (only the monitor raises and resolves that one).
            self._step("dead-clock-check", lambda: monitor.check(self.clock(), lambda: read_json(self.st.ws.guard_cache_path)))
            # Interim, until the monitor moves to its own thread: this check is one monitor pass.
            alerts.end_observation(alerts.MONITOR, ["dead-clock-check"])
        ok, lead = self._read_lead(t_us)
        if ok and lead is not None and lead >= self.st.lead_us - grid.D_US:
            self.filling = False

    def run(self, max_ticks: int | None = None) -> None:
        self.notify("READY=1")
        ticks = 0
        try:
            while max_ticks is None or ticks < max_ticks:
                started = time.monotonic()
                self.tick(self.clock())
                ticks += 1
                if max_ticks is not None and ticks >= max_ticks:
                    break
                self.sleep(max(0.0, self.tick_s - (time.monotonic() - started)))
        finally:
            self.notify("STOPPING=1")


def cloud_lines(read: Callable[[str], dict | None], t_us: int | None = None) -> list[str]:
    """`status`'s cloud half: the guard, the operator's flag, a raise, cloud
    alerts. `read(key)` returns a state/ document or None (cloudstate.get_json).
    Each document is read on its own: a corrupt one prints its own line and the
    rest still print. An access or transport failure ends the half with one
    `unavailable` line (the next read would fail the same way)."""
    now = time.time_ns() // 1000 if t_us is None else t_us
    lines: list[str] = []

    def fetch(key: str, label: str, consequence: str = ""):
        """(ok, doc): a corrupt document prints its own line; anything else raises."""
        try:
            return True, read(key)
        except CloudDocumentError as exc:
            lines.append(f"{label} unreadable: {exc}" + (f" -- {consequence}" if consequence else ""))
            return False, None

    try:
        ok, guard = fetch(cloudstate.GUARD_KEY, "guard     ", "the clock treats it as a spend trip")
        if ok:
            problem = cloudstate.guard_doc_problem(guard) if guard is not None else None
            try:
                summary = cloudstate.guard_summary(guard)
            except (TypeError, ValueError, AttributeError):
                summary = []
            if problem is not None:
                lines.append(f"guard      CORRUPT ({problem}): the clock treats it as a spend trip")
                lines += summary[1:]               # its own verdict line is replaced, as `budget` does
                guard = None
            else:
                lines += summary
        ok, offair = fetch(cloudstate.OFFAIR_KEY, "offair    ", "the clock treats the station as off the air")
        if ok:
            if offair is None:
                lines.append("offair     off")
            elif offair.get("offair") is True:
                lines.append(f"offair     ON since {offair.get('since')} ({offair.get('reason')})"
                             + (f", expected until {offair['until']}" if offair.get("until") else ""))
            elif offair.get("offair") is False:
                lines.append("offair     off")
            else:
                lines.append("offair     CORRUPT: the clock treats the station as off the air; "
                             "rewrite with transmitter offair on|off")
        ok, raised = fetch(cloudstate.BUDGET_KEY, "raise     ")
        if ok and raised:
            lines.append(cloudstate.raise_status_line(raised, guard, now))
        ok, cloud_alerts = fetch(cloudstate.ALERTS_KEY, "alerts     cloud:")
        if ok:
            active = sorted(k for k, e in (cloud_alerts or {}).items() if isinstance(e, dict) and e.get("active"))
            lines.append(f"alerts     cloud: {', '.join(active) if active else 'none'}")
    except Exception as exc:                       # a read-only view: never a traceback
        lines.append(f"cloud      unavailable: {exc}")
    return lines


def _cloud_tail(cloud, cloud_error: str | None, t_us: int) -> list[str]:
    if cloud is not None:
        return cloud_lines(cloud, t_us)
    return [f"cloud      unavailable: {cloud_error}"] if cloud_error else []


def status_lines(cfg: TransmitterConfig, t_us: int, cloud: Callable[[str], dict | None] | None = None,
                 cloud_error: str | None = None) -> list[str]:
    ws = Workspace(cfg.root)
    epoch = load_epoch(ws)
    if epoch is None:
        return ["no epoch yet - run `transmitter plan` (or `transmitter run`) first"] + _cloud_tail(cloud, cloud_error, t_us)
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
    lines.append("anchors    none (the scheduler and its window misses are phase 3)")
    state = alerts.load_state(ws.alerts_path)
    if state is None:
        lines.append(f"alerts     hugo: unreadable ({ws.alerts_path})")
    else:
        hugo = alerts.active_codes(state, t_us / 1e6, cfg.alerts.repeat_hours * 3600)
        lines.append(f"alerts     hugo: {', '.join(hugo) if hugo else 'none'}")
    return lines + _cloud_tail(cloud, cloud_error, t_us)
