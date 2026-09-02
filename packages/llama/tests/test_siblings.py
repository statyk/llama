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


def test_an_unpaired_tagged_track_is_not_an_anchor():
    """A track the DP paired with nothing offers no proposal to agree with."""
    rows, tracks = _one_to_one(
        ["Alpha", "Bravo", "Charlie"],
        [("Alpha", "tags"), ("Bravo", "tags"), ("Charlie", "tags")])
    rows[1] = SiblingRow(2, None, None, 0.0, 0.0, "decline", "no sibling track")
    res = rate_alignment(rows, tracks)
    assert res.n_anchors == 2
    assert [d.track for d in res.disagreements] == []


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
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"),
                     ("Charlie", "tags"))
    rows = [_row(1, "Alpha", (0, 1)),
            _row(2, None, (1, 2), "decline", "sibling track untitled"),
            _row(3, "Charlie", (2, 3))]
    out = cplus_filter(rows, tracks)
    assert [r.reason for r in out if r.track == 2] == ["sibling track untitled"]


# --------------------------------------------------------------------------
# The localised shift -- the regression pin for the class C+ exists to catch
# --------------------------------------------------------------------------

def _localised_shift():
    """The `gd1971-08-06` shape, synthetic and driven through the real DP.

    13 target files against a 14-track sibling. Head (1-5) and tail (10, 12,
    13) tags are correct and agree. Tracks 6-7 carry tags shifted one song
    forward -- the tape's own tagger was a song ahead -- so they disagree.
    Tracks 8-9 and 11 are unresolved.

    Donor track 12 ("Xray") is a short donor-only segment the target's taper
    dropped; the DP absorbs it into target track 11 (the module docstring's
    absorption rule), giving that run a 2-track donor span for one file.

    Agreement is 8/10 = exactly AUTO, so the RATIO IS BLIND to the shift.
    That blindness is the point: pinned here as documentation, and the reason
    layer 2 exists.
    """
    donor_durs = [300.0, 415.0, 520.0, 265.0, 380.0, 610.0, 245.0, 495.0,
                  330.0, 570.0, 250.0, 95.0, 440.0, 355.0]
    donor = DonorTape("sib.mtx.seamons",
                      [f"d{i + 1:02d}.mp3" for i in range(14)],
                      donor_durs, list(NATO))
    target = [300.0, 415.0, 520.0, 265.0, 380.0, 610.0, 245.0, 495.0,
              330.0, 570.0, 300.0, 440.0, 355.0]
    rows, diag = propose_rows(target, donor, metadata_norms=set())
    tracks = _tracks(
        ("Alpha", "tags"), ("Bravo", "tags"), ("Charlie", "tags"),
        ("Delta", "tags"), ("Echo", "tags"),
        ("Golf", "tags"),                      # shifted: really "Foxtrot"
        ("Hotel", "tags"),                     # shifted: really "Golf"
        ("f8.mp3", "unresolved"), ("f9.mp3", "unresolved"),
        ("Juliett", "tags"),
        ("f11.mp3", "unresolved"),
        ("Mike", "tags"), ("November", "tags"))
    return rows, tracks, diag


def test_the_localised_shift_passes_the_ratio_band_the_ratio_is_blind():
    rows, tracks, _ = _localised_shift()
    res = rate_alignment(rows, tracks)
    assert res.agreement == AUTO
    assert res.n_anchors == 10
    assert res.band == "auto"
    assert {(d.track, d.tape_title, d.proposed) for d in res.disagreements} == {
        (6, "Golf", "Foxtrot"), (7, "Hotel", "Golf")}


def test_the_localised_shift_adopts_zero_interior_titles_under_cplus():
    """NAMED IN MUTATIONS A AND B. The pair clears the ratio band; C+ must
    ship nothing in the shifted interior.

    Run 8-9 is flanked by a disagreeing anchor -> not bracketed. Run 11 IS
    bracketed by two agreeing anchors and is caught only by count-forcing --
    the shift's last wrong title, which would otherwise ship "Kilo > Xray"
    onto a file holding one song.
    """
    rows, tracks, _ = _localised_shift()
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
