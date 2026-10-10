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

Before the horizon PUT a batch persists its candidate `last` as the local
high-water mark (state.PublishState.high_water): a crash between that PUT and
the save advancing `last` must not let plan_step re-plan keys R2 may already
list. The horizon is never rewritten below that mark.
"""

import dataclasses
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
    # A clock stepped backwards (negative age) must not let a cached
    # `blocked: false` hold off the spend kill switch: re-read.
    if cached is not None and 0 <= now_s - cached["checked_at"] < interval_s:
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
        # notes and page BEFORE the timeline that references them: an exception
        # here propagates past the timeline PUT below.
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
        # After a crash between a horizon PUT and the local save, R2 lists up
        # to the high-water mark: re-send up to it in one batch, whatever
        # batch_segments is now, or a smaller batch would be held forever.
        end = nxt + p.cfg.publish.batch_segments
        if state.high_water is not None:
            end = max(end, state.high_water + 1)
        batch: list[int] = []
        for n in range(nxt, end):
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
            state.epoch_id = p.epoch.epoch_id
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
        if state.high_water is not None and last < state.high_water:
            # A crash after an earlier horizon PUT left R2 listing up to the
            # high-water mark; this batch re-sent part of that range and stopped.
            # Rewriting the horizon now would move R2's `last` backwards.
            report.error = (f"{report.error}; " if report.error else "") + \
                f"horizon held: segment {last} is below the high-water mark {state.high_water}"
            return report
        notes = state.notes
        try:
            notes = _publish_site(p, rows, last, now_us, state.notes)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
            return report
        except Exception as exc:                     # segments are fine; the horizon still advances
            p.log(f"site step failed: {exc!r}")
            report.error = f"site: {exc!r}"
        # Durably record that R2 may list up to `last` BEFORE the horizon PUT
        # (see the module docstring): plan_step never re-plans at or below it.
        if state.high_water != last:
            state = dataclasses.replace(state, epoch_id=p.epoch.epoch_id, high_water=last)
            save_publish_state(p.ws, state)
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
                                              runs=state.runs, notes=notes, high_water=last))
        for n in uploaded:                           # only now: the horizon and local state agree
            (seg_dir / f"{n}.aac").unlink(missing_ok=True)
        report.uploaded, report.horizon = uploaded, (first, last)
        return report


@dataclass
class PruneReport:
    deleted: int = 0
    first: int | None = None
    stopped: str | None = None       # "guard" | "put-budget" | "high-water"
    error: str | None = None


def prune(p: Publisher, now_us: int) -> PruneReport:
    """Delete segments that started more than `prune_margin` ago (so lagging
    players don't 404): advance horizon.first first, then delete by computed
    key range (per-key DeleteObject; never List, never DeleteObjects), across
    every recorded run. Never past horizon.last -- an outage must not move
    `last`, which the clock's off-air rule is measured from. Batched: nothing
    happens until `prune_min_segments` are prunable, since each prune costs a
    horizon PUT."""
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
        if state.high_water is not None and state.high_water > state.last:
            # R2 may list up to the high-water mark (a crash between a horizon
            # PUT and the save advancing `last`); a horizon bounded by `last`
            # would move R2's `last` backwards. publish_batch reconciles first.
            report.stopped = "high-water"
            return report
        cutoff_us = now_us - int(p.cfg.publish.prune_margin_minutes * 60 * 1_000_000)
        n_max = min(grid.first_segment_at_or_after(p.epoch.epoch_us, cutoff_us) - 1, state.last)
        prunable = sum(max(0, min(hi, n_max) - lo + 1) for lo, hi in state.runs)
        if prunable < p.cfg.publish.prune_min_segments:
            return report                    # batch it: each prune costs a horizon PUT
        if state.first is not None and n_max >= state.first:
            # The horizon stops listing them BEFORE any is deleted.
            try:
                put_json(p.uploader, HORIZON_KEY,
                         horizon_doc(p.epoch, n_max + 1, state.last, now_us, load_fallback_version(p.ws)),
                         STATE_CACHE)
            except PutBudgetExceeded as exc:
                report.stopped, report.error = "put-budget", str(exc)
                return report
            except PublishError as exc:
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
