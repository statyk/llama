from llama.models import Criteria, DJNotes, LedgerEntry, Manifest, Show, Track


def test_criteria_defaults_and_roundtrip():
    c = Criteria(query="GD 73-74 with a china>rider")
    assert c.min_avg_rating == 3.5 and c.min_reviews == 3 and c.count == 1
    assert c.setlist_constraints == []
    assert c.year_cap == 1.0
    again = Criteria.model_validate_json(c.model_dump_json())
    assert again == c


def test_show_defaults():
    s = Show(
        performance_id="GratefulDead/1973-06-10",
        identifier="gd73-06-10.sbd",
        artist="Grateful Dead",
        date="1973-06-10",
        tracks=[
            Track(index=1, set="1", title="Morning Dew", filename="d1t01.mp3", title_source="tags")
        ],
    )
    assert s.needs_review is False and s.review_flags == [] and s.set_breaks == []


def test_manifest_schema_version():
    m = Manifest(
        show={}, source={}, tracks=[], set_breaks=[],
        dj_notes=DJNotes(intro="hi", set_intros={}, outro="bye"),
        total_duration_sec=0.0, set_durations_sec={},
    )
    assert m.schema_version == 2


def test_ledger_entry():
    e = LedgerEntry(
        performance_id="GratefulDead/1973-06-10", artist="Grateful Dead",
        date="1973-06-10", status="selected", run="r1", recorded_at="2026-07-14T00:00:00+00:00",
    )
    assert e.venue is None


def test_research_vetting_defaults():
    from llama.models import ResearchVetting, VettingResult

    v = ResearchVetting()
    assert v.asserted_songs == [] and v.asserted_dates == [] and v.context == ""
    r = VettingResult(vetting=v)
    assert r.flags == []
