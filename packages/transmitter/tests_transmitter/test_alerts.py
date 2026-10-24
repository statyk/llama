import email.header
import logging
import threading

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


def _gated(d, code, step, message="x"):
    """Reach a gated code's send: GATE consecutive tick observations in which
    it fires, `step` (a step declaring it) having run in each."""
    for _ in range(alerts.GATE):
        d.fire(code, message)
        d.end_observation(alerts.TICK, [step])


def test_unconfigured_alerts_only_log(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_first_occurrence_is_sent_then_deduped_until_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("put-budget", "PUT budget exceeded")
    clock["t"] += 60
    alerts.alert("put-budget", "PUT budget exceeded again")
    assert [s[0] for s in rec.sent] == ["llama radio: put-budget"]
    clock["t"] += 6 * H
    alerts.alert("put-budget", "still exceeded")
    assert len(rec.sent) == 2
    assert "(1 more since the last message)" in rec.sent[1][1]
    assert read_json(tmp_path / "alerts.json")["put-budget"]["active"] is True


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
    alerts.alert("put-budget", "PUT budget exceeded")
    alerts.alert("dead-clock", "stale")
    assert d.active() == ["dead-clock", "put-budget"]
    clock["t"] += 6 * H + 1
    assert d.active() == ["dead-clock"]                       # a level code stays until resolved
    alerts.alert("put-budget", "exceeded again")              # a new occurrence: sent at once
    assert d.active() == ["dead-clock", "put-budget"] and len(rec.sent) == 3


def test_a_failing_channel_never_raises_and_the_next_occurrence_retries(tmp_path, caplog):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        alerts.alert("put-budget", "x")
    assert "alert channel rec failed" in caplog.text
    d.channels = [broken, ok]
    clock["t"] += 60
    alerts.alert("put-budget", "x")
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
        alerts.alert("put-budget", "x")
        assert len(rec.sent) == 1 and read_json(path)["put-budget"]["active"] is True
        sent = 1
        for bad in ('{"put-budget": null, "dead-clock": [1], '
                    '"guard-stale": {"last_sent_at": "x", "count": "y", "active": true}}',
                    "[1]"):
            path.write_text(bad)
            d, _ = _dispatcher(tmp_path, rec)               # a fresh dispatcher: nothing in memory
            alerts.configure(d)
            for code in ("put-budget", "dead-clock", "guard-stale"):
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
    _gated(d, "render", "render")                             # a gated level code: its first message fails
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
    alerts.alert("put-budget", "x")
    alerts.alert("horizon-held", "y")               # inside the cool-down: not even tried
    assert len(calls) == 1
    clock["t"] += alerts.CHANNEL_COOLDOWN_S + 1
    alerts.alert("put-budget", "x")
    assert len(calls) == 2
    ok = Recorder()
    d.channels = [broken, ok]
    clock["t"] += alerts.CHANNEL_COOLDOWN_S + 1
    alerts.alert("put-budget", "x")                 # broken tried (fails), ok delivers
    assert len(ok.sent) == 1 and len(calls) == 3


def test_a_skipped_channel_counts_as_not_delivered(tmp_path):
    broken = Recorder(fail=True)
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    alerts.alert("put-budget", "x")
    clock["t"] += 10
    d.channels = [broken]                           # still cooling down
    alerts.alert("put-budget", "x")
    assert read_json(tmp_path / "alerts.json")["put-budget"]["last_sent_at"] is None


def test_dedupe_survives_an_unwritable_alerts_file(tmp_path, monkeypatch):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)

    def boom(*a, **k):
        raise OSError("ENOSPC")

    monkeypatch.setattr(alerts, "write_json", boom)
    for _ in range(5):
        clock["t"] += 60
        alerts.alert("put-budget", "x")
    assert len(rec.sent) == 1 and d.active() == ["put-budget"]
    clock["t"] += 6 * H
    alerts.alert("put-budget", "x")
    assert len(rec.sent) == 2 and "(4 more since the last message)" in rec.sent[1][1]
    alerts.resolve("put-budget")
    assert rec.sent[-1][0] == "llama radio: resolved: put-budget" and d.active() == []


def test_a_late_delivery_reports_what_was_suppressed(tmp_path):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    alerts.alert("put-budget", "x")
    clock["t"] += alerts.CHANNEL_COOLDOWN_S + 1
    alerts.alert("put-budget", "x")
    d.channels = [ok]
    clock["t"] += 60
    alerts.alert("put-budget", "x")
    assert "(2 more since the first)" in ok.sent[0][1]


def test_one_channel_accepting_records_the_message_as_sent(tmp_path):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken, ok)
    alerts.configure(d)
    alerts.alert("put-budget", "x")
    assert read_json(tmp_path / "alerts.json")["put-budget"]["last_sent_at"] == clock["t"]
    clock["t"] += 60
    alerts.alert("put-budget", "x")
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


# ---- the 3-consecutive gate (spec Part 1) ----

def obs(d, *steps):
    d.end_observation(alerts.TICK, steps)


def _fire_obs(d, code, *steps, message="x"):
    d.fire(code, message)
    obs(d, *steps)


def test_gated_codes_are_exactly_the_approved_list():
    assert alerts.GATE == 3
    assert alerts.GATED_CODES == {"prune", "publish", "publish-state", "station-root", "plan", "render",
                                  "dead-clock-check"}
    assert frozenset().union(*alerts.STEP_CODES.values()) == alerts.GATED_CODES
    assert frozenset().union(*alerts.OBSERVER_STEPS.values()) == set(alerts.STEP_CODES)
    for code in ("put-budget", "frame-count-drift", "monitor-stalled", "dead-clock", "guard-stale", "horizon-held"):
        assert code not in alerts.GATED_CODES


@pytest.mark.parametrize("code", ["put-budget", "frame-count-drift", "monitor-stalled", "dead-clock", "guard-stale",
                                  "horizon-held"])
def test_each_ungated_code_sends_on_its_first_fire(tmp_path, code):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    d.fire(code, "m")
    assert [s[0] for s in rec.sent] == [f"llama radio: {code}"]


def test_a_gated_code_sends_only_on_the_third_consecutive_observation(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    for _ in range(2):
        d.fire("publish", "PUT failed")
        obs(d, "lead", "publish")
        clock["t"] += 60
        assert rec.sent == [] and d.active() == [] and "publish" not in (read_json(tmp_path / "alerts.json", {}) or {})
    d.fire("publish", "PUT failed")
    obs(d, "lead", "publish")
    assert [s[0] for s in rec.sent] == ["llama radio: publish"] and "3 consecutive" in rec.sent[0][1]
    assert d.active() == ["publish"]


def test_an_observation_where_a_declaring_step_ran_without_the_code_resets_its_streak(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    for _ in range(2):
        _fire_obs(d, "publish", "lead", "publish")
    obs(d, "lead", "publish")                               # publish ran and did not fail
    assert d._streak["publish"] == 0
    _fire_obs(d, "publish", "lead", "publish")
    assert rec.sent == []
    for _ in range(2):
        _fire_obs(d, "publish", "lead", "publish")
    assert [s[0] for s in rec.sent] == ["llama radio: publish"]


def test_an_observation_where_no_declaring_step_ran_neither_advances_nor_resets(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    for _ in range(2):
        _fire_obs(d, "plan", "lead", "plan", "render", "publish")
    obs(d, "lead", "publish")                               # an idle tick: plan did not run
    assert d._streak["plan"] == 2 and rec.sent == []
    _fire_obs(d, "plan", "lead", "plan", "render", "publish")
    assert [s[0] for s in rec.sent] == ["llama radio: plan"]


def test_repeated_fires_within_one_observation_count_once(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    for _ in range(2):
        d.fire("publish", "a")
        d.fire("publish", "b")
        obs(d, "lead", "publish")
    assert rec.sent == [] and d._streak["publish"] == 2
    d.fire("publish", "a")
    d.fire("publish", "b")
    obs(d, "lead", "publish")
    assert len(rec.sent) == 1 and d._streak["publish"] == 3


def test_a_retried_first_message_keeps_the_gate_note(tmp_path):
    broken = Recorder(fail=True)
    d, clock = _dispatcher(tmp_path, broken)
    for _ in range(3):
        _fire_obs(d, "publish", "lead", "publish")
    assert broken.sent == [] and d.active() == ["publish"]
    assert read_json(tmp_path / "alerts.json")["publish"]["last_sent_at"] is None
    ok = Recorder()
    d.channels = [ok]
    clock["t"] += 60
    _fire_obs(d, "publish", "lead", "publish")
    assert len(ok.sent) == 1 and "3 consecutive" in ok.sent[0][1]


def test_an_undelivered_first_message_is_resent_without_the_gate(tmp_path):
    broken = Recorder(fail=True)
    d, clock = _dispatcher(tmp_path, broken)
    for _ in range(3):
        _fire_obs(d, "publish", "lead", "publish")
    assert d.active() == ["publish"] and read_json(tmp_path / "alerts.json")["publish"]["last_sent_at"] is None
    obs(d, "lead", "publish")                               # a clean observation
    assert d._streak["publish"] == 0
    ok = Recorder()
    d.channels = [ok]
    clock["t"] += 60
    d.fire("publish", "x")                                  # streak 1: the undelivered first message goes at once
    assert d._streak["publish"] == 1
    assert [s[0] for s in ok.sent] == ["llama radio: publish"] and "3 consecutive" in ok.sent[0][1]


def test_the_send_decision_is_made_at_the_first_fire_with_its_message(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    for _ in range(2):
        _fire_obs(d, "publish", "lead", "publish")
    d.fire("publish", "A")
    d.fire("publish", "B")
    obs(d, "lead", "publish")
    assert len(rec.sent) == 1 and rec.sent[0][1].startswith("A")


def test_ending_one_observer_never_touches_the_other_observers_codes(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    for _ in range(2):
        d.fire("dead-clock-check", "x")
        d.end_observation(alerts.MONITOR, ["dead-clock-check"])
        d.fire("publish", "x")
        obs(d, "lead", "publish")
    d.end_observation(alerts.TICK, ["lead", "plan", "render", "publish"])     # resets publish only
    d.end_observation(alerts.MONITOR, [])                                       # an empty pass: resets nothing
    assert d._streak["dead-clock-check"] == 2 and d._streak["publish"] == 0
    d.fire("dead-clock-check", "x")
    assert [s[0] for s in rec.sent] == ["llama radio: dead-clock-check"]


def test_a_single_blip_inside_an_active_episode_never_sends_a_repeat(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    for _ in range(3):
        _fire_obs(d, "publish", "lead", "publish")
    assert len(rec.sent) == 1
    clock["t"] += 6 * H                       # a repeat is due; the event code has not expired
    obs(d, "lead", "publish")                 # reset
    _fire_obs(d, "publish", "lead", "publish")
    assert len(rec.sent) == 1 and d.active() == ["publish"]
    assert read_json(tmp_path / "alerts.json")["publish"]["last_fired_at"] == clock["t"]


def test_a_gated_level_code_still_resolves_and_says_so(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    for _ in range(3):
        _fire_obs(d, "station-root", "lead", "plan")
    assert [s[0] for s in rec.sent] == ["llama radio: station-root"]
    d.resolve("station-root")
    assert rec.sent[-1][0] == "llama radio: resolved: station-root" and d.active() == []


def test_after_a_restart_an_active_episode_continues_without_a_send_until_the_streak_rebuilds(tmp_path):
    rec = Recorder()
    d1, clock = _dispatcher(tmp_path, rec)
    for _ in range(3):
        _fire_obs(d1, "publish", "lead", "publish")
    assert len(rec.sent) == 1
    clock["t"] += 6 * H
    d2 = Dispatcher(tmp_path / "alerts.json", [rec], 6 * H, "llama radio", now=lambda: clock["t"])
    for _ in range(2):
        _fire_obs(d2, "publish", "lead", "publish")
    assert len(rec.sent) == 1 and d2.active() == ["publish"]
    _fire_obs(d2, "publish", "lead", "publish")
    assert len(rec.sent) == 2 and "more since the last message" in rec.sent[1][1]


def test_the_dispatcher_serialises_fire_under_its_lock(tmp_path):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    d._lock.acquire()
    t = threading.Thread(target=d.fire, args=("put-budget", "m"))
    t.start()
    t.join(0.2)
    assert t.is_alive() and rec.sent == []
    d._lock.release()
    t.join(2)
    assert len(rec.sent) == 1


@pytest.mark.parametrize("call", ["resolve", "active", "end_observation"])
def test_resolve_active_and_end_observation_take_the_lock(tmp_path, call):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    args = {"resolve": ("put-budget",), "active": (), "end_observation": (alerts.TICK, ["publish"])}[call]
    d._lock.acquire()
    t = threading.Thread(target=getattr(d, call), args=args)
    t.start()
    t.join(0.2)
    assert t.is_alive()
    d._lock.release()
    t.join(2)
    assert not t.is_alive()


def test_end_observation_refuses_an_unknown_observer_or_a_foreign_step(tmp_path):
    d, _ = _dispatcher(tmp_path)
    with pytest.raises(ValueError):
        d.end_observation("nobody", ["plan"])
    with pytest.raises(ValueError):
        d.end_observation(alerts.TICK, ["dead-clock-check"])
    with pytest.raises(ValueError):
        d.end_observation(alerts.MONITOR, ["publish"])


def test_the_module_level_wrappers_never_raise(tmp_path, caplog):
    rec = Recorder()
    d, _ = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.end_observation("nobody", ["plan"])                      # unknown observer: logged, not raised
    alerts.end_observation(alerts.TICK, ["dead-clock-check"])       # another observer's step: logged, not raised
    assert "end_observation" in caplog.text
    alerts.configure(None)
    alerts.end_observation(alerts.TICK, ["plan"])                   # no dispatcher: a no-op
