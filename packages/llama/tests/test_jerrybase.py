import csv
from importlib import resources

from llama import jerrybase
from llama.models import JerrybaseEvent


def test_vendored_csv_is_present_and_well_formed():
    path = resources.files("llama.data").joinpath("set_breaks.csv")
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 18074
    assert list(rows[0].keys()) == [
        "date", "artist", "event_id", "venue", "city", "state", "show_set",
        "time", "song", "song_n", "isong", "next_set", "Nevents", "ievent",
        "break_length",
    ]
    # A known row survives quoted-comma parsing intact.
    cornell = [r for r in rows if r["date"] == "1977-05-08" and r["artist"] == "GratefulDead"]
    assert any(r["venue"] == "Barton Hall, Cornell University" for r in cornell)


def test_artist_key_alphanumeric_only():
    assert jerrybase.artist_key("Grateful Dead") == "gratefuldead"
    assert jerrybase.artist_key("Phil Lesh and Friends") == "philleshandfriends"
    # llama string and CSV token collapse to the same key.
    assert jerrybase.artist_key("Phil Lesh and Friends") == jerrybase.artist_key("PhilLeshAndFriends")


def test_normalize_set_label_maps_conventions():
    n = jerrybase.normalize_set_label
    assert n("Set 1") == "1"
    assert n("Set One") == "1"
    assert n("Set I") == "1"
    assert n("Set II") == "2"
    assert n("Set III") == "3"
    assert n("Set 3") == "3"
    assert n("Show") == "1"
    assert n("Set") == "1"
    assert n("Encore") == "encore"
    assert n("Encore 1") == "encore"
    assert n("Encore 2") == "encore"
    assert n("Soundcheck") is None
    assert n("") is None


def _row(**kw):
    base = {"date": "1999-09-09", "artist": "TestBand", "event_id": "1",
            "venue": "V", "city": "C", "state": "ST", "show_set": "Set 1",
            "time": "", "song": "X", "song_n": "1", "isong": "0",
            "next_set": "", "Nevents": "1", "ievent": "1", "break_length": "long"}
    base.update(kw)
    return base


def test_build_index_song_count_deltas_and_first_none():
    rows = [
        _row(show_set="Set 1", song="A", isong="5"),
        _row(show_set="Set 2", song="B", isong="15"),
        _row(show_set="Set 3", song="C", isong="22"),
    ]
    index, skipped = jerrybase.build_index(rows)
    assert skipped == 0
    events = index[(jerrybase.artist_key("TestBand"), "1999-09-09")]
    assert len(events) == 1
    sets = events[0].sets
    assert [s.name for s in sets] == ["1", "2", "3"]
    assert [s.closer for s in sets] == ["A", "B", "C"]
    assert [s.song_count for s in sets] == [None, 10, 7]


def test_build_index_skips_malformed_rows():
    rows = [
        _row(show_set="Set 1", song="A", isong="5"),
        _row(show_set="Medical Emergency", song="B", isong="6"),  # unmappable label
        _row(show_set="Set 2", song="C", isong="not-an-int"),     # bad isong
    ]
    index, skipped = jerrybase.build_index(rows)
    assert skipped == 2
    events = index[(jerrybase.artist_key("TestBand"), "1999-09-09")]
    assert [s.name for s in events[0].sets] == ["1"]


def test_build_index_orders_events_by_ievent():
    rows = [
        _row(event_id="802", ievent="2", venue="Second", song="B", isong="10"),
        _row(event_id="801", ievent="1", venue="First", song="A", isong="5"),
    ]
    index, _ = jerrybase.build_index(rows)
    events = index[(jerrybase.artist_key("TestBand"), "1999-09-09")]
    assert [e.event_id for e in events] == ["801", "802"]
    assert [e.venue for e in events] == ["First", "Second"]


def test_lookup_known_show_three_sets():
    events = jerrybase.lookup("Grateful Dead", "1973-06-10")
    assert len(events) == 1
    ev = events[0]
    assert [s.name for s in ev.sets] == ["1", "2", "3"]
    assert [s.closer for s in ev.sets] == [
        "Playing In The Band", "Sugar Magnolia", "Johnny B. Goode"]
    assert [s.song_count for s in ev.sets] == [None, 10, 8]
    assert ev.venue == "Robert F. Kennedy Stadium"


def test_lookup_multi_event_date():
    events = jerrybase.lookup("Grateful Dead", "1970-02-14")
    assert len(events) == 2
    assert [e.event_id for e in events] == ["801", "802"]
    assert all(e.venue == "Fillmore East" for e in events)


def test_lookup_cornell_short_break_before_encore():
    events = jerrybase.lookup("Grateful Dead", "1977-05-08")
    assert len(events) == 1
    ev = events[0]
    assert [s.name for s in ev.sets] == ["1", "2", "encore"]
    assert ev.venue == "Barton Hall, Cornell University"
    by_name = {s.name: s for s in ev.sets}
    assert by_name["2"].break_length == "short"  # short break before the encore


def test_lookup_unknown_returns_empty():
    assert jerrybase.lookup("Nonexistent Artist", "1900-01-01") == []


from llama.models import JerrybaseSet, Track


def _tracks(titles):
    return [Track(index=i + 1, set="1", title=t, filename=f"{i+1:02d}.mp3",
                  title_source="tags") for i, t in enumerate(titles)]


def _event(closers_and_names):
    return JerrybaseEvent(
        event_id="1", venue="V", city="C", state="ST",
        sets=[JerrybaseSet(name=n, closer=c, break_length="long")
              for c, n in closers_and_names],
    )


def test_anchor_breaks_places_sets_from_closers():
    tracks = _tracks(["A", "B", "C", "D", "E", "F"])
    event = _event([("C", "1"), ("E", "2")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "1", "2", "2", "2"]


def test_anchor_breaks_none_when_closer_missing():
    tracks = _tracks(["A", "B", "C"])
    event = _event([("C", "1"), ("Z", "2")])
    assert jerrybase.anchor_breaks(tracks, event) is None


def test_anchor_breaks_repeated_closer_takes_the_latest_occurrence():
    # A song played twice used to make anchoring give up. A set closes on the
    # LAST time its closer is played, so the later occurrence wins.
    tracks = _tracks(["A", "C", "B", "C"])
    event = _event([("C", "1")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "1", "1"]


def test_anchor_breaks_repeated_closer_resolves_against_the_next_closer():
    # "C" twice, then "E" closes set 2: set 1 must take the latest "C" that
    # still precedes "E" (a Playing-in-the-Band sandwich, in miniature).
    tracks = _tracks(["A", "C", "B", "C", "D", "E"])
    event = _event([("C", "1"), ("E", "2")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "1", "1", "2", "2"]


def test_anchor_breaks_none_when_no_candidate_precedes_the_next_closer():
    # Both sets claim to close on "C" but the tape plays it once — unresolvable.
    tracks = _tracks(["A", "B", "C"])
    event = _event([("C", "1"), ("C", "2")])
    assert jerrybase.anchor_breaks(tracks, event) is None


def test_anchor_breaks_matches_closer_across_ampersand_spelling():
    tracks = _tracks(["A", "Me & My Uncle", "B"])
    event = _event([("Me and My Uncle", "1")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "1"]


def test_anchor_breaks_matches_closer_across_dropped_subtitle():
    tracks = _tracks(["A", "Mississippi Half Step", "B", "C"])
    event = _event([("Mississippi Half Step Uptown Toodeloo", "1"), ("C", "2")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "2", "2"]


def test_anchor_breaks_matches_merged_track_on_its_last_component():
    # The tape merges the pair onto one file; the set still closes on Rider.
    tracks = _tracks(["A", "China Cat Sunflower > I Know You Rider", "B", "C"])
    event = _event([("I Know You Rider", "1"), ("C", "2")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "2", "2"]


def test_anchor_breaks_prefers_an_exact_closer_match_over_a_fuzzy_one():
    # "Not Fade Away" and "Not Fade Away Chant" are both plausible fuzzy hits.
    # The exact one wins even though it is the earlier candidate.
    tracks = _tracks(["Not Fade Away", "X", "Not Fade Away Chant", "Y"])
    event = _event([("Not Fade Away", "1"), ("Y", "2")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "2", "2", "2"]


def test_anchor_breaks_preserves_a_trailing_encore_jerrybase_does_not_know():
    # Jerrybase often records only the numbered sets. Anchoring must not
    # swallow an encore the alignment already found AFTER the last closer.
    tracks = _tracks(["A", "B", "C", "D", "E", "F"])
    event = _event([("C", "1"), ("D", "2")])       # no encore row; set 2 ends at D
    aligned = ["1", "1", "1", "2", "encore", "encore"]
    assert jerrybase.anchor_breaks(tracks, event, aligned_sets=aligned) == [
        "1", "1", "1", "2", "encore", "encore"]


def test_anchor_breaks_encore_guard_restores_an_encore_folded_into_the_last_set():
    # Jerrybase often folds an omitted encore into the final set, so its
    # recorded closer IS the encore song (E here). The restore must be able to
    # reach back over that closer, or the guard would never fire in the very
    # case it exists for.
    tracks = _tracks(["A", "B", "C", "D", "E"])
    event = _event([("C", "1"), ("E", "2")])
    aligned = ["1", "1", "1", "2", "encore"]
    assert jerrybase.anchor_breaks(tracks, event, aligned_sets=aligned) == [
        "1", "1", "1", "2", "encore"]


def test_anchor_breaks_encore_guard_never_erases_the_final_numbered_set():
    # Alignment claims the encore starts at D, but set 2 would then have zero
    # tracks — a structurally invalid show. The restore stops one track into
    # the final set, so set 2 keeps D.
    tracks = _tracks(["A", "B", "C", "D", "E"])
    event = _event([("C", "1"), ("E", "2")])
    aligned = ["1", "1", "2", "encore", "encore"]
    assert jerrybase.anchor_breaks(tracks, event, aligned_sets=aligned) == [
        "1", "1", "1", "2", "encore"]


def test_anchor_breaks_ignores_aligned_sets_of_the_wrong_length():
    # Public function with a defaulted kwarg: a mismatched list must be ignored
    # outright rather than producing a non-contiguous labelling.
    tracks = _tracks(["A", "B", "C", "D", "E"])
    event = _event([("C", "1"), ("E", "2")])
    assert jerrybase.anchor_breaks(tracks, event, aligned_sets=["1", "1", "encore"]) == [
        "1", "1", "1", "2", "2"]


def test_anchor_breaks_encore_guard_inert_when_jerrybase_has_an_encore():
    tracks = _tracks(["A", "B", "C", "D", "E"])
    event = _event([("C", "1"), ("D", "2"), ("E", "encore")])
    aligned = ["1", "1", "1", "1", "encore"]
    assert jerrybase.anchor_breaks(tracks, event, aligned_sets=aligned) == [
        "1", "1", "1", "2", "encore"]


def test_anchor_breaks_encore_guard_only_restores_a_trailing_run():
    # A stray mid-tape "encore" label is not an encore; don't resurrect it.
    tracks = _tracks(["A", "B", "C", "D", "E"])
    event = _event([("C", "1"), ("E", "2")])
    aligned = ["1", "encore", "2", "2", "2"]
    assert jerrybase.anchor_breaks(tracks, event, aligned_sets=aligned) == [
        "1", "1", "1", "2", "2"]


def test_anchor_breaks_none_when_out_of_order():
    tracks = _tracks(["A", "E", "C", "D"])
    event = _event([("C", "1"), ("E", "2")])  # E precedes C in tracks
    assert jerrybase.anchor_breaks(tracks, event) is None


def _tracks_with_sets(pairs):
    return [Track(index=i + 1, set=s, title=t, filename=f"{i+1:02d}.mp3",
                  title_source="tags") for i, (t, s) in enumerate(pairs)]


def test_closer_contradictions_none_when_closers_at_boundaries():
    tracks = _tracks_with_sets([("A", "1"), ("B", "1"), ("C", "2"), ("D", "2")])
    event = _event([("B", "1"), ("D", "2")])  # both closers end their sets
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert hard == []
    assert soft == []


def test_closer_contradictions_flags_mid_set_closer():
    tracks = _tracks_with_sets([("A", "1"), ("B", "1"), ("C", "1"), ("D", "2")])
    event = _event([("B", "1")])  # jerrybase says set 1 ends on B, but C is still set 1
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert any("B" in f and "set break" in f for f in hard)
    assert soft == []


def test_closer_contradictions_soft_note_when_closer_absent():
    tracks = _tracks_with_sets([("A", "1"), ("B", "1")])
    event = _event([("Z", "1")])
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert hard == []
    assert any("Z" in n for n in soft)


def test_closer_contradictions_matches_ampersand_and_subtitle_spellings():
    # The tripwire compared raw normalized titles, so taper spellings made real
    # contradictions look like absent closers.
    tracks = _tracks_with_sets([("A", "1"), ("Me & My Uncle", "1"), ("C", "1")])
    hard, soft = jerrybase.closer_contradictions(tracks, _event([("Me and My Uncle", "1")]))
    assert soft == []                                    # no longer "not found"
    assert any("Me and My Uncle" in f and "set break" in f for f in hard)


def test_closer_contradictions_matches_merged_track_on_last_component():
    tracks = _tracks_with_sets([("A", "1"), ("China Cat Sunflower > I Know You Rider", "1")])
    hard, soft = jerrybase.closer_contradictions(tracks, _event([("I Know You Rider", "1")]))
    assert hard == [] and soft == []     # closer is the last track: no contradiction


def test_anchor_breaks_declines_an_encore_only_event():
    # normalize_set_label cannot map jerrybase labels like "First part" /
    # "Second part", so build_index truncates those events down to their Encore
    # row alone. Such an event carries no set-break information at all, and
    # anchoring on it would label the WHOLE show "encore" with no breaks.
    tracks = _tracks(["A", "B", "C"])
    event = _event([("C", "encore")])
    assert jerrybase.anchor_breaks(tracks, event) is None


def test_artist_key_folds_ampersand_to_and():
    # The CSV spells these "DeadAndCompany" / "PhilLeshAndFriends"; stripping
    # "&" instead of folding it silently denied both acts all evidence.
    assert jerrybase.artist_key("Dead & Company") == "deadandcompany"
    assert jerrybase.artist_key("Phil Lesh & Friends") == "philleshandfriends"
    assert jerrybase.artist_key("Grateful Dead") == "gratefuldead"


def test_is_family_artist_covers_dataset_and_extras():
    assert jerrybase.is_family_artist("Grateful Dead")
    assert jerrybase.is_family_artist("Dark Star Orchestra")
    assert jerrybase.is_family_artist("Dead & Company")
    # Absent from the dataset, but family by vocabulary.
    assert jerrybase.is_family_artist("Joe Russo's Almost Dead")
    # Not family: must get no Dead vocabulary.
    assert not jerrybase.is_family_artist("Fugazi")
    assert not jerrybase.is_family_artist("")
