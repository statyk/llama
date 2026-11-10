"""Task 5: search for synthetic `ts-` keys (spec "Search and grouping").

The query for an allowlisted key targets the taperssection collection by the
entry's creators; `creator:(...)` is only a prefilter, so search keeps a doc
only on an exact normalized creator and the entry's policy (active window,
date cross-check, exclude, lineage). Every LMA query is byte-identical to today.
"""
import json
import logging
from pathlib import Path

import pytest

import llama.cli as cli
from llama import ts_rules
from llama.config import Config, TaperssectionArtist, TaperssectionConfig
from llama.errors import LlamaError
from llama.grouping import _summary
from llama.models import Candidate, Criteria
from llama.stages.search import (SEARCH_FIELDS, TS_EXTRA_FIELDS, build_query, run_search,
                                 ts_filter_docs)
from llama.taperssection import Allowlist
from llama.workspace import RunWorkspace, read_model_list

FIXTURES = Path(__file__).parent / "fixtures"
P_IDENT = "phish1997-12-29.003886.newyork.mk41.cmc6.flac1644"

PHISH = TaperssectionArtist(name="Phish", creators=["Phish", "Phish (band)"],
                            lineages=["aud"], exclude=["Sonosax"],
                            active_from="1983-12-02", active_until="2030-12-31")


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries)))


def _fixture_doc(**over) -> dict:
    """The fixture item as the scrape serves it (description with `<br />` and
    `&gt;`, ISO timestamps for date/addeddate)."""
    m = json.loads((FIXTURES / f"{P_IDENT}.json").read_text())["metadata"]
    doc = {
        "identifier": m["identifier"], "title": m["title"],
        "date": m["date"] + "T00:00:00Z", "creator": m["creator"],
        "addeddate": m["addeddate"].replace(" ", "T") + "Z",
        "description": m["description"], "downloads": 1234,
    }
    doc.update(over)
    return doc


class StubIA:
    def __init__(self, docs_by_query=None, docs=None):
        self.docs_by_query = docs_by_query or {}
        self.docs = docs
        self.calls = []

    def scrape(self, query, fields, count=10000):
        self.calls.append((query, list(fields)))
        if self.docs is not None:
            return self.docs
        for needle, docs in self.docs_by_query.items():
            if needle in query:
                return docs
        return []


# --- build_query ------------------------------------------------------------

LMA_SHAPES = [
    (Criteria(query="q", collection="GratefulDead"),
     "mediatype:etree AND collection:GratefulDead"),
    (Criteria(query="q", artist="Phish"),
     'mediatype:etree AND creator:"Phish"'),
    (Criteria(query="q", collection="JazzIsPhish", date_from="1997-01-01", date_to="1997-12-31"),
     "mediatype:etree AND collection:JazzIsPhish AND date:[1997-01-01 TO 1997-12-31]"),
]


@pytest.mark.parametrize("crit,want", LMA_SHAPES)
def test_build_query_lma_unchanged(crit, want):
    assert build_query(crit) == want
    assert build_query(crit, None) == want
    assert build_query(crit, Allowlist.empty()) == want
    assert build_query(crit, _al(PHISH)) == want


def test_build_query_synthetic():
    al = _al(PHISH)
    assert build_query(Criteria(query="q", collection="ts-phish"), al) == (
        'collection:taperssection AND mediatype:audio AND creator:("Phish" OR "Phish (band)")')
    assert build_query(Criteria(query="q", collection="ts-phish", date_from="1997-01-01"), al) == (
        'collection:taperssection AND mediatype:audio AND creator:("Phish" OR "Phish (band)")'
        " AND date:[1997-01-01 TO 2100-01-01]")
    # fail closed: never an LMA query for a ts- key
    with pytest.raises(LlamaError, match="ts-phish"):
        build_query(Criteria(query="q", collection="ts-phish"))
    with pytest.raises(LlamaError, match="ts-gone"):
        build_query(Criteria(query="q", collection="ts-gone"), al)


# --- ts_filter_docs ---------------------------------------------------------

def test_filter_drops_tributes_dates_forbidden_excluded(caplog):
    entry = PHISH.model_copy(update={"exclude": ["badtoken"]})
    survivor = _fixture_doc()
    docs = [
        survivor,
        # tribute act: creator:"Phish" phrase-matches it, the exact test does not
        _fixture_doc(identifier="phishtribute1997-12-29", creator="Phish Tribute Band",
                     title="Phish Tribute Band 1997-12-29"),
        # creator list, none exact
        _fixture_doc(identifier="jip1997-12-29", creator=["Jazz Is Phish"]),
        # before active_from
        _fixture_doc(identifier="ph1980-01-01.aud", date="1980-01-01T00:00:00Z",
                     title="Phish 1980-01-01"),
        # date cross-check: identifier claims a date that disagrees with `date`
        _fixture_doc(identifier="ph2027-07-27.aud", title="Phish", date="2017-07-27T00:00:00Z"),
        # no date, while the identifier claims one
        _fixture_doc(identifier="ph1998-01-01.aud", title="Phish", date=None),
        # excluded (token in identifier)
        _fixture_doc(identifier="ph1997-12-29.badtoken.aud"),
        # forbidden lineage: a soundboard when the entry allows aud only
        _fixture_doc(identifier="ph1997-12-29.sbd.flac", title="Phish 1997-12-29 SBD",
                     description="Source: SBD > DAT"),
    ]
    with caplog.at_level(logging.INFO, logger="llama"):
        kept = ts_filter_docs(docs, entry, rule=ts_rules.RULE)
    assert [d["identifier"] for d in kept] == [P_IDENT]
    msgs = [r.getMessage() for r in caplog.records]
    hit = [m for m in msgs if "ph2027-07-27.aud" in m]
    assert hit and "2017-07-27" in hit[0] and "2027-07-27" in hit[0]
    hit = [m for m in msgs if "ph1998-01-01.aud" in m]
    assert hit and "1998-01-01" in hit[0]


def test_filter_exclude_reads_fixture_source_segment():
    # PHISH excludes "Sonosax", which appears only in the fixture's Source line
    # (after `<br />` / `&gt;` unescaping).
    assert ts_filter_docs([_fixture_doc()], PHISH, rule=ts_rules.RULE) == []
    entry = PHISH.model_copy(update={"exclude": []})
    assert len(ts_filter_docs([_fixture_doc()], entry, rule=ts_rules.RULE)) == 1


def test_filter_unknown_lineage_held_not_dropped():
    # rule "a": no evidence means unknown, which is not forbidden here
    entry = PHISH.model_copy(update={"exclude": []})
    doc = _fixture_doc(identifier="ph1997-12-29.flac16", title="Phish 1997-12-29",
                       description="Phish live")
    assert ts_rules.RULE == "a"
    assert len(ts_filter_docs([doc], entry, rule=ts_rules.RULE)) == 1


# --- run_search -------------------------------------------------------------

def test_all_filtered_candidate_dropped(tmp_path: Path):
    docs = [_fixture_doc(creator="Phish Tribute"),
            _fixture_doc(identifier="ph1997-12-30.sbd", title="Phish 1997-12-30 SBD",
                         date="1997-12-30T00:00:00Z", description="Source: SBD")]
    ia = StubIA(docs=docs)
    ws = RunWorkspace(tmp_path, "r1")
    cands = run_search(ws, ia, Criteria(query="q", collection="ts-phish"),
                       allowlist=_al(PHISH.model_copy(update={"exclude": []})))
    assert cands == []
    assert read_model_list(ws.candidates, Candidate) == []


def test_ts_recording_fields_populated(tmp_path: Path):
    entry = PHISH.model_copy(update={"exclude": []})
    al = _al(entry)
    other = _fixture_doc(identifier="phish1997-12-29.mtx.lineage", lineage="Matrix > CD",
                         source="FOB Schoeps", description="Phish live",
                         title="Phish 1997-12-29")
    docs = [_fixture_doc(), other]
    ia = StubIA(docs=docs)
    ws = RunWorkspace(tmp_path, "r1")
    crit = Criteria(query="q", collection="ts-phish")
    run_search(ws, ia, crit, allowlist=al)

    query, fields = ia.calls[0]
    assert query == build_query(crit, al)
    assert fields == SEARCH_FIELDS + TS_EXTRA_FIELDS
    assert "description" in fields and "creator" in fields and "addeddate" in fields

    # the candidate as stored in the run (what provenance carries)
    [cand] = read_model_list(ws.candidates, Candidate)
    assert cand.performance_id == "ts-phish/1997-12-29"
    assert cand.collection == "ts-phish"
    by_id = {r.identifier: r for r in cand.recordings}
    rec = by_id[P_IDENT]
    assert rec.creator == "Phish"
    assert rec.addeddate == "2025-09-08T13:05:28Z"
    assert rec.source is None and rec.lineage is None
    assert rec.downloads == 1234
    assert "Schoeps CMC6/MK41&gt;" in rec.description
    rec2 = by_id["phish1997-12-29.mtx.lineage"]
    assert rec2.lineage == "Matrix > CD"
    assert rec2.source == "FOB Schoeps"
    # classify() on the stored summary equals classify() at filter time
    for doc in docs:
        at_filter = ts_rules.classify(_summary(doc, doc["date"][:10]))
        assert ts_rules.classify(by_id[doc["identifier"]]) == at_filter
    assert ts_rules.classify(rec) == "aud"


def test_run_search_ts_without_allowlist_fails_closed(tmp_path: Path):
    ia = StubIA(docs=[_fixture_doc()])
    with pytest.raises(LlamaError, match="ts-phish"):
        run_search(RunWorkspace(tmp_path, "r1"), ia, Criteria(query="q", collection="ts-phish"))
    assert ia.calls == []


def test_run_search_fanout_mixes_lma_and_ts(tmp_path: Path):
    entry = PHISH.model_copy(update={"exclude": []})
    al = _al(entry)
    lma_docs = [{"identifier": "jip1997-12-29", "date": "1997-12-29T00:00:00Z",
                 "creator": "Phish", "venue": "Somewhere"}]
    ia = StubIA(docs_by_query={"collection:JazzIsPhish": lma_docs,
                               "collection:taperssection": [_fixture_doc()]})
    artists = [{"identifier": "JazzIsPhish", "title": "Jazz Is Phish"},
               {"identifier": "ts-phish", "title": "Phish"}]
    crit = Criteria(query="q", date_from="1997-01-01", date_to="1997-12-31")
    cands = run_search(RunWorkspace(tmp_path, "r1"), ia, crit, artists=artists, allowlist=al)
    (q1, f1), (q2, f2) = ia.calls
    assert q1 == "mediatype:etree AND collection:JazzIsPhish AND date:[1997-01-01 TO 1997-12-31]"
    assert f1 == SEARCH_FIELDS
    assert q2.startswith("collection:taperssection AND mediatype:audio")
    assert f2 == SEARCH_FIELDS + TS_EXTRA_FIELDS
    assert sorted(c.performance_id for c in cands) == ["JazzIsPhish/1997-12-29",
                                                     "ts-phish/1997-12-29"]
    # an LMA doc's recording is summarized exactly as before
    lma = next(c for c in cands if c.collection == "JazzIsPhish").recordings[0]
    assert lma.creator == "Phish"  # present in the doc; LMA scrapes never request it


# --- _execute pre-flight -----------------------------------------------------

class _NoScrapeIA:
    def scrape(self, *a, **k):
        raise AssertionError("no scrape may run before the key check")


def _execute(tmp_path, monkeypatch, criteria):
    config = Config(root=tmp_path, taperssection=TaperssectionConfig(artists=[PHISH]))

    def boom(*a, **k):
        raise AssertionError("nothing may run before the key check")

    monkeypatch.setattr(cli, "run_search", boom)
    monkeypatch.setattr(cli, "run_discover", boom)
    monkeypatch.setattr(cli, "run_winnow", boom)
    ws = RunWorkspace(tmp_path, "r1")
    cli._execute(config, _NoScrapeIA(), None, ws, criteria, count=1, auto=True,
                 human_gate=False)


def test_unknown_pinned_key_raises(tmp_path: Path, monkeypatch):
    with pytest.raises(LlamaError, match="ts-gone"):
        _execute(tmp_path, monkeypatch,
                 Criteria(query="q", artists=["GratefulDead", "ts-gone"]))


def test_unknown_collection_key_raises(tmp_path: Path, monkeypatch):
    with pytest.raises(LlamaError, match="ts-gone"):
        _execute(tmp_path, monkeypatch, Criteria(query="q", collection="ts-gone"))


def test_execute_passes_allowlist_to_search(tmp_path: Path, monkeypatch):
    config = Config(root=tmp_path, taperssection=TaperssectionConfig(artists=[PHISH]))
    seen = {}

    def search(ws, ia, criteria, artists=None, force=False, jerrybase_enabled=True,
               allowlist=None):
        seen["allowlist"] = allowlist
        return []

    monkeypatch.setattr(cli, "run_search", search)
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: [])
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"score_reviews": None, "light_research": None})
    ws = RunWorkspace(tmp_path, "r1")
    cli._execute(config, _NoScrapeIA(), None, ws,
                 Criteria(query="q", collection="ts-phish"), count=1, auto=True,
                 human_gate=False)
    assert seen["allowlist"].require("ts-phish").name == "Phish"
