from typer.testing import CliRunner

from llama.cli import app

runner = CliRunner()


def test_help_shows_description():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Live Music Archive" in result.output


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
