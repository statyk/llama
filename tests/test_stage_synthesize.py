import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.llm.tasks import load_prompt
from llama.models import DJNotes, Overrides, Show, Track
from llama.presenters import Presenter
from llama.stages.synthesize import (
    NEUTRAL_STYLE,
    factual_guard,
    narration_note,
    persona_style,
    render_notes_md,
    run_synthesize,
)
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


def notes_dict(**overrides):
    d = {
        "context": "Peak 1973 tour",
        "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                       "2": "A monumental Dark Star."},
        "outro": "Johnny B. Goode sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "Dark Star", "Johnny B. Goode"],
    }
    d.update(overrides)
    return d


def test_guard_passes_clean_notes():
    assert factual_guard(DJNotes(**notes_dict()), make_show()) == []


def test_guard_catches_fabrications_and_mismatches():
    bad = DJNotes(**notes_dict(
        mentioned_songs=["Morning Dew", "Werewolves of London"],
        set_intros={"1": "x", "2": "y", "3": "huh"},
    ))
    problems = factual_guard(bad, make_show())
    assert any("Werewolves of London" in p for p in problems)
    assert any("nonexistent" in p and "3" in p for p in problems)


def test_guard_rejects_encore_lead_in():
    # Option A: the encore gets no lead-in, so an "encore" key is a fault.
    notes = DJNotes(**notes_dict(set_intros={"1": "a", "2": "b", "encore": "c"}))
    problems = factual_guard(notes, make_show())
    assert any("encore" in p for p in problems)


def test_guard_requires_every_non_encore_set():
    notes = DJNotes(**notes_dict(set_intros={"1": "a"}))  # missing set 2
    assert any("missing set intros" in p for p in factual_guard(notes, make_show()))


def make_single_set_show():
    show = make_show()
    show.tracks = [Track(index=1, set="1", title="Morning Dew",
                         filename="a.mp3", title_source="tags")]
    show.set_breaks = []
    return show


def single_set_notes(**overrides):
    d = notes_dict(set_intros={"1": "Opens with Morning Dew."},
                   mentioned_songs=["Morning Dew"])
    d.update(overrides)
    return d


def test_guard_catches_set_count_claim_in_prose():
    # The steepcanyonrangers-2002-07-07 case: structurally consistent notes
    # whose lead-in prose still claims two sets against a single-set structure.
    notes = DJNotes(**single_set_notes(
        set_intros={"1": "They actually played two sets that day, and both sets cook."}))
    problems = factual_guard(notes, make_single_set_show())
    assert problems == ["dj notes claim 2 sets but structure has 1"]


def test_guard_catches_set_count_claim_with_adjective():
    notes = DJNotes(**single_set_notes(outro="Both festival sets, young band."))
    problems = factual_guard(notes, make_single_set_show())
    assert problems == ["dj notes claim 2 sets but structure has 1"]


def test_guard_catches_ordinal_set_claim():
    notes = DJNotes(**notes_dict(outro="The third set peak says it all."))
    problems = factual_guard(notes, make_show())
    assert problems == ["dj notes mention the third set but structure has 2 sets"]


def test_guard_allows_consistent_set_count_prose():
    notes = DJNotes(**notes_dict(
        outro="Two sets plus an encore tonight, and the second set is huge."))
    assert factual_guard(notes, make_show()) == []


def test_guard_ignores_sets_of_phrases():
    notes = DJNotes(**single_set_notes(
        outro="Two sets of fiddle tunes bookend the show."))
    assert factual_guard(notes, make_single_set_show()) == []


def test_notes_md_one_lead_in_per_set_then_outro():
    # One lead-in section per non-encore set, in order, then the outro. The
    # encore has no lead-in (it folds into set 2's music); the outro recaps it.
    md = render_notes_md(DJNotes(**notes_dict()), make_show())
    headers = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert headers == ["## Set 1 lead-in", "## Set 2 lead-in", "## Outro"]


def test_segment_layout_has_no_adjacent_talk():
    # For a 2-sets-plus-encore show: one clip per non-encore set, then the
    # outro. No 00-intro, no break*, no encore lead-in.
    from llama.stages.package import _segment_texts

    show = make_show()
    stems = [s for s, _ in _segment_texts(DJNotes(**notes_dict()))]
    assert stems == ["set1-intro", "set2-intro", "99-outro"]
    non_encore = len({t.set for t in show.tracks if t.set != "encore"})
    assert len(stems) == non_encore + 1


def test_synthesize_writes_notes_and_md(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    notes = run_synthesize(sws, fake, show, research_md="# R", reviews=[{"reviewbody": "great"}])
    assert notes.set_intros["1"].startswith("Tonight")
    assert sws.dj_notes_json.exists()
    md = sws.dj_notes_md.read_text()
    assert "## Set 1 lead-in" in md and "## Set 2 lead-in" in md and "## Outro" in md
    # clean notes: show untouched
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_synthesize_retries_with_guard_feedback(tmp_path: Path):
    # Real case (Veneta '72): the LLM wrote an intro for nonexistent "set 5".
    # One corrective retry must fix it instead of holding the show.
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    bad = json.dumps(notes_dict(
        set_intros={"1": "a", "2": "b", "5": "??"}))
    fake = FakeProvider(completes=[bad, json.dumps(notes_dict())])
    notes = run_synthesize(sws, fake, show, research_md="", reviews=[])
    assert set(notes.set_intros) == {"1", "2"}
    assert json.loads(sws.show.read_text())["needs_review"] is False
    retry_prompt = fake.calls[1][1]
    assert "fact-check" in retry_prompt and "set: 5" in retry_prompt


def test_synthesize_guard_failure_marks_needs_review(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    bad = json.dumps(notes_dict(mentioned_songs=["Fake Song"]))
    fake = FakeProvider(completes=[bad, bad])  # retry also fails
    run_synthesize(sws, fake, show, research_md="", reviews=[])
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("Fake Song" in f for f in saved["review_flags"])


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
    assert "You are Casey" in style
    assert "You are male; refer to yourself accordingly." in style
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


def make_show_one_set():
    return Show(performance_id="X/2003-04-19", identifier="x", artist="X",
                date="2003-04-19",
                tracks=[Track(index=1, set="1", title="Unknown 1",
                              filename="a.mp3", title_source="unresolved")])


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
