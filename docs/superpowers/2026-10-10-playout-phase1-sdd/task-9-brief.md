### Task 9: Plan and render steps — revalidation, recovery, segment writing

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/pipeline.py`
- Create: `packages/transmitter/tests_transmitter/test_pipeline.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (`FakeEngine`)

**Interfaces:**
- Consumes: Tasks 3–8: `TransmitterConfig`, `Workspace`, `Epoch`, `atomic_write_bytes`, `load_publish_state`, `FrameStore/PlanRow/rows_overlapping`, `station.scan/Show/Ineligible`, `planner.*`, `analysis.load_or_analyze/ShowAnalysis`, `render.render_show/planned_frames/RenderSettings`, `aacenc.extra_frames/silent_frame`, `errors.*`.
- Produces:
  - `Engine` protocol: `analyze(show) -> ShowAnalysis`, `extra_frames() -> int`, `silent_frame() -> bytes`, `encode_show(show, analysis, out_path) -> int`. `FfmpegEngine(ws, cfg)` implements it.
  - `Station(ws, cfg, epoch, engine, scan=None, log=print)` with `scan_now(now_us) -> list[Show]`, `gap_frames`, `pause_samples`, `lead_us`, `until_frame(now_us)`, `start_margin_segments`, `frames_of(show) -> int`.
  - `plan_step(st, now_us, *, max_new=None) -> list[PlanRow]`.
  - `RenderReport(written: list[int], replanned: list[str], covered: bool)`; `render_step(st, now_us, *, limit=None) -> RenderReport` — raises `FrameCountDrift` on an encode/plan frame mismatch, and `LayoutError` when a row whose encode is missing has already started airing (`r.start_frame < n·441`): re-planning it would cut a show mid-air. Garbage-collects finished encodes and `render/shows/.*.tmp` files older than 1 h.
  - helpers: `FakeEngine(samples_per_file=60*44100, extra=1, fail=set(), drift=0)`, `make_station(tmp_path, n_packages=3, engine=None) -> tuple[Station, list[str]]`, constants `E`, `NOW`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
from transmitter import grid as _grid
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import RenderError
from transmitter.render import planned_frames
from transmitter.workspace import Epoch, Workspace

E = 1_800_000_000 * 1_000_000          # an epoch on a whole second (2027-01-15)
NOW = E + 1_000 * _grid.D_US


class FakeEngine:
    """An Engine without ffmpeg: a show's "encode" is fake ADTS frames whose
    payload is '<key>:<i>', so segment contents can be read back."""

    def __init__(self, samples_per_file: int = 60 * 44_100, extra: int = 1,
                 fail: set[str] | None = None, drift: int = 0, pause_seconds: float = 0.75):
        self.samples_per_file = samples_per_file
        self.extra = extra
        self.fail = fail or set()
        self.drift = drift
        self.pause_samples = _grid.samples_for_seconds(pause_seconds)
        self.encoded: list[str] = []
        self.analyzed: list[str] = []

    def analyze(self, show):
        # Computes like production's analyze, but never writes the analysis
        # cache: tests that publish prove the timeline does not depend on it.
        self.analyzed.append(show.slug)
        files = tuple(FileAnalysis(e.path, e.kind, e.title, self.samples_per_file) for e in show.entries)
        return ShowAnalysis(key=show.key, slug=show.slug, files=files, tracks_i_lufs=-20.0,
                            tracks_tp_dbfs=-3.0, meta=dict(show.meta))

    def extra_frames(self):
        return self.extra

    def silent_frame(self):
        return fake_frame("silence", 0)

    def encode_show(self, show, analysis, out_path):
        if show.slug in self.fail:
            raise RenderError(f"{show.slug}: simulated decode failure")
        frames = planned_frames(analysis, self.pause_samples, self.extra) + self.drift
        write_fake_show(out_path, show.key, frames)
        self.encoded.append(show.slug)
        return frames


def make_station(tmp_path: Path, n_packages: int = 3, engine=None):
    from transmitter.pipeline import Station

    root = make_root(tmp_path)
    for i in range(n_packages):
        build_package(root, f"band-2005-11-{i + 1:02d}")
    cfg = TransmitterConfig(root=tmp_path / "tx",
                            station={"root": root, "quiet_minutes": 0},
                            planner={"start_delay_minutes": 0.5},
                            render={"lead_hours": 0.1, "low_water_hours": 0.05})
    logs: list[str] = []
    st = Station(ws=Workspace(cfg.root), cfg=cfg, epoch=Epoch("etest", E),
                 engine=engine or FakeEngine(), log=logs.append)
    return st, logs
```

`tests_transmitter/test_pipeline.py`:

```python
import os
import time

import pytest

from tests_transmitter.helpers import NOW, FakeEngine, make_station, payloads, set_age
from transmitter import grid, pipeline, segment
from transmitter.errors import FrameCountDrift, LayoutError, StationRootError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.layout import segment_pieces
from transmitter.planner import read_plan
from transmitter.state import PublishState, save_publish_state

HOUR_US = 3600 * 1_000_000


def test_plan_step_starts_a_run_ahead_of_now(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    now_n = st.epoch.index_at(NOW)
    assert st.start_margin_segments == 3
    assert rows[0].run_start and rows[0].start_frame == (now_n + 3) * F
    assert rows[-1].end_frame >= st.until_frame(NOW)
    for a, b in zip(rows, rows[1:]):
        assert b.start_frame == a.end_frame + grid.gap_frames(2.0) and not b.run_start
    assert read_plan(st.ws.plan_path) == rows


def test_plan_step_is_idempotent_when_covered(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    assert pipeline.plan_step(st, NOW) == rows


def test_plan_step_max_new(tmp_path):
    st, _ = make_station(tmp_path)
    assert len(pipeline.plan_step(st, NOW, max_new=1)) == 1


def test_plan_step_refuses_without_marker_and_keeps_plan(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    (st.cfg.station.root / ".station-root").unlink()
    with pytest.raises(StationRootError):
        pipeline.plan_step(st, NOW + HOUR_US)
    assert read_plan(st.ws.plan_path) == rows


def test_plan_step_recovers_after_an_outage(tmp_path):
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    first_n = rows[0].start_frame // F
    last = first_n + 10
    save_publish_state(st.ws, PublishState(epoch_id="etest", first=first_n, last=last, runs=[[first_n, last]]))
    seg_dir = st.ws.seg_dir("etest")
    seg_dir.mkdir(parents=True)
    stale = seg_dir / f"{last + 1}.aac"
    stale.write_bytes(b"x")
    later = NOW + 3 * HOUR_US
    new_rows = pipeline.plan_step(st, later)
    boundary = (last + 1) * F
    assert new_rows[0].cut_frame == boundary            # the show on air when it stopped
    run = [r for r in new_rows if r.run_start]
    assert run[-1].start_frame == (st.epoch.index_at(later) + 3) * F
    assert all(r.start_frame >= run[-1].start_frame for r in new_rows[1:])
    assert not stale.exists()
    assert any("recovery" in m for m in logs)


def _seg(st, n):
    return segment.parse((st.ws.seg_dir("etest") / f"{n}.aac").read_bytes())


def test_render_step_writes_grid_segments_up_to_the_lead(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    report = pipeline.render_step(st, NOW)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))
    for n in report.written:
        ts, frames = _seg(st, n)
        assert ts == grid.segment_timestamp(n) and len(frames) == F
    assert payloads(_seg(st, first_n)[1])[0] == f"{rows[0].key}:0"


def test_render_step_fills_the_show_gap_with_silence(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    pipeline.render_step(st, NOW)
    n = rows[0].end_frame // F
    expected: list[str] = []
    for p in segment_pieces(rows, n):
        expected += ["silence:0"] * p.count if p.key is None else [f"{p.key}:{i}" for i in range(p.offset, p.offset + p.count)]
    assert payloads(_seg(st, n)[1]) == expected
    assert "silence:0" in expected


def test_render_step_is_idempotent_and_honours_limit(tmp_path):
    st, _ = make_station(tmp_path)
    pipeline.plan_step(st, NOW)
    first = pipeline.render_step(st, NOW, limit=5)
    assert len(first.written) == 5
    rest = pipeline.render_step(st, NOW)
    assert rest.written[0] == first.written[-1] + 1
    assert pipeline.render_step(st, NOW).written == []


def test_render_step_replans_a_changed_package(tmp_path):
    engine = FakeEngine()
    st, logs = make_station(tmp_path, engine=engine)
    rows = pipeline.plan_step(st, NOW)
    victim = rows[1]
    f = next((st.cfg.station.root / victim.dir / "audio").iterdir())
    f.write_bytes(f.read_bytes() + b"re-voiced")         # file set (and key) change
    set_age(st.cfg.station.root / victim.dir, 3600)
    report = pipeline.render_step(st, NOW)
    assert victim.slug in report.replanned
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[1].start_frame == victim.start_frame and new_rows[1].slug != victim.slug
    assert victim.slug not in engine.encoded
    assert any("plan-changed" in m for m in logs)


def test_render_step_skips_a_show_that_fails_to_encode(tmp_path):
    st0, _ = make_station(tmp_path / "probe")
    victim = pipeline.plan_step(st0, NOW)[1].slug
    st, logs = make_station(tmp_path / "real", engine=FakeEngine(fail={victim}))
    pipeline.plan_step(st, NOW)
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim]
    assert any("render failed" in m for m in logs)


def test_frame_count_drift_is_fatal(tmp_path):
    st, _ = make_station(tmp_path, engine=FakeEngine(drift=1))
    pipeline.plan_step(st, NOW)
    with pytest.raises(FrameCountDrift):
        pipeline.render_step(st, NOW)


def test_render_step_refuses_to_replan_a_show_already_on_air(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    first_n = rows[0].start_frame // F
    mid_n = rows[1].start_frame // F + 1                    # starts after rows[1] does
    pipeline.render_step(st, NOW, limit=mid_n - first_n)     # stops just before mid_n
    (st.ws.shows_dir / f"{rows[1].key}.aac").unlink()        # its encode is lost
    with pytest.raises(LayoutError, match="already on air"):
        pipeline.render_step(st, NOW)
    assert read_plan(st.ws.plan_path) == rows
    assert not (st.ws.seg_dir("etest") / f"{mid_n}.aac").exists()


def test_render_step_gcs_finished_encodes(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    shows = st.ws.shows_dir
    shows.mkdir(parents=True, exist_ok=True)
    old_tmp, new_tmp = shows / ".k-old.aac.tmp", shows / ".k-new.aac.tmp"
    old_tmp.write_bytes(b"x")
    new_tmp.write_bytes(b"x")
    two_hours_ago = time.time() - 7200
    os.utime(old_tmp, (two_hours_ago, two_hours_ago))
    pipeline.render_step(st, NOW)
    assert not (shows / f"{rows[0].key}.aac").exists()     # fully segmented
    assert (shows / f"{rows[1].key}.aac").exists()         # still needed
    assert not old_tmp.exists() and new_tmp.exists()       # a crashed encode's temp; one in flight
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.pipeline'`.

- [ ] **Step 3: Implement `pipeline.py`**

```python
"""Plan and render steps over the workspace (spec "Lead", "Frozen means
rendered", "Recovery after an outage longer than the lead").

plan_step extends plan.jsonl until it covers now + lead (or starts a fresh
run after an outage); render_step writes segment files
render/seg/<epoch_id>/<N>.aac in ascending N from the next unpublished
segment to now + lead, encoding each show the first time a segment needs it.
Before encoding, a show is re-validated against the current station scan;
a changed or failing show is skipped at its boundary and the plan re-extended
from there. Encoded shows are frozen: their segments are built from the
encode regardless of later package changes.
"""

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from transmitter import aacenc, analysis as analysis_mod, grid, render, station
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import FrameCountDrift, LayoutError, TransmitterError
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import FrameStore, PlanRow, rows_overlapping
from transmitter.planner import (cut_for_recovery, extend, next_start, publish_next, read_plan,
                                 replan_from, write_plan)
from transmitter.state import load_publish_state
from transmitter.station import Ineligible, Show
from transmitter.workspace import Epoch, Workspace, atomic_write_bytes


class Engine(Protocol):
    def analyze(self, show: Show) -> ShowAnalysis: ...
    def extra_frames(self) -> int: ...
    def silent_frame(self) -> bytes: ...
    def encode_show(self, show: Show, analysis: ShowAnalysis, out_path: Path) -> int: ...


class FfmpegEngine:
    def __init__(self, ws: Workspace, cfg: TransmitterConfig):
        self.ws = ws
        self.settings = render.RenderSettings.from_config(cfg.render)

    def analyze(self, show: Show) -> ShowAnalysis:
        return analysis_mod.load_or_analyze(self.ws.cache_dir, show, self.settings.ffmpeg)

    def extra_frames(self) -> int:
        return aacenc.extra_frames(self.settings.ffmpeg)

    def silent_frame(self) -> bytes:
        return aacenc.silent_frame(self.settings.ffmpeg)

    def encode_show(self, show: Show, analysis: ShowAnalysis, out_path: Path) -> int:
        return render.render_show(show, analysis, out_path, settings=self.settings,
                                  extra=self.extra_frames())


Scanner = Callable[[float], tuple[list[Show], list[Ineligible]]]


@dataclass
class Station:
    ws: Workspace
    cfg: TransmitterConfig
    epoch: Epoch
    engine: Engine
    scan: Scanner | None = None
    log: Callable[[str], None] = print

    def scan_now(self, now_us: int) -> list[Show]:
        """Eligible shows; raises StationRootError when the root is unusable."""
        if self.scan is not None:
            return self.scan(now_us / 1e6)[0]
        return station.scan(self.cfg.station.root, now_s=now_us / 1e6,
                            quiet_s=self.cfg.station.quiet_minutes * 60)[0]

    @property
    def gap_frames(self) -> int:
        return grid.gap_frames(self.cfg.render.show_gap_seconds)

    @property
    def pause_samples(self) -> int:
        return grid.samples_for_seconds(self.cfg.render.clip_pause_seconds)

    @property
    def lead_us(self) -> int:
        return int(self.cfg.render.lead_hours * 3600 * 1_000_000)

    @property
    def start_margin_segments(self) -> int:
        return math.ceil(self.cfg.planner.start_delay_minutes * 60 * 1_000_000 / grid.D_US)

    def until_frame(self, now_us: int) -> int:
        return (self.epoch.index_at(now_us + self.lead_us) + 2) * SEGMENT_FRAMES

    def frames_of(self, show: Show) -> int:
        return render.planned_frames(self.engine.analyze(show), self.pause_samples,
                                     self.engine.extra_frames())

    def extend(self, rows: list[PlanRow], shows: list[Show], now_us: int, *, start_frame: int,
               run_start: bool, max_new: int | None = None) -> list[PlanRow]:
        return extend(rows, shows, frames_of=self.frames_of, seed=self.cfg.planner.seed,
                      gap_frames=self.gap_frames, until_frame=self.until_frame(now_us),
                      start_frame=start_frame, run_start=run_start, max_new=max_new,
                      on_skip=lambda s, e: self.log(f"skipping {s.slug}: {e}"))


def _drop_unpublished_segments(st: Station, last: int | None) -> None:
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    if not seg_dir.is_dir():
        return
    floor = -1 if last is None else last
    for p in seg_dir.glob("*.aac"):
        if p.stem.isdigit() and int(p.stem) > floor:
            p.unlink(missing_ok=True)


def plan_step(st: Station, now_us: int, *, max_new: int | None = None) -> list[PlanRow]:
    shows = st.scan_now(now_us)              # StationRootError: refuse, plan untouched
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    now_n = st.epoch.index_at(now_us)
    fresh = (now_n + st.start_margin_segments) * SEGMENT_FRAMES
    nxt = publish_next(rows, pub.last)
    if nxt is None:
        start, run_start = fresh, True
    elif nxt <= now_n:
        # The next segment to publish is already due: the outage outlasted the
        # lead and listeners are already off the live edge. Start a fresh run.
        rows = cut_for_recovery(rows, pub.last)
        _drop_unpublished_segments(st, pub.last)
        st.log(f"recovery: segment {nxt} was due at index {now_n}; new run at segment "
               f"{fresh // SEGMENT_FRAMES}")
        start, run_start = fresh, True
    else:
        if rows[-1].end_frame >= st.until_frame(now_us):
            return rows
        start, run_start = next_start(rows, st.gap_frames), False
    rows = st.extend(rows, shows, now_us, start_frame=start, run_start=run_start, max_new=max_new)
    write_plan(st.ws.plan_path, rows)
    return rows


@dataclass
class RenderReport:
    written: list[int] = field(default_factory=list)
    replanned: list[str] = field(default_factory=list)
    covered: bool = True


TMP_MAX_AGE_S = 3600


def _gc_encodes(st: Station, rows: list[PlanRow], next_n: int) -> None:
    """Drop encodes no remaining segment needs, and temp files a crashed
    encode left behind (older than an hour, so never one still being written)."""
    keep = {r.key for r in rows if r.end_frame > next_n * SEGMENT_FRAMES}
    if not st.ws.shows_dir.is_dir():
        return
    for p in st.ws.shows_dir.glob("*.aac"):
        if p.stem not in keep:
            p.unlink(missing_ok=True)
    stale = time.time() - TMP_MAX_AGE_S
    for p in st.ws.shows_dir.glob(".*.tmp"):
        try:
            if p.stat().st_mtime < stale:
                p.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def render_step(st: Station, now_us: int, *, limit: int | None = None) -> RenderReport:
    report = RenderReport()
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    n = publish_next(rows, pub.last)
    if n is None:
        return report
    target = st.epoch.index_at(now_us + st.lead_us)
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    store = FrameStore(st.ws.shows_dir, st.engine.silent_frame())
    shows: dict[str, Show] | None = None
    excluded: set[str] = set()
    while n <= target and (limit is None or len(report.written) < limit):
        path = seg_dir / f"{n}.aac"
        if path.exists():
            n += 1
            continue
        if not rows or (n + 1) * SEGMENT_FRAMES > rows[-1].end_frame:
            report.covered = False
            break
        replanned = False
        for r in rows_overlapping(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES):
            if store.has(r.key):
                continue
            if r.start_frame < n * SEGMENT_FRAMES:
                # Its earlier segments are already rendered (frozen); a re-plan
                # here would cut the show mid-air. Alert and let the operator act.
                raise LayoutError(f"{r.slug} is already on air (from frame {r.start_frame}) but its "
                                  f"encode {r.key} is missing; refusing to re-plan into a mid-show cut")
            if shows is None:
                shows = {s.slug: s for s in st.scan_now(now_us)}
            show = shows.get(r.slug)
            reason = None
            if show is None or show.key != r.key:
                reason = "package changed or is no longer eligible"
            else:
                try:
                    frames = st.engine.encode_show(show, st.engine.analyze(show), store.path(r.key))
                    if frames != r.frames:
                        store.path(r.key).unlink(missing_ok=True)
                        raise FrameCountDrift(f"{r.slug}: encoded {frames} frames, plan says {r.frames}")
                except FrameCountDrift:
                    raise
                except TransmitterError as exc:
                    reason = f"render failed: {exc}"
            if reason is not None:
                excluded.add(r.slug)
                kept, start, run_start = replan_from(rows, rows.index(r))
                pool = [s for s in shows.values() if s.slug not in excluded]
                rows = st.extend(kept, pool, now_us, start_frame=start, run_start=run_start)
                write_plan(st.ws.plan_path, rows)
                st.log(f"plan-changed: skipped {r.slug} at frame {r.start_frame} ({reason})")
                report.replanned.append(r.slug)
                replanned = True
                break
        if replanned:
            continue
        atomic_write_bytes(path, store.build_segment(n, rows))
        report.written.append(n)
        n += 1
    _gc_encodes(st, rows, n)
    return report
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py -q`
Expected: PASS.

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): plan and render steps with revalidation, recovery and segment writing"
```

---

