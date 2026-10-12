import logging

import pytest

from tests_transmitter.helpers import NOW, TEMPLATE_PATH, FakeBucket, FakeEngine, make_station, write_seg
from transmitter import alerts, grid, pipeline, publish, service
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
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport())
    with caplog.at_level(logging.WARNING):
        service.publish_all(p, NOW)
    assert "ALERT put-budget: over" in caplog.text


def test_publish_all_alerts_put_budget_from_prune(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub())
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport(stopped="put-budget", error="over"))
    with caplog.at_level(logging.WARNING):
        service.publish_all(p, NOW)
    assert "ALERT put-budget: over" in caplog.text


def test_publish_all_alerts_a_prune_stopped_for_no_fallback(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub())
    monkeypatch.setattr(publish, "prune",
                        lambda p, t: publish.PruneReport(stopped="no-fallback", error=publish.NO_FALLBACK))
    with caplog.at_level(logging.WARNING):
        service.publish_all(p, NOW)
    assert "ALERT prune: stopped: no-fallback: no fallback rendered" in caplog.text


def test_publish_all_warns_on_high_water_without_alerting(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub())
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport(stopped="high-water"))
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "high-water" in caplog.text and "ALERT" not in caplog.text
    assert any(r.levelno == logging.WARNING and "high-water" in r.getMessage() for r in caplog.records)


def test_publish_all_warns_on_a_held_horizon_without_alerting(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    err = "horizon held: segment 5 is below the high-water mark 9"
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(error=err, held=True))
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport())
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "ALERT" not in caplog.text
    assert any(r.levelno == logging.WARNING and "horizon held" in r.getMessage() for r in caplog.records)


def test_publish_all_alerts_errors_and_logs_guard(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(error="PUT x failed"))
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport(error="DELETE y failed"))
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "ALERT publish: PUT x failed" in caplog.text and "ALERT prune: DELETE y failed" in caplog.text
    caplog.clear()
    monkeypatch.setattr(publish, "publish_batch", lambda p, t: _report_pub(stopped="guard"))
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport(stopped="guard"))
    with caplog.at_level(logging.INFO):
        service.publish_all(p, NOW)
    assert "ALERT" not in caplog.text and "guard" in caplog.text



def test_a_persistent_held_horizon_escalates_on_the_third_pass_and_resets(tmp_path, caplog, monkeypatch):
    p = _publisher(make_station(tmp_path)[0], FakeBucket())
    err = "horizon held: segment 5 is below the high-water mark 9"
    held = {"on": True}
    monkeypatch.setattr(publish, "publish_batch",
                        lambda p, t: _report_pub(error=err, held=True) if held["on"] else _report_pub())
    monkeypatch.setattr(publish, "prune", lambda p, t: publish.PruneReport())
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
        runner.tick(NOW)
        fired = "station-root" if step == "plan_step" else "render"
        assert rec.sent == [f"llama radio: {fired}"]
        fail["on"] = False
        runner.tick(NOW)
        assert f"llama radio: resolved: {fired}" in rec.sent
        assert runner.p is not None and alerts._dispatcher.active() == []
    finally:
        alerts.configure(None)


def test_the_runner_runs_the_dead_clock_check_every_tick_with_the_guard_cache(tmp_path):
    st, _ = make_station(tmp_path)
    calls = []

    class Monitor:
        def check(self, now_us, guard_cache):
            calls.append((now_us, guard_cache))

    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=Monitor())
    runner.tick(NOW)
    runner.tick(NOW + 60_000_000)
    assert [c[0] for c in calls] == [NOW, NOW + 60_000_000]
    assert calls[0][1]["blocked"] is False and calls[0][1]["offair"] is False   # written by publish's guard read


def test_open_monitor_needs_site_url(tmp_path):
    st, _ = make_station(tmp_path)
    assert service.open_monitor(st) is None
    st.cfg.antenna.site_url = "https://radio.example.org/"
    m = service.open_monitor(st)
    assert m.url == "https://radio.example.org/live.m3u8" and m.dead_clock_s == 120.0 and m.guard_stale_s == 2700.0
    assert m.forbidden_checks == 17                     # guard_check_minutes 15 + 2
