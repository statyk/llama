### Task 11: Publisher core — ordering invariant, retry, PUT budget, guard read, flock

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/r2.py`, `packages/transmitter/src/transmitter/publish.py`
- Create: `packages/transmitter/tests_transmitter/test_r2.py`, `test_publish.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (`FakeBucket`)

**Interfaces:**
- Consumes: `config.PublishConfig/TransmitterConfig`, `workspace.*`, `state.*`, `planner.read_plan/publish_next`, `segment.segment_key`, `site.*`, `analysis.ShowAnalysis`, `layout.PlanRow`, `grid`, `errors.ConfigError/PublishError/PublishLocked/PutBudgetExceeded`.
- Produces:
  - `transmitter.r2.make_client(cfg: PublishConfig)` — boto3 S3 client for R2 (keys from `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`).
  - `transmitter.publish`: constants `AAC_TYPE, JSON_TYPE, HTML_TYPE, IMMUTABLE, TIMELINE_CACHE, NOTES_CACHE, STATE_CACHE, HORIZON_KEY, GUARD_KEY, TIMELINE_KEY, CONTAINER="adts"`; `PutBudget(path, limit, today=<utc date fn>)` with `.take()`; `Uploader(client, bucket, budget, *, sleep=time.sleep, attempts=4, base_delay_s=1.0)` with `.put(key, body, content_type, cache_control)`, `.get_json(key) -> dict | None`, `.delete(key)`; `guard_blocks_publishing(uploader, ws, now_s, interval_s) -> bool`; `publish_lock(ws)` context manager (non-blocking: raises `PublishLocked` while another holder has it); `Publisher(ws, cfg, epoch, uploader, template, analysis_for, log=print)` where `analysis_for(row: PlanRow) -> ShowAnalysis | None` is injected (Task 14 wires it to the engine's read-or-compute `analyze`, so the timeline never depends on the analysis cache surviving); `horizon_doc(epoch, first, last, now_us, fallback_version) -> dict`; `put_json(uploader, key, doc, cache_control)`; `PublishReport(uploaded, horizon, stopped, error)`; `publish_batch(p, now_us) -> PublishReport` (records the attempted segment range in local `runs` before the first PUT, so prune reaches segments a stopped batch uploaded; a site-step exception of any type is recorded in `report.error` while segments and horizon still advance; an unreadable package never replaces an already-published notes/page).
  - helpers: `FakeBucket` (records `log` of `("put"|"get"|"delete", key)`, `objects`, `fail_puts: dict[key, int]`, `fail_gets: set[key]`; any other attribute access fails the test — no List calls); `make_publisher(tmp_path, bucket, *, batch=360, budget=17_500, sleep=None, rows=None, run_start_n=100, prune_min=1, station_root=None) -> Publisher` (its `analysis_for` serves in-memory analyses; nothing is cached on disk); `write_seg(ws, epoch_id, n)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
import io

from botocore.exceptions import ClientError


class FakeBucket:
    """An in-memory R2 bucket speaking the boto3 S3 calls transmitter uses.
    Any other call (list_objects*, delete_objects, …) fails the test."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.log: list[tuple[str, str]] = []
        self.fail_puts: dict[str, int] = {}
        self.fail_gets: set[str] = set()

    def put_object(self, *, Bucket, Key, Body, ContentType, CacheControl):
        self.log.append(("put", Key))
        if self.fail_puts.get(Key, 0) > 0:
            self.fail_puts[Key] -= 1
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "PutObject")
        self.objects[Key] = {"Body": bytes(Body), "ContentType": ContentType, "CacheControl": CacheControl}
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, *, Bucket, Key):
        self.log.append(("get", Key))
        if Key in self.fail_gets:
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "GetObject")
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["Body"])}

    def delete_object(self, *, Bucket, Key):
        self.log.append(("delete", Key))
        self.objects.pop(Key, None)
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    def __getattr__(self, name):
        raise AssertionError(f"unexpected S3 call: {name}")

    def json(self, key):
        return json.loads(self.objects[key]["Body"])

    def puts(self):
        return [k for op, k in self.log if op == "put"]


def write_seg(ws, epoch_id: str, n: int) -> None:
    from transmitter import segment as _segment

    path = ws.seg_dir(epoch_id) / f"{n}.aac"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_segment.assemble(n, [fake_frame("seg", n)] * 441))


TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "antenna" / "templates" / "show.html"


def make_publisher(tmp_path: Path, bucket: "FakeBucket", *, batch: int = 360, budget: int = 17_500,
                   sleep=None, rows=None, run_start_n: int = 100, prune_min: int = 1,
                   station_root: Path | None = None):
    """A Publisher over a workspace holding one planned show (key "k1"),
    starting a run at segment `run_start_n`. Its analyses are served from
    memory by `analysis_for` (none is cached on disk); `p.analyses` holds them."""
    from transmitter import planner, publish
    from transmitter.layout import PlanRow

    cfg = TransmitterConfig(root=tmp_path / "tx", station={"root": station_root},
                            publish={"bucket": "b", "batch_segments": batch, "daily_put_budget": budget,
                                     "prune_min_segments": prune_min})
    ws = Workspace(cfg.root)
    epoch = Epoch("etest", E)
    rows = rows or [PlanRow(seq=0, slug="band-1", dir="band-1", key="k1",
                            start_frame=run_start_n * 441, frames=441 * 50, run_start=True)]
    planner.write_plan(ws.plan_path, rows)
    files = (FileAnalysis("audio/01.mp3", "track", "Song 1", 441 * 1024 * 40),)
    meta = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
            "profile": "indie", "url": "https://archive.org/details/band1", "lineage": "AUD"}
    analyses = {r.key: ShowAnalysis(r.key, "band-1", files, -18.0, -2.0, meta) for r in rows}
    sleeps = []
    uploader = publish.Uploader(bucket, "b", publish.PutBudget(ws.puts_path, budget, today=lambda: "2027-01-15"),
                                sleep=sleep or sleeps.append)
    p = publish.Publisher(ws=ws, cfg=cfg, epoch=epoch, uploader=uploader,
                          template=TEMPLATE_PATH.read_text(),
                          analysis_for=lambda row: analyses.get(row.key), log=lambda m: None)
    p.sleeps = sleeps
    p.analyses = analyses
    return p
```

`tests_transmitter/test_r2.py`:

```python
import pytest

from transmitter import r2
from transmitter.config import PublishConfig
from transmitter.errors import ConfigError


def test_client_needs_keys(monkeypatch):
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(ConfigError, match="R2_ACCESS_KEY_ID"):
        r2.make_client(PublishConfig(account_id="acct", bucket="b"))


def test_client_endpoint_from_account(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    client = r2.make_client(PublishConfig(account_id="acct", bucket="b"))
    assert client.meta.endpoint_url == "https://acct.r2.cloudflarestorage.com"
    # one HTTP request per Uploader attempt, so every attempt is counted against the PUT
    # budget (botocore reads a bare `max_attempts: 1` as one *retry*: 2 requests)
    assert client.meta.config.retries["total_max_attempts"] == 1
    override = r2.make_client(PublishConfig(endpoint_url="http://localhost:9000", bucket="b"))
    assert override.meta.endpoint_url == "http://localhost:9000"


def test_client_needs_an_endpoint(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    with pytest.raises(ConfigError, match="account_id"):
        r2.make_client(PublishConfig(bucket="b"))
```

`tests_transmitter/test_publish.py`:

```python
import json

import pytest

from tests_transmitter.helpers import FakeBucket, make_publisher, write_seg
from transmitter import publish
from transmitter.errors import PublishLocked
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_publish_state, save_publish_state

NOW_US = None  # set per test from the publisher's epoch


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
                 "published_at": h["published_at"], "container": "adts", "fallback_version": None}
    assert not any(p.ws.seg_dir("etest").iterdir())
    assert load_publish_state(p.ws) == PublishState(epoch_id="etest", first=100, last=109, runs=[[100, 109]],
                                                    notes=load_publish_state(p.ws).notes)


def test_cache_headers_and_types(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 102))
    publish.publish_batch(p, _now(p))
    o = bucket.objects
    assert o[segment_key("etest", 100)]["CacheControl"] == "public, max-age=31536000, immutable"
    assert o[segment_key("etest", 100)]["ContentType"] == "audio/aac"
    assert o["timeline.json"]["CacheControl"] == "public, max-age=30"
    assert o["notes/band-1.json"]["CacheControl"] == "public, max-age=3600"
    assert o["show/band-1.html"]["ContentType"] == "text/html; charset=utf-8"
    assert o["state/horizon.json"]["CacheControl"] == "no-store"


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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_r2.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.r2'` / `transmitter.publish`.

- [ ] **Step 3: Implement `r2.py`**

```python
"""boto3 client for R2's S3 API (spec "Publisher (phase 1)"). Keys come from
the environment (the service's env file); the account id and bucket from
config. botocore's own retries are off -- the Uploader owns retry/backoff so
every attempt is counted against the daily PUT budget -- and checksums are
only sent when an operation requires them."""

import os

from transmitter.config import PublishConfig
from transmitter.errors import ConfigError


def make_client(cfg: PublishConfig):
    import boto3
    from botocore.config import Config

    key = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not key or not secret:
        raise ConfigError("set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY (the service's env file)")
    endpoint = cfg.endpoint_url or (
        f"https://{cfg.account_id}.r2.cloudflarestorage.com" if cfg.account_id else None)
    if endpoint is None:
        raise ConfigError("set [publish] account_id (or endpoint_url) in transmitter's config.toml")
    return boto3.client(
        "s3", endpoint_url=endpoint, region_name="auto",
        aws_access_key_id=key, aws_secret_access_key=secret,
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required",
                      connect_timeout=10, read_timeout=60),
    )
```

- [ ] **Step 4: Implement `publish.py`**

```python
"""Publisher (spec "Publisher (phase 1)", "R2 object contract").

Ordering invariant: segments go up in ascending N; state/horizon.json is
rewritten only after every segment it covers returned 200; a show's notes and
page go up before the timeline.json that references them. Presence is the
PUT's 200 -- there are no List calls. Every PUT attempt counts against a local
daily budget; publishing stops while state/guard.json says tripped (absent =
not tripped; unreadable = treated as tripped, i.e. fail closed). Publish and
prune hold a local flock so a manual run cannot race the service; the lock
does not wait, so a manual `publish` while `run` holds it fails with
PublishLocked.
"""

import fcntl
import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

from transmitter import grid, site
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import PublishError, PublishLocked, PutBudgetExceeded
from transmitter.layout import PlanRow
from transmitter.planner import publish_next, read_plan
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_fallback_version, load_publish_state, save_publish_state
from transmitter.workspace import Epoch, Workspace, read_json, write_json

AAC_TYPE = "audio/aac"
JSON_TYPE = "application/json"
HTML_TYPE = "text/html; charset=utf-8"
IMMUTABLE = "public, max-age=31536000, immutable"
TIMELINE_CACHE = "public, max-age=30"
NOTES_CACHE = "public, max-age=3600"
STATE_CACHE = "no-store"
HORIZON_KEY = "state/horizon.json"
GUARD_KEY = "state/guard.json"
TIMELINE_KEY = "timeline.json"
CONTAINER = "adts"


class BucketClient(Protocol):
    def put_object(self, **kwargs: Any) -> dict: ...
    def get_object(self, **kwargs: Any) -> dict: ...
    def delete_object(self, **kwargs: Any) -> dict: ...


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class PutBudget:
    """Own-write cap (spec): at most `limit` PUT requests per UTC day."""

    def __init__(self, path: Path, limit: int, today: Callable[[], str] = _utc_today):
        self.path, self.limit, self.today = Path(path), limit, today

    def take(self) -> None:
        data = read_json(self.path, {}) or {}
        day = self.today()
        count = data.get("count", 0) if data.get("day") == day else 0
        if count >= self.limit:
            raise PutBudgetExceeded(f"daily PUT budget of {self.limit} reached for {day} (UTC)")
        write_json(self.path, {"day": day, "count": count + 1})


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


class Uploader:
    def __init__(self, client: BucketClient, bucket: str, budget: PutBudget, *,
                 sleep: Callable[[float], None] = time.sleep, attempts: int = 4, base_delay_s: float = 1.0):
        self.client, self.bucket, self.budget = client, bucket, budget
        self.sleep, self.attempts, self.base_delay_s = sleep, attempts, base_delay_s

    def put(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        last: Exception | None = None
        for attempt in range(self.attempts):
            self.budget.take()                      # every attempt is a billable request
            try:
                resp = self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                              ContentType=content_type, CacheControl=cache_control)
                status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status == 200:
                    return
                last = PublishError(f"PUT {key}: HTTP {status}")
            except Exception as exc:                # botocore raises many types; all are retryable here
                last = exc
            if attempt + 1 < self.attempts:
                self.sleep(self.base_delay_s * 2 ** attempt)
        raise PublishError(f"PUT {key} failed after {self.attempts} attempts: {last}") from last

    def get_json(self, key: str) -> dict | None:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _error_code(exc) in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read())

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise PublishError(f"DELETE {key} failed: {exc}") from exc


def guard_blocks_publishing(uploader: Uploader, ws: Workspace, now_s: float, interval_s: float) -> bool:
    cached = read_json(ws.guard_cache_path)
    if cached is not None and now_s - cached["checked_at"] < interval_s:
        return cached["blocked"]
    try:
        doc = uploader.get_json(GUARD_KEY)
        blocked, error = bool(doc and doc.get("tripped")), None
    except Exception as exc:                        # cannot see the guard: do not spend
        blocked, error = True, str(exc)
    write_json(ws.guard_cache_path, {"checked_at": now_s, "blocked": blocked, "error": error})
    return blocked


@contextmanager
def publish_lock(ws: Workspace) -> Iterator[None]:
    ws.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(ws.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublishLocked("another transmitter publish or prune holds the lock "
                                "(is `transmitter run` running?); not waiting") from exc
        yield
    finally:
        os.close(fd)


@dataclass
class Publisher:
    ws: Workspace
    cfg: TransmitterConfig
    epoch: Epoch
    uploader: Uploader
    template: str
    # A planned row's analysis, or None. Injected so the timeline does not
    # depend on the analysis cache surviving: production reads-or-computes.
    analysis_for: Callable[[PlanRow], ShowAnalysis | None]
    log: Callable[[str], None] = print


@dataclass
class PublishReport:
    uploaded: list[int] = field(default_factory=list)
    horizon: tuple[int, int] | None = None
    stopped: str | None = None       # "guard" | "put-budget"
    error: str | None = None


def horizon_doc(epoch: Epoch, first: int, last: int, now_us: int, fallback_version: str | None) -> dict:
    return {"epoch_id": epoch.epoch_id, "epoch": epoch.iso, "d": grid.D_US / 1_000_000,
            "first": first, "last": last, "published_at": grid.us_to_iso(now_us),
            "container": CONTAINER, "fallback_version": fallback_version}


def put_json(uploader: Uploader, key: str, doc: dict, cache_control: str) -> None:
    body = (json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n").encode()
    uploader.put(key, body, JSON_TYPE, cache_control)


def check_epoch(state: PublishState, epoch: Epoch) -> None:
    if state.epoch_id is not None and state.epoch_id != epoch.epoch_id:
        raise PublishError(f"published state belongs to epoch {state.epoch_id}, not {epoch.epoch_id}; "
                           "an epoch change is a deliberate re-render-everything operation")


def _extend_runs(runs: list[list[int]], start: int, last: int) -> list[list[int]]:
    """Add [start, last] to the uploaded-segment runs prune deletes, merging
    with the last run when they touch or overlap (a batch retrying a range
    an earlier, stopped batch already recorded)."""
    runs = [list(r) for r in runs]
    if runs and runs[-1][0] <= start <= runs[-1][1] + 1:
        runs[-1][1] = max(runs[-1][1], last)
    else:
        runs.append([start, last])
    return runs


def _publish_site(p: Publisher, rows: list[PlanRow], last: int, now_us: int, notes: dict[str, str]) -> dict[str, str]:
    pause = grid.samples_for_seconds(p.cfg.render.clip_pause_seconds)
    lo, hi = now_us - site.DAY_US, p.epoch.start_us(last + 1)
    analyses = {}
    for r in rows:                                   # only rows the timeline window can list
        start_us, end_us = site.row_span_us(r, p.epoch)
        if r.key not in analyses and end_us > lo and start_us < hi:
            a = p.analysis_for(r)
            if a is not None:
                analyses[r.key] = a
    timeline = site.build_timeline(rows, analyses, p.epoch, now_us=now_us, last_n=last, pause_samples=pause)
    notes = dict(notes)
    root = p.cfg.station.root
    for show in timeline["shows"]:
        slug = show["slug"]
        row = next(r for r in rows if r.slug == slug and r.key in analyses)
        manifest, briefing = site.read_package_notes(Path(root) / row.dir) if root else (None, None)
        if manifest is None and slug in notes:
            continue                                 # never replace a published page with a degraded one
        doc = site.build_notes(slug, manifest, briefing, site.airtimes(rows, slug, p.epoch, lo, hi),
                               analyses[row.key].meta)
        notes_body = (json.dumps(doc, sort_keys=True) + "\n").encode()
        page = site.render_show_page(p.template, doc, site_url=p.cfg.antenna.site_url,
                                     station_name=p.cfg.antenna.station_name).encode()
        digest = hashlib.sha256(notes_body + b"\0" + page).hexdigest()
        if notes.get(slug) == digest:
            continue
        p.uploader.put(f"notes/{slug}.json", notes_body, JSON_TYPE, NOTES_CACHE)
        p.uploader.put(f"show/{slug}.html", page, HTML_TYPE, NOTES_CACHE)
        notes[slug] = digest
    put_json(p.uploader, TIMELINE_KEY, timeline, TIMELINE_CACHE)
    return notes


def publish_batch(p: Publisher, now_us: int) -> PublishReport:
    report = PublishReport()
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            report.stopped = "guard"
            return report
        state = load_publish_state(p.ws)
        check_epoch(state, p.epoch)
        rows = read_plan(p.ws.plan_path)
        nxt = publish_next(rows, state.last)
        if nxt is None:
            return report
        seg_dir = p.ws.seg_dir(p.epoch.epoch_id)
        batch: list[int] = []
        for n in range(nxt, nxt + p.cfg.publish.batch_segments):
            if not (seg_dir / f"{n}.aac").exists():
                break
            batch.append(n)
        if not batch:
            return report
        # Record the range before the first PUT: if this batch stops part-way
        # (budget, horizon failure) and a recovery later abandons the range,
        # prune still deletes whatever of it reached R2.
        runs = _extend_runs(state.runs, nxt, batch[-1])
        if runs != state.runs:
            state.runs = runs
            save_publish_state(p.ws, state)
        uploaded: list[int] = []
        try:
            for n in batch:
                path = seg_dir / f"{n}.aac"
                p.uploader.put(segment_key(p.epoch.epoch_id, n), path.read_bytes(), AAC_TYPE, IMMUTABLE)
                uploaded.append(n)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
        except PublishError as exc:
            report.error = str(exc)
        if not uploaded or report.stopped:
            return report
        continuing = state.last is not None and nxt == state.last + 1 and state.first is not None
        first = state.first if continuing else nxt
        last = uploaded[-1]
        notes = state.notes
        try:
            notes = _publish_site(p, rows, last, now_us, state.notes)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
            return report
        except Exception as exc:                     # segments are fine; the horizon still advances
            p.log(f"site step failed: {exc!r}")
            report.error = f"site: {exc!r}"
        try:
            put_json(p.uploader, HORIZON_KEY,
                     horizon_doc(p.epoch, first, last, now_us, load_fallback_version(p.ws)), STATE_CACHE)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
            return report
        except PublishError as exc:
            report.error = f"horizon: {exc}"
            return report
        save_publish_state(p.ws, PublishState(epoch_id=p.epoch.epoch_id, first=first, last=last,
                                              runs=state.runs, notes=notes))
        for n in uploaded:                           # only now: the horizon and local state agree
            (seg_dir / f"{n}.aac").unlink(missing_ok=True)
        report.uploaded, report.horizon = uploaded, (first, last)
        return report
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_r2.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): R2 publisher with the ordering invariant, retries, PUT budget and guard read"
```

---

