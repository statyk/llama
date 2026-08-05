import pytest

from llama.models import ParsedSetlist, SetlistItem
from llama.titles import (
    clean_tag_title, clean_tag_titles, is_real_title, resolve_titles,
    set_breaks, sibling_format_titles, title_fraction,
)


def make_setlist() -> ParsedSetlist:
    def item(t, s, segue=False):
        return SetlistItem(title=t, normalized=t.lower(), set=s, segue=segue)
    return ParsedSetlist(
        items=[
            item("Morning Dew", "1"),
            item("China Cat Sunflower", "1", segue=True),
            item("I Know You Rider", "1"),
            item("Dark Star", "2", segue=True),
            item("Eyes of the World", "2"),
            item("Johnny B. Goode", "encore"),
        ],
        confidence="high",
    )


def make_files(titles: list[str | None]) -> list[dict]:
    names = ["d1t01.mp3", "d1t02.mp3", "d1t03.mp3", "d2t01.mp3", "d2t02.mp3", "d3t01.mp3"]
    files = []
    for name, title in zip(names, titles):
        f = {"name": name, "length": "05:00"}
        if title:
            f["title"] = title
        files.append(f)
    return files


def test_tags_win_and_setlist_fills_gaps():
    files = make_files(["Morning Dew", "China Cat Sunflower", None, "Dark Star", None, None])
    tracks = resolve_titles(files, make_setlist())
    assert [t.title_source for t in tracks] == ["tags", "tags", "setlist", "tags", "setlist", "setlist"]
    assert tracks[2].title == "I Know You Rider"
    # placeholders: structure stamping (real set/segue) moved to gather
    assert tracks[5].set == "1"
    assert tracks[1].segue is False
    assert tracks[0].duration_sec == 300.0
    assert [t.index for t in tracks] == [1, 2, 3, 4, 5, 6]


def test_sibling_fallback_when_setlist_misaligned():
    files = make_files([None] * 6)
    short = ParsedSetlist(items=make_setlist().items[:3], confidence="high")  # count mismatch
    tracks = resolve_titles(files, short, sibling_titles=[
        "Morning Dew", "China Cat Sunflower", "I Know You Rider",
        "Dark Star", "Eyes of the World", "Johnny B. Goode",
    ])
    assert all(t.title_source == "sibling" for t in tracks)
    # placeholder set - structure stamping moved to gather
    assert tracks[0].set == "1"


def test_unresolved_flagged_not_guessed():
    files = make_files([None] * 6)
    tracks = resolve_titles(files, ParsedSetlist(items=[], confidence="low"))
    assert all(t.title_source == "unresolved" for t in tracks)
    assert tracks[0].title == "d1t01.mp3"


def test_set_breaks():
    # set_breaks() itself is unchanged - it just reads Track.set - but
    # resolve_titles no longer stamps real sets, so this test stamps them
    # the way gather.py now does (from llama.structure.align) before calling it.
    tracks = resolve_titles(
        make_files(["Morning Dew", "China Cat Sunflower", None, "Dark Star", None, None]),
        make_setlist(),
    )
    real_sets = [item.set for item in make_setlist().items]
    tracks = [t.model_copy(update={"set": s}) for t, s in zip(tracks, real_sets)]
    assert set_breaks(tracks) == [3, 5]  # after track 3 (set 1->2) and track 5 (set 2->encore)


@pytest.mark.parametrize("raw,cleaned", [
    ("gd73-06-10d1t04 Here Comes Sunshine", "Here Comes Sunshine"),
    ("gd1977-05-08t12 Scarlet Begonias.flac", "Scarlet Begonias"),
    ("gd73.06.10d1t01 - Morning Dew", "Morning Dew"),
    ("gd73-06-10d1t04.mp3", ""),          # pure filename residue
    ("unknown", ""),
    ("Unknown", ""),
    ("Here Comes Sunshine", "Here Comes Sunshine"),  # plain titles untouched
    ("Deal", "Deal"),
    (None, ""),
])
def test_clean_tag_title(raw, cleaned):
    assert clean_tag_title(raw) == cleaned


@pytest.mark.parametrize("cleaned,real", [
    ("Deal", True), ("Jam", True), ("Here Comes Sunshine", True),
    ("d1t02", False), ("", False), ("A B", False),
])
def test_is_real_title(cleaned, real):
    assert is_real_title(cleaned) is real


def test_junk_tag_title_falls_through_cascade():
    # tag is filename residue -> cleaned to junk -> setlist wins
    files = make_files(["gd73-06-10d1t01.mp3", "China Cat Sunflower",
                        None, "Dark Star", None, None])
    tracks = resolve_titles(files, make_setlist())
    assert tracks[0].title == "Morning Dew"
    assert tracks[0].title_source == "setlist"


def test_tag_title_is_stored_cleaned():
    files = make_files(["gd73-06-10d1t01 Morning Dew", "China Cat Sunflower",
                        "I Know You Rider", "Dark Star", "Eyes of the World",
                        "Johnny B. Goode"])
    tracks = resolve_titles(files, make_setlist())
    assert tracks[0].title == "Morning Dew"
    assert tracks[0].title_source == "tags"


def numbered_files(titles: list[str]) -> list[dict]:
    """Kept-file dicts carrying only what the title path reads."""
    return [{"name": f"t{n:02d}.mp3", "title": t} for n, t in enumerate(titles, 1)]


def test_clean_tag_titles_strips_numbers_on_an_enumerated_tape():
    # gus2018-01-13's real shape: every track numbered, 1..n.
    files = numbered_files([
        "01 Intro - Ramona", "02 Two Points For Honesty", "03 Banter - Sports Talk",
        "04 G Major", "05 Demons",
    ])
    assert clean_tag_titles(files) == [
        "Intro - Ramona", "Two Points For Honesty", "Banter - Sports Talk",
        "G Major", "Demons",
    ]


def test_clean_tag_titles_protects_a_lone_numeric_title():
    # bt1990-08-17: "100 Years" is the only numbered title among 4 tracks.
    files = numbered_files(["The Way It Is", "100 Years", "Mandolin Rain", "Every Little Kiss"])
    assert clean_tag_titles(files) == [
        "The Way It Is", "100 Years", "Mandolin Rain", "Every Little Kiss",
    ]


@pytest.mark.parametrize("title", [
    "100 Years", "200 More Miles", "20 Eyes", "2 x 4",
    "52 Vincent Black Lightning", "40 Miles From Denver", "18 Wheels Of Love",
])
def test_clean_tag_titles_never_mutilates_a_real_numeric_title(title):
    """Every one of these is a real song title measured in the live corpus,
    sitting alone among unnumbered tracks. See the spec's A1 evidence."""
    files = numbered_files(["Opener", title, "Closer"])
    assert clean_tag_titles(files)[1] == title


def test_clean_tag_titles_leaves_a_four_digit_year_alone_even_when_enumerated():
    """A year title that carries its OWN track number keeps the year on a tape
    the gate is actively stripping.

    This does NOT pin the \\d{1,3} bound, despite what it used to claim: the
    title's own "02 " is stripped by one anchored substitution and the year
    survives under a widened \\d+ too. The bound is pinned by
    test_clean_tag_titles_leaves_an_unnumbered_year_title_alone; what this one
    validly pins is strip-once."""
    files = numbered_files([
        "01 Opener", "02 1952 Vincent Black Lightning", "03 Third", "04 Fourth",
    ])
    assert clean_tag_titles(files)[1] == "1952 Vincent Black Lightning"


def test_clean_tag_titles_leaves_an_unnumbered_year_title_alone():
    """titles._TRACK_NUM_PREFIX's \\d{1,3} bound, isolated. The year title
    carries no track number of its own, so nothing else can save it.

    Shipped -> "1952 Vincent Black Lightning". Widen the bound to \\d+ and the
    year is eaten, leaving "Vincent Black Lightning".

    The 9-of-10 shape is deliberate and the margin matters. A bare year does
    NOT match the leading-number pattern, so it never counts toward the
    enumerated tally: the obvious fixture - 3 numbered tracks plus the year -
    is 3/4 = 0.75 coverage, the gate DECLINES, nothing is stripped, and the
    test passes under both regexes. That is a test that pins nothing while
    looking like it does. 9/10 = 0.90 fires with room to spare; 4/5 = 0.80
    fires but sits exactly on the floor, one fixture edit from silence.

    The first assertion is not decoration: a test whose subject is "the bound
    protects this title" must first establish that anything was being stripped
    at all, or a future coverage-floor change turns it green for the wrong
    reason."""
    files = numbered_files(
        [f"{n:02d} Song {n}" for n in range(1, 10)]
        + ["1952 Vincent Black Lightning"]
    )
    cleaned = clean_tag_titles(files)
    assert cleaned[0] == "Song 1", "the gate must be firing, or this pins nothing"
    assert cleaned[9] == "1952 Vincent Black Lightning"


def test_clean_tag_titles_strips_once_never_loops():
    """On an enumerated tape a title may legitimately begin with its own
    number. A looping strip would take this to "More Miles"."""
    files = numbered_files(["01 200 More Miles", "02 Second", "03 Third", "04 Fourth"])
    assert clean_tag_titles(files)[0] == "200 More Miles"


def test_clean_tag_titles_declines_below_the_count_floor():
    """A 2-track recording where both titles are real numeric song titles:
    coverage is 100% (2 of 2), so the coverage floor alone would let this
    through - it's the absolute-count floor (>=3 numbered files) that
    declines it. Fixed from the brief's original 2-of-10 fixture, which the
    Step 5 mutation check showed was *also* below the coverage floor (0.2),
    so it couldn't isolate the count floor: mutating _ENUMERATED_MIN_FILES to
    0 left it passing/failing for the same reason either way."""
    files = numbered_files(["100 Years", "18 Wheels Of Love"])
    assert clean_tag_titles(files) == ["100 Years", "18 Wheels Of Love"]


def test_clean_tag_titles_leaves_dbt2014_01_31s_corpus_shape_alone():
    """Documents a real corpus shape rather than isolating a floor.
    dbt2014-01-31 is two numbered files among ten, and both numbers are song
    titles - it sits below the count floor (2 < 3) AND the coverage floor
    (0.2 < 0.8), so it cannot tell you which one declined it. Kept alongside
    test_clean_tag_titles_declines_below_the_count_floor, which can, because
    this is the shape the floors exist for."""
    files = numbered_files(
        ["18 Wheels Of Love", "3 Dimes Down"] + [f"Song {n}" for n in range(8)]
    )
    assert clean_tag_titles(files)[:2] == ["18 Wheels Of Love", "3 Dimes Down"]


def test_clean_tag_titles_declines_below_the_coverage_floor():
    """dbt2017-09-30: three numbered titles, but only 3 of 30 files - well
    under 80%, so all three are real titles, not enumeration."""
    files = numbered_files(
        ["72 (This Highway's Mean)", "3 Dimes Down", "18 Wheels of Love"]
        + [f"Song {n}" for n in range(27)]
    )
    assert clean_tag_titles(files)[:3] == [
        "72 (This Highway's Mean)", "3 Dimes Down", "18 Wheels of Love",
    ]


def test_clean_tag_titles_accepts_its_known_false_negatives():
    """Fishbone1992-09-18's shape: disc 2 numbered 8..16, 9 of 15 files = 0.60
    coverage. These ARE track numbers and the gate deliberately misses them -
    the prefix survives, which is the pre-existing behaviour.

    Pinned so that widening the gate is a visible, deliberate change rather
    than a silent one. If this test starts failing, someone loosened a floor;
    that may be right, but it must be argued from a re-measurement."""
    files = numbered_files(
        [f"Song {n}" for n in range(6)]
        + [f"{n:02d} Numbered {n}" for n in range(8, 17)]
    )
    assert clean_tag_titles(files)[6] == "08 Numbered 8"


def test_clean_tag_titles_strips_a_real_numeric_title_on_an_enumerated_tape():
    """The gate's destructive mode, pinned as deliberate and known rather than
    left unexamined. See the spec's Part 1 section "Accepted gap: a real
    numeric title on an enumerated tape" - accepted, NOT fixed. Do not tighten
    the gate or add an out-of-sequence flag to make this test pass.

    What was measured, precisely: for the OUT-OF-RANGE half (a numeric title
    whose number falls outside the tape's own sequence, as "100 Years" does
    here) there are ZERO occurrences across the 1,708 stripped tracks, with the
    detector positive-controlled two ways. The IN-RANGE half - "2 x 4",
    "8 Cylinders" on a tape numbering 1..n - is undetectable by ANY rule that
    inspects only the number, so its rate is UNBOUNDED, not zero."""
    files = numbered_files(["01 A", "02 B", "100 Years", "04 D"])
    assert clean_tag_titles(files)[2] == "Years"


def test_clean_tag_titles_still_strips_the_identifier_prefix():
    """The per-string cleaner must keep working through the list wrapper."""
    files = [{"name": "d1t04.mp3", "title": "gd73-06-10d1t04 Here Comes Sunshine"}]
    assert clean_tag_titles(files) == ["Here Comes Sunshine"]


def test_clean_tag_titles_handles_empty_input():
    assert clean_tag_titles([]) == []


def test_title_fraction():
    assert title_fraction(["Dark Star", "Eyes of the World"]) == 1.0
    assert title_fraction(["Dark Star", "", "d1t02", "Eyes"]) == 0.5
    assert title_fraction([]) == 0.0


def fmt_files(names_titles: list[tuple[str, str]]) -> list[dict]:
    return [{"name": n, "title": t} for n, t in names_titles]


def test_sibling_format_titles_matches_by_stem():
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("d1t01.flac", "Jack Straw"), ("d1t02.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) == {
        "d1t01.mp3": "Jack Straw", "d1t02.mp3": "Sugaree",
    }


def test_sibling_format_titles_survives_a_reordered_sibling():
    """The map is keyed by name, so sibling order is irrelevant."""
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("d1t02.flac", "Sugaree"), ("d1t01.flac", "Jack Straw")])
    assert sibling_format_titles(mp3, flac) == {
        "d1t01.mp3": "Jack Straw", "d1t02.mp3": "Sugaree",
    }


def test_sibling_format_titles_declines_on_a_count_mismatch():
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("d1t01.flac", "Jack Straw")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_when_stems_differ():
    """Same count, different naming convention - guessing by position here is
    exactly the failure this function exists to refuse."""
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("track01.flac", "Jack Straw"), ("track02.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_on_duplicate_stems():
    """Duplicates on BOTH sides at once - which a one-sided guard would also
    decline, hence the two one-sided cases below."""
    mp3 = fmt_files([("t01.mp3", ""), ("t01.mp3", "")])
    flac = fmt_files([("t01.flac", "A"), ("t01.flac", "B")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_on_duplicates_on_our_side_only():
    """Equal counts, duplicates only in `kept`: the bijection is broken on the
    left and the sibling is clean."""
    mp3 = fmt_files([("t01.mp3", ""), ("t01.mp3", "")])
    flac = fmt_files([("t01.flac", "Jack Straw"), ("t02.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_on_duplicates_on_the_sibling_side_only():
    """Equal counts, duplicates only in `other_kept`: broken on the right."""
    mp3 = fmt_files([("t01.mp3", ""), ("t02.mp3", "")])
    flac = fmt_files([("t01.flac", "Jack Straw"), ("t01.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_on_empty_input():
    assert sibling_format_titles([], []) is None


def test_sibling_format_titles_keeps_subdirectories_distinct():
    """archive.org names can carry a directory component; two files sharing a
    basename in different directories are different tracks."""
    mp3 = fmt_files([("d1/t01.mp3", ""), ("d2/t01.mp3", "")])
    flac = fmt_files([("d1/t01.flac", "Bertha"), ("d2/t01.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) == {
        "d1/t01.mp3": "Bertha", "d2/t01.mp3": "Sugaree",
    }


def test_sibling_format_titles_cleans_recovered_titles():
    """Recovered FLAC tags carry leading track numbers too - measured at 5 of
    2,928 - so the enumerated-tape gate must run over them as well."""
    mp3 = fmt_files([(f"t{n:02d}.mp3", "") for n in range(1, 5)])
    flac = fmt_files([
        ("t01.flac", "01 Bertha"), ("t02.flac", "02 Sugaree"),
        ("t03.flac", "03 Dire Wolf"), ("t04.flac", "04 Loser"),
    ])
    assert sibling_format_titles(mp3, flac) == {
        "t01.mp3": "Bertha", "t02.mp3": "Sugaree",
        "t03.mp3": "Dire Wolf", "t04.mp3": "Loser",
    }
