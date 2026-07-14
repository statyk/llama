from llama.grouping import group_candidates


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


def test_early_late_split():
    cands = group_candidates("GratefulDead", [
        doc("gd66-07-16.early.aud", date="1966-07-16T00:00:00Z"),
        doc("gd66-07-16.late.aud", date="1966-07-16T00:00:00Z"),
    ])
    ids = sorted(c.performance_id for c in cands)
    assert ids == ["GratefulDead/1966-07-16/early", "GratefulDead/1966-07-16/late"]


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
