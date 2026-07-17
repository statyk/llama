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


def test_inline_set_markers_without_line_breaks():
    # Real Veneta '72 convention: the whole three-set show on ONE line, set
    # markers inline, numbered encores. Every set must be recovered.
    desc = ("Set I: Promised Land, Sugaree, Me & My Uncle, China Cat Sunflower >"
            "I Know You Rider, Bertha Set II: Playin' in the Band, He's Gone, "
            "Jack Straw Set III: Dark Star> El Paso, Sing Me Back Home, "
            "Sugar Magnolia, E1: Casey Jones, E2: Saturday Night")
    parsed = parse_setlist(desc)
    by_set = {}
    for i in parsed.items:
        by_set.setdefault(i.set, []).append(i.title)
    assert set(by_set) == {"1", "2", "3", "encore"}
    assert by_set["3"] == ["Dark Star", "El Paso", "Sing Me Back Home", "Sugar Magnolia"]
    assert by_set["encore"] == ["Casey Jones", "Saturday Night"]
    assert parsed.confidence == "high"


def test_html_entities_unescape_before_parsing():
    # Common LMA convention: segues written as &gt; and ampersands as &amp;.
    desc = "Set 1: Bertha, Me &amp; My Uncle, Drums &gt; The Wheel &gt; Wharf Rat"
    parsed = parse_setlist(desc)
    assert [i.title for i in parsed.items] == [
        "Bertha", "Me & My Uncle", "Drums", "The Wheel", "Wharf Rat"]
    assert parsed.items[2].segue is True and parsed.items[3].segue is True


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


# --- Corpus of real archive.org descriptions that broke the parser once. ---
# Each string is verbatim (or minimally trimmed) from a live item. When a new
# pathological description surfaces, add it here with its expected outcome.

VENETA_BRAVERMAN = (
    "Set I: Promised Land, Sugaree, Me & My Uncle, Deal, Black Throated Wind, "
    "China Cat Sunflower >I Know You Rider, Mexicali Blues, Bertha Set II: "
    "Playin' in the Band, He's Gone, Jack Straw, Bird Song, Greatest Story Ever Told "
    "Set III: Dark Star> El Paso, Sing Me Back Home, Sugar Magnolia, "
    "E1: Casey Jones, E2: Saturday Night"
)

BOSTON_77_ENTITIES = (
    "Set I Bertha Cassidy Deal Jack Straw Peggy-O New Minglewood Blues "
    "Mississippi Half-Step Uptown Toodleloo &gt; Big River Tennessee Jed "
    "The Music Never Stopped Set II Terrapin Station Samson & Delilah "
    "Friend Of The Devil Estimated Prophet Eyes Of The World &gt; Drums &gt; "
    "The Wheel &gt; Wharf Rat &gt; Around & Around Encore: U.S. Blues"
)

VENETA_SPACE_SEPARATED = (
    "Set One The Promised Land Sugaree Me And My Uncle Deal Black Throated Wind "
    "China Cat Sunflower I Know You Rider Mexicali Blues Bertha"
)

SCR_STAGE_SETS = """Early Set - Grove Stage

1. Intro
2. New Song
3. Norma Jean
4. Sittin' Alone in the Moonlight
5. Done Gone
6. Carolina Home
7. Mr. Taylor's New Home
8. Hibritton Mountain
9. Don't Let My Heart Be Lonesome
10. Tennessee Blues


Late Set - Meadow Stage

11. T'aint True
12. Big Jet Airplane
13. Summer's Gone
14. The Dusty Miller
15. The Wicked Path of Sin
16. Live and Let Live
17. 8:45?
18. I'll Take the Blame
19. Five More Days
20. Alabama Jubilee
21. Devil in Disguise
22. Endless Highway
23. (I've Got My) Future on Ice
24. Rawhide"""


def test_corpus_veneta_inline_markers_and_numbered_encores():
    p = parse_setlist(VENETA_BRAVERMAN)
    assert {i.set for i in p.items} == {"1", "2", "3", "encore"}
    assert p.confidence == "high"
    assert len(p.items) >= 18


def test_corpus_entity_segues_do_not_mangle_titles():
    p = parse_setlist(BOSTON_77_ENTITIES)
    titles = [i.title for i in p.items]
    assert "Wharf Rat" in titles and "The Wheel" in titles
    assert not any("&" in t and "gt" in t for t in titles)  # no '&gt' residue


def test_corpus_space_separated_setlist_degrades_gracefully():
    # No commas, no segue marks: undecipherable deterministically. The parser
    # must not invent paragraph-length "titles"; it reports low confidence so
    # ranking prefers a sibling parse or the LLM extraction fallback.
    p = parse_setlist(VENETA_SPACE_SEPARATED)
    assert p.confidence == "low"
    assert all(len(i.title) <= 80 for i in p.items)


def test_corpus_labeled_stage_sets_and_numbered_lists():
    # steepcanyonrangers 2002-07-07: festival sets labeled "Early Set - Grove
    # Stage" / "Late Set - Meadow Stage" with a numbered song list. The old
    # parser saw no set markers (everything landed in set 1) and kept the
    # "3. " list prefixes, which poisoned alignment downstream.
    p = parse_setlist(SCR_STAGE_SETS)
    by_set: dict[str, list[str]] = {}
    for i in p.items:
        by_set.setdefault(i.set, []).append(i.title)
    assert set(by_set) == {"1", "2"}
    assert by_set["1"] == [
        "Intro", "New Song", "Norma Jean", "Sittin' Alone in the Moonlight",
        "Done Gone", "Carolina Home", "Mr. Taylor's New Home", "Hibritton Mountain",
        "Don't Let My Heart Be Lonesome", "Tennessee Blues",
    ]
    assert by_set["2"][0] == "T'aint True" and by_set["2"][-1] == "Rawhide"
    assert "8:45?" in by_set["2"]  # prefix "17. " stripped, title digits kept
    assert p.confidence == "high"


def test_labeled_set_with_colon_keeps_inline_songs():
    # Colon after a labeled header introduces songs; a dash introduces a
    # stage/venue label, never songs.
    desc = "Acoustic Set: Ripple, Attics of My Life\nElectric Set: Sugar Magnolia"
    p = parse_setlist(desc)
    assert [(i.set, i.title) for i in p.items] == [
        ("1", "Ripple"), ("1", "Attics of My Life"), ("2", "Sugar Magnolia")]


def test_spelled_ordinal_set_headers():
    desc = "First Set:\nBertha\nSugaree\nSecond Set:\nTruckin'\nDeal\nEncore:\nRipple"
    p = parse_setlist(desc)
    assert [i.set for i in p.items] == ["1", "1", "2", "2", "encore"]
    assert p.confidence == "high"


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
