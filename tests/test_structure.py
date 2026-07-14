from llama.models import ParsedSetlist, SetlistItem, SourcedParse
from llama.structure import from_setlistfm, norm_title, rank_parses


def sp(source, sets_titles, confidence="high"):
    """Helper: build a SourcedParse from (set, title) pairs."""
    items = [SetlistItem(title=t, normalized=norm_title(t), set=s, segue=False)
             for s, t in sets_titles]
    return SourcedParse(source=source, parsed=ParsedSetlist(items=items, confidence=confidence))


def test_norm_title_strips_encore_prefix_and_segue_arrow():
    assert norm_title("E: It's All Over Now, Baby Blue") == "its all over now baby blue"
    assert norm_title("Encore: Casey Jones") == "casey jones"
    assert norm_title("China Cat Sunflower >") == "china cat sunflower"
    assert norm_title("Morning Dew") == "morning dew"


def test_from_setlistfm_converts_sets_and_encore():
    raw = {"sets": {"set": [
        {"song": [{"name": "US Blues"}, {"name": "Mexicali Blues"}, {"name": "Loser"}]},
        {"song": [{"name": "Big River"}, {"name": "Dark Star"},
                  {"name": "Intro Tape", "tape": True}]},
        {"encore": 1, "song": [{"name": "Casey Jones"}]},
    ]}}
    p = from_setlistfm(raw)
    assert p.confidence == "high"
    assert [(i.set, i.title) for i in p.items] == [
        ("1", "US Blues"), ("1", "Mexicali Blues"), ("1", "Loser"),
        ("2", "Big River"), ("2", "Dark Star"), ("encore", "Casey Jones"),
    ]
    assert all(i.segue is False for i in p.items)


def test_from_setlistfm_rejects_stubs():
    raw = {"sets": {"set": [{"song": [{"name": "One"}, {"name": "Two"}]}]}}
    assert from_setlistfm(raw) is None
    assert from_setlistfm({}) is None


FIVE = [("1", "A"), ("1", "B"), ("2", "C"), ("2", "D"), ("encore", "E")]
FLAT = [("1", "A"), ("1", "B"), ("1", "C"), ("1", "D"), ("1", "E")]


def test_rank_setlistfm_beats_lma_high():
    best = rank_parses([sp("chosen", FIVE, "high"), sp("setlist.fm", FIVE, "high")], 5)
    assert best.source == "setlist.fm"


def test_rank_confidence_then_multiset_then_count():
    assert rank_parses([sp("lma:a", FIVE, "medium"), sp("lma:b", FIVE, "high")], 5).source == "lma:b"
    assert rank_parses([sp("lma:flat", FLAT, "high"), sp("lma:sets", FIVE, "high")], 5).source == "lma:sets"
    close = sp("lma:close", FIVE, "high")
    far = sp("lma:far", FIVE + [("encore", "F"), ("encore", "G")], "high")
    assert rank_parses([far, close], 5).source == "lma:close"


def test_rank_ties_go_to_first_listed_and_empty_is_unrankable():
    a, b = sp("chosen", FIVE, "high"), sp("lma:copy", FIVE, "high")
    assert rank_parses([a, b], 5).source == "chosen"
    assert rank_parses([SourcedParse(source="chosen", parsed=ParsedSetlist())], 5) is None
    assert rank_parses([], 5) is None
