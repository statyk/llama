import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Criteria
from llama.stages.discover import match_artists, run_discover
from llama.workspace import RunWorkspace

COLLECTIONS = [
    {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    {"identifier": "JoanBaez", "title": "Joan Baez"},
    {"identifier": "GratefulDead", "title": "Grateful Dead"},
    {"identifier": "JoanJett", "title": "Joan Jett"},
]


class StubIA:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def search(self, query, fields, rows=500):
        self.queries.append((query, rows))
        return self.docs


def crit() -> Criteria:
    return Criteria(query="well-known folk/acoustic performer 60s-70s",
                    soft_preferences="folk/acoustic, well known",
                    date_from="1960-01-01", date_to="1979-12-31")


def proposed(names):
    return json.dumps({"artists": names})


def test_discover_matches_orders_and_writes(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[proposed(["Joan Baez", "Doc Watson", "Nick Drake"])])
    ia = StubIA(COLLECTIONS)
    got = run_discover(ws, fake, ia, crit())
    assert got == [
        {"identifier": "JoanBaez", "title": "Joan Baez"},
        {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    ]  # LLM order kept; Nick Drake (not on LMA) dropped
    assert ia.queries[0][0] == "collection:etree AND mediatype:collection"
    assert ia.queries[0][1] == 10000
    assert json.loads(ws.artists.read_text()) == got


def test_equality_beats_containment_and_first_wins_ties():
    cols = [{"identifier": "JoanJett", "title": "Joan"},
            {"identifier": "JoanBaez", "title": "Joan Baez"}]
    assert match_artists(["Joan Baez"], cols)[0]["identifier"] == "JoanBaez"
    tie = [{"identifier": "A", "title": "The Seldom Scene Live"},
           {"identifier": "B", "title": "Seldom Scene (live)"}]
    assert match_artists(["Seldom Scene"], tie)[0]["identifier"] == "A"


def test_cap_and_dedup():
    cols = [{"identifier": f"A{i}", "title": f"Artist Number {i}"} for i in range(20)]
    names = [f"Artist Number {i}" for i in range(20)] + ["Artist Number 0"]
    got = match_artists(names, cols, max_artists=10)
    assert len(got) == 10
    assert len({a["identifier"] for a in got}) == 10


def test_single_word_names_match_by_equality_only():
    cols = [{"identifier": "WarrenHaynes", "title": "Warren Haynes Presents War Stories"},
            {"identifier": "War", "title": "War"}]
    got = match_artists(["War"], cols)
    assert [a["identifier"] for a in got] == ["War"]
    # and with no exact-title collection present, a single word matches nothing
    assert match_artists(["War"], cols[:1]) == []


def test_stopword_heavy_names_do_not_containment_match():
    cols = [{"identifier": "AllmanBrothers", "title": "The Allman Brothers Band"},
            {"identifier": "TheBand", "title": "The Band"}]
    got = match_artists(["The Band"], cols)
    assert [a["identifier"] for a in got] == ["TheBand"]  # equality, not containment
    assert match_artists(["The Who"], [{"identifier": "GuessWho", "title": "The Guess Who"}]) == []


def test_stopwords_removed_before_containment():
    cols = [{"identifier": "DocWatson", "title": "Doc and Merle Watson"}]
    assert match_artists(["Doc Watson"], cols)[0]["identifier"] == "DocWatson"


def test_zero_matches_writes_empty(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[proposed(["Nick Drake"])])
    assert run_discover(ws, fake, StubIA(COLLECTIONS), crit()) == []
    assert json.loads(ws.artists.read_text()) == []


def test_skip_if_exists(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    run_discover(ws, FakeProvider(completes=[proposed(["Joan Baez"])]),
                 StubIA(COLLECTIONS), crit())
    again = run_discover(ws, FakeProvider(), StubIA(COLLECTIONS), crit())
    assert again[0]["identifier"] == "JoanBaez"
