import pytest

from tests_transmitter.helpers import FakeBucket, make_publisher
from transmitter import publish
from transmitter.errors import PublishLocked
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_publish_state, save_publish_state

MIN_US = 60 * 1_000_000


def _seed(p, bucket, runs, first, last, high_water=None):
    for lo, hi in runs:
        for n in range(lo, hi + 1):
            bucket.objects[segment_key("etest", n)] = {"Body": b"x", "ContentType": "", "CacheControl": ""}
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=first, last=last,
                                          runs=[list(r) for r in runs], high_water=high_water))


def test_prune_advances_first_before_deleting_and_keeps_the_margin(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    now = p.epoch.start_us(300) + 10 * MIN_US           # cutoff = start of segment 300
    report = publish.prune(p, now)
    assert report.first == 300 and report.deleted == 200
    ops = [op for op in bucket.log if op[0] in ("put", "delete")]
    assert ops[0] == ("put", "state/horizon.json")
    assert all(op == "delete" for op, _ in ops[1:])
    assert bucket.json("state/horizon.json")["first"] == 300
    assert bucket.json("state/horizon.json")["last"] == 400
    assert segment_key("etest", 299) not in bucket.objects and segment_key("etest", 300) in bucket.objects
    assert load_publish_state(p.ws).runs == [[300, 400]]


def test_prune_never_moves_past_last(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 150)], 100, 150)
    report = publish.prune(p, p.epoch.start_us(10_000))  # long outage
    assert report.first == 151
    h = bucket.json("state/horizon.json")
    assert (h["first"], h["last"]) == (151, 150)        # empty horizon; last unchanged
    assert load_publish_state(p.ws).runs == []


def test_prune_deletes_an_old_run_left_by_a_recovery(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(40, 60), (500, 600)], 500, 600)
    report = publish.prune(p, p.epoch.start_us(510) + 10 * MIN_US)
    assert report.deleted == 21 + 10
    assert load_publish_state(p.ws).runs == [[510, 600]]


def test_prune_is_idempotent(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    now = p.epoch.start_us(300) + 10 * MIN_US
    publish.prune(p, now)
    bucket.log.clear()
    assert publish.prune(p, now).deleted == 0
    assert [op for op, _ in bucket.log if op != "get"] == []


def test_prune_resumes_after_a_failed_delete(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 200)], 100, 200)
    real = bucket.delete_object
    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 6:
            raise RuntimeError("network")
        return real(**kw)

    bucket.delete_object = flaky
    report = publish.prune(p, p.epoch.start_us(150) + 10 * MIN_US)
    assert report.error and report.deleted == 5
    assert load_publish_state(p.ws).runs == [[105, 200]]
    bucket.delete_object = real
    assert publish.prune(p, p.epoch.start_us(150) + 10 * MIN_US).deleted == 45


def test_prune_waits_until_enough_segments_are_prunable(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, prune_min=60)
    _seed(p, bucket, [(100, 400)], 100, 400)
    report = publish.prune(p, p.epoch.start_us(159) + 10 * MIN_US)       # 59 prunable: 100..158
    assert report.deleted == 0 and report.first == 100
    assert [op for op, _ in bucket.log if op in ("put", "delete")] == []    # no horizon write
    assert publish.prune(p, p.epoch.start_us(160) + 10 * MIN_US).deleted == 60


def test_prune_stops_while_the_guard_is_tripped(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": true}', "ContentType": "", "CacheControl": ""}
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    assert publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US).stopped == "guard"
    assert not [op for op, _ in bucket.log if op in ("put", "delete")]


def test_prune_stops_when_the_guard_cannot_be_read(tmp_path):
    bucket = FakeBucket()
    bucket.fail_gets.add("state/guard.json")
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    assert publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US).stopped == "guard"
    assert not [op for op in bucket.log if op[0] in ("put", "delete")]


def test_prune_takes_the_publish_lock_without_waiting(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    with publish.publish_lock(p.ws):
        with pytest.raises(PublishLocked):
            publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    assert bucket.log == []
    assert load_publish_state(p.ws).runs == [[100, 400]]


def test_a_failed_horizon_put_deletes_nothing(tmp_path):
    bucket = FakeBucket()
    bucket.fail_puts["state/horizon.json"] = 99
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    report = publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    assert report.error and report.error.startswith("horizon:") and report.deleted == 0
    assert not [op for op in bucket.log if op[0] == "delete"]
    state = load_publish_state(p.ws)
    assert (state.first, state.runs) == (100, [[100, 400]])


def test_a_spent_put_budget_stops_prune_before_any_delete(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, budget=1)
    _seed(p, bucket, [(100, 400)], 100, 400)
    p.uploader.budget.take()                            # the day's one PUT is gone
    report = publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    assert report.stopped == "put-budget" and report.deleted == 0
    assert not [op for op in bucket.log if op[0] in ("put", "delete")]
    assert load_publish_state(p.ws).first == 100


def test_prune_never_rewrites_the_horizon_without_a_recorded_fallback(tmp_path):
    # fallback.json lost after publishing (deleted, or ~/.transmitter restored
    # without it): a prune rewrite would PUT `fallback_version: null`. Stop
    # before the horizon PUT, and before any delete (deletes must follow the
    # horizon shrinking past them).
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    p.ws.fallback_path.unlink()
    before = load_publish_state(p.ws)
    report = publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    assert report.stopped == "no-fallback" and report.deleted == 0
    assert "transmitter fallback render" in report.error
    assert not [op for op in bucket.log if op[0] in ("put", "delete")]
    assert not p.ws.puts_path.exists()                          # no PUT budget spent
    assert load_publish_state(p.ws) == before
    from transmitter.state import save_fallback_version
    save_fallback_version(p.ws, "fbafter00000")                 # the operator re-runs fallback render
    report = publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    assert report.stopped is None and report.first == 300 and report.deleted == 200
    assert bucket.json("state/horizon.json")["fallback_version"] == "fbafter00000"


def test_prune_waits_while_r2_may_list_past_last(tmp_path):
    # A crash between a horizon PUT and the save advancing `last` leaves
    # high_water > last: R2 may list up to high_water, so a horizon rewrite
    # bounded by `last` would move R2's `last` backwards. Prune waits for
    # publish to reconcile.
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 460)], 100, 400, high_water=460)
    report = publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    assert report.stopped == "high-water" and report.deleted == 0
    assert not [op for op in bucket.log if op[0] in ("put", "delete")]
    assert load_publish_state(p.ws).high_water == 460


def test_prune_preserves_the_high_water_mark(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400, high_water=400)
    publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US)
    state = load_publish_state(p.ws)
    assert (state.first, state.last, state.high_water) == (300, 400, 400)


def test_prune_respects_a_configured_margin(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    p.cfg.publish.prune_margin_minutes = 30.0
    _seed(p, bucket, [(100, 400)], 100, 400)
    report = publish.prune(p, p.epoch.start_us(300) + 30 * MIN_US)
    assert report.first == 300 and report.deleted == 200
