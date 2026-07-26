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


def test_help_orders_and_panels_commands():
    from typer.testing import CliRunner
    from llama import cli
    out = CliRunner().invoke(cli.app, ["--help"]).output
    # panels present
    for panel in ["Discover & process", "Inspect & triage", "Act on shows", "Housekeeping"]:
        assert panel in out
    # deliberate order: find before status before ledger
    assert out.index("find") < out.index("status") < out.index("ledger")
