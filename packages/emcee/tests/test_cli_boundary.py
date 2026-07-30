import pytest
from herder import HerderError
from typer.testing import CliRunner

from emcee.cli import app, main_cli
from emcee.errors import EmceeError

runner = CliRunner()


def test_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Voice llama show packages" in result.output


def test_main_cli_renders_emcee_error(monkeypatch, capsys):
    from emcee import cli

    def boom():
        raise EmceeError("station root missing", details=["set [station] root"])
    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as e:
        main_cli()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "error: station root missing" in err
    assert "  set [station] root" in err


def test_main_cli_renders_herder_error(monkeypatch, capsys):
    from emcee import cli

    def boom():
        raise HerderError("no provider configured for tier high")
    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as e:
        main_cli()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "error: no provider configured for tier high" in err
