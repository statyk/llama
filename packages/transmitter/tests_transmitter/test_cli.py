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

