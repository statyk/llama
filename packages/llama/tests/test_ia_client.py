import hashlib
import json
import logging
import random
from pathlib import Path

import httpx
import pytest

from llama.ia_client import (DOWNLOAD_CONNECT_TIMEOUT_S, DOWNLOAD_DEADLINE_S,
                             DOWNLOAD_STALL_TIMEOUT_S, TRICKLE_FLOOR_BPS, TRICKLE_WINDOW_S,
                             IAClient, IADownloadError, IAError)


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
    assert clock.now >= first_pass_end + DOWNLOAD_DEADLINE_S  # and kept going until then
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


def test_metadata_http_error_means_redirect_only(tmp_path: Path):
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/metadata/"):
            raise httpx.TooManyRedirects("metadata redirect loop", request=request)
        seen.append(str(request.url))
        return httpx.Response(200, content=BODY)

    ia = make_client(tmp_path, handler)
    assert ia._download_candidates("x", "t.mp3") == ([REDIRECT], None)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT]


# --- download_file: trickle switch with Range continuation --------------------------

LONG = bytes(range(256)) * 400  # 102,400 bytes: ~102 simulated s at the trickle rate
LONG_MD5 = hashlib.md5(LONG).hexdigest()
TRICKLE = 1_000  # B/s: a tenth of the floor
HEALTHY = 100_000  # B/s
# A trickle arrives in 1,000-byte chunks, one per simulated second, and is abandoned at
# the first chunk TRICKLE_WINDOW_S after its first byte: 31 chunks in, that chunk written.
K = (int(TRICKLE_WINDOW_S) + 1) * TRICKLE


def long_metadata(*servers: str, md5: str | None = LONG_MD5, data: bytes = LONG) -> dict:
    return item_metadata(*servers, md5=md5, size=str(len(data)))


def stream(clock: FakeClock, data: bytes, rate: int, *, delay: float = 0.0,
           arrivals: list | None = None, chunk: int = 1_000):
    """A lazy body: `data` in `chunk`-byte pieces, the fake clock advancing
    len(piece)/rate s before each piece (and `delay` s before the first). Each
    piece's arrival time is appended to `arrivals` when given."""
    def body():
        clock.advance(delay)
        for i in range(0, len(data), chunk):
            piece = data[i:i + chunk]
            clock.advance(len(piece) / rate)
            if arrivals is not None:
                arrivals.append(clock.now)
            yield piece
    return body()


def serve(clock: FakeClock, data: bytes, rate: int, *, ranges: list | None = None,
          arrivals: list | None = None):
    """A handler serving `data` at `rate` B/s that honours `Range: bytes=N-` with a 206
    and its Content-Range. Records each request's Range header (None without one)."""
    def handler(request: httpx.Request) -> httpx.Response:
        asked = request.headers.get("range")
        if ranges is not None:
            ranges.append(asked)
        if asked is None:
            return httpx.Response(200, content=stream(clock, data, rate, arrivals=arrivals))
        start = int(asked.removeprefix("bytes=").removesuffix("-"))
        return httpx.Response(
            206, headers={"content-range": f"bytes {start}-{len(data) - 1}/{len(data)}"},
            content=stream(clock, data[start:], rate, arrivals=arrivals))
    return handler


def test_slow_but_above_floor_transfer_finishes(tmp_path: Path):
    clock = FakeClock()
    slow = bytes(range(256)) * 9375  # 2,400,000 bytes: 120 s at twice the floor
    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, slow, 2 * TRICKLE_FLOOR_BPS),
                                       SERVER: serve(clock, slow, HEALTHY)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org",
                                            md5=hashlib.md5(slow).hexdigest(), data=slow),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=hashlib.md5(slow).hexdigest())
    assert dest.read_bytes() == slow
    assert seen == [REDIRECT]
    assert clock.now >= 119.9


def test_trickle_switches_and_continues_from_offset(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    ranges: list = []
    arrivals: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE, arrivals=arrivals),
                                       SERVER: serve(clock, LONG, HEALTHY, ranges=ranges)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER]
    assert ranges == [f"bytes={K}-"]  # the .part size at abandonment, triggering chunk included
    # Abandoned at the first chunk TRICKLE_WINDOW_S after the first byte, not before or after.
    assert len(arrivals) == K // TRICKLE
    assert arrivals[-1] - arrivals[0] >= TRICKLE_WINDOW_S > arrivals[-2] - arrivals[0]
    assert no_leftovers(tmp_path)


def test_range_answered_200_restarts_from_zero(tmp_path: Path):
    clock = FakeClock()
    ranges: list = []

    def ignores_range(request: httpx.Request) -> httpx.Response:
        ranges.append(request.headers.get("range"))
        return httpx.Response(200, content=stream(clock, LONG, HEALTHY))

    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE),
                                       SERVER: ignores_range}, []),
                     metadata=long_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert ranges == [f"bytes={K}-"]


@pytest.mark.parametrize("content_range, body", [
    (f"bytes 0-{len(LONG) - 1}/{len(LONG)}", LONG),  # starts at 0, not at the offset
    (f"bytes {K}-{len(LONG)}/{len(LONG) + 1}", LONG[K:] + b"x"),  # a different-length copy
], ids=["wrong-start", "wrong-total"])
def test_wrong_content_range_restarts_from_zero(tmp_path: Path, content_range, body):
    clock = FakeClock()
    seen: list = []
    ranges: list = []

    def mismatched(request: httpx.Request) -> httpx.Response:
        ranges.append(request.headers.get("range"))
        if request.headers.get("range"):
            return httpx.Response(206, headers={"content-range": content_range},
                                  content=stream(clock, body, HEALTHY))
        return httpx.Response(200, content=stream(clock, LONG, HEALTHY))

    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE),
                                       SERVER: mismatched}, seen),
                     metadata=long_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert ranges == [f"bytes={K}-", None]  # re-issued without Range in the same attempt
    assert seen == [REDIRECT, SERVER, SERVER]


def test_stitched_file_with_bad_md5_is_deleted_and_refetched_from_zero(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    s1_ranges: list = []
    s2_ranges: list = []
    corrupt = bytes(len(LONG))
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE),
                                       SERVER: serve(clock, corrupt, HEALTHY, ranges=s1_ranges),
                                       SERVER2: serve(clock, LONG, HEALTHY, ranges=s2_ranges)},
                                      seen),
                     metadata=long_metadata("ia800903.us.archive.org", "ia600903.us.archive.org"),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER, SERVER2]
    assert s1_ranges == [f"bytes={K}-"]  # the stitch, checked once
    assert s2_ranges == [None]  # the failed stitch was deleted: from byte 0
    assert no_leftovers(tmp_path)


def test_last_non_abandoned_candidate_is_never_abandoned(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    ranges: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE),
                                       SERVER: 404,
                                       SERVER2: serve(clock, LONG, TRICKLE, ranges=ranges)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org", "ia600903.us.archive.org"),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER, SERVER2]
    assert ranges == [f"bytes={K}-"]  # one request, run to completion however slow


def test_single_candidate_trickle_completes_in_one_request(tmp_path: Path):
    clock = FakeClock()
    ranges: list = []
    md = {"files": [{"name": "t.mp3", "md5": LONG_MD5, "size": str(len(LONG))}]}  # no dir
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE, ranges=ranges)}, []),
                     metadata=md, clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert ranges == [None]


def test_each_candidate_abandoned_at_most_once(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    r_ranges: list = []
    s_ranges: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE, ranges=r_ranges),
                                       SERVER: serve(clock, LONG, TRICKLE, ranges=s_ranges)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert s_ranges == [f"bytes={K}-"]  # never abandoned: the redirect already was
    assert r_ranges == [None]
    assert seen == [REDIRECT, SERVER]


def test_an_abandoned_candidate_is_not_abandoned_again(tmp_path: Path):
    # SERVER2 stays retryable and un-abandoned, the deadline is far off and the .part
    # short of `size`, so only "abandoned once already" keeps the redirect's second
    # request running to completion.
    clock = FakeClock()
    seen: list = []
    r_ranges: list = []
    s_ranges: list = []
    s_arrivals: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE, ranges=r_ranges),
                                       SERVER: serve(clock, LONG, TRICKLE, ranges=s_ranges,
                                                     arrivals=s_arrivals),
                                       SERVER2: 500}, seen),
                     metadata=long_metadata("ia800903.us.archive.org", "ia600903.us.archive.org"),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER, SERVER2, REDIRECT]
    assert s_ranges == [f"bytes={K}-"]
    # The server is abandoned in turn about a window later (its clock base is not a
    # whole number, so the window may close a chunk late), and the redirect continues.
    assert s_arrivals[-1] - s_arrivals[0] >= TRICKLE_WINDOW_S
    assert len(s_arrivals) in (K // TRICKLE, K // TRICKLE + 1)
    assert r_ranges == [None, f"bytes={K + TRICKLE * len(s_arrivals)}-"]


def test_full_part_is_never_abandoned(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    exact = LONG[:K]  # the window closes on the chunk that completes the file
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, exact, TRICKLE),
                                       SERVER: serve(clock, exact, HEALTHY)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org",
                                            md5=hashlib.md5(exact).hexdigest(), data=exact),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=hashlib.md5(exact).hexdigest())
    assert dest.read_bytes() == exact
    assert seen == [REDIRECT]


def test_no_abandonment_after_the_deadline(tmp_path: Path):
    clock = FakeClock()
    events: list = []
    r_ranges: list = []
    trickle = serve(clock, LONG, TRICKLE, ranges=r_ranges)

    def server(request: httpx.Request) -> httpx.Response:
        events.append(("S", clock.now))
        return httpx.Response(500)

    def redirect(request: httpx.Request) -> httpx.Response:
        events.append(("R", clock.now))
        s_starts = [t for who, t in events if who == "S"]
        # Instant handlers: the first pass ends as the server's first attempt starts.
        if not s_starts or clock.now < s_starts[0] + DOWNLOAD_DEADLINE_S - 10:
            return httpx.Response(500)
        return trickle(request)  # starts < 10 s before the deadline: its window closes after

    ia = make_client(tmp_path, routed({REDIRECT: redirect, SERVER: server}, []),
                     metadata=long_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert r_ranges == [None]
    deadline = events[1][1] + DOWNLOAD_DEADLINE_S
    assert events[-1][0] == "R" and events[-1][1] < deadline < clock.now


def test_abandonment_just_before_the_deadline_still_gets_its_next_attempt(tmp_path: Path):
    clock = FakeClock()
    events: list = []
    s_ranges: list = []
    rest = serve(clock, LONG, HEALTHY, ranges=s_ranges)

    def server(request: httpx.Request) -> httpx.Response:
        events.append(("S", clock.now))
        return rest(request) if request.headers.get("range") else httpx.Response(500)

    def redirect(request: httpx.Request) -> httpx.Response:
        events.append(("R", clock.now))
        s_starts = [t for who, t in events if who == "S"]
        deadline = s_starts[0] + DOWNLOAD_DEADLINE_S if s_starts else None
        if deadline is None or clock.now < deadline - 40:
            return httpx.Response(500)
        # First byte at deadline - 30.5: abandoned about half a second before the
        # deadline (0.1 s chunks, so float drift costs at most 0.1 s), so the pause
        # (>= 1 s) before the next attempt ends after it.
        first_byte = deadline - TRICKLE_WINDOW_S - 0.5
        return httpx.Response(200, content=stream(clock, LONG, TRICKLE, chunk=100,
                                                  delay=first_byte - 0.1 - clock.now))

    ia = make_client(tmp_path, routed({REDIRECT: redirect, SERVER: server}, []),
                     metadata=long_metadata("ia800903.us.archive.org"), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    deadline = events[1][1] + DOWNLOAD_DEADLINE_S
    assert len(s_ranges) == 1 and s_ranges[0] != "bytes=0-"  # continued the abandoned .part
    assert events[-1][0] == "S" and events[-1][1] > deadline  # started past the deadline


def test_no_md5_trickle_restarts_from_zero(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    ranges: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE),
                                       SERVER: serve(clock, LONG, HEALTHY, ranges=ranges)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org", md5=None), clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest)  # size check only
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER]  # still abandoned
    assert ranges == [None]  # but no stitching without an md5
    assert no_leftovers(tmp_path)


def test_206_to_a_plain_request_is_rejected(tmp_path: Path):
    def partial(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("range") is None
        return httpx.Response(206, headers={"content-range": f"bytes 0-{len(BODY) - 1}/{len(BODY)}"},
                              content=BODY)

    def server(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("range") is None and no_leftovers(tmp_path)
        return httpx.Response(200, content=BODY)

    seen: list = []
    ia = make_client(tmp_path, routed({REDIRECT: partial, SERVER: server}, seen),
                     metadata=item_metadata("ia800903.us.archive.org"))
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=BODY_MD5)
    assert dest.read_bytes() == BODY
    assert seen == [REDIRECT, SERVER]

    lone: list = []
    ia = make_client(tmp_path / "lone", routed({REDIRECT: partial}, lone), metadata={})
    with pytest.raises(IADownloadError) as info:
        ia.download_file("x", "t.mp3", tmp_path / "lone.mp3", md5=BODY_MD5)
    assert "206" in str(info.value)
    assert len(lone) > 1  # retryable
    assert no_leftovers(tmp_path)


def test_416_discards_the_part_and_restarts_from_zero(tmp_path: Path):
    clock = FakeClock()
    seen: list = []
    s_ranges: list = []
    s2_ranges: list = []
    redirect_calls = iter([serve(clock, LONG, TRICKLE)])

    def redirect(request: httpx.Request) -> httpx.Response:
        first = next(redirect_calls, None)
        return first(request) if first else httpx.Response(500)

    def shorter_copy(request: httpx.Request) -> httpx.Response:
        s_ranges.append(request.headers.get("range"))
        if request.headers.get("range"):
            return httpx.Response(416)
        return httpx.Response(200, content=stream(clock, LONG, HEALTHY))

    def not_found(request: httpx.Request) -> httpx.Response:
        s2_ranges.append(request.headers.get("range"))
        return httpx.Response(404)

    ia = make_client(tmp_path, routed({REDIRECT: redirect, SERVER: shorter_copy,
                                       SERVER2: not_found}, seen),
                     metadata=long_metadata("ia800903.us.archive.org", "ia600903.us.archive.org"),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER, SERVER2, REDIRECT, SERVER]  # the 416 was retryable
    assert s_ranges == [f"bytes={K}-", None]
    assert s2_ranges == [None]  # the 416 discarded the .part


def test_stale_part_from_a_previous_process_is_not_continued(tmp_path: Path):
    clock = FakeClock()
    ranges: list = []
    dest = tmp_path / "t.mp3"
    dest.with_suffix(".mp3.part").write_bytes(b"junk from a killed process" * 100)
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, HEALTHY, ranges=ranges)}, []),
                     metadata=long_metadata(), clock=clock)
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert ranges == [None]
    assert no_leftovers(tmp_path)


def refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize("failure", [500, refuse_connection], ids=["status", "connect"])
def test_a_status_error_keeps_the_continuation_part(tmp_path: Path, failure):
    clock = FakeClock()
    seen: list = []
    ranges: list = []
    ia = make_client(tmp_path, routed({REDIRECT: serve(clock, LONG, TRICKLE),
                                       SERVER: failure,
                                       SERVER2: serve(clock, LONG, HEALTHY, ranges=ranges)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org", "ia600903.us.archive.org"),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=LONG_MD5)
    assert dest.read_bytes() == LONG
    assert seen == [REDIRECT, SERVER, SERVER2]
    assert ranges == [f"bytes={K}-"]


def test_a_transfer_that_slows_to_a_trickle_is_abandoned(tmp_path: Path):
    # The window slides: a fast start does not license a trickle after it.
    clock = FakeClock()
    fast, slow = 500_000, 100_000
    data = bytes(range(256)) * ((fast + slow) // 256) + bytes((fast + slow) % 256)
    sent = {"n": 0}

    def fast_then_trickle(request: httpx.Request) -> httpx.Response:
        def body():
            for i in range(0, fast, 10_000):
                clock.advance(0.1)
                sent["n"] += 10_000
                yield data[i:i + 10_000]
            for i in range(fast, fast + slow, 1_000):
                clock.advance(1.0)
                sent["n"] += 1_000
                yield data[i:i + 1_000]
        return httpx.Response(200, content=body())

    seen: list = []
    ranges: list = []
    ia = make_client(tmp_path, routed({REDIRECT: fast_then_trickle,
                                       SERVER: serve(clock, data, HEALTHY, ranges=ranges)}, seen),
                     metadata=long_metadata("ia800903.us.archive.org",
                                            md5=hashlib.md5(data).hexdigest(), data=data),
                     clock=clock)
    dest = tmp_path / "t.mp3"
    ia.download_file("x", "t.mp3", dest, md5=hashlib.md5(data).hexdigest())
    assert dest.read_bytes() == data
    assert seen == [REDIRECT, SERVER]
    assert ranges == [f"bytes={sent['n']}-"]
    # Abandoned within about a window of the slowdown, not at the end of the file.
    assert fast < sent["n"] <= fast + (TRICKLE_WINDOW_S + 2) * TRICKLE
