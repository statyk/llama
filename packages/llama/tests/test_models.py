from llama.models import Criteria, DJNotes, LedgerEntry, Manifest, ManifestBriefing, Show, Track


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
        briefing=ManifestBriefing(),
        dj_notes=DJNotes(set_intros={"1": "hi"}, outro="bye"),
        total_duration_sec=0.0, set_durations_sec={},
    )
    assert m.schema_version == 3


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


def test_show_date_fields_default_for_old_artifacts():
    from llama.models import Show, VettingResult, ResearchVetting
    s = Show(performance_id="p", identifier="i", artist="a", date="1976-01-01")
    assert s.item_date is None and s.date_source == "item"
    v = VettingResult(vetting=ResearchVetting())
    assert v.adopted_date is None


def test_jerrybase_models_construct():
    from llama.models import JerrybaseEvent, JerrybaseSet

    ev = JerrybaseEvent(
        event_id="2673", venue="Barton Hall, Cornell University",
        city="Ithaca", state="NY",
        sets=[
            JerrybaseSet(name="1", closer="Dancin' In The Streets", break_length="long"),
            JerrybaseSet(name="2", closer="Morning Dew", break_length="short", song_count=7),
            JerrybaseSet(name="encore", closer="One More Saturday Night",
                         break_length="long", song_count=1),
        ],
    )
    assert ev.sets[0].song_count is None
    assert ev.sets[1].break_length == "short"
    assert [s.name for s in ev.sets] == ["1", "2", "encore"]


def test_show_venue_source_defaults_to_item():
    from llama.models import Show

    s = Show(performance_id="X/2020-01-01", identifier="x", artist="X",
             date="2020-01-01")
    assert s.venue_source == "item"


def test_criteria_and_provenance_voice_default_none():
    from llama.models import Candidate, Criteria, Provenance, RecordingSummary

    assert Criteria(query="q").voice is None
    prov = Provenance(
        performance_id="GratefulDead/1973-06-10", run="r",
        candidate=Candidate(performance_id="GratefulDead/1973-06-10",
                            collection="GratefulDead", date="1973-06-10",
                            recordings=[RecordingSummary(identifier="i")]),
        processed_at="2026-07-22T00:00:00+00:00",
    )
    assert prov.voice is None


def test_criteria_presenter_and_title_default_none():
    c = Criteria(query="q")
    assert c.presenter is None and c.title is None
    again = Criteria.model_validate_json(c.model_dump_json())
    assert again == c


def test_criteria_profile_default_none_and_roundtrip():
    c = Criteria(query="x")
    assert c.profile is None
    again = Criteria.model_validate_json(c.model_dump_json())
    assert again == c
    stamped = Criteria(query="x", profile="sunday-dead-hour")
    assert Criteria.model_validate_json(stamped.model_dump_json()).profile == "sunday-dead-hour"


def test_provenance_presenter_fields_default_none():
    from llama.models import Candidate, Provenance

    p = Provenance(performance_id="x", run="r",
                   candidate=Candidate(performance_id="x", collection="c",
                                       date="1970-01-01", recordings=[]),
                   processed_at="2026-07-24T00:00:00+00:00")
    assert p.presenter is None and p.title is None
