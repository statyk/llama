import json
from pathlib import Path

import httpx

from llama.config import Config
from llama.setlistfm import SetlistFMClient, make_client

WINTERLAND = {
    "id": "abc123",
    "eventDate": "24-02-1974",
    "venue": {"name": "Winterland", "city": {"name": "San Francisco", "stateCode": "CA"}},
    "sets": {"set": [{"song": [{"name": "U.S. Blues"}]}]},
}
OAKLAND = {
    "id": "zzz999",
    "eventDate": "24-02-1974",
    "venue": {"name": "Oakland Coliseum", "city": {"name": "Oakland", "stateCode": "CA"}},
    "sets": {"set": [{"song": [{"name": "Other Song"}]}]},
}


def make(tmp_path: Path, handler) -> SetlistFMClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, headers={"x-api-key": "k"})
    return SetlistFMClient(cache_dir=tmp_path / "cache", api_key="k",
                           client=http, backoff_s=0, rate_limit_s=0)


def test_picks_venue_match_and_caches(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.params["date"] == "24-02-1974"
        return httpx.Response(200, json={"setlist": [OAKLAND, WINTERLAND]})

    c = make(tmp_path, handler)
    got = c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena", city="San Francisco, CA")
    assert got["id"] == "abc123"
    again = c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena", city="San Francisco, CA")
    assert again["id"] == "abc123"
    assert calls["n"] == 1  # second call served from disk cache


def test_no_venue_match_returns_none(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"setlist": [OAKLAND]})

    c = make(tmp_path, handler)
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena", city="San Francisco, CA") is None


def test_no_venue_given_accepts_sole_result_rejects_multiple(tmp_path: Path):
    def one(request):
        return httpx.Response(200, json={"setlist": [WINTERLAND]})

    def two(request):
        return httpx.Response(200, json={"setlist": [WINTERLAND, OAKLAND]})

    assert make(tmp_path / "a", one).setlist("Grateful Dead", "1974-02-24")["id"] == "abc123"
    assert make(tmp_path / "b", two).setlist("Grateful Dead", "1974-02-24") is None


def test_404_is_no_result_and_cached(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    c = make(tmp_path, handler)
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena") is None
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena") is None
    assert calls["n"] == 1  # no-result is a normal outcome: cached


def test_server_error_returns_none_and_is_not_cached(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    c = make(tmp_path, handler)
    assert c.setlist("Grateful Dead", "1974-02-24", venue="Winterland Arena") is None
    assert calls["n"] == 3  # retried
    assert not list((tmp_path / "cache").glob("slfm_*.json"))  # errors not cached


def test_make_client_requires_key(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    assert make_client(Config()) is None
    cfg = Config.model_validate({"setlistfm": {"api_key": "fromtoml"}})
    assert make_client(cfg).api_key == "fromtoml"
    monkeypatch.setenv("SETLISTFM_API_KEY", "fromenv")
    assert make_client(cfg).api_key == "fromenv"
