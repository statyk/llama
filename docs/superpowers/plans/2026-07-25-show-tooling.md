# Show-management tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable per-show `overrides.json` (excluded tracks + narration
mode) that gather/synthesize honor, a "voiced" dimension and richer selectors
to `status`, single-and-set resolution on `show` (with interactive walkthrough
and `--apply`), selector-batch `redo`/`deliver`, and a sensibly ordered/paneled
`--help`.

**Architecture:** `overrides.json` is a hand-authored input file the
derive-from-scratch stages read, so it survives every `redo`; `show.json` stays
purely derived. A shared `catalog.select_shows` selector vocabulary is reused by
`status`, `show` (set form), and the batch forms of `redo`/`deliver`. All show
resolution (single, interactive, set) lives on `show`; there is no new verb.

**Tech Stack:** Python 3, Typer (0.26, rich rendering available — no `rich`
dependency added), Pydantic v2, pytest with the `fake` LLM backend, offline.

## Global Constraints

- No backward compatibility, no migration: `overrides.json` is purely additive;
  a show without one behaves exactly as today.
- Offline, deterministic tests only (`fake` backend + captured fixtures). Never
  commit audio.
- Do not add new third-party dependencies. Typer's rich help rendering is
  already available; use it via a custom group class, not a new dep.
- `overrides.narration` is binary: `"full"` (default) | `"vague"`. No graduated
  levels.
- State is derived, never stored (`catalog.derive_state`). `overrides.json` is
  an *input*, not derived state.
- Held shows still gate processing; there is no force-through-processing flag.
- Match existing code style: `typer.echo` for output, `log`/`log.warning`
  (logger name `"llama"`) for narration/warnings, `write_artifact` for atomic
  writes, `read_model`/`read_json` for reads.

---

### Task 1: `Overrides` model + workspace path + read helper

**Files:**
- Modify: `src/llama/models.py` (add `Overrides` near `Show`, ~line 186)
- Modify: `src/llama/workspace.py` (add `ShowWorkspace.overrides`; add
  `read_overrides`)
- Test: `tests/test_workspace.py`

**Interfaces:**
- Produces: `llama.models.Overrides(exclude: list[str] = [], narration: str = "full")`
- Produces: `ShowWorkspace.overrides: Path` (= `dir / "overrides.json"`)
- Produces: `llama.workspace.read_overrides(show_ws: ShowWorkspace) -> Overrides`
  (returns defaults when the file is absent)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_workspace.py`:

```python
from llama.models import Overrides
from llama.workspace import ShowWorkspace, read_overrides, write_artifact


def test_read_overrides_defaults_when_absent(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    ov = read_overrides(ws)
    assert ov.exclude == [] and ov.narration == "full"


def test_read_overrides_round_trip(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))
    ov = read_overrides(ws)
    assert ov.exclude == ["a.mp3"] and ov.narration == "vague"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workspace.py -k overrides -q`
Expected: FAIL — `ImportError: cannot import name 'Overrides'` / `read_overrides`.

- [ ] **Step 3: Add the model**

In `src/llama/models.py`, after the `Show` class (around line 186) add:

```python
class Overrides(BaseModel):
    """Hand-authored per-show operator input, durable across re-derivation.
    Read by gather (exclude) and synthesize (narration); never auto-written by
    a stage. Absent file == this default."""
    exclude: list[str] = Field(default_factory=list)   # source filenames to drop
    narration: str = "full"                            # "full" | "vague"
```

- [ ] **Step 4: Add the workspace path + reader**

In `src/llama/workspace.py`, inside `ShowWorkspace.__init__`, after
`self.dj_notes_json = ...` add:

```python
        self.overrides = dir / "overrides.json"
```

At module level (after `read_json`), add:

```python
def read_overrides(show_ws: "ShowWorkspace"):
    from llama.models import Overrides
    if show_ws.overrides.exists():
        return read_model(show_ws.overrides, Overrides)
    return Overrides()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workspace.py -k overrides -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/llama/models.py src/llama/workspace.py tests/test_workspace.py
git commit -m "feat: Overrides model + overrides.json workspace path and reader"
```

---

### Task 2: gather honors `overrides.exclude`

**Files:**
- Modify: `src/llama/stages/gather.py` (after `filter_files`, ~line 119)
- Test: `tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `read_overrides` (Task 1), `ShowWorkspace.overrides`
- Behavior: named files are dropped from `kept` before setlist ranking and
  alignment; they are appended to the `excluded` record with reason
  `"operator-excluded"`; a non-matching exclude entry logs a warning and is a
  no-op; a clean re-derivation yields `needs_review=False` on its own.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_stage_gather.py`:

```python
from llama.models import Overrides
from llama.workspace import read_overrides, write_artifact


def test_gather_drops_operator_excluded_file(tmp_path: Path):
    # First derive normally to learn a real filename.
    base = ShowWorkspace(tmp_path / "base")
    show0 = run_gather(base, StubIA(), FakeProvider(), make_candidate(), IDENT)
    drop = show0.tracks[-1].filename
    n = len(show0.tracks)

    ws = ShowWorkspace(tmp_path / "show")
    write_artifact(ws.overrides, Overrides(exclude=[drop]))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)

    assert drop not in [t.filename for t in show.tracks]
    assert len(show.tracks) == n - 1
    assert [t.index for t in show.tracks] == list(range(1, n))  # contiguous
    assert any(x["filename"] == drop and "operator-excluded" in x["reasons"]
               for x in show.excluded_files)


def test_gather_exclude_no_match_warns_and_is_noop(tmp_path: Path, caplog):
    ws = ShowWorkspace(tmp_path / "show")
    write_artifact(ws.overrides, Overrides(exclude=["does-not-exist.mp3"]))
    with caplog.at_level("WARNING", logger="llama"):
        show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert len(show.tracks) == 6
    assert any("matched no file" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_gather.py -k operator_excluded -q`
Expected: FAIL — excluded file still present / no warning emitted.

- [ ] **Step 3: Implement the exclusion**

In `src/llama/stages/gather.py`, add the import at the top with the other
workspace imports (line 17):

```python
from llama.workspace import ShowWorkspace, read_model, read_overrides, should_run, write_artifact
```

Immediately after the `kept, excluded, ordering = filter_files(...)` line
(~line 119) insert:

```python
    overrides = read_overrides(show_ws)
    if overrides.exclude:
        drop = set(overrides.exclude)
        matched = {f["name"] for f in kept if f["name"] in drop}
        for missing in sorted(drop - matched):
            log.warning("overrides.exclude entry %r matched no file", missing)
        excluded += [{"filename": f["name"], "reasons": ["operator-excluded"]}
                     for f in kept if f["name"] in drop]
        kept = [f for f in kept if f["name"] not in drop]
```

(Note: `filter_files` yields file dicts keyed by `"name"`; the surrounding code
already uses `f.get("title")` on `kept` entries, confirming they are the raw
archive file dicts.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS (all gather tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/gather.py tests/test_stage_gather.py
git commit -m "feat: gather drops overrides.exclude files, warns on no-match"
```

---

### Task 3: synthesize honors `overrides.narration`

**Files:**
- Modify: `src/llama/prompts/synthesize.md` (add `{{narration_note}}` slot)
- Modify: `src/llama/stages/synthesize.py` (helper + inputs)
- Test: `tests/test_stage_synthesize.py`, `tests/test_prompts.py`

**Interfaces:**
- Consumes: `read_overrides` (Task 1)
- Produces: `llama.stages.synthesize.narration_note(narration: str) -> str`
  (`""` for `"full"`, the vague instruction for `"vague"`)
- Prompt `synthesize` gains exactly one new placeholder: `narration_note`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_stage_synthesize.py`:

```python
from llama.models import Overrides
from llama.stages.synthesize import narration_note, run_synthesize
from llama.workspace import write_artifact


def test_narration_note_full_is_empty():
    assert narration_note("full") == ""


def test_narration_note_vague_forbids_naming_songs():
    note = narration_note("vague")
    assert note and "do not name" in note.lower()


def test_synthesize_passes_narration_note_from_overrides(tmp_path, monkeypatch):
    import llama.stages.synthesize as syn
    captured = {}

    def fake_run_json_task(provider, task, schema, *, feedback="", **inputs):
        captured.update(inputs)
        return schema(context="c", set_intros={"1": "a lead-in"}, outro="bye",
                      mentioned_songs=[])

    monkeypatch.setattr(syn, "run_json_task", fake_run_json_task)
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(narration="vague"))
    show = make_show_one_set()  # helper already in this test module
    run_synthesize(ws, FakeProvider(), show, "research", [], force=True)
    assert captured["narration_note"]  # non-empty vague note reached the prompt
```

Update the golden expectation in `tests/test_prompts.py`:

```python
    "synthesize": {"style", "show_json", "research", "reviews_digest",
                   "lead_in_sets", "encore_note", "feedback", "narration_note"},
```

If `tests/test_stage_synthesize.py` has no `make_show_one_set` helper, add one:

```python
def make_show_one_set():
    from llama.models import Show, Track
    return Show(performance_id="X/2003-04-19", identifier="x", artist="X",
                date="2003-04-19",
                tracks=[Track(index=1, set="1", title="Unknown 1",
                              filename="a.mp3", title_source="unresolved")])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_synthesize.py -k narration tests/test_prompts.py -k synthesize -q`
Expected: FAIL — `narration_note` missing; golden placeholder set mismatch.

- [ ] **Step 3: Add the prompt slot**

In `src/llama/prompts/synthesize.md`, after the three hard-rules block and
before `Show data (JSON):`, insert on its own line:

```
{{narration_note}}
```

- [ ] **Step 4: Implement the helper + wire inputs**

In `src/llama/stages/synthesize.py` add near the top (after the imports):

```python
_VAGUE_NOTE = (
    "IMPORTANT — uncertain setlist: this show's song list is incomplete and the "
    "available sources conflict. Do NOT name specific songs, do NOT assert a set "
    "count or set structure, and state nothing as fact that the show data does "
    "not confirm. Speak to the band, the era, the venue, the performance, and its "
    "reputation instead. Leave mentioned_songs empty."
)


def narration_note(narration: str) -> str:
    return _VAGUE_NOTE if narration == "vague" else ""
```

In `run_synthesize`, before building `inputs`, read overrides:

```python
    from llama.workspace import read_overrides
    note = narration_note(read_overrides(show_ws).narration)
```

Add to the `inputs = dict(...)` call:

```python
        narration_note=note,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_stage_synthesize.py tests/test_prompts.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/prompts/synthesize.md src/llama/stages/synthesize.py tests/test_stage_synthesize.py tests/test_prompts.py
git commit -m "feat: synthesize honors overrides.narration (vague mode)"
```

---

### Task 4: catalog — `voiced` derivation, entry fields, `select_shows`

**Files:**
- Modify: `src/llama/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces: `CatalogEntry.voiced: bool | None` (None = pre-package),
  `CatalogEntry.overrides: Overrides`
- Produces: `llama.catalog.derive_voiced(ws: ShowWorkspace) -> bool | None`
- Produces: `llama.catalog.select_shows(entries, *, states: set[str] | None = None,
  voiced: bool | None = None, artist: str | None = None, run: str | None = None)
  -> list[CatalogEntry]` — `states` matches by membership (OR within the state
  dimension); every other dimension ANDs.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_catalog.py`:

```python
from llama.catalog import derive_voiced, select_shows
from llama.models import Overrides


def test_derive_voiced_states(tmp_path):
    pre = build(tmp_path / "a", "a", stages={"select"})
    assert derive_voiced(pre) is None
    silent = build(tmp_path / "b", "b",
                   stages={"select", "gather", "research", "vet", "synthesize", "package"})
    assert derive_voiced(silent) is False
    voiced = ShowWorkspace(tmp_path / "c" / "shows" / "c")
    write_artifact(voiced.package_dir / "manifest.json",
                   {"schema_version": 2, "dj_audio": {"set_intros": {"1": "x"}, "outro": "o"}})
    assert derive_voiced(voiced) is True


def test_iter_shows_populates_voiced_and_overrides(tmp_path):
    ws = build(tmp_path, "s", stages={"select", "gather"})
    write_artifact(ws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))
    (entry,) = iter_shows(tmp_path, Ledger(tmp_path / "ledger.jsonl"))
    assert entry.voiced is None
    assert entry.overrides.exclude == ["a.mp3"] and entry.overrides.narration == "vague"


def test_select_shows_filters():
    from llama.catalog import CatalogEntry
    from llama.workspace import ShowWorkspace
    def e(slug, state, voiced=None, artist="Grateful Dead"):
        return CatalogEntry(slug=slug, ws=ShowWorkspace(Path("/x")), state=state,
                            voiced=voiced, artist=artist)
    es = [e("a", "held"), e("b", "packaged", voiced=False),
          e("c", "packaged", voiced=True), e("d", "delivered", artist="Phish")]
    assert {x.slug for x in select_shows(es, states={"held"})} == {"a"}
    assert {x.slug for x in select_shows(es, states={"held", "packaged"})} == {"a", "b", "c"}
    assert {x.slug for x in select_shows(es, voiced=False)} == {"b"}
    assert {x.slug for x in select_shows(es, artist="phish")} == {"d"}
    assert {x.slug for x in select_shows(es, states={"packaged"}, voiced=True)} == {"c"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_catalog.py -k "voiced or select_shows or overrides" -q`
Expected: FAIL — names not defined / `CatalogEntry` has no `voiced`.

- [ ] **Step 3: Implement in `src/llama/catalog.py`**

Add imports at the top:

```python
from llama.models import Overrides, Provenance, Show
from llama.workspace import ShowWorkspace, read_json, read_model, read_overrides
```

(Extend the existing `from llama.workspace import ...` and `from llama.models
import ...` lines rather than duplicating.)

Add the two new fields to `CatalogEntry`:

```python
    voiced: bool | None = None
    overrides: Overrides = field(default_factory=Overrides)
```

Add `derive_voiced` (after `derive_state`):

```python
def derive_voiced(ws: ShowWorkspace) -> bool | None:
    """True/False once a package exists (from the manifest's dj_audio block,
    falling back to a non-empty dj-audio/ dir); None for a pre-package show."""
    manifest = ws.package_dir / "manifest.json"
    if not manifest.exists():
        return None
    if read_json(manifest).get("dj_audio") is not None:
        return True
    audio = ws.package_dir / "dj-audio"
    return bool(audio.is_dir() and any(audio.glob("*.mp3")))
```

In `iter_shows`, where each `CatalogEntry(...)` is built, add:

```python
        entries.append(CatalogEntry(slug=d.name, ws=ws, state=state, flags=flags,
                                    provenance=prov, artist=artist, date=date,
                                    voiced=derive_voiced(ws),
                                    overrides=read_overrides(ws)))
```

Add `select_shows` (after `iter_shows`):

```python
def select_shows(entries, *, states=None, voiced=None, artist=None, run=None):
    out = list(entries)
    if states:
        out = [e for e in out if e.state in states]
    if voiced is not None:
        out = [e for e in out if e.voiced is voiced]
    if artist:
        out = [e for e in out if artist.lower() in e.artist.lower()]
    if run:
        out = [e for e in out if e.provenance and e.provenance.run == run]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_catalog.py -q`
Expected: PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/llama/catalog.py tests/test_catalog.py
git commit -m "feat: catalog voiced dimension, overrides on entries, select_shows"
```

---

### Task 5: `status` — voiced/state filters + annotations + JSON fields

**Files:**
- Modify: `src/llama/cli.py` (the `status` command, ~lines 643-693)
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: `select_shows` (Task 4), `CatalogEntry.voiced`/`.overrides`
- Adds options `--voiced`, `--unvoiced`, `--state NAME`.
- Text rows gain a trailing annotation `[voiced, vague, 2x-excl]` when non-empty.
- `--json` records gain `voiced` and `overrides`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_status.py` (mirror the file's existing setup helpers; if it
builds shows via `catalog`/`ShowWorkspace`, reuse that; otherwise use the
`build` pattern from `tests/test_catalog.py`). Example assuming a `build` helper
and a `run_status(*args)` invoking the CLI:

```python
import json


def test_status_unvoiced_filter_and_annotation(tmp_path, cli_config):
    # a packaged silent show and a voiced one
    build(tmp_path, "silent", stages=ALL_PACKAGE_STAGES)
    voiced = ShowWorkspace(tmp_path / "shows" / "voiced")
    write_artifact(voiced.package_dir / "manifest.json",
                   {"schema_version": 2, "dj_audio": {"set_intros": {}, "outro": "o"}})
    write_artifact(voiced.provenance, some_provenance("voiced"))

    out = run_status(["--unvoiced", "--config", cli_config])
    assert "silent" in out and "voiced" not in out


def test_status_json_has_voiced_and_overrides(tmp_path, cli_config):
    ws = build(tmp_path, "s", stages={"select", "gather"})
    write_artifact(ws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))
    rows = json.loads(run_status(["--json", "--config", cli_config]))
    row = next(r for r in rows if r["slug"] == "s")
    assert row["voiced"] is None
    assert row["overrides"] == {"exclude": ["a.mp3"], "narration": "vague"}
```

(Adapt `build`, `cli_config`, `run_status`, `ALL_PACKAGE_STAGES`,
`some_provenance` to whatever `tests/test_status.py` already provides; the
assertions are the contract.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_status.py -k "unvoiced or overrides" -q`
Expected: FAIL — unknown option `--unvoiced` / missing JSON keys.

- [ ] **Step 3: Implement in the `status` command**

Add options to the signature:

```python
    voiced: bool = typer.Option(False, "--voiced", help="Only voiced shows"),
    unvoiced: bool = typer.Option(False, "--unvoiced", help="Only packaged shows with no DJ audio"),
    state: str = typer.Option(None, "--state", help="Only shows in this derived state"),
```

Replace the manual filter block (`if held:` … `if artist:`) with:

```python
    from llama.catalog import iter_shows, select_shows

    config, _, ledger = _setup(config_path)
    entries = iter_shows(config.root, ledger)
    states = set()
    if held:
        states.add("held")
    if packaged:
        states.add("packaged")
    if state:
        states.add(state)
    voiced_filter = True if voiced else (False if unvoiced else None)
    entries = select_shows(entries, states=states or None, voiced=voiced_filter,
                           artist=artist, run=run)
    filtering = bool(states or voiced_filter is not None or run or artist)
```

Change the delivered-trim guard from `if not all_shows and not (held or
packaged):` to:

```python
    if not all_shows and not filtering:
```

In the `--json` block, extend each record dict with:

```python
            "voiced": e.voiced,
            "overrides": {"exclude": e.overrides.exclude, "narration": e.overrides.narration},
```

In the text-rendering loop, after the main `typer.echo(f"{e.slug...}")` line,
build and append an annotation:

```python
    for e in entries:
        run_name = e.provenance.run if e.provenance else "?"
        marks = []
        if e.voiced:
            marks.append("voiced")
        if e.overrides.narration == "vague":
            marks.append("vague")
        if e.overrides.exclude:
            marks.append(f"{len(e.overrides.exclude)}x-excl")
        suffix = f"  [{', '.join(marks)}]" if marks else ""
        typer.echo(f"{e.slug:42.42s} {e.state:10s} {e.artist:20.20s} {e.date:10s} {run_name}{suffix}")
        for f in e.flags:
            typer.echo(f"      - {f}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_status.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_status.py
git commit -m "feat: status --voiced/--unvoiced/--state filters and annotations"
```

---

### Task 6: Refactor `redo` into a reusable `_redo_show` helper

**Files:**
- Modify: `src/llama/cli.py` (extract from the `redo` command body, ~577-641)
- Test: existing `tests/test_cli_commands.py::test_redo_*` (regression net)

**Interfaces:**
- Produces: `_redo_show(config, ia, ledger, entry, from_stage: str, *,
  with_research: bool = False, script: bool | None = None,
  voice: bool | None = None) -> Path | None` — drops `from_stage` + downstream,
  re-runs the tail via `process_show`, returns the package path or `None`
  (needs-review skip). Raises `LlamaError` when the show has no provenance.
- The `redo` CLI command becomes a thin wrapper around it (behavior unchanged).

- [ ] **Step 1: Add the helper (pure extraction)**

In `src/llama/cli.py`, add above the `redo` command:

```python
def _redo_show(config, ia, ledger, entry, from_stage: str, *,
               with_research: bool = False, script: bool | None = None,
               voice: bool | None = None) -> Path | None:
    """Re-run one resolved show from `from_stage` onward; returns the package
    path, or None if the show was held/skipped. Raises LlamaError on a
    hand-built show with no provenance."""
    from llama.models import QualityAssessment
    from llama.workspace import drop_stage_artifacts

    if entry.provenance is None:
        raise LlamaError(f"no provenance.json in {entry.ws.dir} - "
                         "reprocess it via its run first")
    prov = entry.provenance
    presenter = (load_presenter(config.root, prov.presenter)
                 if prov.presenter else None)
    keep_research = not with_research and from_stage in ("select", "gather")
    drop_stage_artifacts(entry.ws, from_stage, keep_research=keep_research)
    assessment = (prov.assessment.model_copy(update={"rationale": prov.dossier})
                  if prov.assessment is not None
                  else QualityAssessment(performance_id=prov.performance_id,
                                         quality_score=0.0, rationale=prov.dossier))
    shortlist_entry = ShortlistEntry(rank=1, candidate=prov.candidate, assessment=assessment)
    ws = RunWorkspace(config.root, prov.run)
    effective_voice = _replay_voice(config, prov.voice, voice)
    effective_script = (prov.script if script is None else script) or effective_voice is not None
    speech = _speech_for(config, effective_voice, presenter)
    try:
        return process_show(ws, ia, ledger, shortlist_entry, make_providers(config),
                            prov.run, config.audio_format, script=effective_script,
                            voice=effective_voice, speech=speech, chunk=config.tts.chunk,
                            bed=resolve_bed(config, presenter),
                            presenter=presenter, title=prov.title,
                            setlistfm=make_client(config), structure_cfg=config.structure,
                            jerrybase_enabled=config.jerrybase.enabled,
                            selection_cfg=config.selection)
    finally:
        if speech is not None:
            speech.close()
```

- [ ] **Step 2: Rewrite the `redo` command body to call it**

Replace the body of `redo` after the stage-validation block with:

```python
    config, ia, ledger = _setup(config_path)
    entry = _resolve_show(config, ledger, name)
    if entry.provenance is None:
        typer.echo(f"no provenance.json in {entry.ws.dir} - "
                   "reprocess it via its run first", err=True)
        raise typer.Exit(1)
    pkg = _redo_show(config, ia, ledger, entry, from_stage,
                     with_research=with_research, script=script, voice=voice)
    if pkg:
        typer.echo(f"packaged: {pkg}")
    else:
        typer.echo(f"needs-review, skipped: {entry.provenance.performance_id}")
```

(Delete the now-duplicated inline logic; keep the stage-validation guard that
precedes it.)

- [ ] **Step 3: Run the redo regression tests**

Run: `pytest tests/test_cli_commands.py -k redo tests/test_cli_voice.py -q`
Expected: PASS (behavior unchanged — same messages, same artifacts).

- [ ] **Step 4: Commit**

```bash
git add src/llama/cli.py
git commit -m "refactor: extract _redo_show helper from redo command"
```

---

### Task 7: `show` single-show resolution flags + overrides display

**Files:**
- Modify: `src/llama/cli.py` (the `show` command, ~483-533; add helpers)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `read_overrides`, `write_artifact`, `_redo_show` (Task 6)
- Produces helpers: `_edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(),
  narration=None) -> Overrides`; `_clear_hold(show_ws) -> None`
- `show` gains `--exclude FILE` (repeatable), `--include FILE` (repeatable),
  `--vague`, `--full`, `--apply`. Existing `--clear` unchanged. Output gains an
  `overrides:` line. Default (no action flag) still just inspects.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_commands.py`:

```python
from llama.models import Overrides
from llama.workspace import read_overrides


def _held_show_dir(tmp_path):
    # minimal held, provenance-bearing show (reuse existing builders if present)
    from test_catalog import build
    ws = build(tmp_path, "gratefuldead-1973-06-10",
               stages={"select", "gather"}, needs_review=True)
    return ws


def test_show_vague_writes_overrides_clears_hold_prints_next(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _held_show_dir(tmp_path)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--vague", "--config", cfg])
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.narration == "vague"
    from llama.models import Show
    assert read_model(ws.show, Show).needs_review is False
    assert "redo gratefuldead-1973-06-10 --from synthesize" in r.output


def test_show_exclude_writes_overrides_keeps_hold_prints_gather(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _held_show_dir(tmp_path)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--exclude", "junk.mp3",
                                "--config", cfg])
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["junk.mp3"]
    from llama.models import Show
    assert read_model(ws.show, Show).needs_review is True   # NOT pre-cleared
    assert "--from gather" in r.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -k "show_vague or show_exclude" -q`
Expected: FAIL — unknown options `--vague`/`--exclude`.

- [ ] **Step 3: Add the helpers**

In `src/llama/cli.py` add near `_resolve_show`:

```python
def _edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(), narration=None):
    from llama.models import Overrides
    from llama.workspace import read_overrides
    ov = read_overrides(show_ws)
    exclude = [f for f in ov.exclude if f not in set(rm_exclude)]
    for f in add_exclude:
        if f not in exclude:
            exclude.append(f)
    ov = Overrides(exclude=exclude, narration=narration or ov.narration)
    write_artifact(show_ws.overrides, ov)
    return ov


def _clear_hold(show_ws):
    s = read_model(show_ws.show, Show)
    s.needs_review = False
    s.review_flags = []
    write_artifact(show_ws.show, s)
```

- [ ] **Step 4: Extend the `show` command**

Add options to the signature (keep `name` and `clear`):

```python
    exclude: list[str] = typer.Option(None, "--exclude", help="Add source filenames to overrides.exclude"),
    include: list[str] = typer.Option(None, "--include", help="Remove filenames from overrides.exclude"),
    vague: bool = typer.Option(False, "--vague", help="Set narration=vague and clear the hold"),
    full: bool = typer.Option(False, "--full", help="Reset narration to full"),
    apply: bool = typer.Option(False, "--apply", help="Run the resolving redo now instead of printing it"),
```

After the existing inspection output (the stage table + needs-review block, but
*before* the old `if clear:` block), add the `overrides:` display right after
the `state:` line:

```python
    from llama.workspace import read_overrides
    ov = read_overrides(sws)
    if ov.exclude or ov.narration != "full":
        typer.echo(f"overrides: narration={ov.narration} exclude={ov.exclude}")
```

Replace the trailing `if clear: ... else: ...` block with unified resolution
handling:

```python
    did_exclude = bool(exclude or include)
    did_narration = vague or full
    if did_exclude:
        _edit_overrides(sws, add_exclude=exclude or [], rm_exclude=include or [])
    if vague:
        _edit_overrides(sws, narration="vague")
        _clear_hold(sws)
    if full:
        _edit_overrides(sws, narration="full")
    if clear:
        _clear_hold(sws)
    if not (did_exclude or did_narration or clear):
        return
    stage = "gather" if did_exclude else ("synthesize" if did_narration else "package")
    if apply:
        config2, ia, ledger2 = _setup(config_path)
        entry2 = _resolve_show(config2, ledger2, entry.slug)
        pkg = _redo_show(config2, ia, ledger2, entry2, stage)
        typer.echo(f"packaged: {pkg}" if pkg else f"needs-review, skipped: {entry.slug}")
    else:
        typer.echo(f"next: llama redo {entry.slug} --from {stage}")
```

(Note: `show` currently unpacks `config, _, ledger = _setup(...)`; change it to
`config, ia, ledger = _setup(...)` so `--apply` has an IA client, and drop the
re-`_setup` above — reuse `ia`/`ledger`/`config` and re-resolve `entry` after
the edits so the reloaded provenance/overrides are fresh.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k "show" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: show --exclude/--include/--vague/--full/--apply resolution flags"
```

---

### Task 8: `show` interactive resolve + set iteration

**Files:**
- Modify: `src/llama/cli.py` (the `show` command + helpers)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Produces: `_interactive_enabled() -> bool` (patchable; wraps
  `sys.stdin.isatty()`); `_pick_excludes(show) -> list[str]`;
  `_interactive_resolve(config, ia, ledger, entry) -> None`
- `show` accepts either a single `<slug>` (name optional now) OR selectors
  (`--held/--packaged/--voiced/--unvoiced/--state/--artist/--run`); the set form
  defaults to `--held`. Interactive resolve runs the chosen resolution inline.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_commands.py`:

```python
def test_show_interactive_vague_runs_resolution(tmp_path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "_interactive_enabled", lambda: True)

    # real held show via find
    runner.invoke(cli.app, ["find", "GD 1973", "--auto", "--script",
                            "--run-name", "r", "--config", cfg])
    ws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")
    s = read_model(ws.show, Show); s.needs_review = True; s.review_flags = ["x"]
    write_artifact(ws.show, s)

    r = runner.invoke(cli.app, ["show", "gratefuldead", "--config", cfg], input="v\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).narration == "vague"
    assert read_model(ws.show, Show).needs_review is False


def test_show_set_form_defaults_to_held(tmp_path, monkeypatch):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "_interactive_enabled", lambda: False)  # inspect-only
    build(tmp_path, "held-one", stages={"select", "gather"}, needs_review=True)
    build(tmp_path, "clean-one", stages={"select", "gather"}, needs_review=False)
    r = runner.invoke(cli.app, ["show", "--config", cfg])
    assert "held-one" in r.output and "clean-one" not in r.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -k "interactive or set_form" -q`
Expected: FAIL — `_interactive_enabled` missing / `name` required.

- [ ] **Step 3: Add the interactive helpers**

In `src/llama/cli.py`:

```python
def _interactive_enabled() -> bool:
    return sys.stdin.isatty()


def _pick_excludes(show) -> list[str]:
    typer.echo("tracks:")
    for t in show.tracks:
        typer.echo(f"  {t.index:2d}. {t.set:6s} {t.title:28.28s} {t.filename}")
    picks = _parse_ranks(typer.prompt("exclude which track numbers? (comma-separated, empty = none)",
                                      default="", show_default=False))
    return [t.filename for t in show.tracks if t.index in picks]


def _interactive_resolve(config, ia, ledger, entry) -> None:
    _print_show_entry(entry)  # see Step 4
    if entry.state != "held":
        return
    choice = typer.prompt("[e]xclude tracks / [v]ague / [c]lear / [s]kip / [q]uit",
                          default="s", show_default=False).strip().lower()
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
    elif choice == "v":
        _edit_overrides(entry.ws, narration="vague")
        _clear_hold(entry.ws)
        stage = "synthesize"
    elif choice == "c":
        _clear_hold(entry.ws)
        stage = "package"
    else:
        typer.echo("unrecognized; skipping")
        return
    fresh = _resolve_show(config, ledger, entry.slug)
    pkg = _redo_show(config, ia, ledger, fresh, stage)
    typer.echo(f"packaged: {pkg}" if pkg else f"still held: {entry.slug}")
```

- [ ] **Step 4: Extract the inspection printer and wire the set/single forms**

Extract the existing inspection output (identity, recording, state, overrides
line, stage table, needs-review flags) into a function:

```python
def _print_show_entry(entry) -> None:
    sws = entry.ws
    ...  # move the current body of `show` (from reading show.json through the
         # needs-review flag list) here, using `sws`/`entry`
```

Change the `show` signature: make `name` optional and add selectors:

```python
@app.command()
def show(
    name: str = typer.Argument(None, help="Show slug, unique substring, or path"),
    # ... the Task 7 action flags ...
    held: bool = typer.Option(False, "--held"),
    packaged: bool = typer.Option(False, "--packaged"),
    voiced: bool = typer.Option(False, "--voiced"),
    unvoiced: bool = typer.Option(False, "--unvoiced"),
    state: str = typer.Option(None, "--state"),
    artist: str = typer.Option(None, "--artist"),
    run: str = typer.Option(None, "--run"),
    config_path: Path = typer.Option(None, "--config"),
):
```

At the top of the body, branch on set vs single:

```python
    config, ia, ledger = _setup(config_path)
    if name is None:
        from llama.catalog import iter_shows, select_shows
        states = {s for s, on in [("held", held), ("packaged", packaged)] if on}
        if state:
            states.add(state)
        if not states and not (voiced or unvoiced or artist or run):
            states = {"held"}   # set form defaults to held
        vf = True if voiced else (False if unvoiced else None)
        entries = select_shows(iter_shows(config.root, ledger),
                               states=states or None, voiced=vf, artist=artist, run=run)
        if not entries:
            typer.echo("no matching shows")
            return
        for e in entries:
            if _interactive_enabled():
                _interactive_resolve(config, ia, ledger, e)
            else:
                _print_show_entry(e)
        return
    entry = _resolve_show(config, ledger, name)
    # ... Task 7 single-show handling, using _print_show_entry(entry) for output ...
```

For the single-show path with **no action flag**, after printing, add the
interactive offer:

```python
    if not (did_exclude or did_narration or clear):
        if entry.state == "held" and _interactive_enabled():
            _interactive_resolve(config, ia, ledger, entry)
        return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k "show" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: show interactive resolve + set-form walkthrough (default --held)"
```

---

### Task 9: Batch `redo` / `deliver` via selectors

**Files:**
- Modify: `src/llama/cli.py` (the `redo` and `deliver` commands)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `select_shows`, `_redo_show`, `iter_shows`
- Produces: `_batch_select(config, ledger, *, held, packaged, voiced, unvoiced,
  state, artist, run) -> list[CatalogEntry]` — resolves the set, **excluding
  held shows unless `held=True`**.
- `redo`/`deliver` accept selectors instead of a single `<show>`; exactly one of
  {positional, ≥1 selector} required. Batches print a plan and prompt
  `Proceed? [y/N]`; `--yes` skips.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_commands.py`:

```python
def test_redo_batch_unvoiced_plans_and_confirms(tmp_path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    runner.invoke(cli.app, ["find", "GD 1973", "--auto", "--script",
                            "--run-name", "r", "--config", cfg])

    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["redo", "--unvoiced", "--from", "package",
                                "--voice", "--config", cfg], input="y\n")
    assert r.exit_code == 0, r.output
    assert calls == ["gratefuldead-1973-06-10"]


def test_redo_batch_requires_target(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["redo", "--from", "package", "--config", cfg])
    assert r.exit_code != 0
    assert "a show or a selector" in r.output.lower()


def test_deliver_batch_excludes_held(tmp_path, monkeypatch):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\ndelivery_path = "{tmp_path}/out"\n')
    # one packaged, one held+packaged
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "synthesize", "package"},
          needs_review=True)
    delivered = []
    monkeypatch.setattr(cli, "_deliver_one", lambda cfg_, led_, e, dest, force: delivered.append(e.slug))
    r = runner.invoke(cli.app, ["deliver", "--packaged", "--yes", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert delivered == ["ready"]  # held excluded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -k "batch" -q`
Expected: FAIL — selectors unknown / behavior absent.

- [ ] **Step 3: Add the batch-select helper**

In `src/llama/cli.py`:

```python
def _batch_select(config, ledger, *, held=False, packaged=False, voiced=False,
                  unvoiced=False, state=None, artist=None, run=None):
    from llama.catalog import iter_shows, select_shows
    states = {s for s, on in [("held", held), ("packaged", packaged)] if on}
    if state:
        states.add(state)
    vf = True if voiced else (False if unvoiced else None)
    entries = select_shows(iter_shows(config.root, ledger),
                           states=states or None, voiced=vf, artist=artist, run=run)
    if not held:                         # never act on held shows implicitly
        entries = [e for e in entries if e.state != "held"]
    return entries


def _has_selector(held, packaged, voiced, unvoiced, state, artist, run) -> bool:
    return any([held, packaged, voiced, unvoiced, state, artist, run])


def _confirm_plan(entries, action: str, yes: bool) -> bool:
    typer.echo(f"{len(entries)} show(s) to {action}:")
    for e in entries:
        typer.echo(f"  {e.slug}")
    if yes:
        return True
    return typer.confirm("Proceed?", default=False)
```

- [ ] **Step 4: Wire selectors into `redo`**

Make `name` optional on `redo`, add the selector options + `--yes`, and branch:

```python
    if name is None:
        if not _has_selector(held, packaged, voiced, unvoiced, state, artist, run):
            typer.echo("give a show or a selector (e.g. --unvoiced)", err=True)
            raise typer.Exit(1)
        config, ia, ledger = _setup(config_path)
        entries = _batch_select(config, ledger, held=held, packaged=packaged,
                                voiced=voiced, unvoiced=unvoiced, state=state,
                                artist=artist, run=run)
        if not entries:
            typer.echo("no matching shows")
            return
        if not _confirm_plan(entries, f"redo --from {from_stage}", yes):
            return
        for e in entries:
            try:
                pkg = _redo_show(config, ia, ledger, e, from_stage,
                                 with_research=with_research, script=script, voice=voice)
                typer.echo(f"packaged: {pkg}" if pkg else f"needs-review, skipped: {e.slug}")
            except (LlamaError, TaskFailed, LLMError, IAError, SpeechError) as exc:
                typer.echo(f"FAILED {e.slug}: {exc}", err=True)
        return
    # ... existing single-show redo (Task 6 wrapper) ...
```

- [ ] **Step 5: Wire selectors into `deliver`**

Extract the current copy+ledger body into `_deliver_one(config, ledger, entry,
dest, force) -> None` (raising `LlamaError` on refusal instead of
`typer.Exit`), then branch `deliver` the same way as `redo`: single `name` calls
`_deliver_one`; `name is None` + selectors runs `_batch_select` (default
`packaged` when only `--yes`/no state given is fine — require an explicit
selector as with redo), plan+confirm, loop `_deliver_one` with per-show
try/except. Add `--yes` and the selector options to the signature.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k "batch or redo or deliver" -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: batch redo/deliver via selectors with plan+confirm (held excluded)"
```

---

### Task 10: `--help` ordered command panels

**Files:**
- Modify: `src/llama/cli.py` (custom group class + `rich_help_panel` labels)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `OrderedPanelGroup(typer.core.TyperGroup)` overriding
  `list_commands` to a fixed order; passed via `typer.Typer(cls=...)`.
- Every top-level command and sub-app declares a `rich_help_panel`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_help_orders_and_panels_commands():
    from typer.testing import CliRunner
    from llama import cli
    out = CliRunner().invoke(cli.app, ["--help"]).output
    # panels present
    for panel in ["Discover & process", "Inspect & triage", "Act on shows", "Housekeeping"]:
        assert panel in out
    # deliberate order: find before status before ledger
    assert out.index("find") < out.index("status") < out.index("ledger")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -k help_orders -q`
Expected: FAIL — panel titles absent / order not guaranteed.

- [ ] **Step 3: Add the ordered group class**

In `src/llama/cli.py`, near the top (after imports):

```python
from typer.core import TyperGroup

_COMMAND_ORDER = ["find", "artists", "run", "review", "profile",
                  "status", "runs", "show", "redo", "deliver",
                  "ledger", "config", "version"]


class OrderedPanelGroup(TyperGroup):
    def list_commands(self, ctx):
        cmds = super().list_commands(ctx)
        return sorted(cmds, key=lambda n: (_COMMAND_ORDER.index(n)
                                           if n in _COMMAND_ORDER else len(_COMMAND_ORDER)))
```

Change the app creation:

```python
app = typer.Typer(help="Live Music Archive -> radio station pipeline",
                  pretty_exceptions_enable=False, cls=OrderedPanelGroup)
```

- [ ] **Step 4: Label every command + sub-app**

Add `rich_help_panel=...` to each decorator/registration:

- `find`, `artists`, `run`, `review` → `rich_help_panel="Discover & process"`
- `status`, `runs`, `show` → `rich_help_panel="Inspect & triage"`
- `redo`, `deliver` → `rich_help_panel="Act on shows"`
- `version` → `rich_help_panel="Housekeeping"`
- sub-apps: `app.add_typer(profile_app, name="profile", rich_help_panel="Discover & process")`;
  `app.add_typer(ledger_app, name="ledger", rich_help_panel="Housekeeping")`;
  `app.add_typer(config_app, name="config", rich_help_panel="Housekeeping")`

(Example: `@app.command(rich_help_panel="Inspect & triage")` above `def status`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_cli.py -k help_orders -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli.py
git commit -m "feat: group and order --help commands into labeled panels"
```

---

### Task 11: Documentation

**Files:**
- Modify: `docs/workflow.md` (command reference + recipes + on-disk layout)
- Modify: `CLAUDE.md` (architecture: overrides.json)

**Interfaces:** none (docs only). No code.

- [ ] **Step 1: Update the on-disk layout**

In `docs/workflow.md`, in the `shows/<slug>/` tree (~line 69-90), add:

```
    ├── overrides.json          # hand-authored, durable: excluded tracks +
    │                           # narration mode; read by gather/synthesize,
    │                           # survives every redo
```

- [ ] **Step 2: Document the three resolutions**

In the "Clearing gate 2" section (~line 206-224), add a short table/paragraph
covering: **correct** (`show --exclude` → `redo --from gather`, self-clears),
**accept-as-vague** (`show --vague` → `redo --from synthesize`), **overrule**
(`show --clear` → `redo --from package`), and that `--apply` runs the redo
inline while the default prints it.

- [ ] **Step 3: Update the command reference**

Rewrite the `llama show` entry (~429) to document single vs set form, the
resolution flags (`--exclude/--include/--vague/--full/--apply`), the interactive
walkthrough (`llama show --held`), and the `overrides:` display. Update the
`llama status` entry to add `--voiced/--unvoiced/--state` and the annotations.
Update `llama redo`/`llama deliver` entries to document the selector-batch form
(`redo --unvoiced --from package --voice`, `deliver --packaged`), the plan/
confirm, `--yes`, and that held shows are excluded unless `--held`.

- [ ] **Step 4: Add recipes**

In "Recipes" (~514), add:
- "Clear my overnight holds": `llama show --held` (walkthrough).
- "Voice every packaged-but-silent show": `llama redo --unvoiced --from package --voice`.
- "This show has junk announcement tracks": `llama show <s> --exclude <file> --apply`.
- "This show's setlist is unknowable": `llama show <s> --vague --apply`.

- [ ] **Step 5: Update CLAUDE.md**

In the "Architecture" section, add one bullet: `overrides.json` is the durable
per-show operator input (excluded tracks + `narration=vague`) that gather and
synthesize honor; `show.json` stays purely derived; resolutions are
correct/accept-vague/overrule on `llama show`.

- [ ] **Step 6: Commit**

```bash
git add docs/workflow.md CLAUDE.md
git commit -m "docs: overrides.json, three resolutions, show/status/redo/deliver updates"
```

---

## Final verification

- [ ] Run the whole suite: `pytest -q`. Expected: all pass.
- [ ] Sanity-check help: `llama --help` shows four panels in the intended order.

## Self-review notes (author)

- **Spec coverage:** Part 1 → Tasks 1-3, 7; Part 2 → Tasks 4-5; Part 3
  (selectors/show-resolve/batch) → Tasks 4, 8, 9; Part 4 → Task 10; docs →
  Task 11. `_redo_show` extraction (Task 6) enables show `--apply`, interactive,
  and batch reuse.
- **Deviation from spec:** the spec said "labeled panels (Typer
  `rich_help_panel`)"; `rich` is not a declared dependency, but Typer 0.26's
  bundled rich rendering makes both the panels and a custom-ordered
  `TyperGroup` work with no new dependency (verified). Order is guaranteed by
  the group class even if panel rendering ever degrades.
- **Type consistency:** `Overrides(exclude, narration)`, `read_overrides`,
  `derive_voiced`, `select_shows(states=, voiced=, artist=, run=)`,
  `_redo_show(...)->Path|None`, `_edit_overrides`, `_clear_hold`,
  `_batch_select`, `_deliver_one` are used consistently across tasks.
