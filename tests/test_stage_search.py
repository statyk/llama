from pathlib import Path

from llama.models import Criteria
from llama.stages.search import build_query, run_search
from llama.workspace import RunWorkspace


class StubIA:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def scrape(self, query, fields, count=10000):
        self.queries.append(query)
        return self.docs


def test_build_query_hard_filters_only():
    crit = Criteria(query="q", collection="GratefulDead",
                    date_from="1973-01-01", date_to="1974-12-31", min_avg_rating=4.5)
    q = build_query(crit)
    assert q == "mediatype:etree AND collection:GratefulDead AND date:[1973-01-01 TO 1974-12-31]"
    assert "rating" not in q  # quality is winnow's job — wide net here


def test_build_query_artist_without_collection():
    q = build_query(Criteria(query="q", artist="Doc Watson"))
    assert 'creator:"Doc Watson"' in q


def test_run_search_groups_and_writes(tmp_path: Path):
    docs = [
        {"identifier": "gd73-06-10.sbd", "date": "1973-06-10T00:00:00Z", "venue": "RFK Stadium",
         "avg_rating": 4.7, "num_reviews": 30},
        {"identifier": "gd73-06-10.aud", "date": "1973-06-10T00:00:00Z", "venue": "RFK Stadium"},
        {"identifier": "gd74-05-19.sbd", "date": "1974-05-19T00:00:00Z", "venue": "Portland Memorial Coliseum"},
    ]
    ws = RunWorkspace(tmp_path, "r1")
    ia = StubIA(docs)
    cands = run_search(ws, ia, Criteria(query="q", collection="GratefulDead"))
    assert [c.performance_id for c in cands] == ["GratefulDead/1973-06-10", "GratefulDead/1974-05-19"]
    assert len(cands[0].recordings) == 2
    assert ws.candidates.exists()
    # skip-if-exists: no second IA call
    run_search(ws, ia, Criteria(query="q", collection="GratefulDead"))
    assert len(ia.queries) == 1


def test_run_search_fans_out_per_artist(tmp_path: Path):
    docs_by_collection = {
        "JoanBaez": [{"identifier": "jb1963-11-23", "date": "1963-11-23T00:00:00Z",
                      "venue": "Club 47"}],
        "DocWatson": [{"identifier": "dw1964-03-07", "date": "1964-03-07T00:00:00Z",
                       "venue": "Ash Grove"}],
    }

    class FanStubIA:
        def __init__(self):
            self.queries = []

        def scrape(self, query, fields, count=10000):
            self.queries.append(query)
            for ident, docs in docs_by_collection.items():
                if f"collection:{ident}" in query:
                    return docs
            return []

    ws = RunWorkspace(tmp_path, "r1")
    ia = FanStubIA()
    artists = [{"identifier": "JoanBaez", "title": "Joan Baez"},
               {"identifier": "DocWatson", "title": "Doc and Merle Watson"}]
    crit = Criteria(query="q", date_from="1960-01-01", date_to="1969-12-31")
    cands = run_search(ws, ia, crit, artists=artists)
    assert len(ia.queries) == 2
    assert all("mediatype:etree" in q and "date:[1960-01-01 TO 1969-12-31]" in q
               for q in ia.queries)
    pids = sorted(c.performance_id for c in cands)
    assert pids == ["DocWatson/1964-03-07", "JoanBaez/1963-11-23"]


def test_search_requests_downloads_field():
    from llama.stages.search import SEARCH_FIELDS
    assert "downloads" in SEARCH_FIELDS


def test_run_search_splits_multi_event_when_enabled(tmp_path: Path):
    docs = [{"identifier": "gd1970-02-14.late.sbd", "date": "1970-02-14T00:00:00Z",
             "venue": "Fillmore East", "description": "Casey Jones ... And We Bid You Good Night"}]
    ia = StubIA(docs)
    on = run_search(RunWorkspace(tmp_path / "on", "r"), ia,
                    Criteria(query="q", collection="GratefulDead"), jerrybase_enabled=True)
    assert [c.performance_id for c in on] == ["GratefulDead/1970-02-14/e2"]

    off = run_search(RunWorkspace(tmp_path / "off", "r"), StubIA(docs),
                     Criteria(query="q", collection="GratefulDead"), jerrybase_enabled=False)
    assert [c.performance_id for c in off] == ["GratefulDead/1970-02-14/late"]
