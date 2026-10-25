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
