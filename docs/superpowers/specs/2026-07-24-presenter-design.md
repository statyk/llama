# llama — Presenters (Radio-Show Hosts)

**Date:** 2026-07-24
**Status:** Approved design, pending implementation plan

## Purpose

Introduce **presenters**: reusable radio-show hosts. A presenter is a TTS voice
plus an authored character/persona that shapes how the DJ script is written,
plus an on-air identity ("Casey"). A **profile** in llama is a recurring *radio
show* — its curation criteria plus a host — and now references one presenter.
Presenters **never influence curation**; curation stays entirely the profile's
job. The presenter affects exactly two things: the writing/delivery of the DJ
script (the `synthesize` stage) and the spoken voice (the TTS/`package` layer).

Alongside the configurable persona, the synthesize prompt's grounding
**loosens deliberately**: the host may hold opinions, add brief subjective
color, and adopt opinions found in the research/reviews as his or her own —
while concert *facts* stay grounded in the inputs and the structured
hallucination defenses (`vet` + `factual_guard`) stay fully on as the
backstop. A run with no presenter behaves byte-for-byte as today.

## Decisions made during brainstorming

- **Presenter = voice + persona + identity, per file.** New hand-editable
  `presenters/<id>.toml` under the workspace root, symmetric with
  `profiles/<name>.toml`. Fields: `name` (on-air identity, spoken), `sex`
  (informs the character and self-reference — deliberately "sex", not
  "pronouns"; it drives how the host refers to himself/herself), `voice`
  **XOR** `voice_clone` (exactly one), and `character` (free-text, multi-line
  persona description).
- **Profile gains `presenter` and `title`, loses `voice`.**
  `presenter = "<id>"` references `presenters/<id>.toml` by exact name (the
  same resolution profiles use). `title` is the radio show's on-air name
  ("Bluegrass Valley") — the host knows it and drops it occasionally on air.
  It is named `title`, NOT `show_name`, deliberately: "show" is slated for a
  future app-wide rename (see Out of scope). `Profile.voice` (shipped with
  the ElevenLabs DJ-voice feature) is **removed**, along with
  `profile add --voice`; its job is subsumed by the presenter. Migration is
  trivial (solo user, hand-edited profiles): a legacy `voice =` key in a
  profile TOML is silently ignored on load (pydantic default extra-ignore).
- **Voice resolution collapses to presenter-or-house.** Per run: profile names
  a presenter → that presenter's `voice`/`voice_clone` + its persona;
  otherwise (no presenter, or a one-off `llama find` run) → the house default
  `[tts] voice`/`[tts] voice_clone` + the built-in neutral persona. There is
  no three-way source anymore. Run-level stamping (`Criteria.voice`,
  `Provenance.voice`, replay via `--voice/--no-voice`) stays unchanged.
- **Voxtral-first.** `voice_clone` is Voxtral-only. ElevenLabs remains a
  working opt-in backend but is not a design target; no parity investment.
- **Grounding boundary (conservative option "a").** The host must NOT claim
  personal presence at or participation in real events ("I was at Barton
  Hall") — no invented personal history presented as real. Opinions and
  perspective yes; fabricated first-hand experience no. May be revisited.
- **Structured hallucination defenses stay fully on.** `vet_research`
  grounding checks and synthesize's `factual_guard` are unchanged; opinions
  are prose and invisible to them by design — that is the intended seam (see
  the coexistence analysis below).

Resolved at spec time (gaps in the brainstorm, decided here):

- **Persona replays live; voice stays stamped.** `Criteria` and `Provenance`
  gain `presenter` (the id) and `title`; the persona *text* is resolved from
  `presenters/<id>.toml` at synthesize time, every time. Precedent: `[tts]`
  `backend`/`model` are already live config on replay while only the resolved
  voice id is stamped. Live resolution is also what makes character iteration
  work: edit the TOML, `llama redo <show> --from synthesize`, hear the new
  host. A deleted/broken presenter file fails the replay loudly
  (`PresenterError`), never silently reverts to neutral. The voice *string*
  keeps today's stamped-at-process-time semantics exactly as required.
- **Presenter implies voice opt-in.** A profile with a presenter is voiced
  even when `[tts] enabled` is false — carrying forward the shipped
  `Profile.voice` opt-in semantics verbatim. `--no-voice` on a replay still
  strips the audio; the persona keeps shaping the script (persona = writing,
  voice = audio; independent layers).
- **`title` speaks only through a presenter.** The no-presenter prompt must be
  byte-for-byte today's, so a profile with `title` but no `presenter` renders
  the neutral prompt and the title goes unspoken. (In practice `title` and
  `presenter` travel together; this just pins the edge.)
- **`sex` is a free string** (typically `"male"`/`"female"`), passed into the
  persona block as prose. No Literal constraint — flexibility costs nothing
  and the field only informs self-reference.
- **A presenter fully owns its voice.** When a presenter is in play, its
  `voice_clone` (or none) is what reaches the speech factory — the station
  `[tts] voice_clone` never bleeds into a presenter-preset run. The factory
  gains an explicit `clone_ref` parameter and stops reading
  `config.tts.voice_clone` itself; callers resolve it. `voice_clone` with
  `backend = "elevenlabs"` raises `SpeechError` (cloning is Voxtral-only;
  never degrade silently).

## Architecture

### New module — `src/llama/presenters.py`

Symmetric with `profiles.py` (owns `root / "presenters"`, just as
`profiles.py` owns `root / "profiles"`; no `workspace.py` change needed):

```python
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ValidationError, model_validator

from llama.errors import LlamaError


class PresenterError(LlamaError):
    """A presenter file is missing, unparseable, or fails validation."""


class Presenter(BaseModel):
    id: str              # filename stem; injected by load_presenter, not stored in TOML
    name: str            # on-air identity, spoken ("Casey")
    sex: str             # informs character + self-reference ("male" / "female")
    voice: str | None = None        # voxtral preset name (or elevenlabs voice_id)
    voice_clone: str | None = None  # path to a 3-25s reference WAV (voxtral-only)
    character: str       # free-text persona description shaping tone

    @model_validator(mode="after")
    def _exactly_one_voice(self):
        if bool(self.voice) == bool(self.voice_clone):
            raise ValueError("a presenter needs exactly one of voice / voice_clone")
        return self

    @property
    def voice_id(self) -> str:
        """The resolved voice string this presenter stamps into a run."""
        return self.voice or self.voice_clone


def save_presenter(root: Path, presenter: Presenter) -> Path:
    path = root / "presenters" / f"{presenter.id}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(
        presenter.model_dump(mode="json", exclude_none=True, exclude={"id"})))
    return path


def load_presenter(root: Path, presenter_id: str) -> Presenter:
    path = root / "presenters" / f"{presenter_id}.toml"
    if not path.exists():
        raise PresenterError(f"no presenter {presenter_id!r}: {path} does not exist")
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise PresenterError(f"invalid presenter at {path}: {exc}") from exc
    try:
        return Presenter.model_validate({**data, "id": presenter_id})
    except ValidationError as exc:
        raise PresenterError(f"invalid presenter at {path}: {exc}") from exc
```

Presenters are hand-authored (no `llama presenter add` CLI — `save_presenter`
exists for symmetry and tests). A sample file, documented in README/workflow:

```toml
name = "Casey"
sex = "male"
voice = "american-dj"          # or: voice_clone = "/path/to/casey-ref.wav"
character = """
Warm late-night FM veteran. Dry humor, deep tape-collector knowledge, gets
audibly excited about big jams. Keeps it loose but never sloppy.
"""
```

### Profile changes — `src/llama/profiles.py`

```python
class Profile(BaseModel):
    name: str
    criteria: Criteria
    count: int = 1
    human_gate: bool = False
    script: bool = True  # verbatim DJ script (high-tier call); --no-script opts out
    # This radio show's host: presenters/<id>.toml. Naming a presenter voices
    # this profile's runs even when the global [tts] enabled flag is false.
    presenter: str | None = None
    # The radio show's on-air name ("Bluegrass Valley"); the host knows it and
    # drops it occasionally. Named `title` (rename-safe), not `show_name`.
    title: str | None = None
```

`voice` is gone. `save_profile`/`load_profile` are unchanged (None fields
already drop for TOML; unknown legacy keys are ignored on load).

### Run stamping — `src/llama/models.py`

`Criteria` gains, next to `voice`:

```python
    # Presenter id + radio-show title stamped by profile runs (None = house
    # default / one-off run). The persona TEXT is deliberately NOT stamped:
    # it resolves live from presenters/<id>.toml at synthesize time, so
    # editing a character and `redo --from synthesize` takes effect. The
    # voice string above stays stamped-resolved, as before.
    presenter: str | None = None
    title: str | None = None
```

`Provenance` gains the same two fields (default `None`), stamped by
`process_show`, so `llama redo` works standalone. Old `criteria.json` /
`provenance.json` files parse unchanged (defaults).

### Voice resolution — `src/llama/cli.py`

`_resolve_voice` keeps its shape; the third parameter is renamed and
re-documented — it now carries a presenter's voice (profile runs) or the
stamped voice (replays), never a bare profile voice:

```python
def _resolve_voice(config: Config, want: bool | None,
                   explicit_voice: str | None = None) -> str | None:
    """Resolve the run's voice id (None = voice off for this run).

    --no-voice (want=False) always wins. An explicit voice — a presenter's,
    or the stamp on replay — opts in even when [tts] enabled is false.
    Otherwise --voice (want=True) or the global flag activates the house
    default. Voice active with no voice id is an error, never a silent skip.
    """
    if want is False:
        return None
    if explicit_voice:
        return explicit_voice
    if want is True or config.tts.enabled:
        resolved = config.tts.voice or config.tts.voice_clone
        if not resolved:
            raise SpeechError("voice is active but none is configured: set "
                              "[tts] voice, [tts] voice_clone, or give the "
                              "profile a presenter")
        return resolved
    return None
```

`_replay_voice` is unchanged (it already passes the stamp through). A new
helper builds the speech provider so a presenter fully owns its clone:

```python
def _speech_for(config: Config, voice: str | None, presenter: Presenter | None):
    """Speech provider for a resolved voice (None = no voice). A presenter
    fully owns its voice: its voice_clone (or none) is used — the station
    [tts] voice_clone never bleeds into a presenter's run."""
    if voice is None:
        return None
    clone = presenter.voice_clone if presenter is not None else config.tts.voice_clone
    return speech_provider_for(config, voice, clone_ref=clone)
```

### Speech factory — `src/llama/tts/__init__.py`

`speech_provider_for(config, voice)` becomes
`speech_provider_for(config, voice, clone_ref=None)`. The voxtral branch uses
the passed `clone_ref` instead of reading `config.tts.voice_clone` (callers
resolve it — see `_speech_for`); the elevenlabs branch rejects a clone:

```python
    if backend == "voxtral":
        if not (voice or clone_ref):
            raise SpeechError("no Voxtral voice configured: set [tts] voice "
                              "(preset) or [tts] voice_clone (reference clip)")
        return VoxtralProvider(voice=voice, clone_ref=clone_ref,
                               model=config.tts.model, api_key=config.tts.api_key)
    if backend == "elevenlabs":
        if clone_ref:
            raise SpeechError("voice cloning is Voxtral-only: a voice_clone is "
                              "set but [tts] backend is elevenlabs")
        ...
```

Note the behavior change this bakes in: `backend = "elevenlabs"` with a
station `[tts] voice_clone` set used to be silently ignored; it now errors
(contradictory config, and "never degrade silently" wins). When a presenter
carries `voice_clone`, the stamped voice string is the clone path and the
factory receives it as both `voice` and `clone_ref`; `VoxtralProvider` already
prefers clone mode, and its cache identity is the clip-bytes hash
(`clone:<sha256[:16]>`), so per-presenter clones invalidate the per-segment
cache correctly with zero change to `package.py`.

### The prompt — `src/llama/prompts/synthesize.md` + `src/llama/stages/synthesize.py`

The template's hardcoded first-paragraph persona becomes a `{{style}}`
placeholder. Line 1 of the template becomes exactly:

```
Write on-air DJ notes for a full-concert radio broadcast. {{style}}
```

Everything else in the template — inputs, sets/breaks lines, `{{feedback}}`,
the JSON response shape including the `mentioned_songs` contract ("every song
title referenced anywhere above, spelled exactly as in the show data") — is
untouched.

`synthesize.py` defines the neutral fill so a no-presenter render is
**byte-for-byte identical** to today's prompt (a test locks this):

```python
NEUTRAL_STYLE = (
    "Every fact must come from the\n"
    "inputs below — do not invent stories, dates, personnel, or song details. "
    "Voice: warm,\nknowledgeable, economical; written to be read aloud."
)
```

and the persona fill:

```python
def persona_style(presenter: Presenter, title: str | None) -> str:
    """The {{style}} block for a presenter-hosted show: identity + character
    + the loosened-but-bounded grounding rules."""
    lines = [
        f"You are {presenter.name}, the host, speaking in the first person; "
        f"written to be read aloud. You are {presenter.sex}; refer to "
        "yourself accordingly.",
        "Character:",
        presenter.character.strip(),
    ]
    if title:
        lines.append(f'Your show is called "{title}" — you know it well; drop '
                     "the name naturally now and then, not in every segment.")
    lines += [
        "Grounding rules:",
        "- Concert facts — dates, venue, songs, set structure, personnel, what "
        "happened on stage — must come from the inputs below; do not invent any.",
        "- You may voice opinions, perspective, and brief subjective color of "
        "your own.",
        "- You may adopt opinions found in the research or listener reviews as "
        "your own, paraphrased in your voice — never quote reviewers verbatim "
        "at length and never cite them as sources.",
        "- Never claim you attended this concert or took part in real events; "
        "no invented first-hand history presented as fact.",
        "- Every song you name — including in opinions — must be one of this "
        "show's tracks, spelled exactly as in the show data (map any loose "
        "review titles to those spellings), and listed in mentioned_songs.",
    ]
    return "\n".join(lines)
```

`run_synthesize` gains two optional parameters and one input:

```python
def run_synthesize(show_ws, provider, show, research_md, reviews,
                   force=False, presenter: Presenter | None = None,
                   title: str | None = None) -> DJNotes:
    ...
    inputs = dict(
        ...,
        style=persona_style(presenter, title) if presenter else NEUTRAL_STYLE,
    )
```

The retry loop, `factual_guard`, needs-review flagging, and artifact writes
are unchanged. As with every stage, the dj-notes artifact caches: re-scripting
with an edited character is `llama redo <show> --from synthesize`.

### Coexistence with the hallucination defenses (verified)

The persona loosening neither weakens the guards nor gets falsely flagged by
them; here is the seam, exactly:

- **`factual_guard` checks structured claims only** — `mentioned_songs`
  against the tracklist (normalized exact match), `set_intros` keys vs actual
  sets, break-note count, and the set-count/ordinal regexes over the prose.
  Opinions and subjective color are prose that adds no structured claim, so
  the guard is persona-agnostic. The set-count regexes run over persona prose
  identically ("both sets cook tonight" is checked the same in any voice), and
  the sets/breaks instruction lines of the prompt are untouched — no
  weakening, no new false-positive surface.
- **The one genuine seam is adopted opinions naming songs.** A reviewer's
  "love how funky this Shakedown is" adopted verbatim could (a) use a loose
  title the tracklist spells differently, or (b) reference a song from a
  *different* show ("best Dark Star since Cornell"). The persona block's final
  rule closes both: any song named must be one of this show's tracks, in the
  show data's spelling, and listed in `mentioned_songs`. If the model slips
  anyway, `factual_guard` flags the unknown title, the existing
  retry-with-feedback fires, and a persistent failure marks `needs-review` —
  the designed backstop, unchanged.
- **`vet_research` never sees the persona.** It extracts assertions from
  `research.md` — produced by `deep_research`, upstream of synthesize and
  untouched by this feature — so its song/date/set-count grounding checks are
  structurally unaffected. Its gate also runs *before* synthesize in
  `process_show`, so a flagged show never reaches the persona prompt at all.
- **What is deliberately invisible to the guards:** opinion prose that smuggles
  no structured fact (e.g. an invented "I've always loved this venue" mood
  line survives; a fabricated "I was there" should be prevented by the prompt
  boundary rule but is not machine-checked). That is the accepted trade the
  owner chose; the guards' job remains structured facts only.

### Pipeline threading — `src/llama/pipeline.py`

`process_show` gains `presenter: Presenter | None = None` and
`title: str | None = None`:

- `Provenance` write adds
  `presenter=presenter.id if presenter else None, title=title`.
- The `run_synthesize` call passes `presenter=presenter, title=title`.
- Nothing else changes (package already receives the constructed `speech`).

### CLI wiring — `src/llama/cli.py`

- **`_execute`** gains `presenter: Presenter | None = None,
  title: str | None = None`; builds `speech = _speech_for(config, voice,
  presenter)` and passes `presenter`/`title` into `process_show`.
- **`profile add`**: `--voice` removed. New `--presenter <id>` (validated
  eagerly via `load_presenter` — a typo fails at add time, with the
  `PresenterError` surfaced by the CLI error boundary) and `--title <text>`.
  Saved onto the `Profile`.
- **`profile run`**: loads the presenter when set, resolves the voice from it,
  stamps everything:

  ```python
  presenter = (load_presenter(config.root, profile.presenter)
               if profile.presenter else None)
  voice_id = _resolve_voice(config, None,
                            presenter.voice_id if presenter else None)
  script = profile.script or voice_id is not None  # voice implies script
  criteria = profile.criteria.model_copy(update={
      "count": profile.count, "script": script, "voice": voice_id,
      "presenter": profile.presenter, "title": profile.title})
  ```

  and passes `presenter=presenter, title=profile.title` to `_execute`.
- **`run` / `review`**: after reading criteria,
  `presenter = load_presenter(config.root, criteria.presenter) if
  criteria.presenter else None`; voice replay via `_replay_voice` is
  unchanged; `_execute(..., presenter=presenter, title=criteria.title)`.
- **`redo`**: same, from `prov.presenter` / `prov.title`; builds speech via
  `_speech_for(config, effective_voice, presenter)`.
- **`find`**: unchanged behavior — one-off runs are always house-default
  (no `--presenter` flag; deliberate). Its `--voice` help text drops the
  stale "(ElevenLabs)" wording for backend-neutral phrasing.

### Config surface — `src/llama/config.py`

No `TTSConfig` field changes. Comment-only updates to the `[tts]` block of
`DEFAULT_CONFIG_TOML` (template-sync test unaffected): the `enabled` and
`voice` comments now describe the presenter as the per-profile override
("a profile with a presenter is voiced even when this is off"; `voice`/
`voice_clone` are the **house** voice used when no presenter is set), plus a
pointer line that hosts live in `presenters/<id>.toml`
(name / sex / voice XOR voice_clone / character).

## Components / files touched

- **New:** `src/llama/presenters.py` — `Presenter`, `PresenterError`,
  `load_presenter`, `save_presenter`.
- `src/llama/profiles.py` — `Profile`: `voice` removed; `presenter`, `title`
  added.
- `src/llama/models.py` — `Criteria` + `Provenance`: `presenter`, `title`.
- `src/llama/prompts/synthesize.md` — first paragraph becomes `{{style}}`.
- `src/llama/stages/synthesize.py` — `NEUTRAL_STYLE`, `persona_style`,
  `run_synthesize(presenter=, title=)`.
- `src/llama/pipeline.py` — `process_show(presenter=, title=)`, provenance
  stamping.
- `src/llama/cli.py` — `_resolve_voice` (param rename + message),
  `_speech_for`, `_execute`, `profile add` (drop `--voice`, add
  `--presenter`/`--title`), `profile run`, `run`, `review`, `redo`, `find`
  help text.
- `src/llama/tts/__init__.py` — `speech_provider_for(clone_ref=)`; elevenlabs
  clone rejection.
- `src/llama/config.py` — `[tts]` template comments only.
- **Docs:** README, station-brief, workflow, CLAUDE.md — presenter concept,
  sample TOML, profile `presenter`/`title`, removal of profile `voice`.
- **Tests:** new `tests/test_presenters.py`; updates to `test_profiles.py`,
  `test_prompts.py`, `test_stage_synthesize.py`, `test_tts.py`,
  `test_cli_voice.py`, `test_voice_pipeline.py`.

## Testing strategy

All offline, hermetic (`fake` LLM + `fake` speech backends), per house rules.

1. **`presenters.py` unit tests:** TOML round-trip (id from filename, not
   stored); XOR validation (both set / neither set → error); multi-line
   `character` survives; missing file → `PresenterError` naming the path;
   invalid TOML / failed validation → `PresenterError`.
2. **Profile model:** `presenter`/`title` round-trip; unset fields omitted
   from TOML; a legacy profile TOML containing `voice = "x"` still loads
   (field ignored); `Profile` no longer has a `voice` attribute.
3. **Prompt / synthesize:**
   - byte-for-byte: `load_prompt("synthesize").replace("{{style}}",
     NEUTRAL_STYLE)` reproduces today's exact opening paragraph;
   - `test_prompts.py` placeholder set for synthesize gains `style`;
   - `run_synthesize` with no presenter sends a prompt containing the neutral
     sentence and no "Grounding rules:";
   - with a presenter: prompt contains the name, sex, character text, title
     sentence (and omits it when `title=None`), the no-first-hand-history
     rule, and the show-data-spelling song rule;
   - guard coexistence: a persona-mode response whose adopted opinion names
     an unknown song still trips `factual_guard`, retries with feedback, and
     marks needs-review on repeated failure (existing tests re-run green;
     one new persona-mode variant).
4. **Speech factory:** voxtral clone via explicit `clone_ref`; voxtral raises
   when neither voice nor `clone_ref`; elevenlabs + `clone_ref` →
   `SpeechError`; existing factory tests updated to the new parameter.
5. **CLI:**
   - `_resolve_voice` matrix unchanged in behavior (explicit voice opts in
     when globally disabled; `--no-voice` wins; active-but-unconfigured
     raises);
   - `profile add --presenter/--title` persists both, validates the presenter
     exists (bad id → clean `error:` exit), and `--voice` is gone;
   - `profile run` with a presenter stamps `criteria.voice` (from the
     presenter), `criteria.presenter`, `criteria.title`, and forces script;
     voiced even with `[tts] enabled = false`;
   - `run`/`redo` replays resolve the presenter from the stamp and pass it to
     `_execute`/`process_show`; a deleted presenter file fails loudly.
6. **End-to-end (fixture pipeline, fake backends):** a presenter-profile run
   packages with `package/dj-audio/` present, `provenance.json` carrying
   `presenter`/`title`, and the recorded synthesize prompt containing the
   persona block; a plain `find` run's synthesize prompt is byte-identical in
   its opening to the pre-feature prompt.

## Out of scope / future work

- **Sign-off tagline** per presenter — deferred; maybe later.
- **Terminology rename** — the app currently uses "show" for the
  concert/performance (`shows/<slug>/`, `llama show`, the `Show` model). The
  owner wants an eventual app-wide rename to "concert" (performance) vs
  "show" (radio show). Separate future effort; it is why the profile field is
  `title`, not `show_name` (rename-safe). Not implemented here.
- **ElevenLabs feature parity** — remains a working opt-in backend only;
  presenter `voice` works as an ElevenLabs voice_id, `voice_clone` does not
  (and errors loudly).
- **Any curation influence from the presenter** — never.
- **Full-latitude anecdotes** (boundary option "b") — not now; the
  conservative no-first-hand-history rule ships.
- **Presenter management CLI** (`llama presenter add/list`) — presenters are
  hand-edited TOML; revisit only if the file-format friction shows up.
- **Machine-checking the presence boundary** — "I was there" claims are
  prompt-forbidden but not guard-detected; acceptable per the owner's chosen
  seam. Revisit if it leaks on air.
