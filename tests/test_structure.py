from llama.models import ParsedSetlist, SetlistItem, SourcedParse, Track
from llama.structure import align, blend_segues, from_setlistfm, norm_title, rank_parses, structure_guard


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
    assert r.coverage == 0.5
    assert r.segues[1] is False


def test_align_first_track_unmatched_defaults_to_set_1():
    c = canon(("1", "B", False))
    r = align([tr(1, "Intro"), tr(2, "B")], c)
    assert r.sets == ["1", "1"]


def test_align_empty_inputs():
    r = align([], canon(("1", "A", False)))
    assert r.sets == [] and r.coverage == 0.0
    r = align([tr(1, "A")], ParsedSetlist())
    assert r.sets == ["1"] and r.coverage == 0.0


def _tracks(n, dur=300.0):
    return [Track(index=i + 1, set="1", title=f"S{i}", filename=f"t{i}.mp3",
                  duration_sec=dur, segue=False, title_source="tags") for i in range(n)]


def test_guard_fires_on_long_duration_no_breaks():
    assert structure_guard(_tracks(10, dur=700.0), []) == "single-set structure for a long show"


def test_guard_fires_on_track_count_even_without_durations():
    assert structure_guard(_tracks(20, dur=None), []) == "single-set structure for a long show"


def test_guard_silent_on_short_single_set_and_any_multiset():
    assert structure_guard(_tracks(8, dur=300.0), []) is None          # 40 min, 8 tracks
    assert structure_guard(_tracks(30, dur=700.0), [11]) is None       # has a break


def test_guard_respects_thresholds():
    assert structure_guard(_tracks(10, dur=700.0), [], min_minutes=200) is None
    assert structure_guard(_tracks(10, dur=None), [], min_tracks=10) is not None


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
