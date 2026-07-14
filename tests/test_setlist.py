from llama.setlist import parse_setlist

GD_DESC = """Grateful Dead
RFK Stadium 6/10/73
SBD > Master Reel > DAT > CD > SHN
Recorded by Kidd Candelario; transfer by hollister

Set 1:
Morning Dew
China Cat Sunflower > I Know You Rider
Looks Like Rain

Set 2:
d2t01 - Dark Star > Eyes of the World
He's Gone

Encore:
Johnny B. Goode"""


def test_parses_sets_segues_and_confidence():
    parsed = parse_setlist(GD_DESC)
    titles = [i.title for i in parsed.items]
    assert titles == [
        "Morning Dew", "China Cat Sunflower", "I Know You Rider", "Looks Like Rain",
        "Dark Star", "Eyes of the World", "He's Gone", "Johnny B. Goode",
    ]
    assert [i.set for i in parsed.items] == ["1", "1", "1", "1", "2", "2", "2", "encore"]
    assert parsed.items[1].segue is True   # China Cat > Rider
    assert parsed.items[2].segue is False
    assert parsed.items[4].segue is True   # Dark Star > Eyes
    assert parsed.items[0].normalized == "morning dew"
    assert parsed.confidence == "high"


def test_lineage_lines_are_not_songs():
    parsed = parse_setlist(GD_DESC)
    joined = " ".join(i.title.lower() for i in parsed.items)
    assert "sbd" not in joined and "recorded" not in joined


def test_html_breaks_and_inline_set_marker():
    desc = "Set 1: Bertha, Sugaree<br>Set 2: Truckin' > The Other One<br>E: Casey Jones, Ripple, Brokedown Palace"
    parsed = parse_setlist(desc)
    assert [i.title for i in parsed.items] == [
        "Bertha", "Sugaree", "Truckin'", "The Other One", "Casey Jones", "Ripple", "Brokedown Palace",
    ]
    assert [i.set for i in parsed.items] == ["1", "1", "2", "2", "encore", "encore", "encore"]
    assert parsed.items[2].segue is True
    assert parsed.confidence == "high"


def test_no_markers_is_medium():
    desc = "Bertha\nSugaree\nDeal\nLoser\nCasey Jones"
    parsed = parse_setlist(desc)
    assert all(i.set == "1" for i in parsed.items)
    assert len(parsed.items) == 5
    assert parsed.confidence == "medium"


def test_garbage_is_low():
    parsed = parse_setlist("Recorded by somebody. Transferred via DAT.")
    assert parsed.items == []
    assert parsed.confidence == "low"


def test_encore_marker_does_not_eat_song_titles():
    parsed = parse_setlist("Set 1:\nEyes of the World\nEl Paso\nEncore:\nRipple\nAnd We Bid You Goodnight\nAttics of My Life")
    assert [i.title for i in parsed.items] == [
        "Eyes of the World", "El Paso", "Ripple", "And We Bid You Goodnight", "Attics of My Life",
    ]
    assert [i.set for i in parsed.items] == ["1", "1", "encore", "encore", "encore"]


def test_unbroken_single_line_setlist_is_medium():
    # Real-world archive.org convention (e.g. many early-2000s LMA uploads): the whole
    # setlist as one long comma/segue-separated line, no per-set headers, no line breaks.
    desc = (
        "Morning Dew, Beat It On Down The Line, Ramble On Rose, Jack Straw, Box Of Rain, "
        "They Love Each Other, Row Jimmy, El Paso, Bird Song, Dark Star-> He's Gone-> "
        "Wharf Rat-> Truckin', Sugar Magnolia, Johnny B. Goode"
    )
    parsed = parse_setlist(desc)
    assert len(parsed.items) >= 5
    assert all(i.set == "1" for i in parsed.items)
    assert parsed.confidence == "medium"


def test_unstructured_prose_paragraph_stays_low():
    # A long, unbroken paragraph with no set markers and no comma/segue separators at
    # all collapses to a single implausibly-long "title" fragment and must not count.
    prose = (
        "The crowd at this show was unusually quiet during the first half but grew "
        "louder and more energetic as the night went on until everyone was dancing "
        "together near the stage by the end of the second half of the evening."
    )
    parsed = parse_setlist(prose)
    assert parsed.items == []
    assert parsed.confidence == "low"
