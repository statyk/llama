from llama.manifest import build_manifest, m3u_text
from llama.models import DJNotes, ManifestTrack, Show, Track


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        tracks=[Track(index=i, set=s, title=t, filename=f"f{i}", title_source="tags")
                for i, (s, t) in enumerate(
                    [("1", "Morning Dew"), ("2", "Dark Star"), ("encore", "Johnny B. Goode")], 1)],
        set_breaks=[1, 2], lineage="SBD > DAT", source_url="https://archive.org/details/gd73",
    )


def make_notes():
    return DJNotes(context="Peak 73", intro="i", outro="o",
                   set_intros={"1": "a", "2": "b", "encore": "c"},
                   set_break_notes=["x", "y"])


def make_packaged():
    return [
        ManifestTrack(index=1, set="1", title="Morning Dew", filename="01 - Morning Dew.mp3",
                      duration_sec=600.0),
        ManifestTrack(index=2, set="2", title="Dark Star", filename="02 - Dark Star.mp3",
                      duration_sec=1800.0, segue=True),
        ManifestTrack(index=3, set="encore", title="Johnny B. Goode",
                      filename="03 - Johnny B. Goode.mp3", duration_sec=300.0),
    ]


def test_build_manifest():
    m = build_manifest(make_show(), make_notes(), make_packaged())
    assert m.schema_version == 1
    assert m.show == {"artist": "Grateful Dead", "date": "1973-06-10",
                      "venue": "RFK Stadium", "city": "Washington, DC", "context": "Peak 73"}
    assert m.source["identifier"] == "gd73" and m.source["lineage"] == "SBD > DAT"
    assert m.source["performance_id"] == "GratefulDead/1973-06-10"
    assert m.total_duration_sec == 2700.0
    assert m.set_durations_sec == {"1": 600.0, "2": 1800.0, "encore": 300.0}
    assert [(b.after_track, b.note_index) for b in m.set_breaks] == [(1, 0), (2, 1)]


def test_m3u_text():
    text = m3u_text(["01 - Morning Dew.mp3", "02 - Dark Star.mp3"])
    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "audio/01 - Morning Dew.mp3"
    assert text.endswith("\n")
