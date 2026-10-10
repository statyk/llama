"""CLI boundary: typer app + `main_cli` error boundary (mirrors emcee's)."""

import sys
import traceback
from pathlib import Path

import typer

from transmitter.config import DEFAULT_CONFIG_TOML, default_root
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


def main_cli() -> None:
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
