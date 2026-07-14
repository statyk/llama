from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Show, Track
from llama.stages.research import run_research
from llama.workspace import ShowWorkspace


def make_show():
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73",
                artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
                tracks=[Track(index=1, set="1", title="Morning Dew",
                              filename="d1t01.mp3", title_source="tags")])


def test_research_renders_and_writes(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    fake = FakeProvider(researches=["## Reputation\nLegendary."])
    out = run_research(sws, fake, make_show(), dossier="winnow says: great")
    assert out.startswith("## Reputation")
    assert sws.research.read_text() == out
    brief = fake.calls[0][1]
    assert "1973-06-10" in brief and "winnow says: great" in brief and "Morning Dew" in brief


def test_research_skips_when_exists(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    run_research(sws, FakeProvider(researches=["x"]), make_show(), dossier="d")
    assert run_research(sws, FakeProvider(), make_show(), dossier="d") == "x"
