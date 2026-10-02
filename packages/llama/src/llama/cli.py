import json
import re
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
from herder.failures import set_capture_dir
from herder.limits import RateLimited
from herder.usage import read_usage
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
from llama import pacing as _pacing   # module, not `from ... import _now`:
                                      # a rebound name defeats the tests' clock
from llama import pacing_state
from llama.pacing import (PaceOptions, PauseUntil, Proceed, Progress,
                          binding_forecast, decide, duration_arg, format_delta,
                          pace_options, resume_at, sleep_until)
from llama.pipeline import choose_entries, make_providers, process_show
from llama.profiles import (
    Profile, ProfileError, delete_profile, list_profiles, load_profile, save_profile,
)
from llama.sessions import (STATE_AWAITING, STATE_INCOMPLETE, STATE_PAUSED,
                            attention_sessions, mark_awaiting, mark_complete,
                            mark_incomplete, mark_paused, read_request,
                            session_state)
from llama.setlistfm import make_client
from llama.stages.discover import run_discover
from llama.stages.interpret import run_interpret
from llama.stages.search import run_search
from llama.stages.winnow import run_winnow
from llama.status import configure_logging
from llama.util import parse_performance_id, slugify
from llama.workspace import (RunWorkspace, SHOW_STAGE_ORDER, claim_run_dir,
                             read_model, read_model_list, write_artifact)

VALID_STAGES = {"search", "winnow", "select", "gather", "research", "vet", "brief", "package"}
RUN_LEVEL_STAGES = {"search", "winnow"}

_COMMAND_ORDER = ["get", "artists", "status", "show", "pipeline", "pacing",
                  "triage", "fix", "redo", "deliver", "rm",
                  "suppress", "unsuppress", "run", "profile",
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


def _pace(config, wait: bool | None, max_wait: str | None,
           no_pacing: bool) -> PaceOptions:
    """Resolve the pacing flags, failing on a bad --max-wait before the run
    starts rather than four shows in."""
    try:
        return pace_options(config, wait=wait, max_wait=max_wait,
                            no_pacing=no_pacing)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)


def _render_pause(ws: RunWorkspace, limited, pace: PaceOptions, *,
                  header: str, header_err: bool = False,
                  note: str | None = None,
                  when: datetime | None = None,
                  stalled: bool = False,
                  outcome: str | None = None,
                  failures: list[dict] | None = None,
                  resume_prefix: str = "") -> bool:
    """Render one pause. True = slept, the caller should retry; False = stop.

    ONE renderer for all four pause sites -- the pre-flight gate, the
    run-level catch, the interpret catch (`_interpret_with_pause`) and the
    show loop -- because the half they share is the
    half that must not drift: the timing arithmetic, the sleep-or-checkpoint
    decision, and the whole KeyboardInterrupt contract. When those lived in
    two copies they diverged three ways inside a single commit (`elif` vs `if`
    on the max-wait line, two spellings of the no-progress sentence, and the
    header on a different stream), which is what a duplicated interrupt
    contract looks like just before it costs something.

    What genuinely differs between the sites is passed in, and it is all
    presentation: the header and its stream, an optional note, and the prefix
    on the resume hint (the loop says how many shows are left; a run-level
    site has no queue to report).

    `stalled` is the no-progress guard. The loop computes it from a progress
    watermark across pause cycles; a run-level site has no progress to compare
    across a nap, so it passes `stalled` on any pause after the first at that
    site. Sleeping twice where nothing can change between naps is not a slow
    run, it is a stuck one -- and at a run-level site it is a HOT spin, because
    a `when` already in the past makes `sleep_until` return without sleeping,
    which no sleep-budget guard in a test can see.

    `when` is for a caller holding a `PauseUntil`, whose instant already
    includes reset_skew; routing one through `resume_at` would read a
    `resets_at` it has not got. See PauseUntil's docstring.
    """
    when = when or resume_at(limited, pace)
    wait_s = (when - _pacing._now()).total_seconds()
    reason, scope = str(limited), getattr(limited, "scope", None)
    typer.echo(header, err=header_err)
    if note:
        typer.echo(f"  {note}")
    if stalled:
        typer.echo("  no progress since last pause — checkpointing rather "
                   "than waiting again")
    if not stalled and pace.wait and wait_s <= pace.max_wait_s:
        typer.echo(f"  resumes {when.astimezone().strftime('%H:%M')} "
                   f"({format_delta(wait_s)})")
        try:
            sleep_until(when, echo=lambda m: typer.echo(m))
        except KeyboardInterrupt:
            # A clean checkpoint at exit 0, so an interrupted wait resumes
            # with the command a planned one would have used.
            mark_paused(ws, outcome, failures or [], when.isoformat(), scope, reason)
            typer.echo(f"\ninterrupted; resume with: llama run resume {ws.name}")
            return False
        return True
    if wait_s > pace.max_wait_s:
        typer.echo(f"  resets in {format_delta(wait_s)} — exceeds "
                   f"--max-wait {format_delta(pace.max_wait_s)}")
    mark_paused(ws, outcome, failures or [], when.isoformat(), scope, reason)
    typer.echo(f"  {resume_prefix}resume with: llama run resume {ws.name}"
               + (f" --max-wait {duration_arg(wait_s)}"
                  if wait_s > pace.max_wait_s else ""))
    return False


def _meter_applies(config: Config, pace: PaceOptions) -> bool:
    """Whether this run has a usage window worth reading at all.

    Gated on the backend because only claude_cli has an account window: the
    fake backend must never read one (it would make the offline suite
    non-deterministic) and openrouter has no `/usage` equivalent. Gated on
    `pace.enabled` too, because `--no-pacing` opts out of the whole feature
    and must not spend a subprocess per show on a reading nothing consults.

    Extracted from `_meter` so the print sites can ask the same question
    without restating it. `_meter` collapses all three ways of getting None
    -- disabled, wrong backend, failed read -- into one value, which is
    right for a caller that only wants the number and wrong for one that
    has to SAY something about it: only a failed read means "the proactive
    gate is blind but the reactive backstop is live", and printing that
    sentence on the other two says something false.
    """
    return pace.enabled and config.llm_for("default").backend == "claude_cli"


def _meter(config: Config, pace: PaceOptions):
    """A live meter reading, or None when there is no window to read.

    Deliberately NOT routed through `pipeline.make_providers`: a meter read
    is not an LLM call and has no business going through the tier/model
    resolution ladder.
    """
    if not _meter_applies(config, pace):
        return None
    return read_usage()


def _reset_label(fc) -> str:
    """How the binding window's reset is written in the pacing line.

    A 5-hour reset is by construction within five hours, so a bare clock
    time is unambiguous and stays exactly as it was. A weekly one can be
    days out, where `07:00` alone reads as "this morning" -- worse than a
    wrong count, because it looks like a bug rather than a weekly ceiling.
    The weekly form therefore carries its date AND names the window: a bare
    `Sep 9 07:00` would still leave the operator wondering why a session
    reset is three days away.

    `{when.day}` rather than `%-d`/`%e`: the first is not portable and the
    second pads to a width, and `Sep  9` in running prose reads as a typo.
    """
    when = fc.resets_at.astimezone()
    if fc.scope == "seven_day":
        return f"the weekly reset, {when:%b} {when.day} {when:%H:%M}"
    return f"{when:%H:%M}"


def _pacing_line(reading, state, pace: PaceOptions) -> str:
    """The one-line meter summary printed at run start and by `llama pacing`.

    Every part after the 5-hour meter is conditional, because each one is a
    thing that may genuinely not be known yet: a reading can arrive without
    the weekly meter, and `per_show_delta` is None until a boundary has been
    observed. Rendering a placeholder for those would read as a measurement.

    No `count` here: `llama pacing` has no run to size the forecast against,
    so the consequence clause ("the remaining N pause until the reset") is
    appended by `_execute`, which does. A formatter that rendered differently
    per caller would be worse than one that does not.
    """
    if reading is None or reading.five_hour is None:
        # Prefixed like every other line this function returns, so the
        # run-start block has one identifiable owner per line. The CLAIM is
        # untouched -- it is only ever printed where the reactive backstop
        # really is live, which is what R19 protected; `_execute` and
        # `llama pacing` both gate the other two None causes upstream.
        return "pacing: usage read unavailable — pacing on limit errors only"
    parts = [f"5h {reading.five_hour.percent}%"]
    if reading.seven_day is not None:
        parts.append(f"weekly {reading.seven_day.percent}%")
    # The account's per-model window, when /usage reported one. Rendered but
    # NOT consulted by `decide` -- see the spec's evidence bar for binding it.
    # Sorted because dict order here is the account's parse order.
    for label, meter in sorted(reading.per_model.items()):
        parts.append(f"{label} {meter.percent}%")
    if state.per_show_delta:
        parts.append(f"est {state.per_show_delta:.1f}%/show")
    # The BINDING window, not the 5-hour one: `decide` checks the weekly
    # first and both ceilings default to 90, so forecasting only the session
    # window printed `weekly 84% ... ~17 fit` where the weekly headroom was
    # one show -- a line contradicting, inches away, the meter beside it.
    fc = binding_forecast(reading, state.per_show_delta, pace)
    if fc is not None and fc.resets_at is not None:
        parts.append(f"~{fc.shows} fit before {_reset_label(fc)}")
    return "pacing: " + " · ".join(parts)


PREFLIGHT_NOTE = "nothing has run yet; resume when the window resets"


def _preflight_gate(ws: RunWorkspace, config: Config, pace: PaceOptions,
                    state, *, note: str = PREFLIGHT_NOTE) -> tuple[bool, object]:
    """Meter, decide, and pause until the window can take the next unit.

    Returns `(proceed, reading)`. `proceed=False` means a checkpoint was
    written and the caller must return. The reading comes back because the
    caller prints its pacing line from it: a second `_meter` call would spend
    another subprocess to print a line that could disagree with the decision
    already taken.

    Sleeps AT MOST ONCE. Nothing completes between naps at a site where no
    work has run, so a second pause passes `stalled=True` -- without it a
    `when` already in the past makes `sleep_until` return immediately and the
    pause becomes a hot spin, which HANGS the suite rather than reddening it.
    No sleep-budget assertion can see that mutation; it is caught only by
    running the pre-flight tests under a hard timeout and reading the exit
    code. Do not "simplify" `stalled=slept` away.
    """
    slept = False
    while True:
        reading = _meter(config, pace)
        verdict = decide(_pacing._now(), reading,
                         Progress(state.per_show_delta), pace)
        if not isinstance(verdict, PauseUntil):
            return True, reading
        # `when=` because the verdict already carries a skewed instant; see
        # PauseUntil's docstring for what recomputing it would cost.
        if not _render_pause(ws, verdict, pace, when=verdict.when,
                             header=f"paused: {verdict}", header_err=True,
                             stalled=slept, note=note):
            return False, reading
        # Re-read and re-decide rather than proceeding on the nap alone: the
        # meter is account-wide, so another session may have spent the window
        # we just waited for, and the reset itself may have moved.
        slept = True


def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False,
             force_stage: str | None = None,
             full_rationale: bool = False, plan: bool = False,
             pace: PaceOptions | None = None) -> None:
    providers = make_providers(config)
    if pace is None:
        pace = pace_options(config)
    # Pre-flight, BEFORE the opening burst: run_discover/run_search/run_winnow
    # each write their artifact only on success, so a refusal part-way through
    # one costs the whole stage on the resume. This is the cheapest place in a
    # run to stop, and the only gate that runs before any of them.
    #
    # The reading is bound and reused, not re-read: the forecast below must
    # describe the same reading this verdict was computed from.
    state = pacing_state.read_state(config.root)
    proceed, reading = _preflight_gate(ws, config, pace, state)
    if not proceed:
        return
    # Proceeding: say what the run is proceeding on. `count` is what makes
    # the consequence clause sayable here and not in `llama pacing`, which
    # has no run to size. NOT used to reduce `count` -- that feeds
    # choose_entries' artist and year caps, so cutting it would change
    # *which* shows are picked, not just how many.
    #
    # Gated on `_meter_applies`, not on `reading is not None`: a None reading
    # under `--no-pacing` or a non-claude_cli backend is the normal steady
    # state, not a degradation, and the unavailable sentence would then be
    # actively false -- with pacing off, a limit FAILS the show (the
    # `except RateLimited` handler below re-raises), so promising "pacing on
    # limit errors only" is a safety net announced at the moment it is gone.
    # A failed read on a paced claude_cli run is the one case worth a line.
    if _meter_applies(config, pace):
        line = _pacing_line(reading, state, pace)
        fc = binding_forecast(reading, state.per_show_delta, pace)
        if fc is not None and fc.shows < count:
            # Names the window for the same reason the forecast does: after
            # "~1 fit before the weekly reset", a bare "the reset" would
            # point at the sooner one the run is not waiting for.
            reset = "weekly reset" if fc.scope == "seven_day" else "reset"
            line += f"; the remaining {count - fc.shows} pause until the {reset}"
        typer.echo(line)
    # The one place raw-output capture is switched on: every provider
    # make_providers built shares this module-level destination.
    set_capture_dir(config.root / "llm-failures")
    # Retried, not merely caught: a limit here used to checkpoint even under
    # `--wait`. The three stages gate on `should_run`, so a retry after the
    # nap re-runs only what did not finish -- cheap for the ones that did.
    slept_stage = False
    # The interactive artist prune below is NOT idempotent and must not be
    # retried: it writes the PRUNED roster to ws.artists, so a second pass
    # re-lists an already-pruned set with fresh 1..N numbering and the same
    # answer selects different artists. Every other test drives auto=True,
    # so only a non-auto run can see it.
    chose_artists = False
    while True:
        try:
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
                if not auto and not chose_artists:
                    chose_artists = True
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
            break
        except RateLimited as exc:
            # BEFORE any `except HerderError`: RateLimited subclasses it, and the
            # reverse ordering silently reverts this to an ordinary stage failure.
            #
            # Covers exactly the three run-level stages inside this try --
            # run_discover, run_search, run_winnow -- and NOT run_interpret,
            # which runs outside `_execute` entirely, at two IN-RUN call
            # sites (`_get_query` and `run_resume`'s criteria-less branch);
            # `profile_add` is a third, outside any run. Both in-run ones go
            # through `_interpret_with_pause`, which is that stage's own copy
            # of this catch; there is no gap here to close.
            #
            # Recoverable, not cheap: those three gate on `should_run` at
            # WHOLE-STAGE granularity, so the resume re-runs the interrupted stage
            # from the top and re-spends the light_research calls it had already
            # made. Per-candidate artifacts are out of scope.
            if not pace.enabled:
                raise
            if not _render_pause(
                    ws, exc, pace, stalled=slept_stage,
                    header=f"paused: {exc}", header_err=True,
                    note="limit hit in discover/search/winnow, before any "
                         "show ran; a resume re-runs that whole stage"):
                return
            slept_stage = True
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
    packaged = held = 0
    failures: list[dict] = []          # {show, error} per show this run lost
    # A RateLimited is a window that refused us; a PauseUntil is one the gate
    # stopped short of. Both pause the run, and the block below renders either.
    limited: RateLimited | PauseUntil | None = None

    def _process(entry):
        nonlocal packaged, held, limited
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force,
                               setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
                               force_stage=force_stage, profile=criteria.profile)
        except RateLimited as exc:
            # Caught BEFORE the HerderError arm below, which it subclasses.
            # Not a failure: nothing is wrong with this show. Its finished
            # stages are on disk and a resume redoes only what is missing.
            if not pace.enabled:
                typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
                failures.append({"show": entry.candidate.performance_id, "error": str(exc)})
                return
            limited = exc
            return
        except (TaskFailed, HerderError, IAError) as exc:
            if isinstance(exc, TaskFailed) and exc.raw_output:
                failure_path = ws.show_ws(entry.candidate.performance_id).dir / "llm-failure.txt"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(exc.raw_output)
            typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
            failures.append({"show": entry.candidate.performance_id, "error": str(exc)})
            return
        if pkg:
            typer.echo(f"packaged: {pkg}")
            packaged += 1
        else:
            typer.echo(f"needs-review, skipped: {entry.candidate.performance_id}")
            held += 1

    def _outcome() -> str | None:
        parts = []
        if packaged:
            parts.append(f"{packaged} packaged")
        if held:
            parts.append(f"{held} held")
        if failures:
            parts.append(f"{len(failures)} failed")
        return ", ".join(parts) if parts else None

    pending = list(chosen)
    done_before_pause = -1                  # progress watermark; see the guard below
    while pending:
        deferred, unprocessed = [], []
        for idx, entry in enumerate(pending):
            # BEFORE the show lock, and before any of this show's work: the
            # whole point is not to start a show the window cannot finish.
            reading_before = _meter(config, pace)
            verdict = decide(_pacing._now(), reading_before,
                             Progress(state.per_show_delta), pace)
            if isinstance(verdict, PauseUntil):
                limited = verdict
                unprocessed.extend(pending[idx:])   # this show has NOT run
                break
            lock_path = ws.show_ws(entry.candidate.performance_id).lock
            ran = True
            try:
                with file_lock(lock_path, blocking=False):
                    _process(entry)
            except Locked:
                deferred.append(entry)         # another run is building it
                ran = False
            # AFTER the call, not before: `pending[idx:]` must INCLUDE the show
            # that hit the limit. Checking at the top of the body instead starts
            # the slice one entry late and silently drops that show from the
            # run, which then reports `complete` having never processed it.
            if limited:
                unprocessed.extend(pending[idx:])
                break
            if ran and reading_before is not None:
                # One show boundary, measured from its own two readings: what
                # the meter moved by while exactly this show ran. A deferred
                # show ran nothing between them, and folding its zero in would
                # teach the gate a cheaper show than any that exists -- an
                # under-estimate being the direction that walks into the wall.
                # A show that was REFUSED is excluded for the same reason, by
                # the `if limited` break above: it did partial work, so its
                # delta understates a whole show.
                #
                # No reading means no window to read -- every openrouter and
                # fake-backend run, and every --no-pacing one. Recording there
                # would fold nothing while still costing a mkdir, a lock and a
                # `pacing-state.json` in a workspace that never paced.
                state = pacing_state.record(config.root, reading_before,
                                            _meter(config, pace))
        if limited:
            unprocessed.extend(deferred)
        else:
            for idx, entry in enumerate(deferred):   # come back and wait
                # Gated like the first pass. It was not, so a show another run
                # held the lock on was the one show that could start on an
                # exhausted window.
                #
                # Deliberately NOT measured as a boundary: this pass takes a
                # BLOCKING lock, so the delta would span an unbounded wait
                # during which the other run spent the meter. That is not this
                # show's cost, and folding it in would teach the gate a show
                # far more expensive than any that exists.
                verdict = decide(_pacing._now(), _meter(config, pace),
                                 Progress(state.per_show_delta), pace)
                if isinstance(verdict, PauseUntil):
                    limited = verdict
                    unprocessed.extend(deferred[idx:])
                    break
                with file_lock(ws.show_ws(entry.candidate.performance_id).lock):
                    _process(entry)
                if limited:
                    unprocessed.extend(deferred[idx:])
                    break
        if not limited:
            break

        # A PauseUntil already holds the instant to come back at, skew
        # included; resume_at reads `resets_at`, which it has not got, so
        # routing one through it silently swaps the reset the meter named
        # for the unknown-reset default. See PauseUntil's docstring for why
        # the fix is here and not a `resets_at` property on it.
        when = (limited.when if isinstance(limited, PauseUntil)
                else resume_at(limited, pace))
        wait_s = (when - _pacing._now()).total_seconds()
        reason = str(limited)
        scope = limited.scope
        # No-progress guard: if a whole pause cycle bought us nothing, sleeping
        # again would nap indefinitely against a backend that keeps refusing.
        # Checkpoint instead, and say WHY so it is not read as an ordinary
        # window pause.
        done_now = packaged + held + len(failures)
        stalled = done_now == done_before_pause
        done_before_pause = done_now
        if not _render_pause(
                ws, limited, pace, when=when, stalled=stalled,
                header=f"paused after {packaged + held} shows: {reason}",
                outcome=_outcome(), failures=failures,
                resume_prefix=f"{len(unprocessed)} shows left; "):
            return
        limited = None
        pending = unprocessed
        continue

    outcome = _outcome()
    # A run that lost shows stays on the attention list (`run list` is
    # state != complete) until a `run resume` finishes cleanly -- otherwise a
    # usage limit or a dropped connection costs shows silently, and the only
    # record of why scrolls off the terminal.
    if failures:
        mark_incomplete(ws, outcome, failures)
    else:
        mark_complete(ws, outcome)


def _interpret_and_stamp(config, ws: RunWorkspace, req: dict) -> Criteria:
    """Interpret a persisted request and stamp its explicit flags.

    ONE function for both entry points -- `_get_query`'s first pass and
    `run resume`'s re-interpret -- because a resume that stamped a different
    set of flags than the original command would replay as a different run,
    silently. Two copies of this is exactly the drift T6b's checkpoint would
    otherwise introduce.
    """
    criteria = run_interpret(ws, make_providers(config)["interpret"], req["query"])
    updates = {}
    # Falsy, not `is not None`: --limit is typer.Option(0, ...), so an
    # unspecified limit persists as 0, and `is not None` would stamp
    # count=0 onto every resumed run.
    if req.get("limit"):
        updates["count"] = req["limit"]
    if req.get("artist_cap") is not None:
        updates["artist_cap"] = req["artist_cap"]
    if req.get("min_score") is not None:
        updates["min_quality_score"] = req["min_score"]
    if req.get("year_cap") is not None:
        updates["year_cap"] = req["year_cap"]
    if updates:
        criteria = criteria.model_copy(update=updates)
        write_artifact(ws.criteria, criteria)
    return criteria


INTERPRET_NOTE = "interpret did not complete; resume when the window resets"


def _interpret_with_pause(config, ws: RunWorkspace, req: dict,
                          pace: PaceOptions) -> Criteria | None:
    """Interpret, pausing instead of dying if the window refuses us.

    The fourth pause site, through the same renderer as the other three:
    same timing arithmetic, same sleep-or-checkpoint rule, same
    KeyboardInterrupt contract. `None` means a checkpoint was written and
    the caller must return, exactly as `_preflight_gate`'s `proceed=False`
    does.

    ONE copy for both entry points -- `_get_query`'s first pass and `run
    resume`'s re-interpret branch -- for the same reason
    `_interpret_and_stamp` is one copy. A resume that hit a limit and died
    would be the very defect T6b removes, on the one command that exists to
    recover from it; a proactive gate that passed a moment ago does not
    stop the next call being refused.

    `pace.enabled` is checked the way `_execute`'s run-level catch checks
    it: `--no-pacing` restores the pre-pacing behaviour at EVERY site, and a
    site that paused anyway would make that flag's promise false.

    Sleeps AT MOST ONCE. Nothing completes between naps at a site where no
    work has run, so a second pause passes `stalled=True` -- without it a
    `when` already in the past makes `sleep_until` return immediately and
    the pause becomes a hot spin. No sleep-budget assertion can see it: the
    spin never calls `_sleep` again.

    What catches it HERE, measured rather than assumed:
    `test_a_limit_during_interpret_sleeps_at_most_once` refuses through a
    provider bounded at `times=99`, so `stalled=stalled` -> `stalled=False`
    exhausts that bound and lands as a RED TEST in under a second -- no
    timeout needed. That bound is deliberate. Unbounding it (`times=10**9`)
    reproduces production instead: the same mutant then HANGS, exit 124
    under `timeout 60`, while restoring the guard passes in 0.5s against
    that same unbounded provider -- so it is the guard, not the bound, that
    stops the spin. Do not "simplify" `stalled=stalled` away, and do not
    unbound the test to "make the pin realistic": that trades a red test
    for a hung suite and pins nothing extra.

    (`_preflight_gate` says the hang version of this and is correct there --
    its tests do not bound the refusal. Same invariant, different evidence.)
    """
    # A profile run is never criteria-less -- `_get_profile` writes
    # criteria.json before anything can fail -- so this branch is
    # unreachable for one today. The guard is here so that if that ever
    # changes it fails loudly rather than asking the LLM to interpret None.
    if req.get("mode", "query") != "query":
        typer.echo(f"cannot re-interpret a {req['mode']} run: "
                   f"{ws.dir} has no criteria.json", err=True)
        raise typer.Exit(1)
    stalled = False
    while True:
        try:
            return _interpret_and_stamp(config, ws, req)
        except RateLimited as limited:
            if not pace.enabled:
                raise
            if not _render_pause(ws, limited, pace,
                                 header=f"paused: {limited}", header_err=True,
                                 stalled=stalled, note=INTERPRET_NOTE):
                return None
            # Re-interpret rather than proceed on the nap alone, for the same
            # reason the pre-flight gate re-reads its meter: nothing this run
            # did has changed, but the account-wide window may have.
            stalled = True


def _get_query(config, ia, ledger, query: str, limit: int, auto: bool, plan: bool,
              name: str | None,
              artist_cap: float | None, min_score: float | None, year_cap: float | None,
              full_rationale: bool, pace: PaceOptions | None = None) -> None:
    """Query mode: today's `find` verbatim (interpret -> stamp explicit flags
    into criteria for replay -> `_execute`)."""
    if artist_cap == 0.0 or year_cap == 0.0:
        typer.echo("--artist-cap/--year-cap must be above 0 "
                   "(a tiny value forces strict rotation; 1.0 disables the cap)", err=True)
        raise typer.Exit(1)
    run_name = name or claim_run_dir(config.root,
                                     f"{date.today().isoformat()}-{slugify(query)[:40]}")
    ws = RunWorkspace(config.root, run_name)
    # Persisted BEFORE the first LLM call: a limit during interpret parks a
    # session whose query would otherwise live only in argv. This artifact is
    # what makes such a session resumable at all (T6b).
    write_artifact(ws.request, json.dumps({
        "mode": "query", "query": query, "profile": None,
        "limit": limit, "artist_cap": artist_cap,
        "min_score": min_score, "year_cap": year_cap,
        "auto": auto, "plan": plan}, indent=2))
    if pace is None:
        pace = pace_options(config)
    # BEFORE interpret, not after: interpret is this run's first LLM call, and
    # until now it was the one call spent with no proactive check at all.
    # `_execute` keeps its own gate -- it has four other entry points.
    proceed, _ = _preflight_gate(ws, config, pace,
                                 pacing_state.read_state(config.root))
    if not proceed:
        return
    criteria = _interpret_with_pause(config, ws, {
        "mode": "query", "query": query, "limit": limit, "artist_cap": artist_cap,
        "min_score": min_score, "year_cap": year_cap}, pace)
    if criteria is None:
        return
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False,
             full_rationale=full_rationale, plan=plan, pace=pace)


def _get_profile(config, ia, ledger, name: str, auto: bool, plan: bool,
                 full_rationale: bool, pace: PaceOptions | None = None) -> None:
    """Profile mode: today's `profile run` verbatim (load profile -> stamp
    count into the run's criteria -> `_execute`)."""
    profile = load_profile(config.root, name)
    ws = RunWorkspace(config.root, claim_run_dir(config.root,
                                                 f"{date.today().isoformat()}-{name}"))
    # The same invocation record `_get_query` writes. Without it a profile
    # run parked by the run-level catch resumes with plan=False and performs
    # a full acquisition -- from the recovery path the CLI itself prints.
    # The query-mode selection flags are None here: a profile run takes those
    # values from its stored criteria, not from argv.
    write_artifact(ws.request, json.dumps({
        "mode": "profile", "query": None, "profile": name,
        "limit": None, "artist_cap": None,
        "min_score": None, "year_cap": None,
        "auto": auto, "plan": plan}, indent=2))
    # Stamp count into the run's criteria: a later `llama run` on this dir
    # must behave like the profile, not the defaults.
    criteria = profile.criteria.model_copy(update={"count": profile.count,
                                                   "profile": name})
    write_artifact(ws.criteria, criteria)
    _execute(config, ia, ledger, ws, criteria, profile.count, auto,
             human_gate=profile.human_gate,
             full_rationale=full_rationale, plan=plan, pace=pace)


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
    wait: bool = typer.Option(None, "--wait/--no-wait",
                              help="On a usage-limit pause: sleep until the window "
                                   "resets (default), or checkpoint and exit"),
    max_wait: str = typer.Option(None, "--max-wait",
                                 help="Never sleep longer than this (default 6h); a "
                                      "longer wait checkpoints instead. e.g. 30h"),
    no_pacing: bool = typer.Option(False, "--no-pacing",
                                   help="Disable usage pacing: a limit fails the show "
                                        "as it did before"),
):
    """Acquire: find, vet, research, and package shows -- one-off (QUERY) or
    a standing profile (--profile NAME). --plan stops after the shortlist
    prints and parks the session for `llama run approve`/`llama run rm`
    instead of processing it."""
    if bool(query) == bool(profile):
        typer.echo("give exactly one of QUERY or --profile", err=True)
        raise typer.Exit(1)
    config, ia, ledger = _setup()
    pace = _pace(config, wait, max_wait, no_pacing)
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
        _get_profile(config, ia, ledger, profile, auto, plan, full_rationale,
                     pace=pace)
        return
    _get_query(config, ia, ledger, query, limit, auto, plan, name,
              artist_cap, min_score, year_cap, full_rationale, pace=pace)


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
        line = f"{s.id:<36} {label:<18} {age:>4}  {_session_criteria_str(s)}"
        if s.outcome:
            line += f"   {s.outcome}"
        if s.state == STATE_PAUSED and s.resume_after:
            line += f"   resumes {s.resume_after}"
        typer.echo(line)
        # One line per show the run lost, mirroring `status`'s flag lines.
        for failure in s.failures:
            typer.echo(f"      - {failure.get('show', '?')}: {failure.get('error', '')}")


@run_app.command("list")
def run_list(
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """List sessions awaiting approval, incomplete, or paused (the
    attention-list); complete sessions never show here."""
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
    wait: bool = typer.Option(None, "--wait/--no-wait",
                              help="On a usage-limit pause: sleep until the window "
                                   "resets (default), or checkpoint and exit"),
    max_wait: str = typer.Option(None, "--max-wait",
                                 help="Never sleep longer than this (default 6h); a "
                                      "longer wait checkpoints instead. e.g. 30h"),
    no_pacing: bool = typer.Option(False, "--no-pacing",
                                   help="Disable usage pacing: a limit fails the show "
                                        "as it did before"),
):
    """Gate 1: show a session's persisted shortlist, approve ranks, then
    optionally process it now."""
    config, ia, ledger = _setup()
    pace = _pace(config, wait, max_wait, no_pacing)
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
                 full_rationale=full_rationale, pace=pace)
    else:
        typer.echo(f"next: llama run resume {ws.name}")


@run_app.command("resume")
def run_resume(
    session: str = typer.Argument(..., help="Session id, unique substring, or path"),
    auto: bool = typer.Option(True, "--auto/--interactive"),
    full_rationale: bool = typer.Option(False, "--full-rationale",
                                        help="Show each shortlisted show's full selection "
                                             "rationale (default: first few lines)"),
    wait: bool = typer.Option(None, "--wait/--no-wait",
                              help="On a usage-limit pause: sleep until the window "
                                   "resets (default), or checkpoint and exit"),
    max_wait: str = typer.Option(None, "--max-wait",
                                 help="Never sleep longer than this (default 6h); a "
                                      "longer wait checkpoints instead. e.g. 30h"),
    no_pacing: bool = typer.Option(False, "--no-pacing",
                                   help="Disable usage pacing: a limit fails the show "
                                        "as it did before"),
):
    """Resume a crashed or incomplete session from its artifacts (stages
    skip work already done). To force a stage re-run (run-wide or per-show),
    use `llama redo --run`."""
    config, ia, ledger = _setup()
    pace = _pace(config, wait, max_wait, no_pacing)
    ws = _resolve_run(config, session)
    if not ws.criteria.exists():
        if not ws.request.exists():
            typer.echo(f"no criteria.json in {ws.dir}", err=True)
            raise typer.Exit(1)
        # Parked before interpret ever succeeded (T6b). The persisted request
        # is enough to re-interpret and carry on -- but this branch spends an
        # interpret call BEFORE `_execute`'s own gate is reached, so gate it
        # here or the one command that exists to recover from a limit pays
        # the very call T6b removed. Only this branch: the ordinary resume
        # reaches `_execute`'s gate with nothing spent ahead of it.
        proceed, _ = _preflight_gate(ws, config, pace,
                                     pacing_state.read_state(config.root))
        if not proceed:
            return
        # ...and catch a refusal on the call itself, not just gate ahead of
        # it: the gate reads an account-wide meter that another session can
        # empty between the reading and the call. A resume that died here
        # would leave the session exactly as parked, having spent the call.
        req = json.loads(ws.request.read_text())
        criteria = _interpret_with_pause(config, ws, req, pace)
        if criteria is None:
            return
    else:
        criteria = read_model(ws.criteria, Criteria)
        # A run parked by the run-level `RateLimited` catch -- in discover /
        # search / winnow -- HAS criteria.json, and that is the LIKELIER
        # place for a `--plan` run to die: interpret is one call, those three
        # are where a window actually empties. So this branch has to read the
        # request too. Guarded, because a run dir predating `--plan` has no
        # request.json at all and must keep resuming exactly as it did.
        req = json.loads(ws.request.read_text()) if ws.request.exists() else {}
    # One expression, both branches. `--plan` means "stop AT the shortlist",
    # so that directive is already SATISFIED once a shortlist exists, and a
    # resume past that point should process normally. Replaying `plan`
    # unconditionally is worse than dropping it: `request.json` carries
    # `plan: true` for the life of the run, so every later `run resume` --
    # including the one `run approve` itself recommends when the operator
    # declines to process immediately -- would re-park the session awaiting
    # and process nothing, permanently.
    #
    # `auto` is deliberately NOT replayed this way: `run resume` has its own
    # explicit `--auto/--interactive` flag, and a persisted value must never
    # override an explicit one. `auto` stays in the request artifact as
    # informational only.
    plan = bool(req.get("plan")) and not ws.shortlist.exists()
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=False,
             force_stage=None,
             full_rationale=full_rationale, plan=plan, pace=pace)


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


def _edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(), add_include=(),
                    narration=None,
                    venue=_UNSET, city=_UNSET, date=_UNSET, set_titles=None,
                    clear_titles=(), set_breaks=_UNSET, clear_set_breaks=False,
                    encore_after=_UNSET, clear_encore=False):
    from llama.workspace import read_overrides

    ov = read_overrides(show_ws)
    # Adding to one list removes the same name from the other, so no call that
    # sets only one of them can leave a file in both -- which is what makes
    # gather's "exclude wins" tiebreak (a defined answer for a hand-mangled
    # overrides.json) unreachable through the CLI.
    #
    # This function does NOT enforce that invariant on its own, and must not be
    # read as if it did: `add_exclude=["a"], add_include=["a"]` in ONE call
    # returns "a" in both lists. The guard that rejects that combination is the
    # caller's -- `fix`'s "--exclude and --include name the same file(s)" check,
    # which runs before this is called and is the only way to reach the case.
    exclude = [f for f in ov.exclude if f not in set(rm_exclude) | set(add_include)]
    for f in add_exclude:
        if f not in exclude:
            exclude.append(f)
    include = [f for f in ov.include if f not in set(add_exclude)]
    for f in add_include:
        if f not in include:
            include.append(f)
    titles = dict(ov.titles)
    for n in clear_titles:
        titles.pop(int(n), None)
    for n, t in (set_titles or {}).items():
        titles[int(n)] = t
    data = ov.model_copy(update={
        "exclude": exclude,
        "include": include,
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
    if clear_encore:
        data = data.model_copy(update={"encore_after": None})
    elif encore_after is not _UNSET:
        data = data.model_copy(update={"encore_after": encore_after})
    write_artifact(show_ws.overrides, data)
    return data


def _unexclude_routing_note(undo: list[str]) -> str:
    """The one sentence both `--include` surfaces use to say a row was routed to
    overrides.exclude instead. Two literals differing only by a slug prefix is
    how the two messages drift apart."""
    return (f"{', '.join(undo)} was operator-excluded, not junk-filtered -- "
            "removed from overrides.exclude rather than added to overrides.include")


def _split_include_targets(show_ws, resolved: list[str]) -> tuple[list[str], list[str]]:
    """Route resolved `--include` targets: `(un-exclude, re-admit)`.

    A row whose reason is `operator-excluded` was never junk-filtered, so
    "re-admitting" it means removing it from `overrides.exclude` -- the
    `--unexclude` case that `--include` folds in. Everything else appends to
    `overrides.include`.

    Shared by `fix --include` and triage's `[i]` deliberately: two surfaces
    reimplementing this split would diverge on the next change to it, exactly
    as `[t]` and `fix --suggest-titles` share `_propose_and_confirm_titles`
    for the same reason. Order within each list follows `resolved`."""
    was_operator = {e["filename"] for e in read_model(show_ws.show, Show).excluded_files
                    if "operator-excluded" in e.get("reasons", [])}
    return ([f for f in resolved if f in was_operator],
            [f for f in resolved if f not in was_operator])


def _split_tokens(tokens) -> list[str]:
    """Flatten repeated flags and comma groups into non-empty tokens.

    The ONE line `_resolve_exclude_tokens` and `_resolve_include_tokens`
    genuinely share. Extracted rather than left duplicated for two reasons:
    the two resolvers must never diverge on how a comma group is read, and
    while the line was byte-identical in both, a mutation anchor addressing
    it matched twice and aborted rather than mutating either (whole-branch
    review). The rest of the two functions stays separate on purpose --
    different predicates, lookup tables, key types and operator-facing error
    strings, which unifying would turn into four parameters and a callback.
    """
    return [p.strip() for tok in tokens for p in str(tok).split(",") if p.strip()]


def _resolve_exclude_tokens(show_ws, tokens) -> list[str]:
    """Expand comma groups and map all-digit tokens to that track's filename
    (via show.json). Non-numeric tokens pass through as filenames."""
    parts = _split_tokens(tokens)
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


_HANDLE = re.compile(r"x\d+")


def _resolve_include_tokens(show_ws, tokens) -> list[str]:
    """Expand comma groups and map `xN` handles to that excluded file's
    filename, via the same `_excluded_handles` numbering `show --tracks`
    prints. Non-handle tokens pass through as filenames.

    Going through `_excluded_handles` rather than indexing
    `show.excluded_files[N-1]` is the whole point: one producer means the
    handle the operator reads and the handle this resolver means cannot
    drift apart."""
    parts = _split_tokens(tokens)
    if not any(_HANDLE.fullmatch(p) for p in parts):
        return parts
    if not show_ws.show.exists():
        raise LlamaError("resolving an x-handle needs show.json; "
                         "reference the file by name instead")
    by_handle = {h: e["filename"]
                 for h, e in _excluded_handles(read_model(show_ws.show, Show))}
    out = []
    for p in parts:
        if _HANDLE.fullmatch(p):
            if p not in by_handle:
                raise LlamaError(
                    f"no excluded file {p} (show has {len(by_handle)} excluded files)")
            out.append(by_handle[p])
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


def _excluded_handles(show) -> list[tuple[str, dict]]:
    """`x`-handles for every file missing from the track list, in show.json
    order — junk-filter drops and the operator's own `overrides.exclude`
    entries alike, since gather appends both to `show.excluded_files`.

    ONE producer, consumed by both the `--tracks` listing and `fix --include`'s
    token resolver, so the handle an operator reads is always the handle the
    resolver means."""
    return [(f"x{i}", e) for i, e in enumerate(show.excluded_files, start=1)]


def _format_tracks(show) -> list[str]:
    # title_source says where a title CAME FROM, not whether it MATCHED. The
    # gd1990-03-29 encore read "tags" -- the most ordinary value there is --
    # while matching nothing, so the only symptom was a hold naming a
    # different song. The two are orthogonal; this column carries the second.
    # the duration column's own "?" (_fmt_dur) means no length in the item
    # metadata. Junk drops such files, so it appears only on a track the
    # operator re-admitted via overrides.include; package.py re-probes the
    # real duration from the downloaded file at package time.
    _MARK = {True: " ", False: "?", None: "-"}
    lines = ["tracks:"]
    for t in show.tracks:
        title = t.title if t.title_source != "unresolved" else "(unknown)"
        # duration before filename so a long filename can print in full without
        # misaligning the numeric column.
        # 14 is the width of the longest title_source, "sibling-format" - at 10
        # it rendered as "sibling-fo". Nothing wider exists: tags 4, setlist 7,
        # sibling 7, override 8, unresolved 10.
        # the `+` sits in its own one-character column rather than sharing the
        # `_MARK` one: re-admission and setlist-match are orthogonal, and a
        # re-admitted track has a match state like any other.
        lines.append(f"  {t.index:2d}.{'+' if t.included else ' '} set {t.set:6.6s} "
                     f"{_MARK[t.matched]} {title:28.28s} "
                     f"{t.title_source:14.14s} {_fmt_dur(t.duration_sec):>6s}  {t.filename}")
    if any(t.matched is False for t in show.tracks):
        lines.append("  ? = no setlist match")
    if any(t.matched is None for t in show.tracks):
        lines.append("  - = not measured")
    if any(t.included for t in show.tracks):
        # NOT "(the junk filter had dropped it)": Track.included means only
        # that the operator NAMED this file in overrides.include. Naming a file
        # the filter would have kept anyway is reachable and unwarned, so that
        # phrasing asserted something untrue on such a row.
        lines.append("  + = ruled in by the operator (overrides.include)")
    handles = _excluded_handles(show)
    if handles:
        lines.append(f"excluded ({len(handles)}):")
        for handle, e in handles:
            # Column order matches the track rows three lines above, for the
            # reason their own comment gives: duration before filename, so a
            # long filename prints IN FULL without misaligning the numeric
            # column. The filename is deliberately UNPADDED -- padding to the
            # widest name made every row as long as the worst one (measured at
            # 121 characters on a real LMA filename), where unpadded only the
            # genuinely long row is long. And it must never be TRUNCATED: this
            # filename is the operator's handle for the dropped file and
            # `--include` accepts it verbatim, so a shortened one is unusable
            # for the exact purpose this listing exists to serve.
            # e.get, never e[...]: a show.json written before this feature has
            # no `duration_sec` key at all, and `show` must render it, not die.
            # .rstrip(): `reasons` can be absent or empty (a pre-feature
            # show.json, or an entry excluded with no recorded reason), which
            # otherwise leaves the row ending in the two-space separator.
            lines.append((f"  {handle:>3s}  {_fmt_dur(e.get('duration_sec')):>6s}  "
                          f"{e['filename']}  "
                          f"{', '.join(e.get('reasons', []))}").rstrip())
    return lines


def _pick_excludes(show) -> tuple[list[str], bool]:
    """Returns `(filenames, wrong_mode)`. `wrong_mode` is True when the operator
    typed an x-handle here, which `_parse_ranks` would otherwise drop silently.

    The caller must return to the PROMPT on `wrong_mode`, not fall through to
    "nothing selected; skipping" and exit the show: telling an operator to use
    `[i]nclude` while ejecting them from the show they would use it on is worse
    than the silence it replaced. A mixed input (`1,x2`) applies NOTHING for the
    same reason -- half-applying it excludes track 1 and loses the `x2` with no
    way to tell that happened."""
    for line in _format_tracks(show):
        typer.echo(line)
    raw = typer.prompt("exclude which track numbers? (comma-separated, empty = none)",
                       default="", show_default=False)
    if any(_HANDLE.fullmatch(t) for t in _split_tokens([raw])):
        typer.echo("x-handles name DROPPED files -- use [i]nclude to re-admit one; "
                   "this prompt takes play-order track numbers")
        return [], True
    picks = _parse_ranks(raw)
    return [t.filename for t in show.tracks if t.index in picks], False


def _pick_includes(show_ws, show) -> list[str]:
    """`[i]nclude`'s counterpart to `_pick_excludes`. Resolution goes through
    `_resolve_include_tokens`, the same producer `fix --include` uses, so the
    handle an operator reads in this listing is the handle both surfaces mean."""
    for line in _format_tracks(show):
        typer.echo(line)
    raw = typer.prompt("re-admit which excluded files? (x-handles or filenames, "
                       "comma-separated, empty = none)", default="", show_default=False)
    return _resolve_include_tokens(show_ws, [raw]) if raw.strip() else []


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
# The `[t]` variant, shown only on a hold flagged `unresolved track titles`
# (see UNRESOLVED_TITLES_FLAG below). Selected per show (not echoed once
# before the loop) -- M1 (task-8 review round 1): the old code printed the
# hint ONCE before the `while True:` loop, so it silently vanished from the
# visible prompt after any `continue` back to it (e.g. a declined proposal,
# or `[m]` with nothing changed) -- the operator would see the bare prompt
# again with no reminder `[t]` was still available.
#
# Derived from `RESOLVE_PROMPT` by inserting the `[t]` option before
# `[s]kip`, rather than a hand-copied literal, so `RESOLVE_PROMPT` is
# actually (not just claimed to be) the single source of truth for the
# common tail -- M2 (task-8 review round 2): the previous hand-copied
# literal meant a sentinel edit to `RESOLVE_PROMPT` passed every test
# without the `WITH_TITLES` variant moving at all; see
# test_resolve_prompt_with_titles_is_derived_from_resolve_prompt.
def _resolve_prompt(*, titles: bool = False, include: bool = False) -> str:
    """The resolve prompt with its two CONDITIONAL options inserted.

    Both are derived from `RESOLVE_PROMPT` by replacement rather than
    hand-copied, so it stays the single source of truth for the common tail --
    the property M2 added a test for after a hand-copied literal let a sentinel
    edit pass every test. `[t]` is offered only under the `unresolved track
    titles` flag and `[i]` only when the show has junk-filtered files, so all
    FOUR combinations are reachable and none may become its own literal.

    `[i]nclude dropped` is placed next to `[e]xclude tracks` rather than before
    `[s]kip`: they are the two halves of one decision about the file list, and
    reading them apart invites the number-vs-handle confusion the picker's own
    hint exists to catch."""
    text = RESOLVE_PROMPT
    if include:
        text = text.replace("[e]xclude tracks", "[e]xclude tracks / [i]nclude dropped")
    if titles:
        text = text.replace("[s]kip", "[t] suggest titles / [s]kip")
    return text


# Must stay byte-for-byte in sync with the literal `gather.py` appends to
# `review_flags` (`stages/gather.py`, ~line 819) -- there is no shared named
# constant on that side, only the inline string, so this comment is the only
# thing keeping the two from drifting apart silently.
UNRESOLVED_TITLES_FLAG = "unresolved track titles"


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
    # Task 8: offered only on a hold this feature can actually help with --
    # `entry.flags` is `derive_state`'s (== `show.review_flags`) for a held
    # show, so this reads it the same way `test_held_beats_everything`
    # pins it, no extra I/O. Read once per show, not re-derived per loop
    # iteration: the only branch that mutates `review_flags` in a way that
    # could change this (a `[t]` adoption) always redoes-and-returns rather
    # than looping back, so it can never go stale within one show's session
    # (see the M3 comment on the `t` branch below for the fuller invariant).
    suggest_titles_offered = UNRESOLVED_TITLES_FLAG in entry.flags
    # `[i]` is offered on the same terms as `[t]`: only when it has something to
    # act on. Read once per show for the same reason -- the only branch that can
    # change `excluded_files` (an `[i]` or `[e]` adoption) redoes and returns
    # rather than looping back, so it cannot go stale within one show's session.
    include_offered = bool(
        entry.ws.show.exists() and read_model(entry.ws.show, Show).excluded_files)
    prompt_text = _resolve_prompt(titles=suggest_titles_offered,
                                  include=include_offered)
    while True:
        choice = typer.prompt(prompt_text, default="s", show_default=False).strip().lower()
        if choice in ("", "s"):
            return
        if choice == "q":
            raise typer.Exit()
        if choice == "e":
            files, wrong_mode = _pick_excludes(read_model(entry.ws.show, Show))
            if wrong_mode:
                continue   # back to the prompt, where [i]nclude is waiting
            if not files:
                typer.echo("nothing selected; skipping")
                return
            _edit_overrides(entry.ws, add_exclude=files)
            stage = "gather"
        elif choice == "i" and include_offered:
            try:
                targets = _pick_includes(entry.ws, read_model(entry.ws.show, Show))
            except LlamaError as exc:
                typer.echo(str(exc), err=True)
                continue   # a bad handle is a typo, not a reason to leave the show
            if not targets:
                typer.echo("nothing selected; skipping")
                return
            # Routing shared with `fix --include` (`_split_include_targets`), not
            # reimplemented: an operator-excluded row un-excludes rather than
            # appending to overrides.include, and two surfaces deciding that
            # separately would diverge on the next change to it.
            undo, readmit = _split_include_targets(entry.ws, targets)
            _edit_overrides(entry.ws, rm_exclude=undo, add_include=readmit)
            if undo:
                typer.echo(_unexclude_routing_note(undo))
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
        elif choice == "t" and suggest_titles_offered:
            # Shares `_propose_and_confirm_titles`/`_propose_titles_for_show`
            # with `fix --suggest-titles` (Task 8) -- deliberately, so this
            # surface and that one can never silently diverge (see both
            # functions' docstrings). `entry.provenance`/`entry.ws.show`
            # guards mirror `fix`'s M7 guard rather than risking an
            # unguarded AttributeError; a held show is normally gathered,
            # but this is defensive, not load-bearing.
            if entry.provenance is None or not entry.ws.show.exists():
                typer.echo(f"{entry.slug}: no provenance.json/show.json to "
                           "propose titles from", err=True)
                continue
            show = read_model(entry.ws.show, Show)
            picks = _propose_and_confirm_titles(ia, config, entry, show)
            if not picks:
                continue   # nothing changed - back to the prompt, same show
            # No `parsed_titles.setdefault(...)` merge here, unlike `fix`'s
            # own adoption -- and that is not a hole (M3, task-8 review
            # round 1): `_propose_and_confirm_titles` only ever returns
            # picks for tracks still `title_source == "unresolved"` (see
            # `_propose_titles_for_show`'s docstring), so there is no
            # already-titled track a same-invocation human edit could be
            # racing against here the way `fix --set-title` can race a
            # proposal on the same track; and `_edit_overrides(set_titles=
            # ...)` itself MERGES into the existing `overrides.titles` dict
            # rather than replacing it (see `_edit_overrides`), so no prior
            # override this show may already carry is lost either.
            _edit_overrides(entry.ws, set_titles=picks)
            stage = "gather"
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
    dropped = f", {len(s.excluded_files)} dropped" if s.excluded_files else ""
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks{dropped})")
    _print_recording_info(sws)
    typer.echo(f"state: {entry.state}   path: {sws.dir}")
    from llama.workspace import read_overrides
    ov = read_overrides(sws)
    parts = []
    if ov.narration != "full":
        parts.append(f"narration={ov.narration}")
    if ov.exclude:
        parts.append(f"exclude={ov.exclude}")
    if ov.include:
        parts.append(f"include={ov.include}")
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
    if ov.encore_after is not None:
        parts.append(f"encore_after={ov.encore_after}")
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
        # Emitted HERE, not inside _format_tracks: only this path has
        # `entry.slug` (a Show carries no slug, so the shared helper could
        # print a literal `<show>` at best), and the helper is also the
        # interactive [e]xclude picker's renderer -- where naming a `llama fix`
        # command to an operator sitting at a play-order-integers prompt is
        # noise. The picker keeps the listing (spec section 4) and loses this.
        handles = _excluded_handles(s)
        if handles:
            typer.echo(f"  re-admit one with: llama fix {entry.slug} "
                       f"--include {handles[0][0]}")


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
            "exclude": ov.exclude, "include": ov.include,
            "narration": ov.narration, "venue": ov.venue,
            "city": ov.city, "date": ov.date, "titles": ov.titles,
            "set_breaks": ov.set_breaks,
            "encore_after": ov.encore_after,
        }
    if show_tracks:
        data["tracks"] = [t.model_dump() for t in s.tracks] if s is not None else None
        data["excluded"] = s.excluded_files if s is not None else None
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


@app.command(rich_help_panel="Watch",
             short_help="Print the usage meters, the learned per-show cost, "
                        "and what fits.")
def pacing() -> None:      # shadows nothing: cli.py imports the pacing module
                           # as `_pacing`, deliberately
    """Show the usage meters, the learned per-show cost, and what fits.

    Read-only, in the shape of `llama pipeline`. Run it before launching to
    decide whether a run fits in the current window.
    """
    config = load_config(_config_path)   # the callback's --config, not the default
    pace = pace_options(config)
    if not _meter_applies(config, pace):
        # `_execute` prints NOTHING in these two cases -- an unsolicited
        # run-start line about a mode the operator chose is noise. Here it is
        # the opposite: this command exists to answer "what is my pacing
        # situation", so silence, or the unavailable sentence (which promises
        # a reactive backstop neither case has), would be the one answer it
        # must not give. The gate is still `_meter_applies`; only the
        # EXPLANATION branches, after it has already said no.
        typer.echo("pacing is off ([pacing] enabled = false) — a usage limit "
                   "will fail the show rather than pause the run"
                   if not pace.enabled else
                   f"no usage window to read on the "
                   f"{config.llm_for('default').backend} backend — pacing "
                   f"applies to claude_cli only")
        return
    state = pacing_state.read_state(config.root)
    reading = _meter(config, pace)
    typer.echo(_pacing_line(reading, state, pace))
    if reading is None:
        return
    verdict = decide(_pacing._now(), reading, Progress(state.per_show_delta), pace)
    typer.echo("would proceed" if isinstance(verdict, Proceed)
               else f"would pause: {verdict.reason}")


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


def _destination_is_voiced(out: Path) -> bool:
    """True when `out/manifest.json` is a JSON object whose `dj_audio` is
    non-null -- emcee's mark that it voiced this delivered package. Read as
    raw JSON (llama never imports emcee); anything unreadable or not an
    object counts as not voiced."""
    try:
        m = json.loads((out / "manifest.json").read_text())
    except (OSError, ValueError):
        return False
    return isinstance(m, dict) and m.get("dj_audio") is not None


def _replace_destination(pkg: Path, out: Path, target_dir: Path) -> None:
    """Swap a fresh copy of `pkg` in for `out` wholesale: stage a sibling
    temp copy, move the old destination aside, rename the copy into place,
    then delete the old one. A failure before the swap removes the temp dir
    and leaves `out` untouched. The dot-prefixed siblings are skipped by
    emcee's scans."""
    from uuid import uuid4

    tmp = target_dir / f".{out.name}.deliver-{uuid4().hex}"
    old = target_dir / f".{out.name}.old-{uuid4().hex}"
    try:
        shutil.copytree(pkg, tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    out.rename(old)
    try:
        tmp.rename(out)
    except BaseException:
        old.rename(out)           # put the original back
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _deliver_one(config, ledger, entry, dest, replace_voiced=False) -> Path:
    """Copy one resolved show's package to `dest` (or config.delivery_path)
    and record the delivery in the ledger; returns the destination path.
    Raises LlamaError on refusal -- no destination, a deliver-gate
    refusal from `catalog.deliver_refusals` (none of its three legs is
    overridable), or a destination emcee has already voiced (re-delivering
    would silently un-voice it) unless `replace_voiced`, which replaces it
    wholesale with a fresh, unvoiced copy."""
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
        if _destination_is_voiced(out):
            if not replace_voiced:
                raise LlamaError(
                    f"refusing to deliver {entry.slug}: {out} is already voiced "
                    "by emcee; re-delivering would un-voice it (pass "
                    "--replace-voiced to replace it with a fresh, unvoiced copy)")
            _replace_destination(pkg, out, target_dir)
        else:
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


def _deliver_batch(config, ledger, sel, dest, yes, replace_voiced=False) -> None:
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
            out = _deliver_one(config, ledger, e, dest, replace_voiced)
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
    replace_voiced: bool = typer.Option(
        False, "--replace-voiced",
        help="Replace a destination emcee has already voiced with a fresh, "
             "unvoiced copy (discards its DJ script and audio)"),
):
    """Copy a show package to the station's watched folder and record delivery.

    Requires a clean package: packaged, file-complete, and not held for
    review. None of these three legs is overridable. A destination emcee has
    already voiced is refused (re-delivering would un-voice it) unless
    --replace-voiced, which swaps in a fresh, unvoiced copy.
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
            out = _deliver_one(config, ledger, entry, dest, replace_voiced)
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
    _deliver_batch(config, ledger, sel, dest, yes, replace_voiced)


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


def _format_proposal_row(r) -> str:
    """Render one `ProposalRow` for `_propose_titles_for_show`'s proposal
    table. Extracted into its own function (Task 8 review finding A3) so
    the margin/forced/filler trichotomy (see `models.ProposalRow`'s
    docstring) can be pinned directly against synthetic rows: the ymsb
    fixture this module's tests otherwise share never produces a forced
    row (its setlist has no segues, so every row is either matched with a
    real margin or filler), so a collapse of the `forced` label into the
    filler dash previously left the whole suite green -- the same
    forced/filler collapse a Task 5 correspondence.py test exists to
    prevent, silently reintroduced one layer up at render time."""
    shown = r.title or "(unresolved - hand-edit)"
    if r.margin_sec is not None:
        margin = f"{r.margin_sec:5.0f}s"
    elif r.forced:
        # No alternative assignment exists for this track/item count --
        # a RIGIDITY signal, not a correctness one (see the trichotomy
        # comment on models.ProposalRow.forced). A no-segue, one-track-
        # per-item setlist is forced on EVERY row, and that is exactly
        # the unanchored regime measured 45-52% wrong -- so this column
        # must never look like a confidence score. A blank/dash would
        # read as "no signal, presumably fine"; the explicit "forced"
        # label reads as "no signal, unverified", which is the honest
        # claim. It is deliberately NOT rendered as a large/high margin
        # (e.g. as if margin_sec were +inf) -- that would flatter a
        # forced row as if it had cleared a real comparison.
        margin = "forced"
    else:
        # Filler (item_span is None): no canonical item was assigned to
        # this track at all, so a margin is not applicable.
        margin = "     -"
    return (f"  {r.index:2d}. {_fmt_dur(r.duration_sec):>6s} "
            f"{margin:>6s}  {shown}")


def _sibling_donor_coverage(rows, canonical) -> tuple[int, int]:
    """How many ADOPTED sibling rows embed in the canonical setlist -- the
    "tested fallback, useful evidence, known-insufficient guard" figure the
    design spec calls for on a no-anchors proposal (it missed gd1982-10-10 at
    92%, hence the head-row caution alongside it, not instead of it). A row
    embeds when any component of its (possibly merged, "A > B") proposed
    title loosely matches some canonical item -- this is corroborating
    evidence, not a second alignment, so it does not need to be at the same
    position."""
    from llama.structure import loosely_same_title
    adopted = [r for r in rows if r.verdict == "adopt" and r.proposed]
    if not adopted:
        return 0, 0
    item_titles = [it.title for it in canonical.items]
    hits = 0
    for r in adopted:
        comps = [c.strip() for c in r.proposed.split(" > ")]
        if any(loosely_same_title(c, it) for c in comps for it in item_titles):
            hits += 1
    return hits, len(adopted)


def _sibling_canonical_text(title: str, canonical) -> str:
    """The canonical setlist's own text for `title` (the sibling's proposal,
    or the tape's own disagreeing tag), when one of its components loosely
    matches a canonical item -- the three-way disagreement display's
    "setlist:" column, from the already-built canonical. "" when nothing
    matches (spec: "blank when absent")."""
    from llama.structure import loosely_same_title
    if not title:
        return ""
    comps = [c.strip() for c in title.split(" > ")]
    for it in canonical.items:
        if any(loosely_same_title(c, it.title) for c in comps):
            return it.title
    return ""


def _format_sibling_proposal_row(r) -> str:
    """One sibling-arm `ProposalRow`, the counterpart of `_format_proposal_row`
    for the canonical DP. Kept as a separate formatter rather than branching
    inside one: the two row shapes carry different evidence (residual
    seconds and a per-row decline note here; margin/forced there), and a
    shared formatter would need a third trichotomy neither row actually has.

    Fix round 1 (I2/m1): the per-row `note` is deliberately NOT rendered
    inline here any more -- `_sibling_run_reasons` prints it once per
    contiguous run instead, so a long declined run reads as one reason line
    rather than the same bracket repeated on every row (the "checkerboard"
    a reviewer mutation exposed: 24 identical brackets, one per row)."""
    shown = r.title or "(unresolved - hand-edit)"
    resid = f"{r.residual_sec:5.0f}s" if r.residual_sec is not None else "     -"
    return f"  {r.index:2d}. {_fmt_dur(r.duration_sec):>6s} {resid:>6s}  {shown}"


def _sibling_run_reasons(prop_rows) -> list[tuple[int, int, str]]:
    """Contiguous `prop_rows` sharing the IDENTICAL decline `note`, collapsed
    to one reason per run -- fix round 1, I2/m1: "declined runs printed with
    their reason line, not silent holes" means one line per run, not the
    same bracket repeated on every row of it (a reviewer-verified
    "checkerboard" hazard: cplus_filter's own reason text, applied under
    mutation A, printed `[tracks 1-24: not bracketed by agreeing anchors]`
    24 times).

    Adopted rows (empty `note`) never start or extend a run. Two declined
    rows with genuinely DIFFERENT notes (e.g. two different weak-evidence
    penalties) are deliberately NOT collapsed together -- only an exact text
    match extends a run, so this never hides a real difference to save a
    line. Returns `(lo, hi, note)` with `lo`/`hi` 0-based positions into
    `prop_rows` (not `.index` -- the caller reads `.index` off the endpoints
    itself, the same half-open-adjacent convention `structure.unresolved_runs`
    uses for its own inclusive `[lo, hi]` runs)."""
    runs: list[tuple[int, int, str]] = []
    lo: int | None = None
    prev_note = ""
    for i, r in enumerate(prop_rows):
        declined_with_note = bool(r.note) and not r.title
        if declined_with_note and lo is not None and r.note == prev_note:
            continue                                   # extend the current run
        if lo is not None:
            runs.append((lo, i - 1, prev_note))
        lo, prev_note = (i, r.note) if declined_with_note else (None, "")
    if lo is not None:
        runs.append((lo, len(prop_rows) - 1, prev_note))
    return runs


def _sibling_proposal(ia, entry, show, cand, want, meta, events, canonical):
    """Task 6's entry seam: the sibling-transfer arm of
    `_propose_titles_for_show`, attempted BEFORE the canonical correspondence
    DP. Loads donors exactly as `gather._sibling_transfer` does and picks the
    same winner it would (`gather.best_donor` -- fix round 1, I5: this used
    to re-derive "which donor wins" with its own copy of `propose_rows` ->
    `rate_alignment` -> `_donor_key` -> sort, and a reviewer mutation that
    reversed the CLI's own sort (picking the WORST donor) passed the whole
    suite. `best_donor` is the one definition now, and its extraction also
    removes the need to import `_donor_key` privately across the module
    boundary -- `show_metadata_norms` is `gather`'s other cross-boundary
    dependency, promoted to public for the identical reason fix round 1's
    reviewers gave (matching Task 3's `structure.hygienic_title` precedent):
    a leading underscore imported by another module is a false promise that
    the symbol is free to rename or re-signature.

    Returns `(prop, picks)` when the winning pair reaches the operator,
    auto, or no-anchors band -- the three bands this surface exists to
    serve -- AND produces at least one pick. Returns None on a declined pair
    (evidence of a BAD alignment, not weak evidence of a good one -- gather's
    own note), when no donor loads at all, or when the winning pair's own
    picks are EMPTY (fix round 1, I6 -- a spec-compliance finding: an
    operator-band donor untagged on exactly this tape's unresolved tracks
    used to preempt the canonical DP with a table nobody could adopt from,
    silencing a fallback that might have proposed real titles for those
    same tracks). Any of these three cases falls through to the canonical
    correspondence DP UNCHANGED -- the sibling table, if one was built, has
    already been echoed as a side effect by the time this returns None, so
    an operator still sees it even when the caller discards the return
    value and shows the DP's table underneath.

    THE RENDERER NEVER CALLS `cplus_filter` -- spec invariant 1, quoted
    verbatim: "applied to the renderer it would show an untagged tape
    nothing -- C+ gates adoption, never display." C+ only ever runs inside
    `gather`, at automatic-adoption time; every row `propose_rows` produced
    for the winning donor is rendered here, whatever band the pair reached,
    including rows an operator-band or no-anchors-band donor would never
    have reached C+ for at all.
    """
    from llama.models import ProposalRow, TitleProposal
    from llama.stages.gather import best_donor, show_metadata_norms

    metadata_norms = show_metadata_norms(show.artist, cand, meta, events)
    donor, rows, res, notes = best_donor(ia, cand, show.identifier, want,
                                         show.tracks, metadata_norms)
    for note in notes:      # m4: a donor that existed and failed to fetch is
        typer.echo(f"  {note}")  # otherwise indistinguishable from no donor at all
    if donor is None:
        return None
    if res.band not in ("operator", "auto", "no-anchors"):
        return None    # declined -- fall through to the canonical DP

    prop_rows = []
    picks: dict[int, str] = {}
    for row in rows:
        is_adopt = row.verdict == "adopt"
        # I4 (fix round 1): a declined row's OWN title column stays blank --
        # `picks` below gates on `is_adopt` directly (the raw SiblingRow
        # verdict), never on whether `ProposalRow.title` happens to be
        # truthy, so a future change to what renders in `title` can never
        # leak a declined title into `overrides.titles` by itself. What the
        # SiblingRow docstring asks for -- "the operator path can render
        # what the DP thought" on a weak-evidence decline -- is honoured in
        # `note` instead, which never feeds `picks`.
        note = row.reason
        if not is_adopt and row.proposed:
            note = f"{row.reason} - DP proposed {row.proposed!r}"
        prop_rows.append(ProposalRow(
            index=row.track, duration_sec=show.tracks[row.track - 1].duration_sec,
            title=(row.proposed if is_adopt else ""),
            evidence="sibling-align", residual_sec=row.residual_sec, note=note))
        if is_adopt and show.tracks[row.track - 1].title_source == "unresolved":
            picks[row.track] = row.proposed
    prop = TitleProposal(rows=prop_rows, feasible=True, evidence_source="sibling-align")

    typer.echo(f"{entry.slug}: proposal (sibling-align, donor {donor.identifier}, "
               f"band {res.band})")
    for r in prop_rows:
        typer.echo(_format_sibling_proposal_row(r))
    for lo, hi, note in _sibling_run_reasons(prop_rows):
        label = (f"track {prop_rows[lo].index}" if lo == hi
                else f"tracks {prop_rows[lo].index}-{prop_rows[hi].index}")
        typer.echo(f"  {label}: {note}")

    if res.disagreements:
        typer.echo("  anchor disagreements (tape / sibling / setlist):")
        for d in res.disagreements:
            setlist_title = _sibling_canonical_text(d.proposed, canonical)
            typer.echo(f"    t{d.track} tape: {d.tape_title!r} | "
                      f"sibling: {d.proposed!r} | setlist: {setlist_title!r}")

    if res.band == "no-anchors":
        hits, total = _sibling_donor_coverage(rows, canonical)
        pct = f"{hits / total:.0%}" if total else "n/a"
        typer.echo(f"  no independent anchors on this tape -- donor {donor.identifier}, "
                   f"embeds in canonical setlist: {hits}/{total} ({pct})")
        typer.echo("  caution: check track 1 by ear before confirming -- the one "
                   "measured miss on this path was a head-banner title shifted "
                   "onto the tape's first track")

    if not picks:
        # I6: nothing this arm proposed is actually adoptable (e.g. an
        # operator-band donor untitled on exactly the unresolved tracks) --
        # fall through so the canonical DP still gets a chance, rather than
        # preempting it with a table nobody can confirm anything from. The
        # table above has already been echoed, so it is not lost, only not
        # authoritative.
        return None
    return prop, picks


def _propose_titles_for_show(ia, config, entry, show):
    """Build the canonical setlist and render a title-correspondence
    proposal for `show`'s tracks. `build_canonical` is always called with
    `provider=None` -- this CLI path must never fire an LLM call, since the
    correspondence DP is proposal-only and a human confirmation is the only
    thing standing between a proposed title and adoption (see
    correspondence.py's module docstring: unanchored monotone correspondence
    measured 45-52% wrong).

    `setlistfm=make_client(config)` and the real jerrybase `events` are
    threaded through so the canonical this proposal is built from matches
    what the `gather` redo the confirmation triggers will itself use --
    reviewer-caught gap: an earlier draft passed `setlistfm=None,
    events=[]` unconditionally, which meant an operator with a setlist.fm
    key configured would confirm a proposal built from a strictly weaker
    LMA-only canonical than the one `gather` actually consumes. `kept` is
    filtered against `entry.overrides.exclude` for the same reason (Task 8
    review finding A1): `run_gather` drops excluded files from `kept`
    *before* calling `build_canonical` (gather.py), so on a show with prior
    exclusions an unfiltered `kept` here could rank a different winning
    parse (`rank_parses(..., target_count=len(kept))` feeds the `plausible`
    tier) than the redo the confirmation triggers will itself compute.
    `entry.overrides` (not a fresh `read_overrides` call) is deliberate, and
    relies on a different invariant per caller (M3, task-8 review round 1
    -- spelled out here rather than left implicit, since it's easy to
    silently invalidate by changing control flow elsewhere):
    - `fix --suggest-titles`: every invocation resolves `entry` once at the
      top of `fix`, and `--suggest-titles` refuses to combine with
      `--exclude`/`--unexclude` in the same invocation, so nothing in that
      same call can change `overrides.exclude` between resolution and use.
    - `triage`'s `[t]` resolution: each `entry` comes from one
      `iter_shows`/`resolve_show` call feeding exactly one
      `_interactive_resolve(..., entry)`, and inside that function every
      choice that WRITES overrides (`e`/`m`/`v`/`o`/`t`) redoes and
      `return`s immediately rather than looping back -- so `entry` is
      never reused across a write. **This is load-bearing on `[e]` staying
      non-looping**: if `[e]` were ever changed to loop back to the prompt
      the way `[m]` does on "nothing changed", a `[t]` chosen afterward in
      that same session would read a stale `entry.overrides.exclude`,
      reopening exactly the silent-wrong-title hazard the `--suggest-titles
      --exclude` refusal (I2) exists to prevent on the `fix` side.

    Returns `(prop, picks)`: the raw `TitleProposal` (so a caller can read
    `.feasible`/`.reason` without re-deriving it) and `picks` -- track
    number -> title, for exactly the rows both proposed AND still
    `title_source == "unresolved"` on `show` (a track that already carries a
    real title is never silently overwritten by a proposal -- reviewer
    mutation-verified: deleting this clause leaves the rest of the suite
    green, see test_never_clobbers_a_track_that_already_has_a_title).
    Rendering only: an operator confirmation and the actual
    `overrides.titles` write stay the caller's job, so Task 8 can wire this
    same helper into `llama triage`'s interactive walkthrough as a pure
    wiring change rather than a refactor of this function.

    Module-level rather than inlined in `fix` for the same reason.
    """
    from llama import jerrybase
    from llama.correspondence import propose_titles, sibling_item_durations
    from llama.junk import FORMAT_BY_AUDIO, filter_files
    from llama.models import TitleProposal
    from llama.setlistfm import make_client
    from llama.stages.gather import build_canonical

    cand = entry.provenance.candidate
    meta = ia.metadata(show.identifier).get("metadata", {})
    want = FORMAT_BY_AUDIO[config.audio_format]
    # `readmit=` is not optional here: gather applies overrides.include INSIDE
    # filter_files, so a recomputation without it is one file short of every
    # correctly-gathered show that has an effective include -- and the C1 guard
    # below then declines forever, blaming a stale show.json that is in fact
    # exactly what gather just wrote. Both reviewer seats found this
    # independently on the whole-branch review; pinned by
    # test_suggest_titles_survives_an_effective_overrides_include.
    kept, _, _ = filter_files(ia.metadata(show.identifier).get("files", []),
                              want_format=want,
                              readmit=frozenset(entry.overrides.include))
    if entry.overrides.exclude:
        drop = set(entry.overrides.exclude)
        kept = [f for f in kept if f["name"] not in drop]
    # C1 (final review): `kept` is recomputed here straight from
    # `ia.metadata` + `entry.overrides.exclude`, but `show.tracks` is
    # whatever `show.json` last had `gather` write -- NOT re-derived. Those
    # two agree only when the most recent `gather` redo already saw the
    # current `overrides.exclude` (and cache). When they disagree (an
    # `--exclude`/`--unexclude` staged with `--no-run`, or a redo that died
    # after `_edit_overrides` wrote `overrides.json` but before `gather`
    # completed, or a refreshed metadata cache changing the file list), the
    # DP below still runs over `show.tracks`' STALE 1-based numbering while
    # `overrides.titles` gets applied post-exclusion by `gather` -- a
    # confirmed proposal then writes titles onto the wrong tracks with no
    # error and no flag (reproduced end to end: three titles landed on three
    # wrong files). Comparing the filename LISTS, not just lengths, also
    # catches the metadata-cache-refresh case, where lengths could still
    # match by coincidence. This must be a hard decline, not a warning --
    # nothing downstream can tell a stale proposal from a fresh one.
    kept_names = [f["name"] for f in kept]
    track_names = [t.filename for t in show.tracks]
    if kept_names != track_names:
        reason = (f"show.json is stale relative to overrides.json "
                  f"({len(kept_names)} files kept, {len(track_names)} tracks on disk) "
                  f"- run `llama redo {entry.slug} --from gather` first")
        prop = TitleProposal(feasible=False, reason=reason)
        typer.echo(f"{entry.slug}: {prop.reason}")
        return prop, {}
    events = jerrybase.lookup(show.artist, cand.date) if config.jerrybase.enabled else []
    canonical = build_canonical(ia, cand, show.identifier, meta, kept, show.artist, events,
                                setlistfm=make_client(config), provider=None).setlist

    # Task 6: the sibling-transfer arm, attempted BEFORE the canonical DP.
    # `canonical` is already built above -- needed either way, since the
    # sibling arm's own disagreement/coverage display reads it too -- so
    # trying the sibling arm first costs nothing extra when it declines.
    sib = _sibling_proposal(ia, entry, show, cand, want, meta, events, canonical)
    if sib is not None:
        return sib

    prop = propose_titles(
        show.tracks, canonical,
        item_durations=sibling_item_durations(ia, cand, show.identifier, canonical, want))
    if not prop.feasible:
        typer.echo(f"{entry.slug}: {prop.reason}")
        return prop, {}

    typer.echo(f"{entry.slug}: proposal ({prop.evidence_source})")
    for r in prop.rows:
        typer.echo(_format_proposal_row(r))

    picks = {r.index: r.title for r in prop.rows
             if r.title and show.tracks[r.index - 1].title_source == "unresolved"}
    return prop, picks


def _propose_and_confirm_titles(ia, config, entry, show) -> dict[int, str] | None:
    """The propose -> render -> confirm surface shared by `fix
    --suggest-titles` and `triage`'s `[t] suggest titles` resolution
    (Task 8) -- factored out so the two surfaces cannot silently diverge
    (a divergence here would be invisible: both read the same proposal,
    but only one code path would echo/gate it). Returns the picks dict
    (track number -> title) the operator confirmed, or None when there is
    nothing to adopt -- infeasible proposal, no picks, or a declined
    confirmation, each of which has already echoed its own reason. Every
    caller must treat None as "nothing changed", not as an error."""
    prop, picks = _propose_titles_for_show(ia, config, entry, show)
    if not prop.feasible:
        return None   # _propose_titles_for_show already echoed prop.reason
    if not picks:
        typer.echo("nothing to adopt: every track already has a title")
        return None
    if not typer.confirm(f"write {len(picks)} titles into overrides?"):
        typer.echo("declined; nothing written")
        return None
    return picks


@app.command(rich_help_panel="Fix & ship",
             short_help="Edit a show's overrides / resolve its hold, then auto-run the redo.")
def fix(
    name: str = typer.Argument(..., help="Show slug, unique substring, or path"),
    exclude: list[str] = typer.Option(
        None, "--exclude", help="Add source filenames (or track numbers) to overrides.exclude"),
    unexclude: list[str] = typer.Option(
        None, "--unexclude", help="Remove filenames (or track numbers) from overrides.exclude"),
    include: list[str] = typer.Option(
        None, "--include",
        help="Re-admit a file missing from the track list: an x-handle from "
             "`llama show <show> --tracks` (e.g. x1) or the source filename. "
             "A junk-filter drop is added to overrides.include; a row you "
             "excluded yourself is un-excluded instead."),
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
    set_encore: str = typer.Option(
        None, "--set-encore",
        help="Mark the encore: it begins after track N (same convention as --set-breaks). "
             "On a multi-set show, combine with --set-breaks -- the override path replaces "
             "alignment entirely rather than adding to it, so --set-encore alone flattens "
             "every earlier set into set 1. Any structure override loses every segue; "
             "combining the flags does not bring segues back."),
    clear_encore: bool = typer.Option(
        False, "--clear-encore", help="Clear the encore override"),
    suggest_titles: bool = typer.Option(
        False, "--suggest-titles",
        help="Propose titles for unresolved tracks from the setlist and, on "
             "confirmation, write them all into overrides.titles at once"),
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
    encore_val = None
    if set_encore:
        if not set_encore.strip().isdigit():
            typer.echo(f"--set-encore expects a track number, got {set_encore!r}", err=True)
            raise typer.Exit(1)
        encore_val = int(set_encore.strip())

    if suggest_titles:
        # I2 (review round 1): the proposal is computed over the CURRENT
        # track list, but a same-invocation --exclude/--unexclude renumbers
        # tracks (titles.py's index=pos+1 over the post-exclusion kept
        # list), while overrides.titles is applied by that same 1-based
        # position (gather.py). Any picked index still in range after the
        # renumbering would land on the wrong track with no error -- exactly
        # the silent-wrong-title failure this whole feature exists to
        # prevent. Refuse the combination outright rather than trying to
        # re-derive the post-exclusion numbering here.
        if exclude or unexclude or include:
            # C1 (final review): naming only "run the exclusion first, then
            # --suggest-titles" used to be the attack path INTO C1 -- an
            # operator following it literally via `--exclude ... --no-run`
            # staged overrides.json without ever re-running gather, so the
            # second invocation's `show.tracks` was stale relative to the
            # exclusion. The C1 fix makes that second invocation refuse
            # rather than silently misnumber, but the remedy this message
            # names must actually finish the job in one pass: the exclusion
            # has to be followed by a real `gather` redo, not just staged,
            # before --suggest-titles can see a consistent track list.
            # The remedy is the half an operator copies, so it names the flag
            # they actually typed rather than a hardcoded --exclude: being told
            # to re-run "--exclude ..." after typing --include is not a remedy.
            typed = " ".join(f"{flag} ..." for flag, given in
                             (("--exclude", exclude), ("--unexclude", unexclude),
                              ("--include", include)) if given)
            typer.echo(
                "--suggest-titles cannot be combined with "
                "--exclude/--unexclude/--include: "
                "a file edit in the same invocation renumbers tracks before the "
                "proposal's numbering would apply. Run the file edit first and let "
                f"it redo (`llama fix {entry.slug} {typed}` without --no-run, "
                f"or `--no-run` followed by `llama redo {entry.slug} --from gather`), "
                "then --suggest-titles as a separate invocation.", err=True)
            raise typer.Exit(1)
        if not sws.show.exists():
            typer.echo(f"no show.json in {sws.dir} (state: {entry.state})", err=True)
            raise typer.Exit(1)
        if entry.provenance is None:
            # M7 (review round 1): match the two nearest analogues --
            # _redo_show (raises LlamaError, caught by callers) and triage's
            # own guard -- rather than an unguarded AttributeError on
            # `entry.provenance.candidate` inside the helper below.
            typer.echo(f"no provenance.json in {entry.ws.dir} - "
                       "reprocess it via its run first", err=True)
            raise typer.Exit(1)
        show = read_model(sws.show, Show)
        # I1 (review round 1): the outcomes handled inside
        # _propose_and_confirm_titles used to always exit 0 immediately,
        # silently discarding any OTHER edit flag given in the same
        # invocation (worst case: `--suggest-titles --overrule` on a
        # declined proposal reads as exit 0 = "hold cleared" when it was
        # not). Only exit early when suggest-titles was the ONLY edit flag
        # given; otherwise warn and fall through to the remaining edits
        # below. `exclude`/`unexclude`/`include` are omitted from this check
        # -- the guard above already exits before this point whenever any of
        # them is set.
        other_edit_requested = bool(
            set_venue or set_city or set_date or parsed_titles or clear_title_nums
            or set_breaks or clear_set_breaks or set_encore or clear_encore
            or narration is not None or overrule)
        picks = _propose_and_confirm_titles(ia, config, entry, show)
        adopted = False
        if picks:
            # M10 (review round 1): an explicit --set-title on the same
            # invocation must win over a generated proposal for the same
            # track -- the same human-authority principle the confirmation
            # gate itself protects. `setdefault` never overwrites a key
            # `parsed_titles` already carries from --set-title parsing above.
            for idx, title in picks.items():
                parsed_titles.setdefault(idx, title)
            adopted = True
        if not adopted:
            if not other_edit_requested:
                raise typer.Exit(0)
            typer.echo("proposal not adopted; continuing with the other edit flag(s) given")

    did_files = bool(exclude or unexclude or include)
    did_meta = bool(set_venue or set_city or set_date or parsed_titles
                    or clear_title_nums or set_breaks or clear_set_breaks
                    or set_encore or clear_encore)
    did_narration = narration is not None

    if not (did_files or did_meta or did_narration or overrule):
        typer.echo("nothing to fix: give an edit flag (see --help), or inspect with: "
                   f"llama show {entry.slug}", err=True)
        raise typer.Exit(1)

    if not sws.show.exists():
        typer.echo(f"no show.json in {sws.dir} (state: {entry.state})", err=True)
        raise typer.Exit(1)

    real_edit = False
    if did_files:
        try:
            add = _resolve_exclude_tokens(sws, exclude or [])
            rm = _resolve_exclude_tokens(sws, unexclude or [])
            inc = _resolve_include_tokens(sws, include or [])
        except LlamaError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        clash = sorted(set(add) & set(inc))
        if clash:
            typer.echo("--exclude and --include name the same file(s): "
                       f"{', '.join(clash)}", err=True)
            raise typer.Exit(1)
        undo, readmit = _split_include_targets(sws, inc)
        ov = _edit_overrides(sws, add_exclude=add, rm_exclude=list(rm) + undo,
                             add_include=readmit)
        if undo:
            # The operator typed --include and would otherwise be told only that
            # overrides.EXCLUDE changed -- true, but it does not answer "what did
            # my flag do?". Name the folded-in --unexclude routing explicitly.
            typer.echo(f"{entry.slug}: {_unexclude_routing_note(undo)}")
        # Gated on what the operator TYPED, not on what it resolved to: an
        # exclude-side flag that resolves to nothing (`--exclude ,`) is still
        # an exclude-side request, still redoes from gather, and printed the
        # list before this feature existed. Gating on `add or rm` silenced it
        # (whole-branch review M2). `undo` is here because `--include` on an
        # operator-excluded row edits overrides.exclude.
        if exclude or unexclude or undo:
            typer.echo(f"{entry.slug}: overrides.exclude = {ov.exclude} "
                       "(the hold clears itself if a clean re-gather results)")
        if readmit:
            typer.echo(f"{entry.slug}: overrides.include = {ov.include} "
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
            clear_set_breaks=clear_set_breaks,
            encore_after=encore_val if set_encore else _UNSET,
            clear_encore=clear_encore)
        typer.echo(f"{entry.slug}: metadata override updated")
        real_edit = True

    if not real_edit:
        return   # e.g. a lone --overrule on a show that was never held

    stage = "gather" if (did_files or did_meta) else ("brief" if did_narration else "package")
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
    exclude tracks, edit metadata, accept vague narration, overrule the
    hold, or (only on a hold flagged "unresolved track titles") suggest
    titles from the setlist correspondence, confirm, and adopt them all at
    once. Always interactive: requires a TTY."""
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
        except (LlamaError, TaskFailed, HerderError, IAError) as exc:
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


_ATTENTION_LABELS = {STATE_AWAITING: "awaiting approval", STATE_INCOMPLETE: "incomplete",
                     STATE_PAUSED: "paused"}
_ATTENTION_HINTS = {STATE_AWAITING: "llama run approve {id}", STATE_INCOMPLETE: "llama run resume {id}",
                    STATE_PAUSED: "llama run resume {id}"}


def _session_json(s) -> dict:
    # Carries everything the human table renders, `resumes <instant>`
    # included: a consumer reading state="paused" out of `run list --json`
    # has nothing else to answer "when may this be retried?" with, and the
    # table already answers it. Both keys are always present and null off a
    # pause, like `outcome`, so no row changes shape. `pause_scope` is
    # deliberately not here -- it is in the marker but not on SessionInfo,
    # and the reason text names the window anyway.
    return {"id": s.id, "state": s.state, "updated_at": s.updated_at,
            "query": s.query, "profile": s.profile,
            "outcome": s.outcome, "failures": s.failures,
            "resume_after": s.resume_after, "pause_reason": s.pause_reason}


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
    grouping), query/profile. Absorbs the deleted `runs` command."""
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
        ws = RunWorkspace(config.root, d.name)
        query, profile = "", None
        if ws.criteria.exists():
            criteria = read_model(ws.criteria, Criteria)
            query, profile = criteria.query, criteria.profile
        elif ws.request.exists():
            # Paused before interpret ever wrote criteria: mirrors
            # iter_sessions' mode-aware branch (sessions.py) -- a profile
            # run's request.json carries no `query`, so reading that field
            # alone left a parked profile run blank here while `run list`
            # (which goes through iter_sessions) named it correctly. A
            # missing `mode` means an artifact written before modes
            # existed, and those were all query runs. A malformed request
            # reads as "no request" (`read_request`) so one bad file can't
            # blind this sweep to every other session.
            req = read_request(ws.request)
            if req.get("mode", "query") == "profile":
                profile = req.get("profile")
            else:
                query = req.get("query") or ""
        counts = by_run.get(d.name, Counter())
        rows.append({"id": d.name, "query": query, "profile": profile,
                    "states": dict(sorted(counts.items()))})
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
            label = f"profile: {row['profile']}" if row["profile"] else row["query"]
            typer.echo(f"{row['id']:34.34s} {summary:40.40s} {label:40.40s}")
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
    profile = Profile(name=name, criteria=criteria, count=count, human_gate=human_gate)
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


_PROFILE_LIST_HEADER = f"{'NAME':<20} {'CNT':>3} QUERY"


@profile_app.command("list")
def profile_list():
    """List profiles: name, count, query."""
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
        typer.echo(f"{p.name:<20} {p.count:>3} {p.criteria.query:40.40s}")


@profile_app.command("show")
def profile_show(name: str = typer.Argument(...)):
    """Inspect one profile: criteria, count, and pinned roster.
    Strictly read-only -- never prompts, never edits. No LLM call."""
    config, _, _ = _setup()
    profile = load_profile(config.root, name)   # ProfileError -> main_cli boundary
    c = profile.criteria
    typer.echo(f"{profile.name}  count={profile.count}  human_gate={profile.human_gate}")
    typer.echo(f"query: {c.query}")
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
