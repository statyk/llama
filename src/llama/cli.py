import logging
from datetime import date
from pathlib import Path

import typer

from llama.config import Config, load_config
from llama.ia_client import IAClient
from llama.ledger import Ledger
from llama.models import Criteria, ShortlistEntry
from llama.pipeline import choose_entries, make_providers, process_show
from llama.stages.interpret import run_interpret
from llama.stages.search import run_search
from llama.stages.winnow import run_winnow
from llama.util import slugify
from llama.workspace import RunWorkspace, read_model, read_model_list, write_artifact

app = typer.Typer(help="Live Music Archive -> radio station pipeline")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@app.callback()
def main() -> None:
    """Find, vet, research, and package LMA concerts for broadcast."""


@app.command()
def version() -> None:
    """Print the llama version."""
    import llama

    typer.echo(llama.__version__)


def _setup(config_path: Path | None) -> tuple[Config, IAClient, Ledger]:
    config = load_config(config_path)
    ia = IAClient(config.root / "cache")
    ledger = Ledger(config.root / "ledger.jsonl")
    return config, ia, ledger


def _print_shortlist(entries: list[ShortlistEntry]) -> None:
    for e in entries:
        c = e.candidate
        typer.echo(f"{e.rank:2d}. {c.date}  {c.venue or '?':30.30s}  "
                   f"score {e.assessment.quality_score:.1f}  {e.assessment.rationale[:80]}")


def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False) -> None:
    providers = make_providers(config)
    run_search(ws, ia, criteria, force=force)
    shortlist = run_winnow(ws, providers["score_reviews"], providers["light_research"], ia, criteria, ledger,
                           shortlist_size=max(12, count), force=force)
    if not shortlist:
        typer.echo("No shows survived winnowing.")
        return
    _print_shortlist(shortlist)
    if not auto and all(e.approved is None for e in shortlist):
        picks = typer.prompt("Process which ranks? (comma-separated, empty = top picks)",
                             default="", show_default=False)
        if picks.strip():
            wanted = {int(p) for p in picks.split(",")}
            for e in shortlist:
                e.approved = e.rank in wanted
            write_artifact(ws.shortlist, shortlist)
    chosen = choose_entries(shortlist, count, human_gate and auto)
    if chosen is None:
        typer.echo(f"Shortlist awaits review: llama review {ws.dir}")
        return
    for entry in chosen:
        pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format, force=force)
        if pkg:
            typer.echo(f"packaged: {pkg}")
        else:
            typer.echo(f"needs-review, skipped: {entry.candidate.performance_id}")


@app.command()
def find(
    query: str,
    limit: int = typer.Option(0, "--limit", help="How many shows (0 = let the query decide)"),
    auto: bool = typer.Option(False, "--auto", help="No prompts; take top-ranked"),
    run_name: str = typer.Option(None, "--run-name"),
    config_path: Path = typer.Option(None, "--config"),
):
    """One-off: find, vet, research, and package shows matching QUERY."""
    config, ia, ledger = _setup(config_path)
    name = run_name or f"{date.today().isoformat()}-{slugify(query)[:40]}"
    ws = RunWorkspace(config.root, name)
    criteria = run_interpret(ws, make_providers(config)["interpret"], query)
    count = limit or criteria.count
    _execute(config, ia, ledger, ws, criteria, count, auto, human_gate=False)


@app.command()
def run(
    run_dir: Path,
    stage: str = typer.Option(None, "--stage", help="Force re-run of one stage"),
    auto: bool = typer.Option(True, "--auto/--interactive"),
    force: bool = typer.Option(False, "--force"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Replay an existing run from its artifacts (stages skip work already done)."""
    config, ia, ledger = _setup(config_path)
    ws = RunWorkspace(config.root, run_dir.name)
    if not ws.criteria.exists():
        typer.echo(f"no criteria.json in {ws.dir}", err=True)
        raise typer.Exit(1)
    criteria = read_model(ws.criteria, Criteria)
    if stage and force:
        targets = {"search": ws.candidates, "winnow": ws.shortlist}
        if stage in targets and targets[stage].exists():
            targets[stage].unlink()
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=force and stage is None)
