from llama.desc_list import clean_entries, clean_one, is_header_shape, written_seconds


def test_cleaning_fixtures_from_real_lists():
    # rosehilldrive-2008-12-31
    out = clean_entries(["(05:12) 01-?", "(03:43) 02-Sneak Out", "(04:01) 03-X"])
    assert [c.text for c in out] == ["?", "Sneak Out", "X"]
    # motherhips-2010-10-16
    assert clean_one(".01  I'm No Good", strip_leader=True).text == "I'm No Good"
    # gomez-2006-10-06
    c = clean_one("Shot Shot  3.00")
    assert c.text == "Shot Shot"
    assert c.durations == (180.0,)
    assert clean_one("(05:12) Bertha").text == "Bertha"


def test_duration_forms():
    for raw in ["Song [4:47]", "Song (4:47)", "Song\t4:47", "Song 4:47"]:
        c = clean_one(raw)
        assert c.text == "Song", raw
        assert c.durations == (287.0,), raw
    c = clean_one("(6:40) Song")
    assert c.text == "Song" and c.durations == (400.0,)
    c = clean_one("05:12 - Song")
    assert c.text == "Song" and c.durations == (312.0,)
    c = clean_one("Song (1:02:03)")
    assert c.text == "Song" and c.durations == (3723.0,)
    c = clean_one("Song (4:47) (5:02)")
    assert c.text == "Song" and len(c.durations) == 2
    assert written_seconds(c) is None
    assert written_seconds(clean_one("Song 4:47")) == 287.0
    assert written_seconds(clean_one("Song")) is None
    assert clean_one("2:22").text == "2:22"
    assert clean_one("Song 4:47").trailing_time_stripped is True
    assert clean_one("Song [4:47]").trailing_time_stripped is False
    c = clean_one("1 Samuel 15:23")
    assert c.text == "1 Samuel" and c.trailing_time_stripped


def test_leader_stripped_only_under_the_vote():
    assert [c.text for c in clean_entries(["01-A", "02-B", "03-C", "D"])] == [
        "01-A", "02-B", "03-C", "D"]
    out = clean_entries(["01-A", "02-B", "03-C", "04-D", "E"])
    assert [c.text for c in out] == ["A", "B", "C", "D", "E"]
    assert out[0].leader_stripped and not out[4].leader_stripped
    assert [c.text for c in clean_entries(["01-A", "02-B"])] == ["01-A", "02-B"]


def test_date_shaped_entries_keep_their_numbers():
    odd = ["09-15-00", "12.28.99", "01.", "01-"]
    for x in odd:
        c = clean_one(x, strip_leader=True)
        assert c.text == x and not c.leader_stripped
    # a list where the vote demonstrably passes: 16 numbered of 20 = 0.8
    base = [f"{i:02d}-Song{chr(65 + i)}" for i in range(1, 17)]
    out = clean_entries(base + odd)
    assert all(c.leader_stripped for c in out[:16])
    assert [c.text for c in out][16:] == odd
    assert not any(c.leader_stripped for c in out[16:])


def test_markers_and_encore_and_quotes():
    assert clean_one("Pyramid County (1) > Little Maggie").text == "Pyramid County > Little Maggie"
    assert clean_one("Bertha >").text == "Bertha"
    assert clean_one("Dew ->").text == "Dew"
    assert clean_one("Jack Straw *").text == "Jack Straw"
    assert clean_one("Jack Straw @").text == "Jack Straw"
    for raw in ["E: Baby Blue", "EN: Baby Blue", "Encore: Baby Blue"]:
        assert clean_one(raw).text == "Baby Blue"
    assert clean_one('"Sugaree"').text == "Sugaree"
    c = clean_one("Filler: Dark Star")
    assert c.text == "Dark Star" and c.filler_marked


def test_entities_and_curly_quotes_clean():
    assert clean_one("Me &amp; My Uncle").text == "Me & My Uncle"
    assert clean_one("“Sugaree”").text == "Sugaree"
    assert clean_one("Truckin’").text == "Truckin’"


def test_header_shape():
    for t in ["Set 2", "CD 2", "Disc Two", "Disc 1, Track 10", "[Set One]"]:
        assert is_header_shape(t), t
    for t in ["Set 2: Bertha", '"Set" 1:', "Settle Down", "Jam"]:
        assert not is_header_shape(t), t


from llama.desc_list import read_numbered  # noqa: E402


def test_reads_a_plain_numbered_list():
    d = read_numbered("1. Bertha\n2. Jack Straw\n3) Deal")
    assert d.raws == ("Bertha", "Jack Straw", "Deal")
    assert set(d.blocks) == {0} and d.boundaries == ()
    assert d.reader == "numbered"
    assert tuple(c.text for c in d.cleaned) == d.raws


def test_br_separated_entries():
    d = read_numbered("1. Bertha<br />2. Jack Straw<br/>3) Deal")
    assert d.raws == ("Bertha", "Jack Straw", "Deal")


def test_set_header_restart_is_a_new_block():
    d = read_numbered("Set 1:\n1. A\n2. B\nSet 2:\n=====\n1. C")
    assert d.raws == ("A", "B", "C")
    assert d.blocks == (0, 0, 1) and d.boundaries == ("set",)


def test_numbering_continuing_across_a_header_is_one_list_two_blocks():
    body = "\n".join(f"{i}. S{i}" for i in range(1, 11))
    d = read_numbered(f"{body}\nDisc 2\n11. K")
    assert len(d.raws) == 11
    assert d.blocks == (0,) * 10 + (1,) and d.boundaries == ("disc",)
    assert read_numbered("1. A\n2. B\n1. C") == "non-contiguous at 1"


def test_header_with_text_is_a_boundary_not_an_entry():
    d = read_numbered("1. A\n2. B\nSet 2: Bertha\n3. C")
    assert d.raws == ("A", "B", "C")
    assert d.blocks == (0, 0, 1) and d.boundaries == ("set",)
    d = read_numbered("1. A\n2. B\nSet 2:\n3. C")
    assert d.blocks == (0, 0, 1)


def test_restart_after_encore_line():
    s = "1. A\n2. B\nEncore:\n1. C"
    assert read_numbered(s) == "non-contiguous at 1"
    d = read_numbered(s, encore_header=True)
    assert d.boundaries == ("encore",) and d.blocks == (0, 0, 1)


def test_disc_prefix_change_is_a_restart():
    d = read_numbered("d1t01- A\nd1t02- B\nd2t01- C")
    assert d.raws == ("A", "B", "C")
    assert d.blocks == (0, 0, 1) and d.boundaries == ("disc",)


def test_three_digit_numbers_read_as_disc_prefixed():
    d = read_numbered("101 A\n102 B\n201 C")
    assert d.blocks == (0, 0, 1) and d.boundaries == ("disc",)


def test_gaps_are_inadmissible():
    assert read_numbered("1. A\n2. B\n4. D") == "non-contiguous at 4"


def test_empty_numbered_line_is_inadmissible():
    assert read_numbered("1. A\n07) \n3. C") == "empty entry"
    d = read_numbered("1. A\n2:\n2. B")
    assert d.raws == ("A", "B")


def test_timestamp_lines_are_not_entries():
    d = read_numbered("12:30 tuning\n1. A\n2. B")
    assert d.raws == ("A", "B")
    assert read_numbered("12:30 tuning") == "no numbered lines"


def test_run_on_line_yields_no_list():
    # furthur-2012-04-21 (selected description, verbatim excerpt): one run-on line.
    desc = (
        "Tuning, Playing in the Band> China Cat> Estimated Prophet> Ramble On Rose, "
        "Birdsong, Sugar Magnolia> Playing in the Band Help on the Way> Slipknot> "
        "Franklins Tower> Cryptical Envelopment> The Other One> Shakedown Street> "
        "Viola Lee Blues> Bertha> Viola Lee Blues> Wharf Rat> Viola Lee Blues, "
        "Stella Blue> I Know You Rider, Donor Rap. U.S. Blues"
    )
    assert isinstance(read_numbered(desc), str)


# --- Reader (ii): parse_setlist's own items, and read_desc_list ----------------------------

from llama.desc_list import (  # noqa: E402
    DescList,
    DescRead,
    drop_leading_artist_items,
    read_desc_list,
    read_parse,
)
from llama.models import ParsedSetlist, SetlistItem  # noqa: E402
from llama.setlist import parse_setlist  # noqa: E402


def _ident(p):
    return p, frozenset()


def _removing(drop: set[int], report: frozenset[int]):
    """A test cleaner: removes the input items in `drop`, reports `report`."""
    def clean(p):
        kept = [it for i, it in enumerate(p.items) if i not in drop]
        return p.model_copy(update={"items": kept}), report
    return clean


ENCORE_DESC = "Set 1:\nBertha\nDeal\nEncore:\nRipple"
BANNER_DESC = (
    "Grateful Dead\nWinterland Arena, San Francisco CA\nSoundboard > Reel > DAT > FLAC\n"
    "Set 1:\nBertha\nDeal\nLineage: SBD > DAT > FLAC\nSet 2:\nPlayin' In The Band"
)
# railroadearth-2004-04-09 (rre2004-04-09.shnf), the selected description, verbatim.
RRE_DESC = (
    "Disc 1: Set 1:  \nEverything Comes Together\nDrag Him Down\nSaddle Of The Sun* >\n"
    "Mourning Flies*\nLois Anne*\nJust So You Know*\nFlowers Tween The Stones*\n"
    "Ragtime Annie Lee*\n\nSet 2:\nRaindance*\nDandelion Wine*\nReal Love*\n\nDisc 2: \n"
    "Head*\nGoat*\nRailroad Earth*\nBird In A House*\nWaterfountain Quicksand*\n"
    "Brown County Breakdown*\nBowling Green*\n\nDisc 3:\nI Am A Mess*\nPeace*\n"
    "post show chatter\n\nEncore:\nSeven Story Mountain*\nSittin' Here In Limbo*\n"
    "Sing For Me*"
)


def test_parse_items_admissible_one_per_line():
    d = read_parse(ENCORE_DESC, artist="Grateful Dead", clean=_ident)
    assert d.reader == "parse"
    assert d.raws == ("Bertha", "Deal", "Ripple")
    assert d.blocks == (0, 0, 1) and d.boundaries == ("encore",)
    assert tuple(c.text for c in d.cleaned) == d.raws


def test_set_change_is_a_set_boundary():
    d = read_parse("Set 1:\nBertha\nSet 2:\nDeal\nEncore:\nRipple", artist="X",
                   clean=_ident)
    assert d.blocks == (0, 1, 2) and d.boundaries == ("set", "encore")


def test_removed_indices_exempt_their_lines():
    # Line 0 is a banner line yielding two items (`Fox Theatre`, `Boulder CO`).
    desc = "Fox Theatre, Boulder CO\nBertha\nDeal\nRipple"
    assert len(parse_setlist(desc).items) == 5
    # Only part of the line removed: not exempt (spec (ii)), so it still yields two items.
    r = read_parse(desc, artist="X", clean=_removing({0}, frozenset({0})))
    assert r == "line yields 2 items: Fox Theatre, Boulder CO"
    # Every item of the line removed: exempt.
    d = read_parse(desc, artist="X", clean=_removing({0, 1}, frozenset({0, 1})))
    assert isinstance(d, DescList)
    assert d.raws == ("Bertha", "Deal", "Ripple")
    r = read_parse(desc, artist="X", clean=_removing({0}, frozenset()))
    assert r == "line yields 2 items: Fox Theatre, Boulder CO"

    # A rewrite (footnote marker) is not a removal: no line is exempted by it.
    def rewrite(p):
        items = [it.model_copy(update={"title": it.title.replace(" (1)", "")})
                 for it in p.items]
        return p.model_copy(update={"items": items}), frozenset()
    d = read_parse("Bertha (1)\nDeal\nRipple", artist="X", clean=rewrite)
    assert d.raws == ("Bertha", "Deal", "Ripple")
    assert read_parse("Bertha (1), Sugaree\nDeal\nRipple", artist="X",
                      clean=rewrite) == "line yields 2 items: Bertha (1), Sugaree"


def test_cleaner_report_disagreeing_with_its_output_is_inadmissible():
    r = read_parse("Bertha\nDeal\nRipple", artist="X", clean=_removing({0}, frozenset()))
    assert r == "cleaner count disagrees"


def test_a_line_split_into_two_items_is_inadmissible():
    r = read_parse("Bertha > Jack Straw\nDeal", artist="X", clean=_ident)
    assert r == "line yields 2 items: Bertha > Jack Straw"
    # an inline marker splitting one raw line counts the same way
    r = read_parse("Set 1: Bertha\nDeal E: Ripple", artist="X", clean=_ident)
    assert r == "line yields 2 items: Deal E: Ripple"


def test_a_non_exempt_line_yielding_nothing_is_inadmissible():
    # Not a header, not noise, not removed: an over-length prose line yields 0 items.
    prose = "x" * 90
    r = read_parse(f"Bertha\n{prose}\nDeal", artist="X", clean=_ident)
    assert r == f"line yields 0 items: {prose}"


def test_artist_item_dropped_only_in_the_banner():
    d = read_parse(RRE_DESC, artist="Railroad Earth", clean=_ident)
    assert isinstance(d, DescList)
    assert "Railroad Earth" in d.raws  # the self-titled song mid-list stays
    assert len(d.raws) == 24
    assert d.boundaries == ("set", "encore")
    led = read_parse("Railroad Earth\n" + RRE_DESC, artist="Railroad Earth", clean=_ident)
    assert isinstance(led, DescList)
    assert led.raws == d.raws  # the leading banner line is dropped, the song is not
    p = parse_setlist("Railroad Earth\nRailroad Earth\nBertha\nRailroad Earth")
    assert [i.title for i in drop_leading_artist_items(p, "Railroad Earth").items] == [
        "Bertha", "Railroad Earth"]
    assert drop_leading_artist_items(p, "") == p


def test_banner_and_noise_lines_are_exempt():
    d = read_parse(BANNER_DESC, artist="Grateful Dead", clean=_ident)
    assert isinstance(d, DescList)
    assert d.raws == ("Bertha", "Deal", "Playin' In The Band")
    assert d.boundaries == ("set",)
    # No marker: nothing is truncated, so a banner line is exempt only when the cleaner
    # removes its item; a lineage line in the body is `_NOISE` and always exempt.
    desc = "Winterland Arena, San Francisco CA\nBertha\nDeal\nTransferred by J. Taper\nRipple"
    assert read_parse(desc, artist="X", clean=_ident) == (
        "line yields 2 items: Winterland Arena, San Francisco CA")
    d = read_parse(desc, artist="X", clean=_removing({0, 1}, frozenset({0, 1})))
    assert d.raws == ("Bertha", "Deal", "Ripple")


def test_empty_numbered_line_makes_both_readers_inadmissible():
    desc = "1. A\n07) \n3. C"
    r = read_desc_list(desc, 3, artist="X", clean=_ident)
    assert isinstance(r, DescRead)
    assert r.used is None
    assert r.numbered == "empty entry"
    assert r.parsed == "empty entry"


def test_prefers_numbered_when_both_qualify():
    desc = "1. Bertha\n2. Deal\n3. Ripple"
    r = read_desc_list(desc, 3, artist="X", clean=_ident)
    assert isinstance(r.numbered, DescList) and isinstance(r.parsed, DescList)
    assert r.used is r.numbered and r.used.reader == "numbered"
    assert read_desc_list(desc, 4, artist="X", clean=_ident).used is None


def test_count_matched_parse_used_when_numbered_is_not_count_matched():
    # (i) reads two numbered lines; (ii) also admits the unnumbered encore line.
    desc = "1. Bertha\n2. Deal\nRipple"
    r = read_desc_list(desc, 3, artist="X", clean=_ident)
    assert len(r.numbered.raws) == 2
    assert r.used is r.parsed and r.used.raws == ("Bertha", "Deal", "Ripple")


def test_parse_only_when_numbered_absent():
    r = read_desc_list("Bertha\nDeal\nRipple", 3, artist="X", clean=_ident)
    assert r.numbered == "no numbered lines"
    assert r.used is not None and r.used.reader == "parse"


def test_no_items_reason():
    assert read_parse("", artist="X", clean=_ident) == "no items"
    assert read_parse("Bertha", artist="X",
                      clean=_removing({0}, frozenset({0}))) == "no items"


def _ps(conf, rows):
    return ParsedSetlist(confidence=conf, items=[
        SetlistItem(title=t, normalized=n, set=s, segue=g) for t, n, s, g in rows])


def test_parse_setlist_unchanged():
    """(pin) Generated on `main` (setlist.py byte-identical); reader (ii) must not move
    parse_setlist's outputs."""
    assert parse_setlist(ENCORE_DESC) == _ps("low", [
        ('Bertha', 'bertha', '1', False),
        ('Deal', 'deal', '1', False),
        ('Ripple', 'ripple', 'encore', False),
    ])
    assert parse_setlist(BANNER_DESC) == _ps("low", [
        ('Bertha', 'bertha', '1', False),
        ('Deal', 'deal', '1', False),
        ("Playin' In The Band", 'playing in the band', '2', False),
    ])
    assert parse_setlist(RRE_DESC) == _ps("high", [
        ('Everything Comes Together', 'everything comes together', '1', False),
        ('Drag Him Down', 'drag him down', '1', False),
        ('Saddle Of The Sun', 'saddle of the sun', '1', True),
        ('Mourning Flies', 'mourning flies', '1', False),
        ('Lois Anne', 'lois anne', '1', False),
        ('Just So You Know', 'just so you know', '1', False),
        ('Flowers Tween The Stones', 'flowers tween the stones', '1', False),
        ('Ragtime Annie Lee', 'ragtime annie lee', '1', False),
        ('Raindance', 'raindance', '2', False),
        ('Dandelion Wine', 'dandelion wine', '2', False),
        ('Real Love', 'real love', '2', False),
        ('Head', 'head', '2', False),
        ('Goat', 'goat', '2', False),
        ('Railroad Earth', 'railroad earth', '2', False),
        ('Bird In A House', 'bird in a house', '2', False),
        ('Waterfountain Quicksand', 'waterfountain quicksand', '2', False),
        ('Brown County Breakdown', 'brown county breakdown', '2', False),
        ('Bowling Green', 'bowling green', '2', False),
        ('I Am A Mess', 'i am a mess', '2', False),
        ('Peace', 'peace', '2', False),
        ('post show chatter', 'post show chatter', '2', False),
        ('Seven Story Mountain', 'seven story mountain', 'encore', False),
        ("Sittin' Here In Limbo", 'sittin here in limbo', 'encore', False),
        ('Sing For Me', 'sing for me', 'encore', False),
    ])


def test_per_line_counts_must_sum_to_the_parse():
    # The document is enumerated, so parse_setlist strips `04 ` and drops the bare time;
    # judged on its own the raw line still yields one item.
    desc = "1 Bertha\n2 Deal\n3 Ripple\n04 3:45"
    assert len(parse_setlist(desc).items) == 3
    assert read_parse(desc, artist="X", clean=_ident) == "per-line count disagrees"
