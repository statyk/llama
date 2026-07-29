import json
from pathlib import Path

from herder import FakeProvider
from llama.models import Criteria
from llama.stages.discover import run_discover
from llama.workspace import RunWorkspace

COLLECTIONS = [
    {"identifier": "DocWatson", "title": "Doc and Merle Watson", "downloads": 800000},
    {"identifier": "JoanBaez", "title": "Joan Baez", "downloads": 900000},
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "TinyBand", "title": "Tiny Band", "downloads": 20},
]

ITEMS = [{"identifier": f"jb{i}", "collection": ["JoanBaez"], "year": "1965"} for i in range(3)]


class StubIA:
    def __init__(self, collections=COLLECTIONS, items=ITEMS):
        self._collections = collections
        self._items = items
        self.queries = []

    def scrape(self, query, fields, count=10000):
        self.queries.append(query)
        if "mediatype:collection" in query:
            return self._collections
        return self._items


def crit() -> Criteria:
    return Criteria(query="well-known folk/acoustic performer 60s-70s",
                    soft_preferences="folk/acoustic, well known",
                    date_from="1960-01-01", date_to="1979-12-31")


def matches(*pairs):
    return json.dumps({"matches": [{"identifier": i, "reason": r} for i, r in pairs]})


def test_discover_matches_orders_and_writes(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches(("JoanBaez", "60s folk icon"),
                                           ("DocWatson", "flatpicking legend"))])
    got = run_discover(ws, fake, StubIA(), crit(), cache_dir=tmp_path / "cache")
    assert got == [
        {"identifier": "JoanBaez", "title": "Joan Baez"},
        {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    ]  # LLM ranking kept; reasons not persisted in the artifact
    assert json.loads(ws.artists.read_text()) == got
    prompt = fake.calls[0][1]
    assert "well-known folk/acoustic performer 60s-70s" in prompt  # verbatim request
    # interpret's soft_preferences paraphrase must NOT ride along: it restates
    # the request and paraphrase loses exclusions ("not blues-rock")
    assert "folk/acoustic, well known" not in prompt
    assert "1960-01-01" in prompt                     # era reaches the LLM
    assert "TinyBand" not in prompt                   # junk-filtered out of the table


def test_discover_caps_at_max_artists(tmp_path: Path):
    cols = [{"identifier": f"A{i}", "title": f"Artist {i}", "downloads": 60000}
            for i in range(15)]
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches(*((f"A{i}", "fits") for i in range(15)))])
    got = run_discover(ws, fake, StubIA(collections=cols, items=[]), crit(),
                       cache_dir=tmp_path / "cache", max_artists=10)
    assert len(got) == 10


def test_discover_default_budget_matches_llama_artists(tmp_path: Path):
    # test-driving a query with `llama artists` (limit 20) must preview the
    # same slate a profile/find discovery sees
    cols = [{"identifier": f"A{i}", "title": f"Artist {i}", "downloads": 60000}
            for i in range(25)]
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches(*((f"A{i}", "fits") for i in range(25)))])
    got = run_discover(ws, fake, StubIA(collections=cols, items=[]), crit(),
                       cache_dir=tmp_path / "cache")
    assert len(got) == 20


def test_zero_matches_writes_empty(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[matches()])
    assert run_discover(ws, fake, StubIA(), crit(), cache_dir=tmp_path / "cache") == []
    assert json.loads(ws.artists.read_text()) == []


def test_skip_if_exists(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    run_discover(ws, FakeProvider(completes=[matches(("JoanBaez", "x"))]),
                 StubIA(), crit(), cache_dir=tmp_path / "cache")
    again = run_discover(ws, FakeProvider(), StubIA(), crit(),
                         cache_dir=tmp_path / "cache")
    assert again[0]["identifier"] == "JoanBaez"
