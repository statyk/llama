# DJ Segment Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit exactly one spoken DJ clip per gap between music blocks — a lead-in before each non-encore set (the first also opens the show), an unannounced encore, and a closing outro — so no two DJ clips ever play back-to-back.

**Architecture:** Reshape the DJ-script data model and the three stages that touch it. `DJNotes.set_intros` becomes one combined lead-in per non-encore set; `intro` and `set_break_notes` are removed; `outro` recaps the encore. `DJAudio` and the manifest `SetBreak` lose their break-clip/break-note wiring. Tasks are ordered output-side → producer-side → docs so the full suite stays green at every task boundary.

**Tech Stack:** Python 3, Pydantic v2, pytest, Typer CLI. Offline `fake` LLM + `fake` TTS backends in tests.

## Global Constraints

- **No migration / no back-compat.** Existing `shows/<slug>/dj-notes.json` keep the old shape until regenerated (`llama redo <show> --from synthesize`). Add no schema shim. (Spec: "No migration".)
- **Option A encore handling.** An encore set gets **no** lead-in; it plays after the final set and the always-last `outro` recaps it. `set_intros` is keyed by **non-encore** sets only.
- **Broadcast order:** non-encore sets in numeric order, each `set<key>-intro`, then `99-outro`. Files gone: `00-intro`, `break<N>`.
- **Tests are offline and deterministic** (`pytest -q`). Run the full suite at each task's final step; it must be green.
- Spec: `docs/superpowers/specs/2026-07-24-dj-segment-consolidation-design.md`.

---

### Task 1: Output side — models (`DJAudio`, `SetBreak`), manifest, package

Reshape everything that *consumes* DJ notes to the new segment set, while `DJNotes` still carries the (now partly unused) `intro`/`set_break_notes` fields. This keeps `synthesize` and its tests untouched and green.

**Files:**
- Modify: `src/llama/models.py` (`DJAudio`, `SetBreak`)
- Modify: `src/llama/manifest.py` (`build_manifest`)
- Modify: `src/llama/stages/package.py` (`_segment_texts`, `_synthesize_dj_audio` return)
- Test: `tests/test_manifest.py`, `tests/test_stage_package.py`, `tests/test_chunk.py`, `tests/test_pipeline.py`, `tests/test_voice_pipeline.py`

**Interfaces:**
- Consumes: `DJNotes` unchanged this task — still has `intro`, `set_intros` (may include an `"encore"` key this task), `set_break_notes`, `outro`.
- Produces:
  - `class DJAudio(set_intros: dict[str,str], outro: str)` — no `intro`, no `set_breaks`.
  - `class SetBreak(after_track: int)` — no `note_index`, no `audio`.
  - `_segment_texts(notes) -> list[tuple[str,str]]` = one `set<key>-intro` per `set_intros` key (sorted, encore last) then `("99-outro", notes.outro)`.

- [ ] **Step 1: Update the manifest test to the new `SetBreak` / `DJAudio` shape**

In `tests/test_manifest.py`:
- `make_notes()` (~line 17): drop `intro="i"` and `set_break_notes=["x","y"]`; keep `context`, `set_intros`, `outro`. (Encore key may stay for now.)
- `test_build_manifest_*` (~line 42): set-break assertions become `after_track`-only:

```python
    assert [b.after_track for b in m.set_breaks] == [1, 2]
```

- `test_build_manifest_with_dj_audio` (~line 70): `DJAudio` loses `intro`/`set_breaks`:

```python
    dj_audio = DJAudio(
        set_intros={"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        outro="dj-audio/99-outro.mp3",
    )
    m = build_manifest(make_show(), make_notes(), make_packaged(), dj_audio=dj_audio)
    assert m.dj_audio == dj_audio
    assert [b.after_track for b in m.set_breaks] == [1, 2]
```

- Delete assertions referencing `b.note_index` / `b.audio` (lines ~42, 65, 82-83, 89).

- [ ] **Step 2: Run the manifest test to verify it fails**

Run: `pytest tests/test_manifest.py -q`
Expected: FAIL — `DJAudio`/`SetBreak` still have the old required/extra fields.

- [ ] **Step 3: Reshape `DJAudio` and `SetBreak` in `models.py`**

```python
class DJAudio(BaseModel):
    """Per-segment spoken DJ clips, as package-relative paths (dj-audio/...)."""
    set_intros: dict[str, str]  # keyed by non-encore set: "1", "2"
    outro: str


class SetBreak(BaseModel):
    after_track: int  # physical set boundary; DJ talk rides the next set's lead-in
```

- [ ] **Step 4: Reshape `build_manifest` in `manifest.py`**

Replace the `breaks = [...]` comprehension (lines 19-27) with `after_track`-only markers:

```python
    breaks = [SetBreak(after_track=idx) for idx in show.set_breaks]
```

Leave the rest of `build_manifest` unchanged (it still embeds `notes` and `dj_audio` whole).

- [ ] **Step 5: Reshape `_segment_texts` and the `DJAudio` return in `package.py`**

```python
def _segment_texts(notes: DJNotes) -> list[tuple[str, str]]:
    """(segment file stem, text) in broadcast order: one lead-in per set, then outro."""
    ordered = sorted(notes.set_intros, key=lambda x: (x == "encore", x))
    segs = [(f"set{key}-intro", notes.set_intros[key]) for key in ordered]
    segs.append(("99-outro", notes.outro))
    return segs
```

And the `_synthesize_dj_audio` return (lines 173-179):

```python
    return DJAudio(
        set_intros={key: f"dj-audio/set{key}-intro.mp3" for key in notes.set_intros},
        outro="dj-audio/99-outro.mp3",
    )
```

- [ ] **Step 6: Update package/chunk/pipeline tests to the new segment set**

`tests/test_stage_package.py`:
- `make_notes()` (~line 47): drop `intro="i"` and `set_break_notes=["x"]`; keep `context`, `set_intros={"1":"a","2":"b"}`, `outro="o"`.
- `test_package_synthesizes_dj_audio_and_manifest_block` (~line 144): expected files become `["set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"]` (no `00-intro`, no `break1`); `speech.calls == [notes.set_intros["1"], notes.set_intros["2"], notes.outro]`; `m["dj_audio"] == {"set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"}, "outro": "dj-audio/99-outro.mp3"}`; `m["set_breaks"] == [{"after_track": 1}]`.
- `test_package_*` set-break assertions (lines ~70, 132): `== [{"after_track": 1}]`.
- The `model_copy(update={"intro": ...})` at ~line 179: switch to a field that still exists, e.g. `update={"outro": "a different outro"}`, and adjust the surrounding assertion to match.

`tests/test_chunk.py`:
- `make_notes()` (~line 190): drop `intro=...` and `set_break_notes=[]`; put the multi-sentence copy into `set_intros={"1": "<3-sentence text>"}` and keep `outro=...`.
- `test_*` that reads `dj-audio/00-intro.mp3` (~line 233): read `dj-audio/set1-intro.mp3` instead; update `speech.calls` expectation (~line 252) to `[notes.set_intros["1"], notes.outro]`.

`tests/test_pipeline.py`:
- `set_breaks` manifest assertions (lines ~113, 182, 202, 231): drop `note_index`/`audio`, e.g. `== [{"after_track": 3}, {"after_track": 5}]`; `note_index`-only assertions (182, 202) are deleted.
- Leave `SYNTH_RESPONSE` (line ~40, still has `intro`/`set_break_notes`/encore) unchanged this task.

`tests/test_voice_pipeline.py`:
- dj-audio filename list (~line 105): `["set1-intro.mp3", "set2-intro.mp3", "setencore-intro.mp3", "99-outro.mp3"]` (encore lead-in still present this task; `00-intro`/`break*` gone).
- `manifest["dj_audio"]` (~line 109): `{"set_intros": {"1": ".../set1-intro.mp3", "2": ".../set2-intro.mp3", "encore": ".../setencore-intro.mp3"}, "outro": "dj-audio/99-outro.mp3"}`.
- `manifest["set_breaks"]` (~line 116): `== [{"after_track": 3}, {"after_track": 5}]`.
- Leave `SYNTH_RESPONSE` (line ~37) unchanged this task.

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS. (`test_stage_synthesize`, `test_models`, `test_catalog` untouched and still green because `DJNotes` is unchanged.)

- [ ] **Step 8: Commit**

```bash
git add src/llama/models.py src/llama/manifest.py src/llama/stages/package.py tests/
git commit -m "refactor: reshape DJ audio/manifest to one clip per music gap (output side)"
```

---

### Task 2: Producer side — `DJNotes`, synthesize prompt/guard/render/run

Now change what *produces* the notes so `set_intros` carries the combined per-set lead-ins (no encore key), `intro`/`set_break_notes` are removed, and the outro recaps the encore.

**Files:**
- Modify: `src/llama/models.py` (`DJNotes`)
- Modify: `src/llama/stages/synthesize.py` (`factual_guard`, `render_notes_md`, `run_synthesize`)
- Modify: `src/llama/prompts/synthesize.md`
- Test: `tests/test_stage_synthesize.py`, `tests/test_models.py`, `tests/test_catalog.py`, `tests/test_pipeline.py`, `tests/test_voice_pipeline.py`

**Interfaces:**
- Consumes: `_segment_texts` / `DJAudio` / `SetBreak` from Task 1.
- Produces:
  - `class DJNotes(context: str = "", set_intros: dict[str,str], outro: str, mentioned_songs: list[str] = [])` — no `intro`, no `set_break_notes`.
  - `factual_guard(notes, show)` validates `set_intros` keys against **non-encore** sets and covers all of them; no break-count check.

- [ ] **Step 1: Write/adjust the failing synthesize tests**

In `tests/test_stage_synthesize.py`:
- `notes_dict()` (~line 34): drop `intro=` and `set_break_notes=`; `set_intros={"1": "...", "2": "..."}` (no `encore` key); keep `context`, `outro`, `mentioned_songs`. Add a `single_set_notes()` shim if the helper referenced `intro`/`set_break_notes` kwargs — route that prose into `outro` or a `set_intros["1"]` value.
- Prose-claim tests (~lines 78-105) that passed copy via `intro=`: move the offending prose into `outro=` or `set_intros={"1": ...}` so the free-text scan still sees it.
- `test_notes_md_interleaves_breaks_with_set_intros` (~line 109): replace with a new `render_notes_md` expectation — headers are exactly `["## Set 1 lead-in", "## Set 2 lead-in", "## Outro"]` for a two-set show (context line above); no `## Show intro`, no `## Set break N`, no `## Encore …`.
- Any assertion on `notes.intro` (~line 126) / `"## Show intro"` (~line 129): update to `set_intros`/`## Set 1 lead-in`.
- Add the new guard test:

```python
def test_factual_guard_rejects_encore_lead_in():
    show = make_show()  # has an "encore" set
    notes = DJNotes(**notes_dict(set_intros={"1": "a", "2": "b", "encore": "c"}))
    problems = factual_guard(notes, show)
    assert any("encore" in p for p in problems)


def test_factual_guard_requires_every_non_encore_set():
    show = make_show()
    notes = DJNotes(**notes_dict(set_intros={"1": "a"}))  # missing set 2
    assert any("missing" in p for p in factual_guard(notes, show))
```

- Add the segment-layout invariant test:

```python
def test_segment_layout_has_no_adjacent_talk():
    from llama.stages.package import _segment_texts
    show = make_show()  # 2 sets + encore
    notes = DJNotes(**notes_dict(set_intros={"1": "a", "2": "b"}))
    stems = [s for s, _ in _segment_texts(notes)]
    assert stems == ["set1-intro", "set2-intro", "99-outro"]
    non_encore = len({t.set for t in show.tracks if t.set != "encore"})
    assert len(stems) == non_encore + 1
```

- [ ] **Step 2: Run the synthesize tests to verify they fail**

Run: `pytest tests/test_stage_synthesize.py -q`
Expected: FAIL — `DJNotes` still requires `intro`; guard still checks break count / all sets.

- [ ] **Step 3: Remove `intro` / `set_break_notes` from `DJNotes`**

```python
class DJNotes(BaseModel):
    context: str = ""  # one-line era/tour context
    set_intros: dict[str, str]  # combined lead-in per non-encore set: "1", "2"
    outro: str
    mentioned_songs: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Rewrite `factual_guard`, `render_notes_md`, `run_synthesize`**

`factual_guard` (replace lines 67-82 region):

```python
    lead_in_sets = {t.set for t in show.tracks if t.set != "encore"}
    for s in notes.set_intros:
        if s not in lead_in_sets:
            problems.append(f"dj notes reference nonexistent or encore set: {s}")
    missing = lead_in_sets - set(notes.set_intros)
    if missing:
        problems.append(f"dj notes missing set intros: {sorted(missing)}")
    # (removed: set_break_notes count check)
    prose = " ".join([notes.context, notes.outro, *notes.set_intros.values()])
```

`render_notes_md` (replace lines 106-116):

```python
    for s in sorted(notes.set_intros, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)} lead-in", notes.set_intros[s], ""]
    lines += ["## Outro", notes.outro, ""]
```

`run_synthesize` (replace the `inputs`/feedback bits, lines 133-152):

```python
    sets = sorted({t.set for t in show.tracks}, key=lambda x: (x == "encore", x))
    lead_in_sets = [s for s in sets if s != "encore"]
    encore_note = (
        "This show ends with an encore that plays unannounced right after the "
        "final set — write NO lead-in for it; instead have the outro recap it."
        if "encore" in sets else ""
    )
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        reviews_digest=reviews_digest(reviews),
        lead_in_sets=", ".join(f'"{s}"' for s in lead_in_sets),
        encore_note=encore_note,
        style=persona_style(presenter, title) if presenter else NEUTRAL_STYLE,
    )
    feedback = ""
    for _attempt in range(2):
        notes = run_json_task(provider, "synthesize", DJNotes, feedback=feedback, **inputs)
        problems = factual_guard(notes, show)
        if not problems:
            break
        feedback = (
            "IMPORTANT: your previous script failed fact-checking: "
            + "; ".join(problems)
            + ". Fix every problem; write one lead-in per set listed above."
        )
```

- [ ] **Step 5: Rewrite the prompt template `prompts/synthesize.md`**

Keep line 1 (`Write on-air DJ notes for a full-concert radio broadcast. {{style}}`) and the `{{show_json}}`/`{{research}}`/`{{reviews_digest}}` blocks byte-identical (the neutral-prompt lock checks the opening). Replace the sets line (12) and the JSON shape (15-21):

```
Write one lead-in per set: {{lead_in_sets}}. {{encore_note}}
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<one line placing the show in its era/tour>",
 "set_intros": {<one key per set from: {{lead_in_sets}}>:
   "<the lead-in for that set. The FIRST set's lead-in also opens the broadcast — artist, date, venue, why this show earns airtime (~60-90s) — then what to listen for. Each LATER set's lead-in briefly recaps the set just played, then teases this one (~30-45s)>"},
 "outro": "<sign-off after the final music: recap the show including any encore, recording source credit, invitation to next broadcast>",
 "mentioned_songs": [<every song title referenced anywhere above, spelled exactly as in the show data>]}
Raw JSON only.
```

- [ ] **Step 6: Update the integration fixtures and remaining tests**

- `tests/test_models.py` (~line 29): `DJNotes(set_intros={"1": "a"}, outro="bye")` (drop `intro="hi"`).
- `tests/test_catalog.py` (~line 43): the written `dj_notes_json` dict drops `"intro"`; `{"set_intros": {"1": "a"}, "outro": "o", "context": "", "mentioned_songs": []}` (or minimal valid shape).
- `tests/test_pipeline.py` `SYNTH_RESPONSE` (~line 40): drop `"intro"` and `"set_break_notes"`; `set_intros` keeps only non-encore keys `{"1": "...", "2": "..."}`. Adjust any downstream assertions that expected an encore lead-in.
- `tests/test_voice_pipeline.py` `SYNTH_RESPONSE` (~line 37): same — drop `"intro"`/`"set_break_notes"`, remove the `"encore"` key from `set_intros`. Update the dj-audio filename list (~line 105) to `["set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"]` and `manifest["dj_audio"]["set_intros"]` to the two non-encore keys.

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/llama/models.py src/llama/stages/synthesize.py src/llama/prompts/synthesize.md tests/
git commit -m "feat: combined per-set DJ lead-ins, encore folds into outro (producer side)"
```

---

### Task 3: Docs

Bring live docs in line with the new segment set and manifest shape. (Dated plans/specs stay as historical record.)

**Files:**
- Modify: `README.md`
- Modify: `docs/station-brief.md`
- Modify: `src/llama/config.py` (the `[tts]` template comment)
- Modify: `CLAUDE.md` (if it enumerates the old segment set)

- [ ] **Step 1: Update `docs/station-brief.md`**

- The `set_breaks` JSON example (~line 112-113): drop `note_index`/`audio`, leaving `{ "after_track": 8 }`.
- The prose about playing `set_breaks[i].audio` during a break and the "`dj_audio.set_breaks` is parallel…" note (~lines 197-199): rewrite to describe DJ audio as `dj_audio.set_intros[<set>]` played *before* each set and `dj_audio.outro` after the final music; a `set_breaks` entry is now a physical marker only.

- [ ] **Step 2: Update `README.md`**

- "one break note per entry in `manifest.set_breaks`" (~line 313) and any dj-audio segment enumeration: describe one lead-in per non-encore set (`set<key>-intro`), an unannounced encore, and a closing `99-outro`.

- [ ] **Step 3: Update `src/llama/config.py` `[tts]` comment**

Change the segment list from `(00-intro, set<key>-intro, break<N>, 99-outro)` to `(one set<key>-intro per set, then 99-outro)`. Keep the "one clip per DJ segment / manifest dj_audio block" framing.

- [ ] **Step 4: Update `CLAUDE.md` if needed**

Grep for `00-intro`/`break<N>`/`set-break` segment enumerations in `CLAUDE.md`; if present, update to the new set. If absent, no change.

- [ ] **Step 5: Verify and commit**

Run: `pytest -q` (docs-only, still green) and eyeball `git diff`.

```bash
git add README.md docs/station-brief.md src/llama/config.py CLAUDE.md
git commit -m "docs: describe consolidated DJ segments (lead-in per set + outro)"
```

---

## Self-Review

**Spec coverage:** DJNotes/DJAudio/SetBreak reshape → Tasks 1-2; segment files → Task 1 Step 5; prompt → Task 2 Step 5; guard → Task 2 Step 4; render → Task 2 Step 4; manifest → Task 1 Step 4; no-migration → Global Constraints; docs → Task 3; invariant test → Task 2 Step 1. All covered.

**Placeholder scan:** No TBD/TODO; every code step shows the code. Test-body edits reference exact fixtures and line anchors.

**Type consistency:** `DJAudio(set_intros, outro)`, `SetBreak(after_track)`, `DJNotes(context, set_intros, outro, mentioned_songs)`, `_segment_texts` signature, and `factual_guard`/`render_notes_md` bodies are consistent across tasks. Task 1 leaves `DJNotes` intact (green); Task 2 removes its fields only after all consumers stopped reading them.
