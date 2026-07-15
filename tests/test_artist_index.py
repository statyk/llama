import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from llama.artist_index import build_index, filter_artists, fmt_count, load_or_build
from llama.ia_client import IAError

COLLECTIONS = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "RobynHitchcock", "title": "Robyn Hitchcock", "downloads": 1311958},
    {"identifier": "BackyardBand", "title": "Backyard Band"},  # no downloads field
]

ITEMS = [
    # normal item: attributed to GratefulDead; etree/stream_only ignored
    {"identifier": "gd73-06-10.sbd", "collection": ["GratefulDead", "etree", "stream_only"],
     "year": "1973"},
    {"identifier": "gd77-05-08.sbd", "collection": ["GratefulDead", "etree"], "year": 1977},
    # collection as bare string, not list
    {"identifier": "rh96", "collection": "RobynHitchcock", "year": "1996"},
    # missing year and garbage year: counted, years skipped
    {"identifier": "rh-noyear", "collection": ["RobynHitchcock"]},
    {"identifier": "rh-badyear", "collection": ["RobynHitchcock"], "year": "n/a"},
    # year as list (archive.org quirk)
    {"identifier": "rh14", "collection": ["RobynHitchcock"], "year": ["2014"]},
    # item pointing at an unknown collection: ignored entirely
    {"identifier": "stray", "collection": ["NotAnArtist"], "year": "1999"},
]


class ScrapeStubIA:
    def __init__(self, collections=COLLECTIONS, items=ITEMS):
        self._collections = collections
        self._items = items
        self.queries = []

    def scrape(self, query, fields, count=10000):
        self.queries.append((query, tuple(fields)))
        if "mediatype:collection" in query:
            return self._collections
        return self._items


def by_id(index):
    return {a["identifier"]: a for a in index["artists"]}


def test_build_index_aggregates_recordings_years_downloads():
    index = build_index(ScrapeStubIA())
    artists = by_id(index)
    gd = artists["GratefulDead"]
    assert gd["recordings"] == 2
    assert (gd["year_min"], gd["year_max"]) == (1973, 1977)
    assert gd["downloads"] == 226766373
    rh = artists["RobynHitchcock"]
    assert rh["recordings"] == 4  # string collection, no-year, bad-year, list-year all count
    assert (rh["year_min"], rh["year_max"]) == (1996, 2014)


def test_build_index_zero_item_artist_and_missing_downloads():
    artists = by_id(build_index(ScrapeStubIA()))
    bb = artists["BackyardBand"]
    assert bb["recordings"] == 0
    assert bb["downloads"] == 0
    assert bb["year_min"] is None and bb["year_max"] is None
    assert "NotAnArtist" not in artists


def test_build_index_queries_and_timestamp():
    ia = ScrapeStubIA()
    index = build_index(ia)
    assert ia.queries[0][0] == "collection:etree AND mediatype:collection"
    assert ia.queries[1][0] == "collection:etree AND mediatype:etree"
    assert index["built_at"].startswith("20")
    ids = [a["identifier"] for a in index["artists"]]
    assert ids == sorted(ids)


class FailingIA:
    def scrape(self, query, fields, count=10000):
        raise IAError("boom")


def test_load_or_build_builds_and_reuses(tmp_path: Path):
    ia = ScrapeStubIA()
    artists = load_or_build(ia, tmp_path)
    assert {a["identifier"] for a in artists} == {"GratefulDead", "RobynHitchcock", "BackyardBand"}
    assert (tmp_path / "artist_index.json").exists()
    again = load_or_build(FailingIA(), tmp_path)  # fresh file: no scrape happens
    assert again == artists


def test_load_or_build_rebuilds_when_stale(tmp_path: Path):
    load_or_build(ScrapeStubIA(), tmp_path)
    future = datetime.now(timezone.utc) + timedelta(days=31)
    ia = ScrapeStubIA(collections=[{"identifier": "New", "title": "New", "downloads": 1}], items=[])
    artists = load_or_build(ia, tmp_path, now=future)
    assert [a["identifier"] for a in artists] == ["New"]


def test_load_or_build_refresh_forces(tmp_path: Path):
    load_or_build(ScrapeStubIA(), tmp_path)
    ia = ScrapeStubIA(collections=[{"identifier": "New", "title": "New", "downloads": 1}], items=[])
    artists = load_or_build(ia, tmp_path, refresh=True)
    assert [a["identifier"] for a in artists] == ["New"]


def test_load_or_build_keeps_stale_on_failure(tmp_path: Path):
    load_or_build(ScrapeStubIA(), tmp_path)
    future = datetime.now(timezone.utc) + timedelta(days=31)
    artists = load_or_build(FailingIA(), tmp_path, now=future)  # rebuild fails -> stale kept
    assert {a["identifier"] for a in artists} == {"GratefulDead", "RobynHitchcock", "BackyardBand"}


def test_load_or_build_raises_without_any_index(tmp_path: Path):
    with pytest.raises(IAError):
        load_or_build(FailingIA(), tmp_path)


def test_filter_artists_or_semantics():
    artists = [
        {"identifier": "Deep", "recordings": 100, "downloads": 0},
        {"identifier": "Popular", "recordings": 3, "downloads": 90000},
        {"identifier": "Backyard", "recordings": 3, "downloads": 20},
        {"identifier": "EdgeRec", "recordings": 25, "downloads": 0},
        {"identifier": "EdgeDl", "recordings": 0, "downloads": 50000},
    ]
    kept = {a["identifier"] for a in filter_artists(artists, 25, 50000)}
    assert kept == {"Deep", "Popular", "EdgeRec", "EdgeDl"}


def test_fmt_count():
    assert fmt_count(226766373) == "226.8M"
    assert fmt_count(54321) == "54.3k"
    assert fmt_count(950) == "950"
