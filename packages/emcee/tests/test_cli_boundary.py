import pytest
from herder import HerderError
from typer.main import get_command
from typer.testing import CliRunner

from emcee.cli import _COMMAND_ORDER, _typed_error, app, main_cli
from emcee.errors import EmceeError

runner = CliRunner()


def test_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Voice llama show packages" in result.output


def test_ordered_panel_group_lists_commands_in_declared_order():
    """Direct coverage of `OrderedPanelGroup`/`_COMMAND_ORDER` -- deferred
    from Task 1, when ordering was unassertable because no real commands
    existed yet. Goes through `list_commands` itself (not a parsed-help-text
    scrape, which is fragile against Rich's wrapping/formatting) so it pins
    the sort behavior precisely enough to catch a mutation to the sort key.
    """
    click_group = get_command(app)
    ctx = click_group.make_context("emcee", [], resilient_parsing=True)
    assert click_group.list_commands(ctx) == _COMMAND_ORDER == \
        ["run", "voice", "status", "presenter", "config"]


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


# ---------------------------------------------------------------------------
# Fix 2 (whole-branch review, Important): _typed_error must NOT type-prefix
# EmceeError (and subclasses) -- their message already reads as a complete
# sentence -- but must still type-prefix an arbitrary bare exception like
# KeyError, whose str() alone is an unlabeled fragment.
# ---------------------------------------------------------------------------


def test_typed_error_does_not_prefix_emcee_error():
    exc = EmceeError("scriptwrite failed fact-checking after retry")
    assert _typed_error(exc) == "scriptwrite failed fact-checking after retry"


def test_typed_error_does_not_prefix_emcee_error_subclass():
    from emcee.presenters import PresenterError

    exc = PresenterError("no presenter 'waldo': /x/presenters/waldo.toml does not exist")
    assert _typed_error(exc) == str(exc)
    assert not _typed_error(exc).startswith("PresenterError:")


def test_typed_error_prefixes_non_emcee_error():
    try:
        {}["filename"]
    except KeyError as exc:
        assert _typed_error(exc) == "KeyError: 'filename'"
