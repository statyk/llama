"""Task 12 Step 1: offline end-to-end for the Taper's Section allowlist.

`llama get ... --auto` through interpret -> search -> winnow -> select ->
gather -> research -> vet -> brief -> package, with a populated allowlist in
the config, the fake LLM backend and the Task 0 fixtures (real archive.org
metadata for a Phish aud tape and a Garcia late-show soundboard). No live
archive.org, no live LLM: the fake IA serves the fixture to every scrape (the
search query and the taperssection download-index build alike).
"""
import json
from pathlib import Path

from herder import FakeProvider
from typer.testing import CliRunner

import llama.cli as cli
import llama.pipeline as pipeline
from llama import ts_rules
from llama.grouping import _summary

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"
P_IDENT = "phish1997-12-29.003886.newyork.mk41.cmc6.flac1644"
G_IDENT = "jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16"

TS_CONFIG = """
[[taperssection.artists]]
name = "Phish"
creators = ["Phish"]
lineages = ["aud"]

[[taperssection.artists]]
name = "Jerry Garcia"
creators = ["Jerry Garcia"]
lineages = ["sbd", "aud"]
jerrybase = "Jerry Garcia Band"
"""


def _doc(md: dict) -> dict:
    """The fixture item as the scrape API serves it (ISO timestamps)."""
    m = md["metadata"]
    return {"identifier": m["identifier"], "title": m["title"],
            "date": m["date"] + "T00:00:00Z", "year": m["date"][:4],
            "creator": m["creator"], "addeddate": m["addeddate"].replace(" ", "T") + "Z",
            "description": m["description"], "downloads": 1234,
            "avg_rating": None, "num_reviews": 0}


def _fake_ia():
    """Both fixtures, served by creator: a Taper's Section scrape gets the items
    whose creator its query names (the index build needs every entry answered)."""
    mds = {i: json.loads((FIXTURES / f"{i}.json").read_text()) for i in (P_IDENT, G_IDENT)}

    class FakeIA:
        queries: list[str] = []

        def __init__(self, *args, **kwargs):
            pass

        def scrape(self, query, fields, count=10000):
            FakeIA.queries.append(query)
            return [_doc(md) for md in mds.values()
                    if f'"{md["metadata"]["creator"]}"' in query]

        def metadata(self, identifier):
            return mds[identifier]

        def download_file(self, identifier, filename, dest, md5=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x00" * 64)
            return dest

    return FakeIA


def _criteria(key: str, artist: str, day: str) -> str:
    return json.dumps({
        "query": f"{artist} {day}", "collection": key, "artist": artist,
        "date_from": day, "date_to": day, "setlist_constraints": [],
        "soft_preferences": None, "min_avg_rating": 3.5, "min_reviews": 2, "count": 1})


def _assessment(pid: str) -> str:
    return json.dumps({"assessments": [{
        "performance_id": pid, "quality_score": 8.5,
        "non_attendee_evidence": "heavily downloaded for its age",
        "recording_complaints": [], "rationale": "a celebrated run",
        "attribution": "ok", "attribution_reason": None}]})


def _briefing(context: str) -> str:
    return json.dumps({
        "context": context, "significance": "Worth airing.",
        "per_set": {"1": ["Opens hot"]}, "notable_moments": [], "review_sentiment": "Praised.",
        "non_attendee_sentiment": True, "cautions": [], "narration": "full",
        "mentioned_songs": []})


# The Phish fixture's own description defeats the deterministic alignment:
# `parse_setlist` keeps the `s1t01 - ` prefixes and then reads the appended
# "original text file" block as more encore items, so coverage falls under the
# threshold and gather takes its `align_structure` LLM touchpoint (as it would
# in production; this is the LMA parser's behaviour, not the allowlist's). The
# fake answers with the tape's own layout: 9 songs, 5, encore.
_PHISH_SETS = ["1"] * 9 + ["2"] * 5 + ["encore"]
_PHISH_SEGUES = {1, 2, 6, 10, 11}
_PHISH_SONGS = ["NICU", "Golgi Apparatus", "Crossroads", "Cars Trucks Buses", "Train Song",
                "Theme From the Bottom", "Fluffhead", "Dirt", "Run Like an Antelope",
                "Down with Disease", "David Bowie", "Possum", "Tube", "You Enjoy Myself",
                "Good Times Bad Times"]
PHISH_ALIGN = json.dumps({"tracks": [
    {"index": i, "set": s, "segue": i in _PHISH_SEGUES, "matched_title": t}
    for i, (s, t) in enumerate(zip(_PHISH_SETS, _PHISH_SONGS), 1)]})


def _providers(key, artist, day, pid, songs, context, align=()):
    vet = json.dumps({"asserted_songs": songs, "asserted_dates": [day], "context": context})

    def make(config):
        return {
            "interpret": FakeProvider(completes=[_criteria(key, artist, day)]),
            "score_reviews": FakeProvider(completes=[_assessment(pid)]),
            "light_research": FakeProvider(researches=[f"{artist} {day} is well regarded."]),
            "extract_setlist": FakeProvider(),
            "deep_research": FakeProvider(researches=[
                f"## Reputation\nWell regarded.\n## Performance highlights\n{songs[0]}.\n"
                f"## Context\n{context}\n## Recording notes\nAudience tape."]),
            "brief": FakeProvider(completes=[_briefing(context)]),
            "align_structure": FakeProvider(completes=list(align)),
            "vet_research": FakeProvider(completes=[vet]),
        }
    return make


def _run_get(tmp_path, monkeypatch, providers, query):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{TS_CONFIG}')
    monkeypatch.setattr(pipeline, "make_providers", providers)
    monkeypatch.setattr(cli, "make_providers", providers)
    ia = _fake_ia()
    monkeypatch.setattr(cli, "IAClient", ia)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                     "get", query, "--auto", "--name", "e2e"])
    if result.exit_code != 0:
        import traceback
        tb = "".join(traceback.format_exception(*result.exc_info)) if result.exc_info else ""
        raise AssertionError(f"{result.output}\n{tb}")
    return result, ia


def test_phish_aud_fixture_packages_clean(tmp_path, monkeypatch):
    pid = "ts-phish/1997-12-29"
    providers = _providers("ts-phish", "Phish", "1997-12-29", pid,
                           ["You Enjoy Myself", "David Bowie"], "Madison Square Garden run",
                           align=[PHISH_ALIGN])
    result, ia = _run_get(tmp_path, monkeypatch, providers, "Phish 1997-12-29")

    # Every scrape targeted Taper's Section, never the etree path.
    assert ia.queries and all("taperssection" in q for q in ia.queries), ia.queries
    show_dir = tmp_path / "shows" / "ts-phish-1997-12-29"
    show = json.loads((show_dir / "show.json").read_text())
    assert show["artist"] == "Phish"
    assert show["identifier"] == P_IDENT
    assert show["needs_review"] is False, show["review_flags"]
    assert show["review_flags"] == []
    # The two Task 10 holds stay quiet: attribution ok, lineage classified aud.
    prov = json.loads((show_dir / "provenance.json").read_text())
    assert prov["assessment"]["attribution"] == "ok"
    md = json.loads((FIXTURES / f"{P_IDENT}.json").read_text())
    assert ts_rules.classify(_summary(_doc(md), "1997-12-29")) == "aud"

    pkg = show_dir / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["show"]["artist"] == "Phish"
    assert manifest["source"]["performance_id"] == pid
    assert manifest["source"]["identifier"] == P_IDENT
    assert len(manifest["tracks"]) == 15
    assert manifest["tracks"][0]["title"].startswith("NICU")
    assert manifest["briefing"]["vetted"] is True
    ledger = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert ledger[0]["performance_id"] == pid


def test_garcia_fixture_packages_with_jerrybase_evidence(tmp_path, monkeypatch):
    # 1982-06-24 has two JGB events in jerrybase; the late-show tape groups into
    # the second, so the performance id carries /e2.
    pid = "ts-jerry-garcia/1982-06-24/e2"
    providers = _providers("ts-jerry-garcia", "Jerry Garcia", "1982-06-24", pid,
                           ["Sugaree", "Deal"], "Capitol Theatre, Passaic")
    _run_get(tmp_path, monkeypatch, providers, "Jerry Garcia 1982-06-24")

    show_dir = tmp_path / "shows" / "ts-jerry-garcia-1982-06-24-e2"
    show = json.loads((show_dir / "show.json").read_text())
    assert show["artist"] == "Jerry Garcia"
    # jerrybase evidence reached gather through the entry's `jerrybase` key
    # ("Jerry Garcia Band"): the late event's set-1 closer (Run For The Roses)
    # anchors the break, with Deal as the encore.
    assert show["structure"]["alignment"] == "jerrybase"
    assert "set breaks anchored from jerrybase" in show["structure"]["conflicts"]
    assert show["set_breaks"] == [8]
    assert [t["set"] for t in show["tracks"]][-2:] == ["1", "encore"]
    assert show["venue"] == "Capitol Theatre"
    assert show["needs_review"] is False, show["review_flags"]
    manifest = json.loads((show_dir / "package" / "manifest.json").read_text())
    assert manifest["show"]["artist"] == "Jerry Garcia"
    assert manifest["source"]["performance_id"] == pid
    assert manifest["source"]["identifier"] == G_IDENT
