import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import DJNotes, Show, Track
from llama.stages.synthesize import factual_guard, run_synthesize
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
        "intro": "Tonight: the Dead at RFK.",
        "set_intros": {"1": "Opens with Morning Dew.", "2": "A monumental Dark Star.",
                       "encore": "Johnny B. Goode sendoff."},
        "set_break_notes": ["That was set one.", "That was set two."],
        "outro": "Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "Dark Star", "Johnny B. Goode"],
    }
    d.update(overrides)
    return d


def test_guard_passes_clean_notes():
    assert factual_guard(DJNotes(**notes_dict()), make_show()) == []


def test_guard_catches_fabrications_and_mismatches():
    bad = DJNotes(**notes_dict(
        mentioned_songs=["Morning Dew", "Werewolves of London"],
        set_intros={"1": "x", "2": "y", "3": "huh", "encore": "z"},
        set_break_notes=["only one"],
    ))
    problems = factual_guard(bad, make_show())
    assert any("Werewolves of London" in p for p in problems)
    assert any("nonexistent set" in p for p in problems)
    assert any("count mismatch" in p for p in problems)


def test_synthesize_writes_notes_and_md(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    notes = run_synthesize(sws, fake, show, research_md="# R", reviews=[{"reviewbody": "great"}])
    assert notes.intro.startswith("Tonight")
    assert sws.dj_notes_json.exists()
    md = sws.dj_notes_md.read_text()
    assert "## Show intro" in md and "## Encore intro" in md and "## Set break 1" in md
    # clean notes: show untouched
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_synthesize_guard_failure_marks_needs_review(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[json.dumps(notes_dict(mentioned_songs=["Fake Song"]))])
    run_synthesize(sws, fake, show, research_md="", reviews=[])
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("Fake Song" in f for f in saved["review_flags"])
