"""CLI boundary: typer app + `main_cli` error boundary (mirrors emcee's)."""

import logging
import sys
import traceback
from pathlib import Path

import typer

from transmitter import aacenc, fallback, grid, pipeline, service
from transmitter.config import DEFAULT_CONFIG_TOML, default_root, load_config
from transmitter.errors import TransmitterError
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
