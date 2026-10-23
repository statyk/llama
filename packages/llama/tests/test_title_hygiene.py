from llama import siblings
from llama.desc_list import clean_one
from llama.title_hygiene import (
    INDEPENDENT_SOURCES,
    agrees,
    duplicate,
    judge,
)


def _j(raw, *, track_no=5, first=False, stem="gd73-06-10d1t05", own_core="", norms=None):
    return judge(clean_one(raw), track_no=track_no, first=first, stem=stem,
                 own_core=own_core, metadata_norms=norms or set())


def test_spec_pass_fixtures():
    for raw in ["2:45 AM", "09-15-00", "12.28.99", "42", "405", "118", "420", "J", "1 in 7"]:
        assert _j(raw).ok, raw


def test_spec_decline_fixtures():
    for raw in ["?", "??,  [4:47]", "01.", "01-"]:
        h = _j(raw)
        assert (h.ok, h.scope) == (False, "track"), raw
    h = _j('"Set" 1:')
    assert (h.scope, h.check) == ("show", "hygiene:trailing colon")
    for raw in ["Disc 1, Track 10", "s1t07:", "w/ Eric Johnson", "Fruit Bats opened",
                "soulive2012-02-24-d1t01"]:
        h = _j(raw)
        assert (h.ok, h.scope) == (False, "show"), raw
    assert _j("Unknown").scope == "track"


def test_bare_number_rules():
    assert _j("5", track_no=5).scope == "track"
    assert _j("05", track_no=9).scope == "track"
    assert _j("42", track_no=7).ok
    assert _j("07", track_no=7, own_core="07").ok
    assert _j("4", track_no=5).ok


def test_metadata_hit_scope():
    norms = {"railroad earth"}
    h = _j("Railroad Earth", first=True, norms=norms)
    assert (h.scope, h.check) == ("show", "hygiene:banner")
    h = _j("Railroad Earth", first=False, norms=norms)
    assert (h.scope, h.check) == ("track", "metadata")


def test_equal_to_own_stem_declines_show():
    h = _j("gd73-06-10d1t05", stem="gd73-06-10d1t05")
    assert (h.scope, h.check) == ("show", "hygiene:filename residue")


def test_filler_entry_is_per_track():
    h = _j("Filler: Tuning")
    assert (h.scope, h.check) == ("track", "filler entry")


def test_short_core_compares_by_equality_only():
    assert agrees("J", "Jack Straw") is False
    assert agrees("J", "J") is True
    assert agrees("Sailin On", "Sailing On") is True


def test_duplicate_comparator():
    assert duplicate("Dark Star", "Dark Star Jam") is True
    assert duplicate("Truckin'", "Truckin' Jam") is False
    assert duplicate("Sailing On", "Sailin On") is False
    assert duplicate("Tuning", "Tuning") is False


def test_independent_sources_is_not_the_siblings_set():
    """(pin)"""
    assert INDEPENDENT_SOURCES - siblings.INDEPENDENT_TITLE_SOURCES == {"sibling-align"}
    assert siblings.INDEPENDENT_TITLE_SOURCES == {"tags", "sibling-format", "override"}
