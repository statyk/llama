from pathlib import Path

from llama.artist_index import build_index

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
