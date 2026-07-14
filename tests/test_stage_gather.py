import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Candidate, RecordingSummary
from llama.stages.gather import run_gather
from llama.workspace import ShowWorkspace

FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"


class StubIA:
    def __init__(self, md=None):
        self.md = md or json.loads(FIXTURE.read_text())

    def metadata(self, identifier):
        return self.md


def make_candidate():
    return Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
        date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        recordings=[RecordingSummary(identifier=IDENT)],
    )


def test_gather_builds_show_from_fixture(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.artist == "Grateful Dead"
    assert [t.title for t in show.tracks] == [
        "Morning Dew", "China Cat Sunflower", "I Know You Rider",
        "Dark Star", "Eyes of the World", "Johnny B. Goode",
    ]
    # d3t01 has no tag title -> resolved from parsed setlist
    assert show.tracks[5].title_source == "setlist"
    assert show.tracks[1].segue is True
    assert [t.set for t in show.tracks] == ["1", "1", "1", "2", "2", "encore"]
    assert show.set_breaks == [3, 5]
    assert any(e["filename"] == "FOLLOW-ME @BYPIKENO.mp3" for e in show.excluded_files)
    assert show.needs_review is False
    assert show.source_url.endswith(IDENT)
    assert sws.show.exists() and sws.reviews.exists()
    assert len(json.loads(sws.reviews.read_text())) == 2


def test_gather_llm_fallback_on_unparseable_description(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "An amazing night of music, seeded with love."
    fallback = json.dumps({
        "items": [
            {"title": t, "normalized": t.lower(), "set": s, "segue": g}
            for t, s, g in [
                ("Morning Dew", "1", False), ("China Cat Sunflower", "1", True),
                ("I Know You Rider", "1", False), ("Dark Star", "2", True),
                ("Eyes of the World", "2", False), ("Johnny B. Goode", "encore", False),
            ]
        ],
        "confidence": "medium",
    })
    sws = ShowWorkspace(tmp_path / "show")
    fake = FakeProvider(completes=[fallback])
    show = run_gather(sws, StubIA(md), fake, make_candidate(), IDENT)
    assert fake.calls and fake.calls[0][0] == "complete"
    assert show.tracks[5].title == "Johnny B. Goode"


def test_gather_flags_unresolved(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    for f in md["files"]:
        f.pop("title", None)
    sws = ShowWorkspace(tmp_path / "show")
    # empty description -> no LLM fallback attempted -> unresolved titles flagged
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.needs_review is True
    assert any("unresolved" in f for f in show.review_flags)
