"""CLI boundary: typer app + `main_cli` error boundary.

`_COMMAND_ORDER` fixes the `--help` panel ordering via `OrderedPanelGroup`,
mirroring llama's `cli.py:57-65` pattern.
"""

import json
import re
import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import typer
from typer.core import TyperGroup

from herder import HerderError

from emcee.config import DEFAULT_CONFIG_TOML, EmceeConfig, default_root, load_config
from emcee.errors import EmceeError
from emcee.moves import Moves, clear_move, load_moves, record_move
from emcee.package_io import Package, UnsupportedPackage, rewrite_manifest
from emcee.presenters import (
    Presenter, PresenterError, delete_presenter, list_presenters, load_presenter, save_presenter,
)
from emcee.audio import render_speech_mp3
from emcee.process import (ad_hoc_bed, ad_hoc_speech, assignment_for, presenter_label,
                           resolve_assignment,
                           process_package, resolve_voicing, speech_for_voicing)
from emcee.speech_text import load_lexicon, normalize_for_speech
from emcee.tts.bed import load_bed_pcm
from emcee.tts.provider import SpeechError
from emcee.tts.verify import SttClient
from emcee.tts.resolve import TTSResolutionError, resolve_tts
from emcee.workspace import atomic_write_bytes
from emcee.station import (AWAITING, PackageStatus, assess, awaiting_fix_reason, effective_profile, identity,
                           manifest_performance_id, manifest_profile, manifest_voiced_profile,
                           manifest_voiced_source, package_status, profile_label, raw_manifest,
                           scan, target_problem, unsupported_status)

_COMMAND_ORDER = ["run", "voice", "status", "move", "say", "presenter", "config"]


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

config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        import emcee

        typer.echo(emcee.__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the emcee version and exit.",
    ),
) -> None:
    """`--version`, mirroring llama's `cli.py:78-102` pattern.

    Also a shape-independent hedge: a callback guarantees the
    `COMMAND [ARGS]...` `--help` group form no matter how top-level
    registrations change later, including the one shape that does collapse
    `--help` to `Usage: emcee [OPTIONS]` — a single plain command with no
    sub-typer and no callback. Typer allows only one `@app.callback()`; a
    second one wouldn't error, it would just silently supersede this one.
    """


def _resolve_station_root(config: EmceeConfig, override: Path | None) -> Path:
    """Resolve `[station] root`, hard-failing if it is unset, missing, or
    not a directory.

    `station.scan()` deliberately returns `[]` for that case -- it can't
    tell "not configured yet" from "legitimately empty" -- so that judgment
    call is left to callers (see `scan`'s docstring). `run`/`status` are
    exactly those callers: they need "not configured"/"missing" to be a
    hard, actionable error rather than a silently empty report.
    """
    root = override if override is not None else config.station.root
    if root is None:
        raise EmceeError(
            "[station] root is not set: pass --station-root or set "
            "[station] root in config.toml"
        )
    root = Path(root)
    if not root.is_dir():
        raise EmceeError(f"[station] root does not exist or is not a directory: {root}")
    return root


def _resolve_package(config: EmceeConfig, name: str, station_root: Path | None) -> Path:
    """The package directory `name` addresses: an existing directory path
    as-is, else a package under `[station] root` (or `--station-root`) by
    exact name or unique substring -- the same addressing llama gives shows.

    Candidates are what `station.scan` would visit: non-dot subdirectories
    holding a `manifest.json` (a dot dir is llama's replace-voiced swap
    sibling, never a target). An exact name wins over substring hits, so
    `showA` still reaches `showA` beside `showA-late`.
    """
    path = Path(name).expanduser()
    if path.is_dir():
        return path
    root = _resolve_station_root(config, station_root)
    names = sorted(d.name for d in root.iterdir()
                   if d.is_dir() and not d.name.startswith(".")
                   and (d / "manifest.json").exists())
    if name in names:
        return root / name
    hits = [n for n in names if name in n]
    if len(hits) == 1:
        return root / hits[0]
    if not hits:
        raise EmceeError(f"no package matches {name!r} in {root}")
    raise EmceeError(f"{name!r} is ambiguous in {root}", hits)


def _typed_error(exc: Exception) -> str:
    """An exception's message, type-prefixed unless it's already a complete
    sentence.

    A bare stdlib exception's `str()` is often useless on its own -- a
    `KeyError`'s `str()` is just the missing key, e.g. `'filename'`, which
    reads as a stray, un-quoted-looking fragment in an `error: <slug>: ...`
    line or a status table row. `KeyError: 'filename'` is legible; `'filename'`
    alone is not. `EmceeError`/`HerderError` (and their subclasses) are the
    opposite case: `str(self)` is documented (`errors.py`) to already read as
    a complete, actionable sentence, so type-prefixing it would just glue a
    redundant `EmceeError: `/`HerderError: ` fragment onto an already-finished
    sentence -- so those render their message alone, same as `main_cli`'s own
    top-level boundary. Applied at every point an *arbitrary* (broadly-caught)
    exception's message reaches the user -- `_scan_broad`'s per-entry failures
    and `run`/`voice`'s per-package processing failures.
    """
    if isinstance(exc, (EmceeError, HerderError)):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def _error_reasons(exc: Exception) -> list[str]:
    """`_typed_error(exc)` followed by any `exc.details` lines -- the full
    set of lines a broadly-caught exception should surface, whether that's a
    `PackageStatus.reasons` list or the indented lines `run`/`voice` echo to
    stderr under their `error: <slug>: ...` line. Plain exceptions (no
    `details` attribute) yield just the one line."""
    return [_typed_error(exc), *getattr(exc, "details", [])]


def _scan_broad(root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]:
    """Re-walk `root` package-by-package, never letting one malformed
    package's readiness check abort the walk.

    `package_io`/`station` deliberately validate no manifest model, so a
    valid-JSON-but-structurally-wrong v3 manifest (a track missing
    `filename`, `dj_audio` not a dict) raises a bare KeyError/AttributeError/
    TypeError out of `assess`. This mirrors `scan`'s walk with every entry
    wrapped, reporting a failure as `state="error"`. It threads the same
    config and moves as `scan`, so a moved package stays moved here too.
    """
    statuses: list[PackageStatus] = []
    for entry in sorted(Path(root).iterdir()):
        if (not entry.is_dir() or entry.name.startswith(".")  # llama's swap dirs
                or not (entry / "manifest.json").exists()):
            continue
        pkg = Package(entry)
        try:
            manifest = pkg.manifest()
        except UnsupportedPackage:
            statuses.append(unsupported_status(pkg))
            continue
        except Exception as exc:
            raw = raw_manifest(pkg.manifest_path)
            if isinstance(raw, dict):
                # Valid JSON, wrong structure (e.g. `"schema_version": "3"`):
                # `identity` is total over any dict, so this row still carries
                # the effective profile, performance_id and `voiced_source`,
                # and a move-voiced package counts toward `_load_station`'s
                # missing-moves.json guard (strict surface 2).
                ident = identity(raw, config, moves)
            else:
                # Documented limit: unreadable JSON (or a non-object top
                # level) carries nothing to resolve, so the row records no
                # profile and no `voiced_source` -- never `identity(None)`,
                # which would stamp `profile_source: "llama"` on it. A
                # move-voiced package whose manifest is unreadable does not
                # count toward the missing-moves.json guard.
                profile = manifest_profile(raw)
                ident = {"profile": profile, "delivered_profile": profile}
            statuses.append(PackageStatus(path=entry, state="error", reasons=_error_reasons(exc),
                                          **ident))
            continue
        try:
            statuses.append(package_status(pkg, config, moves, manifest))
        except Exception as exc:
            statuses.append(PackageStatus(path=entry, state="error", reasons=_error_reasons(exc),
                                          **identity(manifest, config, moves)))
    return statuses


def _station_statuses(root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]:
    """Every package's status under `root`: `station.scan` first; if a
    structurally mangled manifest makes it raise mid-walk, the per-entry
    isolated `_scan_broad`. Both are read-only, so the re-walk is safe."""
    try:
        return scan(root, config, moves)
    except Exception:
        return _scan_broad(root, config, moves)


def _load_station(config: EmceeConfig, root: Path) -> tuple[Moves, list[PackageStatus]]:
    """moves.json first (a bad file is an EmceeError naming it), then the
    scan, then the missing-file guard: all before the caller does any work
    (strict surface 2). Loaded once per command and passed everywhere."""
    moves = load_moves(config.root)
    statuses = _station_statuses(root, config, moves)
    moves.require_present([(s.path.name, s.performance_id, s.voiced_profile)
                           for s in statuses if s.voiced_source == "move"])
    return moves, statuses


def _process_one(config: EmceeConfig, moves: Moves, pkg: Package, force: bool,
                 fresh: Sequence[str] = ()) -> None:
    """Script + voice + broadcast-assemble one package. Shared by `run`'s
    per-package loop and `voice`.

    The package is resolved exactly once (`resolve_voicing`: effective
    profile, presenter, title, TTS) and that `Voicing` is passed through to
    `process_package`; it is never hoisted above a per-package loop.

    Order (strict surface): resolution (including use-time move validation)
    and provider construction, then `speech.preflight()`, THEN the `--fresh`
    unlink (`fresh` holds already-validated, de-duplicated clip stems), THEN
    the manifest clear, THEN `process_package` (the first LLM spend). So no
    configuration-only failure -- an invalid move target, an unpinned
    presenter under an mlx_audio house, a down mlx-audio server, a missing
    model -- can discard a clip or take a broadcast-ready package off air.
    """
    manifest = pkg.manifest()
    held = awaiting_fix_reason(manifest)
    if held is not None:
        detail = held.removeprefix("awaiting fix from llama: ")
        raise EmceeError(
            "awaiting fix from llama"
            + (f" ({detail})" if detail != held else "")
            + "; re-deliver from llama first")
    voicing = resolve_voicing(config, moves, manifest)
    speech, _bed = speech_for_voicing(config, voicing)
    try:
        speech.preflight()
        if fresh:
            audio_dir = pkg.dir / "dj-audio"
            for stem in fresh:
                (audio_dir / f"{stem}.mp3").unlink()
            typer.echo(f"re-rolling {', '.join(fresh)} "
                       "(previous take(s) discarded — TTS is non-deterministic)")
        # JUDGMENT CALL: clears the manifest's dj_notes/dj_audio blocks before
        # reprocessing -- but only now, after resolution, provider
        # construction and preflight have all succeeded. `process_package`
        # overwrites `dj-notes.md` well before the manifest write that marks
        # its success, so a mid-pipeline failure on an already-*ready* package
        # would otherwise leave `dj-notes.md` holding the new (unrecorded)
        # script while the manifest -- and therefore `station.readiness` --
        # still reports the *old* blocks as present. Clearing first means a
        # failure here instead degrades the package to "pending". It never
        # touches `dj-audio/segments.json` (the per-clip cache `--fresh`
        # relies on).
        rewrite_manifest(pkg, dj_notes=None, dj_audio=None)
        process_package(config, pkg, speech, force, voicing=voicing)
    finally:
        # A raising close() must never mask a successful process_package --
        # or turn a completed package into a reported failure. Best-effort.
        try:
            speech.close()
        except Exception:
            pass


def _presenter_file(root: Path, presenter_id: str) -> Path | None:
    """`presenters/<id>.toml`, comparing the id case-insensitively (the
    config may say `BillyG` for `billyg.toml`); None when there is none."""
    pdir = root / "presenters"
    exact = pdir / f"{presenter_id}.toml"
    if exact.exists():
        return exact
    want = f"{presenter_id}.toml".lower()
    if pdir.is_dir():
        for p in pdir.iterdir():
            if p.name.lower() == want:
                return p
    return None


def _presenter_or_marker(config: EmceeConfig, presenter_id: str) -> Presenter | str:
    """The presenter, or the bracketed marker `--dry-run` and the plan print
    for one that cannot be loaded. Never raises. An unreadable or non-UTF-8
    file (OSError / UnicodeDecodeError, which load_presenter does not wrap)
    is invalid too."""
    path = _presenter_file(config.root, presenter_id)
    if path is None:
        return f"[missing presenters/{presenter_id}.toml]"
    try:
        return load_presenter(config.root, path.stem)
    except (PresenterError, OSError, ValueError):
        return f"[invalid presenters/{presenter_id}.toml]"


def _dry_run_marker(config: EmceeConfig, presenter_id: str) -> str:
    """The row suffix `run --dry-run` prints for a presenter-assigned package:
    a missing or invalid file, a failed TTS resolution, or -- for a PINNED
    presenter only -- the backend and model it resolves to. Never raises;
    never preflights."""
    presenter = _presenter_or_marker(config, presenter_id)
    if isinstance(presenter, str):
        return f"  {presenter}"
    try:
        resolution = resolve_tts(config, presenter)
    except TTSResolutionError as exc:
        return f"  [unresolved: {exc}]"
    if resolution.pinned:
        return f"  [{resolution.backend} {resolution.model}]"
    return ""


def _stdin_is_tty() -> bool:
    """Whether someone can answer `run`'s question. Tests patch this."""
    return sys.stdin.isatty()


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _stale_moves(moves: Moves, statuses: list[PackageStatus]) -> int:
    """Recorded moves whose performance_id no scanned package carries."""
    live = {s.performance_id for s in statuses if s.performance_id is not None}
    return sum(1 for pid in moves.entries if pid not in live)


def _stale_note(n: int) -> str:
    return f"note: {n} recorded move(s) match no package (emcee move --list)"


def _plan_tts_cell(config: EmceeConfig, presenter_id: str | None) -> tuple[str, str]:
    """(who, how) for one TTS line of the plan: `<id> (<name>)` or `house`,
    and `<backend>  <model>` -- or the `--dry-run` marker when the presenter
    cannot be loaded or resolved. Never raises."""
    presenter: Presenter | None = None
    who = "house"
    if presenter_id is not None:
        loaded = _presenter_or_marker(config, presenter_id)
        if isinstance(loaded, str):
            return presenter_id, loaded
        presenter, who = loaded, f"{presenter_id} ({loaded.name})"
    try:
        resolution = resolve_tts(config, presenter)
    except TTSResolutionError as exc:
        return who, f"[unresolved: {exc}]"
    return who, f"{resolution.backend}  {resolution.model or '-'}"


def _echo_plan(config: EmceeConfig, to_voice: list[PackageStatus], stale: int) -> None:
    """The plan `run` prints before any spend (stderr): what will be voiced,
    why, with which TTS. `new` = unvoiced; `re-voice` = the profile check
    fails (grouped by reason, every package named: it is destructive);
    `repair` = voiced, profile check passing, something else missing (named:
    it also overwrites the script and clips)."""
    def out(line: str) -> None:
        typer.echo(line, err=True)

    clips = sum(s.clips for s in to_voice)
    out(f"to voice: {_plural(len(to_voice), 'package')}, {_plural(clips, 'clip')}")
    new = [s for s in to_voice if not s.voiced]
    revoice: dict[str, list[str]] = {}
    for s in to_voice:
        if s.voiced and s.profile_reason is not None:
            revoice.setdefault(s.profile_reason, []).append(s.path.name)
    repair = [s.path.name for s in to_voice if s.voiced and s.profile_reason is None]
    if new:
        out(f"  {'new':<9}{len(new):>3}")
    if revoice:
        out(f"  {'re-voice':<9}{sum(len(v) for v in revoice.values()):>3}")
        for reason, slugs in revoice.items():
            out(f"    {reason}: {len(slugs)}")
            for slug in slugs:
                out(f"      {slug}")
    if repair:
        out(f"  {'repair':<9}{len(repair):>3}")
        for slug in repair:
            out(f"      {slug}")
    out("TTS:")
    counts: dict[str | None, int] = {}
    for s in to_voice:
        pid = assignment_for(config, s.profile).presenter
        counts[pid] = counts.get(pid, 0) + 1
    order = sorted(counts, key=lambda pid: (pid is None, pid or ""))
    cells = [(_plan_tts_cell(config, pid), counts[pid]) for pid in order]
    width = max(len(who) for (who, _), _ in cells)
    for (who, how), n in cells:
        out(f"  {who:<{width}}  {how}  {_plural(n, 'package')}")
    if stale:
        out(_stale_note(stale))


@app.command()
def run(
    force: bool = typer.Option(False, "--force",
                               help="Re-synthesize every DJ clip even if cached"),
    station_root: Path = typer.Option(
        None, "--station-root",
        help="Override \\[station] root for this invocation"),
    profile: list[str] = typer.Option(
        [], "--profile",
        help="Only packages whose effective profile is this (exact match; a move or "
             "artist rule counts); repeatable"),
    assigned: bool = typer.Option(
        False, "--assigned",
        help="Only packages whose effective profile has its own \\[assign.profiles] "
             "entry (skip those that would fall to the default or house voice)"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="List what would be voiced, and with which presenter, then the plan; no LLM, "
             "TTS, or writes (--force is ignored); never asks"),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Voice without asking (the plan is still printed)"),
):
    """Voice every pending package in the station, after a plan and a yes.

    Scans `\\[station] root` (or `--station-root`) once, with config and
    `moves.json` loaded once. Before any LLM or TTS call it prints a plan on
    stderr -- packages to voice (new / re-voice by reason / repair), the
    exact clip count, and which presenter and TTS backend voice them -- and
    asks `Proceed? [y/N]`. `--yes` skips the question. With no terminal and
    no `--yes` it prints the plan and refuses (exit 1). After a yes it
    voices exactly the planned packages, from the same scan.

    A pending package with missing track audio is skipped, whatever else is
    wrong with it (`skip <slug>: N audio file(s) missing; re-deliver from
    llama`): voicing cannot fix it. "unsupported" (pre-v3) packages are
    reported and never modified. A package whose recorded move targets a
    profile with no `\\[assign.profiles]` entry is an error row and is never
    voiced, even when it is otherwise ready. Per-package failures are
    printed as `error: <slug>: <message>` and do not stop the batch.

    `--profile NAME` (repeatable) and `--assigned` select by the EFFECTIVE
    profile (a recorded move, else an `\\[assign.artists]` rule, else the
    llama profile). `--dry-run` prints `would voice: <slug>  <profile>
    <presenter>` rows, then the plan, and never asks or writes.

    Exits 1 whenever an error row was printed (proceeded, declined, or
    nothing to voice); otherwise a decline or nothing to voice exits 0.
    """
    config = load_config()
    root = _resolve_station_root(config, station_root)
    moves, statuses = _load_station(config, root)
    stale = _stale_moves(moves, statuses)

    _note_unmatched_profiles(statuses, profile)
    filtering = bool(profile) or assigned
    unreadable = 0
    failed = False
    to_voice: list[PackageStatus] = []
    for status in statuses:
        slug = status.path.name
        if filtering:
            if status.profile is None and status.state in ("error", "unsupported"):
                unreadable += 1
                continue
            if profile and status.profile not in profile:
                continue
            if assigned and assignment_for(config, status.profile).source != "profile":
                continue
        if status.state == "unsupported":
            typer.echo(f"skip {slug}: {status.reasons[0]}")
            continue
        if status.state == "error":
            typer.echo(f"error: {slug}: {status.reasons[0]}", err=True)
            for line in status.reasons[1:]:
                typer.echo(f"  {line}", err=True)
            failed = True
            continue
        if status.move_problem is not None:   # before the ready check: a ready package reports it too
            typer.echo(f"error: {slug}: {status.move_problem}", err=True)
            failed = True
            continue
        if status.state == AWAITING:
            typer.echo(f"skip {slug}: awaiting fix from llama")
            continue
        if status.state == "ready":
            continue
        if status.missing_tracks:   # tracks first: voicing cannot fix them
            typer.echo(f"skip {slug}: {status.missing_tracks} audio file(s) missing; "
                       "re-deliver from llama")
            continue
        if dry_run:
            view = assignment_for(config, status.profile)
            line = f"would voice: {slug}  {status.profile or '(none)'}  {presenter_label(view)}"
            if view.presenter is not None:
                line += _dry_run_marker(config, view.presenter)
            typer.echo(line)
        to_voice.append(status)

    if unreadable:
        typer.echo(f"note: {unreadable} package(s) skipped: manifest unreadable "
                   "(see emcee status --list)")
    if to_voice:
        _echo_plan(config, to_voice, stale)
    elif stale:
        typer.echo(_stale_note(stale), err=True)

    if dry_run:
        typer.echo(f"{len(to_voice)} package(s) would be voiced"
                   + (" (with errors)" if failed else ""))
        if failed:
            raise typer.Exit(1)
        return

    if to_voice and not yes:
        if not _stdin_is_tty():
            typer.echo("error: refusing to voice without confirmation; pass --yes", err=True)
            raise typer.Exit(1)
        if not typer.confirm("Proceed?", default=False, err=True):
            typer.echo("nothing voiced")
            raise typer.Exit(1 if failed else 0)

    processed = 0
    for status in to_voice:
        slug = status.path.name
        try:
            _process_one(config, moves, Package(status.path), force)
        except Exception as exc:
            typer.echo(f"error: {slug}: {_typed_error(exc)}", err=True)
            for line in getattr(exc, "details", []):
                typer.echo(f"  {line}", err=True)
            failed = True
            continue
        processed += 1
        typer.echo(f"voiced: {slug}")

    typer.echo(f"{processed} package(s) voiced" + (" (with errors)" if failed else ""))
    if failed:
        raise typer.Exit(1)


@app.command("voice")
def voice_cmd(
    package: str = typer.Argument(
        ..., help="A package directory, or a package's name (or unique substring) "
                  "under \\[station] root"),
    fresh: list[str] = typer.Option(
        [], "--fresh",
        help="Re-roll (re-synthesize) just these DJ-clip stems, e.g. set1-intro "
             "or 99-outro; repeatable. Deletes the cached clip (after the TTS preflight passes) so "
             "reprocessing re-renders only it -- other clips keep their "
             "cached audio, PROVIDED the DJ script comes back unchanged. "
             "CAVEATS (both unlike llama, which stamps and replays a "
             "provenance voice/script): (1) emcee re-scripts on every call -- "
             "with a real, non-deterministic LLM, a re-voice's regenerated "
             "script text usually differs at least slightly, which changes "
             "EVERY clip's cache key and defeats single-clip granularity "
             "(every clip re-renders, not just the named one) -- there is no "
             "way around this short of a script-reuse mode this CLI does not "
             "have yet; (2) a re-voice always resolves the voice fresh from "
             "config + presenter assignment (no stamp), so if the configured "
             "voice changed since the last render, that alone also "
             "invalidates every clip's cache key."),
    force: bool = typer.Option(False, "--force",
                               help="Re-synthesize every DJ clip even if cached"),
    station_root: Path = typer.Option(
        None, "--station-root",
        help="Override \\[station] root for resolving a package name"),
):
    """Script + voice + broadcast-assemble ONE delivered package.

    `package` is a package directory, or a package's name or unique
    substring under `\\[station] root` (`--station-root` overrides it); an
    existing directory path always wins -- use `emcee run` to process a
    whole station. Re-processing an already-"ready" package
    clears its `dj_notes`/`dj_audio` manifest blocks (once presenter/voice
    resolution AND the TTS preflight have succeeded) before reprocessing, so a
    mid-pipeline failure degrades it to "pending" -- self-consistent with
    `station.readiness` -- instead of leaving it stale-"ready" while
    `dj-notes.md` already holds an unrecorded new script; a clean run
    overwrites both blocks again as its own success marker. One
    consequence: a package that was previously broadcast-ready and fails a
    re-voice partway through goes back to NOT broadcast-ready until a
    later `voice`/`run` call on it succeeds -- there is no automatic
    rollback to the prior (working) script/audio.

    Per-package failures -- including a structurally invalid manifest (e.g.
    a track missing its filename, or a briefing block missing entirely),
    since emcee validates no manifest model -- are caught broadly and
    printed as `error: <slug>: <message>` plus any indented detail lines,
    matching `emcee run`, instead of a raw traceback. Exits 1 on failure.
    """
    config = load_config()
    moves = load_moves(config.root)   # a bad file fails here, before any work
    pkg = Package(_resolve_package(config, package, station_root))
    manifest = pkg.manifest()  # validates schema_version >= 3; UnsupportedPackage/EmceeError -> boundary
    if manifest_voiced_source(manifest) == "move":
        moves.require_present([(pkg.dir.name, manifest_performance_id(manifest),
                                manifest_voiced_profile(manifest))])

    stems: list[str] = []
    if fresh:
        audio_dir = pkg.dir / "dj-audio"
        available = sorted(p.stem for p in audio_dir.glob("*.mp3")) if audio_dir.is_dir() else []
        if not available:
            raise EmceeError(f"{pkg.dir.name} has no DJ audio to re-roll (not voiced yet)")
        unknown = [s for s in fresh if s not in available]
        if unknown:
            raise EmceeError(
                f"no clip {unknown[0]!r} in {pkg.dir.name}; clips: {', '.join(available)}"
            )
        stems = list(dict.fromkeys(fresh))  # dedupe: a repeated stem must not double-unlink

    try:
        _process_one(config, moves, pkg, force, fresh=stems)
    except Exception as exc:
        typer.echo(f"error: {pkg.dir.name}: {_typed_error(exc)}", err=True)
        for line in getattr(exc, "details", []):
            typer.echo(f"  {line}", err=True)
        raise typer.Exit(1)
    typer.echo(f"voiced: {pkg.dir}")


@app.command("say")
def say_cmd(
    text_file: Path = typer.Argument(..., help="UTF-8 text file to read aloud"),
    out: Path = typer.Option(
        None, "-o", "--out",
        help="Where to write the MP3; default <text file>.mp3 beside the input"),
    clone: Path = typer.Option(
        None, "--clone",
        help="Reference clip to clone (3-25s; voxtral or mlx_audio), instead of a "
             "preset voice"),
    clone_text: str = typer.Option(
        None, "--clone-text",
        help="Transcript of the --clone clip; required when the house backend is "
             "mlx_audio, ignored otherwise"),
    voice: str = typer.Option(
        None, "--voice", help="Preset voice name, instead of the house [tts] voice"),
    presenter: str = typer.Option(
        None, "--presenter",
        help="Read in this presenter's voice (and its bed), as a voiced package would"),
    bed: Path = typer.Option(
        None, "--bed",
        help="Instrumental bed WAV (24kHz mono 16-bit) mixed under the voice; "
             "overrides the presenter's bed and [tts] bed"),
    no_bed: bool = typer.Option(
        False, "--no-bed", help="Read dry: suppress the presenter's bed and [tts] bed"),
    bed_gain: float = typer.Option(
        None, "--bed-gain",
        help="Bed loudness under the voice in dB (negative = quieter); "
             "default [tts] bed_gain_db"),
    chunk: bool = typer.Option(
        True, "--chunk/--no-chunk",
        help="Synthesize in paragraph-packed chunks (up to \\[tts] chunk_chars) and "
             "concatenate (default), rather than one call for the whole passage"),
    raw: bool = typer.Option(
        False, "--raw",
        help="Speak the text verbatim: skip symbol expansion and the "
             "pronunciation lexicon"),
):
    """Voice an arbitrary text file to an MP3 -- no package, no script, no LLM.

    The ad-hoc counterpart to `emcee voice`: `say` never touches a delivered
    package, writes no manifest, and calls no language model -- it is purely
    text in, speech out, so it works on a station whose `[llm]` backend is
    absent or unconfigured.

    VOICE: at most one of `--clone`, `--voice` and `--presenter`; with none of
    them the house `[tts] voice`/`voice_clone` reads it, including its
    `[tts] voice_clone_text`. `--clone-text` is the `--clone` clip's
    transcript, required when the house backend is mlx_audio (which is
    clone-only, so `--voice` is refused there); `--presenter` resolves exactly
    as in `emcee run`, pin included.

    BED: resolved exactly as a voiced package's is (the presenter's own bed,
    else `[tts] bed`), with `--bed` overriding the file, `--bed-gain` the
    loudness, and `--no-bed` suppressing it outright. As elsewhere, a bed must
    be a 24kHz mono 16-bit WAV matching the voice audio, and a bedded clip is
    re-encoded via lameenc rather than shipping the provider's own MP3.

    CHUNKING defaults ON, as `[tts] chunk` does for DJ clips: an arbitrary text
    file routinely exceeds the backend's per-request character cap, which a
    single whole-passage call cannot survive. `--no-chunk` restores the single
    call for short passages. Chunks follow the text's paragraphs up to
    `\\[tts] chunk_chars` and never end inside a sentence; exact-silence gaps
    are filled with the clip's own room tone (`\\[tts] room_tone`). Chunked and
    bedded renders are loudness-normalized; `--no-chunk` without a bed ships
    the provider's own MP3 un-normalized.
    """
    config = load_config()
    if clone_text is not None and clone is None:
        _usage("--clone-text needs --clone")
    house_mlx = config.tts.backend == "mlx_audio"
    if house_mlx and voice:
        _usage("--voice is a preset, but the house backend is mlx_audio, which is clone-only "
               "(use --clone with --clone-text, or --presenter)")
    if house_mlx and clone is not None and not (clone_text or "").strip():
        _usage("--clone needs --clone-text (the clip's transcript) when the house backend "
               "is mlx_audio")

    text = text_file.read_text().strip()
    if not text:
        raise EmceeError(f"nothing to say: {text_file} is empty")

    host = load_presenter(config.root, presenter) if presenter else None
    speech = ad_hoc_speech(config, clone_ref=str(clone) if clone else None,
                           clone_text=clone_text if house_mlx else None,
                           voice=voice, presenter=host)
    resolved_bed = ad_hoc_bed(config, host, bed_path=bed, no_bed=no_bed,
                              gain_db=bed_gain)

    spoken = text if raw else normalize_for_speech(text, load_lexicon(config.root))
    bed_pcm = bed_rate = None
    if resolved_bed is not None:
        bed_pcm, bed_rate, _, _ = load_bed_pcm(resolved_bed.path)

    data = render_speech_mp3(
        spoken, speech, chunking=config.tts.chunking(enabled=chunk), bed_pcm=bed_pcm, bed_rate=bed_rate,
        bed_gain_db=resolved_bed.gain_db if resolved_bed is not None else 0.0)

    dest = out or text_file.with_suffix(".mp3")
    atomic_write_bytes(dest, data)
    typer.echo(f"wrote {dest}")


_STATUS_STATES = ("ready", "pending", "unsupported", "error", "awaiting-fix")


def _profile_cell(s: PackageStatus) -> str:
    """The `--list` profile cell: the effective profile; ` (from <llama's>)`
    when a move or rule changed it; ` [no assign entry]` when its recorded
    move cannot be voiced."""
    cell = profile_label(s.profile)
    if s.profile_source is not None and s.profile != s.delivered_profile:
        cell += f" (from {profile_label(s.delivered_profile)})"
    if s.move_problem is not None:
        cell += " [no assign entry]"
    return cell


def _recorded_tts(s: PackageStatus) -> tuple[str, str | None] | None:
    """(backend, model) of the recorded `dj_audio.tts`; None when the package
    is not voiced or the record is unusable (no `tts`, or `backend` not a
    non-empty string)."""
    if not s.voiced or s.tts is None:
        return None
    backend = s.tts.get("backend")
    if not isinstance(backend, str) or not backend:
        return None
    model = s.tts.get("model")
    return backend, (model if isinstance(model, str) and model else None)


@dataclass(frozen=True)
class _TtsView:
    recorded: tuple[str, str | None] | None   # usable recorded (backend, model)
    now: tuple[str, str | None] | None        # resolved (backend, model)
    unresolved: str | None                # why "now" did not resolve
    has_now: bool                         # False: error/unsupported row, no "now" at all

    @property
    def drifted(self) -> bool | None:
        if self.recorded is None or self.now is None:
            return None
        return self.recorded != self.now


class _TtsNow:
    """What would voice a package today (its effective profile -> presenter ->
    `resolve_tts`), computed once per distinct profile per command: resolving
    reads the presenter TOML from disk."""

    def __init__(self, config: EmceeConfig) -> None:
        self._config = config
        self._by_profile: dict[str | None, tuple[tuple[str, str | None] | None, str | None]] = {}

    def _resolve(self, profile: str | None) -> tuple[tuple[str, str | None] | None, str | None]:
        if profile not in self._by_profile:
            try:
                presenter, _title = resolve_assignment(self._config, profile)
                resolution = resolve_tts(self._config, presenter)
                self._by_profile[profile] = ((resolution.backend, resolution.model), None)
            except (EmceeError, OSError, ValueError) as exc:
                # EmceeError covers TTSResolutionError and PresenterError;
                # load_presenter's read_text can also raise OSError/UnicodeDecodeError
                # (a ValueError), which it does not wrap.
                self._by_profile[profile] = (None, str(exc))
        return self._by_profile[profile]

    def view(self, s: PackageStatus) -> _TtsView:
        recorded = _recorded_tts(s)
        if s.state in ("error", "unsupported"):
            return _TtsView(recorded, None, None, False)
        if s.move_problem is not None:
            return _TtsView(recorded, None, s.move_problem, True)
        now, err = self._resolve(s.profile)
        return _TtsView(recorded, now, err, True)


def _status_json_row(config: EmceeConfig, s: PackageStatus, tts_now: _TtsNow) -> dict:
    view = assignment_for(config, s.profile)
    presenter, source = view.presenter, view.source
    if s.profile is None and s.state in ("error", "unsupported"):
        presenter = source = None  # unreadable manifest: no profile, so no assignment
    tts_view = tts_now.view(s)
    return {"slug": s.path.name, "state": s.state, "reasons": s.reasons,
            "profile": s.profile, "delivered_profile": s.delivered_profile,
            "profile_source": s.profile_source, "voiced_by": s.voiced_by,
            "assigned_presenter": presenter, "assignment_source": source,
            "tts": s.tts, "move_problem": s.move_problem,
            "tts_now": _tts_now_json(tts_view), "tts_drifted": tts_view.drifted,
            "awaiting_fix": s.awaiting_fix}


def _tts_now_json(v: _TtsView) -> dict | None:
    if not v.has_now:
        return None
    if v.now is None:
        return {"unresolved": v.unresolved}
    return {"backend": v.now[0], "model": v.now[1]}


def _note_unmatched_profiles(statuses: list[PackageStatus], names) -> None:
    """One stderr note per requested `--profile` that no package (any state)
    carries -- a typo'd or wrong-case name must not look like an empty queue."""
    known = {s.profile for s in statuses}
    for name in names or []:
        if name not in known:
            typer.echo(f"note: no package has profile {name!r}", err=True)


def _voiced_by_cell(config: EmceeConfig, s: PackageStatus) -> str:
    """`-` when unvoiced; else who voiced it, annotated `(now: X)` when the
    current assignment would pick a different presenter (ids compare
    case-insensitively; `?` -- a legacy, unrecorded voicing -- never drifts)."""
    if s.voiced_by is None:
        return "-"
    if s.voiced_by == "?":
        return "?"
    current = assignment_for(config, s.profile).presenter
    if s.voiced_by.lower() != (current or "house").lower():
        return f"{s.voiced_by} (now: {current or 'house'})"
    return s.voiced_by


def _compact_tts_cell(recorded: tuple[str, str | None], now: tuple[str, str | None] | None,
                      *, drifted: bool, has_now: bool) -> str:
    """The recorded backend, plus `(now: <backend>)` on a backend drift, `(now: new
    model)` when only the model moved, or `(now: unresolved)`. Models are in --json."""
    cell = recorded[0]
    if drifted and now is not None:
        cell += " (now: new model)" if now[0] == recorded[0] else f" (now: {now[0]})"
    elif has_now and now is None:
        cell += " (now: unresolved)"
    return cell


def _tts_cell(s: PackageStatus, v: _TtsView) -> str:
    """`-` unvoiced, `?` voiced with no usable record, else `_compact_tts_cell`."""
    if not s.voiced:
        return "-"
    if v.recorded is None:
        return "?"
    return _compact_tts_cell(v.recorded, v.now, drifted=v.drifted, has_now=v.has_now)


_REASON_SHORT = {"no DJ script (dj_notes block + dj-notes.md required)": "no script",
                 "no DJ audio (unvoiced)": "unvoiced", "no broadcast.m3u": "no m3u"}
_CLIPS_MISSING = re.compile(r"(\d+) DJ audio clip\(s\) missing")
_AUDIO_MISSING = re.compile(r"(\d+ of \d+) audio file\(s\) missing")
_DELIVERED_TAIL = " (delivered profile; no rule or move applies)"


def _reasons_cell(s: PackageStatus) -> str:
    """The table's short form of `s.reasons` (--json keeps the full text): blank for
    awaiting-fix, whose state column says it; a never-voiced package is `unvoiced`."""
    if s.state == AWAITING:
        return ""
    short = []
    for r in s.reasons:
        if r in _REASON_SHORT:
            short.append(_REASON_SHORT[r])
        elif m := _CLIPS_MISSING.match(r):
            short.append(f"{m[1]} clips missing")
        elif m := _AUDIO_MISSING.match(r):
            short.append(f"{m[1]} audio missing")
        else:
            short.append(r.removesuffix(_DELIVERED_TAIL))
    if {"no script", "unvoiced", "no m3u"} <= set(short):
        short = [r for r in short if r not in ("no script", "no m3u")]
    return "; ".join(short)


def _voiced_on_cell(members: list[PackageStatus]) -> str:
    """`voxtral 112, mlx_audio 3, ? 2`: voiced packages by recorded backend,
    count descending then name; empty when none is voiced."""
    counts: dict[str, int] = {}
    for m in members:
        if m.voiced:
            rec = _recorded_tts(m)
            key = rec[0] if rec is not None else "?"
            counts[key] = counts.get(key, 0) + 1
    return ", ".join(f"{k} {n}" for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _note_unmatched_tts(statuses: list[PackageStatus], names) -> None:
    """One stderr note per requested `--tts` backend no package records
    (`none` is a keyword, never noted)."""
    known = {rec[0] for s in statuses if (rec := _recorded_tts(s)) is not None}
    for name in names or []:
        if name != "none" and name not in known:
            typer.echo(f"note: no package is voiced with tts {name!r}", err=True)


def _tts_match(s: PackageStatus, names: Sequence[str]) -> bool:
    """`--tts` filter: recorded backend in `names`; a voiced package with no
    usable record matches `none`."""
    rec = _recorded_tts(s)
    if rec is None:
        return s.voiced and "none" in names
    return rec[0] in names


def _echo_status_summary(config: EmceeConfig, statuses: list[PackageStatus]) -> None:
    """One row per profile (sorted; `(none)` then `(unknown)` last, each only
    when non-empty) with ready/pending/other counts, then a total line."""
    groups: dict[str, list[PackageStatus]] = {}
    for s in statuses:
        if s.profile is not None:
            key = s.profile
        elif s.state in ("error", "unsupported"):
            key = "(unknown)"  # no profile recoverable from an unreadable manifest
        else:
            key = "(none)"
        groups.setdefault(key, []).append(s)
    keys = sorted(k for k in groups if k not in ("(none)", "(unknown)"))
    keys += [k for k in ("(none)", "(unknown)") if k in groups]

    rows = [("profile", "presenter", "ready", "pending", "other", "awaiting fix", "voiced on")]
    for key in keys:
        members = groups[key]
        presenter = ("" if key == "(unknown)"
                     else presenter_label(assignment_for(config, members[0].profile)))
        count = lambda *states: sum(1 for m in members if m.state in states)  # noqa: E731
        rows.append((key, presenter, str(count("ready")), str(count("pending")),
                     str(count("unsupported", "error")), str(count(AWAITING)),
                     _voiced_on_cell(members)))
    total = lambda *states: sum(1 for s in statuses if s.state in states)  # noqa: E731
    rows.append(("total", "", str(total("ready")), str(total("pending")),
                 str(total("unsupported", "error")), str(total(AWAITING)),
                 _voiced_on_cell(statuses)))
    widths = [max(len(r[c]) for r in rows) for c in range(7)]
    for r in rows:
        typer.echo("  ".join(f"{cell:<{w}}" for cell, w in zip(r, widths)).rstrip())


@app.command("status")
def status_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON (always per-show; filters apply)"),
    list_view: bool = typer.Option(
        False, "--list", "-l", help="Per-show table instead of the per-profile summary"),
    profile: list[str] = typer.Option(
        None, "--profile", help="Only this profile (exact match; repeatable); implies --list"),
    state: list[str] = typer.Option(
        None, "--state",
        help="Only this state: ready|pending|unsupported|error|awaiting-fix (repeatable); implies --list"),
    tts: list[str] = typer.Option(
        None, "--tts",
        help="Only shows voiced on this TTS backend (none = unrecorded; repeatable); implies --list"),
    drifted: bool = typer.Option(
        False, "--drifted",
        help="Only shows whose voice now resolves to a different TTS backend or model; implies --list"),
    station_root: Path = typer.Option(
        None, "--station-root",
        help="Override \\[station] root for this invocation"),
):
    """Station status: one row per profile, or `--list` for every show.

    Profiles are effective (a move or artist rule can override llama's).
    A show pending only for a profile change keeps airing its old voicing
    until it is re-voiced. TTS drift `(now: ...)` is display-only and never
    makes a show pending.
    """
    config = load_config()
    root = _resolve_station_root(config, station_root)
    moves, statuses = _load_station(config, root)
    stale = _stale_moves(moves, statuses)

    bad = [st for st in (state or []) if st not in _STATUS_STATES]
    if bad:
        raise typer.BadParameter(
            f"unknown state {bad[0]!r}; expected one of {', '.join(_STATUS_STATES)}",
            param_hint="--state")
    filtered = bool(profile or state or tts or drifted)
    station_empty = not statuses
    _note_unmatched_profiles(statuses, profile)
    _note_unmatched_tts(statuses, tts)
    tts_now = _TtsNow(config)
    if profile:
        statuses = [s for s in statuses if s.profile in profile]
    if state:
        statuses = [s for s in statuses if s.state in state]
    if tts:
        statuses = [s for s in statuses if _tts_match(s, tts)]
    if drifted:
        statuses = [s for s in statuses if tts_now.view(s).drifted]

    if json_output:
        typer.echo(json.dumps([_status_json_row(config, s, tts_now) for s in statuses],
                              indent=2))
    elif not statuses:
        typer.echo("no packages found" if station_empty or not filtered
                   else "no packages match")
    elif not (list_view or filtered):
        _echo_status_summary(config, statuses)
    else:
        width = max(len(s.path.name) for s in statuses)
        profiles = [_profile_cell(s) for s in statuses]
        pwidth = max(len(p) for p in profiles)
        cells = [_voiced_by_cell(config, s) for s in statuses]
        vwidth = max(len(c) for c in cells)
        ttss = [_tts_cell(s, tts_now.view(s)) for s in statuses]
        twidth = max(len(c) for c in ttss)
        for s, pcell, cell, tcell in zip(statuses, profiles, cells, ttss):
            reasons = _reasons_cell(s)
            typer.echo(f"{s.path.name:<{width}}  {pcell:<{pwidth}}  "
                       f"{s.state:<12}  {cell:<{vwidth}}  {tcell:<{twidth}}  {reasons}".rstrip())
    if stale:
        typer.echo(_stale_note(stale), err=True)


def _assignments_using_presenter(config: EmceeConfig, presenter_id: str) -> list[str]:
    """Names of emcee `[assign]` config entries that still name this
    presenter -- used by `presenter remove`'s in-use refusal. Profile entries
    are named by their `[assign.profiles.<name>]` key; the station-wide
    `[assign] default` has no profile name of its own, so it is reported as
    the literal string `"[assign] default"`."""
    users = [name for name, a in config.assign.profiles.items() if a.presenter == presenter_id]
    if config.assign.default == presenter_id:
        users.append("[assign] default")
    return users


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _echo_moves(config: EmceeConfig, moves: Moves, statuses: list[PackageStatus]) -> None:
    """`move --list`: one row per recorded move, sorted by performance_id:
    package, id, target (from delivered), `missing` when no scanned package
    carries the id, `[no assign entry]` when the move fails use-time
    validation."""
    if not moves.entries:
        typer.echo("no moves recorded")
        return
    by_pid: dict[str, PackageStatus] = {}
    for s in statuses:
        if s.performance_id is not None:
            by_pid.setdefault(s.performance_id, s)
    for pid, entry in sorted(moves.entries.items()):
        target = entry["profile"]
        package = entry.get("package")
        name = package if isinstance(package, str) and package else pid
        status = by_pid.get(pid)
        if status is None:
            line = f"{name}  {pid}  {profile_label(target)} (from ?)  missing"
            bad = target is not None and target not in config.assign.profiles
        else:
            line = f"{name}  {pid}  {profile_label(target)} (from {profile_label(status.delivered_profile)})"
            bad = target_problem(config, target, status.delivered_profile) is not None
        if bad:
            line += "  [no assign entry]"
        typer.echo(line)


@app.command("move")
def move_cmd(
    show: str = typer.Argument(
        None, help="A package directory, or a package's name (or unique substring) under "
                   "\\[station] root; for --clear also a recorded performance_id or package name"),
    profile: str = typer.Argument(None, help="The profile to voice this show as"),
    delivered: bool = typer.Option(
        False, "--delivered",
        help="Move back to the profile llama delivered it under (exempts it from an artist rule)"),
    clear: bool = typer.Option(False, "--clear", help="Remove this show's recorded move"),
    list_moves: bool = typer.Option(False, "--list", help="List every recorded move"),
    station_root: Path = typer.Option(
        None, "--station-root", help="Override \\[station] root for this invocation"),
):
    """Record, clear or list a one-off profile move (`moves.json`).

    `emcee move <show> <profile>` voices that show as `<profile>` from the
    next `emcee run` on, whatever llama delivered it under; `--delivered`
    moves it back to llama's profile, which is how one show is exempted from
    an `\\[assign.artists]` rule. The target needs its own
    `\\[assign.profiles.<name>]` entry unless it is the delivered profile.
    Moves are keyed by the manifest's `source.performance_id`, so they
    survive llama's `--replace-voiced` re-delivery. No LLM or TTS call is
    made: the show is re-voiced by the next `emcee run`.
    """
    if list_moves:
        if show is not None or profile is not None or delivered or clear:
            _usage("--list takes no package, profile, --delivered or --clear")
    else:
        if show is None:
            _usage("give a package and one of <profile>, --delivered, --clear; or --list")
        if sum([profile is not None, delivered, clear]) != 1:
            _usage("give exactly one of <profile>, --delivered, --clear")

    config = load_config()
    root = _resolve_station_root(config, station_root)
    moves, statuses = _load_station(config, root)   # bad or missing moves.json: refuse first

    if list_moves:
        _echo_moves(config, moves, statuses)
        return

    if clear:
        def live_performance_id() -> str:
            pkg = Package(_resolve_package(config, show, station_root))
            pid = manifest_performance_id(pkg.manifest())
            if pid is None:
                raise EmceeError(f"{pkg.dir.name} has no source.performance_id; "
                                 "no move can be recorded for it")
            return pid

        typer.echo(f"cleared: {clear_move(config.root, show, live_performance_id)}")
        return

    pkg = Package(_resolve_package(config, show, station_root))
    manifest = pkg.manifest()  # unsupported or unreadable: EmceeError -> exit 1
    pid = manifest_performance_id(manifest)
    if pid is None:
        raise EmceeError(f"{pkg.dir.name} has no source.performance_id; "
                         "a move cannot be recorded for it")
    delivered_profile = manifest_profile(manifest)
    target = delivered_profile if delivered else profile
    if target_problem(config, target, delivered_profile) is not None:
        raise EmceeError(
            f"no [assign.profiles.{target}] entry: a move must target an assigned profile "
            f"or the delivered one ({profile_label(delivered_profile)})")
    before = effective_profile(config, moves, manifest).profile
    if not record_move(config.root, pid, target, pkg.dir.name, moved_at=_utc_now()):
        typer.echo(f"unchanged: {pkg.dir.name}  move to {profile_label(target)} already recorded")
        return
    try:
        a = assess(pkg, config, load_moves(config.root))
    except Exception as exc:
        typer.echo(f"moved: {pkg.dir.name}  {profile_label(before)} -> {profile_label(target)} "
                   f"(state unknown: {_typed_error(exc)})")
        return
    after = profile_label(a.effective.profile)
    # The state is the profile check's, not full readiness (a missing clip or
    # broadcast.m3u still reads "ready"). Missing track audio replaces any
    # "voiced on the next run" claim: `run` skips such a package.
    missing = (f"{a.missing_tracks} audio file(s) missing — re-deliver from llama"
               if a.missing_tracks else None)
    if not a.voiced:
        state = "unvoiced; " + (missing or f"voiced as {after} on the next emcee run")
    elif a.profile_reason is None:
        state = f"ready; already voiced as {after}" + (f"; {missing}" if missing else "")
    else:
        state = "pending; " + (missing or "voiced on the next emcee run")
    typer.echo(f"moved: {pkg.dir.name}  {profile_label(before)} -> {after} ({state})")


def _usage(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(2)


def _abs_clip(path: str) -> str:
    """voice_clone is stored absolute and resolved: the mlx-audio server
    reads the clip from its own working directory."""
    return str(Path(path).expanduser().resolve())


def _draft_transcript(config: EmceeConfig, clip: str) -> str:
    """`--transcribe`: draft voice_clone_text by transcribing `clip` with
    verification's STT client and [tts.mlx_audio] stt_model, print it, and
    return it only on confirmation. With [tts.verify] backends empty the STT
    model is unloaded afterwards (the server keeps every model resident)."""
    mlx = config.tts.mlx_audio
    if not mlx.stt_model:
        _usage("--transcribe needs [tts.mlx_audio] stt_model (a speech-to-text model on "
               "the mlx-audio server)")
    try:
        audio = Path(clip).expanduser().read_bytes()
    except OSError as exc:
        raise EmceeError(f"cannot read the voice clone {clip}: {exc}") from exc
    stt = SttClient(url=mlx.url, model=mlx.stt_model, timeout_s=mlx.timeout_s)
    try:
        try:
            text = stt.transcribe(audio)
        finally:
            # Memory on the host is tight: free the STT model even when the
            # transcription failed (unless verification keeps it in use).
            if not config.tts.verify.backends:
                try:
                    stt.unload()
                except SpeechError as exc:
                    typer.echo(f"note: {exc}", err=True)
    finally:
        stt.close()
    if not text:
        raise EmceeError("the transcription came back empty; give --voice-clone-text by hand")
    typer.echo("transcript draft:")
    typer.echo(text)
    if not typer.confirm("use this transcript?", default=False):
        typer.echo("transcript not written; presenter unchanged", err=True)
        raise typer.Exit(1)
    return text


def _pin_label(p: Presenter) -> str:
    return f"tts={p.tts}" + (f" tts_model={p.tts_model}" if p.tts_model else "")


def _read_character_file(path: Path) -> str:
    """The --character-file read shared by `presenter add` and `edit`."""
    try:
        return path.read_text().strip()
    except OSError as exc:
        typer.echo(f"cannot read --character-file {path}: {exc}", err=True)
        raise typer.Exit(1)


def _build_presenter(fields: dict) -> Presenter:
    """Validate `fields` whole into a Presenter (never model_copy, which skips
    validators); any rejection prints `invalid presenter: ...` and exits 1."""
    try:
        return Presenter.model_validate(fields)
    except Exception as exc:
        typer.echo(f"invalid presenter: {exc}", err=True)
        raise typer.Exit(1)


@presenter_app.command("add")
def presenter_add(
    id: str = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
    sex: str = typer.Option(..., "--sex"),
    voice: str = typer.Option(None, "--voice"),
    voice_clone: str = typer.Option(None, "--voice-clone",
                                    help="Reference clip, stored as an absolute path"),
    voice_clone_text: str = typer.Option(None, "--voice-clone-text",
                                         help="Transcript of the voice clone"),
    character: str = typer.Option(None, "--character"),
    character_file: Path = typer.Option(None, "--character-file"),
    bed: str = typer.Option(None, "--bed"),
    tts: str = typer.Option(None, "--tts",
                            help="Pin a TTS backend: voxtral, elevenlabs or mlx_audio"),
    tts_model: str = typer.Option(None, "--tts-model", help="mlx_audio model for this presenter"),
    transcribe: bool = typer.Option(
        False, "--transcribe",
        help="Draft voice_clone_text by transcribing the clip on the mlx-audio server; "
             "written only on confirmation"),
    force: bool = typer.Option(False, "--force"),
):
    """Create a presenter (on-air host)."""
    config = load_config()
    root = config.root
    if bool(character) == bool(character_file):
        typer.echo("give exactly one of --character / --character-file", err=True)
        raise typer.Exit(1)
    if transcribe and voice_clone_text is not None:
        _usage("--transcribe and --voice-clone-text are mutually exclusive")
    if transcribe and not voice_clone:
        _usage("--transcribe needs --voice-clone")
    text = character if character else _read_character_file(character_file)
    dest = root / "presenters" / f"{id}.toml"
    if dest.exists() and not force:
        typer.echo(f"presenter {id!r} exists: {dest} (use --force to overwrite)", err=True)
        raise typer.Exit(1)
    fields = dict(id=id, name=name, sex=sex, voice=voice,
                  voice_clone=_abs_clip(voice_clone) if voice_clone else None,
                  character=text, bed=bed, tts=tts, tts_model=tts_model,
                  voice_clone_text=voice_clone_text)
    if transcribe:
        _build_presenter({**fields, "voice_clone_text": "draft"})  # every other rule first
        fields["voice_clone_text"] = _draft_transcript(config, fields["voice_clone"])
    p = _build_presenter(fields)
    typer.echo(f"saved: {save_presenter(root, p)}")


@presenter_app.command("edit")
def presenter_edit(
    id: str = typer.Argument(...),
    name: str = typer.Option(None, "--name"),
    sex: str = typer.Option(None, "--sex"),
    character: str = typer.Option(None, "--character"),
    character_file: Path = typer.Option(None, "--character-file"),
    voice: str = typer.Option(None, "--voice",
                              help="Preset voice; clears voice_clone and voice_clone_text"),
    voice_clone: str = typer.Option(
        None, "--voice-clone",
        help="Reference clip, stored as an absolute path; clears voice, and clears "
             "voice_clone_text unless --voice-clone-text or --transcribe gives a new one"),
    voice_clone_text: str = typer.Option(None, "--voice-clone-text",
                                         help="Transcript of the voice clone"),
    bed: str = typer.Option(None, "--bed"),
    tts: str = typer.Option(None, "--tts",
                            help="Pin a TTS backend: voxtral, elevenlabs or mlx_audio"),
    tts_model: str = typer.Option(None, "--tts-model", help="mlx_audio model for this presenter"),
    clear_tts: bool = typer.Option(False, "--clear-tts"),
    clear_tts_model: bool = typer.Option(False, "--clear-tts-model"),
    clear_bed: bool = typer.Option(False, "--clear-bed"),
    clear_voice_clone_text: bool = typer.Option(False, "--clear-voice-clone-text"),
    transcribe: bool = typer.Option(
        False, "--transcribe",
        help="Draft voice_clone_text by transcribing the (resulting) clip on the mlx-audio "
             "server; written only on confirmation"),
):
    """Edit a presenter; unspecified fields keep their values.

    The edit is validated whole (exactly the rules `presenters/<id>.toml` is
    loaded with) before an atomic save; any rejection -- validation, a
    declined transcript, an unreachable server -- leaves the file untouched.
    """
    config = load_config()
    old = load_presenter(config.root, id)  # PresenterError -> main_cli boundary
    for value, clear, set_flag, clear_flag in (
            (tts, clear_tts, "--tts", "--clear-tts"),
            (tts_model, clear_tts_model, "--tts-model", "--clear-tts-model"),
            (bed, clear_bed, "--bed", "--clear-bed"),
            (voice_clone_text, clear_voice_clone_text, "--voice-clone-text",
             "--clear-voice-clone-text")):
        if value is not None and clear:
            _usage(f"{set_flag} and {clear_flag} are mutually exclusive")
    if voice is not None and voice_clone is not None:
        _usage("--voice and --voice-clone are mutually exclusive")
    if character is not None and character_file is not None:
        _usage("give at most one of --character / --character-file")
    if transcribe and voice_clone_text is not None:
        _usage("--transcribe and --voice-clone-text are mutually exclusive")
    if transcribe and clear_voice_clone_text:
        _usage("--transcribe and --clear-voice-clone-text are mutually exclusive")

    changes: dict = {}
    if name is not None:
        changes["name"] = name
    if sex is not None:
        changes["sex"] = sex
    if character is not None:
        changes["character"] = character
    if character_file is not None:
        changes["character"] = _read_character_file(character_file)
    if voice is not None:
        changes.update(voice=voice, voice_clone=None, voice_clone_text=None)
    if voice_clone is not None:
        changes.update(voice_clone=_abs_clip(voice_clone), voice=None)
        if voice_clone_text is None and not transcribe:
            changes["voice_clone_text"] = None  # forces a fresh transcript for an mlx pin
    if voice_clone_text is not None:
        changes["voice_clone_text"] = voice_clone_text
    if clear_voice_clone_text:
        changes["voice_clone_text"] = None
    if bed is not None:
        changes["bed"] = bed
    if clear_bed:
        changes["bed"] = None
    if tts is not None:
        changes["tts"] = tts
    if clear_tts:
        changes["tts"] = None
    if tts_model is not None:
        changes["tts_model"] = tts_model
    if clear_tts_model:
        changes["tts_model"] = None
    if not changes and not transcribe:
        _usage("nothing to edit: give at least one field option")

    def merged(extra: dict | None = None) -> Presenter:
        # model_validate on the whole merge, never model_copy(update=...),
        # which skips validators.
        return _build_presenter({**old.model_dump(), **changes, **(extra or {})})

    if transcribe:
        clip = changes.get("voice_clone", old.voice_clone)
        if not clip:
            _usage("--transcribe needs a voice clone (this presenter has a preset voice)")
        merged({"voice_clone_text": "draft"})  # every other rule, before transcribing
        changes["voice_clone_text"] = _draft_transcript(config, clip)
    new = merged()
    typer.echo(f"saved: {save_presenter(config.root, new)}")


@presenter_app.command("list")
def presenter_list():
    """List presenters."""
    root = load_config().root
    rows = list_presenters(root)
    if not rows:
        typer.echo("no presenters")
        return
    for pid, p in rows:
        if isinstance(p, str):
            typer.echo(f"{pid:16.16s} (invalid: {p})")
        else:
            v = p.voice or f"clone:{p.voice_clone}"
            pin = f"  {_pin_label(p)}" if p.tts else ""
            typer.echo(f"{pid:16.16s} {p.name:20.20s} {p.sex:8.8s} {v}{pin}")


@presenter_app.command("show")
def presenter_show(id: str = typer.Argument(...)):
    """Show one presenter's fields."""
    root = load_config().root
    p = load_presenter(root, id)     # PresenterError -> main_cli boundary
    v = p.voice or f"clone:{p.voice_clone}"
    typer.echo(f"{p.name}  ({p.sex})  voice={v}" + (f"  bed={p.bed}" if p.bed else "")
               + (f"  {_pin_label(p)}" if p.tts else ""))
    typer.echo("character:")
    typer.echo(p.character)
    if p.tts and p.voice_clone_text:
        typer.echo("transcript:")
        typer.echo(p.voice_clone_text)


@presenter_app.command("remove")
def presenter_remove(
    id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
    force: bool = typer.Option(False, "--force",
                               help="Remove even if an assignment still names this presenter"),
):
    """Delete a presenter's TOML file. Refuses if an assignment still names
    it as its presenter -- pass --force to remove it anyway."""
    config = load_config()
    root = config.root
    path = root / "presenters" / f"{id}.toml"
    if not path.exists():
        raise PresenterError(f"no presenter {id!r}: {path} does not exist")
    if not force:
        users = _assignments_using_presenter(config, id)
        if users:
            typer.echo(f"presenter {id} is used by: {', '.join(users)} "
                       "— --force to remove anyway", err=True)
            raise typer.Exit(1)
    if not yes and not typer.confirm(f"remove presenter {id!r}?", default=False):
        return
    delete_presenter(root, id)
    typer.echo(f"removed: {path}")


@config_app.command("init")
def config_init(
    stdout: bool = typer.Option(False, "--stdout",
                                help="Print the default config instead of writing a file"),
    config_path: Path = typer.Option(None, "--config",
                                     help="Target file (default: EMCEE_ROOT or ~/.emcee, "
                                          "then /config.toml)"),
):
    """Seed a config file with the baked-in defaults, fully commented."""
    if stdout:
        typer.echo(DEFAULT_CONFIG_TOML, nl=False)
        return
    target = config_path or default_root() / "config.toml"
    if target.exists():
        typer.echo(f"{target} already exists - not overwriting "
                   "(delete it first if you mean to reseed)", err=True)
        raise typer.Exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML)
    typer.echo(f"wrote {target}")
    typer.echo("note: config values replace built-in defaults (no merging); "
               "the defaults are written out so additive edits keep them")


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
