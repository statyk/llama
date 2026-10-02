"""The `process_package` orchestrator: script + DJ audio + broadcast.m3u for
one delivered llama package, plus presenter assignment and voice resolution.

`resolve_assignment`/`speech_for` are ports of llama's assignment-driven
voice resolution (`cli.py:136-195`, folded together since emcee resolves a
presenter from the package's manifest rather than from a `Profile`).
`process_package` is emcee's analog of llama's `run_package`
(`stages/package.py:259-...`): it writes the script, synthesizes DJ audio,
assembles `broadcast.m3u`, and rewrites the manifest's `dj_notes`/`dj_audio`
blocks -- in that order, with the manifest last (spec section 2: the
manifest rewrite is the package's success marker).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from herder import provider_for

from emcee.audio import _synthesize_dj_audio, broadcast_m3u_text
from emcee.config import EmceeConfig
from emcee.errors import EmceeError
from emcee.package_io import Package, rewrite_manifest
from emcee.presenters import Presenter, load_presenter
from emcee.scriptwrite import render_notes_md, write_script
from emcee.speech_text import load_lexicon
from emcee.tts import speech_provider_for
from emcee.tts.bed import Bed
from emcee.workspace import atomic_write_text


@dataclass(frozen=True)
class AssignmentView:
    """Which presenter a package resolves to, without loading any TOML."""
    presenter: str | None
    title: str | None
    source: Literal["profile", "default", "house"]


def assignment_for(config: EmceeConfig, profile: str | None) -> AssignmentView:
    """The three assignment rules, pure (no presenter file is read):

    1. a matching `[assign.profiles.<profile>]` entry -> that presenter + its title
    2. no match (or no profile) -> `[assign] default` presenter, no title
    3. no default either -> the neutral house narrator (no presenter)
    """
    if profile:
        assignment = config.assign.profiles.get(profile)
        if assignment is not None:
            return AssignmentView(assignment.presenter, assignment.title, "profile")
    if config.assign.default:
        return AssignmentView(config.assign.default, None, "default")
    return AssignmentView(None, None, "house")


def presenter_label(view: AssignmentView) -> str:
    """`<id>` for an explicit profile assignment, `<id> (default)` for the
    station default, `house` for no presenter."""
    if view.presenter is None:
        return "house"
    return f"{view.presenter} (default)" if view.source == "default" else view.presenter


def resolve_assignment(config: EmceeConfig, manifest: dict) -> tuple[Presenter | None, str | None]:
    """(presenter, title) for a delivered package, keyed off the llama
    profile name stamped at `manifest["source"]["profile"]`; the rules live
    in `assignment_for`."""
    view = assignment_for(config, manifest.get("source", {}).get("profile"))
    if view.presenter is None:
        return None, None
    return load_presenter(config.root, view.presenter), view.title


def _resolve_bed(config: EmceeConfig, presenter: Presenter | None) -> Bed | None:
    """Port of llama's resolve_bed (`cli.py:177-184`): a presenter's own bed
    if set, else the station default. Gain is always the station
    `config.tts.bed_gain_db` -- a presenter never overrides gain."""
    path = presenter.bed if presenter is not None and presenter.bed else config.tts.bed
    if not path:
        return None
    return Bed(Path(path), config.tts.bed_gain_db)


def speech_for(config: EmceeConfig, presenter: Presenter | None):
    """(speech_provider, bed) for a resolved presenter (or the house voice).

    Port of llama's `_speech_for` (`cli.py:167-174`) folded together with
    `resolve_bed` (`cli.py:186-195`), applying `_resolve_voice`'s
    (`cli.py:136-157`) presenter-owns-its-voice precedence rule -- minus the
    `[tts] enabled` gate, since emcee has no station-wide voice toggle (it
    always voices what it processes).

    A presenter fully owns its voice: `presenter.voice or
    presenter.voice_clone` is resolved, and `presenter.voice_clone` is
    passed as `clone_ref` -- the station `[tts] voice_clone` never bleeds
    into a presenter's run. With no presenter, falls back to the house
    `config.tts.voice or config.tts.voice_clone`, `clone_ref=
    config.tts.voice_clone`. Raises `EmceeError` if no voice can be
    resolved at all -- there is no profile to fault here (unlike llama),
    so the message instead points at `[tts] voice`/`[tts] voice_clone`/the
    presenter's own fields.
    """
    if presenter is not None:
        voice = presenter.voice_id  # presenter.voice or presenter.voice_clone
        clone = presenter.voice_clone
    else:
        voice = config.tts.voice or config.tts.voice_clone
        clone = config.tts.voice_clone
    if not voice:
        raise EmceeError(
            "voice is active but none is configured: set [tts] voice, "
            "[tts] voice_clone, or give the profile a presenter"
        )
    speech = speech_provider_for(config, voice, clone_ref=clone)
    return speech, _resolve_bed(config, presenter)


def ad_hoc_speech(config: EmceeConfig, *, clone_ref: str | None = None,
                  voice: str | None = None, presenter: Presenter | None = None):
    """The speech provider for one ad-hoc `emcee say` run.

    At most one voice source may be named: a reference clip to clone
    (`--clone`), a preset voice (`--voice`), or an existing presenter
    (`--presenter`, which brings its own voice or voice clone exactly as a
    voiced package would). With none of them, falls back to the house
    `[tts] voice`/`voice_clone` via `speech_for`, whose error message
    already points at the right config keys when nothing is set.

    Unlike `speech_for` this returns the provider alone -- `say` resolves
    its bed separately through `ad_hoc_bed`, which layers the command
    line's overrides on top.
    """
    named = [s for s in (clone_ref, voice, presenter) if s]
    if len(named) > 1:
        raise EmceeError("--clone, --voice and --presenter are mutually exclusive")
    if presenter is not None:
        return speech_provider_for(config, presenter.voice_id,
                                   clone_ref=presenter.voice_clone)
    if clone_ref:
        return speech_provider_for(config, None, clone_ref=clone_ref)
    if voice:
        return speech_provider_for(config, voice)
    speech, _ = speech_for(config, None)
    return speech


def ad_hoc_bed(config: EmceeConfig, presenter: Presenter | None, *,
               bed_path: Path | None = None, no_bed: bool = False,
               gain_db: float | None = None) -> Bed | None:
    """The bed for one ad-hoc `emcee say` run, or None for a dry read.

    Resolution order, highest first: `--no-bed` (suppresses every source),
    `--bed PATH`, the presenter's own bed, `[tts] bed`. Gain comes from
    `--bed-gain` when given, else the station `[tts] bed_gain_db` -- so a
    presenter still never overrides gain, matching `_resolve_bed`.
    """
    if no_bed:
        return None
    gain = config.tts.bed_gain_db if gain_db is None else gain_db
    if bed_path is not None:
        return Bed(Path(bed_path), gain)
    base = _resolve_bed(config, presenter)
    return None if base is None else Bed(base.path, gain)


def process_package(config: EmceeConfig, pkg: Package, speech, force: bool = False) -> None:
    """Script, voice, and broadcast-assemble one delivered package.

    Order: write_script -> render dj-notes.md -> synthesize DJ audio ->
    broadcast.m3u -> rewrite the manifest's dj_notes/dj_audio blocks last.
    The manifest rewrite is the package's success marker (spec section 2):
    on any failure this raises and the manifest is left byte-for-byte as it
    was, so a partially-processed package still reads `dj_notes`/`dj_audio`
    as `None` and stays `pending` in `station.readiness` regardless of any
    dj-notes.md / dj-audio/*.mp3 / broadcast.m3u files a failed run left
    behind.

    `speech` is the already-resolved speech provider for this package's
    assigned presenter (built by the caller via `speech_for`, or a test
    double); `process_package` re-derives the presenter (and its bed) itself
    from the manifest so it can build the scriptwriting persona and the
    correct bed without the caller having to thread them through separately.

    CALLER CONTRACT: `speech` MUST be the provider `speech_for` returned for
    THIS package's own `resolve_assignment` result -- not one resolved for a
    different package and reused. Nothing here checks that `speech` and the
    bed this function derives came from the same presenter: a batch loop
    that resolves a presenter and builds `speech` once, then calls
    `process_package` for multiple packages, would silently pair presenter
    X's voice with presenter Y's bed (and gain) for any package assigned to
    Y -- no exception, wrong audio, and a cache key that faithfully records
    the wrong render. Callers (e.g. `emcee run` iterating a station) must
    resolve `speech_for` fresh per package, not hoist it above the loop.
    """
    manifest = pkg.manifest()
    presenter, title = resolve_assignment(config, manifest)

    llm_provider = provider_for(config.llm_settings(), "scriptwrite")
    notes = write_script(pkg, llm_provider, presenter, title)
    atomic_write_text(pkg.dir / "dj-notes.md", render_notes_md(notes, manifest))

    bed = _resolve_bed(config, presenter)
    lexicon = load_lexicon(config.root)
    dj_audio = _synthesize_dj_audio(pkg.dir, notes, speech, force,
                                    chunk=config.tts.chunk, lexicon=lexicon, bed=bed)

    atomic_write_text(pkg.dir / "broadcast.m3u",
                      broadcast_m3u_text(manifest["tracks"], dj_audio))

    rewrite_manifest(pkg, dj_notes=notes, dj_audio=dj_audio)
