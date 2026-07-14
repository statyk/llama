import hashlib
import json
from pathlib import Path

import httpx
import pytest

from llama.ia_client import IAClient, IAError


def make_client(tmp_path: Path, handler) -> IAClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return IAClient(cache_dir=tmp_path / "cache", client=http, backoff_s=0, rate_limit_s=0)


def test_search_returns_docs_and_caches(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"response": {"docs": [{"identifier": "gd73-06-10.sbd"}]}})

    ia = make_client(tmp_path, handler)
    docs = ia.search("collection:GratefulDead", ["identifier"])
    assert docs == [{"identifier": "gd73-06-10.sbd"}]
    again = ia.search("collection:GratefulDead", ["identifier"])
    assert again == docs
    assert calls["n"] == 1  # second call served from disk cache


def test_metadata_caches(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"metadata": {"venue": "RFK"}, "files": []})

    ia = make_client(tmp_path, handler)
    assert ia.metadata("gd73-06-10.sbd")["metadata"]["venue"] == "RFK"
    ia.metadata("gd73-06-10.sbd")
    assert calls["n"] == 1


def test_retries_then_succeeds(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"response": {"docs": []}})

    ia = make_client(tmp_path, handler)
    assert ia.search("q", ["identifier"]) == []
    assert calls["n"] == 3


def test_retries_exhausted_raises(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    ia = make_client(tmp_path, handler)
    with pytest.raises(IAError):
        ia.search("q", ["identifier"])


def test_download_verifies_md5(tmp_path: Path):
    body = b"fake audio bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        assert "FOLLOW" not in str(request.url)
        return httpx.Response(200, content=body)

    ia = make_client(tmp_path, handler)
    dest = tmp_path / "out.mp3"
    good = hashlib.md5(body).hexdigest()
    assert ia.download_file("gd73", "d1t01.mp3", dest, md5=good) == dest
    assert dest.read_bytes() == body

    bad_dest = tmp_path / "bad.mp3"
    with pytest.raises(IAError):
        ia.download_file("gd73", "d1t01.mp3", bad_dest, md5="0" * 32)
    assert not bad_dest.exists()
    assert not list(tmp_path.glob("*.part"))


def test_download_url_encodes_filename(tmp_path: Path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.raw_path.decode()
        return httpx.Response(200, content=b"x")

    ia = make_client(tmp_path, handler)
    ia.download_file("gd73", "file with space.mp3", tmp_path / "o.mp3")
    assert "%20" in seen["path"]
