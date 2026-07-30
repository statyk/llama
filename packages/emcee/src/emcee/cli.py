"""CLI boundary: typer app + `main_cli` error boundary.

Later tasks register real commands on `app`. `_COMMAND_ORDER` fixes the
`--help` panel ordering via `OrderedPanelGroup`, mirroring llama's
`cli.py:57-65` pattern.
"""

import sys
import traceback

import typer
from typer.core import TyperGroup

from herder import HerderError

from emcee.errors import EmceeError

_COMMAND_ORDER = ["run", "voice", "status", "presenter", "config"]


class OrderedPanelGroup(TyperGroup):
    def list_commands(self, ctx):
        cmds = super().list_commands(ctx)
        order = {name: i for i, name in enumerate(_COMMAND_ORDER)}
        return sorted(cmds, key=lambda c: order.get(c, len(order)))


app = typer.Typer(help="Voice llama show packages: DJ script + TTS audio + broadcast.m3u",
                  pretty_exceptions_enable=False, cls=OrderedPanelGroup)


@app.callback()
def _main() -> None:
    """No global options yet — placeholder callback.

    A Typer group with zero registered commands cannot build a Click command
    at all (`RuntimeError: Could not get a command for this Typer instance`),
    so an empty callback is required here even before any subcommands exist.
    Later tasks may replace this body with real global options, mirroring
    llama's `cli.py:99` callback.
    """


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
