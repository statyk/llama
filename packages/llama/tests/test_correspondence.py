import pytest

from llama.correspondence import propose_titles
from llama.models import (Candidate, ParsedSetlist, ProposalRow, RecordingSummary,
                          SetlistItem, TitleProposal, Track)


def _canon(*specs):
    return ParsedSetlist(
        items=[SetlistItem(title=t, normalized=t.lower(), set=s, segue=g)
               for t, s, g in specs], confidence="high")


def _tracks(*durations, title_source="tags"):
    """A tape of `durations`, by default one whose tracks all already carry a
    title of their own.

    `title_source="tags"` is the DEFAULT deliberately, and it is what makes
    every DP-mechanics test below reach the DP at all: `propose_titles`'
    accountability guard only ever inspects runs of `unresolved` tracks
    (nothing else is adoptable), so a fully-titled tape has no run to check
    and the guard is vacuous. These fixtures carry filename-shaped titles,
    which match no canonical item, so they anchor nothing either -- they
    exercise `_solve`, and only `_solve`. The guard's own behaviour is
    pinned separately, on tapes that DO have unresolved runs, in the
    accountability tests at the bottom of this file."""
    return [Track(index=i + 1, set="1", title=f"f{i + 1}.mp3",
                  filename=f"f{i + 1}.mp3", duration_sec=d,
                  title_source=title_source)
            for i, d in enumerate(durations)]


def _tape(*spec):
    """A tape from (duration, title) pairs: a title of `None` means the track
    is still unresolved (and so adoptable), anything else is a track that
    carries its own tag title and can therefore anchor."""
    return [Track(index=i + 1, set="1",
                  title=(t if t is not None else f"f{i + 1}.mp3"),
                  filename=f"f{i + 1}.mp3", duration_sec=d,
                  title_source=("tags" if t is not None else "unresolved"))
            for i, (d, t) in enumerate(spec)]


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


def _file(name: str, title: str, length, fmt: str = "VBR MP3") -> dict:
    """One archive.org file entry, shaped to clear junk.filter_files'
    provenance/naming/duration filters (source="original", a shared filename
    stem so the dominant-convention check passes, a plausible duration)."""
    return {"name": name, "title": title, "length": str(length),
           "format": fmt, "source": "original"}


class _Donor:
    """Serves a fixed `files` list for any identifier other than the one it
    is told to reject."""

    def __init__(self, files):
        self.files = files
        self.calls = 0

    def metadata(self, identifier):
        self.calls += 1
        return {"files": self.files}


def test_sibling_item_durations_returns_none_without_a_tagged_sibling():
    """I1: the brief's own version of this test passed `ia=None`, so it
    returned on the `if ia is None` guard and never reached the donor loop,
    the uniqueness refusal, or the length invariant -- despite its name.
    Measured: replacing the whole function body with `return None` left the
    suite green. This version passes a REAL `ia` whose `.metadata` raises if
    called, so "no tagged sibling" is exercised by the candidate genuinely
    having no other recording (the for loop's `continue` skips the only
    entry and falls through to `return None`), not by short-circuiting on a
    None `ia` before the loop is ever reached."""
    from llama.correspondence import sibling_item_durations

    class _Unreachable:
        def metadata(self, identifier):
            raise AssertionError("must not be called -- there is no sibling recording")

    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only")])
    assert sibling_item_durations(_Unreachable(), cand, "only", canonical,
                                  ("VBR MP3",)) is None


def test_sibling_item_durations_resolves_every_item_from_a_tagged_donor():
    """Positive path: a donor that tags every canonical item returns exactly
    len(canonical.items) floats, and the result is usable end-to-end through
    propose_titles -- not just shape-checked in isolation."""
    from llama.correspondence import sibling_item_durations

    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    donor = _Donor([_file("d1.mp3", "Alpha", 300), _file("d2.mp3", "Bravo", 400)])
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only"),
                                RecordingSummary(identifier="donor")])
    durations = sibling_item_durations(donor, cand, "only", canonical, ("VBR MP3",))
    assert durations == [300.0, 400.0]
    assert donor.calls == 1

    prop = propose_titles(_tracks(300.0, 400.0), canonical, item_durations=durations)
    assert prop.feasible
    assert [r.title for r in prop.rows] == ["Alpha", "Bravo"]
    assert [r.evidence for r in prop.rows] == ["sibling-duration", "sibling-duration"]


def test_sibling_item_durations_refuses_a_donor_that_misses_an_item():
    """A donor that resolves only part of the setlist must not guess by
    position for the rest -- refuse the whole donor, not just the miss."""
    from llama.correspondence import sibling_item_durations

    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    donor = _Donor([_file("d1.mp3", "Alpha", 300), _file("d2.mp3", "Charlie", 400)])
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only"),
                                RecordingSummary(identifier="donor")])
    assert sibling_item_durations(donor, cand, "only", canonical, ("VBR MP3",)) is None


def test_sibling_item_durations_refuses_a_donor_with_a_duplicate_title():
    """Two donor tracks sharing a normalized title make that title
    ambiguous on the DONOR side; refuse rather than guess which one is the
    real match for the canonical item."""
    from llama.correspondence import sibling_item_durations

    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    donor = _Donor([_file("d1.mp3", "Alpha", 300), _file("d2.mp3", "Alpha", 310),
                    _file("d3.mp3", "Bravo", 400)])
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only"),
                                RecordingSummary(identifier="donor")])
    assert sibling_item_durations(donor, cand, "only", canonical, ("VBR MP3",)) is None


def test_sibling_item_durations_refuses_a_zero_length_donor_track():
    """A donor track with no usable duration (missing/zero `length`) must
    not silently hand back a 0.0 that would then poison _solve's cost model
    as if it were a real, tiny duration."""
    from llama.correspondence import sibling_item_durations

    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    donor = _Donor([_file("d1.mp3", "Alpha", 0), _file("d2.mp3", "Bravo", 400)])
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only"),
                                RecordingSummary(identifier="donor")])
    assert sibling_item_durations(donor, cand, "only", canonical, ("VBR MP3",)) is None


def test_sibling_item_durations_refuses_an_empty_canonical():
    """M3: `all(...)` over an empty `norms` list is vacuously true, so
    without an explicit guard the first non-self recording would "resolve"
    a zero-item setlist and hand back `[]` -- read by a caller as
    successfully-resolved evidence rather than "nothing to resolve"."""
    from llama.correspondence import sibling_item_durations

    canonical = ParsedSetlist(items=[], confidence="low")
    donor = _Donor([_file("d1.mp3", "Alpha", 300)])
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only"),
                                RecordingSummary(identifier="donor")])
    assert sibling_item_durations(donor, cand, "only", canonical, ("VBR MP3",)) is None


def test_sibling_item_durations_refuses_a_repeated_canonical_title():
    """I2 regression, reproducing the reviewer's measured case verbatim:
    before this fix, a canonical repeat (a reprise, or two merged tracks
    sharing a title) let a donor's single duration for that title get
    assigned by POSITION to every occurrence -- canonical
    [Alpha, Bravo, Alpha, Charlie, Delta, Echo] against a donor with one
    Alpha returned [300, 400, 300, 500, 350, 450]. That is exactly the
    positional guess this function's docstring says it refuses to make."""
    from llama.correspondence import sibling_item_durations

    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Alpha", "1", False), ("Charlie", "1", False),
                       ("Delta", "1", False), ("Echo", "1", False))
    donor = _Donor([_file("d1.mp3", "Alpha", 300), _file("d2.mp3", "Bravo", 400),
                    _file("d3.mp3", "Charlie", 500), _file("d4.mp3", "Delta", 350),
                    _file("d5.mp3", "Echo", 450)])
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only"),
                                RecordingSummary(identifier="donor")])
    assert sibling_item_durations(donor, cand, "only", canonical, ("VBR MP3",)) is None


# --- the accountability guard -------------------------------------------
#
# The M3 gate rendered four feasible tables over six real held shows and
# three of the four would have written wrong titles, with nothing in the
# rendering telling them apart. Every one of those failures was a
# canonical/track-list mismatch, so the guard is a COUNT, not a confidence:
# each maximal run of still-unresolved (== adoptable) tracks must be
# count-forced between anchors, exactly as `structure.adopt_gap_titles`
# requires before it adopts silently.
#
# Note what CANNOT be pinned here and is a real limit of the design, stated
# rather than assumed away: the whole-tape comparison the guard reports in
# its reason ("N canonical items vs M song-like tracks") does NOT by itself
# separate the gate's shows. `yondermountainstringband-2005-12-31` (declines)
# and `trampledbyturtles-2007-07-20` (renders correctly) are BOTH 24
# song-like tracks against 23 canonical items. The separating fact is local
# and structural -- where the adoptable run sits relative to anchors -- which
# is why these tests are written over runs, not totals.


def _two_items_one_gap(gap_titles):
    """Anchor, gap, anchor: `Alpha` and `Omega` are tag-titled and match the
    canonical's first and last items, so the run between them is bracketed
    and its item span is closed."""
    canonical = _canon(("Alpha", "1", False), *[(t, "1", False) for t in gap_titles],
                       ("Omega", "1", False))
    return canonical


def test_a_count_forced_gap_between_anchors_is_proposed():
    """One unresolved file, exactly one canonical item between the two
    tracks that bracket it: no shift can hide in the run, so it renders.
    This is `trampledbyturtles-2007-07-20` track 21 (`1922`) in miniature --
    the M3 gate's one correct adoption, and a title `setlist-gap` itself
    refuses because `is_real_title("1922")` is False."""
    canonical = _two_items_one_gap(["1922"])
    prop = propose_titles(_tape((300.0, "Alpha"), (300.0, None), (300.0, "Omega")),
                          canonical, item_durations=[300.0, 300.0, 300.0])
    assert prop.feasible, prop.reason
    assert prop.rows[1].title == "1922"


def test_a_gap_with_one_item_too_many_declines():
    """The `infamousstringdusters-2014-03-15` shape: the bracketed span holds
    more canonical items than the run holds files, so some item must be
    dropped or merged and the choice is unforced -- which is exactly the
    displacement that show's table shipped."""
    canonical = _two_items_one_gap(["Bravo", "Charlie"])
    prop = propose_titles(_tape((300.0, "Alpha"), (300.0, None), (300.0, "Omega")),
                          canonical, item_durations=[300.0] * 4)
    assert not prop.feasible
    assert "does not account for track 2" in prop.reason
    assert "1 file but 2 setlist items" in prop.reason
    assert "Bravo, Charlie" in prop.reason
    assert "off by 1" in prop.reason


def test_a_gap_with_one_item_too_few_declines():
    """The other side of the same boundary: two files, one item between the
    anchors. Equally unforced -- one of the two files gets no title and
    nothing says which."""
    canonical = _two_items_one_gap(["Bravo"])
    prop = propose_titles(
        _tape((300.0, "Alpha"), (300.0, None), (300.0, None), (300.0, "Omega")),
        canonical, item_durations=[300.0] * 3)
    assert not prop.feasible
    assert "does not account for tracks 2-3" in prop.reason
    assert "2 files but 1 setlist item" in prop.reason


def test_a_wholly_untagged_tape_declines_for_want_of_an_anchor():
    """Both `yondermountainstringband` shows: no track carries a title of its
    own, so nothing pins the setlist to the tape at either end and the whole
    correspondence is free to slide. The counts here even AGREE (3 items, 3
    song-like tracks) -- the decline is about anchoring, and the reason says
    so while still reporting the counts an operator needs."""
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0, 300.0, title_source="unresolved"),
                          canonical, item_durations=[300.0] * 3)
    assert not prop.feasible
    assert "cannot be pinned to tracks 1-3" in prop.reason
    assert "3 canonical items vs 3 song-like tracks - counts agree" in prop.reason


def test_a_trailing_run_declines_even_when_the_counts_work_out():
    """A run reaching the last track is anchored on one side only, so its
    span would have to run to the END of the canonical -- where a parsed LMA
    description keeps the taper's lineage notes and thank-yous. Declined
    outright, the same asymmetry `structure.gap_span` enforces for
    `setlist-gap` and for the same measured reason."""
    canonical = _two_items_one_gap(["Bravo"])
    prop = propose_titles(_tape((300.0, "Alpha"), (300.0, "Bravo"), (300.0, None)),
                          canonical, item_durations=[300.0] * 3)
    assert not prop.feasible
    assert "cannot be pinned to track 3" in prop.reason


def test_a_leading_run_fills_against_a_real_right_anchor():
    """The mirror case that is NOT declined: a run touching the START of the
    tape has a closed span, because it ends at a real anchor's item rather
    than running off the canonical's tail."""
    canonical = _canon(("Alpha", "1", False), ("Omega", "1", False))
    prop = propose_titles(_tape((300.0, None), (300.0, "Omega")),
                          canonical, item_durations=[300.0, 300.0])
    assert prop.feasible, prop.reason
    assert prop.rows[0].title == "Alpha"


def test_a_fully_titled_tape_is_not_blocked_by_the_guard():
    """Nothing is adoptable, so there is no run to account for and the guard
    must stay out of the way -- the CLI's own "nothing to adopt: every track
    already has a title" branch is what handles this case, one layer up."""
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tape((300.0, "Alpha"), (300.0, "Bravo")), canonical,
                          item_durations=[300.0, 300.0])
    assert prop.feasible, prop.reason


def test_the_guard_runs_before_the_dp_not_after():
    """A shift is CONSISTENT by construction, so an unaccountable tape still
    produces a cheap, feasible-looking DP solution -- which is why the guard
    cannot be expressed as a property of the solution. Pinned by identity of
    the reason: this tape's run is unanchored, and it must report THAT, not
    `_solve`'s "no consistent correspondence"."""
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0, title_source="unresolved"),
                          canonical, item_durations=[300.0, 300.0])
    assert not prop.feasible
    assert "cannot be pinned" in prop.reason
    assert "no consistent correspondence" not in prop.reason


def test_a_dp_solution_that_contradicts_a_forced_gap_declines():
    """Count-forcing alone is not enough, which is the whole reason the guard
    has a second half. The DP never sees an anchor: here `Alpha` segues, so
    it can spend its one merge on track 1, slide every later assignment
    forward, and hand back `Charlie`/`Omega` for a gap the anchors fix as
    `Bravo`/`Charlie`. The counts still balance -- 2 files, 2 items between
    the anchors -- so only comparing the SOLUTION against the anchoring
    catches it.

    Mutation-verified against the real fixture, not just synthetically: drop
    the merged tag title from `_staged_anchored_ymsb_show`'s track 1 and its
    24-track tape declines here rather than at the count check."""
    canonical = _canon(("Alpha", "1", True), ("Bravo", "1", False),
                       ("Charlie", "1", False), ("Omega", "1", False))
    prop = propose_titles(
        _tape((200.0, "Alpha"), (100.0, None), (100.0, None), (10.0, "Omega")),
        canonical, item_durations=[100.0] * 4)
    assert not prop.feasible
    assert "contradicts the setlist at tracks 2-3" in prop.reason


def test_the_dp_is_held_to_a_forced_gap_only_where_it_is_adoptable():
    """The mirror of the test above: the same contradiction ON AN ALREADY
    TITLED ROW is not a decline. Those rows are never adopted (`picks` is
    filtered to `unresolved` tracks one layer up), so holding the DP to them
    would reject safe proposals over display noise -- and it would reject
    `trampledbyturtles-2007-07-20`, the M3 gate's one correct adoption,
    whose rows 1-3 and 11-12 disagree with the tape's own tags."""
    canonical = _canon(("Alpha", "1", True), ("Bravo", "1", False),
                       ("Charlie", "1", False), ("Omega", "1", False))
    tape = _tape((200.0, "Alpha"), (5.0, "Bravo"), (100.0, None), (100.0, "Omega"))
    prop = propose_titles(tape, canonical, item_durations=[100.0] * 4)
    assert prop.feasible, prop.reason
    assert prop.rows[2].title == "Charlie"       # the gap: DP agrees with the anchors
    # ... and the DP really did contradict two anchored rows, so this is a
    # live case rather than one where the check simply had nothing to see:
    # it merged `Bravo` onto the track tagged `Alpha`, and called the track
    # tagged `Bravo` filler.
    assert prop.rows[0].title == "Alpha > Bravo" and tape[0].title == "Alpha"
    assert prop.rows[1].item_span is None and tape[1].title == "Bravo"
