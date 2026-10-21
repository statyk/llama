import hashlib
import json
import logging
import random
from pathlib import Path

import httpx
import pytest

from llama.ia_client import (DOWNLOAD_CONNECT_TIMEOUT_S, DOWNLOAD_DEADLINE_S,
                             DOWNLOAD_STALL_TIMEOUT_S, IAClient, IADownloadError, IAError)


class FakeClock:
    """A monotonic clock that only moves when slept on or advanced by a handler."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_client(tmp_path: Path, handler, *, metadata: dict | None = None,
                clock: FakeClock | None = None) -> IAClient:
    """`metadata`, when given, is served at the metadata URL for every identifier;
    otherwise the metadata request reaches `handler` like any other."""
    def route(request: httpx.Request) -> httpx.Response:
        if metadata is not None and request.url.path.startswith("/metadata/"):
            return httpx.Response(200, json=metadata)
        return handler(request)

    clock = clock or FakeClock()
    http = httpx.Client(transport=httpx.MockTransport(route))
    return IAClient(cache_dir=tmp_path / "cache", client=http, backoff_s=0, rate_limit_s=0,
                    clock=clock, sleep=clock.sleep, rng=random.Random(0))


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


def test_4xx_does_not_retry(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    ia = make_client(tmp_path, handler)
    with pytest.raises(IAError):
        ia.search("q", ["identifier"])
    assert calls["n"] == 1


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


def test_scrape_follows_cursor(tmp_path: Path):
    pages = [
        {"items": [{"identifier": "A"}, {"identifier": "B"}], "count": 2,
         "cursor": "next-1", "total": 3},
        {"items": [{"identifier": "C"}], "count": 1, "total": 3},
    ]
    seen = {"params": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"].append(dict(request.url.params))
        return httpx.Response(200, json=pages[len(seen["params"]) - 1])

    ia = make_client(tmp_path, handler)
    docs = ia.scrape("collection:etree AND mediatype:collection",
                     ["identifier", "title", "downloads"], count=2)
    assert [d["identifier"] for d in docs] == ["A", "B", "C"]
    assert seen["params"][0]["fields"] == "identifier,title,downloads"
    assert seen["params"][0]["count"] == "2"
    assert "cursor" not in seen["params"][0]
    assert seen["params"][1]["cursor"] == "next-1"


def test_scrape_is_not_disk_cached(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [{"identifier": "A"}], "count": 1, "total": 1})

    ia = make_client(tmp_path, handler)
    ia.scrape("q", ["identifier"])
    ia.scrape("q", ["identifier"])
    assert calls["n"] == 2


def test_scrape_client_error_raises(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad"})

    ia = make_client(tmp_path, handler)
    with pytest.raises(IAError):
        ia.scrape("q", ["identifier"])


def test_scrape_non_json_200_raises(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    ia = make_client(tmp_path, handler)
    with pytest.raises(IAError):
        ia.scrape("q", ["identifier"])


def test_scrape_survives_502_burst_beyond_default_retries(tmp_path: Path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 4:
            return httpx.Response(502)
        return httpx.Response(200, json={"items": [{"identifier": "A"}], "count": 1, "total": 1})

    ia = make_client(tmp_path, handler)  # instance default max_retries=3
    docs = ia.scrape("q", ["identifier"])
    assert [d["identifier"] for d in docs] == ["A"]
    assert calls["n"] == 5  # four 502s outlast search's 3 attempts; scrape rides them out


def test_scrape_logs_progress_per_page(tmp_path: Path, caplog):
    pages = [
        {"items": [{"identifier": "A"}, {"identifier": "B"}], "count": 2,
         "cursor": "next-1", "total": 3},
        {"items": [{"identifier": "C"}], "count": 1, "total": 3},
    ]
    n = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(200, json=pages[n["i"] - 1])

    ia = make_client(tmp_path, handler)
    with caplog.at_level(logging.INFO, logger="llama"):
        ia.scrape("q", ["identifier"], count=2)
    assert [r.message for r in caplog.records] == ["scrape: 2/3 docs", "scrape: 3/3 docs"]


# --- download_file: server fallback, classification, schedule ---------------------

BODY = b"the real audio bytes"
BODY_MD5 = hashlib.md5(BODY).hexdigest()
REDIRECT = "https://archive.org/download/x/t.mp3"
SERVER = "https://ia800903.us.archive.org/9/items/x/t.mp3"
SERVER2 = "https://ia600903.us.archive.org/9/items/x/t.mp3"


def item_metadata(*servers: str, md5: str | None = BODY_MD5, size: object = None,
                  name: str = "t.mp3", **extra) -> dict:
    entry: dict = {"name": name}
    if md5 is not None:
        entry["md5"] = md5
    entry["size"] = str(len(BODY)) if size is None else size
    return {"dir": "/9/items/x", "workable_servers": list(servers), "files": [entry], **extra}


def routed(responses: dict, seen: list):
    """A handler answering each URL from `responses`: a status code, bytes (200), or a
    callable taking the request. Records every download URL requested, in order."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        answer = responses[url]
        if callable(answer):
            return answer(request)
        if isinstance(answer, bytes):
            return httpx.Response(200, content=answer)
        return httpx.Response(answer)
    return handler


def no_leftovers(tmp_path: Path) -> bool:
    return not list(tmp_path.rglob("*.part"))


def test_500_on_redirect_falls_back_to_listed_server(tmp_path: Path):
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: 500, SERVER: BODY}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "out" / "t.mp3"
    assert ia.download_file("x", "t.mp3", dest, md5=BODY_MD5) == dest
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER]
    assert no_leftovers(tmp_path)


def test_every_server_failing_raises_after_first_pass_and_deadline(tmp_path: Path):
    clock = FakeClock()
    starts: list = []

    def failing(request: httpx.Request) -> httpx.Response:
        starts.append((clock.now, str(request.url)))
        return httpx.Response(500)

    ia = make_client(tmp_path, failing, metadata=item_metadata("ia800903.us.archive.org"),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    with pytest.raises(IADownloadError) as info:
        ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    message = str(info.value)
    assert message.startswith("download of t.mp3 failed")
    assert REDIRECT in message and SERVER in message
    assert [url for _, url in starts[:2]] == [REDIRECT, SERVER]
    first_pass_end = starts[1][0]  # instant handlers: the pass ends as its last attempt starts
    assert len(starts) > 2  # repeat attempts happened
    assert starts[-1][0] < first_pass_end + DOWNLOAD_DEADLINE_S
    # The repeats cycle both retryable candidates.
    assert {url for _, url in starts[2:]} == {REDIRECT, SERVER}
    assert not dest.exists() and no_leftovers(tmp_path)


def test_hanging_redirect_does_not_starve_listed_servers(tmp_path: Path):
    clock = FakeClock()
    seen: list = []

    def hang(request: httpx.Request) -> httpx.Response:
        clock.advance(500)
        raise httpx.ReadTimeout("stalled", request=request)

    ia = make_client(tmp_path, routed({REDIRECT: hang, SERVER: BODY}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER]


def test_deadline_counts_from_the_end_of_the_first_pass(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    answers = iter([500])

    hangs = iter([True])

    def hang_once(request: httpx.Request) -> httpx.Response:
        if next(hangs, False):
            clock.advance(500)
            raise httpx.ConnectTimeout("no answer", request=request)
        return httpx.Response(500)

    def flaky(request: httpx.Request) -> httpx.Response:
        code = next(answers, 200)
        return httpx.Response(code, content=BODY if code == 200 else b"")

    ia = make_client(tmp_path, routed({REDIRECT: hang_once, SERVER: flaky}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)  # a 500 s first pass leaves the repeats intact
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER, REDIRECT, SERVER]


def test_4xx_moves_on_then_succeeds(tmp_path: Path):
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: 404, SERVER: BODY}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER]


def test_all_4xx_fails_after_one_pass(tmp_path: Path):
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: 404, SERVER: 403}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    with pytest.raises(IADownloadError):
        ia.download_file("x", "t.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert seen == [REDIRECT, SERVER]


@pytest.mark.parametrize("status", [408, 429, 503])
def test_408_429_and_5xx_are_retried(tmp_path: Path, status: int):
    seen: list = []
    answers = iter([status, status])

    def flaky(request: httpx.Request) -> httpx.Response:
        code = next(answers, 200)
        return httpx.Response(code, content=BODY if code == 200 else b"")

    ia = make_client(tmp_path, routed({REDIRECT: flaky, SERVER: status}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER, REDIRECT, SERVER, REDIRECT]


def test_md5_mismatch_on_one_server_then_success(tmp_path: Path):
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: b"corrupt copy", SERVER: BODY}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert hashlib.md5(dest.read_bytes()).hexdigest() == BODY_MD5
    assert seen == [REDIRECT, SERVER]
    assert no_leftovers(tmp_path)


def test_md5_mismatch_copy_is_checked_once(tmp_path: Path):
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: b"corrupt", SERVER: b"also corrupt"}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    with pytest.raises(IADownloadError) as info:
        ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert seen == [REDIRECT, SERVER]
    assert "md5 mismatch" in str(info.value)
    assert not dest.exists() and no_leftovers(tmp_path)


def test_md5_mismatch_copy_is_skipped_by_repeat_attempts(tmp_path: Path):
    seen: list = []
    answers = iter([500])

    def flaky(request: httpx.Request) -> httpx.Response:
        code = next(answers, 200)
        return httpx.Response(code, content=BODY if code == 200 else b"")

    ia = make_client(tmp_path, routed({REDIRECT: b"corrupt", SERVER: flaky}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER, SERVER]


def test_too_many_redirects_is_caught(tmp_path: Path):
    def loop(request: httpx.Request) -> httpx.Response:
        raise httpx.TooManyRedirects("redirect loop", request=request)

    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: loop, SERVER: BODY}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY

    lone: list = []
    ia = make_client(tmp_path / "lone", routed({REDIRECT: loop}, lone), metadata={})
    with pytest.raises(IADownloadError) as info:
        ia.download_file("x", "t.mp3", tmp_path / "lone.mp3", md5=BODY_MD5)
    assert "TooManyRedirects" in str(info.value)
    assert len(lone) > 1 and set(lone) == {REDIRECT}  # retryable: repeated until the deadline


def test_size_check_when_no_md5(tmp_path: Path):
    seen: list = []
    body10 = b"0123456789"
    md = item_metadata("ia800903.us.archive.org", md5=None, size="10")
    ia = make_client(tmp_path, routed({REDIRECT: body10[:9], SERVER: body10}, seen), metadata=md)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest)
    assert dest.read_bytes() == body10
    assert seen == [REDIRECT, SERVER]

    lone: list = []
    md = {"files": [{"name": "t.mp3", "size": "10"}]}  # no dir: the redirect is the only copy
    ia = make_client(tmp_path / "lone", routed({REDIRECT: body10[:9]}, lone), metadata=md)
    lone_dest = tmp_path / "lone.mp3"
    with pytest.raises(IADownloadError) as info:
        ia.download_file("x", "t.mp3", lone_dest)
    assert "size mismatch" in str(info.value)
    assert lone == [REDIRECT]  # a wrong-length copy is checked once, like an md5 mismatch
    assert not lone_dest.exists() and no_leftovers(tmp_path)


def test_mid_stream_failure_is_retryable(tmp_path: Path):
    def dies(request: httpx.Request) -> httpx.Response:
        def body():
            yield BODY[:5]
            raise httpx.ReadError("connection reset")
        return httpx.Response(200, content=body())

    def server(request: httpx.Request) -> httpx.Response:
        assert no_leftovers(tmp_path)  # the failed attempt deleted its partial .part
        return httpx.Response(200, content=BODY)

    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: dies, SERVER: server}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER]
    assert no_leftovers(tmp_path)

    lone: list = []
    ia = make_client(tmp_path / "lone", routed({REDIRECT: dies}, lone), metadata={})
    with pytest.raises(IADownloadError):
        ia.download_file("x", "t.mp3", tmp_path / "lone.mp3", md5=BODY_MD5)
    assert len(lone) > 1  # retryable
    assert no_leftovers(tmp_path)


def test_missing_server_fields_mean_redirect_only(tmp_path: Path):
    md = item_metadata("ia800903.us.archive.org", d1="ia600903.us.archive.org")
    del md["dir"]
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: BODY}, seen), metadata=md)
    assert ia._download_candidates("x", "t.mp3") == ([REDIRECT], len(BODY))
    ia.download_file("x", "t.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert seen == [REDIRECT]

    ia = make_client(tmp_path / "b", routed({}, []), metadata={"dir": "/9/items/x"})
    assert ia._download_candidates("x", "t.mp3") == ([REDIRECT], None)


def test_d1_d2_used_only_when_workable_servers_empty(tmp_path: Path):
    md = item_metadata(d1="ia800903.us.archive.org", d2="ia800903.us.archive.org")
    ia = make_client(tmp_path, routed({}, []), metadata=md)
    assert ia._download_candidates("x", "t.mp3")[0] == [REDIRECT, SERVER]

    md = item_metadata(d1="ia800903.us.archive.org", d2="ia600903.us.archive.org")
    del md["workable_servers"]
    ia = make_client(tmp_path / "missing", routed({}, []), metadata=md)
    assert ia._download_candidates("x", "t.mp3")[0] == [REDIRECT, SERVER, SERVER2]

    md = item_metadata("ia600903.us.archive.org", d1="ia800903.us.archive.org",
                       d2="ia600903.us.archive.org")
    seen: list = []
    ia = make_client(tmp_path / "listed", routed({REDIRECT: 500, SERVER2: 500}, seen), metadata=md)
    with pytest.raises(IADownloadError):
        ia.download_file("x", "t.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert SERVER not in seen and set(seen) == {REDIRECT, SERVER2}


def test_listed_server_url_quotes_but_keeps_slash(tmp_path: Path):
    paths: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.raw_path.decode())
        return httpx.Response(500 if request.url.host == "archive.org" else 200, content=BODY)

    ia = make_client(tmp_path, handler,
                     metadata=item_metadata("ia800903.us.archive.org", name="set 2/t 06.mp3"))
    ia.download_file("x", "set 2/t 06.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert paths == ["/download/x/set%202/t%2006.mp3", "/9/items/x/set%202/t%2006.mp3"]


@pytest.mark.parametrize("metadata_answer", [
    httpx.Response(500),
    httpx.Response(200, content=b"<html>not json</html>"),
])
def test_unusable_metadata_degrades_to_redirect_only(tmp_path: Path, metadata_answer):
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/metadata/"):
            return metadata_answer
        seen.append(str(request.url))
        return httpx.Response(200, content=BODY)

    ia = make_client(tmp_path, handler)
    assert ia._download_candidates("x", "t.mp3") == ([REDIRECT], None)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT]


@pytest.mark.parametrize("files", [
    [{"name": "t.mp3", "size": "abc"}],     # non-numeric size
    [{"name": "t.mp3", "size": None}],
    [{"name": "t.mp3"}],                    # no size
    [{"name": "other.mp3", "size": "3"}],   # no entry for this file
    "not a list",
])
def test_unusable_size_means_no_size_check(tmp_path: Path, files):
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: BODY}, seen), metadata={"files": files})
    assert ia._download_candidates("x", "t.mp3") == ([REDIRECT], None)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest)  # no md5, no usable size: renamed as before
    assert dest.read_bytes() == BODY


def test_duplicate_servers_are_tried_once(tmp_path: Path):
    md = item_metadata("ia800903.us.archive.org", "ia600903.us.archive.org",
                       "ia800903.us.archive.org", "ia600903.us.archive.org")
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: 404, SERVER: 404, SERVER2: 404}, seen),
                     metadata=md)
    assert ia._download_candidates("x", "t.mp3")[0] == [REDIRECT, SERVER, SERVER2]
    with pytest.raises(IADownloadError):
        ia.download_file("x", "t.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert seen == [REDIRECT, SERVER, SERVER2]


def test_download_uses_short_timeouts(tmp_path: Path):
    timeouts: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, content=BODY)

    ia = make_client(tmp_path, handler, metadata={})
    ia.download_file("x", "t.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert len(timeouts) == 1
    assert timeouts[0]["connect"] == DOWNLOAD_CONNECT_TIMEOUT_S
    assert timeouts[0]["read"] == DOWNLOAD_STALL_TIMEOUT_S


def test_sleeps_between_attempts_are_short_and_random(tmp_path: Path):
    clock = FakeClock()
    ia = make_client(tmp_path, lambda r: httpx.Response(500),
                     metadata=item_metadata("ia800903.us.archive.org"), clock=clock)
    with pytest.raises(IADownloadError):
        ia.download_file("x", "t.mp3", tmp_path / "t.mp3", md5=BODY_MD5)
    assert clock.sleeps and all(1.0 <= s <= 4.0 for s in clock.sleeps)
    assert len(set(clock.sleeps)) > 1


def test_download_error_is_an_ia_error():
    assert issubclass(IADownloadError, IAError)
