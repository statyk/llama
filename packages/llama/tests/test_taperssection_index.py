"""Task 4: the Taper's Section pass of the artist index, its download store,
the discovery floor bypass, and pinned rosters resolving to ts- keys."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.artist_index as artist_index
import llama.cli as cli
from herder import FakeProvider
from herder.tasks import render
from llama.artist_index import (
    TS_INDEX_FILENAME,
    TS_INDEX_TTL_DAYS,
    build_ts_index,
    filter_artists,
    find_matching_artists,
    load_or_build,
    load_ts_index,
    render_artist_table,
    resolve_artists,
    ts_items,
)
from llama.config import TaperssectionArtist, TaperssectionConfig
from llama.errors import ArtistResolutionError, LlamaError
from llama.models import Criteria
from llama.profiles import Profile, load_profile, save_profile
from llama.prompts import load_prompt
from llama.stages.discover import run_discover
from llama.taperssection import Allowlist
from llama.workspace import RunWorkspace

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "find_artists_pre_ts.txt"

COLLECTIONS = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "CatsUnderTheStarsTributeToJerryGarcia",
     "title": "Cats Under The Stars - Tribute to Jerry Garcia", "downloads": 900},
    {"identifier": "JazzIsPhish", "title": "Jazz Is Phish", "downloads": 1200},
]
ITEMS = (
    [{"identifier": f"gd{i}", "collection": ["GratefulDead"], "year": "1973"} for i in range(30)]
    + [{"identifier": "cats1", "collection": ["CatsUnderTheStarsTributeToJerryGarcia"], "year": "2015"}]
    + [{"identifier": "jip1", "collection": ["JazzIsPhish"], "year": "2016"}]
)

PEARL_JAM = [
    {"identifier": "pj2000-08-03", "creator": "Pearl Jam", "date": "2000-08-03T00:00:00Z",
     "year": "2000", "downloads": 400, "addeddate": "2020-01-01T00:00:00Z"},
    {"identifier": "pj2000-08-03.aud2", "creator": "The Pearl Jam", "date": "2000-08-03",
     "year": 2000, "downloads": 100, "addeddate": "2021-01-01T00:00:00Z"},
    {"identifier": "pj2003-04-01", "creator": ["Pearl Jam"], "date": "2003-04-01",
     "year": "2003", "downloads": 50, "addeddate": "2022-05-01T00:00:00Z"},
    # a tribute band whose creator merely contains the name: dropped
    {"identifier": "vitalogy2019", "creator": "Vitalogy: Pearl Jam Tribute", "date": "2019-01-01",
     "year": "2019", "downloads": 9999, "addeddate": "2019-02-01T00:00:00Z"},
]
GARCIA = [
    {"identifier": f"jg{i}", "creator": "Jerry Garcia", "date": f"1976-12-{10 + i:02d}",
     "year": "1976", "downloads": 10, "addeddate": "2023-01-01T00:00:00Z"} for i in range(5)
]
OTHER = [  # what an unfiltered / wrong-query page looks like
    {"identifier": f"x{i}", "creator": f"Some Band {i}", "date": "2001-01-01", "year": "2001",
     "downloads": 1, "addeddate": "2020-01-01"} for i in range(20)
]


class FakeIA:
    """Answers the LMA queries from COLLECTIONS/ITEMS and the taperssection
    queries by creator; `ts_pages` overrides per-creator answers in order."""

    def __init__(self, ts_pages=None):
        self.ts_pages = {k: list(v) for k, v in (ts_pages or {}).items()}
        self.queries = []

    def scrape(self, query, fields, count=10000):
        self.queries.append((query, tuple(fields)))
        if "mediatype:collection" in query:
            return COLLECTIONS
        if "collection:etree" in query:
            return ITEMS
        assert "collection:taperssection" in query and "mediatype:audio" in query
        for who, pages in self.ts_pages.items():
            if f'"{who}"' in query and pages:
                return pages.pop(0)
        if '"Pearl Jam"' in query:
            return PEARL_JAM
        if '"Jerry Garcia"' in query:
            return GARCIA
        return []

    def ts_queries(self):
        return [q for q, _ in self.queries if "taperssection" in q]


def _entry(name, creators=None, **kw):
    return TaperssectionArtist(name=name, creators=creators or [name], lineages=["aud"], **kw)


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries)))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(artist_index, "_sleep", lambda s: None)


# ---- the ts pass -----------------------------------------------------------


def test_ts_index_keeps_exact_creators_only():
    al = _al(_entry("Pearl Jam"))
    ia = FakeIA()
    data = build_ts_index(ia, al)
    q, fields = ia.queries[0]
    assert q == 'collection:taperssection AND mediatype:audio AND creator:("Pearl Jam")'
    assert set(fields) == {"identifier", "creator", "date", "year", "downloads", "addeddate"}
    [row] = data["artists"]
    assert row == {"identifier": "ts-pearl-jam", "title": "Pearl Jam", "recordings": 3,
                   "year_min": 2000, "year_max": 2003, "downloads": 550, "allowlisted": True}
    items = data["items"]["ts-pearl-jam"]
    assert sorted(items) == ["2000-08-03", "2003-04-01"]
    assert [i["identifier"] for i in items["2000-08-03"]] == ["pj2000-08-03", "pj2000-08-03.aud2"]
    assert items["2003-04-01"] == [{"identifier": "pj2003-04-01", "downloads": 50,
                                   "addeddate": "2022-05-01T00:00:00Z"}]
    assert "vitalogy2019" not in json.dumps(data)
    assert data["allowlist"] == al.fingerprint()
    datetime.fromisoformat(data["built_at"])


def test_ts_query_ors_every_creator():
    al = _al(_entry("Jerry Garcia", creators=["Jerry Garcia", "Jerry Garcia Band"]))
    ia = FakeIA()
    build_ts_index(ia, al)
    assert ia.ts_queries() == [
        'collection:taperssection AND mediatype:audio AND creator:("Jerry Garcia" OR "Jerry Garcia Band")'
    ]


def test_ts_items_reads_one_key():
    data = build_ts_index(FakeIA(), _al(_entry("Pearl Jam")))
    assert set(ts_items(data, "ts-pearl-jam")) == {"2000-08-03", "2003-04-01"}
    assert ts_items(data, "ts-nobody") == {}
    assert ts_items({"artists": [], "items": {}}, "ts-pearl-jam") == {}


def test_ts_index_retries_suspect_empty_scrape():
    ia = FakeIA(ts_pages={"Pearl Jam": [[], []]})
    data = build_ts_index(ia, _al(_entry("Pearl Jam")))
    assert len(ia.ts_queries()) == 3
    assert data["artists"][0]["recordings"] == 3


def test_ts_index_rejects_wrong_query_page():
    # the endpoint once served another query's page: retried, not aggregated
    ia = FakeIA(ts_pages={"Pearl Jam": [OTHER + PEARL_JAM[:1]]})
    data = build_ts_index(ia, _al(_entry("Pearl Jam")))
    assert len(ia.ts_queries()) == 2
    assert data["artists"][0]["recordings"] == 3


def test_ts_index_still_empty_raises_naming_entry_and_caches_nothing(tmp_path):
    ia = FakeIA(ts_pages={"Pearl Jam": [[]] * 10})
    al = _al(_entry("Jerry Garcia"), _entry("Pearl Jam"))
    with pytest.raises(LlamaError, match="Pearl Jam"):
        load_ts_index(ia, tmp_path, al)
    assert len([q for q in ia.ts_queries() if "Pearl Jam" in q]) == artist_index.TS_SCRAPE_ATTEMPTS
    assert not (tmp_path / TS_INDEX_FILENAME).exists()


def test_ts_index_no_exact_creator_raises():
    # a plausible page (creators contain the name) whose exact filter keeps nothing
    ia = FakeIA(ts_pages={"Pearl Jam": [PEARL_JAM[3:]] * 10})
    with pytest.raises(LlamaError, match="Pearl Jam"):
        build_ts_index(ia, _al(_entry("Pearl Jam")))


def test_failed_rebuild_keeps_stale_index_with_same_allowlist(tmp_path, caplog):
    al = _al(_entry("Pearl Jam"))
    good = load_ts_index(FakeIA(), tmp_path, al)
    later = datetime.now(timezone.utc) + timedelta(days=TS_INDEX_TTL_DAYS + 1)
    flaky = FakeIA(ts_pages={"Pearl Jam": [[]] * 10})
    got = load_ts_index(flaky, tmp_path, al, now=later)
    assert flaky.ts_queries()  # it did try
    assert got == good
    assert "stale" in caplog.text


def test_failed_rebuild_after_allowlist_change_raises(tmp_path):
    load_ts_index(FakeIA(), tmp_path, _al(_entry("Pearl Jam")))
    flaky = FakeIA(ts_pages={"Jerry Garcia": [[]] * 10})
    with pytest.raises(LlamaError, match="Jerry Garcia"):
        load_ts_index(flaky, tmp_path, _al(_entry("Pearl Jam"), _entry("Jerry Garcia")))


def test_ts_index_rebuilds_on_allowlist_change(tmp_path):
    al = _al(_entry("Pearl Jam"))
    ia = FakeIA()
    load_ts_index(ia, tmp_path, al)
    assert len(ia.ts_queries()) == 1
    load_ts_index(ia, tmp_path, al)  # unchanged: cached
    assert len(ia.ts_queries()) == 1
    al_note = _al(_entry("Pearl Jam", note="a note only"))
    load_ts_index(ia, tmp_path, al_note)  # note-only edit: same fingerprint
    assert len(ia.ts_queries()) == 1
    al2 = _al(_entry("Pearl Jam"), _entry("Jerry Garcia"))
    got = load_ts_index(ia, tmp_path, al2)
    assert len(ia.ts_queries()) == 3
    assert [a["identifier"] for a in got["artists"]] == ["ts-jerry-garcia", "ts-pearl-jam"]
    load_ts_index(ia, tmp_path, al2, refresh=True)
    assert len(ia.ts_queries()) == 5


def test_ts_index_rebuilds_after_ttl(tmp_path):
    al = _al(_entry("Pearl Jam"))
    ia = FakeIA()
    load_ts_index(ia, tmp_path, al)
    path = tmp_path / TS_INDEX_FILENAME
    data = json.loads(path.read_text())
    data["built_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    path.write_text(json.dumps(data))
    load_ts_index(ia, tmp_path, al)
    assert len(ia.ts_queries()) == 2


def test_empty_allowlist_ts_index_does_no_io(tmp_path):
    ia = FakeIA()
    assert load_ts_index(ia, tmp_path, Allowlist.empty()) == {"artists": [], "items": {}}
    assert load_ts_index(ia, tmp_path, None) == {"artists": [], "items": {}}
    assert ia.queries == []
    assert list(tmp_path.iterdir()) == []


def test_empty_allowlist_no_io_and_lma_index_identical(tmp_path):
    today = load_or_build(FakeIA(), tmp_path / "a")
    ia = FakeIA()
    got = load_or_build(ia, tmp_path / "b", allowlist=Allowlist.empty())
    assert got == today
    assert ia.ts_queries() == []
    assert not (tmp_path / "b" / TS_INDEX_FILENAME).exists()


def test_populated_allowlist_appends_ts_rows_lma_rows_unchanged(tmp_path):
    today = load_or_build(FakeIA(), tmp_path / "a")
    got = load_or_build(FakeIA(), tmp_path / "b", allowlist=_al(_entry("Jerry Garcia")))
    assert got[: len(today)] == today
    assert [a["identifier"] for a in got[len(today):]] == ["ts-jerry-garcia"]
    assert (tmp_path / "b" / TS_INDEX_FILENAME).exists()


def test_prefix_collision_raises(tmp_path):
    ia = FakeIA()
    COLLECTIONS.append({"identifier": "TS-Phish", "title": "x", "downloads": 1})
    try:
        with pytest.raises(LlamaError, match="TS-Phish"):
            load_or_build(ia, tmp_path, allowlist=_al(_entry("Jerry Garcia")))
        # no allowlist: no check, today's behaviour
        assert any(a["identifier"] == "TS-Phish" for a in load_or_build(ia, tmp_path))
    finally:
        COLLECTIONS.pop()


# ---- floor bypass and discovery ----------------------------------------------


def test_allowlisted_bypass_floor():
    small = {"identifier": "ts-nin", "title": "Nine Inch Nails", "recordings": 5,
             "downloads": 300, "year_min": 2000, "year_max": 2009, "allowlisted": True}
    lma_small = {**small, "identifier": "NIN", "allowlisted": False}
    lma_small.pop("allowlisted")
    assert filter_artists([small, lma_small], 25, 50000) == [small]


def test_run_discover_offers_allowlisted_rows(tmp_path):
    al = _al(_entry("Jerry Garcia"))
    ws = RunWorkspace(tmp_path / "runs", "r1")
    reply = json.dumps({"matches": [{"identifier": "ts-jerry-garcia", "reason": "jgb"}]})
    provider = FakeProvider(completes=[reply])
    got = run_discover(ws, provider, FakeIA(), Criteria(query="mellow jerry"),
                       cache_dir=tmp_path / "cache", allowlist=al)
    assert got == [{"identifier": "ts-jerry-garcia", "title": "Jerry Garcia"}]
    prompt = provider.calls[0][1]
    assert "ts-jerry-garcia | Jerry Garcia | 5 recordings" in prompt
    assert "Taper's Section" in prompt


# ---- the find_artists prompt -------------------------------------------------

POOL = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "recordings": 18271,
     "downloads": 226766373, "year_min": 1965, "year_max": 1995},
    {"identifier": "RobynHitchcock", "title": "Robyn Hitchcock", "recordings": 985,
     "downloads": 1311958, "year_min": 1996, "year_max": 2014},
]
GOLDEN_QUERY = "jangly college rock, not blues"


def test_find_artists_prompt_unchanged_without_allowlisted_rows():
    fake = FakeProvider(completes=[json.dumps({"matches": []})])
    find_matching_artists(fake, POOL, GOLDEN_QUERY, max_results=5)
    assert fake.calls[0][1] == GOLDEN.read_text()


def test_find_artists_prompt_names_ts_artists_when_present():
    ts = {"identifier": "ts-phish", "title": "Phish", "recordings": 900, "downloads": 5,
          "year_min": 1988, "year_max": 2024, "allowlisted": True}
    fake = FakeProvider(completes=[json.dumps({"matches": []})])
    find_matching_artists(fake, POOL + [ts], GOLDEN_QUERY, max_results=5)
    prompt = fake.calls[0][1]
    assert prompt != GOLDEN.read_text()
    assert "Taper's Section" in prompt and "eligible" in prompt
    # the only difference is the one added sentence (and the ts row's table line)
    assert prompt.count("Taper's Section") == 1
    table_line = render_artist_table([ts])
    sentence = artist_index.TS_INVENTORY_NOTE
    assert prompt.replace(sentence, "").replace("\n" + table_line, "") == GOLDEN.read_text()


# ---- pinned rosters ------------------------------------------------------------

LMA_INDEX = [
    {"identifier": "CatsUnderTheStarsTributeToJerryGarcia",
     "title": "Cats Under The Stars - Tribute to Jerry Garcia"},
    {"identifier": "JazzIsPhish", "title": "Jazz Is Phish"},
    {"identifier": "Galactic", "title": "Galactic"},
]
TS_ROWS = [
    {"identifier": "ts-jerry-garcia", "title": "Jerry Garcia", "allowlisted": True},
    {"identifier": "ts-phish", "title": "Phish", "allowlisted": True},
]


def test_pin_jerry_garcia_resolves_to_ts_key():
    # today, with no allowlist, it pins the tribute band by unique substring
    assert resolve_artists(LMA_INDEX, ["Jerry Garcia"])[0]["identifier"] == \
        "CatsUnderTheStarsTributeToJerryGarcia"
    al = _al(_entry("Jerry Garcia", creators=["Jerry Garcia", "Jerry Garcia Band"]), _entry("Phish"))
    index = LMA_INDEX + TS_ROWS
    assert [a["identifier"] for a in resolve_artists(index, ["Jerry Garcia"], al)] == ["ts-jerry-garcia"]
    # a listed creator spelling resolves to the entry too
    assert resolve_artists(index, ["jerry garcia band"], al)[0]["identifier"] == "ts-jerry-garcia"
    assert resolve_artists(index, ["phish"], al)[0]["identifier"] == "ts-phish"


def test_lma_substring_pin_unchanged_with_allowlist():
    al = _al(_entry("Jerry Garcia"), _entry("Phish"))
    index = LMA_INDEX + TS_ROWS
    for name in ["Cats Under", "jazz is", "galactic", "JazzIsPhish", "tribute to jerry"]:
        assert resolve_artists(index, [name], al) == resolve_artists(LMA_INDEX, [name])
    # "jerry" would also be a substring of the ts row: ts rows sit outside that rung
    assert resolve_artists(index, ["jerry"], al)[0]["identifier"] == \
        "CatsUnderTheStarsTributeToJerryGarcia"


def test_allowlisted_name_missing_from_index_raises():
    al = _al(_entry("Jerry Garcia"))
    with pytest.raises(ArtistResolutionError, match="ts-jerry-garcia"):
        resolve_artists(LMA_INDEX, ["Jerry Garcia"], al)


# ---- cli wiring ----------------------------------------------------------------

runner = CliRunner()


def _cli(tmp_path, monkeypatch, provider=None):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n\n[[taperssection.artists]]\nname = "Jerry Garcia"\n'
        'creators = ["Jerry Garcia"]\nlineages = ["aud"]\n')
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: FakeIA())
    if provider is not None:
        monkeypatch.setattr(cli, "provider_ladder", lambda config, task: provider)
    return ["--config", str(tmp_path / "config.toml")]


def test_artists_cmd_lists_allowlisted_row_past_floor(tmp_path, monkeypatch):
    cfg = _cli(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [*cfg, "artists"])
    assert result.exit_code == 0, result.output
    assert "Jerry Garcia" in result.output and "5 rec" in result.output  # 5 < floor 25


def test_profile_artists_set_pins_ts_key(tmp_path, monkeypatch):
    cfg = _cli(tmp_path, monkeypatch)
    save_profile(tmp_path, Profile(name="jg", criteria=Criteria(query="jerry")))
    result = runner.invoke(cli.app, [*cfg, "profile", "artists", "jg", "--set", "Jerry Garcia"])
    assert result.exit_code == 0, result.output
    assert load_profile(tmp_path, "jg").criteria.artists == ["ts-jerry-garcia"]


# ---- fix round 1: a failed ts build never takes down LMA paths; truncation is suspect ----


class FlakyTsIA(FakeIA):
    """LMA queries answer; every taperssection query comes back empty."""

    def scrape(self, query, fields, count=10000):
        if "taperssection" in query:
            self.queries.append((query, tuple(fields)))
            return []
        return super().scrape(query, fields, count)


def test_load_or_build_survives_failed_ts_build(tmp_path, caplog):
    today = load_or_build(FakeIA(), tmp_path / "a")
    ia = FlakyTsIA()
    got = load_or_build(ia, tmp_path / "b", allowlist=_al(_entry("Jerry Garcia")))
    assert got == today
    assert ia.ts_queries()  # it tried
    assert not (tmp_path / "b" / TS_INDEX_FILENAME).exists()
    assert "Jerry Garcia" in caplog.text and "taperssection" in caplog.text


def test_load_ts_index_itself_still_raises(tmp_path):
    with pytest.raises(LlamaError, match="Jerry Garcia"):
        load_ts_index(FlakyTsIA(), tmp_path, _al(_entry("Jerry Garcia")))


def test_resolve_missing_ts_row_mentions_failed_index():
    with pytest.raises(ArtistResolutionError, match="could not be built"):
        resolve_artists(LMA_INDEX, ["Jerry Garcia"], _al(_entry("Jerry Garcia")))


def _flaky_cli(tmp_path, monkeypatch):
    cfg = _cli(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: FlakyTsIA())
    save_profile(tmp_path, Profile(name="p", criteria=Criteria(query="x")))
    return cfg


def test_profile_set_lma_artist_survives_failed_ts_build(tmp_path, monkeypatch):
    cfg = _flaky_cli(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [*cfg, "profile", "artists", "p", "--set", "Grateful Dead"])
    assert result.exit_code == 0, result.output
    assert load_profile(tmp_path, "p").criteria.artists == ["GratefulDead"]


def test_profile_set_ts_artist_with_failed_ts_build_raises_naming_key(tmp_path, monkeypatch):
    cfg = _flaky_cli(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [*cfg, "profile", "artists", "p", "--set", "Jerry Garcia"])
    assert result.exit_code != 0
    assert "ts-jerry-garcia" in str(result.exception) + result.output
    assert load_profile(tmp_path, "p").criteria.artists == []


def test_full_page_multiple_is_suspect_truncation():
    # a bad later page ends the cursor walk at exactly a page multiple
    page = artist_index.TS_SCRAPE_PAGE
    full = [{"identifier": f"pj{i}", "creator": "Pearl Jam", "date": "2000-08-03",
             "year": "2000", "downloads": 1, "addeddate": "2020-01-01"} for i in range(page)]
    ia = FakeIA(ts_pages={"Pearl Jam": [full]})
    data = build_ts_index(ia, _al(_entry("Pearl Jam")))
    assert len(ia.ts_queries()) == 2  # retried
    assert data["artists"][0]["recordings"] == 3
    with pytest.raises(LlamaError, match="Pearl Jam"):
        build_ts_index(FakeIA(ts_pages={"Pearl Jam": [full] * 10}), _al(_entry("Pearl Jam")))
