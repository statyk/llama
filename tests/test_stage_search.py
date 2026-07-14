from pathlib import Path

from llama.models import Criteria
from llama.stages.search import build_query, run_search
from llama.workspace import RunWorkspace


class StubIA:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def search(self, query, fields, rows=500):
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
