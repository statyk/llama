from llama.grouping import group_candidates

import pytest

from llama import grouping
from llama.models import JerrybaseEvent, JerrybaseSet


def _event(venue, city, closers):
    return JerrybaseEvent(
        event_id=venue, venue=venue, city=city, state="NY",
        sets=[JerrybaseSet(name=str(i + 1), closer=c, break_length="long")
              for i, c in enumerate(closers)],
    )


def _two_fillmore_events():
    # e1 (early) closes on Turn On Your Lovelight; e2 (late) on And We Bid You Good Night.
    return [
        _event("Fillmore East", "New York", ["Turn On Your Lovelight"]),
        _event("Fillmore West", "San Francisco", ["And We Bid You Good Night"]),
    ]


def doc(identifier, date="1973-06-10T00:00:00Z", venue="RFK Stadium", **kw):
    d = {"identifier": identifier, "title": "Grateful Dead Live", "date": date,
         "venue": venue, "coverage": "Washington, DC", "avg_rating": 4.5, "num_reviews": 12}
    d.update(kw)
    return d


def test_same_date_recordings_merge():
    cands = group_candidates("GratefulDead", [
        doc("gd73-06-10.sbd.hollister"),
        doc("gd73-06-10.aud.weiner", venue="Robert F. Kennedy Stadium", avg_rating=3.9),
    ])
    assert len(cands) == 1
    c = cands[0]
    assert c.performance_id == "GratefulDead/1973-06-10"
    assert len(c.recordings) == 2
    assert c.city == "Washington, DC"


def test_jerrybase_single_event_overrides_early_late_hint():
    # 1966-07-16 is a single jerrybase event (real vendored set_breaks.csv).
    # That ground truth overrides the /early|/late identifier hint: the two
    # tapes merge into one plain-pid candidate rather than splitting.
    cands = group_candidates("GratefulDead", [
        doc("gd66-07-16.early.aud", date="1966-07-16T00:00:00Z"),
        doc("gd66-07-16.late.aud", date="1966-07-16T00:00:00Z"),
    ])
    assert [c.performance_id for c in cands] == ["GratefulDead/1966-07-16"]
    assert len(cands[0].recordings) == 2


def test_venue_majority_and_missing_date_skipped():
    cands = group_candidates("GratefulDead", [
        doc("a"), doc("b"), doc("c", venue="Robert F. Kennedy Stadium"),
        {"identifier": "no-date"},
    ])
    assert len(cands) == 1
    assert cands[0].venue == "RFK Stadium"


def test_num_reviews_coerced():
    cands = group_candidates("GratefulDead", [doc("a", num_reviews="7", avg_rating="4.2")])
    rec = cands[0].recordings[0]
    assert rec.num_reviews == 7
    assert rec.avg_rating == 4.2


def test_list_valued_numeric_fields_coerced():
    cands = group_candidates("GratefulDead", [doc("a", num_reviews=[7], avg_rating=[4.2])])
    rec = cands[0].recordings[0]
    assert rec.num_reviews == 7
    assert rec.avg_rating == 4.2


def test_downloads_mapped_and_defaulted():
    docs = [
        {"identifier": "gd73-a", "date": "1973-06-10", "downloads": [1500]},
        {"identifier": "gd73-b", "date": "1973-06-10"},
    ]
    cands = group_candidates("GratefulDead", docs)
    recs = {r.identifier: r for r in cands[0].recordings}
    assert recs["gd73-a"].downloads == 1500
    assert recs["gd73-b"].downloads == 0


def test_single_event_keeps_plain_pid(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup",
                        lambda a, d: [_event("RFK Stadium", "Washington", ["Johnny B. Goode"])])
    cands = group_candidates("GratefulDead", [
        doc("gd73-06-10.sbd.hollister"),
        doc("gd73-06-10.aud.weiner"),
    ])
    assert len(cands) == 1
    assert cands[0].performance_id == "GratefulDead/1973-06-10"
    assert len(cands[0].recordings) == 2


def test_no_jerrybase_data_preserves_early_late(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: [])
    cands = group_candidates("GratefulDead", [
        doc("gd66-07-16.early.aud", date="1966-07-16T00:00:00Z"),
        doc("gd66-07-16.late.aud", date="1966-07-16T00:00:00Z"),
    ])
    ids = sorted(c.performance_id for c in cands)
    assert ids == ["GratefulDead/1966-07-16/early", "GratefulDead/1966-07-16/late"]


def test_two_event_split_by_early_late_text(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.early.aud", date="1970-02-14T00:00:00Z", description="a set"),
        doc("gd70-02-14.late.sbd", date="1970-02-14T00:00:00Z", description="a set"),
    ])
    ids = sorted(c.performance_id for c in cands)
    assert ids == ["GratefulDead/1970-02-14/e1", "GratefulDead/1970-02-14/e2"]


def test_two_event_split_by_description_closers(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.aud.a", date="1970-02-14T00:00:00Z",
            description="Cold Rain > Turn On Your Lovelight"),
        doc("gd70-02-14.aud.b", date="1970-02-14T00:00:00Z",
            description="Casey Jones ... And We Bid You Good Night"),
    ])
    by_id = {c.performance_id: c for c in cands}
    assert set(by_id) == {"GratefulDead/1970-02-14/e1", "GratefulDead/1970-02-14/e2"}
    assert by_id["GratefulDead/1970-02-14/e1"].recordings[0].identifier == "gd70-02-14.aud.a"


def test_recording_spanning_both_events_is_held(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.sbd.complete", date="1970-02-14T00:00:00Z",
            description="Turn On Your Lovelight ... And We Bid You Good Night"),
    ])
    assert [c.performance_id for c in cands] == ["GratefulDead/1970-02-14/spans"]


def test_unassignable_recording_is_held(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.aud.mystery", date="1970-02-14T00:00:00Z",
            description="a wonderful night of music"),
    ])
    assert [c.performance_id for c in cands] == ["GratefulDead/1970-02-14/unassigned"]


def test_per_event_venue_enrichment_when_archive_absent(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.aud.a", date="1970-02-14T00:00:00Z", venue=None, coverage=None,
            description="Turn On Your Lovelight"),
    ])
    c = cands[0]
    assert c.performance_id == "GratefulDead/1970-02-14/e1"
    assert c.venue == "Fillmore East"
    assert c.city == "New York"


def test_jerrybase_disabled_does_not_split(monkeypatch):
    def _boom(a, d):
        raise AssertionError("lookup must not be called when disabled")
    monkeypatch.setattr(grouping.jerrybase, "lookup", _boom)
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.late.sbd", date="1970-02-14T00:00:00Z"),
    ], jerrybase_enabled=False)
    assert cands[0].performance_id == "GratefulDead/1970-02-14/late"
