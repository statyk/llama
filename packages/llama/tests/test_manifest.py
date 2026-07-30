import json

from llama.manifest import build_manifest, m3u_text
from llama.models import ManifestTrack, Show, Track


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        tracks=[Track(index=i, set=s, title=t, filename=f"f{i}", title_source="tags")
                for i, (s, t) in enumerate(
                    [("1", "Morning Dew"), ("2", "Dark Star"), ("encore", "Johnny B. Goode")], 1)],
        set_breaks=[1, 2], lineage="SBD > DAT", source_url="https://archive.org/details/gd73",
    )


def make_packaged():
    return [
        ManifestTrack(index=1, set="1", title="Morning Dew", filename="01 - Morning Dew.mp3",
                      duration_sec=600.0),
        ManifestTrack(index=2, set="2", title="Dark Star", filename="02 - Dark Star.mp3",
                      duration_sec=1800.0, segue=True),
        ManifestTrack(index=3, set="encore", title="Johnny B. Goode",
                      filename="03 - Johnny B. Goode.mp3", duration_sec=300.0),
    ]


def make_briefing():
    from llama.models import ManifestBriefing
    return ManifestBriefing(narration="full", vetted=False)


def test_build_manifest():
    m = build_manifest(make_show(), make_packaged(),
                       briefing=make_briefing(), context="Peak 73")
    assert m.schema_version == 3
    assert m.show == {"artist": "Grateful Dead", "date": "1973-06-10",
                      "venue": "RFK Stadium", "city": "Washington, DC", "context": "Peak 73"}
    assert m.source["identifier"] == "gd73" and m.source["lineage"] == "SBD > DAT"
    assert m.source["performance_id"] == "GratefulDead/1973-06-10"
    assert m.total_duration_sec == 2700.0
    assert m.set_durations_sec == {"1": 600.0, "2": 1800.0, "encore": 300.0}
    assert [b.after_track for b in m.set_breaks] == [1, 2]


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
    from llama.models import ManifestBriefing
    m = build_manifest(make_show(), [], briefing=ManifestBriefing(
        narration="full", vetted=False))
    assert m.briefing.narration == "full"


def test_m3u_text():
    text = m3u_text(["01 - Morning Dew.mp3", "02 - Dark Star.mp3"])
    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "audio/01 - Morning Dew.mp3"
    assert text.endswith("\n")


def test_build_manifest_dj_notes_and_dj_audio_default_none():
    # llama never writes dj_notes/dj_audio anymore (emcee-written passthrough);
    # build_manifest's output must default them to None.
    show = Show(performance_id="p", identifier="i", artist="a", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="t", filename="f.mp3", title_source="tags")],
                set_breaks=[1])
    packaged = [ManifestTrack(index=1, set="1", title="t", filename="01 - t.mp3", duration_sec=60.0)]
    m = build_manifest(show, packaged, briefing=make_briefing(), context="ctx",
                       research="research.md", reviews="reviews.md", research_vetted=True)
    assert m.schema_version == 3
    assert m.dj_notes is None
    assert m.dj_audio is None
    assert m.set_breaks[0].after_track == 1
    assert m.show["context"] == "ctx"
    assert m.research == "research.md" and m.research_vetted is True
