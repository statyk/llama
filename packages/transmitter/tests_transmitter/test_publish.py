import json

import pytest

from tests_transmitter.helpers import FALLBACK_VERSION, FakeBucket, make_publisher, write_seg
from transmitter import publish
from transmitter.errors import PublishLocked
from transmitter.layout import PlanRow
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_publish_state, save_publish_state


def _now(p):
    return p.epoch.start_us(90)


def _segs(p, rng):
    for n in rng:
        write_seg(p.ws, "etest", n)


def test_uploads_segments_then_site_then_horizon(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 110))
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == list(range(100, 110)) and report.horizon == (100, 109)
    puts = bucket.puts()
    assert puts[:10] == [segment_key("etest", n) for n in range(100, 110)]
    assert puts[10:] == ["notes/band-1.json", "show/band-1.html", "timeline.json", "state/horizon.json"]
    h = bucket.json("state/horizon.json")
    assert h == {"epoch_id": "etest", "epoch": p.epoch.iso, "d": 10.24, "first": 100, "last": 109,
                 "published_at": h["published_at"], "container": "adts",
                 "fallback_version": FALLBACK_VERSION}
    assert not any(p.ws.seg_dir("etest").iterdir())
    assert load_publish_state(p.ws) == PublishState(epoch_id="etest", first=100, last=109, runs=[[100, 109]],
                                                    notes=load_publish_state(p.ws).notes, high_water=109)


def test_cache_headers_and_types(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 102))
    publish.publish_batch(p, _now(p))
    o = bucket.objects
    assert o[segment_key("etest", 100)]["CacheControl"] == "public, max-age=31536000, immutable"
    assert o[segment_key("etest", 100)]["ContentType"] == "audio/aac"
    assert o["timeline.json"]["CacheControl"] == "public, max-age=30"
    assert o["timeline.json"]["ContentType"] == "application/json"
    assert o["notes/band-1.json"]["CacheControl"] == "public, max-age=3600"
    assert o["notes/band-1.json"]["ContentType"] == "application/json"
    assert o["show/band-1.html"]["CacheControl"] == "public, max-age=3600"
    assert o["show/band-1.html"]["ContentType"] == "text/html; charset=utf-8"
    assert o["state/horizon.json"]["CacheControl"] == "no-store"
    assert o["state/horizon.json"]["ContentType"] == "application/json"


def test_failed_segment_blocks_the_horizon(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 106))
    bucket.fail_puts[segment_key("etest", 102)] = 99
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == [100, 101] and report.horizon == (100, 101)
    assert "seg/etest/102.aac" in report.error
    assert bucket.json("state/horizon.json")["last"] == 101
    left = sorted(int(f.stem) for f in p.ws.seg_dir("etest").iterdir())
    assert left == [102, 103, 104, 105]
    assert segment_key("etest", 103) not in bucket.objects          # never past the failure
    bucket.fail_puts.clear()
    assert publish.publish_batch(p, _now(p)).horizon == (100, 105)


def test_retry_with_backoff_and_every_attempt_counts_against_the_budget(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    key = segment_key("etest", 100)
    bucket.fail_puts[key] = 2
    p.uploader.put(key, b"x", publish.AAC_TYPE, publish.IMMUTABLE)
    assert p.sleeps == [1.0, 2.0]
    assert bucket.puts() == [key] * 3
    assert json.loads(p.ws.puts_path.read_text()) == {"day": "2027-01-15", "count": 3}


def test_horizon_failure_keeps_state_and_files_for_the_next_batch(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 103))
    bucket.fail_puts["state/horizon.json"] = 99
    report = publish.publish_batch(p, _now(p))
    assert report.horizon is None and "horizon" in report.error
    assert load_publish_state(p.ws).last is None
    assert len(list(p.ws.seg_dir("etest").iterdir())) == 3
    bucket.fail_puts.clear()
    assert publish.publish_batch(p, _now(p)).horizon == (100, 102)


class _Crash(BaseException):
    """The process dies (kill -9, power loss): nothing after this runs."""


class _CrashAfterHorizon(FakeBucket):
    def put_object(self, **kw):
        resp = super().put_object(**kw)
        if kw["Key"] == "state/horizon.json" and self.crash:
            self.crash = False
            raise _Crash()                           # R2 stored it; the 200 never reached us
        return resp


def test_the_high_water_mark_is_saved_before_the_horizon_put(tmp_path):
    bucket = _CrashAfterHorizon()
    bucket.crash = True
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 110))
    with pytest.raises(_Crash):
        publish.publish_batch(p, _now(p))
    assert bucket.json("state/horizon.json")["last"] == 109      # R2 lists 100..109
    state = load_publish_state(p.ws)
    assert state.last is None and state.high_water == 109        # ...and local state knows it may
    assert state.epoch_id == "etest"
    assert len(list(p.ws.seg_dir("etest").iterdir())) == 10     # files kept: nothing confirmed locally
    report = publish.publish_batch(p, _now(p))                   # identical bytes re-PUT, once
    assert report.horizon == (100, 109)
    assert load_publish_state(p.ws).last == 109


def test_the_horizon_never_moves_below_the_high_water_mark(tmp_path):
    bucket = _CrashAfterHorizon()
    bucket.crash = True
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 110))
    with pytest.raises(_Crash):
        publish.publish_batch(p, _now(p))
    bucket.fail_puts[segment_key("etest", 103)] = 99             # the re-PUT stops part-way
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == [] and report.horizon is None
    assert "high-water" in report.error
    assert bucket.json("state/horizon.json")["last"] == 109      # not rewritten down to 102
    assert bucket.puts().count("state/horizon.json") == 1
    bucket.fail_puts.clear()
    assert publish.publish_batch(p, _now(p)).horizon == (100, 109)


def test_a_batch_stopping_below_the_high_water_mark_reports_the_horizon_held(tmp_path):
    bucket = _CrashAfterHorizon()
    bucket.crash = True
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 110))
    with pytest.raises(_Crash):
        publish.publish_batch(p, _now(p))
    before = load_publish_state(p.ws)
    (p.ws.seg_dir("etest") / "105.aac").unlink()                 # the batch now stops at 104 < 109
    report = publish.publish_batch(p, _now(p))
    assert report.held is True and "horizon held" in report.error
    assert report.horizon is None and report.uploaded == []
    assert bucket.puts().count("state/horizon.json") == 1        # only the crashed batch's PUT
    after = load_publish_state(p.ws)
    assert after.last == before.last and after.high_water == 109   # local state not advanced


def test_a_lowered_batch_size_after_a_crash_still_reaches_the_high_water_mark(tmp_path):
    bucket = _CrashAfterHorizon()
    bucket.crash = True
    p = make_publisher(tmp_path, bucket, batch=10)
    _segs(p, range(100, 110))
    with pytest.raises(_Crash):
        publish.publish_batch(p, _now(p))
    p.cfg.publish.batch_segments = 5                             # the operator lowers it meanwhile
    report = publish.publish_batch(p, _now(p))                   # one batch re-sends up to the mark
    assert report.uploaded == list(range(100, 110)) and report.horizon == (100, 109)
    assert load_publish_state(p.ws).last == 109
    _segs(p, range(110, 120))
    assert publish.publish_batch(p, _now(p)).uploaded == list(range(110, 115))   # normal size again


def test_publish_state_without_a_high_water_mark_still_loads(tmp_path):
    p = make_publisher(tmp_path, FakeBucket())
    p.ws.publish_state_path.write_text(json.dumps(
        {"epoch_id": "etest", "first": 1, "last": 5, "runs": [[1, 5]], "notes": {}}))
    assert load_publish_state(p.ws) == PublishState(epoch_id="etest", first=1, last=5, runs=[[1, 5]])
    assert load_publish_state(p.ws).high_water is None


def test_put_budget_stops_publishing(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, budget=5)
    _segs(p, range(100, 110))
    report = publish.publish_batch(p, _now(p))
    assert report.stopped == "put-budget"
    assert len(bucket.puts()) == 5 and "state/horizon.json" not in bucket.objects
    assert publish.publish_batch(p, _now(p)).stopped == "put-budget"
    assert len(bucket.puts()) == 5


def test_the_attempted_range_is_recorded_before_the_first_put(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, budget=5)
    _segs(p, range(100, 110))
    assert publish.publish_batch(p, _now(p)).stopped == "put-budget"     # 100..104 went up
    state = load_publish_state(p.ws)
    assert state.last is None and state.runs == [[100, 109]]           # prune still reaches them
    p.uploader.budget.limit = 17_500
    assert publish.publish_batch(p, _now(p)).horizon == (100, 109)
    assert load_publish_state(p.ws).runs == [[100, 109]]                # merged, not duplicated


def test_a_site_error_of_any_type_still_advances_the_horizon(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)

    def broken(row):
        raise KeyError("artist")

    p.analysis_for = broken
    _segs(p, range(100, 102))
    report = publish.publish_batch(p, _now(p))
    assert report.horizon == (100, 101) and report.error.startswith("site: ")
    assert bucket.json("state/horizon.json")["last"] == 101
    assert "timeline.json" not in bucket.objects


def test_a_failed_notes_put_never_lets_a_timeline_reference_the_show(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    bucket.fail_puts["notes/band-1.json"] = 99
    _segs(p, range(100, 102))
    report = publish.publish_batch(p, _now(p))
    assert report.horizon == (100, 101) and report.error.startswith("site: ")
    assert "timeline.json" not in bucket.objects and "show/band-1.html" not in bucket.objects
    bucket.fail_puts.clear()
    _segs(p, range(102, 103))
    publish.publish_batch(p, _now(p))
    puts = bucket.puts()
    assert puts.index("show/band-1.html") < puts.index("timeline.json")
    assert [s["slug"] for s in bucket.json("timeline.json")["shows"]] == ["band-1"]


def test_a_show_entering_the_timeline_gets_its_page_before_that_timeline(tmp_path):
    bucket = FakeBucket()
    rows = [PlanRow(seq=0, slug="band-1", dir="band-1", key="k1", start_frame=100 * 441,
                    frames=441 * 3, run_start=True),
            PlanRow(seq=1, slug="band-2", dir="band-2", key="k2", start_frame=103 * 441,
                    frames=441 * 3, run_start=False)]
    p = make_publisher(tmp_path, bucket, rows=rows)
    _segs(p, range(100, 103))
    publish.publish_batch(p, _now(p))
    assert [s["slug"] for s in bucket.json("timeline.json")["shows"]] == ["band-1"]
    assert "notes/band-2.json" not in bucket.objects
    mark = len(bucket.log)
    _segs(p, range(103, 106))
    publish.publish_batch(p, _now(p))
    puts = [k for op, k in bucket.log[mark:] if op == "put"]
    assert [s["slug"] for s in bucket.json("timeline.json")["shows"]] == ["band-1", "band-2"]
    timeline_at = puts.index("timeline.json")
    assert puts.index("notes/band-2.json") < timeline_at and puts.index("show/band-2.html") < timeline_at
    assert timeline_at < puts.index("state/horizon.json")


def test_an_unreadable_package_never_replaces_a_published_page(tmp_path):
    from tests_transmitter.helpers import build_package, make_root

    root = make_root(tmp_path)
    pkg = build_package(root, "band-1")
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, station_root=root)
    _segs(p, range(100, 101))
    publish.publish_batch(p, _now(p))
    assert bucket.json("notes/band-1.json")["briefing"].startswith("A fine show.")
    (pkg / "manifest.json").unlink()                       # mid-redeliver, or the share is down
    _segs(p, range(101, 102))
    assert publish.publish_batch(p, _now(p)).horizon == (100, 101)
    assert bucket.puts().count("notes/band-1.json") == 1
    assert bucket.json("notes/band-1.json")["briefing"].startswith("A fine show.")


def test_tripped_guard_stops_publishing_and_is_read_at_most_every_15_minutes(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": json.dumps({"tripped": True, "reason": "spend"}).encode()}
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 102))
    assert publish.publish_batch(p, _now(p)).stopped == "guard"
    assert publish.publish_batch(p, _now(p) + 60_000_000).stopped == "guard"
    assert bucket.log == [("get", "state/guard.json")]
    later = _now(p) + 16 * 60 * 1_000_000
    bucket.objects["state/guard.json"]["Body"] = b'{"tripped": false}'
    assert publish.publish_batch(p, later).uploaded == [100, 101]


def test_a_clock_stepped_backwards_rereads_the_guard(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": false}'}
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    assert publish.publish_batch(p, _now(p)).uploaded == [100]
    bucket.objects["state/guard.json"]["Body"] = b'{"tripped": true}'
    _segs(p, range(101, 102))
    earlier = _now(p) - 60 * 60 * 1_000_000                       # NTP stepped the clock back an hour
    assert publish.publish_batch(p, earlier).stopped == "guard"
    assert bucket.log.count(("get", "state/guard.json")) == 2


def test_absent_guard_is_not_tripped(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    assert publish.publish_batch(p, _now(p)).uploaded == [100]


def test_unreadable_guard_fails_closed(tmp_path):
    bucket = FakeBucket()
    bucket.fail_gets.add("state/guard.json")
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    assert publish.publish_batch(p, _now(p)).stopped == "guard"
    assert bucket.puts() == []


def test_lock_is_exclusive(tmp_path):
    p = make_publisher(tmp_path, FakeBucket())
    with publish.publish_lock(p.ws):
        with pytest.raises(PublishLocked):
            publish.publish_batch(p, _now(p))


def test_check_epoch_refuses_another_epochs_state(tmp_path):
    from transmitter.errors import PublishError

    p = make_publisher(tmp_path, FakeBucket())
    publish.check_epoch(PublishState(), p.epoch)
    publish.check_epoch(PublishState(epoch_id="etest"), p.epoch)
    with pytest.raises(PublishError, match="eother"):
        publish.check_epoch(PublishState(epoch_id="eother"), p.epoch)


def test_a_new_run_starts_the_horizon_at_the_run_start(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, run_start_n=500)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=40, last=60, runs=[[40, 60]]))
    _segs(p, range(500, 503))
    report = publish.publish_batch(p, p.epoch.start_us(490))
    assert report.horizon == (500, 502)
    assert load_publish_state(p.ws).runs == [[40, 60], [500, 502]]


def test_notes_are_reuploaded_only_when_they_change(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    publish.publish_batch(p, _now(p))
    _segs(p, range(101, 102))
    publish.publish_batch(p, _now(p))
    assert bucket.puts().count("notes/band-1.json") == 1
    assert bucket.puts().count("timeline.json") == 2


def test_nothing_rendered_is_a_quiet_no_op(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == [] and bucket.puts() == []


def test_no_fallback_rendered_publishes_nothing_and_never_re_puts(tmp_path):
    # Without a fallback version the horizon would carry `fallback_version:
    # null`, which makes both off-air levers inert: refuse before ANY PUT.
    # Segments are only dropped locally after a horizon PUT, so uploading them
    # now would re-PUT the same batch on every tick until a fallback exists.
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, fallback_version=None)
    _segs(p, range(100, 105))
    for _ in range(2):
        report = publish.publish_batch(p, _now(p))
        assert report.uploaded == [] and report.horizon is None and report.stopped is None
        assert "transmitter fallback render" in report.error
    assert bucket.puts() == []
    assert not p.ws.puts_path.exists()                          # no PUT budget spent
    assert load_publish_state(p.ws) == PublishState()
    assert len(list(p.ws.seg_dir("etest").iterdir())) == 5      # kept for the first real batch
    from transmitter.state import save_fallback_version
    save_fallback_version(p.ws, "fbafter00000")                 # the operator runs fallback render
    report = publish.publish_batch(p, _now(p))
    assert report.horizon == (100, 104) and report.error is None
    assert bucket.json("state/horizon.json")["fallback_version"] == "fbafter00000"
    assert [k for k in bucket.puts() if k.startswith("seg/")] == [segment_key("etest", n) for n in range(100, 105)]
