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


# --- Class A: the credit-line GRAMMAR (task-3-attribution.md sections 1+3) ---
# Five measured shape dimensions the old dash-anchored suffix rule missed
# (`trail`, `mod`, `nospace`, `colon`, `vocab`), plus the connector and
# instrument-word additions that took the rule from variant A (793 dropped)
# to the shipped variant A2 (853 dropped). Each test below pins one
# dimension with the exact example line from the measurement.


def test_credit_line_trailing_decoration_survives_the_drop():
    # `trail`: something after the instrument (*, #) - the single largest
    # dimension, 132/529.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Martin Fierro - Saxophone *\nMatthew Kelly - Harmonica #\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_modifier_between_dash_and_instrument():
    # `mod`: a modifier word (lead/rhythm/backing/...) between the dash and
    # the instrument - 93/529. "Keyboards and Vocals" also exercises the
    # A2 one-or-more connector (a bare `and` joining two instruments).
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Jeff Mattson – lead guitar\nRob Barraco - Keyboards and Vocals\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_modifier_and_trailing_decoration_combine():
    # `mod`+`trail` together - "Talking Drum" is the design's own worked
    # example: NOT a vocabulary miss (`drums?` was always in the list), a
    # modifier ("Talking") sitting between the dash and the instrument.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Sikiru Adepoju - Talking Drum *\nBob Weir - rhythm guitar & vocals\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_no_space_before_the_dash():
    # `nospace`: the second-largest single dimension after `trail`, 51/529.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Del McCoury- guitar\nRonnie McCoury-mandolin\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_colon_separator_with_no_space():
    # `nospace`+`colon`: a colon instead of a dash, glued to the name.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Dino English: Drums\nLisa Mackey: Vocals\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_out_of_original_vocabulary():
    # `vocab`: the smallest dimension (16/529, 3%) - a pure word-list miss
    # with no other shape problem. Not the primary fix, but still covered.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Jeff Chimenti - Keys\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_comma_separated_instrument_list():
    # A single NAME credited with several instruments on one line - the
    # shape that produces the M2 "split component" residue when the whole
    # line is declined (see task-3-attribution.md section 1): fixing the
    # LINE removes every comma-separated tail item too, in one pass.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Bruce Hornsby - Piano, Accordion\n"
            "Oteil Burbridge - Bass Guitar, Percussion, Vocals\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_semicolon_joined_multi_name_entries():
    # Several NAME-instrument ENTRYs on one physical line, `;`-joined - the
    # measured multi-credit line ("Chris Whitley...; Alan Gevaert...; ...").
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Chris Whitley: vocals, guitar; Alan Gevaert: bass; "
            "Louie Lepore: guitar; Billy Ward: drums\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_a2_extra_instrument_words():
    # The two literal additions variant A2 carries over variant A: "drumz"
    # (misspelling) and "Hammond B-3" (a modifier + instrument compound).
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Jay Lane - drumz\nVince Welnick - Hammond B-3\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_with_guest_prefix():
    # MEASURED (fix round 1): a "w/ <name> - <instrument>" guest credit -
    # common "with special guest X" phrasing - is caught via the leading
    # `w/`/`#w/` decor tolerance added to `_CREDIT_LINE`, without loosening
    # the whole-line anchor itself (the prefix is a fixed literal
    # alternative, not a wildcard).
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "w/ Oteil Burbridge - bass\n#w/ Casey Driessen - Fiddle\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_with_quoted_nickname():
    # MEASURED (fix round 1): a quoted nickname aside inside the name
    # ('Brad "The EZB" Morgan') is tolerated as one bounded-length "word"
    # in `_CREDIT_NAME`, not an open-ended wildcard.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Brad \"The EZB\" Morgan - drums\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_with_non_ascii_name():
    # MEASURED (fix round 1): `_CREDIT_NAME`'s letter class covers any
    # Unicode letter, not just A-Za-z, so a real accented name like
    # "Béla Fleck" is reachable.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Béla Fleck - Banjo\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_credit_line_residual_after_name_widening_still_leaks():
    # DOCUMENTED RESIDUAL (fix round 1, not chased further - "one attempt,
    # then stop"): a leading footnote-number marker before "w/" ("1. w/
    # Oteil Burbridge - bass") and two full entries joined by a bare comma
    # instead of ";" both sit outside "widen NAME only" and are left as
    # accepted residual - this pins that they are STILL not dropped, so a
    # future widening attempt doesn't have to rediscover the boundary.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "1. w/ Oteil Burbridge - bass\n"
            "w/ Anna Moss - vocals, Joel Ludford - guitar\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert any("Oteil Burbridge" in t for t in titles)
    assert any("Anna Moss" in t for t in titles)


def test_credit_line_role_vocabulary_is_out_of_scope():
    # DECIDED AND DECLINED: no role vocabulary (sound/lighting/production
    # are real title words). A role-only credit line is NOT dropped - it is
    # not credit-shaped under this grammar (no instrument word), so it
    # still reaches the item list. This pins the deliberate scope boundary,
    # not a defect.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Phil Ek: sound\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert any("Phil Ek" in t for t in titles)


def test_credit_line_hazard_words_survive():
    # The standing-ruling hazard probe (task-3-attribution.md section 3):
    # none of these may ever be treated as noise, credit-shaped or not.
    # `Drums` and `Space` are SONGS by standing domain ruling. `drums`
    # (lowercase) and `Drumz` are included explicitly, not just `Drums` -
    # `drumz` is a word THIS CHANGE added to `_CREDIT_INSTR`, so `Drumz` is
    # precisely the token whose song-hood this new vocabulary put at risk.
    # "Drums > Space" is a segue, not a single title - `_split_songs` splits
    # it into "Drums" then "Space" upstream of any noise/junk filtering, so
    # it is exercised here as a segue pair rather than as one literal title.
    desc = ("Set 1:\nBertha\n333\n1977\n1662\n16\n?\n??\nDrums\ndrums\nDrumz\n"
            "Space\nJam\nDrums > Space\nDrums/Space\n")
    titles = [i.title for i in parse_setlist(desc).items]
    for hazard in ("Bertha", "333", "1977", "1662", "16", "?", "??",
                   "Drums", "drums", "Drumz", "Space", "Jam", "Drums/Space"):
        assert hazard in titles, f"{hazard!r} was wrongly treated as noise"


def test_credit_line_requires_whole_line_consumption():
    """LOAD-BEARING: the `^...$` whole-line-consumption anchor is the
    false-positive guard, not the vocabulary (task-3-attribution.md
    section 3, binding condition 1). A line is dropped only if EVERY token
    on it is a name, a separator, a connector, a modifier or an instrument
    - nothing may be left over.

    "Sugaree, Jerry Garcia - guitar" is one physical description line: the
    credit tail ("Jerry Garcia - guitar") is genuinely credit-shaped, but
    "Sugaree" ahead of it is not part of any NAME-instrument ENTRY (no
    dash/colon separator follows it, and it is followed by a bare comma),
    so the line as a WHOLE does not reduce to the credit grammar. Correct
    behavior: the line survives `_NOISE` untouched and is handed to the
    comma splitter, which keeps "Sugaree" as a clean title (and leaks the
    credit tail as its own junk item - an accepted M2-shaped residual, not
    what this test is pinning).

    If the anchor is relaxed to an unanchored SEARCH - i.e. `_NOISE` only
    has to find the credit shape ANYWHERE in the line, not consume all of
    it - this line is wrongly recognized as pure noise (the credit tail is
    still found via search) and the WHOLE line, "Sugaree" included, is
    dropped outright before it ever reaches the comma splitter: the exact
    `Disc Two 1. Eyes of the World` glued-song casualty class this design
    exists to avoid. This test is the one that must FAIL under that
    mutation; it was executed by hand (see task-3-implementer.md) and did.
    """
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree, Jerry Garcia - guitar\n"
            "Row Jimmy\nBig River\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "Sugaree" in titles


def test_credit_line_requires_whole_line_consumption_at_the_end_too():
    # MEASURED: dropping only the trailing `$` newly eats 48 distinct lines,
    # including the real song 'Two-Horn Blues' (bfft1999-04-25.nak.flac16) —
    # "Two" is a NAME, "-" a separator, "Horn" an instrument, and "Blues" is
    # simply left over. Nothing may be left over - this is a SEPARATE test
    # from the `^` one above (not another assert on it) because `assert`
    # short-circuits and the first test's only assert already guards `^`.
    desc = ("Set 1:\nBertha\nJack Straw\nTwo-Horn Blues\nRow Jimmy\nBig River\n")
    assert "Two-Horn Blues" in [i.title for i in parse_setlist(desc).items]


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
    """RETARGETED - was the COUPLING GUARD; now pins the coupled fix itself.

    Formerly a characterization test pinning a KNOWN COUPLING: `_ENCORE_LINE`
    lacked `_LEAD_DECOR` tolerance on purpose, because `parse_setlist` used to
    treat ANY first marker as the start of the setlist, and a recognized
    "---encore:" marker sitting below a long tracklist would make the whole
    tracklist "header" and discard it (measured: nmas2013-02-13 lost 26 real
    songs, 32 items -> 6). That coupling is now discharged by
    `_may_start_a_show` - an encore marker can never open a show, so it can no
    longer truncate anything above it - so `_ENCORE_LINE` now carries the
    same leading-decoration tolerance the set markers already had.

    What this test pins now: "---encore:" IS recognized as a marker (it no
    longer survives as a literal junk title), the tracklist above it survives
    intact, and the song below it is correctly labelled "encore".
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
    items = parse_setlist(desc).items
    titles = [i.title for i in items]

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
        "t07) Rollin\' N Tumblin\'",
    ]
    # "---encore:" is now a recognized marker, not a title, and it correctly
    # labels the song below it - the coupled encore-tolerance half.
    assert [i.set for i in items] == ["1"] * 6 + ["encore"]


def test_encore_first_marker_does_not_discard_the_setlist():
    desc = ("Shimmy She Wobble\nBack Back Train\nCypress Grove\nDeep Ellum\n"
            "Goin' Down South\nRolling Stone\nSkinny Woman\nStanding In My Doorway\n"
            "Encore:\nRollin' N Tumblin'\n")
    items = parse_setlist(desc).items
    assert len(items) == 9
    assert [i.title for i in items][:2] == ["Shimmy She Wobble", "Back Back Train"]
    assert {i.set for i in items} == {"1", "encore"}
    assert [i.set for i in items][-1] == "encore"


def test_set_two_first_marker_does_not_discard_the_setlist():
    # A show does not start at Set 2; the block above IS set 1.
    desc = ("Bertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Set 2:\nTruckin'\nStella Blue\n")
    items = parse_setlist(desc).items
    assert [i.title for i in items][:5] == [
        "Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]
    assert [i.set for i in items] == ["1"] * 5 + ["2"] * 2


def test_set_one_first_marker_still_truncates_its_header():
    # Deliberately unchanged: content above a Set 1 marker is header/support-act
    # material (measured: 43 non-Dead descriptions, sampled, header-dominated).
    desc = ("Blues Traveler\nH.O.R.D.E. Festival\nsoundboard master\n"
            "Runaround\nHook\nSet 1:\nBertha\nJack Straw\n")
    assert [i.title for i in parse_setlist(desc).items] == ["Bertha", "Jack Straw"]


def test_block_below_the_floor_still_truncates():
    # Fewer than 5 parseable items above is junk, not a lost setlist.
    desc = ("One Set: (1:39:44)\n1. intro\n2.\n3.\nEncore:\nBertha\n")
    items = parse_setlist(desc).items
    assert all(i.set == "encore" for i in items)


def test_decorated_encore_marker_is_recognized():
    # The coupled half: "---encore:" is a marker, not a song title.
    desc = ("Bertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "---encore:\nOne More Saturday Night\n")
    items = parse_setlist(desc).items
    assert not any("encore" in i.title.lower() for i in items)
    assert [i.set for i in items][-1] == "encore"
    assert len(items) == 6


def test_escaped_markup_cannot_truncate_the_recovery_probe():
    """The probe must be STRUCTURALLY unable to truncate (spec 1c).

    Preprocessing substitutes `<br>` BEFORE it unescapes entities, so an
    escaped `&lt;br&gt;` survives the first pass as the literal text `<br>`.
    The old probe recursed into `parse_setlist`, which re-ran preprocessing and
    turned that literal into a line break — manufacturing an "Encore:" marker
    inside the probe's own input. The probe then truncated, its item count fell
    under the recovery floor, and the outer parse discarded four real songs.

    `_emit_items` has no preprocessing and no truncation step, so the escape is
    inert."""
    escaped = ("Bertha\nJack Straw\nSugaree\n"
               "Row Jimmy &lt;br&gt;Encore: Bogus\nEncore:\nJohnny B Goode\n")
    titles = [i.title for i in parse_setlist(escaped).items]
    assert titles[:3] == ["Bertha", "Jack Straw", "Sugaree"]
    assert any(t.startswith("Row Jimmy") for t in titles)
    assert parse_setlist(escaped).items[-1].set == "encore"


def test_only_the_escape_changes_behaviour_not_the_literal_break():
    """Gate 2b's "identical with and without the escape", stated as the
    assertion that is actually available and actually constrains the code.

    The two forms are NOT the same document — a literal `<br>` is a line break
    by design and an escaped one is literal text — so their parses differ and
    always will. What §1c fixes is narrower and exactly checkable: the
    **literal** side is the same under the old recursive probe and the current
    one, so any behavioural difference between the two forms is caused by the
    escape and by nothing else. Both parses are pinned here; a probe that
    re-preprocesses collapses the escaped list to `["Johnny B Goode"]` while
    leaving the literal list untouched, which is what makes this a constraint
    and not a pin.

    (The literal side truncating to two items is CORRECT: only four items sit
    above its marker, below `_RECOVER_FLOOR`.)"""
    escaped = ("Bertha\nJack Straw\nSugaree\n"
               "Row Jimmy &lt;br&gt;Encore: Bogus\nEncore:\nJohnny B Goode\n")
    literal = escaped.replace("&lt;br&gt;", "<br>")
    assert [i.title for i in parse_setlist(escaped).items] == [
        "Bertha", "Jack Straw", "Sugaree", "Row Jimmy <br",
        "Encore: Bogus", "Johnny B Goode"]
    assert [i.title for i in parse_setlist(literal).items] == [
        "Bogus", "Johnny B Goode"]


def test_bracketed_durations_are_not_songs():
    desc = ("Set 1:\nIntro\n[1:51]\nRamblin Boy\n[4:40]\nRiver\n[6:25]\n"
            "Two Hits\n[3:38]\nSharecropper's Son\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Intro", "Ramblin Boy", "River", "Two Hits",
                      "Sharecropper's Son"]


def test_total_time_lines_are_not_songs():
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Total time = 1:34:29\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "Total time = 1:34:29" not in titles
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_bracketed_total_time_with_three_digit_minutes_is_not_a_song():
    # MEASURED: corpus form 'Total time:  [105:01]' — bracketed duration after
    # the label, runs of whitespace, 3-digit minute value. Distinct from the
    # unbracketed 'Total time = 1:34:29' form already covered above.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Total time:  [105:01]\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


# --- Class B: the widened item-level total-time rule
# (task-3-attribution.md section 2). ITEM-level, in `_JUNK_TITLE`, not
# `_NOISE`: the entire 21-item residue is a single emitted item apiece, so
# item-level loses nothing, and an item-level rule cannot take a glued-on
# song with it the way a line-level one can.


def test_total_time_widened_forms_are_dropped():
    # MEASURED residual forms the old `total time[:=]<duration>` shape did
    # not cover: wrapping brackets, a `~` separator with sub-second
    # precision, a bare dash separator, no separator at all (just
    # whitespace before the bracketed duration), a bare label with no
    # duration, and "total RUNNING time" with a duration shape the old
    # rule's colon/equals requirement never accounted for.
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "[Total Time 1:47:37]\nTotal Time ~ 03:17:25.981\n"
            "Total Time- 97:30\nTotal Time\nTotal Time:\n"
            "total time  [78:22]\nTotal running time [79:48]\n"
            "Total Running Time TRT 46:29\nTotal running time: 1h03'23\"\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_total_time_after_a_set_marker_is_dropped():
    # The two items `_NOISE` structurally can never reach: the marker
    # branch in `_emit_items` consumes "Set One:"/"Set Two:" before `_NOISE`
    # is ever consulted, so only an ITEM-level rule (this one) catches the
    # remainder. A `_NOISE`-only fix would leave these behind permanently -
    # this is the measured reason Class B stays out of `_NOISE`.
    desc = ("Set One:  total time  [78:22]\nBertha\nJack Straw\n"
            "Set Two:  total time  [93:48]\nSugaree\nRow Jimmy\nBig River\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_total_time_hazard_words_survive():
    # "total" followed by whitespace then "time" is required - neither the
    # missing space in "Totally" nor the unrelated word "Eclipse" satisfies
    # that, so both survive as ordinary titles.
    desc = ("Set 1:\nBertha\nDrums\nSpace\nJam\n333\n1977\n?\n"
            "Total Eclipse Of The Heart\nTotally Wired\n")
    titles = [i.title for i in parse_setlist(desc).items]
    for hazard in ("Bertha", "Drums", "Space", "Jam", "333", "1977", "?",
                   "Total Eclipse Of The Heart", "Totally Wired"):
        assert hazard in titles, f"{hazard!r} was wrongly treated as junk"


def test_total_time_item_level_does_not_eat_a_glued_song():
    # A regression guard, not the test that PROVES item-level scoping - this
    # fixture is inside a comma run reached via the `Set 1:` marker branch,
    # which `_NOISE` never sees regardless of whether the total-time rule
    # lives in `_NOISE` or `_JUNK_TITLE`, so it would pass even if the rule
    # were (wrongly) moved to `_NOISE`. `test_total_time_after_a_set_marker_
    # is_dropped` is the one that actually pins item- vs line-level
    # placement (moving the rule to `_NOISE` and reverting `_JUNK_TITLE`
    # kills it). What THIS test does pin: a total-time item glued onto a
    # real song via a comma survives right alongside it - only the
    # total-time item itself is dropped.
    desc = "Set 1: Bertha, Total Time: 45:00, Sugaree\n"
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Sugaree"]


def test_real_numeric_titles_survive_the_junk_filter():
    # MEASURED: '333', '1977', '1662', '16' are real songs matching real tracks.
    # A bare-number rule was rejected for breaking 8 real matches; this pins it.
    desc = ("Set 1:\n333\n1977\n1662\n16\nBertha\n")
    assert [i.title for i in parse_setlist(desc).items] == \
        ["333", "1977", "1662", "16", "Bertha"]


def test_unidentified_track_markers_survive():
    # MEASURED: '?' items correspond to '?' TRACKS (35x) — the taper's
    # unidentified-song marker on both sides. Positionally meaningful, not junk.
    desc = ("Set 1:\nBertha\n?\nSugaree\n??\nBig River\n")
    assert [i.title for i in parse_setlist(desc).items] == \
        ["Bertha", "?", "Sugaree", "??", "Big River"]
