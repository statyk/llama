from llama.manifest import (
    broadcast_m3u_text,
    build_manifest,
    interleave_broadcast,
    m3u_text,
)
from llama.models import DJAudio, DJNotes, ManifestTrack, Show, Track


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
    return DJNotes(context="Peak 73", outro="o", set_intros={"1": "a", "2": "b"})


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
    m = build_manifest(make_show(), make_notes(), make_packaged(), context=make_notes().context)
    assert m.schema_version == 2
    assert m.show == {"artist": "Grateful Dead", "date": "1973-06-10",
                      "venue": "RFK Stadium", "city": "Washington, DC", "context": "Peak 73"}
    assert m.source["identifier"] == "gd73" and m.source["lineage"] == "SBD > DAT"
    assert m.source["performance_id"] == "GratefulDead/1973-06-10"
    assert m.total_duration_sec == 2700.0
    assert m.set_durations_sec == {"1": 600.0, "2": 1800.0, "encore": 300.0}
    assert [b.after_track for b in m.set_breaks] == [1, 2]


def test_m3u_text():
    text = m3u_text(["01 - Morning Dew.mp3", "02 - Dark Star.mp3"])
    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "audio/01 - Morning Dew.mp3"
    assert text.endswith("\n")


def make_dj_audio():
    return DJAudio(
        set_intros={"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        outro="dj-audio/99-outro.mp3",
    )


def test_interleave_broadcast_slots_leadins_and_outro():
    # Each set's lead-in precedes that set's first track; the encore (no
    # set_intros key) gets none; the outro closes.
    assert interleave_broadcast(make_packaged(), make_dj_audio()) == [
        "dj-audio/set1-intro.mp3",
        "audio/01 - Morning Dew.mp3",
        "dj-audio/set2-intro.mp3",
        "audio/02 - Dark Star.mp3",
        "audio/03 - Johnny B. Goode.mp3",  # encore: plays straight into the outro
        "dj-audio/99-outro.mp3",
    ]


def test_broadcast_m3u_text_wraps_interleaved_paths():
    text = broadcast_m3u_text(make_packaged(), make_dj_audio())
    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "dj-audio/set1-intro.mp3"
    assert lines[2] == "audio/01 - Morning Dew.mp3"
    assert lines[-1] == "dj-audio/99-outro.mp3"
    assert text.endswith("\n")


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
    assert m.set_breaks[0].after_track == 1
    assert m.show["context"] == "ctx"
    assert m.research == "research.md" and m.research_vetted is True


def test_build_manifest_with_dj_audio():
    from llama.models import DJAudio

    dj_audio = DJAudio(
        set_intros={"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        outro="dj-audio/99-outro.mp3",
    )
    m = build_manifest(make_show(), make_notes(), make_packaged(), dj_audio=dj_audio)
    assert m.dj_audio == dj_audio
    assert [b.after_track for b in m.set_breaks] == [1, 2]


def test_build_manifest_without_dj_audio():
    m = build_manifest(make_show(), make_notes(), make_packaged())
    assert m.dj_audio is None
    assert [b.after_track for b in m.set_breaks] == [1, 2]
