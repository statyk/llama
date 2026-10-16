"""The `process_package` orchestrator: script + DJ audio + broadcast.m3u for
one delivered llama package, plus presenter assignment and voice resolution.

`resolve_voicing` resolves one package exactly once -- its effective
profile (station.effective_profile: move > artist rule > llama's), the
presenter and on-air title that profile is assigned, and the TTS backend --
and `process_package` receives that `Voicing` rather than re-deriving any
of it, so voice, persona, title, bed and the recorded profile can never
come from two different resolutions.
`process_package` is emcee's analog of llama's `run_package`
(`stages/package.py:259-...`): it writes the script, synthesizes DJ audio,
assembles `broadcast.m3u`, and rewrites the manifest's `dj_notes`/`dj_audio`
blocks -- in that order, with the manifest last (spec section 2: the
manifest rewrite is the package's success marker).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from herder import HerderError, provider_for

from emcee.audio import _synthesize_dj_audio, broadcast_m3u_text, detail
from emcee.config import EmceeConfig
from emcee.errors import EmceeError
from emcee.models import DJAudioBlock, ScriptNotes, TTSRecord
from emcee.moves import Moves
from emcee.package_io import Package, rewrite_manifest
from emcee.presenters import Presenter, load_presenter
from emcee.scriptwrite import (_fold, render_notes_md, rephrase_problems, rephrase_segment,
                               script_guard, write_script)
from emcee.speech_text import load_lexicon
from emcee.station import Effective, effective_profile, move_target_problem
from emcee.tts import speech_provider_for
from emcee.tts.bed import Bed
from emcee.tts.provider import SpeechBlocked
from emcee.tts.resolve import TTSResolution, resolve_tts
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


def resolve_assignment(config: EmceeConfig, profile: str | None) -> tuple[Presenter | None, str | None]:
    """(presenter, title) for an EFFECTIVE profile (`Voicing.effective`).
    Takes a profile, never a manifest, so no caller can key it on the
    delivered profile by accident; the rules live in `assignment_for`."""
    view = assignment_for(config, profile)
    if view.presenter is None:
        return None, None
    return load_presenter(config.root, view.presenter), view.title


@dataclass(frozen=True)
class Voicing:
    """Everything one package's voicing is resolved to, once."""
    effective: Effective
    presenter: Presenter | None
    title: str | None
    resolution: TTSResolution


def resolve_voicing(config: EmceeConfig, moves: Moves, manifest: dict) -> Voicing:
    """The single resolution for one package: a recorded move whose target
    cannot be voiced is refused (use-time validation, spec section 3); then
    the effective profile, its presenter and title, and the presenter's TTS.
    Pure apart from reading the presenter's TOML: raises before any spend
    and before `_process_one` clears the manifest."""
    problem = move_target_problem(config, moves, manifest)
    if problem is not None:
        raise EmceeError(problem)
    effective = effective_profile(config, moves, manifest)
    presenter, title = resolve_assignment(config, effective.profile)
    return Voicing(effective, presenter, title, resolve_tts(config, presenter))


def _resolve_bed(config: EmceeConfig, presenter: Presenter | None) -> Bed | None:
    """Port of llama's resolve_bed (`cli.py:177-184`): a presenter's own bed
    if set, else the station default. Gain is always the station
    `config.tts.bed_gain_db` -- a presenter never overrides gain."""
    path = presenter.bed if presenter is not None and presenter.bed else config.tts.bed
    if not path:
        return None
    return Bed(Path(path), config.tts.bed_gain_db)


def _speech_from(config: EmceeConfig, presenter: Presenter | None, resolution: TTSResolution):
    """(speech_provider, bed) for an already-resolved presenter and TTS
    resolution. A presenter fully owns its voice; with no presenter the
    house [tts] voice/voice_clone/voice_clone_text are used."""
    if presenter is not None:
        voice, clone, text = presenter.voice, presenter.voice_clone, presenter.voice_clone_text
    else:
        voice, clone, text = config.tts.voice, config.tts.voice_clone, config.tts.voice_clone_text
    if not (voice or clone):
        raise EmceeError(
            "voice is active but none is configured: set [tts] voice, "
            "[tts] voice_clone, or give the profile a presenter"
        )
    speech = speech_provider_for(config, resolution, voice=voice, clone_ref=clone,
                                 clone_text=text)
    return speech, _resolve_bed(config, presenter)


def speech_for(config: EmceeConfig, presenter: Presenter | None):
    """(speech_provider, bed) for a presenter (or the house voice), resolving
    its TTS first (`resolve_tts`, pure: an unpinned presenter under an
    mlx_audio house raises here). Used by `emcee say`; package voicing uses
    `speech_for_voicing` so the TTS is resolved once."""
    return _speech_from(config, presenter, resolve_tts(config, presenter))


def speech_for_voicing(config: EmceeConfig, voicing: Voicing):
    """(speech_provider, bed) for one package's `Voicing`."""
    return _speech_from(config, voicing.presenter, voicing.resolution)


def ad_hoc_speech(config: EmceeConfig, *, clone_ref: str | None = None,
                  clone_text: str | None = None, voice: str | None = None,
                  presenter: Presenter | None = None):
    """The speech provider for one ad-hoc `emcee say` run.

    At most one voice source may be named: a reference clip to clone
    (`--clone`, with its transcript `--clone-text`), a preset voice
    (`--voice`), or an existing presenter (`--presenter`, resolved exactly
    as a voiced package's presenter is: its pin, its clip, its transcript).
    With none of them, the house voice via `speech_for`. `--clone`/`--voice`
    voice on the HOUSE backend.

    Unlike `speech_for` this returns the provider alone -- `say` resolves
    its bed separately through `ad_hoc_bed`, which layers the command
    line's overrides on top.
    """
    named = [s for s in (clone_ref, voice, presenter) if s]
    if len(named) > 1:
        raise EmceeError("--clone, --voice and --presenter are mutually exclusive")
    if presenter is not None:
        speech, _ = speech_for(config, presenter)
        return speech
    if clone_ref:
        return speech_provider_for(config, resolve_tts(config, None), voice=None,
                                   clone_ref=clone_ref, clone_text=clone_text)
    if voice:
        return speech_provider_for(config, resolve_tts(config, None), voice=voice,
                                   clone_ref=None, clone_text=None)
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


# Rephrase attempts per blocked segment per process_package call. An attempt
# is consumed by a guard/containment failure, an unchanged reply, or the
# revision being blocked again.
MAX_REPHRASES = 2


def _segment_text(notes: ScriptNotes, stem: str) -> str:
    if stem == "99-outro":
        return notes.outro
    return notes.set_intros[stem.removeprefix("set").removesuffix("-intro")]


def _with_segment(notes: ScriptNotes, stem: str, text: str) -> ScriptNotes:
    # model_copy is shallow: build a new set_intros dict, never mutate notes'.
    if stem == "99-outro":
        return notes.model_copy(update={"outro": text})
    key = stem.removeprefix("set").removesuffix("-intro")
    return notes.model_copy(update={"set_intros": {**notes.set_intros, key: text}})


def _repair(notes: ScriptNotes, blocked: SpeechBlocked, manifest: dict, provider,
            used: dict[str, int], last: dict[str, str], repaired: set[str],
            pkg_dir: Path) -> ScriptNotes:
    """Reword the segment `blocked` names until a revision passes
    `rephrase_problems` and `script_guard`, within MAX_REPHRASES; return the
    accepted notes. Each attempt rephrases the ADOPTED text, never a rejected
    candidate, and a rejected candidate is never returned."""
    seg = blocked.segment
    narration = manifest["briefing"]["narration"]
    cats = f" ({', '.join(blocked.categories)})" if blocked.categories else ""
    if seg in repaired:
        last[seg] = f'your previous rewording was also blocked: "{blocked.text}"'
    current = _segment_text(notes, seg)
    while used.get(seg, 0) < MAX_REPHRASES:
        used[seg] = used.get(seg, 0) + 1
        try:
            revised = rephrase_segment(provider, current, blocked.text, blocked.categories,
                                       feedback=last.get(seg, ""))
        except HerderError as e:
            raise EmceeError(
                f"content filter blocked a sentence in {seg}{cats}; "
                f"the rephrase task failed: {e}",
                details=[f'blocked: "{blocked.text}"',
                         f"re-run `emcee voice {pkg_dir}` for a fresh script"],
            ) from e
        candidate = _with_segment(notes, seg, revised)
        # Whitespace/typography-only differences count as unchanged: voicing
        # them would resend the identical refused sentence.
        if not revised or _fold(revised) == _fold(current):
            problems = ["the rephrase returned the segment unchanged"]
        else:
            problems = (rephrase_problems(current, revised, manifest)
                        + script_guard(candidate, manifest, narration))
        if not problems:
            repaired.add(seg)
            detail(f"content filter blocked a sentence in {seg}{cats}; rephrased")
            detail(f'  blocked: "{blocked.text}"')
            detail(f'  revised: "{revised}"')
            return candidate
        last[seg] = "; ".join(problems)
    raise EmceeError(
        f"content filter blocked a sentence in {seg}{cats}; "
        f"{MAX_REPHRASES} rephrase attempts failed",
        details=[f'blocked: "{blocked.text}"',
                 f"last attempt: {last.get(seg, 'unknown')}",
                 f"re-run `emcee voice {pkg_dir}` for a fresh script"],
    )


def process_package(config: EmceeConfig, pkg: Package, speech, force: bool = False, *,
                    voicing: Voicing) -> None:
    """Script, voice, and broadcast-assemble one delivered package.

    Order: write_script -> render dj-notes.md -> synthesize DJ audio ->
    broadcast.m3u -> rewrite the manifest's dj_notes/dj_audio blocks last.
    The manifest rewrite is the package's success marker: on any failure
    this raises and the manifest is left byte-for-byte as it was.

    A TTS content-filter block (`SpeechBlocked`) is repaired in place by
    `_repair`.

    CALLER CONTRACT: `voicing` is THIS package's `resolve_voicing` result
    and `speech` is `speech_for_voicing(config, voicing)` -- never resolved
    for one package and reused for another. The persona, title and bed all
    come from `voicing.presenter`, and the recorded `dj_audio` from
    `voicing` plus `speech`; nothing here re-resolves, so a hoisted
    resolution would voice, script AND record the wrong presenter
    consistently.
    """
    manifest = pkg.manifest()
    presenter, title = voicing.presenter, voicing.title

    llm_provider = provider_for(config.llm_settings(), "scriptwrite")
    notes = write_script(pkg, llm_provider, presenter, title)
    atomic_write_text(pkg.dir / "dj-notes.md", render_notes_md(notes, manifest))

    bed = _resolve_bed(config, presenter)
    lexicon = load_lexicon(config.root)
    # A TTS content-filter block is repaired in place: reword the segment,
    # re-guard, rewrite dj-notes.md, re-synthesize. Clips already rendered
    # this call come from the cache (even under --force, via `rendered`).
    rendered: set[str] = set()
    used: dict[str, int] = {}
    last: dict[str, str] = {}
    repaired: set[str] = set()
    rephraser = None
    while True:
        try:
            clips = _synthesize_dj_audio(pkg.dir, notes, speech, force,
                                         chunk=config.tts.chunk, lexicon=lexicon,
                                         bed=bed, rendered=rendered)
            break
        except SpeechBlocked as blocked:
            if blocked.whole_passage or blocked.segment is None:
                raise
            if rephraser is None:  # built lazily: most packages never need it
                rephraser = provider_for(config.llm_settings(), "rephrase")
            notes = _repair(notes, blocked, manifest, rephraser, used, last, repaired, pkg.dir)
            atomic_write_text(pkg.dir / "dj-notes.md", render_notes_md(notes, manifest))

    atomic_write_text(pkg.dir / "broadcast.m3u",
                      broadcast_m3u_text(manifest["tracks"], clips))

    dj_audio = DJAudioBlock(
        set_intros=clips.set_intros, outro=clips.outro,
        presenter=presenter.id if presenter is not None else None,
        profile=voicing.effective.profile, profile_source=voicing.effective.source,
        tts=TTSRecord(backend=voicing.resolution.backend, model=speech.model,
                      voice=speech.voice))
    rewrite_manifest(pkg, dj_notes=notes, dj_audio=dj_audio)
