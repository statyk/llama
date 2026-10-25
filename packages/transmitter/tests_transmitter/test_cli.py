from pathlib import Path

from typer.testing import CliRunner

import transmitter
from transmitter.cli import app
from transmitter.config import DEFAULT_CONFIG_TOML


def test_version():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == transmitter.__version__


def test_config_init_writes_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path))
    runner = CliRunner()
    first = runner.invoke(app, ["config", "init"])
    assert first.exit_code == 0
    assert (tmp_path / "config.toml").read_text() == DEFAULT_CONFIG_TOML
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]
    second = runner.invoke(app, ["config", "init"])
    assert second.exit_code == 1


def test_config_init_stdout():
    result = CliRunner().invoke(app, ["config", "init", "--stdout"])
    assert result.exit_code == 0 and result.output == DEFAULT_CONFIG_TOML

from tests_transmitter.helpers import FakeBucket, FakeEngine, build_package, make_root
from transmitter import aacenc, fallback, service
from transmitter.state import save_fallback_version
from transmitter.workspace import Workspace

REPO = Path(__file__).resolve().parents[3]


def _config(tmp_path, root):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[station]\nroot = "{root}"\nquiet_minutes = 0.0\n'
        '[planner]\nstart_delay_minutes = 0.5\n'
        '[render]\nlead_hours = 0.1\nlow_water_hours = 0.05\n'
        '[publish]\nbucket = "b"\n'
        f'[antenna]\ndir = "{REPO / "antenna"}"\n'
    )
    return path


def test_status_before_anything(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0 and "no epoch yet" in result.output


def test_plan_command(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    result = CliRunner().invoke(app, ["plan", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    assert "band-2005-11-01" in result.output
    assert (tmp_path / "tx" / "plan.jsonl").exists()


def test_run_once_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    root = make_root(tmp_path)
    for i in (1, 2):
        build_package(root, f"band-2005-11-0{i}")
    save_fallback_version(Workspace(tmp_path / "tx"), "v0")    # `fallback render` ran first
    result = CliRunner().invoke(app, ["run", "--once", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    keys = set(bucket.objects)
    assert any(k.startswith("seg/") for k in keys)
    assert {"state/horizon.json", "timeline.json"} <= keys
    assert any(k.startswith("notes/") for k in keys) and any(k.startswith("show/") for k in keys)


def test_publish_without_a_bucket_is_a_config_error(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    path = tmp_path / "c.toml"
    path.write_text(f'[station]\nroot = "{root}"\n')
    result = CliRunner().invoke(app, ["publish", "--config", str(path)])
    assert result.exit_code != 0 and "bucket" in str(result.exception)


def _fallback_setup(tmp_path, monkeypatch, with_horizon):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    cfgp = _config(tmp_path, root)
    if with_horizon:
        save_fallback_version(Workspace(tmp_path / "tx"), "v0")    # an earlier fallback render
        assert CliRunner().invoke(app, ["run", "--once", "--config", str(cfgp)]).exit_code == 0
    build = fallback.FallbackBuild("v1", (b"s0", b"s1"), b"nn")
    monkeypatch.setattr(fallback, "build_fallback", lambda *a, **k: build)
    monkeypatch.setattr(aacenc, "extra_frames", lambda ffmpeg: 1)
    loop = tmp_path / "loop.wav"
    loop.write_bytes(b"x")
    return cfgp, loop, bucket


def test_fallback_render_reports_horizon_updated(tmp_path, monkeypatch):
    cfgp, loop, bucket = _fallback_setup(tmp_path, monkeypatch, with_horizon=True)
    result = CliRunner().invoke(app, ["fallback", "render", str(loop), "--config", str(cfgp)])
    assert result.exit_code == 0, result.output
    assert "horizon updated" in result.output and "fallback/v1/notice.aac" in bucket.objects
    assert bucket.json("state/horizon.json")["fallback_version"] == "v1"


def test_fallback_render_reports_horizon_deferred(tmp_path, monkeypatch):
    cfgp, loop, bucket = _fallback_setup(tmp_path, monkeypatch, with_horizon=False)
    result = CliRunner().invoke(app, ["fallback", "render", str(loop), "--config", str(cfgp)])
    assert result.exit_code == 0, result.output
    assert "horizon deferred" in result.output and "state/horizon.json" not in bucket.objects



def _publish_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    save_fallback_version(Workspace(tmp_path / "tx"), "v0")        # `fallback render` ran first
    return _config(tmp_path, root), bucket


def test_publish_exits_zero_when_clean_or_empty(tmp_path, monkeypatch):
    cfgp, bucket = _publish_setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["publish", "--config", str(cfgp)])   # nothing rendered yet
    assert result.exit_code == 0, result.output
    assert CliRunner().invoke(app, ["render", "--config", str(cfgp)]).exit_code == 0
    result = CliRunner().invoke(app, ["publish", "--config", str(cfgp)])
    assert result.exit_code == 0, result.output
    assert any(k.startswith("seg/") for k in bucket.objects)


def test_publish_exits_nonzero_when_the_put_budget_stops_it(tmp_path, monkeypatch):
    cfgp, bucket = _publish_setup(tmp_path, monkeypatch)
    assert CliRunner().invoke(app, ["render", "--config", str(cfgp)]).exit_code == 0
    cfgp.write_text(cfgp.read_text().replace('bucket = "b"', 'bucket = "b"\ndaily_put_budget = 2'))
    result = CliRunner().invoke(app, ["publish", "--config", str(cfgp)])
    assert result.exit_code == 1
    assert "put-budget" in result.output      # stderr is mixed into output by CliRunner


def test_publish_exits_nonzero_when_the_guard_is_tripped(tmp_path, monkeypatch):
    cfgp, bucket = _publish_setup(tmp_path, monkeypatch)
    assert CliRunner().invoke(app, ["render", "--config", str(cfgp)]).exit_code == 0
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": true}', "ContentType": "x", "CacheControl": "x"}
    result = CliRunner().invoke(app, ["publish", "--config", str(cfgp)])
    assert result.exit_code == 1 and "guard" in result.output


def test_publish_exits_nonzero_until_a_fallback_is_rendered(tmp_path, monkeypatch):
    cfgp, bucket = _publish_setup(tmp_path, monkeypatch)
    (tmp_path / "tx" / "fallback.json").unlink()
    assert CliRunner().invoke(app, ["render", "--config", str(cfgp)]).exit_code == 0
    result = CliRunner().invoke(app, ["publish", "--config", str(cfgp)])
    assert result.exit_code == 1 and "transmitter fallback render" in result.output
    assert bucket.puts() == []


def test_fallback_render_on_a_fresh_workspace_then_run_publishes_with_its_version(tmp_path, monkeypatch):
    # The documented first start: `fallback render` before any horizon exists
    # defers the horizon but records the version, so the first batch carries it.
    cfgp, loop, bucket = _fallback_setup(tmp_path, monkeypatch, with_horizon=False)
    assert CliRunner().invoke(app, ["fallback", "render", str(loop), "--config", str(cfgp)]).exit_code == 0
    result = CliRunner().invoke(app, ["run", "--once", "--config", str(cfgp)])
    assert result.exit_code == 0, result.output
    assert bucket.json("state/horizon.json")["fallback_version"] == "v1"


def test_run_installs_the_alert_dispatcher_and_clears_it_afterwards(tmp_path, monkeypatch):
    from transmitter import alerts

    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: FakeBucket())
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    save_fallback_version(Workspace(tmp_path / "tx"), "v0")
    sentinel = object()
    built, configured = [], []
    monkeypatch.setattr(alerts, "dispatcher_from_config", lambda cfg, ws: built.append(ws) or sentinel)
    monkeypatch.setattr(alerts, "configure", configured.append)
    result = CliRunner().invoke(app, ["run", "--once", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    assert len(built) == 1 and configured == [sentinel, None]


def test_run_hands_the_runner_the_dead_clock_monitor(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: FakeBucket())
    sentinel = object()
    seen = {}

    class FakeRunner:
        def __init__(self, st, p, **kw):
            seen.update(kw)

        def run(self, max_ticks=None):
            seen.setdefault("run", []).append(max_ticks)

        def run_once(self):
            seen["run_once"] = seen.get("run_once", 0) + 1

    monkeypatch.setattr(service, "open_monitor", lambda st: sentinel)
    monkeypatch.setattr(service, "Runner", FakeRunner)
    root = make_root(tmp_path)
    result = CliRunner().invoke(app, ["run", "--once", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    assert seen["monitor"] is sentinel and seen["run_once"] == 1 and "run" not in seen


def test_plan_and_render_refuse_while_locked(tmp_path, monkeypatch):
    from transmitter.locks import plan_lock
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    cfg = str(_config(tmp_path, root))
    with plan_lock(Workspace(tmp_path / "tx")):
        for cmd in ("plan", "render"):
            result = CliRunner().invoke(app, [cmd, "--config", cfg])
            assert result.exit_code == 1, result.output
            assert type(result.exception).__name__ == "PlanLocked"
            assert "another transmitter plan or render holds the lock" in str(result.exception)
    assert not (tmp_path / "tx" / "plan.jsonl").exists()


def test_announcements_export_writes_missing_scripts_only(tmp_path, monkeypatch):
    import os
    import time

    from transmitter import announce
    from transmitter.clock import load_clock

    root = tmp_path / "ws"
    monkeypatch.setenv("TRANSMITTER_ROOT", str(root))
    station_root = tmp_path / "station"
    folder = station_root / "interstitials"
    folder.mkdir(parents=True)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[station]\nroot = "{station_root}"\n')
    clock = tmp_path / "clock.toml"
    clock.write_text('timezone = "America/New_York"\n\n[[block]]\nname = "a"\ntitle = "Funk"\nstart = "19:00"\n')
    need = announce.needed(load_clock(clock), int(time.time() * 1_000_000), 8)
    texts = {r.id: r.text for r in need}
    assert len(texts) == 2                      # a daily block follows itself: one-block forms only
    present = need[0].id
    clip = folder / f"ann-{present}.mp3"
    clip.write_bytes(b"ID3x")
    os.utime(clip, (time.time() - 3600,) * 2)
    out = tmp_path / "out"
    result = CliRunner().invoke(app, ["announcements", "--config", str(cfg), "--clock", str(clock),
                                      "--export", str(out)])
    assert result.exit_code == 0, result.output
    assert f"{present}  present" in result.output
    others = [i for i in texts if i != present]
    for other in others:
        assert f"{other}  missing  {texts[other]}" in result.output
        assert (out / f"ann-{other}.txt").read_text(encoding="utf-8") == texts[other] + "\n"
    assert sorted(p.name for p in out.iterdir()) == sorted(f"ann-{i}.txt" for i in others)
    assert "exported 1 script(s)" in result.output
    assert not list(root.rglob("clock.last-good.toml"))


GOOD_CLOCK = 'timezone = "America/New_York"\n\n[[block]]\nname = "a"\ntitle = "Funk"\nstart = "19:00"\n'


def _ws(tmp_path, monkeypatch, with_root=True):
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv("TRANSMITTER_ROOT", str(root))
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[station]\nroot = "{tmp_path / "station"}"\n' if with_root else "")
    return root, cfg


def test_announcements_live_clock_writes_no_last_good_copy(tmp_path, monkeypatch):
    root, cfg = _ws(tmp_path, monkeypatch)
    (root / "clock.toml").write_text(GOOD_CLOCK)
    result = CliRunner().invoke(app, ["announcements", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "Stay tuned for Funk at 7 Eastern, 4 Pacific." in result.output
    assert not (root / "clock.last-good.toml").exists()


def test_announcements_invalid_live_clock_notes_and_writes_no_copy(tmp_path, monkeypatch):
    root, cfg = _ws(tmp_path, monkeypatch)
    (root / "clock.toml").write_text("not = [valid")
    result = CliRunner().invoke(app, ["announcements", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "note: " in result.output and "clock" in result.output
    assert not (root / "clock.last-good.toml").exists()


def test_announcements_bad_clock_file_exits_1(tmp_path, monkeypatch):
    _, cfg = _ws(tmp_path, monkeypatch)
    bad = tmp_path / "bad.toml"
    bad.write_text("not = [valid")
    result = CliRunner().invoke(app, ["announcements", "--config", str(cfg), "--clock", str(bad)])
    assert result.exit_code == 1


def test_announcements_notes_a_missing_interstitials_folder(tmp_path, monkeypatch):
    root, cfg = _ws(tmp_path, monkeypatch, with_root=False)
    (root / "clock.toml").write_text(GOOD_CLOCK)
    result = CliRunner().invoke(app, ["announcements", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "note: no interstitials folder (" in result.output
    assert result.output.count("note: no interstitials folder") == 1
    assert "missing" in result.output


# --- schedule, library, status (Task 13) ---------------------------------------

import json  # noqa: E402

from tests_transmitter.helpers import E, add_clip, mark_awaiting_fix  # noqa: E402
from transmitter import announce, clock as clock_mod  # noqa: E402
from transmitter.workspace import write_json  # noqa: E402

_CLOCK = 'timezone = "UTC"\n' + "".join(
    f'[[block]]\nname = "b{h:02d}"\ntitle = "Block {h}"\nstart = "{h:02d}:00"\nprofiles = ["indie"]\n'
    for h in range(0, 24, 2))


def _tree(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def _setup(tmp_path, monkeypatch, *, epoch=True, clock=_CLOCK, ids=(), packages=3):
    tx = tmp_path / "tx"
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tx))
    engine = FakeEngine()
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: engine)
    root = make_root(tmp_path)
    for i in range(packages):
        build_package(root, f"band-2005-11-0{i + 1}")
    for name in ids:
        add_clip(root, f"id-{name}.mp3")
    tx.mkdir()
    if epoch:
        ws = Workspace(tx)
        write_json(ws.epoch_path, {"epoch_id": "etest", "epoch": service.grid.us_to_iso(
            service.now_us() - 3_600_000_000), "d": 10.24})
    if clock is not None:
        (tx / "clock.toml").write_text(clock)
    return tx, root, engine, _config(tmp_path, root)


def test_schedule_writes_nothing(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, ids=("a",))
    (tx / "clock.last-good.toml").write_text("# older\n" + _CLOCK)
    before = _tree(tx)
    result = CliRunner().invoke(app, ["schedule", "--days", "1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "Block" in result.output and "summary" in result.output
    assert _tree(tx) == before                     # clock.last-good.toml, cache/, alerts.json, plan: untouched
    assert engine.analyzed == []                   # no analysis requested


def test_schedule_with_no_epoch_previews_and_creates_none(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, epoch=False)
    result = CliRunner().invoke(app, ["schedule", "--days", "1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "no epoch yet" in result.output
    assert not (tx / "epoch.json").exists()
    assert not (tx / "epoch.lock").exists()


def test_schedule_marks_estimates(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["schedule", "--days", "1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "~" in result.output and "min)" in result.output


def test_schedule_lists_missing_announcement_audio(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, ids=("a",))
    live = clock_mod.load_clock(tx / "clock.toml")
    need = announce.needed(live, service.now_us(), 2)
    assert need
    have = need[0]
    add_clip(root, f"ann-{have.id}.mp3")
    result = CliRunner().invoke(app, ["schedule", "--days", "1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "missing announcement audio" in result.output
    assert f"ann-{need[1].id}.mp3" in result.output and f"ann-{have.id}.mp3" not in result.output
    assert "announcement(s) missing" in result.output


def test_schedule_draft_clock_and_delivered_library(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, clock=None)
    draft = tmp_path / "draft.toml"
    draft.write_text(_CLOCK)
    build_package(root, "unvoiced-2005-11-09", voiced=False)
    result = CliRunner().invoke(app, ["schedule", "--days", "1", "--clock", str(draft), "--library", "delivered",
                                      "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "Block" in result.output
    assert not (tx / "clock.toml").exists()


def test_library_reports_profiles_pool_and_ineligible(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, ids=("hello",))
    mark_awaiting_fix(build_package(root, "held-2005-11-05"))
    build_package(root, "plain-2005-11-06", voiced=False)
    add_clip(root, "ann-abc123def456.mp3")
    result = CliRunner().invoke(app, ["library", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "indie" in out and "3 shows" in out and "median" in out and "p10" in out and "p90" in out
    assert "id-hello" in out and "ann-abc123def456" in out
    assert "awaiting fix from llama" in out and "held-2005-11-05" in out
    assert engine.analyzed == []


def test_status_says_no_clock_open_all_week(tmp_path, monkeypatch):
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, clock=None)
    result = CliRunner().invoke(app, ["status", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "clock      no clock: open all week" in result.output
    assert "anchors" not in result.output


def test_status_reads_persisted_rows_only(tmp_path, monkeypatch):
    from transmitter import scheduler, pipeline
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch, ids=("a",))
    from transmitter.config import load_config
    st = service.open_station(load_config(cfg), service.now_us())
    pipeline.plan_step(st, service.now_us())
    n_analyzed = len(engine.analyzed)

    def boom(*a, **k):
        raise AssertionError("status must not run the scheduler")

    monkeypatch.setattr(scheduler, "project", boom)
    monkeypatch.setattr(service.station, "scan", boom)
    result = CliRunner().invoke(app, ["status", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "clock      clock.toml" in result.output
    assert "block      " in result.output
    assert "last 24 h" in result.output and "next 24 h" in result.output
    assert "announce" in result.output
    assert len(engine.analyzed) == n_analyzed


def test_status_names_the_show_not_the_clip_on_air(tmp_path, monkeypatch):
    from transmitter.layout import PlanRow
    from transmitter.planner import write_plan
    tx, root, engine, cfg = _setup(tmp_path, monkeypatch)
    now = service.now_us()
    ws = Workspace(tx)
    frame = (now - service.load_epoch(ws).epoch_us) * 44_100 // (1024 * 1_000_000)
    write_plan(ws.plan_path, [PlanRow(seq=0, slug="id-hello", dir="interstitials", key="k", start_frame=frame - 10,
                                      frames=1000, run_start=False, kind="interstitial", role="id",
                                      block="b00", nominal_start="2026-11-02T00:00:00Z")])
    result = CliRunner().invoke(app, ["status", "--config", str(cfg)])
    assert "on air     station break" in result.output and "on air     id-hello" not in result.output


def test_status_block_lines_name_the_current_and_next_block(tmp_path, monkeypatch):
    from transmitter import grid, pipeline
    from transmitter.config import load_config
    from transmitter.planner import read_plan
    tx, root, engine, cfg_path = _setup(tmp_path, monkeypatch, ids=("a",))
    cfg = load_config(cfg_path)
    st = service.open_station(cfg, service.now_us())
    pipeline.plan_step(st, service.now_us())
    rows = read_plan(st.ws.plan_path)
    t = st.epoch.epoch_us + (rows[0].start_frame + 10) * grid.FRAME_SAMPLES * 1_000_000 // grid.SAMPLE_RATE
    lines = service.status_lines(cfg, t)
    block = next(l for l in lines if l.startswith("block      "))
    assert block.startswith("block      now Block ") and "; next " in block
    assert any(l.startswith("last 24 h ") and "misses" in l for l in lines)
    assert any(l.startswith("bends      ") for l in lines) and any(l.startswith("degraded   ") for l in lines)
