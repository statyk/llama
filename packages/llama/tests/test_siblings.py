"""Unit tests for `llama.siblings` -- the pure duration-sequence DP that
aligns an untagged tape against a tagged sibling recording of the same
performance, and proposes per-row title transfers.

Every acceptance assertion here is on a TITLE STRING, never on a count: the
phase this module belongs to exists because a shape-passing gate once shipped
13 wrong titles out of 22. `test_a2_*` and `test_a3_*` are the load-bearing
deletion controls -- they are what a positional transfer
(`titles[i] = donor.titles[i]`) cannot survive.
"""

from llama.siblings import (
    MIN_EXCLUSION_PENALTY,
    MIN_MATCH_FRACTION,
    DonorTape,
    align_durations,
    propose_rows,
)
from llama.structure import fuzzy_norm_title


def _donor(durations, titles, identifier="donor.item"):
    return DonorTape(
        identifier=identifier,
        names=[f"t{i + 1:02d}.mp3" for i in range(len(durations))],
        durations=list(durations),
        titles=list(titles),
    )


def _by_track(rows):
    return {r.track: r for r in rows}


# --------------------------------------------------------------------------
# The DP itself
# --------------------------------------------------------------------------

def test_align_durations_pairs_one_merged_file_with_its_two_donor_tracks():
    cost, ops = align_durations([700.0], [300.0, 400.0])
    assert cost == 0.0
    assert ops == [(0, 1, 0, 2)]


def test_align_durations_forbidding_the_best_pairing_makes_the_solution_worse():
    target = [300.0, 420.0, 510.0]
    donor = [301.0, 419.0, 512.0]
    base, ops = align_durations(target, donor)
    assert (0, 1, 0, 1) in ops
    worse, _ = align_durations(target, donor, forbid=(0, 1, 0, 1))
    assert worse > base


def test_align_durations_skips_a_target_track_no_merge_can_absorb():
    """A target track can only be reported as SKIPPED where absorbing it into
    a neighbouring pairing is structurally illegal -- here the next target
    file is itself a 1:2 pairing, so absorbing would need an illegal 2:2 op.

    (Absorption and skipping cost the same under an L1 timeline cost -- both
    add the orphan's duration -- so where absorption is legal the DP's
    exploration order decides. See the module docstring.)
    """
    target = [330.0, 912.0, 358.0, 481.0, 300.0]
    donor = [400.0, 512.0, 358.0, 481.0, 300.0]
    cost, ops = align_durations(target, donor)
    assert cost == 330.0
    assert (0, 1, 0, 0) in ops          # target track 0 skipped, no donor
    assert (1, 2, 0, 2) in ops          # target track 1 holds donor 0 and 1


def test_align_durations_ops_partition_both_sequences():
    target = [330.0, 912.0, 358.0, 481.0, 300.0]
    donor = [400.0, 512.0, 358.0, 481.0, 300.0]
    _cost, ops = align_durations(target, donor)
    i = j = 0
    for i0, i1, j0, j1 in ops:
        assert (i0, j0) == (i, j)
        i, j = i1, j1
    assert (i, j) == (len(target), len(donor))


# --------------------------------------------------------------------------
# Row transfer: the happy paths, asserted string by string
# --------------------------------------------------------------------------

def test_one_to_one_alignment_adopts_the_donors_titles_string_by_string():
    target = [300.0, 420.0, 510.0, 360.0, 480.0]
    donor = _donor([301.0, 419.0, 512.0, 358.0, 481.0],
                   ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
    rows, diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    got = _by_track(rows)
    assert got[1].proposed == "Alpha"
    assert got[2].proposed == "Bravo"
    assert got[3].proposed == "Charlie"
    assert got[4].proposed == "Delta"
    assert got[5].proposed == "Echo"
    assert [r.verdict for r in rows] == ["adopt"] * 5
    assert diag["identifier"] == "donor.item"


def test_donor_span_is_half_open_and_zero_based_while_track_is_one_based():
    """The span convention Task 4's bracketing guard consumes: `track` is the
    1-based target track number (as `Track.track`), `donor_span` is a
    half-open range over 0-BASED donor track indices -- the same shape
    `structure.anchor_spans` / `structure.gap_span` return over canonical
    items."""
    target = [300.0, 420.0, 510.0]
    donor = _donor([301.0, 419.0, 512.0], ["Alpha", "Bravo", "Charlie"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    got = _by_track(rows)
    assert got[1].donor_span == (0, 1)
    assert got[2].donor_span == (1, 2)
    assert got[3].donor_span == (2, 3)


def test_residual_seconds_reports_each_pairings_duration_gap():
    """`residual_sec` is the gap the pairing leaves, in seconds. Pinned on a
    fixture whose every row has a DIFFERENT non-zero gap: an implementation
    that hard-codes 0.0, or that reports the whole tape's drift instead of the
    pairing's, dies here."""
    target = [300.0, 420.0, 510.0, 360.0, 480.0]
    donor = _donor([301.0, 419.0, 512.0, 358.0, 481.0],
                   ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    assert [r.residual_sec for r in rows] == [1.0, 1.0, 2.0, 2.0, 1.0]


def test_a_merged_target_file_proposes_the_segue_join():
    target = [703.0, 512.0, 358.0, 481.0]
    donor = _donor([300.0, 400.0, 512.0, 358.0, 481.0],
                   ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    got = _by_track(rows)
    assert got[1].proposed == "Alpha > Bravo"
    assert got[1].donor_span == (0, 2)
    assert got[1].verdict == "adopt"
    assert got[1].residual_sec == 3.0   # 703 s of file against 700 s of donor
    assert got[2].proposed == "Charlie"
    assert got[3].proposed == "Delta"
    assert got[4].proposed == "Echo"


# --------------------------------------------------------------------------
# A2 / A3: the deletion controls. A positional transfer dies here.
# --------------------------------------------------------------------------

def test_one_file_may_hold_three_donor_songs():
    """MAX_MERGE = 3 pinned from BELOW. A suite naturally pins the direction
    that breaks the happy path (raising the bound) and leaves the other side
    free, so a constant tested one way looks pinned and is half-loose -- the
    same asymmetry that let Task 2's four-digit bound widen silently. Lowering
    MAX_MERGE to 2 makes this three-song file unrepresentable and the proposal
    collapses to "Alpha > Bravo"."""
    target = [900.0, 480.0]
    donor = _donor([300.0, 300.0, 300.0, 480.0],
                   ["Alpha", "Bravo", "Charlie", "Delta"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    got = _by_track(rows)
    assert got[1].proposed == "Alpha > Bravo > Charlie"
    assert got[1].donor_span == (0, 3)
    assert got[1].verdict == "adopt"
    assert got[2].proposed == "Delta"


def test_a2_deleted_donor_head_track_declines_the_orphan_and_keeps_the_rest():
    """A2-shaped: the donor's first track is gone, so target track 1 has no
    counterpart. The orphan declines and EVERY other row still carries its own
    correct title -- no uniform shift. A positional transfer would title
    track 1 "Bravo" and slide the whole tape up by one.
    """
    target = [330.0, 912.0, 358.0, 481.0, 300.0, 540.0]
    donor = _donor([400.0, 512.0, 358.0, 481.0, 300.0, 539.0],
                   ["Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf"])
    rows, diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    # 5 of 6 tracks matched. The sixth pair is here on purpose: a five-track
    # version of this fixture lands on match_fraction == 0.80 EXACTLY, so the
    # test would be measuring the threshold's boundary as much as the deletion.
    assert diag["match_fraction"] > MIN_MATCH_FRACTION
    got = _by_track(rows)
    assert got[1].verdict == "decline"
    assert got[1].reason == "no sibling track"
    assert got[1].proposed is None
    assert got[1].donor_span is None
    assert got[2].proposed == "Bravo > Charlie"
    assert got[3].proposed == "Delta"
    assert got[4].proposed == "Echo"
    assert got[5].proposed == "Foxtrot"
    assert got[6].proposed == "Golf"
    assert [got[t].verdict for t in (2, 3, 4, 5, 6)] == ["adopt"] * 5


def test_a3_deleted_donor_middle_track_declines_the_orphan_and_keeps_the_rest():
    """A3-shaped: a donor track in the MIDDLE is gone. Same property."""
    target = [720.0, 350.0, 900.0, 480.0, 360.0, 540.0]
    donor = _donor([300.0, 420.0, 500.0, 400.0, 480.0, 360.0, 539.0],
                   ["Alpha", "Bravo", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"])
    rows, diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    assert diag["match_fraction"] > MIN_MATCH_FRACTION   # off the 0.80 boundary
    got = _by_track(rows)
    assert got[1].proposed == "Alpha > Bravo"
    assert got[2].verdict == "decline"
    assert got[2].reason == "no sibling track"
    assert got[2].proposed is None
    assert got[3].proposed == "Delta > Echo"
    assert got[4].proposed == "Foxtrot"
    assert got[5].proposed == "Golf"
    assert got[6].proposed == "Hotel"
    assert [got[t].verdict for t in (1, 3, 4, 5, 6)] == ["adopt"] * 5


def test_a1_a_donor_track_the_target_lacks_adds_no_row_to_the_target():
    """A1-shaped, the mirror of A2: the DONOR has a song this tape never
    recorded. A donor track paired with nothing must produce NO row at all --
    rows are indexed by target track, one apiece, and Tasks 4-6 index by that
    invariant. Emitting a row for the unmatched donor track would duplicate
    target track 1, which is what makes the assertion on the track list, not
    on a count, the thing that catches it.

    Here donor track 2 is one 912 s song the target split across two files, so
    those two rows decline on the split rule while the tail still adopts.
    """
    target = [400.0, 512.0, 358.0, 481.0, 300.0]
    donor = _donor([330.0, 912.0, 358.0, 481.0, 300.0],
                   ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    assert [r.track for r in rows] == [1, 2, 3, 4, 5]
    got = _by_track(rows)
    assert got[1].reason == "sibling song split across target files"
    assert got[2].reason == "sibling song split across target files"
    assert got[3].proposed == "Charlie"
    assert got[4].proposed == "Delta"
    assert got[5].proposed == "Echo"
    assert "Alpha" not in [r.proposed for r in rows]


# --------------------------------------------------------------------------
# Per-row evidence and hygiene
# --------------------------------------------------------------------------

def test_near_ambiguous_pairing_declines_on_weak_evidence():
    """The donor carries a 25 s inter-song fragment, so target track 1 is
    explained about equally well by "Alpha + fragment" and by "Alpha, fragment
    dropped" -- the boundary can move for almost nothing. The exclusion
    penalty (20 s) is under MIN_EXCLUSION_PENALTY, so the two rows the shift
    touches decline while the rows past it, whose evidence is worth hundreds
    of seconds, still adopt their own correct titles.
    """
    target = [310.0, 420.0, 510.0, 360.0]
    donor = _donor([300.0, 25.0, 420.0, 510.0, 360.0],
                   ["Alpha", "Crowd Noise", "Bravo", "Charlie", "Delta"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    got = _by_track(rows)
    assert got[1].verdict == "decline"
    assert got[1].reason.startswith("weak evidence")
    assert got[1].penalty_sec < MIN_EXCLUSION_PENALTY
    assert got[2].verdict == "decline"
    assert got[2].reason.startswith("weak evidence")
    assert got[3].proposed == "Charlie"
    assert got[3].verdict == "adopt"
    assert got[4].proposed == "Delta"
    assert got[4].verdict == "adopt"


def test_an_untitled_donor_track_declines_only_its_own_row():
    """Per-item, not per-donor: this donor is 67% tagged -- under the
    prototype's whole-donor MIN_SIB_TAGGED gate the entire pair would have
    been refused and both correct titles lost with it."""
    target = [300.0, 420.0, 510.0]
    donor = _donor([300.0, 420.0, 510.0], ["Alpha", "", "Charlie"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    got = _by_track(rows)
    assert got[1].proposed == "Alpha"
    assert got[1].verdict == "adopt"
    assert got[2].verdict == "decline"
    assert got[2].reason == "sibling track untitled"
    assert got[2].proposed is None
    assert got[3].proposed == "Charlie"
    assert got[3].verdict == "adopt"


def test_a_donor_song_split_across_target_files_declines_those_rows():
    target = [300.0, 300.0, 480.0]
    donor = _donor([600.0, 480.0], ["Alpha", "Bravo"])
    rows, _diag = propose_rows(target, donor, metadata_norms=set())
    assert rows is not None
    got = _by_track(rows)
    for track in (1, 2):
        assert got[track].verdict == "decline"
        assert got[track].reason == "sibling song split across target files"
        assert got[track].proposed is None
        assert got[track].donor_span == (0, 1)
    assert got[3].proposed == "Bravo"
    assert got[3].verdict == "adopt"


def test_a_donor_track_titled_with_show_metadata_fails_hygiene():
    target = [300.0, 420.0, 510.0]
    donor = _donor([300.0, 420.0, 510.0],
                   ["Alpha", "Fillmore Auditorium", "Charlie"])
    norms = {fuzzy_norm_title("Fillmore Auditorium")}
    rows, _diag = propose_rows(target, donor, metadata_norms=norms)
    assert rows is not None
    got = _by_track(rows)
    assert got[1].proposed == "Alpha"
    assert got[2].verdict == "decline"
    assert got[2].reason == "sibling title fails hygiene"
    assert got[2].proposed is None
    assert got[3].proposed == "Charlie"


# --------------------------------------------------------------------------
# Whole-tape preconditions
# --------------------------------------------------------------------------

def test_a_none_duration_declines_instead_of_raising():
    """`models.Track.duration_sec` is `float | None`, and gather feeds these
    lists straight off `Track` objects -- so a file the item gave no length for
    arrives here as a literal `None`, not as 0.0. A bare `d > 0` raises
    TypeError on it and takes the whole stage down instead of declining one
    donor. Deliberately a real `None`: 0.0 or a stand-in would pass while the
    production path still crashed."""
    donor = _donor([300.0, 420.0, 510.0], ["Alpha", "Bravo", "Charlie"])
    rows, diag = propose_rows([300.0, None, 510.0], donor, metadata_norms=set())
    assert rows is None
    assert diag["decline"] == "missing per-track durations"

    holey = _donor([300.0, None, 510.0], ["Alpha", "Bravo", "Charlie"])
    rows, diag = propose_rows([300.0, 420.0, 510.0], holey, metadata_norms=set())
    assert rows is None
    assert diag["decline"] == "missing per-track durations"


def test_a_missing_duration_on_either_side_declines_the_whole_pair():
    donor = _donor([300.0, 420.0, 510.0], ["Alpha", "Bravo", "Charlie"])
    rows, diag = propose_rows([300.0, 0.0, 510.0], donor, metadata_norms=set())
    assert rows is None
    assert diag["decline"] == "missing per-track durations"

    holey = _donor([300.0, 0.0, 510.0], ["Alpha", "Bravo", "Charlie"])
    rows, diag = propose_rows([300.0, 420.0, 510.0], holey, metadata_norms=set())
    assert rows is None
    assert diag["decline"] == "missing per-track durations"


def test_too_few_matched_tracks_declines_the_whole_pair():
    donor = _donor([300.0], ["Alpha"])
    rows, diag = propose_rows([300.0, 420.0, 510.0, 360.0, 480.0], donor,
                              metadata_norms=set())
    assert rows is None
    assert diag["match_fraction"] < 0.80
    assert "matched" in diag["decline"]


def test_a_donor_whose_fields_disagree_in_length_declines():
    donor = DonorTape(identifier="ragged", names=["a.mp3", "b.mp3"],
                      durations=[300.0, 420.0], titles=["Alpha"])
    rows, diag = propose_rows([300.0, 420.0], donor, metadata_norms=set())
    assert rows is None
    assert diag["decline"] == "donor track fields disagree in length"


def test_an_empty_tape_declines_rather_than_dividing_by_zero():
    donor = _donor([300.0], ["Alpha"])
    rows, diag = propose_rows([], donor, metadata_norms=set())
    assert rows is None
    assert diag["decline"] == "empty tape"


def test_the_exclusion_penalty_is_what_the_best_rival_explanation_costs():
    """A lone pairing's only rival is "skip both sides", so its penalty is the
    two skipped durations. This pins the penalty's meaning -- how much the best
    global explanation degrades without the pairing -- rather than a magnitude.

    (An infinite penalty, the `forced` case the row model documents, is
    structurally unreachable: skips always leave a feasible alignment. The
    branch is kept because the interface names it, not because a tape can
    produce it.)
    """
    donor = _donor([300.0], ["Alpha"])
    rows, _diag = propose_rows([300.0], donor, metadata_norms=set())
    assert rows is not None
    assert rows[0].penalty_sec == 600.0
    assert rows[0].proposed == "Alpha"
    assert rows[0].verdict == "adopt"
