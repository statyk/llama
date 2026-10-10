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
