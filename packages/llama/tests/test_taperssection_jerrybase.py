"""Task 6a: jerrybase routing by candidate key (spec "Search and grouping",
the jerrybase paragraph). An allowlisted synthetic key resolves to the entry's
optional `jerrybase` artist; every LMA collection passes its fallback through
unchanged, whatever its creator is called."""
import json
from pathlib import Path

import pytest

from llama import jerrybase
from llama.config import TaperssectionArtist, TaperssectionConfig
from llama.errors import LlamaError
from llama.grouping import group_candidates
from llama.jerrybase import jerrybase_artist
from llama.models import Candidate, Criteria, RecordingSummary
from llama.stages.gather import compute_gather
from llama.stages.winnow import _has_songs
from llama.taperssection import Allowlist
from llama.workspace import ShowWorkspace

FIXTURES = Path(__file__).parent / "fixtures"
G_IDENT = "jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16"
G_DATE = "1982-06-24"     # two JGB events in jerrybase (early + late, Capitol Theatre)

GARCIA = TaperssectionArtist(name="Jerry Garcia", creators=["Jerry Garcia"],
                             lineages=["sbd", "aud"], jerrybase="Jerry Garcia Band")
PHISH = TaperssectionArtist(name="Phish", creators=["Phish"], lineages=["aud"])


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries)))


class _IA:
    def __init__(self):
        self.md = json.loads((FIXTURES / f"{G_IDENT}.json").read_text())

    def metadata(self, identifier):
        return self.md


def _garcia_candidate(collection: str, pid_tail: str = "/e1") -> Candidate:
    # venue/city None: an event that resolves enriches the venue from jerrybase,
    # which is the observable that the event reached gather.
    return Candidate(performance_id=f"{collection}/{G_DATE}{pid_tail}", collection=collection,
                     date=G_DATE, venue=None, city=None,
                     recordings=[RecordingSummary(identifier=G_IDENT, creator="Jerry Garcia")])


def test_jerrybase_artist_maps_key_and_passes_through():
    al = _al(GARCIA)
    assert jerrybase_artist("ts-jerry-garcia", "Jerry Garcia", al) == "Jerry Garcia Band"
    assert jerrybase_artist("GratefulDead", "Grateful Dead", al) == "Grateful Dead"


def test_ts_key_entry_without_jerrybase_returns_fallback():
    assert jerrybase_artist("ts-phish", "Phish", _al(PHISH, GARCIA)) == "Phish"


def test_lma_creator_named_jerry_garcia_unchanged():
    # Keys only on the collection: an LMA item whose creator is exactly the
    # allowlisted name keeps today's lookup key, with or without an allowlist.
    for al in (None, Allowlist.empty(), _al(GARCIA)):
        assert jerrybase_artist("JerryGarcia", "Jerry Garcia", al) == "Jerry Garcia"
        assert jerrybase_artist("Jerry Garcia", "Jerry Garcia", al) == "Jerry Garcia"


def test_ts_key_without_allowlist_raises():
    with pytest.raises(LlamaError):
        jerrybase_artist("ts-jerry-garcia", "x", None)
    with pytest.raises(LlamaError):
        jerrybase_artist("ts-jerry-garcia", "x", Allowlist.empty())
    with pytest.raises(LlamaError):
        jerrybase_artist("ts-unknown", "x", _al(GARCIA))


def test_family_vocabulary_for_garcia():
    al = _al(GARCIA)
    assert jerrybase.is_family_artist(jerrybase_artist("ts-jerry-garcia", "Jerry Garcia", al))
    # ...and the bare creator name is not family: the routing is what grants it.
    assert not jerrybase.is_family_artist("Jerry Garcia")


def test_garcia_e1_candidate_gets_event_in_gather(tmp_path, monkeypatch):
    seen = []
    real = jerrybase.lookup
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: seen.append((a, d)) or real(a, d))
    res = compute_gather(ShowWorkspace(tmp_path / "show"), _IA(), None,
                         _garcia_candidate("ts-jerry-garcia"), G_IDENT,
                         jerrybase_enabled=True, allowlist=_al(GARCIA))
    assert ("Jerry Garcia Band", G_DATE) in seen
    assert res.show.venue_source == "jerrybase"
    assert res.show.venue == "Capitol Theatre"


def test_lma_jerry_garcia_candidate_gets_no_event_in_gather(tmp_path, monkeypatch):
    # The same tape under an LMA collection: the lookup keys on the creator as
    # today, finds no JGB row, and ships no jerrybase venue.
    seen = []
    real = jerrybase.lookup
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: seen.append((a, d)) or real(a, d))
    res = compute_gather(ShowWorkspace(tmp_path / "show"), _IA(), None,
                         _garcia_candidate("JerryGarcia", ""), G_IDENT,
                         jerrybase_enabled=True, allowlist=_al(GARCIA))
    assert seen == [("Jerry Garcia", G_DATE)]
    assert res.show.venue_source == "item"


def test_ts_candidate_in_gather_without_allowlist_raises(tmp_path):
    with pytest.raises(LlamaError):
        compute_gather(ShowWorkspace(tmp_path / "show"), _IA(), None,
                       _garcia_candidate("ts-jerry-garcia"), G_IDENT,
                       jerrybase_enabled=True)


def test_grouping_partitions_a_ts_garcia_two_event_date():
    docs = [{"identifier": G_IDENT, "date": G_DATE}]
    cands = group_candidates("ts-jerry-garcia", docs, allowlist=_al(GARCIA))
    # Two jerrybase events on the date: the per-event path, not the legacy split.
    assert all(c.performance_id.startswith(f"ts-jerry-garcia/{G_DATE}/") for c in cands)
    with pytest.raises(LlamaError):
        group_candidates("ts-jerry-garcia", docs)


def test_winnow_song_constraint_uses_dead_shorthand_for_ts_garcia():
    from llama.models import SetlistConstraint
    cand = Candidate(performance_id=f"ts-jerry-garcia/{G_DATE}", collection="ts-jerry-garcia",
                     date=G_DATE, recordings=[RecordingSummary(identifier="x",
                                                               description="Help On The Way > Slipknot > Franklin's Tower")])
    # Shorthand applies to the query only, and "slip"/"frank" match only via it.
    crit = Criteria(query="q", setlist_constraints=[
        SetlistConstraint(sequence=["Help", "Slip", "Frank"])])
    assert _has_songs(cand, crit, allowlist=_al(GARCIA))
    lma = cand.model_copy(update={"collection": "JerryGarcia"})
    assert not _has_songs(lma, crit, allowlist=_al(GARCIA))
    with pytest.raises(LlamaError):
        _has_songs(cand, crit)
