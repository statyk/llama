import llama.structure as structure
from llama.models import ParsedSetlist, SetlistItem, SourcedParse, Track
from llama.songs import normalize_song
from llama.structure import (
    TAIL_GUARD_ITEMS,
    TAIL_GUARD_MAX_SKIP,
    TAIL_GUARD_TRACKS_REMAINING,
    _tail_guard_declines,
    _window_hi,
    align,
    blend_segues,
    from_setlistfm,
    is_filler,
    norm_title,
    rank_parses,
    structure_guard,
)


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


def pl(*titles_segues, confidence="high"):
    items = [SetlistItem(title=t, normalized=norm_title(t), set="1", segue=g)
             for t, g in titles_segues]
    return ParsedSetlist(items=items, confidence=confidence)


def test_blend_overlays_lma_segues_onto_winner():
    winner = pl(("China Cat Sunflower", False), ("I Know You Rider", False), ("Loser", False))
    lma = pl(("China Cat Sunflower", True), ("I Know You Rider", False), ("Loser", False))
    out = blend_segues(winner, lma)
    assert [i.segue for i in out.items] == [True, False, False]
    assert out.confidence == winner.confidence


def test_blend_matches_repeated_songs_in_order():
    winner = pl(("Not Fade Away", False), ("GDTRFB", False), ("Not Fade Away", False))
    lma = pl(("Not Fade Away", True), ("GDTRFB", True), ("Not Fade Away", False))
    out = blend_segues(winner, lma)
    assert [i.segue for i in out.items] == [True, True, False]


def test_blend_noop_when_lma_missing_same_or_segue_free():
    winner = pl(("A", False), ("B", False))
    assert blend_segues(winner, None) is winner
    assert blend_segues(winner, winner) is winner
    assert blend_segues(winner, pl(("A", False), ("B", False))) is winner


def tr(idx, title):
    return Track(index=idx, set="1", title=title, filename=f"t{idx:02d}.mp3",
                 duration_sec=300.0, segue=False, title_source="tags")


def canon(*rows):
    """rows: (set, title, segue)"""
    items = [SetlistItem(title=t, normalized=norm_title(t), set=s, segue=g)
             for s, t, g in rows]
    return ParsedSetlist(items=items, confidence="high")


def test_align_exact_match():
    c = canon(("1", "A", True), ("1", "B", False), ("2", "C", False))
    r = align([tr(1, "A"), tr(2, "B"), tr(3, "C")], c)
    assert r.sets == ["1", "1", "2"]
    assert r.segues == [True, False, False]
    assert r.coverage == 1.0
    assert r.conflicts == []


def test_align_repeated_songs_map_in_order():
    c = canon(("2", "Not Fade Away", True), ("2", "GDTRFB", True), ("2", "Not Fade Away", False),
              ("encore", "Baby Blue", False))
    r = align([tr(1, "Not Fade Away >"), tr(2, "GDTRFB >"), tr(3, "Not Fade Away"),
               tr(4, "E: Baby Blue")], c)
    assert r.sets == ["2", "2", "2", "encore"]
    assert r.segues == [True, True, False, False]
    assert r.coverage == 1.0


def test_align_skips_merged_canonical_item_via_lookahead():
    # Recording merges "WRS Part 1" into the Prelude file: canonical has 3 items,
    # the recording 2 files. "Let It Grow" is found 2 items ahead.
    c = canon(("2", "Weather Report Suite Prelude", True),
              ("2", "Weather Report Suite Part 1", True),
              ("2", "Let It Grow", True),
              ("2", "Row Jimmy", False),
              ("2", "Ship of Fools", False))
    r = align([tr(1, "Weather Report Suite Prelude >"), tr(2, "Let It Grow >"),
               tr(3, "Row Jimmy"), tr(4, "Ship of Fools")], c)
    assert r.sets == ["2", "2", "2", "2"]
    assert r.coverage == 1.0
    assert r.conflicts == ["Weather Report Suite Part 1"]


def test_align_unmatched_tracks_inherit_previous_set():
    c = canon(("1", "A", False), ("2", "B", False))
    r = align([tr(1, "A"), tr(2, "Tuning"), tr(3, "B"), tr(4, "Crowd")], c)
    assert r.sets == ["1", "1", "2", "2"]
    assert r.matched == [True, False, True, False]
    assert r.coverage == 1.0  # Tuning/Crowd are filler, excluded from coverage
    assert r.segues[1] is False


def test_align_first_track_unmatched_defaults_to_set_1():
    c = canon(("1", "B", False))
    r = align([tr(1, "Intro"), tr(2, "B")], c)
    assert r.sets == ["1", "1"]


def test_alignment_coverage_ignores_filler_tracks():
    # Real case (GD 1977-05-07): a third of the tracks are Tune Up / Equipment
    # Repairs / Crowd filler that no canonical setlist contains. Coverage is
    # measured over song-like tracks only.
    c = canon(("1", "A", False), ("1", "B", False), ("2", "C", False))
    tracks = [tr(1, "Tune Up"), tr(2, "A"), tr(3, "Equipment Repairs"),
              tr(4, "B"), tr(5, "Stage Annoucements"), tr(6, "C"),
              tr(7, "Crowd Noise")]
    r = align(tracks, c)
    assert r.coverage == 1.0
    assert r.sets == ["1", "1", "1", "1", "1", "2", "2"]  # filler inherits sets


def test_alignment_coverage_all_filler_is_zero():
    r = align([tr(1, "Tuning"), tr(2, "Applause")], canon(("1", "A", False)))
    assert r.coverage == 0.0


def test_align_empty_inputs():
    r = align([], canon(("1", "A", False)))
    assert r.sets == [] and r.coverage == 0.0
    r = align([tr(1, "A")], ParsedSetlist())
    assert r.sets == ["1"] and r.coverage == 0.0


def _tracks(n, dur=300.0):
    return [Track(index=i + 1, set="1", title=f"S{i}", filename=f"t{i}.mp3",
                  duration_sec=dur, segue=False, title_source="tags") for i in range(n)]


def test_guard_fires_on_long_duration_no_breaks():
    # 28 tracks x 460s ≈ 215 min: two-set-show territory with no breaks.
    assert structure_guard(_tracks(28, dur=460.0), []) == \
        "single-set structure for a long show (215 min)"


def test_guard_allows_real_long_single_sets():
    # GD 1969-12-07 Fillmore West: 12 tracks, ~106 min, genuinely one set
    # (multi-band bill). Anything under 2.5 hours is plausible as one set.
    assert structure_guard(_tracks(12, dur=530.0), []) is None


def test_guard_ignores_track_count():
    # Many short songs in one set is normal club-show shape; count is not a signal.
    assert structure_guard(_tracks(21, dur=220.0), []) is None   # ~77 min, 21 tracks
    assert structure_guard(_tracks(20, dur=None), []) is None    # no durations known


def test_guard_fires_when_multiset_evidence_lost_in_alignment():
    got = structure_guard(_tracks(8, dur=300.0), [], evidence_sets={"1", "2"})
    assert got == "setlist evidence shows multiple sets but alignment found none"


def test_guard_silent_on_short_single_set_and_any_multiset():
    assert structure_guard(_tracks(8, dur=300.0), []) is None          # 40 min, 8 tracks
    assert structure_guard(_tracks(30, dur=700.0), [11]) is None       # has a break
    assert structure_guard(_tracks(30, dur=700.0), [11], evidence_sets={"1", "2"}) is None


def test_guard_respects_thresholds():
    assert structure_guard(_tracks(28, dur=460.0), [], min_minutes=300) is None


def _sets(labels, dur=300.0):
    return [Track(index=i + 1, set=s, title=f"S{i}", filename=f"t{i}.mp3",
                  duration_sec=dur, segue=False, title_source="tags")
            for i, s in enumerate(labels)]


def test_guard_set_count_ignores_encore():
    # 3 numbered sets + an encore vs jerrybase's 3 sets is NOT a mismatch: an
    # encore is a coda, not a set. (gd 1972-08-27 shape.)
    tracks = _sets(["1", "1", "2", "2", "3", "3", "encore"])
    assert structure_guard(tracks, [2, 4, 6], expected_set_count=3) is None
    # a genuine numbered-set mismatch still fires (encore aside).
    got = structure_guard(_sets(["1", "1", "2", "2", "encore"]), [2, 4],
                          expected_set_count=3)
    assert got == "structure has 2 sets but jerrybase shows 3"
    assert structure_guard(_tracks(12, dur=530.0), [], min_minutes=90) is not None


def _guard_tracks(sets, dur=60):
    from llama.models import Track
    return [Track(index=i + 1, set=s, title=f"T{i}", filename=f"{i}.mp3",
                  duration_sec=dur, title_source="tags") for i, s in enumerate(sets)]


def test_structure_guard_flags_set_count_mismatch():
    from llama.titles import set_breaks
    from llama.structure import structure_guard

    tracks = _guard_tracks(["1", "1", "2", "2", "3"])   # 3 genuine numbered sets
    breaks = set_breaks(tracks)
    flag = structure_guard(tracks, breaks, expected_set_count=2)
    assert flag is not None
    assert "3" in flag and "2" in flag


def test_structure_guard_no_flag_when_set_count_matches():
    from llama.titles import set_breaks
    from llama.structure import structure_guard

    # 2 numbered sets + an encore vs jerrybase's 2 sets is a match: an encore is
    # a coda, not counted as a set.
    tracks = _guard_tracks(["1", "1", "2", "2", "encore"])
    breaks = set_breaks(tracks)
    assert structure_guard(tracks, breaks, expected_set_count=2) is None


def test_structure_guard_preserves_old_behavior_without_expected_count():
    from llama.titles import set_breaks
    from llama.structure import structure_guard

    tracks = _guard_tracks(["1", "1", "1"], dur=200 * 60)  # long single set
    assert structure_guard(tracks, set_breaks(tracks)) is not None
    short = _guard_tracks(["1", "1", "1"], dur=60)
    assert structure_guard(short, set_breaks(short)) is None


from llama.models import AlignedStructure, AlignedTrack
from llama.structure import apply_llm_alignment


def test_apply_llm_alignment_builds_result():
    tracks = _tracks(3)
    resp = AlignedStructure(tracks=[
        AlignedTrack(index=1, set="1", segue=True, matched_title="A"),
        AlignedTrack(index=3, set="encore", segue=False, matched_title=""),
        AlignedTrack(index=2, set="2", segue=False, matched_title="B"),
    ])
    r = apply_llm_alignment(tracks, resp)
    assert r.sets == ["1", "2", "encore"]      # reordered by index
    assert r.segues == [True, False, False]
    assert r.matched == [True, True, False]
    assert abs(r.coverage - 2 / 3) < 1e-9


def test_apply_llm_alignment_rejects_bad_indices_or_sets():
    tracks = _tracks(2)
    missing = AlignedStructure(tracks=[AlignedTrack(index=1, set="1")])
    assert apply_llm_alignment(tracks, missing) is None
    bad_set = AlignedStructure(tracks=[AlignedTrack(index=1, set="1"),
                                       AlignedTrack(index=2, set="afterparty")])
    assert apply_llm_alignment(tracks, bad_set) is None


import pytest

from llama.structure import venues_equivalent


@pytest.mark.parametrize("a,b", [
    ("RFK Stadium", "Robert F. Kennedy Stadium"),   # initialism + shared tail
    ("MSG", "Madison Square Garden"),               # bare initialism
    ("Winterland", "Winterland Arena"),             # token subset
    ("Barton Hall", "Barton Hall, Cornell University"),  # subset, city/school tail
    ("Fillmore Aud", "Fillmore Auditorium"),        # abbreviation expansion
    ("Fillmore East", "Fillmore East (New York)"),  # parenthetical tail dropped
    ("Fillmore Theatre", "Fillmore Theater"),       # theatre/theater
    ("The Spectrum", "Spectrum"),                   # stopword dropped
    ("RFK Stadium", "RFK Stadium"),                 # identity
])
def test_venues_equivalent_true(a, b):
    assert venues_equivalent(a, b)
    assert venues_equivalent(b, a)   # symmetric


@pytest.mark.parametrize("a,b", [
    ("Fillmore East", "Fillmore West"),             # different halls
    ("Boston Garden", "Boston Music Hall"),         # different venues, shared city
    ("Winterland", "Warfield"),                     # unrelated
])
def test_venues_not_equivalent(a, b):
    assert not venues_equivalent(a, b)
    assert not venues_equivalent(b, a)


# --- fuzzy title matching (jerrybase closer matching; see the 2026-08-01 spec) --

from llama.structure import fuzzy_norm_title, fuzzy_title_eq, title_components


def test_fuzzy_norm_title_folds_ampersand_to_and():
    # normalize_song's punctuation strip deletes "&" outright, so these two
    # spellings of one song normalize differently under plain norm_title.
    assert norm_title("Me & My Uncle") != norm_title("Me and My Uncle")
    assert fuzzy_norm_title("Me & My Uncle") == fuzzy_norm_title("Me and My Uncle")
    assert fuzzy_norm_title("Around & Around") == fuzzy_norm_title("Around and Around")


def test_title_components_splits_merged_tracks_in_order():
    assert title_components("China Cat Sunflower > I Know You Rider") == [
        "china cat sunflower", "i know you rider"]
    assert title_components("Help on the Way -> Slipknot! -> Franklin's Tower") == [
        "help on the way", "slipknot", "franklins tower"]


def test_title_components_of_plain_title_is_single_component():
    assert title_components("Morning Dew") == ["morning dew"]


def test_title_components_ignores_trailing_segue_marker():
    # A dangling ">" is a segue flag, not a second song.
    assert title_components("Truckin >") == ["truckin"]


def test_fuzzy_title_eq_accepts_subtitle_both_directions():
    short, long = "mississippi half step", "mississippi half step uptown toodeloo"
    assert fuzzy_title_eq(short, long)
    assert fuzzy_title_eq(long, short)


def test_fuzzy_title_eq_rejects_single_word_shorthand():
    # Single-word shorthand is the hardcoded table's job, not a general rule's:
    # a 1-word floor would match "Dew" to anything containing the word.
    assert not fuzzy_title_eq("scarlet", "scarlet begonias")
    assert not fuzzy_title_eq("dew", "morning dew")


def test_fuzzy_title_eq_rejects_unrelated_titles():
    assert not fuzzy_title_eq("morning dew", "casey jones")
    assert not fuzzy_title_eq("half step mississippi", "mississippi half step")


from llama.songs import GD_SHORTHAND


def test_shorthand_expands_only_when_aliases_passed():
    assert fuzzy_norm_title("Scarlet") == "scarlet"
    assert fuzzy_norm_title("Scarlet", GD_SHORTHAND) == "scarlet begonias"
    assert fuzzy_norm_title("Chinacat", GD_SHORTHAND) == "china cat sunflower"


def test_shorthand_applies_to_each_merged_component():
    assert title_components("Scarlet > Fire", GD_SHORTHAND) == [
        "scarlet begonias", "fire on the mountain"]


def test_shorthand_targets_are_all_canonical_and_two_way_safe():
    # Every value must itself be a full title, never another key: a table that
    # chains would depend on lookup order.
    assert not (set(GD_SHORTHAND.values()) & set(GD_SHORTHAND))


def test_blocklist_stops_the_known_cross_song_subphrase():
    # Two different songs, both in the repertoire; the subphrase rule pairs
    # them on 15 corpus shows.
    assert not fuzzy_title_eq("its all over now", "its all over now baby blue")
    assert not fuzzy_title_eq("its all over now baby blue", "its all over now")
    # ... but the correct shortening must keep working.
    assert fuzzy_title_eq("baby blue", "its all over now baby blue")


def test_components_drop_credit_only_parentheticals():
    # Seen live: "(Cripe)", "(SBD)", "(Tape Flip)", "(White Strat)".
    assert title_components("Lazy Lightning* -> (Cripe)") == ["lazy lightning"]
    assert title_components("New Orleans > (w/ Rick Danko)") == ["new orleans"]


def test_components_strip_trailing_subtitle_parenthetical():
    assert title_components("You Ain't Woman Enough (to Take My Man)") == [
        "you aint woman enough"]


def test_components_keep_a_real_second_song():
    assert title_components("China Cat Sunflower > I Know You Rider") == [
        "china cat sunflower", "i know you rider"]


def test_components_of_an_all_parenthetical_title_fall_back_to_the_whole_title():
    assert title_components("(Tape Flip)") == ["tape flip"]


def test_align_folds_ampersand_on_both_sides():
    c = canon(("1", "Me and My Uncle", False), ("1", "Big River", False))
    r = align([tr(1, "Me & My Uncle"), tr(2, "Big River")], c)
    assert r.sets == ["1", "1"]
    assert r.matched == [True, True]


def test_align_matches_a_dropped_subtitle():
    c = canon(("1", "Mississippi Half Step Uptown Toodeloo", False),
              ("2", "Big River", False))
    r = align([tr(1, "Mississippi Half Step"), tr(2, "Big River")], c)
    assert r.sets == ["1", "2"]
    assert r.matched == [True, True]


def test_align_prefers_an_exact_match_over_a_subphrase_in_the_window():
    # "Not Fade Away" IS a subphrase of "Not Fade Away Chant", which sits first
    # in the window. Exact-first must reach past it to the real item; the sets
    # differ so the assertion says which item was actually consumed.
    c = canon(("1", "Not Fade Away Chant", False), ("2", "Not Fade Away", False))
    r = align([tr(1, "Not Fade Away")], c)
    assert r.sets == ["2"]
    assert r.conflicts == ["Not Fade Away Chant"]


def test_align_shorthand_only_with_aliases():
    from llama.songs import GD_SHORTHAND
    c = canon(("2", "Scarlet Begonias", True), ("2", "Fire on the Mountain", False))
    plain = align([tr(1, "Scarlet"), tr(2, "Fire")], c)
    assert plain.matched == [False, False]
    gated = align([tr(1, "Scarlet"), tr(2, "Fire")], c, aliases=GD_SHORTHAND)
    assert gated.matched == [True, True]
    assert gated.sets == ["2", "2"]


def test_align_does_not_pair_the_blocklisted_pair():
    c = canon(("1", "It's All Over Now, Baby Blue", False))
    r = align([tr(1, "It's All Over Now")], c)
    assert r.matched == [False]
    assert r.conflicts == ["It's All Over Now, Baby Blue"]


def test_align_matches_a_merged_track_as_a_run():
    c = canon(("2", "China Cat Sunflower", True), ("2", "I Know You Rider", False),
              ("2", "Big River", False))
    r = align([tr(1, "China Cat Sunflower > I Know You Rider"), tr(2, "Big River")], c)
    assert r.sets == ["2", "2"]
    assert r.matched == [True, True]
    # Both consumed items count as matched, so neither is a conflict.
    assert r.conflicts == []
    assert r.coverage == 1.0
    assert r.merge_conflicts == []


def test_merged_run_takes_the_segue_that_follows_the_last_component():
    c = canon(("2", "Scarlet Begonias", True), ("2", "Fire on the Mountain", True),
              ("2", "Estimated Prophet", False))
    r = align([tr(1, "Scarlet Begonias > Fire on the Mountain"),
               tr(2, "Estimated Prophet")], c)
    assert r.segues == [True, False]


def test_merged_run_spanning_a_set_break_is_flagged():
    # Physically impossible: one continuous performance cannot straddle a
    # break, so this is evidence the parse is wrong.
    c = canon(("1", "Playing in the Band", True), ("2", "Uncle John's Band", False))
    r = align([tr(1, "Playing in the Band > Uncle John's Band")], c)
    assert r.sets == ["1"]          # first component's set
    assert r.merge_conflicts == [1]  # 1-based track number


def test_merged_run_needs_every_component_to_match():
    # "patch" is a transfer note, not a song: the run must not form, and the
    # track falls back to a single-title match on the whole string.
    c = canon(("2", "Space", False), ("2", "The Other One", False))
    r = align([tr(1, "Space > patch"), tr(2, "The Other One")], c)
    assert r.matched == [False, True]
    assert r.merge_conflicts == []


def test_align_matches_a_leading_encore_marker_item():
    # Formerly a characterization test pinning a KNOWN PARSER DEFECT:
    # `setlist.py`'s `_INLINE_MARKER` used to require a set/encore marker to
    # carry a MANDATORY digit ("e\d") to split mid-line, so a bare mid-line
    # "E:" never triggered a split, and a description like "...Sugar
    # Magnolia; E: Goin' Down the Road..." left the encore song's canonical
    # item stamped with the PRECEDING numbered set (per the project owner,
    # bare-"E:" items of this shape occur in the corpus: 18 shows for
    # "Brokedown Palace", 11 for "Johnny B. Goode", 7 for "Casey Jones", 7
    # for "Black Muddy River"). Phase 3 fixed `_INLINE_MARKER` to match
    # `_ENCORE_LINE`'s optional digit ("e\d?"), so the parser now correctly
    # labels such items "encore" instead of the preceding set.
    #
    # This test no longer exercises the parser (it builds the canonical item
    # by hand), so the fix isn't visible by re-running it unchanged - it is
    # retargeted to lock in the CORRECTED item shape a fixed parser now
    # produces: title still carrying an unstripped "E: " prefix (as
    # `setlist.py:114`/`structure.py`'s `from_setlistfm` both build
    # `SetlistItem.normalized` from the UNSTRIPPED `normalize_song(title)`),
    # but `set` now correctly "encore" rather than "1". What it actually pins:
    # `align` matches an item carrying a leading "E: " marker to a clean track
    # title.
    #
    # Built by hand instead of via `canon()`: `canon()` sets `normalized=
    # norm_title(t)`, which already strips the "E:" prefix, so a canonical
    # item built that way never actually carries the "E: " prefix in
    # `.normalized` and this test would pass even without Task 4's `align()`
    # change - proving nothing about the fuzzy-matching behavior above.
    c = ParsedSetlist(items=[
        SetlistItem(title="Sugar Magnolia", normalized=normalize_song("Sugar Magnolia"),
                    set="1", segue=False),
        SetlistItem(title="E: Baby Blue", normalized=normalize_song("E: Baby Blue"),
                    set="encore", segue=False),
    ], confidence="high")
    r = align([tr(1, "Sugar Magnolia"), tr(2, "Baby Blue")], c)
    assert r.matched == [True, True]
    assert r.sets == ["1", "encore"]


def test_filler_covers_spoken_and_break_segments():
    for t in ("Intro", "intro", "Outro", "Chat", "Chatter", "talk",
              "Band Intros & Chatter", "Encore Break", "encore break",
              "Intro by Fiona Black"):
        assert is_filler(t), t


def test_filler_never_swallows_drums_space_or_feedback():
    # Domain ruling: Drums, Space and Feedback are SONGS. They segue into and
    # out of adjacent songs and sit mid-second-set from ~1979 on. Treating them
    # as filler would drop them out of set-break reasoning entirely.
    for t in ("Drums", "Drums >", "Drumz", "Space", "Space ->", "Feedback",
              "Drums > Space >"):
        assert not is_filler(t), t


def test_filler_does_not_match_songs_containing_those_words():
    # "talk" must not fire on "Talkin'", "chat" must not fire on "Chattanooga".
    for t in ("Talkin' World War III Blues", "Chattanooga Choo Choo",
              "Introduction To The Blues Jam", "Big Railroad Blues"):
        assert not is_filler(t), t


def test_encore_break_does_not_prefix_match_a_song():
    # "encore break" is filler, but a bare `encore\s+break` had no trailing
    # word boundary, so it prefix-matched a song whose title continues into
    # another word ("Encore Breakdown"). The `s?\b` anchor fixes that class.
    #
    # NOT fixed here, deliberately: `is_filler` uses `.search()`, so a title
    # that CONTAINS a filler token as a whole word ("Encore Break On Through")
    # still matches. That is a known, owner-deferred issue affecting every
    # `_FILLER` alternative, not just this one; fixing it means making
    # `is_filler` components-based, which is a semantics change out of scope
    # for this phase.
    assert is_filler("Encore Break")
    assert is_filler("encore breaks")
    assert not is_filler("Encore Breakdown")


def test_space_insensitive_fallback_matches_spacing_variants():
    assert fuzzy_title_eq("turn on your lovelight", "turn on your love light")
    assert fuzzy_title_eq("cc rider", "c c rider")
    assert fuzzy_title_eq("west la fadeaway", "west l a fadeaway")


def test_space_insensitive_fallback_respects_the_blocklist():
    assert not fuzzy_title_eq("its all over now", "its all over now baby blue")


def test_space_insensitive_fallback_does_not_equate_distinct_songs():
    assert not fuzzy_title_eq("black peter", "black muddy river")
    assert not fuzzy_title_eq("the wheel", "wheel of fortune")


def test_spelling_variants_collapse_under_the_family_table():
    from llama.songs import GD_SHORTHAND
    pairs = [("Touch of Gray", "Touch of Grey"),
             ("Drumz", "Drums"),
             ("Throwin Stones", "Throwing Stones"),
             ("Man Smart, Woman Smarter", "Women Are Smarter")]
    for a, b in pairs:
        assert fuzzy_norm_title(a, GD_SHORTHAND) == fuzzy_norm_title(b, GD_SHORTHAND), (a, b)


def test_variants_do_nothing_without_the_family_table():
    assert fuzzy_norm_title("Touch of Gray") != fuzzy_norm_title("Touch of Grey")
    assert fuzzy_norm_title("Women Are Smarter") != fuzzy_norm_title("Man Smart, Woman Smarter")


def test_space_after_drums_matches_a_jam_item():
    c = canon(("2", "Eyes Of The World", True), ("2", "Drums", True),
              ("2", "Jam", True), ("2", "Stella Blue", False))
    r = align([tr(1, "Eyes Of The World >"), tr(2, "Drums >"),
               tr(3, "Space >"), tr(4, "Stella Blue")], c)
    assert r.matched == [True, True, True, True]
    assert r.sets == ["2", "2", "2", "2"]


def test_space_without_a_preceding_drums_does_not_match_jam():
    c = canon(("2", "Eyes Of The World", True), ("2", "Jam", True),
              ("2", "Stella Blue", False))
    r = align([tr(1, "Eyes Of The World >"), tr(2, "Space >"),
               tr(3, "Stella Blue")], c)
    assert r.matched == [True, False, True]


def test_a_jam_track_does_not_match_a_space_item():
    # The rule is directional: the TRACK being called Space is the evidence.
    c = canon(("2", "Drums", True), ("2", "Space", True), ("2", "Stella Blue", False))
    r = align([tr(1, "Drums >"), tr(2, "Jam >"), tr(3, "Stella Blue")], c)
    assert r.matched == [True, False, True]


def test_rank_parses_prefers_a_complete_parse_over_a_confident_fragment():
    frag = SourcedParse(source="lma:a", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"S{n}", normalized=f"s{n}", set="encore")
               for n in range(8)], confidence="high"))
    full = SourcedParse(source="lma:b", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"T{n}", normalized=f"t{n}", set="1")
               for n in range(34)], confidence="medium"))
    assert rank_parses([frag, full], target_count=34) is full


def test_rank_parses_keeps_todays_order_when_all_are_implausible():
    # Guards GRACEFUL DEGRADATION, not tier placement: with both candidates at
    # 1 item the plausibility tier is constant, so this passes under every tier
    # position (measured, including with the tier removed). What it would catch
    # is plausibility reimplemented as a filter rather than a tier - that
    # returns None here. Placement is pinned by
    # test_rank_parses_prefers_a_complete_parse_over_a_confident_fragment.
    a = SourcedParse(source="lma:a", parsed=ParsedSetlist(
        items=[SetlistItem(title="A", normalized="a", set="1")], confidence="high"))
    b = SourcedParse(source="lma:b", parsed=ParsedSetlist(
        items=[SetlistItem(title="B", normalized="b", set="1")], confidence="low"))
    assert rank_parses([a, b], target_count=40) is a


def test_setlistfm_outranks_a_complete_lma_parse_however_short_it_is():
    # The plausibility tier must stay BELOW the setlist.fm source check. A
    # 3-item setlist.fm stub is implausible against a 34-track tape and the
    # 34-item LMA parse is plausible, so this is exactly the case that inverts
    # if the tier is hoisted above the source bit.
    fm = SourcedParse(source="setlist.fm", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"F{n}", normalized=f"f{n}", set="1")
               for n in range(3)], confidence="high"))
    lma = SourcedParse(source="lma:x", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"T{n}", normalized=f"t{n}", set="1")
               for n in range(34)], confidence="high"))
    assert rank_parses([lma, fm], target_count=34) is fm


def test_plausibility_floor_never_exceeds_the_tape_itself():
    # On a tape of <=4 kept tracks a bare max(5, tc // 2) floor demands more
    # items than the tape has, so the parse that matches the tape exactly grades
    # implausible while a longer parse of someone ELSE's show grades plausible
    # and wins. The min(target_count, ...) clamp is what stops that inversion.
    complete = SourcedParse(source="lma:complete", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"C{n}", normalized=f"c{n}", set="1")
               for n in range(3)], confidence="medium"))
    over = SourcedParse(source="lma:over", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"O{n}", normalized=f"o{n}", set="1")
               for n in range(7)], confidence="low"))
    assert rank_parses([over, complete], target_count=3) is complete


def test_numeric_prefixed_tracks_match_on_an_enumerated_tape():
    c = canon(("1", "Lost My Driving Wheel", True), ("1", "History Lesson", True),
              ("1", "KC Jones", False))
    r = align([tr(1, "18 Lost My Driving Wheel"), tr(2, "08 History Lesson"),
               tr(3, "[05:20] KC Jones")], c)
    assert r.matched == [True, True, True]


def test_numeric_titles_survive_on_a_non_enumerated_tape():
    c = canon(("1", "8 Miles High", True), ("1", "1952 Vincent Black Lightning", False))
    r = align([tr(1, "8 Miles High"), tr(2, "1952 Vincent Black Lightning")], c)
    assert r.matched == [True, True]


def test_a_real_numeric_title_is_not_stripped_even_when_enumerated():
    # "8 Miles High" matches unstripped, so the fallback never fires on it.
    c = canon(("1", "8 Miles High", True), ("1", "Bertha", True),
              ("1", "Sugaree", True), ("1", "Loser", False))
    r = align([tr(1, "8 Miles High"), tr(2, "02 Bertha"), tr(3, "03 Sugaree"),
               tr(4, "04 Loser")], c)
    assert r.matched == [True, True, True, True]


def test_the_strip_is_a_miss_path_fallback_not_an_eager_rewrite():
    # The three tests above do NOT pin the miss-path ordering: measured, an
    # eager strip passes all of them, because "8 Miles High" stripped to
    # "Miles High" still reaches its item by subphrase. "16 Tons" is the case
    # that separates them - stripped it leaves one word, below
    # fuzzy_title_eq's two-word floor, so an eager strip loses an item that
    # matches exactly today.
    c = canon(("1", "16 Tons", True), ("1", "Bertha", True),
              ("1", "Sugaree", True), ("1", "Loser", False))
    r = align([tr(1, "16 Tons"), tr(2, "02 Bertha"), tr(3, "03 Sugaree"),
               tr(4, "04 Loser")], c)
    assert r.matched == [True, True, True, True]


def test_the_strip_needs_an_enumerated_tape():
    # One prefix-shaped title is a song, not a numbering scheme, so "02 Bertha"
    # stays unmatched here even though stripping it would match. Pins the >=3
    # tape gate, which the three tests above also leave untested.
    c = canon(("1", "Bertha", True), ("1", "Sugaree", True), ("1", "Loser", False))
    r = align([tr(1, "02 Bertha"), tr(2, "Sugaree"), tr(3, "Loser")], c)
    assert r.matched == [False, True, True]


def test_the_prefix_shape_declines_long_numbers():
    # Asserted against the regex DIRECTLY, deliberately. No behavioural test can
    # pin the 1-2 digit cap: the miss-path ordering already saves any real
    # numeric title whose item is in the window, so widening the cap to \d{1,4}
    # leaves every other test in this file green (measured). Without this test
    # the cap - which is what protects "1952 Vincent Black Lightning" - ships
    # with no coverage at all.
    from llama.structure import _TRACK_PREFIX
    assert _TRACK_PREFIX.match("1952 Vincent Black Lightning") is None
    assert _TRACK_PREFIX.match("100 Years") is None
    assert _TRACK_PREFIX.match("1-800 Suicide") is None
    assert _TRACK_PREFIX.match("2112") is None
    # ... while still firing on a genuine 1-2 digit index or an mm:ss duration.
    assert _TRACK_PREFIX.match("18 Lost My Driving Wheel")
    assert _TRACK_PREFIX.match("[05:20] KC Jones")


# --- Rule C: a duration glued onto the ITEM title ("Althea  [8:40]",
# "Arguement (4:54)") - the mirror image of the _TRACK_PREFIX fallback above.
# That one strips a leading index/duration off the TRACK title; this one
# strips a trailing duration off the ITEM title. Both are miss-path-only
# fallbacks over the same cascade and neither touches the other's side.

def test_duration_glued_to_item_title_matches_square_bracket_style():
    # No `r.sets` assertion here, deliberately: both items sit in set "1", the
    # same value an unmatched track's set falls back to, so a `sets` check
    # would still pass under the mutation this test exists to catch (see
    # M-1 in the phase-3 fix log) and add no discriminating power.
    c = canon(("1", "Althea  [8:40]", True), ("1", "Bertha", False))
    r = align([tr(1, "Althea"), tr(2, "Bertha")], c)
    assert r.matched == [True, True]


def test_duration_glued_to_item_title_matches_paren_style():
    c = canon(("1", "Arguement (4:54)", True), ("1", "Bertha", False))
    r = align([tr(1, "Arguement"), tr(2, "Bertha")], c)
    assert r.matched == [True, True]


def test_duration_glued_to_item_title_matches_bare_style():
    # Single-word title, deliberately: a multi-word title with a bare
    # trailing duration ("Eyes Of The World 11:20") is already rescued by the
    # existing subphrase fallback in `fuzzy_title_eq` (the unstripped item
    # normalizes to "eyes of the world 11 20", and the track's "eyes of the
    # world" is a contiguous subphrase of that) - so it would pass even
    # without this fallback and wouldn't actually pin it. `fuzzy_title_eq`'s
    # subphrase check requires >= 2 words on the shorter side, so a
    # single-word title like "Feedback" gets no such rescue and genuinely
    # needs the new fallback.
    c = canon(("1", "Feedback 3:15", True), ("1", "Bertha", False))
    r = align([tr(1, "Feedback"), tr(2, "Bertha")], c)
    assert r.matched == [True, True]


def test_duration_strip_never_touches_the_stored_item_title():
    # Matching-layer only: `SetlistItem.title` feeds the briefing and the
    # manifest and must survive `align()` byte-for-byte, glued duration and
    # all.
    c = canon(("1", "Althea  [8:40]", True), ("1", "Bertha", False))
    align([tr(1, "Althea"), tr(2, "Bertha")], c)
    assert c.items[0].title == "Althea  [8:40]"


def test_glued_duration_strip_is_a_miss_path_fallback_not_an_eager_rewrite():
    # "5:15" (The Who) is a real song title shaped exactly like a glued
    # duration. It must match its own item unstripped; an eager strip would
    # empty the item's norm before the plain compare ever runs and lose it.
    #
    # No `r.sets` assertion, deliberately (see the same note on
    # test_duration_glued_to_item_title_matches_square_bracket_style above) -
    # both items sit in set "1", which is also the unmatched-track fallback,
    # so it wouldn't discriminate the eager-strip mutation this test exists
    # to catch.
    c = canon(("1", "5:15", True), ("1", "Bertha", False))
    r = align([tr(1, "5:15"), tr(2, "Bertha")], c)
    assert r.matched == [True, True]


def test_a_mid_title_duration_is_never_stripped():
    # The bracket sits mid-title, not at the end, so it must never be
    # stripped - an unanchored strip would corrupt this item down to
    # "terrapin station suite", which collides with an unrelated track that
    # legitimately has no duration in it at all.
    c = canon(("1", "Terrapin Station [8:40] Suite", True), ("1", "Bertha", False))
    r = align([tr(1, "Terrapin Station Suite"), tr(2, "Bertha")], c)
    assert r.matched == [False, True]


def test_an_emptied_strip_never_becomes_a_wildcard():
    # "#  [9:41]" is a footnote marker glued to a duration - stripping the
    # duration leaves nothing but the marker's own junk, which normalizes to
    # "". An empty string is not evidence of anything, so it must never sit
    # in `stripped_norms` where `_window_match`'s exact-equality pass would
    # match it against ANY track whose own norm is also "" (here, the junk
    # track "..."). Left unguarded, that spurious match consumes the window
    # position, strands the real "Jack Straw" item, and drags the real Jack
    # Straw track into the wrong (encore) set.
    c = canon(("1", "Bertha", True), ("1", "Jack Straw", True),
              ("encore", "#  [9:41]", False))
    r = align([tr(1, "Bertha"), tr(2, "..."), tr(3, "Jack Straw")], c)
    assert r.matched == [True, False, True]
    assert r.sets == ["1", "1", "1"]


# --- Tail-exhaustion guard ---------------------------------------------------
# See TAIL_GUARD_ITEMS/_tail_guard_declines in structure.py for the mechanism
# (now three axes: how near the item list's end, how many tracks remain, how
# far the candidate skipped ahead to get there). These tests were written
# first and run against two mutants of `_tail_guard_declines` - `lambda *a:
# False` (never decline: "under-eager") and `lambda *a: True` (always
# decline: "over-eager") - to confirm each one actually depends on the
# guard, in the direction that matters for what it asserts. See the fix-1
# section of task-1-report.md for the full per-test two-mutant table.
#
# Fix-round-1 addendum, condition C: an outcome-only assertion on an
# align()-level guard test is indistinguishable from a fixture that never
# reaches the guard at all - exactly the failure the review caught (two
# tests, zero predicate calls, that looked green and meaningful). Every
# align()-level test below therefore spies on `_tail_guard_declines` via
# `_GuardSpy` and asserts on the recorded calls, not merely on the resulting
# labels - including the negative ones, where the assertion is "reached the
# guard, AND the guard correctly returned False". Pure predicate-unit tests
# above (item/tracks/skip axis boundaries etc.) call `_tail_guard_declines`
# directly as their own assertion subject - the call IS the test, so a spy
# wrapper around it would be circular and is intentionally not used there.


class _GuardSpy:
    """Records every call to `structure._tail_guard_declines` as
    `(args, result)` while active, via `pytest.MonkeyPatch` wrapping the real
    function (never replacing its logic). Lets an align()-level test assert
    the guard was genuinely CONSULTED - and what it decided - rather than
    only that a particular outcome resulted, which a bypassed guard could
    also produce (review finding 2 / fix-round-1 addendum condition C)."""

    def __init__(self):
        self.calls: list[tuple[tuple, bool]] = []

    def __enter__(self):
        real = structure._tail_guard_declines

        def spy(*args):
            result = real(*args)
            self.calls.append((args, result))
            return result

        self._mp = pytest.MonkeyPatch()
        self._mp.setattr(structure, "_tail_guard_declines", spy)
        return self

    def __exit__(self, *exc_info):
        self._mp.undo()
        return False

    @property
    def declined(self):
        return [c for c in self.calls if c[1] is True]

    @property
    def allowed(self):
        return [c for c in self.calls if c[1] is False]


def test_tail_guard_declines_hit_index_is_zero_based_and_inclusive():
    """hit and track_index are 0-based, and n_items-hit / n_tracks-track_index
    are both INCLUSIVE of the position itself, not just what comes after it.
    Landing on the literal last item (hit == n_items - 1) counts as "1 item
    remaining", not 0 - clears the item axis for any TAIL_GUARD_ITEMS >= 1.
    Value-agnostic (review finding 6): derives its "not enough tracks" case
    directly from TAIL_GUARD_TRACKS_REMAINING rather than a hardcoded
    number, so it keeps holding whatever Task 3 measures the constant to."""
    n_items, n_tracks = 10, 1000
    skip = TAIL_GUARD_MAX_SKIP + 1  # comfortably clears the skip axis too
    assert _tail_guard_declines(9, n_items, 0, n_tracks, skip) is True
    short_of_threshold = n_tracks - (TAIL_GUARD_TRACKS_REMAINING - 1)
    assert _tail_guard_declines(9, n_items, short_of_threshold, n_tracks, skip) is False


def test_tail_guard_declines_item_axis_boundary():
    # Holds the tracks and skip axes safely inside their firing zones
    # throughout, so only the item axis is under test.
    n_items, n_tracks, track_index = 10, 20, 0
    skip = TAIL_GUARD_MAX_SKIP + 1
    at_threshold = n_items - TAIL_GUARD_ITEMS       # n_items - hit == TAIL_GUARD_ITEMS exactly
    one_outside = at_threshold - 1                  # one item further from the end
    assert _tail_guard_declines(at_threshold, n_items, track_index, n_tracks, skip) is True
    assert _tail_guard_declines(one_outside, n_items, track_index, n_tracks, skip) is False


def test_tail_guard_declines_tracks_axis_boundary():
    # Holds the item and skip axes deep in their firing zones throughout, so
    # only the tracks-remaining axis is under test.
    n_items, hit, n_tracks = 10, 9, 20
    skip = TAIL_GUARD_MAX_SKIP + 1
    at_threshold = n_tracks - TAIL_GUARD_TRACKS_REMAINING  # remaining == TAIL_GUARD_TRACKS_REMAINING exactly
    one_outside = at_threshold + 1                          # one track closer to the end
    assert _tail_guard_declines(hit, n_items, at_threshold, n_tracks, skip) is True
    assert _tail_guard_declines(hit, n_items, one_outside, n_tracks, skip) is False


def test_tail_guard_declines_skip_axis_boundary():
    """Holds the item and tracks axes deep in their firing zones throughout,
    so only the skip axis is under test. Pins the convention from the module
    comment above TAIL_GUARD_MAX_SKIP: skip must be STRICTLY greater than
    TAIL_GUARD_MAX_SKIP to decline - at exactly the threshold the guard
    still lets the match through. This strictness is also what makes la=3
    structurally inert for any TAIL_GUARD_MAX_SKIP >= 3 (the shipped value of
    6 satisfies this with margin - la=3 was the shipped default before Task
    4's bump to 8, at which the relationship no longer holds) - see
    test_tail_guard_inert_whenever_lookahead_le_max_skip."""
    n_items, hit, n_tracks, track_index = 10, 9, 20, 0
    at_threshold = TAIL_GUARD_MAX_SKIP        # skip == TAIL_GUARD_MAX_SKIP exactly: not enough
    one_more = at_threshold + 1               # one item further skipped: enough
    assert _tail_guard_declines(hit, n_items, track_index, n_tracks, at_threshold) is False
    assert _tail_guard_declines(hit, n_items, track_index, n_tracks, one_more) is True


def test_tail_guard_declines_requires_all_three_conditions():
    """Value-agnostic (review finding F7): `almost_done` is derived from
    TAIL_GUARD_TRACKS_REMAINING, the same technique
    test_tail_guard_declines_hit_index_is_zero_based_and_inclusive uses,
    rather than a hardcoded `n_tracks - 1` - which only leaves the tracks
    axis correctly UNCLEARED (remaining < TRACKS_REMAINING) for
    TAIL_GUARD_TRACKS_REMAINING > 1, and silently flips the second assertion
    below to the wrong outcome at TRACKS_REMAINING <= 1."""
    n_items, n_tracks = 10, 20
    tail_hit, non_tail_hit = n_items - 1, 0
    plenty_remaining = 0
    almost_done = n_tracks - (TAIL_GUARD_TRACKS_REMAINING - 1)
    big_skip, no_skip = TAIL_GUARD_MAX_SKIP + 1, 0
    # item + tracks clear their bars, but nothing was skipped.
    assert _tail_guard_declines(tail_hit, n_items, plenty_remaining, n_tracks, no_skip) is False
    # item + skip clear their bars, but too few tracks remain.
    assert _tail_guard_declines(tail_hit, n_items, almost_done, n_tracks, big_skip) is False
    # tracks + skip clear their bars, but the hit isn't near the end.
    assert _tail_guard_declines(non_tail_hit, n_items, plenty_remaining, n_tracks, big_skip) is False
    # all three together decline.
    assert _tail_guard_declines(tail_hit, n_items, plenty_remaining, n_tracks, big_skip) is True


def test_tail_guard_inert_whenever_lookahead_le_max_skip():
    """Direct, fixture-free proof of design gate 2's general RELATIONSHIP
    (review finding 1/4, fix-round-1 addendum condition A): state the
    relationship itself, not just "we tried some particular lookahead and
    nothing changed".

    Task 4 re-scoped this test: it used to read `align`'s shipped default
    off its real signature and assert inertness THERE, back when the
    shipped default (3) satisfied `TAIL_GUARD_MAX_SKIP >= lookahead`. Task 4
    bumped the shipped default to 8 specifically so the guard becomes
    REACHABLE in production for the first time (`TAIL_GUARD_MAX_SKIP=6 <
    8`) - that is the entire point of landing the guard, so an assertion of
    inertness AT the shipped default would now be FALSE by design, not a
    regression to catch. The invariant that is actually, permanently true -
    independent of whatever `align`'s current default happens to be - is
    that the guard cannot fire for ANY lookahead `L <= TAIL_GUARD_MAX_SKIP`
    (which includes the pre-bump default of 3). This test sweeps that whole
    range directly instead of reading off `align`'s signature.

    `align`'s search window bound is computed by `_window_hi` - CALLED
    below, not a copied expression, so this test breaks loudly if that
    arithmetic ever changes (fix-round-2, condition A: the fix-round-1
    version mirrored the formula in its own body instead, which cannot
    break when the original changes - measured: widening `_window_hi` to
    `j + 2 + lookahead` left that version, and the whole guard subset and
    full suite, green; re-verified after this re-scoping - see the Task 4
    report). `_window_hi(j, L, huge) - 1 == j + L`, so the largest possible
    skip at lookahead=L is exactly L.

    Given that, `TAIL_GUARD_MAX_SKIP >= lookahead` makes the skip axis
    UNREACHABLE at that lookahead - not an empirical property of some
    corpus, a structural one of the arithmetic itself. For each lookahead in
    the swept range this test derives the bound from the window formula and
    checks every skip that lookahead can actually produce, with the other
    two axes held maximally in their firing zones so only the skip axis is
    left to save the match. A final boundary check one lookahead past
    `TAIL_GUARD_MAX_SKIP` confirms the relationship is tight, not merely
    "small lookahead never happens to trigger it": that boundary IS the
    shipped default's actual regime (8 > 6)."""
    n_items, n_tracks = 10, 100
    for lookahead in range(0, TAIL_GUARD_MAX_SKIP + 1):
        j = 0  # arbitrary - the relationship holds for any j
        hi = _window_hi(j, lookahead, 10 ** 9)  # the SAME function align() calls, not a copy
        max_reachable_skip = (hi - 1) - j
        assert max_reachable_skip == lookahead, (
            "window arithmetic diverged from the stated relationship at "
            f"lookahead={lookahead} - the sanity check that keeps this test "
            "coupled to _window_hi's real formula"
        )
        for skip in range(0, max_reachable_skip + 1):
            assert _tail_guard_declines(n_items - 1, n_items, 0, n_tracks, skip) is False, (
                f"guard fired at lookahead={lookahead}, skip={skip}, even though "
                f"TAIL_GUARD_MAX_SKIP={TAIL_GUARD_MAX_SKIP} >= lookahead should make it inert"
            )

    # Boundary: one lookahead past TAIL_GUARD_MAX_SKIP, the largest reachable
    # skip clears the strict `>` bar and the guard DOES fire. This is the
    # shipped default's own regime (lookahead=8 > TAIL_GUARD_MAX_SKIP=6).
    boundary_lookahead = TAIL_GUARD_MAX_SKIP + 1
    hi = _window_hi(0, boundary_lookahead, 10 ** 9)
    boundary_skip = hi - 1
    assert _tail_guard_declines(n_items - 1, n_items, 0, n_tracks, boundary_skip) is True, (
        "the guard should be reachable one lookahead past TAIL_GUARD_MAX_SKIP "
        "- if this fails, the relationship swept above is not tight"
    )


def test_align_window_bound_reachability_is_pinned_through_align():
    """M10 (final review F4, both reviewers; mid-wave design-author addendum:
    the probe must assert BOTH directions, not just one). The test above
    calls `_window_hi` directly, so it is coupled to the HELPER, not to
    `align()` - an inline bound in `align` that silently diverges from
    `_window_hi`, in EITHER direction, passes the entire suite including
    that test. Measured: `align`'s call site changed to
    `min(j + 2 + lookahead, len(items))` (WIDER) passes the full 1334-test
    suite; changed to `min(j + lookahead, len(items))` (NARROWER) also
    passes it - and the narrower case is a genuine behavior regression (a
    legitimate match at the window edge becomes permanently unreachable, at
    every lookahead), unnoticed by any of the 1334, including the ones that
    predate this branch - this is a pre-existing hole in test coverage, not
    one dug by this branch.

    This probe pins `align`'s ACTUAL reachable window from OUTSIDE, through
    public behavior, with no formula mirrored in the test body: a canonical
    setlist where the only possible match for the recording's single track
    sits exactly `L` items past the walk pointer (`skip == L`, this file's
    own convention). Both directions are asserted, and each is required to
    catch a different mutant: a NARROWER inline bound fails the "found at
    lookahead=L" half; a WIDER one fails the "not found at lookahead=L-1"
    half - a probe carrying only one half would leave the other mutant
    undetected.

    A single track can never clear the tracks axis (`n_tracks -
    track_index` is 1, under any realistic TAIL_GUARD_TRACKS_REMAINING), so
    `_tail_guard_declines` cannot fire here regardless of `L` - this probe
    measures `_window_hi`'s arithmetic AS USED BY `align`, deliberately
    decoupled from the guard's own decision, not entangled with it.

    Keep the existing `_window_hi`-calling structural test above alongside
    this one - one pins the expression, this one pins the consequence, and
    only this one survives a refactor that routes `align` around
    `_window_hi` while leaving `_window_hi` itself untouched and correct."""
    L = 5
    c = canon(*[("1", f"Skip{i}", False) for i in range(L)], ("1", "Target", False))
    tracks = [tr(1, "Target")]

    r_at_l = align(tracks, c, lookahead=L)
    assert r_at_l.matched == [True], "a match exactly L items ahead must be found at lookahead=L"
    assert r_at_l.sets == ["1"]

    r_at_l_minus_1 = align(tracks, c, lookahead=L - 1)
    assert r_at_l_minus_1.matched == [False], (
        "that same match must NOT be reachable at lookahead=L-1 - if it is, "
        "the window bound is wider than lookahead promises"
    )


def test_tail_guard_never_declines_a_legitimate_one_item_skip_at_shipped_la3():
    """Review finding 1/2. A real closer reached by a genuine 1-item skip -
    the ordinary reason lookahead exists at all is a song that isn't on THIS
    particular tape - must not be declined, even though the item and tracks
    axes alone (the pre-fix, two-axis formula) were both satisfied. Modeled
    on the reviewer's Probe A: 10 canonical items, the recording is missing
    item 8 (a song cut from the tape), the real closer is item 9, and two
    trailing filler tracks (crowd noise, tuning) follow it - present in the
    list `align` walks, since `is_filler`/`_songish_coverage` exist
    precisely to tolerate them there.

    Unlike the sequential-ending shapes elsewhere in this file, this one is
    PROVEN to actually reach `_tail_guard_declines` (review finding 2: two
    earlier tests never called it, because every match in them was a
    same-position match short-circuited by the caller's `hit > j` gate
    before the predicate was ever consulted) - the closer here is a genuine
    1-item skip (`hit == j + 1`), so the gate lets the call through, and
    this test spies on it (fix-round-1 addendum condition C) to prove that
    AND that the guard, having been reached, correctly returned False -
    rather than merely asserting a green vector a bypassed guard would also
    produce."""
    c = canon(
        ("1", "Song A", False), ("1", "Song B", False),
        ("1", "Song C", False), ("1", "Song D", False),
        ("2", "Song E", False), ("2", "Song F", False),
        ("2", "Song G", False), ("2", "Song H", False),
        ("2", "Song I", False),   # NOT on this tape - the cut song
        ("encore", "Song J", False),
    )
    tracks = [
        tr(1, "Song A"), tr(2, "Song B"), tr(3, "Song C"), tr(4, "Song D"),
        tr(5, "Song E"), tr(6, "Song F"), tr(7, "Song G"), tr(8, "Song H"),
        tr(9, "Song J"),           # the real closer - "Song I" isn't on this tape
        tr(10, "Crowd Noise"), tr(11, "Tuning"),
    ]
    with _GuardSpy() as spy:
        r = align(tracks, c)  # shipped default lookahead=8

    assert spy.calls, "the guard predicate was never consulted - this test proves nothing"
    assert spy.allowed and not spy.declined  # reached the guard, which correctly did not fire
    assert r.matched[8] is True
    assert r.sets[8] == "encore"
    assert r.sets[9:] == ["encore", "encore"]


def test_tail_guard_declines_a_mid_tape_match_on_the_encore_song():
    """Constructed shape of the measured defect (gd85-04-06, gd91-03-28): the
    encore song appears as a FILE mid-tape (a rip/filename-ordering
    artifact). At a wide lookahead the far-ahead match lands on the true
    encore item at the very end of the canonical list, which - unguarded -
    exhausts `j` and wrongly drags every later, otherwise-correct track into
    "encore".

    Sized off TAIL_GUARD_TRACKS_REMAINING and TAIL_GUARD_MAX_SKIP (review
    finding 5), not a hardcoded track count, so it keeps exercising the
    tracks axis regardless of what Task 3 measures the constants to be -
    the original fixed-9-track version only held for
    TAIL_GUARD_TRACKS_REMAINING <= 5. `lookahead` is likewise sized off the
    padding so the window always reaches the tail item."""
    pad = TAIL_GUARD_TRACKS_REMAINING + TAIL_GUARD_MAX_SKIP + 2  # tail songs after the artifact
    preamble = [f"Preamble {i}" for i in range(4)]
    tail_songs = [f"Tail Song {i}" for i in range(pad)]
    c = canon(
        *[("1", t, False) for t in preamble],
        *[("2", t, False) for t in tail_songs],
        ("encore", "Casey Jones", False),
    )
    tracks = [tr(i + 1, t) for i, t in enumerate(preamble)]
    tracks.append(tr(len(tracks) + 1, "Casey Jones"))  # rip artifact: encore song mid-tape
    tracks += [tr(len(tracks) + 1 + i, t) for i, t in enumerate(tail_songs)]

    with _GuardSpy() as spy:
        r = align(tracks, c, lookahead=pad + 4)

    assert spy.declined, "the guard predicate was never consulted to decline anything"
    artifact_pos = len(preamble)
    assert r.matched[artifact_pos] is False           # declined: contained, single-track miss
    assert r.sets[artifact_pos] == "1"                # inherits the preamble's set, not "encore"
    assert r.matched[artifact_pos + 1:] == [True] * pad
    assert r.sets[artifact_pos + 1:] == ["2"] * pad    # tail NOT exhausted


def test_legitimate_tail_matching_survives_the_guard():
    """The counter-case that decides the whole design (see the design
    brief): the last tracks of a tape ARE supposed to match the last
    canonical items, however far ahead the match has to reach.

    Two shapes (review finding 2): a same-position sequential ending (never
    calls the predicate at all, since the caller's `hit > j` gate
    short-circuits first - kept as the cheapest possible baseline, but by
    itself this shape is NOT evidence the guard behaves correctly, only
    that the gate does) and a true tail match reached via a big skip - sized
    off TAIL_GUARD_MAX_SKIP + 1 (final-review finding F1: a fixed 5-item gap
    only isolated the tracks axis while MAX_SKIP was 3; once Task 3 raised it
    to 6, skip=5 fell UNDER the new bar and the skip axis started saving the
    match too, silently making this shape's assertion vacuous as to which
    axis actually did it) - with only one track left, where
    TAIL_GUARD_TRACKS_REMAINING, NOT the skip axis, is what has to save it.
    The shape asserts its own isolation (`skip_recorded > TAIL_GUARD_MAX_SKIP`)
    rather than trusting a hand-picked number to stay bigger than a constant
    that can change again. The second shape proves the tracks axis is still
    load-bearing even with the skip axis in place, not made redundant by it,
    and genuinely reaches the predicate."""
    # Sequential ending - trivial, does not reach the predicate. Spied and
    # asserted explicitly (fix-round-1 addendum condition C), rather than
    # left as an implicit assumption: this shape alone is NOT evidence the
    # guard behaves correctly, only that the `hit > j` gate does.
    c = canon(("1", "A", False), ("1", "B", False), ("2", "C", False),
              ("2", "D", False), ("encore", "E", False))
    tracks = [tr(1, "A"), tr(2, "B"), tr(3, "C"), tr(4, "D"), tr(5, "E")]
    for la in (3, 8, 12):
        with _GuardSpy() as spy:
            r = align(tracks, c, lookahead=la)
        assert not spy.calls  # confirms this shape never reaches the guard at all
        assert r.matched == [True, True, True, True, True]
        assert r.sets == ["1", "1", "2", "2", "encore"]

    # Big-skip ending: only the tracks axis protects it. The missing-item run
    # is sized off TAIL_GUARD_MAX_SKIP + 1, so the resulting skip clears the
    # skip axis's own bar - the tracks axis is the only thing left standing.
    n_missing = TAIL_GUARD_MAX_SKIP + 1
    missing_rows = [("1", f"Missing {i}", False) for i in range(n_missing)]
    c2 = canon(("1", "A", False), ("1", "B", False), *missing_rows,
               ("encore", "Closer", False))
    tracks2 = [tr(1, "A"), tr(2, "B"), tr(3, "Closer")]  # the missing songs are not on this tape
    with _GuardSpy() as spy2:
        r2 = align(tracks2, c2, lookahead=n_missing)
    assert spy2.calls, "the guard predicate was never consulted - this shape proves nothing"
    assert spy2.allowed and not spy2.declined  # reached the guard; tracks axis correctly saved it
    skip_recorded = spy2.calls[0][0][4]
    assert skip_recorded > TAIL_GUARD_MAX_SKIP, (
        "this shape must clear the skip axis's own bar, so only the tracks "
        "axis is left standing between the guard and this match - if this "
        "fails, the shape has stopped isolating what it claims to isolate"
    )
    assert r2.matched == [True, True, True]
    assert r2.sets == ["1", "1", "encore"]


def test_tail_guard_decline_lets_a_later_fallback_find_an_earlier_hit():
    """Design decision: a decline is treated like an ordinary miss, not a
    terminal failure - the cascade below keeps trying and may still land a
    legitimate, non-tail hit in the same window. Here the primary compare
    exact-matches the untouched title against a TAIL duplicate of "Alpha";
    only the glued-duration miss-path fallback (which searches
    `stripped_norms`) reaches the true, non-tail item ("Alpha [5:20]"
    stripped down to "Alpha"). FAILS WITHOUT THE GUARD: the primary
    compare's tail hit is taken directly, matched[0] comes back True
    against the tail duplicate ("encore" set) instead of item 0, `j` jumps
    to the end of the item list, and the two tracks after it (which should
    cleanly match "Beta"/"Gamma") come back unmatched, inheriting the wrong
    set instead.

    Sized off TAIL_GUARD_MAX_SKIP and TAIL_GUARD_TRACKS_REMAINING
    (fix-round-2 item 3; review finding 5's technique applied here), not
    the fixed 6-item/3-track fixture fix-round-1 shipped, which only held
    for TAIL_GUARD_TRACKS_REMAINING <= 3. Decoy items push the tail
    duplicate far enough past `j` to clear the skip axis regardless of the
    constant, and padding tracks (which match nothing) clear the tracks
    axis the same way."""
    TRACKS_REM, MAX_SKIP = TAIL_GUARD_TRACKS_REMAINING, TAIL_GUARD_MAX_SKIP
    n_items = MAX_SKIP + 5   # margin of 4 over the skip bar
    decoy_count = n_items - 5
    rows = [
        ("1", "Alpha [5:20]", False), ("1", "Beta", False), ("1", "Gamma", False),
        ("1", "Delta", False),
        *[("1", f"Decoy{i}", False) for i in range(decoy_count)],
        ("encore", "Alpha", False),  # tail duplicate: hijacks the primary compare
    ]
    assert len(rows) == n_items
    c = canon(*rows)
    pad_tracks = [tr(100 + i, f"Filler{i}") for i in range(TRACKS_REM)]  # clears the tracks axis
    tracks = [tr(1, "Alpha"), tr(2, "Beta"), tr(3, "Gamma")] + pad_tracks
    with _GuardSpy() as spy:
        r = align(tracks, c, lookahead=n_items)
    assert spy.declined  # the primary compare's tail hit was genuinely reached and declined
    assert r.matched[:3] == [True, True, True]
    assert r.sets[:3] == ["1", "1", "1"]  # items 0/1/2, not the tail duplicate


def test_tail_guard_declines_a_merge_run_landing_in_the_tail():
    """The merge-run path advances `j` past ALL of a merged track's matched
    components, so the item that matters for the tail (item-axis) test is
    the LAST consumed item (`run + len(comps) - 1`), while the skip axis is
    measured from where the run STARTS (`run - j`) - two different
    questions, "how deep did it land" vs "how far did it jump". The
    canonical items between `j` and the merge target are genuinely absent
    from this tape, so the skip clears TAIL_GUARD_MAX_SKIP - a wide-open
    gap, not a 1-item skip, which is the actual measured shape. Declining
    must leave `j` untouched so those items stay available and the tracks
    that follow keep their own shot at them. FAILS WITHOUT THE GUARD: the
    merge run is taken directly (matched[2] True, sets[2] "2"), `j` jumps to
    the end of the item list, and the skipped items - which should cleanly
    match - come back unmatched instead.

    Sized off all three constants (fix-round-2 item 3; review finding 5's
    technique applied here), not the fixed 8-item/7-track fixture
    fix-round-1 shipped, which only held for TAIL_GUARD_TRACKS_REMAINING <
    6 and broke outright at TAIL_GUARD_ITEMS == 1. The merge components are
    single words ("X", "Y") rather than real song names on purpose: a
    multi-word component (the original used "China Cat Sunflower") is
    itself a valid match for the DECLINED run's single-title fallback
    compare - the whole merged track's normalized text starts with the
    first component's normalized text as a literal subphrase (see
    fuzzy_title_eq's subphrase rule) - so it can resurface as a SECOND
    guard candidate anchored at the run's START rather than its last item,
    and whether THAT candidate also gets declined depends on the constants
    in a way unrelated to what this test is about (measured: this is
    exactly what broke the original fixture at TAIL_GUARD_ITEMS == 1). A
    single-word component can never satisfy the subphrase rule
    (`_is_subphrase` requires >= 2 words on the short side), so no second
    candidate arises and the fixture stays governed by exactly the two axes
    under test."""
    ITEMS, TRACKS_REM, MAX_SKIP = TAIL_GUARD_ITEMS, TAIL_GUARD_TRACKS_REMAINING, TAIL_GUARD_MAX_SKIP
    skip = MAX_SKIP + 3                     # comfortably clears the skip axis
    skipped = [f"Skip{i}" for i in range(skip)]  # canonical items absent from the tape
    run = 2 + skip                          # merge target's start index (after A, B)
    last_item = run + 1                     # 2-component run (X, Y): the LAST consumed item
    n_items = last_item + ITEMS             # boundary: item axis clears at exactly ITEMS
    trailing = n_items - 1 - last_item

    c = canon(
        ("1", "A", False), ("1", "B", False),
        *[("1", s, False) for s in skipped],
        ("2", "X", True), ("2", "Y", False),
        *[("2", f"Trail{i}", False) for i in range(trailing)],
    )
    tracks = [
        tr(1, "A"), tr(2, "B"),
        tr(3, "X > Y"),  # merge run landing on the tail pair
        *[tr(4 + i, s) for i, s in enumerate(skipped)],
    ]
    pad = [tr(100 + i, f"Pad{i}") for i in range(TRACKS_REM)]  # clears the tracks axis with margin
    with _GuardSpy() as spy:
        r = align(tracks + pad, c, lookahead=n_items)
    assert spy.declined  # the merge run was genuinely declined
    assert r.matched[2] is False  # merge run declined - falls to the single-match miss path
    assert r.sets[2] == "1"       # inherits B's set, not "2"
    assert r.matched[3:3 + skip] == [True] * skip  # the skipped items still reachable
    assert r.sets[3:3 + skip] == ["1"] * skip      # j did not advance


def test_tail_guard_merge_run_pins_run_start_vs_last_item():
    """Condition B residual (fix-round-1 addendum / review): the merge-run
    call site must pass the LAST consumed item (`run + len(comps) - 1`) as
    the item axis and the RUN START distance (`run - j`) as the skip axis -
    two different indices, easy to accidentally swap. Both plausible swaps
    (item=run with skip measured from the last item; or only the skip axis
    swapped) survived every OTHER guard test, because the 2-component
    fixture above puts `run` and `run + len(comps) - 1` only one index
    apart - on the same side of both thresholds either way.

    This test uses a 3-component run, so `run` and the last consumed item
    (`run + 2`) are two apart, and sizes the item axis so the LAST item
    clears its bar while `run` itself - two items further from the end -
    provably does not, for ANY TAIL_GUARD_ITEMS: n_items - run =
    (n_items - last_item) + 2, and n_items - last_item is pinned at exactly
    TAIL_GUARD_ITEMS by construction, so the swapped value is always
    TAIL_GUARD_ITEMS + 2 - never <= TAIL_GUARD_ITEMS. It then asserts the
    EXACT arguments `_GuardSpy` recorded for the merge call, not just the
    align() outcome: an item-axis swap flips the outcome (item axis fails
    to clear, so the swap's guard call would return False, not True), but
    a skip-axis-only swap does not - real skip and swapped skip both clear
    TAIL_GUARD_MAX_SKIP here, so only reading the recorded argument value
    itself (not the outcome) catches it."""
    ITEMS, TRACKS_REM, MAX_SKIP = TAIL_GUARD_ITEMS, TAIL_GUARD_TRACKS_REMAINING, TAIL_GUARD_MAX_SKIP
    skip = MAX_SKIP + 1        # just clears the skip axis
    j = 2                      # pointer position when the merge track is reached (after A, B)
    run = j + skip
    fillers = [f"Filler{i}" for i in range(run - 2)]  # items between B and the run start
    last_item = run + 2        # 3-component run (X, Y, Z): the LAST consumed item
    n_items = last_item + ITEMS  # boundary: item axis clears at exactly ITEMS for last_item,
                                  # and therefore at ITEMS + 2 (never clearing) for `run` itself
    trailing = n_items - 1 - last_item

    c = canon(
        ("1", "A", False), ("1", "B", False),
        *[("1", f, False) for f in fillers],
        ("2", "X", True), ("2", "Y", True), ("2", "Z", False),
        *[("2", f"Trail{i}", False) for i in range(trailing)],
    )
    tracks = [tr(1, "A"), tr(2, "B"), tr(3, "X > Y > Z")]
    pad = [tr(100 + i, f"Pad{i}") for i in range(TRACKS_REM)]  # clears the tracks axis with margin
    with _GuardSpy() as spy:
        r = align(tracks + pad, c, lookahead=n_items)

    assert spy.calls, "the merge-run call site never reached the guard"
    args, result = spy.calls[0]
    item_idx, n_items_arg, track_pos, n_tracks_arg, recorded_skip = args
    assert item_idx == last_item, "item axis must be the LAST consumed item, not the run start"
    assert recorded_skip == skip, "skip axis must be measured from the run START, not the last item"
    assert result is True  # both axes clear at this fixture's real values - genuinely declined
    assert r.matched[2] is False
    assert r.sets[2] == "1"


# --- F3 (final review, both reviewers): call-site coverage -----------------
# Of the five `_tail_guard_declines` call sites in `align`, three already had
# a fixture that drives a genuine decline through them (the primary compare,
# the merge run, and the glued-duration fallback - all covered above).
# Measured: short-circuiting the guard check at either of the remaining two
# sites - the Space/Drums -> "jam" fallback, or the enumerated-tape
# track-prefix-strip fallback - left the FULL 1334-test suite green, because
# no fixture anywhere ever drove a live decline through them. That is the
# same blind spot the branch's own `_GuardSpy` standard exists to prevent,
# one level up: the standard catches a test that never reaches a guard it
# claims to test; a call site with no test at all is the limiting case the
# standard cannot see, because there is no fixture to put the spy in. The two
# tests below close it, verified by mutation (see the fixwave report for the
# executed `if False:` short-circuit at each site, run with
# PYTHONDONTWRITEBYTECODE=1 and a cleared __pycache__, restored after).


def test_tail_guard_declines_a_jam_fallback_match_in_the_tail():
    """Call site structure.py (search "Setlists often write \"Jam\""). A
    preamble of two matched tracks puts the walk pointer at j=2; a skip-gap
    of TAIL_GUARD_MAX_SKIP + 1 canonical items absent from the tape clears
    the skip axis; the canonical "Jam" item sits exactly TAIL_GUARD_ITEMS
    items from the end, clearing the item axis; and enough padding tracks
    after the Drums/Space pair leave exactly TAIL_GUARD_TRACKS_REMAINING
    tracks remaining, clearing the tracks axis too - all three, so the guard
    genuinely declines rather than merely being reached.

    The Space track's PRIMARY compare must miss first (no canonical item is
    literally titled "Space" here) so it is the jam-fallback specifically -
    not the primary compare, already covered elsewhere - that reaches the
    guard. `spy.declined` proves that, rather than assuming it from the
    fixture's shape."""
    ITEMS, TRACKS_REM, MAX_SKIP = TAIL_GUARD_ITEMS, TAIL_GUARD_TRACKS_REMAINING, TAIL_GUARD_MAX_SKIP
    skip = MAX_SKIP + 1                      # clears the skip axis
    skipped = [f"Skip{i}" for i in range(skip)]  # canonical items absent from the tape
    hit = 2 + skip                           # index of the "Jam" canonical item
    n_items = hit + ITEMS                    # boundary: item axis clears at exactly ITEMS remaining
    trailing = n_items - 1 - hit
    c = canon(
        ("1", "A", False), ("1", "B", False),
        *[("1", s, False) for s in skipped],
        ("2", "Jam", False),
        *[("2", f"Trail{i}", False) for i in range(trailing)],
    )
    pad = [tr(100 + i, f"Filler{i}") for i in range(TRACKS_REM - 1)]  # clears the tracks axis exactly
    tracks = [tr(1, "A"), tr(2, "B"), tr(3, "Drums"), tr(4, "Space")] + pad
    with _GuardSpy() as spy:
        r = align(tracks, c, lookahead=n_items)
    assert spy.declined, "the jam fallback's guard check was never reached - this test proves nothing"
    assert r.matched[3] is False   # declined: contained, single-track miss
    assert r.sets[3] == "1"        # inherits the preceding set, not "2" (the Jam item's set)


def test_tail_guard_declines_an_enumerated_prefix_fallback_match_in_the_tail():
    """Call site structure.py (the `_TRACK_PREFIX`-strip fallback, reached
    only when `_is_enumerated_tape` is True and the unstripped compare has
    already missed). Three numeric-prefixed tracks (clearing
    `_ENUMERATED_MIN`) so the tape reads as enumerated; the third strips to a
    bare title matching a canonical item TAIL_GUARD_MAX_SKIP + 1 items past
    the pointer (clears the skip axis), positioned TAIL_GUARD_ITEMS items
    from the end (clears the item axis), with enough padding tracks after it
    to leave exactly TAIL_GUARD_TRACKS_REMAINING tracks remaining (clears
    the tracks axis).

    The unstripped PRIMARY compare must miss first: "09 Closer" is two
    normalized words against the canonical one-word "Closer", so
    `_is_subphrase`'s two-word floor on the short side never fires (the same
    property the module comment notes for "16 Tons" vs "8 Miles High") and
    the match is only found once the enumerated fallback strips the leading
    "09 ". `spy.declined` proves that path was the one reached, rather than
    assuming it from the fixture's shape."""
    ITEMS, TRACKS_REM, MAX_SKIP = TAIL_GUARD_ITEMS, TAIL_GUARD_TRACKS_REMAINING, TAIL_GUARD_MAX_SKIP
    skip = MAX_SKIP + 1                      # clears the skip axis
    skipped = [f"Skip{i}" for i in range(skip)]  # canonical items absent from the tape
    hit = 2 + skip                           # index of the "Closer" canonical item
    n_items = hit + ITEMS                    # boundary: item axis clears at exactly ITEMS remaining
    trailing = n_items - 1 - hit
    c = canon(
        ("1", "A", False), ("1", "B", False),
        *[("1", s, False) for s in skipped],
        ("2", "Closer", False),
        *[("2", f"Trail{i}", False) for i in range(trailing)],
    )
    pad = [tr(100 + i, f"{100 + i} Filler{i}") for i in range(TRACKS_REM - 1)]  # clears tracks axis
    tracks = [tr(1, "01 A"), tr(2, "02 B"), tr(3, "09 Closer")] + pad
    with _GuardSpy() as spy:
        r = align(tracks, c, lookahead=n_items)
    assert spy.declined, (
        "the enumerated-prefix fallback's guard check was never reached - this test proves nothing"
    )
    assert r.matched[2] is False   # declined: contained, single-track miss
    assert r.sets[2] == "1"        # inherits the preceding set, not "2" (the Closer item's set)
