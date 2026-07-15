"""Live tests against real archive.org. Run explicitly: pytest -m live -q"""
import os
from pathlib import Path

import pytest

from llama.grouping import group_candidates
from llama.ia_client import IAClient
from llama.junk import filter_files
from llama.setlist import parse_setlist
from llama.stages.search import SEARCH_FIELDS

IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"

SETLISTFM_KEY = os.environ.get("SETLISTFM_API_KEY")  # read at import: see tests/conftest.py


@pytest.mark.live
def test_search_and_group_real(tmp_path: Path):
    ia = IAClient(cache_dir=tmp_path / "cache")
    docs = ia.search(
        "mediatype:etree AND collection:GratefulDead AND date:[1973-06-01 TO 1973-06-30]",
        SEARCH_FIELDS, rows=100,
    )
    assert docs, "no search results from archive.org"
    cands = group_candidates("GratefulDead", docs)
    assert any(c.performance_id == "GratefulDead/1973-06-10" for c in cands)


@pytest.mark.live
def test_real_item_spam_is_filtered(tmp_path: Path):
    ia = IAClient(cache_dir=tmp_path / "cache")
    md = ia.metadata(IDENT)
    kept, excluded = filter_files(md["files"])
    kept_names = [f["name"] for f in kept]
    assert all(n.startswith("gd73-06-10") for n in kept_names)
    assert len(kept_names) >= 20  # full show, all discs
    parsed = parse_setlist(str(md["metadata"].get("description", "")))
    assert parsed.confidence in ("high", "medium")


@pytest.mark.live
@pytest.mark.skipif(not SETLISTFM_KEY, reason="needs SETLISTFM_API_KEY")
def test_setlistfm_live_winterland_1974(tmp_path):
    from llama.setlistfm import SetlistFMClient

    c = SetlistFMClient(tmp_path / "cache", SETLISTFM_KEY)
    got = c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena",
                    city="San Francisco, CA")
    assert got is not None
    songs = [s["name"] for st in got["sets"]["set"] for s in st["song"]]
    assert any("Dark Star" in s for s in songs)


@pytest.mark.live
def test_scrape_api_shape(tmp_path):
    """One real scrape request: the collections pass returns thousands of
    artist docs with the fields the index build depends on."""
    from llama.artist_index import COLLECTIONS_QUERY
    from llama.ia_client import IAClient

    ia = IAClient(cache_dir=tmp_path / "cache")
    docs = ia.scrape(COLLECTIONS_QUERY, ["identifier", "title", "downloads"])
    assert len(docs) > 5000
    sample = docs[0]
    assert "identifier" in sample
