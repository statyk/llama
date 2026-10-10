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
