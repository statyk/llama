import pytest

from llama.correspondence import propose_titles
from llama.models import (Candidate, ParsedSetlist, ProposalRow, RecordingSummary,
                          SetlistItem, TitleProposal, Track)


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
    # I2: pin the margin computation itself, not just its presence/absence.
    # Measured directly against _solve: the optimal assignment costs 20.0
    # (both 300s tracks match an item exactly; the 20s track is filler).
    # Forbidding either 300s row's span from the solve raises the best
    # remaining cost to 580.0, so margin_sec = 580.0 - 20.0 = 560.0 on both
    # rows that consumed an item. The filler row has no margin at all.
    assert prop.rows[0].margin_sec == 560.0
    assert prop.rows[2].margin_sec == 560.0
    assert prop.rows[1].margin_sec is None
    # Round 4: the trichotomy in test_margins_are_reported_per_row never
    # exercises a filler row (that fixture has zero fillers), so a producer
    # that sets forced=True on filler rows -- exactly the forced/filler
    # collapse these rounds exist to prevent -- passed every test until
    # this. Pin the trichotomy at a second site that DOES have a filler row.
    for r in prop.rows:
        assert (r.margin_sec is not None) + r.forced + (r.item_span is None) == 1


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
    # I3: "margins are reported per row" is a trichotomy, not a disjunction --
    # every row is EXACTLY one of: has a numeric margin, is forced, or is
    # filler (item_span is None). `r.margin_sec is not None or r.forced` is
    # true for this fixture but false in general (a filler row is
    # margin_sec=None, forced=False), so it doesn't actually pin the
    # invariant its name claims. This does, for every row in every proposal:
    for r in prop.rows:
        assert (r.margin_sec is not None) + r.forced + (r.item_span is None) == 1


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


def test_forced_rows_from_the_real_producer_stay_forced_across_a_json_round_trip():
    # I1: the hand-built round-trip test above only pins that ProposalRow
    # CAN carry the forced/filler distinction through JSON -- it never
    # calls propose_titles, so it can't catch a producer that stops setting
    # `forced` (e.g. a revert to the old margin_sec=float("inf") sentinel,
    # forced=False). This drives the real entry point and round-trips the
    # whole TitleProposal. Mutation-verified against the pre-fix producer
    # (margin_sec=_INF if alt == _INF else alt - cost, forced=False): this
    # test fails there because every row comes back forced=False.
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical,
                          item_durations=[300.0, 300.0])
    back = TitleProposal.model_validate_json(prop.model_dump_json())
    assert all(r.forced and r.margin_sec is None for r in back.rows)


def test_item_durations_length_mismatch_is_rejected():
    # I5: a short/long item_durations list would otherwise silently
    # truncate sum(idur[b:b+k]) inside _solve, corrupting every merge cost
    # past the boundary with no signal -- the DP still returns a
    # fully-populated table. Task 6 feeds this from a sibling recording
    # where a length mismatch is a live possibility, so fail loudly instead.
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    with pytest.raises(ValueError, match="item_durations has 1 entries, expected 2"):
        propose_titles(_tracks(300.0, 300.0), canonical, item_durations=[300.0])


def test_sibling_item_durations_returns_none_without_a_tagged_sibling():
    from llama.correspondence import sibling_item_durations
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only")])
    assert sibling_item_durations(None, cand, "only", canonical, ("VBR MP3",)) is None
