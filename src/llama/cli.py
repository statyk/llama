import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import typer

from llama.config import Config, load_config
from llama.ia_client import IAClient, IAError
from llama.ledger import Ledger
from llama.llm.provider import LLMError, TaskFailed
from llama.models import Criteria, LedgerEntry, ShortlistEntry
from llama.pipeline import choose_entries, make_providers, process_show
from llama.profiles import Profile, load_profile, save_profile
from llama.stages.discover import run_discover
from llama.stages.interpret import run_interpret
from llama.stages.search import run_search
from llama.stages.winnow import run_winnow
from llama.util import slugify
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, read_model_list, write_artifact

VALID_STAGES = {"search", "winnow", "select", "gather", "research", "synthesize", "package"}
RUN_LEVEL_STAGES = {"search", "winnow"}

app = typer.Typer(help="Live Music Archive -> radio station pipeline")
logging.basicConfig(level=logging.INFO, format="%(message)s")

profile_app = typer.Typer(help="Standing criteria profiles for recurring segments")
ledger_app = typer.Typer(help="Broadcast-history ledger")
app.add_typer(profile_app, name="profile")
app.add_typer(ledger_app, name="ledger")


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


def _parse_ranks(text: str) -> set[int]:
    """Ignore non-numeric tokens so junk input never tracebacks."""
    return {int(p) for p in text.split(",") if p.strip().isdigit()}


def _show_stage_artifacts(show_ws: ShowWorkspace, stage: str) -> list[Path]:
    return {
        "select": [show_ws.selection],
        "gather": [show_ws.show, show_ws.reviews],
        "research": [show_ws.research],
        "synthesize": [show_ws.dj_notes_json, show_ws.dj_notes_md],
        "package": [show_ws.package_dir / "manifest.json"],
    }[stage]


def _print_shortlist(entries: list[ShortlistEntry]) -> None:
    for e in entries:
        c = e.candidate
        typer.echo(f"{e.rank:2d}. {c.date}  {c.venue or '?':30.30s}  "
                   f"score {e.assessment.quality_score:.1f}  {e.assessment.rationale[:80]}")


def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False) -> None:
    providers = make_providers(config)
    artists = None
    if criteria.collection is None and criteria.artist is None and criteria.soft_preferences:
        artists = run_discover(ws, providers["propose_artists"], ia, criteria, force=force)
        if not artists:
            typer.echo("none of the proposed artists were found on the LMA - "
                       "try naming an artist or broadening the style", err=True)
            return
        if not auto:
            typer.echo("Proposed artists:")
            for i, a in enumerate(artists, 1):
                typer.echo(f"{i:2d}. {a.get('title') or a['identifier']}")
            picks = typer.prompt("Search which artists? (comma-separated, empty = all)",
                                 default="", show_default=False)
            wanted = _parse_ranks(picks)
            if wanted:
                pruned = [a for i, a in enumerate(artists, 1) if i in wanted]
                if not pruned:
                    typer.echo("no valid selections - keeping none; aborting run", err=True)
                    return
                artists = pruned
                write_artifact(ws.artists, artists)
    run_search(ws, ia, criteria, artists=artists, force=force)
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
            wanted = _parse_ranks(picks)
            for e in shortlist:
                e.approved = e.rank in wanted
            write_artifact(ws.shortlist, shortlist)
    chosen = choose_entries(shortlist, count, human_gate and auto)
    if chosen is None:
        typer.echo(f"Shortlist awaits review: llama review {ws.dir}")
        return
    for entry in chosen:
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format, force=force)
        except (TaskFailed, LLMError, IAError) as exc:
            if isinstance(exc, TaskFailed) and exc.raw_output:
                failure_path = ws.show_ws(entry.candidate.performance_id).dir / "llm-failure.txt"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(exc.raw_output)
            typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
            continue
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
    if stage is not None and stage not in VALID_STAGES:
        typer.echo(f"unknown stage {stage!r}; valid: {sorted(VALID_STAGES)}", err=True)
        raise typer.Exit(1)
    criteria = read_model(ws.criteria, Criteria)
    if stage and force:
        if stage in RUN_LEVEL_STAGES:
            targets = {"search": ws.candidates, "winnow": ws.shortlist}
            if targets[stage].exists():
                targets[stage].unlink()
        else:
            shows_dir = ws.dir / "shows"
            if shows_dir.exists():
                for show_dir in sorted(shows_dir.iterdir()):
                    if not show_dir.is_dir():
                        continue
                    show_ws = ShowWorkspace(show_dir)
                    for path in _show_stage_artifacts(show_ws, stage):
                        if path.exists():
                            path.unlink()
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=force and stage is None)


@app.command()
def review(
    run_dir: Path,
    config_path: Path = typer.Option(None, "--config"),
):
    """Human gate: approve/prune a run's shortlist before processing."""
    config, _, _ = _setup(config_path)
    ws = RunWorkspace(config.root, run_dir.name)
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    _print_shortlist(entries)
    picks = typer.prompt("Approve which ranks? (comma-separated)")
    wanted = _parse_ranks(picks)
    for e in entries:
        e.approved = e.rank in wanted
    write_artifact(ws.shortlist, entries)
    typer.echo(f"approved: {sorted(wanted)}")


@app.command()
def deliver(
    show_dir: Path,
    dest: Path = typer.Option(None, "--dest", help="Defaults to config delivery_path"),
    force: bool = typer.Option(False, "--force", help="Deliver even if the show is marked needs-review"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Copy a show package to the station's watched folder and record delivery."""
    import json as _json

    config, _, ledger = _setup(config_path)
    target_dir = dest or config.delivery_path
    if target_dir is None:
        typer.echo("no --dest given and no delivery_path in config", err=True)
        raise typer.Exit(1)
    show_json = show_dir / "show.json"
    if show_json.exists() and not force:
        show_data = _json.loads(show_json.read_text())
        if show_data.get("needs_review"):
            flags = ", ".join(show_data.get("review_flags", []))
            typer.echo(
                f"refusing to deliver: show is marked needs-review ({flags}); use --force to override",
                err=True,
            )
            raise typer.Exit(1)
    pkg = show_dir / "package"
    manifest = _json.loads((pkg / "manifest.json").read_text())
    out = target_dir / show_dir.name
    shutil.copytree(pkg, out, dirs_exist_ok=True)
    show = manifest["show"]
    ledger.record(LedgerEntry(
        performance_id=manifest["source"].get("performance_id", show_dir.name),
        artist=show["artist"], date=show["date"], venue=show.get("venue"),
        status="delivered", run=show_dir.parent.parent.name,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    ))
    typer.echo(f"delivered: {out}")


@profile_app.command("add")
def profile_add(
    name: str,
    query: str,
    count: int = typer.Option(1, "--count"),
    human_gate: bool = typer.Option(False, "--human-gate"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Interpret QUERY once and save it as a named standing profile."""
    config, _, _ = _setup(config_path)
    scratch = RunWorkspace(config.root, f"profile-setup-{name}")
    criteria = run_interpret(scratch, make_providers(config)["interpret"], query)
    profile = Profile(name=name, criteria=criteria, count=count, human_gate=human_gate)
    path = save_profile(config.root, profile)
    typer.echo(f"saved: {path}")


@profile_app.command("run")
def profile_run(
    name: str,
    auto: bool = typer.Option(False, "--auto"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Find and process the profile's next N shows, avoiding ledger duplicates."""
    config, ia, ledger = _setup(config_path)
    profile = load_profile(config.root, name)
    ws = RunWorkspace(config.root, f"{date.today().isoformat()}-{name}")
    write_artifact(ws.criteria, profile.criteria)
    _execute(config, ia, ledger, ws, profile.criteria, profile.count, auto,
             human_gate=profile.human_gate)


@profile_app.command("list")
def profile_list(config_path: Path = typer.Option(None, "--config")):
    config, _, _ = _setup(config_path)
    profiles_dir = config.root / "profiles"
    for p in sorted(profiles_dir.glob("*.toml")) if profiles_dir.exists() else []:
        typer.echo(p.stem)


@ledger_app.command("list")
def ledger_list(config_path: Path = typer.Option(None, "--config")):
    _, _, ledger = _setup(config_path)
    for e in ledger.entries():
        typer.echo(f"{e.recorded_at[:10]}  {e.status:9s}  {e.performance_id}  ({e.run})")


@ledger_app.command("add")
def ledger_add(
    performance_id: str,
    artist: str = typer.Option(..., "--artist"),
    show_date: str = typer.Option(..., "--date"),
    status: str = typer.Option("selected", "--status"),
    config_path: Path = typer.Option(None, "--config"),
):
    _, _, ledger = _setup(config_path)
    ledger.record(LedgerEntry(performance_id=performance_id, artist=artist, date=show_date,
                              status=status, run="manual",
                              recorded_at=datetime.now(timezone.utc).isoformat()))
    typer.echo(f"recorded: {performance_id} ({status})")


@ledger_app.command("remove")
def ledger_remove(performance_id: str, config_path: Path = typer.Option(None, "--config")):
    _, _, ledger = _setup(config_path)
    n = ledger.remove(performance_id)
    typer.echo(f"removed {n} entries")
