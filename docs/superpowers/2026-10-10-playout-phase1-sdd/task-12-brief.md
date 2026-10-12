### Task 12: Prune

**Model hint:** opus

**Files:**
- Modify: `packages/transmitter/src/transmitter/publish.py` (add `PruneReport`, `prune`)
- Create: `packages/transmitter/tests_transmitter/test_prune.py`

**Interfaces:**
- Consumes: Task 11's `Publisher`, `Uploader.delete`, `put_json`, `horizon_doc`, `guard_blocks_publishing`, `publish_lock`, `check_epoch`, `HORIZON_KEY`, `STATE_CACHE`; `grid.first_segment_at_or_after`.
- Produces: `PruneReport(deleted: int, first: int | None, stopped: str | None, error: str | None)`; `prune(p, now_us) -> PruneReport` — once `E + N·d < now − prune_margin`, and only when at least `prune_min_segments` (default 60) segments are prunable (so the horizon is rewritten at most once per ~10 min, not every tick): rewrites `state/horizon.json` with the advanced `first` **before** deleting, never past `horizon.last` (an outage must not move `last`), then deletes by computed key range (per-key DeleteObject, the documented free operation; never List or DeleteObjects), across every recorded run.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_prune.py`:

```python
from tests_transmitter.helpers import FakeBucket, make_publisher
from transmitter import grid, publish
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_publish_state, save_publish_state

MIN_US = 60 * 1_000_000


def _seed(p, bucket, runs, first, last):
    for lo, hi in runs:
        for n in range(lo, hi + 1):
            bucket.objects[segment_key("etest", n)] = {"Body": b"x", "ContentType": "", "CacheControl": ""}
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=first, last=last, runs=[list(r) for r in runs]))


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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_prune.py -q`
Expected: FAIL — `AttributeError: module 'transmitter.publish' has no attribute 'prune'`.

- [ ] **Step 3: Implement `prune`**

Append to `publish.py`:

```python
@dataclass
class PruneReport:
    deleted: int = 0
    first: int | None = None
    stopped: str | None = None
    error: str | None = None


def prune(p: Publisher, now_us: int) -> PruneReport:
    """Delete segments that started more than `prune_margin` ago (so lagging
    players don't 404): advance horizon.first first, then delete by computed key
    range. Never past horizon.last -- an outage must not move `last`, which the
    clock's off-air rule is measured from."""
    report = PruneReport()
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            report.stopped = "guard"
            return report
        state = load_publish_state(p.ws)
        check_epoch(state, p.epoch)
        report.first = state.first
        if state.last is None:
            return report
        cutoff_us = now_us - int(p.cfg.publish.prune_margin_minutes * 60 * 1_000_000)
        n_max = min(grid.first_segment_at_or_after(p.epoch.epoch_us, cutoff_us) - 1, state.last)
        prunable = sum(max(0, min(hi, n_max) - lo + 1) for lo, hi in state.runs)
        if prunable < p.cfg.publish.prune_min_segments:
            return report                    # batch it: each prune costs a horizon PUT
        if state.first is not None and n_max >= state.first:
            try:
                put_json(p.uploader, HORIZON_KEY,
                         horizon_doc(p.epoch, n_max + 1, state.last, now_us, load_fallback_version(p.ws)),
                         STATE_CACHE)
            except (PublishError, PutBudgetExceeded) as exc:
                report.error = f"horizon: {exc}"
                return report
            state.first = n_max + 1
            save_publish_state(p.ws, state)
            report.first = state.first
        remaining: list[list[int]] = []
        failed = False
        for lo, hi in state.runs:
            if failed:
                remaining.append([lo, hi])
                continue
            n = lo
            try:
                while n <= min(hi, n_max):
                    p.uploader.delete(segment_key(p.epoch.epoch_id, n))
                    n += 1
                    report.deleted += 1
            except PublishError as exc:
                report.error, failed = str(exc), True
            if n <= hi:
                remaining.append([n, hi])
        state.runs = remaining
        save_publish_state(p.ws, state)
        return report
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_prune.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): prune by computed key range after advancing horizon.first"
```

---

