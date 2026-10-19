"""placeholders: the fixed-a-priori junk classes of slices 2a/2b (spec 'Testing': near misses)."""
import pytest

from llama.placeholders import (is_date_like, is_junk_tag, is_placeholder, is_placeholder_title,
                                is_residue, is_timestamp, letters_after_residue, looks_like_filename,
                                recording_level_junk, starts_with_timestamp)


@pytest.mark.parametrize("s", ["Track 01", "track six", "Trac3", "Track ten", "Trk 7", "Tr-02", "Cut 3",
                               "tmp", "temp", "No Title", "Title", "TRACK  12"])
def test_placeholder_vocabulary(s):
    assert is_placeholder(s)


@pytest.mark.parametrize("s", ["Untitled", "Untitled #12", "Song #1", "1979", "Track", "Tracks of My Tears",
                               "Title Fight", "Temptation"])
def test_placeholder_near_misses(s):
    assert not is_placeholder(s)


@pytest.mark.parametrize("s, expected", [("27:36.27", True), ("05:27 -", True), ("[12:30]", True),
                                         ("07:22 - IB49", False), ("3AM", False), ("2001", False)])
def test_timestamp(s, expected):
    assert is_timestamp(s) is expected


@pytest.mark.parametrize("s, expected", [("07:22 - IB49", True), ("05:27", True), ("(1:02) Jam", True),
                                         ("3AM", False), ("2001", False), ("Jam 07:22", False)])
def test_starts_with_timestamp(s, expected):
    assert starts_with_timestamp(s) is expected


@pytest.mark.parametrize("s, expected", [("12-28-99", True), ("1999-12-28", True), ("28.12.1999", True),
                                         ("December 28", True), ("Dec 28, 1999", True), ("28 December", True),
                                         ("May 1977", True), ("7-11", False), ("1 in 7", False),
                                         ("I-55", False), ("1979", False), ("May", False)])
def test_date_like(s, expected):
    assert is_date_like(s) is expected


@pytest.mark.parametrize("s, expected", [("d1t02", True), ("t1", True), ("123456_01", True),
                                         ("gd73-06-10d1t04", True), ("FF", False), ("42", False),
                                         ("J", False), ("7-11", False)])
def test_filename_residue_shape(s, expected):
    assert looks_like_filename(s) is expected


def test_letters_after_residue():
    assert letters_after_residue("buckethead2004-06-04d2t05") == 0
    assert letters_after_residue("fIREHOSE 1992-02-19 t02") == 0
    assert letters_after_residue("Scarlet Begonias 1977-05-08") == 15   # the prefix is start-anchored
    assert letters_after_residue("sbd matrix remaster") == 0
    assert is_residue("buckethead2004-06-04d2t05") and not is_residue("1979") and not is_residue("")


@pytest.mark.parametrize("s, expected", [("Track 01", True), ("tmp", True), ("Trac3", True),
                                         ("27:36.27", True), ("buckethead2004-06-04d2t05", True),
                                         ("1979", False), ("1759", False), ("Song #1", False),
                                         ("Untitled", False), ("Untitled #12", False), ("Jam", False),
                                         ("", False), ("   ", False), ("Scarlet Begonias 1977-05-08", False)])
def test_is_placeholder_title(s, expected):
    assert is_placeholder_title(s) is expected


@pytest.mark.parametrize("s, expected", [("?", False), ("FF", False), ("J", False), ("42", False),
                                         ("7-11", False), ("I-55", False), ("1 in 7", False),
                                         ("Track 01", True), ("05:27", True), ("12-28-99", True),
                                         ("d1t02", True), ("t1", True), ("07:22 - IB49", True)])
def test_is_junk_tag_never_counts_letters(s, expected):
    assert is_junk_tag(s) is expected


def test_recording_level_junk():
    assert recording_level_junk(["tmp"] * 19, None)
    assert recording_level_junk(["Live at X", "live at x", "Live At X"], "Live at X")
    assert not recording_level_junk(["tmp", "tmp"], None)            # under 3 tracks
    assert not recording_level_junk(["Dew", "Dew", "Star"], None)
    assert recording_level_junk(["Dew", "Dew", "Dew"], "Dew")       # identical on three tracks IS the class


@pytest.mark.parametrize("s", ["Jam 12-31-99", "Master", "Matrix"])
def test_residue_class_demotes_the_ruled_limitation_cases(s):
    """Ruled (P5 residue over-demotion): these three ARE demoted -- the anchored
    prefix consumes `Jam` + a date; `master`/`matrix` are lineage tokens.
    Accepted as a documented limitation (demotion only leaves a track
    unresolved, so the show stays held). Pinned so a change is deliberate."""
    assert is_residue(s)
    assert is_placeholder_title(s)


def test_recording_level_junk_item_title_that_normalizes_to_nothing_never_matches():
    """An item title with no normalizable text (`---`) does not make every
    distinct empty-normalizing tag 'the item's own title'."""
    assert not recording_level_junk(["?", "!", "..."], "---")
    assert not recording_level_junk(["Dew", "Star", "Jam"], "   ")
