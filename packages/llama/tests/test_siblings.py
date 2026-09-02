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


# ==========================================================================
# The guards: the ratio band (`rate_alignment`) and guard shape C+
# (`cplus_filter`).
#
# Every assertion below is on a TITLE STRING or on a decline REASON. A count
# of adopted rows cannot tell a correct fill from a shifted one, which is the
# entire failure this layer exists to prevent.
# ==========================================================================

from llama.models import Track
from llama.siblings import (
    AUTO,
    FLOOR,
    MIN_ANCHORS,
    SiblingRow,
    cplus_filter,
    rate_alignment,
)

NATO = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf",
        "Hotel", "India", "Juliett", "Kilo", "Xray", "Mike", "November"]


def _tracks(*specs):
    """specs: `(title, title_source)` pairs, in play order."""
    return [Track(index=i + 1, set="1", title=t, filename=f"f{i + 1}.mp3",
                  duration_sec=300.0, title_source=src)
            for i, (t, src) in enumerate(specs)]


def _row(track, proposed, span, verdict="adopt", reason=""):
    """A row of the shape the DP reports, with evidence already cleared:
    penalty far above MIN_EXCLUSION_PENALTY so layer 3 is not what is under
    test here."""
    return SiblingRow(track, proposed, span, 0.0, 900.0, verdict, reason)


def _one_to_one(titles, sources):
    """n target tracks paired 1:1 with n donor tracks carrying `titles`."""
    tracks = _tracks(*[(t if src != "unresolved" else f"f{i + 1}.mp3", src)
                       for i, (t, src) in enumerate(sources)])
    rows = [_row(i + 1, titles[i], (i, i + 1)) for i in range(len(titles))]
    return rows, tracks


def _adopted(rows):
    """{track: proposed} for every row C+ still lets ship."""
    return {r.track: r.proposed for r in rows if r.verdict == "adopt"}


# --------------------------------------------------------------------------
# Layer 1 -- the ratio band
# --------------------------------------------------------------------------

def test_agreement_below_auto_but_above_floor_routes_to_the_operator():
    """9 of 13 anchors agree (0.69). The four disagreements are the band's
    payload -- they are what the operator display shows three ways."""
    titles = list(NATO[:13])
    sources = [(t, "tags") for t in titles]
    rows, tracks = _one_to_one(titles, sources)
    # Four tapes tags that disagree with what the sibling proposes.
    for pos, tag in ((3, "Dire Wolf"), (7, "Casey Jones"),
                     (9, "Ripple"), (11, "Loser")):
        tracks[pos] = tracks[pos].model_copy(update={"title": tag})
    res = rate_alignment(rows, tracks)
    assert res.band == "operator"
    assert res.n_anchors == 13
    assert 0.69 < res.agreement < 0.70
    assert {(d.track, d.tape_title, d.proposed) for d in res.disagreements} == {
        (4, "Dire Wolf", "Delta"), (8, "Casey Jones", "Hotel"),
        (10, "Ripple", "Juliett"), (12, "Loser", "Xray")}


def test_agreement_below_floor_is_declined_outright():
    titles = list(NATO[:13])
    sources = [(t, "tags") for t in titles]
    rows, tracks = _one_to_one(titles, sources)
    wrong = ["Dire Wolf", "Casey Jones", "Ripple", "Loser", "Bertha",
             "Jack Straw", "Deal", "Tennessee Jed", "Candyman", "Sugaree",
             "Cassidy"]
    for pos, tag in enumerate(wrong):      # 11 wrong, 2 right -> 0.15
        tracks[pos] = tracks[pos].model_copy(update={"title": tag})
    res = rate_alignment(rows, tracks)
    assert res.band == "declined"
    assert res.agreement < FLOOR


def test_two_agreeing_anchors_are_enough_for_the_automatic_band():
    """MIN_ANCHORS from above: at 3 this pair would route to the operator."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "tags"), ("f2.mp3", "unresolved"), ("Charlie", "tags")])
    res = rate_alignment(rows, tracks)
    assert res.band == "auto"
    assert res.n_anchors == 2
    assert res.agreement == 1.0


def test_a_single_agreeing_anchor_routes_to_the_operator_not_auto():
    """MIN_ANCHORS from below: perfect agreement over ONE anchor is not a
    measured statistic -- the bands were measured over >= 2 -- so it goes to
    a human regardless of the ratio."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "tags"), ("f2.mp3", "unresolved"), ("f3.mp3", "unresolved")])
    res = rate_alignment(rows, tracks)
    assert res.agreement == 1.0
    assert res.n_anchors == 1
    assert res.band == "operator"


def test_a_single_disagreeing_anchor_routes_to_the_operator_not_declined():
    """THE ONE CASE THAT SEPARATES THE BAND LADDER'S TWO POSSIBLE ORDERINGS.

    One anchor that disagrees scores 0.0, which satisfies `< FLOOR` and
    `< MIN_ANCHORS` at once. Anchor count is evaluated FIRST, so it routes to
    the operator: FLOOR's 68-99% marginal-error basis was measured over pairs
    with >= 2 anchors and does not exist at 1. Reorder the ladder to put
    `declined` above the anchor-count clause and this test -- and, before it
    existed, nothing at all -- goes red.

    Every other single-anchor test in this file uses an AGREEING anchor
    (ratio 1.0), which both orderings route to `operator`, so none of them can
    see the difference. A ratio strictly between 0 and 1 is impossible at one
    anchor, so this fixture is the entire separating surface.
    """
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Casey Jones", "tags"), ("f2.mp3", "unresolved"),
         ("f3.mp3", "unresolved")])
    res = rate_alignment(rows, tracks)
    assert res.n_anchors == 1
    assert res.agreement == 0.0
    assert res.band == "operator"
    assert [(d.track, d.tape_title, d.proposed) for d in res.disagreements] == [
        (1, "Casey Jones", "Alpha")]


def test_a_wholly_untagged_tape_has_no_anchors_and_no_agreement():
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("f1.mp3", "unresolved"), ("f2.mp3", "unresolved"),
         ("f3.mp3", "unresolved")])
    res = rate_alignment(rows, tracks)
    assert res.band == "no-anchors"
    assert res.agreement is None
    assert res.n_anchors == 0
    assert res.disagreements == []


def test_an_override_title_anchors_the_guard_like_a_tag():
    """An operator-forced title is independent evidence, and stronger than a
    tag -- it must be able to anchor, not merely survive."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "override"), ("Bravo", "sibling-format"),
         ("f3.mp3", "unresolved")])
    res = rate_alignment(rows, tracks)
    assert res.n_anchors == 2
    assert res.band == "auto"


def test_a_setlist_gap_title_is_not_an_anchor():
    """`setlist`/`setlist-gap` titles are the canonical setlist's own text,
    not independent evidence about where this tape sits."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "setlist"), ("Bravo", "setlist-gap"),
         ("Charlie", "tags")])
    res = rate_alignment(rows, tracks)
    assert res.n_anchors == 1
    assert res.band == "operator"


def test_a_track_the_dp_paired_with_nothing_is_not_an_anchor():
    """Pins `donor_span is not None` ONLY -- this fixture never reaches the
    `bool(row.proposed)` clause, which the next two tests own."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "tags"), ("Bravo", "tags"), ("Charlie", "tags")])
    rows[1] = SiblingRow(2, None, None, 0.0, 0.0, "decline", "no sibling track")
    res = rate_alignment(rows, tracks)
    assert res.n_anchors == 2
    assert [d.track for d in res.disagreements] == []


def _untitled_donor_pairing():
    """A tagged target track the DP DID pair, with a donor track carrying no
    usable tag -- the exact row `propose_rows` emits for that shape."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "tags"), ("Bravo", "tags"), ("f3.mp3", "unresolved")])
    rows[1] = SiblingRow(2, None, (1, 2), 0.0, 900.0, "decline",
                         "sibling track untitled")
    return rows, tracks


def test_a_row_with_no_proposal_does_not_crash_the_guard():
    """`bool(row.proposed)` in `_anchor_row`, pinned as a CRASH guard.

    Without it the untitled-donor row reaches
    `loosely_same_title(track.title, None)` and `fuzzy_norm_title` raises
    `AttributeError: 'NoneType' object has no attribute 'replace'` -- a stage
    crash, not a decline, on a row the DP emits by itself.

    Deliberately separate from the denominator test below: one test asserting
    both would let either half rot while staying green.
    """
    rows, tracks = _untitled_donor_pairing()
    res = rate_alignment(rows, tracks)          # must not raise
    assert res.band in {"auto", "operator", "declined", "no-anchors"}


def test_a_track_paired_with_an_untitled_donor_is_not_counted_as_an_anchor():
    """The same clause, pinned as the ANCHOR DENOMINATOR -- the definition
    Task 7's measurement scorer has to mirror.

    An untitled donor track offers nothing to agree WITH, so it is neither an
    agreement nor a disagreement. Counting it as a disagreement would let a
    partly-untagged sibling drag a correct alignment below FLOOR, which is the
    per-donor gating this module's docstring rules out.
    """
    rows, tracks = _untitled_donor_pairing()
    res = rate_alignment(rows, tracks)
    assert res.n_anchors == 1                   # track 1 only, not track 2
    assert res.agreement == 1.0
    assert res.disagreements == []


# --------------------------------------------------------------------------
# Layer 2 -- guard shape C+
# --------------------------------------------------------------------------

def test_a_bracketed_count_forced_interior_run_adopts_its_titles():
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie", "Delta"],
        [("Alpha", "tags"), ("f2.mp3", "unresolved"),
         ("f3.mp3", "unresolved"), ("Delta", "tags")])
    out = cplus_filter(rows, tracks)
    assert _adopted(out)[2] == "Bravo"
    assert _adopted(out)[3] == "Charlie"


def test_a_leading_edge_run_adopts_gap_spans_exception_is_inherited():
    """`gap_span` keeps the leading branch (its span ends at a real anchor's
    donor track, so it cannot run off the end). C+ inherits that by calling
    it, rather than restating the rule."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("f1.mp3", "unresolved"), ("f2.mp3", "unresolved"),
         ("Charlie", "tags")])
    out = cplus_filter(rows, tracks)
    assert _adopted(out) == {1: "Alpha", 2: "Bravo", 3: "Charlie"}


def test_a_tail_run_never_adopts_automatically():
    """No track at hi+1, so `gap_span` returns None -- the absent trailing
    branch, inherited. NAMED IN MUTATION A."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie", "Delta"],
        [("Alpha", "tags"), ("Bravo", "tags"),
         ("f3.mp3", "unresolved"), ("f4.mp3", "unresolved")])
    out = cplus_filter(rows, tracks)
    assert "Charlie" not in _adopted(out).values()
    assert "Delta" not in _adopted(out).values()
    assert [r.reason for r in out if r.track in (3, 4)] == [
        "tracks 3-4: not bracketed by agreeing anchors"] * 2


def test_a_run_whose_donor_span_holds_more_tracks_than_files_declines():
    """Count-forcing. The donor span between the two agreeing anchors holds 4
    donor tracks for a 3-file run -- one file is a merge, so which title
    belongs to which file is not forced. NAMED IN MUTATION B."""
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"),
                     ("f3.mp3", "unresolved"), ("f4.mp3", "unresolved"),
                     ("Foxtrot", "tags"))
    rows = [_row(1, "Alpha", (0, 1)), _row(2, "Bravo", (1, 2)),
            _row(3, "Charlie > Delta", (2, 4)), _row(4, "Echo", (4, 5)),
            _row(5, "Foxtrot", (5, 6))]
    out = cplus_filter(rows, tracks)
    assert _adopted(out) == {1: "Alpha", 5: "Foxtrot"}
    assert [r.reason for r in out if r.track in (2, 3, 4)] == [
        "tracks 2-4: donor span holds 4 tracks for a 3-file run"] * 3


def test_runs_decline_individually_one_unbracketed_run_does_not_sink_the_pair():
    """Per-item, not per-donor. The bracketed run ships its own titles while
    the run flanked by a DISAGREEING anchor declines alone."""
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"),
                     ("f3.mp3", "unresolved"), ("Delta", "tags"),
                     ("Casey Jones", "tags"),          # disagrees with "Echo"
                     ("f6.mp3", "unresolved"), ("f7.mp3", "unresolved"),
                     ("Hotel", "tags"))
    rows = [_row(i + 1, NATO[i], (i, i + 1)) for i in range(8)]
    out = cplus_filter(rows, tracks)
    # Track 5 is not in a fill run at all -- see the next test.
    assert _adopted(out) == {1: "Alpha", 2: "Bravo", 3: "Charlie",
                             4: "Delta", 5: "Echo", 8: "Hotel"}
    assert [r.reason for r in out if r.track in (6, 7)] == [
        "tracks 6-7: not bracketed by agreeing anchors"] * 2
    assert [r.verdict for r in out if r.track in (2, 3)] == ["adopt", "adopt"]


def test_cplus_says_nothing_about_a_track_that_already_has_a_title():
    """C+ gates FILL RUNS. Track 2 here is tagged "Casey Jones" while the
    sibling proposes "Echo" -- a disagreeing anchor -- and its row survives as
    an adopt, because no run covers it.

    That is safe only because of where this sits: the transfer fills tracks
    whose `title_source == "unresolved"` and nothing else (spec, wiring
    section), exactly like `adopt_gap_titles`. A caller that wrote every adopt
    row onto its track would overwrite the tape's own tags with the sibling's,
    which is not a thing any band of this design licenses.
    """
    tracks = _tracks(("Alpha", "tags"), ("Casey Jones", "tags"),
                     ("Charlie", "tags"))
    rows = [_row(1, "Alpha", (0, 1)), _row(2, "Echo", (1, 2)),
            _row(3, "Charlie", (2, 3))]
    out = cplus_filter(rows, tracks)
    assert _adopted(out)[2] == "Echo"
    assert [t.title_source for t in tracks] == ["tags"] * 3


def test_a_disagreeing_anchor_does_not_bracket_even_though_it_is_titled():
    tracks = _tracks(("Casey Jones", "tags"), ("f2.mp3", "unresolved"),
                     ("Charlie", "tags"))
    rows = [_row(1, "Alpha", (0, 1)), _row(2, "Bravo", (1, 2)),
            _row(3, "Charlie", (2, 3))]
    out = cplus_filter(rows, tracks)
    assert "Bravo" not in _adopted(out).values()
    assert [r.reason for r in out if r.track == 2] == [
        "track 2: not bracketed by agreeing anchors"]


def test_cplus_applied_to_the_display_would_blind_the_operator():
    """INVARIANT 1, as a test. A wholly untagged tape has no anchors, so C+
    declines every run -- which is correct for the automatic band and would
    destroy the proposal display. The rows still carry their proposed titles;
    the renderer (Task 6) shows those and never calls this function."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("f1.mp3", "unresolved"), ("f2.mp3", "unresolved"),
         ("f3.mp3", "unresolved")])
    out = cplus_filter(rows, tracks)
    assert _adopted(out) == {}
    assert [r.proposed for r in out] == ["Alpha", "Bravo", "Charlie"]


def test_cplus_leaves_a_layer_three_decline_reason_alone():
    """C+ demotes ADOPTS; it never rewrites a reason layer 3 already gave.

    The run must be one C+ actually declines, or this pins nothing: a
    bracketed count-forced run takes the `continue` and no row is rewritten at
    all. Hence a TAIL run (tracks 3-4), which `gap_span` never brackets.
    """
    tracks = _tracks(("Alpha", "tags"), ("Bravo", "tags"),
                     ("f3.mp3", "unresolved"), ("f4.mp3", "unresolved"))
    rows = [_row(1, "Alpha", (0, 1)), _row(2, "Bravo", (1, 2)),
            _row(3, None, (2, 3), "decline", "sibling track untitled"),
            _row(4, "Delta", (3, 4))]
    out = cplus_filter(rows, tracks)
    by = {r.track: r for r in out}
    assert by[3].reason == "sibling track untitled"      # layer 3 survives
    assert by[4].reason == "tracks 3-4: not bracketed by agreeing anchors"
    assert by[4].verdict == "decline"


# --------------------------------------------------------------------------
# Two shift shapes, both driven through the real DP. They are DIFFERENT
# mechanisms and neither substitutes for the other:
#
#   1. a TAPE-TAG shift  -- the alignment is correct, the tape's own tags are
#      a song ahead. Anchors disagree, so BRACKETING declines the runs beside
#      them. Pins the ratio's blindness at exactly AUTO.
#   2. a DONOR-SPAN SLIDE -- the tags are right and the ALIGNMENT slid, so the
#      interior proposals are wrong titles while every anchor agrees
#      (agreement 1.0). Bracketing cannot see it; COUNT-FORCING is the only
#      thing that declines it. This is the class the spec names.
# --------------------------------------------------------------------------

def _tape_tag_shift():
    """13 target files against a 14-track sibling, through the real DP.

    NOT a donor-span shift -- the ops are 1:1 throughout and the alignment is
    correct end to end. What is shifted is the TAPE'S OWN TAGS: tracks 6-7
    carry the titles of tracks 7-8, so those two anchors disagree. Head (1-5)
    and tail (10, 12, 13) tags are correct and agree. Tracks 8-9 and 11 are
    unresolved.

    Consequences, stated plainly because the earlier docstring overclaimed
    them: the two interior fills C+ blocks at tracks 8-9 ("Hotel", "India")
    are the CORRECT titles, refused because their left flank is a disagreeing
    anchor. The one genuinely wrong title is track 11's "Kilo > Xray" -- donor
    track 12 ("Xray") is a short donor-only segment the target's taper
    dropped, and the DP absorbs it (the module docstring's absorption rule),
    proposing a segue for a file that holds one song. Count-forcing catches
    that one.

    Agreement is 8/10 = exactly AUTO, so the RATIO IS BLIND. That is what this
    fixture pins; the donor-span slide below pins the other half.

    WHY THIS FIXTURE EXISTS ALONGSIDE THE DONOR-SPAN SLIDE BELOW: a tape-tag
    shift like this one is the COMMONER phenomenon -- this phase measured
    that 24.1% of disagreeing anchors are tape-wrong (the sibling and the
    canonical setlist agree against the target's own tag). Deleting this
    fixture to make room for the rarer donor-span slide below would trade
    away coverage of the failure mode that actually shows up more often.
    """
    donor_durs = [300.0, 415.0, 520.0, 265.0, 380.0, 610.0, 245.0, 495.0,
                  330.0, 570.0, 250.0, 95.0, 440.0, 355.0]
    donor = DonorTape("sib.mtx.seamons",
                      [f"d{i + 1:02d}.mp3" for i in range(14)],
                      donor_durs, list(NATO))
    target = [300.0, 415.0, 520.0, 265.0, 380.0, 610.0, 245.0, 495.0,
              330.0, 570.0, 300.0, 440.0, 355.0]
    rows, _ = propose_rows(target, donor, metadata_norms=set())
    tracks = _tracks(
        ("Alpha", "tags"), ("Bravo", "tags"), ("Charlie", "tags"),
        ("Delta", "tags"), ("Echo", "tags"),
        ("Golf", "tags"),                      # shifted: really "Foxtrot"
        ("Hotel", "tags"),                     # shifted: really "Golf"
        ("f8.mp3", "unresolved"), ("f9.mp3", "unresolved"),
        ("Juliett", "tags"),
        ("f11.mp3", "unresolved"),
        ("Mike", "tags"), ("November", "tags"))
    return rows, tracks


def test_a_tape_tag_shift_passes_the_ratio_band_the_ratio_is_blind():
    rows, tracks = _tape_tag_shift()
    res = rate_alignment(rows, tracks)
    assert res.agreement == AUTO
    assert res.n_anchors == 10
    assert res.band == "auto"
    assert {(d.track, d.tape_title, d.proposed) for d in res.disagreements} == {
        (6, "Golf", "Foxtrot"), (7, "Hotel", "Golf")}


def test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus():
    """NAMED IN MUTATIONS A AND B (this is the test those acceptance criteria
    called "the localised-shift test"; renamed to what it reproduces).

    The pair clears the ratio band and C+ ships nothing. Run 8-9 is flanked by
    a disagreeing anchor -> not bracketed (mutation A ships "Hotel"). Run 11 is
    bracketed by two AGREEING anchors and is caught only by count-forcing
    (mutation B ships "Kilo > Xray").
    """
    rows, tracks = _tape_tag_shift()
    assert {r.track: r.proposed for r in rows if r.verdict == "adopt"}[11] == \
        "Kilo > Xray"                      # the DP does propose it
    out = cplus_filter(rows, tracks)
    adopted = _adopted(out)
    # One assertion per wrong title, so a mutation says which one it ships.
    assert "Hotel" not in adopted.values()        # bracketing catches 8-9
    assert "India" not in adopted.values()
    assert "Kilo > Xray" not in adopted.values()  # count-forcing catches 11
    assert 8 not in adopted
    assert 9 not in adopted
    assert 11 not in adopted
    reasons = {r.track: r.reason for r in out}
    assert reasons[8] == "tracks 8-9: not bracketed by agreeing anchors"
    assert reasons[9] == "tracks 8-9: not bracketed by agreeing anchors"
    assert reasons[11] == "track 11: donor span holds 2 tracks for a 1-file run"


def _donor_span_slide():
    """The arithmetic signature of a donor-span slide, through the real DP.

    9 target files against a 10-track sibling. EVERY TAPE TAG IS CORRECT and
    every anchor agrees, so `rate_alignment` reports agreement 1.0: the ratio
    has nothing to object to. The alignment itself has slid.

    The donor's track 5 ("Echo") is a song the target's taper cut. Its three
    interior files are unresolved, and their durations line up one-to-one with
    the donor's tracks 5, 6 and 7-plus-8 rather than with 6, 7 and 8, so the DP
    pairs them a song early: it proposes "Echo", "Foxtrot" and "Golf > Hotel"
    for files whose ground truth (declared by this fixture) is Foxtrot, Golf
    and Hotel. Three wrong titles, all as `adopt` rows with exclusion penalties
    of 406, 406 and 240 s -- layer 3 sees nothing wrong, because each pairing
    really is the best explanation of the durations.

    THE ERROR IS STIPULATED, NOT EXHIBITED. A scoped re-review dumped this
    fixture's rows: by the fixture's own durations, the DP's reading has
    residuals of 2.0, 2.0 and 0.0 s (207 vs Echo's 205; 393 vs Foxtrot's 395;
    425 vs Golf+Hotel's 305+120), while the DECLARED truth -- track 5 is
    really Foxtrot, 6 is really Golf, 7 is really Hotel alone -- would
    require duration errors of roughly 188, 88 and 305 s. The DP's reading is
    the plausible one; the declared truth is not. So this fixture does not
    exhibit C+ preventing a wrong adoption -- it pins C+'s YIELD COST: a
    correct proposal declined because the donor span (4 tracks) holds one
    more track than the target has files (3).

    Bracketing cannot catch this: both flanking anchors are correct AND
    agreeing. Only COUNT-FORCING can -- the donor span between them holds 4
    tracks for a 3-file run, which is the arithmetic signature of a slide.
    That is not a coincidence of this fixture but a property of the guard: if
    both flanks are right and the span count equals the file count, the
    interior is forced and cannot slide. A slide therefore ALWAYS shows up as
    a count mismatch (a donor-side skip or a merge inside the run), which is
    why mutation A cannot kill this test and mutation B must -- the asymmetry
    is derivable from the guard, not incidental to this fixture, and a reader
    who does not know it may try to "fix" this fixture to also respond to
    mutation A and break it.

    WHY THIS FIXTURE EXISTS ALONGSIDE THE TAPE-TAG SHIFT ABOVE: this is the
    RARER case, the one C+ primarily exists for -- an alignment that actually
    slides, as opposed to the commoner tape-tag failure (24.1% of disagreeing
    anchors, measured this phase) that the fixture above pins. Deleting the
    tape-tag fixture to make room for this one would trade away coverage of
    the commoner failure for the rarer one; both stay.

    HONESTY NOTE ON THE DURATIONS, because it bears on Task 7. Forcing a slide
    through a real L1 duration cost requires the target's songs to differ from
    the donor's by minutes, which is not credible tape-to-tape drift -- the
    same stipulation flagged above, restated here for the population
    question. The credible real-world mechanism -- several adjacent songs of
    near-equal length, one of them missing from the target -- was tried first
    and does NOT reach this guard: with near-equal durations every rival
    pairing is nearly as cheap, so the exclusion penalty collapses (measured:
    2-18 s against MIN_EXCLUSION_PENALTY = 60) and layer 3 declines the rows
    before C+ sees them. The ambiguity that lets an alignment slide is the
    same quantity the penalty measures. So this fixture is a faithful pin of
    the GUARD and its yield cost, and an open question about the POPULATION
    -- see the report.
    """
    donor_durs = [300.0, 415.0, 520.0, 265.0, 205.0, 395.0, 305.0, 120.0,
                  330.0, 355.0]
    donor = DonorTape("sib.slide", [f"d{i + 1:02d}.mp3" for i in range(10)],
                      donor_durs, list(NATO[:10]))
    target = [300.0, 415.0, 520.0, 265.0, 207.0, 393.0, 425.0, 330.0, 355.0]
    rows, _ = propose_rows(target, donor, metadata_norms=set())
    tracks = _tracks(("Alpha", "tags"), ("Bravo", "tags"), ("Charlie", "tags"),
                     ("Delta", "tags"),
                     ("f5.mp3", "unresolved"), ("f6.mp3", "unresolved"),
                     ("f7.mp3", "unresolved"),
                     ("India", "tags"), ("Juliett", "tags"))
    return rows, tracks


def test_a_donor_span_slide_passes_the_ratio_band_with_perfect_agreement():
    """The ratio's blindness in its sharpest form: agreement is 1.0 -- not
    merely at the AUTO knee -- while three interior titles are wrong. No
    anchor can see inside a fill run, which is the whole reason layer 2
    exists."""
    rows, tracks = _donor_span_slide()
    res = rate_alignment(rows, tracks)
    assert res.agreement == 1.0
    assert res.n_anchors == 6
    assert res.disagreements == []
    assert res.band == "auto"


def test_a_donor_span_slide_adopts_zero_interior_titles_under_cplus():
    """NAMED IN MUTATION B. The regression pin for the class C+ exists for.

    The DP really has slid: track 5's donor span is (4, 5) -- the donor's
    "Echo" -- where the correct span is (5, 6). Asserted on the span, not just
    the title, so a fixture that stopped reproducing the slide would fail here
    rather than pass vacuously.
    """
    rows, tracks = _donor_span_slide()
    proposed = {r.track: r.proposed for r in rows}
    by = {r.track: r for r in rows}
    assert by[5].donor_span == (4, 5)          # the slide, one donor track early
    assert by[5].verdict == "adopt"            # layer 3 sees nothing wrong
    assert [proposed[t] for t in (5, 6, 7)] == ["Echo", "Foxtrot", "Golf > Hotel"]

    out = cplus_filter(rows, tracks)
    adopted = _adopted(out)
    assert "Echo" not in adopted.values()
    assert "Foxtrot" not in adopted.values()
    assert "Golf > Hotel" not in adopted.values()
    assert 5 not in adopted and 6 not in adopted and 7 not in adopted
    assert {r.reason for r in out if r.track in (5, 6, 7)} == {
        "tracks 5-7: donor span holds 4 tracks for a 3-file run"}
    # The anchors around it are untouched and still ship.
    assert adopted[4] == "Delta" and adopted[8] == "India"
