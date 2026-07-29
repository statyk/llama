# Briefing + Manifest v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the default-on `brief` pipeline stage (neutral, vetted briefing: `briefing.json` + `briefing.md`) between vet and synthesize, and bump the show-package contract to manifest v3 with a required `briefing` block.

**Architecture:** A new `stages/brief.py` mirrors the synthesize stage's shape (LLM task + deterministic render + factual guard + retry-once-then-hold) but is always neutral and always runs. The package stage copies the briefing into `package/` and the manifest gains a required `briefing` block. The existing synthesize/voice path is **byte-for-byte untouched** — `stages/synthesize.py` must show no diff at the end of this plan. Spec: `docs/superpowers/specs/2026-07-29-briefing-manifest-v3-design.md`.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest, herder (`run_json_task`). No new dependencies.

## Global Constraints

- **No new third-party dependencies.**
- **`packages/llama/src/llama/stages/synthesize.py` is never modified** (brief.py may *import* from it).
- TTS, presenters, `broadcast_readiness`, `deliver_refusals`, and the deliver gate are not modified.
- Full suite green after every task: `pytest -q` from the repo root (1036+ tests, offline).
- Commit after every task; messages follow the repo's `feat:`/`refactor:`/`docs:` convention.
- The brief stage is default-on: no flag, no config gate.
- All tests below go in `packages/llama/tests/`; run commands assume the repo root with `.venv` active (`source .venv/bin/activate`).

---

### Task 1: `Briefing` model + deterministic markdown render

**Files:**
- Modify: `packages/llama/src/llama/models.py` (add `Briefing` after `DJNotes`, ~line 211)
- Create: `packages/llama/src/llama/stages/brief.py`
- Test: `packages/llama/tests/test_stage_brief.py` (new file)

**Interfaces:**
- Consumes: `llama.models.Show`, `llama.stages.synthesize._set_label`.
- Produces: `Briefing` (pydantic model, exact fields below) and
  `render_briefing_md(briefing: Briefing, show: Show) -> str` — Tasks 3–5 rely on both names.

- [ ] **Step 1: Write the failing tests**

Create `packages/llama/tests/test_stage_brief.py`:

```python
from llama.models import Briefing, Show, Track
from llama.stages.brief import render_briefing_md


def _show(sets=("1", "2"), encore=True) -> Show:
    tracks, idx = [], 1
    for s in sets:
        tracks.append(Track(index=idx, set=s, title=f"Song {idx}", filename=f"t{idx}.mp3",
                            title_source="tags"))
        idx += 1
    if encore:
        tracks.append(Track(index=idx, set="encore", title=f"Song {idx}",
                            filename=f"t{idx}.mp3", title_source="tags"))
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73",
                artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
                tracks=tracks)


def _briefing(**kw) -> Briefing:
    base = dict(context="Peak-era Dead on the summer '73 run.",
                significance="A standout show from a strong year.",
                per_set={"1": ["Opens hot"], "2": ["The big jam"]},
                notable_moments=["A monster Dark Star"],
                review_sentiment="Widely praised, including by non-attendees.",
                non_attendee_sentiment=True,
                cautions=["research is thin"],
                mentioned_songs=[])
    base.update(kw)
    return Briefing(**base)


def test_briefing_defaults():
    b = _briefing()
    assert b.narration == "full"
    assert b.mentioned_songs == []


def test_render_briefing_md_sections_and_determinism():
    b, show = _briefing(), _show()
    md = render_briefing_md(b, show)
    assert md == render_briefing_md(b, show)  # pure function
    assert md.startswith("# Briefing: Grateful Dead — 1973-06-10, RFK Stadium")
    for heading in ["## Context", "## Why this show", "## Set 1", "## Set 2",
                    "## Notable moments", "## Reception",
                    "## Cautions for the scriptwriter"]:
        assert heading in md
    assert "- Opens hot" in md and "- research is thin" in md
    # Set sections follow show order; encore label renders as "Encore"
    b2 = _briefing(per_set={"1": ["a"], "encore": ["short sweet closer"]})
    md2 = render_briefing_md(b2, _show())
    assert "## Encore" in md2
    assert md2.index("## Set 1") < md2.index("## Encore")


def test_render_briefing_md_omits_empty_optional_sections():
    b = _briefing(notable_moments=[], cautions=[], per_set={})
    md = render_briefing_md(b, _show())
    assert "## Notable moments" not in md
    assert "## Cautions" not in md
    assert "## Set" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_stage_brief.py -q`
Expected: FAIL — `ImportError: cannot import name 'Briefing'`.

- [ ] **Step 3: Add the `Briefing` model**

In `packages/llama/src/llama/models.py`, directly after the `DJNotes` class (~line 211):

```python
class Briefing(BaseModel):
    """Neutral, vetted show briefing — the scriptwriter-facing text deliverable
    (spec: 2026-07-29-briefing-manifest-v3-design.md). Always house-neutral;
    persona styling is a downstream concern. `narration` is stamped from
    overrides.json after generation, never trusted from the LLM."""
    context: str                     # era/tour/venue context prose
    significance: str                # why this show is worth airing
    per_set: dict[str, list[str]] = Field(default_factory=dict)  # set label -> talking points
    notable_moments: list[str] = Field(default_factory=list)
    review_sentiment: str = ""
    non_attendee_sentiment: bool = False  # True iff sentiment includes non-attendee voices
    cautions: list[str] = Field(default_factory=list)
    narration: str = "full"          # "full" | "vague" (stamped, see above)
    mentioned_songs: list[str] = Field(default_factory=list)
```

(`narration` is a plain `str` like `Overrides.narration` at `models.py:198` — follow that precedent, not `Literal`.)

- [ ] **Step 4: Create `stages/brief.py` with the render**

Create `packages/llama/src/llama/stages/brief.py`:

```python
from llama.models import Briefing, Show
from llama.stages.synthesize import _set_label


def render_briefing_md(briefing: Briefing, show: Show) -> str:
    """Deterministic markdown render of the briefing model: briefing.md is a
    pure function of briefing.json, so the two artifacts can never disagree."""
    lines = [f"# Briefing: {show.artist} — {show.date}, {show.venue or 'venue unknown'}", ""]
    lines += ["## Context", briefing.context, ""]
    lines += ["## Why this show", briefing.significance, ""]
    for s in sorted(briefing.per_set, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)}", *[f"- {p}" for p in briefing.per_set[s]], ""]
    if briefing.notable_moments:
        lines += ["## Notable moments", *[f"- {m}" for m in briefing.notable_moments], ""]
    lines += ["## Reception", briefing.review_sentiment, ""]
    if briefing.cautions:
        lines += ["## Cautions for the scriptwriter", *[f"- {c}" for c in briefing.cautions], ""]
    return "\n".join(lines)
```

- [ ] **Step 5: Run the new tests, then the full suite**

Run: `pytest packages/llama/tests/test_stage_brief.py -q` → all pass.
Run: `pytest -q` → 1036 + 3 passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/models.py packages/llama/src/llama/stages/brief.py packages/llama/tests/test_stage_brief.py
git commit -m "feat: Briefing model + deterministic briefing.md render"
```

---

### Task 2: `briefing_guard`

**Files:**
- Modify: `packages/llama/src/llama/stages/brief.py`
- Test: `packages/llama/tests/test_stage_brief.py`

**Interfaces:**
- Consumes: `Briefing`, `Show`, `llama.songs.normalize_song`, and the module-scope
  claim regexes from `stages/synthesize.py` (`_SET_COUNT_CLAIM`, `_ORDINAL_SET`,
  `_COUNT_WORDS`, `_ORDINALS` — **imported**, so both guards share one
  implementation without touching synthesize.py).
- Produces: `briefing_guard(briefing: Briefing, show: Show) -> list[str]` (Task 3
  consumes it). Flag strings start with `"briefing "` (they land in
  `show.review_flags`, where the `dj notes ...` strings from `factual_guard` are
  the established precedent).

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_stage_brief.py`:

```python
from llama.stages.brief import briefing_guard


def test_guard_passes_clean_full_briefing():
    assert briefing_guard(_briefing(), _show()) == []


def test_guard_flags_unknown_song():
    b = _briefing(mentioned_songs=["Song 1", "Not A Real Song"])
    problems = briefing_guard(b, _show())
    assert problems == ["briefing mentions unknown song: Not A Real Song"]


def test_guard_flags_bogus_set_key_but_allows_encore():
    b = _briefing(per_set={"1": ["a"], "2": ["b"], "3": ["nope"], "encore": ["ok"]})
    assert briefing_guard(b, _show()) == ["briefing references nonexistent set: 3"]


def test_guard_flags_wrong_set_count_claim_in_prose():
    b = _briefing(significance="They played three sets that night.")
    assert briefing_guard(b, _show()) == [
        "briefing claims 3 sets but structure has 2"]
    b2 = _briefing(notable_moments=["The fourth set closed with fireworks."])
    assert briefing_guard(b2, _show()) == [
        "briefing mentions the fourth set but structure has 2 sets"]


def test_guard_accepts_correct_set_count_claim():
    assert briefing_guard(_briefing(context="Both sets stretch out."), _show()) == []


def test_guard_vague_mode_violations():
    b = _briefing(narration="vague", per_set={"1": ["a"]}, mentioned_songs=["Song 1"])
    problems = briefing_guard(b, _show())
    assert "briefing has per-set talking points under vague narration" in problems
    assert "briefing names songs under vague narration" in problems
    # a set-count claim is a violation under vague even when numerically right
    b2 = _briefing(narration="vague", per_set={}, mentioned_songs=[],
                   context="They played two sets.")
    assert briefing_guard(b2, _show()) == [
        "briefing asserts set structure under vague narration"]


def test_guard_vague_mode_clean():
    b = _briefing(narration="vague", per_set={}, mentioned_songs=[],
                  context="A revered night from the '73 run.")
    assert briefing_guard(b, _show()) == []


def test_guard_flags_empty_per_set_under_full():
    b = _briefing(per_set={})
    assert briefing_guard(b, _show()) == ["briefing has no per-set talking points"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_stage_brief.py -q`
Expected: FAIL — `ImportError: cannot import name 'briefing_guard'`.

- [ ] **Step 3: Implement the guard**

In `packages/llama/src/llama/stages/brief.py`, extend the imports and add:

```python
from llama.songs import normalize_song
from llama.stages.synthesize import (_COUNT_WORDS, _ORDINALS, _ORDINAL_SET,
                                     _SET_COUNT_CLAIM, _set_label)


def briefing_guard(briefing: Briefing, show: Show) -> list[str]:
    """A briefing that misnames songs or sets — or breaks the vague-narration
    contract — must never ship; cross-check against show.json. Same hold
    semantics as synthesize's factual_guard, stricter vague enforcement."""
    problems: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in briefing.mentioned_songs:
        if normalize_song(song) not in known:
            problems.append(f"briefing mentions unknown song: {song}")
    sets = {t.set for t in show.tracks}
    for s in briefing.per_set:
        if s not in sets:
            problems.append(f"briefing references nonexistent set: {s}")
    prose = " ".join([briefing.context, briefing.significance,
                      briefing.review_sentiment, *briefing.notable_moments,
                      *(p for pts in briefing.per_set.values() for p in pts)])
    n_sets = len({t.set for t in show.tracks if t.set != "encore"})
    claimed = {_COUNT_WORDS[m.group(1).lower()] for m in _SET_COUNT_CLAIM.finditer(prose)}
    implied = {_ORDINALS[m.group(1).lower()]: m.group(1).lower()
               for m in _ORDINAL_SET.finditer(prose)}
    if briefing.narration == "vague":
        # Vague means: assert nothing about set structure, name no songs.
        if briefing.per_set:
            problems.append("briefing has per-set talking points under vague narration")
        if briefing.mentioned_songs:
            problems.append("briefing names songs under vague narration")
        if claimed or implied:
            problems.append("briefing asserts set structure under vague narration")
    else:
        if not briefing.per_set:
            problems.append("briefing has no per-set talking points")
        for n in sorted(claimed):
            if n != n_sets:
                problems.append(f"briefing claims {n} sets but structure has {n_sets}")
        for n, word in sorted(implied.items()):
            if n > n_sets:
                problems.append(
                    f"briefing mentions the {word} set but structure has {n_sets} sets")
    return problems
```

- [ ] **Step 4: Run the tests**

Run: `pytest packages/llama/tests/test_stage_brief.py -q` → all pass.
Run: `pytest -q` → no regressions.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/stages/brief.py packages/llama/tests/test_stage_brief.py
git commit -m "feat: briefing_guard — setlist cross-check + strict vague enforcement"
```

---

### Task 3: `brief` prompt + `run_brief` stage function

**Files:**
- Create: `packages/llama/src/llama/prompts/brief.md`
- Modify: `packages/llama/src/llama/stages/brief.py`
- Test: `packages/llama/tests/test_stage_brief.py`

**Interfaces:**
- Consumes: `herder.run_json_task`, `llama.prompts.load_prompt`,
  `llama.util.reviews_digest`, `llama.workspace` helpers (`should_run`,
  `read_model`, `read_overrides`, `write_artifact`), `llama.models.VettingResult`,
  `llama.stages.synthesize.narration_note`, plus Task 1–2's `render_briefing_md`
  / `briefing_guard`.
- Produces: `run_brief(show_ws: ShowWorkspace, provider, show: Show,
  research_md: str, reviews: list[dict], force: bool = False) -> Briefing` —
  Task 4 calls it from `process_show` with `providers["brief"]`. Also
  `vetting_summary(show_ws: ShowWorkspace) -> str` (used only internally, but
  tested). Artifacts: writes `show_ws.briefing_json` and `show_ws.briefing_md`
  (ShowWorkspace gains those path attributes in **this** task so the stage is
  testable; the rest of the wiring waits for Task 4).

- [ ] **Step 1: Add the ShowWorkspace paths**

In `packages/llama/src/llama/workspace.py`, inside `ShowWorkspace.__init__`
(after `self.vetting = dir / "vetting.json"`, line 78):

```python
        self.briefing_json = dir / "briefing.json"
        self.briefing_md = dir / "briefing.md"
```

- [ ] **Step 2: Write the failing tests**

Append to `packages/llama/tests/test_stage_brief.py`:

```python
import json

from herder.fake import FakeProvider
from llama.models import Overrides, VettingResult, ResearchVetting
from llama.stages.brief import run_brief, vetting_summary
from llama.workspace import ShowWorkspace, write_artifact

GOOD_BRIEFING = json.dumps({
    "context": "Peak-era Dead on the summer '73 run.",
    "significance": "A standout show from a strong year.",
    "per_set": {"1": ["Opens hot"], "2": ["The big jam"]},
    "notable_moments": [], "review_sentiment": "Praised.",
    "non_attendee_sentiment": True, "cautions": [],
    "narration": "full", "mentioned_songs": []})

BAD_BRIEFING = json.dumps({
    "context": "", "significance": "They played three sets.",
    "per_set": {"1": ["a"], "2": ["b"]}, "notable_moments": [],
    "review_sentiment": "", "non_attendee_sentiment": False, "cautions": [],
    "narration": "full", "mentioned_songs": []})


def _ws(tmp_path, show) -> ShowWorkspace:
    ws = ShowWorkspace(tmp_path / "show")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.show, show)
    return ws


def test_run_brief_writes_artifacts_and_stamps_narration(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    provider = FakeProvider(completes=[GOOD_BRIEFING])
    b = run_brief(ws, provider, show, "research text", [], force=False)
    assert ws.briefing_json.exists() and ws.briefing_md.exists()
    assert b.narration == "full"
    assert "## Context" in ws.briefing_md.read_text()
    # the prompt carried the inputs
    prompt = provider.calls[0][1]
    assert "research text" in prompt and "RFK Stadium" in prompt


def test_run_brief_skips_when_artifact_exists(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    run_brief(ws, FakeProvider(completes=[GOOD_BRIEFING]), show, "", [], force=False)
    # no queued responses: a second call must not hit the provider
    again = run_brief(ws, FakeProvider(completes=[]), show, "", [], force=False)
    assert again.context == "Peak-era Dead on the summer '73 run."


def test_run_brief_narration_stamp_overrides_llm_value(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    write_artifact(ws.overrides, Overrides(narration="vague"))
    vague_ok = json.dumps({"context": "A revered night.", "significance": "Legendary.",
                           "per_set": {}, "notable_moments": [],
                           "review_sentiment": "Praised.", "non_attendee_sentiment": True,
                           "cautions": [], "narration": "full", "mentioned_songs": []})
    b = run_brief(ws, FakeProvider(completes=[vague_ok]), show, "", [], force=False)
    assert b.narration == "vague"          # stamped from overrides, LLM said "full"
    assert json.loads(ws.briefing_json.read_text())["narration"] == "vague"


def test_run_brief_retries_with_feedback_then_holds(tmp_path):
    from llama.models import Show
    show = _show()
    ws = _ws(tmp_path, show)
    provider = FakeProvider(completes=[BAD_BRIEFING, BAD_BRIEFING])
    run_brief(ws, provider, show, "", [], force=False)
    assert len(provider.calls) == 2
    assert "failed fact-checking" in provider.calls[1][1]
    held = Show.model_validate_json(ws.show.read_text())
    assert held.needs_review is True
    assert any("briefing claims 3 sets" in f for f in held.review_flags)
    assert ws.briefing_json.exists()       # artifacts still written when held


def test_run_brief_recovers_on_retry(tmp_path):
    from llama.models import Show
    show = _show()
    ws = _ws(tmp_path, show)
    provider = FakeProvider(completes=[BAD_BRIEFING, GOOD_BRIEFING])
    run_brief(ws, provider, show, "", [], force=False)
    assert Show.model_validate_json(ws.show.read_text()).needs_review is False


def test_vetting_summary(tmp_path):
    ws = _ws(tmp_path, _show())
    assert vetting_summary(ws) == "(no vetting data)"
    write_artifact(ws.vetting, VettingResult(
        vetting=ResearchVetting(context="Summer '73 stadium run."),
        flags=["research asserts a song not in the show"],
        adopted_date="1973-06-10"))
    text = vetting_summary(ws)
    assert "research asserts a song not in the show" in text
    assert "1973-06-10" in text and "Summer '73 stadium run." in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_stage_brief.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_brief'`.

- [ ] **Step 4: Write the prompt template**

Create `packages/llama/src/llama/prompts/brief.md`:

```markdown
Write a neutral, factual briefing on a full-concert recording for a radio
scriptwriter. The reader has never heard of this show; the briefing must be
thorough enough that they can write an on-air script from it alone. This is a
reference document, not a script: plain informative prose, no address to
listeners, no radio patter.

Register rules:
- Strictly neutral: no first-person voice, no enthusiasm of your own, no
  hype adjectives asserted in your own voice.
- Opinions appear ONLY as attributed sentiment ("reviewers describe...",
  "tapers regard..."), never as the briefing's own judgment.
- Every fact — dates, venue, songs, set structure, personnel, events on
  stage — must come from the inputs below. Do not invent anything.
- Note in `cautions` anything a scriptwriter must know before asserting
  facts on air: thin or conflicting research, corrected dates, vetting
  flags, uncertain structure.

{{narration_note}}Show data (JSON):
{{show_json}}

Research findings:
{{research}}

Vetting notes (the research above was checked against the show data):
{{vetting}}

Listener review excerpts:
{{reviews_digest}}
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<a short paragraph placing the show in its era/tour/venue>",
 "significance": "<a short paragraph on why this show is worth airtime>",
 "per_set": {<one key per set label found in the show data (e.g. "1", "2",
   "encore")>: ["<talking point grounded in the inputs>", ...]},
 "notable_moments": ["<specific highlight grounded in research/reviews>", ...],
 "review_sentiment": "<summary of reception: who praises it and for what>",
 "non_attendee_sentiment": <true iff the sentiment includes voices who were
   not at the show>,
 "cautions": ["<caveat the scriptwriter needs>", ...],
 "narration": "full",
 "mentioned_songs": [<every song title referenced anywhere above, spelled
   exactly as in the show data>]}
Raw JSON only.
```

- [ ] **Step 5: Implement `vetting_summary` and `run_brief`**

In `packages/llama/src/llama/stages/brief.py`, extend imports and add:

```python
from herder import run_json_task
from llama.models import VettingResult
from llama.prompts import load_prompt
from llama.stages.synthesize import narration_note
from llama.util import reviews_digest
from llama.workspace import (ShowWorkspace, read_model, read_overrides,
                             should_run, write_artifact)


def vetting_summary(show_ws: ShowWorkspace) -> str:
    """Compact rendering of vetting.json for the prompt's {{vetting}} slot, so
    `cautions` are grounded in the vet stage's findings rather than invented."""
    if not show_ws.vetting.exists():
        return "(no vetting data)"
    vr = read_model(show_ws.vetting, VettingResult)
    lines = ["Vetting flags: " + "; ".join(vr.flags) if vr.flags
             else "Research passed vetting with no flags."]
    if vr.adopted_date:
        lines.append(f"The show date was corrected to {vr.adopted_date} "
                     "based on research (archive metadata had a placeholder).")
    if vr.vetting.context:
        lines.append("Context: " + vr.vetting.context)
    return "\n".join(lines)


def run_brief(
    show_ws: ShowWorkspace,
    provider,
    show: Show,
    research_md: str,
    reviews: list[dict],
    force: bool = False,
) -> Briefing:
    if not should_run(show_ws.briefing_json, force):
        return read_model(show_ws.briefing_json, Briefing)

    narration = read_overrides(show_ws).narration
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        vetting=vetting_summary(show_ws),
        reviews_digest=reviews_digest(reviews),
        narration_note=narration_note(narration),
    )
    feedback = ""
    for _attempt in range(2):
        briefing = run_json_task(provider, "brief", Briefing,
                                 template=load_prompt("brief"), feedback=feedback, **inputs)
        briefing.narration = narration  # stamped; the LLM's value is never trusted
        problems = briefing_guard(briefing, show)
        if not problems:
            break
        feedback = (
            "IMPORTANT: your previous briefing failed fact-checking: "
            + "; ".join(problems)
            + ". Fix every problem; stay strictly grounded in the inputs."
        )
    if problems:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + problems
        current.needs_review = True
        write_artifact(show_ws.show, current)
    write_artifact(show_ws.briefing_json, briefing)
    write_artifact(show_ws.briefing_md, render_briefing_md(briefing, show))
    return briefing
```

- [ ] **Step 6: Run the tests**

Run: `pytest packages/llama/tests/test_stage_brief.py -q` → all pass.
Run: `pytest -q` → no regressions.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/prompts/brief.md packages/llama/src/llama/stages/brief.py packages/llama/src/llama/workspace.py packages/llama/tests/test_stage_brief.py
git commit -m "feat: run_brief stage — vetted neutral briefing with guard + hold"
```

---

### Task 4: Wire `brief` into the pipeline, workspace order, and CLI

**Files:**
- Modify: `packages/llama/src/llama/workspace.py:88-99` (`SHOW_STAGE_ORDER`, `show_stage_artifacts`)
- Modify: `packages/llama/src/llama/pipeline.py:24-26` (`TASK_KEYS`), `pipeline.py:100-118` (`process_show`)
- Modify: `packages/llama/src/llama/config.py:17-27` (`DEFAULT_TIERS`)
- Modify: `packages/llama/src/llama/cli.py:48` (`VALID_STAGES`), `cli.py:866-868` (triage accept-vague), `cli.py:1038-1050` (`_PIPELINE_STAGE_DESC`), `cli.py:1052-1056` (`_PIPELINE_FLOW`), `cli.py:1069-1075` (`_PIPELINE_REDO_CHEATSHEET`), `cli.py:1420` (fix redo stage), `cli.py:1549` (redo help text)
- Test: `packages/llama/tests/test_pipeline.py`, `packages/llama/tests/test_workspace.py`, plus suite-driven fixes

**Interfaces:**
- Consumes: Task 3's `run_brief`.
- Produces: stage name `"brief"` valid everywhere a stage name is accepted;
  `providers["brief"]` present in every `make_providers()` result; narration
  edits redo from `brief` (not `synthesize`). Task 5 relies on the stage having
  run before `run_package`.

- [ ] **Step 1: Write the failing tests**

In `packages/llama/tests/test_pipeline.py`, add (adapting the file's existing
fixture style — it already builds `providers` dicts of `FakeProvider`s and calls
`process_show`; put the constant near its existing canned responses):

```python
GOOD_BRIEFING_JSON = json.dumps({
    "context": "Peak-era Dead.", "significance": "Worth airing.",
    "per_set": {"1": ["Opens hot"]}, "notable_moments": [],
    "review_sentiment": "Praised.", "non_attendee_sentiment": True,
    "cautions": [], "narration": "full", "mentioned_songs": []})


def test_task_keys_include_brief():
    from llama.pipeline import TASK_KEYS
    assert "brief" in TASK_KEYS
    from llama.config import DEFAULT_TIERS
    assert DEFAULT_TIERS["brief"] == "high"


def test_process_show_runs_brief_and_writes_artifacts(...):
    # extend the file's existing happy-path process_show test: add
    #   "brief": FakeProvider(completes=[GOOD_BRIEFING_JSON]),
    # to its providers dict, then assert after the run:
    assert show_ws.briefing_json.exists()
    assert show_ws.briefing_md.exists()


def test_process_show_holds_on_briefing_guard_failure(...):
    # clone the happy-path test but queue two bad briefings:
    #   "brief": FakeProvider(completes=[BAD, BAD])   # BAD asserts three sets
    # process_show must return None (held before synthesize/package), and the
    # synthesize/package providers' queues must be untouched.
```

In `packages/llama/tests/test_workspace.py` add:

```python
def test_stage_order_and_artifacts_include_brief(tmp_path):
    from llama.workspace import SHOW_STAGE_ORDER, ShowWorkspace, show_stage_artifacts
    assert SHOW_STAGE_ORDER == ["select", "gather", "research", "vet",
                                "brief", "synthesize", "package"]
    ws = ShowWorkspace(tmp_path)
    assert show_stage_artifacts(ws, "brief") == [ws.briefing_json, ws.briefing_md]


def test_drop_from_brief_drops_downstream(tmp_path):
    from llama.workspace import ShowWorkspace, drop_stage_artifacts
    ws = ShowWorkspace(tmp_path)
    for p in [ws.vetting, ws.briefing_json, ws.briefing_md, ws.dj_notes_json, ws.dj_notes_md]:
        p.write_text("{}")
    (ws.package_dir).mkdir()
    (ws.package_dir / "manifest.json").write_text("{}")
    drop_stage_artifacts(ws, "brief")
    assert ws.vetting.exists()
    for p in [ws.briefing_json, ws.briefing_md, ws.dj_notes_json,
              ws.dj_notes_md, ws.package_dir / "manifest.json"]:
        assert not p.exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest packages/llama/tests/test_workspace.py packages/llama/tests/test_pipeline.py -q`
Expected: FAIL on the new tests (stage order, TASK_KEYS, missing artifacts).

- [ ] **Step 3: Wire the stage**

`workspace.py:88`:
```python
SHOW_STAGE_ORDER = ["select", "gather", "research", "vet", "brief", "synthesize", "package"]
```
`workspace.py` `show_stage_artifacts` — insert between `vet` and `synthesize`:
```python
        "brief": [show_ws.briefing_json, show_ws.briefing_md],
```

`pipeline.py:24-26`:
```python
TASK_KEYS = ["interpret", "score_reviews", "light_research",
             "extract_setlist", "deep_research", "brief", "synthesize",
             "find_artists", "align_structure", "vet_research"]
```

`config.py` `DEFAULT_TIERS` — after `"deep_research": "high",`:
```python
    "brief": "high",
```

`pipeline.py` — import `run_brief` alongside the other stage imports:
```python
from llama.stages.brief import run_brief
```
and in `process_show`, directly after the post-vet hold check (`return None` at
line 103) and before the `notes = None` line:
```python
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    with step(f"[{pid}] briefing"):
        run_brief(show_ws, providers["brief"], show, research_md, reviews, force=force)
    show = read_model(show_ws.show, Show)  # brief's guard may have flagged it
    if show.needs_review:
        log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(show.review_flags))
        return None
```
then delete the now-duplicate `reviews = read_json(...)` line inside the
`if script:` block (reuse the variable read above).

`cli.py:48`:
```python
VALID_STAGES = {"search", "winnow", "select", "gather", "research", "vet", "brief", "synthesize", "package"}
```

`cli.py` `_PIPELINE_STAGE_DESC` — insert between `vet` and `synthesize`:
```python
    "brief": "neutral vetted briefing for scriptwriters, factually guarded (always on) -> briefing.*",
```
`cli.py` `_PIPELINE_FLOW`:
```python
_PIPELINE_FLOW = (
    "interpret → search → winnow →(gate 1: run approve)→ select → "
    "gather → research → vet → brief → synthesize → package "
    "→(gate 2: held → triage / fix)→ deliver"
)
```
`cli.py:1071` cheat-sheet entry becomes:
```python
    ("narration mode (vague)", "brief"),
```
`cli.py:868` (triage accept-vague resolution): `stage = "synthesize"` → `stage = "brief"`.
`cli.py:1420` (fix): `("synthesize" if did_narration else "package")` → `("brief" if did_narration else "package")`.
`cli.py:1549` (redo `--from` help): `"synthesize|package"` → `"brief|synthesize|package"`.

- [ ] **Step 4: Run the full suite and repair fallout**

Run: `pytest -q`. Expected breakage classes (fix each the same way):
- Tests calling `process_show` without a `"brief"` provider →
  `KeyError: 'brief'` or FakeProvider exhaustion: add
  `"brief": FakeProvider(completes=[GOOD_BRIEFING_JSON])` to their providers
  dicts (files to expect: `test_pipeline.py`, `test_voice_pipeline.py`,
  `test_multi_event_integration.py`, `test_get_cmd.py`, `test_redo_cmd.py`,
  `test_cli_voice.py` — follow the failures).
- Tests asserting the old stage list / `pipeline` command output
  (`test_workspace.py`, `test_cli_commands.py`): update expectations to include
  `brief`.
- Tests asserting fix/triage redo stage for narration
  (`test_fix.py`, `test_triage.py`): expected stage becomes `brief`.

Note (spec): a pre-existing workspace with dj-notes but no `briefing.json`
redone `--from package` **will regenerate the briefing** — `process_show`
finds the artifact missing. `test_redo_cmd.py` gets one new test asserting
exactly that self-heal.

- [ ] **Step 5: Verify the untouched-synthesize constraint**

Run: `git diff --stat main -- packages/llama/src/llama/stages/synthesize.py`
Expected: empty output (no diff), and full suite green.

- [ ] **Step 6: Commit**

```bash
git add -A packages/llama
git commit -m "feat: wire default-on brief stage into pipeline, redo, fix, and CLI"
```

---

### Task 5: Manifest v3 with required `briefing` block

**Files:**
- Modify: `packages/llama/src/llama/models.py:246-258` (`Manifest`, new `ManifestBriefing`)
- Modify: `packages/llama/src/llama/manifest.py:6-34` (`build_manifest`)
- Modify: `packages/llama/src/llama/stages/package.py` (`run_package`)
- Modify: `packages/llama/tests/helpers.py` (`build_ready` manifest dict)
- Test: `packages/llama/tests/test_manifest.py`, `packages/llama/tests/test_stage_package.py`

**Interfaces:**
- Consumes: `Briefing` (read from `show_ws.briefing_json`), `LlamaError`.
- Produces: `ManifestBriefing` model (fields `file`, `json_file` serialized as
  `"json"`, `narration`, `vetted`); `Manifest.schema_version` default `3`;
  `Manifest.briefing: ManifestBriefing` (required); `build_manifest(...,
  briefing: ManifestBriefing, ...)` keyword parameter. Task 6/7 rely on the
  serialized key names.

- [ ] **Step 1: Write the failing tests**

In `packages/llama/tests/test_manifest.py`:

```python
def test_manifest_v3_briefing_block():
    from llama.models import Manifest, ManifestBriefing
    m = Manifest(show={}, source={}, tracks=[], set_breaks=[],
                 briefing=ManifestBriefing(narration="vague", vetted=True),
                 total_duration_sec=0.0, set_durations_sec={})
    assert m.schema_version == 3
    dumped = json.loads(m.model_dump_json(by_alias=True))
    assert dumped["briefing"] == {"file": "briefing.md", "json": "briefing.json",
                                  "narration": "vague", "vetted": True}


def test_build_manifest_carries_briefing():
    from llama.manifest import build_manifest
    from llama.models import ManifestBriefing
    m = build_manifest(_show(), None, [], briefing=ManifestBriefing(
        narration="full", vetted=False))
    assert m.briefing.narration == "full"
```

(`_show()` refers to the file's existing show fixture; match its actual name.)

In `packages/llama/tests/test_stage_package.py` (following its existing
fixture style — it already fakes `ia` and builds workspaces):

```python
def test_package_copies_briefing_and_emits_v3(...):
    # extend the existing happy-path package test: before run_package, write
    # briefing artifacts the way run_brief would:
    write_artifact(ws.briefing_json, _briefing())          # a Briefing model
    write_artifact(ws.briefing_md, "# Briefing: ...\n")
    pkg = run_package(ws, ia, show, None, force=True)
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["schema_version"] == 3
    assert manifest["briefing"]["json"] == "briefing.json"
    assert manifest["briefing"]["narration"] == "full"
    assert (pkg / "briefing.md").exists() and (pkg / "briefing.json").exists()


def test_package_hard_fails_without_briefing(...):
    # same setup minus the briefing artifacts:
    with pytest.raises(LlamaError, match="no briefing"):
        run_package(ws, ia, show, None, force=True)
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest packages/llama/tests/test_manifest.py packages/llama/tests/test_stage_package.py -q`
Expected: FAIL — `ImportError: cannot import name 'ManifestBriefing'`.

- [ ] **Step 3: Model changes**

In `packages/llama/src/llama/models.py`, before `Manifest`:

```python
class ManifestBriefing(BaseModel):
    """Pointer block for the packaged briefing (manifest v3). `json_file`
    serializes as "json" — the attribute name avoids shadowing BaseModel.json."""
    file: str = "briefing.md"
    json_file: str = Field("briefing.json", alias="json")
    narration: str = "full"          # "full" | "vague" — travels with the package
    vetted: bool = False             # research_vetted at package time

    model_config = {"populate_by_name": True}
```

`Manifest` changes (two lines):
```python
    schema_version: int = 3
    briefing: ManifestBriefing       # required in v3; always llama-written
```

Check how `write_artifact` serializes models (`workspace.py:41-44` →
`_to_jsonable`): confirm it dumps **by alias**; if it does not, adjust
`_to_jsonable`'s `model_dump` call to `model_dump(by_alias=True)` — that call
site serializes every artifact, and no other model declares an alias, so the
flip is behavior-neutral for them.

- [ ] **Step 4: `build_manifest` + `run_package`**

`manifest.py` — add a required keyword param and pass it through:
```python
def build_manifest(
    show: Show,
    notes: DJNotes | None,
    packaged: list[ManifestTrack],
    *,
    briefing: ManifestBriefing,
    context: str = "",
    research: str | None = None,
    reviews: str | None = None,
    research_vetted: bool = False,
    dj_audio: DJAudio | None = None,
) -> Manifest:
```
(add `briefing=briefing` to the `Manifest(...)` construction; import
`ManifestBriefing` in the module's model import line.)

`package.py` `run_package` — after the vetting/context block (`package.py:286-292`)
and before the research copy, add:

```python
    if not (show_ws.briefing_json.exists() and show_ws.briefing_md.exists()):
        raise LlamaError(
            f"{show.performance_id}: package requires a briefing but this show "
            "has no briefing artifacts; run `llama redo` from the brief stage")
    briefing = read_model(show_ws.briefing_json, Briefing)
    write_artifact(pkg / "briefing.md", show_ws.briefing_md.read_text())
    write_artifact(pkg / "briefing.json", show_ws.briefing_json.read_text())
```
and extend the manifest call (`package.py:317-320`):
```python
    write_artifact(manifest_path, build_manifest(
        show, notes, packaged,
        briefing=ManifestBriefing(narration=briefing.narration, vetted=vetted),
        context=context,
        research=research_name, reviews="reviews.md", research_vetted=vetted,
        dj_audio=dj_audio))
```
Imports: add `Briefing, ManifestBriefing` to package.py's `llama.models` import
and `LlamaError` from `llama.errors`.

- [ ] **Step 5: Update `helpers.py` and repair fallout**

In `packages/llama/tests/helpers.py` `build_ready`, update the fabricated
manifest dict to the v3 shape:
```python
    manifest = {"schema_version": 3,
                "briefing": {"file": "briefing.md", "json": "briefing.json",
                             "narration": "full", "vetted": False},
                ...unchanged keys...}
```

Run: `pytest -q`. Expected fallout: every test that drives `run_package`
without briefing artifacts now hits the hard-fail — fix by writing briefing
artifacts in their setup (reuse `GOOD_BRIEFING_JSON`-style content or a
`Briefing(...)` model + `write_artifact`), NOT by weakening the hard-fail.
Pipeline-level tests already pass through `run_brief` (Task 4) and need no
change. Suite green.

- [ ] **Step 6: Commit**

```bash
git add -A packages/llama
git commit -m "feat: manifest v3 — required briefing block; package ships briefing files"
```

---

### Task 6: Catalog state + status surface (`briefed`)

**Files:**
- Modify: `packages/llama/src/llama/catalog.py:48-54` (`_STAGES`)
- Modify: `packages/llama/src/llama/cli_select.py:16-26` (`ShowState`)
- Modify: `packages/llama/src/llama/cli.py:1058-1067` (`_PIPELINE_STATE_DESC`), `cli.py:881-890` (`_stage_ages`)
- Test: `packages/llama/tests/test_status.py`, `packages/llama/tests/test_status_cmd.py`, `packages/llama/tests/test_show_cmd.py`

**Interfaces:**
- Consumes: `ws.briefing_json` (Task 3).
- Produces: derived state `"briefed"` between `vetted` and `scripted`;
  `ShowState.briefed`; `--state briefed` accepted by every selector.

- [ ] **Step 1: Write the failing tests**

In `packages/llama/tests/test_status.py` (match its existing derive_state
fixture style):

```python
def test_briefed_state_between_vetted_and_scripted(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    ws.dir.mkdir(parents=True)
    for p in [ws.selection, ws.show, ws.research, ws.vetting]:
        write_artifact(p, {}) if p != ws.show else write_artifact(p, _minimal_show())
    assert derive_state(ws, set())[0] == "vetted"
    write_artifact(ws.briefing_json, {"context": "c", "significance": "s"})
    assert derive_state(ws, set())[0] == "briefed"
    write_artifact(ws.dj_notes_json, {"set_intros": {}, "outro": "o"})
    assert derive_state(ws, set())[0] == "scripted"
```
(`_minimal_show()`: whatever minimal `Show` the file already uses for
`derive_state` tests — reuse it.)

In `packages/llama/tests/test_status_cmd.py`: extend the existing `--state`
filter test to include `--state briefed` accepting and filtering.

- [ ] **Step 2: Run to verify they fail**

Run: `pytest packages/llama/tests/test_status.py -q`
Expected: FAIL — state derives as `"vetted"` where `"briefed"` is expected.

- [ ] **Step 3: Implement**

`catalog.py` `_STAGES`:
```python
_STAGES = [
    ("selection", 1, "selected"),
    ("show", 2, "gathered"),
    ("research", 3, "researched"),
    ("vetting", 4, "vetted"),
    ("briefing_json", 5, "briefed"),
    ("dj_notes_json", 6, "scripted"),
]
```

`cli_select.py` `ShowState` — insert between `vetted` and `scripted`:
```python
    briefed = "briefed"
```

`cli.py` `_PIPELINE_STATE_DESC` — insert between `vetted` and `scripted`:
```python
    "briefed": "briefing.* exist (neutral vetted briefing)",
```

`cli.py` `_stage_ages` (line 884-887) — the `llama show` stage table hardcodes
the artifact list; insert between vetting and dj-notes:
```python
                 ("briefing.json", sws.briefing_json),
```
(and add a `test_show_cmd.py` assertion that the show detail lists
`briefing.json` once the artifact exists).

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`. Expected minor fallout: `test_cli_commands.py`'s `pipeline`
output assertions (state list now includes `briefed`) — update them. Suite
green.

- [ ] **Step 5: Commit**

```bash
git add -A packages/llama
git commit -m "feat: derived briefed state + --state briefed selector"
```

---

### Task 7: Documentation + config-init note + end-to-end verification

**Files:**
- Modify: `docs/station-brief.md` (package-format section ~line 77, tree ~54-71, "other files" ~137, contract details ~182, question 7 ~238)
- Modify: `README.md` ("Package format (v2)" ~line 269, downstream synthesis contract ~407)
- Modify: `docs/workflow.md` (workspace tree ~58-94, stage table ~149-162, voice section cross-refs ~263)
- Modify: `CLAUDE.md` (Architecture: stage list, briefing, manifest v3)
- Modify: `packages/llama/src/llama/config.py` (`DEFAULT_CONFIG_TOML` comment block, ~line 178)
- Test: full suite + `llama pipeline` smoke

**Interfaces:** none new — prose only, plus one config comment.

- [ ] **Step 1: Update the station contract doc**

`docs/station-brief.md`:
- Retitle the format section `## Package format — manifest.json, schema_version 3`.
- In the annotated manifest example: `"schema_version": 3` and add, after `set_breaks`:
```json
  "briefing": {              // llama's scriptwriter-facing text deliverable
    "file": "briefing.md",   // neutral vetted briefing (prose)
    "json": "briefing.json", // same content, structured (per-set talking points, cautions)
    "narration": "full",     // "vague": assert no songs/set structure downstream
    "vetted": true           // research passed the grounding check
  },
```
- Package tree: add `briefing.md` and `briefing.json` lines.
- "The other files": document both briefing files; describe `dj-notes.md` as
  the in-house verbatim script (transitional; a downstream persona tool owns
  scripting after the split completes).
- Contract details: the narration directive is binding on any downstream
  scriptwriter — under `"vague"`, name no songs and assert no set structure.
- Question 7: note v3 as the worked example of the schema_version promise.

- [ ] **Step 2: Update README.md, docs/workflow.md, CLAUDE.md**

- README: section header → `## Package format (v3)`; add the two briefing
  files + manifest block to the bullets; "Downstream synthesis contract" now
  leads with the briefing as the scriptwriting source (dj_notes remains for
  the in-house voice path).
- workflow.md: workspace tree gains `briefing.json` / `briefing.md` (show dir)
  and `package/briefing.*`; manifest annotation → `# schema v3`; stage table
  gains the `brief` row between vet and synthesize:
  `brief | neutral vetted briefing for scriptwriters, factually guarded (always on) | briefing.json, briefing.md`;
  synthesize row notes it is transitional (in-house script/voice path).
- CLAUDE.md (project): stage list in the Architecture bullet gains `brief`
  between vet and synthesize; add two sentences: the brief stage emits a
  neutral vetted briefing (briefing.md/briefing.json, always on, guarded like
  synthesize, narration directive from overrides); manifest is v3 with a
  required `briefing` block.

- [ ] **Step 3: config init note**

In `config.py`'s `DEFAULT_CONFIG_TOML` comment block (~line 178), where task
tier overrides are listed, add `brief` to the example task names (e.g. the
comment enumerating `[llm.<task>]` names).

- [ ] **Step 4: Full verification**

```bash
pytest -q                      # full suite green
llama pipeline                 # smoke: brief stage + briefed state render
git diff main --stat -- packages/llama/src/llama/stages/synthesize.py   # empty
```

- [ ] **Step 5: Commit**

```bash
git add docs/station-brief.md README.md docs/workflow.md CLAUDE.md packages/llama/src/llama/config.py
git commit -m "docs: package contract v3 — briefing block, brief stage, briefed state"
```
