from llama import siblings
from llama.desc_list import DescList, clean_entries, clean_one
from llama.models import ParsedSetlist, SetlistItem, Track
from llama.songs import GD_SHORTHAND
from llama.title_hygiene import (
    AGREEMENT_FLOOR,
    INDEPENDENT_SOURCES,
    adjacent_duplicate,
    agreement_share,
    agrees,
    duplicate,
    judge,
    position_agreement,
    tape_disagreement,
    wholly_untagged,
    written_duration_mismatch,
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


# ---- Task 5: checks 2 and 3, written durations, agreement, wholly untagged ----

def _t(title, source="tags", dur=300.0, n=1):
    return Track(index=n, set="1", filename=f"f{n}.mp3", title=title, title_source=source,
                 duration_sec=dur)


def _tracks(*titles, source="tags", durs=None):
    return [_t(t, source, (durs[i] if durs else 300.0), i + 1) for i, t in enumerate(titles)]


def _dl(*raws):
    return DescList("numbered", tuple(raws), tuple(clean_entries(list(raws))),
                    tuple(0 for _ in raws), ())


def _canon(*titles):
    return ParsedSetlist(items=[SetlistItem(title=t, normalized=t.lower(), set="1")
                                for t in titles], confidence="high")


def test_check2_finds_shift_signature():
    tr = _tracks("Bertha", "Unresolved Thing")
    tr[1] = _t("", "unresolved", n=2)
    assert adjacent_duplicate({1: "Bertha"}, tr) == (1, "Bertha", "Bertha")
    ft = [_t("Tuning"), _t("", "unresolved", n=2)]
    assert adjacent_duplicate({1: "Tuning"}, ft) is None


def test_check2_neighbour_is_a_candidate_too():
    # darkstarorchestra-2004-08-31 shape
    tr = [_t("", "unresolved", n=1), _t("", "unresolved", n=2)]
    assert adjacent_duplicate({0: "Jam", 1: "Jam"}, tr) == (0, "Jam", "Jam")


def test_check3_disagreement_declines():
    # gracepotterandthenocturnals-2009-07-26: the list opens with `intro`, so the
    # tagged tracks sit one position off the entries.
    dl = _dl("intro", "Some Kind of Ride", "Joey", "Tooth Brush and My Table >")
    tr = _tracks("Some Kind of Ride", "Joey", "Tooth Brush and My Table >", "Big White Gate")
    assert tape_disagreement(tr, dl)[0] == 0
    ok = _dl("Some Kind of Ride", "Joey", "Tooth Brush and My Table >", "Big White Gate")
    assert tape_disagreement(tr, ok) is None


def test_filler_tag_against_song_entry_disagrees():
    assert position_agreement(_t("Tuning"), clean_one("Bertha")) == "disagree"
    assert position_agreement(_t("Bertha"), clean_one("Tuning")) == "disagree"


def test_filler_against_filler_is_neutral():
    assert position_agreement(_t("Tuning"), clean_one("Banter")) == "neutral"


def test_setlist_gap_title_is_neutral():
    for src in ("setlist-gap", "setlist", "unresolved", "desc-position"):
        assert position_agreement(_t("Bertha", src), clean_one("Dark Star")) == "skip"
    assert position_agreement(_t("Bertha", "override"), clean_one("Dark Star")) == "disagree"


def test_check3_runs_on_cleaned_copies():
    # umphreysmcgee-2004-03-17
    tr = _tracks("Joel Piano Solo (02:05)")
    assert tape_disagreement(tr, _dl("piano solo^")) is None


def test_check3_agrees_across_ampersand_and_curly_apostrophe():
    tr = _tracks("Me & My Uncle", "Truckin'")
    assert tape_disagreement(tr, _dl("Me &amp; My Uncle", "Truckin\u2019")) is None


def test_check3_takes_no_aliases():
    tr = _tracks("China Cat Sunflower")
    assert tape_disagreement(tr, _dl("Chinacat")) is not None
    dl = _dl("Chinacat")
    assert agreement_share(dl, _canon("China Cat Sunflower"), GD_SHORTHAND) == 1.0
    assert agreement_share(dl, _canon("China Cat Sunflower"), {}) == 0.0


def test_filler_marked_entry_judged_on_its_text():
    assert position_agreement(_t("Dark Star"), clean_one("Filler: Dark Star")) == "agree"
    assert position_agreement(_t("Bertha"), clean_one("Filler: Dark Star")) == "disagree"
    assert position_agreement(_t("Tuning"), clean_one("Filler: Tuning")) == "neutral"


def test_written_durations_need_half_the_list():
    tr = _tracks("a", "b", "c", "d", "e", durs=[100.0] * 5)
    two = _dl("A (5:00)", "B (5:00)", "C", "D", "E")
    three = _dl("A (5:00)", "B (5:00)", "C (5:00)", "D", "E")
    assert written_duration_mismatch(tr, two) is None
    assert written_duration_mismatch(tr, three) == (0, 100.0, 300.0)


def test_written_tolerance_scales_with_length():
    def mm(file, written):
        m, s = divmod(written, 60)
        return written_duration_mismatch(_tracks("a", durs=[float(file)]), _dl(f"A ({m}:{s:02d})"))
    assert mm(655, 600) is None
    assert mm(661, 600) is not None
    assert mm(136, 120) is not None
    assert mm(135, 120) is None


def test_written_duration_check_skips_missing_file_lengths():
    tr = [_t("a", dur=None, n=1), _t("b", dur=300.0, n=2)]
    assert written_duration_mismatch(tr, _dl("A (5:00)", "B (5:00)")) is None
    tr2 = [_t("a", dur=None, n=1), _t("b", dur=100.0, n=2)]
    assert written_duration_mismatch(tr2, _dl("A (5:00)", "B (5:00)")) == (1, 100.0, 300.0)


def test_agreement_share():
    dl = _dl("One Way", "Two Way", "Three Way", "Four Way", "Five Way")
    c = _canon("One Way", "Two Way", "Three Way", "Four Way", "Other Song")
    assert agreement_share(dl, c, {}) == 0.8
    sc = _canon("China Cat Sunflower")
    assert agreement_share(_dl("Chinacat"), sc, {}) == 0.0
    assert agreement_share(_dl("Chinacat"), sc, GD_SHORTHAND) == 1.0
    assert agreement_share(_dl("J"), _canon("Jack Straw"), {}) == 0.0
    assert agreement_share(dl, _canon(), {}) is None
    assert agreement_share(_dl("Tuning"), c, {}) is None  # no song-like entries


def test_agreement_exactly_at_floor_passes():
    dl = _dl("One Way", "Two Way")
    share = agreement_share(dl, _canon("One Way", "Other Song"), {})
    assert share == 0.5
    assert not share < AGREEMENT_FLOOR


def test_wholly_untagged_predicate():
    assert wholly_untagged(["Bertha", "Tuning", ""], frozenset())
    assert not wholly_untagged(["Bertha", "Dark Star"], frozenset())
    assert wholly_untagged(["Bertha", "Dark Star"], frozenset({1}))
    assert wholly_untagged(["Tuning", "Banter"], frozenset())
