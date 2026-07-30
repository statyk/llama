import shutil
import sys
import tempfile
import textwrap
import traceback
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

import typer
from typer.core import TyperGroup

from herder import HerderError, TaskFailed, provider_ladder
from llama.artist_index import (
    filter_artists, find_matching_artists, fmt_count, load_or_build, resolve_artists,
)
from llama.catalog import library_performance_ids
from llama.cli_select import ShowState
from llama.config import DEFAULT_CONFIG_TOML, DEFAULT_ROOT, Config, load_config
from llama.errors import LlamaError
from llama.ia_client import IAClient, IAError
from llama.ledger import Ledger
from llama.locks import Locked, file_lock
from llama.models import Criteria, LedgerEntry, ShortlistEntry, Show
from llama.pipeline import choose_entries, make_providers, process_show
from llama.presenters import (
    Presenter, PresenterError, delete_presenter, list_presenters, load_presenter, save_presenter,
)
from llama.profiles import (
    Profile, ProfileError, delete_profile, list_profiles, load_profile, save_profile,
)
from llama.sessions import (STATE_AWAITING, STATE_INCOMPLETE,
                            attention_sessions, mark_awaiting, mark_complete,
                            session_state)
from llama.setlistfm import make_client
from llama.stages.discover import run_discover
from llama.stages.interpret import run_interpret
from llama.stages.search import run_search
from llama.stages.winnow import run_winnow
from llama.status import configure_logging
from llama.tts.provider import SpeechError
from llama.util import parse_performance_id, slugify
from llama.workspace import (RunWorkspace, SHOW_STAGE_ORDER, claim_run_dir,
                             read_model, read_model_list, write_artifact)

VALID_STAGES = {"search", "winnow", "select", "gather", "research", "vet", "brief", "package"}
RUN_LEVEL_STAGES = {"search", "winnow"}

_COMMAND_ORDER = ["get", "artists", "status", "show", "pipeline",
                  "triage", "fix", "redo", "deliver", "rm",
                  "suppress", "unsuppress", "run", "profile", "presenter",
                  "history", "config"]


class OrderedPanelGroup(TyperGroup):
    def list_commands(self, ctx):
        cmds = super().list_commands(ctx)
        return sorted(cmds, key=lambda n: (_COMMAND_ORDER.index(n)
                                           if n in _COMMAND_ORDER else len(_COMMAND_ORDER)))


app = typer.Typer(help="Live Music Archive -> radio station pipeline",
                  pretty_exceptions_enable=False, cls=OrderedPanelGroup)
configure_logging()

profile_app = typer.Typer(help="Standing criteria profiles for recurring segments", pretty_exceptions_enable=False)
history_app = typer.Typer(
    help="Broadcast history — dispositions for shows no longer on disk.",
    pretty_exceptions_enable=False)
app.add_typer(profile_app, name="profile", rich_help_panel="Sessions & config")
app.add_typer(history_app, name="history", rich_help_panel="Sessions & config")

config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)
app.add_typer(config_app, name="config", rich_help_panel="Sessions & config")

presenter_app = typer.Typer(help="On-air hosts (presenters/<id>.toml)",
                            pretty_exceptions_enable=False)
app.add_typer(presenter_app, name="presenter", rich_help_panel="Sessions & config")

run_app = typer.Typer(
    help="Acquisition sessions — approve, resume, list, or discard.",
    pretty_exceptions_enable=False)
app.add_typer(run_app, name="run", rich_help_panel="Sessions & config")


def _version_callback(value: bool) -> None:
    if value:
        import llama

        typer.echo(llama.__version__)
        raise typer.Exit()


_config_path: Path | None = None


@app.callback()
def main(
    config: Path = typer.Option(
        None,
        "--config",
        help="Config file (default ~/.llama/config.toml)",
    ),
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the llama version and exit.",
    ),
) -> None:
    """Find, vet, research, and package LMA concerts for broadcast."""
    global _config_path
    _config_path = config


def _setup() -> tuple[Config, IAClient, Ledger]:
    config = load_config(_config_path)
    ia = IAClient(config.root / "cache")
    ledger = Ledger(config.root / "ledger.jsonl")
    return config, ia, ledger


_STATE_RANK = {"held": 0, "packaged": 1, "briefed": 2, "vetted": 3,
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
             force_stage: str | None = None,
             full_rationale: bool = False, plan: bool = False) -> None:
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
                    mark_complete(ws, "no valid selections - keeping none; aborting run")
                    return
                artists = pruned
                write_artifact(ws.artists, artists)
    run_search(ws, ia, criteria, artists=artists, force=force,
               jerrybase_enabled=config.jerrybase.enabled)
    shortlist = run_winnow(ws, providers["score_reviews"], providers["light_research"], ia, criteria, ledger,
                           library_ids=library_performance_ids(config.root),
                           shortlist_size=max(12, count),
                           max_metadata_fetch=config.winnow.max_metadata_fetch, force=force)
    if not shortlist:
        typer.echo("No shows survived winnowing.")
        mark_complete(ws, "no shows survived winnowing")
        return
    _print_shortlist(shortlist, full=full_rationale)
    if plan:
        mark_awaiting(ws)
        typer.echo("shortlist ready — nothing processed.")
        typer.echo(f"to approve & process:  llama run approve {ws.name}")
        typer.echo(f"to discard:            llama run rm {ws.name}")
        return
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
        mark_awaiting(ws)
        typer.echo(f"Shortlist awaits review: llama run approve {ws.name}")
        return
    setlistfm = make_client(config)
    packaged = held = failed = 0

    def _process(entry):
        nonlocal packaged, held, failed
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force,
                               setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
                               force_stage=force_stage, profile=criteria.profile)
        except (TaskFailed, HerderError, IAError, SpeechError) as exc:
            if isinstance(exc, TaskFailed) and exc.raw_output:
                failure_path = ws.show_ws(entry.candidate.performance_id).dir / "llm-failure.txt"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(exc.raw_output)
            typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
            failed += 1
            return
        if pkg:
            typer.echo(f"packaged: {pkg}")
            packaged += 1
        else:
            typer.echo(f"needs-review, skipped: {entry.candidate.performance_id}")
            held += 1

    deferred = []
    for entry in chosen:
        lock_path = ws.show_ws(entry.candidate.performance_id).lock
        try:
            with file_lock(lock_path, blocking=False):
                _process(entry)
        except Locked:
            deferred.append(entry)                 # another run is building it
    for entry in deferred:                          # come back and wait
        with file_lock(ws.show_ws(entry.candidate.performance_id).lock):
            _process(entry)
    parts = []
    if packaged:
        parts.append(f"{packaged} packaged")
    if held:
        parts.append(f"{held} held")
    if failed:
        parts.append(f"{failed} failed")
    mark_complete(ws, ", ".join(parts) if parts else None)


def _get_query(config, ia, ledger, query: str, limit: int, auto: bool, plan: bool,
              name: str | None,
              artist_cap: float | None, min_score: float | None, year_cap: float | None,
              full_rationale: bool) -> None:
    """Query mode: today's `find` verbatim (interpret -> stamp explicit flags
    into criteria for replay -> `_execute`)."""
    if artist_cap == 0.0 or year_cap == 0.0:
        typer.echo("--artist-cap/--year-cap must be above 0 "
                   "(a tiny value forces strict rotation; 1.0 disables the cap)", err=True)
        raise typer.Exit(1)
    run_name = name or claim_run_dir(config.root,
                                     f"{date.today().isoformat()}-{slugify(query)[:40]}")
    ws = RunWorkspace(config.root, run_name)
    criteria = run_interpret(ws, make_providers(config)["interpret"], query)
    # Stamp explicit flags into the run's criteria so replays behave the same.
    updates = {}
    if limit:
        updates["count"] = limit
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
             human_gate=False,
             full_rationale=full_rationale, plan=plan)


def _get_profile(config, ia, ledger, name: str, auto: bool, plan: bool,
                 full_rationale: bool) -> None:
    """Profile mode: today's `profile run` verbatim (load profile -> stamp
    count into the run's criteria -> `_execute`)."""
    profile = load_profile(config.root, name)
    ws = RunWorkspace(config.root, claim_run_dir(config.root,
                                                 f"{date.today().isoformat()}-{name}"))
    # Stamp count into the run's criteria: a later `llama run` on this dir
    # must behave like the profile, not the defaults.
    criteria = profile.criteria.model_copy(update={"count": profile.count,
                                                   "profile": name})
    write_artifact(ws.criteria, criteria)
    _execute(config, ia, ledger, ws, criteria, profile.count, auto,
             human_gate=profile.human_gate,
             full_rationale=full_rationale, plan=plan)


@app.command(rich_help_panel="Acquire",
             short_help="Find, vet, research & package shows: a query or a standing --profile.")
def get(
    query: str = typer.Argument(
        None, help="Natural-language query (one-off); give this OR --profile, not both"),
    profile: str = typer.Option(
        None, "--profile", help="Standing profile name (recurring segment) instead of a query"),
    limit: int = typer.Option(0, "--limit",
                              help="How many shows (0 = let the query decide); query mode only"),
    auto: bool = typer.Option(False, "--auto", help="No prompts; take top-ranked"),
    plan: bool = typer.Option(
        False, "--plan",
        help="Stop after the shortlist prints and park the session awaiting "
             "approval; nothing is processed (beats --auto)"),
    name: str = typer.Option(None, "--name",
                             help="Session id override (auto-unique otherwise); query mode only"),
    artist_cap: float = typer.Option(None, "--artist-cap", min=0.0, max=1.0,
                                     help="Max share of the shortlist one artist may hold "
                                          "(1.0 = pure best-first; default 1/3); query mode only"),
    min_score: float = typer.Option(None, "--min-score", min=0.0, max=10.0,
                                    help="Quality floor (0-10) on the LLM review score; "
                                         "lower-scored shows never shortlist (default 6.0); "
                                         "query mode only"),
    year_cap: float = typer.Option(None, "--year-cap", min=0.0, max=1.0,
                                   help="Max share of the shortlist one year may hold "
                                        "(default 1.0 = scores decide the year mix; "
                                        "set low for an era tour); query mode only"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
):
    """Acquire: find, vet, research, and package shows -- one-off (QUERY) or
    a standing profile (--profile NAME). --plan stops after the shortlist
    prints and parks the session for `llama run approve`/`llama run rm`
    instead of processing it."""
    if bool(query) == bool(profile):
        typer.echo("give exactly one of QUERY or --profile", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup()
    if profile is not None:
        given = []
        if limit:
            given.append("--limit")
        if name is not None:
            given.append("--name")
        if artist_cap is not None:
            given.append("--artist-cap")
        if min_score is not None:
            given.append("--min-score")
        if year_cap is not None:
            given.append("--year-cap")
        if given:
            typer.echo(f"set these on the profile: {', '.join(given)}", err=True)
            raise typer.Exit(1)
        _get_profile(config, ia, ledger, profile, auto, plan, full_rationale)
        return
    _get_query(config, ia, ledger, query, limit, auto, plan, name,
              artist_cap, min_score, year_cap, full_rationale)


@app.command(rich_help_panel="Acquire",
             short_help="Search LMA artists, or list the deepest catalogs.")
def artists(
    query: str = typer.Argument(None, help="Natural-language artist query (omit to list by catalog size)"),
    limit: int = typer.Option(20, "--limit", help="Max artists to show"),
    min_recordings: int = typer.Option(None, "--min-recordings",
                                       help="Junk filter floor (default from [artists] config)"),
    min_downloads: int = typer.Option(None, "--min-downloads",
                                      help="Junk filter floor (default from [artists] config)"),
    include_junk: bool = typer.Option(False, "--include-junk", help="Skip the junk filter entirely"),
    refresh: bool = typer.Option(False, "--refresh", help="Force an artist index rebuild"),
):
    """Search LMA artists with a natural-language query, or list the deepest catalogs."""
    config, ia, _ = _setup()
    index = load_or_build(ia, config.root / "cache", refresh=refresh)
    mr = min_recordings if min_recordings is not None else config.artists.min_recordings
    md = min_downloads if min_downloads is not None else config.artists.min_downloads
    pool = index if include_junk else filter_artists(index, mr, md)
    if not pool:
        typer.echo("no artists pass the current thresholds - "
                   "lower --min-recordings/--min-downloads or use --include-junk")
        return
    if query is None:
        _print_artists(sorted(pool, key=lambda a: -a["recordings"])[:limit])
        return
    matches = find_matching_artists(provider_ladder(config.llm_settings(), "find_artists"),
                                    pool, query, max_results=limit)
    if not matches:
        typer.echo("no matching artists - try a broader query, "
                   "lower thresholds, or --include-junk")
        return
    _print_artists(matches)


_RUN_LIST_HEADER = "SESSION                              STATE               AGE   CRITERIA"


def _humanize_age(updated_at: str) -> str:
    """`3h`/`2d`-style age from an ISO timestamp (spec §4)."""
    then = datetime.fromisoformat(updated_at)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = max((datetime.now(timezone.utc) - then).total_seconds(), 0)
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _session_criteria_str(s) -> str:
    """`profile: <name>` when the session came from a profile, else the
    query quoted and truncated to 40 chars."""
    if s.profile:
        return f"profile: {s.profile}"
    return f'"{s.query:.40s}"'


def _print_sessions(sessions) -> None:
    if not sessions:
        typer.echo("no sessions need attention")
        return
    typer.echo(_RUN_LIST_HEADER)
    for s in sessions:
        label = _ATTENTION_LABELS.get(s.state, s.state)
        age = _humanize_age(s.updated_at)
        typer.echo(f"{s.id:<36} {label:<18} {age:>4}  {_session_criteria_str(s)}")


@run_app.command("list")
def run_list(
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """List sessions awaiting approval or incomplete (the attention-list);
    complete sessions never show here."""
    import json as _json

    config, _, _ = _setup()
    sessions = attention_sessions(config.root)
    if as_json:
        typer.echo(_json.dumps([_session_json(s) for s in sessions], indent=2))
        return
    _print_sessions(sessions)


@run_app.command("approve")
def run_approve(
    session: str = typer.Argument(..., help="Session id, unique substring, or path"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
):
    """Gate 1: show a session's persisted shortlist, approve ranks, then
    optionally process it now."""
    config, ia, ledger = _setup()
    ws = _resolve_run(config, session)
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
                 full_rationale=full_rationale)
    else:
        typer.echo(f"next: llama run resume {ws.name}")


@run_app.command("resume")
def run_resume(
    session: str = typer.Argument(..., help="Session id, unique substring, or path"),
    auto: bool = typer.Option(True, "--auto/--interactive"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
):
    """Resume a crashed or incomplete session from its artifacts (stages
    skip work already done). To force a stage re-run (run-wide or per-show),
    use `llama redo --run`."""
    config, ia, ledger = _setup()
    ws = _resolve_run(config, session)
    if not ws.criteria.exists():
        typer.echo(f"no criteria.json in {ws.dir}", err=True)
        raise typer.Exit(1)
    criteria = read_model(ws.criteria, Criteria)
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=False,
             force_stage=None,
             full_rationale=full_rationale)


@run_app.command("rm")
def run_rm(
    session: str = typer.Argument(..., help="Session id, unique substring, or path"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
):
    """Discard a session directory. Shows it already processed are untouched
    (they live in shows/ and carry provenance) -- sessions have no ledger
    history of their own."""
    config, _, _ = _setup()
    ws = _resolve_run(config, session)
    state = session_state(ws.dir)
    if not yes:
        typer.echo(f"session {ws.name}: {state}")
        if not typer.confirm("Proceed?", default=False):
            return
    shutil.rmtree(ws.dir)
    typer.echo(f"removed session {ws.name}")


def _resolve_run(config, name: str) -> RunWorkspace:
    from llama.catalog import resolve_run

    return RunWorkspace(config.root, resolve_run(config.root, name))


def _resolve_show(config, ledger, name: str):
    from llama.catalog import resolve_show

    return resolve_show(config.root, ledger, name)


_UNSET = object()


def _edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(), narration=None,
                    venue=_UNSET, city=_UNSET, date=_UNSET, set_titles=None,
                    clear_titles=(), set_breaks=_UNSET, clear_set_breaks=False):
    from llama.workspace import read_overrides

    ov = read_overrides(show_ws)
    exclude = [f for f in ov.exclude if f not in set(rm_exclude)]
    for f in add_exclude:
        if f not in exclude:
            exclude.append(f)
    titles = dict(ov.titles)
    for n in clear_titles:
        titles.pop(int(n), None)
    for n, t in (set_titles or {}).items():
        titles[int(n)] = t
    data = ov.model_copy(update={
        "exclude": exclude,
        "narration": narration or ov.narration,
        "titles": titles,
    })
    if venue is not _UNSET:
        data = data.model_copy(update={"venue": venue})
    if city is not _UNSET:
        data = data.model_copy(update={"city": city})
    if date is not _UNSET:
        data = data.model_copy(update={"date": date})
    if clear_set_breaks:
        data = data.model_copy(update={"set_breaks": None})
    elif set_breaks is not _UNSET:
        data = data.model_copy(update={"set_breaks": set_breaks})
    write_artifact(show_ws.overrides, data)
    return data


def _resolve_exclude_tokens(show_ws, tokens) -> list[str]:
    """Expand comma groups and map all-digit tokens to that track's filename
    (via show.json). Non-numeric tokens pass through as filenames."""
    parts = [p.strip() for tok in tokens for p in str(tok).split(",") if p.strip()]
    if not any(p.isdigit() for p in parts):
        return parts
    if not show_ws.show.exists():
        raise LlamaError("resolving a track number needs show.json; reference the file by name instead")
    tracks = read_model(show_ws.show, Show).tracks
    by_index = {t.index: t.filename for t in tracks}
    out = []
    for p in parts:
        if p.isdigit():
            n = int(p)
            if n not in by_index:
                raise LlamaError(f"no track {n} (show has {len(tracks)} tracks)")
            out.append(by_index[n])
        else:
            out.append(p)
    return out


def _clear_hold(show_ws):
    s = read_model(show_ws.show, Show)
    s.needs_review = False
    s.review_flags = []
    write_artifact(show_ws.show, s)


def _fmt_dur(sec) -> str:
    if not sec:
        return "?"
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def _format_tracks(show) -> list[str]:
    lines = ["tracks:"]
    for t in show.tracks:
        title = t.title if t.title_source != "unresolved" else "(unknown)"
        # duration before filename so a long filename can print in full without
        # misaligning the numeric column.
        lines.append(f"  {t.index:2d}. set {t.set:6.6s} {title:28.28s} "
                     f"{t.title_source:10.10s} {_fmt_dur(t.duration_sec):>6s}  {t.filename}")
    return lines


def _pick_excludes(show) -> list[str]:
    for line in _format_tracks(show):
        typer.echo(line)
    picks = _parse_ranks(typer.prompt("exclude which track numbers? (comma-separated, empty = none)",
                                      default="", show_default=False))
    return [t.filename for t in show.tracks if t.index in picks]


def _print_recording_info(ws) -> None:
    """Archive URL + considered-recordings block (spec §10) — extracted once
    so the interactive resolve header (`show`/`triage`) and, later, `show`'s
    own inspection block (Task 4's `_print_recording_info` consumer) share the
    identical formatter."""
    from llama.catalog import recording_info

    info = recording_info(ws)
    if info is None:
        return
    typer.echo(f"  {info.url}")
    if info.considered:
        typer.echo("considered:")
        for c in info.considered:
            typer.echo(f"  {c.identifier:<44} {c.score:.1f}")


RESOLVE_PROMPT = "[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip / [q]uit"


def _metadata_editor(entry) -> bool:
    """The `[m]etadata` mini-editor: sequential prompts for the gather-consumed
    override fields, each defaulting to (and so, on bare Enter, keeping) the
    current effective value. Validation mirrors `fix`'s flags. Returns True
    iff any field actually changed (and the overrides were written); False
    means nothing changed, so the caller should return to the prompt rather
    than redo anything."""
    from llama.workspace import read_overrides

    sws = entry.ws
    s = read_model(sws.show, Show)
    ov = read_overrides(sws)

    cur_venue = ov.venue if ov.venue is not None else (s.venue or "")
    cur_city = ov.city if ov.city is not None else (s.city or "")
    cur_date = ov.date if ov.date is not None else (s.date or "")
    cur_titles = ", ".join(f"{n}={t}" for n, t in sorted(ov.titles.items()))
    cur_breaks = ",".join(str(n) for n in (ov.set_breaks or []))

    venue = typer.prompt("venue", default=cur_venue, show_default=True)
    city = typer.prompt("city", default=cur_city, show_default=True)
    show_date = typer.prompt("date (YYYY-MM-DD)", default=cur_date, show_default=True)
    titles_in = typer.prompt("title overrides (N=Title, comma-separated)",
                             default=cur_titles, show_default=True)
    breaks_in = typer.prompt("set breaks after tracks (e.g. 9,17)", default=cur_breaks, show_default=True)

    titles_changed = titles_in != cur_titles
    breaks_changed = breaks_in != cur_breaks
    if (venue == cur_venue and city == cur_city and show_date == cur_date
            and not titles_changed and not breaks_changed):
        return False

    parsed_titles = {}
    if titles_changed:
        for spec in (p.strip() for p in titles_in.split(",")):
            if not spec:
                continue
            n, sep, t = spec.partition("=")
            if not sep or not n.strip().isdigit():
                typer.echo(f"title overrides expects N=Title, got {spec!r}")
                return False
            parsed_titles[int(n.strip())] = t

    breaks_val = None
    if breaks_changed:
        parts = [x.strip() for x in breaks_in.split(",") if x.strip()]
        if not all(p.isdigit() for p in parts):
            typer.echo(f"set breaks expects comma-separated track numbers, got {breaks_in!r}")
            return False
        breaks_val = [int(p) for p in parts]

    _edit_overrides(sws,
                    venue=venue if venue != cur_venue else _UNSET,
                    city=city if city != cur_city else _UNSET,
                    date=show_date if show_date != cur_date else _UNSET,
                    set_titles=parsed_titles if titles_changed else None,
                    clear_titles=list(ov.titles.keys()) if titles_changed else [],
                    set_breaks=breaks_val if breaks_changed else _UNSET)
    typer.echo(f"{entry.slug}: metadata override updated")
    return True


def _interactive_resolve(config, ia, ledger, entry) -> None:
    _print_show_entry(entry)
    if entry.state != "held":
        return
    while True:
        choice = typer.prompt(RESOLVE_PROMPT, default="s", show_default=False).strip().lower()
        if choice in ("", "s"):
            return
        if choice == "q":
            raise typer.Exit()
        if choice == "e":
            files = _pick_excludes(read_model(entry.ws.show, Show))
            if not files:
                typer.echo("nothing selected; skipping")
                return
            _edit_overrides(entry.ws, add_exclude=files)
            stage = "gather"
        elif choice == "m":
            if not _metadata_editor(entry):
                continue   # nothing changed - back to the prompt, same show
            stage = "gather"
        elif choice == "v":
            _edit_overrides(entry.ws, narration="vague")
            _clear_hold(entry.ws)
            stage = "brief"
        elif choice == "o":
            _clear_hold(entry.ws)
            stage = "package"
        else:
            typer.echo("unrecognized; skipping")
            return
        fresh = _resolve_show(config, ledger, entry.slug)
        pkg = _redo_show(config, ia, ledger, fresh, stage)
        typer.echo(f"packaged: {pkg}" if pkg else f"still held: {entry.slug}")
        return


def _stage_ages(sws) -> list[tuple[str, float | None]]:
    """(label, age_days|None) per show-level artifact, shallowest to deepest.
    Shared by the text stage table and `--json`'s `stages` block."""
    artifacts = [("selection.json", sws.selection), ("show.json", sws.show),
                 ("research.md", sws.research), ("vetting.json", sws.vetting),
                 ("briefing.json", sws.briefing_json),
                 ("package/manifest.json", sws.package_dir / "manifest.json")]
    now = datetime.now(timezone.utc).timestamp()
    return [(label, (now - path.stat().st_mtime) / 86400 if path.exists() else None)
            for label, path in artifacts]


def _print_stages(sws) -> None:
    typer.echo("stages:")
    for label, age in _stage_ages(sws):
        if age is None:
            typer.echo(f"  {label:22s} missing")
        else:
            typer.echo(f"  {label:22s} {age:5.1f}d old")


def _print_show_entry(entry, show_tracks: bool = False) -> None:
    """Read-only inspection block (spec §5.2, §10) — never prompts, never
    writes. A show with no show.json yet (pre-gather) prints only slug/state/
    path, the stage table, and the archive-URL block (when selection.json
    exists); it skips the identity/overrides/needs-review sections since
    there is no Show to source them from."""
    sws = entry.ws
    if not sws.show.exists():
        typer.echo(f"slug: {entry.slug}")
        typer.echo(f"state: {entry.state}   path: {sws.dir}")
        _print_stages(sws)
        _print_recording_info(sws)
        return
    s = read_model(sws.show, Show)
    place = ", ".join(p for p in [s.venue, s.city] if p)
    if s.venue_source == "jerrybase" and place:
        place = f"{place} (venue from jerrybase)"
    date_str = s.date
    if s.date_source == "research" and s.item_date:
        date_str = f"{s.date} (item date {s.item_date}, corrected via research)"
    typer.echo(f"{s.artist}  {date_str}  {place}".rstrip())
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks)")
    _print_recording_info(sws)
    typer.echo(f"state: {entry.state}   path: {sws.dir}")
    from llama.workspace import read_overrides
    ov = read_overrides(sws)
    parts = []
    if ov.narration != "full":
        parts.append(f"narration={ov.narration}")
    if ov.exclude:
        parts.append(f"exclude={ov.exclude}")
    if ov.venue is not None:
        parts.append(f"venue={ov.venue!r}")
    if ov.city is not None:
        parts.append(f"city={ov.city!r}")
    if ov.date is not None:
        parts.append(f"date={ov.date}")
    if ov.titles:
        parts.append(f"titles={ov.titles}")
    if ov.set_breaks is not None:
        parts.append(f"set_breaks={ov.set_breaks}")
    if parts:
        typer.echo("overrides: " + "  ".join(parts))
    _print_stages(sws)
    if not s.needs_review:
        typer.echo("needs-review: no")
    else:
        typer.echo("needs-review: yes")
        for f in s.review_flags:
            typer.echo(f"  - {f}")
        typer.echo(f"to overrule after inspecting: llama fix {entry.slug} --overrule")
    if show_tracks:
        for line in _format_tracks(s):
            typer.echo(line)


def _print_show_json(entry, show_tracks: bool = False) -> None:
    import json as _json

    from llama.catalog import recording_info
    from llama.workspace import read_overrides

    sws = entry.ws
    s = read_model(sws.show, Show) if sws.show.exists() else None
    info = recording_info(sws)

    data = {
        "slug": entry.slug,
        "state": entry.state,
        "flags": entry.flags,
        "artist": s.artist if s else None,
        "date": s.date if s else None,
        "venue": s.venue if s else None,
        "city": s.city if s else None,
        "identifier": info.identifier if info else None,
        "archive_url": info.url if info else None,
        "considered": [
            {"identifier": c.identifier, "score": c.score, "lineage": c.lineage,
             "kept_tracks": c.kept_tracks}
            for c in (info.considered if info else [])
        ],
        "path": str(sws.dir),
        "run": entry.provenance.run if entry.provenance else None,
        "needs_review": s.needs_review if s else None,
        "overrides": None,
        "stages": dict(_stage_ages(sws)),
    }
    if s is not None:
        ov = read_overrides(sws)
        data["overrides"] = {
            "exclude": ov.exclude, "narration": ov.narration, "venue": ov.venue,
            "city": ov.city, "date": ov.date, "titles": ov.titles,
            "set_breaks": ov.set_breaks,
        }
    if show_tracks:
        data["tracks"] = [t.model_dump() for t in s.tracks] if s is not None else None
    typer.echo(_json.dumps(data, indent=2))


@app.command(rich_help_panel="Watch",
             short_help="Inspect one show, read-only (identity, overrides, URLs, stages).")
def show(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    tracks: bool = typer.Option(False, "--tracks", help="List the show's tracks (numbered)"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """Inspect one show: identity, overrides, stage ages, and archive URL.
    Strictly read-only — never prompts, never edits. Use `llama fix` to edit
    overrides or resolve a hold, and `llama triage` for the interactive
    walkthrough."""
    config, _, ledger = _setup()
    entry = _resolve_show(config, ledger, name)
    if as_json:
        _print_show_json(entry, show_tracks=tracks)
        return
    _print_show_entry(entry, show_tracks=tracks)


# Teaching content for `pipeline` (spec §5.3): static text only, maintained
# here so it can't silently drift from `docs/workflow.md`. Stage/state names
# are sourced from the real constants (`workspace.SHOW_STAGE_ORDER`,
# `cli_select.ShowState`) so the teaching output can't drift from reality.
_PIPELINE_RUN_STAGES = ["interpret", "search", "winnow"]

_PIPELINE_STAGE_DESC: dict[str, str] = {
    "interpret": "query -> structured criteria (artist, era, count, constraints) -> criteria.json",
    "search": "wide-net archive.org scrape, grouped by performance -> candidates.json",
    "winnow": "ledger dedup + quality floors + LLM review scoring -> shortlist.json",
    "select": "picks the best recording of the performance -> selection.json",
    "gather": "junk-filters files, resolves track titles, builds set structure -> show.json, reviews.json",
    "research": "deep web research on the specific performance -> research.md",
    "vet": "grounding check of research's claims against the setlist/date -> vetting.json",
    "brief": "neutral vetted briefing for scriptwriters, factually guarded (always on) -> briefing.*",
    "package": "downloads/tags/verifies audio, writes manifest v3 + m3u -> package/",
    "deliver": "copies package/ into the station's watched folder, records a delivered ledger entry",
}

_PIPELINE_FLOW = (
    "interpret → search → winnow →(gate 1: run approve)→ select → "
    "gather → research → vet → brief → package "
    "→(gate 2: held → triage / fix)→ deliver"
)

_PIPELINE_STATE_DESC: dict[str, str] = {
    "held": "show.json has needs_review: true -- gate 2 hold, sorts first in `llama status`",
    "selected": "selection.json exists; no deeper stage artifact yet",
    "gathered": "show.json / reviews.json exist",
    "researched": "research.md exists",
    "vetted": "vetting.json exists",
    "briefed": "briefing.* exist (neutral vetted briefing)",
    "packaged": "package/manifest.json exists",
    "delivered": "the ledger has a delivered entry for the performance",
}

_PIPELINE_REDO_CHEATSHEET = [
    ("excludes / metadata edit", "gather"),
    ("narration mode (vague)", "brief"),
    ("overrule (false-alarm hold)", "package"),
    ("new recording pick", "select"),
    ("re-research", "research"),
]


@app.command(rich_help_panel="Watch",
             short_help="Print the stages, states, and redo cheat-sheet (static, read-only).")
def pipeline():
    """Teaching command: print the stage flow, the derived states, and the
    redo cheat-sheet. Static text, read-only -- no config, no I/O, never
    prompts, never writes."""
    typer.echo(_PIPELINE_FLOW)
    typer.echo()
    typer.echo("Stages:")
    for name in _PIPELINE_RUN_STAGES:
        typer.echo(f"  {name.ljust(12)}{_PIPELINE_STAGE_DESC[name]}")
    typer.echo("  >> gate 1: run approve -- \"llama run approve <run>\" decides which "
               "shortlisted shows get processed <<")
    for name in SHOW_STAGE_ORDER:
        typer.echo(f"  {name.ljust(12)}{_PIPELINE_STAGE_DESC[name]}")
    typer.echo("  >> gate 2: held -- a flagged show stops here for \"llama triage\" / "
               "\"llama fix\" before it can ship <<")
    typer.echo(f"  {'deliver'.ljust(12)}{_PIPELINE_STAGE_DESC['deliver']}")
    typer.echo()
    typer.echo("States (derived, never stored):")
    for state in ShowState:
        typer.echo(f"  {state.value.ljust(12)}{_PIPELINE_STATE_DESC[state.value]}")
    typer.echo()
    typer.echo("Redo cheat-sheet (\"llama fix\" applies these automatically -- earliest"
               "-affected stage wins on combos -- \"llama redo --from STAGE\" is the "
               "manual escape hatch for any stage, including select/research):")
    for cause, stage in _PIPELINE_REDO_CHEATSHEET:
        typer.echo(f"  {cause.ljust(30)} -> redo --from {stage}")


def _confirm_plan(entries, action: str, yes: bool) -> bool:
    typer.echo(f"{len(entries)} show(s) to {action}:")
    for e in entries:
        typer.echo(f"  {e.slug}")
    if yes:
        return True
    return typer.confirm("Proceed?", default=False)


def _deliver_pointer(slug: str, reasons: list[str]) -> str:
    """The one-line hint following a refusal, by category (first match wins).
    The only two categories left post-cut: held (resolve via triage) and
    everything else -- not packaged or missing audio -- (re-package)."""
    if "held for review" in reasons:
        return f"  resolve it: llama triage {slug}"
    return f"  re-package: llama redo {slug} --from package"


def _deliver_one(config, ledger, entry, dest) -> Path:
    """Copy one resolved show's package to `dest` (or config.delivery_path)
    and record the delivery in the ledger; returns the destination path.
    Raises LlamaError on refusal -- no destination, or a deliver-gate
    refusal from `catalog.deliver_refusals` (none of its three legs is
    overridable)."""
    import json as _json

    from llama.catalog import deliver_refusals

    show_ws = entry.ws
    show_dir = show_ws.dir
    target_dir = dest or config.delivery_path
    if target_dir is None:
        raise LlamaError("no --dest given and no delivery_path in config")
    with file_lock(show_ws.lock):
        reasons = deliver_refusals(show_ws)
        if reasons:
            message = f"refusing to deliver {entry.slug}: {'; '.join(reasons)}"
            raise LlamaError(f"{message}\n{_deliver_pointer(entry.slug, reasons)}")
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
    return out


def _deliver_batch(config, ledger, sel, dest, yes) -> None:
    from llama.catalog import iter_shows
    from llama.cli_select import HELD_NOTE, apply_selector, split_held

    entries = apply_selector(iter_shows(config.root, ledger), sel)
    kept, dropped = split_held(entries, sel)
    if dropped:
        typer.echo(HELD_NOTE.format(n=len(dropped)))
    if not kept:
        typer.echo("no matching shows")
        return
    if not _confirm_plan(kept, "deliver", yes):
        return
    for e in kept:
        try:
            out = _deliver_one(config, ledger, e, dest)
        except LlamaError as exc:
            typer.echo(str(exc), err=True)
        except OSError as exc:
            typer.echo(f"FAILED {e.slug}: {exc}", err=True)
        else:
            typer.echo(f"delivered: {out}")


@app.command(rich_help_panel="Fix & ship",
             short_help="Copy a show package to the station's watched folder; record delivery.")
def deliver(
    name: str = typer.Argument(None, help="Show slug, unique substring, or path"),
    dest: Path = typer.Option(None, "--dest", help="Defaults to config delivery_path"),
    held: bool = typer.Option(False, "--held", help="Selector: include held shows"),
    packaged: bool = typer.Option(False, "--packaged", help="Selector: packaged, undelivered shows"),
    state: list[ShowState] = typer.Option(
        [], "--state", help="Selector: shows in this derived state (repeatable)"),
    artist: str = typer.Option(None, "--artist", help="Selector: substring filter on artist"),
    run: str = typer.Option(None, "--run", help="Selector: shows processed by this run"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt for a batch"),
):
    """Copy a show package to the station's watched folder and record delivery.

    Requires a clean package: packaged, file-complete, and not held for
    review. None of these three legs is overridable.
    """
    from llama.cli_select import build_selector

    other_selector = any([held, packaged, state, artist, run])
    if name is not None and other_selector:
        typer.echo("give a show OR selectors, not both", err=True)
        raise typer.Exit(1)
    if name is None and not other_selector:
        typer.echo("give a show or a selector (e.g. --packaged)", err=True)
        raise typer.Exit(1)

    config, _, ledger = _setup()

    if name is not None:
        entry = _resolve_show(config, ledger, name)
        try:
            out = _deliver_one(config, ledger, entry, dest)
        except LlamaError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        typer.echo(f"delivered: {out}")
        return

    try:
        sel = build_selector(held=held, packaged=packaged, states=state,
                             artist=artist, run=run)
    except LlamaError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    _deliver_batch(config, ledger, sel, dest, yes)


def _redo_show(config, ia, ledger, entry, from_stage: str, *,
               with_research: bool = False) -> Path | None:
    """Re-run one resolved show from `from_stage` onward; returns the package
    path, or None if the show was held/skipped. Raises LlamaError on a
    hand-built show with no provenance."""
    from llama.models import QualityAssessment
    from llama.workspace import drop_stage_artifacts

    if entry.provenance is None:
        raise LlamaError(f"no provenance.json in {entry.ws.dir} - "
                         "reprocess it via its run first")
    prov = entry.provenance
    keep_research = not with_research and from_stage in ("select", "gather")
    show_ws = entry.ws
    with file_lock(show_ws.lock):
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
        shortlist_entry = ShortlistEntry(rank=1, candidate=prov.candidate, assessment=assessment)
        ws = RunWorkspace(config.root, prov.run)
        return process_show(ws, ia, ledger, shortlist_entry, make_providers(config),
                            prov.run, config.audio_format,
                            setlistfm=make_client(config), structure_cfg=config.structure,
                            jerrybase_enabled=config.jerrybase.enabled,
                            selection_cfg=config.selection, profile=prov.profile)


class NarrationMode(str, Enum):
    vague = "vague"
    full = "full"


@app.command(rich_help_panel="Fix & ship",
             short_help="Edit a show's overrides / resolve its hold, then auto-run the redo.")
def fix(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    exclude: list[str] = typer.Option(
        None, "--exclude", help="Add source filenames (or track numbers) to overrides.exclude"),
    unexclude: list[str] = typer.Option(
        None, "--unexclude", help="Remove filenames (or track numbers) from overrides.exclude"),
    set_venue: str = typer.Option(None, "--set-venue", help="Force overrides.venue"),
    set_city: str = typer.Option(None, "--set-city", help="Force overrides.city"),
    set_date: str = typer.Option(None, "--set-date", help="Force overrides.date (YYYY-MM-DD)"),
    set_title: list[str] = typer.Option(
        None, "--set-title", help='Force a track title: --set-title N="Song"'),
    clear_title: list[str] = typer.Option(
        None, "--clear-title", help="Drop a title override by track number"),
    set_breaks: str = typer.Option(
        None, "--set-breaks", help='Force set breaks by track number: "9,17"'),
    clear_set_breaks: bool = typer.Option(
        False, "--clear-set-breaks", help="Clear the set-breaks override"),
    narration: NarrationMode = typer.Option(
        None, "--narration", help="vague clears the hold; full resets narration and leaves it"),
    overrule: bool = typer.Option(
        False, "--overrule", help="Overrule a held show: clear needs-review and its flags"),
    no_run: bool = typer.Option(
        False, "--no-run", help="Stage the resolving redo instead of running it now"),
):
    """Edit one show's overrides.json / resolve its hold, then auto-run the
    correct redo (earliest-affected stage wins on combos). --no-run stages
    the redo instead of running it."""
    config, ia, ledger = _setup()
    entry = _resolve_show(config, ledger, name)
    sws = entry.ws

    parsed_titles = {}
    for spec in (set_title or []):
        n, sep, t = spec.partition("=")
        if not sep or not n.strip().isdigit():
            typer.echo(f'--set-title expects N="Title" with a track number, got {spec!r}', err=True)
            raise typer.Exit(1)
        parsed_titles[int(n.strip())] = t
    clear_title_nums = []
    for spec in (clear_title or []):
        if not str(spec).strip().isdigit():
            typer.echo(f"--clear-title expects a track number, got {spec!r}", err=True)
            raise typer.Exit(1)
        clear_title_nums.append(int(str(spec).strip()))
    breaks_val = None
    if set_breaks:
        parts = [x.strip() for x in set_breaks.split(",") if x.strip()]
        if not all(p.isdigit() for p in parts):
            typer.echo(f"--set-breaks expects comma-separated track numbers, got {set_breaks!r}", err=True)
            raise typer.Exit(1)
        breaks_val = [int(p) for p in parts]

    did_exclude = bool(exclude or unexclude)
    did_meta = bool(set_venue or set_city or set_date or parsed_titles
                    or clear_title_nums or set_breaks or clear_set_breaks)
    did_narration = narration is not None

    if not (did_exclude or did_meta or did_narration or overrule):
        typer.echo("nothing to fix: give an edit flag (see --help), or inspect with: "
                   f"llama show {entry.slug}", err=True)
        raise typer.Exit(1)

    if not sws.show.exists():
        typer.echo(f"no show.json in {sws.dir} (state: {entry.state})", err=True)
        raise typer.Exit(1)

    real_edit = False
    if did_exclude:
        try:
            add = _resolve_exclude_tokens(sws, exclude or [])
            rm = _resolve_exclude_tokens(sws, unexclude or [])
        except LlamaError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        ov = _edit_overrides(sws, add_exclude=add, rm_exclude=rm)
        typer.echo(f"{entry.slug}: overrides.exclude = {ov.exclude} "
                   "(the hold clears itself if a clean re-gather results)")
        real_edit = True
    if narration == NarrationMode.vague:
        _edit_overrides(sws, narration="vague")
        _clear_hold(sws)
        typer.echo(f"{entry.slug}: narration = vague; hold cleared")
        real_edit = True
    if narration == NarrationMode.full:
        _edit_overrides(sws, narration="full")
        typer.echo(f"{entry.slug}: narration = full")
        real_edit = True
    if overrule:
        if entry.state == "held":
            _clear_hold(sws)
            typer.echo(f"{entry.slug}: hold cleared")
            real_edit = True
        else:
            typer.echo(f"{entry.slug}: not held; nothing to overrule")
    if did_meta:
        _edit_overrides(sws,
            venue=set_venue if set_venue is not None else _UNSET,
            city=set_city if set_city is not None else _UNSET,
            date=set_date if set_date is not None else _UNSET,
            set_titles=parsed_titles or None,
            clear_titles=clear_title_nums,
            set_breaks=breaks_val if set_breaks else _UNSET,
            clear_set_breaks=clear_set_breaks)
        typer.echo(f"{entry.slug}: metadata override updated")
        real_edit = True

    if not real_edit:
        return   # e.g. a lone --overrule on a show that was never held

    stage = "gather" if (did_exclude or did_meta) else ("brief" if did_narration else "package")
    if no_run:
        typer.echo(f"staged; next: llama redo {entry.slug} --from {stage}")
        return
    entry2 = _resolve_show(config, ledger, entry.slug)
    pkg = _redo_show(config, ia, ledger, entry2, stage)
    typer.echo(f"packaged: {pkg}" if pkg else f"still held: {entry.slug}")


@app.command(rich_help_panel="Fix & ship",
             short_help="Interactively resolve shows (default: held) -- the walkthrough.")
def triage(
    name: str = typer.Argument(None, help="Show slug, unique substring, or path"),
    held: bool = typer.Option(False, "--held", help="Selector: include held shows"),
    packaged: bool = typer.Option(False, "--packaged", help="Selector: packaged, undelivered shows"),
    state: list[ShowState] = typer.Option(
        [], "--state", help="Selector: shows in this derived state (repeatable)"),
    artist: str = typer.Option(None, "--artist", help="Selector: substring filter on artist"),
    run: str = typer.Option(None, "--run", help="Selector: shows processed by this run"),
):
    """Interactively walk shows for resolution (default: held shows) —
    exclude tracks, edit metadata, accept vague narration, or overrule the
    hold. Always interactive: requires a TTY."""
    if not sys.stdin.isatty():
        typer.echo("triage is interactive; use 'llama status' or 'llama show' "
                   "for scripted reads", err=True)
        raise typer.Exit(1)
    from llama.catalog import iter_shows
    from llama.cli_select import apply_selector, build_selector, selector_active

    try:
        sel = build_selector(held=held, packaged=packaged,
                             states=state, artist=artist, run=run)
    except LlamaError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    if name is not None and selector_active(sel):
        typer.echo("give a show OR selectors, not both", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup()
    if name is not None:
        entries = [_resolve_show(config, ledger, name)]
    else:
        if not selector_active(sel):
            sel = build_selector(held=True)   # triage's default: held (spec §2 exception)
        entries = apply_selector(iter_shows(config.root, ledger), sel)
    if not entries:
        typer.echo("no matching shows")
        return
    for e in entries:
        _interactive_resolve(config, ia, ledger, e)


def _redo_batch(config, ia, ledger, sel, from_stage: str, *, redo_research: bool,
                yes: bool) -> None:
    """The selector-batch form shared by a plain selector redo and a
    `--run`-scoped show-level redo: apply the selector, drop held shows
    (opt in via `--held` or an explicit `held` state), plan/confirm, then
    `_redo_show` each survivor with per-show failure isolation."""
    from llama.catalog import iter_shows
    from llama.cli_select import HELD_NOTE, apply_selector, split_held

    entries = apply_selector(iter_shows(config.root, ledger), sel)
    kept, dropped = split_held(entries, sel)
    if dropped:
        typer.echo(HELD_NOTE.format(n=len(dropped)))
    if not kept:
        typer.echo("no matching shows")
        return
    if not _confirm_plan(kept, f"redo --from {from_stage}", yes):
        return
    for e in kept:
        try:
            pkg = _redo_show(config, ia, ledger, e, from_stage,
                             with_research=redo_research)
            typer.echo(f"packaged: {pkg}" if pkg else f"still held: {e.slug}")
        except (LlamaError, TaskFailed, HerderError, IAError, SpeechError) as exc:
            typer.echo(f"FAILED {e.slug}: {exc}", err=True)


def _redo_run_level(config, ia, ledger, run_name: str, from_stage: str) -> None:
    """`redo --run SESSION --from search|winnow`: the old `run --stage X
    --force` run-wide re-execution, relocated verbatim (approvals-loss
    confirm on a doomed shortlist, downstream-artifact deletion, then a
    plain `_execute` replay with the run's own persisted criteria)."""
    ws = _resolve_run(config, run_name)
    if not ws.criteria.exists():
        typer.echo(f"no criteria.json in {ws.dir}", err=True)
        raise typer.Exit(1)
    criteria = read_model(ws.criteria, Criteria)
    if from_stage == "search" and ws.shortlist.exists():
        entries = read_model_list(ws.shortlist, ShortlistEntry)
        if any(e.approved is not None for e in entries):
            typer.echo("this rebuilds the shortlist and discards the approvals recorded on it")
            if not typer.confirm("Continue?", default=False):
                raise typer.Exit(1)
    # a stale shortlist would block re-winnowing after a fresh search
    doomed = [ws.candidates, ws.shortlist] if from_stage == "search" else [ws.shortlist]
    for path in doomed:
        if path.exists():
            path.unlink()
    _execute(config, ia, ledger, ws, criteria, criteria.count, True,
             human_gate=False, force=False,
             force_stage=None, full_rationale=False)


@app.command(rich_help_panel="Fix & ship",
             short_help="The re-execution verb: re-run a show, batch, or --run from a stage.")
def redo(
    name: str = typer.Argument(None, help="Show slug, unique substring, or path"),
    from_stage: str = typer.Option(..., "--from",
                                   help="Stage to re-run from: select|gather|research|vet|"
                                        "brief|package (search|winnow valid only with --run)"),
    run: str = typer.Option(None, "--run",
                            help="Session scope: redo a whole run's shows (with a show-level "
                                 "--from), or rebuild that run's candidates/shortlist (--from "
                                 "search|winnow). Exclusive with a show name or other selectors."),
    redo_research: bool = typer.Option(False, "--redo-research",
                                       help="Also drop research.md (kept by default)"),
    held: bool = typer.Option(False, "--held", help="Selector: include held shows"),
    packaged: bool = typer.Option(False, "--packaged", help="Selector: packaged, undelivered shows"),
    state: list[ShowState] = typer.Option(
        [], "--state", help="Selector: shows in this derived state (repeatable)"),
    artist: str = typer.Option(None, "--artist", help="Selector: substring filter on artist"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt for a batch"),
):
    """Re-run one show (--from STAGE), a selector batch, or a whole
    --run session -- the single re-execution verb (spec §7.1)."""
    from llama.cli_select import build_selector

    other_selector = any([held, packaged, state, artist])
    # Three-form grammar: positional show | --run SESSION | selectors -- exactly one.
    if name is not None and (run is not None or other_selector):
        typer.echo("give a show OR selectors, not both", err=True)
        raise typer.Exit(1)
    if run is not None and other_selector:
        typer.echo("give --run OR other selectors, not both", err=True)
        raise typer.Exit(1)

    valid_stages = VALID_STAGES if run is not None else (VALID_STAGES - RUN_LEVEL_STAGES)
    if from_stage not in valid_stages:
        rule = "" if run is not None else " (search/winnow need --run)"
        typer.echo(f"unknown stage {from_stage!r}; valid here: {sorted(valid_stages)}{rule}",
                   err=True)
        raise typer.Exit(1)

    if run is not None:
        config, ia, ledger = _setup()
        if from_stage in RUN_LEVEL_STAGES:
            _redo_run_level(config, ia, ledger, run, from_stage)
            return
        sel = build_selector(run=run)
        _redo_batch(config, ia, ledger, sel, from_stage, redo_research=redo_research,
                   yes=yes)
        return

    if name is not None:
        config, ia, ledger = _setup()
        entry = _resolve_show(config, ledger, name)
        if entry.provenance is None:
            typer.echo(f"no provenance.json in {entry.ws.dir} - "
                       "reprocess it via its run first", err=True)
            raise typer.Exit(1)
        pkg = _redo_show(config, ia, ledger, entry, from_stage,
                         with_research=redo_research)
        if pkg:
            typer.echo(f"packaged: {pkg}")
        else:
            typer.echo(f"still held: {entry.slug}")
        return

    if not other_selector:
        typer.echo("give a show, --run, or a selector (e.g. --packaged)", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup()
    try:
        sel = build_selector(held=held, packaged=packaged, states=state, artist=artist)
    except LlamaError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    _redo_batch(config, ia, ledger, sel, from_stage, redo_research=redo_research,
               yes=yes)


def _rm_action(forget: bool, suppress: bool) -> str:
    """The confirm-plan action label, folding in the history disposition
    (spec §8.1) so the confirmation prompt names it before `Proceed?`."""
    if forget:
        return "remove -- forget: purges ledger history (re-eligible)"
    if suppress:
        return "remove -- suppress: reversible rejected row (undo: llama unsuppress <pid>)"
    return "remove -- history untouched"


def _rm_batch(config, ledger, sel, *, forget: bool, suppress: bool, yes: bool) -> None:
    """The selector-batch form: apply the selector, drop held shows (opt in
    via `--held` or an explicit `held` state), plan/confirm, then
    `catalog.remove_show` each survivor with per-show failure isolation."""
    from llama.catalog import iter_shows, remove_show
    from llama.cli_select import HELD_NOTE, apply_selector, split_held

    entries = apply_selector(iter_shows(config.root, ledger), sel)
    kept, dropped = split_held(entries, sel)
    if dropped:
        typer.echo(HELD_NOTE.format(n=len(dropped)))
    if not kept:
        typer.echo("no matching shows")
        return
    if not _confirm_plan(kept, _rm_action(forget, suppress), yes):
        return
    for e in kept:
        try:
            lines = remove_show(e, ledger, forget=forget, suppress=suppress)
        except LlamaError as exc:
            typer.echo(f"FAILED {e.slug}: {exc}", err=True)
            continue
        for line in lines:
            typer.echo(line)


@app.command(rich_help_panel="Fix & ship",
             short_help="Delete a show (confirms); --forget/--suppress choose its history fate.")
def rm(
    name: str = typer.Argument(None, help="Show slug, unique substring, or path"),
    forget: bool = typer.Option(False, "--forget",
                                help="Purge this show's ledger history (re-eligible)"),
    suppress: bool = typer.Option(False, "--suppress",
                                  help="Write a reversible rejected ledger row instead"),
    held: bool = typer.Option(False, "--held", help="Selector: include held shows"),
    packaged: bool = typer.Option(False, "--packaged", help="Selector: packaged, undelivered shows"),
    state: list[ShowState] = typer.Option(
        [], "--state", help="Selector: shows in this derived state (repeatable)"),
    artist: str = typer.Option(None, "--artist", help="Selector: substring filter on artist"),
    run: str = typer.Option(None, "--run", help="Selector: shows processed by this run"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
):
    """Delete a show's directory -- the one irreversible local operation, so
    it confirms by default (`--yes` skips). History is left untouched
    unless you say otherwise: `--forget` purges every ledger row for this
    performance (re-eligible again); `--suppress` instead appends a
    reversible `rejected` row (undo with `llama unsuppress <performance-id>`);
    the two are mutually exclusive. A selector batches the same over every
    match (shared selector layer, held opt-in required -- see `--held`; a
    positional show is deleted regardless of held state, same as `redo`).
    """
    from llama.cli_select import build_selector

    other_selector = any([held, packaged, state, artist, run])
    if name is not None and other_selector:
        typer.echo("give a show OR selectors, not both", err=True)
        raise typer.Exit(1)
    if name is None and not other_selector:
        typer.echo("give a show or a selector (e.g. --packaged)", err=True)
        raise typer.Exit(1)

    config, _, ledger = _setup()

    if name is not None:
        from llama.catalog import remove_show

        entry = _resolve_show(config, ledger, name)
        if not _confirm_plan([entry], _rm_action(forget, suppress), yes):
            return
        # forget/suppress mutual exclusion and no-resolvable-pid errors are
        # raised by remove_show itself and left to propagate -- the
        # LlamaError boundary prints them cleanly (main_cli's `error: ...`).
        for line in remove_show(entry, ledger, forget=forget, suppress=suppress):
            typer.echo(line)
        return

    try:
        sel = build_selector(held=held, packaged=packaged, states=state,
                             artist=artist, run=run)
    except LlamaError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    _rm_batch(config, ledger, sel, forget=forget, suppress=suppress, yes=yes)


def _resolve_pid_and_metadata(config, ledger, name: str) -> tuple[str, str, str, str | None]:
    """(performance_id, artist, date, venue) for `suppress`, resolving an
    on-disk show like other acting commands (metadata from
    show.json/provenance) and falling back to a raw `collection/date[/eN]`
    performance id for anything not (or no longer) on disk. A `CatalogError`
    from an unresolvable, unparseable name propagates to the LlamaError
    boundary."""
    from llama.catalog import CatalogError

    try:
        entry = _resolve_show(config, ledger, name)
    except CatalogError:
        parsed = parse_performance_id(name)
        if parsed is None:
            raise
        artist, show_date = parsed
        return name, artist, show_date, None

    show = read_model(entry.ws.show, Show) if entry.ws.show.exists() else None
    if entry.provenance is not None:
        pid = entry.provenance.performance_id
    elif show is not None:
        pid = show.performance_id
    else:
        raise LlamaError(f"cannot resolve a performance id for {entry.slug}")
    if show is not None:
        artist, show_date, venue = show.artist, show.date, show.venue
    else:
        candidate = entry.provenance.candidate
        artist, show_date, venue = candidate.collection, candidate.date, candidate.venue
    return pid, artist, show_date, venue


def _resolve_pid(config, ledger, name: str) -> str:
    """Just the performance id half of `_resolve_pid_and_metadata`, for
    `unsuppress` (which has nothing to write, so no other metadata needed)."""
    return _resolve_pid_and_metadata(config, ledger, name)[0]


@app.command(rich_help_panel="Fix & ship",
             short_help="Skip a performance in future gets (reversible `rejected` row).")
def suppress(name: str = typer.Argument(
    ..., help="Show slug, unique substring, path, or a raw collection/date[/eN] performance id")):
    """Write a reversible `rejected` history row -- without touching anything
    on disk -- so the performance is skipped by future gets. Resolves an
    on-disk show like other acting commands; a raw performance id also works
    for a performance that isn't (or is no longer) on disk. No confirmation
    prompt -- undo any time with `llama unsuppress <performance-id>`.
    """
    config, _, ledger = _setup()
    pid, artist, show_date, venue = _resolve_pid_and_metadata(config, ledger, name)
    ledger.record(LedgerEntry(
        performance_id=pid, artist=artist, date=show_date, venue=venue,
        status="rejected", run="manual",
        recorded_at=datetime.now(timezone.utc).isoformat(),
    ))
    typer.echo(f"suppressed: {pid}")


@app.command(rich_help_panel="Fix & ship",
             short_help="Undo a suppress: remove the `rejected` row (eligible again).")
def unsuppress(name: str = typer.Argument(
    ..., help="Show slug, unique substring, path, or a raw collection/date[/eN] performance id")):
    """Remove a `rejected` history row written by `suppress` (or `rm
    --suppress`), making the performance eligible again. A clean no-op
    (still exit 0) when there is nothing to remove.
    """
    config, _, ledger = _setup()
    pid = _resolve_pid(config, ledger, name)
    n = ledger.remove_status(pid, "rejected")
    typer.echo(f"removed {n} rejected row(s) for {pid}")


_ATTENTION_LABELS = {STATE_AWAITING: "awaiting approval", STATE_INCOMPLETE: "incomplete"}
_ATTENTION_HINTS = {STATE_AWAITING: "llama run approve {id}", STATE_INCOMPLETE: "llama run resume {id}"}


def _session_json(s) -> dict:
    return {"id": s.id, "state": s.state, "updated_at": s.updated_at,
            "query": s.query, "profile": s.profile}


def _print_attention(sessions) -> None:
    if not sessions:
        return
    typer.echo("sessions needing attention:")
    for s in sessions:
        label = _ATTENTION_LABELS.get(s.state, s.state)
        hint = _ATTENTION_HINTS.get(s.state, "llama run resume {id}").format(id=s.id)
        typer.echo(f"  {s.id:<36} {label:<18} {hint}")


def _by_run_rollup(config, ledger) -> list[dict]:
    """One row per session dir: id, per-state show counts (via provenance
    grouping), query. Absorbs the deleted `runs` command."""
    from collections import Counter

    from llama.catalog import iter_shows

    by_run: dict[str, Counter] = {}
    for e in iter_shows(config.root, ledger):
        if e.provenance:
            by_run.setdefault(e.provenance.run, Counter())[e.state] += 1
    runs_dir = config.root / "runs"
    run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.is_dir() else []
    rows = []
    for d in run_dirs:
        query = ""
        if (d / "criteria.json").exists():
            query = read_model(RunWorkspace(config.root, d.name).criteria, Criteria).query
        counts = by_run.get(d.name, Counter())
        rows.append({"id": d.name, "query": query, "states": dict(sorted(counts.items()))})
    return rows


@app.command(rich_help_panel="Watch",
             short_help="Global triage: session attention-list + every show's state.")
def status(
    held: bool = typer.Option(False, "--held", help="Selector: include held shows"),
    packaged: bool = typer.Option(False, "--packaged", help="Selector: packaged, undelivered shows"),
    state: list[ShowState] = typer.Option(
        [], "--state", help="Selector: shows in this derived state (repeatable)"),
    run: str = typer.Option(None, "--run", help="Selector: shows processed by this run"),
    artist: str = typer.Option(None, "--artist", help="Selector: substring filter on artist"),
    all_shows: bool = typer.Option(False, "--all", help="Include all delivered shows"),
    by_run: bool = typer.Option(False, "--by-run",
                               help="Per-session show-count rollup instead of the show table "
                                    "(exclusive of selectors/--all)"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """Global triage view: session attention-list, then every show and its
    state, held-for-review first. Read-only — never prompts, never writes."""
    import json as _json

    from llama.catalog import iter_shows
    from llama.cli_select import apply_selector, build_selector, selector_active

    try:
        sel = build_selector(held=held, packaged=packaged, states=state,
                             artist=artist, run=run)
    except LlamaError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    if by_run and (selector_active(sel) or all_shows):
        typer.echo("--by-run is exclusive of selectors and --all", err=True)
        raise typer.Exit(1)

    config, _, ledger = _setup()
    sessions = attention_sessions(config.root)

    if not as_json:
        _print_attention(sessions)

    if by_run:
        rollup = _by_run_rollup(config, ledger)
        if as_json:
            typer.echo(_json.dumps({
                "sessions": [_session_json(s) for s in sessions],
                "runs": rollup,
            }, indent=2))
            return
        if not rollup:
            typer.echo("no runs")
            return
        for row in rollup:
            summary = "  ".join(f"{s} {n}" for s, n in row["states"].items()) or "no shows"
            typer.echo(f"{row['id']:34.34s} {summary:40.40s} {row['query']:40.40s}")
        return

    entries = apply_selector(iter_shows(config.root, ledger), sel)
    filtering = selector_active(sel)
    entries.sort(key=lambda e: (_STATE_RANK[e.state], e.slug))
    if not all_shows and not filtering:
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
        typer.echo(_json.dumps({
            "sessions": [_session_json(s) for s in sessions],
            "shows": [{
                "slug": e.slug, "state": e.state, "artist": e.artist, "date": e.date,
                "run": e.provenance.run if e.provenance else None,
                "flags": e.flags, "path": str(e.ws.dir),
                "overrides": {"exclude": e.overrides.exclude, "narration": e.overrides.narration},
            } for e in entries],
        }, indent=2))
        return
    if not entries:
        typer.echo("no shows")
        return
    for e in entries:
        run_name = e.provenance.run if e.provenance else "?"
        marks = []
        if e.overrides.narration == "vague":
            marks.append("vague")
        if e.overrides.exclude:
            marks.append(f"{len(e.overrides.exclude)}x-excl")
        suffix = f"  [{', '.join(marks)}]" if marks else ""
        typer.echo(f"{e.slug:42.42s} {e.state:10s} {e.artist:20.20s} {e.date:10s} {run_name}{suffix}")
        for f in e.flags:
            typer.echo(f"      - {f}")


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
    presenter: str = typer.Option(None, "--presenter",
                                  help="Host for this show: presenters/<id>.toml; its "
                                       "voice voices this profile's runs even when "
                                       "[tts] enabled is false"),
    title: str = typer.Option(None, "--title",
                              help="The radio show's on-air name (the host knows it "
                                   "and says it occasionally)"),
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
):
    """Interpret QUERY once and save it as a named standing profile."""
    if artist_cap == 0.0 or year_cap == 0.0:
        typer.echo("--artist-cap/--year-cap must be above 0 "
                   "(a tiny value forces strict rotation; 1.0 disables the cap)", err=True)
        raise typer.Exit(1)
    config, ia, _ = _setup()
    if presenter:
        load_presenter(config.root, presenter)  # fail fast on a typo'd id
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = RunWorkspace(Path(tmpdir), "interpret")
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
        resolved = resolve_artists(index, names)
        updates["artists"] = [a["identifier"] for a in resolved]
        typer.echo("pinned: " + ", ".join(f"{a['title']} ({a['identifier']})" for a in resolved))
    if updates:
        criteria = criteria.model_copy(update=updates)
    profile = Profile(name=name, criteria=criteria, count=count, human_gate=human_gate,
                      presenter=presenter, title=title)
    path = save_profile(config.root, profile)
    typer.echo(f"saved: {path}")


@profile_app.command("artists")
def profile_artists(
    name: str = typer.Argument(...),
    set_: str = typer.Option(None, "--set", help='Re-pin the roster (comma names); "" clears it'),
):
    """Show or re-pin a profile's pinned artist roster."""
    config, ia, _ = _setup()
    profile = load_profile(config.root, name)
    if set_ is None:
        roster = profile.criteria.artists
        typer.echo(", ".join(roster) if roster else "no pinned roster (uses the LLM matcher)")
        return
    names = [n.strip() for n in set_.split(",") if n.strip()]
    if not names:
        criteria = profile.criteria.model_copy(update={"artists": []})
        save_profile(config.root, profile.model_copy(update={"criteria": criteria}))
        typer.echo("cleared pinned roster (reverts to the LLM matcher)")
        return
    index = load_or_build(ia, config.root / "cache")
    resolved = resolve_artists(index, names)
    criteria = profile.criteria.model_copy(update={"artists": [a["identifier"] for a in resolved]})
    save_profile(config.root, profile.model_copy(update={"criteria": criteria}))
    typer.echo("pinned: " + ", ".join(f"{a['title']} ({a['identifier']})" for a in resolved))


_PROFILE_LIST_HEADER = f"{'NAME':<20} {'CNT':>3} {'PRESENTER':<14} QUERY"


@profile_app.command("list")
def profile_list():
    """List profiles: name, count, presenter, query."""
    config, _, _ = _setup()
    rows = list_profiles(config.root)
    if not rows:
        typer.echo("no profiles")
        return
    typer.echo(_PROFILE_LIST_HEADER)
    for name, p in rows:
        if isinstance(p, str):
            typer.echo(f"{name:<20} (invalid: {p})")
            continue
        presenter = p.presenter or "-"
        typer.echo(f"{p.name:<20} {p.count:>3} {presenter:<14} {p.criteria.query:40.40s}")


@profile_app.command("show")
def profile_show(name: str = typer.Argument(...)):
    """Inspect one profile: criteria, count, presenter, and pinned roster.
    Strictly read-only -- never prompts, never edits. No LLM call."""
    config, _, _ = _setup()
    profile = load_profile(config.root, name)   # ProfileError -> main_cli boundary
    c = profile.criteria
    typer.echo(f"{profile.name}  count={profile.count}  human_gate={profile.human_gate}")
    typer.echo(f"query: {c.query}")
    typer.echo(f"presenter: {profile.presenter or '-'}")
    typer.echo(f"title: {profile.title or '-'}")
    if c.artists:
        typer.echo("pinned roster: " + ", ".join(c.artists))
    else:
        typer.echo("no pinned roster")
    typer.echo("criteria:")
    typer.echo(f"  collection/artist: {c.collection or '-'} / {c.artist or '-'}")
    typer.echo(f"  date range: {c.date_from or '-'} .. {c.date_to or '-'}")
    typer.echo(f"  artist_cap/year_cap/min_quality_score: "
               f"{c.artist_cap} / {c.year_cap} / {c.min_quality_score}")


@profile_app.command("remove")
def profile_remove(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
):
    """Delete a profile's TOML file. Sessions and shows are untouched."""
    config, _, _ = _setup()
    path = config.root / "profiles" / f"{name}.toml"
    if not path.exists():
        raise ProfileError(f"no profile {name!r}: {path} does not exist")
    if not yes and not typer.confirm(f"remove profile {name!r}?", default=False):
        return
    delete_profile(config.root, name)
    typer.echo(f"removed: {path}")


def _profiles_using_presenter(root: Path, presenter_id: str) -> list[str]:
    """Names (filename stems) of profiles that still name this presenter,
    sorted -- used by `presenter remove`'s in-use refusal."""
    d = root / "profiles"
    if not d.is_dir():
        return []
    users = []
    for p in sorted(d.glob("*.toml")):
        try:
            prof = load_profile(root, p.stem)
        except ProfileError:
            continue
        if prof.presenter == presenter_id:
            users.append(p.stem)
    return users


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
    config, _, _ = _setup()
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
    dest = config.root / "presenters" / f"{id}.toml"
    if dest.exists() and not force:
        typer.echo(f"presenter {id!r} exists: {dest} (use --force to overwrite)", err=True)
        raise typer.Exit(1)
    try:
        p = Presenter(id=id, name=name, sex=sex, voice=voice,
                      voice_clone=voice_clone, character=text, bed=bed)
    except Exception as exc:
        typer.echo(f"invalid presenter: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"saved: {save_presenter(config.root, p)}")


@presenter_app.command("list")
def presenter_list():
    """List presenters."""
    config, _, _ = _setup()
    rows = list_presenters(config.root)
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
    config, _, _ = _setup()
    p = load_presenter(config.root, id)     # PresenterError -> main_cli boundary
    v = p.voice or f"clone:{p.voice_clone}"
    typer.echo(f"{p.name}  ({p.sex})  voice={v}" + (f"  bed={p.bed}" if p.bed else ""))
    typer.echo("character:")
    typer.echo(p.character)


@presenter_app.command("remove")
def presenter_remove(
    id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
    force: bool = typer.Option(False, "--force",
                               help="Remove even if a profile still names this presenter"),
):
    """Delete a presenter's TOML file. Refuses if a profile still names it
    as its presenter -- pass --force to remove it anyway."""
    config, _, _ = _setup()
    path = config.root / "presenters" / f"{id}.toml"
    if not path.exists():
        raise PresenterError(f"no presenter {id!r}: {path} does not exist")
    if not force:
        users = _profiles_using_presenter(config.root, id)
        if users:
            typer.echo(f"presenter {id} is used by: {', '.join(users)} "
                       "— --force to remove anyway", err=True)
            raise typer.Exit(1)
    if not yes and not typer.confirm(f"remove presenter {id!r}?", default=False):
        return
    delete_presenter(config.root, id)
    typer.echo(f"removed: {path}")


@history_app.command("list")
def history_list(
    log: bool = typer.Option(False, "--log",
                             help="Every ledger row, not just each performance's latest disposition"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """Dispositions for shows no longer on disk; the library covers what's on
    disk. Collapses to one row per performance (its latest disposition) by
    default -- `--log` shows the full append-only trail instead."""
    import json as _json

    _, _, ledger = _setup()
    rows = ledger.entries() if log else ledger.latest_dispositions()
    if as_json:
        typer.echo(_json.dumps([
            {"performance_id": e.performance_id, "status": e.status,
             "run": e.run, "recorded_at": e.recorded_at}
            for e in rows
        ], indent=2))
        return
    for e in rows:
        typer.echo(f"{e.recorded_at[:10]}  {e.status:9s}  {e.performance_id}  ({e.run})")


def main_cli() -> None:
    """CLI entry point with a single error boundary.

    Expected, user-actionable failures (`llama.errors.LlamaError` or
    `herder.HerderError`) print a clean `error: <message>` plus any indented
    details and exit 1. `KeyboardInterrupt` exits 130 quietly. Any other
    exception is a bug: we print a plain traceback ourselves and exit 1 —
    printing it here (rather than letting it propagate) suppresses the frozen
    bootloader's `Failed to execute script` line. `SystemExit`/`typer.Exit`
    from commands pass through untouched.
    """
    try:
        app()
    except (LlamaError, HerderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in getattr(exc, "details", []):
            print(f"  {detail}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
