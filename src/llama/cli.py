import logging
import shutil
import sys
import textwrap
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import typer

from llama.artist_index import (
    filter_artists, find_matching_artists, fmt_count, load_or_build, resolve_artists,
)
from llama.config import DEFAULT_CONFIG_TOML, DEFAULT_ROOT, Config, load_config
from llama.errors import LlamaError
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
from llama.workspace import RunWorkspace, read_model, read_model_list, write_artifact

VALID_STAGES = {"search", "winnow", "select", "gather", "research", "vet", "synthesize", "package"}
RUN_LEVEL_STAGES = {"search", "winnow"}

app = typer.Typer(help="Live Music Archive -> radio station pipeline", pretty_exceptions_enable=False)
configure_logging()

profile_app = typer.Typer(help="Standing criteria profiles for recurring segments", pretty_exceptions_enable=False)
ledger_app = typer.Typer(help="Broadcast-history ledger", pretty_exceptions_enable=False)
app.add_typer(profile_app, name="profile")
app.add_typer(ledger_app, name="ledger")

config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)
app.add_typer(config_app, name="config")


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


_STATE_RANK = {"held": 0, "packaged": 1, "scripted": 2, "vetted": 3,
               "researched": 4, "gathered": 5, "selected": 6, "delivered": 7}
RECENT_DELIVERED = 5


def _parse_ranks(text: str) -> set[int]:
    """Ignore non-numeric tokens so junk input never tracebacks."""
    return {int(p) for p in text.split(",") if p.strip().isdigit()}


RATIONALE_WIDTH = 90   # wrap column for the indented rationale block
RATIONALE_LINES = 3    # default cap; --full-rationale lifts it


def _print_shortlist(entries: list[ShortlistEntry], full: bool = False) -> None:
    for i, e in enumerate(entries):
        if i:
            typer.echo()
        c = e.candidate
        typer.echo(f"{e.rank:2d}. {c.date}  {c.collection:18.18s}  {c.venue or '?':26.26s}  "
                   f"score {e.assessment.quality_score:.1f}")
        lines = textwrap.wrap(e.assessment.rationale, width=RATIONALE_WIDTH)
        if not full and len(lines) > RATIONALE_LINES:
            lines = lines[:RATIONALE_LINES]
            lines[-1] += " …"
        for ln in lines:
            typer.echo(f"      {ln}")


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
             script: bool = False, force_stage: str | None = None,
             full_rationale: bool = False) -> None:
    providers = make_providers(config)
    artists = None
    if criteria.artists:
        # Pinned roster: deterministic fan-out, no LLM matching, no prune gate.
        artists = [{"identifier": a, "title": a} for a in criteria.artists]
        write_artifact(ws.artists, artists)
        typer.echo("pinned artists: " + ", ".join(criteria.artists))
    elif criteria.collection is None and criteria.artist is None and criteria.soft_preferences:
        artists = run_discover(ws, providers["find_artists"], ia, criteria,
                               cache_dir=config.root / "cache",
                               min_recordings=config.artists.min_recordings,
                               min_downloads=config.artists.min_downloads,
                               max_artists=config.artists.max_matched,
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
    run_search(ws, ia, criteria, artists=artists, force=force,
               jerrybase_enabled=config.jerrybase.enabled)
    shortlist = run_winnow(ws, providers["score_reviews"], providers["light_research"], ia, criteria, ledger,
                           shortlist_size=max(12, count),
                           max_metadata_fetch=config.winnow.max_metadata_fetch, force=force)
    if not shortlist:
        typer.echo("No shows survived winnowing.")
        return
    _print_shortlist(shortlist, full=full_rationale)
    if not auto and all(e.approved is None for e in shortlist):
        picks = typer.prompt("Process which ranks? (comma-separated, empty = top picks)",
                             default="", show_default=False)
        if picks.strip():
            wanted = _parse_ranks(picks)
            for e in shortlist:
                e.approved = e.rank in wanted
            write_artifact(ws.shortlist, shortlist)
    chosen = choose_entries(shortlist, count, human_gate and auto,
                            artist_cap=criteria.artist_cap,
                            year_cap=criteria.year_cap)
    if chosen is None:
        typer.echo(f"Shortlist awaits review: llama review {ws.dir}")
        return
    setlistfm = make_client(config)
    for entry in chosen:
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force, script=script, setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
                               force_stage=force_stage)
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
    script: bool = typer.Option(True, "--script/--no-script",
                                help="Verbatim DJ script (high-tier LLM call), on by default; "
                                     "--no-script skips it"),
    artist_cap: float = typer.Option(None, "--artist-cap", min=0.0, max=1.0,
                                     help="Max share of the shortlist one artist may hold "
                                          "(1.0 = pure best-first; default 1/3)"),
    min_score: float = typer.Option(None, "--min-score", min=0.0, max=10.0,
                                    help="Quality floor (0-10) on the LLM review score; "
                                         "lower-scored shows never shortlist (default 6.0)"),
    year_cap: float = typer.Option(None, "--year-cap", min=0.0, max=1.0,
                                   help="Max share of the shortlist one year may hold "
                                        "(default 1.0 = scores decide the year mix; "
                                        "set low for an era tour)"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
    config_path: Path = typer.Option(None, "--config"),
):
    """One-off: find, vet, research, and package shows matching QUERY."""
    if artist_cap == 0.0 or year_cap == 0.0:
        typer.echo("--artist-cap/--year-cap must be above 0 "
                   "(a tiny value forces strict rotation; 1.0 disables the cap)", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup(config_path)
    name = run_name or f"{date.today().isoformat()}-{slugify(query)[:40]}"
    ws = RunWorkspace(config.root, name)
    criteria = run_interpret(ws, make_providers(config)["interpret"], query)
    # Stamp explicit flags into the run's criteria so replays behave the same.
    updates = {}
    if limit:
        updates["count"] = limit
    if not script:
        updates["script"] = False
    if artist_cap is not None:
        updates["artist_cap"] = artist_cap
    if min_score is not None:
        updates["min_quality_score"] = min_score
    if year_cap is not None:
        updates["year_cap"] = year_cap
    if updates:
        criteria = criteria.model_copy(update=updates)
        write_artifact(ws.criteria, criteria)
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, script=script, full_rationale=full_rationale)


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
    run_name: str = typer.Argument(..., help="Run name, unique substring, or path"),
    stage: str = typer.Option(None, "--stage", help="Force re-run of one stage"),
    auto: bool = typer.Option(True, "--auto/--interactive"),
    force: bool = typer.Option(False, "--force"),
    script: bool = typer.Option(None, "--script/--no-script",
                                help="Override the run's persisted script setting"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Replay an existing run from its artifacts (stages skip work already done)."""
    config, ia, ledger = _setup(config_path)
    ws = _resolve_run_or_exit(config, run_name)
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
    if stage and force and stage in RUN_LEVEL_STAGES:
        # a stale shortlist would block re-winnowing after a fresh search
        doomed = [ws.candidates, ws.shortlist] if stage == "search" else [ws.shortlist]
        for path in doomed:
            if path.exists():
                path.unlink()
    # Show-level stage forcing is applied per chosen show at process time
    # (force_stage), never as a bulk sweep: shows that are not reprocessed
    # this run must keep their artifacts and packages intact.
    effective_script = criteria.script if script is None else script
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=force and stage is None,
             script=effective_script or stage == "synthesize",
             force_stage=stage if (force and stage not in (None, *RUN_LEVEL_STAGES)) else None,
             full_rationale=full_rationale)


@app.command()
def review(
    run_name: str = typer.Argument(..., help="Run name, unique substring, or path"),
    script: bool = typer.Option(None, "--script/--no-script",
                                help="Override the run's persisted script setting "
                                     "if you process immediately"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Human gate: approve a run's shortlist, then optionally process it."""
    config, ia, ledger = _setup(config_path)
    ws = _resolve_run_or_exit(config, run_name)
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    _print_shortlist(entries, full=full_rationale)
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
                 human_gate=False,
                 script=criteria.script if script is None else script,
                 full_rationale=full_rationale)
    else:
        typer.echo(f"next: llama run {ws.dir}")


def _resolve_run_or_exit(config, name: str) -> RunWorkspace:
    from llama.catalog import CatalogError, resolve_run

    try:
        return RunWorkspace(config.root, resolve_run(config.root, name))
    except CatalogError as err:
        typer.echo(str(err), err=True)
        for m in err.matches:
            typer.echo(f"  {m}", err=True)
        raise typer.Exit(1)


def _resolve_show_or_exit(config, ledger, name: str):
    from llama.catalog import CatalogError, resolve_show

    try:
        return resolve_show(config.root, ledger, name)
    except CatalogError as err:
        typer.echo(str(err), err=True)
        for m in err.matches:
            typer.echo(f"  {m}", err=True)
        raise typer.Exit(1)


@app.command()
def show(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    clear: bool = typer.Option(False, "--clear",
                               help="Overrule the hold: clear needs-review and its flags"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Inspect one show: state, stage artifacts, needs-review flags."""
    config, _, ledger = _setup(config_path)
    entry = _resolve_show_or_exit(config, ledger, name)
    sws = entry.ws
    if not sws.show.exists():
        typer.echo(f"no show.json in {sws.dir} (state: {entry.state})", err=True)
        raise typer.Exit(1)
    s = read_model(sws.show, Show)
    place = ", ".join(p for p in [s.venue, s.city] if p)
    if s.venue_source == "jerrybase" and place:
        place = f"{place} (venue from jerrybase)"
    date_str = s.date
    if s.date_source == "research" and s.item_date:
        date_str = f"{s.date} (item date {s.item_date}, corrected via research)"
    typer.echo(f"{s.artist}  {date_str}  {place}".rstrip())
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks)")
    typer.echo(f"state: {entry.state}   path: {sws.dir}")
    typer.echo("stages:")
    artifacts = [("selection.json", sws.selection), ("show.json", sws.show),
                 ("research.md", sws.research), ("vetting.json", sws.vetting),
                 ("dj-notes.json", sws.dj_notes_json),
                 ("package/manifest.json", sws.package_dir / "manifest.json")]
    now = datetime.now(timezone.utc).timestamp()
    for label, path in artifacts:
        if path.exists():
            age_days = (now - path.stat().st_mtime) / 86400
            typer.echo(f"  {label:22s} {age_days:5.1f}d old")
        else:
            typer.echo(f"  {label:22s} missing")
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
        typer.echo(f"next: llama redo {entry.slug} --from package")
    else:
        typer.echo(f"to overrule after inspecting: llama show --clear {entry.slug}")


@app.command()
def deliver(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    dest: Path = typer.Option(None, "--dest", help="Defaults to config delivery_path"),
    force: bool = typer.Option(False, "--force", help="Deliver even if the show is marked needs-review"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Copy a show package to the station's watched folder and record delivery."""
    import json as _json

    config, _, ledger = _setup(config_path)
    entry = _resolve_show_or_exit(config, ledger, name)
    show_dir = entry.ws.dir
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
    run_name = entry.provenance.run if entry.provenance else "unknown"
    ledger.record(LedgerEntry(
        performance_id=manifest["source"].get("performance_id", show_dir.name),
        artist=show["artist"], date=show["date"], venue=show.get("venue"),
        status="delivered", run=run_name,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    ))
    typer.echo(f"delivered: {out}")


@app.command()
def redo(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    from_stage: str = typer.Option(..., "--from",
                                   help="Stage to re-run from: select|gather|research|vet|synthesize|package"),
    with_research: bool = typer.Option(False, "--with-research",
                                       help="Also drop research.md (kept by default)"),
    script: bool = typer.Option(None, "--script/--no-script",
                                help="Override the script setting recorded at process time"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Re-run one show's pipeline from a stage; earlier artifacts are reused."""
    from llama.models import QualityAssessment
    from llama.workspace import drop_stage_artifacts

    show_stages = VALID_STAGES - RUN_LEVEL_STAGES
    if from_stage not in show_stages:
        typer.echo(f"unknown stage {from_stage!r}; valid: {sorted(show_stages)}", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup(config_path)
    entry = _resolve_show_or_exit(config, ledger, name)
    if entry.provenance is None:
        typer.echo(f"no provenance.json in {entry.ws.dir} - "
                   "reprocess it via its run first", err=True)
        raise typer.Exit(1)
    prov = entry.provenance
    keep_research = not with_research and from_stage in ("select", "gather")
    drop_stage_artifacts(entry.ws, from_stage, keep_research=keep_research)
    # Keep the winnow assessment (quality_score + recording_complaints) so
    # select-recording still avoids complained-about recordings; override only
    # the rationale so the dossier round-trip stays stable (it already carries
    # the external-reputation suffix). Fall back to a zero stub for pre-fix
    # provenance.json files that predate the assessment field.
    assessment = (prov.assessment.model_copy(update={"rationale": prov.dossier})
                  if prov.assessment is not None
                  else QualityAssessment(performance_id=prov.performance_id,
                                         quality_score=0.0, rationale=prov.dossier))
    shortlist_entry = ShortlistEntry(
        rank=1, candidate=prov.candidate, assessment=assessment)
    ws = RunWorkspace(config.root, prov.run)
    effective_script = prov.script if script is None else script
    pkg = process_show(ws, ia, ledger, shortlist_entry, make_providers(config),
                       prov.run, config.audio_format, script=effective_script,
                       setlistfm=make_client(config), structure_cfg=config.structure,
                       jerrybase_enabled=config.jerrybase.enabled,
                       selection_cfg=config.selection)
    if pkg:
        typer.echo(f"packaged: {pkg}")
    else:
        typer.echo(f"needs-review, skipped: {prov.performance_id}")


@app.command()
def status(
    held: bool = typer.Option(False, "--held", help="Only shows held for review"),
    packaged: bool = typer.Option(False, "--packaged", help="Only packaged, undelivered shows"),
    run: str = typer.Option(None, "--run", help="Only shows processed by this run"),
    artist: str = typer.Option(None, "--artist", help="Substring filter on artist"),
    all_shows: bool = typer.Option(False, "--all", help="Include all delivered shows"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Triage view: every show and its state, held-for-review first."""
    import json as _json

    from llama.catalog import iter_shows

    config, _, ledger = _setup(config_path)
    entries = iter_shows(config.root, ledger)
    if held:
        entries = [e for e in entries if e.state == "held"]
    if packaged:
        entries = [e for e in entries if e.state == "packaged"]
    if run:
        entries = [e for e in entries if e.provenance and e.provenance.run == run]
    if artist:
        entries = [e for e in entries if artist.lower() in e.artist.lower()]
    entries.sort(key=lambda e: (_STATE_RANK[e.state], e.slug))
    if not all_shows and not (held or packaged):
        recorded: dict[str, str] = {}
        for le in ledger.entries():
            if le.status == "delivered":
                slug = slugify(le.performance_id)
                recorded[slug] = max(le.recorded_at, recorded.get(slug, ""))
        delivered = sorted((e for e in entries if e.state == "delivered"),
                           key=lambda e: recorded.get(e.slug, ""))
        keep = {e.slug for e in delivered[-RECENT_DELIVERED:]}
        entries = [e for e in entries if e.state != "delivered" or e.slug in keep]
    if as_json:
        typer.echo(_json.dumps([{
            "slug": e.slug, "state": e.state, "artist": e.artist, "date": e.date,
            "run": e.provenance.run if e.provenance else None,
            "flags": e.flags, "path": str(e.ws.dir),
        } for e in entries], indent=2))
        return
    if not entries:
        typer.echo("no shows")
        return
    for e in entries:
        run_name = e.provenance.run if e.provenance else "?"
        typer.echo(f"{e.slug:42.42s} {e.state:10s} {e.artist:20.20s} {e.date:10s} {run_name}")
        for f in e.flags:
            typer.echo(f"      - {f}")


@app.command()
def runs(config_path: Path = typer.Option(None, "--config")):
    """List runs with their criteria and show-state counts."""
    from collections import Counter

    from llama.catalog import iter_shows

    config, _, ledger = _setup(config_path)
    by_run: dict[str, Counter] = {}
    for e in iter_shows(config.root, ledger):
        if e.provenance:
            by_run.setdefault(e.provenance.run, Counter())[e.state] += 1
    runs_dir = config.root / "runs"
    run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.is_dir() else []
    if not run_dirs:
        typer.echo("no runs")
        return
    for d in run_dirs:
        query = ""
        if (d / "criteria.json").exists():
            query = read_model(RunWorkspace(config.root, d.name).criteria, Criteria).query
        counts = by_run.get(d.name, Counter())
        summary = "  ".join(f"{s} {n}" for s, n in sorted(counts.items())) or "no shows"
        typer.echo(f"{d.name:34.34s} {summary:40.40s} {query:40.40s}")


@config_app.command("init")
def config_init(
    stdout: bool = typer.Option(False, "--stdout",
                                help="Print the default config instead of writing a file"),
    config_path: Path = typer.Option(None, "--config",
                                     help="Target file (default ~/.llama/config.toml)"),
):
    """Seed a config file with the baked-in defaults, fully commented."""
    if stdout:
        typer.echo(DEFAULT_CONFIG_TOML, nl=False)
        return
    target = config_path or DEFAULT_ROOT / "config.toml"
    if target.exists():
        typer.echo(f"{target} already exists - not overwriting "
                   "(delete it first if you mean to reseed)", err=True)
        raise typer.Exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML)
    typer.echo(f"wrote {target}")
    typer.echo("note: config values replace built-in defaults (no merging); "
               "the defaults are written out so additive edits keep them")


@profile_app.command("add")
def profile_add(
    name: str,
    query: str,
    count: int = typer.Option(1, "--count"),
    human_gate: bool = typer.Option(False, "--human-gate"),
    script: bool = typer.Option(True, "--script/--no-script"),
    artist_cap: float = typer.Option(None, "--artist-cap", min=0.0, max=1.0,
                                     help="Max share of this profile's shortlist one artist "
                                          "may hold (1.0 = pure best-first; default 1/3)"),
    min_score: float = typer.Option(None, "--min-score", min=0.0, max=10.0,
                                    help="Quality floor (0-10) on the LLM review score; "
                                         "lower-scored shows never shortlist (default 6.0)"),
    year_cap: float = typer.Option(None, "--year-cap", min=0.0, max=1.0,
                                   help="Max share of this profile's shortlist one year "
                                        "may hold (default 1.0 = scores decide; set low "
                                        "for an era tour)"),
    artists: str = typer.Option(None, "--artists",
                                help="Pin the artist roster (comma-separated names); runs skip "
                                     "the LLM matcher and search exactly these"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Interpret QUERY once and save it as a named standing profile."""
    if artist_cap == 0.0 or year_cap == 0.0:
        typer.echo("--artist-cap/--year-cap must be above 0 "
                   "(a tiny value forces strict rotation; 1.0 disables the cap)", err=True)
        raise typer.Exit(1)
    config, ia, _ = _setup(config_path)
    scratch = RunWorkspace(config.root, f"profile-setup-{name}")
    criteria = run_interpret(scratch, make_providers(config)["interpret"], query)
    updates = {}
    if artist_cap is not None:
        updates["artist_cap"] = artist_cap
    if min_score is not None:
        updates["min_quality_score"] = min_score
    if year_cap is not None:
        updates["year_cap"] = year_cap
    if artists:
        names = [n.strip() for n in artists.split(",") if n.strip()]
        index = load_or_build(ia, config.root / "cache")
        try:
            resolved = resolve_artists(index, names)
        except ValueError as e:
            typer.echo(f"cannot pin artists: {e}", err=True)
            raise typer.Exit(1)
        updates["artists"] = [a["identifier"] for a in resolved]
        typer.echo("pinned: " + ", ".join(f"{a['title']} ({a['identifier']})" for a in resolved))
    if updates:
        criteria = criteria.model_copy(update=updates)
    profile = Profile(name=name, criteria=criteria, count=count, human_gate=human_gate, script=script)
    path = save_profile(config.root, profile)
    typer.echo(f"saved: {path}")


@profile_app.command("run")
def profile_run(
    name: str,
    auto: bool = typer.Option(False, "--auto"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Find and process the profile's next N shows, avoiding ledger duplicates."""
    config, ia, ledger = _setup(config_path)
    profile = load_profile(config.root, name)
    ws = RunWorkspace(config.root, f"{date.today().isoformat()}-{name}")
    # Stamp count and script into the run's criteria: a later `llama run` on
    # this dir must behave like the profile, not like the interpreted defaults.
    criteria = profile.criteria.model_copy(update={"count": profile.count,
                                                   "script": profile.script})
    write_artifact(ws.criteria, criteria)
    _execute(config, ia, ledger, ws, criteria, profile.count, auto,
             human_gate=profile.human_gate, script=profile.script,
             full_rationale=full_rationale)


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


def run() -> None:
    """CLI entry point with a single error boundary.

    Expected, user-actionable failures (`llama.errors.LlamaError`) print a clean
    `error: <message>` plus any indented details and exit 1. `KeyboardInterrupt`
    exits 130 quietly. Any other exception is a bug: we print a plain traceback
    ourselves and exit 1 — printing it here (rather than letting it propagate)
    suppresses the frozen bootloader's `Failed to execute script` line.
    `SystemExit`/`typer.Exit` from commands pass through untouched.
    """
    try:
        app()
    except LlamaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in exc.details:
            print(f"  {detail}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
