from llama.correspondence import propose_titles
from llama.models import ParsedSetlist, SetlistItem, Track


def _canon(*specs):
    return ParsedSetlist(
        items=[SetlistItem(title=t, normalized=t.lower(), set=s, segue=g)
               for t, s, g in specs], confidence="high")


def _tracks(*durations):
    return [Track(index=i + 1, set="1", title=f"f{i + 1}.mp3",
                  filename=f"f{i + 1}.mp3", duration_sec=d,
                  title_source="unresolved")
            for i, d in enumerate(durations)]


def test_one_to_one_maps_straight_through():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical)
    assert prop.feasible
    assert [r.title for r in prop.rows] == ["Alpha", "Bravo"]


def test_a_segued_pair_merges_into_one_long_file():
    canonical = _canon(("Alpha", "1", True), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    prop = propose_titles(_tracks(600.0, 300.0),
                          canonical, item_durations=[300.0, 300.0, 300.0])
    assert prop.rows[0].title == "Alpha > Bravo"
    assert prop.rows[1].title == "Charlie"


def test_a_merge_is_never_proposed_across_a_non_segue():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    prop = propose_titles(_tracks(600.0, 300.0),
                          canonical, item_durations=[300.0, 300.0, 300.0])
    # Alpha does not segue, so no merge is legal and the assignment cannot fit
    assert not prop.feasible


def test_a_short_filler_track_consumes_no_item():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 20.0, 300.0),
                          canonical, item_durations=[300.0, 300.0])
    assert prop.rows[1].item_span is None
    assert prop.rows[1].evidence == "filler"


def test_infeasible_when_merges_needed_exceed_segue_markers():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False), ("Delta", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical)
    assert not prop.feasible
    assert "no consistent correspondence" in prop.reason


def test_margins_are_reported_per_row():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical,
                          item_durations=[300.0, 300.0])
    assert all(r.margin_sec is not None for r in prop.rows)
