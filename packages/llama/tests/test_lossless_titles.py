"""Title hygiene slice 3 (C): per-track lossless titles from the same item.

Spec `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`, "Slice 3"; plan Task 8.
C1 adoption follows the plan's reading (Global Constraints, "Plan readings"): a target
agreeing with (a) or (b) is adopted; one agreeing with neither is adopted only when (c)
holds for the show; if any target fails all three, C1 fills nothing on the show."""

from llama.desc_list import DescList, clean_entries, read_numbered
from llama.lossless_titles import _vetoed, apply_lossless
from llama.models import ParsedSetlist, SetlistItem
from llama.titles import clean_tag_titles


def _tape(pairs, *, stem="gd99-01-01d1t", lossless_format="Flac"):
    """`pairs` = (delivered mp3 title, lossless title) per track. Returns (files, kept)."""
    files: list[dict] = []
    kept: list[dict] = []
    for i, (mt, lt) in enumerate(pairs, 1):
        s = f"{stem}{i:02d}"
        mp3 = {"name": f"{s}.mp3", "format": "VBR MP3", "source": "derivative",
               "original": f"{s}.flac", "title": mt, "length": "05:00", "track": str(i)}
        flac = {"name": f"{s}.flac", "format": lossless_format, "source": "original",
                "title": lt, "length": "300.0", "track": str(i)}
        files += [mp3, flac]
        kept.append(mp3)
    return files, kept


def _dl(*raws):
    return DescList("numbered", tuple(raws), tuple(clean_entries(list(raws))),
                    tuple(0 for _ in raws), ())


def _canon(*titles):
    return ParsedSetlist(items=[SetlistItem(title=t, normalized=t.lower(), set="1")
                                for t in titles], confidence="high")


def _run(pairs=None, *, files=None, kept=None, basis=None, desc=None, canon=None,
         in_scope=True, fmt="VBR MP3", norms=None, **tape_kw):
    if pairs is not None:
        files, kept = _tape(pairs, **tape_kw)
    tags = clean_tag_titles(kept)
    return apply_lossless(kept, tags, "tags", in_scope=in_scope, files=files,
                          ordering={"format": fmt},
                          recovery_basis=kept if basis is None else basis,
                          desc=desc, canonical=canon or ParsedSetlist(),
                          metadata_norms=norms or set())


_FURTHUR = ["Shakedown Street", "Bertha", "Sugaree", "Deal", "Loser", "Jack Straw"]


def test_c_does_not_run_below_recover_below():
    r = _run([("tmp", t) for t in _FURTHUR], desc=_dl(*_FURTHUR), in_scope=False)
    assert r.changed == {}
    assert r.declined == "out of scope"
    assert r.titles == ["tmp"] * 6
    assert r.sources == ["tags"] * 6
    assert r.notes == ()


def test_c1_fills_tmp_from_lossless_with_list_agreement():
    # furthur/DSO class: `tmp` on every mp3, the FLAC originals tagged.
    r = _run([("tmp", t) for t in _FURTHUR], desc=_dl(*_FURTHUR))
    assert r.changed == {i: "C1" for i in range(6)}
    assert r.titles == _FURTHUR
    assert r.sources == ["sibling-format"] * 6
    assert r.declined is None
    assert r.c1_verdicts == {i: (True, None) for i in range(6)}
    assert r.c_holds is None  # no target needed (c)
    assert len(r.notes) == 6
    assert r.notes[0] == "lossless title: track 1 'tmp' -> 'Shakedown Street' (C1)"


def test_c1_needs_a_reference_or_consistent_tags():
    two_items = _canon("Bertha", "Sugaree")  # 2 items, 3 files: not count-matched
    # No list, no count-matched canonical; two comparison stems agree -> (c) holds.
    r = _run([("", "Bertha"), ("Sugaree", "Sugaree"), ("Deal", "Deal")], canon=two_items)
    assert r.changed == {0: "C1"}
    assert r.titles[0] == "Bertha" and r.sources[0] == "sibling-format"
    assert r.c1_verdicts == {0: (None, None)}
    assert r.c_holds is True
    # One disagreeing comparison stem -> (c) fails -> nothing.
    r = _run([("", "Bertha"), ("Sugaree", "Sugaree"), ("Deal", "Loser")], canon=two_items)
    assert r.changed == {}
    assert r.titles == ["", "Sugaree", "Deal"]
    assert r.c_holds is False
    # Fewer than MIN_ANCHORS (2) agreeing comparison stems -> (c) fails.
    r = _run([("", "Bertha"), ("Sugaree", "Sugaree"), ("", None)])
    assert r.changed == {}
    assert r.c_holds is False


def test_c1_is_show_level():
    desc = _dl("Bertha", "Jack Straw", "Deal", "Loser")
    # Target 0 agrees with its entry, target 1 does not; (c) fails (stem 3 disagrees).
    r = _run([("", "Bertha"), ("", "Sugaree"), ("Deal", "Deal"), ("Loser", "Big River")],
             desc=desc)
    assert r.changed == {}
    assert r.titles == ["", "", "Deal", "Loser"]
    assert r.c1_verdicts == {0: (True, None), 1: (False, None)}
    assert r.c_holds is False
    assert r.declined == "C1 unconfirmed"
    assert r.notes == ("lossless titles declined: C1 unconfirmed (track 2 'Sugaree')",)
    # The same with (c) holding: every target is filled, the disagreeing one included.
    r = _run([("", "Bertha"), ("", "Sugaree"), ("Deal", "Deal"), ("Loser", "Loser")],
             desc=desc)
    assert r.changed == {0: "C1", 1: "C1"}
    assert r.titles[:2] == ["Bertha", "Sugaree"]
    assert r.c1_verdicts == {0: (True, None), 1: (False, None)}
    assert r.c_holds is True
    assert r.declined is None


def test_c1_verdicts_record_both_references():
    # (a) disagrees, (b) agrees: adopted without consulting (c).
    r = _run([("", "Sugaree"), ("Deal", "Deal"), ("Loser", "Big River")],
             desc=_dl("Bertha", "Deal", "Loser"), canon=_canon("Sugaree", "Deal", "Loser"))
    assert r.c1_verdicts == {0: (False, True)}
    assert r.changed == {0: "C1"}
    assert r.c_holds is None


def test_2a_shape_delivered_tag_is_not_a_c1_target():
    # Without the 2a exclusion `J` (fails is_real_title) would be a C1 target and (c)
    # holds here, so the fill would happen. C2 does not fire: `Jack Straw` does not
    # agree with the entry `J` (short cores compare by equality).
    r = _run([("J", "Jack Straw"), ("Deal", "Deal"), ("Loser", "Loser")],
             desc=_dl("J", "Deal", "Loser"))
    assert r.changed == {}
    assert r.titles[0] == "J"
    assert r.c1_verdicts == {}


def test_2a_shape_delivered_tag_goes_to_c2():
    r = _run([("J", "Jack Straw"), ("Deal", "Deal"), ("Loser", "Loser")],
             desc=_dl("Jack Straw", "Deal", "Loser"))
    assert r.changed == {0: "C2"}
    assert r.titles[0] == "Jack Straw"


# radiators-1991-11-01 (rads1991-11-01.dantepper.flac): verbatim description excerpt and
# the d1t01-d1t04 file titles (mp3 derivative | flac original) from the item metadata.
_RADS_DESC = """Disc 1: (1:09:29)
d1t01 One-Eyed Jack (4:51)
d1t02 The Smokin' Hole (4:41)
d1t03 Mood To Move (4:04)
d1t04 Somebody Done Changed The Lock On My Door (4:58)"""
_RADS = [("One-Eyed Jack", "One-Eyed Jack"),
         ("The Smokin' Hole", "The Smokin' Hole"),
         ("No Skin Off My Back", "Mood To Move"),
         ("The Key I Got Don't Fit", "Somebody Done Changed The Lock On My Door")]


def test_c2_replaces_a_stale_mp3_title():
    desc = read_numbered(_RADS_DESC)
    assert isinstance(desc, DescList) and len(desc.cleaned) == 4
    r = _run(_RADS, desc=desc, stem="rads1991-11-01d1t")
    assert r.changed == {2: "C2", 3: "C2"}
    assert r.titles == ["One-Eyed Jack", "The Smokin' Hole", "Mood To Move",
                        "Somebody Done Changed The Lock On My Door"]
    assert r.sources == ["tags", "tags", "sibling-format", "sibling-format"]
    assert "lossless title: track 3 'No Skin Off My Back' -> 'Mood To Move' (C2)" in r.notes
    assert len(r.notes) == 2


def test_c2_needs_a_reference():
    r = _run(_RADS, canon=_canon("One-Eyed Jack", "Mood To Move"), stem="rads1991-11-01d1t")
    assert r.changed == {}
    assert r.titles == [d for d, _ in _RADS]
    # A count-matched canonical is a reference on its own.
    r = _run(_RADS, canon=_canon(*(lt for _, lt in _RADS)), stem="rads1991-11-01d1t")
    assert r.changed == {2: "C2", 3: "C2"}


def test_list_not_count_matched_is_no_reference():
    r = _run(_RADS, desc=_dl("One-Eyed Jack", "Mood To Move"), stem="rads1991-11-01d1t")
    assert r.changed == {}


def test_case_or_punctuation_difference_is_not_c2():
    r = _run([("mood to move", "Mood To Move!"), ("Me & My Uncle", "Me and My Uncle"),
              ("Deal", "Deal")],
             desc=_dl("Mood To Move!", "Me and My Uncle", "Deal"))
    assert r.changed == {}
    assert r.titles == ["mood to move", "Me & My Uncle", "Deal"]


def test_lossless_vetoes():
    # builttospill-1997-10-13 / mountaingoats-2017-06-02 shapes: a bracketed lossless tag
    # and one ending `(m:ss):` are never taken, even with an agreeing list entry.
    r = _run([("", "[Banter]"), ("", "Song (0:25):"), ("Deal", "Deal"), ("Loser", "Loser")],
             desc=_dl("[Banter]", "Song (0:25):", "Deal", "Loser"))
    assert r.changed == {}
    assert r.titles[:2] == ["", ""]
    assert r.c1_verdicts == {}  # neither is a C1 target: the lossless side is vetoed
    # greenskybluegrass-2014-07-18 shape: `Blue Night @` beside delivered `Blue Night`.
    r = _run([("Blue Night", "Blue Night @"), ("Airmail Special", "Airmail Special ^"),
              ("Deal", "Deal")], desc=_dl("Blue Night @", "Airmail Special ^", "Deal"))
    assert r.changed == {}
    assert r.titles[:2] == ["Blue Night", "Airmail Special"]


def test_veto_predicate():
    assert _vetoed("[Banter]", "")
    assert _vetoed("  [John's Still Got Some Gas…] ", "x")
    assert _vetoed("Song (0:25):", "")
    assert _vetoed("Song:", "")
    assert _vetoed("Blue Night @", "Blue Night")
    assert _vetoed("Can't Stop Now ^", "Can't Stop Now")
    assert _vetoed("Song *#", "Song")
    assert not _vetoed("Blue Night", "Blue Night")
    assert not _vetoed("Blue Night @", "Red Night")
    assert not _vetoed("Song (Reprise)", "Song")
    assert not _vetoed("[Banter] Tuning", "")


def test_two_off_by_one_lossless_tags_skip_c():
    desc = _dl("Bertha", "Sugaree", "Deal", "Loser", "Jack Straw")
    pairs = [("tmp", "Sugaree"), ("tmp", "Deal"), ("tmp", "Loser"), ("tmp", "Jack Straw"),
             ("tmp", "Big River")]
    r = _run(pairs, desc=desc)
    assert r.declined == "off by one"
    assert r.changed == {}
    assert r.titles == ["tmp"] * 5
    assert r.notes == ("lossless titles declined: off by one against the taper's list "
                       "(tracks 1, 2, 3, 4)",)


def test_one_off_by_one_lossless_tag_does_not_skip_c():
    desc = _dl("Bertha", "Sugaree", "Deal", "Loser")
    r = _run([("Bertha", "Bertha"), ("tmp", "Deal"), ("Deal", "Deal"), ("Loser", "Loser")],
             desc=desc)
    assert r.declined != "off by one"


def test_off_by_one_needs_a_reference():
    # Without a count-matched reference the decline cannot fire; (c) decides.
    pairs = [("", "Sugaree"), ("", "Deal"), ("Loser", "Loser"), ("Jack Straw", "Jack Straw")]
    r = _run(pairs, canon=_canon("Bertha", "Sugaree", "Deal"))
    assert r.declined is None
    assert r.changed == {0: "C1", 1: "C1"}


def test_readmitted_file_is_untouched_and_keeps_no_vote():
    files, kept = _tape([("", "Bertha"), ("Sugaree", "Sugaree"), ("Deal", "Deal")])
    extra = {"name": "gd99-01-01d1t04.mp3", "format": "VBR MP3", "source": "derivative",
             "original": "gd99-01-01d1t04.flac", "title": "", "length": "00:40", "track": "4"}
    r = _run(files=files + [extra], kept=kept + [extra], basis=kept)
    assert r.changed == {0: "C1"}
    assert r.titles[3] == ""
    assert r.sources[3] == "tags"
    assert 3 not in r.c1_verdicts


def test_no_lossless_format_declines_quietly():
    files, kept = _tape([("tmp", "Bertha"), ("tmp", "Deal"), ("tmp", "Loser")])
    files = [f for f in files if f["format"] == "VBR MP3"]
    r = _run(files=files, kept=kept, desc=_dl("Bertha", "Deal", "Loser"))
    assert r.declined == "no lossless format"
    assert r.changed == {} and r.notes == ()


def test_first_lossless_format_with_any_title_is_used():
    # `Flac` exists but carries no titles; `24bit Flac` is tagged -> it is the one read.
    files, kept = _tape([("tmp", None), ("tmp", None), ("tmp", None)])
    hi, _ = _tape([("tmp", "Bertha"), ("tmp", "Deal"), ("tmp", "Loser")],
                  lossless_format="24bit Flac")
    hi_files = [f for f in hi if f["format"] == "24bit Flac"]
    r = _run(files=files + hi_files, kept=kept, desc=_dl("Bertha", "Deal", "Loser"))
    assert r.changed == {0: "C1", 1: "C1", 2: "C1"}
    assert r.titles == ["Bertha", "Deal", "Loser"]


def test_delivered_format_is_never_its_own_lossless_source():
    # A Flac-delivered tape does not read Flac again.
    files, kept = _tape([("tmp", "Bertha"), ("tmp", "Deal"), ("tmp", "Loser")])
    flac_kept = [f for f in files if f["format"] == "Flac"]
    for f in flac_kept:
        f["title"] = "tmp"
    r = _run(files=files, kept=flac_kept, fmt="Flac", desc=_dl("Bertha", "Deal", "Loser"))
    assert r.changed == {}
    assert r.declined == "no lossless format"


def test_c1_lossless_must_be_hygienic():
    # A lossless title equal to the show's own metadata (venue) is not adopted.
    r = _run([("tmp", "Fillmore West"), ("tmp", "Deal"), ("tmp", "Loser")],
             desc=_dl("Fillmore West", "Deal", "Loser"), norms={"fillmore west"})
    assert r.changed == {1: "C1", 2: "C1"}
    assert r.titles[0] == "tmp"


# derektrucksband-2007-05-27 (dtb2007-05-27..flac): d1t01-d1t04 file titles from the item
# metadata (mp3 d1t01 carries no title; its flac original says `Announcements/crowd`). The
# canonical is setlist.fm-shaped (it opens `Sailing On`, with the two conflict songs the
# show recorded), count-matched to the four files, so S would ship `Sailing On` at track 1.
_DTB = [(None, "Announcements/crowd"), ("Sailin On", "Sailin On"),
        ("Kam-Ma-Lay", "Kam-Ma-Lay"), ("Soul Serenade", "Soul Serenade")]
_DTB_CANON = ("Sailing On", "Down in the Bottom", "44 Blues", "Soul Serenade")
# The verbatim head of the item's own description (count-matched to these four files).
_DTB_DESC = """disc 2

01: Announcements/crowd
02: Sailin On
03: Kam-ma-lay
04. Soul Serenade"""


def test_derektrucksband_2007_05_27_track1():
    r = _run(_DTB, canon=_canon(*_DTB_CANON), stem="dtb2007-05-27d1t")
    assert r.changed == {0: "C1"}
    assert r.titles[0] == "Announcements/crowd"
    assert r.sources[0] == "sibling-format"
    assert r.c1_verdicts == {0: (None, False)}  # (b) disagrees: adopted via (c)
    assert r.c_holds is True
    assert r.notes == ("lossless title: track 1 '' -> 'Announcements/crowd' (C1)",)
    # One comparison stem disagreeing -> (c) fails -> unchanged.
    bad = list(_DTB)
    bad[2] = ("Kam-Ma-Lay", "Soul Of A Man")
    r = _run(bad, canon=_canon(*_DTB_CANON), stem="dtb2007-05-27d1t")
    assert r.changed == {}
    assert r.titles[0] == ""


def test_derektrucksband_2007_05_27_track1_with_the_taper_list():
    desc = read_numbered(_DTB_DESC)
    assert isinstance(desc, DescList) and len(desc.cleaned) == 4
    r = _run(_DTB, desc=desc, canon=_canon(*_DTB_CANON), stem="dtb2007-05-27d1t")
    assert r.changed == {0: "C1"}
    assert r.c1_verdicts == {0: (True, False)}
    assert r.c_holds is None


def test_c2_needs_the_delivered_tag_to_disagree():
    # `Sugaree Jam` agrees with the entry (containment) but so does the delivered tag.
    r = _run([("Sugaree", "Sugaree Jam"), ("Deal", "Deal"), ("Loser", "Loser")],
             desc=_dl("Sugaree", "Deal", "Loser"))
    assert r.changed == {}
    assert r.titles[0] == "Sugaree"


def test_c2_reference_is_the_list_when_there_is_one():
    pairs = [("No Skin Off My Back", "Mood To Move"), ("Deal", "Deal"), ("Loser", "Loser")]
    # The list sides with the lossless tag, the canonical with the delivered one: C2.
    r = _run(pairs, desc=_dl("Mood To Move", "Deal", "Loser"),
             canon=_canon("No Skin Off My Back", "Deal", "Loser"))
    assert r.changed == {0: "C2"}
    # Reversed: the canonical is not consulted while there is a list.
    r = _run(pairs, desc=_dl("No Skin Off My Back", "Deal", "Loser"),
             canon=_canon("Mood To Move", "Deal", "Loser"))
    assert r.changed == {}


def test_exactly_two_off_by_one_lossless_tags_skip_c():
    desc = _dl("Bertha", "Sugaree", "Deal", "Loser", "Jack Straw")
    pairs = [("Bertha", "Bertha"), ("tmp", "Deal"), ("tmp", "Loser"), ("Loser", "Loser"),
             ("Jack Straw", "Jack Straw")]
    r = _run(pairs, desc=desc)
    assert r.declined == "off by one"
    assert r.changed == {}


def test_lossless_tag_agreeing_at_its_own_position_is_not_shifted():
    # A repeated song (`Jam` x 3) agrees with its neighbours' entries too; it is not a shift.
    r = _run([("tmp", "Jam"), ("tmp", "Jam"), ("tmp", "Jam"), ("tmp", "Deal")],
             desc=_dl("Jam", "Jam", "Jam", "Deal"))
    assert r.declined is None
    assert r.changed == {0: "C1", 1: "C1", 2: "C1", 3: "C1"}


def test_c_ships_the_lossless_title_without_its_trailing_taper_marker():
    # darkstarorchestra-2012-10-13 (Checkpoint A ruling h): the FLAC tags read
    # 'Dark Star->' beside a description that lists 'Dark Star->'.
    names = ["Jack Straw", "Here Comes Sunshine", "Feel Like a Stranger", "Dark Star->",
             "Playin in the Band->", "Morning Dew*"]
    r = _run([("tmp", t) for t in names], desc=_dl(*names))
    assert r.changed == {i: "C1" for i in range(6)}
    assert r.titles[3] == "Dark Star" and r.titles[4] == "Playin in the Band"
    assert r.titles[5] == "Morning Dew"
    assert "lossless title: track 4 'tmp' -> 'Dark Star' (C1)" in r.notes

