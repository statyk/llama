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


# ---- Task 6: the untagged checks and the D decision (slice 2) ----

from llama.desc_list import read_numbered, read_parse  # noqa: E402
from llama.siblings import DonorTape, SiblingRow  # noqa: E402
from llama.title_hygiene import (  # noqa: E402
    DESC_POSITION,
    SHIFT_CHECKS,
    DDecision,
    apply_d,
    block_size_mismatch,
    d_notes,
    decide_d,
    is_self_filled,
    sibling_disagreement,
)

_EMPTY = ParsedSetlist(items=[], confidence="high")
_IDENTITY = lambda p: (p, frozenset())  # noqa: E731


def _u(n, filename=None, dur=300.0):
    return Track(index=n, set="1", filename=filename or f"x2001-01-01d1t{n:02d}.mp3", title="",
                 title_source="unresolved", duration_sec=dur)


def _blocked(blocks, *raws, boundaries=()):
    return DescList("numbered", tuple(raws), tuple(clean_entries(list(raws))), tuple(blocks),
                    tuple(boundaries))


def _d(tracks, dl, *, tag_titles=None, canonical=_EMPTY, norms=None, aliases=None,
       untagged=False, donor=None):
    return decide_d(tracks, dl, tag_titles=tag_titles or ["" for _ in tracks],
                    canonical=canonical, metadata_norms=norms or set(), aliases=aliases or {},
                    wholly_untagged=untagged, donor=donor or (lambda: None))


def test_shift_checks_are_every_show_level_name_not_hygiene():
    """(pin)"""
    assert SHIFT_CHECKS == frozenset({"adjacent duplicate", "tape agreement", "written durations",
                                      "block size", "sibling durations", "agreement"})


def test_d_fills_unresolved_and_never_touches_resolved():
    tr = [_t("Bertha", n=1), _u(2), _t("Sugaree", n=3), _u(4)]
    d = _d(tr, _dl("Bertha", "Jack Straw", "Sugaree", "Ripple"))
    assert d.fills == {1: "Jack Straw", 3: "Ripple"}
    assert d.failed == () and d.track_declines == {} and not d.shift
    out = apply_d(tr, d)
    assert [(t.title, t.title_source) for t in out] == [
        ("Bertha", "tags"), ("Jack Straw", DESC_POSITION), ("Sugaree", "tags"),
        ("Ripple", DESC_POSITION)]
    assert tr[1].title_source == "unresolved"  # input untouched


def test_d_never_touches_an_override():
    tr = [_t("My Own Title", "override", n=1), _u(2)]
    d = _d(tr, _dl("My Own Title", "Jack Straw"))
    assert d.fills == {1: "Jack Straw"}
    assert apply_d(tr, d)[0].title_source == "override"


def test_d_does_not_fire_without_count_match_or_unresolved():
    tr = [_u(1), _u(2), _u(3), _u(4)]
    assert _d(tr, _dl("A Song", "B Song", "C Song", "D Song", "E Song")) is None
    tagged = [_t("A Song", n=1), _t("B Song", n=2)]
    assert _d(tagged, _dl("A Song", "B Song")) is None


def test_d_may_fill_a_2b_demoted_position():
    tr = [_t("Bertha", n=1), _t("Sugaree", n=2), _u(3)]
    d = _d(tr, _dl("Bertha", "Sugaree", "Jack Straw"),
           tag_titles=["Bertha", "Sugaree", "Track 03"])
    assert d.fills == {2: "Jack Straw"}


def test_check2_one_duplicate_declines_every_fill():
    tr = [_t("Bertha", n=1), _u(2), _u(3), _u(4)]
    d = _d(tr, _dl("Bertha", "Bertha", "Jack Straw", "Ripple"))
    assert d.fills == {}
    assert d.failed[0][0] == "adjacent duplicate"
    assert d.shift


# rosehilldrive-2008-12-31 (rhd2008-12-31.akg483.flac16): description verbatim.
_RHD_DESC = (
    "Disc 1\n\n(05:12) 01-?\n(03:43) 02-Sneak Out\n(04:06) 03-Man On Fire\n(11:23) 04-Reptilian"
    " Blues\n(05:50) 05-One Night Stand\n(03:58) 06-Laughing in the Streets\n(08:10) 07-8th"
    " Wonder\n(01:46) 08-NYE Countdown\n\n(44:11) Disc 1 Total\n\nDisc 2\n\n(06:30) 01-Whole"
    " Lotta Love\n(04:44) 02-What is and What Should Never Be\n(06:35) 03-The Lemon Song\n"
    "(06:21) 04-Thank You\n(06:02) 05-Heartbreaker\n(03:33) 06-Living Loving Maid (She's Just"
    " a Woman)\n(05:02) 07-Ramble On\n(05:50) 08-Moby Dick\n(09:46) 09-Bring It on Home\n"
    "(01:41) 10-encore break\n(03:27) 11-?\n(05:13) 12-Do You Want to Get High\n(04:59)"
    " 13-I'm On to You\n\n(1:09:49) Disc 2 Total"
)
_RHD_FILES = [f"rhd2008-12-31.akg483.d1t{i}.mp3" for i in range(1, 9)] + [
    f"rhd2008-12-31.akg483.d2t{i:02d}.mp3" for i in range(1, 14)]
_RHD_DURS = [312, 223, 246, 682, 349, 238, 490, 106, 390, 284, 395, 381, 362, 213, 302, 350,
             586, 101, 206, 313, 299]


def test_slot_placeholders_decline_per_track():
    dl = read_parse(_RHD_DESC, artist="Rose Hill Drive", clean=_IDENTITY)
    assert isinstance(dl, DescList) and len(dl.raws) == 21
    tr = [_u(i + 1, f, float(s)) for i, (f, s) in enumerate(zip(_RHD_FILES, _RHD_DURS))]
    d = _d(tr, dl, untagged=True)
    assert d.failed == ()
    assert d.track_declines == {0: "slot placeholder", 18: "slot placeholder"}
    assert set(d.fills) == set(range(21)) - {0, 18}
    assert d.fills[1] == "Sneak Out"
    assert d_notes(d, dl) == [
        "positional fill declined: desc-position track 1 slot placeholder '?'",
        "positional fill declined: desc-position track 19 slot placeholder '?'",
    ]


def test_bare_number_list_equal_to_track_numbers_declines_every_position():
    tr = [_u(i) for i in range(1, 5)]
    d = _d(tr, _dl("1", "2", "3", "4"))
    assert d.fills == {}
    assert d.track_declines == {0: "slot placeholder", 1: "slot placeholder",
                                2: "slot placeholder", 3: "slot placeholder"}
    shifted = _d(tr, _dl("2", "3", "4", "5"))
    assert shifted.track_declines == {}


def test_filler_marked_entry_is_never_filled():
    tr = [_u(1), _u(2), _u(3)]
    d = _d(tr, _dl("Bertha", "Filler: Dark Star", "Jack Straw"))
    assert d.track_declines == {1: "filler entry"}
    assert d.fills == {0: "Bertha", 2: "Jack Straw"}
    assert d.failed == ()


# belafleckandtheflecktones-2003-06-08 (bfft20030608.shnf): description verbatim.
_BFFT_DESC = (
    '"Set" 1:\nNext\nEarth Jam\nBig Country\nBil Mon\n"Set" 2:\nStomping Grounds\nBela jam->\n'
    "Mudslingers of the Milky Way\nVic Loop jam->\nJam intro->\nSleeper\nFlight of the Cosmic"
    " Hippo [feat. power outage Coffin jam]\nA Moment So Close\nBela solos\nBach: Prelude from"
    " Partita No.3 for solo violin\nEncore: Hoedown"
)
_BFFT_FILES = [f"bfft20030608d1t{i:02d}.mp3" for i in (1, 2, 3, 4, 5, 7, 8, 9, 10)] + [
    f"bfft20030608d2t{i:02d}.mp3" for i in (1, 2, 3, 4, 5, 7, 8, 11)]


def test_show_level_hygiene_is_not_a_shift():
    dl = read_parse(_BFFT_DESC, artist="Bela Fleck and the Flecktones", clean=_IDENTITY)
    assert isinstance(dl, DescList) and len(dl.raws) == 17
    tr = [_u(i + 1, f) for i, f in enumerate(_BFFT_FILES)]
    d = _d(tr, dl, untagged=True)
    assert d.failed[0] == ("hygiene:trailing colon", "track 1 '\"Set\" 1:'")
    assert ("hygiene:trailing colon", "track 6 '\"Set\" 2:'") in d.failed
    assert d.fills == {}
    assert not d.shift


# billystrings-2023-06-10 (BMFS2023-06-10.BMFS): description verbatim.
_BMFS_DESC = (
    "<div><br /></div><div>Billy Strings</div><div>TCU Amphitheater At White River State Park"
    "</div><div>Indianapolis, IN</div><div>2023-06-10</div><div><br /></div><div>Source: "
    "(Inside SBD Cage/7' high)</div><div>Schoeps MK4 (DIN) &gt; Naint PFA &gt; Sound Devices"
    " MixPre 6 II @ 32/96</div><div><br /></div><div>Transfer: Soundforge 17.0 Pro &gt; CD"
    " Wave &gt; FLAC (level 8)</div><div><br /></div><div>Recorded By: Adam Huston / Wild West"
    " Recordings</div><div><br /></div><div>Transfer: Brian Lee (blee421@hotmail.com)</div>"
    "<div><br /></div><div>I did the best I could on tracking.\xa0</div><div><br /></div><div>"
    "SET 1</div><div><br /></div><div>The Fire on My Tongue</div><div>John Hardy\xa0\xa0</div>"
    "<div>Away From the Mire</div><div>Long Forgotten Dream</div><div>Morning Light</div><div>"
    "All Time Low\xa0\xa0</div><div>End of the Rainbow\xa0\xa0</div><div>Ice Bridges</div><div>"
    "My Alice</div><div>Doin' My Time\xa0\xa0</div><div>Libby Phillips Rag</div><div>I'm Still"
    " Here\xa0\xa0</div><div>Dealing Despair</div><div><br /></div><div>SET 2</div><div><br />"
    "</div><div>I'll Be Gone a Long Time</div><div>Run Down &gt;\xa0\xa0</div><div>Pretty"
    " Daughter\xa0\xa0</div><div>All of Tomorrow</div><div>Home</div><div>Good Ole Mountain"
    " Dew\xa0\xa0</div><div>I've Lived a Lot in My Time\xa0\xa0</div><div>I've Just Seen the"
    " Rock of Ages\xa0\xa0</div><div>Psycho &gt;\xa0\xa0</div><div>Thunder\xa0\xa0</div><div>"
    "Nights in White Satin\xa0\xa0</div><div>Turmoil &amp; Tinfoil</div>"
)
_BMFS_FILES = [f"BMFS2023-06-10D1T{i:02d}.mp3" for i in range(1, 13)] + [
    f"BMFS2023-06-10D2T{i:02d}.mp3" for i in range(1, 14)]

# derektrucksband-2003-11-26 (dtb2003-11-26.shnf): description verbatim.
_DTB_DESC = (
    'Disc 1\n1. Volunteered Slavery\n2. So Close So Far\n3. Feel So Bad Sahib>Maki>Sahib\n4. To'
    " Know You Is To Love You\n5. Leavin Trunk\n6. Like Anyone Else\n7. Willisee>\n8. Angola\n"
    '9. For My Brother \n\nDisc 2 \n1. Gonna Move* \n2. Kam-a-lay** \n3. Crowd\n4. E:'
    ' "Philadelphia" Soul Stew>\n5. Joyful Noise**\n'
)
_DTB_FILES = [f"dtb2003-11-26d1t{i:02d}.mp3" for i in range(1, 11)] + [
    f"dtb2003-11-26d2t{i:02d}.mp3" for i in (1, 2, 4, 5)]


def test_block_size_catches_the_two_shifted_untagged_shows():
    bmfs = read_parse(_BMFS_DESC, artist="Billy Strings", clean=_IDENTITY)
    assert isinstance(bmfs, DescList) and len(bmfs.raws) == 25
    assert block_size_mismatch(_BMFS_FILES, bmfs) == "track 1 'The Fire on My Tongue'"
    d = _d([_u(i + 1, f) for i, f in enumerate(_BMFS_FILES)], bmfs, untagged=True)
    assert "block size" in [c for c, _ in d.failed] and d.shift and d.fills == {}

    dtb = read_numbered(_DTB_DESC)
    assert isinstance(dtb, DescList) and len(dtb.raws) == 14
    assert block_size_mismatch(_DTB_FILES, dtb) == "track 1 'Volunteered Slavery'"
    d = _d([_u(i + 1, f) for i, f in enumerate(_DTB_FILES)], dtb, untagged=True)
    assert "block size" in [c for c, _ in d.failed] and d.shift


def test_block_size_matching_counts_pass():
    files = [f"x2001-01-01d1t{i:02d}.flac" for i in range(1, 4)] + [
        f"x2001-01-01d2t{i:02d}.flac" for i in range(1, 3)]
    assert block_size_mismatch(files, _blocked((0, 0, 0, 1, 1), *"ABCDE",
                                               boundaries=("disc",))) is None
    assert block_size_mismatch(files, _blocked((0, 0, 1, 1, 1), *"ABCDE",
                                               boundaries=("disc",))) == "track 1 'A'"


def test_block_size_inert_without_index_or_matching_count():
    dl = _blocked((0, 0, 0, 1, 1), *"ABCDE", boundaries=("disc",))
    no_index = [f"x2001-01-01_{i:02d}.flac" for i in range(1, 6)]
    assert block_size_mismatch(no_index, dl) is None
    one_missing = [f"x2001-01-01d1t{i:02d}.flac" for i in range(1, 5)] + ["x2001-01-01_05.flac"]
    assert block_size_mismatch(one_missing, dl) is None
    three = ["x-d1t01.flac", "x-d1t02.flac", "x-d2t01.flac", "x-d2t02.flac", "x-d3t01.flac"]
    assert block_size_mismatch(three, dl) is None
    single = _blocked((0, 0, 0, 0, 0), *"ABCDE")
    assert block_size_mismatch(["x-d1t01.flac"] * 5, single) is None
    interleaved = ["x-d1t01.flac", "x-d2t01.flac", "x-d1t02.flac", "x-d2t02.flac", "x-d2t03.flac"]
    assert block_size_mismatch(interleaved, dl) is None


def test_disc_index_grammar():
    """`sbd`, `dsbd` and words never read as a disc index; the token must precede a track
    token. (pin)"""
    dl = _blocked((0, 1), "A", "B", boundaries=("disc",))
    assert block_size_mismatch(["gd77.dsbd.d1t01.shn", "gd77.dsbd.d2t01.shn"], dl) is None
    assert block_size_mismatch(["bt1997-10-13cd1t03.flac", "bt1997-10-13cd2t01.flac"],
                               dl) is None
    assert block_size_mismatch(["sbd.t01.flac", "sbd.t02.flac"], dl) is None  # inert
    assert block_size_mismatch(["bt1997-10-13cd1t03.flac", "bt1997-10-13cd1t04.flac"],
                               dl) is None  # one disc value vs two blocks: inert
    dl3 = _blocked((0, 1, 1), "A", "B", "C", boundaries=("disc",))
    assert block_size_mismatch(["show_disc_1_track_01.flac", "show_disc_1_track_02.flac",
                                "show_disc_2_track_01.flac"], dl3) == "track 1 'A'"


def test_encore_block_folds_into_the_preceding_block():
    dl = _blocked((0,) * 5 + (1,) * 4 + (2,), *"ABCDEFGHIJ", boundaries=("set", "encore"))
    discs = ([f"x-d1t{i:02d}.flac" for i in range(1, 6)]
             + [f"x-d2t{i:02d}.flac" for i in range(1, 6)])
    assert block_size_mismatch(discs, dl) is None
    assert block_size_mismatch(discs, dl, fold_encore=False) is None  # 3 blocks vs 2 discs
    off = [f"x-d1t{i:02d}.flac" for i in range(1, 7)] + [f"x-d2t{i:02d}.flac" for i in range(1, 5)]
    assert block_size_mismatch(off, dl) == "track 1 'A'"
    assert block_size_mismatch(off, dl, fold_encore=False) is None
    three = ([f"x-d1t{i:02d}.flac" for i in range(1, 7)] + [f"x-d2t{i:02d}.flac" for i in (1, 2, 3)]
             + ["x-d3t01.flac"])
    assert block_size_mismatch(three, dl) is None  # folded: 2 blocks vs 3 discs, inert
    assert block_size_mismatch(three, dl, fold_encore=False) == "track 1 'A'"


def test_set_headers_use_set_index():
    # Artificial names: every file carries `d1`, so the disc index alone would be inert.
    dl = _blocked((0,) * 5 + (1,) * 4, *"ABCDEFGHI", boundaries=("set",))
    ok = [f"x.d1t{i:02d}.s1t{i:02d}.flac" for i in range(1, 6)] + [
        f"x.d1t{i:02d}.s2t{i:02d}.flac" for i in range(6, 10)]
    assert block_size_mismatch(ok, dl) is None
    off = [f"x.d1t{i:02d}.s1t{i:02d}.flac" for i in range(1, 5)] + [
        f"x.d1t{i:02d}.s2t{i:02d}.flac" for i in range(5, 10)]
    assert block_size_mismatch(off, dl) == "track 1 'A'"
    # A disc boundary keeps the disc index, so the same files are inert.
    disc_dl = _blocked((0,) * 5 + (1,) * 4, *"ABCDEFGHI", boundaries=("disc",))
    assert block_size_mismatch(off, disc_dl) is None
    # Set boundaries but no set index on every file: the disc index is used.
    gd = [f"gd77-05-08d1t{i:02d}.shn" for i in range(1, 5)] + [
        f"gd77-05-08d2t{i:02d}.shn" for i in range(1, 6)]
    assert block_size_mismatch(gd, dl) == "track 1 'A'"
    gd77 = [f"gd77-05-08s1t{i:02d}.shn" for i in range(1, 5)] + [
        f"gd77-05-08s2t{i:02d}.shn" for i in range(1, 6)]
    assert block_size_mismatch(gd77, dl) == "track 1 'A'"


def _donor(titles, rows_spans):
    donor = DonorTape("sib", [f"s{i}" for i in range(len(titles))], [300.0] * len(titles),
                      list(titles))
    rows = [SiblingRow(i + 1, None, span, 0.0, 100.0, "adopt") for i, span in
            enumerate(rows_spans)]
    return donor, rows


def test_sibling_check_catches_a_shift():
    cands = {0: "Bertha", 1: "Jack Straw", 2: "Sugaree", 3: "Ripple"}
    # The donor reads one song later: every 1:1 pair disagrees.
    donor = _donor(["Opening Song", "Bertha", "Jack Straw", "Sugaree"],
                   [(0, 1), (1, 2), (2, 3), (3, 4)])
    assert sibling_disagreement(cands, donor) == (0, "Bertha", "Opening Song")
    tr = [_u(i) for i in range(1, 5)]
    d = _d(tr, _dl("Bertha", "Jack Straw", "Sugaree", "Ripple"), untagged=True,
           donor=lambda: donor)
    assert [c for c, _ in d.failed] == ["sibling durations"]
    assert d.failed[0][1] == "track 1 'Bertha'"
    assert d.shift and d.fills == {}
    agreeing = _donor(["Bertha", "Jack Straw", "Sugaree", "Ripple"],
                      [(0, 1), (1, 2), (2, 3), (3, 4)])
    assert sibling_disagreement(cands, agreeing) is None


def test_sibling_check_inert_without_durations():
    cands = {0: "Bertha", 1: "Jack Straw", 2: "Sugaree"}
    assert sibling_disagreement(cands, None) is None
    # Only track 1 pairs one-to-one: a merged span, a split (shared) span, an unpaired row.
    one = _donor(["Nope", "A", "B", "C"], [(0, 1), (1, 3), None])
    assert sibling_disagreement(cands, one) is None
    split = _donor(["Nope", "Other"], [(0, 1), (1, 2), (1, 2)])
    assert sibling_disagreement(cands, split) is None
    tr = [_u(i) for i in range(1, 4)]
    d = _d(tr, _dl("Bertha", "Jack Straw", "Sugaree"), untagged=True, donor=lambda: None)
    assert d.failed == () and len(d.fills) == 3


def test_sibling_pairs_need_a_real_donor_title_and_ignore_filler():
    cands = {0: "Bertha", 1: "Jack Straw", 2: "Tuning", 3: "Ripple"}
    # Untitled donor rows never count; filler on either side is neutral and is not a pair.
    donor = _donor(["", "", "Dark Star", "Ripple"], [(0, 1), (1, 2), (2, 3), (3, 4)])
    assert sibling_disagreement(cands, donor) is None
    donor2 = _donor(["Banter", "Wrong", "Dark Star", "Ripple"], [(0, 1), (1, 2), (2, 3), (3, 4)])
    assert sibling_disagreement(cands, donor2) == (1, "Jack Straw", "Wrong")
    # A row with no candidate (a resolved position) is not a pair: one pair left, inert.
    assert sibling_disagreement({1: "Jack Straw"}, donor2) is None


def test_filler_sibling_pair_counts_toward_min_anchors_as_neutral():
    # One disagreeing song pair plus one filler pair: two pairs, so the check is live.
    donor = _donor(["Jack Straw", "Tuning"], [(0, 1), (1, 2)])
    assert sibling_disagreement({0: "Bertha", 1: "Tuning"}, donor) == (0, "Bertha", "Jack Straw")
    # Filler on either side is neutral: it never disagrees.
    assert sibling_disagreement({0: "Jack Straw", 1: "Dark Star"}, donor) is None
    tr = [_u(1), _u(2)]
    d = _d(tr, _dl("Bertha", "Tuning"), untagged=True, donor=lambda: donor)
    assert d.failed == (("sibling durations", "track 1 'Bertha'"),)
    assert d.shift and d.fills == {}


def test_untagged_checks_only_on_wholly_untagged():
    bmfs = read_parse(_BMFS_DESC, artist="Billy Strings", clean=_IDENTITY)
    tr = [_u(i + 1, f) for i, f in enumerate(_BMFS_FILES)]
    calls = []

    def donor():
        calls.append(1)
        return None

    d = _d(tr, bmfs, untagged=False, donor=donor)
    assert "block size" not in [c for c, _ in d.failed]
    assert calls == []
    _d(tr, bmfs, untagged=True, donor=donor)
    assert calls == [1]


def test_donor_not_called_without_candidates():
    calls = []
    tr = [_u(1), _u(2)]
    _d(tr, _dl("?", "Filler: Tuning"), untagged=True, donor=lambda: calls.append(1))
    assert calls == []


def test_agreement_check_declines_below_floor():
    tr = [_t("Bertha", n=1), _u(2), _u(3)]
    dl = _dl("Bertha", "Jack Straw", "Sugaree")
    d = _d(tr, dl, canonical=_canon("Dark Star", "Ripple"))
    assert [c for c, _ in d.failed] == ["agreement"]
    assert d.failed[0][1] == "track 1 'Bertha'"
    assert d.shift and d.fills == {}
    ok = _d(tr, dl, canonical=_canon("Bertha", "Jack Straw", "Other"))
    assert ok.failed == () and ok.fills == {1: "Jack Straw", 2: "Sugaree"}
    # aliases reach the agreement check
    sc = _canon("China Cat Sunflower")
    assert _d([_u(1)], _dl("Chinacat"), canonical=sc).failed[0][0] == "agreement"
    assert _d([_u(1)], _dl("Chinacat"), canonical=sc, aliases=GD_SHORTHAND).failed == ()


def test_check_order_and_all_failures_recorded():
    tr = [_t("Bertha", n=1), _u(2), _u(3), _u(4)]
    dl = _dl("Sugaree (5:00)", "w/ Eric Johnson (5:00)", "Jack Straw (5:00)", "Jack Straw")
    tr = [t.model_copy(update={"duration_sec": 100.0}) for t in tr]
    d = _d(tr, dl, canonical=_canon("Dark Star"))
    assert [c for c, _ in d.failed] == ["hygiene:annotation", "adjacent duplicate",
                                        "tape agreement", "written durations", "agreement"]
    assert d.failed[1] == ("adjacent duplicate", "track 3 'Jack Straw'")
    assert d.failed[2] == ("tape agreement", "track 1 'Sugaree'")
    assert d.failed[3] == ("written durations", "track 1 'Sugaree'")


def test_ships_cleaned_text():
    tr = [_u(1), _u(2), _u(3)]
    d = _d(tr, _dl("Pyramid County (1) > Little Maggie", "E: Ripple", "“Sugaree”"))
    assert d.fills == {0: "Pyramid County > Little Maggie", 1: "Ripple", 2: "Sugaree"}


def _filled(*titles_sources):
    return [Track(index=i + 1, set="1", filename=f"f{i}.mp3", title=t, title_source=s)
            for i, (t, s) in enumerate(titles_sources)]


def test_self_filled_requires_d_to_pass_every_check():
    passed = DDecision(fills={0: "A", 1: "B"}, failed=(), track_declines={})
    tr = _filled(("Tuning", "tags"), ("Bertha", DESC_POSITION), ("Sugaree", DESC_POSITION))
    assert is_self_filled(tr, passed)
    failed = DDecision(fills={}, failed=(("agreement", "track 1 'A'"),), track_declines={})
    assert not is_self_filled(tr, failed)
    assert not is_self_filled(tr, None)
    mixed = _filled(("Bertha", "tags"), ("Sugaree", DESC_POSITION))
    assert not is_self_filled(mixed, passed)
    declined = _filled(("", "unresolved"), ("Sugaree", DESC_POSITION))
    assert not is_self_filled(declined, passed)
    assert not is_self_filled(_filled(("Tuning", "tags")), passed)


def test_unresolved_track_blocks_self_filled_even_with_a_filler_looking_filename():
    passed = DDecision(fills={1: "Sugaree"}, failed=(), track_declines={0: "filler entry"})
    # An unresolved track's title is its filename; `is_filler` reads `Tuning` in it.
    tr = _filled(("d1t01 Tuning.flac", "unresolved"), ("Sugaree", DESC_POSITION))
    assert not is_self_filled(tr, passed)


def test_self_filled_end_to_end():
    tr = [_u(1), _u(2), _t("Tuning", n=3)]
    d = _d(tr, _dl("Bertha", "Sugaree", "Tuning"), untagged=True)
    assert is_self_filled(apply_d(tr, d), d)


def test_notes_one_per_show_decline_and_per_track():
    tr = [_t("Bertha", n=1), _u(2), _u(3), _u(4)]
    dl = _dl("Sugaree", "w/ Eric Johnson", "?", "Jack Straw")
    d = _d(tr, dl)
    assert [c for c, _ in d.failed] == ["hygiene:annotation", "tape agreement"]
    assert d.track_declines == {2: "slot placeholder"}
    assert d_notes(d, dl) == [
        "positional fill declined: desc-position hygiene:annotation (track 2 'w/ Eric Johnson')",
        "positional fill declined: desc-position track 3 slot placeholder '?'",
    ]
    assert d.shift
    ok = _d([_u(1)], _dl("Bertha"))
    assert d_notes(ok, _dl("Bertha")) == []


# ---- Task 7: the S plan and the deferred S fill (slice 1 placement) ----------------------

from llama.desc_list import read_desc_list  # noqa: E402
from llama.title_hygiene import SetlistPlan, apply_deferred_setlist, plan_setlist_rung  # noqa: E402
from llama.titles import (  # noqa: E402
    is_real_title,
    placeholder_positions,
    resolve_titles,
    tag_layer,
)

_Q1 = "positional fill declined: setlist wholly untagged tape"
_Q1_CHOSEN = ("positional fill declined: setlist wholly untagged tape "
              "(chosen canonical, no admissible taper list)")


def _plan(items, tags, *, source="setlist.fm", s_positions=None, desc_used=False,
          untagged=False, slice1=True, slice2=True, confidence="high", norms=None):
    canonical = ParsedSetlist(items=[SetlistItem(title=t, normalized=t.lower(), set="1")
                                     for t in items], confidence=confidence)
    real = [is_real_title(t) for t in tags]
    if s_positions is None:
        s_positions = [i for i, r in enumerate(real) if not r]
    return plan_setlist_rung(
        canonical=canonical, canonical_source=source, s_positions=s_positions,
        tag_titles=list(tags), tag_real=real,
        filenames=[f"x2001-01-01d1t{i + 1:02d}.flac" for i in range(len(tags))],
        metadata_norms=norms or set(), desc_used=desc_used, wholly_untagged=untagged,
        slice1=slice1, slice2=slice2)


def test_today_mode_is_todays_rung():
    """(pin) `slice1` off reproduces today's S rung in `resolve_titles` exactly."""
    files = [{"name": f"x2001-01-01d1t{i + 1:02d}.flac", "title": t, "length": "300"}
             for i, t in enumerate(["Bertha", "", "", "d1t04", "Ripple"])]
    items = ["Bertha", "Jack Straw", "Track 03", "Sugaree", "Ripple"]
    canonical = ParsedSetlist(items=[SetlistItem(title=t, normalized=t.lower(), set="1")
                                     for t in items], confidence="high")
    today = {t.index - 1: t.title for t in resolve_titles(files, canonical)
             if t.title_source == "setlist"}
    assert today == {1: "Jack Straw", 3: "Sugaree"}  # the placeholder item refused
    tags, _ = tag_layer(files, None, None)
    demoted = set(placeholder_positions(tags, corroboration=frozenset(), item_title=None))
    s_positions = [i for i, t in enumerate(tags) if i not in demoted and not is_real_title(t)]
    plan = plan_setlist_rung(
        canonical=canonical, canonical_source="setlist.fm", s_positions=s_positions,
        tag_titles=tags, tag_real=[is_real_title(t) for t in tags],
        filenames=[f["name"] for f in files], metadata_norms=set(), desc_used=True,
        wholly_untagged=False, slice1=False, slice2=True)
    assert plan.mode == "today"
    assert plan.fills == today
    assert (plan.deferred, plan.declined, plan.notes) == ({}, frozenset(), ())


def test_today_mode_ignores_q1_and_hygiene():
    """(pin) today's rung has neither Q1 nor checks 1 and 2."""
    plan = _plan(["Set 2", "Jack Straw"], ["", ""], untagged=True, slice1=False)
    assert plan.mode == "today" and plan.fills == {0: "Set 2", 1: "Jack Straw"}


def test_no_count_matched_canonical_is_none():
    assert _plan(["Bertha"], ["", ""]).mode == "none"
    low = _plan(["Bertha", "Ripple"], ["", ""], confidence="low")
    assert low.mode == "none"
    assert (low.fills, low.deferred, low.declined, low.notes) == ({}, {}, frozenset(), ())
    assert _plan(["Bertha"], ["", ""], slice1=False).mode == "none"


def test_s_never_fills_a_wholly_untagged_tape():
    plan = _plan(["Bertha", "Jack Straw", "Sugaree"], ["", "", ""], untagged=True)
    assert plan.mode == "untagged"
    assert plan.fills == {} and plan.deferred == {}
    assert plan.declined == frozenset({0, 1, 2})
    assert plan.notes == (_Q1,)
    # Q1 holds whether or not a taper's list exists (non-chosen canonical).
    assert _plan(["Bertha", "Jack Straw"], ["", ""], untagged=True,
                 desc_used=True).mode == "untagged"


def test_untagged_with_no_s_positions_writes_no_note():
    """Judgement call: nothing for S to withdraw means no Q1 note."""
    plan = _plan(["Bertha", "Jack Straw"], ["", ""], untagged=True, s_positions=[])
    assert plan.mode == "untagged"
    assert (plan.fills, plan.declined, plan.notes) == ({}, frozenset(), ())


def test_chosen_canonical_with_a_list_moves_to_d():
    plan = _plan(["Bertha", "Jack Straw", "Sugaree"], ["Bertha", "", ""], source="chosen",
                 desc_used=True)
    assert plan.mode == "chosen"
    assert (plan.fills, plan.deferred, plan.declined, plan.notes) == ({}, {}, frozenset(), ())
    off = _plan(["Bertha", "Jack Straw", "Sugaree"], ["Bertha", "", ""], source="chosen",
                desc_used=True, slice2=False)
    assert off.mode == "gated"
    assert off.fills == {1: "Jack Straw", 2: "Sugaree"}


def test_chosen_canonical_untagged_tape_writes_no_q1_note():
    plan = _plan(["Bertha", "Jack Straw"], ["", ""], source="chosen", desc_used=True,
                 untagged=True)
    assert plan.mode == "chosen"
    assert plan.notes == ()
    assert plan.declined == frozenset() and plan.fills == {}


# gd73-06-10 (tests/fixtures/gd73_metadata.json), the selected recording's description,
# verbatim: a segue line yields two items, and there are no numbered lines.
_GD73_DESC = ("Set 1:\nMorning Dew\nChina Cat Sunflower > I Know You Rider\n\nSet 2:\n"
              "Dark Star > Eyes of the World\n\nEncore:\nJohnny B. Goode")
_GD73_ITEMS = ["Morning Dew", "China Cat Sunflower", "I Know You Rider", "Dark Star",
               "Eyes of the World", "Johnny B. Goode"]


def test_chosen_canonical_without_admissible_list_stays_gated():
    read = read_desc_list(_GD73_DESC, 6, artist="Grateful Dead",
                          clean=lambda p: (p, frozenset()))
    assert read.used is None
    tags = _GD73_ITEMS[:5] + [""]
    plan = _plan(_GD73_ITEMS, tags, source="chosen", desc_used=False, s_positions=[5])
    assert plan.mode == "gated"
    assert plan.fills == {5: "Johnny B. Goode"}
    assert (plan.deferred, plan.declined, plan.notes) == ({}, frozenset(), ())


def test_chosen_canonical_untagged_without_list_declines():
    plan = _plan(_GD73_ITEMS, [""] * 6, source="chosen", desc_used=False, untagged=True)
    assert plan.mode == "untagged"
    assert plan.fills == {}
    assert plan.declined == frozenset(range(6))
    assert plan.notes == (_Q1_CHOSEN,)


def test_count_matched_list_defers_s():
    plan = _plan(["Bertha", "Jack Straw", "Sugaree", "Ripple"], ["Bertha", "", "", "Ripple"],
                 desc_used=True)
    assert plan.mode == "deferred"
    assert plan.fills == {}
    assert plan.deferred == {1: "Jack Straw", 2: "Sugaree"}
    assert plan.declined == frozenset({1, 2})
    assert plan.notes == ()


def test_copied_sibling_description_canonical_defers_to_d():
    plan = _plan(["Bertha", "Jack Straw", "Sugaree"], ["Bertha", "", ""], source="lma:x",
                 desc_used=True)
    assert plan.mode == "deferred"
    assert plan.fills == {}
    assert plan.deferred == {1: "Jack Straw", 2: "Sugaree"}
    assert plan.declined == frozenset({1, 2})


def test_gated_mode_runs_checks_1_and_2():
    hdr = _plan(["Bertha", "Set 2", "Jack Straw", "Ripple"], ["Bertha", "", "", "Ripple"])
    assert hdr.mode == "gated"
    assert hdr.fills == {} and hdr.declined == frozenset({1, 2})
    assert hdr.notes == ("positional fill declined: setlist hygiene:header (track 2 'Set 2')",)
    dup = _plan(["Jack Straw", "Jack Straw", "Sugaree", "Ripple"],
                ["Jack Straw", "", "", "Ripple"])
    assert dup.fills == {} and dup.declined == frozenset({1, 2})
    assert dup.notes == (
        "positional fill declined: setlist adjacent duplicate (track 2 'Jack Straw')",)
    q = _plan(["Bertha", "?", "Sugaree", "Ripple"], ["Bertha", "", "", "Ripple"])
    assert q.fills == {2: "Sugaree"}
    assert q.declined == frozenset({1})
    assert q.notes == ("positional fill declined: setlist track 2 slot placeholder '?'",)


def test_gated_check_2_compares_candidates_with_each_other():
    plan = _plan(["Bertha", "Sugaree", "Sugaree >", "Ripple"], ["Bertha", "", "", "Ripple"])
    assert plan.fills == {} and plan.declined == frozenset({1, 2})
    assert plan.notes[0].startswith("positional fill declined: setlist adjacent duplicate")


def test_gated_check_2_ignores_an_unreal_tag():
    """A tag that fails `is_real_title` is no neighbour for check 2 (a 2b-demoted
    position 2 here, so not an S position either)."""
    tags = ["Bertha", "", "Sugaree"]
    real = [True, False, False]
    canonical = ParsedSetlist(items=[SetlistItem(title=t, normalized=t.lower(), set="1")
                                     for t in ["Bertha", "Sugaree", "Ripple"]],
                              confidence="high")
    plan = plan_setlist_rung(
        canonical=canonical, canonical_source="setlist.fm", s_positions=[1],
        tag_titles=tags, tag_real=real, filenames=["a.flac", "b.flac", "c.flac"],
        metadata_norms=set(), desc_used=False, wholly_untagged=False, slice1=True,
        slice2=True)
    assert plan.fills == {1: "Sugaree"}


def test_gated_ships_todays_item_text_and_keeps_the_placeholder_refusal():
    plan = _plan(["Bertha", "Sugaree >", "Track 03", "Ripple"], ["Bertha", "", "", "Ripple"])
    assert plan.mode == "gated"
    assert plan.fills == {1: "Sugaree >"}
    assert 2 not in plan.fills


def _dd(failed=(), track_declines=None):
    return DDecision(fills={}, failed=tuple(failed), track_declines=track_declines or {})


_DEFERRED_TAGS = ["Bertha", "", "", "Ripple"]


def _deferred_plan():
    plan = _plan(["Bertha", "Jack Straw", "Sugaree", "Ripple"], _DEFERRED_TAGS, desc_used=True)
    assert plan.mode == "deferred"
    return plan


def _deferred_tracks():
    return [_t("Bertha", n=1), _u(2), _u(3), _t("Ripple", n=4)]


def test_deferred_s_fills_after_a_hygiene_decline():
    d = _dd([("hygiene:annotation", "track 2 'w/ Eric Johnson'")])
    out, notes = apply_deferred_setlist(_deferred_tracks(), _deferred_plan(), d,
                                        tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert [(t.title, t.title_source) for t in out] == [
        ("Bertha", "tags"), ("Jack Straw", "setlist"), ("Sugaree", "setlist"),
        ("Ripple", "tags")]
    assert notes == []


def test_deferred_s_fills_a_per_track_hygiene_decline_of_a_passing_d():
    d = _dd(track_declines={1: "slot placeholder"})
    out, _ = apply_deferred_setlist(_deferred_tracks(), _deferred_plan(), d,
                                    tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert out[1].title == "Jack Straw" and out[1].title_source == "setlist"


def test_deferred_s_declines_with_d_on_a_shift():
    d = _dd([("hygiene:annotation", "track 2 'w/ X'"), ("tape agreement", "track 1 'Sugaree'")])
    tracks = _deferred_tracks()
    out, notes = apply_deferred_setlist(tracks, _deferred_plan(), d,
                                        tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert out == tracks
    assert notes == ["positional fill declined: setlist tape agreement (track 1 'Sugaree')"]


def test_deferred_s_skips_filler_entry_positions():
    d = _dd(track_declines={2: "filler entry"})
    out, _ = apply_deferred_setlist(_deferred_tracks(), _deferred_plan(), d,
                                    tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert out[1].title_source == "setlist"
    assert out[2].title_source == "unresolved"


def test_deferred_s_fills_only_unresolved():
    tracks = _deferred_tracks()
    tracks[1] = _t("Jack Straw Jam", source="sibling-align", n=2)
    d = _dd([("hygiene:annotation", "track 2 'w/ X'")])
    out, _ = apply_deferred_setlist(tracks, _deferred_plan(), d,
                                    tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert (out[1].title, out[1].title_source) == ("Jack Straw Jam", "sibling-align")
    assert (out[2].title, out[2].title_source) == ("Sugaree", "setlist")


def test_deferred_s_rechecks_against_current_tracks():
    # Check 2 against a neighbour resolved since the plan: the whole fill declines.
    tracks = _deferred_tracks()
    tracks[2] = _t("Jack Straw", source="sibling-align", n=3)
    d = _dd([("hygiene:annotation", "track 3 'w/ X'")])
    out, notes = apply_deferred_setlist(tracks, _deferred_plan(), d,
                                        tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert out[1].title_source == "unresolved"
    assert notes == [
        "positional fill declined: setlist adjacent duplicate (track 2 'Jack Straw')"]
    # Check 1, per track.
    plan = _plan(["Bertha", "?", "Sugaree", "Ripple"], _DEFERRED_TAGS, desc_used=True)
    out, notes = apply_deferred_setlist(_deferred_tracks(), plan, d,
                                        tag_titles=_DEFERRED_TAGS, metadata_norms=set())
    assert [t.title_source for t in out] == ["tags", "unresolved", "setlist", "tags"]
    assert notes == ["positional fill declined: setlist track 2 slot placeholder '?'"]


def test_deferred_apply_is_a_no_op_outside_deferred_mode():
    tracks = _deferred_tracks()
    gated = _plan(["Bertha", "Jack Straw", "Sugaree", "Ripple"], _DEFERRED_TAGS)
    assert apply_deferred_setlist(tracks, gated, None, tag_titles=_DEFERRED_TAGS,
                                  metadata_norms=set()) == (tracks, [])
    assert isinstance(gated, SetlistPlan)
