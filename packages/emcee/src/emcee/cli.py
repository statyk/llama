"""CLI boundary: typer app + `main_cli` error boundary.

Later tasks register real commands on `app`. `_COMMAND_ORDER` fixes the
`--help` panel ordering via `OrderedPanelGroup`, mirroring llama's
`cli.py:57-65` pattern.
"""

import os
import sys
import traceback
from pathlib import Path

import typer
from typer.core import TyperGroup

from herder import HerderError

from emcee.errors import EmceeError
from emcee.presenters import (
    Presenter, PresenterError, delete_presenter, list_presenters, load_presenter, save_presenter,
)

_COMMAND_ORDER = ["run", "voice", "status", "presenter", "config"]


class OrderedPanelGroup(TyperGroup):
    def list_commands(self, ctx):
        cmds = super().list_commands(ctx)
        order = {name: i for i, name in enumerate(_COMMAND_ORDER)}
        return sorted(cmds, key=lambda c: order.get(c, len(order)))


app = typer.Typer(help="Voice llama show packages: DJ script + TTS audio + broadcast.m3u",
                  pretty_exceptions_enable=False, cls=OrderedPanelGroup)

presenter_app = typer.Typer(help="On-air hosts (presenters/<id>.toml)",
                            pretty_exceptions_enable=False)
app.add_typer(presenter_app, name="presenter")


@app.callback()
def _main() -> None:
    """No global options yet — placeholder callback.

    Keep it, even though `app` currently has a sub-typer (`presenter`) and so
    already renders `Usage: emcee [OPTIONS] COMMAND [ARGS]...` with or
    without this callback. The risk is future, not current: Typer allows
    exactly one callback, and an app whose *only* top-level registration is a
    single plain command (no sub-typer, no callback) collapses `--help` to
    `Usage: emcee [OPTIONS]` instead of the `... COMMAND [ARGS]...` form.
    Task 9 adds `run`/`voice`/`status` as plain top-level commands
    alongside `presenter`, and this callback is what keeps that combination
    from collapsing. Later tasks may replace this body with real global
    options, mirroring llama's `cli.py:99` callback.
    """


def default_root() -> Path:
    """Resolve the emcee workspace root: `EMCEE_ROOT` env override, else
    `~/.emcee`. Task 5 replaces this with config-based resolution; kept as a
    single obvious seam (one function, called from each command) to swap."""
    root = os.environ.get("EMCEE_ROOT")
    return Path(root) if root else Path.home() / ".emcee"


def _assignments_using_presenter(root: Path, presenter_id: str) -> list[str]:
    """Names of emcee `[assign]` config entries that still name this
    presenter -- used by `presenter remove`'s in-use refusal. Config lands in
    Task 5; until then there is nothing to check, so this always returns
    `[]`. Task 5 re-signatures this to take the loaded config and implements
    the real lookup over `config.assign.profiles` (plus `[assign] default`)."""
    return []


@presenter_app.command("add")
def presenter_add(
    id: str = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
    sex: str = typer.Option(..., "--sex"),
    voice: str = typer.Option(None, "--voice"),
    voice_clone: str = typer.Option(None, "--voice-clone"),
    character: str = typer.Option(None, "--character"),
    character_file: Path = typer.Option(None, "--character-file"),
    bed: str = typer.Option(None, "--bed"),
    force: bool = typer.Option(False, "--force"),
):
    """Create a presenter (on-air host)."""
    root = default_root()
    if bool(character) == bool(character_file):
        typer.echo("give exactly one of --character / --character-file", err=True)
        raise typer.Exit(1)
    if character:
        text = character
    else:
        try:
            text = character_file.read_text().strip()
        except OSError as exc:
            typer.echo(f"cannot read --character-file {character_file}: {exc}", err=True)
            raise typer.Exit(1)
    dest = root / "presenters" / f"{id}.toml"
    if dest.exists() and not force:
        typer.echo(f"presenter {id!r} exists: {dest} (use --force to overwrite)", err=True)
        raise typer.Exit(1)
    try:
        p = Presenter(id=id, name=name, sex=sex, voice=voice,
                      voice_clone=voice_clone, character=text, bed=bed)
    except Exception as exc:
        typer.echo(f"invalid presenter: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"saved: {save_presenter(root, p)}")


@presenter_app.command("list")
def presenter_list():
    """List presenters."""
    root = default_root()
    rows = list_presenters(root)
    if not rows:
        typer.echo("no presenters")
        return
    for pid, p in rows:
        if isinstance(p, str):
            typer.echo(f"{pid:16.16s} (invalid: {p})")
        else:
            v = p.voice or f"clone:{p.voice_clone}"
            typer.echo(f"{pid:16.16s} {p.name:20.20s} {p.sex:8.8s} {v}")


@presenter_app.command("show")
def presenter_show(id: str = typer.Argument(...)):
    """Show one presenter's fields."""
    root = default_root()
    p = load_presenter(root, id)     # PresenterError -> main_cli boundary
    v = p.voice or f"clone:{p.voice_clone}"
    typer.echo(f"{p.name}  ({p.sex})  voice={v}" + (f"  bed={p.bed}" if p.bed else ""))
    typer.echo("character:")
    typer.echo(p.character)


@presenter_app.command("remove")
def presenter_remove(
    id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
    force: bool = typer.Option(False, "--force",
                               help="Remove even if an assignment still names this presenter"),
):
    """Delete a presenter's TOML file. Refuses if an assignment still names
    it as its presenter -- pass --force to remove it anyway."""
    root = default_root()
    path = root / "presenters" / f"{id}.toml"
    if not path.exists():
        raise PresenterError(f"no presenter {id!r}: {path} does not exist")
    if not force:
        users = _assignments_using_presenter(root, id)
        if users:
            typer.echo(f"presenter {id} is used by: {', '.join(users)} "
                       "— --force to remove anyway", err=True)
            raise typer.Exit(1)
    if not yes and not typer.confirm(f"remove presenter {id!r}?", default=False):
        return
    delete_presenter(root, id)
    typer.echo(f"removed: {path}")


def main_cli() -> None:
    """CLI entry point with a single error boundary.

    Expected, user-actionable failures (`emcee.errors.EmceeError` or
    `herder.HerderError`) print a clean `error: <message>` plus any indented
    details and exit 1. `KeyboardInterrupt` exits 130 quietly. Any other
    exception is a bug: we print a plain traceback ourselves and exit 1 —
    printing it here (rather than letting it propagate) suppresses the frozen
    bootloader's `Failed to execute script` line. `SystemExit`/`typer.Exit`
    from commands pass through untouched.
    """
    try:
        app()
    except (EmceeError, HerderError) as e:
        print(f"error: {e}", file=sys.stderr)
        for line in getattr(e, "details", []):
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
