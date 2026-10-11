import dataclasses
import os
import time

import pytest

from tests_transmitter.helpers import NOW, FakeEngine, make_station, payloads, set_age
from transmitter import grid, pipeline, segment
from transmitter.errors import FrameCountDrift, LayoutError, PlanError, StationRootError
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
    published = seg_dir / f"{last}.aac"
    published.write_bytes(b"p")
    later = NOW + 3 * HOUR_US
    new_rows = pipeline.plan_step(st, later)
    boundary = (last + 1) * F
    assert new_rows[0].cut_frame == boundary            # the show on air when it stopped
    run = [r for r in new_rows if r.run_start]
    assert run[-1].start_frame == (st.epoch.index_at(later) + 3) * F
    assert all(r.start_frame >= run[-1].start_frame for r in new_rows[1:])
    assert not stale.exists()
    assert published.read_bytes() == b"p"                  # published keys are never dropped
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
    k2 = next(s.key for s in st.scan_now(NOW) if s.slug == victim.slug)
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim.slug]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[:1] == rows[:1]                       # rows before it are untouched
    # Still eligible under its new key: re-planned in place, never encoded under K1.
    assert new_rows[1].start_frame == victim.start_frame and new_rows[1].slug == victim.slug
    assert new_rows[1].key == k2 != victim.key
    assert (st.ws.seg_dir("etest") / f"{victim.start_frame // F + 1}.aac").exists()
    assert victim.slug in engine.encoded
    assert any("plan-changed" in m and "package changed" in m for m in logs)


def test_render_step_excludes_a_package_no_longer_eligible(tmp_path):
    engine = FakeEngine()
    st, logs = make_station(tmp_path, engine=engine)
    rows = pipeline.plan_step(st, NOW)
    victim = rows[1]
    (st.cfg.station.root / victim.dir / "broadcast.m3u").unlink()    # no longer broadcast-ready
    assert victim.slug not in {s.slug for s in st.scan_now(NOW)}
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim.slug]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[1].start_frame == victim.start_frame
    assert victim.slug not in {r.slug for r in new_rows[1:]}
    assert victim.slug not in engine.encoded
    assert any("plan-changed" in m and "no longer eligible" in m for m in logs)


def test_render_step_skips_a_show_that_fails_to_encode(tmp_path):
    st0, _ = make_station(tmp_path / "probe")
    victim = pipeline.plan_step(st0, NOW)[1].slug
    st, logs = make_station(tmp_path / "real", engine=FakeEngine(fail={victim}))
    rows = pipeline.plan_step(st, NOW)
    assert rows[1].slug == victim
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[1].start_frame == rows[1].start_frame and new_rows[1].slug != victim
    assert any("render failed" in m for m in logs)


def test_frame_count_drift_is_fatal(tmp_path):
    st, _ = make_station(tmp_path, engine=FakeEngine(drift=1))
    rows = pipeline.plan_step(st, NOW)
    with pytest.raises(FrameCountDrift):
        pipeline.render_step(st, NOW)
    assert not (st.ws.shows_dir / f"{rows[0].key}.aac").exists()   # a drifted encode is never frozen


def _render_until_mid_show(st):
    """Plan and render up to (not including) a segment one past rows[1]'s
    start, so rows[1] is on air; return (rows, mid_n)."""
    rows = pipeline.plan_step(st, NOW)
    first_n = rows[0].start_frame // F
    mid_n = rows[1].start_frame // F + 1                    # starts after rows[1] does
    pipeline.render_step(st, NOW, limit=mid_n - first_n)     # stops just before mid_n
    assert not (st.ws.seg_dir("etest") / f"{mid_n}.aac").exists()
    return rows, mid_n


def test_render_step_reencodes_a_lost_encode_of_an_unchanged_show_on_air(tmp_path):
    # An operator cleaned render/shows (or restored ~/.transmitter without it)
    # while a show is on air: the package is unchanged, so a fresh encode
    # reproduces the planned frame count and the next segments are identical.
    engine = FakeEngine()
    st, _ = make_station(tmp_path, engine=engine)
    rows = pipeline.plan_step(st, NOW)
    pipeline.render_step(st, NOW)                            # the reference render
    reference = _seg_files(st)
    mid_n = rows[1].start_frame // F + 1
    seg_dir = st.ws.seg_dir("etest")
    for p in seg_dir.glob("*.aac"):
        if int(p.stem) >= mid_n:
            p.unlink()
    (st.ws.shows_dir / f"{rows[1].key}.aac").unlink()        # its encode is lost
    encoded_before = engine.encoded.count(rows[1].slug)
    report = pipeline.render_step(st, NOW)
    assert report.replanned == []
    assert report.written[0] == mid_n
    assert engine.encoded.count(rows[1].slug) == encoded_before + 1
    assert read_plan(st.ws.plan_path) == rows                # never re-planned
    assert _seg_files(st) == reference                       # byte-identical segments


@pytest.mark.parametrize("damage", ["changed", "ineligible", "render-fails", "frames-changed"])
def test_render_step_refuses_to_replan_a_show_already_on_air(tmp_path, damage):
    engine = FakeEngine()
    st, logs = make_station(tmp_path, engine=engine)
    rows, mid_n = _render_until_mid_show(st)
    victim = rows[1]
    (st.ws.shows_dir / f"{victim.key}.aac").unlink()         # its encode is lost
    pkg = st.cfg.station.root / victim.dir
    if damage == "changed":
        f = next((pkg / "audio").iterdir())
        f.write_bytes(f.read_bytes() + b"re-voiced")         # file set (and key) change
        set_age(pkg, 3600)
    elif damage == "ineligible":
        (pkg / "broadcast.m3u").unlink()
    elif damage == "render-fails":
        engine.fail.add(victim.slug)
    else:
        engine.extra += 1                                     # an encoder change moved the frame-count model
    with pytest.raises(LayoutError, match="already on air"):
        pipeline.render_step(st, NOW)
    assert read_plan(st.ws.plan_path) == rows
    assert not (st.ws.seg_dir("etest") / f"{mid_n}.aac").exists()
    assert not (st.ws.shows_dir / f"{victim.key}.aac").exists()
    assert not any("plan-changed" in m for m in logs)


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


def _seg_files(st):
    seg_dir = st.ws.seg_dir("etest")
    return {p.name: p.read_bytes() for p in seg_dir.glob("*.aac")} if seg_dir.is_dir() else {}


def _publish_up_to(st, first, last):
    save_publish_state(st.ws, PublishState(epoch_id="etest", first=first, last=last, runs=[[first, last]]))


def test_render_step_replans_when_planned_frames_change(tmp_path):
    # An operator changes [render] clip_pause_seconds (or an ffmpeg upgrade
    # changes extra_frames): rows planned under the old model are re-planned
    # from the render frontier, never encoded and reported as drift.
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    render_cfg = st.cfg.render.model_copy(update={"clip_pause_seconds": 1.0})
    engine = FakeEngine(pause_seconds=1.0)
    st2 = dataclasses.replace(st, cfg=st.cfg.model_copy(update={"render": render_cfg}), engine=engine)
    new_frames = st2.frames_of(next(s for s in st2.scan_now(NOW) if s.slug == rows[0].slug))
    assert new_frames != rows[0].frames
    report = pipeline.render_step(st2, NOW)
    assert report.replanned == [rows[0].slug]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[0].run_start and new_rows[0].start_frame == rows[0].start_frame
    # Re-measured and re-planned in place under the current model, then encoded.
    assert new_rows[0].slug == rows[0].slug and new_rows[0].frames == new_frames
    assert engine.encoded[0] == rows[0].slug
    first_n = rows[0].start_frame // F
    assert report.written[0] == first_n
    assert payloads(_seg(st, first_n)[1])[0] == f"{new_rows[0].key}:0"
    assert any("plan-changed" in m and "frame count" in m for m in logs)


def test_plan_step_recovery_with_nothing_eligible_touches_nothing(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    _publish_up_to(st, written[0], written[-3])
    before = _seg_files(st)
    st.scan = lambda now_s: ([], [])                   # every package momentarily "changing"
    with pytest.raises(PlanError):
        pipeline.plan_step(st, NOW + 3 * HOUR_US)
    assert read_plan(st.ws.plan_path) == rows
    assert _seg_files(st) == before


def test_render_step_writes_nothing_while_recovery_is_pending(tmp_path):
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    last = written[-3]
    _publish_up_to(st, written[0], last)
    for n in written:
        if n > last:
            (st.ws.seg_dir("etest") / f"{n}.aac").unlink()
    before = _seg_files(st)
    later = NOW + 3 * HOUR_US                          # last + 1 is long past due
    report = pipeline.render_step(st, later)
    assert report.written == [] and not report.covered
    assert _seg_files(st) == before
    assert read_plan(st.ws.plan_path) == rows
    assert any("recovery pending" in m for m in logs)


def test_plan_step_without_a_plan_resumes_after_published_keys(tmp_path):
    st, _ = make_station(tmp_path)
    pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    fresh_n = st.epoch.index_at(NOW) + st.start_margin_segments
    last = written[len(written) // 2]
    assert last + 1 > fresh_n
    _publish_up_to(st, written[0], last)
    st.ws.plan_path.unlink()                           # the operator deleted plan.jsonl
    new_rows = pipeline.plan_step(st, NOW)
    assert new_rows[0].run_start and new_rows[0].start_frame == (last + 1) * F
    left = {int(name.split(".")[0]) for name in _seg_files(st)}
    assert left == {n for n in written if n <= last}   # unpublished old-plan segments dropped
    report = pipeline.render_step(st, NOW)
    assert report.written[0] == last + 1
    assert payloads(_seg(st, last + 1)[1])[0] == f"{new_rows[0].key}:0"


def test_plan_step_without_a_plan_after_old_published_keys_starts_fresh(tmp_path):
    st, _ = make_station(tmp_path)
    _publish_up_to(st, 10, 20)                         # long before now
    rows = pipeline.plan_step(st, NOW)
    assert rows[0].run_start and rows[0].start_frame == (st.epoch.index_at(NOW) + 3) * F


def test_render_step_refuses_without_marker(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    (st.cfg.station.root / ".station-root").unlink()
    with pytest.raises(StationRootError):
        pipeline.render_step(st, NOW)
    assert _seg_files(st) == {}
    assert read_plan(st.ws.plan_path) == rows


def _with_pause(st, seconds):
    """The same station after an operator changed [render] clip_pause_seconds."""
    render_cfg = st.cfg.render.model_copy(update={"clip_pause_seconds": seconds})
    return dataclasses.replace(st, cfg=st.cfg.model_copy(update={"render": render_cfg}),
                               engine=FakeEngine(pause_seconds=seconds))


def test_one_package_station_replans_in_place_on_a_frame_count_change(tmp_path):
    # With nothing else eligible, excluding the show would leave an empty pool:
    # PlanError on every tick, forever. It is re-planned in place instead.
    st, logs = make_station(tmp_path, n_packages=1)
    rows = pipeline.plan_step(st, NOW)
    st2 = _with_pause(st, 1.0)
    new_frames = st2.frames_of(st2.scan_now(NOW)[0])
    assert new_frames != rows[0].frames
    report = pipeline.render_step(st2, NOW)
    assert report.replanned == [rows[0].slug]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[0].slug == rows[0].slug and new_rows[0].start_frame == rows[0].start_frame
    assert all(r.frames == new_frames for r in new_rows)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))
    assert payloads(_seg(st, first_n)[1])[0] == f"{new_rows[0].key}:0"
    assert st2.engine.encoded == [rows[0].slug]
    assert any("plan-changed" in m and "frame count" in m for m in logs)


def test_one_package_station_replans_in_place_after_a_revoice(tmp_path):
    st, logs = make_station(tmp_path, n_packages=1)
    rows = pipeline.plan_step(st, NOW)
    pkg = st.cfg.station.root / rows[0].dir
    f = next((pkg / "audio").iterdir())
    f.write_bytes(f.read_bytes() + b"re-voiced")         # key K1 -> K2, still eligible
    set_age(pkg, 3600)
    k2 = st.scan_now(NOW)[0].key
    assert k2 != rows[0].key
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [rows[0].slug]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[0].slug == rows[0].slug and new_rows[0].start_frame == rows[0].start_frame
    assert all(r.key == k2 for r in new_rows)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))
    assert payloads(_seg(st, first_n)[1])[0] == f"{k2}:0"
    assert any("plan-changed" in m and "package changed" in m for m in logs)


UNSTABLE_MAX_CALLS = 10      # the guard needs 3-4; more means it stopped bounding the loop


def _unstable(st, slug):
    """Make `slug`'s planned frame count differ on every measurement. Past
    UNSTABLE_MAX_CALLS it raises AssertionError, which render_step does not
    catch, so a broken guard fails the test instead of hanging the suite."""
    calls = {"n": 0}
    real = st.planned_frames

    def planned(analysis):
        if analysis.slug != slug:
            return real(analysis)
        calls["n"] += 1
        if calls["n"] > UNSTABLE_MAX_CALLS:
            raise AssertionError(f"{slug} measured {calls['n']} times: the re-plan loop is unbounded")
        return real(analysis) + calls["n"]
    st.planned_frames = planned
    return calls


def test_a_show_mismatching_twice_in_one_call_is_excluded(tmp_path):
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    victim = rows[0].slug
    _unstable(st, victim)
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim, victim]           # re-planned once in place, then excluded
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[0].start_frame == rows[0].start_frame and new_rows[0].slug != victim
    assert victim not in st.engine.encoded
    first_n = rows[0].start_frame // F
    assert report.written[0] == first_n
    assert payloads(_seg(st, first_n)[1])[0] == f"{new_rows[0].key}:0"


def test_a_lone_show_mismatching_twice_in_one_call_is_a_plan_error(tmp_path):
    st, logs = make_station(tmp_path, n_packages=1)
    pipeline.plan_step(st, NOW)
    _unstable(st, st.scan_now(NOW)[0].slug)
    with pytest.raises(PlanError, match="no eligible packages"):
        pipeline.render_step(st, NOW)
    # One in-place re-plan, then the second mismatch excludes it: bounded.
    assert sum("plan-changed" in m for m in logs) == 1
    assert st.engine.encoded == []


def test_the_second_mismatch_rule_is_per_slug(tmp_path):
    # Two different shows each mismatch ONCE in one call (a measurement that
    # differs on its first read only): both are re-planned in place; neither
    # is excluded because some OTHER show already mismatched.
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    a, b = rows[0].slug, rows[1].slug
    assert a != b
    real = st.planned_frames
    seen: set[str] = set()

    def flaky_once(analysis):
        if analysis.slug in (a, b) and analysis.slug not in seen:
            seen.add(analysis.slug)
            return real(analysis) + 1
        return real(analysis)
    st.planned_frames = flaky_once
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [a, b]
    new_rows = read_plan(st.ws.plan_path)
    assert [r.slug for r in new_rows[:2]] == [a, b]
    assert st.engine.encoded[:2] == [a, b]
    assert sum("plan-changed" in m for m in logs) == 2


def test_the_second_mismatch_rule_is_per_slug_for_package_changes(tmp_path):
    # A frame-count mismatch on show A is already recorded when show B's package
    # turns out to have changed: B is still re-planned in place under its own
    # first mismatch, not excluded because A mismatched. (A re-plan normally
    # re-reads every key, so B's stale key is injected into the first re-plan.)
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    a, b = rows[0], rows[1]
    real_planned, real_extend = st.planned_frames, st.extend
    seen: set[str] = set()

    def flaky_once(analysis):
        if analysis.slug == a.slug and a.slug not in seen:
            seen.add(a.slug)
            return real_planned(analysis) + 1
        return real_planned(analysis)

    injected = []

    def stale_extend(*args, **kw):
        out = real_extend(*args, **kw)
        if injected:
            return out
        injected.append(True)
        return [dataclasses.replace(r, key="stale-key") if r.slug == b.slug else r for r in out]
    st.planned_frames, st.extend = flaky_once, stale_extend
    report = pipeline.render_step(st, NOW + 15 * 1_000_000)   # lead window reaches B
    assert report.replanned == [a.slug, b.slug]
    new_rows = read_plan(st.ws.plan_path)
    real_key = next(s.key for s in st.scan_now(NOW) if s.slug == b.slug)
    assert [(r.slug, r.start_frame) for r in new_rows[:2]] == [(a.slug, a.start_frame), (b.slug, b.start_frame)]
    assert new_rows[1].key == real_key
    assert st.engine.encoded[:2] == [a.slug, b.slug]
    assert sum("plan-changed" in m for m in logs) == 2


# A publish batch persists a high-water mark of its candidate `last` before the
# horizon PUT. A crash between that PUT and the publish.json save leaves R2
# listing segments up to the high-water mark while local `last` lags behind;
# those keys are immutable and CDN-cached, so plan_step must treat everything
# at or below the mark as possibly listed: never drop it, never re-plan it.

def _crashed_after_horizon(st, first, last, high_water):
    save_publish_state(st.ws, PublishState(epoch_id="etest", first=first, last=last,
                                           runs=[[first, high_water]], high_water=high_water))


def test_plan_step_without_a_plan_resumes_after_the_high_water_mark(tmp_path):
    st, _ = make_station(tmp_path)
    pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    fresh_n = st.epoch.index_at(NOW) + st.start_margin_segments
    high_water = written[len(written) // 2]
    assert high_water + 1 > fresh_n
    _crashed_after_horizon(st, written[0], None, high_water)     # the first batch's save never landed
    st.ws.plan_path.unlink()
    new_rows = pipeline.plan_step(st, NOW)
    assert new_rows[0].run_start and new_rows[0].start_frame == (high_water + 1) * F
    left = {int(name.split(".")[0]) for name in _seg_files(st)}
    assert left == {n for n in written if n <= high_water}


def test_plan_step_recovery_cuts_at_the_high_water_mark(tmp_path):
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    last, high_water = written[2], written[12]
    _crashed_after_horizon(st, written[0], last, high_water)
    before = _seg_files(st)
    later = NOW + 3 * HOUR_US
    new_rows = pipeline.plan_step(st, later)
    boundary = (high_water + 1) * F
    spanning = next(r for r in rows if r.start_frame < boundary < r.end_frame)
    kept = new_rows[:new_rows.index(next(r for r in new_rows if r.run_start and r.start_frame >= boundary))]
    assert kept[-1].slug == spanning.slug and kept[-1].cut_frame == boundary
    assert {n: b for n, b in before.items() if int(n.split(".")[0]) <= high_water} == _seg_files(st)
    assert any("recovery" in m for m in logs)


def test_plan_step_does_not_recover_while_r2_may_list_past_now(tmp_path):
    # last + 1 is due, but R2 may list up to the high-water mark, which is still
    # ahead of now: listeners are on old-plan audio that is already up. A
    # recovery here would cut the show on air at the mark (or leave dead air).
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    last, high_water = written[0], written[-1]
    later = st.epoch.start_us(last + 1)                      # last + 1 is due
    assert high_water > st.epoch.index_at(later) + st.start_margin_segments
    _crashed_after_horizon(st, written[0], last, high_water)
    before = _seg_files(st)
    new_rows = pipeline.plan_step(st, later)
    assert new_rows[:len(rows)] == rows                      # nothing cut, no new run
    assert not any(r.run_start for r in new_rows[1:])
    assert _seg_files(st) == before
    assert not any("recovery" in m for m in logs)
