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

from pathlib import Path

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


def resolve_assignment(config: EmceeConfig, manifest: dict) -> tuple[Presenter | None, str | None]:
    """(presenter, title) for a delivered package, keyed off the llama
    profile name stamped at `manifest["source"]["profile"]`:

    1. a matching `[assign.profiles.<profile>]` entry -> that presenter + its title
    2. no match (or no profile stamped) -> `[assign] default` presenter, no title
    3. no default either -> (None, None), the neutral house narrator
    """
    profile = manifest.get("source", {}).get("profile")
    if profile:
        assignment = config.assign.profiles.get(profile)
        if assignment is not None:
            return load_presenter(config.root, assignment.presenter), assignment.title
    if config.assign.default:
        return load_presenter(config.root, config.assign.default), None
    return None, None


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
        voice = presenter.voice or presenter.voice_clone
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
