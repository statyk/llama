from llama.correspondence import propose_titles
from llama.models import ParsedSetlist, ProposalRow, SetlistItem, Track


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
    assert all(r.margin_sec is not None or r.forced for r in prop.rows)


def test_forced_and_filler_rows_stay_distinguishable_across_a_json_round_trip():
    # Regression pin: margin_sec used to carry float("inf") for a forced
    # row, but pydantic's default ser_json_inf_nan="null" serializes inf to
    # JSON null, so a forced row and a filler row became byte-identical
    # JSON and both read back as margin_sec=None. `forced` exists precisely
    # so this distinction survives serialization.
    forced_row = ProposalRow(index=1, item_span=(0, 1), title="Alpha",
                             evidence="sibling-duration", margin_sec=None,
                             forced=True)
    filler_row = ProposalRow(index=2, item_span=None, title="",
                             evidence="filler", margin_sec=None, forced=False)

    forced_back = ProposalRow.model_validate_json(forced_row.model_dump_json())
    filler_back = ProposalRow.model_validate_json(filler_row.model_dump_json())

    assert forced_back.forced is True
    assert forced_back.margin_sec is None
    assert filler_back.forced is False
    assert filler_back.margin_sec is None

