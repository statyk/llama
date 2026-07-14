# Research-First Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every package ships vetted research (`research.md` + `reviews.md`); the verbatim DJ script becomes opt-in (`--script` / profile `script`), guarded by a new low-tier `vet_research` grounding check.

**Architecture:** A ninth LLM touchpoint (`vet_research`, low tier) extracts what research.md *asserts* (songs performed at this show, performance dates, one context line); deterministic Python compares assertions against `show.json` and flags mismatches `needs-review`, halting before packaging. A new `vet` pipeline stage owns this, re-runnable without re-running research. Synthesize becomes conditional; Manifest bumps to schema v2 with optional `dj_notes` and artifact pointers.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, pytest. Spec: `docs/superpowers/specs/2026-07-14-research-first-packaging-design.md`.

## Global Constraints

- All tests run offline and deterministic (`pytest -q`); LLM calls only via `FakeProvider`.
- Stage outputs written only on success, via `write_artifact` (atomic temp+rename).
- Stages skip work when their artifact exists (`should_run(path, force)`).
- Review-flag pattern: append to `show.review_flags`, set `needs_review=True`, rewrite `show.json` — never raise.
- Never commit audio files.
- Prompt templates live in `src/llama/prompts/<task>.md` with `{{placeholder}}` substitution; every template has an entry in `tests/test_prompts.py::EXPECTED` and must be > 200 chars.
- Flag text is user-visible; match existing lowercase style (e.g. `"research asserts unknown song: X"`).

---

### Task 1: `ResearchVetting`/`VettingResult` models, `vet_research` prompt, tier registration

**Files:**
- Modify: `src/llama/models.py` (append after `DJNotes`, ~line 141)
- Create: `src/llama/prompts/vet_research.md`
- Modify: `src/llama/llm/__init__.py:8-17` (`DEFAULT_TIERS`)
- Modify: `src/llama/pipeline.py:19-21` (`TASK_KEYS`)
- Test: `tests/test_prompts.py`, `tests/test_model_tiers.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ResearchVetting(BaseModel)` with `asserted_songs: list[str]`, `asserted_dates: list[str]`, `context: str` (all defaulted); `VettingResult(BaseModel)` with `vetting: ResearchVetting`, `flags: list[str]`; prompt name `"vet_research"` with single placeholder `research`; `DEFAULT_TIERS["vet_research"] == "low"`; `"vet_research"` in `pipeline.TASK_KEYS`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_prompts.py`, add to the `EXPECTED` dict:

```python
    "vet_research": {"research"},
```

In `tests/test_model_tiers.py`, append:

```python
def test_vet_research_defaults_to_low_tier():
    from llama.llm import DEFAULT_TIERS

    assert DEFAULT_TIERS["vet_research"] == "low"
```

In `tests/test_prompts.py`, also append (the grounding check only works if the
prompt forbids extracting context mentions — the spec's "prompt-contract" item):

```python
def test_vet_research_prompt_excludes_context_mentions():
    text = load_prompt("vet_research")
    assert text.count("Exclude") >= 2  # once for songs, once for dates
    assert "AT THIS SHOW" in text
```

In `tests/test_models.py`, append:

```python
def test_research_vetting_defaults():
    from llama.models import ResearchVetting, VettingResult

    v = ResearchVetting()
    assert v.asserted_songs == [] and v.asserted_dates == [] and v.context == ""
    r = VettingResult(vetting=v)
    assert r.flags == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py tests/test_model_tiers.py tests/test_models.py -q`
Expected: FAIL — `vet_research` prompt file missing, `KeyError: 'vet_research'`, `ImportError: cannot import name 'ResearchVetting'`.

- [ ] **Step 3: Implement**

Append to `src/llama/models.py` directly after the `DJNotes` class:

```python
class ResearchVetting(BaseModel):
    """What research.md asserts about this show, extracted for grounding checks."""
    asserted_songs: list[str] = Field(default_factory=list)
    asserted_dates: list[str] = Field(default_factory=list)
    context: str = ""  # one-line era/tour context for the manifest


class VettingResult(BaseModel):
    vetting: ResearchVetting
    flags: list[str] = Field(default_factory=list)  # empty = research passed
```

Create `src/llama/prompts/vet_research.md`:

```markdown
You are auditing a research document written about one specific concert
performance. Extract exactly what the document asserts — do not add outside
knowledge, and do not correct the document. Faithful extraction only.

Research document:
{{research}}

Extract:
1. asserted_songs: every song title the document asserts was performed AT THIS
   SHOW. Exclude songs mentioned only as context — other nights, studio
   versions, tour statistics, comparisons to other performances.
2. asserted_dates: every date the document asserts THIS performance took place
   on, copied exactly as written. Exclude dates of other shows or events
   mentioned as tour/venue context.
3. context: one line placing the show in its era/tour, built only from the
   document's claims.

Respond with ONLY JSON in this shape:
{"asserted_songs": ["<title>", ...],
 "asserted_dates": ["<date exactly as written>", ...],
 "context": "<one line>"}
Raw JSON only.
```

In `src/llama/llm/__init__.py`, add to `DEFAULT_TIERS` after the `"synthesize"` entry:

```python
    "vet_research": "low",
```

In `src/llama/pipeline.py`, extend `TASK_KEYS`:

```python
TASK_KEYS = ["interpret", "score_reviews", "light_research",
             "extract_setlist", "deep_research", "synthesize", "propose_artists",
             "align_structure", "vet_research"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prompts.py tests/test_model_tiers.py tests/test_models.py tests/test_pipeline.py::test_make_providers_includes_align_structure -q`
Expected: PASS.

- [ ] **Step 5: Full suite, then commit**

Run: `pytest -q` — expected all pass (nothing consumes the new pieces yet).

```bash
git add src/llama/models.py src/llama/prompts/vet_research.md src/llama/llm/__init__.py src/llama/pipeline.py tests/test_prompts.py tests/test_model_tiers.py tests/test_models.py
git commit -m "feat: vet_research touchpoint (models, prompt, low-tier default)"
```

---

### Task 2: Move the reviews digest to `util.py`

**Files:**
- Modify: `src/llama/util.py` (append), `src/llama/stages/synthesize.py:46-52,71`
- Test: `tests/test_util.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `util.reviews_digest(reviews: list[dict], limit: int = 5) -> str` — identical behavior to the current private `stages/synthesize.py::_reviews_digest` (top `limit` reviews, body capped at 800 chars, `"(no reviews)"` when empty). Task 4's package stage and synthesize both call it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_util.py`:

```python
def test_reviews_digest_formats_caps_and_handles_empty():
    from llama.util import reviews_digest

    reviews = [{"reviewtitle": "Wow", "reviewbody": "x" * 900},
               {"reviewbody": "no title here"}]
    out = reviews_digest(reviews)
    lines = out.splitlines()
    assert lines[0].startswith("- Wow: ") and len(lines[0]) <= 800 + len("- Wow: ")
    assert lines[1] == "- no title here"
    assert reviews_digest([]) == "(no reviews)"
    assert len(reviews_digest([{"reviewbody": str(i)} for i in range(9)]).splitlines()) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_util.py -q`
Expected: FAIL — `ImportError: cannot import name 'reviews_digest'`.

- [ ] **Step 3: Move the function**

Append to `src/llama/util.py`:

```python
def reviews_digest(reviews: list[dict], limit: int = 5) -> str:
    """Trimmed listener-review digest: what synthesize consumes and packages ship."""
    parts = []
    for r in reviews[:limit]:
        title = str(r.get("reviewtitle") or "").strip()
        body = str(r.get("reviewbody") or "").strip()[:800]
        parts.append(f"- {title}: {body}" if title else f"- {body}")
    return "\n".join(parts) or "(no reviews)"
```

In `src/llama/stages/synthesize.py`: delete `_reviews_digest` (lines 46-52), add `from llama.util import reviews_digest` to the imports, and change the call in `run_synthesize` to `reviews_digest=reviews_digest(reviews),`.

Run `grep -rn "_reviews_digest" src tests` — expected: no hits remain.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_util.py tests/test_stage_synthesize.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/util.py src/llama/stages/synthesize.py tests/test_util.py
git commit -m "refactor: shared reviews_digest in util"
```

---

### Task 3: `vet` stage — extraction call + deterministic grounding check

**Files:**
- Modify: `src/llama/workspace.py:42-51` (`ShowWorkspace`)
- Create: `src/llama/stages/vet_research.py`
- Test: `tests/test_stage_vet.py` (new)

**Interfaces:**
- Consumes: `ResearchVetting`, `VettingResult` (Task 1); `run_json_task`, `normalize_song`, `should_run`/`read_model`/`write_artifact`.
- Produces: `ShowWorkspace.vetting` (`dir / "vetting.json"`); `run_vet_research(show_ws, provider, show: Show, research_md: str, force: bool = False) -> VettingResult`; helpers `grounding_flags(vetting: ResearchVetting, show: Show) -> list[str]` and `normalize_date(text: str) -> str | None`. Flag strings: `research asserts unknown song: <t>`, `research asserts wrong date: <d>`, `research asserts unparseable date: <d>`. On any flag, `show.json` is rewritten with `needs_review=True` (append to `review_flags`). Always writes `vetting.json` (the `VettingResult`), pass or fail.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stage_vet.py`:

```python
import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Show, Track
from llama.stages.vet_research import normalize_date, run_vet_research
from llama.workspace import ShowWorkspace, write_artifact


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[
            Track(index=1, set="1", title="Morning Dew", filename="a.mp3", title_source="tags"),
            Track(index=2, set="2", title="Dark Star", filename="b.mp3", title_source="tags"),
            Track(index=3, set="encore", title="Johnny B. Goode", filename="c.mp3", title_source="tags"),
        ],
        set_breaks=[1, 2],
    )


def vet_json(**overrides):
    d = {"asserted_songs": ["Morning Dew", "Dark Star"],
         "asserted_dates": ["1973-06-10", "June 10, 1973"],
         "context": "Peak 1973 tour"}
    d.update(overrides)
    return json.dumps(d)


def setup(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    return sws, show


def test_normalize_date_common_forms():
    assert normalize_date("1973-06-10") == "1973-06-10"
    assert normalize_date("1973-6-1") == "1973-06-01"
    assert normalize_date("6/10/73") == "1973-06-10"
    assert normalize_date("06/10/1973") == "1973-06-10"
    assert normalize_date("June 10, 1973") == "1973-06-10"
    assert normalize_date("Jun. 10th, 73") == "1973-06-10"
    assert normalize_date("10 June 1973") == "1973-06-10"
    assert normalize_date("the summer of '73") is None


def test_clean_research_passes_and_writes_vetting(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json()])
    result = run_vet_research(sws, fake, show, "## Reputation\nLegendary.")
    assert result.flags == []
    assert result.vetting.context == "Peak 1973 tour"
    assert sws.vetting.exists()
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_alias_matching_uses_normalize_song(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_songs=["JBG", "Morning Dew!"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_unknown_song_flags_needs_review(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_songs=["Werewolves of London"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts unknown song: Werewolves of London"]
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert saved["review_flags"] == result.flags


def test_wrong_and_unparseable_dates_flag(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_dates=["1977-05-08", "that legendary night"])])
    result = run_vet_research(sws, fake, show, "r")
    assert "research asserts wrong date: 1977-05-08" in result.flags
    assert "research asserts unparseable date: that legendary night" in result.flags


def test_skips_when_vetting_exists(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "r")
    cached = run_vet_research(sws, FakeProvider(), show, "r")  # empty queue: any call would raise
    assert cached.vetting.context == "Peak 1973 tour"


def test_revet_after_artifact_delete_leaves_research_alone(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_artifact(sws.research, "original research")
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "original research")
    sws.vetting.unlink()
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "original research")
    assert sws.research.read_text() == "original research"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_vet.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.stages.vet_research'`.

- [ ] **Step 3: Implement**

In `src/llama/workspace.py`, add to `ShowWorkspace.__init__` after the `self.research` line:

```python
        self.vetting = dir / "vetting.json"
```

Create `src/llama/stages/vet_research.py`:

```python
import re

from llama.llm.tasks import run_json_task
from llama.models import ResearchVetting, Show, VettingResult
from llama.songs import normalize_song
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def _month(name: str) -> int | None:
    if name in _MONTHS:
        return _MONTHS[name]
    if len(name) >= 3:
        hits = [i for full, i in _MONTHS.items() if full.startswith(name)]
        if len(hits) == 1:
            return hits[0]
    return None


def _year(y: int) -> int:
    """Two-digit years: LMA coverage is overwhelmingly 20th-century."""
    if y >= 100:
        return y
    return 1900 + y if y >= 30 else 2000 + y


def normalize_date(text: str) -> str | None:
    """Normalize common prose date spellings to YYYY-MM-DD; None if unparseable."""
    s = re.sub(r"\s+", " ", text.strip().lower().replace(",", " ").replace(".", " ")).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        return f"{_year(int(m[3])):04d}-{int(m[1]):02d}-{int(m[2]):02d}"
    m = re.fullmatch(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)? '?(\d{2,4})", s)
    if m and _month(m[1]):
        return f"{_year(int(m[3])):04d}-{_month(m[1]):02d}-{int(m[2]):02d}"
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]+) '?(\d{2,4})", s)
    if m and _month(m[2]):
        return f"{_year(int(m[3])):04d}-{_month(m[2]):02d}-{int(m[1]):02d}"
    return None


def grounding_flags(vetting: ResearchVetting, show: Show) -> list[str]:
    """Deterministic check: research assertions must match this show. Zero tokens."""
    flags: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in vetting.asserted_songs:
        if normalize_song(song) not in known:
            flags.append(f"research asserts unknown song: {song}")
    for date_text in vetting.asserted_dates:
        norm = normalize_date(date_text)
        if norm is None:
            flags.append(f"research asserts unparseable date: {date_text}")
        elif norm != show.date:
            flags.append(f"research asserts wrong date: {date_text}")
    return flags


def run_vet_research(
    show_ws: ShowWorkspace, provider, show: Show, research_md: str, force: bool = False,
) -> VettingResult:
    if not should_run(show_ws.vetting, force):
        return read_model(show_ws.vetting, VettingResult)
    vetting = run_json_task(provider, "vet_research", ResearchVetting, research=research_md)
    flags = grounding_flags(vetting, show)
    if flags:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + flags
        current.needs_review = True
        write_artifact(show_ws.show, current)
    result = VettingResult(vetting=vetting, flags=flags)
    write_artifact(show_ws.vetting, result)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stage_vet.py tests/test_workspace.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/workspace.py src/llama/stages/vet_research.py tests/test_stage_vet.py
git commit -m "feat: vet stage - research grounding check against show.json"
```

---

### Task 4: Manifest v2 + package ships research and reviews, script optional

**Files:**
- Modify: `src/llama/models.py:152-165` (`SetBreak`, `Manifest`)
- Modify: `src/llama/manifest.py:6-21` (`build_manifest`)
- Modify: `src/llama/stages/package.py`
- Test: `tests/test_stage_package.py`, `tests/test_manifest.py`

**Interfaces:**
- Consumes: `VettingResult` (Task 1, read from `show_ws.vetting`), `util.reviews_digest` (Task 2).
- Produces: `Manifest` with `schema_version: int = 2`, `dj_notes: DJNotes | None = None`, `research: str | None = None`, `reviews: str | None = None`, `research_vetted: bool = False`; `SetBreak.note_index: int | None = None`. `build_manifest(show, notes, packaged, context="", research=None, reviews=None, research_vetted=False) -> Manifest` (notes may be `None`; `note_index` populated only when notes given). `run_package(show_ws, ia, show, notes=None, force=False) -> Path` — copies `research.md` when present, always writes `reviews.md`, copies `dj-notes.md` only when it exists, sources `manifest.show.context` from vetting (fallback: `notes.context`, else `""`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_stage_package.py`, append:

```python
from llama.models import ResearchVetting, VettingResult


def write_vetting(sws, context="Peak 1973, RFK", flags=None):
    write_artifact(sws.vetting, VettingResult(
        vetting=ResearchVetting(context=context), flags=flags or []))


def test_package_ships_research_reviews_and_vetting_context(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_artifact(sws.research, "## Reputation\nLegendary.")
    write_artifact(sws.reviews, [{"reviewtitle": "Wow", "reviewbody": "great tape"}])
    write_vetting(sws)
    pkg = run_package(sws, StubIA(), show, make_notes())
    assert (pkg / "research.md").read_text() == "## Reputation\nLegendary."
    assert (pkg / "reviews.md").read_text() == "- Wow: great tape"
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["schema_version"] == 2
    assert m["research"] == "research.md" and m["reviews"] == "reviews.md"
    assert m["research_vetted"] is True
    assert m["show"]["context"] == "Peak 1973, RFK"  # vetting wins over notes.context


def test_package_without_script(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)  # no dj-notes.md written
    write_artifact(sws.research, "r")
    write_vetting(sws)
    pkg = run_package(sws, StubIA(), show, notes=None)
    assert not (pkg / "dj-notes.md").exists()
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_notes"] is None
    assert m["set_breaks"] == [{"after_track": 1, "note_index": None}]
    assert (pkg / "reviews.md").read_text() == "(no reviews)"


def test_package_without_vetting_falls_back_to_notes_context(tmp_path: Path):
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show, make_notes())
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["show"]["context"] == make_notes().context
    assert m["research"] is None and m["research_vetted"] is False
```

Also update `make_notes()` in this file so the fallback assertion is meaningful:

```python
def make_notes():
    return DJNotes(context="from the notes", intro="i", outro="o",
                   set_intros={"1": "a", "2": "b"}, set_break_notes=["x"])
```

In `tests/test_manifest.py`, append:

```python
def test_build_manifest_without_notes():
    from llama.manifest import build_manifest
    from llama.models import ManifestTrack, Show, Track

    show = Show(performance_id="p", identifier="i", artist="a", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="t", filename="f.mp3", title_source="tags")],
                set_breaks=[1])
    packaged = [ManifestTrack(index=1, set="1", title="t", filename="01 - t.mp3", duration_sec=60.0)]
    m = build_manifest(show, None, packaged, context="ctx", research="research.md",
                       reviews="reviews.md", research_vetted=True)
    assert m.schema_version == 2
    assert m.dj_notes is None
    assert m.set_breaks[0].note_index is None
    assert m.show["context"] == "ctx"
    assert m.research == "research.md" and m.research_vetted is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_package.py tests/test_manifest.py -q`
Expected: FAIL — `build_manifest` rejects the new keyword arguments; `Manifest` requires `dj_notes`.

- [ ] **Step 3: Implement**

In `src/llama/models.py`, replace `SetBreak` and `Manifest`:

```python
class SetBreak(BaseModel):
    after_track: int
    note_index: int | None = None  # index into dj_notes.set_break_notes when a script exists


class Manifest(BaseModel):
    schema_version: int = 2
    show: dict
    source: dict
    tracks: list[ManifestTrack]
    set_breaks: list[SetBreak]
    dj_notes: DJNotes | None = None
    research: str | None = None  # relative path within the package
    reviews: str | None = None
    research_vetted: bool = False
    total_duration_sec: float
    set_durations_sec: dict[str, float]
```

In `src/llama/manifest.py`, replace `build_manifest`:

```python
def build_manifest(
    show: Show,
    notes: DJNotes | None,
    packaged: list[ManifestTrack],
    context: str = "",
    research: str | None = None,
    reviews: str | None = None,
    research_vetted: bool = False,
) -> Manifest:
    per_set: dict[str, float] = defaultdict(float)
    for t in packaged:
        per_set[t.set] += t.duration_sec or 0.0
    return Manifest(
        show={"artist": show.artist, "date": show.date, "venue": show.venue,
              "city": show.city, "context": context},
        source={"performance_id": show.performance_id, "identifier": show.identifier,
                "url": show.source_url, "lineage": show.lineage},
        tracks=packaged,
        set_breaks=[SetBreak(after_track=idx, note_index=i if notes is not None else None)
                    for i, idx in enumerate(show.set_breaks)],
        dj_notes=notes,
        research=research,
        reviews=reviews,
        research_vetted=research_vetted,
        total_duration_sec=sum(t.duration_sec or 0.0 for t in packaged),
        set_durations_sec=dict(per_set),
    )
```

In `src/llama/stages/package.py`: change the signature to
`def run_package(show_ws: ShowWorkspace, ia, show: Show, notes: DJNotes | None = None, force: bool = False) -> Path:`,
add imports `from llama.models import VettingResult`, `from llama.util import reviews_digest`, `from llama.workspace import read_json`, and replace the manifest-writing block (currently `write_artifact(manifest_path, build_manifest(show, notes, packaged))` and the dj-notes copy) with:

```python
    context = notes.context if notes is not None else ""
    vetted = False
    if show_ws.vetting.exists():
        vr = read_model(show_ws.vetting, VettingResult)
        if vr.vetting.context:
            context = vr.vetting.context
        vetted = not vr.flags

    research_name = None
    if show_ws.research.exists():
        write_artifact(pkg / "research.md", show_ws.research.read_text())
        research_name = "research.md"
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    write_artifact(pkg / "reviews.md", reviews_digest(reviews))

    write_artifact(manifest_path, build_manifest(
        show, notes, packaged, context=context,
        research=research_name, reviews="reviews.md", research_vetted=vetted))
    write_artifact(pkg / "playlist.m3u", m3u_text([t.filename for t in packaged]))
    if show_ws.dj_notes_md.exists():
        write_artifact(pkg / "dj-notes.md", show_ws.dj_notes_md.read_text())
```

(The duration-flag block below stays unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stage_package.py tests/test_manifest.py -q`
Expected: PASS. Then `pytest -q` — `tests/test_pipeline.py` must still pass (its manifest assertions don't touch the new keys; synthesize still runs unconditionally until Task 6).

- [ ] **Step 5: Commit**

```bash
git add src/llama/models.py src/llama/manifest.py src/llama/stages/package.py tests/test_stage_package.py tests/test_manifest.py
git commit -m "feat: manifest v2 - optional dj_notes, packaged research + reviews digest"
```

---

### Task 5: `Profile.script` field

**Files:**
- Modify: `src/llama/profiles.py:10-14`
- Test: `tests/test_profiles.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Profile.script: bool = False`, surviving the TOML round-trip. Task 6's `profile_run` reads it.

- [ ] **Step 1: Write the failing test**

In `tests/test_profiles.py::test_profile_toml_roundtrip_with_none_fields`, change the `Profile(...)` construction to include `script=True` and add to the final assertions:

```python
    assert loaded.script is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profiles.py -q`
Expected: FAIL — `Profile` has no field `script`.

- [ ] **Step 3: Implement**

In `src/llama/profiles.py`, add to `Profile` after `human_gate`:

```python
    script: bool = False  # also generate the verbatim DJ script (extra high-tier call)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profiles.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/profiles.py tests/test_profiles.py
git commit -m "feat: profile-level script toggle"
```

---

### Task 6: Wire vet + optional script through pipeline and CLI

**Files:**
- Modify: `src/llama/pipeline.py:38-87` (`process_show`)
- Modify: `src/llama/cli.py:23` (`VALID_STAGES`), `:60-67` (`_show_stage_artifacts`), `:77-135` (`_execute`), `find`, `run`, `profile_add`, `profile_run`
- Test: `tests/test_pipeline.py`, `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `run_vet_research` (Task 3), `run_package(..., notes=None, ...)` (Task 4), `Profile.script` (Task 5), `providers["vet_research"]` (Task 1).
- Produces: `process_show(..., script: bool = False)` — vets after research, halts on vet flags before any synthesize/packaging, calls synthesize only when `script=True`; `_execute(..., script: bool = False)`; `--script/--no-script` (default off) on `llama find` and `llama run`; `--script` on `llama profile add`; `llama run --stage synthesize` implies `script=True`; `"vet"` in `VALID_STAGES` with artifact `show_ws.vetting`.

- [ ] **Step 1: Update pipeline tests (failing first)**

In `tests/test_pipeline.py`:

Add after the `NOTES` constant:

```python
VET = json.dumps({
    "asserted_songs": ["Morning Dew", "Dark Star"],
    "asserted_dates": ["1973-06-10"],
    "context": "Peak 1973, RFK Stadium",
})
```

Add to the dict in `fake_providers`:

```python
        "vet_research": FakeProvider(completes=[VET]),
```

Add `"--script",` to the `runner.invoke` argument lists of `test_find_end_to_end`, `test_show_failure_is_isolated_and_raw_output_saved`, and `test_needs_review_show_is_skipped_and_not_recorded` (all three exercise synthesize). In `test_find_end_to_end`, add assertions after the existing dj-notes check:

```python
    assert (pkg / "research.md").exists()
    assert (pkg / "reviews.md").exists()
    assert manifest["schema_version"] == 2
    assert manifest["show"]["context"] == "Peak 1973, RFK Stadium"
```

Append two new tests:

```python
def test_find_default_skips_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["synthesize"] = FakeProvider()  # any call would raise: queue is empty
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--run-name", "noscript",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "runs" / "noscript" / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is None
    assert manifest["research"] == "research.md"
    assert manifest["set_breaks"][0]["note_index"] is None
    assert manifest["show"]["context"] == "Peak 1973, RFK Stadium"
    assert (pkg / "research.md").exists() and (pkg / "reviews.md").exists()
    assert not (pkg / "dj-notes.md").exists()


def test_vet_failure_skips_show_before_packaging(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["vet_research"] = FakeProvider(completes=[json.dumps({
        "asserted_songs": ["Werewolves of London"], "asserted_dates": [], "context": "",
    })])
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--run-name", "badresearch",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "needs-review" in result.output
    show_dir = tmp_path / "runs" / "badresearch" / "shows" / "gratefuldead-1973-06-10"
    saved = json.loads((show_dir / "show.json").read_text())
    assert any("unknown song" in f for f in saved["review_flags"])
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()
```

In `tests/test_cli_commands.py`, append (add `ShowWorkspace` to its existing
`llama.workspace` import; `test_run_unknown_stage_exits_with_message` is the
only other stage-related test there and needs no change):

```python
def test_stage_vet_is_valid_and_maps_to_vetting_artifact(tmp_path: Path):
    assert "vet" in cli.VALID_STAGES
    sws = ShowWorkspace(tmp_path / "s")
    assert cli._show_stage_artifacts(sws, "vet") == [sws.vetting]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py tests/test_cli_commands.py -q`
Expected: FAIL — `find` has no `--script` option; default run still calls synthesize (FakeProvider raises "no queued complete responses left").

- [ ] **Step 3: Implement pipeline change**

In `src/llama/pipeline.py`: add `from llama.stages.vet_research import run_vet_research` to imports; add `script: bool = False,` to `process_show`'s keyword parameters (after `force`); replace the block from the research step through the packaging step with:

```python
    with step(f"[{pid}] researching"):
        research_md = run_research(show_ws, providers["deep_research"], show, dossier, force=force)
    with step(f"[{pid}] vetting research"):
        run_vet_research(show_ws, providers["vet_research"], show, research_md, force=force)
    show = read_model(show_ws.show, Show)  # vet may have flagged it
    if show.needs_review:
        log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(show.review_flags))
        return None
    notes = None
    if script:
        reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
        with step(f"[{pid}] synthesizing"):
            notes = run_synthesize(show_ws, providers["synthesize"], show, research_md, reviews, force=force)
        show = read_model(show_ws.show, Show)  # synthesize may have flagged it
        if show.needs_review:
            log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(show.review_flags))
            return None
    with step(f"[{pid}] packaging"):
        pkg = run_package(show_ws, ia, show, notes, force=force)
```

(Everything after — the post-package flag check and ledger record — stays unchanged.)

- [ ] **Step 4: Implement CLI changes**

In `src/llama/cli.py`:

```python
VALID_STAGES = {"search", "winnow", "select", "gather", "research", "vet", "synthesize", "package"}
```

In `_show_stage_artifacts`, add after the `"research"` entry:

```python
        "vet": [show_ws.vetting],
```

`_execute`: add parameter `script: bool = False` (after `human_gate`) and pass `script=script` in the `process_show(...)` call.

`find`: add option and pass-through:

```python
    script: bool = typer.Option(False, "--script/--no-script",
                                help="Also generate the verbatim DJ script (extra high-tier LLM call)"),
```

and call `_execute(config, ia, ledger, ws, criteria, count, auto, human_gate=False, script=script)`.

`run`: add the same `script` option; final call becomes:

```python
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=force and stage is None,
             script=script or stage == "synthesize")
```

`profile_add`: add `script: bool = typer.Option(False, "--script")` and pass `script=script` to the `Profile(...)` construction.

`profile_run`: pass `script=profile.script` in its `_execute(...)` call.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py tests/test_cli_commands.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/llama/pipeline.py src/llama/cli.py tests/test_pipeline.py tests/test_cli_commands.py
git commit -m "feat: vet stage in pipeline; DJ script generation now opt-in (--script)"
```

---

### Task 7: Docs — package contract v2 and updated project summary

**Files:**
- Modify: `README.md` (append section; adjust any pipeline/stage list it already contains to include `vet`)
- Modify: `CLAUDE.md` (three edits below)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–6.
- Produces: documentation only; no code.

- [ ] **Step 1: Add the package-format section to README.md**

Append (or merge into an existing packaging section if one exists):

```markdown
## Package format (v2)

A delivered show package contains:

- `audio/` — verified, tagged tracks (`01 - Morning Dew.mp3`, ...)
- `playlist.m3u`
- `manifest.json` — `schema_version: 2`; tracks, set breaks, durations,
  source lineage, `show.context`, pointers `research` / `reviews`, and
  `research_vetted`
- `research.md` — web-researched show notes, grounding-checked against the
  setlist (`vet` stage) before packaging
- `reviews.md` — trimmed listener-review digest (top 5, 800 chars each)
- `dj-notes.md` + `manifest.dj_notes` — verbatim DJ script, present only when
  the run generated one (`--script`, or `script = true` on a profile)

### Downstream synthesis contract

If your DJ (human or LLM) writes its own spoken copy from this package, it
inherits the factual guard this pipeline applies to its own scripts:

- every song mentioned must match a track title in `manifest.tracks`
- set intros must cover exactly the sets present in `manifest.tracks[].set`
- one break note per entry in `manifest.set_breaks`

Copy that names songs or sets not in the manifest must not air.
```

- [ ] **Step 2: Update CLAUDE.md**

Three edits in the existing text:

1. In **What this is**, change `emits a self-contained "show package" (verified audio, m3u, manifest with track titles/set breaks, LLM-written DJ notes)` to `emits a self-contained "show package" (verified audio, m3u, manifest v2 with track titles/set breaks, vetted research + reviews digest; verbatim DJ script opt-in via --script or profile script)`.
2. Same section, change `medium by default, high for deep_research/synthesize` to `medium by default, high for deep_research/synthesize, low for vet_research`.
3. In **Architecture**, change `interpret → search (wide net) → winnow (quality gate + optional human gate) → select-recording → gather → research → synthesize → package` to `... → gather → research → vet (grounding check) → synthesize (opt-in) → package`, and `Eight named touchpoints` to `Nine named touchpoints`. In **Quality philosophy**, extend the suspicious-output list with `research asserting songs or dates that don't belong to the show`.

- [ ] **Step 3: Verify and commit**

Run: `pytest -q` — expected: all pass (docs only).

```bash
git add README.md CLAUDE.md
git commit -m "docs: package format v2, downstream synthesis contract, vet stage"
```
