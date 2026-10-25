import logging
import threading

import pytest

from tests_transmitter.helpers import NOW, TEMPLATE_PATH, FakeBucket, FakeEngine, make_station, write_seg
from transmitter import alerts, grid, monitor, pipeline, publish, r2, service
from transmitter.errors import FrameCountDrift, PlanError, PublishLocked, StationRootError
from transmitter.planner import read_plan
from transmitter.segment import segment_key
from transmitter.state import save_fallback_version


def _publisher(st, bucket, *, fallback: bool = True):
    if fallback:                                  # as `transmitter fallback render` records it
        save_fallback_version(st.ws, "fb0123456789")
    uploader = publish.Uploader(bucket, "b", publish.PutBudget(st.ws.puts_path, 17_500, today=lambda: "d"),
                                sleep=lambda s: None)
    return publish.Publisher(ws=st.ws, cfg=st.cfg, epoch=st.epoch, uploader=uploader,
                             template=TEMPLATE_PATH.read_text(),
                             analysis_for=lambda row: service.row_analysis(st, row), log=lambda m: None)


def test_alert_logs(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_runner_fills_to_the_lead_then_idles_until_low_water(tmp_path):
    engine = FakeEngine()
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    for _ in range(5):
        runner.tick(NOW)
        if not runner.filling:
            break
    assert not runner.filling
    assert runner.lead_us(NOW) >= st.lead_us - grid.D_US
    seg_puts = len([k for k in bucket.puts() if k.startswith("seg/")])
    encoded = list(engine.encoded)
    runner.tick(NOW)                                        # lead is full: nothing new
    assert engine.encoded == encoded
    assert len([k for k in bucket.puts() if k.startswith("seg/")]) == seg_puts
    runner.tick(NOW + 200 * 1_000_000)                      # 160 s of lead < 180 s low water
    assert len([k for k in bucket.puts() if k.startswith("seg/")]) > seg_puts


def test_runner_alerts_and_keeps_publishing_when_planning_fails(tmp_path, caplog):
    st, _ = make_station(tmp_path)
    pipeline.plan_step(st, NOW)
    pipeline.render_step(st, NOW)                          # segments exist, unpublished
    (st.cfg.station.root / ".station-root").unlink()
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
    assert "ALERT station-root" in caplog.text and ".station-root" in caplog.text
    assert any(k.startswith("seg/") for k in bucket.puts())
    assert "state/horizon.json" in bucket.objects          # publishing really happened


def test_runner_survives_an_unexpected_error_and_the_next_tick_runs(tmp_path, caplog, monkeypatch):
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    real = pipeline.render_step
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_step", flaky)
    with caplog.at_level(logging.ERROR):
        runner.tick(NOW)
        runner.tick(NOW)
    assert "ALERT render: KeyError: 'boom'" in caplog.text and "Traceback" in caplog.text
    assert len(calls) == 2
    assert any(k.startswith("seg/") for k in bucket.puts())


def test_frame_count_drift_halts_filling_but_keeps_publishing(tmp_path, caplog):
    engine = FakeEngine(drift=1)
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
        assert runner.halted and not runner.filling
        attempts = list(engine.encoded)
        n = read_plan(st.ws.plan_path)[0].start_frame // grid.SEGMENT_FRAMES
        write_seg(st.ws, "etest", n)                       # rendered before the halt
        runner.tick(NOW + 60_000_000)
        runner.tick(NOW + 120_000_000)
    assert caplog.text.count("ALERT frame-count-drift") == 1
    assert engine.encoded == attempts                      # no further render attempts
    assert segment_key("etest", n) in bucket.objects       # publishing went on


def test_run_with_max_ticks_sleeps_between_ticks(tmp_path):
    st, _ = make_station(tmp_path)
    sleeps = []
    clock = iter([NOW, NOW + 60_000_000, NOW + 120_000_000])
    runner = service.Runner(st, _publisher(st, FakeBucket()), clock=lambda: next(clock),
                            sleep=sleeps.append, tick_s=60.0)
    runner.run(max_ticks=3)
    assert len(sleeps) == 2


def test_status_lines(tmp_path):
    st, _ = make_station(tmp_path)
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    lines = service.status_lines(st.cfg, NOW)
    assert lines[0].startswith("epoch      etest")
    assert any(l.startswith("published  nothing yet") for l in lines)
    assert any("fallback   none" in l for l in lines)


@pytest.mark.parametrize("exc", [PlanError("no show fits"), StationRootError("root gone")])
def test_plan_errors_alert_and_the_loop_continues(tmp_path, caplog, monkeypatch, exc):
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    real = pipeline.plan_step
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise exc
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "plan_step", flaky)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
        assert not runner.halted
        runner.tick(NOW)
    code = "station-root" if isinstance(exc, StationRootError) else "plan"
    assert f"ALERT {code}: {type(exc).__name__}: {exc}" in caplog.text
    assert len(calls) == 2 and any(k.startswith("seg/") for k in bucket.puts())


def test_frame_count_drift_sets_halted_and_alerts(tmp_path, caplog, monkeypatch):
    st, _ = make_station(tmp_path)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)

    def drift(*args, **kwargs):
        raise FrameCountDrift("encoder drifted")

    monkeypatch.setattr(pipeline, "render_step", drift)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
    assert runner.halted and not runner.filling
    assert "ALERT frame-count-drift: encoder drifted" in caplog.text


def _report_pub(**kw):
    return publish.PublishReport(**kw)


def test_publish_all_alerts_put_budget_from_publish(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(stopped="put-budget", error="over"))
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport())
    with caplog.at_level(logging.WARNING):
        service.publish_all(p, NOW)
    assert "ALERT put-budget: over" in caplog.text


def test_publish_all_alerts_put_budget_from_prune(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub())
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport(stopped="put-budget", error="over"))
    with caplog.at_level(logging.WARNING):
        service.publish_all(p, NOW)
    assert "ALERT put-budget: over" in caplog.text


def test_publish_all_alerts_a_prune_stopped_for_no_fallback(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub())
    monkeypatch.setattr(publish, "prune",
                        lambda p, t, notify=None: publish.PruneReport(stopped="no-fallback", error=publish.NO_FALLBACK))
    with caplog.at_level(logging.WARNING):
        service.publish_all(p, NOW)
    assert "ALERT prune: stopped: no-fallback: no fallback rendered" in caplog.text


def test_publish_all_warns_on_high_water_without_alerting(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub())
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport(stopped="high-water"))
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "high-water" in caplog.text and "ALERT" not in caplog.text
    assert any(r.levelno == logging.WARNING and "high-water" in r.getMessage() for r in caplog.records)


def test_publish_all_warns_on_a_held_horizon_without_alerting(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    err = "horizon held: segment 5 is below the high-water mark 9"
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(error=err, held=True))
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport())
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "ALERT" not in caplog.text
    assert any(r.levelno == logging.WARNING and "horizon held" in r.getMessage() for r in caplog.records)


def test_publish_all_alerts_errors_and_logs_guard(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(error="PUT x failed"))
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport(error="DELETE y failed"))
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "ALERT publish: PUT x failed" in caplog.text and "ALERT prune: DELETE y failed" in caplog.text
    caplog.clear()
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(stopped="guard"))
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport(stopped="guard"))
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "ALERT" not in caplog.text and "guard" in caplog.text



def test_a_persistent_held_horizon_escalates_on_the_third_pass_and_resets(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    err = "horizon held: segment 5 is below the high-water mark 9"
    held = {"on": True}
    monkeypatch.setattr(publish, "publish_batch",
                        lambda p, t: _report_pub(error=err, held=True) if held["on"] else _report_pub())
    monkeypatch.setattr(publish, "prune", lambda p, t, notify=None: publish.PruneReport())
    tracker = service.HeldTracker()
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            service.publish_all(p, NOW, tracker)
        assert "ALERT" not in caplog.text
        assert sum("horizon held" in r.getMessage() for r in caplog.records) == 2
        service.publish_all(p, NOW, tracker)
        assert caplog.text.count("ALERT horizon-held") == 1
        held["on"] = False
        service.publish_all(p, NOW, tracker)               # a clean batch resets the streak
        held["on"] = True
        caplog.clear()
        for _ in range(2):
            service.publish_all(p, NOW, tracker)
    assert "ALERT" not in caplog.text


def test_runner_warns_without_traceback_or_alert_on_publish_locked(tmp_path, caplog, monkeypatch):
    st, _ = make_station(tmp_path)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)

    def locked(*args, **kwargs):
        raise PublishLocked("another publish holds the lock")

    monkeypatch.setattr(publish, "publish_batch", locked)
    with caplog.at_level(logging.WARNING):
        runner.tick(NOW)
    assert "ALERT" not in caplog.text and "Traceback" not in caplog.text
    assert any(r.levelno == logging.WARNING and "lock" in r.getMessage() for r in caplog.records)


def test_status_lines_populated(tmp_path):
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    for _ in range(5):
        runner.tick(NOW)
        if not runner.filling:
            break
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    first_row = read_plan(st.ws.plan_path)[0]
    t = st.epoch.epoch_us + (first_row.start_frame + 10) * grid.FRAME_SAMPLES * 1_000_000 // grid.SAMPLE_RATE
    lines = service.status_lines(st.cfg, t)
    assert any(l.startswith("plan       ") and "rows through" in l for l in lines)
    assert f"on air     {first_row.slug}" in lines
    assert any(l.startswith("published  segments ") and "lead" in l for l in lines)


def test_runner_alerts_and_spends_nothing_until_a_fallback_is_rendered(tmp_path, caplog):
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket, fallback=False), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
        runner.tick(NOW + 60_000_000)
    assert caplog.text.count("ALERT publish:") == 2 and "transmitter fallback render" in caplog.text
    assert bucket.puts() == []                              # nothing PUT, nothing re-PUT
    assert any(st.ws.seg_dir("etest").iterdir())            # rendered and waiting
    save_fallback_version(st.ws, "fb0123456789")
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW + 120_000_000)
    assert "ALERT" not in caplog.text
    assert bucket.json("state/horizon.json")["fallback_version"] == "fb0123456789"


@pytest.mark.parametrize("damage", [b'{"last": 1', b"[1, 2]"])
def test_an_unreadable_publish_state_alerts_and_fails_the_tick_closed(tmp_path, caplog, damage):
    # publish.json is the local mirror of R2: without it neither the lead
    # (filling) nor the publish/prune ranges are known. Alert, do nothing,
    # and do not crash-loop the service.
    engine = FakeEngine()
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    st.ws.publish_state_path.parent.mkdir(parents=True, exist_ok=True)
    st.ws.publish_state_path.write_bytes(damage)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
    assert "ALERT publish-state:" in caplog.text
    assert bucket.log == [] and engine.analyzed == [] and not st.ws.plan_path.exists()
    st.ws.publish_state_path.unlink()                       # the operator repairs it
    runner.tick(NOW)
    assert "state/horizon.json" in bucket.objects


class _Rec:
    name = "rec"

    def __init__(self):
        self.sent = []

    def send(self, subject, body, priority):
        self.sent.append(subject)


@pytest.mark.parametrize("step, codes", [("plan_step", ("station-root", "plan")), ("render_step", ("render",))])
def test_a_successful_step_resolves_its_level_codes(tmp_path, monkeypatch, step, codes):
    st, _ = make_station(tmp_path)
    rec = _Rec()
    alerts.configure(alerts.Dispatcher(tmp_path / "alerts.json", [rec], 6 * 3600.0))
    try:
        runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
        real = getattr(pipeline, step)
        fail = {"on": True}

        def flaky(*a, **k):
            if fail["on"]:
                raise StationRootError("root gone") if step == "plan_step" else RuntimeError("encode failed")
            return real(*a, **k)

        monkeypatch.setattr(pipeline, step, flaky)
        for _ in range(alerts.GATE - 1):
            runner.tick(NOW)
        assert rec.sent == []                               # gated: below 3 consecutive ticks
        runner.tick(NOW)
        fired = "station-root" if step == "plan_step" else "render"
        assert rec.sent == [f"llama radio: {fired}"]
        fail["on"] = False
        runner.tick(NOW)
        assert f"llama radio: resolved: {fired}" in rec.sent
        assert runner.p is not None and alerts._dispatcher.active() == []
    finally:
        alerts.configure(None)


class FakeMonitor:
    """Stands in for monitor.MonitorLoop: records what the Runner asks of it."""

    def __init__(self, started=False, stalled=(), record=None):
        self.started = started
        self._stalled = list(stalled)
        self.record = [] if record is None else record

    def run_pass(self, *, relay=True):
        self.record.append(("run_pass", relay, threading.current_thread()))

    def stalled(self):
        self.record.append(("stalled",))
        return self._stalled.pop(0) if self._stalled else None

    def start(self):
        self.record.append(("start",))
        self.started = True

    def stop(self, timeout_s=None):
        self.record.append(("stop",))


def test_tick_no_longer_runs_the_monitor(tmp_path):
    st, _ = make_station(tmp_path)
    mon = FakeMonitor()
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=mon)
    runner.tick(NOW)
    runner.tick(NOW + 60_000_000)
    assert mon.record == []


def test_monitor_stalled_fires_at_once_and_resolves_when_passes_are_fresh(tmp_path):
    st, _ = make_station(tmp_path)
    rec = _Rec()
    alerts.configure(alerts.Dispatcher(tmp_path / "alerts.json", [rec], 6 * 3600.0))
    try:
        mon = FakeMonitor(started=True, stalled=["the dead-clock monitor has completed no pass for 6 minutes", None])
        runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=mon)
        runner.tick(NOW)
        assert rec.sent == ["llama radio: monitor-stalled"]            # one tick: not gated
        assert "monitor-stalled" in alerts._dispatcher.active()
        runner.tick(NOW)
        assert rec.sent == ["llama radio: monitor-stalled", "llama radio: resolved: monitor-stalled"]
        assert alerts._dispatcher.active() == []
    finally:
        alerts.configure(None)


def test_monitor_stalled_is_checked_on_the_failed_lead_read_path(tmp_path, caplog):
    st, _ = make_station(tmp_path)
    mon = FakeMonitor(started=True, stalled=["the dead-clock monitor thread is not running"])
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=mon)
    st.ws.publish_state_path.parent.mkdir(parents=True, exist_ok=True)
    st.ws.publish_state_path.write_bytes(b'{"last": 1')
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
    assert "ALERT publish-state:" in caplog.text
    assert "ALERT monitor-stalled: the dead-clock monitor thread is not running" in caplog.text


def test_a_raising_stalled_check_alerts_monitor_stalled_and_the_tick_goes_on(tmp_path, monkeypatch, caplog):
    # Task 4b review BM1: the stalled check must not raise out of tick (it
    # would end run() and restart-loop the service); it fails toward alerting,
    # and the tick's observation still ends after it.
    seen = _observations(monkeypatch)
    fired = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: fired.append((code, msg)))
    st, _ = make_station(tmp_path)

    class Broken(FakeMonitor):
        def stalled(self):
            seen.append(("stalled",))
            raise RuntimeError("boom")

    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=Broken(started=True))
    with caplog.at_level(logging.ERROR, logger="transmitter"):
        assert runner.tick(NOW) is None                     # returns: nothing escapes
    assert seen == [("stalled",), (alerts.TICK, {"lead", "plan", "render", "publish"})]
    assert [c for c, _ in fired] == ["monitor-stalled"] and "RuntimeError: boom" in fired[0][1]
    assert "monitor-stalled check failed" in caplog.text and "Traceback" in caplog.text


def test_monitor_stalled_is_ungated_and_a_level_code():
    assert "monitor-stalled" not in alerts.GATED_CODES and "monitor-stalled" in alerts.LEVEL_CODES


def test_no_started_monitor_means_no_monitor_stalled_check(tmp_path, caplog):
    st, _ = make_station(tmp_path)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None).tick(NOW)
    mon = FakeMonitor(started=False, stalled=["x"])
    service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=mon).tick(NOW)
    assert mon.record == [] and "monitor-stalled" not in caplog.text


def test_run_starts_the_monitor_and_stops_it_when_the_loop_raises(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    record = []
    mon = FakeMonitor(record=record)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=mon,
                            notify=lambda m: record.append(("notify", m)))

    def interrupted(t_us):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "tick", interrupted)
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert [r for r in record if r[0] in ("start", "stop")] == [("start",), ("stop",)]
    assert record == [("notify", "READY=1"), ("start",), ("stop",), ("notify", "STOPPING=1")]


def test_run_once_checks_once_on_the_main_thread_without_relay_or_thread(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    record = []
    real = service.publish_all

    def publish_all(*a, **k):
        record.append(("publish",))
        return real(*a, **k)

    monkeypatch.setattr(service, "publish_all", publish_all)
    mon = FakeMonitor(record=record)
    threads = threading.active_count()
    service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=mon).run_once()
    assert threading.active_count() == threads
    assert record == [("publish",), ("run_pass", False, threading.main_thread())]


def test_open_monitor_needs_site_url(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    st.cfg.publish.bucket = "b"
    made = []
    monkeypatch.setattr(service, "make_reader_client", lambda cfg: made.append(threading.current_thread()) or FakeBucket())
    assert service.open_monitor(st) is None and made == []
    st.cfg.antenna.site_url = "https://radio.example.org/"
    loop = service.open_monitor(st)
    assert isinstance(loop, monitor.MonitorLoop) and not loop.started
    m = loop.deadclock
    assert m.url == "https://radio.example.org/live.m3u8" and m.dead_clock_s == 120.0 and m.guard_stale_s == 2700.0
    assert m.forbidden_checks == 17                     # guard_check_minutes 15 + 2
    assert made == [threading.main_thread()]            # built before any thread starts
    assert loop.reader.bucket == "b" and loop.relay is None


def test_open_monitor_with_ntfy_only_relays_without_a_dead_clock_check(tmp_path, monkeypatch):
    from transmitter import relay as relay_mod

    st, _ = make_station(tmp_path)
    st.cfg.publish.bucket = "b"
    st.cfg.alerts.ntfy_url = "https://ntfy.example/t"
    st.cfg.antenna.station_name = "test radio"
    made = []
    monkeypatch.setattr(service, "make_reader_client", lambda cfg: made.append(threading.current_thread()) or FakeBucket())
    env = {"NTFY_TOKEN": "tk_relay"}
    loop = service.open_monitor(st, env=env)
    assert isinstance(loop, monitor.MonitorLoop) and not loop.started and loop.deadclock is None
    r = loop.relay
    assert isinstance(r, relay_mod.Relay)
    assert isinstance(r.channel, alerts.NtfyChannel)
    assert r.channel.url == "https://ntfy.example/t" and r.channel.token == "tk_relay"
    assert r.station == "test radio" and r.cursor_path == st.ws.relay_cursor_path
    assert r.get_json == loop.reader.get_json           # the monitor's get-only reader
    d = alerts.dispatcher_from_config(st.cfg, st.ws, env)
    assert d.channels and all(ch is not r.channel for ch in d.channels)
    assert made == [threading.main_thread()]


def test_no_ntfy_means_no_relay_and_one_warning(tmp_path, monkeypatch, caplog):
    st, _ = make_station(tmp_path)
    st.cfg.publish.bucket = "b"
    st.cfg.antenna.site_url = "https://radio.example.org"
    monkeypatch.setattr(service, "make_reader_client", lambda cfg: FakeBucket())
    with caplog.at_level(logging.WARNING, logger="transmitter"):
        loop = service.open_monitor(st, env={})
    assert loop is not None and loop.deadclock is not None and loop.relay is None
    assert len([r for r in caplog.records if "not relayed" in r.getMessage()]) == 1


def test_neither_site_url_nor_ntfy_means_no_monitor(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    st.cfg.publish.bucket = "b"
    made = []
    monkeypatch.setattr(service, "make_reader_client", lambda cfg: made.append(1) or FakeBucket())
    assert service.open_monitor(st, env={"NTFY_TOKEN": "x"}) is None and made == []


def test_make_reader_client_has_short_timeouts(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    seen = {}
    monkeypatch.setattr(r2, "make_client", lambda cfg, **kw: seen.update(cfg=cfg, **kw) or "client")
    assert service.make_reader_client(st.cfg) == "client"
    assert seen == {"cfg": st.cfg.publish, "connect_timeout": 5, "read_timeout": 10}


def _with_epoch(st):
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    return st


def test_status_shows_the_cloud_state_and_active_alerts(tmp_path):
    import json as _json

    st = _with_epoch(make_station(tmp_path)[0])
    (st.ws.root / "alerts.json").write_text(_json.dumps({"dead-clock": {"active": True}, "render": {"active": False},
                                                         "publish": {"active": True, "last_fired_at": 0.0}}))
    docs = {
        "state/guard.json": {"schema": 1, "tripped": True, "reason": "blind", "tripped_at": "2026-10-20T06:00:00.000Z",
                             "last_error": "analytics: HTTP 503", "last_success": "2026-10-20T00:00:00.000Z",
                             "waf": {"enabled": True, "error": None}, "period": None, "evaluation": None,
                             "since": "2026-10-20T06:00:00.000Z", "tripped_period_start": None,
                             "tripped_budget_usd": None, "evaluated_at": None},
        "state/offair.json": {"offair": True, "reason": "objection", "since": "2026-10-20T05:00:00.000Z", "until": None},
        "state/alerts.json": {"tripped-blind": {"active": True}},
    }
    lines = service.status_lines(st.cfg, NOW, cloud=docs.get)
    text = "\n".join(lines)
    assert "alerts     hugo: dead-clock" in lines           # the 1970 publish event has gone stale
    assert "guard      TRIPPED (blind)" in text and "reading    failing since 2026-10-20T00:00:00.000Z" in text
    assert "killswitch enabled" in text
    assert "offair     ON since 2026-10-20T05:00:00.000Z (objection)" in text
    assert "alerts     cloud: tripped-blind" in text
    assert "anchors    none" in text


def test_status_without_cloud_access_still_prints_the_local_half(tmp_path):
    from transmitter.errors import CloudStateError

    st = _with_epoch(make_station(tmp_path)[0])

    def broken(key):
        raise CloudStateError("cannot read state/guard.json: boom")

    assert service.status_lines(st.cfg, NOW, cloud=broken)[-1] == "cloud      unavailable: cannot read state/guard.json: boom"
    assert service.status_lines(st.cfg, NOW, cloud_error="set R2_ACCESS_KEY_ID")[-1] == \
        "cloud      unavailable: set R2_ACCESS_KEY_ID"


# ---- status never trusts a state document (fix round 1: G1-G6) ----

def _reader(docs):
    """A cloud reader over raw bytes, through the real cloudstate.get_json."""
    import json as _json
    from transmitter import cloudstate

    bucket = FakeBucket()
    for key, doc in docs.items():
        bucket.objects[key] = {"Body": doc if isinstance(doc, bytes) else _json.dumps(doc).encode(),
                               "ContentType": "application/json", "CacheControl": "no-store"}
    return lambda key: cloudstate.get_json(bucket, "b", key)


@pytest.mark.parametrize("raw", [b"{not json", b"[1,2]"])
def test_status_survives_a_corrupt_local_alerts_file(tmp_path, raw):
    st = _with_epoch(make_station(tmp_path)[0])
    (st.ws.root / "alerts.json").write_bytes(raw)
    lines = service.status_lines(st.cfg, NOW, cloud=_reader({}))
    assert f"alerts     hugo: unreadable ({st.ws.alerts_path})" in lines
    assert any(line.startswith("fallback") for line in lines) and "alerts     cloud: none" in lines


def test_status_renders_a_malformed_or_expired_raise_through_the_verdict(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])
    bad = service.status_lines(st.cfg, NOW, cloud=_reader({"state/budget.json": {"budget_usd": "abc"}}))
    assert any(line.startswith("raise      unknown until") and "ignored: budget_usd is not a number" in line
               for line in bad)
    old = service.status_lines(st.cfg, NOW, cloud=_reader(
        {"state/budget.json": {"budget_usd": 20, "expires": "2000-01-01T00:00:00Z"}}))
    assert any(line.startswith("raise      $20.00 until 2000-01-01") and line.endswith("(expired)") for line in old)
    assert "alerts     cloud: none" in old


@pytest.mark.parametrize("doc", [{"offair": "true"}, {}])
def test_status_flags_a_corrupt_offair_document(tmp_path, doc):
    st = _with_epoch(make_station(tmp_path)[0])
    lines = service.status_lines(st.cfg, NOW, cloud=_reader({"state/offair.json": doc}))
    assert ("offair     CORRUPT: the clock treats the station as off the air; "
            "rewrite with transmitter offair on|off") in lines


def test_status_offair_absent_and_false_read_as_off(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])
    assert "offair     off" in service.status_lines(st.cfg, NOW, cloud=_reader({}))
    assert "offair     off" in service.status_lines(st.cfg, NOW, cloud=_reader({"state/offair.json": {"offair": False}}))


def test_status_flags_a_guard_document_the_guard_would_reject(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])
    lines = service.status_lines(st.cfg, NOW, cloud=_reader({"state/guard.json": {"tripped": False}}))
    corrupt = [line for line in lines if line.startswith("guard      CORRUPT (")]
    assert corrupt and corrupt[0].endswith("): the clock treats it as a spend trip")
    assert "offair     off" in lines


def test_one_unreadable_document_blanks_only_its_own_line(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])
    lines = service.status_lines(st.cfg, NOW, cloud=_reader(
        {"state/offair.json": b"not json", "state/alerts.json": {"x": {"active": True}, "y": {"active": False}}}))
    assert any(line.startswith("offair     unreadable: state/offair.json is not JSON") for line in lines)
    assert "alerts     cloud: x" in lines            # the inactive entry is not listed
    assert any(line.startswith("guard      no state/guard.json") for line in lines)
    assert not any(line.startswith("cloud      unavailable") for line in lines)


def test_get_json_turns_a_body_read_failure_into_a_cloud_state_error():
    from transmitter import cloudstate
    from transmitter.errors import CloudStateError

    class Body:
        def read(self):
            raise ConnectionError("reset")

    class Client:
        def get_object(self, **kw):
            return {"Body": Body()}

    with pytest.raises(CloudStateError, match="cannot read state/guard.json: reset"):
        cloudstate.get_json(Client(), "b", "state/guard.json")


def test_status_turns_any_reader_exception_into_the_unavailable_line(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])

    def boom(key):
        raise ValueError("odd")

    lines = service.status_lines(st.cfg, NOW, cloud=boom)
    assert lines[-1] == "cloud      unavailable: odd"
    assert any(line.startswith("fallback") for line in lines)


def test_status_without_an_epoch_still_shows_the_cloud_half(tmp_path):
    st = make_station(tmp_path)[0]
    lines = service.status_lines(st.cfg, NOW, cloud=_reader({}))
    assert lines[0].startswith("no epoch yet") and "offair     off" in lines
    assert service.status_lines(st.cfg, NOW, cloud_error="no keys")[-1] == "cloud      unavailable: no keys"


def test_cli_status_with_a_malformed_endpoint_prints_the_local_half(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from transmitter.cli import app

    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))

    def bad_client(cfg):
        raise ValueError("Invalid endpoint: nope")

    monkeypatch.setattr(service, "make_client", bad_client)
    cfgp = tmp_path / "c.toml"
    cfgp.write_text('[publish]\nbucket = "b"\n')
    r = CliRunner().invoke(app, ["status", "--config", str(cfgp)])
    assert r.exit_code == 0, r.output
    assert "no epoch yet" in r.output and "cloud      unavailable: Invalid endpoint: nope" in r.output


@pytest.mark.parametrize("tripped", [False, True])
def test_a_corrupt_guard_never_shows_its_own_verdict_line(tmp_path, tripped):
    st = _with_epoch(make_station(tmp_path)[0])
    lines = service.status_lines(st.cfg, NOW, cloud=_reader({"state/guard.json": {"tripped": tripped}}))
    assert not any(line.startswith(("guard      not tripped", "guard      TRIPPED")) for line in lines)
    assert sum(line.startswith("guard      ") for line in lines) == 1


def test_unreadable_guard_and_offair_documents_state_the_consequence(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])
    lines = service.status_lines(st.cfg, NOW, cloud=_reader(
        {"state/guard.json": b"nope", "state/offair.json": b"nope"}))
    assert any(line.startswith("guard      unreadable:") and line.endswith("the clock treats it as a spend trip")
               for line in lines)
    assert any(line.startswith("offair     unreadable:")
               and line.endswith("the clock treats the station as off the air") for line in lines)


def test_a_raise_with_no_known_period_end_is_not_plainly_honoured(tmp_path):
    st = _with_epoch(make_station(tmp_path)[0])
    lines = service.status_lines(st.cfg, NOW, cloud=_reader(
        {"state/budget.json": {"budget_usd": 20, "expires": "2999-01-01T00:00:00Z"}}))
    assert any(line.endswith("(honoured (period end unknown))") for line in lines)


# ---- the 3-consecutive gate: the tick is one observation (spec Part 1) ----

def test_station_root_from_plan_survives_a_render_that_succeeds_without_scanning(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    rec = _Rec()
    alerts.configure(alerts.Dispatcher(tmp_path / "alerts.json", [rec], 6 * 3600.0))
    try:
        def root_gone(*a, **k):
            raise StationRootError("root gone")

        monkeypatch.setattr(pipeline, "plan_step", root_gone)
        monkeypatch.setattr(pipeline, "render_step", lambda *a, **k: None)
        runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
        runner.tick(NOW)
        assert alerts._dispatcher._streak["station-root"] == 1 and rec.sent == []
        runner.tick(NOW)
        assert rec.sent == []
        runner.tick(NOW)
        assert rec.sent == ["llama radio: station-root"]
    finally:
        alerts.configure(None)


def _observations(monkeypatch):
    seen = []
    monkeypatch.setattr(alerts, "end_observation", lambda o, steps: seen.append((o, set(steps))))
    return seen


def test_the_tick_ends_its_observation_on_every_path(tmp_path, monkeypatch):
    seen = _observations(monkeypatch)
    st, _ = make_station(tmp_path)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
    runner.tick(NOW)                                        # filling
    assert seen == [(alerts.TICK, {"lead", "plan", "render", "publish"})]
    for _ in range(5):
        if not runner.filling:
            break
        runner.tick(NOW)
    assert not runner.filling
    seen.clear()
    runner.tick(NOW)                                        # idle: the lead is above low water
    assert seen == [(alerts.TICK, {"lead", "publish"})]
    st.ws.publish_state_path.write_bytes(b'{"last": 1')     # damaged: the tick fails closed
    seen.clear()
    runner.tick(NOW)
    assert seen == [(alerts.TICK, {"lead"})]


def test_the_tick_ends_its_observation_when_a_step_escapes(tmp_path, monkeypatch):
    seen = _observations(monkeypatch)
    st, _ = make_station(tmp_path)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)

    def escape(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "plan_step", escape)
    with pytest.raises(KeyboardInterrupt):
        runner.tick(NOW)
    assert seen == [(alerts.TICK, {"lead"})]


def test_a_publish_locked_step_neither_advances_nor_resets(tmp_path, monkeypatch):
    seen = _observations(monkeypatch)
    st, _ = make_station(tmp_path)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)

    def locked(*args, **kwargs):
        raise PublishLocked("another publish holds the lock")

    monkeypatch.setattr(publish, "publish_batch", locked)
    runner.tick(NOW)
    assert seen == [(alerts.TICK, {"lead", "plan", "render"})]


def test_status_cloud_line_omits_a_pending_antenna_entry(tmp_path):
    lines = service.cloud_lines(_reader({"state/alerts.json": {
        "waf-api": {"active": False, "pending": True, "resolvable": True, "title": "WAF API failing",
                    "first_at": "2026-10-24T00:00:00.000Z", "last_sent_at": None, "cleared_at": None,
                    "streak": 2}}}), NOW)
    assert "alerts     cloud: none" in lines


def test_the_runner_wires_its_notify_into_the_station(tmp_path):
    st, _ = make_station(tmp_path)
    rec = lambda m: True  # noqa: E731
    service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, notify=rec)
    assert st.notify is rec
    st2, _ = make_station(tmp_path / "two")
    own = lambda m: True  # noqa: E731
    st2.notify = own
    service.Runner(st2, _publisher(st2, FakeBucket()), sleep=lambda s: None, notify=rec)
    assert st2.notify is own


def test_row_analysis_ignores_interstitial_rows_even_when_cached(tmp_path):
    import json
    from transmitter import analysis
    from transmitter.layout import PlanRow
    st, _ = make_station(tmp_path)
    sa = analysis.ShowAnalysis("kk", "ann", (), -18.0, -2.0, {})
    st.ws.cache_dir.mkdir(parents=True, exist_ok=True)
    (st.ws.cache_dir / "kk.json").write_text(json.dumps(sa.to_json()))
    assert analysis.load_cached(st.ws.cache_dir, "kk") is not None
    show_row = PlanRow(seq=0, slug="ann", dir="x", key="kk", start_frame=0, frames=441)
    assert service.row_analysis(st, show_row) is not None       # the cache is live for a show row
    row = PlanRow(seq=0, slug="ann", dir="interstitials", key="kk", start_frame=0, frames=441,
                  kind="interstitial", role="id")
    assert service.row_analysis(st, row) is None


def test_tick_skips_plan_and_render_while_the_plan_lock_is_held(tmp_path, caplog, monkeypatch):
    from transmitter.locks import plan_lock
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    runner.filling = True
    published = []
    monkeypatch.setattr(service, "publish_all", lambda *a, **k: published.append(1))
    before = st.ws.plan_path.read_bytes() if st.ws.plan_path.exists() else None
    with plan_lock(st.ws), caplog.at_level(logging.WARNING):
        runner.tick(NOW)
    after = st.ws.plan_path.read_bytes() if st.ws.plan_path.exists() else None
    assert after == before
    assert "ALERT" not in caplog.text
    assert "plan step skipped" in caplog.text and "render step skipped" in caplog.text
    assert published == [1]


def test_tick_appends_aired_rows_after_publishing(tmp_path):
    st, _ = make_station(tmp_path)
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
    runner.filling = True
    runner.tick(NOW)
    t = NOW + 3 * 3600 * 1_000_000
    runner.tick(t)
    from transmitter.history import load_aired
    from transmitter.state import load_publish_state
    last = load_publish_state(st.ws).last
    plan = read_plan(st.ws.plan_path)
    assert last is not None and plan
    aired = load_aired(st.ws)
    due = [r for r in plan if r.end_frame <= (last + 1) * grid.SEGMENT_FRAMES]
    assert due and [a.start_frame for a in aired] == [r.start_frame for r in due]
    runner.tick(t)
    assert len(load_aired(st.ws)) == len(due)           # idempotent


def test_history_failure_alerts_and_the_tick_completes(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path)
    rec = _Rec()
    alerts.configure(alerts.Dispatcher(tmp_path / "alerts.json", [rec], 6 * 3600.0))
    try:
        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(service.history, "append_aired", boom)
        runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
        runner.tick(NOW)                                 # end_observation does not raise
        assert "history" in alerts._dispatcher.active()
    finally:
        alerts.configure(None)
