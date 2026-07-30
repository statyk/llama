"""CLI boundary: typer app + `main_cli` error boundary.

`_COMMAND_ORDER` fixes the `--help` panel ordering via `OrderedPanelGroup`,
mirroring llama's `cli.py:57-65` pattern.
"""

import json
import sys
import traceback
from pathlib import Path

import typer
from typer.core import TyperGroup

from herder import HerderError

from emcee.config import DEFAULT_CONFIG_TOML, EmceeConfig, default_root, load_config
from emcee.errors import EmceeError
from emcee.package_io import Package, UnsupportedPackage, rewrite_manifest
from emcee.presenters import (
    Presenter, PresenterError, delete_presenter, list_presenters, load_presenter, save_presenter,
)
from emcee.process import process_package, resolve_assignment, speech_for
from emcee.station import PackageStatus, readiness, scan

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


def _scan_broad(root: Path) -> list[PackageStatus]:
    """Re-walk `root` package-by-package, never letting one malformed
    package's `readiness()` check abort the walk.

    `package_io`/`station` deliberately validate no manifest model (see
    `package_io`'s module docstring), so a valid-JSON-but-structurally-wrong
    v3 manifest -- a track dict missing `filename`, `dj_audio` not a dict,
    `tracks` not a list -- raises a bare `KeyError`/`AttributeError`/
    `TypeError` straight out of `readiness()`, escaping both the
    `EmceeError` taxonomy and `station.scan`'s own try/except (which only
    guards `UnsupportedPackage`). This is the fallback `_station_statuses`
    reaches for when the fast path (`station.scan`) blows up on exactly
    that: it mirrors `scan`'s walk but wraps every entry's `manifest()`/
    `readiness()` call individually, reporting a failure as a `PackageStatus`
    with `state="error"` -- a state `station.scan` itself never produces --
    instead of propagating and taking the rest of the batch down with it.
    """
    statuses: list[PackageStatus] = []
    for entry in sorted(Path(root).iterdir()):
        if not entry.is_dir() or not (entry / "manifest.json").exists():
            continue
        pkg = Package(entry)
        try:
            pkg.manifest()
        except UnsupportedPackage:
            version = json.loads(pkg.manifest_path.read_text()).get("schema_version", "?")
            statuses.append(PackageStatus(
                path=entry, state="unsupported",
                reasons=[f"unsupported (v{version} — re-deliver from llama)"],
            ))
            continue
        except Exception as exc:
            statuses.append(PackageStatus(path=entry, state="error", reasons=_error_reasons(exc)))
            continue
        try:
            ok, reasons = readiness(pkg)
        except Exception as exc:
            statuses.append(PackageStatus(path=entry, state="error", reasons=_error_reasons(exc)))
            continue
        statuses.append(PackageStatus(path=entry, state="ready" if ok else "pending", reasons=reasons))
    return statuses


def _station_statuses(root: Path) -> list[PackageStatus]:
    """Every package's status under `root`. Tries `station.scan` first (the
    normal, documented path); if a structurally-mangled manifest makes it
    raise mid-walk (see `_scan_broad`'s docstring), falls back to a
    per-entry-isolated re-walk so one bad package can't take the whole
    report down. `scan`/`readiness` are read-only, so re-walking on the
    fallback path is safe and idempotent.
    """
    try:
        return scan(root)
    except Exception:
        return _scan_broad(root)


def _process_one(config: EmceeConfig, pkg: Package, force: bool) -> None:
    """Script + voice + broadcast-assemble one package. Shared by `run`'s
    per-pending-package loop and `voice`.

    Per the blessed call convention: `resolve_assignment`/`speech_for` are
    resolved fresh here, every call -- never hoisted above a per-package
    loop -- so each package's presenter-derived voice is never accidentally
    reused for a different package.
    """
    manifest = pkg.manifest()
    presenter, title = resolve_assignment(config, manifest)
    speech, bed = speech_for(config, presenter)

    # JUDGMENT CALL: clears the manifest's dj_notes/dj_audio blocks before
    # reprocessing -- but only now, after resolve_assignment/speech_for have
    # already succeeded. `process_package` overwrites `dj-notes.md` well
    # before the manifest write that marks its success, so a mid-pipeline
    # failure on an already-*ready* package would otherwise leave
    # `dj-notes.md` holding the new (unrecorded) script while the manifest
    # -- and therefore `station.readiness` -- still reports the *old*
    # blocks as present, reading "ready" despite the drift. Clearing first
    # means a failure here instead degrades the package to "pending"
    # (self-consistent with llama's `redo --from package`, which unlinks
    # the manifest first). Deliberately placed after resolve_assignment/
    # speech_for, not before: both can fail on configuration alone (a
    # `[assign] default` naming a presenter with no TOML file, no `[tts]
    # voice` configured) with no manifest write ever attempted -- clearing
    # before that point would take a genuinely broadcast-ready package off
    # air over nothing but a config typo, and force every clip to
    # re-synthesize (real TTS spend) on the retry even though nothing was
    # ever going to be overwritten. Harmless on the happy path:
    # `process_package` overwrites both blocks again moments later as its
    # own success marker. It also never touches `dj-audio/segments.json` --
    # the per-clip hash cache that actually drives what `voice --fresh`
    # re-renders -- so it has no effect on `--fresh`'s re-roll behavior.
    rewrite_manifest(pkg, dj_notes=None, dj_audio=None)
    try:
        process_package(config, pkg, speech, force)
    finally:
        # A raising close() must never mask a successful process_package --
        # or, worse, turn a genuinely-completed package into a reported
        # failure (`run` would otherwise print `error: <slug>: ...` and
        # count a `ready` package as failed even though the manifest was
        # already written). Best-effort cleanup only.
        try:
            speech.close()
        except Exception:
            pass


@app.command()
def run(
    force: bool = typer.Option(False, "--force",
                               help="Re-synthesize every DJ clip even if cached"),
    station_root: Path = typer.Option(
        None, "--station-root",
        help="Override \\[station] root for this invocation"),
):
    """Voice every pending package in the station.

    Scans `\\[station] root` (or `--station-root`) and processes every
    package whose derived state is "pending": writes the DJ script,
    synthesizes DJ audio, assembles `broadcast.m3u`, and rewrites the
    manifest's `dj_notes`/`dj_audio` blocks. Packages already "ready" are
    left alone. "unsupported" (pre-v3) packages are reported and never
    modified -- re-deliver them from llama first.

    Per-package failures -- including a structurally invalid manifest
    (e.g. a track missing its filename), since emcee validates no manifest
    model -- are caught broadly and printed as `error: <slug>: <message>`
    plus any indented detail lines (e.g. a scriptwrite guard failure's
    specific fact-check problems). Does not stop the rest of the batch.
    Exits 1 if any package failed.
    """
    config = load_config()
    root = _resolve_station_root(config, station_root)
    statuses = _station_statuses(root)

    failed = False
    processed = 0
    for status in statuses:
        slug = status.path.name
        if status.state == "unsupported":
            typer.echo(f"skip {slug}: {status.reasons[0]}")
            continue
        if status.state == "ready":
            continue
        if status.state == "error":
            typer.echo(f"error: {slug}: {status.reasons[0]}", err=True)
            for line in status.reasons[1:]:
                typer.echo(f"  {line}", err=True)
            failed = True
            continue
        try:
            _process_one(config, Package(status.path), force)
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
    package_path: Path = typer.Argument(..., help="Path to one delivered package directory"),
    fresh: list[str] = typer.Option(
        [], "--fresh",
        help="Re-roll (re-synthesize) just these DJ-clip stems, e.g. set1-intro "
             "or 99-outro; repeatable. Deletes the cached clip first so "
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
):
    """Script + voice + broadcast-assemble ONE delivered package.

    `package_path` names one package directory directly -- use `emcee run`
    to process a whole station. Re-processing an already-"ready" package
    clears its `dj_notes`/`dj_audio` manifest blocks (once presenter/voice
    resolution has already succeeded) before reprocessing, so a
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
    pkg = Package(package_path)
    pkg.manifest()  # validates schema_version >= 3; UnsupportedPackage/EmceeError -> boundary

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
        for stem in stems:
            (audio_dir / f"{stem}.mp3").unlink()
        typer.echo(f"re-rolling {', '.join(stems)} "
                   "(previous take(s) discarded — TTS is non-deterministic)")

    try:
        _process_one(config, pkg, force)
    except Exception as exc:
        typer.echo(f"error: {pkg.dir.name}: {_typed_error(exc)}", err=True)
        for line in getattr(exc, "details", []):
            typer.echo(f"  {line}", err=True)
        raise typer.Exit(1)
    typer.echo(f"voiced: {pkg.dir}")


@app.command("status")
def status_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    station_root: Path = typer.Option(
        None, "--station-root",
        help="Override \\[station] root for this invocation"),
):
    """Table of every package in the station: slug, state, reasons.

    States: "ready" (fully voiced and broadcast-assembled), "pending" (not
    yet, or not fully, processed), "unsupported" (pre-v3 manifest --
    re-deliver from llama). Same `\\[station] root` resolution (including
    `--station-root`) and the same broad per-package error handling as
    `run`: a structurally malformed manifest renders as an "error" row with
    its exception message instead of crashing the whole table.
    """
    config = load_config()
    root = _resolve_station_root(config, station_root)
    statuses = _station_statuses(root)

    if json_output:
        payload = [
            {"slug": s.path.name, "state": s.state, "reasons": s.reasons}
            for s in statuses
        ]
        typer.echo(json.dumps(payload, indent=2))
        return

    if not statuses:
        typer.echo("no packages found")
        return
    width = max(len(s.path.name) for s in statuses)
    for s in statuses:
        reasons = "; ".join(s.reasons)
        typer.echo(f"{s.path.name:<{width}}  {s.state:<12}  {reasons}")


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
    root = load_config().root
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
            typer.echo(f"{pid:16.16s} {p.name:20.20s} {p.sex:8.8s} {v}")


@presenter_app.command("show")
def presenter_show(id: str = typer.Argument(...)):
    """Show one presenter's fields."""
    root = load_config().root
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
