import dataclasses
import os
import time

import pytest

from tests_transmitter.helpers import NOW, FakeEngine, make_station, mark_awaiting_fix, payloads, set_age
from transmitter import grid, pipeline, segment, station
from transmitter.errors import FrameCountDrift, LayoutError, PlanError, StationRootError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.layout import segment_pieces
from transmitter.planner import read_plan
from transmitter.state import PublishState, save_publish_state

HOUR_US = 3600 * 1_000_000


def test_plan_step_starts_a_run_ahead_of_now(tmp_path):
    # No clock.toml and no interstitials folder: the scheduler plans the
    # implicit open block, eligible shows back to back with the plain gap.
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    now_n = st.epoch.index_at(NOW)
    assert st.start_margin_segments == 3
    assert rows[0].run_start and rows[0].start_frame == (now_n + 3) * F
    assert rows[-1].end_frame >= st.until_frame(NOW) > rows[-2].end_frame
    for a, b in zip(rows, rows[1:]):
        assert b.start_frame == a.end_frame + grid.gap_frames(2.0) and not b.run_start
    eligible = {s.slug: s for s in st.scan_now(NOW)}
    assert all(r.kind == "show" and r.role == "show" and r.block == "open" for r in rows)   # no IDs
    assert all(r.slug in eligible and r.key == eligible[r.slug].key and r.package == r.slug for r in rows)
    assert len({r.slug for r in rows}) == len(rows)                   # no repeat while others exist
    assert read_plan(st.ws.plan_path) == rows


def test_a_show_measuring_no_frames_is_skipped_not_fatal(tmp_path, monkeypatch):
    st, logs = make_station(tmp_path)
    victim = pipeline.plan_step(make_station(tmp_path / "probe")[0], NOW)[0].slug
    real = st.planned_frames
    st.planned_frames = lambda a: 0 if a.slug == victim else real(a)
    rows = pipeline.plan_step(st, NOW)
    assert victim not in {r.slug for r in rows}
    assert any(m.startswith(f"skipping {victim}: ") and "0 frames" in m for m in logs)


def test_nothing_eligible_is_a_plan_error_only_when_planning_is_needed(tmp_path):
    st, _ = make_station(tmp_path)
    with pytest.raises(PlanError, match="no eligible packages"):
        st.extend([], [], NOW, start_frame=0, run_start=True)
    rows = pipeline.plan_step(st, NOW)
    assert st.extend(rows, [], NOW, start_frame=next_start(rows, st.gap_frames), run_start=False) == rows


def test_scan_pieces_analyses_clips_unless_read_only(tmp_path):
    from transmitter.errors import RenderError

    class BadClip(FakeEngine):
        def analyze(self, show):
            if show.slug == "id-bad":
                raise RenderError("id-bad: not audio")
            return super().analyze(show)

    st, logs = make_station(tmp_path, engine=BadClip(clip_samples=CLIP_SAMPLES), ids=("a", "bad"))
    ro = st.scan_pieces(NOW, read_only=True)
    assert st.engine.analyzed == [] and logs == []
    assert {(p.kind, p.slug, p.exact) for p in ro if p.kind == "interstitial"} == \
        {("interstitial", "id-a", False), ("interstitial", "id-bad", False)}
    pool = st.scan_pieces(NOW)
    clips = [p for p in pool if p.kind == "interstitial"]
    assert [(p.slug, p.exact, p.dir) for p in clips] == [("id-a", True, "interstitials")]
    assert clips[0].frames == exact_frames(st, clips[0].show)
    assert logs == ["skipping id-bad: id-bad: not audio"]
    assert {p.slug for p in pool if p.kind == "show"} == {s.slug for s in st.scan_now(NOW)}


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


def test_render_step_pings_after_its_own_analysis_before_the_encode(tmp_path):
    events: list[str] = []

    class Spy(FakeEngine):
        def analyze(self, show):
            events.append("analyze")
            return super().analyze(show)

        def encode_show(self, show, analysis, out):
            events.append("encode")
            return super().encode_show(show, analysis, out)

    st, _ = make_station(tmp_path, engine=Spy())
    pipeline.plan_step(st, NOW)
    events.clear()
    pipeline.render_step(st, NOW, notify=lambda m: events.append("ping" if m == "WATCHDOG=1" else m))
    assert "analyze" in events and "encode" in events
    for i, e in enumerate(events):
        if e == "analyze":
            assert events[i + 1] == "ping"                       # fed before the encode starts


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


def _count_projections(monkeypatch) -> list[int]:
    calls: list[int] = []
    real = pipeline.project

    def counted(*a, **kw):
        calls.append(1)
        return real(*a, **kw)
    monkeypatch.setattr(pipeline, "project", counted)
    return calls


def test_plan_step_pings_the_watchdog_after_each_analysis(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path, n_packages=3)
    pings: list[str] = []
    st.notify = pings.append
    projections = _count_projections(monkeypatch)
    pipeline.plan_step(st, NOW)
    assert len(st.engine.analyzed) >= 1
    assert pings.count("WATCHDOG=1") == len(st.engine.analyzed) + len(projections)


def test_render_steps_replan_path_pings_too(tmp_path, monkeypatch):
    st, _ = make_station(tmp_path, n_packages=3)
    pings: list[str] = []
    st.notify = pings.append
    projections = _count_projections(monkeypatch)
    st.extend([], st.scan_pieces(NOW), NOW, start_frame=0, run_start=True)
    assert len(st.engine.analyzed) >= 1
    assert pings.count("WATCHDOG=1") == len(st.engine.analyzed) + len(projections)


def test_a_failed_analysis_still_pings(tmp_path, monkeypatch):
    from transmitter.errors import RenderError

    class FailingEngine(FakeEngine):
        def analyze(self, show):
            if show.slug.endswith("-02"):
                self.analyzed.append(show.slug)
                raise RenderError(f"{show.slug}: simulated analysis failure")
            return super().analyze(show)

    st, logs = make_station(tmp_path, n_packages=3, engine=FailingEngine())
    pings: list[str] = []
    st.notify = pings.append
    projections = _count_projections(monkeypatch)
    pipeline.plan_step(st, NOW)
    assert any("skipping" in m and "-02" in m for m in logs)
    assert len(st.engine.analyzed) >= 2
    assert pings.count("WATCHDOG=1") == len(st.engine.analyzed) + len(projections)


def test_frames_of_without_notify_is_unchanged(tmp_path):
    st, _ = make_station(tmp_path)
    assert st.notify is None
    show = st.scan_now(NOW)[0]
    assert st.frames_of(show) == st.planned_frames(st.engine.analyze(show))


# --- the scheduler drives plan and render ------------------------------------

import json

from tests_transmitter.helpers import add_clip, write_clock
from transmitter import alerts
from transmitter.layout import PlanRow
from transmitter.planner import next_start, write_plan
from transmitter.scheduler import PlannedPiece

MIN_SAMPLES = 60 * 44_100
CLIP_SAMPLES = 10 * 44_100


def short_clock(hours=(0, 2, 5, 7, 10, 12, 15, 17, 20, 22), prefix="b", wiggle=20) -> str:
    """Short, mixed blocks (2 h and 3 h; the operator's real clocks mostly use
    2-3 h blocks), all titled, alternately open, indie-only, open, jazz-only."""
    lines = ['timezone = "America/New_York"', f"wiggle_minutes = {wiggle}"]
    profiles = ([], ["indie"], [], ["jazz"])
    for i, h in enumerate(hours):
        lines += ["[[block]]", f'name = "{prefix}{h:02d}"', f'title = "Block {prefix}{h:02d}"',
                  f'start = "{h:02d}:00"']
        if profiles[i % 4]:
            lines.append(f"profiles = {json.dumps(profiles[i % 4])}")
    return "\n".join(lines) + "\n"


def library(n=8):
    """`n` packages by different artists, alternately indie and jazz."""
    return [{"slug": f"act{i:02d}-19{70 + i}-05-0{1 + i % 9}", "artist": f"Act {i}",
             "date": f"19{70 + i}-05-0{1 + i % 9}", "profile": ("indie", "jazz")[i % 2]} for i in range(n)]


def clock_station(tmp_path, *, clock="short", n=8, ids=("a", "b", "c"), lead_hours=1.5,
                  show_minutes=4, engine=None, **kw):
    """20-minute shows (5 files of `show_minutes`), 10 s station IDs, short blocks."""
    engine = engine or FakeEngine(samples_per_file=show_minutes * MIN_SAMPLES, clip_samples=CLIP_SAMPLES)
    return make_station(tmp_path, engine=engine, clock=short_clock() if clock == "short" else clock,
                        lead_hours=lead_hours, packages=library(n), ids=ids, **kw)


def exact_frames(st, show):
    return st.planned_frames(st.engine.analyze(show))


def _publish_through(st, t_us):
    """Mark segments published through `t_us`'s segment (+1), so a plan step at
    t_us extends the plan instead of recovering."""
    rows = read_plan(st.ws.plan_path)
    first = rows[0].start_frame // F
    _publish_up_to(st, first, max(first, st.epoch.index_at(t_us) + 1))


def _gap_ok(rows, gap):
    return all(b.start_frame == a.end_frame + gap and not b.run_start for a, b in zip(rows, rows[1:]))


def test_written_rows_always_carry_exact_frames(tmp_path):
    st, _ = clock_station(tmp_path)
    pool = st.scan_pieces(NOW)
    estimates = {p.slug: p.frames for p in pool if p.kind == "show"}
    assert estimates and not any(p.exact for p in pool if p.kind == "show")
    rows = pipeline.plan_step(st, NOW)
    shows = {s.slug: s for s in st.scan_now(NOW)}
    clips = {p.slug: p.show for p in pool if p.kind == "interstitial"}
    assert any(r.kind == "interstitial" for r in rows) and any(r.kind == "show" for r in rows)
    for r in rows:
        exact = exact_frames(st, shows[r.slug] if r.kind == "show" else clips[r.slug])
        assert r.frames == exact
        if r.kind == "show":
            assert estimates[r.slug] != exact          # the estimate never reaches a written row
    assert read_plan(st.ws.plan_path) == rows


def _scripted_project(monkeypatch, script):
    """Replace the scheduler with `script(call_index, inp) -> PlannedPiece`."""
    calls = []

    def fake(inp, *, until_frame=None, ahead=2):
        calls.append(inp)
        return [script(len(calls) - 1, inp)]
    monkeypatch.setattr(pipeline, "project", fake)
    return calls


def _pp(piece, inp, **kw):
    return PlannedPiece(piece, inp.start_frame, inp.run_start, kw.pop("block", "b05"),
                        kw.pop("nominal", "2096-10-02T09:00:00.000Z"), kw.pop("role", "show"), **kw)


def test_run2_pick_unanalysed_falls_back_to_run1(tmp_path, monkeypatch):
    st, _ = clock_station(tmp_path)
    pool = st.scan_pieces(NOW)
    a, b = [p for p in pool if p.kind == "show"][:2]

    def script(i, inp):
        if i == 0:
            return _pp(a, inp, miss=False)
        assert next(p for p in inp.pool if p.slug == a.slug).exact      # run 2 sees a's exact count
        return _pp(b, inp, miss=True)                                    # b is still an estimate
    calls = _scripted_project(monkeypatch, script)
    rows = st.extend([], pool, NOW, start_frame=0, run_start=True, max_new=1)
    assert len(calls) == 2
    assert [r.slug for r in rows] == [a.slug] and rows[0].miss is False
    assert rows[0].frames == exact_frames(st, a.show) != a.frames
    assert [s for s in st.engine.analyzed if not s.startswith("id-")].count(b.slug) == 0


def test_run2_pick_is_appended_when_analysed(tmp_path, monkeypatch):
    st, _ = clock_station(tmp_path)
    pool = st.scan_pieces(NOW)
    a = next(p for p in pool if p.kind == "show")
    clip = next(p for p in pool if p.kind == "interstitial")
    assert clip.exact

    def script(i, inp):
        return _pp(a, inp) if i == 0 else _pp(clip, inp, role="id")
    _scripted_project(monkeypatch, script)
    rows = st.extend([], pool, NOW, start_frame=0, run_start=True, max_new=1)
    assert [(r.slug, r.kind, r.frames) for r in rows] == [(clip.slug, "interstitial", clip.frames)]


def test_an_exact_run1_pick_is_appended_without_a_second_run(tmp_path, monkeypatch):
    st, _ = clock_station(tmp_path)
    pool = st.scan_pieces(NOW)
    clip = next(p for p in pool if p.kind == "interstitial")
    calls = _scripted_project(monkeypatch, lambda i, inp: _pp(clip, inp, role="id"))
    rows = st.extend([], pool, NOW, start_frame=0, run_start=True, max_new=1)
    assert len(calls) == 1 and [r.slug for r in rows] == [clip.slug]


def test_at_least_one_row_per_step_while_short(tmp_path):
    from transmitter.errors import RenderError

    class MostlyFailing(FakeEngine):
        def analyze(self, show):
            if not show.meta.get("role") and not show.slug.startswith(("act03", "act04")):
                self.analyzed.append(show.slug)
                raise RenderError(f"{show.slug}: simulated analysis failure")
            return super().analyze(show)

    st, logs = clock_station(tmp_path, engine=MostlyFailing(samples_per_file=4 * MIN_SAMPLES,
                                                            clip_samples=CLIP_SAMPLES))
    rows: list = []
    steps = 0
    while not rows or rows[-1].end_frame < st.until_frame(NOW):
        before = len(rows)
        rows = pipeline.plan_step(st, NOW, max_new=1)
        assert len(rows) == before + 1
        steps += 1
        assert steps < 40
    assert steps >= 3
    assert {r.slug for r in rows if r.kind == "show"} <= {s["slug"] for s in library()[3:5]}
    assert any(m.startswith("skipping act0") for m in logs)
    assert pipeline.plan_step(st, NOW, max_new=1) == rows             # covered: nothing more


def test_appended_rows_obey_the_gap_layout(tmp_path, monkeypatch):
    st, _ = clock_station(tmp_path)
    gap = st.gap_frames
    rows = pipeline.plan_step(st, NOW)
    assert rows[0].run_start and any(r.kind == "interstitial" for r in rows)
    assert _gap_ok(rows, gap)
    later = NOW + HOUR_US
    _publish_through(st, later)
    more = pipeline.plan_step(st, later)
    assert more[:len(rows)] == rows and len(more) > len(rows)
    assert _gap_ok(more[len(rows) - 1:], gap)
    # the internal-bug guard: a piece laid out anywhere else is refused
    pool = st.scan_pieces(later)
    show = next(p for p in pool if p.kind == "show" and p.exact)
    _scripted_project(monkeypatch, lambda i, inp: dataclasses.replace(_pp(show, inp),
                                                                       start_frame=inp.start_frame - 1))
    with pytest.raises(LayoutError, match="gap"):
        st.extend(more, pool, later + 3 * HOUR_US, start_frame=next_start(more, gap), run_start=False)


def test_multi_row_extend_never_repeats_a_show_or_id_while_alternatives_exist(tmp_path):
    st, _ = clock_station(tmp_path, n=10, lead_hours=2.5)
    start = (st.epoch.index_at(NOW) + 3) * F
    rows = st.extend([], st.scan_pieces(NOW), NOW, start_frame=start, run_start=True)
    shows = [r.slug for r in rows if r.kind == "show"]
    ids = [r.slug for r in rows if r.role == "id"]
    assert len(shows) >= 6 and len(ids) >= 4
    assert len(shows) == len(set(shows))
    assert all(len(set(ids[i:i + 3])) == 3 for i in range(len(ids) - 2))
    assert rows[-1].end_frame >= st.until_frame(NOW) > rows[-2].end_frame
    assert _gap_ok(rows, st.gap_frames)


def test_extend_feeds_the_watchdog_after_each_projection(tmp_path, monkeypatch):
    st, _ = clock_station(tmp_path)
    events: list[str] = []
    st.notify = lambda msg: events.append("ping" if msg == "WATCHDOG=1" else msg)
    real = pipeline.project

    def counted(*a, **kw):
        out = real(*a, **kw)
        events.append("project")
        return out
    monkeypatch.setattr(pipeline, "project", counted)
    pipeline.plan_step(st, NOW)
    n_project = events.count("project")
    assert n_project >= 3
    assert all(events[i + 1] == "ping" for i, e in enumerate(events) if e == "project")
    assert events.count("ping") == n_project + len(st.engine.analyzed)


def test_append_only_under_a_clock_edit(tmp_path):
    st, _ = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    lines = st.ws.plan_path.read_text().splitlines()
    write_clock(st.ws, short_clock(hours=(1, 3, 6, 8, 11, 13, 16, 18, 21, 23), prefix="c"))
    later = NOW + HOUR_US
    _publish_through(st, later)
    new = pipeline.plan_step(st, later)
    assert len(new) > len(rows)
    assert new[:len(rows)] == rows                                     # every persisted row, in place
    assert st.ws.plan_path.read_text().splitlines()[:len(lines)] == lines
    assert {r.block[0] for r in new[len(rows):]} == {"c"}              # planned on the edited clock
    assert _gap_ok(new[len(rows) - 1:], st.gap_frames)


def test_invalid_clock_alerts_and_plans_with_last_good(tmp_path, monkeypatch):
    fired, resolved = [], []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: fired.append((code, msg)))
    monkeypatch.setattr(alerts, "resolve", resolved.append)
    st, _ = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    assert fired == [] and "clock" in resolved
    assert st.ws.clock_last_good_path.read_text() == short_clock()
    write_clock(st.ws, short_clock().replace('start = "05:00"', 'start = "25:00"'))
    later = NOW + HOUR_US
    _publish_through(st, later)
    new = pipeline.plan_step(st, later)
    assert len(new) > len(rows) and new[:len(rows)] == rows
    assert {r.block[0] for r in new[len(rows):]} == {"b"}              # the last good clock's blocks
    assert {c for c, _ in fired} == {"clock"}
    msg = fired[0][1]
    assert str(st.ws.clock_path) in msg and "25:00" in msg
    assert msg.endswith("; planning with the last-good clock")
    assert "\n" not in msg and "errors.pydantic.dev" not in msg and len(msg) < 400
    assert st.ws.clock_last_good_path.read_text() == short_clock()     # never overwritten by a bad clock


def test_no_clock_plans_on_the_implicit_open_block(tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: fired.append(code))
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    assert {r.block for r in rows} == {"open"} and fired == []
    assert not st.ws.clock_last_good_path.exists()


def _clip_path(st, slug):
    return st.cfg.station.root / "interstitials" / f"{slug}.mp3"


def test_render_skips_a_vanished_interstitial_and_moves_on(tmp_path):
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    i, victim = next((i, r) for i, r in enumerate(rows) if i > 0 and r.kind == "interstitial")
    _clip_path(st, victim.slug).unlink()
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim.slug]
    new = read_plan(st.ws.plan_path)
    assert new[:i] == rows[:i]                                         # rows before it untouched
    assert new[i].start_frame == victim.start_frame
    assert victim.slug not in {r.slug for r in new[i:]}
    assert _gap_ok(new[i - 1:], st.gap_frames)
    assert any("plan-changed" in m and victim.slug in m for m in logs)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))


def test_render_drops_a_changed_clip_for_the_rest_of_the_call(tmp_path):
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    i, victim = next((i, r) for i, r in enumerate(rows) if i > 0 and r.kind == "interstitial")
    path = _clip_path(st, victim.slug)
    path.write_bytes(path.read_bytes() + b"re-recorded")                 # file-set key changes
    os.utime(path, (time.time() - 3600,) * 2)
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim.slug]
    new = read_plan(st.ws.plan_path)
    assert new[:i] == rows[:i] and new[i].start_frame == victim.start_frame
    assert victim.slug not in {r.slug for r in new[i:]}
    assert any("plan-changed" in m and victim.slug in m and "clip changed" in m for m in logs)
    assert report.covered


def test_render_skips_a_row_of_unknown_kind(tmp_path):
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    i = 2
    odd = dataclasses.replace(rows[i], kind="jingle", key="k-jingle")
    write_plan(st.ws.plan_path, rows[:i] + [odd] + rows[i + 1:])
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [odd.slug]
    new = read_plan(st.ws.plan_path)
    assert new[:i] == rows[:i] and new[i].start_frame == odd.start_frame
    assert "jingle" not in {r.kind for r in new}
    assert any("plan-changed" in m and "jingle" in m for m in logs)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))


def test_render_replan_cap(tmp_path):
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    real = st.extend

    def always_odd(kept, pool, now_us, *, start_frame, run_start, max_new=None):
        # every re-plan puts an unknown-kind row where the skipped one was
        out = real(kept, pool, now_us, start_frame=start_frame, run_start=run_start, max_new=max_new)
        i = len(kept)
        return out[:i] + [dataclasses.replace(out[i], kind="jingle", key=f"k-odd-{len(logs)}")] + out[i + 1:]
    st.extend = always_odd
    plan = rows[:1] + [dataclasses.replace(rows[1], kind="jingle", key="k-odd")] + rows[2:]
    write_plan(st.ws.plan_path, plan)
    from transmitter.layout import rows_overlapping
    first_n = rows[0].start_frame // F
    target = st.epoch.index_at(NOW + st.lead_us)
    clips = sum(p.kind == "interstitial" for p in st.scan_pieces(NOW))
    cap = clips + len(rows_overlapping(plan, first_n * F, (target + 1) * F)) + 10
    with pytest.raises(PlanError, match=f"render re-planned {cap} times in one call; stopping"):
        pipeline.render_step(st, NOW)
    assert sum("plan-changed" in m for m in logs) == cap
    assert read_plan(st.ws.plan_path)[0] == rows[0]


def test_interstitial_rows_are_rendered_from_the_clip_folder(tmp_path):
    st, logs = clock_station(tmp_path, quiet_minutes=10)
    fresh = add_clip(st.cfg.station.root, "id-fresh.mp3", mtime_s=NOW / 1e6 - 60)   # inside the quiet period
    pool = st.scan_pieces(NOW)
    assert "id-fresh" not in {p.slug for p in pool}
    rows = pipeline.plan_step(st, NOW)
    assert "id-fresh" not in {r.slug for r in rows}
    clip_row = next(r for r in rows if r.kind == "interstitial")
    assert clip_row.dir == "interstitials" and clip_row.role == "id"
    report = pipeline.render_step(st, NOW)
    assert clip_row.slug in st.engine.encoded
    n = clip_row.start_frame // F + 1                                  # a segment inside the clip
    assert n in report.written
    got = payloads(_seg(st, n)[1])
    assert any(p.startswith(f"{clip_row.key}:") for p in got)
    assert fresh.exists()


def _occurrence(clock_text, name, local_day="2096-10-02"):
    from transmitter.clock import _parse, occurrences
    from pathlib import Path
    ck = _parse(clock_text, Path("clock.toml"))
    for o in occurrences(ck, NOW - 2 * 24 * HOUR_US, NOW + 2 * 24 * HOUR_US):
        if o.block.name == name and str(o.local_date) == local_day:
            return o
    raise LookupError(name)


def _persisted_ann_then_extend(st, x, ann_at_us, *, names):
    """Persist [show, `next` announcement for X] ending near `ann_at_us`, then
    append X's first show."""
    gap = st.gap_frames
    first = (st.epoch.index_at(ann_at_us) - 200) * F
    show = PlanRow(seq=0, slug="act00-1970-05-01", dir="act00-1970-05-01", key="k-old", start_frame=first,
                   frames=200 * F - gap - 400, run_start=True, kind="show", block="b02",
                   nominal_start="2096-10-02T06:00:00.000Z", role="show", miss=False,
                   package="act00-1970-05-01")
    ann = PlanRow(seq=1, slug="ann-x", dir="interstitials", key="k-ann", start_frame=show.end_frame + gap,
                  frames=400, kind="interstitial", block=x.block.name, nominal_start=x.nominal_iso,
                  role="next", names=names)
    rows = [show, ann]
    pool = [p for p in st.scan_pieces(NOW)]
    return rows, st.extend(rows, pool, NOW, start_frame=next_start(rows, gap), run_start=False, max_new=1)


def test_announcement_broken_marked_on_the_named_blocks_first_show(tmp_path):
    st, logs = clock_station(tmp_path)
    x = _occurrence(short_clock(), "b05")
    # X's first show starts an hour after its nominal start: outside its 20-minute window
    rows, out = _persisted_ann_then_extend(st, x, x.nominal_us + HOUR_US, names=((x.block.name, x.nominal_iso),))
    first = out[len(rows)]
    assert out[:len(rows)] == rows
    assert (first.kind, first.block, first.nominal_start, first.miss) == ("show", "b05", x.nominal_iso, True)
    assert first.announcement_broken is True
    assert any(m == f"announcement-broken: b05 {x.nominal_iso}" for m in logs)


def test_announcement_kept_or_not_made_is_not_broken(tmp_path):
    st, logs = clock_station(tmp_path)
    x = _occurrence(short_clock(), "b05")
    # on time: the promise held
    rows, out = _persisted_ann_then_extend(st, x, x.nominal_us, names=((x.block.name, x.nominal_iso),))
    assert out[len(rows)].miss is False and out[len(rows)].announcement_broken is False
    # late, but no persisted announcement names X
    st2, logs2 = clock_station(tmp_path / "2")
    rows, out = _persisted_ann_then_extend(st2, x, x.nominal_us + HOUR_US, names=(("b02", "2096-10-02T06:00:00.000Z"),))
    assert out[len(rows)].miss is True and out[len(rows)].announcement_broken is False
    assert not any("announcement-broken" in m for m in logs + logs2)


# --- required scenarios (spec "Testing") --------------------------------------

def test_scenario_clock_edit_mid_fill(tmp_path):
    st, _ = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW, max_new=1)
    rows = pipeline.plan_step(st, NOW, max_new=1)                      # filling, one row per tick
    assert len(rows) == 2
    write_clock(st.ws, short_clock(hours=(1, 4, 6, 9, 11, 14, 16, 19, 21, 23), prefix="c"))
    while rows[-1].end_frame < st.until_frame(NOW):
        before = rows
        rows = pipeline.plan_step(st, NOW, max_new=1)
        assert rows[:len(before)] == before and len(rows) == len(before) + 1
    assert rows[2].block.startswith("c") and {r.block[0] for r in rows[2:]} == {"c"}
    assert _gap_ok(rows, st.gap_frames)
    report = pipeline.render_step(st, NOW)
    assert report.covered and report.replanned == []


def test_scenario_skip_path_drops_an_interstitial_and_a_show(tmp_path):
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    i_clip = next(i for i, r in enumerate(rows) if i > 0 and r.kind == "interstitial")
    clip = rows[i_clip]
    failing = {r.slug for r in rows[i_clip:] if r.kind == "show"}       # still eligible, but fail to encode
    assert failing
    _clip_path(st, clip.slug).unlink()
    st.engine.fail |= failing
    report = pipeline.render_step(st, NOW)
    assert report.replanned[0] == clip.slug
    dropped_shows = [s for s in report.replanned[1:] if s in failing]
    assert dropped_shows                                              # the re-plan's pick was skipped too
    new = read_plan(st.ws.plan_path)
    assert new[:i_clip] == rows[:i_clip]
    assert clip.slug not in {r.slug for r in new}
    assert not failing & {r.slug for r in new[i_clip:]}
    for slug in [clip.slug] + dropped_shows:
        assert any("plan-changed" in m and slug in m for m in logs)
    assert _gap_ok(new[i_clip - 1:], st.gap_frames)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))
    assert report.covered


def test_scenario_recovery_after_a_guard_stop_longer_than_the_lead(tmp_path):
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    written = pipeline.render_step(st, NOW).written
    last = written[len(written) // 3]
    _publish_up_to(st, written[0], last)                               # then the guard stopped publishing
    later = NOW + 2 * st.lead_us + HOUR_US                             # longer than the lead
    new = pipeline.plan_step(st, later)
    boundary = (last + 1) * F
    kept = [r for r in new if r.start_frame < boundary]
    assert [dataclasses.replace(r, cut_frame=None) for r in kept] == rows[:len(kept)]
    assert kept[-1].end_frame <= boundary
    run = next(r for r in new if r.start_frame >= boundary)
    assert run.run_start and run.start_frame == (st.epoch.index_at(later) + st.start_margin_segments) * F
    assert _gap_ok(new[new.index(run):], st.gap_frames)
    assert any("recovery" in m for m in logs)
    report = pipeline.render_step(st, later)
    assert report.written[0] == run.start_frame // F and report.covered


def test_scenario_show_gap_seconds_change(tmp_path):
    st, _ = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    old_gap = st.gap_frames
    render_cfg = st.cfg.render.model_copy(update={"show_gap_seconds": 5.0})
    st2 = dataclasses.replace(st, cfg=st.cfg.model_copy(update={"render": render_cfg}))
    new_gap = st2.gap_frames
    assert new_gap != old_gap
    later = NOW + HOUR_US
    _publish_through(st, later)
    new = pipeline.plan_step(st2, later)                               # no failure
    assert new[:len(rows)] == rows and _gap_ok(rows, old_gap)          # old rows keep the old gap
    assert _gap_ok(new[len(rows) - 1:], new_gap)                       # new rows use the new one
    report = pipeline.render_step(st2, later)
    assert report.covered and report.replanned == []


def test_scenario_phase1_plan_extended(tmp_path):
    st, _ = clock_station(tmp_path)
    shows = st.scan_now(NOW)
    gap = st.gap_frames
    start = (st.epoch.index_at(NOW) + 3) * F
    old: list = []
    for i, s in enumerate(shows[:2]):
        at = start if not old else old[-1].end_frame + gap
        old.append(PlanRow(seq=i, slug=s.slug, dir=s.dir.name, key=s.key, start_frame=at,
                           frames=exact_frames(st, s), run_start=not old))
    st.ws.root.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps({k: getattr(r, k) for k in ("seq", "slug", "dir", "key", "start_frame", "frames",
                                                           "run_start", "cut_frame")}, sort_keys=True) + "\n"
                   for r in old)
    st.ws.plan_path.write_text(text)
    new = pipeline.plan_step(st, NOW)
    assert new[:2] == old and len(new) > 2
    assert st.ws.plan_path.read_text().startswith(text)                # phase-1 rows byte-identical
    assert all(r.block is not None for r in new[2:])
    assert _gap_ok(new, gap)
    report = pipeline.render_step(st, NOW)
    assert report.covered and report.replanned == []


def test_scenario_crash_between_append_and_render(tmp_path):
    st, _ = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    text = st.ws.plan_path.read_text()
    # the process died here: plan.jsonl written, nothing rendered
    st2, _ = clock_station(tmp_path / "restarted")
    st2 = dataclasses.replace(st2, ws=st.ws, cfg=st.cfg)               # a fresh process on the same workspace
    assert pipeline.plan_step(st2, NOW) == rows
    report = pipeline.render_step(st2, NOW)
    assert report.replanned == [] and report.covered
    assert st.ws.plan_path.read_text() == text
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))


# --- fix round 1 ---------------------------------------------------------------

def test_scenario_skip_path_after_a_show_gap_seconds_change(tmp_path):
    # Rows planned under gap A, some segments rendered, then the operator shrinks
    # the gap to B and a later show fails to encode: the skip path re-plans from
    # the dropped row's OWN start (prev.end + A), never prev.end + B (which could
    # land inside an already-written segment), and lays the new rows with gap B.
    st, logs = clock_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    old_gap = st.gap_frames
    first_n = rows[0].start_frame // F
    assert pipeline.render_step(st, NOW, limit=3).written == [first_n, first_n + 1, first_n + 2]
    i, victim = next((i, r) for i, r in enumerate(rows) if i > 0 and r.kind == "show"
                     and r.start_frame >= (first_n + 3) * F)
    render_cfg = st.cfg.render.model_copy(update={"show_gap_seconds": 0.5})
    st2 = dataclasses.replace(st, cfg=st.cfg.model_copy(update={"render": render_cfg}))
    new_gap = st2.gap_frames
    assert new_gap < old_gap
    st2.engine.fail |= {victim.slug}
    report = pipeline.render_step(st2, NOW)                            # no LayoutError
    assert victim.slug in report.replanned
    new = read_plan(st.ws.plan_path)
    assert new[:i] == rows[:i] and _gap_ok(rows[:i], old_gap)          # old rows keep the old gap
    assert new[i].start_frame == victim.start_frame == new[i - 1].end_frame + old_gap
    assert victim.slug not in {r.slug for r in new[i:]}
    assert _gap_ok(new[i:], new_gap)                                   # later rows use the new gap
    assert report.covered
    assert report.written[-1] == st.epoch.index_at(NOW + st.lead_us)


def test_a_frame_count_change_under_the_same_pause_and_extra_is_re_measured(tmp_path):
    # The count changes while pause and extra do not (so the length cache is not
    # rebuilt): the length this Station learned at plan time must be forgotten,
    # or the in-place re-plan would reuse the stale count and mismatch again.
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    st.engine.samples_per_file += 44_100                               # every show is now longer
    show0 = next(s for s in st.scan_now(NOW) if s.slug == rows[0].slug)
    new_frames = exact_frames(st, show0)
    assert new_frames != rows[0].frames
    report = pipeline.render_step(st, NOW)
    assert report.replanned[0] == rows[0].slug
    assert len(report.replanned) == len(set(report.replanned))         # each re-planned once, in place
    new = read_plan(st.ws.plan_path)
    assert (new[0].slug, new[0].start_frame, new[0].frames) == (rows[0].slug, rows[0].start_frame, new_frames)
    assert st.engine.encoded[0] == rows[0].slug
    assert report.covered


def test_announcement_broken_when_the_named_block_degrades_to_open_time(tmp_path):
    clock = short_clock().replace('start = "05:00"\n', 'start = "05:00"\nprofiles = ["polka"]\n')
    st, logs = clock_station(tmp_path, clock=clock)                    # no polka shows: b05 degrades
    x = _occurrence(clock, "b05")
    rows, out = _persisted_ann_then_extend(st, x, x.nominal_us, names=((x.block.name, x.nominal_iso),))
    first = out[len(rows)]
    assert (first.kind, first.block, first.miss, first.degraded) == ("show", "b05", False, True)
    assert first.announcement_broken is True
    assert f"announcement-broken: b05 {x.nominal_iso}" in logs


def test_render_step_drops_a_planned_show_marked_awaiting_a_fix(tmp_path):
    engine = FakeEngine()
    st, logs = make_station(tmp_path, engine=engine)
    rows = pipeline.plan_step(st, NOW)
    victim = rows[1]
    pkg = st.cfg.station.root / victim.dir
    mark_awaiting_fix(pkg)                                  # manifest only
    assert station.file_set_key(pkg, station.read_m3u(pkg / "broadcast.m3u")) == victim.key
    assert victim.slug not in {s.slug for s in st.scan_now(NOW)}
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim.slug]
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[:1] == rows[:1]
    assert new_rows[1].start_frame == victim.start_frame
    assert victim.slug not in {r.slug for r in new_rows}
    assert victim.slug not in engine.encoded
    assert any("plan-changed" in m and victim.slug in m and "no longer eligible" in m for m in logs)
    assert new_rows[-1].start_frame + new_rows[-1].frames >= rows[-1].start_frame   # plan still covered


def test_render_step_lets_a_marked_show_already_on_air_finish_as_planned(tmp_path):
    engine = FakeEngine()
    st, logs = make_station(tmp_path, engine=engine)
    rows, mid_n = _render_until_mid_show(st)
    victim = rows[1]                                         # mid-render: some segments encoded
    mark_awaiting_fix(st.cfg.station.root / victim.dir)
    assert victim.slug not in {s.slug for s in st.scan_now(NOW)}
    report = pipeline.render_step(st, NOW)                   # no LayoutError, no drop
    assert report.replanned == []
    assert report.written[0] == mid_n
    assert read_plan(st.ws.plan_path) == rows
    assert not any("plan-changed" in m for m in logs)
