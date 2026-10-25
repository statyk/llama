"""CLI boundary: typer app + `main_cli` error boundary (mirrors emcee's)."""

import logging
import sys
import traceback
from pathlib import Path

import typer

from transmitter import aacenc, cloudstate, fallback, grid, pipeline, service
from transmitter.config import DEFAULT_CONFIG_TOML, default_root, load_config
from transmitter.errors import CloudStateError, ConfigError, TransmitterError
from transmitter.locks import plan_lock
from transmitter.workspace import atomic_write_text

app = typer.Typer(help="Plan, render and publish the station's HLS stream",
                  pretty_exceptions_enable=False, no_args_is_help=True)

config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        import transmitter

        typer.echo(transmitter.__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(None, "--version", callback=_version_callback,
                                 is_eager=True, help="Print the transmitter version and exit."),
) -> None:
    """Station playout."""


@config_app.command("init")
def config_init(
    stdout: bool = typer.Option(False, "--stdout", help="Print the default config instead of writing it"),
    config_path: Path = typer.Option(None, "--config", help="Target file (default: $TRANSMITTER_ROOT "
                                                            "or ~/.transmitter, then /config.toml)"),
):
    """Seed a config file with the baked-in defaults, commented."""
    if stdout:
        typer.echo(DEFAULT_CONFIG_TOML, nl=False)
        return
    target = config_path or default_root() / "config.toml"
    if target.exists():
        typer.echo(f"{target} already exists - not overwriting", err=True)
        raise typer.Exit(1)
    atomic_write_text(target, DEFAULT_CONFIG_TOML)
    typer.echo(f"wrote {target}")



CONFIG_OPT = typer.Option(None, "--config", help="Config file (default: $TRANSMITTER_ROOT or "
                                                 "~/.transmitter, then /config.toml)")

fallback_app = typer.Typer(help="The fallback loop and off-air notice", pretty_exceptions_enable=False)
app.add_typer(fallback_app, name="fallback")

offair_app = typer.Typer(help="Take the station off the air (state/offair.json), or put it back",
                         pretty_exceptions_enable=False, no_args_is_help=True)
app.add_typer(offair_app, name="offair")


def _cloud(config: Path | None):
    """(client, bucket) for the operator commands: R2 keys from the environment."""
    cfg = load_config(config)
    if not cfg.publish.bucket:
        raise ConfigError("set [publish] bucket in transmitter's config.toml")
    return service.make_client(cfg), cfg.publish.bucket


@offair_app.command("on")
def offair_on(
    reason: str = typer.Option(..., "--reason", help="Why (shown in `transmitter status`)"),
    until: str = typer.Option(None, "--until", help="Expected end, ISO-8601 UTC (informational only)"),
    config: Path = CONFIG_OPT,
):
    """Off the air: within about a minute the clock lists the off-air notice and
    ENDLIST, index.html becomes the off-air page and the WAF kill switch is on."""
    client, bucket = _cloud(config)
    doc = cloudstate.set_offair(client, bucket, True, reason, until, service.now_us())
    typer.echo(f"state/offair.json: off the air since {doc['since']} ({doc['reason']}). The clock blocks the "
               "station within about a minute: the off-air playlist and page, and the kill switch.")


@offair_app.command("off")
def offair_off(
    reason: str = typer.Option("back on air", "--reason", help="Why (shown in `transmitter status`)"),
    config: Path = CONFIG_OPT,
):
    """Back on the air (clears only the operator's flag; a tripped cost guard keeps the station blocked)."""
    client, bucket = _cloud(config)
    doc = cloudstate.set_offair(client, bucket, False, reason, None, service.now_us())
    typer.echo(f"state/offair.json: on the air since {doc['since']}.")
    # The flag is written: a failure from here on is a note, not an error.
    try:
        guard = cloudstate.get_json(client, bucket, cloudstate.GUARD_KEY)
    except TransmitterError as exc:
        typer.echo(f"note: could not read state/guard.json ({exc}); the station may stay blocked (a corrupt "
                   "guard.json is a spend trip; see `transmitter budget`).", err=True)
        return
    problem = cloudstate.guard_doc_problem(guard) if guard is not None else None
    if problem is not None:
        typer.echo(f"note: state/guard.json is not a document the guard wrote ({problem}); the guard treats the "
                   "station as tripped until it rewrites it (see `transmitter budget`).", err=True)
    elif guard and guard.get("tripped"):
        typer.echo(f"note: the cost guard is tripped ({guard.get('reason')}); the station stays blocked until it "
                   "clears (see `transmitter budget`).", err=True)


@app.command()
def budget(
    raise_to: float = typer.Option(None, "--raise-to", help="Raise this billing period's budget to USD"),
    config: Path = CONFIG_OPT,
):
    """Show the cost guard's state, or raise the budget for the rest of this billing period."""
    client, bucket = _cloud(config)
    if raise_to is not None:
        doc = cloudstate.raise_budget(client, bucket, raise_to, service.now_us())
        typer.echo(f"state/budget.json: ${doc['budget_usd']:.2f} until {doc['expires']}. The guard evaluates at its "
                   "next run; a spend trip clears only if that evaluation is under the thresholds.")
        return
    failed = False
    guard = None
    try:
        guard = cloudstate.get_json(client, bucket, cloudstate.GUARD_KEY)
    except TransmitterError as exc:
        failed = True
        typer.echo(f"guard      {exc}")
    problem = cloudstate.guard_doc_problem(guard) if guard is not None else None
    if problem is not None:
        failed = True
        typer.echo(f"guard      state/guard.json is not a document the guard wrote ({problem}); the guard "
                   "treats it as a spend trip")
        guard = None
    elif not failed:
        for line in cloudstate.guard_summary(guard):
            typer.echo(line)
    try:
        raised = cloudstate.get_json(client, bucket, cloudstate.BUDGET_KEY)
    except TransmitterError as exc:
        failed = True
        typer.echo(f"raise      {exc}")
        raised = None
    if raised:
        typer.echo(cloudstate.raise_status_line(raised, guard, service.now_us()))
    if failed:
        raise typer.Exit(1)


@app.command()
def plan(config: Path = CONFIG_OPT):
    """Extend the plan to cover now + lead (phase 1: fixed shuffled order)."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    with plan_lock(st.ws):
        rows = pipeline.plan_step(st, t)
    for r in rows[-10:]:
        typer.echo(f"{grid.us_to_iso(st.epoch.epoch_us + grid.frame_to_us(r.start_frame))}  {r.slug}")


@app.command()
def render(config: Path = CONFIG_OPT):
    """Plan, then render segments up to now + lead."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    with plan_lock(st.ws):
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
    problems = [f"publish: {r.stopped or ''}{': ' if r.stopped and r.error else ''}{r.error or ''}"
                for r in reports if r.error or r.stopped in ("put-budget", "guard")]
    if pruned.error or pruned.stopped in ("put-budget", "guard"):
        problems.append(f"prune: {pruned.stopped or ''}{': ' if pruned.stopped and pruned.error else ''}"
                        f"{pruned.error or ''}")
    for line in problems:
        typer.echo(line, err=True)
    if problems:
        raise typer.Exit(1)


@app.command()
def run(config: Path = CONFIG_OPT,
        once: bool = typer.Option(False, "--once", help="Run one tick, then one dead-clock check (no relay), and exit")):
    """The service loop: plan/render below low water, publish and prune every minute."""
    from transmitter import alerts

    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    alerts.configure(alerts.dispatcher_from_config(cfg, st.ws))
    try:
        runner = service.Runner(st, service.open_publisher(st), monitor=service.open_monitor(st))
        if once:
            runner.run_once()
        else:
            runner.run()
    finally:
        alerts.configure(None)


@app.command()
def status(config: Path = CONFIG_OPT):
    """Epoch, plan, on air, lead, fallback; the cost guard, off-air flag, kill switch and active alerts."""
    cfg = load_config(config)
    cloud, error = None, None
    try:
        client, bucket = _cloud(config)

        def cloud(key: str):                       # a read-only view: any failure is a line, not a traceback
            try:
                return cloudstate.get_json(client, bucket, key)
            except TransmitterError:
                raise
            except Exception as exc:
                raise CloudStateError(f"cannot read {key}: {exc}") from exc
    except Exception as exc:                       # no bucket, no R2 keys, a malformed endpoint: local half still prints
        error = str(exc)
    for line in service.status_lines(cfg, service.now_us(), cloud, error):
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
    written = fallback.upload_fallback(p, build, t)
    typer.echo(f"fallback {build.version}: {len(build.segments)} segment(s) + notice uploaded; "
               + ("horizon updated" if written else
                  "horizon deferred (the next publish batch carries the version)"))


def main_cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        app()
    except TransmitterError as e:
        print(f"error: {e}", file=sys.stderr)
        for line in e.details:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
