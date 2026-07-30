# emcee Build (Sub-project 3, Plan A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `emcee` package — the station-side package→package filter that voices delivered show packages (DJ script + TTS audio + broadcast.m3u) — complete and tested, WITHOUT touching llama.

**Architecture:** New `packages/emcee/` in the monorepo. The speech/TTS/presenter layers are **ports of llama's modules** (copy + import rename, no behavior change); new code is the station model (scan/readiness/atomic manifest rewrite), the `scriptwrite` LLM task sourced from briefing+manifest, assignment resolution, and the CLI. llama's source is not modified by this plan at all — the removal is Plan B (`2026-07-29-emcee-b-cut.md`). Spec: `docs/superpowers/specs/2026-07-29-emcee-and-the-cut-design.md`.

**Tech Stack:** Python ≥3.11, typer, pydantic v2 (via herder), numpy, lameenc, httpx (via herder). **No dependency that is not already used by the monorepo.**

## Global Constraints

- **No modifications under `packages/llama/` or `packages/herder/`** in this plan (reading/copying from them is the point; `git diff` on both must stay empty). Exception: none — even the root README waits for Plan B.
- License `GPL-3.0-or-later`; `requires-python = ">=3.11"`; copy `LICENSE` into `packages/emcee/` (same lesson as sub-project 1: hatchling silently no-ops on a missing license file).
- **emcee never imports llama** (guard test from Task 1 onward). herder imports are allowed.
- **Ports are verbatim**: a ported file differs from its llama source only in import paths (`llama.X` → `emcee.Y`) and stated exceptions. Reviewers diff ported files against their sources.
- Full suite green after every task: `pytest -q` from the repo root; emcee's suite must also pass standalone: `pytest packages/emcee/tests -q`.
- Commit after every task (`feat:`/`test:`/`docs:` convention).
- Setup command for the worktree: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee` (llama's editable install stays — its suite still runs).

---

### Task 1: Package scaffold, error boundary, CLI skeleton, guard test

**Files:**
- Create: `packages/emcee/pyproject.toml`, `packages/emcee/LICENSE` (copy of repo-root LICENSE)
- Create: `packages/emcee/src/emcee/__init__.py`, `errors.py`, `cli.py`, `__main__.py`
- Create: `packages/emcee/tests/test_no_llama_imports.py`, `packages/emcee/tests/test_cli_boundary.py`
- Modify: `pytest.ini` (repo root — add emcee's test path)

**Interfaces:**
- Produces: `EmceeError(Exception)` base (message + `details: list[str]`, mirroring `LlamaError`'s shape from `packages/llama/src/llama/errors.py` but NOT importing it); `emcee.cli.main_cli()` boundary catching `(EmceeError, HerderError)`; console script `emcee`; typer `app` with an `OrderedPanelGroup`-style command order `["run", "voice", "status", "presenter", "config"]`. All later tasks register commands on this `app`.

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_no_llama_imports.py` — mirror herder's guard test (`packages/herder/tests/test_no_llama_imports.py`) but scan BOTH `packages/emcee/src` and `packages/emcee/tests` for `import llama` / `from llama`:

```python
import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(import llama\b|from llama\b)", re.M)


def test_emcee_never_imports_llama():
    root = Path(__file__).resolve().parents[1]
    offenders = [
        str(p) for d in ("src", "tests") for p in (root / d).rglob("*.py")
        if FORBIDDEN.search(p.read_text())
    ]
    assert offenders == []
```

`packages/emcee/tests/test_cli_boundary.py`:

```python
from typer.testing import CliRunner

from emcee.cli import app, main_cli
from emcee.errors import EmceeError

runner = CliRunner()


def test_help_runs_and_lists_ordered_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_main_cli_renders_emcee_error(monkeypatch, capsys):
    import pytest
    from emcee import cli

    def boom():
        raise EmceeError("station root missing", details=["set [station] root"])
    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as e:
        main_cli()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "error: station root missing" in err
    assert "  set [station] root" in err
```

- [ ] **Step 2: Run to verify they fail** — `pytest packages/emcee/tests -q` → import errors.

- [ ] **Step 3: Implement the scaffold**

`packages/emcee/pyproject.toml` — mirror `packages/llama/pyproject.toml`'s structure exactly (hatchling, license-files, dev extra with pytest):

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llama-emcee"
version = "0.1.0"
description = "Station-side DJ: voices llama show packages (script + TTS + broadcast.m3u)"
requires-python = ">=3.11"
license = "GPL-3.0-or-later"
license-files = ["LICENSE"]
dependencies = [
    "llama-herder",
    "typer>=0.12",
    "numpy>=1.26",
    "lameenc>=1.7",
    "tomli-w>=1.0",
]

[project.scripts]
emcee = "emcee.cli:main_cli"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.hatch.build.targets.wheel]
packages = ["src/emcee"]
```

(Pin floors to match the versions llama's pyproject already uses — copy them, don't invent.)

`errors.py` — `EmceeError` with the same message+details contract as `LlamaError` (write it fresh, ~15 lines, same docstring intent; do not import llama's).

`cli.py` — typer app + boundary, modeled on `packages/llama/src/llama/cli.py:57-65` and `main_cli` at `cli.py:2364-2388`:

```python
import typer
from typer.core import TyperGroup

from herder import HerderError
from emcee.errors import EmceeError

_COMMAND_ORDER = ["run", "voice", "status", "presenter", "config"]


class OrderedPanelGroup(TyperGroup):
    def list_commands(self, ctx):
        cmds = super().list_commands(ctx)
        order = {name: i for i, name in enumerate(_COMMAND_ORDER)}
        return sorted(cmds, key=lambda c: order.get(c, len(order)))


app = typer.Typer(help="Voice llama show packages: DJ script + TTS audio + broadcast.m3u",
                  pretty_exceptions_enable=False, cls=OrderedPanelGroup)


def main_cli() -> None:
    # Same boundary contract as llama's main_cli (cli.py:2364-2388): expected
    # errors render as `error: <msg>` + indented details; bugs get tracebacks.
    import sys, traceback
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
```

`__main__.py` — `from emcee.cli import main_cli` + `if __name__ == "__main__": main_cli()` (llama's 6-line pattern).

Root `pytest.ini`: add `packages/emcee/tests` to the existing testpaths line.

- [ ] **Step 4: Install + run** — `pip install -e packages/emcee`, then `pytest packages/emcee/tests -q` (pass) and `pytest -q` (1070 + new, no regressions).

- [ ] **Step 5: Commit** — `git add packages/emcee pytest.ini && git commit -m "feat: emcee package scaffold — CLI boundary, error base, no-llama guard"`

---

### Task 2: Port the speech-text layer

**Files:**
- Create: `packages/emcee/src/emcee/speech_text.py` (port of `packages/llama/src/llama/speech_text.py`, 102 lines)
- Create: `packages/emcee/src/emcee/data/__init__.py`, `packages/emcee/src/emcee/data/pronunciations.csv` (copy of llama's seed: header + Sugaree/Mydland rows)
- Create: `packages/emcee/tests/test_speech_text.py` (port of llama's 12 tests)

**Interfaces:**
- Produces: `Lexicon` (`.apply(text)`, `.empty()`), `normalize_for_speech(text, lexicon) -> str`, `load_lexicon(root: Path | None) -> Lexicon` — identical signatures to llama's. Task 8 consumes them.

- [ ] **Step 1: Copy the test file** from `packages/llama/tests/test_speech_text.py`, changing only `from llama.speech_text import ...` → `from emcee.speech_text import ...` and any `llama.data` resource references → `emcee.data`. Run → fails (module missing).
- [ ] **Step 2: Copy the module**, changing only: `resources.files("llama.data")` → `resources.files("emcee.data")` and the module docstring's package name. No other edits.
- [ ] **Step 3: Run** — emcee suite + full suite green. Diff check: `diff packages/llama/src/llama/speech_text.py packages/emcee/src/emcee/speech_text.py` shows ONLY the resource-package line (+docstring if changed).
- [ ] **Step 4: Commit** — `feat: port speech-text normalization + pronunciation lexicon to emcee`

---

### Task 3: Port the TTS provider layer

**Files:**
- Create: `packages/emcee/src/emcee/tts/__init__.py`, `provider.py`, `voxtral.py`, `elevenlabs.py`, `fake.py`, `bed.py` (ports of the five modules under `packages/llama/src/llama/tts/`)
- Create: `packages/emcee/tests/test_tts.py`, `test_voxtral.py`, `test_bed.py` (ports of llama's 22+17+9 tests)

**Interfaces:**
- Produces: `SpeechError(EmceeError)` (re-based — llama's subclasses `LlamaError`, `tts/provider.py:6`); `SpeechProvider` protocol (`synthesize(text, fmt="mp3", *, previous_text=None, next_text=None) -> bytes`); `VoxtralProvider`/`ElevenLabsProvider`/`FakeSpeechProvider`; `Bed` dataclass, `load_bed_pcm`, `mix_bed`. `speech_provider_for` is **deferred to Task 5** (it consumes emcee's config type, which doesn't exist yet) — port `tts/__init__.py` as an empty re-export module for now.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Copy the three test files**, import-renamed (`llama.tts.X` → `emcee.tts.X`, `llama.errors`/`LlamaError` expectations → `emcee.errors`/`EmceeError`). `test_tts.py`'s `speech_provider_for` factory tests move to Task 5's test file — extract them out now and stash them in Task 5's plan step (delete from the ported file). Run → fail.
- [ ] **Step 2: Copy the five modules**, changing only: `from llama.errors import LlamaError` → `from emcee.errors import EmceeError` (and the `SpeechError(EmceeError)` base), inter-module imports `llama.tts.` → `emcee.tts.`. `bed.py`, `voxtral.py`, `elevenlabs.py`, `fake.py` need no other edits. `tts/__init__.py`: keep only the re-exports (`SpeechError`, `SpeechProvider`, providers, `Bed`) — `speech_provider_for`'s body comes in Task 5.
- [ ] **Step 3: Run** — both suites green; per-file diff vs llama sources shows only the import/base lines.
- [ ] **Step 4: Commit** — `feat: port TTS provider layer (voxtral/elevenlabs/fake/bed) to emcee`

---

### Task 4: Port presenters + presenter CLI

**Files:**
- Create: `packages/emcee/src/emcee/presenters.py` (port of llama's, 77 lines)
- Modify: `packages/emcee/src/emcee/cli.py` (presenter sub-app)
- Create: `packages/emcee/tests/test_presenters.py` (port, 9 tests), `packages/emcee/tests/test_presenter_cmd.py`

**Interfaces:**
- Consumes: `EmceeError`.
- Produces: `Presenter` model (`id`/`name`/`sex`/`voice` XOR `voice_clone`/`character`/`bed`), `save_presenter`/`load_presenter`/`delete_presenter`/`list_presenters(root)` — identical signatures; `presenter_app` registered on the CLI as `emcee presenter add/list/show/remove`. Presenters live under `<emcee workspace root>/presenters/` — the root comes from config (Task 5); until then the CLI takes `--root` from an env override `EMCEE_ROOT` defaulting to `~/.emcee` (a module-level `default_root()` helper the config task replaces).
- **One deliberate behavior change** (spec §4): `presenter remove`'s referential guard checks emcee's `[assign]` config entries (which assignment names this presenter), NOT llama profiles. Until Task 5 lands config, implement the guard as a hook function `_assignments_using_presenter(root, presenter_id) -> list[str]` returning `[]`, with a TODO-free comment stating Task 5 fills it; Task 5's steps include wiring + testing it.

- [ ] **Step 1: Copy `test_presenters.py`** (import rename only; `PresenterError` should subclass `EmceeError` — assert that). Write `test_presenter_cmd.py` fresh, covering: add (flags + `--character-file`), add rejects both/neither voice fields, list table, show renders character, remove refuses when `_assignments_using_presenter` returns entries unless `--force`, remove works with `--yes`. Model the assertions on llama's 6 presenter tests in `packages/llama/tests/test_cli_commands.py`, addressing the emcee CLI (`runner.invoke(app, ["presenter", "add", ...])`, `EMCEE_ROOT` pointed at tmp_path).
- [ ] **Step 2: Port `presenters.py`** (imports only: errors base). Write the presenter sub-app in `cli.py` by porting llama's four commands (`cli.py:2250-2337`) with: root resolution via `default_root()`, guard call re-targeted as described. Register `app.add_typer(presenter_app, name="presenter")`.
- [ ] **Step 3: Run** — both suites green.
- [ ] **Step 4: Commit** — `feat: port presenters + presenter CLI to emcee`

---

### Task 5: Config (`EmceeConfig`) + `config init` + `speech_provider_for`

**Files:**
- Create: `packages/emcee/src/emcee/config.py`
- Modify: `packages/emcee/src/emcee/cli.py` (config sub-app: `emcee config init`), `packages/emcee/src/emcee/tts/__init__.py` (`speech_provider_for`), `packages/emcee/src/emcee/presenters` guard wiring in `cli.py`
- Create: `packages/emcee/tests/test_config.py`, plus the stashed `speech_provider_for` factory tests from Task 3 into `packages/emcee/tests/test_tts.py`

**Interfaces:**
- Consumes: `herder.LLMSettings`, `herder.TaskConfig`; `EmceeError`.
- Produces (Tasks 6–9 rely on all of these):

```python
DEFAULT_ROOT = Path.home() / ".emcee"
TASK_KEYS = ["scriptwrite"]
DEFAULT_TIERS = {"scriptwrite": "high"}

class StationConfig(BaseModel):
    root: Path | None = None          # the delivered-packages folder; required by run/status

class TTSConfig(BaseModel):           # port of llama's TTSConfig (config.py:39-53) MINUS `enabled`
    backend: str = "voxtral"
    voice: str | None = None
    voice_clone: str | None = None
    model: str | None = None
    api_key: str | None = None
    chunk: bool = False
    bed: str | None = None
    bed_gain_db: float = -20.0

class Assignment(BaseModel):
    presenter: str
    title: str | None = None

class AssignConfig(BaseModel):
    default: str | None = None                          # station-default presenter id
    profiles: dict[str, Assignment] = Field(default_factory=dict)

class EmceeConfig(BaseModel):
    root: Path = DEFAULT_ROOT
    station: StationConfig
    tts: TTSConfig
    assign: AssignConfig
    llm: dict[str, LLMTaskConfig]     # [llm.<task>] — same narrowing as llama's config.py:30-32
    tiers: dict[str, str]             # [llm.tiers.<backend>] passthrough
    def llm_settings(self) -> LLMSettings: ...          # mirrors llama config.py:132-133

def load_config(path: Path | None = None) -> EmceeConfig   # ~/.emcee/config.toml; values replace defaults, nothing merges
DEFAULT_CONFIG_TOML: str                                    # fully commented template
```

- Also produces: `speech_provider_for(config: EmceeConfig, voice, clone_ref=None)` — port of llama's `tts/__init__.py:8-37` reading `config.tts` identically (no `enabled` gate); and `_assignments_using_presenter(config, presenter_id)` returning `[name for name, a in config.assign.profiles.items() if a.presenter == presenter_id]` (+ `default`), wired into `presenter remove`.

- [ ] **Step 1: Write failing tests** — `test_config.py`: defaults (root, empty assign, tts backend voxtral, no `enabled` attr — `assert not hasattr(cfg.tts, "enabled")`), TOML round-trip for every section (station root, assign default + profile entries with/without title, [llm.scriptwrite] tier override narrows/validates, tiers passthrough), `llm_settings()` carries `DEFAULT_TIERS`, `DEFAULT_CONFIG_TOML` parses to defaults and mentions every section, unknown narration of missing station root raises `EmceeError` from the commands that need it (covered in Task 9). Port the stashed factory tests (fake/voxtral/elevenlabs dispatch + error cases) against `EmceeConfig`.
- [ ] **Step 2: Implement** — model llama's `config.py` structure (tomllib load, ValidationError → `EmceeError` with details). Write `DEFAULT_CONFIG_TOML` fresh covering `[station]`, `[llm]`/`[llm.scriptwrite]`/`[llm.tiers.*]`, `[tts]` (port llama's comment block minus `enabled`, `config.py:210-258`), `[assign]`/`[assign.profiles.<name>]` with a worked example. `emcee config init` mirrors llama's (`cli.py:2066-2087`): refuses to overwrite without `--force`.
- [ ] **Step 3: Run** — both suites green. — **Step 4: Commit** — `feat: emcee config — station/tts/assign/llm sections + config init`

---

### Task 6: Package IO + station model (scan, readiness, fixture helper)

**Files:**
- Create: `packages/emcee/src/emcee/models.py`, `packages/emcee/src/emcee/package_io.py`, `packages/emcee/src/emcee/station.py`
- Create: `packages/emcee/tests/helpers.py`, `packages/emcee/tests/test_station.py`, `packages/emcee/tests/test_package_io.py`

**Interfaces:**
- Produces:

```python
# models.py — emcee's OWN contract models (shape-identical to llama's manifest blocks)
class ScriptNotes(BaseModel):         # == llama DJNotes shape (models.py:206-210)
    context: str = ""
    set_intros: dict[str, str]
    outro: str
    mentioned_songs: list[str] = Field(default_factory=list)

class DJAudioBlock(BaseModel):        # == llama DJAudio shape (models.py:236-239)
    set_intros: dict[str, str]
    outro: str

# package_io.py
class Package:                        # wraps one package dir
    dir: Path
    manifest_path: Path               # dir / "manifest.json"
    def manifest(self) -> dict        # read + validate schema_version >= 3 (else UnsupportedPackage)
    def briefing(self) -> dict        # briefing.json parsed
    def briefing_md(self) -> str
class UnsupportedPackage(EmceeError): ...
def rewrite_manifest(pkg: Package, *, dj_notes: ScriptNotes | None, dj_audio: DJAudioBlock | None) -> None
    # read dict -> set blocks (model_dump) -> unique-temp atomic write; never touches other keys
def atomic_write(path: Path, text: str) -> None      # port of llama's unique-temp pattern (util/workspace)

# station.py
@dataclass
class PackageStatus:
    path: Path
    state: str            # "ready" | "pending" | "unsupported"
    reasons: list[str]    # readiness legs failing (pending) or version note (unsupported)
def readiness(pkg: Package) -> tuple[bool, list[str]]
    # legs (spec §2): dj_notes block + dj-notes.md; dj_audio block + every referenced file on disk;
    # broadcast.m3u exists; every manifest track's audio file on disk
def scan(station_root: Path) -> list[PackageStatus]   # direct subdirs containing manifest.json
```

- `helpers.py`: `build_package(root, slug="gd1973-06-10", *, voiced=False, profile=None, narration="full", sets=("1","2"), encore=True) -> Path` — fabricates a full v3 package: manifest (schema_version 3, briefing block, `source.profile` when given, tracks with per-set files + set_breaks), `briefing.json`/`briefing.md`, `audio/*.mp3` stub files, and (when `voiced`) dj blocks + `dj-audio/*.mp3` + `broadcast.m3u`. Model the manifest dict on llama's `packages/llama/tests/helpers.py:build_ready` v3 shape. Every later task's tests use this.

- [ ] **Step 1: Failing tests** — `test_package_io.py`: v3 manifest parses; v2 raises `UnsupportedPackage`; missing manifest raises `EmceeError`; `rewrite_manifest` sets exactly the two blocks (byte-compare every other key before/after), is atomic (no partial file on injected failure), and round-trips `None` (clears blocks). `test_station.py`: `scan` finds packages one level deep and skips non-package dirs; `readiness` fails each leg independently (unvoiced fixture → the three voice legs; delete one music file → audio leg; voiced fixture → ready); v2 package → `unsupported` with re-deliver message.
- [ ] **Step 2: Implement.** — **Step 3: Run both suites.** — **Step 4: Commit** — `feat: emcee package IO + station scan/readiness model`

---

### Task 7: Scriptwrite — prompt, persona port, guard, render

**Files:**
- Create: `packages/emcee/src/emcee/scriptwrite.py`, `packages/emcee/src/emcee/prompts/__init__.py` (port of llama's 5-line loader, resource package `emcee.prompts`), `packages/emcee/src/emcee/prompts/scriptwrite.md`
- Create: `packages/emcee/tests/test_scriptwrite.py`

**Interfaces:**
- Consumes: `herder.run_json_task`, `FakeProvider` (herder), `ScriptNotes`, `Package` (Task 6), `Presenter`.
- Produces:

```python
NEUTRAL_STYLE: str                    # byte-for-byte from llama synthesize.py:39-43
def persona_style(presenter: Presenter, title: str | None) -> str   # byte-for-byte port of synthesize.py:46-75
def normalize_song(title: str) -> str                # port from llama.songs (just the normalizer emcee needs)
def script_guard(notes: ScriptNotes, manifest: dict, narration: str) -> list[str]
def render_notes_md(notes: ScriptNotes, manifest: dict) -> str      # port of synthesize.py:112-125, show fields from manifest["show"]
def write_script(pkg: Package, provider, presenter: Presenter | None, title: str | None) -> ScriptNotes
    # briefing+manifest -> prompt -> run_json_task("scriptwrite", ScriptNotes, ...) -> guard -> retry once -> raise EmceeError on persistent failure
```

- Guard checks, ported from `factual_guard` (`synthesize.py:78-109`) re-sourced to manifest: `mentioned_songs` ⊆ manifest track titles (via `normalize_song`); `set_intros` keys == non-encore sets from `manifest["tracks"][i]["set"]`; every non-encore set has an intro; set-count claims in prose (port the four regex/dict constants verbatim). **Plus** narration: when `narration == "vague"`, any `mentioned_songs` entry or any set-count claim in prose is a failure (segment structure stays — spec §3). Flag strings keep llama's `"dj notes ..."` phrasing (the strings are station-visible contract in dj-notes rendering — keep continuity).
- `scriptwrite.md`: port `packages/llama/src/llama/prompts/synthesize.md` with these edits ONLY: `{{show_json}}` → `{{manifest_show_json}}` (the manifest `show`/`tracks`/`set_breaks` slice), `Research findings:{{research}}` → `Briefing (your source material):{{briefing_md}}`, drop `{{reviews_digest}}` (review sentiment arrives inside the briefing), keep `{{style}}`/`{{narration_note}}`/`{{lead_in_sets}}`/`{{encore_note}}`/`{{feedback}}` and all three spoken-delivery rules verbatim. Vague narration note: port `_VAGUE_NOTE` + `narration_note()` (`synthesize.py:11-25`) into `scriptwrite.py`.

- [ ] **Step 1: Failing tests** — port the guard/render/persona halves of llama's `test_stage_synthesize.py` (the ~10 persona/style tests + guard tests), re-addressed to manifest-sourced calls via Task 6's `build_package`; add: NEUTRAL_STYLE byte-lock test (compare against the literal string), vague-mode guard cases, `write_script` retry-with-feedback then `EmceeError` (queue two bad `FakeProvider` responses), successful write returns stamped notes without touching the package (write happens in Task 8's orchestrator — `write_script` is pure).
- [ ] **Step 2: Implement.** — **Step 3: Run both suites** (byte-diff `persona_style`/`NEUTRAL_STYLE` against llama's source in the test). — **Step 4: Commit** — `feat: emcee scriptwrite — persona port, manifest-sourced guard, prompt`

---

### Task 8: Audio pipeline + process_package orchestrator

**Files:**
- Create: `packages/emcee/src/emcee/audio.py` (port of `package.py`'s speech half), `packages/emcee/src/emcee/process.py`
- Create: `packages/emcee/tests/test_audio.py`, `packages/emcee/tests/test_process.py`

**Interfaces:**
- Consumes: everything above.
- Produces:

```python
# audio.py — ports from packages/llama/src/llama/stages/package.py, import-renamed:
#   _split_sentences (L50-77), _bitrate_for_rate (L80-95), _encode_mp3 (L98-106),
#   _chunked_pcm (L109-136), _synthesize_chunked (L139-157), _segment_pcm (L160-172),
#   _segment_texts (L175-180), _synthesize_dj_audio (L183-256, param `notes: ScriptNotes`)
# plus ports of llama manifest.py:41-62:
def interleave_broadcast(tracks: list[dict], dj_audio: DJAudioBlock) -> list[str]
def broadcast_m3u_text(tracks: list[dict], dj_audio: DJAudioBlock) -> str

# process.py
def resolve_assignment(config: EmceeConfig, manifest: dict) -> tuple[Presenter | None, str | None]
    # source.profile -> assign.profiles[name] -> load_presenter; else assign.default; else (None, None)
def process_package(config: EmceeConfig, pkg: Package, speech, force: bool = False) -> None
    # write_script -> render dj-notes.md -> _synthesize_dj_audio -> broadcast.m3u
    # -> rewrite_manifest(dj_notes=..., dj_audio=...)  [manifest LAST — success marker]
    # loads the lexicon itself: load_lexicon(config.root) — station overlay at ~/.emcee/pronunciations.csv
    # On ANY failure: raise; nothing partial visible (script/audio staged to temp names or
    # written only after all succeed — dj-notes.md, dj-audio/, broadcast.m3u written, then manifest)
def speech_for(config: EmceeConfig, presenter: Presenter | None):   # port of llama cli.py:167-185
    # presenter voice_clone/voice > station tts voice/voice_clone; raise EmceeError if none; resolve_bed folded in
```

- The per-segment cache, orphan pruning, chunking, bed mixing, and normalization behavior all arrive via the `_synthesize_dj_audio` port unchanged (`segments.json` sidecar, key = sha256 of spoken+voice+model+chunk+bed_key).
- Failure semantics (spec §2): `process_package` writes the manifest **last**; a guard/TTS failure leaves the package without the new blocks → still `pending`.

- [ ] **Step 1: Failing tests** — port the ~15 voice-specific tests from llama's `test_stage_package.py` (dj-audio synthesis + manifest block, cache skip/re-key on voice change, the 5 bed tests, segue-symbol + lexicon normalization, chunk flag) re-addressed to `process_package` with `FakeSpeechProvider` and `build_package` fixtures; port llama's `test_chunk.py` splitter/encoder tests against `emcee.audio`. New tests: assignment resolution chain (profile match → default → neutral), manifest-written-last (inject TTS failure after script → manifest unchanged, no dj blocks), broadcast.m3u interleave parity with llama's (`test_manifest.py`'s interleave cases, ported).
- [ ] **Step 2: Implement.** — **Step 3: Run both suites.** — **Step 4: Commit** — `feat: emcee audio pipeline + process_package orchestrator`

---

### Task 9: CLI verbs — `run`, `voice`, `status`

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py`
- Create: `packages/emcee/tests/test_run_cmd.py`, `packages/emcee/tests/test_status_cmd.py`, `packages/emcee/tests/test_voice_cmd.py`

**Interfaces:**
- Consumes: `scan`/`readiness`/`process_package`/`speech_for`/`load_config`.
- Produces the user-facing surface:
  - `emcee run [--force] [--station-root PATH]` — scan; process every `pending` package; per-package errors are caught, printed (`error: <slug>: <msg>`), and the batch continues; exit 1 if any failed, else 0. `unsupported` packages print their re-deliver note. Empty/missing station root → `EmceeError` naming `[station] root`.
  - `emcee voice <package-path> [--fresh STEM]... [--force]` — one package. `--fresh` deletes `dj-audio/<stem>.mp3` (validating the stem exists in the manifest's dj_audio block first, llama `voice --fresh` semantics from `cli.py:1675-1709`) then reprocesses; cache re-rolls just those clips.
  - `emcee status [--json]` — table: slug, state (`ready`/`pending`/`unsupported`), reasons; `--json` emits the same as a list of objects.
- [ ] **Step 1: Failing tests** — CliRunner-driven: run over a station with one unvoiced + one voiced + one v2 package (processes exactly the unvoiced one, exit 0; with an injected failing package → exit 1, other package still processed); status renders all three states with reasons (+ `--json` shape); voice on a single path; `--fresh` re-rolls one stem (file mtime/content changes, sibling clip untouched — port llama's `test_voice_cmd.py` fresh cases); missing station root error.
- [ ] **Step 2: Implement** (fake speech via config `backend = "fake"`, per llama's test convention). — **Step 3: Run both suites.** — **Step 4: Commit** — `feat: emcee run/voice/status CLI`

---

### Task 10: Whole-package verification

**Files:** none new (fixes only if verification fails).

- [ ] **Step 1:** `pytest packages/emcee/tests -q` standalone AND `pytest -q` from root — both green; record counts.
- [ ] **Step 2:** Fresh-venv check: new venv, `pip install -e packages/herder -e packages/emcee` (NO llama), `pytest packages/emcee/tests -q` — proves emcee runs without llama installed; then `emcee --help`, `emcee config init` into a temp `EMCEE_ROOT`, `emcee status` against a fabricated station dir.
- [ ] **Step 3:** Verify `git diff main -- packages/llama packages/herder` is empty (this plan never touched them).
- [ ] **Step 4:** Commit any fixes — `test: emcee whole-package verification` (or no commit if clean).
