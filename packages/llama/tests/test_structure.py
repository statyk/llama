from llama.models import ParsedSetlist, SetlistItem, SourcedParse, Track
from llama.songs import normalize_song
from llama.structure import align, blend_segues, from_setlistfm, is_filler, norm_title, rank_parses, structure_guard


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


def test_align_matches_a_leading_encore_marker_item_characterization():
    # CHARACTERIZES A KNOWN PARSER DEFECT - this is NOT a specification of
    # desired behavior. `setlist.py`'s `_INLINE_MARKER` requires a set/encore
    # marker to carry a MANDATORY digit ("e\d") to split mid-line, so a bare
    # mid-line "E:" never triggers a split. Contrast `_ENCORE_LINE`, which
    # uses "e\d?" (digit optional) and so DOES recognize a bare "E:" at line
    # start. A description like "...Sugar Magnolia; E: Goin' Down the
    # Road..." therefore leaves the encore song's canonical item stamped with
    # the PRECEDING numbered set, title still carrying the "E: " prefix (per
    # the project owner, bare-"E:" items of this shape occur in the corpus:
    # 18 shows for "Brokedown Palace", 11 for "Johnny B. Goode", 7 for
    # "Casey Jones", 7 for "Black Muddy River").
    #
    # Task 4 made align()'s item side compare through `fuzzy_norm_title` (which
    # strips "E:"/"Encore:" via `_STRUCTURE_PREFIX`) instead of the bare
    # `normalize_song`-based `SetlistItem.normalized`. The track side was
    # already prefix-stripped, so a canonical item literally titled
    # "E: Baby Blue" can now match a track titled "Baby Blue" - previously it
    # could not match at all. The set label the track receives is whatever the
    # (possibly wrong) item carries, here "1", not "encore".
    #
    # This is accepted for phase 2 and is not fixed here. Fixing
    # `_INLINE_MARKER` in `setlist.py` (phase 3) to also split on a bare mid-
    # line "E:" is expected to CHANGE the set-label assertion below.
    #
    # Built by hand instead of via `canon()`: `canon()` sets `normalized=
    # norm_title(t)`, which already strips the "E:" prefix, so a canonical
    # item built that way never actually carries the "E: " prefix in
    # `.normalized` and this test would pass even against the pre-branch
    # matcher - proving nothing about the defect above. Production builds
    # `SetlistItem.normalized` as the UNSTRIPPED `normalize_song(title)`
    # (`setlist.py:114`, `structure.py`'s `from_setlistfm:217`), so this test
    # reproduces that here to genuinely exercise the defect.
    c = ParsedSetlist(items=[
        SetlistItem(title="Sugar Magnolia", normalized=normalize_song("Sugar Magnolia"),
                    set="1", segue=False),
        SetlistItem(title="E: Baby Blue", normalized=normalize_song("E: Baby Blue"),
                    set="1", segue=False),
    ], confidence="high")
    r = align([tr(1, "Sugar Magnolia"), tr(2, "Baby Blue")], c)
    assert r.matched == [True, True]
    assert r.sets == ["1", "1"]  # NOT "encore" - see comment above


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
