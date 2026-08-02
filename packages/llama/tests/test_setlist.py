import json
from pathlib import Path

from llama.setlist import parse_setlist

FIXTURES = Path(__file__).parent / "fixtures"

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


def test_enumerated_track_numbers_are_stripped():
    desc = ("Set 1:\n01 Bertha\n02 Jack Straw\n03 Sugaree\n04 Row Jimmy\n"
            "05 Big River\nSet 2:\n06 Truckin'\n07 Drums\n08 Space\n")
    items = parse_setlist(desc).items
    assert [i.title for i in items] == [
        "Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River",
        "Truckin'", "Drums", "Space"]


def test_enumerated_prefixes_without_a_space_are_stripped():
    desc = ("Set 1:\n1.Sugaree\n2.Bertha\n3.Loser\n4.Deal\n5.Althea\n")
    assert [i.title for i in parse_setlist(desc).items] == [
        "Sugaree", "Bertha", "Loser", "Deal", "Althea"]


def test_three_digit_and_repeated_dot_prefixes_are_stripped():
    desc = ("Set 2:\n205....Scarlet Begonias\n206....Fire On The Mountain\n"
            "207. Drums\n208. Space\n209. Truckin'\n")
    assert [i.title for i in parse_setlist(desc).items] == [
        "Scarlet Begonias", "Fire On The Mountain", "Drums", "Space", "Truckin'"]


def test_song_titles_starting_with_numbers_survive():
    # NOT enumerated: only two lines match _NUM_LINE ("8 Miles High", "72 (This
    # Highway's Mean)") - below the >=3 threshold, so the bare-number strip stays gated off.
    desc = ("Set 1:\nBertha\n1952 Vincent Black Lightning\n8 Miles High\n"
            "72 (This Highway's Mean)\nSugaree\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "1952 Vincent Black Lightning" in titles
    assert "8 Miles High" in titles
    assert "72 (This Highway's Mean)" in titles


def test_num_prefix_does_not_corrupt_a_hazard_title_when_gate_is_open():
    # The gate opens here (4 of 5 lines are bare-numbered), and a hazard
    # title sharing the description with real track numbers is NOT immune —
    # that's inherent to a document-level gate. What must not happen is
    # corruption: the old zero-width-satisfiable `_NUM_PREFIX` truncated
    # "1952 Vincent Black Lightning" to "2 Vincent Black Lightning" instead
    # of leaving it alone. Assert the clean (untouched) outcome.
    desc = ("Set 1:\n01 Bertha\n02 Jack Straw\n03 Sugaree\n"
            "1952 Vincent Black Lightning\n05 Deal\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "1952 Vincent Black Lightning" in titles
    assert "2 Vincent Black Lightning" not in titles


def test_two_bare_numbered_lines_do_not_open_the_gate():
    # Below the >=3 threshold: bare leading numbers are retained verbatim.
    desc = "Set 1:\n01 Bertha\n02 Sugaree\n"
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["01 Bertha", "02 Sugaree"]


def test_punctuated_track_numbers_strip_unconditionally_even_below_gate():
    # Only 2 numbered lines - below the >=3 gate - but "N. Title" is
    # unambiguous (digits + punctuation + space never shows up in a real
    # song title) so _TRACK_PREFIX strips it regardless of the gate.
    desc = "Set 1:\n1. Bertha\n2. Sugaree\n"
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Sugaree"]


def test_disc_track_tokens_still_stripped_when_not_enumerated():
    # The constraint this task was most at risk of breaking: d/t disc-track
    # tokens must keep stripping unconditionally even when the bare-number
    # gate never opens (only 2 lines here, both disc/track-token form, no
    # bare numbers at all).
    desc = "Set 1:\nd1t01 Bertha\nt02 Sugaree\n"
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Sugaree"]


def test_personnel_credits_are_not_songs():
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Jerry Garcia - guitar\nBob Weir - guitar\n"
            "Bill Kreutzmann - drums\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_bare_durations_and_disc_markers_are_not_songs():
    desc = ("Set 1:\nBertha\n(13:33)\nJack Straw\n01:50\nDisc #2\n"
            "Sugaree\nRow Jimmy\nBig River\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_a_song_called_drums_survives_a_drums_credit():
    # "Bill Kreutzmann - drums" is a credit; a bare "Drums" is a song.
    desc = ("Set 2:\nTruckin'\nDrums\nSpace\nStella Blue\nSugar Magnolia\n"
            "Mickey Hart - drums\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "Drums" in titles
    assert not any("Mickey" in t for t in titles)


def test_noise_lines_do_not_open_the_enumerated_gate():
    # Defensive hardening, not a fix for a measured corpus problem - see
    # _enumerated_prefix's docstring for the caveat on why this can't be
    # measured from the corpus either way (it stores post-parse setlists,
    # so a line _NOISE already dropped is invisible to it). This test
    # demonstrates the code-level mechanism directly with a synthetic
    # example: three lineage lines that (a) begin with a digit, so they'd
    # count toward the >=3 enumerated-tracklist gate, and (b) already
    # match _NOISE, so the per-line noise filter was always going to drop
    # them as items regardless of the gate. Before this change they still
    # counted toward the gate; "8 Miles High" - a real song title that
    # happens to start with a digit - paid for it: the gate opened on
    # their count alone and _NUM_PREFIX stripped its leading "8 " down to
    # "Miles High". Counting the gate over non-noise lines only means
    # these 3 lines don't count (only the real "8 Miles High" does,
    # 1 < 3), the gate stays shut, and the title survives intact.
    desc = ("2 Disc Two, mixdown by the crew\n"  # word-numeral disc-marker alternative
            "1 SBD source\n"
            "3 FLAC files seeded by taper\n"
            "1952 Vincent Black Lightning\n"
            "8 Miles High\n"
            "Bertha\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["1952 Vincent Black Lightning", "8 Miles High", "Bertha"]


def test_word_numeral_disc_markers_are_noise():
    desc = ("Set 1:\nBertha\nDisc Two\nJack Straw\nDisc II\nSugaree\n"
            "Disc #2\nRow Jimmy\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy"]


def test_word_numeral_disc_marker_glued_to_a_song_drops_the_whole_line():
    # Accepted trade (owner-priced, 2 occurrences against 98 junk lines
    # removed): a noise line with a real song glued onto it in the same
    # physical line loses the glued-on song too, since the whole line is
    # dropped once _NOISE matches anywhere in it - the same compound-
    # heuristic class as the _TRACK_PREFIX/_NUM_PREFIX composition note on
    # _TRACK_PREFIX, not a clean win. This locks in the known, intentional
    # current behavior rather than leaving it to be rediscovered as a bug.
    desc = "Set 1:\nBertha\nDisc Two 1. Eyes of the World\nSugaree\n"
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Sugaree"]
    assert not any("Eyes" in t for t in titles)


def test_word_numeral_disc_marker_survives_a_comma_run_without_junk_title_fix():
    # _NOISE never sees this line's content: it matched _SET_LINE first, so
    # the per-line noise check is bypassed entirely and "Disc Two" would
    # survive as a split title unless _JUNK_TITLE also recognizes the
    # word-numeral form.
    desc = "Set 1: Bertha, Disc Two, Sugaree\n"
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Sugaree"]


def test_bare_e_marker_mid_line_starts_the_encore():
    desc = ("Set 2: Truckin', Stella Blue, Sugar Magnolia; "
            "E: Goin' Down The Road Feelin' Bad, One More Saturday Night")
    items = parse_setlist(desc).items
    by_title = {i.title: i.set for i in items}
    assert by_title["Sugar Magnolia"] == "2"
    assert by_title["Goin' Down The Road Feelin' Bad"] == "encore"
    assert by_title["One More Saturday Night"] == "encore"
    # the marker must not survive inside a title
    assert all(not i.title.upper().startswith("E:") for i in items)


def test_gd74_windsor_keeps_the_whole_setlist_around_its_inline_encore():
    """REGRESSION CANARY. gd74_windsor is one unbroken comma-separated line
    whose only marker is a bare mid-line "E:". When the inline-marker split
    ran BEFORE header truncation, the manufactured "E: ..." line became the
    first `_ENCORE_LINE` match, so `first_marker` truncation threw the entire
    setlist away and the parse collapsed to 8 encore-only items (34 -> 8).
    Measured over 923 cached LMA descriptions, that ordering cost 31
    descriptions their setlists. Truncation is decided over the PRE-SPLIT
    lines precisely so a split-created marker can never truncate anything.

    This pins BOTH halves: the full 34-item parse, AND Task 5's real win -
    the bare "E:" still starts the encore instead of leaving those songs
    labelled with the preceding set.
    """
    md = json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text())
    parsed = parse_setlist(md["metadata"]["description"])

    assert len(parsed.items) == 34
    assert parsed.items[0].title == "U.S. Blues"
    # the 26 songs above the encore marker keep the default set...
    assert [i.set for i in parsed.items[:26]] == ["1"] * 26
    # ...and everything from the bare "E:" onwards is the encore.
    assert [i.set for i in parsed.items[26:]] == ["encore"] * 8
    assert parsed.items[26].title.startswith("It's All Over Now Baby Blue")
    # the marker itself must not survive inside a title
    assert all(not i.title.upper().startswith("E:") for i in parsed.items)


def test_dash_decorated_set_headers_are_recognized():
    """"- Set One -" / "-----Set 1-----" are set headers, not songs.

    A header the parser fails to recognize is not a cosmetic miss: it leaves
    the description with no truncation point, so the band/venue/lineage block
    above it is parsed as songs. Measured on the real corpus,
    ruthiefoster2007-02-25.blues gained 11 junk items that way, and an
    inflated setlist is exactly what pushes the alignment two-pointer out of
    its window.
    """
    desc = (
        "Ruthie Foster\n"
        "Capilano College Performing Arts Theatre\n"
        "North Vancouver, BC\n"
        "- Set One -\n"
        "01 Up Above My Head\n"
        "02 Runaway Soul\n"
        "-----Set 2-----\n"
        "03 Woke Up This Mornin\'\n"
        "- Third Set -\n"
        "04 Mama Said\n"
    )
    items = parse_setlist(desc).items
    by_title = {i.title: i.set for i in items}

    # the header block above the first marker is gone, not parsed as songs
    assert "Ruthie Foster" not in by_title
    assert "Capilano College Performing Arts Theatre" not in by_title
    assert "North Vancouver" not in by_title

    # every song lands in the set its decorated header opened
    assert by_title["Up Above My Head"] == "1"
    assert by_title["Runaway Soul"] == "1"
    assert by_title["Woke Up This Mornin\'"] == "2"
    assert by_title["Mama Said"] == "3"

    # KNOWN, ACCEPTED RESIDUE, pinned so a future change to it is deliberate:
    # the tolerance strips only LEADING decoration, so a trailing run can
    # survive as a junk title - "- Set One -" leaves a bare "-" (split off by
    # _INLINE_MARKER) and "-----Set 2-----" leaves "----" as `rest`. Stripping
    # trailing decoration was considered and declined: it buys one junk item
    # per description and costs a new rule on a path that has already produced
    # two measured regressions, against titles genuinely ending in a dash or
    # asterisk - a shape nobody has measured.
    assert [i.title for i in items] == [
        "-", "Up Above My Head", "Runaway Soul",
        "----", "Woke Up This Mornin\'", "Mama Said",
    ]


def test_undecorated_set_headers_are_unchanged():
    """The decoration run is zero-width-satisfiable: plain headers parse
    exactly as they did before the tolerance existed."""
    parsed = parse_setlist(GD_DESC)
    assert [(i.title, i.set) for i in parsed.items][:2] == [
        ("Morning Dew", "1"),
        ("China Cat Sunflower", "1"),
    ]
    assert parsed.items[-1].set == "encore"


def test_encore_rule_above_a_tracklist_does_not_truncate():
    """COUPLING GUARD - read this before "finishing" `_LEAD_DECOR`.

    `_LEAD_DECOR` is applied to `_SET_LINE`/`_LABELED_SET_LINE` but NOT to
    `_ENCORE_LINE`, and that omission is a COUPLING, not caution. Recognizing
    "---encore:" as an encore marker is *correct*. It is harmful only because
    `parse_setlist` treats the first marker as the start of the setlist: a
    recognized encore rule sitting below a long tracklist would make that
    whole tracklist "header" and discard it.

    Measured on the real corpus: enabling the encore half costs
    nmas2013-02-13 26 real songs (32 items -> 6), and 149 of 923 cached LMA
    descriptions already sit in that first-marker-is-an-encore shape. The
    encore half is built and measured, and must land WITH the header-
    truncation fix - never before it.

    If you enable it early, this test is what tells you.
    """
    desc = (
        "t01) Shimmy She Wobble\n"
        "t02) Back Back Train\n"
        "t03) Goin\' Down South\n"
        "t04) Blue Skies\n"
        "t05) Snake Drive\n"
        "t06) Skinny Woman\n"
        "---encore:\n"
        "t07) Rollin\' N Tumblin\'\n"
    )
    titles = [i.title for i in parse_setlist(desc).items]

    # the tracklist SURVIVES - it is not eaten as header above an encore rule.
    # (The "tNN)" prefixes are left on by _TRACK_PREFIX, which requires
    # whitespace/./-/: after the track token and so does not strip ")". That
    # is pre-existing and orthogonal; asserting the real titles keeps this
    # test about truncation.)
    assert titles == [
        "t01) Shimmy She Wobble",
        "t02) Back Back Train",
        "t03) Goin\' Down South",
        "t04) Blue Skies",
        "t05) Snake Drive",
        "t06) Skinny Woman",
        "---encore:",
        "t07) Rollin\' N Tumblin\'",
    ]
