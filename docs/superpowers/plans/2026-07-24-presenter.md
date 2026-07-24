# Presenter (Radio-Show Host) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reusable radio-show hosts (`presenters/<id>.toml`: voice + persona + on-air identity) that profiles reference via `presenter`/`title`, shaping the DJ script's voice and delivery — with loosened-but-bounded grounding and the structured hallucination guards fully intact.

**Architecture:** A new `presenters.py` module (symmetric with `profiles.py`) loads hand-editable presenter TOMLs. `Profile` gains `presenter`/`title` and loses `voice`; `Criteria`/`Provenance` stamp the presenter *id* and title while the persona *text* resolves live from the TOML at synthesize time. The synthesize prompt's hardcoded persona becomes a `{{style}}` placeholder — neutral runs render byte-for-byte today's prompt; presenter runs get an identity + character + grounding-rules block. The speech factory gains an explicit `clone_ref` so a presenter fully owns its voice.

**Tech Stack:** Python 3.14, Pydantic v2 models, tomllib/tomli-w, Typer CLI, pytest (hermetic: `fake` LLM + `fake` speech backends).

## Global Constraints

- **No presenter → byte-for-byte today's prompt.** `load_prompt("synthesize").replace("{{style}}", NEUTRAL_STYLE)` must reproduce the current prompt exactly (a test locks the opening bytes).
- **Persona replays live; voice stays stamped.** `Criteria`/`Provenance` stamp `presenter` (the id) and `title`; the persona text is re-read from `presenters/<id>.toml` at every synthesize. The resolved voice *string* keeps today's stamped-at-process-time semantics (`Criteria.voice`, `Provenance.voice`, `--voice/--no-voice` replay) unchanged.
- **Presenter implies voice opt-in.** A profile with a presenter is voiced even when `[tts] enabled` is false (carrying forward the removed `Profile.voice` semantics). `--no-voice` strips audio only; the persona still shapes the script.
- **`voice` XOR `voice_clone`** on a presenter — exactly one, validated at load.
- **A presenter fully owns its voice.** `speech_provider_for` gains `clone_ref` and never reads `config.tts.voice_clone` itself; callers resolve it (presenter's `voice_clone`, or `[tts] voice_clone` for the house voice). `clone_ref` with `backend = "elevenlabs"` raises `SpeechError` (cloning is Voxtral-only; never degrade silently).
- **Guards untouched.** Zero edits to `factual_guard`, `src/llama/stages/vet_research.py`, or `src/llama/stages/package.py`.
- **Presenters never influence curation.** No presenter reference anywhere in search/winnow/select.
- **Errors are `LlamaError` subclasses** (`PresenterError`, `SpeechError`) so the CLI boundary prints `error: <message>`, never a traceback. A missing/broken presenter file fails loudly — never a silent fall-back to neutral.
- **Offline test suite stays hermetic** — `fake` LLM + `fake` speech backends; no network.
- **Presenter files live at `<root>/presenters/<id>.toml`**, exact-name resolution (same as profiles).

---

### Task 1: `presenters.py` — model, loader, saver

**Files:**
- Create: `src/llama/presenters.py`
- Test: `tests/test_presenters.py`

**Interfaces:**
- Consumes: `LlamaError` from `src/llama/errors.py`.
- Produces: `Presenter(id, name, sex, voice=None, voice_clone=None, character)` with `.voice_id` property (the `voice or voice_clone` string a run stamps); `PresenterError(LlamaError)`; `load_presenter(root: Path, presenter_id: str) -> Presenter`; `save_presenter(root: Path, presenter: Presenter) -> Path`. The `id` is the filename stem, injected by `load_presenter`, never stored in the TOML.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_presenters.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from llama.errors import LlamaError
from llama.presenters import Presenter, PresenterError, load_presenter, save_presenter


def make(**overrides):
    d = dict(id="casey", name="Casey", sex="male", voice="american-dj",
             character="Warm late-night FM veteran.\nDry humor, deep tape knowledge.")
    d.update(overrides)
    return Presenter(**d)


def test_roundtrip_and_id_from_filename(tmp_path: Path):
    path = save_presenter(tmp_path, make())
    assert path == tmp_path / "presenters" / "casey.toml"
    assert "id" not in path.read_text()          # id is the filename, not a field
    loaded = load_presenter(tmp_path, "casey")
    assert loaded == make()
    assert "\nDry humor" in loaded.character     # multi-line character survives


def test_voice_clone_roundtrip(tmp_path: Path):
    save_presenter(tmp_path, make(voice=None, voice_clone="/refs/casey.wav"))
    loaded = load_presenter(tmp_path, "casey")
    assert loaded.voice is None and loaded.voice_clone == "/refs/casey.wav"
    assert loaded.voice_id == "/refs/casey.wav"


def test_voice_id_prefers_preset():
    assert make().voice_id == "american-dj"


def test_exactly_one_of_voice_and_clone():
    with pytest.raises(ValidationError):
        make(voice=None, voice_clone=None)
    with pytest.raises(ValidationError):
        make(voice="a", voice_clone="/b.wav")


def test_missing_file_raises_presenter_error(tmp_path: Path):
    with pytest.raises(PresenterError) as exc:
        load_presenter(tmp_path, "ghost")
    assert "ghost" in str(exc.value)
    assert isinstance(exc.value, LlamaError)     # CLI boundary prints it cleanly


def test_invalid_toml_raises_presenter_error(tmp_path: Path):
    path = tmp_path / "presenters" / "bad.toml"
    path.parent.mkdir(parents=True)
    path.write_text("name = [unclosed")
    with pytest.raises(PresenterError):
        load_presenter(tmp_path, "bad")


def test_failed_validation_raises_presenter_error(tmp_path: Path):
    path = tmp_path / "presenters" / "half.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "Casey"\n')          # no sex / voice / character
    with pytest.raises(PresenterError):
        load_presenter(tmp_path, "half")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_presenters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.presenters'`

- [ ] **Step 3: Write the module**

```python
# src/llama/presenters.py
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ValidationError, model_validator

from llama.errors import LlamaError


class PresenterError(LlamaError):
    """A presenter file is missing, unparseable, or fails validation."""


class Presenter(BaseModel):
    """A reusable radio-show host: a TTS voice + an authored persona + an
    on-air identity. Referenced by profiles; never influences curation."""
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
    # TOML has no null: drop None fields; id is the filename, not file content.
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_presenters.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/llama/presenters.py tests/test_presenters.py
git commit -m "feat: Presenter model + presenters/<id>.toml loader"
```

---

### Task 2: Profile gains presenter/title (drops voice); Criteria/Provenance stamps; profile add/run

**Files:**
- Modify: `src/llama/profiles.py`
- Modify: `src/llama/models.py` (`Criteria`, `Provenance`)
- Modify: `src/llama/cli.py` (`profile_add`, `profile_run`)
- Test: `tests/test_profiles.py`, `tests/test_models.py`, `tests/test_cli_voice.py`

**Interfaces:**
- Consumes: `Presenter`, `load_presenter`, `save_presenter` from Task 1.
- Produces: `Profile(name, criteria, count=1, human_gate=False, script=True, presenter: str | None = None, title: str | None = None)` — **no `voice` field**. `Criteria` and `Provenance` each gain `presenter: str | None = None` and `title: str | None = None`. `profile add` options: `--presenter <id>` (validated eagerly via `load_presenter`), `--title <text>`; `--voice` removed. `profile run` resolves the voice from the presenter and stamps `voice`/`presenter`/`title` into the run's criteria. (Threading the `Presenter` object into `_execute`/`process_show` is Task 5.)

- [ ] **Step 1: Update the profile model tests**

In `tests/test_profiles.py`, **delete** `test_profile_voice_roundtrip_and_unset_omitted` entirely and add in its place:

```python
def test_profile_presenter_title_roundtrip_and_unset_omitted(tmp_path: Path):
    crit = Criteria(query="q")
    save_profile(tmp_path, Profile(name="hosted", criteria=crit,
                                   presenter="casey", title="Sunday Morning Dead"))
    loaded = load_profile(tmp_path, "hosted")
    assert loaded.presenter == "casey" and loaded.title == "Sunday Morning Dead"
    path = save_profile(tmp_path, Profile(name="plain", criteria=crit))
    text = path.read_text()
    assert "presenter" not in text and "title" not in text  # TOML has no null
    plain = load_profile(tmp_path, "plain")
    assert plain.presenter is None and plain.title is None


def test_profile_legacy_voice_key_is_ignored(tmp_path: Path):
    # Profile.voice shipped with the ElevenLabs DJ-voice feature and is gone;
    # a hand-edited profile that still carries it must load (key dropped).
    path = tmp_path / "profiles" / "old.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "old"\nvoice = "v-legacy"\n[criteria]\nquery = "q"\n')
    loaded = load_profile(tmp_path, "old")
    assert not hasattr(loaded, "voice")
```

- [ ] **Step 2: Add the stamped-field tests to `tests/test_models.py`**

Append:

```python
def test_criteria_presenter_and_title_default_none():
    c = Criteria(query="q")
    assert c.presenter is None and c.title is None
    again = Criteria.model_validate_json(c.model_dump_json())
    assert again == c


def test_provenance_presenter_fields_default_none():
    from llama.models import Candidate, Provenance

    p = Provenance(performance_id="x", run="r",
                   candidate=Candidate(performance_id="x", collection="c",
                                       date="1970-01-01", recordings=[]),
                   processed_at="2026-07-24T00:00:00+00:00")
    assert p.presenter is None and p.title is None
```

- [ ] **Step 3: Update the profile CLI tests**

In `tests/test_cli_voice.py`, **delete** `test_profile_add_voice` and `test_profile_run_explicit_voice_opts_in_when_globally_disabled` and add in their place:

```python
def test_profile_add_presenter_and_title(tmp_path: Path, monkeypatch):
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import load_profile

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    result = runner.invoke(cli.app, [
        "profile", "add", "gdhour", "GD 1973", "--presenter", "casey",
        "--title", "Sunday Morning Dead", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    saved = load_profile(tmp_path, "gdhour")
    assert saved.presenter == "casey" and saved.title == "Sunday Morning Dead"


def test_profile_add_unknown_presenter_fails_fast(tmp_path: Path, monkeypatch):
    from llama.presenters import PresenterError

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    result = runner.invoke(cli.app, [
        "profile", "add", "gdhour", "GD 1973", "--presenter", "ghost",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code != 0
    assert isinstance(result.exception, PresenterError)
    assert not (tmp_path / "profiles" / "gdhour.toml").exists()


def test_profile_run_presenter_opts_in_when_globally_disabled(
        tmp_path: Path, monkeypatch):
    from llama.models import Criteria
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')  # enabled = false
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    save_profile(tmp_path, Profile(name="voiced",
                                   criteria=Criteria.model_validate_json(CRITERIA),
                                   script=False, presenter="casey",
                                   title="Sunday Morning Dead"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "profile", "run", "voiced", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-voiced"))  # named <today>-voiced
    saved = json.loads((run_dir / "criteria.json").read_text())
    assert saved["voice"] == "v-casey"          # presenter's voice, opted in
    assert saved["presenter"] == "casey" and saved["title"] == "Sunday Morning Dead"
    assert saved["script"] is True              # voice implies script (profile had script=False)
    assert seen["voice"] == "v-casey" and seen["script"] is True
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_profiles.py tests/test_models.py tests/test_cli_voice.py -q`
Expected: FAIL — `Profile` has no `presenter` field, `Criteria` has no `presenter` field, `profile add` has no `--presenter` option.

- [ ] **Step 5: Update `Profile`**

In `src/llama/profiles.py`, replace the `Profile` class body:

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

(`voice` is gone; `save_profile`/`load_profile` unchanged — pydantic's default extra-ignore drops a legacy `voice =` key on load.)

- [ ] **Step 6: Add the stamped fields to `Criteria` and `Provenance`**

In `src/llama/models.py`, in `Criteria`, directly below the `voice: str | None = None` field, add:

```python
    # Presenter id + radio-show title stamped by profile runs (None = house
    # default / one-off run). The persona TEXT is deliberately NOT stamped:
    # it resolves live from presenters/<id>.toml at synthesize time, so an
    # edited character + `redo --from synthesize` takes effect. The voice
    # string above stays stamped-resolved, as before.
    presenter: str | None = None
    title: str | None = None
```

In `Provenance`, directly below its `voice` field, add:

```python
    presenter: str | None = None  # presenter id (persona resolves live from its TOML)
    title: str | None = None      # radio-show title spoken by the presenter
```

- [ ] **Step 7: Update `profile add` and `profile run`**

In `src/llama/cli.py`, add to the imports block:

```python
from llama.presenters import load_presenter
```

In `profile_add`, **delete** the `voice` option (the `voice: str = typer.Option(None, "--voice", ...)` parameter) and add in its place:

```python
    presenter: str = typer.Option(None, "--presenter",
                                  help="Host for this show: presenters/<id>.toml; its "
                                       "voice voices this profile's runs even when "
                                       "[tts] enabled is false"),
    title: str = typer.Option(None, "--title",
                              help="The radio show's on-air name (the host knows it "
                                   "and says it occasionally)"),
```

In the body, right after `config, ia, _ = _setup(config_path)`, add:

```python
    if presenter:
        load_presenter(config.root, presenter)  # fail fast on a typo'd id
```

and change the `Profile(...)` construction to:

```python
    profile = Profile(name=name, criteria=criteria, count=count, human_gate=human_gate,
                      script=script, presenter=presenter, title=title)
```

In `profile_run`, replace the lines from `voice_id = _resolve_voice(...)` through the `criteria = profile.criteria.model_copy(...)` statement with:

```python
    presenter = (load_presenter(config.root, profile.presenter)
                 if profile.presenter else None)
    voice_id = _resolve_voice(config, None,
                              presenter.voice_id if presenter else None)
    script = profile.script or voice_id is not None  # voice implies script
    # Stamp count/script/voice/presenter/title into the run's criteria: a later
    # `llama run` on this dir must behave like the profile, not the defaults.
    criteria = profile.criteria.model_copy(update={"count": profile.count,
                                                   "script": script,
                                                   "voice": voice_id,
                                                   "presenter": profile.presenter,
                                                   "title": profile.title})
```

(The `_execute(...)` call is unchanged in this task; Task 5 threads `presenter`/`title` into it.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_profiles.py tests/test_models.py tests/test_cli_voice.py tests/test_cli_commands.py -q`
Expected: PASS (including the untouched profile tests in `test_cli_commands.py`)

- [ ] **Step 9: Commit**

```bash
git add src/llama/profiles.py src/llama/models.py src/llama/cli.py \
        tests/test_profiles.py tests/test_models.py tests/test_cli_voice.py
git commit -m "feat: profiles reference a presenter + title; Profile.voice removed"
```

---

### Task 3: Persona prompt — `{{style}}` placeholder, `NEUTRAL_STYLE`, `persona_style`

**Files:**
- Modify: `src/llama/prompts/synthesize.md`
- Modify: `src/llama/stages/synthesize.py`
- Test: `tests/test_prompts.py`, `tests/test_stage_synthesize.py`

**Interfaces:**
- Consumes: `Presenter` from Task 1.
- Produces: `NEUTRAL_STYLE: str` and `persona_style(presenter: Presenter, title: str | None) -> str` in `src/llama/stages/synthesize.py`; `run_synthesize(show_ws, provider, show, research_md, reviews, force=False, presenter: Presenter | None = None, title: str | None = None)`. The prompt template's persona paragraph becomes `{{style}}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_prompts.py`, change the `"synthesize"` entry of `EXPECTED` to:

```python
    "synthesize": {"style", "show_json", "research", "reviews_digest",
                   "sets", "n_breaks", "feedback"},
```

Append to `tests/test_stage_synthesize.py` (top-of-file imports first — add these below the existing imports):

```python
from llama.llm.tasks import load_prompt
from llama.presenters import Presenter
from llama.stages.synthesize import NEUTRAL_STYLE, persona_style
```

then the tests at the bottom:

```python
ORIGINAL_OPENING = (
    "Write on-air DJ notes for a full-concert radio broadcast. Every fact must come from the\n"
    "inputs below — do not invent stories, dates, personnel, or song details. Voice: warm,\n"
    "knowledgeable, economical; written to be read aloud.\n"
)


def make_presenter(**overrides):
    d = dict(id="casey", name="Casey", sex="male", voice="v-casey",
             character="Warm late-night FM veteran with dry humor.")
    d.update(overrides)
    return Presenter(**d)


def test_neutral_style_reproduces_original_prompt_bytes():
    # The no-presenter prompt must be byte-for-byte the pre-feature prompt.
    rendered = load_prompt("synthesize").replace("{{style}}", NEUTRAL_STYLE)
    assert rendered.startswith(ORIGINAL_OPENING)


def test_synthesize_without_presenter_sends_neutral_prompt(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    run_synthesize(sws, fake, show, research_md="", reviews=[])
    prompt = fake.calls[0][1]
    assert "Voice: warm,\nknowledgeable, economical" in prompt
    assert "Grounding rules:" not in prompt


def test_persona_style_contains_identity_rules_and_title():
    style = persona_style(make_presenter(), "Sunday Morning Dead")
    assert "You are Casey" in style and "male" in style
    assert "Warm late-night FM veteran" in style
    assert 'Your show is called "Sunday Morning Dead"' in style
    assert "must come from the inputs below" in style          # facts stay grounded
    assert "adopt opinions found in the research or listener reviews" in style
    assert "Never claim you attended this concert" in style
    assert "spelled exactly as in the show data" in style      # guard-coexistence rule


def test_persona_style_omits_title_when_none():
    assert "Your show is called" not in persona_style(make_presenter(), None)


def test_synthesize_with_presenter_sends_persona_prompt(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    run_synthesize(sws, fake, show, research_md="", reviews=[],
                   presenter=make_presenter(), title="Sunday Morning Dead")
    prompt = fake.calls[0][1]
    assert "You are Casey" in prompt and "Grounding rules:" in prompt
    assert "Every fact must come from the\ninputs below" not in prompt


def test_persona_guard_still_catches_unknown_song(tmp_path: Path):
    # The loosened persona must not weaken the backstop: an adopted opinion
    # naming a song that is not in this show still trips factual_guard,
    # retries with feedback, and holds the show on repeated failure.
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    bad = json.dumps(notes_dict(mentioned_songs=["Shakedown Street"]))
    fake = FakeProvider(completes=[bad, bad])  # retry also fails
    run_synthesize(sws, fake, show, research_md="", reviews=[],
                   presenter=make_presenter(), title=None)
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("Shakedown Street" in f for f in saved["review_flags"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py tests/test_stage_synthesize.py -q`
Expected: FAIL — `ImportError: cannot import name 'NEUTRAL_STYLE'`, and the prompt-placeholder test fails (`style` not in the template).

- [ ] **Step 3: Edit the prompt template**

In `src/llama/prompts/synthesize.md`, replace the first paragraph (the three lines from `Write on-air DJ notes` through `written to be read aloud.`) with this single line:

```
Write on-air DJ notes for a full-concert radio broadcast. {{style}}
```

Everything else in the file — inputs, the sets/breaks lines, `{{feedback}}`, the JSON response shape (including the `mentioned_songs` contract) — stays exactly as is.

- [ ] **Step 4: Add the style builders and thread them through `run_synthesize`**

In `src/llama/stages/synthesize.py`, add to the imports:

```python
from llama.presenters import Presenter
```

Below the existing module constants (`_ORDINALS = ...`), add:

```python
# The pre-presenter house narrator, verbatim: rendering the template with this
# fill must reproduce the original prompt byte-for-byte (a test locks it).
NEUTRAL_STYLE = (
    "Every fact must come from the\n"
    "inputs below — do not invent stories, dates, personnel, or song details. "
    "Voice: warm,\nknowledgeable, economical; written to be read aloud."
)


def persona_style(presenter: Presenter, title: str | None) -> str:
    """The {{style}} block for a presenter-hosted show: identity + character
    + the loosened-but-bounded grounding rules. Concert facts stay grounded;
    the final rule keeps adopted opinions inside factual_guard's contract."""
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

Change the `run_synthesize` signature and the `inputs` dict:

```python
def run_synthesize(
    show_ws: ShowWorkspace,
    provider,
    show: Show,
    research_md: str,
    reviews: list[dict],
    force: bool = False,
    presenter: Presenter | None = None,
    title: str | None = None,
) -> DJNotes:
    if not should_run(show_ws.dj_notes_json, force):
        return read_model(show_ws.dj_notes_json, DJNotes)

    sets = sorted({t.set for t in show.tracks}, key=lambda x: (x == "encore", x))
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        reviews_digest=reviews_digest(reviews),
        sets=", ".join(f'"{s}"' for s in sets),
        n_breaks=len(show.set_breaks),
        style=persona_style(presenter, title) if presenter else NEUTRAL_STYLE,
    )
```

The retry loop, `factual_guard`, flagging, and artifact writes below are untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_prompts.py tests/test_stage_synthesize.py -q`
Expected: PASS (all pre-existing synthesize tests plus the seven new ones)

- [ ] **Step 6: Commit**

```bash
git add src/llama/prompts/synthesize.md src/llama/stages/synthesize.py \
        tests/test_prompts.py tests/test_stage_synthesize.py
git commit -m "feat: synthesize persona block via {{style}}; neutral stays byte-for-byte"
```

---

### Task 4: Speech factory — explicit `clone_ref`; ElevenLabs rejects clones

**Files:**
- Modify: `src/llama/tts/__init__.py`
- Test: `tests/test_tts.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `speech_provider_for(config: Config, voice: str | None, clone_ref: str | None = None) -> SpeechProvider`. The factory never reads `config.tts.voice_clone` anymore — callers resolve `clone_ref` (Task 5's `_speech_for` does). `clone_ref` with the elevenlabs backend raises `SpeechError`.

- [ ] **Step 1: Update and add the factory tests**

In `tests/test_tts.py`, replace `test_factory_voxtral_clone_mode` (it currently relies on the factory reading `config.tts.voice_clone`) with:

```python
def test_factory_voxtral_clone_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    from llama.tts.voxtral import VoxtralProvider
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    p = speech_provider_for(Config(), None, clone_ref=str(ref))
    assert isinstance(p, VoxtralProvider)
    assert p.voice.startswith("clone:")


def test_factory_ignores_config_clone_without_clone_ref(monkeypatch, tmp_path):
    # Callers own clone resolution (a presenter must fully own its voice):
    # the factory itself no longer falls back to [tts] voice_clone.
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    cfg = Config.model_validate({"tts": {"voice_clone": str(ref)}})
    with pytest.raises(SpeechError):
        speech_provider_for(cfg, None)


def test_factory_elevenlabs_rejects_clone_ref(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = Config.model_validate({"tts": {"backend": "elevenlabs"}})
    with pytest.raises(SpeechError):
        speech_provider_for(cfg, "v-abc", clone_ref="/refs/x.wav")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts.py -q`
Expected: FAIL — `speech_provider_for` takes no `clone_ref` argument.

- [ ] **Step 3: Rewrite the factory**

In `src/llama/tts/__init__.py`, replace `speech_provider_for` with:

```python
def speech_provider_for(config: Config, voice: str | None,
                        clone_ref: str | None = None) -> SpeechProvider:
    """Construct the speech backend for a run's resolved voice.

    Mirrors llm.provider_for: maps config.tts.backend to a class. No tiers,
    no ladder — one provider, one voice, one model per run. clone_ref is the
    reference-clip path for clone mode; callers resolve it (a presenter's
    voice_clone, or [tts] voice_clone for the house voice) — the factory
    itself never reads config.tts.voice_clone, so a presenter fully owns
    its voice.
    """
    backend = config.tts.backend
    if backend == "fake":
        return FakeSpeechProvider()
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
        if not voice:
            raise SpeechError("no TTS voice configured: "
                              "set [tts] voice or give the profile a presenter")
        return ElevenLabsProvider(voice=voice, model=config.tts.model,
                                  api_key=config.tts.api_key)
    raise SpeechError(f"unknown TTS backend {backend!r}")
```

(Interim note: until Task 5 wires `_speech_for`, a voxtral house-clone-only config would not resolve through `_execute` — no test exercises that path between these two tasks; Task 5 closes it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/tts/__init__.py tests/test_tts.py
git commit -m "feat: speech factory takes explicit clone_ref; elevenlabs rejects clones"
```

---

### Task 5: Thread the presenter through CLI and pipeline

**Files:**
- Modify: `src/llama/cli.py` (`_resolve_voice`, new `_speech_for`, `_execute`, `find` help text, `run`, `review`, `redo`, `profile_run`)
- Modify: `src/llama/pipeline.py` (`process_show`)
- Test: `tests/test_cli_voice.py`; signature fixes in `tests/test_cli_commands.py` and `tests/test_voice_pipeline.py`

**Interfaces:**
- Consumes: `Presenter`, `load_presenter` (Task 1); `Criteria.presenter`/`.title`, `Provenance.presenter`/`.title` (Task 2); `run_synthesize(presenter=, title=)` (Task 3); `speech_provider_for(config, voice, clone_ref=None)` (Task 4).
- Produces: `_resolve_voice(config, want, explicit_voice=None)` (renamed third param, same behavior); `_speech_for(config: Config, voice: str | None, presenter: Presenter | None)` returning a provider or `None`; `_execute(..., presenter: Presenter | None = None, title: str | None = None, ...)`; `process_show(..., presenter: Presenter | None = None, title: str | None = None, ...)` which stamps `Provenance.presenter`/`.title` and passes both to `run_synthesize`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_voice.py`:

```python
def test_speech_for_resolves_clone_ownership(monkeypatch):
    from llama.presenters import Presenter

    seen = {}
    monkeypatch.setattr(cli, "speech_provider_for",
                        lambda config, voice, clone_ref=None:
                        seen.update(voice=voice, clone_ref=clone_ref))
    cfg = Config.model_validate({"tts": {"voice_clone": "/station/ref.wav"}})
    clone_host = Presenter(id="casey", name="Casey", sex="male",
                           voice_clone="/casey/ref.wav", character="c")
    cli._speech_for(cfg, "/casey/ref.wav", clone_host)
    assert seen == {"voice": "/casey/ref.wav", "clone_ref": "/casey/ref.wav"}
    preset_host = Presenter(id="dana", name="Dana", sex="female",
                            voice="v-dana", character="c")
    cli._speech_for(cfg, "v-dana", preset_host)
    # a preset presenter never inherits the station clone
    assert seen == {"voice": "v-dana", "clone_ref": None}
    cli._speech_for(cfg, "/station/ref.wav", None)
    assert seen == {"voice": "/station/ref.wav", "clone_ref": "/station/ref.wav"}
    assert cli._speech_for(cfg, None, clone_host) is None


def test_run_replay_resolves_presenter_from_criteria(tmp_path: Path, monkeypatch):
    from llama.presenters import Presenter, save_presenter

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(
        query="q", voice="v-casey", presenter="casey", title="Sunday Morning Dead"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, ["run", str(ws.dir),
                                     "--config", str(tmp_path / "config.toml")])
    assert result.exit_code == 0, result.output
    assert seen["presenter"].id == "casey" and seen["presenter"].name == "Casey"
    assert seen["title"] == "Sunday Morning Dead"
    assert seen["voice"] == "v-casey"


def test_run_replay_missing_presenter_file_fails(tmp_path: Path, monkeypatch):
    from llama.presenters import PresenterError

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(query="q", presenter="ghost"))
    called = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: called.append(1))
    result = runner.invoke(cli.app, ["run", str(ws.dir),
                                     "--config", str(tmp_path / "config.toml")])
    assert result.exit_code != 0
    assert isinstance(result.exception, PresenterError)
    assert called == []                    # never silently fell back to neutral


def test_profile_run_passes_presenter_and_title_to_execute(
        tmp_path: Path, monkeypatch):
    from llama.models import Criteria
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    save_profile(tmp_path, Profile(name="hosted",
                                   criteria=Criteria.model_validate_json(CRITERIA),
                                   presenter="casey", title="Sunday Morning Dead"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, ["profile", "run", "hosted",
                                     "--config", str(tmp_path / "config.toml")])
    assert result.exit_code == 0, result.output
    assert seen["presenter"].id == "casey"
    assert seen["title"] == "Sunday Morning Dead"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_voice.py -q`
Expected: FAIL — `cli` has no `_speech_for`; `_execute` receives no `presenter`/`title` kwargs.

- [ ] **Step 3: Update `cli.py`**

Change the presenters import to:

```python
from llama.presenters import Presenter, load_presenter
```

Replace `_resolve_voice` (param rename + message; behavior identical):

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

Directly below `_replay_voice`, add:

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

In `_execute`, change the signature and the speech line:

```python
def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False,
             script: bool = False, voice: str | None = None,
             presenter: Presenter | None = None, title: str | None = None,
             force_stage: str | None = None,
             full_rationale: bool = False) -> None:
    providers = make_providers(config)
    speech = _speech_for(config, voice, presenter)
```

and add `presenter=presenter, title=title,` to its `process_show(...)` call (immediately after `voice=voice, speech=speech,`).

In `find`, update the `--voice` help text (backend-neutral):

```python
    voice: bool = typer.Option(None, "--voice/--no-voice",
                               help="Per-segment spoken DJ audio; default "
                                    "follows [tts] enabled; --voice uses the house "
                                    "[tts] voice; voice implies --script"),
```

In `run`, after `criteria = read_model(ws.criteria, Criteria)`, add:

```python
    presenter = (load_presenter(config.root, criteria.presenter)
                 if criteria.presenter else None)
```

and add `presenter=presenter, title=criteria.title,` to its `_execute(...)` call (after `voice=effective_voice,`).

In `review`, inside the `if typer.confirm(...)` branch after `criteria = read_model(ws.criteria, Criteria)`, add the same two-line presenter load, and add `presenter=presenter, title=criteria.title,` to its `_execute(...)` call (after `voice=effective_voice,`).

In `redo`, after `prov = entry.provenance`, add:

```python
    presenter = (load_presenter(config.root, prov.presenter)
                 if prov.presenter else None)
```

replace `speech = speech_provider_for(config, effective_voice) if effective_voice is not None else None` with:

```python
    speech = _speech_for(config, effective_voice, presenter)
```

and add `presenter=presenter, title=prov.title,` to its `process_show(...)` call (after `voice=effective_voice, speech=speech,`).

In `profile_run`, add `presenter=presenter, title=profile.title,` to its `_execute(...)` call (after `voice=voice_id,`).

- [ ] **Step 4: Update `process_show`**

In `src/llama/pipeline.py`, add to the imports:

```python
from llama.presenters import Presenter
```

Add to the `process_show` signature, after `speech=None,`:

```python
    presenter: Presenter | None = None,
    title: str | None = None,
```

In the `Provenance(...)` write, after `script=script, voice=voice,`, add:

```python
        presenter=presenter.id if presenter else None, title=title,
```

Change the `run_synthesize` call to:

```python
            notes = run_synthesize(show_ws, providers["synthesize"], show,
                                   research_md, reviews, force=force,
                                   presenter=presenter, title=title)
```

- [ ] **Step 5: Fix the two test files that stub the old signatures**

In `tests/test_cli_commands.py`, **two** tests define a `fake_execute(...)` stub with the old signature — `test_profile_run_stamps_count_and_script_into_run_criteria` and `test_run_inherits_script_and_count_from_criteria`. In **both**, add `presenter=None, title=None,` to the parameter list (after `voice=None,`).

In `tests/test_voice_pipeline.py`, two tests monkeypatch the factory with the old arity; update both lambdas:
- in `test_speech_failure_fails_show_but_not_batch`:
  `lambda config, voice, clone_ref=None: FakeSpeechProvider(fail=True)`
- in `test_redo_from_package_reuses_cached_segments`:
  `lambda config, voice, clone_ref=None: second`

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli_voice.py tests/test_cli_commands.py tests/test_voice_pipeline.py -q`
Expected: PASS

- [ ] **Step 7: Run the full suite for regressions**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/llama/cli.py src/llama/pipeline.py tests/test_cli_voice.py \
        tests/test_cli_commands.py tests/test_voice_pipeline.py
git commit -m "feat: thread the presenter through CLI, pipeline, and speech construction"
```

---

### Task 6: End-to-end presenter pipeline tests (hermetic)

**Files:**
- Test: `tests/test_voice_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5; the existing `FakeIA` / `fake_providers` / `CRITERIA` / `NOTES` harness and `SHOW_DIR` constant already defined in this file.
- Produces: two integration tests proving a presenter profile run packages voiced audio with stamped provenance and a persona prompt, and that `redo --from synthesize` picks up a hand-edited character (live persona resolution).

- [ ] **Step 1: Write the tests**

Append to `tests/test_voice_pipeline.py`:

```python
PRESENTER_CFG = ('{root}\n[jerrybase]\nenabled = false\n'
                 '[tts]\nbackend = "fake"\n')   # enabled = false; no house voice


def presenter_setup(tmp_path, monkeypatch):
    from llama.models import Criteria as CriteriaModel
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        PRESENTER_CFG.format(root=f'root = "{tmp_path}"'))
    save_presenter(tmp_path, Presenter(
        id="casey", name="Casey", sex="male", voice="v-casey",
        character="Warm late-night FM veteran with dry humor."))
    save_profile(tmp_path, Profile(
        name="sunday", criteria=CriteriaModel.model_validate_json(CRITERIA),
        script=False, presenter="casey", title="Sunday Morning Dead"))
    made = {"synthesize": []}

    def providers(config):
        p = fake_providers(config)
        made["synthesize"].append(p["synthesize"])
        return p

    monkeypatch.setattr(cli, "make_providers", providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    return str(tmp_path / "config.toml"), made


def test_presenter_profile_run_end_to_end(tmp_path: Path, monkeypatch):
    cfg, made = presenter_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["profile", "run", "sunday", "--auto",
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    # presenter implies voice even though [tts] enabled is false
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    assert (pkg / "dj-audio" / "00-intro.mp3").read_bytes() == SILENT_MP3
    # run intent + provenance stamp the presenter id and title, voice resolved
    run_dir = next((tmp_path / "runs").glob("*-sunday"))
    criteria = json.loads((run_dir / "criteria.json").read_text())
    assert criteria["voice"] == "v-casey"
    assert criteria["presenter"] == "casey"
    assert criteria["title"] == "Sunday Morning Dead"
    assert criteria["script"] is True   # voice implies script (profile had script=False)
    prov = json.loads((tmp_path / "shows" / SHOW_DIR / "provenance.json").read_text())
    assert prov["presenter"] == "casey" and prov["title"] == "Sunday Morning Dead"
    # the synthesize prompt carried the persona, not the neutral narrator
    prompt = made["synthesize"][0].calls[0][1]
    assert "You are Casey" in prompt
    assert 'Your show is called "Sunday Morning Dead"' in prompt
    assert "Every fact must come from the\ninputs below" not in prompt


def test_redo_from_synthesize_picks_up_edited_character(tmp_path: Path, monkeypatch):
    from llama.presenters import Presenter, save_presenter

    cfg, made = presenter_setup(tmp_path, monkeypatch)
    assert runner.invoke(cli.app, ["profile", "run", "sunday", "--auto",
                                   "--config", cfg]).exit_code == 0
    # hand-tune the character; redo must re-script from the live file
    save_presenter(tmp_path, Presenter(
        id="casey", name="Casey", sex="male", voice="v-casey",
        character="Now grumpy and terse."))
    redo = runner.invoke(cli.app, ["redo", "gratefuldead", "--from", "synthesize",
                                   "--config", cfg])
    assert redo.exit_code == 0, redo.output
    prompt = made["synthesize"][1].calls[0][1]   # providers rebuilt once per invoke
    assert "Now grumpy and terse." in prompt
    assert "Warm late-night FM veteran" not in prompt
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/test_voice_pipeline.py -q`
Expected: PASS (Tasks 1-5 already implemented everything; these tests are the integration proof. If either fails, the wiring from Task 5 has a bug — fix it there, do not adapt the assertions.)

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_voice_pipeline.py
git commit -m "test: presenter profile run end-to-end; redo picks up edited character"
```

---

### Task 7: Config template comments and documentation

**Files:**
- Modify: `src/llama/config.py` (`DEFAULT_CONFIG_TOML` comments only)
- Modify: `README.md`, `docs/station-brief.md`, `docs/workflow.md`, `CLAUDE.md`
- Test: `tests/test_config.py` (existing template-sync test must stay green)

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-6.
- Produces: docs describing presenters; config template comments describing the presenter as the per-profile voice source.

- [ ] **Step 1: Update the `[tts]` comment block**

In `src/llama/config.py` `DEFAULT_CONFIG_TOML`, replace these comment lines of the `[tts]` block:

```python
# enabled = true             # default false; a profile with its own `voice`
#                            # is voiced even when this is off
```

with:

```python
# enabled = true             # default false; a profile with a presenter
#                            # is voiced even when this is off
```

and replace:

```python
# voice = "..."              # voxtral preset name (or elevenlabs voice_id); a
#                            # profile can set its own `voice` to override this
```

with:

```python
# voice = "..."              # the HOUSE voice: voxtral preset name (or
#                            # elevenlabs voice_id), used when no presenter
```

and directly after the `# api_key = ...` line of the `[tts]` block, add:

```python
# Hosts live in presenters/<id>.toml (name / sex / voice XOR voice_clone /
# character); a profile picks one via `presenter = "<id>"` and names its
# radio show via `title = "..."`.
```

Run: `pytest tests/test_config.py -q`
Expected: PASS (comment-only changes; the template still parses to the defaults)

- [ ] **Step 2: Find every stale profile-voice / DJ-script-persona mention**

Run: `grep -rn -i "profile.*voice\|--voice\|dj script\|dj-voice\|synthesize" README.md docs/station-brief.md docs/workflow.md CLAUDE.md`
Read each hit in context before editing.

- [ ] **Step 3: Update the prose**

For each file (adapt wording to the surrounding sentences; keep each file's voice):

- Introduce the **presenter** concept: a reusable radio-show host = TTS voice + authored character + on-air identity, defined in a hand-edited `presenters/<id>.toml`. Include this sample in README (and wherever the workflow doc shows profile setup):

  ```toml
  name = "Casey"
  sex = "male"
  voice = "american-dj"          # or: voice_clone = "/path/to/casey-ref.wav"
  character = """
  Warm late-night FM veteran. Dry humor, deep tape-collector knowledge, gets
  audibly excited about big jams. Keeps it loose but never sloppy.
  """
  ```

- A profile references a host with `presenter = "<id>"` and names its radio
  show with `title = "..."` (`profile add --presenter casey --title "Sunday
  Morning Dead"`). The host knows the title and drops it occasionally on air.
- Profile `voice` is **removed** (its job subsumed by the presenter): naming a
  presenter voices that profile's runs even when `[tts] enabled` is false;
  `--no-voice` still strips audio per run. No presenter → the house `[tts]`
  voice and today's neutral narrator, unchanged.
- The persona **loosens the script's grounding deliberately**: the host may
  hold opinions and adopt review/research sentiment as his or her own
  (paraphrased, no long quotes), but concert facts stay grounded in the
  research, and the host never claims to have been at the show. The `vet` +
  `factual_guard` defenses are unchanged and still hold shows for review.
- Character edits are live: edit the presenter TOML, then
  `llama redo <show> --from synthesize` re-scripts with the new host.
- `voice_clone` on a presenter is Voxtral-only (errors loudly on the
  elevenlabs backend).
- In `CLAUDE.md`: update the "What this is" / "Voice (opt-in TTS)"
  architecture paragraphs to mention presenters (`presenters/<id>.toml`,
  profile `presenter`/`title`, `Profile.voice` removed, persona block in
  synthesize with grounding guards unchanged).

- [ ] **Step 4: Verify no stale claims remain**

Run: `grep -rn -i "profile add --voice\|profile voice\|Profile.voice" README.md docs/station-brief.md docs/workflow.md CLAUDE.md`
Expected: no hits (or only historical/changelog context that explicitly says "removed").

- [ ] **Step 5: Run the full suite one last time**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/llama/config.py README.md docs/station-brief.md docs/workflow.md CLAUDE.md
git commit -m "docs: presenter hosts (presenters/<id>.toml), profile presenter/title"
```

---

## Self-Review

**Spec coverage:**
- `presenters.py` (model, XOR validation, `PresenterError`, loader/saver, id from filename) → Task 1. ✓
- Profile `presenter`/`title`, `voice` removed, legacy key ignored → Task 2. ✓
- `Criteria`/`Provenance` stamp id + title; persona resolves live → Task 2 (fields) + Task 5 (stamping/threading) + Task 6 (redo-picks-up-edit proof). ✓
- Prompt `{{style}}`; `NEUTRAL_STYLE` byte-for-byte; `persona_style` with identity, sex, character, title, and all five grounding rules → Task 3. ✓
- Guard coexistence (guards untouched; persona-mode unknown-song still trips `factual_guard`; show-data-spelling rule in the persona block) → Task 3; zero edits to `vet_research.py`/`package.py` anywhere. ✓
- Voice resolution: presenter-or-house; presenter opt-in when `enabled = false`; `--no-voice` strips audio only; `_resolve_voice` message update → Tasks 2, 5. ✓
- Factory `clone_ref`; presenter owns its clone (no station bleed-through); elevenlabs rejects clones → Task 4 (factory) + Task 5 (`_speech_for` ownership test). ✓
- CLI: `profile add --presenter/--title` (eager validation), `--voice` gone; `run`/`review`/`redo` resolve the stamped presenter; missing file fails loudly; `find` stays house-only with neutral help text → Tasks 2, 5. ✓
- E2E: voiced package, provenance stamps, persona prompt, live character iteration → Task 6. ✓
- Config template comments + docs (README/station-brief/workflow/CLAUDE.md) → Task 7. ✓
- Out-of-scope items (sign-off tagline, show→concert rename, ElevenLabs parity, curation influence, full-latitude anecdotes, presenter CLI) → correctly absent from all tasks. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; docs steps enumerate concrete content points plus grep verification, matching the voxtral plan's docs-task style.

**Type consistency:** `Presenter(id, name, sex, voice, voice_clone, character)` + `.voice_id` used identically in Tasks 1, 2, 3, 5, 6. `load_presenter(root, presenter_id)` / `save_presenter(root, presenter)` consistent throughout. `persona_style(presenter, title)` defined Task 3, exercised Tasks 3 and 6. `speech_provider_for(config, voice, clone_ref=None)` defined Task 4, called by `_speech_for` in Task 5 and monkeypatched with that exact arity in Tasks 5-6. `_execute`/`process_show` gain `presenter: Presenter | None, title: str | None` in Task 5 and are stubbed with matching signatures in the fixed tests. `Criteria.presenter`/`.title` (Task 2) are the fields read by `run`/`review` in Task 5 and asserted in Task 6; `Provenance.presenter`/`.title` likewise for `redo`.
