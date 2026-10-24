import json
import logging
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from transmitter import alerts, relay
from transmitter.relay import Cursor, Relay
from transmitter.workspace import Workspace

NOW = 1_800_000_000.0


def iso(t: float) -> str:
    """As antenna's toISOString() writes it."""
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def msg(seq, at_s=NOW, *, at=None, kind="alert", priority="high", title=None, message="M", key="waf-api"):
    return {"seq": seq, "at": iso(at_s) if at is None else at, "key": key, "kind": kind, "priority": priority,
            "title": f"T{seq}" if title is None else title, "message": message}


def doc(stream, *msgs):
    return {"stream": stream, "ring": list(msgs)}


def http_error(code):
    return urllib.error.HTTPError("https://ntfy.example/t", code, "x", {}, None)


class FakeNtfy:
    """Records what was sent; `plan` gives each call's outcome in order
    (None: accepted, an exception: raised); calls past the plan are accepted."""
    name = "ntfy"

    def __init__(self, plan=(), on_send=None):
        self.plan = list(plan)
        self.on_send = on_send
        self.sent: list[tuple[str, str, int, str]] = []
        self.attempts: list[str] = []

    def send(self, subject, body, priority, tags=None):
        self.attempts.append(subject)
        if self.on_send is not None:
            self.on_send()
        outcome = self.plan.pop(0) if self.plan else None
        if outcome is not None:
            raise outcome
        self.sent.append((subject, body, priority, tags))

    def subjects(self):
        return [s for s, *_ in self.sent]


class Source:
    """The relay's get_json: the current document (or an exception to raise)."""

    def __init__(self, value=None):
        self.value = value
        self.keys: list[str] = []

    def __call__(self, key):
        self.keys.append(key)
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


def _relay(tmp_path, source, ntfy=None, *, mono=None, cursor_path=None):
    ntfy = FakeNtfy() if ntfy is None else ntfy
    clock = mono if mono is not None else (lambda: 0.0)
    path = tmp_path / "alert-relay-cursor.json" if cursor_path is None else cursor_path
    return Relay(source, ntfy, "llama radio", path, now=lambda: NOW, monotonic=clock), ntfy


def test_relay_key_matches_antenna():
    src = (Path(__file__).resolve().parents[3] / "antenna" / "src" / "alerts.ts").read_text()
    assert f'RELAY_KEY = "{relay.RELAY_KEY}"' in src


def test_the_cursor_file_lives_in_the_workspace(tmp_path):
    assert Workspace(tmp_path).relay_cursor_path == tmp_path / "alert-relay-cursor.json"


def test_messages_above_the_cursor_are_sent_once_in_seq_order(tmp_path):
    source = Source(doc("s", msg(2, NOW - 60), msg(1, NOW - 120), msg(3, NOW - 10)))
    r, ntfy = _relay(tmp_path, source)
    assert r.cursor is None
    r.run_pass()
    assert source.keys == [relay.RELAY_KEY]
    assert ntfy.subjects() == ["llama radio: T1", "llama radio: T2", "llama radio: T3"]
    assert r.cursor == Cursor("s", 3)
    r.run_pass()
    assert len(ntfy.sent) == 3                               # nothing re-sent
    assert json.loads((tmp_path / "alert-relay-cursor.json").read_text()) == {"stream": "s", "seq": 3}


@pytest.mark.parametrize("kind, priority, subject, prio, tags", [
    ("alert", "urgent", "llama radio: T", 5, "rotating_light"),
    ("repeat", "high", "llama radio: T", 4, "warning"),
    ("alert", "default", "llama radio: T", 3, "information_source"),
    ("resolved", "default", "llama radio: resolved: T", 3, "white_check_mark"),
    ("resolved", "urgent", "llama radio: resolved: T", 3, "white_check_mark")])
def test_formatting_title_priority_and_tags(kind, priority, subject, prio, tags):
    s, body, p, t = relay.format_message(msg(1, NOW, kind=kind, priority=priority, title="T"), "llama radio")
    assert (s, p, t) == (subject, prio, tags) and body.startswith("M") and "antenna" in body


def test_a_default_priority_alert_never_carries_the_check_mark_and_an_unknown_priority_is_default():
    for kind in ("alert", "repeat"):
        assert relay.format_message(msg(1, kind=kind, priority="default"), "x")[3] != relay.RESOLVED_TAGS
    assert relay.format_message(msg(1, priority="bogus"), "x")[2:] == (3, "information_source")


def test_the_constants_are_the_specs():
    assert relay.RELAY_MAX_AGE_S == 3600.0 and relay.RELAY_PASS_BUDGET_S == 30.0
    assert relay.PRIORITY == {"urgent": 5, "high": 4, "default": 3}
    assert relay.TAGS == {"urgent": "rotating_light", "high": "warning", "default": "information_source"}
    assert relay.RESOLVED_TAGS == "white_check_mark"


def test_no_cursor_sends_only_messages_younger_than_max_age_and_logs_each_skip_once(tmp_path, caplog):
    source = Source(doc("s", msg(1, NOW - 7200), msg(2, NOW - 3599)))
    r, ntfy = _relay(tmp_path, source)
    with caplog.at_level(logging.INFO, logger="transmitter.relay"):
        r.run_pass()
    assert ntfy.subjects() == ["llama radio: T2"] and r.cursor == Cursor("s", 2)
    skips = [rec for rec in caplog.records if "skipped relayed alert 1" in rec.getMessage()]
    assert len(skips) == 1 and "waf-api" in skips[0].getMessage()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="transmitter.relay"):
        r.run_pass()
    assert [rec for rec in caplog.records if "skipped" in rec.getMessage()] == []
    assert len(ntfy.sent) == 1


def test_a_message_exactly_max_age_old_is_skipped(tmp_path):
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - relay.RELAY_MAX_AGE_S))))
    r.run_pass()
    assert ntfy.sent == [] and r.cursor == Cursor("s", 1)


def test_a_stream_change_restarts_at_seq_0_in_the_new_stream(tmp_path):
    (tmp_path / "alert-relay-cursor.json").write_text(json.dumps({"stream": "old", "seq": 500}))
    r, ntfy = _relay(tmp_path, Source(doc("new", msg(1, NOW - 30), msg(2, NOW - 20))))
    assert r.cursor == Cursor("old", 500)
    r.run_pass()
    assert ntfy.subjects() == ["llama radio: T1", "llama radio: T2"] and r.cursor == Cursor("new", 2)


def test_a_cursor_in_the_same_stream_sends_only_newer_messages(tmp_path):
    (tmp_path / "alert-relay-cursor.json").write_text(json.dumps({"stream": "s", "seq": 2}))
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - 30), msg(2, NOW - 20), msg(3, NOW - 10))))
    r.run_pass()
    assert ntfy.subjects() == ["llama radio: T3"] and r.cursor == Cursor("s", 3)


def test_a_4xx_refusal_other_than_429_is_logged_with_its_status_and_skipped(tmp_path, caplog):
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - 20), msg(2, NOW - 10))), FakeNtfy([http_error(400)]))
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    warnings = [rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1 and "HTTP 400" in warnings[0] and "relayed alert 1 " in warnings[0]
    assert ntfy.subjects() == ["llama radio: T2"] and r.cursor == Cursor("s", 2)


@pytest.mark.parametrize("failure", [http_error(429), http_error(503), urllib.error.URLError("down"),
                                     OSError("ntfy: HTTP 302")])
def test_429_5xx_or_transport_stop_the_pass_and_the_next_pass_retries_from_that_message(tmp_path, failure, caplog):
    source = Source(doc("s", msg(1, NOW - 30), msg(2, NOW - 20), msg(3, NOW - 10)))
    r, ntfy = _relay(tmp_path, source, FakeNtfy([None, failure]))
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    assert ntfy.attempts == ["llama radio: T1", "llama radio: T2"]          # seq 3 never attempted
    assert ntfy.subjects() == ["llama radio: T1"] and r.cursor == Cursor("s", 1)
    assert "relay stopped at 2" in caplog.text
    r.run_pass()
    assert ntfy.subjects() == ["llama radio: T1", "llama radio: T2", "llama radio: T3"]
    assert r.cursor == Cursor("s", 3)


def test_the_pass_stops_after_its_30_s_budget(tmp_path):
    mono = [0.0]

    def advance():
        mono[0] += 20.0

    source = Source(doc("s", *(msg(i, NOW - 10) for i in range(1, 6))))
    r, ntfy = _relay(tmp_path, source, FakeNtfy(on_send=advance), mono=lambda: mono[0])
    r.run_pass()
    assert ntfy.subjects() == ["llama radio: T1", "llama radio: T2"] and r.cursor == Cursor("s", 2)
    r.run_pass()                                             # a new pass, a new budget
    assert ntfy.subjects()[2:] == ["llama radio: T3", "llama radio: T4"] and r.cursor == Cursor("s", 4)


def test_a_missing_object_is_nothing_to_relay_and_keeps_the_cursor(tmp_path):
    path = tmp_path / "alert-relay-cursor.json"
    path.write_text(json.dumps({"stream": "s", "seq": 2}))
    r, ntfy = _relay(tmp_path, Source(None))
    path.write_text("left alone")                            # read once at startup; a rewrite would replace this
    r.run_pass()
    assert ntfy.sent == [] and r.cursor == Cursor("s", 2) and path.read_text() == "left alone"


@pytest.mark.parametrize("bad", ["raise", [], {"stream": 5, "ring": []}, {"stream": "s", "ring": {}},
                                 {"stream": "s", "ring": [{"seq": 1.5}]}, {"stream": "s", "ring": [{"seq": True}]},
                                 {"stream": "s", "ring": [None]}, {"stream": "s", "ring": [1]}])
def test_an_unreadable_or_malformed_document_is_a_warning_never_an_alert(tmp_path, caplog, monkeypatch, bad):
    recorded = []
    monkeypatch.setattr(alerts, "alert", lambda code, m: recorded.append(code))
    monkeypatch.setattr(alerts, "resolve", lambda code: recorded.append(code))
    path = tmp_path / "alert-relay-cursor.json"
    path.write_text(json.dumps({"stream": "s", "seq": 0}))
    source = Source(ValueError("Expecting value: line 1 column 1") if bad == "raise" else bad)
    r, ntfy = _relay(tmp_path, source)
    path.write_text("left alone")
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    assert [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert ntfy.sent == [] and recorded == [] and r.cursor == Cursor("s", 0) and path.read_text() == "left alone"


def test_doc_problem_mirrors_antennas_relay_doc_problem():
    assert relay.doc_problem({"stream": "s", "ring": []}) is None
    assert relay.doc_problem({"stream": "s", "ring": [{"seq": 1}, {"seq": 2, "extra": None}]}) is None
    assert relay.doc_problem(None) == "not an object"
    assert relay.doc_problem([]) == "not an object"
    assert relay.doc_problem("s") == "not an object"
    assert relay.doc_problem({"ring": []}) == "stream is not a string"
    assert relay.doc_problem({"stream": 5, "ring": []}) == "stream is not a string"
    assert relay.doc_problem({"stream": "s"}) == "ring is not an array"
    assert relay.doc_problem({"stream": "s", "ring": {}}) == "ring is not an array"
    assert relay.doc_problem({"stream": "s", "ring": [{"seq": 1}, None]}) == "ring[1] is not an object"
    assert relay.doc_problem({"stream": "s", "ring": [[]]}) == "ring[0] is not an object"
    assert relay.doc_problem({"stream": "s", "ring": [1]}) == "ring[0] is not an object"
    for seq in (True, False, 1.0, 1.5, "1", None):          # bool is an int in Python; JSON 1.0 is a float
        assert relay.doc_problem({"stream": "s", "ring": [{"seq": seq}]}) == "ring[0].seq is not an integer"
    assert relay.doc_problem({"stream": "s", "ring": [{}]}) == "ring[0].seq is not an integer"


def test_an_at_in_the_future_is_sent_and_an_unparseable_at_is_skipped_and_advanced(tmp_path, caplog):
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, at="not a time"), msg(2, NOW + 120))))
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    warnings = [rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1 and "relayed alert 1 " in warnings[0]
    assert ntfy.subjects() == ["llama radio: T2"] and r.cursor == Cursor("s", 2)


@pytest.mark.parametrize("field", ["at", "key", "kind", "priority", "title", "message"])
def test_a_message_with_a_non_string_field_is_skipped_and_advanced(tmp_path, caplog, field):
    bad = msg(1, NOW - 10)
    bad[field] = 7
    r, ntfy = _relay(tmp_path, Source(doc("s", bad, msg(2, NOW - 5))))
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    assert "relayed alert 1" in caplog.text
    assert ntfy.subjects() == ["llama radio: T2"] and r.cursor == Cursor("s", 2)


def test_a_naive_at_is_read_as_utc(tmp_path):
    naive = iso(NOW - 7200).removesuffix("Z")
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, at=naive), msg(2, NOW - 10))))
    r.run_pass()
    assert ntfy.subjects() == ["llama radio: T2"]            # 2 h old in UTC, whatever the host's zone


def test_the_cursor_file_is_read_once_at_startup_and_a_bad_one_is_one_warning(tmp_path, caplog):
    path = tmp_path / "alert-relay-cursor.json"
    path.write_text(json.dumps({"stream": "s", "seq": 1}))
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - 30), msg(2, NOW - 20), msg(3, NOW - 10))))
    path.write_text(json.dumps({"stream": "s", "seq": 5}))  # never re-read
    r.run_pass()
    assert ntfy.subjects() == ["llama radio: T2", "llama radio: T3"]
    path.unlink()
    r.run_pass()                                             # the in-memory cursor is authoritative
    assert len(ntfy.sent) == 2

    for content in ("{", "[]", '{"stream": "s"}', '{"stream": 1, "seq": 1}', '{"stream": "s", "seq": true}',
                    '{"stream": "s", "seq": 1.0}', '{"stream": "s", "seq": -1}'):
        path.write_text(content)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
            r2_, _ = _relay(tmp_path, Source(None))
        assert r2_.cursor is None, content
        assert len([rec for rec in caplog.records if rec.levelno == logging.WARNING]) == 1, content

    path.unlink()
    path.mkdir()                                             # IsADirectoryError
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r3, _ = _relay(tmp_path, Source(None))
    assert r3.cursor is None
    assert len([rec for rec in caplog.records if rec.levelno == logging.WARNING]) == 1


def test_no_cursor_file_is_no_cursor_and_no_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r, _ = _relay(tmp_path, Source(None))
    assert r.cursor is None and caplog.records == []


def test_a_failed_cursor_write_is_a_warning_and_never_causes_a_resend(tmp_path, caplog):
    path = tmp_path / "alert-relay-cursor.json"
    path.mkdir()
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - 10))))
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    assert ntfy.subjects() == ["llama radio: T1"]
    assert len([rec for rec in caplog.records if rec.levelno == logging.WARNING]) == 1
    r.run_pass()
    assert len(ntfy.sent) == 1 and r.cursor == Cursor("s", 1)


def test_the_relay_bypasses_the_dispatcher(tmp_path):
    class Recorder:
        name = "rec"

        def __init__(self):
            self.sent = []

        def send(self, subject, body, priority):
            self.sent.append(subject)

    rec = Recorder()
    alerts.configure(alerts.Dispatcher(tmp_path / "alerts.json", [rec], 6 * 3600.0))
    try:
        r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - 10, key="tripped-spend", priority="urgent"))))
        r.run_pass()
        assert ntfy.subjects() == ["llama radio: T1"]
        assert rec.sent == [] and not (tmp_path / "alerts.json").exists()
    finally:
        alerts.configure(None)


# ---- fix round 1 (I1): a message ntfy can never accept is skipped, never a wedge ----

class _NtfyServer:
    """A local stand-in for ntfy (127.0.0.1, an ephemeral port): records each
    POST's Title, Tags and body and answers 200. The real NtfyChannel and
    http.client run end to end, so a header http.client refuses is exercised."""

    def __init__(self):
        import http.server
        import threading

        received = self.received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append((self.headers["Title"], self.headers["Tags"], body.decode()))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/t"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def ntfy_server():
    server = _NtfyServer()
    yield server
    server.close()


def test_a_title_with_a_newline_is_cleaned_and_sent_and_so_is_the_next(tmp_path, ntfy_server):
    channel = alerts.NtfyChannel(ntfy_server.url)
    source = Source(doc("s", msg(1, NOW - 20, title="bad\ntitle\r\nhere"), msg(2, NOW - 10, title="good")))
    r, _ = _relay(tmp_path, source, channel)
    r.run_pass()
    assert [t for t, *_ in ntfy_server.received] == ["llama radio: bad title  here", "llama radio: good"]
    assert r.cursor == Cursor("s", 2)


def test_a_lone_surrogate_is_sent_without_wedging(tmp_path, ntfy_server):
    channel = alerts.NtfyChannel(ntfy_server.url)
    source = Source(doc("s", msg(1, NOW - 20, title="x\ud800", message="m\udfff", key="k\udc00"),
                        msg(2, NOW - 10, title="good")))
    r, _ = _relay(tmp_path, source, channel)
    r.run_pass()
    assert len(ntfy_server.received) == 2 and r.cursor == Cursor("s", 2)
    title, _, body = ntfy_server.received[0]
    assert title == "llama radio: x?" and body.startswith("m?")


def test_format_message_output_is_header_safe_and_encodable():
    s, body, _, _ = relay.format_message(msg(1, title="a\rb\nc", message="m\ud800"), "st\n1")
    assert "\r" not in s and "\n" not in s and s == "st 1: a b c"
    s.encode("utf-8")
    body.encode("utf-8")


@pytest.mark.parametrize("failure", [ValueError("Invalid header value b'x\\ny'"),
                                     UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")])
def test_a_value_error_from_the_channel_skips_that_message_with_a_warning(tmp_path, caplog, failure):
    r, ntfy = _relay(tmp_path, Source(doc("s", msg(1, NOW - 20), msg(2, NOW - 10))), FakeNtfy([failure]))
    with caplog.at_level(logging.WARNING, logger="transmitter.relay"):
        r.run_pass()
    warnings = [rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1 and "relayed alert 1 " in warnings[0] and "stopped" not in warnings[0]
    assert ntfy.subjects() == ["llama radio: T2"] and r.cursor == Cursor("s", 2)
