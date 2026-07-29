from pathlib import Path

import pytest

from herder import FakeProvider, TaskFailed
from llama.models import Show, Track
from llama.stages.research import run_research
from llama.workspace import ShowWorkspace

REPORT = ("## Reputation\nLegendary.\n## Performance highlights\nDew.\n"
          "## Context\nPeak 73.\n## Recording notes\nSBD.")


def make_show():
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73",
                artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
                tracks=[Track(index=1, set="1", title="Morning Dew",
                              filename="d1t01.mp3", title_source="tags")])


def test_research_renders_and_writes(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    fake = FakeProvider(researches=[REPORT])
    out = run_research(sws, fake, make_show(), dossier="winnow says: great")
    assert out.startswith("## Reputation")
    assert sws.research.read_text() == out
    brief = fake.calls[0][1]
    assert "1973-06-10" in brief and "winnow says: great" in brief and "Morning Dew" in brief


def test_research_skips_when_exists(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    run_research(sws, FakeProvider(researches=[REPORT]), make_show(), dossier="d")
    assert run_research(sws, FakeProvider(), make_show(), dossier="d") == REPORT


def test_research_rejects_narration_and_writes_nothing(tmp_path: Path):
    # A headless backend that hands off to a background workflow returns
    # narration, not the report - the stage must fail, not ship it.
    sws = ShowWorkspace(tmp_path / "s")
    narration = "The research workflow is running in the background - stand by."
    fake = FakeProvider(researches=[narration] * 3)
    with pytest.raises(TaskFailed) as exc:
        run_research(sws, fake, make_show(), dossier="d")
    assert exc.value.raw_output == narration
    assert not sws.research.exists()
