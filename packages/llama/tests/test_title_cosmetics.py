"""Title hygiene slice 5: cosmetic junk stripping (plan Task 10)."""

from llama.models import Track
from llama.title_cosmetics import STRIP_SOURCES, cosmetic_strip


def _t(title, source="tags", i=1):
    return Track(index=i, set="1", title=title, filename=f"f{i}.mp3", title_source=source)


def _run(title, source="tags"):
    out, notes, changed = cosmetic_strip([_t(title, source)])
    return out[0].title, notes, changed


def test_strips_leading_timestamp_shapes():
    assert _run("06:58 - Who Took the Happiness Out?")[0] == "Who Took the Happiness Out?"
    assert _run("16:34) Waiting For the Punchline")[0] == "Waiting For the Punchline"
    assert _run("[05:12] Song")[0] == "Song"
    assert _run("1:02:03 - Song")[0] == "Song"


def test_strips_embedded_stems_and_tails():
    assert _run("Greensky Bluegrass - d2t07-In Control")[0] == "Greensky Bluegrass - In Control"
    assert _run("Song.wav")[0] == "Song"
    assert _run("Song.flac:" + "0123456789abcdef" * 2)[0] == "Song"
    assert _run("Song.flac")[0] == "Song"


def test_note_and_changed_positions():
    tracks = [_t("Keep", i=1), _t("Song.wav", i=2)]
    out, notes, changed = cosmetic_strip(tracks)
    assert changed == [1]
    assert notes == ["cosmetic title strip: track 2 'Song.wav' -> 'Song'"]
    assert tracks[1].title == "Song.wav"  # inputs not mutated


def test_bare_time_word_titles_are_never_stripped():
    for t in ["4:20 Polka", "8 Cylinders", "16 Military Wives", "20 Eyes", "3 AM",
              "1 Samuel 15:23", "2:45 AM"]:
        assert _run(t) == (t, [], [])


def test_encore_and_set_markers_kept():
    for t in ["E: Ripple", "S2: Song", "set1: Song"]:
        assert _run(t)[0] == t


def test_never_override_or_unresolved():
    assert _run("06:58 - X", "override")[0] == "06:58 - X"
    assert _run("phish1995-12-31d2t05.flac", "unresolved")[0] == "phish1995-12-31d2t05.flac"
    assert "override" not in STRIP_SOURCES and "unresolved" not in STRIP_SOURCES


def test_residue_only_title_left_alone():
    assert _run("d&co2017.06.17.mg21.set01t01")[0] == "d&co2017.06.17.mg21.set01t01"


def test_other_sources_are_stripped():
    for s in ["sibling-format", "setlist", "setlist-gap", "desc-position", "sibling-align"]:
        assert _run("Song.wav", s)[0] == "Song"


def test_keep_rule_refuses_placeholder_results():
    for t in ["track01.flac", "d1t01 Track 1", "06:58 - Track 03", "tmp.wav",
              "gd1977-05-08.sbd.flac"]:
        assert _run(t)[0] == t, t


def test_keep_rule_2a_arm_accepts_short_tag_and_vetoes_junk():
    assert _run("06:58 - 42")[0] == "42"
    assert _run("06:58 - 12/31/95")[0] == "06:58 - 12/31/95"
