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
