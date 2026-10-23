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
