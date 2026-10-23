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


# --- Checkpoint B ruling 5 (slice 5 shapes) and final review M-6 --------------------------

def _run_a(title, artist, source="tags"):
    out, notes, changed = cosmetic_strip([_t(title, source)], artist=artist)
    return out[0].title


def test_strip_leaving_an_empty_or_edited_bracket_pair_is_declined():
    # M-6: `Esau (s2t01)` would leave `Esau ()`; zentricksters-2002-12-31 (`zt2002-12-31.SHNF`)
    # tags d2t010 `Banks of the Ohio (actually d2t10)`, which would leave `(actually )`.
    assert _run("Esau (s2t01)") == ("Esau (s2t01)", [], [])
    assert _run("Banks of the Ohio (actually d2t10)") == (
        "Banks of the Ohio (actually d2t10)", [], [])
    assert _run("Song [d1t02]")[0] == "Song [d1t02]"
    # A bracket pair the strip does not touch is kept as it was.
    assert _run("Greensky Bluegrass - d2t04-Booty Jam(Bend Over)")[0] == (
        "Greensky Bluegrass - Booty Jam(Bend Over)")
    assert _run("[05:12] Song")[0] == "Song"


def test_leading_artist_prefix_stripped_greenskybluegrass_2013_05_04():
    # greenskybluegrass-2013-05-04 (`GSBG2013-05-04`, creator `Greensky Bluegrass`), verbatim
    # tags.
    assert _run_a("Greensky Bluegrass - d2t07-In Control", "Greensky Bluegrass") == "In Control"
    assert _run_a("Greensky Bluegrass - d1t02-Dustbowl Overtures",
                  "Greensky Bluegrass") == "Dustbowl Overtures"
    assert _run_a("greensky  bluegrass - Leap Year", "Greensky Bluegrass") == "Leap Year"
    # Only the show's own artist, under fuzzy_norm_title equality; no artist, no strip.
    assert _run_a("Railroad Earth - Leap Year", "Greensky Bluegrass") == (
        "Railroad Earth - Leap Year")
    assert _run_a("Greensky - Leap Year", "Greensky Bluegrass") == "Greensky - Leap Year"
    assert _run("Greensky Bluegrass - Leap Year")[0] == "Greensky Bluegrass - Leap Year"
    assert _run_a("Greensky Bluegrass - ", "Greensky Bluegrass") == "Greensky Bluegrass -"


def test_trailing_h2_recorder_suffix_stripped_lotus_2008_02_07():
    # lotus-2008-02-07 (`Lotus2008-02-07`), verbatim tags.
    assert _run("d01t01 Lucid Awakening H2")[0] == "Lucid Awakening"
    assert _run("d01t05 Sid H2")[0] == "Sid"
    # Exactly the token `H2` after whitespace at the end.
    for t in ["Song H20", "SongH2", "Song h2", "H2 Song", "Song H2O"]:
        assert _run(t)[0] == t, t


def test_leading_encore_dash_stripped_gratefuldead_1974_10_18():
    # gratefuldead-1974-10-18 (`gd1974-10-18.111459.gems.BOSWELL-SMITH.flac24`) #24, verbatim.
    assert _run("5:46] Encore- U.S.Blues")[0] == "U.S.Blues"
    assert _run("Encore - Johnny B. Goode")[0] == "Johnny B. Goode"
    assert _run("Encore- Ripple")[0] == "Ripple"
    # `E: ` stays, as the spec has it; a bare `Encore` or `Encore:` is not this shape.
    for t in ["E: Ripple", "Encore: Ripple", "Encore", "Encore-Ripple"]:
        assert _run(t)[0] == t, t


def test_new_shapes_keep_the_acceptability_test():
    # The result must still be non-empty, real or 2a, and not a placeholder.
    assert _run("Encore - Track 03")[0] == "Encore - Track 03"
    assert _run("Track 03 H2")[0] == "Track 03 H2"
    assert _run_a("Lotus - tmp", "Lotus") == "Lotus - tmp"
