### Task 14: CLI commands, run loop, status

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/alerts.py`, `packages/transmitter/src/transmitter/service.py`
- Modify: `packages/transmitter/src/transmitter/cli.py`
- Create: `packages/transmitter/tests_transmitter/test_service.py`
- Modify: `packages/transmitter/tests_transmitter/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `transmitter.alerts.alert(code: str, message: str) -> None` — phase 1 logs `ALERT <code>: <message>` at ERROR on logger `transmitter.alerts` (phase 2 adds email/ntfy and dedupe behind this call).
  - `transmitter.service`: `now_us()`, `make_engine(ws, cfg)`, `make_client(cfg)` (both module-level so tests monkeypatch them), `open_station(cfg, t_us) -> Station`, `load_template(cfg) -> str`, `row_analysis(st, row) -> ShowAnalysis | None` (the cache if it still holds the row's key, else the engine's `analyze` — which re-caches — on the package when it still has the planned file set), `open_publisher(st) -> Publisher` (wires `analysis_for=lambda row: row_analysis(st, row)`), `publish_all(p, t_us) -> tuple[list[PublishReport], PruneReport]`, `Runner(st, p, *, clock=now_us, sleep=time.sleep, tick_s=60.0)` with `.filling`, `.halted`, `.lead_us(t_us)`, `.tick(t_us)`, `.run(max_ticks=None)` — each tick step (plan, render, publish) catches any `Exception`, logs its traceback, calls `alerts.alert(<step>, …)` and the loop goes on; a `FrameCountDrift` sets the `halted` latch instead (filling stops, one `frame-count-drift` alert, publishing of what exists continues, the loop stays alive until a restart); `status_lines(cfg, t_us) -> list[str]`.
  - CLI: `transmitter plan | render | publish | run [--once] | status | fallback render LOOP [--notice FILE] | config init`, each accepting `--config PATH`.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_service.py`:

```python
import logging

from tests_transmitter.helpers import NOW, TEMPLATE_PATH, FakeBucket, FakeEngine, make_station, write_seg
from transmitter import alerts, grid, pipeline, publish, service
from transmitter.planner import read_plan
from transmitter.segment import segment_key


def _publisher(st, bucket):
    uploader = publish.Uploader(bucket, "b", publish.PutBudget(st.ws.puts_path, 17_500, today=lambda: "d"),
                                sleep=lambda s: None)
    return publish.Publisher(ws=st.ws, cfg=st.cfg, epoch=st.epoch, uploader=uploader,
                             template=TEMPLATE_PATH.read_text(),
                             analysis_for=lambda row: service.row_analysis(st, row), log=lambda m: None)


def test_alert_logs(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_runner_fills_to_the_lead_then_idles_until_low_water(tmp_path):
    engine = FakeEngine()
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    for _ in range(5):
        runner.tick(NOW)
        if not runner.filling:
            break
    assert not runner.filling
    assert runner.lead_us(NOW) >= st.lead_us - grid.D_US
    seg_puts = len([k for k in bucket.puts() if k.startswith("seg/")])
    encoded = list(engine.encoded)
    runner.tick(NOW)                                        # lead is full: nothing new
    assert engine.encoded == encoded
    assert len([k for k in bucket.puts() if k.startswith("seg/")]) == seg_puts
    runner.tick(NOW + 200 * 1_000_000)                      # 160 s of lead < 180 s low water
    assert len([k for k in bucket.puts() if k.startswith("seg/")]) > seg_puts


def test_runner_alerts_and_keeps_publishing_when_planning_fails(tmp_path, caplog):
    st, _ = make_station(tmp_path)
    (st.cfg.station.root / ".station-root").unlink()
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
    assert "ALERT plan" in caplog.text and ".station-root" in caplog.text


def test_runner_survives_an_unexpected_error_and_the_next_tick_runs(tmp_path, caplog, monkeypatch):
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    real = pipeline.render_step
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_step", flaky)
    with caplog.at_level(logging.ERROR):
        runner.tick(NOW)
        runner.tick(NOW)
    assert "ALERT render: KeyError: 'boom'" in caplog.text and "Traceback" in caplog.text
    assert len(calls) == 2
    assert any(k.startswith("seg/") for k in bucket.puts())


def test_frame_count_drift_halts_filling_but_keeps_publishing(tmp_path, caplog):
    engine = FakeEngine(drift=1)
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
        assert runner.halted and not runner.filling
        attempts = list(engine.encoded)
        n = read_plan(st.ws.plan_path)[0].start_frame // grid.SEGMENT_FRAMES
        write_seg(st.ws, "etest", n)                       # rendered before the halt
        runner.tick(NOW + 60_000_000)
        runner.tick(NOW + 120_000_000)
    assert caplog.text.count("ALERT frame-count-drift") == 1
    assert engine.encoded == attempts                      # no further render attempts
    assert segment_key("etest", n) in bucket.objects       # publishing went on


def test_run_with_max_ticks_sleeps_between_ticks(tmp_path):
    st, _ = make_station(tmp_path)
    sleeps = []
    clock = iter([NOW, NOW + 60_000_000, NOW + 120_000_000])
    runner = service.Runner(st, _publisher(st, FakeBucket()), clock=lambda: next(clock),
                            sleep=sleeps.append, tick_s=60.0)
    runner.run(max_ticks=3)
    assert len(sleeps) == 2


def test_status_lines(tmp_path):
    st, _ = make_station(tmp_path)
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    lines = service.status_lines(st.cfg, NOW)
    assert lines[0].startswith("epoch      etest")
    assert any(l.startswith("published  nothing yet") for l in lines)
    assert any("fallback   none" in l for l in lines)
```

Append to `tests_transmitter/test_cli.py`:

```python
from pathlib import Path

from tests_transmitter.helpers import FakeBucket, FakeEngine, build_package, make_root
from transmitter import service

REPO = Path(__file__).resolve().parents[3]


def _config(tmp_path, root):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[station]\nroot = "{root}"\nquiet_minutes = 0.0\n'
        '[planner]\nstart_delay_minutes = 0.5\n'
        '[render]\nlead_hours = 0.1\nlow_water_hours = 0.05\n'
        '[publish]\nbucket = "b"\n'
        f'[antenna]\ndir = "{REPO / "antenna"}"\n'
    )
    return path


def test_status_before_anything(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0 and "no epoch yet" in result.output


def test_plan_command(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    result = CliRunner().invoke(app, ["plan", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    assert "band-2005-11-01" in result.output
    assert (tmp_path / "tx" / "plan.jsonl").exists()


def test_run_once_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    root = make_root(tmp_path)
    for i in (1, 2):
        build_package(root, f"band-2005-11-0{i}")
    result = CliRunner().invoke(app, ["run", "--once", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    keys = set(bucket.objects)
    assert any(k.startswith("seg/") for k in keys)
    assert {"state/horizon.json", "timeline.json"} <= keys
    assert any(k.startswith("notes/") for k in keys) and any(k.startswith("show/") for k in keys)


def test_publish_without_a_bucket_is_a_config_error(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    path = tmp_path / "c.toml"
    path.write_text(f'[station]\nroot = "{root}"\n')
    result = CliRunner().invoke(app, ["publish", "--config", str(path)])
    assert result.exit_code != 0 and "bucket" in str(result.exception)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_service.py packages/transmitter/tests_transmitter/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'alerts'` / `'service'`.

- [ ] **Step 3: Implement `alerts.py` and `service.py`**

`packages/transmitter/src/transmitter/alerts.py`:

```python
"""Alert seam (spec "Alerts and operations", phase 2). Phase 1 logs at ERROR
(journald picks it up under systemd); phase 2 adds SMTP + ntfy channels and
per-condition dedupe in ~/.transmitter/alerts.json behind this same call."""

import logging

log = logging.getLogger("transmitter.alerts")


def alert(code: str, message: str) -> None:
    log.error("ALERT %s: %s", code, message)
```

`packages/transmitter/src/transmitter/service.py`:

```python
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
from transmitter.errors import ConfigError, FrameCountDrift
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


def publish_all(p: publish.Publisher, t_us: int) -> tuple[list[publish.PublishReport], publish.PruneReport]:
    reports = []
    for _ in range(MAX_BATCHES):
        r = publish.publish_batch(p, t_us)
        reports.append(r)
        if r.stopped == "put-budget":
            alerts.alert("put-budget", r.error or "daily PUT budget exceeded; publishing stopped")
        elif r.stopped == "guard":
            log.info("publishing paused: state/guard.json says tripped (or is unreadable)")
        elif r.error:
            alerts.alert("publish", r.error)
        if not r.uploaded or r.stopped or r.error:
            break
    pr = publish.prune(p, t_us)
    if pr.error:
        alerts.alert("prune", pr.error)
    return reports, pr


class Runner:
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.filling = False
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
        self._step("publish", lambda: publish_all(self.p, t_us))
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
```

- [ ] **Step 4: Wire the CLI commands**

In `cli.py`, add imports at the top:

```python
import logging

from transmitter import aacenc, fallback, grid, pipeline, service
from transmitter.config import load_config
```

and these commands after `config_init`:

```python
CONFIG_OPT = typer.Option(None, "--config", help="Config file (default: $TRANSMITTER_ROOT or "
                                                 "~/.transmitter, then /config.toml)")

fallback_app = typer.Typer(help="The fallback loop and off-air notice", pretty_exceptions_enable=False)
app.add_typer(fallback_app, name="fallback")


@app.command()
def plan(config: Path = CONFIG_OPT):
    """Extend the plan to cover now + lead (phase 1: fixed shuffled order)."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    rows = pipeline.plan_step(st, t)
    for r in rows[-10:]:
        typer.echo(f"{grid.us_to_iso(st.epoch.epoch_us + grid.frame_to_us(r.start_frame))}  {r.slug}")


@app.command()
def render(config: Path = CONFIG_OPT):
    """Plan, then render segments up to now + lead."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    pipeline.plan_step(st, t)
    report = pipeline.render_step(st, t)
    extra = f"; re-planned around {', '.join(report.replanned)}" if report.replanned else ""
    typer.echo(f"wrote {len(report.written)} segment(s){extra}")


@app.command("publish")
def publish_cmd(config: Path = CONFIG_OPT):
    """Upload rendered segments, timeline and show pages; then prune."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    reports, pruned = service.publish_all(service.open_publisher(st), t)
    typer.echo(f"uploaded {sum(len(r.uploaded) for r in reports)} segment(s); pruned {pruned.deleted}")


@app.command()
def run(config: Path = CONFIG_OPT,
        once: bool = typer.Option(False, "--once", help="Run one tick and exit")):
    """The service loop: plan/render below low water, publish and prune every minute."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    service.Runner(st, service.open_publisher(st)).run(max_ticks=1 if once else None)


@app.command()
def status(config: Path = CONFIG_OPT):
    """Epoch, plan, what is on air, published lead, fallback version."""
    for line in service.status_lines(load_config(config), service.now_us()):
        typer.echo(line)


@fallback_app.command("render")
def fallback_render(
    loop: Path = typer.Argument(..., exists=True, dir_okay=False, help="Station-ID loop audio"),
    notice: Path = typer.Option(None, "--notice", exists=True, dir_okay=False,
                                help="Off-air notice audio (default: silence)"),
    config: Path = CONFIG_OPT,
):
    """Render the fallback loop + off-air notice and upload them (immutable)."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    p = service.open_publisher(st)
    build = fallback.build_fallback(loop, notice, ffmpeg=cfg.render.ffmpeg,
                                    music_target_lufs=cfg.render.music_target_lufs,
                                    speech_target_lufs=cfg.render.speech_target_lufs,
                                    extra=aacenc.extra_frames(cfg.render.ffmpeg))
    fallback.write_local(st.ws, build)
    fallback.upload_fallback(p, build, t)
    typer.echo(f"fallback {build.version}: {len(build.segments)} segment(s) + notice uploaded")
```

In `main_cli`, configure logging before `app()`:

```python
def main_cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        app()
    ...  # unchanged
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

Run: `./.venv/bin/python -m pytest -q && packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS both.

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): plan/render/publish/run/status/fallback commands and the service loop"
```

---

