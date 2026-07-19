import pytest

from llama.models import ParsedSetlist, SetlistItem
from llama.titles import clean_tag_title, is_real_title, resolve_titles, set_breaks


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
