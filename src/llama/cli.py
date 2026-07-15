import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import typer

from llama.artist_index import filter_artists, find_matching_artists, fmt_count, load_or_build
from llama.config import Config, load_config
from llama.ia_client import IAClient, IAError
from llama.ledger import Ledger
from llama.llm import provider_ladder
from llama.llm.provider import LLMError, TaskFailed
from llama.models import Criteria, LedgerEntry, ShortlistEntry, Show
from llama.pipeline import choose_entries, make_providers, process_show
from llama.profiles import Profile, load_profile, save_profile
from llama.setlistfm import make_client
from llama.stages.discover import run_discover
from llama.stages.interpret import run_interpret
from llama.stages.search import run_search
from llama.stages.winnow import run_winnow
from llama.status import configure_logging
from llama.util import slugify
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, read_model_list, write_artifact

VALID_STAGES = {"search", "winnow", "select", "gather", "research", "vet", "synthesize", "package"}
RUN_LEVEL_STAGES = {"search", "winnow"}
# Forcing a show-level stage also drops everything downstream of it, so a
# replay can never package artifacts derived from the pre-force state.
SHOW_STAGE_ORDER = ["select", "gather", "research", "vet", "synthesize", "package"]

app = typer.Typer(help="Live Music Archive -> radio station pipeline")
configure_logging()

profile_app = typer.Typer(help="Standing criteria profiles for recurring segments")
ledger_app = typer.Typer(help="Broadcast-history ledger")
app.add_typer(profile_app, name="profile")
app.add_typer(ledger_app, name="ledger")


def _version_callback(value: bool) -> None:
    if value:
        import llama

        typer.echo(llama.__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the llama version and exit.",
    ),
) -> None:
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
        "research": [show_ws.research, show_ws.vetting],
        "vet": [show_ws.vetting],
        "synthesize": [show_ws.dj_notes_json, show_ws.dj_notes_md],
        "package": [show_ws.package_dir / "manifest.json"],
    }[stage]


def _print_shortlist(entries: list[ShortlistEntry]) -> None:
    for e in entries:
        c = e.candidate
        typer.echo(f"{e.rank:2d}. {c.date}  {c.venue or '?':30.30s}  "
                   f"score {e.assessment.quality_score:.1f}  {e.assessment.rationale[:80]}")


def _print_artists(rows: list[dict]) -> None:
    for i, a in enumerate(rows, 1):
        years = (f"{a['year_min']}-{a['year_max']}"
                 if a.get("year_min") is not None else "?")
        typer.echo(f"{i:2d}. {a['title']:<40.40s} {a['recordings']:>6d} rec  "
                   f"{years:>9s}  {fmt_count(a['downloads']):>7s} dl")
        if a.get("reason"):
            typer.echo(f"      {a['reason']}")


def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False,
             script: bool = False) -> None:
    providers = make_providers(config)
    artists = None
    if criteria.collection is None and criteria.artist is None and criteria.soft_preferences:
        artists = run_discover(ws, providers["find_artists"], ia, criteria,
                               cache_dir=config.root / "cache",
                               min_recordings=config.artists.min_recordings,
                               min_downloads=config.artists.min_downloads,
                               force=force)
        if not artists:
            typer.echo("no matching artists found on the LMA - "
                       "try naming an artist or broadening the style", err=True)
            return
        if not auto:
            typer.echo("Matched artists:")
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
                           shortlist_size=max(12, count),
                           max_metadata_fetch=config.winnow.max_metadata_fetch, force=force)
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
    setlistfm = make_client(config)
    for entry in chosen:
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force, script=script, setlistfm=setlistfm,
                               structure_cfg=config.structure)
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
    script: bool = typer.Option(False, "--script/--no-script",
                                help="Also generate the verbatim DJ script (extra high-tier LLM call)"),
    config_path: Path = typer.Option(None, "--config"),
):
    """One-off: find, vet, research, and package shows matching QUERY."""
    config, ia, ledger = _setup(config_path)
    name = run_name or f"{date.today().isoformat()}-{slugify(query)[:40]}"
    ws = RunWorkspace(config.root, name)
    criteria = run_interpret(ws, make_providers(config)["interpret"], query)
    count = limit or criteria.count
    _execute(config, ia, ledger, ws, criteria, count, auto, human_gate=False, script=script)


@app.command()
def artists(
    query: str = typer.Argument(None, help="Natural-language artist query (omit to list by catalog size)"),
    limit: int = typer.Option(20, "--limit", help="Max artists to show"),
    min_recordings: int = typer.Option(None, "--min-recordings",
                                       help="Junk filter floor (default from [artists] config)"),
    min_downloads: int = typer.Option(None, "--min-downloads",
                                      help="Junk filter floor (default from [artists] config)"),
    all_artists: bool = typer.Option(False, "--all", help="Skip the junk filter entirely"),
    refresh: bool = typer.Option(False, "--refresh", help="Force an artist index rebuild"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Search LMA artists with a natural-language query, or list the deepest catalogs."""
    config, ia, _ = _setup(config_path)
    try:
        index = load_or_build(ia, config.root / "cache", refresh=refresh)
    except IAError as exc:
        typer.echo(f"artist index build failed: {exc}", err=True)
        raise typer.Exit(1)
    mr = min_recordings if min_recordings is not None else config.artists.min_recordings
    md = min_downloads if min_downloads is not None else config.artists.min_downloads
    pool = index if all_artists else filter_artists(index, mr, md)
    if not pool:
        typer.echo("no artists pass the current thresholds - "
                   "lower --min-recordings/--min-downloads or use --all")
        return
    if query is None:
        _print_artists(sorted(pool, key=lambda a: -a["recordings"])[:limit])
        return
    matches = find_matching_artists(provider_ladder(config, "find_artists"),
                                    pool, query, max_results=limit)
    if not matches:
        typer.echo("no matching artists - try a broader query, "
                   "lower thresholds, or --all")
        return
    _print_artists(matches)


@app.command()
def run(
    run_dir: Path,
    stage: str = typer.Option(None, "--stage", help="Force re-run of one stage"),
    auto: bool = typer.Option(True, "--auto/--interactive"),
    force: bool = typer.Option(False, "--force"),
    script: bool = typer.Option(False, "--script/--no-script",
                                help="Also generate the verbatim DJ script (extra high-tier LLM call)"),
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
    if force and stage in (None, "search") and ws.shortlist.exists():
        entries = read_model_list(ws.shortlist, ShortlistEntry)
        if any(e.approved is not None for e in entries):
            typer.echo("this rebuilds the shortlist and discards the approvals recorded on it")
            if not typer.confirm("Continue?", default=False):
                raise typer.Exit(1)
    if stage and force:
        if stage == "search":
            doomed = [ws.candidates, ws.shortlist]  # a stale shortlist would block re-winnowing
        elif stage == "winnow":
            doomed = [ws.shortlist]
        else:
            doomed = []
            shows_dir = ws.dir / "shows"
            if shows_dir.exists():
                for show_dir in sorted(shows_dir.iterdir()):
                    if not show_dir.is_dir():
                        continue
                    show_ws = ShowWorkspace(show_dir)
                    for st in SHOW_STAGE_ORDER[SHOW_STAGE_ORDER.index(stage):]:
                        doomed += _show_stage_artifacts(show_ws, st)
        for path in doomed:
            if path.exists():
                path.unlink()
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=force and stage is None,
             script=script or stage == "synthesize")


@app.command()
def review(
    run_dir: Path,
    script: bool = typer.Option(False, "--script/--no-script",
                                help="Pass --script through if you process immediately"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Human gate: approve a run's shortlist, then optionally process it."""
    config, ia, ledger = _setup(config_path)
    ws = RunWorkspace(config.root, run_dir.name)
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    _print_shortlist(entries)
    picks = typer.prompt("Approve which ranks? (comma-separated)",
                         default="", show_default=False)
    wanted = _parse_ranks(picks) & {e.rank for e in entries}
    if not wanted:
        typer.echo("no matching ranks given; shortlist unchanged")
        return
    for e in entries:
        if e.rank in wanted:
            e.approved = True   # unnamed ranks stay undecided, not rejected
    write_artifact(ws.shortlist, entries)
    typer.echo(f"approved: {sorted(wanted)}")
    if typer.confirm("Process approved shows now?", default=True):
        criteria = read_model(ws.criteria, Criteria)
        _execute(config, ia, ledger, ws, criteria, criteria.count, auto=True,
                 human_gate=False, script=script)
    else:
        typer.echo(f"next: llama run {ws.dir}")


@app.command()
def show(
    show_dir: Path,
    clear: bool = typer.Option(False, "--clear",
                               help="Overrule the hold: clear needs-review and its flags"),
):
    """Inspect one show's needs-review state (and optionally clear it)."""
    sws = ShowWorkspace(show_dir)
    if not sws.show.exists():
        typer.echo(f"no show.json in {show_dir}", err=True)
        raise typer.Exit(1)
    s = read_model(sws.show, Show)
    place = ", ".join(p for p in [s.venue, s.city] if p)
    typer.echo(f"{s.artist}  {s.date}  {place}".rstrip())
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks)")
    typer.echo(f"packaged: {'yes' if (sws.package_dir / 'manifest.json').exists() else 'no'}")
    if not s.needs_review:
        typer.echo("needs-review: no")
        return
    typer.echo("needs-review: yes")
    for f in s.review_flags:
        typer.echo(f"  - {f}")
    if clear:
        s.needs_review = False
        s.review_flags = []
        write_artifact(sws.show, s)
        typer.echo("cleared")
        typer.echo(f"next: llama run {show_dir.parent.parent}")
    else:
        typer.echo("to overrule after inspecting: llama show --clear " + str(show_dir))


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
    script: bool = typer.Option(False, "--script"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Interpret QUERY once and save it as a named standing profile."""
    config, _, _ = _setup(config_path)
    scratch = RunWorkspace(config.root, f"profile-setup-{name}")
    criteria = run_interpret(scratch, make_providers(config)["interpret"], query)
    profile = Profile(name=name, criteria=criteria, count=count, human_gate=human_gate, script=script)
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
             human_gate=profile.human_gate, script=profile.script)


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
