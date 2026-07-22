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
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY")  # read at import: see tests/conftest.py
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY")  # read at import: see tests/conftest.py


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
    kept, excluded, _ = filter_files(md["files"])
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
def test_scrape_finds_every_recording_of_a_performance(tmp_path: Path):
    """Regression: a single 500-row search page once dropped 5 of Veneta's 7
    copies - including every one whose description carries the set structure."""
    ia = IAClient(cache_dir=tmp_path / "cache")
    docs = ia.scrape(
        "mediatype:etree AND collection:GratefulDead AND date:[1972-08-27 TO 1972-08-27]",
        SEARCH_FIELDS,
    )
    assert len(docs) >= 7
    cands = group_candidates("GratefulDead", docs)
    veneta = next(c for c in cands if c.date == "1972-08-27")
    assert len(veneta.recordings) >= 7


@pytest.mark.live
def test_structure_recovers_from_real_metadata_descriptions(tmp_path: Path):
    """Veneta '72 is three sets; at least one real description must parse to
    multi-set at high confidence (entities, inline markers and all)."""
    ia = IAClient(cache_dir=tmp_path / "cache")
    md = ia.metadata("gd72-08-27.sbd.braverman.16582.sbefail.shnf")
    desc = md["metadata"].get("description") or ""
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    parsed = parse_setlist(str(desc))
    assert parsed.confidence == "high"
    assert {"1", "2", "3"} <= {i.set for i in parsed.items}


@pytest.mark.live
def test_selection_prefers_newest_complete_miller(tmp_path: Path):
    """Regression: GD 1969-11-02 once selected a 6-track fragment over the
    newest complete Charlie Miller sbd (and addeddate misorders the millers,
    so this also pins shnid-based revision ordering)."""
    from llama.models import QualityAssessment
    from llama.stages.select_recording import run_select_recording
    from llama.workspace import ShowWorkspace

    ia = IAClient(cache_dir=tmp_path / "cache")
    docs = ia.scrape(
        "mediatype:etree AND collection:GratefulDead AND date:[1969-11-02 TO 1969-11-02]",
        SEARCH_FIELDS,
    )
    cand = next(c for c in group_candidates("GratefulDead", docs) if c.date == "1969-11-02")
    a = QualityAssessment(performance_id=cand.performance_id, quality_score=9.0, rationale="r")
    chosen = run_select_recording(ShowWorkspace(tmp_path / "s"), ia, cand, a)
    assert chosen == "gd1969-11-02.sbd.miller.32350.sbeok.flac16"


@pytest.mark.live
def test_scrape_api_shape(tmp_path):
    """One real scrape request: the collections pass returns thousands of
    artist docs with the fields the index build depends on."""
    from llama.artist_index import COLLECTIONS_QUERY

    ia = IAClient(cache_dir=tmp_path / "cache")
    docs = ia.scrape(COLLECTIONS_QUERY, ["identifier", "title", "downloads"])
    assert len(docs) > 5000
    sample = docs[0]
    assert "identifier" in sample and "title" in sample and "downloads" in sample


@pytest.mark.live
@pytest.mark.skipif(not ELEVENLABS_KEY, reason="needs ELEVENLABS_API_KEY")
def test_elevenlabs_synthesize_real():
    from llama.tts.elevenlabs import ElevenLabsProvider

    p = ElevenLabsProvider(voice="21m00Tcm4TlvDq8ikWAM",  # "Rachel", a stock voice
                           model="eleven_multilingual_v2", api_key=ELEVENLABS_KEY)
    audio = p.synthesize("Tonight: the Grateful Dead, live at RFK Stadium.")
    assert len(audio) > 10_000                     # a real clip, not an error body
    assert audio[:3] == b"ID3" or audio[:1] == b"\xff"  # playable MP3 framing


@pytest.mark.live
@pytest.mark.skipif(not MISTRAL_KEY, reason="needs MISTRAL_API_KEY")
def test_voxtral_synthesize_real():
    from llama.tts.voxtral import VoxtralProvider

    # "british-dj" is a placeholder preset name pending confirmation against
    # Mistral's real voice catalog when this test is first run live; the
    # same reconciliation applies to the ref_audio/voice_id request fields
    # and the audio_data response field this test exercises end to end.
    with VoxtralProvider(voice="british-dj", api_key=MISTRAL_KEY) as p:
        audio = p.synthesize("Good evening from the archive.")
    assert audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb"  # playable MP3 framing
    assert len(audio) > 1000
