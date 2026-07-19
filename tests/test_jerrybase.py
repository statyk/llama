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


def test_anchor_breaks_none_when_closer_ambiguous():
    tracks = _tracks(["A", "C", "B", "C"])  # "C" appears twice
    event = _event([("C", "1")])
    assert jerrybase.anchor_breaks(tracks, event) is None


def test_anchor_breaks_none_when_out_of_order():
    tracks = _tracks(["A", "E", "C", "D"])
    event = _event([("C", "1"), ("E", "2")])  # E precedes C in tracks
    assert jerrybase.anchor_breaks(tracks, event) is None
