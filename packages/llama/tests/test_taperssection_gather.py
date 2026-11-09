"""Task 6b: gather naming and the title venue (spec "Naming and keys": the
display name is the artist everywhere a human or LLM sees one; gather matches
on every spelling; spec "Search and grouping": the venue from the title is a
candidate-level fallback only).

For a `ts-` candidate `Show.artist` is the entry's `name`, setlist.fm is looked
up by `entry.setlistfm or entry.name`, and every artist-matching use gets the
entry's matching names plus the item's creator. An LMA candidate keys exactly
as before, allowlist or not."""
import copy
import json
from pathlib import Path

import pytest

import fixture_library
from llama import setlistfm as slfm
from llama.adjudicator.bundle import build_bundle
from llama.config import Config, TaperssectionArtist, TaperssectionConfig
from llama.errors import LlamaError
from llama.models import Candidate, Criteria, Provenance, RecordingSummary, Show
from llama.stages.gather import compute_gather, gather_names
from llama.stages.search import run_search
from llama.taperssection import Allowlist
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, write_artifact

FIXTURES = Path(__file__).parent / "fixtures"
G_IDENT = "jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16"
G_DATE = "1982-06-24"     # two JGB events in jerrybase (early + late, Capitol Theatre)
GD_IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"

GARCIA = TaperssectionArtist(name="Jerry Garcia", creators=["Garcia, Jerry", "Jerry Garcia Band"],
                             lineages=["sbd", "aud"], jerrybase="Jerry Garcia Band",
                             setlistfm="Jerry Garcia Band")
PHISH = TaperssectionArtist(name="Phish", creators=["Phish"], lineages=["aud"])


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries)))


def _garcia_md(creator="Garcia, Jerry", first_title=None) -> dict:
    md = json.loads((FIXTURES / f"{G_IDENT}.json").read_text())
    md["metadata"]["creator"] = creator
    if first_title is not None:
        for f in md["files"]:
            if f["name"].startswith("jgb1982-06-24B-d1t01."):
                f["title"] = first_title
    return md


class _IA:
    def __init__(self, md):
        self.md = md

    def metadata(self, identifier):
        return self.md


class _SetlistFM:
    def __init__(self):
        self.calls = []

    def setlist(self, artist, date, venue=None, city=None):
        self.calls.append((artist, date))
        return None


def _cand(collection: str, pid_tail: str = "", *, venue=None, city=None,
          title_venue=None) -> Candidate:
    return Candidate(performance_id=f"{collection}/{G_DATE}{pid_tail}", collection=collection,
                     date=G_DATE, venue=venue, city=city, ts_title_venue=title_venue,
                     recordings=[RecordingSummary(identifier=G_IDENT, creator="Garcia, Jerry")])


def _gather(tmp_path, cand, md=None, **kw):
    return compute_gather(ShowWorkspace(tmp_path / "show"), _IA(md or _garcia_md()), None,
                          cand, G_IDENT, **kw)


def test_show_artist_is_display_name(tmp_path):
    res = _gather(tmp_path, _cand("ts-jerry-garcia"), allowlist=_al(GARCIA))
    assert res.show.artist == "Jerry Garcia"
    # An LMA collection with the same item keeps the creator, allowlist or not.
    lma = _gather(tmp_path, _cand("JerryGarcia"), allowlist=_al(GARCIA))
    assert lma.show.artist == "Garcia, Jerry"


def test_gather_names_ts_and_lma():
    al = _al(GARCIA)
    ts = gather_names("ts-jerry-garcia", "Jerry Garcia", al)
    assert ts.display == "Jerry Garcia"
    assert ts.setlistfm == "Jerry Garcia Band"
    assert ts.matching == ("Jerry Garcia", "Garcia, Jerry", "Jerry Garcia Band")
    lma = gather_names("JerryGarcia", "Garcia, Jerry", al)
    assert (lma.display, lma.setlistfm, lma.matching) == ("Garcia, Jerry", "Garcia, Jerry",
                                                          ("Garcia, Jerry",))
    no_slfm = gather_names("ts-phish", "Phish", _al(PHISH))
    assert no_slfm.setlistfm == "Phish"


def test_jgb_banner_title_cleaned(tmp_path):
    md = _garcia_md(first_title="Jerry Garcia Band - Sugaree")
    res = _gather(tmp_path, _cand("ts-jerry-garcia"), md=md, allowlist=_al(GARCIA))
    assert res.show.tracks[0].title == "Sugaree"
    # The same tape under an LMA collection matches on the creator alone: the
    # "Jerry Garcia Band - " banner is not its artist, so it stays.
    lma = _gather(tmp_path, _cand("JerryGarcia"), md=copy.deepcopy(md), allowlist=_al(GARCIA))
    assert lma.show.tracks[0].title == "Jerry Garcia Band - Sugaree"


def test_description_banner_dropped_on_every_matching_name():
    from llama.models import ParsedSetlist, SetlistItem
    from llama.stages.gather import _drop_artist_items
    items = [SetlistItem(title=t, normalized=t.lower(), set="1")
             for t in ("JERRY GARCIA BAND", "Sugaree", "Jerry Garcia")]
    parsed = ParsedSetlist(items=items)
    one = _drop_artist_items(parsed, ("Jerry Garcia",))
    assert [i.title for i in one.items] == ["JERRY GARCIA BAND", "Sugaree"]
    both = _drop_artist_items(parsed, ("Jerry Garcia", "Jerry Garcia Band"))
    assert [i.title for i in both.items] == ["Sugaree"]


def test_compute_gather_ts_without_allowlist_raises(tmp_path):
    for al in (None, Allowlist.empty()):
        with pytest.raises(LlamaError):
            _gather(tmp_path, _cand("ts-jerry-garcia"), allowlist=al)
    with pytest.raises(LlamaError):
        _gather(tmp_path, _cand("ts-unknown"), allowlist=_al(GARCIA))


def test_setlistfm_looked_up_by_entry_setlistfm_or_name(tmp_path):
    client = _SetlistFM()
    _gather(tmp_path, _cand("ts-jerry-garcia"), allowlist=_al(GARCIA), setlistfm=client)
    plain = GARCIA.model_copy(update={"setlistfm": None})
    _gather(tmp_path, _cand("ts-jerry-garcia"), allowlist=_al(plain), setlistfm=client)
    _gather(tmp_path, _cand("JerryGarcia"), allowlist=_al(GARCIA), setlistfm=client)
    assert client.calls == [("Jerry Garcia Band", G_DATE), ("Jerry Garcia", G_DATE),
                            ("Garcia, Jerry", G_DATE)]


def _ts_bundle_show(tmp_path, entry):
    """A library show re-labelled as a ts show of `entry`, as gather writes one."""
    ws, show = fixture_library.library_show(tmp_path, held=True)
    show = show.model_copy(update={"artist": entry.name})
    write_artifact(ws.show, show)
    prov = read_model(ws.provenance, Provenance)
    cand = prov.candidate.model_copy(update={"collection": "ts-jerry-garcia",
                                             "performance_id": f"ts-jerry-garcia/{show.date}"})
    write_artifact(ws.provenance, prov.model_copy(update={"candidate": cand}))
    ws.selection.write_text(json.dumps({"identifier": GD_IDENT, "scores": {}}))
    md = json.loads((FIXTURES / "gd73_metadata.json").read_text())
    return ws, show, _IA(md)


def test_bundle_setlistfm_key_matches_gather(tmp_path):
    client = _SetlistFM()
    cfg = Config(root=tmp_path, jerrybase={"enabled": False})
    ws, show, ia = _ts_bundle_show(tmp_path, GARCIA)
    _gather(tmp_path / "g", _cand("ts-jerry-garcia"), allowlist=_al(GARCIA), setlistfm=client)
    gather_name = client.calls[0][0]
    (tmp_path / "cache" / f"{slfm.cache_key(gather_name, show.date)}.json").write_text(
        json.dumps({"setlist": [{"sets": {"set": [{"song": [{"name": "Sugaree"}]}]}}]}))
    rows = build_bundle(ws, ia, cfg, allowlist=_al(GARCIA)).sections["setlistfm"]
    assert len(rows) == 1 and "Sugaree" in rows[0].text
    with pytest.raises(LlamaError):
        build_bundle(ws, ia, cfg)


def test_jerrybase_venue_beats_title_venue(tmp_path):
    cand = _cand("ts-jerry-garcia", "/e1",
                 title_venue=("Madison Square Garden", "New York, NY"))
    res = _gather(tmp_path, cand, allowlist=_al(GARCIA), jerrybase_enabled=True)
    assert res.show.venue == "Capitol Theatre"
    assert res.show.venue_source == "jerrybase"
    assert not [f for f in res.show.review_flags if "venue" in f or "city" in f]


def test_title_venue_fills_empty_venue(tmp_path):
    cand = _cand("ts-jerry-garcia", title_venue=("Capitol Theatre", "Passaic, NJ"))
    res = _gather(tmp_path, cand, allowlist=_al(GARCIA), jerrybase_enabled=False)
    assert (res.show.venue, res.show.city) == ("Capitol Theatre", "Passaic, NJ")
    assert res.show.venue_source == "title"
    assert not [f for f in res.show.review_flags if "venue" in f or "city" in f]


def test_title_venue_never_replaces_a_vote_venue(tmp_path):
    cand = _cand("ts-jerry-garcia", venue="Capitol Theater", city="Passaic, NJ",
                 title_venue=("Somewhere Else", "Elsewhere, XX"))
    res = _gather(tmp_path, cand, allowlist=_al(GARCIA), jerrybase_enabled=False)
    assert (res.show.venue, res.show.city, res.show.venue_source) == (
        "Capitol Theater", "Passaic, NJ", "item")


def test_title_venue_keeps_a_vote_city(tmp_path):
    cand = _cand("ts-jerry-garcia", city="Passaic, NJ", title_venue=("Capitol Theatre", None))
    res = _gather(tmp_path, cand, allowlist=_al(GARCIA), jerrybase_enabled=False)
    assert (res.show.venue, res.show.city) == ("Capitol Theatre", "Passaic, NJ")


def test_lma_gather_unchanged(tmp_path):
    md = json.loads((FIXTURES / "gd73_metadata.json").read_text())
    cand = Candidate(performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
                     date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
                     recordings=[RecordingSummary(identifier=GD_IDENT)])
    outs = []
    for i, al in enumerate((None, _al(GARCIA, PHISH))):
        res = compute_gather(ShowWorkspace(tmp_path / f"s{i}"), _IA(copy.deepcopy(md)), None,
                             cand, GD_IDENT, jerrybase_enabled=True, setlistfm=_SetlistFM(),
                             allowlist=al)
        outs.append((res.show.model_dump_json(), res.notes, res.title_paths, res.needs_llm))
    assert outs[0] == outs[1]
    assert json.loads(outs[0][0])["artist"] == "Grateful Dead"


# --- search: ts_title_venue on the candidate ------------------------------------

def _phish_doc(ident, title, date="1997-12-29"):
    return {"identifier": ident, "title": title, "date": date + "T00:00:00Z",
            "creator": "Phish", "addeddate": "2020-01-01T00:00:00Z",
            "description": "", "downloads": 10, "lineage": "aud"}


class _ScrapeIA:
    def __init__(self, by_query):
        self.by_query = by_query

    def scrape(self, query, fields, count=10000):
        return next((docs for needle, docs in self.by_query.items() if needle in query), [])


def test_search_sets_most_common_title_venue_for_ts_only(tmp_path):
    ts_docs = [
        _phish_doc("ph1", "Phish - 1997-12-29 - Madison Square Garden - New York, NY"),
        _phish_doc("ph2", "Phish Live at Madison Square Garden, New York, NY on 1997-12-29"),
        _phish_doc("ph3", "Phish - 1997-12-29 - MSG - New York, NY"),
        _phish_doc("ph4", "Phish 12/29/97"),
    ]
    lma_docs = [{"identifier": "jip1997-12-29", "date": "1997-12-29T00:00:00Z",
                 "title": "Jazz Is Phish - 1997-12-29 - Some Club - Boston, MA"}]
    ia = _ScrapeIA({"collection:taperssection": ts_docs, "collection:JazzIsPhish": lma_docs})
    artists = [{"identifier": "JazzIsPhish"}, {"identifier": "ts-phish"}]
    cands = run_search(RunWorkspace(tmp_path, "r1"), ia, Criteria(query="q"),
                       artists=artists, allowlist=_al(PHISH))
    by = {c.collection: c for c in cands}
    venue, city = by["ts-phish"].ts_title_venue
    assert venue == "Madison Square Garden"
    assert by["JazzIsPhish"].ts_title_venue is None


def test_search_ts_title_venue_none_without_any_parse(tmp_path):
    ia = _ScrapeIA({"collection:taperssection": [_phish_doc("ph4", "Phish 12/29/97")]})
    cands = run_search(RunWorkspace(tmp_path, "r1"), ia,
                       Criteria(query="q", collection="ts-phish"), allowlist=_al(PHISH))
    assert [c.ts_title_venue for c in cands] == [None]
