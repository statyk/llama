import pytest

from llama.models import ParsedSetlist, SetlistItem
from llama.titles import (
    clean_tag_title, clean_tag_titles, is_real_title, resolve_titles,
    set_breaks, title_fraction,
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
    """The \\d{1,3} bound, not the gate, is what protects this one - so it must
    hold even on a tape the gate is actively stripping."""
    files = numbered_files([
        "01 Opener", "02 1952 Vincent Black Lightning", "03 Third", "04 Fourth",
    ])
    assert clean_tag_titles(files)[1] == "1952 Vincent Black Lightning"


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
