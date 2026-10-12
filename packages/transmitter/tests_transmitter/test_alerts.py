import email.header
import logging

import pytest

from transmitter import alerts
from transmitter.alerts import Dispatcher, NtfyChannel, SmtpChannel, dispatcher_from_config
from transmitter.config import TransmitterConfig
from transmitter.workspace import Workspace, read_json

H = 3600.0


class Recorder:
    name = "rec"

    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str, int]] = []
        self.fail = fail

    def send(self, subject, body, priority):
        if self.fail:
            raise OSError("down")
        self.sent.append((subject, body, priority))


@pytest.fixture(autouse=True)
def _unconfigure():
    yield
    alerts.configure(None)


def _dispatcher(tmp_path, *channels, now=None):
    clock = {"t": 1000.0}
    d = Dispatcher(tmp_path / "alerts.json", list(channels), 6 * H, "llama radio", now=lambda: clock["t"])
    return d, clock


def test_unconfigured_alerts_only_log(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_first_occurrence_is_sent_then_deduped_until_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("publish", "PUT failed")
    clock["t"] += 60
    alerts.alert("publish", "PUT failed again")
    assert [s[0] for s in rec.sent] == ["llama radio: publish"]
    clock["t"] += 6 * H
    alerts.alert("publish", "still failing")
    assert len(rec.sent) == 2
    assert "(1 more since the last message)" in rec.sent[1][1]
    assert read_json(tmp_path / "alerts.json")["publish"]["active"] is True


def test_resolve_says_so_and_rearms_the_code(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("dead-clock", "stale")
    alerts.resolve("dead-clock")
    assert rec.sent[-1][0] == "llama radio: resolved: dead-clock" and rec.sent[-1][2] == 3
    clock["t"] += 60
    alerts.alert("dead-clock", "stale again")                 # sent at once, not after 6 h
    assert [s[0] for s in rec.sent].count("llama radio: dead-clock") == 2
    alerts.resolve("never-fired")                             # a no-op
    assert d.active() == ["dead-clock"]


def test_an_event_code_stops_counting_as_active_after_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("publish", "PUT failed")
    alerts.alert("dead-clock", "stale")
    assert d.active() == ["dead-clock", "publish"]
    clock["t"] += 6 * H + 1
    assert d.active() == ["dead-clock"]                       # a level code stays until resolved
    alerts.alert("publish", "PUT failed again")               # a new occurrence: sent at once
    assert d.active() == ["dead-clock", "publish"] and len(rec.sent) == 3


def test_a_failing_channel_never_raises_and_the_next_occurrence_retries(tmp_path, caplog):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        alerts.alert("render", "x")
    assert "alert channel rec failed" in caplog.text
    d.channels = [broken, ok]
    clock["t"] += 60
    alerts.alert("render", "x")
    assert len(ok.sent) == 1


def test_dispatcher_from_config_builds_the_configured_channels(tmp_path, caplog):
    cfg = TransmitterConfig(root=tmp_path, alerts={"email_to": "ops@example.com", "ntfy_url": "https://ntfy.example/t"})
    d = dispatcher_from_config(cfg, Workspace(tmp_path), env={"SMTP_USERNAME": "u@example.com", "SMTP_PASSWORD": "pw",
                                                              "NTFY_TOKEN": "tk_x"})
    smtp, ntfy = d.channels
    assert isinstance(smtp, SmtpChannel) and (smtp.host, smtp.port, smtp.sender, smtp.to) == (
        "smtp.gmail.com", 587, "u@example.com", "ops@example.com")
    assert isinstance(ntfy, NtfyChannel) and ntfy.token == "tk_x"
    assert d.repeat_s == 6 * H and d.path == tmp_path / "alerts.json"
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        d = dispatcher_from_config(cfg, Workspace(tmp_path), env={})
    assert [c.name for c in d.channels] == ["ntfy"] and "email alerts are off" in caplog.text


def test_smtp_channel_uses_starttls_and_login(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, msg):
            calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content().strip()))

    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    SmtpChannel("smtp.gmail.com", 587, "u@example.com", "pw", "u@example.com", "ops@example.com").send("subj", "body", 4)
    assert calls == [("connect", "smtp.gmail.com", 587, 20.0), ("starttls",), ("login", "u@example.com", "pw"),
                     ("send", "u@example.com", "ops@example.com", "subj", "body")]


def test_ntfy_channel_posts_with_headers(monkeypatch):
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, method=req.get_method(), headers=dict(req.header_items()), body=req.data,
                    timeout=timeout)
        return Resp()

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)
    NtfyChannel("https://ntfy.example/t", "tk_1").send("llama radio: dead-clock", "stale", 4)
    assert seen["url"] == "https://ntfy.example/t" and seen["method"] == "POST" and seen["body"] == b"stale"
    assert seen["headers"]["Title"] == "llama radio: dead-clock"
    assert seen["timeout"] == 10.0
    assert seen["headers"]["Priority"] == "4" and seen["headers"]["Authorization"] == "Bearer tk_1"


def test_a_corrupt_state_file_does_not_wedge_alerting(tmp_path, caplog):
    path = tmp_path / "alerts.json"
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    path.write_text("{not json")
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        alerts.alert("publish", "x")
        assert len(rec.sent) == 1 and read_json(path)["publish"]["active"] is True
        sent = 1
        for bad in ('{"publish": null, "render": [1], "plan": {"last_sent_at": "x", "count": "y", "active": true}}',
                    "[1]"):
            path.write_text(bad)
            d, _ = _dispatcher(tmp_path, rec)               # a fresh dispatcher: nothing in memory
            alerts.configure(d)
            for code in ("publish", "render", "plan"):
                alerts.alert(code, "again")
                alerts.resolve(code)
            d.active()
            sent += 6                                       # each code: its first message, then "resolved"
            assert len(rec.sent) == sent
    assert "alert dispatch failed" not in caplog.text and "alert resolve failed" not in caplog.text


def test_a_message_no_channel_accepted_is_not_recorded_as_sent(tmp_path):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    alerts.alert("render", "x")
    assert read_json(tmp_path / "alerts.json")["render"]["last_sent_at"] is None
    d.channels = [ok]
    clock["t"] += 60
    alerts.alert("render", "x")
    assert read_json(tmp_path / "alerts.json")["render"]["last_sent_at"] == clock["t"] and len(ok.sent) == 1
    d.channels = [broken]
    alerts.resolve("render")                                  # undelivered: stays active, retried
    assert d.active() == ["render"]
    d.channels = [ok]
    alerts.resolve("render")
    assert ok.sent[-1][0] == "llama radio: resolved: render" and d.active() == []


def test_channels_carry_a_timeout():
    assert SmtpChannel("h", 587, "u", "p", "s", "t").timeout_s == 20.0 and NtfyChannel("https://x").timeout_s == 10.0


def test_a_failed_channel_is_skipped_for_the_cooldown_then_retried(tmp_path):
    broken = Recorder(fail=True)
    calls = []
    orig = broken.send

    def counting(*a):
        calls.append(1)
        return orig(*a)

    broken.send = counting
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    alerts.alert("render", "x")
    alerts.alert("publish", "y")                    # inside the cool-down: not even tried
    assert len(calls) == 1
    clock["t"] += alerts.CHANNEL_COOLDOWN_S + 1
    alerts.alert("render", "x")
    assert len(calls) == 2
    ok = Recorder()
    d.channels = [broken, ok]
    clock["t"] += alerts.CHANNEL_COOLDOWN_S + 1
    alerts.alert("render", "x")                     # broken tried (fails), ok delivers
    assert len(ok.sent) == 1 and len(calls) == 3


def test_a_skipped_channel_counts_as_not_delivered(tmp_path):
    broken = Recorder(fail=True)
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    alerts.alert("render", "x")
    clock["t"] += 10
    d.channels = [broken]                           # still cooling down
    alerts.alert("render", "x")
    assert read_json(tmp_path / "alerts.json")["render"]["last_sent_at"] is None


def test_dedupe_survives_an_unwritable_alerts_file(tmp_path, monkeypatch):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)

    def boom(*a, **k):
        raise OSError("ENOSPC")

    monkeypatch.setattr(alerts, "write_json", boom)
    for _ in range(5):
        clock["t"] += 60
        alerts.alert("publish", "x")
    assert len(rec.sent) == 1 and d.active() == ["publish"]
    clock["t"] += 6 * H
    alerts.alert("publish", "x")
    assert len(rec.sent) == 2 and "(4 more since the last message)" in rec.sent[1][1]
    alerts.resolve("publish")
    assert rec.sent[-1][0] == "llama radio: resolved: publish" and d.active() == []


def test_a_late_delivery_reports_what_was_suppressed(tmp_path):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    alerts.alert("render", "x")
    clock["t"] += alerts.CHANNEL_COOLDOWN_S + 1
    alerts.alert("render", "x")
    d.channels = [ok]
    clock["t"] += 60
    alerts.alert("render", "x")
    assert "(2 more since the first)" in ok.sent[0][1]


def test_one_channel_accepting_records_the_message_as_sent(tmp_path):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken, ok)
    alerts.configure(d)
    alerts.alert("render", "x")
    assert read_json(tmp_path / "alerts.json")["render"]["last_sent_at"] == clock["t"]
    clock["t"] += 60
    alerts.alert("render", "x")
    assert len(ok.sent) == 1 and broken.sent == []


def test_ntfy_title_is_rfc2047_encoded_when_not_latin1(monkeypatch):
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(alerts.urllib.request, "urlopen",
                        lambda req, timeout: seen.update(h=dict(req.header_items())) or Resp())
    NtfyChannel("https://ntfy.example/t").send("radio \u2014 dead-clock", "stale", 4)
    assert seen["h"]["Title"].startswith("=?utf-8?") and seen["h"]["Title"].isascii()
    NtfyChannel("https://ntfy.example/t").send("caf\u00e9: x", "stale", 4)
    assert seen["h"]["Title"].isascii() and seen["h"]["Title"].startswith("=?utf-8?")
    assert email.header.decode_header(seen["h"]["Title"]) == [("caf\u00e9: x".encode(), "utf-8")]
    long = "llama radio: caf\u00e9 " + "\u00e9" * 80
    NtfyChannel("https://ntfy.example/t").send(long, "stale", 4)
    t = seen["h"]["Title"]
    assert t.isascii() and "\n" not in t and "\r" not in t                      # no obs-fold
    assert str(email.header.make_header(email.header.decode_header(t))) == long
